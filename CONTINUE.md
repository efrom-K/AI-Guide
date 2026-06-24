# CONTINUE.md — состояние проекта «AI Audio Guide» (для продолжения работы)

> Хэндофф-документ для следующей сессии: что есть, как запускать, что осталось, где
> остановились. Дизайн-спека — `ARCHITECTURE.md`; выбор и удешевление модели —
> `MODEL_COMPARISON.md`; канонические промпты — `backend/prompts/*.txt`.

Обновлено: 2026-06-24. Папка: `D:\VS_Code\AI Guide`. Windows 11, PowerShell + Git Bash.
Git: по коммиту на фичу (см. `git log`).

---

## 1. Что это и как устроено

Автономный аудиогид реального времени: GPS+направление → находим места (OSM) → оцениваем
значимость → обогащаем фактами → **озвучиваем живой рассказ**; можно **прервать голосом** и
порулить экскурсией. Один оркестратор-«мозг» + 3 stateless LLM-роли (**Scorer**→JSON,
**Narrator**→текст, **Companion**→чат) через общее состояние сессии. Службы: Geo
(OSM/фикстуры), Enrichment (факты+кэш), STT, TTS-интерфейс, State (in-memory/Redis).
Клиент-сервер по WebSocket; клиент — Flutter (Android + web/десктоп).

---

## 2. Что РАБОТАЕТ (проверено end-to-end)

Бэкенд на **облачном Gemini 3.5 Flash** (OpenRouter) ИЛИ локальном **qwen** (LM Studio) —
переключается одним блоком в `.env`. Flutter-приложение **собирается в APK и работает на
Android-эмуляторе** `guide_emu`.

| Область | Статус | Суть |
|---|---|---|
| Бэкенд-ядро | ✅ | FastAPI + asyncio + WS; FSM, память сессии, эвристический гейт, control_patch, OFFLINE/ERROR/RECOVERY |
| Geo + sim | ✅ | Overpass+фикстуры, ранжирование (дистанция/тип/конус взгляда), адаптивный радиус, дедуп; виртуальная прогулка |
| Промпты + пайплайн | ✅ | CORE+роли; Scorer(строгий JSON)/Narrator/Companion; провайдер-агностичный `LLMClient` |
| **LLM: Gemini 3.5 Flash** | ✅ | OpenRouter на все роли; локальный qwen — фолбэк. Метр токенов/стоимости |
| **WebSearch-обогащение** | ✅ | Реальные факты через OpenRouter web-плагин (`WebSearchEnricher`); off the hot-path: топ-K кандидатов с таймаутом, кэш (память + JSON), дизамбигуация по координатам. `mock` для тестов |
| **Удешевление** | ✅ | Кап reasoning у Narrator + детерминированное молчание/анти-повтор; −58% стоимости, качество 100% (см. `MODEL_COMPARISON.md`) |
| **STT (голосовой barge-in)** | ✅ | Реальный `faster-whisper` (CPU/int8); распознаёт RU. `MockSTT` для тестов |
| TTS | ✅ (на клиенте) | Гид **говорит** через on-device `flutter_tts` (RU). Серверный TTS = NullTTS (Piper не делали) |
| **Flutter-приложение** | ✅ | Android APK на эмуляторе; web/десктоп тоже собираются |
| — озвучка | ✅ | `flutter_tts`, тумблер 🔊, barge-in глушит речь |
| — голосовой вопрос | ✅ | `record` → WAV → STT → ответ Companion (озвучивается) |
| — карта | ✅ | OpenStreetMap (`flutter_map`): позиция+направление, **пины мест**, тумблер **follow/свободный просмотр** |
| — UX | ✅ | Статус-чип состояния, авто-reconnect, футер позиция/место, пустое состояние, очистка, авто-скролл, симуляция/реальный GPS |
| **Мультиязычность (этап 7)** | ✅ | 8 языков (en/ru/es/fr/de/it/pt/zh): narration+TTS+STT по сессии; переключатель языка + автодетект системного (фолбэк EN); **полная локализация UI** (gen-l10n из `lib/l10n/*.arb`). Язык шлётся на бэкенд по WS (`{type:"language"}`) на каждом коннекте/смене |

**Демо сейчас:**
- `python -m sim.run_orchestrator --llm openai` — полный агент на Gemini (или qwen).
- `python -m sim.eval_live --n 5` — метрики качества (% hold-rate) + лог токенов/стоимости.
- Браузер `http://localhost:8000` — веб-демо прогулки.
- Эмулятор `guide_emu` + APK — мобильный клиент (карта, озвучка, микрофон).
- Smoke: `sim.smoke_openrouter` (LLM), `sim.smoke_stt <wav>` (STT), `sim.smoke_cache` (кэш).

