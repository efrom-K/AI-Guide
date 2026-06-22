"""Turn raw places into ranked Candidates for a given position & heading.

Score combines three signals from the business logic:
  * proximity      — closer is better
  * type weight    — museum/monument > shop (categories.py)
  * gaze cone      — objects ahead get a boost; muted when gaze_confidence=low
"""

from __future__ import annotations

from collections.abc import Iterable

from app.shared.geo_math import angle_diff, bearing_deg, haversine_m
from app.shared.schemas import Candidate, GazeConfidence, GeoPoint, Heading, Place

from .categories import weight_for

GAZE_CONE_DEG = 45.0
_GAZE_BOOST_HIGH = 1.5
_GAZE_BOOST_LOW = 1.2


def _score(candidate: Candidate, radius_m: float) -> float:
    proximity = max(0.0, 1.0 - candidate.distance_m / radius_m) if radius_m else 0.0
    gaze = 1.0
    if candidate.in_gaze_cone:
        gaze = (
            _GAZE_BOOST_HIGH
            if candidate.gaze_confidence is GazeConfidence.HIGH
            else _GAZE_BOOST_LOW
        )
    return candidate.type_weight * (0.5 + 0.5 * proximity) * gaze


def build_candidates(
    position: GeoPoint,
    heading: Heading,
    places: Iterable[Place],
    radius_m: float,
    seen: Iterable[str] = (),
) -> list[Candidate]:
    seen_ids = set(seen)
    candidates: list[Candidate] = []
    for place in places:
        if place.id in seen_ids:
            continue
        distance = haversine_m(position, place.location)
        if distance > radius_m:
            continue
        in_cone = False
        if heading.direction_deg is not None:
            bearing = bearing_deg(position, place.location)
            in_cone = angle_diff(bearing, heading.direction_deg) <= GAZE_CONE_DEG
        candidates.append(
            Candidate(
                place=place,
                distance_m=round(distance, 1),
                type_weight=weight_for(place.category),
                in_gaze_cone=in_cone,
                gaze_confidence=heading.gaze_confidence,
            )
        )
    candidates.sort(key=lambda c: _score(c, radius_m), reverse=True)
    return candidates
