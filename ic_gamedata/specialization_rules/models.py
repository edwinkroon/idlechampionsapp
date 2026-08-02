"""Datamodel for documentation-driven specialization rules (V3/V2 full)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ic_gamedata.specialization_rules.provenance import RuleSourceType

RuleSource = Literal[
    "v3_production",
    "v2_full",
    "v3_example",
    "empty",
]

DataSourceVersion = Literal[
    "v3_production",
    "v2_full",
    "v3_example",
    "empty",
]


@dataclass(frozen=True)
class LookupTables:
    run_goals: frozenset[str]
    condition_fields: frozenset[str]
    priorities: frozenset[str]
    manual_review_codes: frozenset[str]
    specialization_keys: frozenset[str]
    tags: frozenset[str]
    specialization_labels: dict[str, str]
    priority_scores: dict[str, int]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    rule_version: str
    seat: int | None
    champion: str
    specialization_family: str
    run_goal: str
    decision_context: str
    condition_field: str
    condition_operator: str
    condition_value: str
    machine_default: str
    machine_alternative: str
    override_when: str
    default_confidence: int
    priority_code: str
    manual_review_code: str
    tags: tuple[str, ...]
    notes_for_cursor: str
    advice_pattern: str
    source_basis: str
    active: bool
    # Human-facing labels from v2_full (usually_choose / alternative).
    default_label: str = ""
    alternative_label: str = ""
    # Derived or explicit provenance metadata.
    rule_source_type: RuleSourceType = "authored"
    data_source_version: DataSourceVersion = "v3_example"

    @property
    def is_v2_full(self) -> bool:
        return self.data_source_version == "v2_full"

    @property
    def is_v3_shaped(self) -> bool:
        return self.data_source_version in {"v3_production", "v3_example"}


@dataclass(frozen=True)
class ExceptionRule:
    exception_id: str
    champion: str
    seat: int | None
    trigger_field: str
    trigger_operator: str
    trigger_value: str
    forced_specialization: str
    reason: str
    manual_review_code: str


@dataclass
class RuleDataset:
    source: RuleSource
    rules: tuple[Rule, ...]
    exceptions: tuple[ExceptionRule, ...]
    lookups: LookupTables
    validation_errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_usable(self) -> bool:
        return bool(self.rules)

    @property
    def data_source_version(self) -> DataSourceVersion:
        return self.source if self.source != "empty" else "empty"

    @property
    def using_v2_fallback(self) -> bool:
        """Backward-compatible alias for legacy callers."""
        return self.source == "v2_full"


@dataclass(frozen=True)
class EvaluationContext:
    hero_id: int
    hero_name: str
    seat: int | None
    run_goal: str
    active_hero_ids: frozenset[int]
    seat_by_hero: dict[int, int]
    highest_damage_hero_id: int | None
    familiar_count: int
    evil_count: int
    good_count: int
    neutral_count: int
    magic_count: int
    melee_count: int
    dwarf_elf_count: int
    enemy_type: str | None
    adventure_name: str | None
    alignment_distribution_changed: bool = False
    enemy_type_changed: bool = False
    secondary_bond_outscores_primary: bool = False
    survival_blocks_progress: bool = False


@dataclass(frozen=True)
class AdviceResult:
    champion: str
    seat: int | None
    specialization_key: str
    upgrade_id: int | None
    rule_id: str | None
    exception_id: str | None
    rationale: str
    condition_used: str
    manual_review: str
    confidence: int
    source: RuleSource
    priority_code: str
    data_source_version: DataSourceVersion = "empty"
    rule_source_type: RuleSourceType = "authored"
    chosen_label: str = ""

    def rule_source_label(self) -> str:
        provenance = f", {self.rule_source_type}" if self.rule_source_type else ""
        version = self.data_source_version or self.source
        if self.exception_id:
            return f"csv-exception ({self.exception_id}, {version}{provenance})"
        if self.rule_id:
            return f"csv-regel ({self.rule_id}, {version}{provenance})"
        return f"csv-regel ({version}{provenance})"
