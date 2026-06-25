"""FastAPI entrypoint.

  * GET  /health  — liveness
  * GET  /        — browser demo client (web/index.html)
  * WS   /ws      — drives the orchestrator: position/utterance in, narration/
                    reply/state out (audio is added with a TTS provider)
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.services.agent.factory import build_orchestrator
from app.services.agent.languages import normalize
from app.services.llm.client import METER, SESSION_ID
from app.services.agent.orchestrator import Orchestrator, OrchestratorOutput, merge_patch
from app.services.stt.stt import STTClient, build_stt
from app.shared.schemas import (
    GeoPoint,
    Heading,
    Pace,
    WSAudioInput,
    WSControl,
    WSPositionUpdate,
    WSSetLanguage,
    WSSetTheme,
    WSUserUtterance,
)

app = FastAPI(title="AI Audio Guide", version="0.1.0")
_log = logging.getLogger("aiguide.ws")

# lightweight observability state
_active_sessions: set[str] = set()
_counters = {"step_errors": 0, "question_errors": 0}
_READY_FAIL_THRESHOLD = 3  # consecutive LLM failures => /ready goes unhealthy

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


@app.on_event("startup")
async def _warm_stt() -> None:
    """Preload the STT model off the request path so the first voice question
    doesn't pay the (one-time) model-load cost. Done in a thread; non-fatal."""

    async def _load() -> None:
        try:
            await asyncio.to_thread(get_stt)
        except Exception:  # noqa: BLE001 — warming is best-effort
            pass

    asyncio.create_task(_load())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-audio-guide", "version": app.version}


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness: unhealthy if the last few LLM calls all failed (quota/region/outage),
    so a wedged backend can be detected/restarted instead of looking 'healthy'."""
    ok = METER.consecutive_failures < _READY_FAIL_THRESHOLD
    body = {
        "ready": ok,
        "active_sessions": len(_active_sessions),
        "consecutive_llm_failures": METER.consecutive_failures,
    }
    return JSONResponse(body, status_code=200 if ok else 503)


@app.get("/stats")
async def stats(token: str = "") -> dict:
    """Admin-only ops view: active sessions, cumulative + per-session cost, errors.
    Disabled unless STATS_TOKEN is set and matches."""
    if not settings.stats_token or token != settings.stats_token:
        raise HTTPException(status_code=404)
    return {
        "active_sessions": len(_active_sessions),
        "ws_step_errors": _counters["step_errors"],
        "ws_question_errors": _counters["question_errors"],
        **METER.snapshot(),
    }


@app.get("/")
async def index() -> HTMLResponse:
    if _WEB_INDEX.exists():
        # bake the /ws access token into the served page so the browser client
        # authenticates automatically (empty in dev => open).
        html = _WEB_INDEX.read_text(encoding="utf-8").replace("__WS_TOKEN__", settings.ws_token)
        return HTMLResponse(html)
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


class _SessionRuntime:
    """Per-connection runtime. A background *producer* generates the narration,
    decoupled from the GPS messages: ``position`` just refreshes the live context,
    while the producer emits ONE paragraph at a time, paced by the client's
    ``played`` signal (with a length-based fallback so older clients still flow).

    A question (``utterance``/``audio``) has top priority: it cancels the in-flight
    generation (its half-built, unsaved state is discarded), answers immediately,
    then the producer resumes — and the orchestrator weaves the answer in next.
    """

    def __init__(self, ws: WebSocket, orch: Orchestrator, session_id: str) -> None:
        self.ws = ws
        self.orch = orch
        self.session_id = session_id
        self.live_position: GeoPoint | None = None
        self.live_heading = Heading()
        self.live_pace = Pace.SLOW
        self.played = asyncio.Event()
        self.wake = asyncio.Event()  # context changed (new position / area / theme)
        self.resume = asyncio.Event()  # a barge-in finished; producer may continue
        self.barging = False
        self.step_task: asyncio.Task | None = None
        self.send_lock = asyncio.Lock()

    async def send_out(self, out: OrchestratorOutput) -> None:
        async with self.send_lock:
            await _send(self.ws, out)

    async def send_json(self, obj: dict) -> None:
        async with self.send_lock:
            await self.ws.send_json(obj)

    async def run_producer(self) -> None:
        while True:
            self.step_task = asyncio.ensure_future(self._step())
            try:
                await self.step_task
            except asyncio.CancelledError:
                if self.barging:  # preempted by a question, not a shutdown
                    self.barging = False
                    await self.resume.wait()
                    continue
                raise  # genuine shutdown -> let the producer exit
            except Exception as e:  # noqa: BLE001 — a bad step must NOT kill the producer
                _counters["step_errors"] += 1
                _log.warning("producer step failed (%s): %s", self.session_id, e)
                await asyncio.sleep(2)  # throttle so a persistent failure can't hot-loop
            finally:
                self.step_task = None

    async def _step(self) -> None:
        if self.live_position is None:  # no GPS yet — idle until the first fix
            self.wake.clear()
            await self.wake.wait()
            return
        SESSION_ID.set(self.session_id)  # attribute LLM cost to this session
        out = await self.orch.on_position(
            self.session_id, self.live_position, self.live_heading, self.live_pace
        )
        await self.send_out(out)
        if out.kind == "narration" and out.text:
            await self._wait_played(out.text)  # pace: don't outrun the player
        else:
            self.wake.clear()  # nothing to say -> idle until the context changes
            await self.wake.wait()

    async def _wait_played(self, text: str) -> None:
        self.played.clear()
        # ~12 chars/sec speaking; fall back if the client never signals (old clients)
        fallback = min(max(len(text) / 12.0, 4.0), 22.0)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.played.wait(), timeout=fallback)

    async def handle_question(self, msg: dict, kind: str) -> None:
        """Top-priority barge-in: cancel the producer's current step, answer now."""
        self.barging = True
        self.resume.clear()
        SESSION_ID.set(self.session_id)  # attribute the answer's LLM cost to this session
        if self.step_task is not None and not self.step_task.done():
            self.step_task.cancel()
        try:
            if kind == "audio":
                a = WSAudioInput.model_validate(msg)
                st = await self.orch.store.load(self.session_id)
                text = await get_stt().transcribe(
                    base64.b64decode(a.data_b64), language=st.language
                )
                await self.send_json({"type": "transcript", "text": text})
            else:
                text = WSUserUtterance.model_validate(msg).text
            out = await self.orch.on_utterance(self.session_id, text)
            await self.send_out(out)
        except Exception as e:  # noqa: BLE001 — a failed question must not drop the session
            _counters["question_errors"] += 1
            _log.warning("question handling failed (%s): %s", self.session_id, e)
            with contextlib.suppress(Exception):
                await self.send_json({"type": "error", "message": "не расслышал, попробуй ещё раз"})
        finally:
            self.resume.set()  # let the producer continue regardless


