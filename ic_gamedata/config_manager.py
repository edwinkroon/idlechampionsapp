"""Central access to local JSON configuration files."""

from __future__ import annotations

import json
from typing import Any

from ic_gamedata.goal_run_history_store import load_goal_run_history, save_goal_run_history
from ic_gamedata.paths import GAMEDATA_CONFIG_PATH
from ic_gamedata.stats_models import GoalRunRecord


class ConfigManager:
    """Load and persist `config/gamedata.json` and goal-run history."""

    def __init__(self, *, gamedata_path=None, goal_history_path=None) -> None:
        self._gamedata_path = gamedata_path or GAMEDATA_CONFIG_PATH

    def load_gamedata(self) -> dict[str, Any]:
        path = self._gamedata_path
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save_gamedata(self, data: dict[str, Any]) -> None:
        path = self._gamedata_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._invalidate_modron_cache()

    def install_path(self) -> str | None:
        value = self.load_gamedata().get("install_path")
        return value.strip() if isinstance(value, str) and value.strip() else None

    def set_install_path(self, install_path: str) -> None:
        data = self.load_gamedata()
        data["install_path"] = install_path.strip()
        self.save_gamedata(data)

    def party_modron_goals(self) -> dict[int, int]:
        raw = self.load_gamedata().get("party_modron_goals")
        if not isinstance(raw, dict):
            return {}
        goals: dict[int, int] = {}
        for key, value in raw.items():
            try:
                party_index = int(key)
                goal = int(value)
            except (TypeError, ValueError):
                continue
            if goal > 0:
                goals[party_index] = goal
        return goals

    def load_goal_run_history(self) -> dict[int, list[GoalRunRecord]]:
        return load_goal_run_history()

    def save_goal_run_history(self, history: dict[int, list[GoalRunRecord]]) -> None:
        save_goal_run_history(history)

    def clear_goal_run_history(self, party_index: int | None = None) -> dict[int, list[GoalRunRecord]]:
        from ic_gamedata.goal_run_history_store import clear_goal_run_history

        return clear_goal_run_history(party_index)

    @staticmethod
    def _invalidate_modron_cache() -> None:
        try:
            from ic_gamedata import modron_area_goal

            modron_area_goal._load_gamedata.cache_clear()
        except (ImportError, AttributeError):
            pass
