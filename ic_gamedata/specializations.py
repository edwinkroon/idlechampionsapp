"""Specialization rules and pending-choice detection."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from ic_gamedata.familiar_seats import familiar_party_count
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.specialization_advice_text import human_specialization_reason
from ic_gamedata.specialization_data import (
    cached_definitions_data,
    hero_name_map_from_cached_definitions,
    hero_name_map_from_champion_config,
)
from ic_gamedata.specialization_engine import (
    FormationContext,
    HERO_HANDLERS,
)
from ic_gamedata.specialization_engine import (
    baseline_default_ids as _baseline_default_ids,
)
from ic_gamedata.specialization_engine import (
    dynamic_default_ids as _dynamic_default_ids,
)
from ic_gamedata.specialization_engine import (
    supplement_missing_tier_ids as _supplement_missing_tier_ids,
)
from ic_gamedata.specialization_models import PendingSpecialization, SpecializationOption
from ic_gamedata.specialization_rules.context_builder import (
    build_evaluation_context,
    champion_names_match,
)
from ic_gamedata.specialization_rules.evaluator import evaluate_specialization
from ic_gamedata.specialization_rules.loader import cached_documentation_rules
from ic_gamedata.specialization_rules.models import AdviceResult

# Backward-compatible aliases for tests and patches.
_hero_name_map_from_cached_definitions = hero_name_map_from_cached_definitions
_hero_name_map_from_champion_config = hero_name_map_from_champion_config


def _extract_upgrade_id(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ("upgrade_id", "id", "specialization_id"):
            parsed = _parse_int(value.get(key))
            if parsed is not None:
                return parsed
        return None
    return _parse_int(value)


def _raw_selected_upgrade_ids(hero: dict[str, Any]) -> set[int]:
    """All upgrade ids recorded on the hero, without filtering to known spec options."""
    selected: set[int] = set()
    for key in ("specialization_choices", "upgrades"):
        raw = hero.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            upgrade_id = _extract_upgrade_id(item)
            if upgrade_id is not None:
                selected.add(upgrade_id)
    return selected


def _party_hero_records(
    payload: dict[str, Any],
    hero_id: int,
    *,
    active_party_id: int,
    active_hero_ids: set[int],
) -> list[dict[str, Any]]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return []
    heroes = details.get("heroes")
    if not isinstance(heroes, list):
        return []
    return [
        hero
        for hero in heroes
        if isinstance(hero, dict)
        and _parse_int(hero.get("hero_id")) == hero_id
        and _hero_belongs_to_active_party(
            hero,
            active_party_id=active_party_id,
            active_hero_ids=active_hero_ids,
        )
    ]


def _merge_upgrade_list_items(*lists: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[int] = set()
    for raw in lists:
        if not isinstance(raw, list):
            continue
        for item in raw:
            upgrade_id = _extract_upgrade_id(item)
            if upgrade_id is None or upgrade_id in seen:
                continue
            seen.add(upgrade_id)
            merged.append(item)
    return merged


def merged_hero_record_for_specializations(
    payload: dict[str, Any],
    hero_id: int,
    *,
    active_party_id: int | None = None,
    active_hero_ids: set[int] | None = None,
) -> dict[str, Any] | None:
    """Merge specialization state from every hero row for this party slot.

    Live API data often stores specialization picks on the shared roster row
    (game_instance_id 0) while a party-specific duplicate row stays stale.
    """
    if active_party_id is None:
        active_party_id = _active_party_id(payload)
    if active_party_id is None:
        return None
    instance = _active_instance(payload)
    if active_hero_ids is None:
        active_hero_ids = _active_hero_ids(instance) if instance else set()
    records = _party_hero_records(
        payload,
        hero_id,
        active_party_id=active_party_id,
        active_hero_ids=active_hero_ids,
    )
    if not records:
        return None

    base = resolve_hero_record(
        payload,
        hero_id,
        active_party_id=active_party_id,
        active_hero_ids=active_hero_ids,
    ) or records[0]
    merged = dict(base)
    max_level = 0
    spec_lists: list[list[Any]] = []
    upgrade_lists: list[list[Any]] = []
    for record in records:
        max_level = max(max_level, _parse_int(record.get("level")) or 0)
        raw_specs = record.get("specialization_choices")
        if isinstance(raw_specs, list):
            spec_lists.append(raw_specs)
        raw_upgrades = record.get("upgrades")
        if isinstance(raw_upgrades, list):
            upgrade_lists.append(raw_upgrades)
    merged["level"] = max_level
    merged["specialization_choices"] = _merge_upgrade_list_items(*spec_lists)
    merged["upgrades"] = _merge_upgrade_list_items(*upgrade_lists)
    return merged


def _hero_belongs_to_active_party(
    hero: dict[str, Any],
    *,
    active_party_id: int,
    active_hero_ids: set[int],
) -> bool:
    hero_id = _parse_int(hero.get("hero_id"))
    if hero_id is None or hero_id not in active_hero_ids:
        return False
    game_instance_id = _parse_int(hero.get("game_instance_id"))
    if game_instance_id is None or game_instance_id <= 0:
        return True
    return game_instance_id == active_party_id


def resolve_hero_record(
    payload: dict[str, Any],
    hero_id: int,
    *,
    active_party_id: int | None = None,
    active_hero_ids: set[int] | None = None,
) -> dict[str, Any] | None:
    """Best matching hero row for the active party (handles game_instance_id 0)."""
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    if active_party_id is None:
        active_party_id = _active_party_id(payload)
    if active_party_id is None:
        return None
    instance = _active_instance(payload)
    if active_hero_ids is None:
        active_hero_ids = _active_hero_ids(instance) if instance else set()

    heroes = details.get("heroes")
    if not isinstance(heroes, list):
        return None

    candidates = [
        hero
        for hero in heroes
        if isinstance(hero, dict)
        and _parse_int(hero.get("hero_id")) == hero_id
        and _hero_belongs_to_active_party(
            hero,
            active_party_id=active_party_id,
            active_hero_ids=active_hero_ids,
        )
    ]
    if not candidates:
        return None
    for hero in candidates:
        if _parse_int(hero.get("game_instance_id")) == active_party_id:
            return hero
    for hero in candidates:
        gid = _parse_int(hero.get("game_instance_id"))
        if gid is None or gid <= 0:
            return hero
    return candidates[0]


def _tier_is_chosen(
    hero: dict[str, Any],
    options: tuple[SpecializationOption, ...] | list[SpecializationOption],
    known_options: list[SpecializationOption],
) -> bool:
    choice_set = set(_current_choices(hero, known_options))
    if any(option.upgrade_id in choice_set for option in options):
        return True
    raw_ids = _raw_selected_upgrade_ids(hero)
    return any(option.upgrade_id in raw_ids for option in options)


def _config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "specializations.json"
    return Path(__file__).resolve().parent.parent / "config" / "specializations.json"



def load_specialization_rules() -> dict[str, Any]:
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "ui": {}, "heroes": {}}
    if not isinstance(data, dict):
        return {"version": 1, "ui": {}, "heroes": {}}
    if not isinstance(data.get("heroes"), dict):
        data["heroes"] = {}
    if not isinstance(data.get("ui"), dict):
        data["ui"] = {}
    return data


def specialization_click_layout(rules: dict[str, Any], option_count: int) -> list[tuple[float, float]]:
    layouts = rules.get("ui") if isinstance(rules.get("ui"), dict) else {}
    raw = layouts.get("click_positions") if isinstance(layouts, dict) else {}
    if isinstance(raw, dict):
        coords = raw.get(str(option_count))
        if isinstance(coords, list):
            out: list[tuple[float, float]] = []
            for item in coords:
                if (
                    isinstance(item, list)
                    and len(item) == 2
                    and isinstance(item[0], (int, float))
                    and isinstance(item[1], (int, float))
                ):
                    out.append((float(item[0]), float(item[1])))
            if out:
                return out
    defaults = {
        1: [(0.50, 0.76)],
        2: [(0.40, 0.76), (0.60, 0.76)],
        3: [(0.28, 0.76), (0.50, 0.76), (0.72, 0.76)],
        4: [(0.20, 0.76), (0.40, 0.76), (0.60, 0.76), (0.80, 0.76)],
    }
    return defaults.get(option_count, defaults[3])


def _active_instance(payload: dict[str, Any]) -> dict[str, Any] | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    instances = details.get("game_instances")
    if not isinstance(instances, list):
        return None
    for inst in instances:
        if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:
            return inst
    return None


def _active_party_id(payload: dict[str, Any]) -> int | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    return _parse_int(details.get("active_game_instance_id"))


def _active_highest_damage_hero_id(payload: dict[str, Any]) -> int | None:
    instance = _active_instance(payload)
    if instance is None:
        return None
    stats = instance.get("stats")
    if not isinstance(stats, dict):
        return None
    return _parse_int(stats.get("this_reset_highest_damage_dealt_hero_id"))


def _active_hero_ids(instance: dict[str, Any]) -> set[int]:
    raw = instance.get("hero_in_seats")
    if not isinstance(raw, dict):
        return set()
    hero_ids: set[int] = set()
    for hero_raw in raw.values():
        hero_id = _parse_int(hero_raw)
        if hero_id is not None and hero_id > 0:
            hero_ids.add(hero_id)
    return hero_ids


def _seat_by_hero(instance: dict[str, Any]) -> dict[int, int]:
    raw = instance.get("hero_in_seats")
    if not isinstance(raw, dict):
        return {}
    out: dict[int, int] = {}
    for seat_raw, hero_raw in raw.items():
        seat = _parse_int(seat_raw)
        hero_id = _parse_int(hero_raw)
        if seat is None or hero_id is None or hero_id <= 0:
            continue
        out[hero_id] = seat
    return out


def _active_adventure_details(payload: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    instance = _active_instance(payload)
    if instance is None:
        return None, None, None
    adventure_id = _parse_int(instance.get("current_adventure_id"))
    if adventure_id is None:
        return None, None, None
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return adventure_id, None, None
    adventures = defines.get("adventure_defines")
    if not isinstance(adventures, list):
        return adventure_id, None, None
    for adv in adventures:
        if not isinstance(adv, dict) or _parse_int(adv.get("id")) != adventure_id:
            continue
        return adventure_id, _parse_int(adv.get("campaign_id")), _parse_int(adv.get("location_id"))
    return adventure_id, None, None


def _definition_name(payload: dict[str, Any], key: str, item_id: int | None) -> str | None:
    if item_id is None:
        return None
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return None
    items = defines.get(key)
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or _parse_int(item.get("id")) != item_id:
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _active_adventure_context(payload: dict[str, Any]) -> dict[str, str | int | None]:
    adventure_id, campaign_id, location_id = _active_adventure_details(payload)
    return {
        "adventure_id": adventure_id,
        "campaign_id": campaign_id,
        "location_id": location_id,
        "adventure_name": _definition_name(payload, "adventure_defines", adventure_id),
        "campaign_name": _definition_name(payload, "campaign_defines", campaign_id),
    }


def _hero_name_map(rules: dict[str, Any]) -> dict[int, str]:
    out = _hero_name_map_from_cached_definitions()
    out.update(_hero_name_map_from_champion_config())
    heroes = rules.get("heroes")
    if not isinstance(heroes, dict):
        return out
    for hero_id_raw, cfg in heroes.items():
        hero_id = _parse_int(hero_id_raw)
        if hero_id is None or not isinstance(cfg, dict):
            continue
        name = cfg.get("name")
        if isinstance(name, str) and name.strip():
            out[hero_id] = name.strip()
    return out


def _known_options_from_rules(rules: dict[str, Any]) -> dict[int, list[SpecializationOption]]:
    out: dict[int, list[SpecializationOption]] = {}
    heroes = rules.get("heroes")
    if not isinstance(heroes, dict):
        return out
    for hero_id_raw, cfg in heroes.items():
        hero_id = _parse_int(hero_id_raw)
        if hero_id is None or not isinstance(cfg, dict):
            continue
        options = cfg.get("options")
        if not isinstance(options, list):
            continue
        items: list[SpecializationOption] = []
        for item in options:
            if not isinstance(item, dict):
                continue
            upgrade_id = _parse_int(item.get("upgrade_id"))
            required_level = _parse_int(item.get("required_level"))
            tier_index = _parse_int(item.get("tier_index"))
            name = item.get("name")
            if (
                upgrade_id is None
                or required_level is None
                or tier_index is None
                or not isinstance(name, str)
                or not name.strip()
            ):
                continue
            items.append(
                SpecializationOption(
                    upgrade_id=upgrade_id,
                    name=name.strip(),
                    required_level=required_level,
                    tier_index=tier_index,
                )
            )
        if items:
            out[hero_id] = sorted(items, key=lambda opt: (opt.tier_index, opt.upgrade_id))
    return out


def _options_from_upgrade_defines(upgrades: Any) -> dict[int, list[SpecializationOption]]:
    if not isinstance(upgrades, list):
        return {}
    out: dict[int, list[SpecializationOption]] = {}
    for item in upgrades:
        if not isinstance(item, dict):
            continue
        spec_name = item.get("specialization_name")
        if not isinstance(spec_name, str) or not spec_name.strip():
            continue
        hero_id = _parse_int(item.get("hero_id"))
        upgrade_id = _parse_int(item.get("id"))
        required_level = _parse_int(item.get("required_level"))
        if hero_id is None or upgrade_id is None or required_level is None:
            continue
        out.setdefault(hero_id, []).append(
            SpecializationOption(
                upgrade_id=upgrade_id,
                name=spec_name.strip(),
                required_level=required_level,
                tier_index=0,
            )
        )
    for hero_id, options in out.items():
        levels = sorted({opt.required_level for opt in options})
        tier_by_level = {level: index for index, level in enumerate(levels)}
        out[hero_id] = [
            SpecializationOption(
                upgrade_id=opt.upgrade_id,
                name=opt.name,
                required_level=opt.required_level,
                tier_index=tier_by_level[opt.required_level],
            )
            for opt in sorted(options, key=lambda opt: (opt.required_level, opt.upgrade_id))
        ]
    return out


def _choices_from_upgrade_defines(payload: dict[str, Any]) -> dict[int, list[SpecializationOption]]:
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return {}
    return _options_from_upgrade_defines(defines.get("upgrade_defines"))


@lru_cache(maxsize=1)
def _choices_from_cached_definitions() -> dict[int, list[SpecializationOption]]:
    data = cached_definitions_data()
    if not data:
        return {}
    return _options_from_upgrade_defines(data.get("upgrade_defines"))


def _merge_known_options(payload: dict[str, Any], rules: dict[str, Any]) -> dict[int, list[SpecializationOption]]:
    merged = _known_options_from_rules(rules)
    for hero_id, options in _choices_from_upgrade_defines(payload).items():
        merged[hero_id] = options
    for hero_id, options in _choices_from_cached_definitions().items():
        merged.setdefault(hero_id, options)
    return merged


def _current_choices(hero: dict[str, Any], known_options: list[SpecializationOption]) -> tuple[int, ...]:
    """Return upgrade_ids for specialization tiers already chosen for this hero."""
    known_ids = {opt.upgrade_id for opt in known_options}
    selected: set[int] = set()

    for key in ("specialization_choices", "upgrades"):
        raw = hero.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            upgrade_id = _extract_upgrade_id(item)
            if upgrade_id is not None and upgrade_id in known_ids:
                selected.add(upgrade_id)

    return tuple(sorted(selected))


def _map_run_goal(context: str) -> str:
    mapping = {
        "speed": "speed_farm",
        "speed_farm": "speed_farm",
        "gold": "gold_farm",
        "gold_farm": "gold_farm",
        "push": "push",
        "survival": "survival",
        "variant": "variant",
        "campaign": "generic_progression",
    }
    return mapping.get(context.strip().casefold(), context.strip().casefold() or "generic_progression")


def _csv_rules_for_champion(hero_name: str) -> bool:
    dataset = cached_documentation_rules()
    if not dataset.is_usable:
        return False
    return any(champion_names_match(rule.champion, hero_name) for rule in dataset.rules)


def _csv_choice_advice(
    hero_id: int,
    hero_name: str,
    *,
    seat: int | None,
    run_goal: str,
    active_hero_ids: set[int] | None,
    highest_damage_hero_id: int | None,
    familiar_count: int,
    seat_by_hero: dict[int, int] | None,
    known_options: list[SpecializationOption] | None,
    payload: dict[str, Any] | None,
) -> tuple[list[int], str, AdviceResult | None]:
    if not known_options or not _csv_rules_for_champion(hero_name):
        return [], "", None

    party_ids = active_hero_ids if active_hero_ids else {hero_id}

    formation = FormationContext(
        active_hero_ids=party_ids,
        highest_damage_hero_id=highest_damage_hero_id,
        familiar_count=familiar_count,
        seat_by_hero=seat_by_hero,
    )
    eval_ctx = build_evaluation_context(
        hero_id=hero_id,
        hero_name=hero_name,
        seat=seat,
        run_goal=run_goal,
        formation=formation,
        payload=payload,
    )

    chosen_ids: list[int] = []
    advice_parts: list[str] = []
    last_advice: AdviceResult | None = None
    for tier_index in sorted({opt.tier_index for opt in known_options}):
        tier_options = [opt for opt in known_options if opt.tier_index == tier_index]
        advice = evaluate_specialization(eval_ctx, tier_options, tier_index=tier_index)
        if advice is None or advice.upgrade_id is None:
            continue
        chosen_ids.append(advice.upgrade_id)
        advice_parts.append(advice.rationale)
        last_advice = advice

    if not chosen_ids or last_advice is None:
        return [], "", last_advice

    detail = advice_parts[0] if advice_parts else last_advice.rationale
    source = last_advice.rule_source_label()
    return chosen_ids, f"{source}: {detail}", last_advice


def _desired_choice_ids(
    hero_id: int,
    hero_name: str,
    rules: dict[str, Any],
    *,
    adventure_id: int | None,
    campaign_id: int | None,
    location_id: int | None,
    context: str,
    run_goal: str | None = None,
    active_hero_ids: set[int] | None = None,
    highest_damage_hero_id: int | None = None,
    familiar_count: int = 0,
    seat_by_hero: dict[int, int] | None = None,
    known_options: list[SpecializationOption] | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[list[int], str, AdviceResult | None]:
    heroes = rules.get("heroes")
    if not isinstance(heroes, dict):
        baseline = _baseline_default_ids(hero_id, known_options or [])
        if baseline is not None:
            return (*baseline, None)
        return [], "geen regel", None
    cfg = heroes.get(str(hero_id))
    if not isinstance(cfg, dict):
        baseline = _baseline_default_ids(hero_id, known_options or [])
        if baseline is not None:
            return (*baseline, None)
        return [], "geen regel", None

    resolved_run_goal = run_goal or _map_run_goal(context)

    def _ids(value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        out: list[int] = []
        for item in value:
            upgrade_id = _parse_int(item)
            if upgrade_id is not None:
                out.append(upgrade_id)
        return out

    by_adventure = cfg.get("adventures")
    if adventure_id is not None and isinstance(by_adventure, dict):
        ids = _ids(by_adventure.get(str(adventure_id)))
        if ids:
            return ids, f"adventure-regel ({adventure_id})", None

    by_location = cfg.get("locations")
    if location_id is not None and isinstance(by_location, dict):
        ids = _ids(by_location.get(str(location_id)))
        if ids:
            return ids, f"locatie-regel ({location_id})", None

    by_campaign = cfg.get("campaigns")
    if campaign_id is not None and isinstance(by_campaign, dict):
        ids = _ids(by_campaign.get(str(campaign_id)))
        if ids:
            return ids, f"campaign-regel ({campaign_id})", None

    by_context = cfg.get("contexts")
    if isinstance(by_context, dict):
        ids = _ids(by_context.get(context))
        if ids:
            return ids, f"context-regel ({context})", None

    csv_ids, csv_source, csv_advice = _csv_choice_advice(
        hero_id,
        hero_name,
        seat=seat_by_hero.get(hero_id) if seat_by_hero else None,
        run_goal=resolved_run_goal,
        active_hero_ids=active_hero_ids,
        highest_damage_hero_id=highest_damage_hero_id,
        familiar_count=familiar_count,
        seat_by_hero=seat_by_hero,
        known_options=known_options,
        payload=payload,
    )
    authored_csv = bool(
        csv_ids and csv_advice and csv_advice.rule_source_type == "authored"
    )
    heuristic_csv = bool(
        csv_ids and csv_advice and csv_advice.rule_source_type == "heuristic"
    )

    def _resolve_dynamic() -> tuple[list[int], str] | None:
        if not active_hero_ids:
            return None
        loot_by_hero = None
        account_stats = None
        event_boon_count = 0
        modron_stacks = 0
        owned_hero_ids = None
        hero_upgrade_ids = None
        roster_filter = None
        if isinstance(payload, dict):
            details = payload.get("details")
            if isinstance(details, dict):
                from ic_gamedata.adventure_restrictions import build_adventure_roster_filter
                from ic_gamedata.loot_stats import loot_stats_by_hero
                from ic_gamedata.specialization_custom_stacks import (
                    event_boon_count_from_details,
                    hero_upgrade_ids_from_details,
                    modron_core_competency_stacks,
                    owned_hero_ids_from_details,
                )

                loot_by_hero = loot_stats_by_hero(details)
                raw_stats = details.get("stats")
                account_stats = raw_stats if isinstance(raw_stats, dict) else None
                event_boon_count = event_boon_count_from_details(details)
                modron_stacks = modron_core_competency_stacks(details)
                owned_hero_ids = owned_hero_ids_from_details(details)
                hero_upgrade_ids = hero_upgrade_ids_from_details(details)
                roster_filter = build_adventure_roster_filter(payload, adventure_id)
        preferred = _ids(cfg.get("default"))
        from ic_gamedata.specialization_advisor_model import (
            advisor_model_for_hero,
            preferred_ids_for_run_goal,
        )

        model = advisor_model_for_hero(hero_id)
        if model is not None:
            model_ids = preferred_ids_for_run_goal(model, run_goal=resolved_run_goal)
            if model_ids:
                preferred = model_ids
        return _dynamic_default_ids(
            hero_id,
            active_hero_ids,
            highest_damage_hero_id=highest_damage_hero_id,
            familiar_count=familiar_count,
            seat_by_hero=seat_by_hero,
            known_options=known_options,
            run_goal=resolved_run_goal,
            loot_by_hero=loot_by_hero,
            account_stats=account_stats,
            event_boon_count=event_boon_count,
            modron_core_competency_stacks=modron_stacks,
            owned_hero_ids=owned_hero_ids,
            hero_upgrade_ids=hero_upgrade_ids,
            roster_filter=roster_filter,
            preferred_ids=preferred,
        )

    if authored_csv:
        # CSV often covers only one tier (e.g. Regis Ahead). Fill open tiers
        # from formation handlers when available.
        if known_options and (cfg.get("default") is not None or hero_id in HERO_HANDLERS):
            dynamic = _resolve_dynamic()
            if dynamic is not None:
                merged = _supplement_missing_tier_ids(
                    known_options, csv_ids, dynamic[0]
                )
                if len(merged) > len(csv_ids):
                    return (
                        merged,
                        f"{csv_source}; {dynamic[1]}",
                        csv_advice,
                    )
        return csv_ids, csv_source, csv_advice

    if active_hero_ids and cfg.get("default") is not None:
        dynamic = _resolve_dynamic()
        if dynamic is not None:
            return (*dynamic, None)

    if heuristic_csv:
        return csv_ids, csv_source, csv_advice

    if csv_ids:
        return csv_ids, csv_source, csv_advice

    ids = _ids(cfg.get("default"))
    if ids:
        return ids, "default-regel", None
    baseline = _baseline_default_ids(hero_id, known_options or [])
    if baseline is not None:
        return (*baseline, None)
    return [], "geen regel", None


def pending_specializations(
    payload: dict[str, Any],
    rules: dict[str, Any] | None = None,
    *,
    context: str = "campaign",
    run_goal: str | None = None,
) -> list[PendingSpecialization]:
    rules = rules or load_specialization_rules()
    details = payload.get("details")
    instance = _active_instance(payload)
    active_party_id = _active_party_id(payload)
    if not isinstance(details, dict) or instance is None or active_party_id is None:
        return []

    adventure_id, campaign_id, location_id = _active_adventure_details(payload)
    highest_damage_hero_id = _active_highest_damage_hero_id(payload)
    familiar_count = familiar_party_count(payload)
    hero_name_map = _hero_name_map(rules)
    known_by_hero = _merge_known_options(payload, rules)
    active_hero_ids = _active_hero_ids(instance)
    seat_by_hero = _seat_by_hero(instance)
    heroes = details.get("heroes")
    if not isinstance(heroes, list):
        return []

    pending: list[PendingSpecialization] = []
    for hero_id in sorted(active_hero_ids):
        hero = merged_hero_record_for_specializations(
            payload,
            hero_id,
            active_party_id=active_party_id,
            active_hero_ids=active_hero_ids,
        )
        if hero is None:
            continue

        known_options = known_by_hero.get(hero_id, [])
        if not known_options:
            continue
        level = _parse_int(hero.get("level")) or 0
        current_choices = _current_choices(hero, known_options)
        game_instance_id = _parse_int(hero.get("game_instance_id"))
        tiers: dict[int, list[SpecializationOption]] = {}
        for opt in known_options:
            tiers.setdefault(opt.tier_index, []).append(opt)

        hero_name = (
            hero_name_map.get(hero_id)
            or (rules.get("heroes", {}).get(str(hero_id), {}) or {}).get("name")
            or f"Hero {hero_id}"
        )

        desired_ids, rule_source, csv_advice = _desired_choice_ids(
            hero_id,
            hero_name,
            rules,
            adventure_id=adventure_id,
            campaign_id=campaign_id,
            location_id=location_id,
            context=context,
            run_goal=run_goal,
            active_hero_ids=active_hero_ids,
            highest_damage_hero_id=highest_damage_hero_id,
            familiar_count=familiar_count,
            seat_by_hero=seat_by_hero,
            known_options=known_options,
            payload=payload,
        )

        for tier_index in sorted(tiers):
            options = tuple(sorted(tiers[tier_index], key=lambda opt: opt.upgrade_id))
            if not options:
                continue
            required_level = options[0].required_level
            if level < required_level:
                continue
            if _tier_is_chosen(hero, options, known_options):
                continue

            desired_upgrade_id = next((item for item in desired_ids if any(opt.upgrade_id == item for opt in options)), None)
            desired_option_index = None
            reason = "geen regel"
            rationale = "Geen specialization-regel gevonden voor deze champion."
            if desired_upgrade_id is not None:
                for index, option in enumerate(options):
                    if option.upgrade_id == desired_upgrade_id:
                        desired_option_index = index
                        reason = "regel match"
                        rationale = f"Gekozen via {rule_source}: {option.name}."
                        break
            elif desired_ids:
                reason = "regel past niet op deze tier"
                rationale = f"Er is wel een {rule_source}, maar die bevat geen keuze voor deze specialization-tier."

            pending.append(
                PendingSpecialization(
                    hero_id=hero_id,
                    hero_name=hero_name,
                    seat=seat_by_hero.get(hero_id),
                    game_instance_id=(
                        game_instance_id
                        if game_instance_id is not None and game_instance_id > 0
                        else active_party_id
                    ),
                    current_choices=current_choices,
                    options=options,
                    desired_upgrade_id=desired_upgrade_id,
                    desired_option_index=desired_option_index,
                    reason=reason,
                    rationale=rationale,
                    advice_source=csv_advice.source if csv_advice else "",
                    confidence=csv_advice.confidence if csv_advice else 0,
                    manual_review=csv_advice.manual_review if csv_advice else "no",
                    condition_used=csv_advice.condition_used if csv_advice else "",
                    data_source_version=csv_advice.data_source_version if csv_advice else "",
                    rule_source_type=csv_advice.rule_source_type if csv_advice else "",
                )
            )
    pending.sort(key=lambda item: (item.seat is None, item.seat or 99, item.hero_id))
    return pending


def format_specialization_advice(
    payload: dict[str, Any],
    pending: list[PendingSpecialization],
) -> str:
    actionable = [
        item for item in pending if item.desired_option_index is not None
    ]
    if not actionable:
        return "Geen specialization-advies nodig."
    pending = actionable
    context = _active_adventure_context(payload)
    header_parts: list[str] = []
    adventure_name = context.get("adventure_name")
    campaign_name = context.get("campaign_name")
    if isinstance(adventure_name, str) and adventure_name:
        header_parts.append(f"Adventure: {adventure_name}")
    if isinstance(campaign_name, str) and campaign_name:
        header_parts.append(f"Campaign: {campaign_name}")
    lines: list[str] = []
    if header_parts:
        lines.append(" | ".join(header_parts))
    for item in pending:
        options = " / ".join(option.name for option in item.options)
        seat_text = f"seat {item.seat}" if item.seat is not None else "onbekende seat"
        if item.desired_option_index is not None:
            chosen = item.options[item.desired_option_index].name
            extra_lines: list[str] = []
            if item.data_source_version:
                extra_lines.append(f"Dataset: {item.data_source_version}")
            if item.rule_source_type:
                extra_lines.append(f"Regelkwaliteit: {item.rule_source_type}")
            if item.advice_source:
                extra_lines.append(f"Bron: {item.advice_source}")
            if item.confidence:
                extra_lines.append(f"Confidence: {item.confidence}/5")
            if item.manual_review and item.manual_review != "no":
                extra_lines.append(f"Manual review: {item.manual_review}")
            if item.condition_used:
                extra_lines.append(f"Condition: {item.condition_used}")
            extra_block = ("\n" + "\n".join(extra_lines)) if extra_lines else ""
            lines.append(
                f"{item.hero_name} ({seat_text})\n"
                f"Advies: {chosen}\n"
                f"Waarom: {human_specialization_reason(item, context)}\n"
                f"Open opties: {options}{extra_block}"
            )
        else:
            lines.append(
                f"{item.hero_name} ({seat_text})\n"
                f"Advies: nog geen vaste keuze\n"
                f"Waarom: {human_specialization_reason(item, context)}\n"
                f"Open opties: {options}"
            )
    return "\n\n".join(lines)

