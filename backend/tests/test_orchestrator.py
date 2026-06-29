import asyncio
from pathlib import Path

from app.services.agent.companion import HeuristicCompanion
from app.services.agent.narrator import TemplateNarrator
from app.services.agent.orchestrator import _MAX_AREA_BEATS, Orchestrator, State, merge_patch
from app.services.agent.pipeline import TextPipeline
from app.services.agent.scorer import HeuristicScorer
from app.services.enrichment.enricher import MockEnricher
from app.services.geo.discovery import Discovery
from app.services.geo.providers import StaticPlaceProvider
from app.services.state.store import InMemoryStateStore
from app.shared.schemas import Address, ControlPatch, GeoPoint, Heading, Pace, Place
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


def test_geocoder_retries_after_empty_then_resolves():
    """#2: an empty/failed first geocode must NOT lock last_geo_pos — otherwise the
    address (and the companion's location-awareness) only resolves after walking
    geocoder_min_move_m. The next tick at the SAME spot should retry and resolve."""

    class FlakyGeo:
        def __init__(self):
            self.calls = 0

        async def reverse(self, point, language="ru"):
            self.calls += 1
            return Address() if self.calls == 1 else Address(city="Москва", district="Тверской")

    orch = _orch([])
    geo = FlakyGeo()
    orch.geocoder = geo

    async def run():
        st = await orch.store.load("geo-retry")
        await orch._resolve_area(st, HERE)  # empty -> must not commit / not lock out
        assert st.last_geo_pos is None
        assert not any(
            (st.address.country, st.address.city, st.address.district, st.address.street)
        )
        await orch._resolve_area(st, HERE)  # SAME spot: retries (not move-gated) -> resolves
        assert geo.calls == 2
        assert st.address.city == "Москва"
        assert st.last_geo_pos is not None

    asyncio.run(run())


def test_street_change_weaves_transition_without_resetting_arc():
    """E: stepping onto a new street within the SAME district sets a transition
    baton (next_hook) and keeps the running arc, instead of a hard reset + opener.
    A district change still resets the arc."""
    orch = _orch([])

    class Geo:
        def __init__(self):
            self.addr = Address(city="Москва", district="Тверской", street="Тверская")

        async def reverse(self, point, language="ru"):
            return self.addr

    geo = Geo()
    orch.geocoder = geo

    async def run():
        st = await orch.store.load("street")
        await orch._resolve_area(st, HERE)  # first resolve -> establishes the area
        assert st.last_street == "Тверская"
        st.area_intro_done = True  # pretend the area opener has played
        st.narrative_plan.outline = ["t1"]
        arc = st.narrative_plan
        # move >150 m; new street, SAME district -> woven transition, no reset
        geo.addr = Address(city="Москва", district="Тверской", street="Камергерский")
        far = GeoPoint(lat=HERE.lat + 0.002, lon=HERE.lon)
        await orch._resolve_area(st, far)
        assert st.narrative_plan is arc  # arc NOT reset
        assert st.narrative_plan.outline == ["t1"]
        assert st.last_street == "Камергерский"
        assert "Камергерский" in (st.narrative_plan.next_hook or "")
        # now a DISTRICT change -> fresh arc
        geo.addr = Address(city="Москва", district="Арбат", street="Арбат")
        farther = GeoPoint(lat=HERE.lat + 0.004, lon=HERE.lon)
        await orch._resolve_area(st, farther)
        assert st.narrative_plan is not arc  # reset on new district
        assert st.area_intro_done is False

    asyncio.run(run())


def test_warm_ahead_caches_in_cone_objects_nonblocking():
    """B: facts for objects you're walking TOWARD (in the course cone) are warmed
    into the cache ahead of arrival; out-of-cone objects are not prioritised."""
    from app.services.enrichment.enricher import EnrichmentCache
    from app.shared.schemas import Candidate, GazeConfidence

    class FakeEnricher:
        async def facts_for(self, place, context=None):
            return f"facts:{place.id}"

    def cand(pid, dist, cone):
        return Candidate(
            place=_place(pid, pid, "monument"),
            distance_m=dist,
            type_weight=0.9,
            in_gaze_cone=cone,
            gaze_confidence=GazeConfidence.LOW,
        )

    async def run():
        cache = EnrichmentCache()
        pipe = TextPipeline(
            HeuristicScorer(), TemplateNarrator(), FakeEnricher(),
            cache=cache, enrich_top_k=2, enrich_timeout_s=5.0,
        )
        task = pipe.warm_ahead([cand("a", 50, True), cand("b", 120, True), cand("c", 80, False)])
        assert task is not None
        await task
        assert cache.get("a") == "facts:a"  # in-cone -> warmed
        assert cache.get("b") == "facts:b"
        assert cache.get("c") is None  # out-of-cone -> not prioritised

        # mock/inline path (enrich_top_k=None) must be a no-op (no background work)
        inline = TextPipeline(HeuristicScorer(), TemplateNarrator(), FakeEnricher())
        assert inline.warm_ahead([cand("a", 50, True)]) is None

    asyncio.run(run())


def test_connective_area_beats_fill_pause_until_budget():
    """#1: once the planned outline is exhausted, the guide keeps filling the pause
    with connective area/city beats (varied angles) up to a per-lull budget, instead
    of going silent immediately."""
    orch = _orch([])

    async def fake_narrate_area(address, **kw):
        return f"connective beat: {kw['topic']}", None  # (spoken, next_hook)

    orch.pipeline.narrate_area = fake_narrate_area

    async def run():
        st = await orch.store.load("conn")
        st.address = Address(city="Москва", district="Тверской")
        st.area_facts = ""  # skip the web-enrich path
        produced = [await orch._area_line(st, Pace.SLOW) for _ in range(_MAX_AREA_BEATS + 2)]
        nonempty = [t for t in produced if t]
        assert len(nonempty) == _MAX_AREA_BEATS  # filled exactly the budget...
        assert produced[_MAX_AREA_BEATS] == ""  # ...then silence
        assert len(set(nonempty)) > 1  # varied angles, not the same line repeated

    asyncio.run(run())
