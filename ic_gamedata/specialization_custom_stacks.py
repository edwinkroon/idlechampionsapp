"""Formation and account stats for custom multiply-stack specialization handlers."""

from __future__ import annotations

from collections import deque
from typing import Any

from ic_gamedata.adventure_restrictions import _parse_int, hero_matches_specialization_expr

_DEFAULT_ADJ: dict[int, frozenset[int]] = {
    1: frozenset({2, 3}),
    2: frozenset({1, 3, 4, 5}),
    3: frozenset({1, 2, 5, 6}),
    4: frozenset({2, 5, 7}),
    5: frozenset({2, 3, 4, 6, 7, 8}),
    6: frozenset({3, 5, 8, 9}),
    7: frozenset({4, 5, 8, 10}),
    8: frozenset({5, 6, 7, 9, 10, 11}),
    9: frozenset({6, 8, 11, 12}),
    10: frozenset({7, 8, 11}),
    11: frozenset({8, 9, 10, 12}),
    12: frozenset({9, 11}),
}

_OMIN_ID = 65
_SHADOWHEART_ID = 141
_DIANA_ID = 148
_DIANA_INSPIRE_IDS = frozenset({14791, 14792, 14793})

_SPECIES_TAGS = frozenset(
    {
        "aarakocra",
        "aasimar",
        "bullywug",
        "centaur",
        "changeling",
        "dhampir",
        "doppelganger",
        "dragonborn",
        "dwarf",
        "elf",
        "fairy",
        "firbolg",
        "genasi",
        "giff",
        "githyanki",
        "githzerai",
        "gnome",
        "goblin",
        "goliath",
        "half-elf",
        "half-orc",
        "halfling",
        "harengon",
        "human",
        "kalashtar",
        "kender",
        "kobold",
        "lizardfolk",
        "minotaur",
        "modron",
        "plasmoid",
        "satyr",
        "saurial",
        "tabaxi",
        "thri-kreen",
        "tiefling",
        "tortle",
        "triton",
        "warforged",
        "yuan-ti",
    }
)
_SPECIES_NORMALIZE = {
    "drow": "elf",
    "wildelf": "elf",
    "halfelf": "half-elf",
    "halforc": "half-orc",
    "yuanti": "yuan-ti",
}


def _hero_tags(hero_id: int, tags_by_hero: dict[int, tuple[str, ...]]) -> set[str]:
    return set(tags_by_hero.get(hero_id, ()))


def unique_species_count(
    active_hero_ids: set[int],
    tags_by_hero: dict[int, tuple[str, ...]],
) -> int:
    species: set[str] = set()
    for hero_id in active_hero_ids:
        for tag in tags_by_hero.get(hero_id, ()):
            canon = _SPECIES_NORMALIZE.get(tag, tag)
            if canon in _SPECIES_TAGS:
                species.add(canon)
    return len(species)


def _is_adjacent(seat_a: int, seat_b: int, adjacency: dict[int, frozenset[int]]) -> bool:
    return seat_b in adjacency.get(seat_a, frozenset())


def seat_graph_distance(
    seat_a: int,
    seat_b: int,
    adjacency: dict[int, frozenset[int]] | None = None,
) -> int:
    if seat_a == seat_b:
        return 0
    adj = adjacency or _DEFAULT_ADJ
    queue: deque[tuple[int, int]] = deque([(seat_a, 0)])
    seen = {seat_a}
    while queue:
        seat, distance = queue.popleft()
        for neighbor in adj.get(seat, frozenset()):
            if neighbor == seat_b:
                return distance + 1
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
    return 0


def _has_acqinc_or_cteam(tags: set[str]) -> bool:
    return "acqinc" in tags or "cteam" in tags


