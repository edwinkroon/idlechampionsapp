"""Build FormationLayoutContext from party advisor payload."""

from __future__ import annotations

from typing import Any

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
    is_hero_allowed,
    player_formation_capacity,
)
from ic_gamedata.formation_advisor.models import FormationLayoutContext
from ic_gamedata.formation_advisor.topology import load_formation_topology
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_advisor import (
    ContextMode,
    FormationHero,
    GoalMode,
    _owned_heroes,
    _resolve_bud_hero,
)
from ic_gamedata.party_advisor_specializations import advisor_run_goal


def _active_instance(payload: dict[str, Any]) -> dict[str, Any] | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    for inst in details.get("game_instances") or []:
        if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:
            return inst
    instances = details.get("game_instances")
    if isinstance(instances, list) and instances and isinstance(instances[0], dict):
        return instances[0]
    return None


def build_formation_layout_context(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    roster_filter: AdventureRosterFilter | None = None,
) -> FormationLayoutContext:
    instance = _active_instance(payload) or {}
    adventure_id = _parse_int(instance.get("current_adventure_id"))

    # Only champions on the live board. ``hero_in_seats`` can still list seat
    # holders who are benched / not placed — never promote those into active.
    seat_by_hero: dict[int, int] = {}
    formation_ids = {hero.hero_id for hero in formation}
    for hero in formation:
        if hero.seat is not None:
            seat_by_hero[hero.hero_id] = hero.seat

    hero_in_seats = instance.get("hero_in_seats")
    if isinstance(hero_in_seats, dict):
        for seat_raw, hero_raw in hero_in_seats.items():
            seat = _parse_int(seat_raw)
            hero_id = _parse_int(hero_raw)
            if (
                seat is not None
                and hero_id is not None
                and hero_id > 0
                and hero_id in formation_ids
            ):
                seat_by_hero.setdefault(hero_id, seat)

    stats = instance.get("stats") if isinstance(instance.get("stats"), dict) else {}
    highest_damage_hero_id = _parse_int(stats.get("this_reset_highest_damage_dealt_hero_id"))

    bud = _resolve_bud_hero(formation)
    carry_hero_id = bud.hero_id if bud is not None else None

    owned = _owned_heroes(payload)
    owned_ids = frozenset(hid for hid, _name, _roles, _tags in owned)
    allowed_bench = frozenset(
        hid for hid in owned_ids if hid not in seat_by_hero and is_hero_allowed(hid, roster_filter)
    )

    hero_name_by_id = {h.hero_id: h.name for h in formation}
    hero_roles_by_id = {h.hero_id: h.roles for h in formation}
    hero_tags_by_id = {h.hero_id: h.tags for h in formation}
    for hid, name, roles, tags in owned:
        hero_name_by_id.setdefault(hid, name)
        hero_roles_by_id.setdefault(hid, roles)
        hero_tags_by_id.setdefault(hid, tags)

    topology = load_formation_topology(payload, adventure_id)
    capacity = player_formation_capacity(payload, adventure_id)
    try:
        from ic_gamedata.formation_seats import live_formation_hero_ids
    except ImportError:
        grid_count = 0
    else:
        grid_count = len(live_formation_hero_ids(payload))

    return FormationLayoutContext(
        active_hero_ids=frozenset(seat_by_hero.keys()),
        seat_by_hero=seat_by_hero,
        hero_name_by_id=hero_name_by_id,
        hero_roles_by_id=hero_roles_by_id,
        hero_tags_by_id=hero_tags_by_id,
        carry_hero_id=carry_hero_id,
        highest_damage_hero_id=highest_damage_hero_id,
        topology=topology,
        run_goal=advisor_run_goal(goal, context),
        context=context,
        goal=goal,
        party_size=max(len(seat_by_hero), grid_count),
        formation_capacity=capacity,
        owned_hero_ids=owned_ids,
        allowed_bench_ids=allowed_bench,
    )
