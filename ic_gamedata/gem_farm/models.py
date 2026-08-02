"""Dataclasses for gem farm health, config, and events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

HealthSeverity = Literal["info", "warning", "critical"]
HealthLevel = Literal["ok", "warning", "critical"]


@dataclass(frozen=True)
class FarmHealthThresholds:
    enabled: bool = True
    run_slowdown_pct: float = 115.0
    gem_drop_pct: float = 85.0
    area_stall_sec: float = 180.0
    gem_drop_min_sec: float = 600.0


@dataclass(frozen=True)
class CopilotSettings:
    send_keys_enabled: bool = False
    advise_only: bool = True
    allow_formation_q: bool = False
    allow_formation_w: bool = False
    allow_formation_e: bool = False
    allow_auto_progress_g: bool = False


@dataclass(frozen=True)
class BrivGearOverride:
    enchant: int | None = None
    rarity: int | None = None
    gild: int | None = None


@dataclass(frozen=True)
class BrivGear:
    hero_id: int
    slot_id: int
    enchant: int
    item_level: int
    item_level_label: str
    rarity: int
    rarity_label: str
    gild: int
    gild_label: str
    source: str


@dataclass(frozen=True)
class BrivZoneAdvice:
    modron_goal: int
    reset_zone: int
    stack_zone_min: int
    stack_zone_max: int
    stack_zone_recommended: int
    stack_target: int | None
    explanation: str


CopilotPhase = Literal[
    "idle",
    "progress",
    "stacking",
    "swap_ready",
    "pre_reset",
    "stuck",
]


@dataclass(frozen=True)
class CopilotAdvice:
    phase: CopilotPhase
    headline: str
    detail: str
    formation_hint: str | None = None


@dataclass(frozen=True)
class FormationHotkeySlot:
    hotkey: str
    save_id: int | None = None
    save_name: str | None = None
    champion_names: tuple[str, ...] = ()
    briv_in_save: bool = False


@dataclass(frozen=True)
class FormationHotkeys:
    party_index: int
    slots: tuple[FormationHotkeySlot, ...]
    source: str = "none"


@dataclass(frozen=True)
class GemFarmSnapshot:
    party_index: int
    monitoring: bool
    health: FarmHealthStatus
    briv_gear: BrivGear | None
    zone_advice: BrivZoneAdvice | None
    copilot: CopilotAdvice | None
    formation_hotkeys: FormationHotkeys | None = None
    briv_stacks: int | None = None
    briv_steelbones_stacks: int | None = None
    gems_per_quarter: float | None = None
    current_area: int | None = None


@dataclass(frozen=True)
class FarmProfile:
    enabled: bool = True
    stack_zone: int | None = None
    reset_zone: int | None = None
    stack_target_stacks: int | None = None
    briv_gear_override: BrivGearOverride | None = None
    formation_q_name: str | None = None
    formation_w_name: str | None = None
    formation_e_name: str | None = None
    copilot: CopilotSettings = field(default_factory=CopilotSettings)


@dataclass(frozen=True)
class GemFarmConfig:
    profiles: dict[int, FarmProfile] = field(default_factory=dict)
    health: FarmHealthThresholds = field(default_factory=FarmHealthThresholds)


@dataclass(frozen=True)
class FarmHealthAlert:
    rule_id: str
    severity: HealthSeverity
    message: str
    detail: str = ""


@dataclass(frozen=True)
class FarmHealthStatus:
    party_index: int
    level: HealthLevel
    monitoring: bool
    alerts: tuple[FarmHealthAlert, ...] = ()


@dataclass(frozen=True)
class FarmEvent:
    timestamp: float
    party_index: int
    kind: str
    rule_id: str
    severity: HealthSeverity
    message: str
    detail: str = ""


@dataclass(frozen=True)
class HealthEvaluationInput:
    party_index: int
    is_active: bool
    modron_goal: int | None
    briv_in_formation: bool
    current_area: int | None
    gems_per_quarter: float | None
    rate_window_sec: float | None
    goal_run_history: tuple
    area_unchanged_sec: float | None
    gem_below_threshold_sec: float | None
    now: float
