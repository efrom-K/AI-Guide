"""LLM client wrapper around the Anthropic SDK + a fake for tests.

Roles map to models via ``router.model_for``. Two entry points:
  * complete_text — plain text (Narrator / Companion)
  * complete_json — structured JSON validated by the API (Scorer)

``FakeLLM`` returns canned responses so the pipeline and tests run with no
API key; real narration quality is exercised with a key via ``AnthropicLLM``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from app.config import settings

from .router import Role, model_for

_log = logging.getLogger("aiguide.tokens")
if not _log.handlers:  # ensure token usage prints regardless of uvicorn's config
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json(text: str) -> dict[str, Any]:
    return json.loads(_FENCE.sub("", text).strip())


class TokenMeter:
    """Process-cumulative token/cost accounting for the OpenAI-compatible client.

    Logs per-call usage and a running total. Cost is estimated from the configured
    per-Mtok prices (0 => skip). The optional budget is only a soft warning — the
    real monthly cap must be set on the provider (OpenRouter) dashboard.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.tok_in = 0
        self.tok_out = 0
        self._warned = False

    @property
    def cost_usd(self) -> float:
        return (
            self.tok_in / 1e6 * settings.openai_price_in_per_mtok
            + self.tok_out / 1e6 * settings.openai_price_out_per_mtok
        )

    def record(self, role: Role, model: str, usage: dict[str, Any] | None) -> None:
        usage = usage or {}
        ti = int(usage.get("prompt_tokens", 0) or 0)
        to = int(usage.get("completion_tokens", 0) or 0)
        self.calls += 1
        self.tok_in += ti
        self.tok_out += to
        budget = settings.usd_session_budget
        cost = self.cost_usd
        tail = f" | ~${cost:.4f}" + (f"/${budget:.0f}" if budget else "")
        _log.info(
            "%s %s: +%d/+%d tok | total in=%d out=%d (%d calls)%s",
            role, model, ti, to, self.tok_in, self.tok_out, self.calls, tail,
        )
        if budget and cost >= budget and not self._warned:
            self._warned = True
            _log.warning(
                "Session spend ~$%.2f reached the $%.0f soft budget. "
                "Set a hard monthly cap on the OpenRouter dashboard.",
                cost, budget,
            )


METER = TokenMeter()


class LLMClient(Protocol):
    async def complete_text(
        self, role: Role, system: str, user: str, *, max_tokens: int = 1024
    ) -> str: ...

    async def complete_json(
        self,
        role: Role,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any]: ...


class AnthropicLLM:
    """Real client. Requires ANTHROPIC_API_KEY (in env or settings)."""

    def __init__(self, api_key: str | None = None) -> None:
        import anthropic

        key = api_key or settings.anthropic_api_key or None
        self._client = anthropic.AsyncAnthropic(api_key=key)

    @staticmethod
    def _text(resp: Any) -> str:
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    async def complete_text(
        self, role: Role, system: str, user: str, *, max_tokens: int = 1024
    ) -> str:
        resp = await self._client.messages.create(
            model=model_for(role),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return self._text(resp)

    async def complete_json(
        self,
        role: Role,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        resp = await self._client.messages.create(
            model=model_for(role),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        return json.loads(self._text(resp))


class FakeLLM:
    """Deterministic stand-in. ``text_response`` / ``json_response`` may be a
    constant or a callable(role, system, user) -> value."""

    def __init__(self, text_response: Any = "[SILENCE]", json_response: Any = None) -> None:
        self._text = text_response
        self._json = json_response or {"scored": [], "next": None, "expand_radius": False}

    async def complete_text(
        self, role: Role, system: str, user: str, *, max_tokens: int = 1024
    ) -> str:
        value = self._text(role, system, user) if callable(self._text) else self._text
        return str(value)

    async def complete_json(
        self,
        role: Role,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        return self._json(role, system, user) if callable(self._json) else self._json


class OpenAICompatLLM:
    """Any OpenAI-compatible /chat/completions endpoint — LM Studio, OpenRouter,
    vLLM, etc. One impl covers local (free) and cloud providers."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        import httpx

        self._url = (base_url or settings.openai_base_url).rstrip("/") + "/chat/completions"
        self._default = default_model or settings.openai_model
        self._client = httpx.AsyncClient(
            timeout=90.0,
            headers={
                "Authorization": f"Bearer {api_key or settings.openai_api_key}",
                "X-Title": "AI Audio Guide",
            },
        )

    def _model_for(self, role: Role) -> str:
        override = {
            Role.SCORER: settings.openai_model_scorer,
            Role.NARRATOR: settings.openai_model_narrator,
            Role.LANDMARK: settings.openai_model_landmark,
            Role.COMPANION: settings.openai_model_companion,
        }[role]
        model = override or self._default
        if not model:
            raise RuntimeError("No OpenAI-compatible model configured (set OPENAI_MODEL)")
        return model

    async def _chat(self, role: Role, system: str, user: str, max_tokens: int, **extra) -> str:
        model = self._model_for(role)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            **extra,
        }
        if settings.openai_reasoning_effort:
            payload["reasoning"] = {"effort": settings.openai_reasoning_effort}
        resp = await self._client.post(self._url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        METER.record(role, model, data.get("usage"))
        return data["choices"][0]["message"]["content"].strip()

    async def complete_text(
        self, role: Role, system: str, user: str, *, max_tokens: int = 1024
    ) -> str:
        return await self._chat(role, system, user, max_tokens, temperature=0.8)

    async def complete_json(
        self,
        role: Role,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "output", "strict": True, "schema": schema},
        }
        text = await self._chat(
            role, system, user, max_tokens, temperature=0, response_format=response_format
        )
        try:
            return _parse_json(text)
        except json.JSONDecodeError:
            # safety net: re-ask in plain text mode with an explicit instruction
            guard = f"{user}\n\nВерни строго валидный JSON по схеме, без markdown."
            text = await self._chat(role, system, guard, max_tokens, temperature=0)
            return _parse_json(text)

    async def aclose(self) -> None:
        await self._client.aclose()
