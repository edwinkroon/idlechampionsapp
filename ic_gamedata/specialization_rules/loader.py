"""Load specialization rule CSV datasets from documentation/."""

from __future__ import annotations

import csv
import re
import sys
from functools import lru_cache
from pathlib import Path

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.specialization_rules.models import (
    DataSourceVersion,
    ExceptionRule,
    LookupTables,
    Rule,
    RuleDataset,
    RuleSource,
)
from ic_gamedata.specialization_rules.provenance import classify_rule_provenance
from ic_gamedata.specialization_rules.validator import validate_rule_dataset

_V3_PRODUCTION = "champion_specialization_rules_v3.csv"
_V3_EXAMPLES = "champion_specialization_rules_v3_example_rows.csv"
_V2_FULL = "idle_champions_specialization_ruleset_v2_full.csv"

_PRIORITY_CONFIDENCE = {"critical": 5, "high": 5, "medium": 3, "low": 2, "fallback": 1}


def documentation_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "documentation"
    return Path(__file__).resolve().parent.parent.parent / "documentation"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _split_tags(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def load_lookup_tables(base: Path) -> LookupTables:
    run_goals = {row["code"].strip() for row in _read_csv_rows(base / "run_goal_lookup.csv") if row.get("code")}
    condition_fields = {
        row["code"].strip()
        for row in _read_csv_rows(base / "condition_field_lookup.csv")
        if row.get("code")
    }
    priorities = {row["code"].strip() for row in _read_csv_rows(base / "priority_lookup.csv") if row.get("code")}
    manual_review_codes = {
        row["code"].strip()
        for row in _read_csv_rows(base / "manual_review_lookup.csv")
        if row.get("code")
    }
    specialization_labels = {
        row["specialization_key"].strip(): row["display_label"].strip()
        for row in _read_csv_rows(base / "specialization_value_lookup.csv")
        if row.get("specialization_key")
    }
    tags = {row["tag"].strip() for row in _read_csv_rows(base / "tag_lookup.csv") if row.get("tag")}
    priority_scores = {
        row["code"].strip(): _parse_int(row.get("score", "")) or 0
        for row in _read_csv_rows(base / "priority_lookup.csv")
        if row.get("code")
    }
    return LookupTables(
        run_goals=frozenset(run_goals),
        condition_fields=frozenset(condition_fields),
        priorities=frozenset(priorities),
        manual_review_codes=frozenset(manual_review_codes),
        specialization_keys=frozenset(specialization_labels),
        tags=frozenset(tags),
        specialization_labels=specialization_labels,
        priority_scores=priority_scores,
    )


def _rule_from_v3_row(row: dict[str, str], *, data_source_version: DataSourceVersion) -> Rule:
    seat = _parse_int(row.get("seat", ""))
    confidence = _parse_int(row.get("default_confidence", "")) or 1
    explicit_type = (row.get("rule_source_type") or row.get("source_quality") or "").strip()
    rule_source_type = classify_rule_provenance(
        usually_choose=row.get("machine_default", ""),
        alternative=row.get("machine_alternative", ""),
        tags=_split_tags(row.get("tags", "")),
        notes_for_cursor=row.get("notes_for_cursor", ""),
        explicit_source_type=explicit_type,
    )
    return Rule(
        rule_id=row.get("rule_id", "").strip(),
        rule_version=row.get("rule_version", "v3").strip() or "v3",
        seat=seat,
        champion=row.get("champion", "").strip(),
        specialization_family=row.get("specialization_family", "").strip(),
        run_goal=row.get("run_goal", "").strip(),
        decision_context=row.get("decision_context", "").strip(),
        condition_field=row.get("condition_field", "").strip(),
        condition_operator=row.get("condition_operator", "").strip(),
        condition_value=row.get("condition_value", "").strip(),
        machine_default=row.get("machine_default", "").strip(),
        machine_alternative=row.get("machine_alternative", "").strip(),
        override_when=row.get("override_when", "").strip(),
        default_confidence=confidence,
        priority_code=row.get("priority_code", "medium").strip() or "medium",
        manual_review_code=row.get("manual_review_code", "no").strip() or "no",
        tags=_split_tags(row.get("tags", "")),
        notes_for_cursor=row.get("notes_for_cursor", "").strip(),
        advice_pattern=row.get("advice_pattern", "").strip(),
        source_basis=row.get("source_basis", "").strip(),
        active=_parse_bool(row.get("active", "true")),
        default_label=row.get("machine_default", "").strip(),
        alternative_label=row.get("machine_alternative", "").strip(),
        rule_source_type=rule_source_type,
        data_source_version=data_source_version,
    )


def _infer_v2_condition(tags: tuple[str, ...]) -> tuple[str, str, str]:
    tag_set = {tag.casefold() for tag in tags}
    if "formation-dependent" in tag_set:
        return "formation_composition", "contains", "bond_match"
    if "alignment" in tag_set:
        return "alignment", "equals", "best_alignment_count"
    if "adventure-specific" in tag_set:
        return "enemy_type", "equals", "current_enemy_type"
    if "speed" in tag_set and "farming" in tag_set:
        return "run_goal", "equals", "speed_farm"
    if "gold" in tag_set or "favor" in tag_set:
        return "run_goal", "equals", "gold_farm"
    if "survival" in tag_set or "healing" in tag_set or "tank" in tag_set:
        return "run_goal", "equals", "survival"
    return "run_goal", "equals", "generic_progression"


def _infer_v2_run_goal(tags: tuple[str, ...]) -> str:
    tag_set = {tag.casefold() for tag in tags}
    if "speed" in tag_set or "farming" in tag_set:
        return "speed_farm"
    if "gold" in tag_set or "favor" in tag_set:
        return "gold_farm"
    if "survival" in tag_set:
        return "survival"
    return "generic_progression"


def _manual_review_for_v2_full(
    *,
    rule_source_type: str,
    tags: tuple[str, ...],
    priority_code: str,
) -> str:
    if rule_source_type == "heuristic":
        return "conditional"
    tag_set = {tag.casefold() for tag in tags}
    if "formation-dependent" in tag_set or "alignment" in tag_set or "adventure-specific" in tag_set:
        return "conditional" if priority_code == "high" else "yes"
    return "no"


def _rule_from_v2_full_row(row: dict[str, str]) -> Rule | None:
    champion = (row.get("champion") or "").strip()
    usually_choose = (row.get("usually_choose") or "").strip()
    if not champion or not usually_choose:
        return None

    seat = _parse_int(row.get("seat", ""))
    alternative = (row.get("alternative") or "").strip()
    tags = _split_tags(row.get("tags", ""))
    notes = (row.get("notes_for_cursor") or "").strip()
    priority_code = (row.get("priority_for_rules") or "medium").strip().casefold() or "medium"
    rule_source_type = classify_rule_provenance(
        usually_choose=usually_choose,
        alternative=alternative,
        tags=tags,
        notes_for_cursor=notes,
        explicit_source_type=(row.get("rule_source_type") or row.get("source_quality") or "").strip(),
    )
    condition_field, condition_operator, condition_value = _infer_v2_condition(tags)
    run_goal = _infer_v2_run_goal(tags)
    confidence = _PRIORITY_CONFIDENCE.get(priority_code, 3)
    if rule_source_type == "heuristic":
        confidence = min(confidence, 3)

    rule_id = f"seat{seat:02d}_{_slug(champion)}" if seat is not None else f"v2full_{_slug(champion)}"
    return Rule(
        rule_id=rule_id,
        rule_version="v2_full",
        seat=seat,
        champion=champion,
        specialization_family=(row.get("specialization_family") or "").strip(),
        run_goal=run_goal,
        decision_context=run_goal,
        condition_field=condition_field,
        condition_operator=condition_operator,
        condition_value=condition_value,
        machine_default=usually_choose,
        machine_alternative=alternative,
        override_when=(row.get("rule_of_thumb") or "").strip(),
        default_confidence=confidence,
        priority_code=priority_code,
        manual_review_code=_manual_review_for_v2_full(
            rule_source_type=rule_source_type,
            tags=tags,
            priority_code=priority_code,
        ),
        tags=tags,
        notes_for_cursor=notes,
        advice_pattern=(row.get("rule_of_thumb") or "").strip(),
        source_basis="v2_full",
        active=True,
        default_label=usually_choose,
        alternative_label=alternative,
        rule_source_type=rule_source_type,
        data_source_version="v2_full",
    )


def _exception_from_row(row: dict[str, str]) -> ExceptionRule:
    seat = _parse_int(row.get("seat", ""))
    return ExceptionRule(
        exception_id=row.get("exception_id", "").strip(),
        champion=row.get("champion", "").strip(),
        seat=seat,
        trigger_field=row.get("trigger_field", "").strip(),
        trigger_operator=row.get("trigger_operator", "").strip(),
        trigger_value=row.get("trigger_value", "").strip(),
        forced_specialization=row.get("forced_specialization", "").strip(),
        reason=row.get("reason", "").strip(),
        manual_review_code=row.get("manual_review_code", "no").strip() or "no",
    )


def _load_v3_production_rules(base: Path) -> tuple[RuleSource, tuple[Rule, ...]]:
    production_rows = _read_csv_rows(base / _V3_PRODUCTION)
    if production_rows:
        return "v3_production", tuple(
            _rule_from_v3_row(row, data_source_version="v3_production") for row in production_rows
        )
    return "empty", ()


def _load_v2_full_rules(base: Path) -> tuple[Rule, ...]:
    rows = _read_csv_rows(base / _V2_FULL)
    if not rows:
        return ()
    mapped = [_rule_from_v2_full_row(row) for row in rows]
    return tuple(rule for rule in mapped if rule is not None)


def _load_v3_example_rules(base: Path) -> tuple[Rule, ...]:
    example_rows = _read_csv_rows(base / _V3_EXAMPLES)
    if not example_rows:
        return ()
    return tuple(_rule_from_v3_row(row, data_source_version="v3_example") for row in example_rows)


def load_documentation_rules(base: Path | None = None) -> RuleDataset:
    """Load rules with priority: V3 production > V2 full > V3 examples."""
    root = base or documentation_dir()
    lookups = load_lookup_tables(root)

    source, rules = _load_v3_production_rules(root)
    if not rules:
        v2_full_rules = _load_v2_full_rules(root)
        if v2_full_rules:
            source = "v2_full"
            rules = v2_full_rules
        else:
            example_rules = _load_v3_example_rules(root)
            if example_rules:
                source = "v3_example"
                rules = example_rules

    exceptions = tuple(_exception_from_row(row) for row in _read_csv_rows(root / "champion_exception_rules.csv"))
    dataset = RuleDataset(
        source=source,
        rules=rules,
        exceptions=exceptions,
        lookups=lookups,
    )
    dataset.validation_errors = tuple(validate_rule_dataset(dataset))
    return dataset


@lru_cache(maxsize=1)
def cached_documentation_rules() -> RuleDataset:
    return load_documentation_rules()
