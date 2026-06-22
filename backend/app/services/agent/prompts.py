"""Prompt assembly: CORE + role block + runtime context.

Loads the versionable templates from ``/prompts`` and builds the per-step user
message for each role from the typed inputs. Static prefix (CORE+ROLE) is kept
separate from the volatile RUNTIME_CONTEXT so it can be prompt-cached later.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from app.services.llm.router import Role
from app.shared.schemas import CompanionInput, NarratorInput, ScorerInput

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"

_ROLE_FILE = {
    Role.SCORER: "scorer",
    Role.NARRATOR: "narrator",
    Role.LANDMARK: "narrator",  # same role block, premium model
    Role.COMPANION: "companion",
}


@cache
def _load(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


def system_for(role: Role, language: str) -> str:
    """CORE(language) + the role-specific block — the cacheable static prefix."""
    core = _load("core").replace("{language}", language)
    return f"{core}\n\n---\n\n{_load(_ROLE_FILE[role])}"


def _json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------- #
# user-message builders (volatile RUNTIME_CONTEXT)
# --------------------------------------------------------------------------- #
def build_scorer_user(inp: ScorerInput) -> str:
    candidates = [
        {
            "place_id": c.place.id,
            "name": c.place.name,
            "type": c.place.category,
            "type_weight": c.type_weight,
            "distance_m": c.distance_m,
            "in_gaze_cone": c.in_gaze_cone,
            "gaze_confidence": c.gaze_confidence.value,
            "facts_available": c.facts_available,
            "facts_snippet": c.facts_snippet,
        }
        for c in inp.candidates
    ]
    return _json(
        {
            "CANDIDATES": candidates,
            "ADDRESS": inp.address.model_dump(exclude_none=True),
            "SEEN": inp.seen,
            "PREFERENCES": inp.preferences.model_dump() if inp.preferences else None,
        }
    )


def build_narrator_user(inp: NarratorInput) -> str:
    return _json(
        {
            "PLACE": {"name": inp.place.name, "type": inp.place.category},
            "SIGNIFICANCE": inp.significance.value,
            "FACTS": inp.facts,
            "DISTANCE": inp.distance_m,
            "HEADING": {
                "direction_deg": inp.heading.direction_deg,
                "gaze_confidence": inp.heading.gaze_confidence.value,
            },
            "PACE": inp.pace.value,
            "CONTEXT": inp.context.model_dump(exclude_none=True),
            "HISTORY": inp.history,
            "FLAGS": {
                "switching": inp.flags.switching,
                "nothing_new": inp.flags.nothing_new,
                "preferences": (
                    inp.flags.preferences.model_dump() if inp.flags.preferences else None
                ),
            },
        }
    )


def build_companion_user(inp: CompanionInput) -> str:
    return _json(
        {
            "USER_MESSAGE": inp.user_message,
            "CONTEXT": inp.context.model_dump(exclude_none=True),
            "LAST_NARRATION": inp.last_narration,
            "ADDRESS": inp.address.model_dump(exclude_none=True),
            "HISTORY": inp.history,
        }
    )
