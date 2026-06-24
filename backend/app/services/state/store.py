"""Session state store: in-memory (default) or Redis.

The orchestrator owns all state mutation: load -> mutate -> save. ``load``
returns a deep copy so a half-applied mutation never leaks before ``save``.
"""

from __future__ import annotations

from typing import Protocol

from app.shared.schemas import SessionState

_KEY = "session:{}"


def _new_session(session_id: str) -> SessionState:
    """Fresh session seeded with the configured default language."""
    from app.config import settings

    return SessionState(session_id=session_id, language=settings.default_language)


class StateStore(Protocol):
    async def load(self, session_id: str) -> SessionState: ...
    async def save(self, state: SessionState) -> None: ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self._data: dict[str, SessionState] = {}

    async def load(self, session_id: str) -> SessionState:
        state = self._data.get(session_id)
        if state is None:
            return _new_session(session_id)
        return state.model_copy(deep=True)

    async def save(self, state: SessionState) -> None:
        self._data[state.session_id] = state.model_copy(deep=True)


class RedisStateStore:
    """Requires a running Redis and the ``redis`` package. Used when
    ``settings.redis_url`` is set."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._r = redis.from_url(url, encoding="utf-8", decode_responses=True)

    async def load(self, session_id: str) -> SessionState:
        raw = await self._r.get(_KEY.format(session_id))
        if raw is None:
            return _new_session(session_id)
        return SessionState.model_validate_json(raw)

    async def save(self, state: SessionState) -> None:
        await self._r.set(_KEY.format(state.session_id), state.model_dump_json())


def default_store() -> StateStore:
    from app.config import settings

    if settings.redis_url:
        return RedisStateStore(settings.redis_url)
    return InMemoryStateStore()
