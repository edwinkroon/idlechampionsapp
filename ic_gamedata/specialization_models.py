"""Dataclasses for specialization advice."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecializationOption:
    upgrade_id: int
    name: str
    required_level: int
    tier_index: int


@dataclass(frozen=True)
class PendingSpecialization:
    hero_id: int
    hero_name: str
    seat: int | None
    game_instance_id: int | None
    current_choices: tuple[int, ...]
    options: tuple[SpecializationOption, ...]
    desired_upgrade_id: int | None
    desired_option_index: int | None
    reason: str
    rationale: str
    advice_source: str = ""
    confidence: int = 0
    manual_review: str = "no"
    condition_used: str = ""
    data_source_version: str = ""
    rule_source_type: str = ""
