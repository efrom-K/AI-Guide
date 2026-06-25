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
**Narrator**→текст, **Companion**→чат, плюс **Landmark** — премиум-нарратор для значимости
LANDMARK) через общее состояние сессии. Службы: Geo (OSM/Overpass), Enrichment
(Wikipedia/Wikidata + платный веб-поиск, кэш), STT, TTS-интерфейс, State (in-memory/Redis).
Клиент-сервер по WebSocket; клиент — Flutter (карта на весь экран, тёмная тема).

---

## 2. Что РАБОТАЕТ (проверено end-to-end)

Бэкенд на **облачном Gemini 3.5 Flash** (OpenRouter) ИЛИ локальном **qwen** (LM Studio) —
переключается одним блоком в `.env`. Flutter-приложение **собирается в APK и работает на
Android-эмуляторе** `guide_emu`.

| Область | Статус | Суть |
|---|---|---|
| Бэкенд-ядро | ✅ | FastAPI + asyncio + WS; FSM, память сессии, эвристический гейт, control_patch, OFFLINE/ERROR/RECOVERY |
| Geo | ✅ | **Реальный Overpass** (зеркало mail.ru), ранжирование (дистанция/тип/конус), адаптивный радиус, дедуп. Селекторы: культура+**природа/вода** (реки, озёра, водохранилища, леса, сады) + структуры (мосты, башни). Линейные объекты привязываются к **ближайшей** к юзеру точке (`out geom`) |
| Промпты + пайплайн | ✅ | CORE+роли; Scorer/Narrator/Companion/Landmark; провайдер-агностичный `LLMClient` |
| **LLM: Gemini 3.5 Flash** | ✅ | OpenRouter на все роли; локальный qwen — фолбэк. Метр токенов/стоимости |
| **Обогащение фактами** | ✅ | **Wikipedia/Wikidata (бесплатно)** → платный веб-поиск (OpenRouter) только для мест **без** вики-тега (`CompositeEnricher`). Off the hot-path: топ-K с таймаутом 9с, кэш память+диск, дизамбигуация по координатам. ~$0.008/место с вики vs ~$0.038 поиском. `mock` для тестов |
| **Поведение рассказа** | ✅ | Бесшовный монолог **без вопросов** к слушателю; факты — приоритет (история/детали), у рядовых мест короткое упоминание без выдумок; **«зацепка»** — когда рядом пусто, гид продолжает про текущее место (до 6 догонов) |
| **STT (голосовой barge-in)** | ✅ | Реальный `faster-whisper` (CPU/int8). `MockSTT` для тестов |
| TTS | ✅ (на клиенте) | On-device `flutter_tts`, голос по выбранному языку. Серверный TTS = NullTTS (Piper не делали) |
| **Flutter — карта на весь экран, тёмная** | ✅ | CARTO dark тайлы; плавающие пилюли (бренд/язык/звук/настройки); стеклянная нижняя карточка (статус-пульс, место+рассказ, одна главная кнопка connect+walk/stop) |
| — пины мест | ✅ | Текущий жёлтый / пройденные серые, **кликабельные** → шторка с названием и историей места |
| — камера | ✅ | **Плавная** центровка (easeInOut); кнопка-компас (ориентация на север); курсор держится **над карточкой** (видим) |
| — озвучка | ✅ | Барджин глушит; **не режет фразу на полуслове** (новый рассказ ждёт окончания, играет самый свежий) |
| — голосовой/текстовый вопрос | ✅ | Микрофон (`record`→WAV→STT) или клавиатура → ответ Companion (озвучивается) |
| — настройки/история | ✅ | Dev-обвязка (WS URL, тумблер симуляции) в шторке; лента сообщений — swipe-up «История»; авто-reconnect |
| **Мультиязычность** | ✅ | 8 языков (en/ru/es/fr/de/it/pt/zh): narration+TTS+STT по сессии; переключатель + автодетект системного (фолбэк EN); полная локализация UI (gen-l10n). Язык по WS (`{type:"language"}`) на коннекте/смене |
| **Демо-маршрут** | ✅ | Симуляция идёт по реальному маршруту (Волгоградский пр-т → Павелецкая) на скорости пешехода (~7 км/ч), как реальный GPS |

