# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An autonomous, real-time **audio guide for everyday walks**. The app tracks the user's GPS
position and heading and narrates the surrounding places aloud, with no interaction
required — open the app and walk. You can also **interrupt by voice** (barge-in) to ask a
question; the guide answers in the same voice and memory, then resumes the tour.

A working MVP exists: a **Python/FastAPI backend** (the agent brain) and a **Flutter client**
(map UI + on-device speech), talking over a single WebSocket. It runs end-to-end on cloud
LLMs (OpenRouter) or a local model (LM Studio), and the Flutter app builds to an Android APK.

## Repository layout

- `backend/` — FastAPI + asyncio + WebSocket server; the orchestrator and all agent logic.
- `mobile/` — Flutter client (Android/web/Windows): full-screen OSM map, on-device TTS/STT, 8 languages.
- `deploy/` — Caddy + docker-compose for the prod host: Caddy terminates TLS, **serves the
  Flutter web build** (`deploy/web/`, identical to the mobile app) at `/`, and reverse-proxies
  `/ws /health /ready /stats` to the backend. Access logging is on (`docker logs ai-guide-caddy`).
- **Design docs** (read these before non-trivial changes): `ARCHITECTURE.md` (full design, in
  Russian), `CONTINUE.md` (handoff: current state, run commands, gotchas — the most up-to-date
  status), `MODEL_COMPARISON.md` (model choice/cost), `E2E_REGIONS.md` (regional eval results),
  `BUSINESS_LOGICS.pdf` (original Russian spec, source of `SYSTEM_PROMPT_RU`).

> The prose in `ARCHITECTURE.md` predates some decisions. Where it disagrees with the code,
> the code wins: the **default LLM backend is Claude/Anthropic** (see `backend/app/config.py`),
> state defaults to **in-memory** (Redis optional), and **TTS runs on the client** (server TTS
> is a no-op `NullTTS`). `CONTINUE.md` reflects the real deployed config (OpenRouter/Gemini in
> dev, DeepSeek in prod due to a regional block).

## Backend — commands

All from `backend/` (Windows paths shown; on POSIX use `.venv/bin/`):

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,stt]"   # stt extra = local faster-whisper
copy .env.example .env                                 # then set keys (see config below)

.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000   # run (0.0.0.0 for devices)
.venv\Scripts\python -m ruff check .                   # lint
.venv\Scripts\python -m pytest -q                      # tests
.venv\Scripts\python -m pytest tests/test_orchestrator.py -q             # single file
.venv\Scripts\python -m pytest tests/test_orchestrator.py::test_name     # single test
```

On Windows, set `$env:PYTHONIOENCODING="utf-8"` before running anything that prints narration
(Cyrillic in the console otherwise breaks).

**Test layout:** the offline suite (no network/keys) is the regression gate and must stay green.
Tests named `*_live.py` (`test_llm_live`, `test_stt_live`) need real network/keys and are not
part of the offline gate. `tests/fixtures/` holds canned places/facts so the agent runs deterministically.

**Simulations** (`backend/sim/`, run as modules — they are the main quality harness, exercising
the agent without sensors/TTS/Flutter):
- `python -m sim.run_orchestrator --llm openai` — full agent on fixtures.
- `python -m sim.eval_live --n 5` — quality metrics + token/cost log.
- `python -m sim.e2e_regions` — walks real OSM routes through the full agent across many regions.
  Needs `OVERPASS_URL=https://maps.mail.ru/osm/tools/overpass/api/interpreter` (public
  overpass-api.de is often blocked); subset via `E2E_ONLY=msk-red-square,paris-eiffel`.
- `sim.smoke_openrouter` / `sim.smoke_stt <wav>` / `sim.smoke_cache` — targeted smoke checks.

## Mobile — commands

From `mobile/` (Flutter 3.44+, needs the backend running on `:8000`):

```bash
flutter analyze
flutter test                  # widget smoke test
flutter run -d chrome         # quickest loop (web; simulated walk works without GPS)
flutter build apk --debug     # Android
```

For the Android emulator after installing the APK: `adb -s emulator-5554 reverse tcp:8000 tcp:8000`
(so `ws://localhost:8000/ws` reaches the host) and grant `RECORD_AUDIO`. See `mobile/README.md`
for the full emulator dance. `mobile/android/gradle.properties` sets `kotlin.incremental=false`
**on purpose** — required because the pub cache (`C:`) and project (`D:`) are on different drives;
don't remove it.

