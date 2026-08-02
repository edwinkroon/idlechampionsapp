"""Persistent farm health / copilot event log."""

from __future__ import annotations

import json
from typing import Any

from ic_gamedata.gem_farm.models import FarmEvent, FarmHealthAlert
from ic_gamedata.paths import FARM_HEALTH_EVENTS_PATH

_MAX_EVENTS = 200


def _event_to_dict(event: FarmEvent) -> dict[str, Any]:
    return {
        "timestamp": event.timestamp,
        "party_index": event.party_index,
        "kind": event.kind,
        "rule_id": event.rule_id,
        "severity": event.severity,
        "message": event.message,
        "detail": event.detail,
    }


def _event_from_dict(raw: dict[str, Any]) -> FarmEvent | None:
    try:
        return FarmEvent(
            timestamp=float(raw["timestamp"]),
            party_index=int(raw["party_index"]),
            kind=str(raw.get("kind") or "health"),
            rule_id=str(raw.get("rule_id") or ""),
            severity=str(raw.get("severity") or "info"),  # type: ignore[arg-type]
            message=str(raw.get("message") or ""),
            detail=str(raw.get("detail") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_farm_events(path=None) -> tuple[FarmEvent, ...]:
    file_path = path or FARM_HEALTH_EVENTS_PATH
    if not file_path.is_file():
        return ()
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    events: list[FarmEvent] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        event = _event_from_dict(item)
        if event is not None:
            events.append(event)
    return tuple(events)


def save_farm_events(events: tuple[FarmEvent, ...], path=None) -> None:
    file_path = path or FARM_HEALTH_EVENTS_PATH
    file_path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = events[-_MAX_EVENTS:]
    payload = [_event_to_dict(event) for event in trimmed]
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_farm_event(event: FarmEvent, path=None) -> None:
    existing = load_farm_events(path)
    save_farm_events((*existing, event), path)


def log_health_alerts(
    *,
    party_index: int,
    alerts: tuple[FarmHealthAlert, ...],
    previous_rule_ids: frozenset[str],
    now: float,
    path=None,
) -> frozenset[str]:
    """Append events for newly active alert rules; return current rule ids."""
    current_ids = frozenset(alert.rule_id for alert in alerts)
    for alert in alerts:
        if alert.rule_id in previous_rule_ids:
            continue
        append_farm_event(
            FarmEvent(
                timestamp=now,
                party_index=party_index,
                kind="health",
                rule_id=alert.rule_id,
                severity=alert.severity,
                message=alert.message,
                detail=alert.detail,
            ),
            path=path,
        )
    return current_ids
