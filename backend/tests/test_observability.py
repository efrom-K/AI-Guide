"""Этап 2 — readiness + admin stats."""

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import settings
from app.services.agent.factory import build_orchestrator
from app.services.llm.client import METER
from app.services.stt.stt import build_stt


def _client() -> TestClient:
    settings.agent_backend = "heuristic"
    settings.geo_source = "fixture"
    settings.stt_backend = "mock"
    main_module._orchestrator = build_orchestrator()
    main_module._stt = build_stt()
    return TestClient(main_module.app)


def test_ready_reflects_consecutive_llm_failures():
    c = _client()
    saved = METER.consecutive_failures
    try:
        METER.consecutive_failures = 0
        assert c.get("/ready").status_code == 200
        METER.consecutive_failures = 5
        assert c.get("/ready").status_code == 503
    finally:
        METER.consecutive_failures = saved


def test_stats_gated_by_token():
    c = _client()
    settings.stats_token = ""
    try:
        assert c.get("/stats").status_code == 404  # disabled when no token set
        settings.stats_token = "adm"
        assert c.get("/stats").status_code == 404  # missing/wrong token
        r = c.get("/stats?token=adm")
        assert r.status_code == 200
        body = r.json()
        assert "cost_usd" in body and "active_sessions" in body and "errors" in body
    finally:
        settings.stats_token = ""
