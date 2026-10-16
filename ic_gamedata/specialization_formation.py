"""Shared formation topology helpers for specialization advice.

All seat/column/adjacency logic for specs should go through this module so
handlers and declarative rules share one diamond (or API-bridged) layout.
"""

from __future__ import annotations

from functools import lru_cache

from ic_gamedata.formation_advisor.models import FormationTopology, Zone
from ic_gamedata.formation_advisor.topology import _heuristic_topology, fallback_seat_column


@lru_cache(maxsize=1)
def formation_topology() -> FormationTopology:
    """Active specialization topology (heuristic diamond until API bridge is wired here)."""
    return _heuristic_topology()


def clear_formation_topology_cache() -> None:
    formation_topology.cache_clear()


def seat_column(seat: int) -> int:
    topo = formation_topology()
    if seat in topo.seat_column:
        return topo.seat_column[seat]
    return fallback_seat_column(seat)


def seat_zone(seat: int) -> Zone:
    topo = formation_topology()
    zone = topo.seat_zone.get(seat)
    if zone is not None:
        return zone
    cols = topo.seat_column
    if not cols:
        return "mid"
    col = seat_column(seat)
    min_col = min(cols.values())
    max_col = max(cols.values())
    if col <= min_col:
        return "front"
    if col >= max_col:
        return "back"
    return "mid"


def is_front_seat(seat: int) -> bool:
    return seat_zone(seat) == "front"


def is_back_seat(seat: int) -> bool:
    return seat_zone(seat) == "back"


def column_of_hero(hero_id: int, seat_by_hero: dict[int, int] | None) -> int | None:
    if not seat_by_hero:
        return None
    seat = seat_by_hero.get(hero_id)
    if seat is None:
        return None
    return seat_column(seat)


def heroes_in_column(
    column: int,
    *,
    active_hero_ids: set[int],
    seat_by_hero: dict[int, int],
) -> list[int]:
    out: list[int] = []
    for hid in active_hero_ids:
        seat = seat_by_hero.get(hid)
        if seat is None:
            continue
        if seat_column(seat) == column:
            out.append(hid)
    return out


def bud_shares_column(
    hero_id: int,
    *,
    seat_by_hero: dict[int, int] | None,
    bud_hero_id: int | None,
    highest_damage_hero_id: int | None = None,
) -> bool:
    focus_id = bud_hero_id or highest_damage_hero_id
    if focus_id is None or focus_id == hero_id or not seat_by_hero:
        return False
    hero_col = column_of_hero(hero_id, seat_by_hero)
    focus_col = column_of_hero(focus_id, seat_by_hero)
    return hero_col is not None and focus_col is not None and hero_col == focus_col


def bud_column_relation(
    hero_id: int,
    *,
    seat_by_hero: dict[int, int] | None,
    bud_hero_id: int | None,
    highest_damage_hero_id: int | None = None,
) -> str | None:
    """Return 'ahead', 'behind', 'same', or None when seats are unknown.

    Lower column index is toward the front of the formation.
    """
    focus_id = bud_hero_id or highest_damage_hero_id
    if focus_id is None or not seat_by_hero:
        return None
    hero_col = column_of_hero(hero_id, seat_by_hero)
    focus_col = column_of_hero(focus_id, seat_by_hero)
    if hero_col is None or focus_col is None:
        return None
    if focus_col < hero_col:
        return "ahead"
    if focus_col > hero_col:
        return "behind"
    return "same"


def adjacent_hero_ids(
    hero_id: int,
    *,
    active_hero_ids: set[int],
    seat_by_hero: dict[int, int] | None,
) -> list[int]:
    if not seat_by_hero:
        return []
    seat = seat_by_hero.get(hero_id)
    if seat is None:
        return []
    neighbors = formation_topology().seat_adjacency.get(seat, frozenset())
    out: list[int] = []
    for hid in active_hero_ids:
        if hid == hero_id:
            continue
        other = seat_by_hero.get(hid)
        if other is not None and other in neighbors:
            out.append(hid)
    return out


def bud_is_adjacent(
    hero_id: int,
    *,
    seat_by_hero: dict[int, int] | None,
    bud_hero_id: int | None,
    highest_damage_hero_id: int | None = None,
    active_hero_ids: set[int] | None = None,
) -> bool:
    focus_id = bud_hero_id or highest_damage_hero_id
    if focus_id is None or focus_id == hero_id or not seat_by_hero:
        return False
    party = active_hero_ids if active_hero_ids is not None else set(seat_by_hero)
    return focus_id in adjacent_hero_ids(
        hero_id,
        active_hero_ids=party,
        seat_by_hero=seat_by_hero,
    )


def adjacent_role_count(
    hero_id: int,
    *,
    role: str,
    active_hero_ids: set[int],
    seat_by_hero: dict[int, int] | None,
) -> int:
    """Count adjacent allies that have the given champion role (e.g. ``tank``)."""
    from ic_gamedata.specialization_data import hero_roles_map_from_champion_config

    roles_by_hero = hero_roles_map_from_champion_config()
    needle = role.casefold()
    count = 0
    for hid in adjacent_hero_ids(
        hero_id,
        active_hero_ids=active_hero_ids,
        seat_by_hero=seat_by_hero,
    ):
        if needle in {r.casefold() for r in roles_by_hero.get(hid, ())}:
            count += 1
    return count