**Демо сейчас:**
- Эмулятор `guide_emu` + APK — мобильный клиент идёт по реальному маршруту (Волгоградский →
  Павелецкая) на скорости пешехода и **рассказывает с фактами** (карта, пины, озвучка, микрофон).
- `python -m sim.e2e_regions` — прогон по 12 регионам РФ/заграницы (реальный Overpass + агент);
  `OVERPASS_URL=...mail.ru...`, `E2E_ONLY=msk-red-square,...` — подмножество. См. `E2E_REGIONS.md`.
- `python -m sim.run_orchestrator --llm openai` — полный агент на фикстурах.
- `python -m sim.eval_live --n 5` — метрики качества + лог токенов/стоимости.
- Docker: `cd backend && docker compose up -d --build` — деплой на LAN-сервер.
- Smoke: `sim.smoke_openrouter` (LLM), `sim.smoke_stt <wav>` (STT), `sim.smoke_cache` (кэш).

---

## 3. Что ОСТАЛОСЬ

- **Связь на прогулке (главное для прода).** Гуляющему телефону нужен бэкенд, доступный
  **по дороге**, а не только в домашнем WiFi — иначе на улице связь рвётся (проверено: на
  реальной прогулке телефон выходил из зоны WiFi → гид замолкал). Варианты: туннель
  (cloudflared/ngrok) с ПК, приватный VPN (Tailscale) или облачный сервер с публичным IP.
  Air-gapped homelab не подходит — бэкенду нужен интернет (LLM + Overpass + факты).
- **Тест на реальном телефоне** — реальный GPS, голоса TTS и микрофон (у эмулятора GPS
  фейковый, голоса не всех языков; эмулятор в этой машине ещё и нестабилен по графике).
- **Резолв адреса (город) для обогащения** — в запрос факта сейчас идут координаты; с
  реальным городом (адрес-резолв 1.2) дизамбигуация ещё надёжнее.
- **Локализация системных промптов** — `{language}` управляет языком вывода; текст правил в
  `core.txt`/ролях остаётся русским. Опционально: per-language файлы промптов.
- **Серверный TTS (Piper)** — опционально; сейчас озвучивает клиент.
- **Продакшн-карта** — публичные CARTO/OSM-тайлы не для нагрузки; свой тайл-сервер/провайдер.
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
- **OpenRouter**: ключ в `backend/.env` (gitignored). Модель в деве — `google/gemini-3.5-flash`,
  **в проде — `deepseek/deepseek-chat`** (см. ниже про региональный блок).

> ⚠️ **Региональный блок (прод-хост, 2026-06-25).** OpenRouter геоблокирует OpenAI / Anthropic /
> Google (Gemini) из региона нашего сервера (РФ): любой вызов → HTTP 403 *"This model is not
> available in your region."* — гид подключался, но молчал. Фикс: на проде `OPENAI_MODEL=deepseek/deepseek-chat`
> (доступен из региона, тянет строгий `json_schema` Scorer'а и мультиязычный рассказ; reasoning-кап
> не нужен — V3 не reasoning-модель). Проверено сквозным WS-смоуком: рассказ по Красной площади
> приходит. В деве Gemini остаётся.

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
GEO_SOURCE=overpass                      # ОБЯЗАТЕЛЬНО для реальной прогулки (fixture = только Красная пл.)
OVERPASS_URL=https://maps.mail.ru/osm/tools/overpass/api/interpreter   # публичный overpass-api.de часто блокируется
ENRICHMENT_SOURCE=websearch              # mock => фикстуры (тесты); websearch => Wikipedia + платный поиск
WEB_SEARCH_MAX_RESULTS=2                 # web-результатов на платный поиск (3 дороже ~$0.13, 2 ~ $0.032)
WEB_SEARCH_MAX_TOKENS=400
ENRICH_TOP_K=2                           # сколько топ-кандидатов обогащать за тик (префетч наперёд)
ENRICH_TIMEOUT_S=9.0                     # веб-поиск занимает ~5-7с; меньше — фактов не будет, только названия
ENRICH_MIN_WEIGHT=0.0                    # вики бесплатна всегда; гейтит только ПЛАТНЫЙ fallback (0 = искать всё)
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
  равно тратит ~380 дорогих выходных токенов → капаем `reasoning.max_tokens` для
  **Narrator/Landmark/Enricher** (у Landmark без капа Gemini сливал «план рассуждений» в текст).
