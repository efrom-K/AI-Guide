import asyncio
from pathlib import Path

from app.services.agent.companion import HeuristicCompanion
from app.services.agent.narrator import LLMNarrator, TemplateNarrator
from app.services.agent.pipeline import TextPipeline
from app.services.agent.scorer import HeuristicScorer, LLMScorer
from app.services.enrichment.enricher import MockEnricher
from app.services.geo.discovery import Discovery
from app.services.geo.providers import StaticPlaceProvider
from app.services.llm.client import FakeLLM
from app.services.llm.router import Role
from app.shared.schemas import (
    Candidate,
    CompanionInput,
    GazeConfidence,
    GeoPoint,
    NarratorFlags,
    NarratorInput,
    Place,
    ScorerInput,
    Significance,
)
from sim.routes import RED_SQUARE
from sim.walk import walk

FIX = Path(__file__).parent / "fixtures"


def _candidate(pid, name, category, weight, dist=10.0, facts=None) -> Candidate:
    return Candidate(
        place=Place(id=pid, name=name, category=category, location=GeoPoint(lat=1, lon=2)),
        distance_m=dist,
        type_weight=weight,
        in_gaze_cone=True,
        gaze_confidence=GazeConfidence.LOW,
        facts_available=facts is not None,
        facts_snippet=facts,
    )


def test_template_narrator_silence_when_nothing_new():
    n = TemplateNarrator()
    inp = NarratorInput(
        place=Place(id="p", name="X", category="park", location=GeoPoint(lat=1, lon=2)),
        significance=Significance.LOW,
        distance_m=5,
        flags=NarratorFlags(nothing_new=True),
    )
    assert asyncio.run(n.narrate(inp)) == ""


def test_template_narrator_no_repeat():
    n = TemplateNarrator()
    inp = NarratorInput(
        place=Place(id="p", name="Музей", category="museum", location=GeoPoint(lat=1, lon=2)),
        significance=Significance.HIGH,
        facts="Большой музей.",
        distance_m=5,
        history=["Музей рядом, интересное место."],
    )
    assert asyncio.run(n.narrate(inp)) == ""  # name already in history


def test_heuristic_scorer_skips_blocked_category():
    scorer = HeuristicScorer()
    from app.shared.schemas import ControlPatch

    out = asyncio.run(
        scorer.score(
            ScorerInput(
                candidates=[
                    _candidate("shop1", "ГУМ", "shop", 0.25),
                    _candidate("mus1", "Музей", "museum", 0.9, facts="факт"),
                ],
                preferences=ControlPatch(skip_categories=["shop"]),
            )
        )
    )
    assert out.next == "mus1"
    sig = {s.place_id: s.significance for s in out.scored}
    assert sig["shop1"] is Significance.SKIP


def test_llm_scorer_with_fake():
    fake = FakeLLM(
        json_response={
            "scored": [{"place_id": "p1", "significance": "HIGH", "reason": "x"}],
            "next": "p1",
            "expand_radius": False,
        }
    )
    out = asyncio.run(
        LLMScorer(fake).score(ScorerInput(candidates=[_candidate("p1", "X", "museum", 0.9)]))
    )
    assert out.next == "p1"
    assert out.scored[0].significance is Significance.HIGH


def test_llm_narrator_normalizes_silence_sentinel():
    fake = FakeLLM(text_response="[SILENCE]")
    inp = NarratorInput(
        place=Place(id="p", name="X", category="park", location=GeoPoint(lat=1, lon=2)),
        significance=Significance.LOW,
        distance_m=5,
    )
    assert asyncio.run(LLMNarrator(fake).narrate(inp)) == ""


def test_companion_heuristic_skips_shops():
    out = asyncio.run(
        HeuristicCompanion().respond(CompanionInput(user_message="пропускай магазины"))
    )
    assert out.control_patch is not None
    assert "shop" in out.control_patch.skip_categories


def test_pipeline_walk_offline_no_repeats():
    async def run() -> list[str]:
        provider = StaticPlaceProvider.from_json(FIX / "places_red_square.json")
        discovery = Discovery(provider)
        pipeline = TextPipeline(
            HeuristicScorer(),
            TemplateNarrator(),
            MockEnricher.from_json(FIX / "facts_red_square.json"),
        )
        seen: list[str] = []
        history: list[str] = []
        narrated_places: list[str] = []
        for step in walk(RED_SQUARE, speed_mps=1.3, step_s=8.0):
            result = await discovery.discover_adaptive(step.position, step.heading, seen, 80.0)
            out = await pipeline.step(
                result.candidates, seen=seen, history=history, heading=step.heading
            )
            if out.text and out.place:
                narrated_places.append(out.place.id)
                history.append(out.text)
                seen.append(out.place.id)
        return narrated_places

    narrated = asyncio.run(run())
    # several distinct landmarks, and never the same place twice (dedup holds)
    assert len(narrated) >= 3
    assert len(narrated) == len(set(narrated))


def test_fake_llm_roles_callable():
    fake = FakeLLM(text_response="hi")
    assert asyncio.run(fake.complete_text(Role.NARRATOR, "s", "u")) == "hi"
