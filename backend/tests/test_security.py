"""Этап 0 — protect the open /ws endpoint and cap spend."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.main as main_module
from app.config import settings
from app.main import _too_big
from app.services.agent.factory import build_orchestrator
from app.services.llm.client import METER, BudgetExceeded, OpenAICompatLLM
from app.services.llm.router import Role
from app.services.stt.stt import build_stt


def _app() -> TestClient:
    settings.agent_backend = "heuristic"
    settings.geo_source = "fixture"
    settings.stt_backend = "mock"
    main_module._orchestrator = build_orchestrator()
    main_module._stt = build_stt()
    return TestClient(main_module.app)


# --- hard spend cap --------------------------------------------------------- #
def test_hard_cap_blocks_llm_call():
    settings.usd_hard_cap = 1.0
    saved = METER.provider_cost
    METER.provider_cost = 5.0  # pretend the process has already spent $5
    try:
        llm = OpenAICompatLLM(base_url="http://unused", api_key="k", default_model="m")
        with pytest.raises(BudgetExceeded):
            asyncio.run(llm.complete_text(Role.NARRATOR, "s", "u"))
    finally:
        METER.provider_cost = saved
        settings.usd_hard_cap = 0.0


def test_under_cap_does_not_block():
    settings.usd_hard_cap = 1000.0
    saved = METER.provider_cost
    METER.provider_cost = 0.0
    try:
        assert METER.over_hard_cap() is False
    finally:
        METER.provider_cost = saved
        settings.usd_hard_cap = 0.0


# --- /ws token gate --------------------------------------------------------- #
def test_ws_rejects_without_token_and_accepts_with_it():
    settings.ws_token = "secret"
    try:
        client = _app()
        # no token -> connection refused before accept
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
        # correct token -> works
        with client.websocket_connect("/ws?token=secret") as ws:
            ws.send_json({"type": "position", "lat": 55.7525, "lon": 37.6231})
            assert ws.receive_json()["type"] in ("state", "narration")
    finally:
        settings.ws_token = ""


# --- input-size limits ------------------------------------------------------ #
def test_too_big_helper():
    settings.max_utterance_chars = 10
    settings.max_audio_b64_chars = 20
    try:
        assert _too_big({"text": "x" * 50}, "utterance") is True
        assert _too_big({"text": "ok"}, "utterance") is False
        assert _too_big({"data_b64": "y" * 50}, "audio") is True
        assert _too_big({"data_b64": "y" * 5}, "audio") is False
        assert _too_big({"lat": 1, "lon": 2}, "position") is False
    finally:
        settings.max_utterance_chars = 2000
        settings.max_audio_b64_chars = 8_000_000
