"""Per-tick text pipeline: discovery candidates -> facts -> Scorer -> Narrator.

This is the Stage-2 core (no FSM/persistence yet — that's the orchestrator in
Stage 3). The caller owns seen-list and history across ticks.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.enrichment.enricher import (
    Enricher,
    EnrichmentCache,
    attach_facts,
    prefetch,
)
from app.shared.schemas import (
    Address,
    Candidate,
    ControlPatch,
    Heading,
    NarratorFlags,
    NarratorInput,
    Pace,
    Place,
    ScorerInput,
    ScorerOutput,
    Significance,
)

from .narrator import Narrator
from .scorer import Scorer


@dataclass
class StepResult:
    text: str  # "" means silence
    decision: ScorerOutput
    place: Place | None
    significance: Significance | None


class TextPipeline:
    def __init__(
        self,
        scorer: Scorer,
        narrator: Narrator,
        enricher: Enricher,
        cache: EnrichmentCache | None = None,
        language: str = "ru",
        enrich_top_k: int | None = None,
        enrich_timeout_s: float | None = None,
    ) -> None:
        self.scorer = scorer
        self.narrator = narrator
        self.enricher = enricher
        self.cache = cache or EnrichmentCache()
        self.language = language
        self.enrich_top_k = enrich_top_k
        self.enrich_timeout_s = enrich_timeout_s

    async def step(
        self,
        candidates: list[Candidate],
        *,
        seen: list[str],
        history: list[str],
        address: Address | None = None,
        heading: Heading | None = None,
        pace: Pace = Pace.SLOW,
        preferences: ControlPatch | None = None,
        switching: bool = False,
        language: str | None = None,
    ) -> StepResult:
        lang = language or self.language
        addr = address or Address()
        ctx = ", ".join(p for p in (addr.city, addr.country) if p) or None
        await prefetch(
            candidates,
            self.enricher,
            self.cache,
            top_k=self.enrich_top_k,
            timeout_s=self.enrich_timeout_s,
            context=ctx,
        )
        enriched = attach_facts(candidates, self.cache)

        decision = await self.scorer.score(
            ScorerInput(
                candidates=enriched,
                address=address or Address(),
                seen=seen,
                preferences=preferences,
                language=lang,
            )
        )
        if decision.next is None:
            return StepResult("", decision, None, None)

        chosen = next(c for c in enriched if c.place.id == decision.next)
        sig = next(
            (s.significance for s in decision.scored if s.place_id == decision.next),
            Significance.MEDIUM,
        )
        text = await self.narrator.narrate(
            NarratorInput(
                place=chosen.place,
                significance=sig,
                facts=chosen.facts_snippet,
                distance_m=chosen.distance_m,
                heading=heading or Heading(),
                pace=pace,
                history=history,
                flags=NarratorFlags(
                    switching=switching,
                    nothing_new=not candidates,
                    preferences=preferences,
                ),
                language=lang,
            )
        )
        return StepResult(text, decision, chosen.place, sig)
