"""Narrator role: turn the chosen place + facts into short spoken text.

  * TemplateNarrator — deterministic, no LLM (offline sim / fallback)
  * LLMNarrator      — living prose via an LLMClient (production)

Both return "" for silence (the [SILENCE] sentinel is normalized away).
"""

from __future__ import annotations

from typing import Protocol

from app.services.llm.client import LLMClient
from app.shared.schemas import NarratorInput, Significance

from .prompts import build_narrator_user, system_for
from .significance import role_for_significance

SILENCE = "[SILENCE]"

# very rough per-category openers for the template fallback (no facts case)
_GENERIC = {
    "park": "Слева небольшой сквер — обычное место, чтобы перевести дух.",
    "garden": "Тут рядом садик, ничего особенного, но приятно.",
    "shop": "",  # commercial without facts → stay silent
    "cafe": "",
    "building": "",
}


def normalize(text: str) -> str:
    text = text.strip()
    return "" if text == SILENCE or not text else text


class Narrator(Protocol):
    async def narrate(self, inp: NarratorInput) -> str: ...


class TemplateNarrator:
    async def narrate(self, inp: NarratorInput) -> str:
        if inp.flags.nothing_new:
            return ""  # idle: silence (the living-companion line is the LLM's job)

        name = inp.place.name
        if any(name in h for h in inp.history):
            return ""  # already covered this place — don't repeat

        prefix = "А вот это уже интереснее — " if inp.flags.switching else ""

        if inp.facts:
            body = inp.facts.strip()
            if len(body) > 220 and not _is_high(inp.significance):
                body = body[:220].rsplit(" ", 1)[0] + "…"
            return normalize(f"{prefix}{name}. {body}")

        # no facts: only speak for genuinely notable types, else silence
        generic = _GENERIC.get(inp.place.category, "")
        return normalize(f"{prefix}{generic}" if generic else "")


class LLMNarrator:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def narrate(self, inp: NarratorInput) -> str:
        # Deterministic silence — decide in code, don't spend an LLM call (or rely
        # on the model's reasoning) to stay quiet. Elaborate mode is the exception:
        # it deliberately revisits an already-covered place to add new detail.
        if not inp.flags.elaborate:
            if inp.flags.nothing_new:
                return ""
            if any(inp.place.name in h for h in inp.history):
                return ""  # already covered this place — never repeat
        role = role_for_significance(inp.significance)
        system = system_for(role, inp.language)
        user = build_narrator_user(inp)
        text = await self._llm.complete_text(role, system, user)
        return normalize(text)


def _is_high(s: Significance) -> bool:
    return s in (Significance.HIGH, Significance.LANDMARK)
