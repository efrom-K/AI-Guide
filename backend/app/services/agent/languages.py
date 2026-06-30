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


# Practical Russian Cyrillic -> Latin romanization. Used as the last-resort title for
# a non-Russian session when OSM has no exonym, so a minor object like "Звонница" is
# shown as "Zvonnitsa" (how the narrator already pronounces it) instead of raw Cyrillic.
_CYR_LAT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # a few non-Russian Cyrillic letters so Ukrainian/Serbian names degrade gracefully
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ђ": "dj", "ј": "j", "љ": "lj",
    "њ": "nj", "ћ": "c", "џ": "dz", "ў": "u",
}


def _has_cyrillic(s: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in s)


def transliterate(s: str) -> str:
    """Romanize Cyrillic to Latin; non-Cyrillic chars pass through unchanged. Source
    case is preserved (an uppercase letter capitalizes its multi-char romanization)."""
    out: list[str] = []
    for ch in s:
        low = ch.lower()
        rep = _CYR_LAT.get(low)
        if rep is None:
            out.append(ch)  # Latin, digits, spaces, punctuation
        elif ch == low or not rep:
            out.append(rep)
        else:
            out.append(rep[0].upper() + rep[1:])  # uppercase source -> "Shch", "Ya"
    return "".join(out)


def display_name(tags: dict[str, str], fallback: str, code: str | None) -> str:
    """Localized display name for a POI / place.

    The raw OSM ``name`` tag is in the LOCAL language (Russian in Moscow, Greek in
    Athens, ...), so a walker who picked English would otherwise see/hear Cyrillic
    titles. Resolution:

    1. ``name:<session-lang>`` — an exact match in the chosen language is always best.
    2. Otherwise the raw local ``name`` for a **Russian** session: Russia is the
       primary deployment region, where the raw tag is already Russian, so a RU
       walker must keep the authentic Cyrillic name (never the English exonym).
    3. For any other (international) session: the English exonym ``name:en``, then the
       official ``int_name``; failing both, a Cyrillic raw name is **romanized** to
       Latin so the title is readable and matches the spoken narration (the narrator
       transliterates proper names anyway). A name already in Latin is kept as-is.

    The ``name:<lang>`` / ``int_name`` tags must be kept on the Place (see ``KEEP_TAGS``
    in geo/categories.py). Compare geocoder ``_name``, which localizes street/city names."""
    lang = normalize(code)
    exact = tags.get(f"name:{lang}")
    if exact:
        return exact
    if lang == "ru":
        return fallback  # raw tag is the authentic Russian name in the home region
    chosen = tags.get("name:en") or tags.get("int_name") or fallback
    return transliterate(chosen) if _has_cyrillic(chosen) else chosen


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