def champions_of_tymora_count(
    active_hero_ids: set[int],
    seat_by_hero: dict[int, int] | None,
    tags_by_hero: dict[int, tuple[str, ...]],
    *,
    known_associates_unlocked: bool = True,
    adjacency: dict[int, frozenset[int]] | None = None,
) -> int:
    if not seat_by_hero or _OMIN_ID not in active_hero_ids:
        return 0
    adj = adjacency or _DEFAULT_ADJ
    omin_seat = seat_by_hero.get(_OMIN_ID)
    if omin_seat is None:
        return 0

    cot: set[int] = {_OMIN_ID}
    for hero_id in active_hero_ids:
        seat = seat_by_hero.get(hero_id)
        if seat is not None and _is_adjacent(omin_seat, seat, adj):
            cot.add(hero_id)

    if known_associates_unlocked:
        affiliate_ids = {
            hero_id
            for hero_id in active_hero_ids
            if _has_acqinc_or_cteam(_hero_tags(hero_id, tags_by_hero))
        }
        cot.update(affiliate_ids)
        for hero_id in active_hero_ids:
            seat = seat_by_hero.get(hero_id)
            if seat is None:
                continue
            for affiliate_id in affiliate_ids:
                affiliate_seat = seat_by_hero.get(affiliate_id)
                if affiliate_seat is not None and _is_adjacent(seat, affiliate_seat, adj):
                    cot.add(hero_id)
                    break
    return len(cot)


def acqinc_cteam_count(
    active_hero_ids: set[int],
    tags_by_hero: dict[int, tuple[str, ...]],
) -> int:
    return sum(
        1
        for hero_id in active_hero_ids
        if _has_acqinc_or_cteam(_hero_tags(hero_id, tags_by_hero))
    )


def dob_qualified_counts(
    active_hero_ids: set[int],
    tags_by_hero: dict[int, tuple[str, ...]],
    attack_types_by_hero: dict[int, frozenset[str]],
    scores_by_hero: dict[int, dict[str, int]],
) -> tuple[int, int, int, int]:
    """Count Dob's Befriend stacks.

    Game text is Oxventure OR the listed filter (magic / CHA≥17 / DEX≥17),
    not Oxventure-only with an extra filter on top.
    """
    magical = friendly = quick = 0
    for hero_id in active_hero_ids:
        tags = _hero_tags(hero_id, tags_by_hero)
        is_oxventure = "oxventure" in tags
        scores = scores_by_hero.get(hero_id, {})
        if is_oxventure or "magic" in attack_types_by_hero.get(hero_id, frozenset()):
            magical += 1
        if is_oxventure or scores.get("cha", 0) >= 17:
            friendly += 1
        if is_oxventure or scores.get("dex", 0) >= 17:
            quick += 1
    return magical, friendly, quick, unique_species_count(active_hero_ids, tags_by_hero)


def shadowheart_duplicity_distance(
    active_hero_ids: set[int],
    seat_by_hero: dict[int, int] | None,
    scores_by_hero: dict[int, dict[str, int]],
    adjacency: dict[int, frozenset[int]] | None = None,
) -> int:
    if not seat_by_hero or _SHADOWHEART_ID not in active_hero_ids:
        return 0
    shadow_seat = seat_by_hero.get(_SHADOWHEART_ID)
    if shadow_seat is None:
        return 0

    best_hero: int | None = None
    best_dex = -1
    best_seat = -1
    for hero_id in active_hero_ids:
        dex = scores_by_hero.get(hero_id, {}).get("dex")
        seat = seat_by_hero.get(hero_id)
        if dex is None or seat is None:
            continue
        if dex > best_dex or (dex == best_dex and seat > best_seat):
            best_dex = dex
            best_seat = seat
            best_hero = hero_id

    if best_hero is None or best_hero == _SHADOWHEART_ID:
        return 0
    duplicate_seat = seat_by_hero.get(best_hero)
    if duplicate_seat is None:
        return 0
    return seat_graph_distance(shadow_seat, duplicate_seat, adjacency)


def diana_inspire_upgrade_id(hero_upgrade_ids: dict[int, frozenset[int]] | None) -> int | None:
    if not hero_upgrade_ids:
        return None
    chosen = hero_upgrade_ids.get(_DIANA_ID, frozenset())
    for upgrade_id in (_DIANA_INSPIRE_IDS):
        if upgrade_id in chosen:
            return upgrade_id
    return None


def diana_inspire_match_count(active_hero_ids: set[int], inspire_upgrade_id: int) -> int:
    if inspire_upgrade_id == 14791:
        expr = "GetStat(`dex`)>=15"
    elif inspire_upgrade_id == 14792:
        expr = "GetStat(`total_ability_score`)<=78"
    elif inspire_upgrade_id == 14793:
        expr = "age<=20&&hero_id!=146"
    else:
        return 0

    count = 0
    for hero_id in active_hero_ids:
        if hero_matches_specialization_expr(hero_id, expr) is True:
            count += 1
    return count


