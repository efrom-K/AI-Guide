"""Shared domain & transport schemas — the single source of truth for all roles.

Grouped as:
  * primitives        — GeoPoint, Address, enums
  * domain            — Place, Candidate, ControlPatch
  * role I/O          — Scorer / Narrator / Companion inputs & outputs
  * session           — SessionState
  * websocket         — client<->server message contract
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
class Significance(StrEnum):
    SKIP = "SKIP"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    LANDMARK = "LANDMARK"


class GazeConfidence(StrEnum):
    HIGH = "high"
    LOW = "low"


class Pace(StrEnum):
    STILL = "still"
    SLOW = "slow"
    FAST = "fast"


class GeoPoint(BaseModel):
    lat: float
    lon: float


class Address(BaseModel):
    country: str | None = None
    city: str | None = None
    district: str | None = None
    street: str | None = None


class Heading(BaseModel):
    direction_deg: float | None = None  # bearing 0..360; None if unknown
    gaze_confidence: GazeConfidence = GazeConfidence.LOW


# --------------------------------------------------------------------------- #
# domain
# --------------------------------------------------------------------------- #
class Place(BaseModel):
    id: str
    name: str
    category: str  # museum, park, shop, church, memorial, ...
    location: GeoPoint
    tags: dict[str, str] = Field(default_factory=dict)


class Candidate(BaseModel):
    place: Place
    distance_m: float
    type_weight: float
    in_gaze_cone: bool
    gaze_confidence: GazeConfidence
    facts_available: bool = False
    facts_snippet: str | None = None
    # Spatial side relative to heading: "ahead"/"behind" are knowable from the GPS
    # course; "left"/"right" only when gaze_confidence=high (a real facing/compass).
    # None means lateral but confidence too low to call a side.
    relative_bearing_deg: float | None = None
    side: str | None = None


class ControlPatch(BaseModel):
    """User-driven steering extracted by the Companion."""

    skip_categories: list[str] = Field(default_factory=list)
    focus_topics: list[str] = Field(default_factory=list)
    verbosity: Literal["shorter", "normal", "longer"] | None = None
    mute: bool = False


# --------------------------------------------------------------------------- #
# role I/O — Scorer
# --------------------------------------------------------------------------- #
class ScorerInput(BaseModel):
    candidates: list[Candidate]
    address: Address = Field(default_factory=Address)
    seen: list[str] = Field(default_factory=list)
    preferences: ControlPatch | None = None
    language: str = "ru"


class ScoredPlace(BaseModel):
    place_id: str
    significance: Significance
    reason: str = ""


class ScorerOutput(BaseModel):
    scored: list[ScoredPlace] = Field(default_factory=list)
    next: str | None = None
    expand_radius: bool = False


# --------------------------------------------------------------------------- #
# role I/O — Narrator
# --------------------------------------------------------------------------- #
class NarrationContext(BaseModel):
    time_of_day: str | None = None
    city: str | None = None
    district: str | None = None
    street: str | None = None


class NarratorFlags(BaseModel):
    switching: bool = False
    nothing_new: bool = False
    elaborate: bool = False  # tell MORE about an already-covered place (nothing new nearby)
    preferences: ControlPatch | None = None


class NarratorInput(BaseModel):
    place: Place
    significance: Significance
    facts: str | None = None
    distance_m: float
    heading: Heading = Field(default_factory=Heading)
    side: str | None = None  # ahead|behind|left|right (left/right only at high gaze)
    pace: Pace = Pace.SLOW
    context: NarrationContext = Field(default_factory=NarrationContext)
    history: list[str] = Field(default_factory=list)
    flags: NarratorFlags = Field(default_factory=NarratorFlags)
    # narrative arc — so the object is woven INTO the running story, not dropped in
    theme: str | None = None  # the through-line to keep the object inside
    told: list[str] = Field(default_factory=list)  # topics/places already covered (don't repeat)
    next_hook: str | None = None  # the transition the previous paragraph set up
    language: str = "ru"


# --------------------------------------------------------------------------- #
# role I/O — Area narrator (the "general -> specific" monologue spine)
# --------------------------------------------------------------------------- #
class AreaInput(BaseModel):
    """One beat of the area-level monologue: advance the story arc about the
    city / district / street, bridging the gaps between objects."""

    address: Address = Field(default_factory=Address)
    facts: str | None = None  # verified area facts (web), may be empty
    theme: str | None = None  # the through-line for this area
    topic: str | None = None  # the specific outline topic this beat should cover
    told: list[str] = Field(default_factory=list)  # covered topics/places (don't repeat)
    next_hook: str | None = None  # transition the previous paragraph set up
    last_place_name: str | None = None  # to weave a smooth return from the last object
    history: list[str] = Field(default_factory=list)
    pace: Pace = Pace.SLOW
    language: str = "ru"


# --------------------------------------------------------------------------- #
# role I/O — Planner (forms the story arc for a freshly entered area)
# --------------------------------------------------------------------------- #
class PlannerInput(BaseModel):
    address: Address = Field(default_factory=Address)
    facts: str | None = None  # verified area facts, if already fetched
    theme_override: str | None = None  # a topic the user explicitly asked for
    language: str = "ru"


class PlannerOutput(BaseModel):
    theme: str = ""  # the through-line for this area (one phrase)
    outline: list[str] = Field(default_factory=list)  # 3-5 ordered topics to cover
    opener: str = ""  # the spoken opening paragraph (introduces area + theme)


# --------------------------------------------------------------------------- #
# role I/O — Companion
# --------------------------------------------------------------------------- #
class CompanionInput(BaseModel):
    user_message: str
    context: NarrationContext = Field(default_factory=NarrationContext)
    last_narration: str | None = None
    address: Address = Field(default_factory=Address)
    history: list[str] = Field(default_factory=list)
    language: str = "ru"


class CompanionOutput(BaseModel):
    reply: str
    control_patch: ControlPatch | None = None


# --------------------------------------------------------------------------- #
# narrative plan (the story arc formed at session/area start, augmented en route)
# --------------------------------------------------------------------------- #
class NarrativePlan(BaseModel):
    area_key: str | None = None  # which area this plan was built for
    theme: str = ""  # the auto-chosen through-line for this area
    theme_override: str | None = None  # a topic the user picked (wins over `theme`)
    outline: list[str] = Field(default_factory=list)  # ordered topics to cover
    told: list[str] = Field(default_factory=list)  # covered topics/place-names (dedup)
    pending_focus: list[str] = Field(default_factory=list)  # user-asked topics to weave next
    next_hook: str | None = None  # transition note to the next paragraph

    def active_theme(self) -> str:
        return self.theme_override or self.theme

    def next_topic(self) -> str | None:
        """The first outline topic not yet covered (case-insensitive)."""
        told_lc = {t.lower() for t in self.told}
        for topic in self.outline:
            if topic.lower() not in told_lc:
                return topic
        return None


# --------------------------------------------------------------------------- #
# session
# --------------------------------------------------------------------------- #
class SessionState(BaseModel):
    session_id: str
    language: str = "ru"
    position: GeoPoint | None = None
    heading: Heading = Field(default_factory=Heading)
    pace: Pace = Pace.SLOW
    address: Address = Field(default_factory=Address)
    seen_place_ids: list[str] = Field(default_factory=list)
    narration_history: list[str] = Field(default_factory=list)
    conversation: list[str] = Field(default_factory=list)
    control_patch: ControlPatch = Field(default_factory=ControlPatch)
    current_radius_m: float = 80.0
    last_place_id: str | None = None  # last narrated place (for switching detection)
    last_place: Place | None = None  # full last place (to elaborate when nothing new)
    last_significance: Significance | None = None
    elaboration_count: int = 0  # follow-ups already told about last_place
    last_candidate_fingerprint: str | None = None  # heuristic gate
    # area-level monologue (general -> specific spine)
    last_geo_pos: GeoPoint | None = None  # where address was last resolved (move-gated)
    last_street: str | None = None  # last resolved street (a change => weave a transition)
    area_key: str | None = None  # district|city signature; change => new area, reset below
    area_facts: str | None = None  # verified facts about the current area (fetched once)
    area_intro_done: bool = False  # the area opener (+ plan) was already delivered
    area_beats: int = 0  # area beats told in the current area (variety + bound)
    # the story arc — formed when an area is entered, augmented along the route
    narrative_plan: NarrativePlan = Field(default_factory=NarrativePlan)
    state: str = "idle"  # FSM state name


# --------------------------------------------------------------------------- #
# websocket contract
# --------------------------------------------------------------------------- #
# client -> server
class WSPositionUpdate(BaseModel):
    type: Literal["position"] = "position"
    lat: float
    lon: float
    direction_deg: float | None = None
    gaze_confidence: GazeConfidence = GazeConfidence.LOW
    pace: Pace = Pace.SLOW


class WSUserUtterance(BaseModel):
    type: Literal["utterance"] = "utterance"
    text: str


class WSControl(BaseModel):
    type: Literal["control"] = "control"
    patch: ControlPatch


class WSSetLanguage(BaseModel):
    """Runtime language switch from the client (and on every (re)connect)."""

    type: Literal["language"] = "language"
    language: str  # ISO-639-1: en|ru|es|fr|de|it|pt|zh


class WSAudioInput(BaseModel):
    type: Literal["audio"] = "audio"
    data_b64: str  # recorded clip (webm/opus, wav, ...) for STT
    format: str = "webm"


class WSPlayed(BaseModel):
    """Client finished speaking the current paragraph — the cadence signal that
    tells the server's narration producer to emit the next one."""

    type: Literal["played"] = "played"


class WSSetTheme(BaseModel):
    """User picked/voiced a topic for the tour to revolve around (empty => auto)."""

    type: Literal["theme"] = "theme"
    theme: str = ""


# server -> client
class WSPlaceItem(BaseModel):
    """One discovered object for the map (lite: no facts)."""

    id: str
    name: str
    category: str
    lat: float
    lon: float


class WSPlaces(BaseModel):
    """The full set of nearby objects found in the search disc — pinned on the map
    as the user walks (distinct from the single narrated place). Pushed whenever the
    inventory disc is (re)fetched."""

    type: Literal["places"] = "places"
    items: list[WSPlaceItem] = Field(default_factory=list)


class WSNarration(BaseModel):
    type: Literal["narration"] = "narration"
    text: str
    place_id: str | None = None
    final: bool = False


class WSAudioChunk(BaseModel):
    type: Literal["audio"] = "audio"
    data_b64: str
    seq: int


class WSReply(BaseModel):
    type: Literal["reply"] = "reply"
    text: str


class WSStateUpdate(BaseModel):
    type: Literal["state"] = "state"
    state: str
