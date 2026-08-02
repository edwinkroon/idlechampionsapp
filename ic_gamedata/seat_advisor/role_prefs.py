"""Persist champion role preferences per goal (BUD / gold)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.seat_advisor.models import SeatRole, STANDARD_SEAT_ROLES

_PREFS_FILENAME = "champion_role_preferences.json"
_VALID_GOALS = frozenset({"bud", "gold"})

if getattr(sys, "frozen", False):
    _CONFIG_BASE = Path(sys.executable).parent
else:
    _CONFIG_BASE = Path(__file__).resolve().parent.parent.parent


def _prefs_path() -> Path:
    return _CONFIG_BASE / "config" / _PREFS_FILENAME


def load_role_preferences() -> dict[int, dict[str, str]]:
    path = _prefs_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[int, dict[str, str]] = {}
    for hero_raw, goals_raw in raw.items():
        hero_id = _parse_int(hero_raw)
        if hero_id is None or not isinstance(goals_raw, dict):
            continue
        mapped: dict[str, str] = {}
        for goal_raw, role_raw in goals_raw.items():
            goal = str(goal_raw).strip().lower()
            role = str(role_raw).strip().lower()
            if goal in _VALID_GOALS and role in STANDARD_SEAT_ROLES:
                mapped[goal] = role
        if mapped:
            result[hero_id] = mapped
    return result


def save_role_preferences(prefs: dict[int, dict[str, str]]) -> None:
    path = _prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {str(hid): goals for hid, goals in sorted(prefs.items())}
    path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_chosen_role(hero_id: int, goal: str, prefs: dict[int, dict[str, str]] | None = None) -> SeatRole | None:
    store = prefs if prefs is not None else load_role_preferences()
    role = store.get(hero_id, {}).get(goal)
    if role in STANDARD_SEAT_ROLES:
        return role  # type: ignore[return-value]
    return None


def set_chosen_role(hero_id: int, goal: str, role: SeatRole | None) -> dict[int, dict[str, str]]:
    prefs = load_role_preferences()
    if role is None:
        if hero_id in prefs:
            prefs[hero_id].pop(goal, None)
            if not prefs[hero_id]:
                del prefs[hero_id]
    else:
        prefs.setdefault(hero_id, {})[goal] = role
    save_role_preferences(prefs)
    return prefs
