"""Discovery: fetch places via a provider and rank them, with adaptive radius.

Adaptive radius (business logic 1.5): if nothing new is found at the current
radius, expand step-by-step up to ``max_radius_m`` so the user isn't left in
silence.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.shared.schemas import Candidate, GeoPoint, Heading

from .providers import PlaceProvider
from .ranking import build_candidates


@dataclass
class DiscoveryResult:
    candidates: list[Candidate]
    radius_m: float
    expanded: bool  # radius was grown beyond the requested one
    exhausted: bool  # hit max_radius with still nothing


class Discovery:
    def __init__(
        self,
        provider: PlaceProvider,
        max_radius_m: float | None = None,
        # Bigger jumps => fewer sequential Overpass calls when an area is sparse
        # (80 -> 200 -> 500 = 3 calls, vs. 5 at 1.6). Faster to find or give up.
        expand_factor: float = 2.5,
    ) -> None:
        self.provider = provider
        self.max_radius_m = max_radius_m or settings.max_radius_m
        self.expand_factor = expand_factor

    async def discover(
        self,
        position: GeoPoint,
        heading: Heading,
        seen: list[str],
        radius_m: float,
    ) -> list[Candidate]:
        places = await self.provider.fetch_places(position, radius_m)
        return build_candidates(position, heading, places, radius_m, seen)

    async def discover_adaptive(
        self,
        position: GeoPoint,
        heading: Heading,
        seen: list[str],
        radius_m: float,
    ) -> DiscoveryResult:
        # One tight query (cheap, fast — covers dense city centres). If it's empty,
        # jump STRAIGHT to the max radius in a single wide query instead of stepping
        # 80 -> 200 -> 500: each step is a slow heavy Overpass call, and three of them
        # in a sparse suburb blew the per-tick deadline, so objects never surfaced
        # (the "talks about the district but never reaches any object" bug). At most
        # two queries now; proximity is handled by ranking, not by re-querying.
        candidates = await self.discover(position, heading, seen, radius_m)
        if candidates:
            return DiscoveryResult(candidates, radius_m, expanded=False, exhausted=False)
        if radius_m >= self.max_radius_m:
            return DiscoveryResult([], radius_m, expanded=False, exhausted=True)
        wide = self.max_radius_m
        candidates = await self.discover(position, heading, seen, wide)
        return DiscoveryResult(candidates, wide, expanded=True, exhausted=not candidates)
