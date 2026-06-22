import asyncio
from pathlib import Path

from app.services.agent.companion import HeuristicCompanion
from app.services.agent.narrator import TemplateNarrator
from app.services.agent.orchestrator import Orchestrator, State, merge_patch
from app.services.agent.pipeline import TextPipeline
from app.services.agent.scorer import HeuristicScorer
from app.services.enrichment.enricher import MockEnricher
from app.services.geo.discovery import Discovery
from app.services.geo.providers import StaticPlaceProvider
from app.services.state.store import InMemoryStateStore
from app.shared.schemas import ControlPatch, GeoPoint, Heading, Pace, Place
from sim.routes import RED_SQUARE
from sim.walk import walk

FIX = Path(__file__).parent / "fixtures"
HERE = GeoPoint(lat=55.7537, lon=37.6205)


def _place(pid, name, category, lat=55.7537, lon=37.6205) -> Place:
    return Place(id=pid, name=name, category=category, location=GeoPoint(lat=lat, lon=lon))


def _orch(places, facts=None, companion=None) -> Orchestrator:
    discovery = Discovery(StaticPlaceProvider(places))
    pipeline = TextPipeline(HeuristicScorer(), TemplateNarrator(), MockEnricher(facts or {}))
    return Orchestrator(
        discovery, pipeline, companion or HeuristicCompanion(), InMemoryStateStore()
    )


class CountingPipeline(TextPipeline):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls = 0

    async def step(self, *a, **k):
        self.calls += 1
        return await super().step(*a, **k)


def test_walk_narrates_and_persists_memory():
    async def run():
        provider = StaticPlaceProvider.from_json(FIX / "places_red_square.json")
        enricher = MockEnricher.from_json(FIX / "facts_red_square.json")
        pipeline = TextPipeline(HeuristicScorer(), TemplateNarrator(), enricher)
        orch = Orchestrator(
            Discovery(provider), pipeline, HeuristicCompanion(), InMemoryStateStore()
        )
        narrated = []
        for step in walk(RED_SQUARE, speed_mps=1.3, step_s=8.0):
            out = await orch.on_position("s1", step.position, step.heading, step.pace)
            if out.kind == "narration":
                narrated.append(out.place_id)
        state = await orch.store.load("s1")
        return narrated, state

    narrated, state = asyncio.run(run())
    assert len(narrated) >= 3
    assert len(narrated) == len(set(narrated))  # dedup
    assert state.seen_place_ids  # memory persisted
    assert set(narrated) <= set(state.seen_place_ids)


def test_heuristic_gate_skips_llm_on_unchanged_set():
    async def run():
        discovery = Discovery(StaticPlaceProvider([_place("shop1", "ГУМ", "shop")]))
        pipeline = CountingPipeline(HeuristicScorer(), TemplateNarrator(), MockEnricher({}))
        orch = Orchestrator(discovery, pipeline, HeuristicCompanion(), InMemoryStateStore())
        o1 = await orch.on_position("s", HERE, Heading(), Pace.SLOW)
        o2 = await orch.on_position("s", HERE, Heading(), Pace.SLOW)
        return o1, o2, pipeline.calls

    o1, o2, calls = asyncio.run(run())
    assert o1.kind == "silence" and o2.kind == "silence"
    assert calls == 1  # second identical tick was gated, pipeline not called again


def test_barge_in_applies_control_patch():
    async def run():
        orch = _orch([_place("m", "Музей", "museum")], facts={"m": "факт"})
        await orch.on_utterance("s", "пропускай магазины")
        return await orch.store.load("s")

    state = asyncio.run(run())
    assert state.state == State.ANSWERING
    assert "shop" in state.control_patch.skip_categories
    assert state.conversation  # dialog remembered


def test_mute_silences_narration():
    async def run():
        orch = _orch([_place("m", "Музей", "museum")], facts={"m": "Большой музей."})
        await orch.on_utterance("s", "помолчи")
        out = await orch.on_position("s", HERE, Heading(), Pace.SLOW)
        state = await orch.store.load("s")
        return out, state

    out, state = asyncio.run(run())
    assert out.kind == "silence"
    assert state.control_patch.mute is True
    assert not state.seen_place_ids  # nothing narrated while muted


def test_offline_degrades_to_silence():
    async def run():
        orch = _orch([_place("m", "Музей", "museum")], facts={"m": "факт"})
        await orch.set_online("s", False)
        off = await orch.on_position("s", HERE, Heading(), Pace.SLOW)
        await orch.set_online("s", True)
        return off

    off = asyncio.run(run())
    assert off.kind == "offline" and off.state == State.OFFLINE


def test_merge_patch_unions_and_overrides():
    base = ControlPatch(skip_categories=["shop"], verbosity="normal")
    patch = ControlPatch(skip_categories=["cafe"], verbosity="shorter", mute=True)
    merged = merge_patch(base, patch)
    assert set(merged.skip_categories) == {"shop", "cafe"}
    assert merged.verbosity == "shorter"
    assert merged.mute is True
