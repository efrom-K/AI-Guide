"""Reverse geocoding: GPS point -> Address(country, city, district, street).

This is what lets the guide narrate "от общего к частному" — it has to know the
city / district / street it is standing in before it can descend to the objects
inside them. Public Nominatim is often blocked/limited, so the default provider
reuses the same reachable Overpass endpoint as place discovery: ``is_in`` returns
the administrative areas enclosing the point, and a small ``around`` query finds
the street. Off the hot-path and move-gated by the orchestrator (areas change
slowly), so the extra request is rare.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from app.config import settings
from app.shared.schemas import Address, GeoPoint


class Geocoder(Protocol):
    async def reverse(self, point: GeoPoint, language: str = "ru") -> Address: ...


# OSM admin_level is locale-dependent; these heuristics target the common cases
# (federal cities like Moscow/SPb where the city is level 4, ordinary cities at
# level 6, districts at level 8+). The ``place`` tag, when present, overrides.
_CITY_PLACES = {"city", "town", "village"}
_DISTRICT_PLACES = {"suburb", "borough", "quarter", "neighbourhood", "city_district", "district"}


def _name(tags: dict, language: str) -> str | None:
    for key in (f"name:{language}", "name:ru", "name:en", "name", "int_name"):
        v = tags.get(key)
        if v:
            return v
    return None


def parse_address(elements: list[dict], language: str = "ru") -> Address:
    """Pure parse of an Overpass ``is_in`` + nearby-street response into an Address."""
    admins: dict[int, str] = {}  # admin_level -> name
    city = district = country = street = None
    for el in elements:
        tags = el.get("tags") or {}
        name = _name(tags, language)
        if not name:
            continue
        place = tags.get("place")
        if place in _CITY_PLACES and not city:
            city = name
        if place in _DISTRICT_PLACES and not district:
            district = name
        if tags.get("highway") and not street:
            street = name
            continue
        lvl = tags.get("admin_level")
        if lvl and lvl.isdigit():
            admins.setdefault(int(lvl), name)

    if 2 in admins:
        country = admins[2]
    # city: an ordinary city sits at level 6; a federal city (Moscow) at level 4.
    # Skip the macro levels 3 (federal district) and 5 (admin okrug).
    if not city:
        city = admins.get(6) or admins.get(4)
    # district: the most specific local area (largest admin_level >= 7).
    if not district:
        deep = [lvl for lvl in admins if lvl >= 7]
        if deep:
            district = admins[max(deep)]
    return Address(country=country, city=city, district=district, street=street)


class OverpassGeocoder:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or settings.overpass_url

    @staticmethod
    def _query(point: GeoPoint) -> str:
        lat, lon = point.lat, point.lon
        return (
            "[out:json][timeout:25];"
            f"is_in({lat},{lon})->.a;"
            "area.a[admin_level];out tags;"
            f"way(around:35,{lat},{lon})[highway][name];out tags 3;"
        )

    async def reverse(self, point: GeoPoint, language: str = "ru") -> Address:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self.url, data={"data": self._query(point)})
            resp.raise_for_status()
            return parse_address(resp.json().get("elements", []), language)


class MockGeocoder:
    """Returns a fixed address — for tests and offline/dev runs."""

    def __init__(self, address: Address) -> None:
        self._address = address

    async def reverse(self, point: GeoPoint, language: str = "ru") -> Address:
        return self._address


class NullGeocoder:
    """No reverse geocoding — empty address (the guide just won't name the area)."""

    async def reverse(self, point: GeoPoint, language: str = "ru") -> Address:
        return Address()
