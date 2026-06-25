"""Per-tick text pipeline: discovery candidates -> facts -> Scorer -> Narrator.

This is the Stage-2 core (no FSM/persistence yet — that's the orchestrator in
Stage 3). The caller owns seen-list and history across ticks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.enrichment.enricher import (
    Enricher,
    EnrichmentCache,
    attach_facts,
    prefetch,
)
from app.shared.schemas import (
    Address,
    AreaInput,
    Candidate,
    ControlPatch,
    GazeConfidence,
    GeoPoint,
    Heading,
    NarrationContext,
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


# Atypical-facts-forward area enrichment: lesser-known facts about the district /
# street / city, not the obvious encyclopedic blurb.
_AREA_ENRICH_SYSTEM = (
    "Ты собираешь нетипичные, малоизвестные факты о районе/улице/городе для "
    "аудиогида. Дай 2-4 кратких достоверных факта именно об этом районе или улице "
    "в указанном городе: необычная история, как место возникло и менялось, забытые "
    "эпизоды, чем известно в узких кругах. Очевидное и банально-общеизвестное не "
    "пиши. Только проверяемые факты, без выдумок и оценок. Если надёжной информации "
    "именно об этом районе нет — ответь ровно: НЕТ."
)


def _context(addr: Address) -> NarrationContext:
    return NarrationContext(city=addr.city, district=addr.district, street=addr.street)


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
        area_llm=None,  # an LLM with web_facts() for area enrichment (optional)
    ) -> None:
        self.scorer = scorer
        self.narrator = narrator
        self.enricher = enricher
        self.cache = cache or EnrichmentCache()
        self.language = language
        self.enrich_top_k = enrich_top_k
        self.enrich_timeout_s = enrich_timeout_s
        self.area_llm = area_llm

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
                context=_context(addr),
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

    async def elaborate(
        self,
        place: Place,
        significance: Significance,
        *,
        history: list[str],
        address: Address | None = None,
        heading: Heading | None = None,
        pace: Pace = Pace.SLOW,
        language: str | None = None,
    ) -> str:
        """Tell MORE about an already-covered place (nothing new nearby). Reuses
        cached facts; the narrator adds a fresh detail, avoiding HISTORY."""
        lang = language or self.language
        addr = address or Address()
        facts = self.cache.get(place.id)
        if facts is None:
            ctx = ", ".join(p for p in (addr.city, addr.country) if p) or None
            await prefetch(
                [Candidate(place=place, distance_m=0.0, type_weight=0.0,
                           in_gaze_cone=False, gaze_confidence=GazeConfidence.LOW)],
                self.enricher,
                self.cache,
                top_k=1,
                timeout_s=self.enrich_timeout_s,
                context=ctx,
            )
            facts = self.cache.get(place.id)
        return await self.narrator.narrate(
            NarratorInput(
                place=place,
                significance=significance,
                facts=facts,
                distance_m=0.0,
                heading=heading or Heading(),
                pace=pace,
                context=_context(addr),
                history=history,
                flags=NarratorFlags(elaborate=True),
                language=lang,
            )
        )

    async def narrate_area(
        self,
        address: Address,
        *,
        facts: str | None,
        intro: bool,
        beat: int,
        last_place_name: str | None,
        history: list[str],
        pace: Pace = Pace.SLOW,
        language: str | None = None,
    ) -> str:
        """One beat of the area-level monologue (city/district/street) — the spine
        that bridges gaps between objects. Returns "" for silence."""
        return await self.narrator.narrate_area(
            AreaInput(
                address=address,
                facts=facts,
                intro=intro,
                beat=beat,
                last_place_name=last_place_name,
                history=history,
                pace=pace,
                language=language or self.language,
            )
        )

    async def enrich_area(
        self, address: Address, point: GeoPoint | None, *, timeout_s: float | None = None
    ) -> str | None:
        """Fetch verified, atypical facts about the current district/street/city via
        web search. Slow-changing -> the orchestrator caches it once per area."""
        if self.area_llm is None:
            return None
        where = " ".join(p for p in (address.district, address.street, address.city) if p)
        if not where:
            return None
        coords = f"координаты {point.lat:.4f}, {point.lon:.4f}" if point else ""
        query = f"{where} {coords} район история чем известен необычные факты".strip()
        try:
            coro = self.area_llm.web_facts(
                _AREA_ENRICH_SYSTEM, query, max_results=3, max_tokens=400
            )
            text = (await asyncio.wait_for(coro, timeout=timeout_s) if timeout_s else await coro)
        except (Exception, asyncio.TimeoutError):
            return None
        cleaned = (text or "").strip()
        if not cleaned or cleaned.upper().lstrip("*•-. ").startswith("НЕТ"):
            return None
        return cleaned
