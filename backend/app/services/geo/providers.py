"""Place providers: a real Overpass client and a static one for tests/sim.

Both satisfy the ``PlaceProvider`` protocol so the discovery layer is agnostic
to the source (live API vs. cached fixtures vs. virtual walk).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx

from app.config import settings
from app.shared.geo_math import haversine_m
from app.shared.schemas import GeoPoint, Place

from .categories import KEEP_TAGS, classify


@runtime_checkable
class PlaceProvider(Protocol):
    async def fetch_places(self, center: GeoPoint, radius_m: float) -> list[Place]: ...


# --------------------------------------------------------------------------- #
# Overpass (live)
# --------------------------------------------------------------------------- #
_SELECTORS = (
    '"tourism"',
    '"historic"',
    '"amenity"="place_of_worship"',
    '"amenity"~"theatre|cinema|arts_centre|fountain"',
    '"leisure"~"park|garden|nature_reserve"',
    # nature & water — so the guide notices reservoirs, rivers, lakes, forests, hills
    '"natural"~"water|wood|peak|bay|beach|cape|cliff|spring|waterfall|volcano|glacier|wetland"',
    '"water"',
    '"waterway"~"river|canal|waterfall|dam"',
    '"landuse"~"reservoir|forest"',
    # notable man-made structures
    '"man_made"~"bridge|tower|lighthouse|watermill|windmill|pier|obelisk"',
)


def build_query(center: GeoPoint, radius_m: float) -> str:
    r = int(radius_m)
    body = "".join(
        f"{kind}(around:{r},{center.lat},{center.lon})[{sel}];"
        for sel in _SELECTORS
        for kind in ("node", "way")
    )
    # "geom" (not "center") so linear/area features (rivers, canals, bays) report
    # their geometry — we then snap to the point nearest the user, not the way's
    # midpoint, which for a long canal sits kilometres away.
    return f"[out:json][timeout:25];({body});out tags geom;"


def _nearest(origin: GeoPoint, geometry: list[dict]) -> tuple[float, float] | None:
    best: tuple[float, float] | None = None
    best_d = float("inf")
    for pt in geometry:
        la, lo = pt.get("lat"), pt.get("lon")
        if la is None or lo is None:
            continue
        d = haversine_m(origin, GeoPoint(lat=la, lon=lo))
        if d < best_d:
            best_d, best = d, (la, lo)
    return best


def _element_to_place(el: dict, origin: GeoPoint) -> Place | None:
    tags = el.get("tags") or {}
    name = tags.get("name")
    if not name:
        return None
    if el.get("type") == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        near = _nearest(origin, el.get("geometry") or [])
        if near is not None:
            lat, lon = near
        else:
            c = el.get("center") or el.get("bounds") or {}
            lat, lon = c.get("lat"), c.get("lon")
    if lat is None or lon is None:
        return None
    category, _ = classify(tags)
    kept = {k: v for k, v in tags.items() if k in KEEP_TAGS}
    return Place(
        id=f'{el.get("type")}/{el.get("id")}',
        name=name,
        category=category,
        location=GeoPoint(lat=lat, lon=lon),
        tags=kept,
    )


def parse_elements(elements: list[dict], origin: GeoPoint) -> list[Place]:
    places: list[Place] = []
    seen_ids: set[str] = set()
    for el in elements:
        place = _element_to_place(el, origin)
        if place and place.id not in seen_ids:
            seen_ids.add(place.id)
            places.append(place)
    return places


class OverpassProvider:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or settings.overpass_url

    async def fetch_places(self, center: GeoPoint, radius_m: float) -> list[Place]:
        query = build_query(center, radius_m)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.url, data={"data": query})
            resp.raise_for_status()
            return parse_elements(resp.json().get("elements", []), center)


# --------------------------------------------------------------------------- #
# Static (fixtures / virtual walk)
# --------------------------------------------------------------------------- #
class StaticPlaceProvider:
    """Returns a fixed set of places, regardless of radius (radius filtering
    happens downstream in ranking)."""

    def __init__(self, places: list[Place]) -> None:
        self._places = places

    async def fetch_places(self, center: GeoPoint, radius_m: float) -> list[Place]:
        return list(self._places)

    @classmethod
    def from_json(cls, path: str | Path) -> StaticPlaceProvider:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        places = [
            Place(
                id=item.get("id") or f'{item["category"]}/{i}',
                name=item["name"],
                category=item["category"],
                location=GeoPoint(lat=item["lat"], lon=item["lon"]),
                tags=item.get("tags", {}),
            )
            for i, item in enumerate(raw)
        ]
        return cls(places)
