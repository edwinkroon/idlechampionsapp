"""Build evaluation context from live game payload and formation metrics."""

from __future__ import annotations

from typing import Any

from ic_gamedata.specialization_engine import (
    FormationContext,
    _hero_attack_types_map_from_cached_definitions,
    _hero_tags_map_from_cached_definitions,
    formation_metrics,
)
from ic_gamedata.specialization_rules.models import EvaluationContext


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def build_evaluation_context(
    *,
    hero_id: int,
    hero_name: str,
    seat: int | None,
    run_goal: str,
    formation: FormationContext,
    payload: dict[str, Any] | None = None,
    previous_enemy_type: str | None = None,
    previous_alignment_leader: str | None = None,
) -> EvaluationContext:
    metrics = formation_metrics(formation.active_hero_ids)
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    attack_types = _hero_attack_types_map_from_cached_definitions()

    neutral_count = 0
    for hid in formation.active_hero_ids:
        tags = set(tags_by_hero.get(hid, ()))
        if "neutral" in tags:
            neutral_count += 1

    magic_count = sum(
        1 for hid in formation.active_hero_ids if "magic" in attack_types.get(hid, frozenset())
    )
    melee_count = sum(
        1 for hid in formation.active_hero_ids if "melee" in attack_types.get(hid, frozenset())
    )

    enemy_type = _enemy_type_from_payload(payload)
    alignment_leader = _alignment_leader(metrics.evil_count, metrics.good_count, neutral_count)
    alignment_distribution_changed = (
        previous_alignment_leader is not None and previous_alignment_leader != alignment_leader
    )
    enemy_type_changed = (
        previous_enemy_type is not None
        and enemy_type is not None
        and previous_enemy_type != enemy_type
    )
    secondary_bond_outscores_primary = metrics.dwarf_elf_count >= max(metrics.human_count, 1)

    return EvaluationContext(
        hero_id=hero_id,
        hero_name=hero_name,
        seat=seat,
        run_goal=run_goal,
        active_hero_ids=frozenset(formation.active_hero_ids),
        seat_by_hero=dict(formation.seat_by_hero or {}),
        highest_damage_hero_id=formation.highest_damage_hero_id,
        familiar_count=formation.familiar_count,
        evil_count=metrics.evil_count,
        good_count=metrics.good_count,
        neutral_count=neutral_count,
        magic_count=magic_count,
        melee_count=melee_count,
        dwarf_elf_count=metrics.dwarf_elf_count,
        enemy_type=enemy_type,
        adventure_name=_adventure_name(payload),
        alignment_distribution_changed=alignment_distribution_changed,
        enemy_type_changed=enemy_type_changed,
        secondary_bond_outscores_primary=secondary_bond_outscores_primary,
        survival_blocks_progress=run_goal == "survival",
    )


def champion_names_match(left: str, right: str) -> bool:
    return _normalize_name(left) == _normalize_name(right)


def _alignment_leader(evil: int, good: int, neutral: int) -> str:
    counts = {"evil": evil, "good": good, "neutral": neutral}
    return max(counts, key=counts.get)


def _adventure_name(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = details.get("active_game_instance_id")
    instances = details.get("game_instances")
    if not isinstance(instances, list):
        return None
    adventure_id = None
    for inst in instances:
        if isinstance(inst, dict) and str(inst.get("game_instance_id")) == str(active_id):
            adventure_id = inst.get("current_adventure_id")
            break
    if adventure_id is None:
        return None
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return None
    adventures = defines.get("adventure_defines")
    if not isinstance(adventures, list):
        return None
    for adv in adventures:
        if isinstance(adv, dict) and str(adv.get("id")) == str(adventure_id):
            name = adv.get("name")
            return name.strip() if isinstance(name, str) else None
    return None


def _enemy_type_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    text_parts: list[str] = []
    defines = payload.get("defines")
    if isinstance(defines, dict):
        adventures = defines.get("adventure_defines")
        details = payload.get("details")
        active_id = details.get("active_game_instance_id") if isinstance(details, dict) else None
        if isinstance(adventures, list) and active_id is not None and isinstance(details, dict):
            adventure_id = None
            for inst in details.get("game_instances") or []:
                if isinstance(inst, dict) and str(inst.get("game_instance_id")) == str(active_id):
                    adventure_id = inst.get("current_adventure_id")
                    break
            for adv in adventures:
                if isinstance(adv, dict) and str(adv.get("id")) == str(adventure_id):
                    restrictions = adv.get("restrictions_text")
                    if isinstance(restrictions, str):
                        text_parts.append(restrictions.casefold())
    joined = " ".join(text_parts)
    for candidate in (
        "humanoid",
        "undead",
        "fiend",
        "dragon",
        "aberration",
        "monstrosity",
        "beast",
        "construct",
    ):
        if candidate in joined:
            return candidate
    return None
