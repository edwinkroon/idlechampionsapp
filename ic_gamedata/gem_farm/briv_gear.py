"""Parse Briv slot-4 gear from getuserdetails loot."""

from __future__ import annotations

from typing import Any

from ic_gamedata.gem_farm.models import BrivGear, BrivGearOverride
from ic_gamedata.loot_stats import _best_loot_by_hero_slot
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_display import BRIV_HERO_ID

BRIV_SPEED_SLOT_ID = 4

RARITY_LABELS = {
    1: "Common",
    2: "Uncommon",
    3: "Rare",
    4: "Epic",
}

GILD_LABELS = {
    0: "None",
    1: "Shiny",
    2: "Golden",
}


def _format_item_level(enchant: int) -> str:
    level = max(enchant, 0) + 1
    if level >= 1_000_000_000:
        return f"{level / 1_000_000_000:.1f}B"
    if level >= 1_000_000:
        return f"{level / 1_000_000:.1f}M"
    if level >= 1_000:
        return f"{level / 1_000:.1f}K"
    return str(level)


def parse_briv_slot4_from_payload(
    payload: dict[str, Any] | None,
    *,
    override: BrivGearOverride | None = None,
) -> BrivGear | None:
    if override is not None and override.enchant is not None:
        enchant = max(0, override.enchant - 1)
        rarity = override.rarity if override.rarity is not None else 4
        gild = override.gild if override.gild is not None else 0
        return BrivGear(
            hero_id=BRIV_HERO_ID,
            slot_id=BRIV_SPEED_SLOT_ID,
            enchant=enchant,
            item_level=enchant + 1,
            item_level_label=_format_item_level(enchant),
            rarity=rarity,
            rarity_label=RARITY_LABELS.get(rarity, f"R{rarity}"),
            gild=gild,
            gild_label=GILD_LABELS.get(gild, str(gild)),
            source="override",
        )

    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    loot = details.get("loot")
    if not isinstance(loot, list):
        return None
    items = _best_loot_by_hero_slot(loot)
    item = items.get((BRIV_HERO_ID, BRIV_SPEED_SLOT_ID))
    if item is None:
        return None
    enchant = _parse_int(item.get("enchant")) or 0
    rarity = _parse_int(item.get("rarity")) or 1
    gild = _parse_int(item.get("gild")) or 0
    return BrivGear(
        hero_id=BRIV_HERO_ID,
        slot_id=BRIV_SPEED_SLOT_ID,
        enchant=enchant,
        item_level=enchant + 1,
        item_level_label=_format_item_level(enchant),
        rarity=rarity,
        rarity_label=RARITY_LABELS.get(rarity, f"R{rarity}"),
        gild=gild,
        gild_label=GILD_LABELS.get(gild, str(gild)),
        source="api",
    )
