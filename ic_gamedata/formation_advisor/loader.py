"""Load formation placement rules CSV."""

from __future__ import annotations

import csv
import sys
from functools import lru_cache
from pathlib import Path

from ic_gamedata.formation_advisor.models import (
    PlacementRule,
    RuleDataset,
)

_RULES_FILE = "formation_placement_rules_v1.csv"
_PRIORITY_SCORES = {"critical": 1, "high": 2, "medium": 3, "low": 4, "fallback": 5}


def documentation_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "documentation"
    return Path(__file__).resolve().parent.parent.parent / "documentation"


def _split_pipe(value: str) -> frozenset[str]:
    parts = [part.strip().casefold() for part in value.split("|") if part.strip()]
    return frozenset(parts)


@lru_cache(maxsize=1)
def cached_formation_rules() -> RuleDataset:
    path = documentation_dir() / _RULES_FILE
    if not path.is_file():
        return RuleDataset(rules=())
    rules: list[PlacementRule] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            tip_type = str(row.get("tip_type") or "warning").strip().casefold()
            if tip_type not in ("placement", "swap", "bench", "warning"):
                tip_type = "warning"
            source = str(row.get("rule_source_type") or "heuristic").strip().casefold()
            if source not in ("authored", "heuristic", "handler"):
                source = "heuristic"
            priority_raw = str(row.get("priority") or "medium").strip().casefold()
            if priority_raw.isdigit():
                priority = int(priority_raw)
            else:
                priority = _PRIORITY_SCORES.get(priority_raw, 3)
            rules.append(
                PlacementRule(
                    rule_id=str(row.get("rule_id") or "").strip(),
                    champion=str(row.get("champion") or "").strip(),
                    role=str(row.get("role") or "").strip().casefold(),
                    tag=str(row.get("tag") or "").strip().casefold(),
                    run_goal=str(row.get("run_goal") or "*").strip().casefold(),
                    context=str(row.get("context") or "*").strip().casefold(),
                    condition_field=str(row.get("condition_field") or "").strip().casefold(),
                    condition_operator=str(row.get("condition_operator") or "").strip().casefold(),
                    condition_value=str(row.get("condition_value") or "").strip().casefold(),
                    tip_type=tip_type,  # type: ignore[arg-type]
                    headline=str(row.get("headline") or "").strip(),
                    detail=str(row.get("detail") or "").strip(),
                    priority=priority,
                    rule_source_type=source,  # type: ignore[arg-type]
                )
            )
    return RuleDataset(rules=tuple(rules))


def rule_matches_goal(rule: PlacementRule, run_goal: str) -> bool:
    if rule.run_goal in ("*", ""):
        return True
    return run_goal.casefold() in _split_pipe(rule.run_goal)


def rule_matches_context(rule: PlacementRule, context: str) -> bool:
    if rule.context in ("*", ""):
        return True
    return context.casefold() in _split_pipe(rule.context) or rule.context == context.casefold()