## Architecture — the big picture

One **stateful orchestrator** ("the brain") drives a continuous loop and owns all session state
(FSM, seen-list, history, conversational memory). Around it are **stateless LLM roles** and
**services**. Roles never talk to each other — only through the `SessionState` the orchestrator
hands them. ("Splitting models per service" in the docs is about deployment/routing, **not**
multiple independent agents.)

The four LLM roles (`backend/app/services/agent/`, prompts in `backend/prompts/*.txt`):
- **Scorer** (`scorer.py`) — ranks nearby candidates, picks the next place, decides
  `expand_radius`. JSON-only, cheap model. Gated by a deterministic heuristic so the LLM is
  only called when the candidate set changes materially.
- **Narrator** (`narrator.py`) — writes the short spoken SUMMARY for the chosen place.
- **Landmark** — same role as Narrator but a premium model, used only for `LANDMARK` significance.
- **Companion** (`companion.py`) — handles voice/text barge-in; can use tools; returns a reply
  plus an optional `control_patch` (e.g. "skip shops", "be brief") that steers the tour.

Prompts are assembled in layers: `SYSTEM_PROMPT(role, lang) = CORE(lang) + ROLE_BLOCK(role) +
RUNTIME_CONTEXT`. `core.txt` holds the invariants shared by every role; `RUNTIME_CONTEXT` is the
volatile per-tick context (built last, for prompt caching).

Services (`backend/app/services/`):
- `geo/` — OSM **Overpass** discovery: radius search, type/distance/gaze-cone ranking, adaptive
  radius, dedup. Linear features (rivers/canals) snap to the nearest geometry point.
- `enrichment/enricher.py` — `CompositeEnricher`: **Wikipedia/Wikidata first (free)** for places
  tagged `wikipedia=`/`wikidata=`, paid OpenRouter web-search fallback only for the rest. Kept
  **off the hot-path**: top-K candidates, prefetch-ahead, ~9 s timeout, memory+disk cache.
- `llm/` — provider-agnostic `LLMClient` + a per-role router. Default Anthropic; OpenAI-compatible
  base URL for OpenRouter or local LM Studio. A `METER` tracks tokens/cost per session.
- `stt/` — `faster-whisper` (real) or `MockSTT`. `tts/` — interface only; `NullTTS` server-side
  (the **client** speaks via `flutter_tts`).
- `state/store.py` — session store, in-memory by default (LRU + TTL caps), Redis optional.

`shared/schemas.py` is the single source of truth for domain models **and** the WebSocket contract.
`config.py` is the env/`.env`-driven `Settings` — the dial-board for the whole backend.

### The agent loop (core domain logic)

1. **Find objects** — Overpass places within radius N, weighted by type and boosted for proximity
   and gaze-cone alignment.
2. **Persist + resolve address** — store found objects (also the seen-tracking) and resolve
   country/city/district/street.
3. **Enrich + score significance** — web/wiki facts per place; assign `SKIP → LOW → MEDIUM → HIGH
   → LANDMARK` from proximity, gaze, and historical/cultural value.
4. **Generate SUMMARY + stream** — Narrator writes a short SUMMARY, streamed to the client TTS.
   Discovery never stops: if a more relevant object appears mid-narration, generate a new SUMMARY
   and switch **seamlessly**.
5. **Adaptive radius** — if nothing new appears and heading is unchanged, expand the search radius
   so the user is never left in silence (the orchestrator also "elaborates" on the current place,
   up to `_MAX_ELABORATE` follow-ups, before going quiet).
6. **Context dedup** — only unseen places enter the LLM context.

### WebSocket contract (`/ws`)

The single transport. The backend runs a **background producer** per connection that emits one
narration paragraph at a time, paced by the client's `played` signal; `position` messages just
refresh live context. A question (`utterance`/`audio`) is top-priority: it cancels the in-flight
step, answers, then the producer resumes.

- **In:** `position` (lat/lon/heading/pace), `utterance` (typed question), `audio` (base64 WAV →
  STT), `played` (paced-playback ack), `language`, `theme`, `control` (manual `control_patch`),
  `ping` (keepalive, ignored).
