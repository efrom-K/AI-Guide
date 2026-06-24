"""FastAPI entrypoint.

  * GET  /health  — liveness
  * GET  /        — browser demo client (web/index.html)
  * WS   /ws      — drives the orchestrator: position/utterance in, narration/
                    reply/state out (audio is added with a TTS provider)
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.services.agent.factory import build_orchestrator
from app.services.agent.languages import normalize
from app.services.agent.orchestrator import Orchestrator, OrchestratorOutput, merge_patch
from app.services.stt.stt import STTClient, build_stt
from app.shared.schemas import (
    GeoPoint,
    Heading,
    WSAudioInput,
    WSControl,
    WSPositionUpdate,
    WSSetLanguage,
    WSUserUtterance,
)

app = FastAPI(title="AI Audio Guide", version="0.1.0")

_WEB_INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"
_orchestrator: Orchestrator | None = None
_stt: STTClient | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator


def get_stt() -> STTClient:
    global _stt
    if _stt is None:
        _stt = build_stt()
    return _stt


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-audio-guide", "version": app.version}


@app.get("/")
async def index() -> HTMLResponse:
    if _WEB_INDEX.exists():
        return HTMLResponse(_WEB_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AI Audio Guide backend</h1><p>See /health</p>")


async def _send(ws: WebSocket, out: OrchestratorOutput) -> None:
    await ws.send_json({"type": "state", "state": out.state})
    if out.kind == "narration" and out.text:
        await ws.send_json(
            {
                "type": "narration",
                "text": out.text,
                "place_id": out.place_id,
                "place_name": out.place_name,
                "lat": out.lat,
                "lon": out.lon,
                "final": True,
            }
        )
    elif out.kind == "reply" and out.text:
        await ws.send_json({"type": "reply", "text": out.text})


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    orch = get_orchestrator()
    session_id = uuid.uuid4().hex
    try:
        while True:
            msg = await websocket.receive_json()
            kind = msg.get("type")
            if kind == "position":
                p = WSPositionUpdate.model_validate(msg)
                out = await orch.on_position(
                    session_id,
                    GeoPoint(lat=p.lat, lon=p.lon),
                    Heading(direction_deg=p.direction_deg, gaze_confidence=p.gaze_confidence),
                    p.pace,
                )
                await _send(websocket, out)
            elif kind == "utterance":
                u = WSUserUtterance.model_validate(msg)
                await _send(websocket, await orch.on_utterance(session_id, u.text))
            elif kind == "audio":
                a = WSAudioInput.model_validate(msg)
                state = await orch.store.load(session_id)
                text = await get_stt().transcribe(
                    base64.b64decode(a.data_b64), language=state.language
                )
                await websocket.send_json({"type": "transcript", "text": text})
                await _send(websocket, await orch.on_utterance(session_id, text))
            elif kind == "language":
                lang = WSSetLanguage.model_validate(msg)
                state = await orch.store.load(session_id)
                state.language = normalize(lang.language)
                await orch.store.save(state)
                await websocket.send_json({"type": "language", "language": state.language})
            elif kind == "control":
                c = WSControl.model_validate(msg)
                state = await orch.store.load(session_id)
                state.control_patch = merge_patch(state.control_patch, c.patch)
                await orch.store.save(state)
                await websocket.send_json({"type": "state", "state": state.state})
            else:
                await websocket.send_json({"type": "error", "message": f"unknown type: {kind}"})
    except WebSocketDisconnect:
        return
