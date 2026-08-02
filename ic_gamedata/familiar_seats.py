"""Seats with a familiar assigned to level the champion (skip F-key leveling)."""

from __future__ import annotations

from typing import Any

from ic_gamedata.formation_seats import _active_instance, _parse_int

# Seat 99 = unassigned / reserve slot in live API (not F1–F12).
_RESERVED_SEATS = frozenset({99})


def _seat_from_assignment(assignment: Any, active_id: int | None) -> int | None:
    """
    Parse familiar assignment → champion F-key seat (1–12) for the active party.

    Live API shape (typical)::

        {"Seat": 4, "game_instance_id": 2}
        {"Clicks": 0, "game_instance_id": 1}   # click/` slot — ignored

    Legacy list shape::

        ["Seat", 4]
    """
    if not assignment:
        return None

    if isinstance(assignment, dict):
        if "Clicks" in assignment or "Ultimates" in assignment:
            return None
        if "Seat" not in assignment:
            return None
        game_id = _parse_int(assignment.get("game_instance_id"))
        if (
            game_id is not None
            and game_id > 0
            and active_id is not None
            and game_id != active_id
        ):
            return None
        seat = _parse_int(assignment.get("Seat"))
        if seat is None or seat in _RESERVED_SEATS:
            return None
        if 1 <= seat <= 12:
            return seat
        return None

    if isinstance(assignment, list) and len(assignment) >= 2:
        kind = str(assignment[0]).strip().lower()
        if kind != "seat":
            return None
        seat = _parse_int(assignment[1])
        if seat is None or seat in _RESERVED_SEATS:
            return None
        if 1 <= seat <= 12:
            return seat

    return None


def _seats_from_familiar_list(
    familiars: Any,
    active_id: int | None,
) -> set[int]:
    seats: set[int] = set()
    if not isinstance(familiars, list):
        return seats
    for fam in familiars:
        if not isinstance(fam, dict):
            continue
        seat = _seat_from_assignment(fam.get("assignment"), active_id)
        if seat is not None:
            seats.add(seat)
    return seats


def familiar_level_seats(payload: dict[str, Any]) -> frozenset[int]:
    """
    Return F-key seats (1–12) on the active party where a familiar levels the champion.
    """
    details = payload.get("details")
    if not isinstance(details, dict):
        return frozenset()

    active_id, _ = _active_instance(payload)
    seats = _seats_from_familiar_list(details.get("familiars"), active_id)
    return frozenset(sorted(seats))


def _familiar_assigned_to_party(assignment: Any, active_id: int | None) -> bool:
    """True when a familiar assignment belongs to the active party (any slot type)."""
    if not assignment:
        return False
    if isinstance(assignment, dict):
        game_id = _parse_int(assignment.get("game_instance_id"))
        if game_id is not None and game_id > 0:
            if active_id is None or game_id != active_id:
                return False
        if "Seat" in assignment:
            seat = _parse_int(assignment.get("Seat"))
            if seat is None or seat in _RESERVED_SEATS:
                return False
        return bool(assignment)
    if isinstance(assignment, list) and len(assignment) >= 2:
        kind = str(assignment[0]).strip().lower()
        if kind == "seat":
            seat = _parse_int(assignment[1])
            if seat is None or seat in _RESERVED_SEATS:
                return False
        return kind in {"seat", "clicks", "ultimates", "level_up_1", "level_up_2"}
    return False


def familiar_party_count(payload: dict[str, Any]) -> int:
    """Return familiars assigned to the active party (Seat, Clicks, Ultimates, etc.)."""
    details = payload.get("details")
    if not isinstance(details, dict):
        return 0
    active_id, _ = _active_instance(payload)
    familiars = details.get("familiars")
    if not isinstance(familiars, list):
        return 0
    return sum(
        1
        for fam in familiars
        if isinstance(fam, dict)
        and _familiar_assigned_to_party(fam.get("assignment"), active_id)
    )
