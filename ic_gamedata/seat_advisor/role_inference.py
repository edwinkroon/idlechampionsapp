"""Infer default seat/champion roles from party context."""

from __future__ import annotations

from ic_gamedata.party_advisor import (
    ContextMode,
    FormationHero,
    GoalMode,
    _is_buffer,
    _is_debuffer,
    _is_dps,
    _is_speed,
    _is_tank,
)
from ic_gamedata.seat_advisor.models import SeatRole
from ic_gamedata.speed_utility_roles import infer_speed_utility_seat_role


def infer_seat_role(
    hero: FormationHero,
    *,
    zone: str,
    bud_hero_id: int | None,
    goal: GoalMode,
    context: ContextMode,
) -> SeatRole:
    if bud_hero_id is not None and hero.hero_id == bud_hero_id:
        return "bud"

    if goal == "gold" and ("gold" in hero.roles or "gold" in hero.tags):
        return "gold"

    utility_role = infer_speed_utility_seat_role(hero, goal)
    if utility_role is not None:
        return utility_role

    if goal == "speed" and _is_speed(hero):
        return "speed"

    if context == "modron" and _is_speed(hero):
        return "speed"

    if _is_debuffer(hero):
        return "debuffer"

    if _is_buffer(hero):
        return "buffer"

    if _is_tank(hero):
        return "tank"

    if "healer" in hero.roles:
        return "healer"

    if "support" in hero.roles:
        return "support"

    if _is_dps(hero):
        return "flex"

    return "flex"


def role_fits_champion(hero: FormationHero, role: SeatRole) -> bool:
    if role == "bud":
        return _is_dps(hero)
    if role == "tank":
        return _is_tank(hero)
    if role == "buffer":
        return _is_buffer(hero)
    if role == "debuffer":
        return _is_debuffer(hero)
    if role == "healer":
        return "healer" in hero.roles
    if role == "support":
        return "support" in hero.roles
    if role == "gold":
        return "gold" in hero.roles or "gold" in hero.tags
    if role == "modron":
        from ic_gamedata.speed_utility_roles import MODRON_SCAVENGER_HERO_IDS

        return hero.hero_id in MODRON_SCAVENGER_HERO_IDS
    if role == "speed":
        return _is_speed(hero)
    return True


def role_label(role: SeatRole) -> str:
    labels = {
        "tank": "Tank",
        "bud": "BUD / carry",
        "buffer": "Buffer",
        "debuffer": "Debuffer",
        "support": "Support",
        "healer": "Healer",
        "gold": "Gem / gold",
        "modron": "Modron scavenger",
        "speed": "Speed",
        "flex": "Flex",
    }
    return labels.get(role, role)