- **Out:** `state`, `narration` (text + place + coords), `reply`, `transcript`, `language`,
  `error`, `ping` (server keepalive every 20 s).

**Connectivity resilience (the real-walk fix — see `CONTINUE.md` §0).** A real mobile walk drops
the socket constantly (NAT idle-reaping during narration lulls, cell handovers, coverage gaps),
which a localhost/emulator or stationary-WiFi test never reproduces. Two mechanisms keep the tour
coherent: (1) an **app-level heartbeat** both directions (`run_heartbeat` server-side, a 15 s timer
client-side) keeps the socket alive through lulls; (2) **session resume** — the client sends a
stable `?sid=` and the backend keys `SessionState` by it and **does not delete the session on
disconnect** (TTL/LRU evict instead), so a reconnect continues the same tour (seen-list, history,
area intro) instead of repeating from scratch. Don't reintroduce per-socket session ids or
delete-on-disconnect.

Other endpoints: `GET /health` (liveness), `GET /ready` (503 if recent LLM calls all failed),
`GET /stats` (admin, gated by `STATS_TOKEN`), `GET /` (browser test client, `backend/web/index.html`).

## Invariants to preserve

Product requirements, not suggestions — keep them in any change:
- **Real-time**: minimize latency from position update to start of narration.
- **No repeats**: only unseen places enter LLM context.
- **Facts only**: never fabricate; facts come from enrichment (wiki/web). If unsure, stay silent
  (Narrator returns exactly `[SILENCE]`).
- **Gaze priority, with confidence**: objects in the gaze direction score higher — but heading
  comes from the GPS course, so `gaze_confidence=low` is the norm. At `low`, never say
  "left/right" (only forward/backward is knowable); the flag is threaded into Scorer and Narrator.
- **Seamless switching** and **adaptive radius** as above.
- **Narration style**: friendly and conversational; no clichés ("unique place", "important
  landmark"); don't inflate ordinary places. Respectful tone for memorials/temples; no ad-speak
  for shops. This is audio — plain speech, no markup/lists, numbers and dates spoken naturally.

## Configuration (key `.env` knobs)

Set in `backend/.env` (gitignored). Defaults wire an **offline/heuristic** stack so sim and tests
run without keys. For a real walk, flip the wiring:
- `AGENT_BACKEND` — `heuristic` (offline) | `openai` (OpenAI-compatible / OpenRouter / LM Studio) | `anthropic`.
- `GEO_SOURCE` — `fixture` (Red Square only) | `overpass` (**required** for a real walk).
- `ENRICHMENT_SOURCE` — `mock` (tests) | `websearch` (wiki + paid fallback).
- `STT_BACKEND` — `mock` | `faster_whisper`.
- For OpenRouter set `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL`; for LM Studio point the
  base URL at `http://localhost:1234/v1`. Per-role overrides exist (`OPENAI_MODEL_SCORER`, etc.).
- **Security/spend** (the `/ws` is public): `WS_TOKEN`, `MAX_CONNECTIONS_PER_IP`, `USD_HARD_CAP`
  (blocks LLM calls past a ceiling), `MAX_UTTERANCE_CHARS`, `MAX_AUDIO_B64_CHARS`. A real monthly
  cap must also be set on the provider dashboard — the code cap is a backstop.

See `CONTINUE.md` §6 for a full annotated dev `.env`, and §5 for the **regional block** caveat
(OpenRouter geoblocks OpenAI/Anthropic/Google from some regions → prod uses `deepseek/deepseek-chat`).

## Gotchas (already paid for — see `CONTINUE.md` §7 for the full list)

- Enrichment timeout must be **≥9 s** — web search takes ~5–7 s; shorter and the Narrator gets no facts.
- Wikimedia rejects a bare User-Agent (403) — the `WikiEnricher` UA must stay meaningful.
- Gemini 3.x reasoning can't be disabled; cap `OPENAI_REASONING_MAX_TOKENS` for Narrator/Landmark/Enricher.
- `flutter_compass` was removed (broke AGP 8); heading comes from `position.heading`, hence `gaze_confidence=low`.
- Public CARTO/OSM tiles are fine for the prototype, not for production load.