- **Веб-поиск фактов занимает ~5-7с** — таймаут обогащения должен быть **≥9с**, иначе запрос
  отменяется до ответа и нарратор остаётся без фактов («тут находится X»). Один поиск ~$0.032
  (≈85% цены места) → берём факты из **Википедии бесплатно**, платим только за не-вики хвост.
- **Wikimedia требует осмысленный User-Agent** — «голый» UA даёт 403. У `WikiEnricher` стоит
  корректный с контактом + `follow_redirects=True`.
- **Линейные OSM-объекты** (канал/река): `out center` отдаёт середину линии (за километры) →
  тянем `out geom` и привязываем к ближайшей точке. Объекты, названные только на route-релации
  (напр. «Канал имени Москвы» — 128 км), намеренно пропускаем (огромный payload).
- **Prompt-caching у Gemini/OpenRouter слабый** (`cached=0` в логах) — и даже работая, кэшировал
  бы только дешёвые Scorer/Narrator, а не платный поиск. Реальную цену не снижает.
- **Эвристический гейт** уже снижает вызовы Scorer, но веб-поиск не трогает (кэш и так ищет
  место один раз). Главный рычаг цены — бесплатные вики-факты, а не гейт/prompt-caching.
- **STT на GPU** требует `cublas64_12.dll` (CUDA runtime) — пока CPU/int8 (~2с на реплику).
- **Эмулятор `guide_emu` нестабилен под нагрузкой** — за сессию уходил в `offline`, ANR и
  GPU-глитч (битый синий кадр в `screencap`). Не баг приложения (в logcat нет исключений Flutter).
  Лечится перезапуском эмулятора; на реальном телефоне рендер нормальный.
- **OSM-тайлы**: публичные CARTO/OSM не для прод-нагрузки.
- **Кириллица в консоли**: `$env:PYTHONIOENCODING="utf-8"` + `sys.stdout.reconfigure(...)`.
- **Драйв эмулятора через adb**: после `monkey`-запуска нужно ~13с на холодный старт — иначе
  тапы уходят в splash.

---

## 8. Где остановились → следующий шаг

**Этап 7 практически закрыт — по сути MVP готов.** За сессию сделали (по коммиту на фичу):
- **Мультиязычность** — 8 языков, переключатель + автодетект, полная локализация UI (gen-l10n),
  язык по WS. Код: `services/agent/languages.py`, `main.dart` (`kLangs`, `_changeLanguage`), `l10n/*.arb`.
- **Обогащение фактами** — прошли путь WebSearch → выборочное (откатили) → **Wikipedia-first
  composite**: вики-факты бесплатно, платный поиск только для не-вики (`CompositeEnricher`,
  `WikiEnricher`). Таймаут поднят до 9с (иначе фактов нет). Проверено: «Улица Талалихина» с
  полной историей при **0 платных поисков** (вики/кэш). Цена ~$0.008/место с вики vs ~$0.038.
- **Geo** — реальный Overpass + природа/вода в селекторах + ближайшая точка для линейных объектов.
- **Поведение** — бесшовный монолог без вопросов, факты-приоритет, «зацепка» (до 6 догонов),
  клиент не режет фразу на полуслове.
- **UI** — карта на весь экран (тёмная CARTO), стеклянная карточка, кликабельные пины,
  компас, плавная центровка, курсор над карточкой. Демо-маршрут на скорости пешехода.
- **Docker-деплой** на LAN-сервер (`Dockerfile`/`compose`/`.env.example`-прод-шаблон).

Тесты: бэкенд офлайн-набор зелёный (47 passed; live-тесты требуют сети), `flutter analyze`
чисто, `flutter test` зелёный, APK собран.

**Рекомендуемый следующий шаг:** решить **связь на прогулке** (туннель/VPN/облако — без этого
телефон теряет бэкенд за пределами WiFi) и протестировать на реальном телефоне. Перед демо
наружу — перевыпустить ключ OpenRouter и поставить лимит в дашборде.
