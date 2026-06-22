"""LLM client wrapper around the Anthropic SDK + a fake for tests.

Roles map to models via ``router.model_for``. Two entry points:
  * complete_text — plain text (Narrator / Companion)
  * complete_json — structured JSON validated by the API (Scorer)

``FakeLLM`` returns canned responses so the pipeline and tests run with no
API key; real narration quality is exercised with a key via ``AnthropicLLM``.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.config import settings

from .router import Role, model_for


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