def ceremorphosis_stack_count(
    active_hero_ids: set[int],
    tags_by_hero: dict[int, tuple[str, ...]],
    cfg_tags_by_hero: dict[int, tuple[str, ...]],
) -> int:
    stacks = 0
    for hero_id in active_hero_ids:
        tags = set(tags_by_hero.get(hero_id, ())) | set(cfg_tags_by_hero.get(hero_id, ()))
        if "absoluteadversaries" in tags:
            stacks += 1
    return max(stacks, 1 if 147 in active_hero_ids or 143 in active_hero_ids else 0)


def high_intelligence_count(
    active_hero_ids: set[int],
    scores_by_hero: dict[int, dict[str, int]],
    *,
    minimum: int = 13,
) -> int:
    return sum(
        1
        for hero_id in active_hero_ids
        if scores_by_hero.get(hero_id, {}).get("int", 0) >= minimum
    )


def unavailable_owned_hero_count(
    owned_hero_ids: frozenset[int] | None,
    roster_filter: Any | None = None,
) -> int:
    """Count owned champions ineligible for the current adventure.

    Matches Gale's Finite Fellowship stacks: unlocked champions that cannot
    join this adventure. Unrestricted adventures (no roster rules) return 0 —
    not ``owned - formation``, which massively overvalues Finite Fellowship.
    """
    if not owned_hero_ids or roster_filter is None:
        return 0
    from ic_gamedata.adventure_restrictions import is_hero_allowed

    return sum(1 for hero_id in owned_hero_ids if not is_hero_allowed(hero_id, roster_filter))


def magic_attack_count(
    active_hero_ids: set[int],
    attack_types_by_hero: dict[int, frozenset[str]],
) -> int:
    return sum(
        1
        for hero_id in active_hero_ids
        if "magic" in attack_types_by_hero.get(hero_id, frozenset())
    )


def grand_tour_base_adventures_completed(account_stats: dict[str, Any] | None) -> int:
    if not account_stats:
        return 0
    for key in (
        "GrandTourBaseAdventuresCompleted",
        "grand_tour_base_adventures_completed",
        "grandTourBaseAdventuresCompleted",
    ):
        value = _parse_int(account_stats.get(key))
        if value is not None:
            return max(0, value)
    return 0


def modron_core_competency_stacks(details: dict[str, Any]) -> int:
    saves = details.get("modron_saves")
    if not isinstance(saves, list):
        return 0
    total_levels = 0
    for save in saves:
        if not isinstance(save, dict):
            continue
        for key in ("level", "core_level", "total_level"):
            level = _parse_int(save.get(key))
            if level is not None:
                total_levels += level
                break
    return total_levels


def event_boon_count_from_details(details: dict[str, Any]) -> int:
    events = details.get("events_details")
    if isinstance(events, dict):
        buffs = events.get("active_boon_buffs")
        if isinstance(buffs, list):
            return len(buffs)
    event_details = details.get("event_details")
    if isinstance(event_details, list):
        total = 0
        for item in event_details:
            if not isinstance(item, dict):
                continue
            buffs = item.get("active_boon_buffs")
            if isinstance(buffs, list):
                total += len(buffs)
        return total
    return 0


def owned_hero_ids_from_details(details: dict[str, Any]) -> frozenset[int]:
    heroes = details.get("heroes")
    if not isinstance(heroes, list):
        return frozenset()
    owned: set[int] = set()
    for hero in heroes:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        owned_flag = hero.get("owned")
        if owned_flag in (True, 1, "1") or owned_flag is None:
            owned.add(hero_id)
    return frozenset(owned)


def hero_upgrade_ids_from_details(details: dict[str, Any]) -> dict[int, frozenset[int]]:
    heroes = details.get("heroes")
    if not isinstance(heroes, list):
        return {}
    by_hero: dict[int, set[int]] = {}
    for hero in heroes:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        ids: set[int] = set()
        for key in ("specialization_choices", "upgrades"):
            raw = hero.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                upgrade_id = _parse_int(item)
                if upgrade_id is not None:
                    ids.add(upgrade_id)
        if ids:
            by_hero.setdefault(hero_id, set()).update(ids)
    return {hero_id: frozenset(ids) for hero_id, ids in by_hero.items()}


def omin_has_known_associates(hero_upgrade_ids: dict[int, frozenset[int]] | None) -> bool:
    if not hero_upgrade_ids:
        return False
    return 12301 in hero_upgrade_ids.get(_OMIN_ID, frozenset())
