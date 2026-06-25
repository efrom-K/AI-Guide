"""Reverse geocoding parse + the area-level monologue flow (general -> specific)."""

import asyncio

from app.services.agent.companion import HeuristicCompanion
from app.services.agent.narrator import Narrator
from app.services.agent.orchestrator import Orchestrator
from app.services.agent.pipeline import TextPipeline
from app.services.agent.scorer import HeuristicScorer
from app.services.enrichment.enricher import MockEnricher
from app.services.geo.discovery import Discovery
from app.services.geo.geocoder import MockGeocoder, parse_address
from app.services.geo.providers import StaticPlaceProvider
from app.services.state.store import InMemoryStateStore
from app.shared.schemas import Address, AreaInput, GeoPoint, Heading, NarratorInput, Pace, Place


# --------------------------------------------------------------------------- #
# parse_address — the locale heuristic
# --------------------------------------------------------------------------- #
def _admin(level, name):
    return {"type": "relation", "tags": {"admin_level": str(level), "name": name}}


def test_parse_federal_city_moscow():
    # Moscow: city is admin_level 4, district 8; macro levels 3/5 are ignored.
    els = [
        _admin(2, "Россия"),
        _admin(3, "Центральный федеральный округ"),
        _admin(4, "Москва"),
        _admin(5, "Центральный административный округ"),
        _admin(8, "Таганский район"),
        {"type": "way", "tags": {"highway": "residential", "name": "Воронцовская улица"}},
    ]
    addr = parse_address(els, "ru")
    assert addr.country == "Россия"
    assert addr.city == "Москва"
    assert addr.district == "Таганский район"
    assert addr.street == "Воронцовская улица"


def test_parse_ordinary_city_prefers_level6():
    # Ordinary city: level 4 is the oblast, level 6 is the city itself.
    els = [
        _admin(2, "Россия"),
        _admin(4, "Тульская область"),
        _admin(6, "Тула"),
        _admin(8, "Центральный район"),
    ]
    addr = parse_address(els, "ru")
    assert addr.city == "Тула"  # not the oblast
    assert addr.district == "Центральный район"


def test_parse_prefers_localized_name_and_empty():
    els = [{"type": "relation", "tags": {"admin_level": "4", "name": "Moscow", "name:ru": "Москва"}}]
    assert parse_address(els, "ru").city == "Москва"
    assert parse_address([], "ru") == Address()


# --------------------------------------------------------------------------- #
# Area monologue flow — general -> specific
# --------------------------------------------------------------------------- #
class ScriptNarrator:
    """Narrator that returns tagged text so the flow is observable."""

    async def narrate(self, inp: NarratorInput) -> str:
        return f"OBJECT:{inp.place.name}"

    async def narrate_area(self, inp: AreaInput) -> str:
        kind = "INTRO" if inp.intro else "BEAT"
        return f"AREA:{kind}:{inp.address.district or inp.address.city}"


def _orch(places) -> Orchestrator:
    pipeline = TextPipeline(HeuristicScorer(), ScriptNarrator(), MockEnricher({}))
    geocoder = MockGeocoder(Address(country="Россия", city="Москва", district="Таганский район"))
    return Orchestrator(
        Discovery(StaticPlaceProvider(places)),
        pipeline,
        HeuristicCompanion(),
        InMemoryStateStore(),
        geocoder=geocoder,
    )


def test_area_intro_precedes_objects_then_beats_fill_gaps():
    place = Place(
        id="node/1", name="Дом Музы", category="historic",
        location=GeoPoint(lat=55.7415, lon=37.6539),
    )

    async def run():
        orch = _orch([place])
        here = GeoPoint(lat=55.7415, lon=37.6539)
        outs = []
        for _ in range(5):
            out = await orch.on_position("s1", here, Heading(), Pace.SLOW)
            outs.append(out.text)
        return outs

    outs = asyncio.run(run())
    # 1st line is the area intro (general), BEFORE any object (specific).
    assert outs[0] == "AREA:INTRO:Таганский район"
    # the object is narrated once it is reached.
    assert "OBJECT:Дом Музы" in outs
    # gaps after the object are filled with area beats, not silence.
    assert any(o == "AREA:BEAT:Таганский район" for o in outs[2:])