---

## 3. Что ОСТАЛОСЬ

- **Тест на реальном телефоне** — реальный GPS, голоса TTS и микрофон полноценно
  проверяются на устройстве (у эмулятора GPS фейковый, голоса не всех языков есть).
- **Локализация системных промптов** — `{language}` сейчас управляет только языком вывода;
  текст правил в `core.txt`/ролях остаётся русским. Опционально: per-language файлы промптов.
- **Серверный TTS (Piper)** — опционально; сейчас озвучивает клиент (этого достаточно).
- **Продакшн-карта** — публичные OSM-тайлы не для нагрузки; свой тайл-сервер/провайдер.
- **Резолв адреса (город) для обогащения** — `WebSearchEnricher` подключён, но город в
  запрос сейчас даёт только координаты (адрес-резолв 1.2 не подключён в sim). С реальным
  городом дизамбигуация ещё надёжнее.
- **Калибровка значимости при обогащении** — когда факты есть почти у всех мест, Scorer
  склонен завышать значимость рядовых объектов (напр. сквер → HIGH). Подкрутить промпт Scorer.
- **Безопасность/бюджет:** перевыпустить ключ OpenRouter (светился в чате) и поставить
  жёсткий лимит $25/мес в дашборде OpenRouter (в коде только мягкое предупреждение).
- **GPU STT** — доустановить `nvidia-cublas-cu12`/`nvidia-cudnn-cu12`, тогда `WHISPER_DEVICE=cuda`.

---

## 4. Как запускать

**Бэкенд** (из `D:\VS_Code\AI Guide\backend`):
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
`--host 0.0.0.0` нужен, чтобы достучаться с эмулятора/телефона. Health: `http://localhost:8000/health`.

**Flutter (эмулятор):**
```powershell
$env:Path = "C:\FlutterSDK\flutter\bin;" + $env:Path
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"   # для sdkmanager/avdmanager/emulator
flutter emulators --launch guide_emu
cd "D:\VS_Code\AI Guide\mobile"; flutter build apk --debug
# установка/запуск:
$env:Path = "C:\Users\efimr\AppData\Local\Android\Sdk\platform-tools;" + $env:Path
adb -s emulator-5554 install -r build\app\outputs\flutter-apk\app-debug.apk
adb -s emulator-5554 reverse tcp:8000 tcp:8000          # эмулятор: localhost:8000 -> хост
adb -s emulator-5554 shell pm grant com.example.ai_audio_guide android.permission.RECORD_AUDIO
adb -s emulator-5554 shell monkey -p com.example.ai_audio_guide -c android.intent.category.LAUNCHER 1
```
В приложении: дефолтный URL `ws://localhost:8000/ws` работает как есть (через `adb reverse`).
На реальном телефоне — вписать `ws://<LAN-IP-ПК>:8000/ws`.

---

## 5. Окружение (факты)

- **Python 3.14**, venv в `backend\.venv`. Зависимости поставлены (FastAPI, httpx, pydantic,
  faster-whisper, ctranslate2, websockets).
- **Flutter 3.44.2** в `C:\FlutterSDK\flutter\bin` (Dart 3.12.2). PATH прописан, но в свежих
  shell-ах префиксь на всякий случай.
- **Android SDK** в `C:\Users\efimr\AppData\Local\Android\Sdk`; лицензии приняты; системный
  образ `system-images;android-35;google_apis;x86_64`; AVD **`guide_emu`** (Pixel 6).
- **JBR JDK 21** в `C:\Program Files\Android\Android Studio\jbr` — задавать как `JAVA_HOME`
  для `sdkmanager`/`avdmanager`/эмулятора (иначе «Java 17+ required»).
- **LM Studio** (если используем qwen): `http://localhost:1234/v1`, модель `qwen/qwen3.5-9b`,
  RTX 3060 12GB.
- **OpenRouter**: ключ в `backend/.env` (gitignored). Модель `google/gemini-3.5-flash`.

---

## 6. Конфиг `.env` (gitignored, `backend/.env`)

