"""Small spherical-geometry helpers (good enough at city scale)."""

from __future__ import annotations

from math import asin, atan2, cos, degrees, radians, sin, sqrt

from app.shared.schemas import GeoPoint

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points, in metres."""
    dlat = radians(b.lat - a.lat)
    dlon = radians(b.lon - a.lon)
    la1, la2 = radians(a.lat), radians(b.lat)
    h = sin(dlat / 2) ** 2 + cos(la1) * cos(la2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))


def bearing_deg(a: GeoPoint, b: GeoPoint) -> float:
    """Initial bearing from a to b, degrees clockwise from north (0..360)."""
    la1, la2 = radians(a.lat), radians(b.lat)
    dlon = radians(b.lon - a.lon)
    y = sin(dlon) * cos(la2)
    x = cos(la1) * sin(la2) - sin(la1) * cos(la2) * cos(dlon)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings (0..180)."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def relative_bearing(heading_deg: float, target_bearing_deg: float) -> float:
    """Signed angle of `target` relative to `heading`, in (-180, 180].

    Bearings are clockwise from north, so a positive result means the target is
    clockwise from where you face — i.e. **to your right**; negative is **left**.
    (Facing north, an object due east → +90 → right; due west → -90 → left.)
    Unlike `angle_diff`, this keeps the sign, which is what distinguishes left
    from right — only meaningful when the heading is a real facing direction
    (compass / gaze_confidence=high), not a noisy GPS course.
    """
    return ((target_bearing_deg - heading_deg + 180.0) % 360.0) - 180.0
