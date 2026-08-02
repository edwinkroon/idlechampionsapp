"""Resolve buff_id → human-readable name from game files and API payload."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.specialization_data import cached_definitions_data

_EFFECT_LABELS: dict[str, str] = {
    "time_scale": "Speed potion",
    "gold_multiplier_mult": "Gold potion",
    "global_dps_multiplier_mult": "DPS potion",
    "global_health_mult": "Health potion",
    "click_damage_seconds_global_dps": "Click potion",
    "modron_bonus_mult": "Modron potion",
    "gem_drop_multiplier_mult": "Gem potion",
}

_DESC_KEY_LABELS: dict[str, str] = {
    "boon_buff_desc_dmg": "Boon: damage",
    "boon_buff_desc_gold": "Boon: gold",
    "boon_buff_desc_health": "Boon: health",
    "boon_buff_desc_click_dmg": "Boon: click damage",
    "boon_buff_desc_speed": "Boon: speed",
}


def _label_from_buff_define(item: dict[str, Any]) -> str | None:
    name = item.get("name") or item.get("title") or item.get("display_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    effect = item.get("effect") or item.get("effect_string")
    if isinstance(effect, str):
        effect_key = effect.split(",", 1)[0].strip()
        label = _EFFECT_LABELS.get(effect_key)
        if label:
            return label
    effect_key = str(item.get("effect_key") or "").strip()
    if effect_key:
        label = _EFFECT_LABELS.get(effect_key)
        if label:
            return label
    desc_key = str(item.get("general_desc_key") or item.get("tooltip_desc_key") or "").strip()
    if desc_key:
        return _DESC_KEY_LABELS.get(desc_key, desc_key.replace("_", " ").replace("boon buff desc ", "Boon: "))
    return None


@lru_cache(maxsize=1)
def buff_name_map_from_cached_definitions() -> dict[int, str]:
    """Names from IdleDragons …/cached_definitions.json (buff_defines)."""
    data = cached_definitions_data()
    out: dict[int, str] = {}
    for key in ("buff_defines", "boon_buff_defines", "season_buff_defines"):
        items = data.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            buff_id = _parse_int(item.get("id"))
            if buff_id is None:
                continue
            label = _label_from_buff_define(item)
            if label:
                out[buff_id] = label
    return out


def _merge_buff_name(out: dict[int, str], buff_id: int | None, label: str | None) -> None:
    if buff_id is None or not label or not str(label).strip():
        return
    text = str(label).strip()
    if buff_id not in out:
        out[buff_id] = text


def _scan_loot_for_buffs(node: Any, out: dict[int, str], *, parent_name: str | None = None) -> None:
    if isinstance(node, dict):
        name = node.get("name") or node.get("promo_buff_title") or parent_name
        if isinstance(name, str):
            name = name.strip() or None
        buff_id = _parse_int(node.get("buff_id"))
        if buff_id is not None and name:
            _merge_buff_name(out, buff_id, name)
        for key, value in node.items():
            if key == "loot" and isinstance(value, list) and name:
                for entry in value:
                    if isinstance(entry, dict):
                        bid = _parse_int(entry.get("buff_id"))
                        _merge_buff_name(out, bid, name)
            else:
                _scan_loot_for_buffs(value, out, parent_name=name if isinstance(name, str) else parent_name)
    elif isinstance(node, list):
        for item in node:
            _scan_loot_for_buffs(item, out, parent_name=parent_name)


def buff_name_map_from_payload(payload: dict[str, Any] | None) -> dict[int, str]:
    """Event/promo/shop buff names present in a getuserdetails payload."""
    if not isinstance(payload, dict):
        return {}
    out: dict[int, str] = {}

    details = payload.get("details")
    if isinstance(details, dict):
        for event in details.get("event_details") or []:
            if not isinstance(event, dict):
                continue
            event_details = event.get("details")
            if not isinstance(event_details, dict):
                continue
            buff_id = _parse_int(event_details.get("buff_id"))
            label = (
                event_details.get("promo_buff_title")
                or event.get("name")
                or event.get("analytics_name")
            )
            if isinstance(label, str):
                _merge_buff_name(out, buff_id, label)

        for key in ("package_deals", "promotions", "current_sales"):
            items = details.get(key)
            if isinstance(items, list):
                _scan_loot_for_buffs(items, out)

    defines = payload.get("defines")
    if isinstance(defines, dict):
        for key in ("boon_buff_defines", "buff_defines", "season_buff_defines"):
            items = defines.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                buff_id = _parse_int(item.get("id"))
                label = _label_from_buff_define(item)
                if label:
                    _merge_buff_name(out, buff_id, label)

    return out


def build_buff_name_map(payload: dict[str, Any] | None = None) -> dict[int, str]:
    merged: dict[int, str] = {}
    for source in (
        buff_name_map_from_cached_definitions(),
        buff_name_map_from_payload(payload),
    ):
        for buff_id, label in source.items():
            merged.setdefault(buff_id, label)
    return merged


def buff_display_name(buff_id: int, payload: dict[str, Any] | None = None) -> str:
    label = build_buff_name_map(payload).get(buff_id)
    if label:
        return label
    return "Onbekende buff"
