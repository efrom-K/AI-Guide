import asyncio
import base64
import contextlib

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import settings
from app.services.agent.factory import build_orchestrator
from app.services.stt.stt import build_stt


def _heuristic_app(stt_text: str = "А когда его построили?"):
    # force a deterministic, offline backend regardless of .env
    settings.agent_backend = "heuristic"
    settings.geo_source = "fixture"
    settings.stt_backend = "mock"
    settings.stt_mock_text = stt_text
    main_module._orchestrator = build_orchestrator()
    main_module._stt = build_stt()
    return TestClient(main_module.app)


def test_ws_narrates_then_replies():
    client = _heuristic_app()
    with client.websocket_connect("/ws") as ws:
        # standing on St Basil's (in the fixture) -> should narrate
        ws.send_json(
            {"type": "position", "lat": 55.7525, "lon": 37.6231, "gaze_confidence": "low"}
        )
        first = ws.receive_json()
        assert first["type"] == "state"
        second = ws.receive_json()
        assert second["type"] == "narration"
        assert "Василия" in second["text"]

        # barge-in
        ws.send_json({"type": "utterance", "text": "пропускай магазины"})
        ws.receive_json()  # state
        reply = ws.receive_json()
        assert reply["type"] == "reply"
        assert reply["text"]


def test_ws_audio_transcribes_then_replies():
    client = _heuristic_app(stt_text="пропускай магазины")
    with client.websocket_connect("/ws") as ws:
        clip = base64.b64encode(b"fake-audio-bytes").decode()
        ws.send_json({"type": "audio", "data_b64": clip, "format": "webm"})
        transcript = ws.receive_json()
        assert transcript["type"] == "transcript"
        assert transcript["text"] == "пропускай магазины"
        ws.receive_json()  # state
        reply = ws.receive_json()
        assert reply["type"] == "reply"
        assert reply["text"]


def test_ws_audio_empty_transcript_errors():
    # Whisper heard nothing intelligible -> say so, don't answer a blank question
    # (which used to produce a vague "ок, продолжим" that felt like no answer).
    client = _heuristic_app(stt_text="   ")
    with client.websocket_connect("/ws") as ws:
        clip = base64.b64encode(b"silence").decode()
        ws.send_json({"type": "audio", "data_b64": clip, "format": "wav"})
        assert ws.receive_json()["type"] == "transcript"
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "расслыш" in err["message"].lower()


def test_ws_listen_pauses_then_question_resumes():
    # Opening the mic ("listen on") must hold the producer so it can't narrate over
    # the user; the answered question then resumes the tour.
    client = _heuristic_app(stt_text="пропускай магазины")
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "listen", "on": True})
        # position arrives while listening -> no narration is emitted (producer held)
        ws.send_json(
            {"type": "position", "lat": 55.7525, "lon": 37.6231, "gaze_confidence": "low"}
        )
        clip = base64.b64encode(b"fake-audio").decode()
        ws.send_json({"type": "audio", "data_b64": clip, "format": "wav"})
        assert ws.receive_json()["type"] == "transcript"
        assert ws.receive_json()["type"] == "state"
        reply = ws.receive_json()
        assert reply["type"] == "reply" and reply["text"]
        # tour resumes after answering
        assert ws.receive_json()["type"] == "state"
        assert ws.receive_json()["type"] == "narration"


def test_producer_exits_on_shutdown_even_while_barging():
    """Zombie-producer regression: a disconnect (the /ws finally cancels the producer)
    that lands WHILE a barge-in is in flight must still terminate the producer. Before
    the fix the shutdown CancelledError was swallowed as a barge-in preempt, so the
    producer parked/hot-looped forever on the closed socket. The `closing` flag makes
    the producer tell the two apart and exit."""

    async def scenario():
        rt = main_module._SessionRuntime(ws=None, orch=None, session_id="z")

        async def idle_step():  # stand-in for _step: park until cancelled
            rt.wake.clear()
            await rt.wake.wait()

        rt._step = idle_step
        producer = asyncio.ensure_future(rt.run_producer())
        await asyncio.sleep(0.05)  # let it create + await the first step_task
        # simulate the /ws finally during an in-flight barge-in:
        rt.barging = True
        rt.closing = True
        producer.cancel()
        # must finish promptly; without the fix it parks on resume.wait() forever and
        # this wait_for raises TimeoutError instead.
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(producer, timeout=2.0)
        assert producer.done()

    asyncio.run(scenario())


def test_ws_unknown_type_errors():
    client = _heuristic_app()
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "nonsense"})
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_ws_ping_is_ignored():
    # keepalive pings must not error or disturb the narration flow
    client = _heuristic_app()
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        ws.send_json(
            {"type": "position", "lat": 55.7525, "lon": 37.6231, "gaze_confidence": "low"}
        )
        assert ws.receive_json()["type"] == "state"
        assert ws.receive_json()["type"] == "narration"


def test_ws_resume_keeps_session_after_disconnect():
    # A reconnect with the same ?sid= must resume the SAME session: the seen-list
    # survives the disconnect (no delete-on-disconnect) so the tour doesn't repeat.
    client = _heuristic_app()
    orch = main_module._orchestrator
    sid = "resumetest123456"
    with client.websocket_connect(f"/ws?sid={sid}") as ws:
        ws.send_json(
            {"type": "position", "lat": 55.7525, "lon": 37.6231, "gaze_confidence": "low"}
        )
        assert ws.receive_json()["type"] == "state"
        assert ws.receive_json()["type"] == "narration"
    # after the socket closes the session is kept (TTL-evicted later, not deleted now)
    state = asyncio.run(orch.store.load(sid))
    assert state.seen_place_ids, "seen-list should persist across reconnects"
