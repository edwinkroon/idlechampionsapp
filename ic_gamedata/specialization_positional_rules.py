"""Declarative formation + goal specialization rules."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ic_gamedata.specialization_advisor_model import normalize_goal_lane
from ic_gamedata.specialization_formation import (
    adjacent_role_count,
    bud_column_relation,
    bud_is_adjacent,
    bud_shares_column,
    column_of_hero,
    heroes_in_column,
    is_back_seat,
    is_front_seat,
)

if TYPE_CHECKING:
    from ic_gamedata.specialization_engine import FormationContext


def _config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "specialization_positional_rules.json"
    return Path(__file__).resolve().parent.parent / "config" / "specialization_positional_rules.json"


@dataclass(frozen=True)
class PositionalRule:
    when: str
    choice_ids: tuple[int, ...]
    reason: str
    goals: frozenset[str] | None = None
    n: int | None = None
    role: str | None = None


@dataclass(frozen=True)
class PositionalHeroRules:
    hero_id: int
    name: str
    rules: tuple[PositionalRule, ...]
    default_ids: tuple[int, ...]
    default_reason: str
    # When set, only fill this tier; caller merges with other tiers (e.g. Regis).
    tier: int | None = None


def _parse_ids(raw: Any) -> tuple[int, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(out)


def _parse_rule(raw: dict[str, Any]) -> PositionalRule | None:
    when = str(raw.get("when") or "").strip()
    choice_ids = _parse_ids(raw.get("choice_ids"))
    reason = str(raw.get("reason") or "").strip()
    if not when or not choice_ids or not reason:
        return None
    goals_raw = raw.get("goals")
    goals: frozenset[str] | None = None
    if isinstance(goals_raw, list):
        lanes = {normalize_goal_lane(str(g)) for g in goals_raw}
        goals = frozenset(g for g in lanes if g is not None)
        if not goals:
            goals = None
    n_raw = raw.get("n")
    n: int | None
    try:
        n = int(n_raw) if n_raw is not None else None
    except (TypeError, ValueError):
        n = None
    role_raw = raw.get("role")
    role = str(role_raw).strip() if role_raw else None
    return PositionalRule(
        when=when,
        choice_ids=choice_ids,
        reason=reason,
        goals=goals,
        n=n,
        role=role or None,
    )


def _parse_hero(raw: dict[str, Any]) -> PositionalHeroRules | None:
    try:
        hero_id = int(raw["hero_id"])
        name = str(raw.get("name") or hero_id)
    except (KeyError, TypeError, ValueError):
        return None
    rules: list[PositionalRule] = []
    for item in raw.get("rules") or []:
        if not isinstance(item, dict):
            continue
        parsed = _parse_rule(item)
        if parsed is not None:
            rules.append(parsed)
    if not rules and not _parse_ids(raw.get("default_ids")):
        return None
    tier_raw = raw.get("tier")
    try:
        tier = int(tier_raw) if tier_raw is not None else None
    except (TypeError, ValueError):
        tier = None
    return PositionalHeroRules(
        hero_id=hero_id,
        name=name,
        rules=tuple(rules),
        default_ids=_parse_ids(raw.get("default_ids")),
        default_reason=str(raw.get("default_reason") or "positional default"),
        tier=tier,
    )


@lru_cache(maxsize=1)
def load_positional_rules() -> dict[int, PositionalHeroRules]:
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    heroes = data.get("heroes") if isinstance(data, dict) else None
    if not isinstance(heroes, dict):
        return {}
    out: dict[int, PositionalHeroRules] = {}
    for raw in heroes.values():
        if not isinstance(raw, dict):
            continue
        model = _parse_hero(raw)
        if model is not None:
            out[model.hero_id] = model
    return out


def clear_positional_rules_cache() -> None:
    load_positional_rules.cache_clear()


def _rule_matches(rule: PositionalRule, ctx: FormationContext, hero_id: int) -> bool:
    lane = normalize_goal_lane(ctx.run_goal)
    if rule.goals is not None:
        # No known lane → only match rules that cover all goals (omit goals) —
        # here goals is set, so require a concrete matching lane.
        if lane is None or lane not in rule.goals:
            return False

    when = rule.when
    if when == "always":
        return True
    if when == "bud_same_column":
        return bud_shares_column(
            hero_id,
            seat_by_hero=ctx.seat_by_hero,
            bud_hero_id=ctx.bud_hero_id,
            highest_damage_hero_id=ctx.highest_damage_hero_id,
        )
    if when == "not_bud_same_column":
        if not ctx.seat_by_hero or hero_id not in ctx.seat_by_hero:
            return False
        focus = ctx.bud_hero_id or ctx.highest_damage_hero_id
        if focus is None or focus not in ctx.seat_by_hero:
            return False
        return not bud_shares_column(
            hero_id,
            seat_by_hero=ctx.seat_by_hero,
            bud_hero_id=ctx.bud_hero_id,
            highest_damage_hero_id=ctx.highest_damage_hero_id,
        )
    if when == "bud_adjacent":
        return bud_is_adjacent(
            hero_id,
            seat_by_hero=ctx.seat_by_hero,
            bud_hero_id=ctx.bud_hero_id,
            highest_damage_hero_id=ctx.highest_damage_hero_id,
            active_hero_ids=ctx.active_hero_ids,
        )
    if when == "bud_column_ahead":
        return (
            bud_column_relation(
                hero_id,
                seat_by_hero=ctx.seat_by_hero,
                bud_hero_id=ctx.bud_hero_id,
                highest_damage_hero_id=ctx.highest_damage_hero_id,
            )
            == "ahead"
        )
    if when == "bud_column_behind":
        return (
            bud_column_relation(
                hero_id,
                seat_by_hero=ctx.seat_by_hero,
                bud_hero_id=ctx.bud_hero_id,
                highest_damage_hero_id=ctx.highest_damage_hero_id,
            )
            == "behind"
        )
    if when == "is_front_seat":
        seat = ctx.seat_by_hero.get(hero_id) if ctx.seat_by_hero else None
        return seat is not None and is_front_seat(seat)
    if when == "is_back_seat":
        seat = ctx.seat_by_hero.get(hero_id) if ctx.seat_by_hero else None
        return seat is not None and is_back_seat(seat)
    if when == "column_count_lte":
        if rule.n is None or not ctx.seat_by_hero:
            return False
        col = column_of_hero(hero_id, ctx.seat_by_hero)
        if col is None:
            return False
        count = len(
            heroes_in_column(
                col,
                active_hero_ids=ctx.active_hero_ids,
                seat_by_hero=ctx.seat_by_hero,
            )
        )
        return count <= rule.n
    if when == "column_count_gt":
        if rule.n is None or not ctx.seat_by_hero:
            return False
        col = column_of_hero(hero_id, ctx.seat_by_hero)
        if col is None:
            return False
        count = len(
            heroes_in_column(
                col,
                active_hero_ids=ctx.active_hero_ids,
                seat_by_hero=ctx.seat_by_hero,
            )
        )
        return count > rule.n
    if when == "adjacent_role_count_gte":
        if rule.n is None or not rule.role:
            return False
        return (
            adjacent_role_count(
                hero_id,
                role=rule.role,
                active_hero_ids=ctx.active_hero_ids,
                seat_by_hero=ctx.seat_by_hero,
            )
            >= rule.n
        )
    return False


def evaluate_positional_rules(
    hero_id: int,
    ctx: FormationContext,
) -> tuple[list[int], str] | None:
    """Evaluate declarative rules for a hero.

    Returns full choice lists for complete heroes. For tier-scoped heroes
    (``tier`` set), returns only that tier's ids — callers must merge.
    """
    model = load_positional_rules().get(hero_id)
    if model is None:
        return None

    if not ctx.seat_by_hero or hero_id not in ctx.seat_by_hero:
        if model.default_ids:
            return list(model.default_ids), model.default_reason
        return None

    for rule in model.rules:
        if _rule_matches(rule, ctx, hero_id):
            return list(rule.choice_ids), f"formation rule ({rule.reason})"

    if model.default_ids:
        return list(model.default_ids), model.default_reason
    return None


def positional_tier_for_hero(hero_id: int) -> int | None:
    model = load_positional_rules().get(hero_id)
    if model is None:
        return None
    return model.tier
