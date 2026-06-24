import asyncio

from app.services.enrichment.enricher import (
    EnrichmentCache,
    WebSearchEnricher,
    prefetch,
)
from app.shared.schemas import Candidate, GazeConfidence, GeoPoint, Place


class FakeWebLLM:
    """Stand-in for OpenAICompatLLM.web_facts. ``reply`` may be a string or a
    callable(query)->string; raises ``boom`` times before succeeding."""

    def __init__(self, reply="* факт", boom=0):
        self._reply = reply
        self._boom = boom
        self.calls = 0

    async def web_facts(self, system, user, *, max_results=3, max_tokens=400):
        self.calls += 1
        if self._boom > 0:
            self._boom -= 1
            raise RuntimeError("network")
        return self._reply(user) if callable(self._reply) else self._reply


def _place(pid, name="X", lat=55.75, lon=37.62):
    return Place(id=pid, name=name, category="historic", location=GeoPoint(lat=lat, lon=lon))


def _cand(pid, name="X"):
    return Candidate(place=_place(pid, name), distance_m=10.0, type_weight=1.0,
                     in_gaze_cone=True, gaze_confidence=GazeConfidence.LOW)


def test_returns_and_caches_facts():
    llm = FakeWebLLM(reply="* построен в 1555 году")
    enr = WebSearchEnricher(llm)
    f1 = asyncio.run(enr.facts_for(_place("p1")))
    f2 = asyncio.run(enr.facts_for(_place("p1")))
    assert f1 == "* построен в 1555 году"
    assert f2 == f1
    assert llm.calls == 1  # second call served from cache


def test_no_facts_marker_is_none_and_cached():
    llm = FakeWebLLM(reply="НЕТ")
    enr = WebSearchEnricher(llm)
    assert asyncio.run(enr.facts_for(_place("p2"))) is None
    assert asyncio.run(enr.facts_for(_place("p2"))) is None
    assert llm.calls == 1  # negative result cached, no re-search


def test_error_returns_none_and_is_not_cached():
    llm = FakeWebLLM(reply="* факт", boom=1)
    enr = WebSearchEnricher(llm)
    assert asyncio.run(enr.facts_for(_place("p3"))) is None  # first call raises
    assert asyncio.run(enr.facts_for(_place("p3"))) == "* факт"  # retried, succeeds
    assert llm.calls == 2


def test_query_pins_coordinates():
    q = WebSearchEnricher._query(_place("p4", "Мечеть", lat=43.3177, lon=45.6939), "Грозный")
    assert "Мечеть" in q and "Грозный" in q and "43.3177" in q and "45.6939" in q


def test_prefetch_respects_top_k_and_fills_cache():
    llm = FakeWebLLM(reply=lambda u: f"факт: {u[:6]}")
    enr = WebSearchEnricher(llm)
    cache = EnrichmentCache()
    cands = [_cand(f"p{i}", f"P{i}") for i in range(5)]
    asyncio.run(prefetch(cands, enr, cache, top_k=2))
    assert llm.calls == 2  # only the top 2 were searched
    assert sum(c.place.id in cache for c in cands) == 2


def test_disk_cache_persists(tmp_path):
    path = tmp_path / "facts.json"
    llm = FakeWebLLM(reply="* факт")
    asyncio.run(WebSearchEnricher(llm, cache_path=str(path)).facts_for(_place("p9")))
    assert path.exists()
    # a fresh enricher reads the file and does not call the LLM again
    llm2 = FakeWebLLM(reply="* другое")
    enr2 = WebSearchEnricher(llm2, cache_path=str(path))
    assert asyncio.run(enr2.facts_for(_place("p9"))) == "* факт"
    assert llm2.calls == 0
