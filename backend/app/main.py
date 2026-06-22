"""FastAPI entrypoint.

Stage 0 surface:
  * GET  /health  — liveness
  * GET  /        — minimal WS test client (web/index.html)
  * WS   /ws      — echo (real agent loop is wired in later stages)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI(title="AI Audio Guide", version="0.0.1")

_WEB_INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-audio-guide", "version": app.version}


@app.get("/")
async def index() -> HTMLResponse:
    if _WEB_INDEX.exists():
        return HTMLResponse(_WEB_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AI Audio Guide backend</h1><p>See /health</p>")


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            msg = await websocket.receive_json()
            # Stage 0: echo the message back so the transport can be verified.
            await websocket.send_json({"type": "echo", "received": msg})
    except WebSocketDisconnect:
        return
