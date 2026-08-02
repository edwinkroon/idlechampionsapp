"""Detect which champion seats are currently in the active formation."""

from __future__ import annotations

from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int


def _active_instance(payload: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None, None
    active_id = _parse_int(details.get("active_game_instance_id"))
    instances = details.get("game_instances")
    if not isinstance(instances, list):
        return active_id, None
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        if _parse_int(inst.get("game_instance_id")) == active_id:
            return active_id, inst
    if instances and isinstance(instances[0], dict):
        fallback_id = _parse_int(instances[0].get("game_instance_id"))
        return fallback_id, instances[0]
    return active_id, None


def _seat_by_hero(instance: dict[str, Any]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    seats = instance.get("hero_in_seats")
    if not isinstance(seats, dict):
        return mapping
    for seat_raw, hero_raw in seats.items():
        seat = _parse_int(seat_raw)
        hero_id = _parse_int(hero_raw)
        if seat is None or hero_id is None or hero_id <= 0:
            continue
        if 1 <= seat <= 12:
            mapping[hero_id] = seat
    return mapping


def _seats_from_hero_ids(hero_ids: list[int], seat_by_hero: dict[int, int]) -> set[int]:
    return {seat_by_hero[hid] for hid in hero_ids if hid in seat_by_hero}


def _formation_hero_ids(formation: Any) -> list[int]:
    if not isinstance(formation, list):
        return []
    ids: list[int] = []
    for raw in formation:
        hero_id = _parse_int(raw)
        if hero_id is not None and hero_id > 0:
            ids.append(hero_id)
    return ids


def _hero_belongs_to_party(game_id: int | None, active_id: int | None) -> bool:
    """Heroes with game_instance_id 0/None are shared roster — treat as active party."""
    if game_id is None or game_id <= 0:
        return True
    if active_id is None:
        return True
    return game_id == active_id


def _in_seat_seats(
    details: dict[str, Any],
    active_id: int | None,
    seat_by_hero: dict[int, int],
) -> set[int]:
    seats: set[int] = set()
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        if hero.get("in_seat") not in (1, "1", True):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        game_id = _parse_int(hero.get("game_instance_id"))
        if hero_id is None:
            continue
        if not _hero_belongs_to_party(game_id, active_id):
            continue
        seat = seat_by_hero.get(hero_id)
        if seat is not None:
            seats.add(seat)
    return seats


def _formation_grid_seats(
    instance: dict[str, Any],
    details: dict[str, Any],
    seat_by_hero: dict[int, int],
) -> set[int]:
    seats = _seats_from_hero_ids(
        _formation_hero_ids(instance.get("formation")), seat_by_hero
    )
    if len(seats) >= 2:
        return seats
    # Some payloads put the live grid on details instead of the instance.
    seats |= _seats_from_hero_ids(
        _formation_hero_ids(details.get("formation")), seat_by_hero
    )
    return seats


def active_formation_seats(payload: dict[str, Any]) -> tuple[int | None, frozenset[int]]:
    """
    Return (active_party_id, seats_in_formation).

    Prefer the live formation grid (who's on the board). ``hero_in_seats`` can still
    list benched seat holders; ``in_seat`` with game_instance_id 0 is noisy across
    parties — only use those as fallbacks when the grid is empty/sparse.
    """
    details = payload.get("details")
    if not isinstance(details, dict):
        return None, frozenset()

    active_id, instance = _active_instance(payload)
    if instance is None:
        return active_id, frozenset()

    seat_by_hero = _seat_by_hero(instance)
    formation_seats = _formation_grid_seats(instance, details, seat_by_hero)
    # 1) Live formation grid — authoritative for F-key leveling
    if len(formation_seats) >= 2:
        return active_id, frozenset(sorted(formation_seats))

    # 2) Live in_seat flags (useful when the grid lags behind a bench/swap)
    seats = _in_seat_seats(details, active_id, seat_by_hero)
    if len(seats) >= 2:
        return active_id, frozenset(sorted(seats))

    if formation_seats:
        return active_id, frozenset(sorted(formation_seats))
    if seats:
        return active_id, frozenset(sorted(seats))

    # 3) Formation save — only when live data is missing
    saves = instance.get("formation_saves_v2")
    if not isinstance(saves, list) or not saves:
        saves = details.get("formation_saves_v2")
    if isinstance(saves, list):
        for save in saves:
            if not isinstance(save, dict):
                continue
            found = _seats_from_hero_ids(
                _formation_hero_ids(save.get("formation")), seat_by_hero
            )
            if found:
                return active_id, frozenset(sorted(found))

    # 4) Last resort: all seats listed for this party instance
    if seat_by_hero:
        return active_id, frozenset(sorted(seat_by_hero.values()))

    return active_id, frozenset()
