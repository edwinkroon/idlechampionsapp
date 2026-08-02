"""Persist completed area-goal run durations across app restarts."""

from __future__ import annotations

import json
from typing import Any

from ic_gamedata.paths import GOAL_RUN_HISTORY_PATH
from ic_gamedata.stats_models import (
    MAX_GOAL_RUN_HISTORY,
    GoalRunRecord,
    is_plausible_goal_run_record,
)


def _record_to_dict(record: GoalRunRecord) -> dict[str, Any]:
    return {
        "duration_sec": record.duration_sec,
        "area_goal": record.area_goal,
        "peak_area": record.peak_area,
        "recorded_at": record.recorded_at,
        "duration_unreliable": record.duration_unreliable,
    }


def _record_from_dict(raw: dict[str, Any]) -> GoalRunRecord | None:
    try:
        duration = float(raw["duration_sec"])
        area_goal = int(raw["area_goal"])
    except (KeyError, TypeError, ValueError):
        return None
    peak_raw = raw.get("peak_area")
    peak_area = int(peak_raw) if peak_raw is not None else None
    recorded_at = float(raw.get("recorded_at") or 0.0)
    duration_unreliable = bool(raw.get("duration_unreliable", False))
    return GoalRunRecord(
        duration_sec=duration,
        area_goal=area_goal,
        peak_area=peak_area,
        recorded_at=recorded_at,
        duration_unreliable=duration_unreliable,
    )


def load_goal_run_history() -> dict[int, list[GoalRunRecord]]:
    path = GOAL_RUN_HISTORY_PATH
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_parties = payload.get("parties")
    if not isinstance(raw_parties, dict):
        return {}
    history: dict[int, list[GoalRunRecord]] = {}
    dirty = False
    for key, raw_records in raw_parties.items():
        try:
            party_index = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(raw_records, list):
            continue
        records: list[GoalRunRecord] = []
        for item in raw_records[:MAX_GOAL_RUN_HISTORY]:
            if not isinstance(item, dict):
                dirty = True
                continue
            record = _record_from_dict(item)
            if record is None:
                dirty = True
                continue
            if not is_plausible_goal_run_record(record):
                dirty = True
                continue
            records.append(record)
        if records:
            history[party_index] = records
        elif raw_records:
            dirty = True
    dirty = _strip_implausible_records(history) or dirty
    if dirty:
        save_goal_run_history(history)
    return history


def _strip_implausible_records(history: dict[int, list[GoalRunRecord]]) -> bool:
    """Return True if any corrupt records were removed."""
    changed = False
    for party_index, records in list(history.items()):
        filtered = [record for record in records if is_plausible_goal_run_record(record)]
        if len(filtered) != len(records):
            changed = True
            if filtered:
                history[party_index] = filtered
            else:
                del history[party_index]
    return changed


def save_goal_run_history(history: dict[int, list[GoalRunRecord]]) -> None:
    path = GOAL_RUN_HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "parties": {
            str(party_index): [_record_to_dict(record) for record in records[:MAX_GOAL_RUN_HISTORY]]
            for party_index, records in sorted(history.items())
            if records
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_goal_run_history(party_index: int | None = None) -> dict[int, list[GoalRunRecord]]:
    """Clear persisted history for one party, or all parties when party_index is None."""
    if party_index is None:
        history: dict[int, list[GoalRunRecord]] = {}
    else:
        history = load_goal_run_history()
        history.pop(party_index, None)
    save_goal_run_history(history)
    return history
