"""Declarative BUD-relative champion placement rules → FormationInsight."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ic_gamedata.formation_advisor.bud_gate import (
    append_proxy_ratio,
    best_swap_to_carry,
)
from ic_gamedata.formation_advisor.models import FormationInsight, FormationLayoutContext
from ic_gamedata.formation_advisor.topology import fallback_seat_column
from ic_gamedata.specialization_advisor_model import normalize_goal_lane
from ic_gamedata.specialization_custom_stacks import (
    seat_graph_distance,
    shadowheart_duplicate_hero,
    shadowheart_duplicity_distance,
)
from ic_gamedata.specialization_data import hero_ability_scores_map_from_cached_definitions


def _config_path() -> Path:
    if getattr(sys, "frozen", False):
        return (
            Path(sys.executable).resolve().parent
            / "config"
            / "formation_champion_placement_rules.json"
        )
    return (
        Path(__file__).resolve().parent.parent.parent
        / "config"
        / "formation_champion_placement_rules.json"
    )


@dataclass(frozen=True)
class PlacementPreference:
    hero_id: int | None
    name: str
    bud_relation: str | None = None
    prefer_column: int | None = None
    avoid_adjacent_role: str | None = None
    prefer_adjacent_role: str | None = None
    n: int | None = None
    priority: int = 3
    headline: str = ""
    detail: str = ""
    goals: frozenset[str] | None = None
    source: str = "hero"
    also: tuple["PlacementPreference", ...] = ()


def _parse_int(raw: Any) -> int | None:
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _parse_pref(
    raw: dict[str, Any],
    *,
    hero_id: int | None,
    name: str,
    source: str,
) -> PlacementPreference | None:
    bud_relation = str(raw.get("bud_relation") or "").strip() or None
    prefer_column = _parse_int(raw.get("prefer_column"))
    avoid = str(raw.get("avoid_adjacent_role") or "").strip() or None
    prefer_role = str(raw.get("prefer_adjacent_role") or "").strip() or None
    when = str(raw.get("when") or "").strip() or None
    # "also" items may use when= instead of bud_relation
    if when and not bud_relation:
        bud_relation = when
    if (
        not bud_relation
        and prefer_column is None
        and not avoid
        and not prefer_role
    ):
        return None
    goals_raw = raw.get("goals")
    goals: frozenset[str] | None = None
    if isinstance(goals_raw, list):
        lanes = {normalize_goal_lane(str(g)) for g in goals_raw}
        goals = frozenset(g for g in lanes if g is not None) or None
    also_raw = raw.get("also") if isinstance(raw.get("also"), list) else []
    also: list[PlacementPreference] = []
    for item in also_raw:
        if not isinstance(item, dict):
            continue
        child = _parse_pref(item, hero_id=hero_id, name=name, source=source)
        if child is not None:
            also.append(child)
    return PlacementPreference(
        hero_id=hero_id,
        name=name,
        bud_relation=bud_relation,
        prefer_column=prefer_column,
        avoid_adjacent_role=avoid,
        prefer_adjacent_role=prefer_role,
        n=_parse_int(raw.get("n")),
        priority=int(raw.get("priority") or 3),
        headline=str(raw.get("headline") or ""),
        detail=str(raw.get("detail") or ""),
        goals=goals,
        source=source,
        also=tuple(also),
    )


@lru_cache(maxsize=1)
def load_champion_placement_config() -> dict[str, Any]:
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def clear_champion_placement_cache() -> None:
    load_champion_placement_config.cache_clear()


def _hero_overrides() -> dict[int, PlacementPreference]:
    data = load_champion_placement_config()
    heroes = data.get("heroes") if isinstance(data.get("heroes"), dict) else {}
    out: dict[int, PlacementPreference] = {}
    for key, raw in heroes.items():
        if not isinstance(raw, dict):
            continue
        hero_id = _parse_int(key) or _parse_int(raw.get("hero_id"))
        if hero_id is None:
            continue
        name = str(raw.get("name") or hero_id)
        pref = _parse_pref(raw, hero_id=hero_id, name=name, source="hero")
        if pref is not None:
            out[hero_id] = pref
    return out


def _default_prefs_for_hero(ctx: FormationLayoutContext, hero_id: int) -> list[PlacementPreference]:
    data = load_champion_placement_config()
    defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    by_tag = defaults.get("by_tag") if isinstance(defaults.get("by_tag"), dict) else {}
    by_role = defaults.get("by_role") if isinstance(defaults.get("by_role"), dict) else {}
    out: list[PlacementPreference] = []
    name = ctx.name(hero_id)
    for tag in ctx.tags(hero_id):
        raw = by_tag.get(tag)
        if isinstance(raw, dict):
            pref = _parse_pref(raw, hero_id=hero_id, name=name, source=f"tag:{tag}")
            if pref is not None:
                out.append(pref)
    for role in ctx.roles(hero_id):
        raw = by_role.get(role)
        if isinstance(raw, dict):
            pref = _parse_pref(raw, hero_id=hero_id, name=name, source=f"role:{role}")
            if pref is not None:
                out.append(pref)
    return out


def _column(ctx: FormationLayoutContext, seat: int) -> int:
    return ctx.topology.seat_column.get(seat, fallback_seat_column(seat))


def _farthest_column_from(ctx: FormationLayoutContext, hero_seat: int) -> int:
    hero_col = _column(ctx, hero_seat)
    cols = set(ctx.topology.seat_column.values()) or {hero_col}
    return max(cols, key=lambda c: abs(c - hero_col))


def _adjacent_occupied_count(ctx: FormationLayoutContext, hero_id: int) -> int:
    seat = ctx.seat_of(hero_id)
    if seat is None:
        return 0
    return sum(1 for n in ctx.adjacent_seats(seat) if ctx.hero_at_seat(n) is not None)


def _formation_column_count(ctx: FormationLayoutContext) -> int:
    cols = set(ctx.topology.seat_column.values())
    return len(cols) if cols else 1


def _hew_teamwork_x(ctx: FormationLayoutContext) -> int:
    """Hew Maan Teamwork: X=1 for ≤4 columns, else X=2."""
    return 1 if _formation_column_count(ctx) <= 4 else 2


def _format_text(
    template: str,
    *,
    ctx: FormationLayoutContext,
    hero_id: int,
    carry_id: int | None,
    extra: dict[str, Any] | None = None,
) -> str:
    seat = ctx.seat_of(hero_id)
    carry_seat = ctx.seat_of(carry_id) if carry_id is not None else None
    values: dict[str, Any] = {
        "hero": ctx.name(hero_id),
        "seat": seat if seat is not None else "?",
        "zone": ctx.zone_of_seat(seat) if seat is not None else "?",
        "hero_col": _column(ctx, seat) if seat is not None else "?",
        "carry": ctx.name(carry_id) if carry_id is not None else "BUD",
        "carry_seat": carry_seat if carry_seat is not None else "?",
        "carry_col": _column(ctx, carry_seat) if carry_seat is not None else "?",
        "carry_zone": (
            ctx.zone_of_seat(carry_seat) if carry_seat is not None else "?"
        ),
        "adjacent_count": _adjacent_occupied_count(ctx, hero_id),
        "distance": "?",
        "farthest_col": "?",
        "column_distance": "?",
        "teamwork_x": _hew_teamwork_x(ctx),
        "formation_columns": _formation_column_count(ctx),
    }
    if seat is not None:
        values["farthest_col"] = _farthest_column_from(ctx, seat)
    if seat is not None and carry_seat is not None:
        values["distance"] = seat_graph_distance(
            seat, carry_seat, dict(ctx.topology.seat_adjacency)
        )
        values["column_distance"] = abs(_column(ctx, seat) - _column(ctx, carry_seat))
    # Shadowheart duplicate labels (best-effort; safe if scores missing).
    try:
        scores = hero_ability_scores_map_from_cached_definitions()
        dup = shadowheart_duplicate_hero(set(ctx.active_hero_ids), dict(ctx.seat_by_hero), scores)
        if dup is not None:
            values["dex_hero"] = ctx.name(dup)
            values["dex_distance"] = shadowheart_duplicity_distance(
                set(ctx.active_hero_ids),
                dict(ctx.seat_by_hero),
                scores,
                adjacency=dict(ctx.topology.seat_adjacency),
            )
    except Exception:
        values.setdefault("dex_hero", "highest-DEX champion")
        values.setdefault("dex_distance", "?")
    if extra:
        values.update(extra)
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


def _goal_ok(pref: PlacementPreference, ctx: FormationLayoutContext) -> bool:
    if pref.goals is None:
        return True
    lane = normalize_goal_lane(ctx.run_goal) or normalize_goal_lane(ctx.goal)
    return lane is not None and lane in pref.goals


def _relation_violated(
    pref: PlacementPreference,
    ctx: FormationLayoutContext,
    hero_id: int,
    carry_id: int,
) -> bool:
    seat = ctx.seat_of(hero_id)
    carry_seat = ctx.seat_of(carry_id)
    if seat is None:
        return False
    relation = pref.bud_relation or ""

    if relation == "adjacent":
        return not ctx.is_adjacent(hero_id, carry_id)
    if relation == "not_adjacent":
        return ctx.is_adjacent(hero_id, carry_id)
    if relation == "adjacent_behind":
        # Trixie-style: BUD in an adjacent seat in a rear-er column.
        if carry_seat is None:
            return False
        if not ctx.is_adjacent(hero_id, carry_id):
            return True
        return not (_column(ctx, seat) < _column(ctx, carry_seat))
    if relation == "adjacent_column":
        # Baeloth-style: BUD in the column immediately ahead or behind.
        if carry_seat is None:
            return False
        return abs(_column(ctx, seat) - _column(ctx, carry_seat)) != 1
    if relation == "same_or_one_behind":
        # Karlach-style: BUD in own column or the single column behind.
        if carry_seat is None:
            return False
        hero_col = _column(ctx, seat)
        carry_col = _column(ctx, carry_seat)
        return carry_col not in {hero_col, hero_col + 1}
    if relation == "hew_teamwork":
        if carry_seat is None:
            return False
        max_cols = _hew_teamwork_x(ctx)
        return abs(_column(ctx, seat) - _column(ctx, carry_seat)) > max_cols
    if relation == "not_edge":
        return ctx.zone_of_seat(seat) in {"front", "back"}
    if relation == "same_column":
        if carry_seat is None:
            return False
        return _column(ctx, seat) != _column(ctx, carry_seat)
    if relation == "ahead":
        if carry_seat is None:
            return False
        return not (_column(ctx, seat) < _column(ctx, carry_seat))
    if relation == "behind":
        if carry_seat is None:
            return False
        return not (_column(ctx, seat) > _column(ctx, carry_seat))
    if relation == "farthest":
        if carry_seat is None:
            return False
        return _column(ctx, carry_seat) != _farthest_column_from(ctx, seat)
    if relation == "front":
        return ctx.zone_of_seat(seat) != "front"
    if relation == "back":
        return ctx.zone_of_seat(seat) != "back"
    if relation == "graph_distance_gte":
        if carry_seat is None or pref.n is None:
            return False
        dist = seat_graph_distance(seat, carry_seat, dict(ctx.topology.seat_adjacency))
        return dist < pref.n
    if relation == "graph_distance_lte":
        if carry_seat is None or pref.n is None:
            return False
        dist = seat_graph_distance(seat, carry_seat, dict(ctx.topology.seat_adjacency))
        # Unreachable (0 from missing edges) treated as violated when seats differ.
        if dist == 0 and seat != carry_seat:
            return True
        return dist > pref.n
    if relation == "adjacent_count_lt":
        if pref.n is None:
            return False
        return _adjacent_occupied_count(ctx, hero_id) < pref.n
    if relation == "carry_not_edge":
        # Lark-style: BUD/carry must sit in a mid column, not front/back edge.
        if carry_seat is None:
            return False
        return ctx.zone_of_seat(carry_seat) in {"front", "back"}
    if relation == "not_front":
        return ctx.zone_of_seat(seat) == "front"
    if relation == "carry_column_distance_lte":
        if carry_seat is None or pref.n is None:
            return False
        return abs(_column(ctx, seat) - _column(ctx, carry_seat)) > pref.n
    if relation == "prefer_adjacent_role":
        role = (pref.prefer_adjacent_role or "").casefold()
        if not role or pref.n is None:
            return False
        count = 0
        for neighbor in ctx.adjacent_seats(seat):
            other = ctx.hero_at_seat(neighbor)
            if other is None:
                continue
            if role in {r.casefold() for r in ctx.roles(other)}:
                count += 1
        return count < pref.n
    if relation == "shadowheart_dex_spread":
        # Find Yourself wants the highest-DEX duplicate ≥ n seats away (graph).
        min_dist = pref.n if pref.n is not None else 2
        scores = hero_ability_scores_map_from_cached_definitions()
        party = set(ctx.active_hero_ids)
        seats = dict(ctx.seat_by_hero)
        adj = dict(ctx.topology.seat_adjacency)
        dup = shadowheart_duplicate_hero(party, seats, scores)
        if dup is None:
            return False
        if dup == hero_id:
            # Shadowheart herself is highest DEX → Sister of Darkness, not spread.
            return True
        dist = shadowheart_duplicity_distance(party, seats, scores, adjacency=adj)
        return dist < min_dist
    return False


def _prefer_column_violated(
    pref: PlacementPreference,
    ctx: FormationLayoutContext,
    hero_id: int,
) -> bool:
    if pref.prefer_column is None:
        return False
    seat = ctx.seat_of(hero_id)
    if seat is None:
        return False
    return _column(ctx, seat) != pref.prefer_column


def _avoid_role_violated(
    pref: PlacementPreference,
    ctx: FormationLayoutContext,
    hero_id: int,
) -> bool:
    role = (pref.avoid_adjacent_role or "").casefold()
    if not role:
        return False
    seat = ctx.seat_of(hero_id)
    if seat is None:
        return False
    for neighbor in ctx.adjacent_seats(seat):
        other = ctx.hero_at_seat(neighbor)
        if other is None:
            continue
        if role in {r.casefold() for r in ctx.roles(other)}:
            return True
    return False


def _make_insight(
    pref: PlacementPreference,
    ctx: FormationLayoutContext,
    hero_id: int,
    carry_id: int | None,
    *,
    suggest_swap: bool = False,
) -> FormationInsight:
    seat = ctx.seat_of(hero_id)
    headline = pref.headline or f"{ctx.name(hero_id)}: adjust placement vs BUD"
    detail = pref.detail or headline
    headline = _format_text(headline, ctx=ctx, hero_id=hero_id, carry_id=carry_id)
    detail = _format_text(detail, ctx=ctx, hero_id=hero_id, carry_id=carry_id)

    related_hero_id = None
    related_hero_name = None
    related_seat = None
    insight_type = "placement"
    bud_ratio = None
    if suggest_swap and carry_id is not None and pref.bud_relation == "adjacent":
        best = best_swap_to_carry(ctx, hero_id)
        if best is not None:
            partner_id, partner_seat, ratio = best
            insight_type = "swap"
            related_hero_id = partner_id
            related_seat = partner_seat
            related_hero_name = ctx.name(partner_id) if partner_id is not None else "empty seat"
            bud_ratio = ratio
            detail = append_proxy_ratio(detail, ratio)

    return FormationInsight(
        insight_type=insight_type,  # type: ignore[arg-type]
        hero_id=hero_id,
        hero_name=ctx.name(hero_id),
        seat=seat,
        related_hero_id=related_hero_id,
        related_hero_name=related_hero_name,
        related_seat=related_seat,
        priority=pref.priority,
        headline=headline,
        detail=detail,
        rule_source_type="authored",
        data_source_version="formation_rules_v1",
        confidence=4 if pref.source == "hero" else 3,
        rule_id=(
            f"champ_place:{pref.source}:{hero_id}:"
            f"{pref.bud_relation or pref.prefer_column or pref.avoid_adjacent_role or pref.prefer_adjacent_role}"
        ),
        bud_ratio=bud_ratio,
    )


def _evaluate_pref(
    pref: PlacementPreference,
    ctx: FormationLayoutContext,
    hero_id: int,
    carry_id: int | None,
) -> FormationInsight | None:
    if not _goal_ok(pref, ctx):
        return None
    seat = ctx.seat_of(hero_id)
    if seat is None:
        return None

    # Secondary constraints that don't need a carry.
    if pref.avoid_adjacent_role and _avoid_role_violated(pref, ctx, hero_id):
        return _make_insight(pref, ctx, hero_id, carry_id)
    if pref.prefer_column is not None and _prefer_column_violated(pref, ctx, hero_id):
        return _make_insight(pref, ctx, hero_id, carry_id)
    if pref.prefer_adjacent_role:
        # Treat as bud_relation prefer_adjacent_role for the shared checker.
        role_pref = PlacementPreference(
            hero_id=pref.hero_id,
            name=pref.name,
            bud_relation="prefer_adjacent_role",
            prefer_adjacent_role=pref.prefer_adjacent_role,
            n=pref.n if pref.n is not None else 1,
            priority=pref.priority,
            headline=pref.headline,
            detail=pref.detail,
            goals=pref.goals,
            source=pref.source,
        )
        if _relation_violated(role_pref, ctx, hero_id, carry_id or -1):
            return _make_insight(pref, ctx, hero_id, carry_id)
        if not pref.bud_relation:
            return None

    relation = pref.bud_relation or ""
    if relation == "adjacent_count_lt":
        if _relation_violated(pref, ctx, hero_id, carry_id or -1):
            return _make_insight(pref, ctx, hero_id, carry_id)
        return None
    if relation in {"front", "back", "not_front", "not_edge", "shadowheart_dex_spread"}:
        if _relation_violated(pref, ctx, hero_id, carry_id or -1):
            return _make_insight(pref, ctx, hero_id, carry_id)
        return None

    # BUD-relative relations require a carry distinct from the hero.
    if carry_id is None or carry_id == hero_id:
        return None
    if relation and _relation_violated(pref, ctx, hero_id, carry_id):
        return _make_insight(
            pref,
            ctx,
            hero_id,
            carry_id,
            suggest_swap=(relation == "adjacent"),
        )
    return None


def evaluate_champion_placement_rules(
    ctx: FormationLayoutContext,
) -> list[FormationInsight]:
    """Evaluate role/tag defaults + per-hero BUD placement overrides."""
    if ctx.party_size < 2:
        return []
    overrides = _hero_overrides()
    carry_id = ctx.carry_hero_id or ctx.highest_damage_hero_id
    insights: list[FormationInsight] = []
    seen_heroes_default: set[int] = set()

    for hero_id in sorted(ctx.active_hero_ids):
        override = overrides.get(hero_id)
        if override is not None:
            tip = _evaluate_pref(override, ctx, hero_id, carry_id)
            if tip is not None:
                insights.append(tip)
            for child in override.also:
                child_tip = _evaluate_pref(child, ctx, hero_id, carry_id)
                if child_tip is not None:
                    insights.append(child_tip)
            seen_heroes_default.add(hero_id)
            continue

        # Role/tag defaults (skip carry themselves for BUD-relative defaults).
        if hero_id == carry_id:
            continue
        for pref in _default_prefs_for_hero(ctx, hero_id):
            # One default tip per hero (first matching tag/role wins by list order).
            if hero_id in seen_heroes_default:
                break
            tip = _evaluate_pref(pref, ctx, hero_id, carry_id)
            if tip is not None:
                insights.append(tip)
                seen_heroes_default.add(hero_id)
                break

    return insights
