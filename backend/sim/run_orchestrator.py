"""Full orchestrator loop over the virtual walk, with an injected barge-in.

    python -m sim.run_orchestrator

Shows FSM states, memory-backed dedup, adaptive radius, the heuristic gate
("…gated"), and a mid-walk voice question that steers the tour via control_patch.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.agent.companion import HeuristicCompanion
from app.services.agent.narrator import TemplateNarrator
from app.services.agent.orchestrator import Orchestrator
from app.services.agent.pipeline import TextPipeline
from app.services.agent.scorer import HeuristicScorer
from app.services.enrichment.enricher import MockEnricher
from app.services.geo.discovery import Discovery
from app.services.geo.providers import StaticPlaceProvider
from app.services.state.store import InMemoryStateStore
from sim.routes import RED_SQUARE
from sim.walk import walk

_FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
_BARGE_IN_AT = 40.0  # seconds into the walk


async def main() -> None:
    provider = StaticPlaceProvider.from_json(_FIX / "places_red_square.json")
    pipeline = TextPipeline(
        HeuristicScorer(),
        TemplateNarrator(),
        MockEnricher.from_json(_FIX / "facts_red_square.json"),
    )
    orch = Orchestrator(Discovery(provider), pipeline, HeuristicCompanion(), InMemoryStateStore())
    sid = "demo"
    barged = False

    for step in walk(RED_SQUARE, speed_mps=1.3, step_s=8.0):
        if not barged and step.t >= _BARGE_IN_AT:
            barged = True
            reply = await orch.on_utterance(sid, "Слушай, пропускай магазины")
            print(f"t={step.t:5.0f}s  [{reply.state}]  🎙 Ты: Пропускай магазины")
            print(f"                   💬 Гид: {reply.text}")

        out = await orch.on_position(sid, step.position, step.heading, step.pace)
        line = f"t={step.t:5.0f}s  [{out.state}]"
        if out.kind == "narration":
            print(f"{line}  🗣 {out.text}")
        elif out.kind == "silence":
            print(f"{line}  …")


if __name__ == "__main__":
    asyncio.run(main())
