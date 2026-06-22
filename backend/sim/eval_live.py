"""Live quality eval against the configured OpenAI-compatible model.

    python -m sim.eval_live            # default 8 samples per check
    python -m sim.eval_live --n 20

Runs rule-based checks (the ones we can verify deterministically) many times and
reports hold-rates. Seeds the eval harness (task #10); LLM-as-judge can layer on.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.agent.companion import LLMCompanion
from app.services.agent.narrator import LLMNarrator
from app.services.agent.scorer import LLMScorer
from app.services.llm.client import OpenAICompatLLM
from app.shared.schemas import (
    Candidate,
    CompanionInput,
    GazeConfidence,
    GeoPoint,
    Heading,
    NarratorFlags,
    NarratorInput,
    Place,
    ScorerInput,
    Significance,
)

_LR = re.compile(r"\b(слева|справа|левее|правее|налево|направо)\b", re.IGNORECASE)
_MD = re.compile(r"(^\s*[-*#]\s)|(\]\(https?://)|(```)", re.MULTILINE)
_CYR = re.compile(r"[а-яё]", re.IGNORECASE)
_CLICHE = re.compile(r"(уникальн|сердце города|важная точка|не оставит равнодушн)", re.IGNORECASE)


def _place(pid, name, cat) -> Place:
    return Place(id=pid, name=name, category=cat, location=GeoPoint(lat=55.75, lon=37.62))


def _cand(pid, name, cat, w, facts=None) -> Candidate:
    return Candidate(
        place=_place(pid, name, cat),
        distance_m=20.0,
        type_weight=w,
        in_gaze_cone=True,
        gaze_confidence=GazeConfidence.LOW,
        facts_available=facts is not None,
        facts_snippet=facts,
    )


def _narr(**kw) -> NarratorInput:
    base = dict(
        place=_place("p", "Музей", "museum"),
        significance=Significance.HIGH,
        facts="Краснокирпичное здание конца девятнадцатого века, музей истории.",
        distance_m=30.0,
        heading=Heading(direction_deg=90.0, gaze_confidence=GazeConfidence.LOW),
    )
    base.update(kw)
    return NarratorInput(**base)


def _bar(rate: float, width: int = 24) -> str:
    fill = round(rate * width)
    return "█" * fill + "·" * (width - fill)


async def main(n: int) -> None:
    llm = OpenAICompatLLM()
    scorer, narrator, companion = LLMScorer(llm), LLMNarrator(llm), LLMCompanion(llm)
    results: list[tuple[str, int, int]] = []

    async def check(name: str, runs, predicate):
        ok = 0
        for r in runs:
            try:
                if await predicate(r):
                    ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"   ! {name}: {type(e).__name__}: {e}")
        results.append((name, ok, len(runs)))

    cands = [
        _cand("shop", "ГУМ", "shop", 0.25),
        _cand("mus", "Музей", "museum", 0.9, facts="Музей."),
    ]

    await check("Scorer: валидный JSON + выбор", range(n),
                lambda _: _scorer_ok(scorer, cands))
    await check("Narrator: без markdown/URL", range(n),
                lambda _: _text_ok(narrator, _narr(), lambda t: t and not _MD.search(t)))
    await check("Narrator: без клише", range(n),
                lambda _: _text_ok(narrator, _narr(), lambda t: not _CLICHE.search(t)))
    await check("Narrator: нет лево/право при low-gaze", range(n),
                lambda _: _text_ok(narrator, _narr(), lambda t: not _LR.search(t)))
    await check("Narrator: [SILENCE] при nothing_new", range(n),
                lambda _: _text_ok(
                    narrator,
                    _narr(facts=None, significance=Significance.LOW,
                          flags=NarratorFlags(nothing_new=True)),
                    lambda t: t == ""))
    await check("Narrator: EN при language=en", range(n),
                lambda _: _text_ok(
                    narrator, _narr(facts="A red-brick history museum.", language="en"),
                    lambda t: t and len(_CYR.findall(t)) <= 2))
    phrases = ["пропускай магазины", "давай покороче", "помолчи немного"]
    await check("Companion: извлекает control_patch", phrases,
                lambda p: _companion_ok(companion, p))

    print("\n=== Live eval (model: qwen via LM Studio) ===")
    for name, ok, total in results:
        rate = ok / total if total else 0
        print(f"{_bar(rate)}  {ok:2}/{total:<2} {int(rate*100):3}%  {name}")


async def _scorer_ok(scorer, cands) -> bool:
    out = await scorer.score(ScorerInput(candidates=cands))
    return {s.place_id for s in out.scored} == {"shop", "mus"} and out.next in (None, "shop", "mus")


async def _text_ok(narrator, inp, predicate) -> bool:
    return bool(predicate(await narrator.narrate(inp)))


async def _companion_ok(companion, phrase) -> bool:
    out = await companion.respond(CompanionInput(user_message=phrase))
    if not out.reply:
        return False
    p = out.control_patch
    if phrase.startswith("пропускай"):
        return bool(p and p.skip_categories)
    if "покороче" in phrase:
        return bool(p and p.verbosity == "shorter")
    if "помолчи" in phrase:
        return bool(p and p.mute)
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    asyncio.run(main(ap.parse_args().n))
