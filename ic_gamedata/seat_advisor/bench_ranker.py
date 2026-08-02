"""Rank bench champions as alternatives for a seat role."""

from __future__ import annotations

from ic_gamedata.adventure_restrictions import AdventureRosterFilter, is_hero_allowed
from ic_gamedata.party_advisor import (
    FormationHero,
)
from ic_gamedata.seat_advisor.models import BenchCandidate, SeatRole
from ic_gamedata.seat_advisor.role_inference import role_fits_champion


def _role_match_score(hero_roles: tuple[str, ...], hero_tags: tuple[str, ...], role: SeatRole) -> float:
    roles = set(hero_roles)
    tags = set(hero_tags)
    if role == "bud":
        return 3.0 if "dps" in roles else 0.0
    if role == "tank":
        return 3.0 if "tank" in roles else 0.0
    if role == "buffer":
        return 3.0 if "buffer" in tags else (1.0 if "support" in roles else 0.0)
    if role == "debuffer":
        return 3.0 if "debuffer" in tags or "bud" in tags else 0.0
    if role == "support":
        return 2.0 if "support" in roles else 0.0
    if role == "healer":
        return 3.0 if "healer" in roles else 0.0
    if role == "gold":
        return 3.0 if "gold" in roles or "gold" in tags else 0.0
    if role == "speed":
        return 3.0 if "speed" in tags else 0.0
    return 1.0 if "support" in roles or "dps" in roles else 0.0


def rank_bench_alternatives(
    *,
    role: SeatRole,
    current_hero: FormationHero,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    in_party: set[int],
    roster_filter: AdventureRosterFilter | None,
    ilvl_by_hero: dict[int, int],
    limit: int = 3,
) -> tuple[BenchCandidate, ...]:
    candidates: list[tuple[float, BenchCandidate]] = []
    for hero_id, name, roles, tags in owned:
        if hero_id in in_party or hero_id == current_hero.hero_id:
            continue
        if roster_filter is not None and not is_hero_allowed(hero_id, roster_filter):
            continue
        match = _role_match_score(roles, tags, role)
        if match <= 0:
            continue
        ilvl = ilvl_by_hero.get(hero_id, 0)
        score = match * 1000 + ilvl
        reason = f"past bij rol {role}"
        if ilvl:
            reason += f" · ilvl {ilvl}"
        candidates.append(
            (
                score,
                BenchCandidate(hero_id=hero_id, hero_name=name, reason=reason, score=score),
            )
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return tuple(item for _score, item in candidates[:limit])


def better_bench_for_role(
    hero: FormationHero,
    role: SeatRole,
    alternatives: tuple[BenchCandidate, ...],
) -> BenchCandidate | None:
    if not alternatives:
        return None
    if role_fits_champion(hero, role) and role != "flex":
        return None
    return alternatives[0]
