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
    NarrativePlan,
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
            # Always start discovery tight (default radius) so the search never
            # stays inflated at 500 m; it still expands within this tick if nothing
            # is found, but the next tick starts close again.
            result = await self.discovery.discover_adaptive(
                position, heading, st.seen_place_ids, settings.default_radius_m
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

        # Weave gate: only objects within weave_radius_m are narrated as "right
        # here"; anything farther (found by an expanded search) is left to the area
        # monologue. Cap the count to bound the Scorer's input/output size.
        near = [c for c in result.candidates if c.distance_m <= settings.weave_radius_m]
        near = near[: settings.scorer_max_candidates]
        if not near:
            return await self._continue_monologue(st, heading, pace, expanded=result.expanded)

        switching = bool(
            st.last_place_id and near[0].place.id != st.last_place_id
        )
        plan = st.narrative_plan
        try:
            out = await self.pipeline.step(
                near,
                seen=st.seen_place_ids,
                history=st.narration_history,
                address=st.address,
                heading=heading,
                pace=pace,
                preferences=st.control_patch,
                switching=switching,
                language=st.language,
                theme=plan.active_theme() or None,
                told=plan.told,
                next_hook=plan.next_hook,
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
            plan.told.append(out.place.name)  # record in the arc ledger (anti-repeat)
            plan.next_hook = None
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
            # fresh area => fresh story arc, but keep the user's chosen theme (if any)
            st.narrative_plan = NarrativePlan(theme_override=st.narrative_plan.theme_override)

    def _has_area(self, st) -> bool:
        a = st.address
        return bool(a.district or a.city or a.street)

    async def _maybe_area_intro(
        self, st, heading: Heading, pace: Pace
    ) -> OrchestratorOutput | None:
        """On entering a new area, form the story arc (theme + outline) and speak
        its opener — before descending to the objects inside. None if not due."""
        if st.area_intro_done or not self._has_area(st):
            return None
        st.area_intro_done = True  # one opener per area, even if it comes back empty
        plan = st.narrative_plan
        try:
            # fast: the planner forms theme+outline+opener from general knowledge;
            # web area facts are fetched lazily for the later beats.
            draft = await self.pipeline.make_plan(
                st.address,
                facts=st.area_facts,
                theme_override=plan.theme_override,
                language=st.language,
            )
        except Exception:
            draft = None
        if draft is None:
            return None
        plan.area_key = st.area_key
        plan.theme = draft.theme or plan.theme
        plan.outline = draft.outline or plan.outline
        opener = (draft.opener or "").strip()
        if not opener:
            return None
        plan.told.append("вступление в район")
        st.narration_history = (st.narration_history + [opener])[-_HISTORY_CAP:]
        return await self._finish(st, State.NARRATING, "narration", opener)

    # When nothing new is nearby, carry the story arc: advance the area outline by
    # one topic (or weave a topic the user asked about), then fall back to
    # elaborating the last object, and only then go silent.
    async def _continue_monologue(
        self, st, heading: Heading, pace: Pace, *, expanded: bool = False
    ) -> OrchestratorOutput:
        # 1) advance the area story arc by one topic
        if self._has_area(st):
            text = await self._area_line(st, pace)
            if text:
                return await self._finish(st, State.NARRATING, "narration", text)

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

    # one beat of the area story arc: pick the next topic (a user-asked focus wins,
    # else the next un-told outline topic), lazily fetch area facts, then narrate.
    async def _area_line(self, st, pace: Pace) -> str:
        plan = st.narrative_plan
        focus = plan.pending_focus[0] if plan.pending_focus else None
        topic = focus or plan.next_topic()
        if topic is None:
            return ""  # outline exhausted -> let elaborate/silence take over
        if settings.area_enrich and st.area_facts is None:
            facts = await self.pipeline.enrich_area(
                st.address, st.position, timeout_s=settings.enrich_timeout_s
            )
            st.area_facts = facts or ""  # cache "" so we don't refetch every beat
        try:
            text = await self.pipeline.narrate_area(
                st.address,
                facts=st.area_facts or None,
                theme=plan.active_theme() or None,
                topic=topic,
                told=plan.told,
                next_hook=plan.next_hook,
                last_place_name=st.last_place.name if st.last_place else None,
                history=st.narration_history,
                pace=pace,
                language=st.language,
            )
        except Exception:
            return ""
        if text:
            if focus:
                plan.pending_focus.pop(0)  # answered/woven this user topic
            plan.told.append(topic)
            plan.next_hook = None
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
        # weave the answer back into the tour: queue the user's topic so the next
        # area beat picks it up ("кстати, ты спрашивал про…"). Highest priority.
        plan = st.narrative_plan
        if text.strip() and text.strip() not in plan.pending_focus:
            plan.pending_focus.append(text.strip())
        return await self._finish(st, State.ANSWERING, "reply", comp.reply)

    # -- theme switching (user picks/voices a topic to revolve around) ------- #
    async def set_theme(self, session_id: str, theme: str) -> None:
        st = await self.store.load(session_id)
        plan = st.narrative_plan
        plan.theme_override = theme.strip() or None
        # re-open the area so the arc is rebuilt around the chosen theme
        st.area_intro_done = False
        plan.outline = []
        await self.store.save(st)

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
