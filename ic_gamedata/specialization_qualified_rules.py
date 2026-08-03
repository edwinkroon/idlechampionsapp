"""Parse multiply-stack specialization rules from cached game definitions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from ic_gamedata.specialization_data import (
    cached_definitions_data,
    hero_name_map_from_cached_definitions,
)

QualifierKind = Literal["expr", "target_filter", "all_crusaders", "unsupported"]

_MULTIPLY_STACK_FUNCS = frozenset({"per_crusader", "per_hero_attribute"})
_CUSTOM_STACK_FUNCS = frozenset(
    {
        "per_unique_race",
        "per_unique_role",
        "per_familiar_in_play",
        "per_ceremorphosis_stacks",
        "per_other_stack_count",
        "per_non_upgrade_targets",
        "per_upgrade_targets",
        "per_active_event_boons",
        "get_stat",
        "shadowheart_invoke_duplicity_dist",
        "per_hero",
    }
)
_UNSUPPORTED_EXPR_MARKERS = (
    "is_any_upgrade_positional",
    "timeavailable",
    "numequipment",
    "numilevels",
    "get_stat(",
)


@dataclass(frozen=True)
class QualifiedStackOptionRule:
    upgrade_id: int
    name: str
    pct: float
    kind: QualifierKind
    expr: str = ""
    target_filter: dict[str, Any] | None = None
    supported: bool = True


@dataclass(frozen=True)
class QualifiedStackTierRule:
    hero_id: int
    hero_name: str
    required_level: int
    options: tuple[QualifiedStackOptionRule, ...]

    @property
    def supported_options(self) -> tuple[QualifiedStackOptionRule, ...]:
        return tuple(opt for opt in self.options if opt.supported)


def _parse_effect_id(raw: Any) -> int | None:
    if not isinstance(raw, str) or not raw.startswith("effect_def,"):
        return None
    parts = raw.split(",")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _parse_pct_from_effect_string(effect_string: Any) -> float | None:
    if not isinstance(effect_string, str):
        return None
    if effect_string.startswith("pre_stack,") or effect_string.startswith("pre_stack_amount,"):
        try:
            return float(effect_string.split(",", 1)[1])
        except ValueError:
            return None
    if effect_string.startswith("buff_upgrade,"):
        parts = effect_string.split(",")
        if len(parts) >= 2:
            try:
                value = float(parts[1])
            except ValueError:
                return None
            if value > 0:
                return value
    multiply_prefixes = (
        "buff_upgrade_per_any_tagged_crusader_mult,",
        "hero_dps_mult_per_tagged_crusader_mult,",
        "buff_upgrade_by_tag_mult,",
        "buff_upgrade_per_any_crusader_where_mult,",
        "hero_dps_multiplier_mult,",
        "gold_multiplier_mult,",
        "hero_kills_gold_mult,",
        "buff_upgrades,",
    )
    for prefix in multiply_prefixes:
        if effect_string.startswith(prefix):
            parts = effect_string.split(",")
            if len(parts) >= 2:
                try:
                    value = float(parts[1])
                except ValueError:
                    return None
                if value > 0:
                    return value
    return None


def _expr_is_supported(expr: str) -> bool:
    lowered = expr.strip().casefold()
    if not lowered:
        return False
    return not any(marker in lowered for marker in _UNSUPPORTED_EXPR_MARKERS)


def _is_multiply_stack_effect(keys: list[Any]) -> bool:
    has_base_buff_pct = False
    has_i_want_stacks = False
    for key in keys:
        if not isinstance(key, dict):
            continue
        if key.get("stack_func") in _CUSTOM_STACK_FUNCS:
            continue
        if key.get("stacks_multiply"):
            return True
        if key.get("amount_func") == "mult" and key.get("stack_func") in _MULTIPLY_STACK_FUNCS:
            return True
        effect_string = key.get("effect_string")
        if not isinstance(effect_string, str):
            continue
        if effect_string.startswith(
            (
                "buff_upgrade_per_any_tagged_crusader_mult,",
                "hero_dps_mult_per_tagged_crusader_mult,",
                "buff_upgrade_by_tag_mult,",
                "buff_upgrade_per_any_crusader_where_mult,",
            )
        ):
            return True
        if effect_string.startswith("buff_upgrade_per_crusader,") and key.get("stacks_multiply"):
            return True
        if effect_string.startswith("buff_upgrades,") and key.get("stacks_multiply"):
            return True
        # Split pattern (e.g. Lazaapz Fury specs): base buff_upgrade,PCT + i_want_stacks
        # qualifier via per_hero_attribute / per_crusader. Without this, those tiers fall
        # through to static defaults and ignore the live qualified × % ranking.
        if effect_string.startswith("buff_upgrade,") and _parse_pct_from_effect_string(effect_string):
            has_base_buff_pct = True
        if (
            effect_string == "i_want_stacks"
            and key.get("stack_func") in _MULTIPLY_STACK_FUNCS
            and key.get("per_hero_expr")
        ):
            has_i_want_stacks = True
    return has_base_buff_pct and has_i_want_stacks


def _unsupported_filter_keys(stack_data: dict[str, Any]) -> bool:
    if stack_data.get("include_escorts"):
        return True
    if stack_data.get("target_filters_or"):
        return True
    return False


def _tags_target_filter(raw_tags: str) -> dict[str, Any]:
    return {"type": "tags", "tags": raw_tags}


def _stat_target_filter(stat: str, comparison: str, value: int | float) -> dict[str, Any]:
    return {
        "type": "stat",
        "stat": stat.strip().lower(),
        "comparison": comparison,
        "value": value,
    }


def _qualifier_from_effect_string(effect_string: str) -> tuple[QualifierKind, str, dict[str, Any] | None, bool] | None:
    if effect_string.startswith("buff_upgrade_per_any_tagged_crusader_mult,"):
        parts = effect_string.split(",")
        if len(parts) >= 4 and parts[3].strip():
            return "target_filter", "", _tags_target_filter(parts[3].strip()), True
    if effect_string.startswith("hero_dps_mult_per_tagged_crusader_mult,"):
        parts = effect_string.split(",")
        if len(parts) >= 3 and parts[2].strip():
            return "target_filter", "", _tags_target_filter(parts[2].strip()), True
    if effect_string.startswith("buff_upgrade_by_tag_mult,"):
        parts = effect_string.split(",")
        if len(parts) >= 3 and parts[2].strip():
            return "target_filter", "", _tags_target_filter(parts[2].strip()), True
    if effect_string.startswith("buff_upgrade_per_any_crusader_where_mult,"):
        parts = effect_string.split(",")
        if len(parts) >= 6:
            stat = parts[3].strip().lower()
            comparison = parts[4].strip()
            try:
                value = float(parts[5])
            except ValueError:
                return None
            return "target_filter", "", _stat_target_filter(stat, comparison, value), True
    if effect_string.startswith("buff_upgrade_per_crusader,"):
        return "all_crusaders", "", None, True
    return None


def _qualifier_from_effect_keys(keys: list[Any]) -> tuple[QualifierKind, str, dict[str, Any] | None, bool]:
    saw_multiply_stack = False
    saw_unsupported_expr = False

    for key in keys:
        if not isinstance(key, dict):
            continue
        if key.get("stack_func") in _CUSTOM_STACK_FUNCS:
            return "unsupported", "", None, False
        if key.get("stacks_multiply") or (
            key.get("amount_func") == "mult" and key.get("stack_func") in _MULTIPLY_STACK_FUNCS
        ):
            saw_multiply_stack = True
        if per_hero_expr := key.get("per_hero_expr"):
            expr_text = str(per_hero_expr).strip()
            if expr_text == "0":
                return "all_crusaders", "", None, True
            if _expr_is_supported(expr_text):
                return "expr", expr_text, None, True
            saw_unsupported_expr = True
            continue
        stack_data = key.get("stack_func_data")
        if isinstance(stack_data, dict):
            if _unsupported_filter_keys(stack_data):
                return "unsupported", "", None, False
            filters = stack_data.get("target_filters")
            if isinstance(filters, list) and filters and isinstance(filters[0], dict):
                target_filter = filters[0]
                return "target_filter", "", target_filter, True
        if key.get("stack_func") == "per_crusader" and key.get("amount_func") == "mult":
            if not key.get("stack_func_data"):
                return "all_crusaders", "", None, True
        effect_string = key.get("effect_string")
        if isinstance(effect_string, str):
            parsed = _qualifier_from_effect_string(effect_string)
            if parsed is not None:
                return parsed

    if saw_unsupported_expr:
        return "unsupported", "", None, False
    if saw_multiply_stack:
        return "all_crusaders", "", None, True

    return "unsupported", "", None, False


def _option_rule_from_upgrade(
    upgrade: dict[str, Any],
    effects_by_id: dict[int, dict[str, Any]],
) -> QualifiedStackOptionRule | None:
    if not upgrade.get("specialization_name"):
        return None
    effect_id = _parse_effect_id(upgrade.get("effect"))
    if effect_id is None:
        return None
    effect = effects_by_id.get(effect_id)
    if effect is None:
        return None
    keys = effect.get("effect_keys") or []
    if not _is_multiply_stack_effect(keys):
        return None

    pct: float | None = None
    for key in keys:
        if not isinstance(key, dict):
            continue
        parsed = _parse_pct_from_effect_string(key.get("effect_string"))
        if parsed is not None:
            pct = parsed
            break
    if pct is None:
        return None

    upgrade_id = upgrade.get("id")
    name = upgrade.get("specialization_name") or upgrade.get("name")
    if upgrade_id is None or not isinstance(name, str):
        return None

    kind, expr, target_filter, supported = _qualifier_from_effect_keys(keys)
    return QualifiedStackOptionRule(
        upgrade_id=int(upgrade_id),
        name=name.strip(),
        pct=float(pct),
        kind=kind,
        expr=expr,
        target_filter=target_filter,
        supported=supported,
    )


def _dedupe_options_by_name(options: list[QualifiedStackOptionRule]) -> list[QualifiedStackOptionRule]:
    """Keep one upgrade per specialization name (lowest id) for branched tiers like Baldric."""
    by_name: dict[str, QualifiedStackOptionRule] = {}
    for opt in sorted(options, key=lambda item: item.upgrade_id):
        key = opt.name.casefold()
        if key not in by_name:
            by_name[key] = opt
    return list(by_name.values())


def _build_tiers_from_definitions(data: dict[str, Any]) -> dict[int, dict[int, QualifiedStackTierRule]]:
    upgrades = data.get("upgrade_defines")
    effects = data.get("effect_defines")
    if not isinstance(upgrades, list) or not isinstance(effects, list):
        return {}

    effects_by_id = {
        int(item["id"]): item
        for item in effects
        if isinstance(item, dict) and item.get("id") is not None
    }
    names = hero_name_map_from_cached_definitions()
    by_hero_level: dict[tuple[int, int], list[QualifiedStackOptionRule]] = {}

    for upgrade in upgrades:
        if not isinstance(upgrade, dict) or not upgrade.get("specialization_name"):
            continue
        hero_id_raw = upgrade.get("hero_id")
        level_raw = upgrade.get("required_level")
        if hero_id_raw is None or level_raw is None:
            continue
        option = _option_rule_from_upgrade(upgrade, effects_by_id)
        if option is None:
            continue
        by_hero_level.setdefault((int(hero_id_raw), int(level_raw)), []).append(option)

    out: dict[int, dict[int, QualifiedStackTierRule]] = {}
    for (hero_id, required_level), options in by_hero_level.items():
        deduped_by_id = {opt.upgrade_id: opt for opt in options}
        deduped = _dedupe_options_by_name(list(deduped_by_id.values()))
        if len(deduped) < 2:
            continue
        supported = tuple(sorted(deduped, key=lambda opt: opt.upgrade_id))
        if len(supported) > 8:
            continue
        if sum(1 for opt in supported if opt.supported) < 2:
            continue
        out.setdefault(hero_id, {})[required_level] = QualifiedStackTierRule(
            hero_id=hero_id,
            hero_name=names.get(hero_id, f"Hero {hero_id}"),
            required_level=required_level,
            options=supported,
        )
    return out


@lru_cache(maxsize=1)
def qualified_stack_tiers_by_hero() -> dict[int, dict[int, QualifiedStackTierRule]]:
    return _build_tiers_from_definitions(cached_definitions_data())


def generic_qualified_stack_hero_ids(*, exclude_hero_ids: set[int] | None = None) -> frozenset[int]:
    excluded = exclude_hero_ids or set()
    covered: set[int] = set()
    for hero_id, tiers in qualified_stack_tiers_by_hero().items():
        if hero_id in excluded:
            continue
        if any(len(tier.supported_options) >= 2 for tier in tiers.values()):
            covered.add(hero_id)
    return frozenset(covered)


def tier_rule_for_hero_level(hero_id: int, required_level: int) -> QualifiedStackTierRule | None:
    return qualified_stack_tiers_by_hero().get(hero_id, {}).get(required_level)


def tiers_for_known_options(
    hero_id: int,
    known_options: list[Any],
) -> list[QualifiedStackTierRule]:
    tiers_by_level = qualified_stack_tiers_by_hero().get(hero_id, {})
    if not tiers_by_level or not known_options:
        return []

    matched: list[QualifiedStackTierRule] = []
    for tier_index in sorted({opt.tier_index for opt in known_options}):
        level_options = [opt for opt in known_options if opt.tier_index == tier_index]
        if not level_options:
            continue
        required_level = level_options[0].required_level
        tier = tiers_by_level.get(required_level)
        if tier is None:
            continue
        known_ids = {opt.upgrade_id for opt in level_options}
        tier_options = [opt for opt in tier.supported_options if opt.upgrade_id in known_ids]
        if len(tier_options) < 2:
            continue
        matched.append(
            QualifiedStackTierRule(
                hero_id=tier.hero_id,
                hero_name=tier.hero_name,
                required_level=tier.required_level,
                options=tuple(tier_options),
            )
        )
    return matched
