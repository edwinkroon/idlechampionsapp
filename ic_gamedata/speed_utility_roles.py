"""Utility champion roles inside speed-focused formations (gems, scavenger loot)."""

from __future__ import annotations

from typing import Literal

from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.party_advisor import FormationHero, GoalMode, _is_speed
from ic_gamedata.seat_advisor.models import SeatRole
from ic_gamedata.specialization_data import (
    ScavengerAbility,
    hero_ability_scores_map_from_cached_definitions,
    hero_age_map_from_cached_definitions,
    hero_attack_types_map_from_cached_definitions,
    scavenger_abilities_from_cached_definitions,
    scavenger_hero_ids_from_cached_definitions,
)

SpeedUtilityRole = Literal["gold", "scavenger"]

# Auto-detected scavenger slot in speed formations (not every scavenger champion).
AUTO_SCAVENGER_HERO_IDS = frozenset({144})  # Presto

# Backward-compatible alias for older imports/tests.
MODRON_SCAVENGER_HERO_IDS = AUTO_SCAVENGER_HERO_IDS


def scavenger_hero_ids() -> frozenset[int]:
    return scavenger_hero_ids_from_cached_definitions()


# Backward-compatible alias; prefer scavenger_hero_ids().
SCAVENGER_HERO_IDS = scavenger_hero_ids()


def list_scavenger_champions() -> tuple[ScavengerAbility, ...]:
    return scavenger_abilities_from_cached_definitions()


def is_scavenger_champion(hero: FormationHero | int) -> bool:
    hero_id = hero if isinstance(hero, int) else hero.hero_id
    return hero_id in scavenger_hero_ids()


def is_gold_utility_in_speed_team(hero: FormationHero, goal: GoalMode) -> bool:
    if goal != "speed":
        return False
    if _is_speed(hero):
        return False
    return "gold" in hero.roles or "gold" in hero.tags


def is_scavenger_utility_in_speed_team(hero: FormationHero, goal: GoalMode) -> bool:
    return goal == "speed" and hero.hero_id in AUTO_SCAVENGER_HERO_IDS


def speed_utility_role(hero: FormationHero, goal: GoalMode) -> SpeedUtilityRole | None:
    if is_scavenger_utility_in_speed_team(hero, goal):
        return "scavenger"
    if is_gold_utility_in_speed_team(hero, goal):
        return "gold"
    return None


def speed_utility_for_effective_role(
    hero: FormationHero,
    goal: GoalMode,
    effective_role: SeatRole,
) -> SpeedUtilityRole | None:
    utility = speed_utility_role(hero, goal)
    if utility is None and goal == "speed" and effective_role == "scavenger":
        if is_scavenger_champion(hero):
            return "scavenger"
        return None
    return utility


def infer_speed_utility_seat_role(hero: FormationHero, goal: GoalMode) -> SeatRole | None:
    utility = speed_utility_role(hero, goal)
    if utility is None:
        return None
    return utility  # type: ignore[return-value]


def speed_utility_role_label(role: SpeedUtilityRole) -> str:
    if role == "gold":
        return "Gem / gold utility"
    return "Scavenger utility"


def speed_utility_relevance_reason(utility: SpeedUtilityRole) -> str:
    if utility == "gold":
        return "Gem slot in speed team (no speed champion)"
    return "Scavenger in speed team"


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

    if utility == "scavenger":
        if hero.hero_id in AUTO_SCAVENGER_HERO_IDS:
            return best_presto_spec_for_party(formation)
        advice = get_role_advice(hero.hero_id, "scavenger")
        if advice is not None and advice.specialization_names:
            return " / ".join(advice.specialization_names)
        return None

    return None


def recommended_feats_for_speed_utility(hero_id: int, utility: SpeedUtilityRole) -> tuple[str, ...]:
    role: SeatRole = utility  # type: ignore[assignment]
    advice = get_role_advice(hero_id, role)
    if advice is not None and advice.feats:
        return advice.feats
    if utility == "scavenger" and hero_id in AUTO_SCAVENGER_HERO_IDS:
        return ("Morning Lineup", "DM's Chosen", "Room to Breathe", "Pocus Imferium")
    if utility == "gold":
        return ("Transmute Gems",)
    return ()