Облачный Gemini (текущий) — ключевые строки:
```
AGENT_BACKEND=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-...                 # вне git; перевыпустить
OPENAI_MODEL=google/gemini-3.5-flash
OPENAI_REASONING_EFFORT=low
OPENAI_REASONING_MAX_TOKENS=64           # кап reasoning для Narrator/Landmark/Enricher
OPENAI_PROMPT_CACHE=true                 # + точный учёт стоимости (usage.include)
OPENAI_PRICE_IN_PER_MTOK=1.5
OPENAI_PRICE_OUT_PER_MTOK=9.0
USD_SESSION_BUDGET=25                    # мягкое предупреждение, не жёсткий кап
STT_BACKEND=faster_whisper
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu                       # cuda нужен cublas/cudnn на PATH
WHISPER_COMPUTE_TYPE=int8
DEFAULT_LANGUAGE=ru
ENRICHMENT_SOURCE=websearch              # mock => фикстуры (тесты); websearch => реальные факты
WEB_SEARCH_MAX_RESULTS=3                 # web-результатов на место (OpenRouter биллит за результат)
ENRICH_TOP_K=3                           # сколько топ-кандидатов обогащать за тик
ENRICH_TIMEOUT_S=6.0                     # бюджет обогащения на тик (частично при таймауте)
ENRICH_CACHE_PATH=.enrich_cache.json     # кэш фактов на диск (gitignored); "" => только память
```
Откат на локальный qwen: заменить `OPENAI_BASE_URL/KEY/MODEL` на LM Studio (закомментированы
в `.env`), `OPENAI_REASONING_*`/`OPENAI_PROMPT_CACHE` можно убрать (LM Studio их не понимает).

---

## 7. Гочи (на чём уже спотыкались)

- **Сборка Kotlin падает «different roots»** — pub-кэш на `C:`, проект на `D:`. Лечение уже
  в `mobile/android/gradle.properties`: `kotlin.incremental=false`.
- **`flutter_compass` выкинули** — не обновлялся, ломал AGP 8 (нет `namespace`). Heading
  берём из курса GPS (`position.heading`), `gaze_confidence=low` — это и есть фолбэк
  «компас в кармане» из дизайна.
- **`record` запинён на `^7.0.0`** — 5.x разрешался в несовместимый федеративный набор
  (record_linux без `startStream`).
- **Gemini 3.x: ризонинг отключить нельзя** («Reasoning is mandatory»). `effort=low` всё
  равно тратит ~380 дорогих выходных токенов → капаем `reasoning.max_tokens` (только Narrator).
- **Prompt-caching у Gemini/OpenRouter слабый** — `cache_control` игнорируется, неявный кэш
  нестабилен. Оставлен ради учёта стоимости, не как основа экономии.
- **STT на GPU** требует `cublas64_12.dll` (CUDA runtime) — пока CPU/int8 (~2с на реплику).
- **adb reverse туннель иногда рвёт WS** на эмуляторе — это не баг приложения; авто-reconnect
  переподключается. На реальном LAN/wss такого нет.
- **OSM-тайлы**: `flutter_map` предупреждает, что публичные тайлы не для прод-нагрузки.
- **Кириллица в консоли**: `$env:PYTHONIOENCODING="utf-8"` + `sys.stdout.reconfigure(...)`.
- **Драйв эмулятора через adb**: после `monkey`-запуска приложению нужно ~6–13с на холодный
  старт (splash) — иначе тапы по координатам уходят в пустоту.

---

## 8. Где остановились → следующий шаг

Только что закрыли **этап 7 — мультиязычность** (коммиты `Stage 7a/7b`): 8 языков на
narration/TTS/STT по сессии, переключатель языка + автодетект системного (фолбэк EN),
полная локализация UI (gen-l10n), язык уходит на бэкенд по WS на каждом коннекте/смене.
Проверено: бэкенд — живой испанский рассказ от Gemini; эмулятор — автодетект EN, мгновенная
смена UI EN↔RU, и **рассказ гида на выбранном языке** (один и тот же собор — по-русски, затем
по-английски). `flutter analyze` чистый, `flutter test` зелёный, APK собран.

Где сделать переключение языка/STT в коде: бэкенд — `services/agent/languages.py` (8 кодов,
маппинг в имя для промпта), `pipeline.step(..., language=)`, ветка `language` в `main.py`;
клиент — `mobile/lib/main.dart` (`kLangs`, `_changeLanguage`, `GuideApp` автодетект) +
`mobile/lib/l10n/app_*.arb`.

Затем подключили **WebSearch-обогащение** (`Stage 7e`): реальные факты через OpenRouter
web-плагин (`WebSearchEnricher` + `OpenAICompatLLM.web_facts`), off the hot-path (топ-K с
таймаутом, кэш память+JSON, дизамбигуация по координатам — после того как одноимённый
«Eurocity» подтянул факты про Гибралтар). Проверено на e2e: Грозный — мечеть «Сердце Чечни»
теперь **LANDMARK** с верными фактами (а «Грозный-Сити» ушёл в LOW). 6 юнит-тестов на enricher.

**Рекомендуемый следующий шаг:** тест на реальном телефоне (живой GPS + голос TTS + микрофон);
подкрутить калибровку значимости Scorer при обогащении. Перед демо — перевыпустить ключ
OpenRouter и поставить лимит в дашборде.
