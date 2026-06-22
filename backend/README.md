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
