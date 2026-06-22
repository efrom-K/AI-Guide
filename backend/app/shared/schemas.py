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


class NarratorFlags(BaseModel):
    switching: bool = False
    nothing_new: bool = False
    preferences: ControlPatch | None = None


class NarratorInput(BaseModel):
    place: Place
    significance: Significance
    facts: str | None = None
    distance_m: float
    heading: Heading = Field(default_factory=Heading)
    pace: Pace = Pace.SLOW
    context: NarrationContext = Field(default_factory=NarrationContext)
    history: list[str] = Field(default_factory=list)
    flags: NarratorFlags = Field(default_factory=NarratorFlags)
    language: str = "ru"


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
    last_candidate_fingerprint: str | None = None  # heuristic gate
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


class WSAudioInput(BaseModel):
    type: Literal["audio"] = "audio"
    data_b64: str  # recorded clip (webm/opus, wav, ...) for STT
    format: str = "webm"


# server -> client
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
