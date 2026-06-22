from fastapi.testclient import TestClient

import app.main as main_module
from app.config import settings
from app.services.agent.factory import build_orchestrator


def _heuristic_app():
    # force a deterministic, offline backend regardless of .env
    settings.agent_backend = "heuristic"
    settings.geo_source = "fixture"
    main_module._orchestrator = build_orchestrator()
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


def test_ws_unknown_type_errors():
    client = _heuristic_app()
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "nonsense"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
