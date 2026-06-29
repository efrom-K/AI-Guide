"""Per-tick text pipeline: discovery candidates -> facts -> Scorer -> Narrator.

This is the Stage-2 core (no FSM/persistence yet — that's the orchestrator in
Stage 3). The caller owns seen-list and history across ticks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import settings
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
    ScorerOutput,
    Significance,
)

from .narrator import Narrator, split_hook
from .scorer import Scorer
from .significance import significance_from_weight


@dataclass
class StepResult:
    text: str  # "" means silence
    decision: ScorerOutput
    place: Place | None
    significance: Significance | None
    next_hook: str | None = None  # baton to weave into the next paragraph


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
        planner=None,  # a Planner that forms the story arc (optional)
    ) -> None:
        self.scorer = scorer
        self.narrator = narrator
        self.enricher = enricher
        self.cache = cache or EnrichmentCache()
        self.language = language
        self.enrich_top_k = enrich_top_k
        self.enrich_timeout_s = enrich_timeout_s
        self.area_llm = area_llm
        self.planner = planner
        self._warm_tasks: set[asyncio.Task] = set()  # hold refs to background warms

    def warm_ahead(self, candidates: list[Candidate], *, address: Address | None = None):
        """Non-blocking: warm the fact cache for objects the user is walking TOWARD
        (in the course cone, nearest first), so facts are ready before arrival. A
        no-op on the mock/inline path (`enrich_top_k is None`). Returns the scheduled
        task (or None) so callers/tests can await it; the orchestrator ignores it."""
        if self.enrich_top_k is None or not candidates:
            return None
        # Cone-first, then nearest: facts for what you're walking toward are warmed
        # first, but nearby objects off the cone still get facts too — so the guide
        # has something ready whichever object you end up passing (background
        # inventory fact-collection).
        pending = [c for c in candidates if c.place.id not in self.cache]
        pending.sort(key=lambda c: (not c.in_gaze_cone, c.distance_m))
        ahead = pending[: settings.enrich_lookahead_k]
        if not ahead:
            return None
        addr = address or Address()
        ctx = ", ".join(p for p in (addr.city, addr.country) if p) or None
        task = asyncio.ensure_future(
            prefetch(
                ahead,
                self.enricher,
                self.cache,
                top_k=settings.enrich_lookahead_k,
                timeout_s=self.enrich_timeout_s,
                context=ctx,
            )
        )
        self._warm_tasks.add(task)
        task.add_done_callback(self._warm_tasks.discard)
        return task

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
        theme: str | None = None,
        told: list[str] | None = None,
        next_hook: str | None = None,
        passing: bool = False,
    ) -> StepResult:
        """Narrate the nearest weave-worthy object, woven INTO the story arc.

        The expensive per-tick LLM Scorer is gone: candidates arrive already
        proximity-gated and ranked, so selection is deterministic (nearest unseen,
        honoring skip-categories) and significance is a cheap heuristic. The arc
        (theme / told / next_hook) keeps the object inside the running story.
        """
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

        seen_set = set(seen)
        skip = set(preferences.skip_categories) if preferences else set()
        chosen = next(
            (c for c in enriched if c.place.id not in seen_set and c.place.category not in skip),
            None,
        )
        if chosen is None:
            return StepResult("", ScorerOutput(), None, None)
        sig = significance_from_weight(chosen.type_weight, chosen.facts_available)
        raw = await self.narrator.narrate(
            NarratorInput(
                place=chosen.place,
                significance=sig,
                facts=chosen.facts_snippet,
                distance_m=chosen.distance_m,
                heading=heading or Heading(),
                side=chosen.side,
                pace=pace,
                context=_context(addr),
                theme=theme,
                told=told or [],
                next_hook=next_hook,
                history=history,
                flags=NarratorFlags(
                    switching=switching,
                    nothing_new=not candidates,
                    passing=passing,
                    preferences=preferences,
                ),
                language=lang,
            )
        )
        text, hook = split_hook(raw)
        return StepResult(text, ScorerOutput(), chosen.place, sig, next_hook=hook)

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
        raw = await self.narrator.narrate(
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
        text, _ = split_hook(raw)  # elaborate stays on the same place; drop the hook
        return text

    async def narrate_area(
        self,
        address: Address,
        *,
        facts: str | None,
        theme: str | None,
        topic: str | None,
        told: list[str],
        next_hook: str | None,
        last_place_name: str | None,
        history: list[str],
        pace: Pace = Pace.SLOW,
        language: str | None = None,
    ) -> tuple[str, str | None]:
        """One beat of the area-level monologue — advance the story arc by one
        topic, staying inside the theme. Returns (spoken_text, next_hook); spoken
        text is "" for silence."""
        raw = await self.narrator.narrate_area(
            AreaInput(
                address=address,
                facts=facts,
                theme=theme,
                topic=topic,
                told=told,
                next_hook=next_hook,
                last_place_name=last_place_name,
                history=history,
                pace=pace,
                language=language or self.language,
            )
        )
        return split_hook(raw)

    async def make_plan(
        self, address: Address, *, facts: str | None, theme_override: str | None, language: str | None = None
    ):
        """Form the story arc (theme + outline + opener) for a freshly entered area."""
        from app.shared.schemas import PlannerInput

        if self.planner is None:
            return None
        return await self.planner.plan(
            PlannerInput(
                address=address,
                facts=facts,
                theme_override=theme_override,
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
