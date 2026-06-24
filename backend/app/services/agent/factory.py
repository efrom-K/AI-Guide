"""Build an Orchestrator from settings — picks Geo source, enricher and the
agent backend (heuristic / openai / anthropic). Keeps the WS handler thin.
"""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.services.agent.companion import Companion, HeuristicCompanion, LLMCompanion
from app.services.agent.narrator import LLMNarrator, Narrator, TemplateNarrator
from app.services.agent.orchestrator import Orchestrator
from app.services.agent.pipeline import TextPipeline
from app.services.agent.scorer import HeuristicScorer, LLMScorer, Scorer
from app.services.enrichment.enricher import (
    CompositeEnricher,
    Enricher,
    MockEnricher,
    WebSearchEnricher,
    WikiEnricher,
)
from app.services.geo.discovery import Discovery
from app.services.geo.providers import OverpassProvider, StaticPlaceProvider
from app.services.state.store import StateStore, default_store

# Demo data (self-contained walk) — used when geo_source/enrichment=fixture/mock.
_FIX = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def _roles() -> tuple[Scorer, Narrator, Companion]:
    backend = settings.agent_backend
    if backend in ("openai", "anthropic"):
        if backend == "openai":
            from app.services.llm.client import OpenAICompatLLM

            llm = OpenAICompatLLM()
        else:
            from app.services.llm.client import AnthropicLLM

            llm = AnthropicLLM()
        return LLMScorer(llm), LLMNarrator(llm), LLMCompanion(llm)
    return HeuristicScorer(), TemplateNarrator(), HeuristicCompanion()


def _discovery() -> Discovery:
    if settings.geo_source == "overpass":
        return Discovery(OverpassProvider())
    return Discovery(StaticPlaceProvider.from_json(_FIX / "places_red_square.json"))


def _enricher() -> Enricher:
    if settings.enrichment_source == "websearch":
        from app.services.llm.client import OpenAICompatLLM

        web = WebSearchEnricher(
            OpenAICompatLLM(),
            max_results=settings.web_search_max_results,
            max_tokens=settings.web_search_max_tokens,
            cache_path=settings.enrich_cache_path,
        )
        # Wikipedia/Wikidata first (free, high quality); paid web search only for
        # places without a wiki article and notable enough.
        return CompositeEnricher(
            WikiEnricher(), web, web_min_weight=settings.enrich_min_weight
        )
    return MockEnricher.from_json(_FIX / "facts_red_square.json")


def build_orchestrator(store: StateStore | None = None) -> Orchestrator:
    scorer, narrator, companion = _roles()
    web = settings.enrichment_source == "websearch"
    pipeline = TextPipeline(
        scorer,
        narrator,
        _enricher(),
        language=settings.default_language,
        # bound enrichment only for the real (slow/paid) provider; the mock path
        # enriches every candidate inline (instant).
        enrich_top_k=settings.enrich_top_k if web else None,
        enrich_timeout_s=settings.enrich_timeout_s if web else None,
    )
    return Orchestrator(_discovery(), pipeline, companion, store or default_store())
