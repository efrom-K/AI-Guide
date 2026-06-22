"""Fact enrichment: a cache + providers, kept OFF the hot-path.

The orchestrator prefetches facts for upcoming places into the cache; the
narrator reads the cache non-blocking (a miss → empty FACTS → generic/silence).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from app.shared.schemas import Candidate, Place


class Enricher(Protocol):
    async def facts_for(self, place: Place) -> str | None: ...


class EnrichmentCache:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def get(self, place_id: str) -> str | None:
        return self._cache.get(place_id)

    def put(self, place_id: str, facts: str) -> None:
        self._cache[place_id] = facts

    def __contains__(self, place_id: str) -> bool:
        return place_id in self._cache


class MockEnricher:
    """Facts from a static fixture (place_id -> facts). For offline sim/tests."""

    def __init__(self, facts: dict[str, str]) -> None:
        self._facts = facts

    async def facts_for(self, place: Place) -> str | None:
        return self._facts.get(place.id)

    @classmethod
    def from_json(cls, path: str | Path) -> MockEnricher:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))


async def prefetch(
    candidates: list[Candidate], enricher: Enricher, cache: EnrichmentCache
) -> None:
    """Populate the cache for any candidate that isn't cached yet."""
    for c in candidates:
        if c.place.id not in cache:
            facts = await enricher.facts_for(c.place)
            if facts:
                cache.put(c.place.id, facts)


def attach_facts(candidates: list[Candidate], cache: EnrichmentCache) -> list[Candidate]:
    """Return candidates with facts_available/facts_snippet filled from the cache."""
    out: list[Candidate] = []
    for c in candidates:
        facts = cache.get(c.place.id)
        out.append(
            c.model_copy(update={"facts_available": facts is not None, "facts_snippet": facts})
        )
    return out
