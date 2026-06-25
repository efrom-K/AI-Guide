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

from app.config import settings
from app.services.agent.companion import Companion
from app.services.agent.pipeline import TextPipeline
from app.services.geo.discovery import Discovery
from app.services.geo.geocoder import Geocoder
from app.services.state.store import StateStore
from app.shared.geo_math import haversine_m
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
# Follow-ups per place when nothing new is nearby. High on purpose: while the area
# is empty the guide keeps adding to the current place's story until the Narrator
# runs out (returns silence), rather than going quiet after a couple of lines.
_MAX_ELABORATE = 6


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
        geocoder: Geocoder | None = None,
    ) -> None:
        self.discovery = discovery
        self.pipeline = pipeline
        self.companion = companion
        self.store = store
        self.geocoder = geocoder

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

        # resolve which city/district/street we're in (move-gated, off-cadence).
        await self._resolve_area(st, position)

        # general -> specific: when we first enter an area, open with it (a short
        # city/district intro) before descending to the concrete objects inside.
        if not st.control_patch.mute:
            intro = await self._maybe_area_intro(st, heading, pace)
            if intro is not None:
                return intro

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
            return await self._continue_monologue(st, heading, pace)
        st.last_candidate_fingerprint = fp

        # nothing unseen nearby -> don't waste a Scorer call; carry the monologue.
        if not result.candidates:
            return await self._continue_monologue(st, heading, pace, expanded=result.expanded)

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
            st.area_beats = 0  # after an object, let the area speak again (return to it)
            state = State.SWITCHING if switching else State.NARRATING
            return await self._finish(
                st, state, "narration", out.text, out.place, out.significance
            )

        return await self._continue_monologue(st, heading, pace, expanded=result.expanded)

    # -- area resolution (general -> specific spine) ------------------------ #
    async def _resolve_area(self, st, position: GeoPoint) -> None:
        """Reverse-geocode the current city/district/street, move-gated so the
        extra request is rare. A change of area resets the area monologue state."""
        if self.geocoder is None:
            return
        moved = (
            st.last_geo_pos is None
            or haversine_m(position, st.last_geo_pos) >= settings.geocoder_min_move_m
        )
        if not moved:
            return
        try:
            addr = await self.geocoder.reverse(position, st.language)
        except Exception:
            return
        st.last_geo_pos = position
        if not any((addr.country, addr.city, addr.district, addr.street)):
            return  # geocoder came back empty — keep whatever we had
        st.address = addr
        new_key = addr.district or addr.city
        if new_key and new_key != st.area_key:
            st.area_key = new_key
            st.area_facts = None
            st.area_intro_done = False
            st.area_beats = 0

    def _has_area(self, st) -> bool:
        a = st.address
        return bool(a.district or a.city or a.street)

    async def _maybe_area_intro(
        self, st, heading: Heading, pace: Pace
    ) -> OrchestratorOutput | None:
        """Open a freshly entered area with a short city/district line, before
        descending to the objects inside it. Returns None if no intro is due."""
        if st.area_intro_done or not self._has_area(st):
            return None
        st.area_intro_done = True  # one opener per area, even if it comes back empty
        text = await self._area_line(st, pace, intro=True)
        if not text:
            return None
        return await self._finish(st, State.NARRATING, "narration", text)

    # When nothing new is nearby, carry a continuous monologue: keep telling about
    # the area (district/street/city), then fall back to elaborating the last
    # object, and only then go silent.
    async def _continue_monologue(
        self, st, heading: Heading, pace: Pace, *, expanded: bool = False
    ) -> OrchestratorOutput:
        # 1) area beat — the spine that fills the gap between objects
        if self._has_area(st) and st.area_beats < settings.area_max_beats:
            text = await self._area_line(st, pace, intro=False)
            if text:
                return await self._finish(st, State.NARRATING, "narration", text)
            st.area_beats = settings.area_max_beats  # area exhausted — stop trying

        # 2) fall back to telling MORE about the last object
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

    # one area beat: lazily fetch area facts (once per area), then narrate.
    # The intro stays fast (general knowledge) — facts are fetched for the first
    # real gap-beat, so entering an area never stalls on a web search.
    async def _area_line(self, st, pace: Pace, *, intro: bool) -> str:
        if settings.area_enrich and not intro and st.area_facts is None:
            facts = await self.pipeline.enrich_area(
                st.address, st.position, timeout_s=settings.enrich_timeout_s
            )
            st.area_facts = facts or ""  # cache "" so we don't refetch every beat
        try:
            text = await self.pipeline.narrate_area(
                st.address,
                facts=st.area_facts or None,
                intro=intro,
                beat=st.area_beats,
                last_place_name=st.last_place.name if st.last_place else None,
                history=st.narration_history,
                pace=pace,
                language=st.language,
            )
        except Exception:
            return ""
        if text:
            st.area_beats += 1
            st.narration_history = (st.narration_history + [text])[-_HISTORY_CAP:]
        return text

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
