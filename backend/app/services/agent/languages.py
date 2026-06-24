"""Supported guide languages — single source of truth (backend side).

Codes are ISO-639-1. faster-whisper accepts these directly (incl. ``zh``), so
STT needs no mapping. The LLM prompt wants a human-readable language name, so
``prompt_language`` maps code -> name for the ``{language}`` placeholder in
``prompts/core.txt``. The client owns the code -> BCP-47 mapping for TTS.
"""

from __future__ import annotations

# code -> name injected into the CORE prompt's "{language}" placeholder.
PROMPT_NAME: dict[str, str] = {
    "en": "English",
    "ru": "русском (Russian)",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "zh": "Chinese",
}

SUPPORTED: frozenset[str] = frozenset(PROMPT_NAME)
FALLBACK = "en"


def normalize(code: str | None) -> str:
    """Map an arbitrary locale/code to a supported code, else fall back to EN."""
    if not code:
        return FALLBACK
    short = code.replace("_", "-").split("-", 1)[0].lower()
    return short if short in SUPPORTED else FALLBACK


def prompt_language(code: str | None) -> str:
    """Human-readable language name for the narration prompt."""
    return PROMPT_NAME[normalize(code)]
