"""Datamodel for seat-centric party advisor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ic_gamedata.feat_status import FeatRecommendation

SeatRole = Literal[
    "tank",
    "bud",
    "buffer",
    "debuffer",
    "support",
    "healer",
    "gold",
    "modron",
    "speed",
    "flex",
]

STANDARD_SEAT_ROLES: tuple[SeatRole, ...] = (
    "tank",
    "bud",
    "buffer",
    "debuffer",
    "support",
    "healer",
    "gold",
    "modron",
    "speed",
    "flex",
)


@dataclass(frozen=True)
class BenchCandidate:
    hero_id: int
    hero_name: str
    reason: str
    score: float


@dataclass(frozen=True)
class SeatInsightLine:
    source: str
    headline: str
    detail: str
    priority: int


@dataclass(frozen=True)
class SeatReport:
    seat: int
    zone: str
    hero_id: int
    hero_name: str
    gear_label: str
    inferred_role: SeatRole
    chosen_role: SeatRole | None
    effective_role: SeatRole
    role_mismatch: bool
    priority: int
    relevance_reason: str
    insights: tuple[SeatInsightLine, ...]
    bench_alternatives: tuple[BenchCandidate, ...]
    best_spec: str | None
    current_specs: tuple[str, ...]
    recommended_feats: tuple[FeatRecommendation, ...]
    formation_advice: str
    advice_source: str
    advice_source_url: str = ""
    advice_wiki_url: str = ""
    guide_default_spec: str | None = None
    is_bud: bool = False
    is_speed_focus: bool = False
    spec_status: str | None = None


@dataclass(frozen=True)
class VisualSeatNode:
    seat: int
    x: float
    y: float
    zone: str
    hero_id: int | None
    hero_name: str | None
    effective_role: SeatRole | None
    inferred_role: SeatRole | None
    chosen_role: SeatRole | None
    is_bud: bool
    has_issue: bool
    is_active: bool


@dataclass(frozen=True)
class SeatAdvisorReport:
    bud_hero_id: int | None
    bud_hero_name: str | None
    seats: tuple[SeatReport, ...]
    visual_nodes: tuple[VisualSeatNode, ...]
    formation_name: str
    html_grid: str
    speed_hero_id: int | None = None
    speed_hero_name: str | None = None
