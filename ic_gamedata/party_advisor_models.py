"""Shared party-advisor types and report dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

GoalMode = Literal["bud", "gold", "speed"]
ContextMode = Literal["campaign", "events", "push", "modron"]

GOAL_LABELS: dict[str, str] = {
    "bud": "BUD / damage",
    "gold": "Gold income",
    "speed": "Speed / areas",
}


def goal_label(goal: GoalMode) -> str:
    return GOAL_LABELS.get(goal, goal)


@dataclass(frozen=True)
class FormationHero:
    hero_id: int
    name: str
    seat: int | None
    level: int
    gear_score: float
    ilvl: int
    ilvl_pct_vs_avg: float
    gear_rank: int
    gear_rank_total: int
    gear_pct_of_best: float
    gear_label: str
    role_label: str
    roles: tuple[str, ...]
    tags: tuple[str, ...]
    highest_damage: float
    active_feats: int
    is_top_damage: bool


@dataclass(frozen=True)
class HeroImprovement:
    priority: int
    hero_name: str | None
    seat: int | None
    headline: str
    action: str


@dataclass(frozen=True)
class AdvisorTip:
    priority: int
    title: str
    detail: str


@dataclass(frozen=True)
class AdvisorReport:
    goal: GoalMode
    context: ContextMode
    adventure_name: str
    adventure_id: int | None
    gold_growth_rate: float | None
    adventure_buff_note: str | None
    main_dps_name: str | None
    formation_heroes: tuple[FormationHero, ...]
    improvements: tuple[HeroImprovement, ...]
    tips: tuple[AdvisorTip, ...]
    summary: str
    specialization_insights: tuple[Any, ...] = ()
    adventure_restrictions_note: str | None = None
    formation_insights: tuple[Any, ...] = ()
    seat_report: Any | None = None
