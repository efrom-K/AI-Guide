# AI Audio Guide — backend

Python (FastAPI + asyncio + WebSocket) backend for the real-time audio guide.
Design: see `../ARCHITECTURE.md`.

## Setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"      # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # POSIX
cp .env.example .env        # add ANTHROPIC_API_KEY (needed from Stage 2)
```

## Run
```bash
.venv\Scripts\python -m uvicorn app.main:app --reload
```
- `GET /health` — liveness
- `GET /` — WebSocket test client (`web/index.html`)
- `WS  /ws` — Stage 0: echo (real agent loop wired in later stages)

## Checks
```bash
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m pytest -q
```

## Deploy on a LAN server (Docker)

Run the backend on a box the phone can reach over Wi-Fi (`Dockerfile` +
`docker-compose.yml` included; STT model + fact cache live on a named volume):
```bash
# on the server, in the backend/ folder:
cp .env.example .env          # then fill OPENAI_API_KEY (sk-or-...)
docker compose up -d --build
curl http://localhost:8000/health        # {"status":"ok",...}
```
The phone then connects to `ws://<server-ip>:8000/ws` (Settings → WebSocket URL).
Key `.env` values for a **real walk**: `GEO_SOURCE=overpass` (not `fixture`),
`ENRICHMENT_SOURCE=websearch`, `AGENT_BACKEND=openai`. The first voice question
downloads the Whisper model into the volume (one-time).

## End-to-end regional testing

`sim/e2e_regions.py` walks real OSM routes through the full agent (discover → score →
narrate, adaptive radius + dedup) across diverse RF regions and abroad — tourist centres
**and** residential/industrial outskirts — each in a per-session language.
```bash
# public overpass-api.de is often blocked → use a mirror
OVERPASS_URL=https://maps.mail.ru/osm/tools/overpass/api/interpreter \
  .venv\Scripts\python -m sim.e2e_regions
# subset: E2E_ONLY=msk-red-square,paris-eiffel  ·  output: E2E_OUT=path.md
```
Latest run (2026-06-24): **12 маршрутов, 24 озвучки, ~$0.24** — facts in city centres,
modest/no-cliché on outskirts, silence where nothing notable, French/Italian abroad. Full
results, highlights and findings: [`../E2E_REGIONS.md`](../E2E_REGIONS.md).

Facts come from real **WebSearch enrichment** (`ENRICHMENT_SOURCE=websearch`) — the OpenRouter
web plugin via `WebSearchEnricher`, kept off the hot-path (top-K candidates, timeout, cached,
coordinate-disambiguated). Set `ENRICHMENT_SOURCE=mock` for offline/fixture runs.

## Layout
```
app/
  config.py            # settings (.env)
  shared/schemas.py    # domain + role I/O + WebSocket contract
  services/
    llm/router.py      # role -> Claude model mapping
prompts/               # CORE / scorer / narrator / companion templates
sim/                   # virtual walk (Stage 1)
tests/                 # pytest
web/index.html         # WS test client
```
