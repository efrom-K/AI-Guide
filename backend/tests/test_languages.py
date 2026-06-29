"""Localization helpers for spoken-verbatim + model-facing agent strings.

The bridges and the STT 'didn't catch that' message reach the user WITHOUT going
through the LLM, so they must be in the session language. The cascade strings steer
the LLM (output language is set by core.txt), so Russian stays byte-identical to the
tuned flow and every other language falls back to neutral English.
"""

from app.services.agent import languages as lang


def test_bridges_are_localized_per_language():
    ru = lang.bridges("ru")
    en = lang.bridges("en")
    assert ru and en
    assert ru != en  # genuinely translated, not echoed
    assert "Идём" in ru[0]
    # every supported language resolves to a non-empty tuple
    for code in ("es", "fr", "de", "it", "pt", "zh"):
        assert lang.bridges(code)
    # unknown code falls back to English
    assert lang.bridges("xx") == en


def test_stt_unclear_is_localized():
    assert lang.stt_unclear("ru") == "Не расслышал — повтори, пожалуйста."
    assert lang.stt_unclear("fr").lower().startswith("je n")
    assert lang.stt_unclear("xx") == lang.stt_unclear("en")  # fallback


def test_cascade_strings_ru_identical_others_english():
    # Russian is preserved exactly so the tuned RU flow is unchanged.
    assert lang.level_labels("ru") == ("город", "район", "улицу")
    assert "про город Москва" in lang.area_topic("ru", "город", "Москва")
    assert lang.street_hook("ru", "Тверская") == "переход на улицу Тверская"
    assert lang.area_intro_told("ru") == "вступление в район"

    # Non-Russian sessions steer the LLM in neutral English.
    assert lang.level_labels("fr") == ("city", "district", "street")
    assert "city Paris" in lang.area_topic("fr", "city", "Paris")
    assert lang.street_hook("de", "Hauptstraße") == "stepping onto Hauptstraße"
    assert lang.area_intro_told("es") == "area intro"
