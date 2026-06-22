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
from app.services.enrichment.enricher import Enricher, MockEnricher
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
    # only "mock" wired for now; websearch enricher lands with the real provider
    return MockEnricher.from_json(_FIX / "facts_red_square.json")


def build_orchestrator(store: StateStore | None = None) -> Orchestrator:
    scorer, narrator, companion = _roles()
    pipeline = TextPipeline(scorer, narrator, _enricher(), language=settings.default_language)
    return Orchestrator(_discovery(), pipeline, companion, store or default_store())
