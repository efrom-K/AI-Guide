from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "ai-audio-guide"


def test_index_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "AI Audio Guide" in r.text


def test_ws_echo():
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "position", "lat": 1.0, "lon": 2.0})
        data = ws.receive_json()
        assert data["type"] == "echo"
        assert data["received"]["lat"] == 1.0
