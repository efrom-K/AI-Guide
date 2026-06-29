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


# --- Spoken-verbatim strings ------------------------------------------------- #
# These reach the user WITHOUT passing through the LLM (the narrator re-expresses
# facts in {language}, but these are emitted as-is), so they MUST be localized.

# Short bridges said when the area material is exhausted and nothing is nearby:
# one is spoken, then the guide goes genuinely quiet. Per language, fallback EN.
_BRIDGES: dict[str, tuple[str, ...]] = {
    "ru": (
        "Идём дальше.",
        "Пройдём дальше, тут пока тихо.",
        "Двигаемся дальше.",
        "Идём дальше — расскажу, как только будет что.",
    ),
    "en": (
        "Let's move on.",
        "Let's walk on — it's quiet here for now.",
        "Onward.",
        "Let's keep walking — I'll chime in as soon as there's something.",
    ),
    "es": (
        "Sigamos.",
        "Sigamos caminando, por ahora hay poco que contar.",
        "Avancemos.",
        "Sigamos andando, te aviso en cuanto haya algo.",
    ),
    "fr": (
        "Continuons.",
        "Avançons, c'est calme par ici pour l'instant.",
        "Poursuivons.",
        "Marchons encore, je reprends dès qu'il y a quelque chose.",
    ),
    "de": (
        "Gehen wir weiter.",
        "Gehen wir weiter, hier ist es gerade ruhig.",
        "Weiter geht's.",
        "Laufen wir weiter — ich melde mich, sobald es etwas gibt.",
    ),
    "it": (
        "Andiamo avanti.",
        "Proseguiamo, qui per ora è tranquillo.",
        "Continuiamo.",
        "Camminiamo ancora un po', ti dico appena c'è qualcosa.",
    ),
    "pt": (
        "Vamos seguindo.",
        "Vamos em frente, por aqui está calmo por agora.",
        "Seguimos.",
        "Vamos caminhando, eu aviso assim que houver algo.",
    ),
    "zh": (
        "我们继续走吧。",
        "继续走吧，这里暂时没什么可说的。",
        "往前走。",
        "继续走，一有什么我马上告诉你。",
    ),
}

# Shown to the user (as a transient toast) when speech wasn't intelligible.
_STT_UNCLEAR: dict[str, str] = {
    "ru": "Не расслышал — повтори, пожалуйста.",
    "en": "Didn't catch that — please say it again.",
    "es": "No te he entendido, ¿puedes repetir?",
    "fr": "Je n'ai pas bien entendu, peux-tu répéter ?",
    "de": "Das habe ich nicht verstanden — bitte noch einmal.",
    "it": "Non ho capito bene, puoi ripetere?",
    "pt": "Não entendi bem — pode repetir, por favor?",
    "zh": "没有听清，请再说一遍。",
}


def bridges(code: str | None) -> tuple[str, ...]:
    """Spoken-verbatim 'let's move on' bridges in the session language."""
    return _BRIDGES.get(normalize(code), _BRIDGES[FALLBACK])


def stt_unclear(code: str | None) -> str:
    """'Didn't catch that' message in the session language."""
    return _STT_UNCLEAR.get(normalize(code), _STT_UNCLEAR[FALLBACK])


# --- Model-facing cascade strings (steer the LLM; output language is governed by
# core.txt's {language}, so English steering is enough for every non-RU session).
# Russian is kept byte-identical to the original so the tuned RU flow is unchanged.

_LEVEL_LABELS_EN = ("city", "district", "street")
_LEVEL_LABELS: dict[str, tuple[str, str, str]] = {
    "ru": ("город", "район", "улицу"),
}

_AREA_TOPIC_EN = (
    "another non-obvious, atypical fact about the {label} {name} — something "
    "people usually don't know; no platitudes and no repeats"
)
_AREA_TOPIC: dict[str, str] = {
    "ru": (
        "ещё один неочевидный, нетипичный факт про {label} {name} — "
        "то, чего обычно не знают; без банальностей и без повторов"
    ),
}

_STREET_HOOK_EN = "stepping onto {street}"
_STREET_HOOK: dict[str, str] = {
    "ru": "переход на улицу {street}",
}

_AREA_INTRO_TOLD_EN = "area intro"
_AREA_INTRO_TOLD: dict[str, str] = {
    "ru": "вступление в район",
}


def level_labels(code: str | None) -> tuple[str, str, str]:
    """(city, district, street) labels for the cascade, in the session language."""
    return _LEVEL_LABELS.get(normalize(code), _LEVEL_LABELS_EN)


def area_topic(code: str | None, label: str, name: str) -> str:
    """One cascade-beat instruction for the area narrator."""
    tmpl = _AREA_TOPIC.get(normalize(code), _AREA_TOPIC_EN)
    return tmpl.format(label=label, name=name)


def street_hook(code: str | None, street: str) -> str:
    """next_hook baton woven in when the walker steps onto a new street."""
    return _STREET_HOOK.get(normalize(code), _STREET_HOOK_EN).format(street=street)


def area_intro_told(code: str | None) -> str:
    """Internal 'told' ledger marker for the area opener."""
    return _AREA_INTRO_TOLD.get(normalize(code), _AREA_INTRO_TOLD_EN)
