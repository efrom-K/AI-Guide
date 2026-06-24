"""Orchestrator: the single stateful brain. Owns the FSM and all state.

It is the only component that calls Geo, the pipeline (Scorer/Narrator),
Companion and the state store. Roles stay stateless and talk only through the
SessionState the orchestrator hands them.

FSM (states x events -> next), incl. degradation paths from the review:

    IDLE/EXPANDING/NARRATING/SWITCHING/ANSWERING ──TICK──▶ SCORING
    SCORING ──NARRATED──▶ NARRATING   ──SWITCH──▶ SWITCHING
    SCORING ──SILENCE──▶ IDLE         ──EXPANDED──▶ EXPANDING
    SCORING ──FAILURE──▶ ERROR        ERROR ──TICK──▶ RECOVERY ──TICK──▶ SCORING
    (any)   ──USER_SPEECH──▶ LISTENING ──ANSWERED──▶ ANSWERING
    (any)   ──GO_OFFLINE──▶ OFFLINE    OFFLINE ──GO_ONLINE──▶ RECOVERY
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.agent.companion import Companion
from app.services.agent.pipeline import TextPipeline
from app.services.geo.discovery import Discovery
from app.services.state.store import StateStore
from app.shared.schemas import (
    Candidate,
    CompanionInput,
    ControlPatch,
    GeoPoint,
    Heading,
    Pace,
    Significance,
)

_HISTORY_CAP = 12
_CONVO_CAP = 20
_MAX_ELABORATE = 2  # follow-ups per place when nothing new is nearby


class State(StrEnum):
    IDLE = "idle"
    EXPANDING = "expanding"
    SCORING = "scoring"
    NARRATING = "narrating"
    SWITCHING = "switching"
    LISTENING = "listening"
    ANSWERING = "answering"
    OFFLINE = "offline"
    ERROR = "error"
    RECOVERY = "recovery"


@dataclass
class OrchestratorOutput:
    state: str
    kind: str  # narration | silence | reply | error | offline
    text: str = ""
    place_id: str | None = None
    significance: str | None = None
    place_name: str | None = None
    lat: float | None = None
    lon: float | None = None


def fingerprint(candidates: list[Candidate]) -> str:
    return ",".join(sorted(c.place.id for c in candidates))


def merge_patch(base: ControlPatch, patch: ControlPatch) -> ControlPatch:
    return ControlPatch(
        skip_categories=sorted(set(base.skip_categories) | set(patch.skip_categories)),
        focus_topics=sorted(set(base.focus_topics) | set(patch.focus_topics)),
        verbosity=patch.verbosity or base.verbosity,
        mute=patch.mute or base.mute,
    )


class Orchestrator:
    def __init__(
        self,
        discovery: Discovery,
        pipeline: TextPipeline,
        companion: Companion,
        store: StateStore,
    ) -> None:
        self.discovery = discovery
        self.pipeline = pipeline
        self.companion = companion
        self.store = store

    # -- narration hot-path ------------------------------------------------- #
    async def on_position(
        self, session_id: str, position: GeoPoint, heading: Heading, pace: Pace
    ) -> OrchestratorOutput:
        st = await self.store.load(session_id)
        st.position, st.heading, st.pace = position, heading, pace

        if st.state == State.OFFLINE:
            # server can't reach the cloud — degrade to silence (cached replay
            # is the client's job offline). Stay until GO_ONLINE.
            return await self._finish(st, State.OFFLINE, "offline")

        try:
            result = await self.discovery.discover_adaptive(
                position, heading, st.seen_place_ids, st.current_radius_m
            )
        except Exception:
            return await self._finish(st, State.ERROR, "error")

        st.current_radius_m = result.radius_m

        if st.control_patch.mute:
            return await self._finish(st, State.IDLE, "silence")

        # heuristic gate: unchanged candidate set + no expansion -> skip the Scorer.
        # Nothing new nearby: instead of silence, keep telling MORE about the last
        # place (bounded), so the user isn't left hanging in an empty area.
        fp = fingerprint(result.candidates)
        if fp == st.last_candidate_fingerprint and not result.expanded:
            return await self._elaborate_or_silence(st, heading, pace)
        st.last_candidate_fingerprint = fp

        # nothing unseen nearby -> don't waste a Scorer call; elaborate or stay quiet.
        if not result.candidates:
            return await self._elaborate_or_silence(st, heading, pace, expanded=result.expanded)

        switching = bool(
            st.last_place_id
            and result.candidates
            and result.candidates[0].place.id != st.last_place_id
        )
        try:
            out = await self.pipeline.step(
                result.candidates,
                seen=st.seen_place_ids,
                history=st.narration_history,
                address=st.address,
                heading=heading,
                pace=pace,
                preferences=st.control_patch,
                switching=switching,
                language=st.language,
            )
        except Exception:
            return await self._finish(st, State.ERROR, "error")

        if out.text and out.place:
            st.narration_history = (st.narration_history + [out.text])[-_HISTORY_CAP:]
            st.seen_place_ids.append(out.place.id)
            st.last_place_id = out.place.id
            st.last_place = out.place
            st.last_significance = out.significance
            st.elaboration_count = 0  # fresh place — allow follow-ups again
            state = State.SWITCHING if switching else State.NARRATING
            return await self._finish(
                st, state, "narration", out.text, out.place, out.significance
            )

        return await self._elaborate_or_silence(st, heading, pace, expanded=result.expanded)

    # When nothing new is nearby, tell more about the last place (capped) instead
    # of going silent; fall back to silence once there's nothing left to add.
    async def _elaborate_or_silence(
        self, st, heading: Heading, pace: Pace, *, expanded: bool = False
    ) -> OrchestratorOutput:
        if st.last_place is not None and st.elaboration_count < _MAX_ELABORATE:
            try:
                text = await self.pipeline.elaborate(
                    st.last_place,
                    st.last_significance or Significance.MEDIUM,
                    history=st.narration_history,
                    address=st.address,
                    heading=heading,
                    pace=pace,
                    language=st.language,
                )
            except Exception:
                text = ""
            if text:
                st.elaboration_count += 1
                st.narration_history = (st.narration_history + [text])[-_HISTORY_CAP:]
                return await self._finish(
                    st, State.NARRATING, "narration", text,
                    st.last_place, st.last_significance,
                )
            st.elaboration_count = _MAX_ELABORATE  # nothing more to add — stop trying
        state = State.EXPANDING if expanded else State.IDLE
        return await self._finish(st, state, "silence")

    # -- barge-in ----------------------------------------------------------- #
    async def on_utterance(self, session_id: str, text: str) -> OrchestratorOutput:
        st = await self.store.load(session_id)
        st.state = State.LISTENING
        last = st.narration_history[-1] if st.narration_history else None

        comp = await self.companion.respond(
            CompanionInput(
                user_message=text,
                last_narration=last,
                address=st.address,
                history=st.conversation[-6:],
                language=st.language,
            )
        )
        if comp.control_patch is not None:
            st.control_patch = merge_patch(st.control_patch, comp.control_patch)
        st.conversation = (st.conversation + [f"U: {text}", f"G: {comp.reply}"])[-_CONVO_CAP:]
        return await self._finish(st, State.ANSWERING, "reply", comp.reply)

    # -- connectivity ------------------------------------------------------- #
    async def set_online(self, session_id: str, online: bool) -> None:
        st = await self.store.load(session_id)
        st.state = State.RECOVERY if online else State.OFFLINE
        await self.store.save(st)

    # ---------------------------------------------------------------------- #
    async def _finish(
        self,
        st,
        state: State,
        kind: str,
        text: str = "",
        place=None,
        significance=None,
    ) -> OrchestratorOutput:
        st.state = state
        await self.store.save(st)
        sig = significance.value if significance is not None else None
        return OrchestratorOutput(
            state.value,
            kind,
            text,
            place.id if place else None,
            sig,
            place.name if place else None,
            place.location.lat if place else None,
            place.location.lon if place else None,
        )
