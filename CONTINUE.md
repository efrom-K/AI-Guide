# CONTINUE.md — состояние проекта «AI Audio Guide» (для продолжения работы)

> Хэндофф-документ для следующей сессии. Здесь максимум контекста: что есть, как
> запускать, что осталось, и где именно мы остановились. Дизайн-спека — в
> `ARCHITECTURE.md`, план — в файле плана сессии. Канонические промпты — в
> `backend/prompts/*.txt`.

Дата паузы: 2026-06-23. Рабочая папка: `D:\VS_Code\AI Guide`. Платформа: Windows 11,
PowerShell + Git Bash. Git: репозиторий инициализирован, по коммиту на этап.

---

## 1. Что это и как устроено (коротко)

Автономный аудиогид реального времени: GPS+направление → находим места → оцениваем
значимость → обогащаем фактами → озвучиваем живой рассказ; можно прервать голосом и
порулить экскурсией. **Один оркестратор-«мозг»** + 3 stateless LLM-роли
(**Scorer**→JSON, **Narrator**→текст, **Companion**→чат), общающиеся только через общее
состояние сессии. Вокруг — службы Geo (OSM/фикстуры), Enrichment (факты+кэш), TTS, STT,
State (in-memory/Redis). Клиент-сервер по WebSocket; клиент — Flutter.

---

## 2. Текущее состояние: что РАБОТАЕТ

Серверное ядро готово и проверено **end-to-end на живой локальной модели** (qwen via LM
Studio). 37 автотестов зелёные, ruff чист.

| Этап | Статус | Суть |
|---|---|---|
| 0 Каркас | ✅ | FastAPI, схемы, конфиг, тесты |
| 1 Geo + sim | ✅ | Overpass+фикстуры, ранжирование (дистанция/тип/конус), адаптивный радиус, дедуп, виртуальная прогулка |
| 2 Промпты + пайплайн | ✅ | CORE+роли; Scorer(JSON)/Narrator/Companion; провайдер-агностичный LLMClient |
| 3 Оркестратор | ✅ | FSM, память сессии, эвристический гейт, control_patch, mute, OFFLINE/ERROR/RECOVERY |
| 4 WebSocket + TTS-интерфейс | ✅ | `/ws`, веб-демо, eval-харнесс. Реальный TTS НЕ подключён (NullTTS) |
| 5 STT (голосовой barge-in) | ✅ | STTClient + MockSTT + FasterWhisperSTT (локально), микрофон в вебе |
| 6a Flutter web/десктоп | ✅ | Клиент компилируется (`flutter build web` OK), analyze чист, виджет-тест |
| 6b Android | 🔶 в процессе | Тулчейн `[√]`, лицензии приняты, cmdline-tools есть. **Нет эмулятора/системного образа. APK ещё не собирал.** |

**Демо, которые реально работают сейчас:**
- `python -m sim.run_orchestrator --llm openai` — полный агент на qwen (рассказ, переключения, гейт, barge-in).
- Браузер `http://localhost:8000` — прогулка + вопросы + кнопка голос.
- `python -m sim.eval_live --n 8` — метрики качества в процентах.

---

## 3. Что ОСТАЛОСЬ

**Главные продуктовые дыры:**
- **TTS не подключён** — аудиогид пока НЕ говорит (везде только текст). План: локальный
  **Piper** (поставить как whisper, бесплатно). Это самая ценная недостающая часть.
- **Мультиязычность** (Этап 7): EN плавает 0–75%, т.к. `{language}` суётся в русский CORE.
  Нужны **per-language CORE-шаблоны**.

**Этап 6b (мобильный):** собрать APK; создать эмулятор (нужен системный образ) или
подключить телефон; добавить реальные сенсоры (GPS/компас/микрофон) вместо симуляции.

**Этап 7:** мультиязычность, бюджет латентности (assert в sim), полировка, README.

