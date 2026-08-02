"""Per-hero equipment stats from API loot payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ic_gamedata.adventure_restrictions import _parse_int

RARITY_EPIC = 4
MIN_GILD_SHINY = 1
MAX_ILVL_PER_HERO = 1800


@dataclass(frozen=True)
class HeroLootStats:
    epic_gear_count: int = 0
    shiny_gear_count: int = 0
    total_ilvl: int = 0


def _slot_item_rank(item: dict[str, Any]) -> tuple[int, int, int]:
    enchant = _parse_int(item.get("enchant")) or 0
    rarity = _parse_int(item.get("rarity")) or 0
    gild = _parse_int(item.get("gild")) or 0
    return (max(enchant, 0), rarity, gild)


def _best_loot_by_hero_slot(loot: list[Any]) -> dict[tuple[int, int], dict[str, Any]]:
    best: dict[tuple[int, int], dict[str, Any]] = {}
    for item in loot:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("hero_id"))
        slot_id = _parse_int(item.get("slot_id"))
        if hero_id is None or slot_id is None:
            continue
        key = (hero_id, slot_id)
        current = best.get(key)
        if current is None or _slot_item_rank(item) > _slot_item_rank(current):
            best[key] = item
    return best


def hero_loot_stats_from_items(items: dict[tuple[int, int], dict[str, Any]], hero_id: int) -> HeroLootStats:
    epic = shiny = total_ilvl = 0
    for (hid, _slot_id), item in items.items():
        if hid != hero_id:
            continue
        rarity = _parse_int(item.get("rarity")) or 0
        gild = _parse_int(item.get("gild")) or 0
        enchant = _parse_int(item.get("enchant")) or 0
        if rarity >= RARITY_EPIC:
            epic += 1
        if gild >= MIN_GILD_SHINY:
            shiny += 1
        total_ilvl += max(enchant, 0) + 1
    return HeroLootStats(
        epic_gear_count=epic,
        shiny_gear_count=shiny,
        total_ilvl=min(total_ilvl, MAX_ILVL_PER_HERO),
    )


def loot_stats_by_hero(details: dict[str, Any]) -> dict[int, HeroLootStats]:
    loot = details.get("loot")
    if not isinstance(loot, list):
        return {}
    items = _best_loot_by_hero_slot(loot)
    hero_ids = {hero_id for hero_id, _slot in items}
    return {hero_id: hero_loot_stats_from_items(items, hero_id) for hero_id in hero_ids}


def formation_loot_stack_totals(
    active_hero_ids: set[int],
    loot_by_hero: dict[int, HeroLootStats] | None,
) -> tuple[int, int, int]:
    """Return (epic_gear, total_ilvl, shiny_gear) stack counts for active formation."""
    if not loot_by_hero:
        return 0, 0, 0
    epic = shiny = ilvl = 0
    for hero_id in active_hero_ids:
        stats = loot_by_hero.get(hero_id)
        if stats is None:
            continue
        epic += stats.epic_gear_count
        shiny += stats.shiny_gear_count
        ilvl += stats.total_ilvl
    return epic, ilvl, shiny
