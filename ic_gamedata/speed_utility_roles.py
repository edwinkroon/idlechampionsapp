"""Utility champion roles inside speed-focused formations (gems, modron parts)."""

from __future__ import annotations

from typing import Literal

from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.party_advisor import FormationHero, GoalMode, _is_speed
from ic_gamedata.seat_advisor.models import SeatRole
from ic_gamedata.specialization_data import (
    hero_ability_scores_map_from_cached_definitions,
    hero_age_map_from_cached_definitions,
    hero_attack_types_map_from_cached_definitions,
)

SpeedUtilityRole = Literal["gold", "modron"]

# Champions with boss-kill scavenger abilities used in speed/modron farming.
MODRON_SCAVENGER_HERO_IDS = frozenset({144})  # Presto

_PRESTO_SPECS: tuple[tuple[str, int], ...] = (
    ("Humble Heroes", 13765),
    ("Junior Juggernauts", 13766),
    ("Magical Mastery", 13767),
)


def is_gold_utility_in_speed_team(hero: FormationHero, goal: GoalMode) -> bool:
    if goal != "speed":
        return False
    if _is_speed(hero):
        return False
    return "gold" in hero.roles or "gold" in hero.tags


def is_modron_utility_in_speed_team(hero: FormationHero, goal: GoalMode) -> bool:
    return goal == "speed" and hero.hero_id in MODRON_SCAVENGER_HERO_IDS


def speed_utility_role(hero: FormationHero, goal: GoalMode) -> SpeedUtilityRole | None:
    if is_modron_utility_in_speed_team(hero, goal):
        return "modron"
    if is_gold_utility_in_speed_team(hero, goal):
        return "gold"
    return None


def infer_speed_utility_seat_role(hero: FormationHero, goal: GoalMode) -> SeatRole | None:
    utility = speed_utility_role(hero, goal)
    if utility is None:
        return None
    return utility  # type: ignore[return-value]


def speed_utility_role_label(role: SpeedUtilityRole) -> str:
    if role == "gold":
        return "Gem / gold utility"
    return "Modron utility"


def speed_utility_relevance_reason(utility: SpeedUtilityRole) -> str:
    if utility == "gold":
        return "Gem-slot in speed-team (geen speed-champion)"
    return "Modron scavenger in speed-team"


def _presto_spec_counts(formation: tuple[FormationHero, ...]) -> dict[str, int]:
    scores = hero_ability_scores_map_from_cached_definitions()
    ages = hero_age_map_from_cached_definitions()
    attacks = hero_attack_types_map_from_cached_definitions()
    counts = {"Humble Heroes": 0, "Junior Juggernauts": 0, "Magical Mastery": 0}
    for hero in formation:
        hid = hero.hero_id
        total = sum(scores.get(hid, {}).values()) if hid in scores else None
        if total is not None and total <= 78:
            counts["Humble Heroes"] += 1
        age = ages.get(hid)
        if age is not None and age <= 20:
            counts["Junior Juggernauts"] += 1
        if "magic" in {tag.casefold() for tag in attacks.get(hid, ())}:
            counts["Magical Mastery"] += 1
    return counts


def best_presto_spec_for_party(formation: tuple[FormationHero, ...]) -> str:
    counts = _presto_spec_counts(formation)
    return max(counts, key=counts.get)


def recommended_spec_for_speed_utility(
    hero: FormationHero,
    formation: tuple[FormationHero, ...],
    *,
    utility: SpeedUtilityRole,
) -> str | None:
    if utility == "gold":
        advice = get_role_advice(hero.hero_id, "gold")
        if advice is not None and advice.specialization_names:
            return " / ".join(advice.specialization_names)
        return None

    if utility == "modron":
        if hero.hero_id in MODRON_SCAVENGER_HERO_IDS:
            return best_presto_spec_for_party(formation)
        advice = get_role_advice(hero.hero_id, "modron")
        if advice is not None and advice.specialization_names:
            return " / ".join(advice.specialization_names)
        return None

    return None


def recommended_feats_for_speed_utility(hero_id: int, utility: SpeedUtilityRole) -> tuple[str, ...]:
    role: SeatRole = utility  # type: ignore[assignment]
    advice = get_role_advice(hero_id, role)
    if advice is not None and advice.feats:
        return advice.feats
    if utility == "modron":
        return ("Morning Lineup", "DM's Chosen", "Room to Breathe", "Pocus Imferium")
    if utility == "gold":
        return ("Transmute Gems",)
    return ()
