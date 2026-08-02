"""Count qualified champions for multiply-stack specialization options."""

from __future__ import annotations

from typing import Any

from ic_gamedata.adventure_restrictions import hero_matches_specialization_expr
from ic_gamedata.adventure_restrictions import _hero_meta, _parse_int
from ic_gamedata.specialization_qualified_rules import QualifiedStackOptionRule

_AFFILIATION_TAGS = frozenset(
    {
        "acqinc",
        "awfulones",
        "companion",
        "cteam",
        "emeraldenclave",
        "heroeslance",
        "majestics",
        "morndinsamman",
        "rivals",
        "wafflecrew",
    }
)


def _hero_has_affiliation(hero_id: int) -> bool | None:
    meta = _hero_meta(hero_id)
    if "unaffiliated" in meta.all_tags:
        return False
    if meta.all_tags & _AFFILIATION_TAGS:
        return True
    if "companion" in meta.all_tags:
        return True
    return False


def _hero_matches_tag_expression(hero_id: int, raw_tags: str) -> bool | None:
    tag_expr = raw_tags.strip()
    if not tag_expr:
        return None
    if tag_expr == "!has_affiliation":
        affiliated = _hero_has_affiliation(hero_id)
        if affiliated is None:
            return None
        return not affiliated
    meta = _hero_meta(hero_id)
    tags = [part.strip().lower() for part in tag_expr.split("|") if part.strip()]
    if not tags:
        return None
    return any(tag in meta.all_tags for tag in tags)


def _hero_matches_target_filter(hero_id: int, target_filter: dict[str, Any]) -> bool | None:
    filter_type = str(target_filter.get("type") or "").strip().lower()
    meta = _hero_meta(hero_id)

    if filter_type == "tags":
        raw_tags = target_filter.get("tags")
        if not isinstance(raw_tags, str) or not raw_tags.strip():
            return None
        return _hero_matches_tag_expression(hero_id, raw_tags)

    if filter_type == "attack_type":
        attack = str(target_filter.get("attack") or "").strip().lower()
        if not attack:
            return None
        if not meta.attack_types:
            return None
        return attack in meta.attack_types

    if filter_type == "stat":
        stat = str(target_filter.get("stat") or "").strip().lower()
        comparison = str(target_filter.get("comparison") or "<=").strip()
        threshold = _parse_int(target_filter.get("value"))
        if threshold is None:
            return None
        if stat == "total_ability_score":
            if len(meta.stats) < 6:
                return None
            value = sum(meta.stats.get(key, 0) for key in ("str", "dex", "con", "int", "wis", "cha"))
        else:
            value = meta.stats.get(stat)
            if value is None:
                return None
        if comparison == "<=":
            return value <= threshold
        if comparison == "<":
            return value < threshold
        if comparison == ">=":
            return value >= threshold
        if comparison == ">":
            return value > threshold
        return None

    return None


def hero_matches_qualified_option(hero_id: int, option: QualifiedStackOptionRule) -> bool | None:
    if not option.supported:
        return None
    if option.kind == "all_crusaders":
        return True
    if option.kind == "expr" and option.expr:
        return hero_matches_specialization_expr(hero_id, option.expr)
    if option.kind == "target_filter" and option.target_filter:
        return _hero_matches_target_filter(hero_id, option.target_filter)
    return None


def count_qualified_heroes(
    active_hero_ids: set[int],
    option: QualifiedStackOptionRule,
) -> tuple[int, bool]:
    """Return (qualified_count, partial_data). partial_data is True when some heroes were unknown."""
    count = 0
    partial = False
    for hero_id in active_hero_ids:
        result = hero_matches_qualified_option(hero_id, option)
        if result is True:
            count += 1
        elif result is None:
            partial = True
    return count, partial
