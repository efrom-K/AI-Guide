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


# -- elaborate (latch onto a place when nothing new is nearby) ----------------
def test_elaborate_flag_bypasses_repeat_guard():
    n = LLMNarrator(FakeLLM(text_response="кстати, ещё одна деталь"))
    place = Place(id="p", name="Парк", category="park", location=GeoPoint(lat=1, lon=2))
    inp = NarratorInput(
        place=place, significance=Significance.MEDIUM, facts="факт", distance_m=0,
        history=["Парк. уже рассказывал про него"],
        flags=NarratorFlags(elaborate=True),
    )
    # name is in HISTORY, but elaborate=True must NOT silence it
    assert asyncio.run(n.narrate(inp)) == "кстати, ещё одна деталь"


def test_repeat_guard_silences_without_elaborate():
    n = LLMNarrator(FakeLLM(text_response="повтор"))
    place = Place(id="p", name="Парк", category="park", location=GeoPoint(lat=1, lon=2))
    inp = NarratorInput(
        place=place, significance=Significance.MEDIUM, facts="факт", distance_m=0,
        history=["Парк. уже рассказывал"], flags=NarratorFlags(),
    )
    assert asyncio.run(n.narrate(inp)) == ""  # repeat guard fires


def test_split_hook_parses_and_strips():
    from app.services.agent.narrator import split_hook

    assert split_hook("Рассказ тут.\nHOOK: дальше к реке") == ("Рассказ тут.", "дальше к реке")
    assert split_hook("Просто текст") == ("Просто текст", None)
    assert split_hook("") == ("", None)
    spoken, hook = split_hook("Начало.\nHOOK: связка\n")
    assert spoken == "Начало." and hook == "связка"
    # inline HOOK (model put it on the SAME line as the last sentence) must still strip
    assert split_hook("…память о прошлом. HOOK: а вот дальше") == (
        "…память о прошлом.", "а вот дальше"
    )


def test_pipeline_step_extracts_next_hook_and_strips_it():
    # the Narrator's trailing HOOK: line must be stripped from speech and surfaced
    # as StepResult.next_hook (the baton woven into the next paragraph).
    narrator = LLMNarrator(FakeLLM(text_response="Старый маяк у входа в порт.\nHOOK: к набережной"))
    pipe = TextPipeline(HeuristicScorer(), narrator, MockEnricher({}))
    cand = _candidate("m", "Маяк", "lighthouse", 0.8)
    out = asyncio.run(pipe.step([cand], seen=[], history=[]))
    assert out.text == "Старый маяк у входа в порт."  # HOOK line gone from speech
    assert out.next_hook == "к набережной"


def test_pipeline_elaborate_uses_cached_facts():
    pipe = TextPipeline(
        HeuristicScorer(),
        LLMNarrator(FakeLLM(text_response=lambda role, system, user: user)),
        MockEnricher({}),
    )
    pipe.cache.put("p", "факт о месте")
    place = Place(id="p", name="Место", category="historic", location=GeoPoint(lat=1, lon=2))
    text = asyncio.run(pipe.elaborate(place, Significance.MEDIUM, history=[]))
    assert "факт о месте" in text  # cached facts reach the narrator


# -- deterministic floor mention (a close object is never dead air) ------------
def test_pipeline_step_floors_silenced_passing_object():
    # DeepSeek sometimes ignores "passing -> never silent"; for a close named object
    # the pipeline must still emit a deterministic one-line mention.
    pipe = TextPipeline(HeuristicScorer(), LLMNarrator(FakeLLM(text_response="[SILENCE]")),
                        MockEnricher({}))
    cand = _candidate("m", "Маяк", "lighthouse", 0.8)
    out = asyncio.run(pipe.step([cand], seen=[], history=[], passing=True))
    assert out.place is not None and out.place.id == "m"
    assert out.text and "Маяк" in out.text  # forced floor mention names the object


def test_pipeline_step_no_floor_when_not_passing():
    pipe = TextPipeline(HeuristicScorer(), LLMNarrator(FakeLLM(text_response="[SILENCE]")),
                        MockEnricher({}))
    cand = _candidate("m", "Маяк", "lighthouse", 0.8)
    out = asyncio.run(pipe.step([cand], seen=[], history=[], passing=False))
    assert out.text == ""  # not passing -> the model's silence stands


def test_pipeline_step_no_floor_when_already_told():
    pipe = TextPipeline(HeuristicScorer(), LLMNarrator(FakeLLM(text_response="[SILENCE]")),
                        MockEnricher({}))
    cand = _candidate("m", "Маяк", "lighthouse", 0.8)
    out = asyncio.run(pipe.step([cand], seen=[], history=["Старый Маяк у входа в порт."],
                                passing=True))
    assert out.text == ""  # already named in history -> no repeat floor mention
