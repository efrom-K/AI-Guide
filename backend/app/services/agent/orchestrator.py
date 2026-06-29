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

import asyncio
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
_SEEN_CAP = 600  # cap the dedup list so a long walk can't grow session state unbounded
_TOLD_CAP = 80  # cap the arc's covered-topics ledger
_CONVO_CAP = 20
# Follow-ups per place when nothing new is nearby. Kept low: a couple of extra
# details is enough — beyond that the guide starts mussing the same place, which
# is exactly the "цепляет одну тему и мусолит её" complaint.
_MAX_ELABORATE = 2
# Connective area/city beats per lull, AFTER the planned outline is exhausted. These
# only fire when we have REAL verified area facts to ground them (see _area_line);
# ungrounded generic beats are the boring "по кругу" rambling, so without facts the
# guide says one short "пройдём дальше" bridge and goes quiet instead.
# Reset whenever a concrete object is narrated, so every lull gets a fresh budget.
_MAX_AREA_BEATS = 3
# Short spoken bridges for when the area material is exhausted and nothing is near:
# say one ("пройдём дальше") and then go genuinely silent, rather than filler.
_BRIDGES = (
    "Идём дальше.",
    "Пройдём дальше, тут пока тихо.",
    "Двигаемся дальше.",
    "Идём дальше — расскажу, как только будет что.",
)
# Varied angles for those connective beats — rotated by beat index so they don't
# repeat; the Narrator still dedups against `told`/history and stays facts-only.
_CONNECTIVE_ANGLES = (
    "история этого района или города",
    "атмосфера, характер и облик этого места",
    "чем район известен и чем живёт сегодня",
    "любопытная деталь, легенда или история этого места",
    "как этот район менялся со временем",
    "известные люди, события или культурные связи этого места",
)
# Hard ceiling on the adaptive-radius discovery per tick. Discovery now makes at
# most two Overpass calls (tight, then one wide), each with its own mirror-failover
# timeout; this caps the pair so a tick can't stall for minutes in a sparse/foreign
# place, while leaving enough room for the wide query + one failover. On timeout we
# keep talking about the current place rather than going silent.
_DISCOVERY_DEADLINE_S = 20.0


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