# process-wide count of concurrent WS connections per client IP (simple abuse guard)
_ip_conns: dict[str, int] = {}


def _client_ip(websocket: WebSocket) -> str:
    # behind Caddy the real IP is in X-Forwarded-For; fall back to the socket peer
    xff = websocket.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return websocket.client.host if websocket.client else "?"


def _too_big(msg: dict, kind: str) -> bool:
    if kind == "utterance":
        return len(str(msg.get("text", ""))) > settings.max_utterance_chars
    if kind == "audio":
        return len(str(msg.get("data_b64", ""))) > settings.max_audio_b64_chars
    return False


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    # --- gate the open endpoint BEFORE accepting (token + per-IP limit) -------
    if settings.ws_token and websocket.query_params.get("token", "") != settings.ws_token:
        await websocket.close(code=1008)  # policy violation
        return
    ip = _client_ip(websocket)
    if settings.max_connections_per_ip and _ip_conns.get(ip, 0) >= settings.max_connections_per_ip:
        await websocket.close(code=1008)
        return
    _ip_conns[ip] = _ip_conns.get(ip, 0) + 1

    await websocket.accept()
    orch = get_orchestrator()
    rt = _SessionRuntime(websocket, orch, uuid.uuid4().hex)
    _active_sessions.add(rt.session_id)
    producer = asyncio.ensure_future(rt.run_producer())
    try:
        while True:
            msg = await websocket.receive_json()
            kind = msg.get("type")
            if _too_big(msg, kind):
                await rt.send_json({"type": "error", "message": "message too large"})
                continue
            if kind == "position":
                p = WSPositionUpdate.model_validate(msg)
                rt.live_position = GeoPoint(lat=p.lat, lon=p.lon)
                rt.live_heading = Heading(
                    direction_deg=p.direction_deg, gaze_confidence=p.gaze_confidence
                )
                rt.live_pace = p.pace
                rt.wake.set()
            elif kind == "played":
                rt.played.set()
            elif kind in ("utterance", "audio"):
                await rt.handle_question(msg, kind)
            elif kind == "language":
                lang = WSSetLanguage.model_validate(msg)
                state = await orch.store.load(rt.session_id)
                state.language = normalize(lang.language)
                await orch.store.save(state)
                await rt.send_json({"type": "language", "language": state.language})
            elif kind == "theme":
                t = WSSetTheme.model_validate(msg)
                await orch.set_theme(rt.session_id, t.theme)
                rt.wake.set()
            elif kind == "control":
                c = WSControl.model_validate(msg)
                state = await orch.store.load(rt.session_id)
                state.control_patch = merge_patch(state.control_patch, c.patch)
                await orch.store.save(state)
                await rt.send_json({"type": "state", "state": state.state})
            else:
                await rt.send_json({"type": "error", "message": f"unknown type: {kind}"})
    except WebSocketDisconnect:
        pass
    finally:
        n = _ip_conns.get(ip, 0) - 1
        if n > 0:
            _ip_conns[ip] = n
        else:
            _ip_conns.pop(ip, None)
        producer.cancel()
        if rt.step_task is not None:
            rt.step_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await producer
        with contextlib.suppress(Exception):
            await orch.store.delete(rt.session_id)  # free the session promptly
        _active_sessions.discard(rt.session_id)
