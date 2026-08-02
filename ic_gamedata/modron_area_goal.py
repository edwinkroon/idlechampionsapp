"""Resolve Modron automation reset area (Set Area Goal) for a party."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.paths import GAMEDATA_CONFIG_PATH

_MODRON_AREA_KEY_HINTS = ("reset", "goal", "target", "automation", "modron")


@lru_cache(maxsize=1)
def _load_gamedata() -> dict[str, Any]:
    if not GAMEDATA_CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(GAMEDATA_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def party_modron_goal_override(party_index: int) -> int | None:
    raw = _load_gamedata().get("party_modron_goals")
    if not isinstance(raw, dict):
        return None
    value = raw.get(str(party_index), raw.get(party_index))
    parsed = _parse_int(value)
    if parsed is not None and parsed > 0:
        return parsed
    return None


def _key_looks_like_modron_area(key: str) -> bool:
    lowered = key.lower()
    if "area" not in lowered:
        return False
    return any(hint in lowered for hint in _MODRON_AREA_KEY_HINTS)


def _scan_mapping_for_modron_area(mapping: dict[str, Any]) -> int | None:
    for key, value in mapping.items():
        if not isinstance(key, str) or not _key_looks_like_modron_area(key):
            continue
        parsed = _parse_int(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def modron_area_goal_from_modron_saves(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    saves = details.get("modron_saves")
    if not isinstance(saves, list):
        return None
    for save in saves:
        if not isinstance(save, dict):
            continue
        goal = _scan_mapping_for_modron_area(save)
        if goal is not None:
            return goal
        automation = save.get("automation")
        if isinstance(automation, dict):
            goal = _scan_mapping_for_modron_area(automation)
            if goal is not None:
                return goal
    return None


def modron_area_goal_from_instance(instance: dict[str, Any]) -> int | None:
    for key in (
        "modron_reset_area",
        "automation_reset_area",
        "automation_area_goal",
        "modron_area_goal",
    ):
        parsed = _parse_int(instance.get(key))
        if parsed is not None and parsed > 0:
            return parsed
    automation = instance.get("automation")
    if isinstance(automation, dict):
        goal = _scan_mapping_for_modron_area(automation)
        if goal is not None:
            return goal
    auto_reset = instance.get("auto_reset_stats")
    if isinstance(auto_reset, dict):
        goal = _scan_mapping_for_modron_area(auto_reset)
        if goal is not None:
            return goal
    return None


def resolve_modron_area_goal(
    instance: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    party_index: int | None,
    memory_modron_area: int | None = None,
) -> int | None:
    """
    Return the Modron \"Set Area Goal\" reset level for one party.

    Priority: config override → live memory → modron_saves / instance fields.
    Does not use stats.adventure_area_goal — that field is often a patron/adventure
    milestone (e.g. 275) rather than your Modron reset (e.g. 225).
    """
    if party_index is not None:
        override = party_modron_goal_override(party_index)
        if override is not None:
            return override
    if memory_modron_area is not None and memory_modron_area > 0:
        return memory_modron_area
    if isinstance(instance, dict):
        goal = modron_area_goal_from_instance(instance)
        if goal is not None:
            return goal
    goal = modron_area_goal_from_modron_saves(payload)
    if goal is not None:
        return goal
    return None
