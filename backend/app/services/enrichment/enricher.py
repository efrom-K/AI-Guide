"""Fact enrichment: a cache + providers, kept OFF the hot-path.

The orchestrator prefetches facts for upcoming places into the cache; the
narrator reads the cache non-blocking (a miss → empty FACTS → generic/silence).
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Protocol

import httpx

from app.shared.schemas import Candidate, Place

_log = logging.getLogger("aiguide.enrich")


class Enricher(Protocol):
    async def facts_for(self, place: Place, context: str | None = None) -> str | None: ...


class EnrichmentCache:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def get(self, place_id: str) -> str | None:
        return self._cache.get(place_id)

    def put(self, place_id: str, facts: str) -> None:
        self._cache[place_id] = facts

    def __contains__(self, place_id: str) -> bool:
        return place_id in self._cache


class MockEnricher:
    """Facts from a static fixture (place_id -> facts). For offline sim/tests."""

    def __init__(self, facts: dict[str, str]) -> None:
        self._facts = facts

    async def facts_for(self, place: Place, context: str | None = None) -> str | None:
        return self._facts.get(place.id)

    @classmethod
    def from_json(cls, path: str | Path) -> MockEnricher:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))


_ENRICH_SYSTEM = (
    "Ты собираешь проверяемые факты о конкретном месте для аудиогида. Место задано "
    "названием, городом/страной и координатами. КРИТИЧНО: бери факты только об этом "
    "самом объекте в указанном месте. Если результаты поиска относятся к одноимённому "
    "объекту в другом городе или стране — игнорируй их. Никогда не смешивай факты о "
    "разных местах. По результатам веб-поиска выдай 2-4 кратких достоверных факта "
    "(история, кто/когда построил, чем примечательно, любопытные детали). Только факты, "
    "без воды и оценок, без выдумок. Если нет надёжной информации именно об этом месте "
    "в указанной локации — ответь ровно: НЕТ."
)


class WebSearchEnricher:
    """Real facts via the OpenRouter "web" plugin. Off the hot-path: a per-place
    negative+positive cache (memory, optionally a JSON file) means each place is
    searched at most once; network/empty results degrade to None (no facts)."""

    def __init__(
        self,
        llm,
        *,
        max_results: int = 3,
        max_tokens: int = 400,
        cache_path: str = "",
    ) -> None:
        self._llm = llm
        self._max_results = max_results
        self._max_tokens = max_tokens
        self._path = Path(cache_path) if cache_path else None
        self._cache: dict[str, str | None] = {}
        if self._path and self._path.exists():
            try:
                self._cache = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    @staticmethod
    def _query(place: Place, context: str | None) -> str:
        # Always pin the location with coordinates so the model can reject a
        # same-named place elsewhere (e.g. an OSM "Eurocity" in Moscow vs Gibraltar).
        where = context or place.tags.get("addr:city") or ""
        coords = f"координаты {place.location.lat:.4f}, {place.location.lon:.4f}"
        parts = [
            place.name,
            f"({place.category})" if place.category else "",
            where,
            coords,
        ]
        return " ".join(p for p in parts if p).strip()

    def _persist(self) -> None:
        if not self._path:
            return
        try:
            self._path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    async def facts_for(self, place: Place, context: str | None = None) -> str | None:
        if place.id in self._cache:
            return self._cache[place.id]
        facts: str | None = None
        try:
            text = await self._llm.web_facts(
                _ENRICH_SYSTEM,
                self._query(place, context),
                max_results=self._max_results,
                max_tokens=self._max_tokens,
            )
            cleaned = text.strip()
            if cleaned and cleaned.upper().lstrip("*•-. ").startswith("НЕТ") is False:
                facts = cleaned
        except Exception as e:  # network/provider hiccup — degrade to no facts
            _log.warning("enrich failed for %s: %s", place.id, e)
            return None  # transient: don't cache, retry on a later tick
        self._cache[place.id] = facts
        self._persist()
        return facts


class WikiEnricher:
    """Free facts from Wikipedia/Wikidata for OSM places tagged wikipedia=/wikidata=.
    Most landmarks carry these tags, so this covers them at no cost (and higher
    quality) — the paid web search is only needed for the untagged long tail."""

    def __init__(
        self, *, summary_chars: int = 700, prefer_langs: tuple[str, ...] = ("ru", "en")
    ) -> None:
        self._chars = summary_chars
        self._prefer = prefer_langs
        self._cache: dict[str, str | None] = {}

    async def facts_for(self, place: Place, context: str | None = None) -> str | None:
        wp = place.tags.get("wikipedia")
        wd = place.tags.get("wikidata")
        if not wp and not wd:
            return None
        if place.id in self._cache:
            return self._cache[place.id]
        facts: str | None = None
        try:
            # Wikimedia requires a descriptive User-Agent (a bare one is 403'd).
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "AI-Audio-Guide/0.1 "
                    "(https://github.com/ai-audio-guide; audioguide@example.org)"
                },
            ) as client:
                if wp:
                    lang, _, title = wp.partition(":")
                    if not title:  # tag was just a title, no "lang:" prefix
                        lang, title = self._prefer[0], wp
                    facts = await self._summary(client, lang, title)
                if not facts and wd:
                    facts = await self._from_wikidata(client, wd)
        except Exception as e:  # transient network/parse — don't cache, retry later
            _log.warning("wiki enrich failed for %s: %s", place.id, e)
            return None
        self._cache[place.id] = facts
        return facts

    async def _summary(self, client: httpx.AsyncClient, lang: str, title: str) -> str | None:
        t = urllib.parse.quote(title.replace(" ", "_"), safe="")
        r = await client.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{t}")
        if r.status_code != 200:
            return None
        extract = (r.json().get("extract") or "").strip()
        return extract[: self._chars] if extract else None

    async def _from_wikidata(self, client: httpx.AsyncClient, qid: str) -> str | None:
        r = await client.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
        if r.status_code != 200:
            return None
        links = r.json().get("entities", {}).get(qid, {}).get("sitelinks", {})
        for lang in self._prefer:
            sl = links.get(f"{lang}wiki")
            if sl:
                return await self._summary(client, lang, sl["title"])
        return None


class CompositeEnricher:
    """Wikipedia first (free), then the paid web search only for places without a
    wiki article and notable enough (type weight >= ``web_min_weight``)."""

    def __init__(self, wiki: Enricher, web: Enricher, *, web_min_weight: float = 0.0) -> None:
        self._wiki = wiki
        self._web = web
        self._web_min_weight = web_min_weight

    async def facts_for(self, place: Place, context: str | None = None) -> str | None:
        facts = await self._wiki.facts_for(place, context)
        if facts:
            return facts
        from app.services.geo.categories import weight_for

        if weight_for(place.category) >= self._web_min_weight:
            return await self._web.facts_for(place, context)
        return None


async def prefetch(
    candidates: list[Candidate],
    enricher: Enricher,
    cache: EnrichmentCache,
    *,
    top_k: int | None = None,
    timeout_s: float | None = None,
    context: str | None = None,
) -> None:
    """Populate the cache with facts for the uncached candidates.

    Only the top ``top_k`` (ranking-ordered, best first) are fetched — concurrently
    and bounded by ``timeout_s`` so a slow/real provider can't stall the tick. Any
    fetch that hasn't finished in time is dropped; its place is retried next tick.
    With ``top_k=None`` and ``timeout_s=None`` every candidate is fetched (the cheap
    mock/fixture path used by tests).
    """
    pending = [c for c in candidates if c.place.id not in cache]
    if top_k is not None:
        pending = pending[:top_k]
    if not pending:
        return

    async def _one(c: Candidate) -> tuple[str, str | None]:
        return c.place.id, await enricher.facts_for(c.place, context)

    tasks = [asyncio.ensure_future(_one(c)) for c in pending]
    done, not_done = await asyncio.wait(tasks, timeout=timeout_s)
    for t in not_done:
        t.cancel()
    for t in done:
        try:
            place_id, facts = t.result()
        except Exception:  # noqa: BLE001 — one bad fetch shouldn't sink the rest
            continue
        if facts:
            cache.put(place_id, facts)


def attach_facts(candidates: list[Candidate], cache: EnrichmentCache) -> list[Candidate]:
    """Return candidates with facts_available/facts_snippet filled from the cache."""
    out: list[Candidate] = []
    for c in candidates:
        facts = cache.get(c.place.id)
        out.append(
            c.model_copy(update={"facts_available": facts is not None, "facts_snippet": facts})
        )
    return out
