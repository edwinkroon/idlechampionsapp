"""Audit specialization tiers that stack multiplicatively by qualified champions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ic_gamedata.specialization_data import (
    cached_definitions_data,
    hero_name_map_from_cached_definitions,
)

StackAuditStatus = Literal["handled", "missing", "custom"]

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
    }
)


@dataclass(frozen=True)
class StackSpecOption:
    upgrade_id: int
    name: str
    pct: float | None
    stack_func: str | None
    filter_summary: str


@dataclass(frozen=True)
class StackSpecTier:
    hero_id: int
    hero_name: str
    required_level: int
    options: tuple[StackSpecOption, ...]
    status: StackAuditStatus
    notes: str


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


def _parse_pre_stack_pct(effect_string: Any) -> float | None:
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
                return float(parts[1])
            except ValueError:
                return None
    return None


def _summarize_filter(key: dict[str, Any]) -> str:
    if expr := key.get("per_hero_expr"):
        return str(expr)
    if tag := key.get("tag"):
        return f"tag:{tag}"
    stack_data = key.get("stack_func_data")
    if isinstance(stack_data, dict):
        filters = stack_data.get("target_filters")
        if isinstance(filters, list) and filters:
            return str(filters[0])
    return ""


def _option_from_effect(
    upgrade: dict[str, Any],
    effects_by_id: dict[int, dict[str, Any]],
) -> StackSpecOption | None:
    effect_id = _parse_effect_id(upgrade.get("effect"))
    if effect_id is None:
        return None
    effect = effects_by_id.get(effect_id)
    if effect is None:
        return None

    pct: float | None = None
    stack_func: str | None = None
    filter_summary = ""
    multiply = False

    for key in effect.get("effect_keys") or []:
        if not isinstance(key, dict):
            continue
        parsed_pct = _parse_pre_stack_pct(key.get("effect_string"))
        if parsed_pct is not None and pct is None:
            pct = parsed_pct
        if key.get("stacks_multiply"):
            multiply = True
        if key.get("amount_func") == "mult" and key.get("stack_func"):
            stack_func = str(key.get("stack_func"))
        summary = _summarize_filter(key)
        if summary and not filter_summary:
            filter_summary = summary

    if not multiply and stack_func not in {"per_crusader", "per_hero_attribute"}:
        return None

    upgrade_id = upgrade.get("id")
    name = upgrade.get("specialization_name") or upgrade.get("name")
    if upgrade_id is None or not isinstance(name, str):
        return None

    return StackSpecOption(
        upgrade_id=int(upgrade_id),
        name=name.strip(),
        pct=pct,
        stack_func=stack_func,
        filter_summary=filter_summary,
    )


def _tier_status(
    hero_id: int,
    options: tuple[StackSpecOption, ...],
    *,
    handled_hero_ids: set[int],
    generic_hero_ids: set[int] | None = None,
) -> tuple[StackAuditStatus, str]:
    stack_funcs = {opt.stack_func for opt in options if opt.stack_func}
    if stack_funcs & _CUSTOM_STACK_FUNCS:
        return "custom", f"custom stack logic: {', '.join(sorted(stack_funcs & _CUSTOM_STACK_FUNCS))}"

    if any(opt.stack_func == "per_unique_race" for opt in options):
        return "custom", "uses per_unique_race (species count, not per-hero tags)"

    if hero_id in handled_hero_ids:
        return "handled", "dynamic handler in specialization_engine"
    if generic_hero_ids and hero_id in generic_hero_ids:
        return "handled", "generic qualified-stack rules from cached_definitions"

    if all(opt.stack_func in {"per_crusader", "per_hero_attribute", None} for opt in options):
        return "missing", "multiply-stack tier without dynamic handler"

    return "custom", f"stack funcs: {', '.join(sorted(stack_funcs)) or 'unknown'}"


def audit_qualified_stack_specs(
    *,
    handled_hero_ids: set[int] | None = None,
    definitions: dict[str, Any] | None = None,
) -> list[StackSpecTier]:
    """Return tier-0+ choice groups whose specs stack multiplicatively by qualified champions."""
    if handled_hero_ids is None:
        from ic_gamedata.specialization_engine import HERO_HANDLERS

        handled_hero_ids = set(HERO_HANDLERS)

    from ic_gamedata.specialization_qualified_rules import generic_qualified_stack_hero_ids

    generic_hero_ids = set(generic_qualified_stack_hero_ids(exclude_hero_ids=handled_hero_ids))

    data = definitions if definitions is not None else cached_definitions_data()
    upgrades = data.get("upgrade_defines")
    effects = data.get("effect_defines")
    if not isinstance(upgrades, list) or not isinstance(effects, list):
        return []

    effects_by_id = {
        int(item["id"]): item
        for item in effects
        if isinstance(item, dict) and item.get("id") is not None
    }
    names = hero_name_map_from_cached_definitions()

    by_hero_level: dict[tuple[int, int], list[StackSpecOption]] = {}
    for upgrade in upgrades:
        if not isinstance(upgrade, dict):
            continue
        if not upgrade.get("specialization_name"):
            continue
        hero_id_raw = upgrade.get("hero_id")
        level_raw = upgrade.get("required_level")
        if hero_id_raw is None or level_raw is None:
            continue
        option = _option_from_effect(upgrade, effects_by_id)
        if option is None:
            continue
        hero_id = int(hero_id_raw)
        required_level = int(level_raw)
        by_hero_level.setdefault((hero_id, required_level), []).append(option)

    tiers: list[StackSpecTier] = []
    for (hero_id, required_level), options in sorted(by_hero_level.items()):
        if len(options) < 2:
            continue
        deduped = tuple(sorted({opt.upgrade_id: opt for opt in options}.values(), key=lambda o: o.upgrade_id))
        if len(deduped) < 2:
            continue
        status, notes = _tier_status(
            hero_id,
            deduped,
            handled_hero_ids=handled_hero_ids,
            generic_hero_ids=generic_hero_ids,
        )
        tiers.append(
            StackSpecTier(
                hero_id=hero_id,
                hero_name=names.get(hero_id, f"Hero {hero_id}"),
                required_level=required_level,
                options=deduped,
                status=status,
                notes=notes,
            )
        )
    return tiers


def missing_stack_handlers(
    *,
    handled_hero_ids: set[int] | None = None,
    definitions: dict[str, Any] | None = None,
) -> list[StackSpecTier]:
    return [
        tier
        for tier in audit_qualified_stack_specs(
            handled_hero_ids=handled_hero_ids,
            definitions=definitions,
        )
        if tier.status == "missing"
    ]