def fingerprint(candidates: list[Candidate], cache=None) -> str:
    """A stable signature of the bubble set used to gate the LLM. When a fact `cache`
    is given it's FACTS-AWARE: each id is tagged with whether its facts are cached yet.
    That keeps the gate stable for a genuinely factless object (no LLM re-call every
    tick), but RE-OPENS it the instant warm_ahead caches facts for a passing object
    whose facts were cold when it entered the bubble — so "walk up to a monument -> it
    gets narrated" is reliable instead of being burned forever by the first cold miss."""
    if cache is None:
        return ",".join(sorted(c.place.id for c in candidates))
    return ",".join(
        f"{c.place.id}:{int(cache.get(c.place.id) is not None)}"
        for c in sorted(candidates, key=lambda c: c.place.id)
    )


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
            # is found, but the next tick starts close again. Bounded by an overall
            # deadline so a slow/blocked Overpass can't stall the tick for minutes.
            discover = (
                self.discovery.discover_inventory(
                    session_id, position, heading, st.seen_place_ids
                )
                if settings.inventory_enabled
                else self.discovery.discover_adaptive(
                    position, heading, st.seen_place_ids, settings.default_radius_m
                )
            )
            result = await asyncio.wait_for(discover, timeout=_DISCOVERY_DEADLINE_S)
        except Exception:  # includes asyncio.TimeoutError from the deadline
            # Don't go silent: keep elaborating on the current place (or a short area
            # line) until discovery succeeds on a later tick.
            return await self._continue_monologue(st, heading, pace)

        st.current_radius_m = result.radius_m

        if st.control_patch.mute:
            return await self._finish(st, State.IDLE, "silence")

        # Warm facts for the whole live window (non-blocking) — collects facts about
        # the surrounding objects in the background, so the story is ready the moment
        # the user reaches one.
        self.pipeline.warm_ahead(result.candidates, address=st.address)

        # Narrate an object ONLY when the user is passing close to it ("проходишь
        # мимо"): within the small narrate bubble, nearest first. Outside it the area
        # story spine (city/district/street) carries the tour — no far-object
        # fallback, so the guide talks about the district, not about objects across
        # the city.
        near = [c for c in result.candidates if c.distance_m <= settings.narrate_radius_m]
        near = sorted(near, key=lambda c: c.distance_m)[: settings.scorer_max_candidates]

        # Gate on the BUBBLE set (not the wide window): skip the LLM when the same
        # object is still in the bubble (standing next to it) or the bubble is empty
        # -> advance the area spine instead. The fingerprint is FACTS-AWARE (see
        # `fingerprint`): it re-opens when warm_ahead caches facts for a passing object
        # whose facts were cold on arrival, so the object is reliably picked up instead
        # of being burned forever by the first cold-facts miss.
        fp = fingerprint(near, self.pipeline.cache)
        gated = fp == st.last_candidate_fingerprint and not result.expanded
        st.last_candidate_fingerprint = fp
        if not near or gated:
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
                passing=True,  # the user is right beside this object — introduce it, don't skip
            )
        except Exception:
            return await self._finish(st, State.ERROR, "error")

        if out.text and out.place:
            st.narration_history = (st.narration_history + [out.text])[-_HISTORY_CAP:]
            st.seen_place_ids = (st.seen_place_ids + [out.place.id])[-_SEEN_CAP:]
            st.last_place_id = out.place.id
            st.last_place = out.place
            st.last_significance = out.significance
            st.elaboration_count = 0  # fresh place — allow follow-ups again
            st.area_beats = 0  # fresh budget of connective area beats for the next lull
            st.area_bridge_said = False  # let a future lull say "пройдём дальше" again
            plan.told = (plan.told + [out.place.name])[-_TOLD_CAP:]  # arc ledger (anti-repeat)
            plan.next_hook = out.next_hook  # baton: weave this into the next paragraph
            state = State.SWITCHING if switching else State.NARRATING
            return await self._finish(
                st, state, "narration", out.text, out.place, out.significance
            )

        # Passing object yielded silence (cold facts / nothing to say). The fp is
        # facts-aware, so once warm_ahead caches its facts the gate re-opens and the
        # next tick narrates it. Carry the area spine meanwhile.
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
            return  # transient failure — retry next tick (don't advance last_geo_pos)
        if not any((addr.country, addr.city, addr.district, addr.street)):
            # Empty result (slow/uncovered geocoder): DON'T commit last_geo_pos, so the
            # next tick retries immediately instead of locking out for geocoder_min_move_m.
            # That was why early voice questions had no location until the user had walked
            # ~150 m ("ответы не учитывали геолокацию, со временем начали").
            return
        st.last_geo_pos = position
        st.address = addr
        new_key = addr.district or addr.city
        if new_key and new_key != st.area_key:
            st.area_key = new_key
            st.area_facts = None
            st.area_intro_done = False
            st.area_beats = 0
            st.area_bridge_said = False
            # fresh area => fresh story arc, but keep the user's chosen theme (if any)
            st.narrative_plan = NarrativePlan(theme_override=st.narrative_plan.theme_override)
            st.last_street = addr.street  # adopt silently; the area opener covers arrival
        elif addr.street and addr.street != st.last_street and st.area_intro_done:
            # Same district, but the user just stepped onto a NEW street. Don't reset
            # the arc — weave a smooth transition into the running monologue via the
            # next-paragraph baton ("свернув на …"), instead of a hard area intro.
            st.last_street = addr.street
            st.narrative_plan.next_hook = f"переход на улицу {addr.street}"

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
        plan.told = (plan.told + ["вступление в район"])[-_TOLD_CAP:]
        st.narration_history = (st.narration_history + [opener])[-_HISTORY_CAP:]
        return await self._finish(st, State.NARRATING, "narration", opener)

    # When nothing new is nearby, carry the story arc: advance the area outline by
    # one topic (or weave a topic the user asked about), then a couple of follow-ups
    # on the last object, then a short "пройдём дальше" bridge, and only then silence.
    async def _continue_monologue(
        self, st, heading: Heading, pace: Pace, *, expanded: bool = False
    ) -> OrchestratorOutput:
        # 1) advance the area story arc by one topic (outline, then briefly grounded
        #    connective beats — see _area_line; ungrounded filler is suppressed there)
        if self._has_area(st):
            text = await self._area_line(st, pace)
            if text:
                return await self._finish(st, State.NARRATING, "narration", text)

        # 2) fall back to telling MORE about the last object (bounded tightly)
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

        # 3) genuinely nothing to say: say one short bridge ("пройдём дальше") and then
        #    go quiet, instead of mussing the same topic in circles. One per lull.
        if self._has_area(st) and not st.area_bridge_said:
            st.area_bridge_said = True
            bridge = _BRIDGES[st.area_beats % len(_BRIDGES)]
            st.narration_history = (st.narration_history + [bridge])[-_HISTORY_CAP:]
            return await self._finish(st, State.IDLE, "narration", bridge)

        state = State.EXPANDING if expanded else State.IDLE
        return await self._finish(st, state, "silence")

    # one beat of the area story arc: pick the next topic (a user-asked focus wins,
    # else the next un-told outline topic), lazily fetch area facts, then narrate.
    async def _area_line(self, st, pace: Pace) -> str:
        plan = st.narrative_plan
        focus = plan.pending_focus[0] if plan.pending_focus else None
        topic = focus or plan.next_topic()
        # Fetch verified area facts once, up front — they both enrich the outline beats
        # and decide whether a connective beat is grounded enough to be worth saying.
        if settings.area_enrich and st.area_facts is None:
            facts = await self.pipeline.enrich_area(
                st.address, st.position, timeout_s=settings.enrich_timeout_s
            )
            st.area_facts = facts or ""  # cache "" so we don't refetch every beat
        if topic is None:
            # Outline delivered. Keep going with a connective beat ONLY when we have
            # REAL facts to ground it (and only briefly) — ungrounded generic beats are
            # the boring "по кругу" rambling. Without facts, return "" so the caller
            # bridges with "пройдём дальше" and goes quiet.
            if not st.area_facts or st.area_beats >= _MAX_AREA_BEATS:
                return ""
            topic = _CONNECTIVE_ANGLES[st.area_beats % len(_CONNECTIVE_ANGLES)]
        try:
            text, hook = await self.pipeline.narrate_area(
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
            st.area_beats += 1  # count this beat (gates the connective-beat budget)
            st.area_bridge_said = False  # real content flowed -> allow a later bridge
            if focus:
                plan.pending_focus.pop(0)  # answered/woven this user topic
            plan.told = (plan.told + [topic])[-_TOLD_CAP:]
            plan.next_hook = hook  # baton for the next paragraph
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