**Ревью-задачи (#9–#13):**
- #9 удешевление hot-path — гейт сделан; осталось **prompt caching** (нужно при облаке).
- #10 eval-харнесс — базовый есть (`sim/eval_live.py`); добавить **LLM-as-judge + golden-корпус**.
- #11 FSM — состояния/переходы есть; **отмена in-flight стрима Narrator** при barge-in (когда будет стриминговый TTS).
- #12 продакшн-реалии — offline-режим (клиентское редуцированное ядро), privacy/consent/TTL, AEC для голоса, OSM ODbL-атрибуция, battery, pedestrian safety.
- #13 verification id/цен (DeepSeek/GLM/Gemini) + мультипровайдерный роутер (сейчас только интерфейс + OpenAI-совместимый клиент).

**Состояние тасков (Task tool):** 1–5 completed, 6 in_progress, 7 pending, 9–13 pending.

---

## 4. Структура репозитория

```
ARCHITECTURE.md        дизайн-спека (архитектура, полный промпт, выбор моделей, пример)
CLAUDE.md              гайд для будущих сессий
CONTINUE.md            этот файл
BUSINESS_LOGICS.pdf    исходная бизнес-логика (RU)
backend/
  .venv/               Python 3.14 venv
  .env                 локальные секреты (gitignored): LM Studio creds
  pyproject.toml       deps; extras: [dev], [stt]
  app/
    config.py          Settings (pydantic-settings, читает .env + env vars)
    main.py            FastAPI: /health, /, /ws (position/utterance/audio/control)
    shared/
      schemas.py       ВСЕ схемы (домен, роли I/O, control_patch, SessionState, WS-сообщения)
      geo_math.py      haversine/bearing/angle_diff
    services/
      geo/             categories, providers (Overpass+Static), ranking, discovery
      enrichment/      enricher (EnrichmentCache, MockEnricher, prefetch/attach_facts)
      agent/           prompts, significance, scorer, narrator, companion,
                       pipeline, orchestrator (FSM), factory (build_orchestrator)
      llm/             router (Role→model), client (LLMClient: AnthropicLLM,
                       FakeLLM, OpenAICompatLLM)
      state/           store (StateStore: InMemory, Redis, default_store)
      tts/             tts (TTSClient, NullTTS)  ← реального TTS пока нет
      stt/             stt (STTClient, MockSTT, FasterWhisperSTT, build_stt)
  prompts/             core.txt, narrator.txt, scorer.txt, companion.txt  ← КАНОН
  sim/                 walk, routes, run_geo, run_agent, run_orchestrator, eval_live
  tests/               37 проходят; test_llm_live (skip без LM Studio); test_stt_live (opt-in)
  web/index.html       браузерное демо (прогулка + чат + микрофон)
mobile/                Flutter-клиент (web/windows готовы; android-скаффолд есть)
  lib/main.dart        тонкий WS-клиент: симуляция прогулки + рассказ/ответ + вопрос
  pubspec.yaml         web_socket_channel; плагины сенсоров закомментированы
```

---

## 5. Окружение (важные факты)

- **Python 3.14.5**, venv: `backend\.venv`. Запуск: `.\.venv\Scripts\python.exe`.
- **LM Studio** на `http://localhost:1234/v1` (OpenAI-совместимый). Загружена модель
  **`qwen/qwen3.5-9b`** (ещё доступны `google/gemma-4-12b-qat`, `google/gemma-4-e4b`).
- **`backend/.env`** (gitignored): `OPENAI_BASE_URL=http://localhost:1234/v1`,
  `OPENAI_API_KEY=lm-studio`, `OPENAI_MODEL=qwen/qwen3.5-9b`. `AGENT_BACKEND` задаём через
  env-переменную при запуске (по умолчанию `heuristic`).
- **faster-whisper** установлен в venv (ставится `pip install -e ".[stt]"`).
- **Flutter 3.44.2** в `C:\FlutterSDK\flutter\bin` (PATH прописан в user-env; в свежих
  shell-ах на всякий случай префиксь `$env:Path = "C:\FlutterSDK\flutter\bin;" + $env:Path`).
  Dart 3.12.2.
- **Android SDK 36.1.0** в `C:\Users\efimr\AppData\Local\Android\Sdk`; **лицензии приняты**,
  cmdline-tools установлены (`...\cmdline-tools\latest\bin\sdkmanager.bat`). **Системного
  образа и AVD нет.**

---

## 6. Команды (шпаргалка)

```powershell
# всегда для кириллицы в консоли:
$env:PYTHONIOENCODING="utf-8"
cd "D:\VS_Code\AI Guide\backend"

# тесты + линт
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q          # 37 pass (+live если LM Studio поднят)

# демо агента (офлайн, шаблон)            / на живой модели:
.\.venv\Scripts\python.exe -m sim.run_orchestrator
.\.venv\Scripts\python.exe -m sim.run_orchestrator --llm openai

# метрики качества на модели
.\.venv\Scripts\python.exe -m sim.eval_live --n 8

# сервер с живой моделью -> http://localhost:8000
$env:AGENT_BACKEND="openai"; .\.venv\Scripts\python.exe -m uvicorn app.main:app

# Flutter (web)
$env:Path = "C:\FlutterSDK\flutter\bin;" + $env:Path
cd "D:\VS_Code\AI Guide\mobile"; flutter run -d chrome
```

---

## 7. Ключевые решения

- **Один оркестратор + 3 stateless роли**, не мульти-агент. Роли общаются через
  `SessionState`. «Разделение моделей по сервисам» = деплой, не несколько агентов.
- **Провайдер-агностичный `LLMClient`**: `AnthropicLLM`, `OpenAICompatLLM` (LM Studio/
  OpenRouter/любой /chat/completions), `FakeLLM` (тесты). Решение: «интерфейс сейчас,
  реальные провайдеры позже».
- **Удешевлённый стек (предложение, НЕ зафиксирован, ids/цены не подтверждены — #13):**
  Scorer/Narrator/Enrichment → DeepSeek/GLM; Companion → Gemini 3.5 Flash; Narrator
  «дёшево везде» с обязательным A/B на RU. Сейчас всё крутится на локальной qwen.
- **Эвристический гейт** перед LLM-Scorer (×7–100 экономии вызовов).
- **`control_patch`** — закрытая pydantic-схема (skip_categories/focus_topics/verbosity/mute).

---

## 8. Известные проблемы / находки (ВАЖНО)

- **LM Studio требует `response_format` = `json_schema`** (а не `json_object`) — уже
  починено в `OpenAICompatLLM.complete_json`.
- **9B qwen изредка выдумывает факты сверх FACTS** (наблюдали «Софийский собор Красного
  Села» вместо Василия Блаженного). Контракт держит 100%, тонкое «только факты» — нет.
  → нужен A/B с облачной моделью (DeepSeek/Gemini обычно строже).
- **Мультиязычность плавает** (EN 0–75%) — `{language}` в русском CORE не переносится.
  → Этап 7: per-language CORE.
- **Single-run live-проверки нарратора флейки** (temperature>0) → качество меряем как
  rate в `sim/eval_live.py`, в pytest только надёжные контрактные проверки.
- **Реального TTS нет** (NullTTS) — гид не говорит. План: локальный Piper.
- Последний eval на qwen (n=8): JSON/markdown/клише/выдуманные-инструкции/лево-право/
  тишина/companion — ~100%; EN — переменно.

## 9. Гочи окружения

- Консоль Windows cp1251 → ставь `$env:PYTHONIOENCODING="utf-8"`; sim-скрипты сами
  reconfigure stdout. `Select-Object -First N` на пайпе sim → exit 255 (безвредно).
- **НЕ передавай кириллицу в `python -` через PowerShell heredoc** — будет мояибаке
  (так испортился вопрос в одном WS-демо). Реальные клиенты шлют чистый UTF-8 по WS.
- Flutter в свежих shell-ах префиксь PATH (см. выше).
- Android-лицензии принимались через redirect stdin из файла:
  `cmd /c "C:\FlutterSDK\flutter\bin\flutter.bat doctor --android-licenses < <файл с 'y'>"`
  (пайп «y» построчно НЕ срабатывает). Уже приняты.
- git ругается LF→CRLF — безвредно.

---

## 10. ГДЕ ОСТАНОВИЛИСЬ → следующий шаг

Остановились на **Этапе 6b**: только что приняли Android-лицензии (`[√] Android toolchain`),
эмулятора/системного образа нет. Собирались запустить `flutter build apk --debug` —
пользователь поставил паузу.

**Чтобы продолжить 6b:**
1. **Собрать APK** (доказательство компиляции под Android; первый Gradle-билд долгий):
   ```powershell
   $env:Path = "C:\FlutterSDK\flutter\bin;" + $env:Path
   cd "D:\VS_Code\AI Guide\mobile"; flutter build apk --debug
   ```
2. **Эмулятор** (нужен системный образ, ~1ГБ):
   ```powershell
   & "C:\Users\efimr\AppData\Local\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat" "system-images;android-35;google_apis;x86_64"
   flutter emulators --create --name guide_emu
   flutter emulators --launch guide_emu
   ```
   (проще — создать AVD через Android Studio → Device Manager GUI; или подключить телефон с USB-debug.)
3. **WS URL на устройстве:** эмулятор → `ws://10.0.2.2:8000/ws`; реальный телефон → LAN-IP
   ПК. В приложении поле URL редактируемое; дефолт `ws://localhost:8000/ws` (для web/десктопа).
4. **Реальные сенсоры (6b+):** раскомментировать в `mobile/pubspec.yaml` плагины
   (geolocator, flutter_compass, just_audio, record), заменить симуляцию прогулки на
   GPS+компас, добавить детекцию «телефон в кармане» → `gaze_confidence`, проигрывание
   аудио и захват микрофона.

**Рекомендуемый приоритет после паузы:** (а) **локальный TTS (Piper)** — чтобы гид
заговорил во всех клиентах; (б) **мультиязычность** (per-language CORE); (в) дотянуть 6b
на телефоне; (г) при доступе к облаку — verification моделей + A/B качества (#13).
