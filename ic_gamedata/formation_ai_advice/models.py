"""Typed models for formation advice (clipboard/chat workflow)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SCHEMA_VERSION = "1.9"

# User-facing export goals (legacy push_damage/speed accepted only via adapters).
AdviceObjective = Literal[
    "push",
    "quest_clear",
    "gem_farm",
    "gold_farm",
    "favor_farm",
    "custom_task",
    "push_damage",  # legacy
    "speed",  # legacy
]
AdviceStatus = Literal["proposal", "needs_information", "no_valid_proposal"]
ExportReadiness = Literal["ready", "ready_with_warnings", "blocked"]
LocalValidationStatus = Literal[
    "valid",
    "invalid",
    "stale",
    "needs_information",
    "unchecked",
]


@dataclass(frozen=True)
class AdviceSource:
    source_id: str
    title: str
    url: str | None = None
    snippet: str | None = None


@dataclass(frozen=True)
class SpecializationChoice:
    group_id: str
    option_id: int
    reason: str = ""


@dataclass(frozen=True)
class AssignmentProposal:
    position_id: int
    champion_id: int
    specialization_choices: tuple[SpecializationChoice, ...] = ()
    placement_reason: str = ""


@dataclass(frozen=True)
class ExpectedKeyBuff:
    source_champion_id: int
    target_champion_id: int
    explanation: str
    ability_id: int | None = None
    locally_checked: bool = False


@dataclass(frozen=True)
class FormationAdviceProposal:
    schema_version: str
    request_id: str
    status: AdviceStatus
    summary: str
    assignments: tuple[AssignmentProposal, ...] = ()
    expected_key_buffs: tuple[ExpectedKeyBuff, ...] = ()
    assumptions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    sources: tuple[AdviceSource, ...] = ()


@dataclass(frozen=True)
class LocalValidationResult:
    status: LocalValidationStatus
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    unchecked_mechanics: tuple[str, ...] = ()
    can_apply: bool = False


@dataclass(frozen=True)
class FormationAdviceResult:
    """Result after parse + local validation (chat status ≠ local status)."""

    request_id: str
    request_fingerprint: str
    data_version: str | None
    requested_at: str
    objective: AdviceObjective
    main_dps_id: int | None
    proposal: FormationAdviceProposal | None
    local_validation: LocalValidationResult
    sources: tuple[AdviceSource, ...] = ()
    error: str | None = None
    specializations_advice_only: bool = True
    provider_label: str = "Clipboard / chat-voorstel"


@dataclass(frozen=True)
class AppliedFormationSnapshot:
    """Undo snapshot for in-app formation overlay (does not touch the game)."""

    seat_by_hero: dict[int, int]
    specialization_advice: dict[int, tuple[SpecializationChoice, ...]]
    label: str = ""
