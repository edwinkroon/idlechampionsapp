"""Suggest owned bench champions that may improve the active party.

Idle Champions constraint: each champion has a fixed seat (1–12). Only one
champion per seat can be in the formation. Suggestions must therefore either:

* replace the current occupant of the **same** seat, or
* bring in a champion from a seat that is **not** in the party (and optionally
  bench someone else to free formation capacity).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace as dc_replace
from functools import lru_cache
from typing import Any, Literal

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
    build_adventure_roster_filter,
    is_hero_allowed,
)
from ic_gamedata.bud_proxy import (
    bud_proxy_ratio,
    estimate_bud_proxy,
    format_bud_ratio,
    meaningful_bud_ratio,
    score_boost_from_ratio,
)
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_advisor_formation import (
    _formation_heroes,
    _loot_ilvl_by_hero,
    _owned_heroes,
    _resolve_bud_hero,
    _resolve_speed_hero,
)
from ic_gamedata.party_advisor_models import ContextMode, FormationHero, GoalMode
from ic_gamedata.seat_advisor.models import SeatRole
from ic_gamedata.seat_advisor.role_inference import infer_seat_role, role_fits_champion, role_label

GapKind = Literal[
    "missing_role",
    "role_mismatch",
    "stronger_same_role",
    "synergy",
]

_ROLE_PRIORITY_BY_GOAL: dict[str, tuple[SeatRole, ...]] = {
    "bud": ("tank", "debuffer", "buffer", "support", "healer"),
    "speed": ("speed", "tank", "support", "buffer"),
    "gold": ("gold", "tank", "support", "buffer"),
}

_AFFILIATION_TAGS = frozenset(
    {
        "companion",
        "acqinc",
        "cteam",
        "wafflecrew",
        "heroeslance",
        "awfulones",
        "emeraldenclave",
        "morndinsamman",
        "majestics",
        "rivals",
    }
)

# Seat swaps that drop these often hurt BUD more than ilvl gains help (e.g. Halsin speed).
_VALUABLE_BUD_TAGS = frozenset({"speed", "debuffer", "bud"})


def _loses_valuable_bud_tags(
    occupant_tags: tuple[str, ...],
    candidate_tags: tuple[str, ...],
) -> frozenset[str]:
    return frozenset(occupant_tags) & _VALUABLE_BUD_TAGS - frozenset(candidate_tags)


@dataclass(frozen=True)
class RosterUpgradeSuggestion:
    candidate_hero_id: int
    candidate_name: str
    candidate_seat: int | None
    replace_hero_id: int | None
    replace_name: str | None
    replace_seat: int | None
    role: SeatRole
    kind: GapKind
    title: str
    why: str
    score: float
    same_seat_swap: bool
    bud_ratio: float | None = None


@dataclass(frozen=True)
class _OwnedChamp:
    hero_id: int
    name: str
    roles: tuple[str, ...]
    tags: tuple[str, ...]
    ilvl: int
    seat_id: int | None


@lru_cache(maxsize=1)
def _hero_seat_id_map() -> dict[int, int]:
    from ic_gamedata.specialization_data import cached_definitions_data

    out: dict[int, int] = {}
    data = cached_definitions_data()
    for hero in data.get("hero_defines") or []:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("id"))
        seat_id = _parse_int(hero.get("seat_id"))
        if hero_id is None or seat_id is None or seat_id <= 0:
            continue
        out[hero_id] = seat_id
    return out


def _seat_zone(seat: int | None) -> str:
    if seat is None:
        return "mid"
    column = ((seat - 1) % 4) + 1
    if column == 1:
        return "front"
    if column == 4:
        return "back"
    return "mid"


def _hero_tags_roles_fit(roles: tuple[str, ...], tags: tuple[str, ...], role: SeatRole) -> bool:
    role_set = set(roles)
    tag_set = set(tags)
    if role == "bud":
        return "dps" in role_set
    if role == "tank":
        return "tank" in role_set
    if role == "buffer":
        return "buffer" in tag_set or "support" in role_set
    if role == "debuffer":
        return "debuffer" in tag_set or "bud" in tag_set
    if role == "healer":
        return "healer" in role_set
    if role == "support":
        return "support" in role_set
    if role == "gold":
        return "gold" in role_set or "gold" in tag_set
    if role == "speed":
        return "speed" in tag_set
    if role == "modron":
        return False
    return True


def _fit_score(roles: tuple[str, ...], tags: tuple[str, ...], role: SeatRole) -> float:
    role_set = set(roles)
    tag_set = set(tags)
    if role == "bud":
        return 3.0 if "dps" in role_set else 0.0
    if role == "tank":
        return 3.0 if "tank" in role_set else 0.0
    if role == "buffer":
        if "buffer" in tag_set:
            return 3.0
        return 1.5 if "support" in role_set else 0.0
    if role == "debuffer":
        if "debuffer" in tag_set:
            return 3.0
        return 2.0 if "bud" in tag_set else 0.0
    if role == "healer":
        return 3.0 if "healer" in role_set else 0.0
    if role == "support":
        return 2.5 if "support" in role_set else 0.0
    if role == "gold":
        return 3.0 if ("gold" in role_set or "gold" in tag_set) else 0.0
    if role == "speed":
        return 3.0 if "speed" in tag_set else 0.0
    return 0.5


def _party_has_role(formation: tuple[FormationHero, ...], role: SeatRole) -> bool:
    return any(role_fits_champion(hero, role) for hero in formation)


def _affiliation_overlap(candidate_tags: tuple[str, ...], party_tags: set[str]) -> list[str]:
    cand = set(candidate_tags) & _AFFILIATION_TAGS
    return sorted(cand & party_tags)


def _replaceable_heroes(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    protected_ids: set[int],
) -> list[FormationHero]:
    """Prefer benching flex / poorly fitting seats before core roles."""
    ranked: list[tuple[float, FormationHero]] = []
    for hero in formation:
        if hero.hero_id in protected_ids:
            continue
        penalty = 0.0
        if role_fits_champion(hero, "tank") and goal in {"bud", "speed", "gold"}:
            penalty += 40
        if role_fits_champion(hero, "debuffer") and goal == "bud":
            penalty += 35
        if role_fits_champion(hero, "buffer") and goal == "bud":
            penalty += 25
        if role_fits_champion(hero, "speed") and goal == "speed":
            penalty += 40
        if role_fits_champion(hero, "gold") and goal == "gold":
            penalty += 35
        ranked.append((penalty + hero.ilvl * 0.01, hero))
    ranked.sort(key=lambda item: item[0])
    return [hero for _score, hero in ranked]


def _owned_champs(
    payload: dict[str, Any],
    *,
    roster_filter: AdventureRosterFilter | None,
    in_party: set[int],
) -> list[_OwnedChamp]:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    ilvl_by_hero = _loot_ilvl_by_hero(details)
    seat_map = _hero_seat_id_map()
    out: list[_OwnedChamp] = []
    for hero_id, name, roles, tags in _owned_heroes(payload):
        if hero_id in in_party:
            continue
        if roster_filter is not None and not is_hero_allowed(hero_id, roster_filter):
            continue
        out.append(
            _OwnedChamp(
                hero_id=hero_id,
                name=name,
                roles=roles,
                tags=tags,
                ilvl=ilvl_by_hero.get(hero_id, 0),
                seat_id=seat_map.get(hero_id),
            )
        )
    return out


def _suggestion(
    *,
    candidate: _OwnedChamp,
    replace: FormationHero | None,
    role: SeatRole,
    kind: GapKind,
    why: str,
    score: float,
    same_seat_swap: bool,
    bud_ratio: float | None = None,
) -> RosterUpgradeSuggestion:
    if replace is None:
        title = f"Zet {candidate.name} in (seat {candidate.seat_id})"
    elif same_seat_swap:
        title = f"Vervang {replace.name} door {candidate.name}"
    else:
        title = f"Zet {candidate.name} in · bench {replace.name}"
    return RosterUpgradeSuggestion(
        candidate_hero_id=candidate.hero_id,
        candidate_name=candidate.name,
        candidate_seat=candidate.seat_id,
        replace_hero_id=replace.hero_id if replace else None,
        replace_name=replace.name if replace else None,
        replace_seat=replace.seat if replace else None,
        role=role,
        kind=kind,
        title=title,
        why=why,
        score=score,
        same_seat_swap=same_seat_swap,
        bud_ratio=bud_ratio,
    )


def _candidate_as_hero(candidate: _OwnedChamp) -> FormationHero:
    return FormationHero(
        hero_id=candidate.hero_id,
        name=candidate.name,
        seat=candidate.seat_id,
        level=0,
        gear_score=float(candidate.ilvl),
        ilvl=candidate.ilvl,
        ilvl_pct_vs_avg=0.0,
        gear_rank=0,
        gear_rank_total=0,
        gear_pct_of_best=0.0,
        gear_label="",
        role_label="",
        roles=candidate.roles,
        tags=candidate.tags,
        highest_damage=0.0,
        active_feats=0,
        is_top_damage=False,
    )


def _hypothetical_formation(
    formation: tuple[FormationHero, ...],
    *,
    candidate: _OwnedChamp,
    replace: FormationHero | None,
    same_seat_swap: bool,
) -> tuple[FormationHero, ...]:
    incoming = _candidate_as_hero(candidate)
    if same_seat_swap and replace is not None:
        return tuple(incoming if hero.hero_id == replace.hero_id else hero for hero in formation)
    out = list(formation)
    if replace is not None:
        out = [hero for hero in out if hero.hero_id != replace.hero_id]
    out.append(incoming)
    return tuple(out)


def _formation_adjacency(payload: dict[str, Any], adventure_id: int | None) -> dict[int, frozenset[int]]:
    try:
        from ic_gamedata.formation_advisor.topology import load_formation_topology
    except ImportError:
        return {}
    return dict(load_formation_topology(payload, adventure_id).seat_adjacency)


def _enrich_bud_proxy(
    suggestion: RosterUpgradeSuggestion,
    *,
    formation: tuple[FormationHero, ...],
    candidate: _OwnedChamp,
    replace: FormationHero | None,
    adjacency: dict[int, frozenset[int]],
) -> RosterUpgradeSuggestion:
    after = _hypothetical_formation(
        formation,
        candidate=candidate,
        replace=replace,
        same_seat_swap=suggestion.same_seat_swap,
    )
    before = estimate_bud_proxy(formation, adjacency=adjacency or None)
    after_proxy = estimate_bud_proxy(after, adjacency=adjacency or None)
    ratio = bud_proxy_ratio(before, after_proxy)
    why = suggestion.why
    if meaningful_bud_ratio(ratio) and ratio >= 1.0:
        why = f"{why} BUD-proxy: {format_bud_ratio(ratio)} t.o.v. huidige party."
    elif meaningful_bud_ratio(ratio) and ratio < 1.0:
        why = f"{why} BUD-proxy: {format_bud_ratio(ratio)} — rol/seat kan toch beter passen."
    return dc_replace(
        suggestion,
        why=why,
        score=suggestion.score + score_boost_from_ratio(ratio),
        bud_ratio=ratio,
    )


def _same_seat_occupant(
    candidate: _OwnedChamp,
    formation_by_seat: dict[int, FormationHero],
) -> FormationHero | None:
    if candidate.seat_id is None:
        return None
    return formation_by_seat.get(candidate.seat_id)


def suggest_roster_upgrades(
    payload: dict[str, Any],
    *,
    goal: GoalMode = "bud",
    context: ContextMode = "campaign",
    limit: int = 6,
) -> tuple[RosterUpgradeSuggestion, ...]:
    """Return ranked seat-legal swap/add suggestions for owned champions."""
    formation = _formation_heroes(payload)
    if not formation:
        return ()

    instance = None
    details = payload.get("details")
    if isinstance(details, dict):
        active_id = _parse_int(details.get("active_game_instance_id"))
        for inst in details.get("game_instances") or []:
            if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:
                instance = inst
                break
    adventure_id = _parse_int((instance or {}).get("current_adventure_id")) if instance else None
    if adventure_id is None and isinstance(details, dict):
        adventure_id = _parse_int(details.get("current_adventure_id"))
    roster_filter = build_adventure_roster_filter(payload, adventure_id)

    in_party = {hero.hero_id for hero in formation}
    formation_by_seat = {hero.seat: hero for hero in formation if hero.seat is not None}
    occupied_seats = set(formation_by_seat)
    bench = _owned_champs(payload, roster_filter=roster_filter, in_party=in_party)
    # Skip champions whose permanent seat is unknown — cannot validate legality.
    bench = [champ for champ in bench if champ.seat_id is not None]
    if not bench:
        return ()

    bud = _resolve_bud_hero(formation) if goal == "bud" else None
    speed = _resolve_speed_hero(formation) if goal == "speed" else None
    protected = set()
    if bud is not None:
        protected.add(bud.hero_id)
    if speed is not None:
        protected.add(speed.hero_id)
    # Never suggest replacing the current hardest hitter — seat-tag heuristics
    # (e.g. Makos vs King of Shadows on seat 9) must not bench a working carry.
    for hero in formation:
        if hero.is_top_damage:
            protected.add(hero.hero_id)
    damage_leaders = [hero for hero in formation if hero.highest_damage > 0]
    if damage_leaders:
        best_damage = max(hero.highest_damage for hero in damage_leaders)
        for hero in damage_leaders:
            if hero.highest_damage >= best_damage * 0.5 and "dps" in hero.roles:
                protected.add(hero.hero_id)

    party_tags: set[str] = set()
    for hero in formation:
        party_tags.update(hero.tags)

    suggestions: list[RosterUpgradeSuggestion] = []
    used_candidates: set[int] = set()
    used_replace: set[int] = set()
    used_bring_in_seats: set[int] = set()
    adjacency = _formation_adjacency(payload, adventure_id) if goal == "bud" else {}

    def _add(
        item: RosterUpgradeSuggestion,
        *,
        candidate: _OwnedChamp,
        replace_hero: FormationHero | None,
    ) -> None:
        if goal == "bud":
            item = _enrich_bud_proxy(
                item,
                formation=formation,
                candidate=candidate,
                replace=replace_hero,
                adjacency=adjacency,
            )
            ratio = item.bud_ratio
            # Never recommend a swap the BUD-proxy expects to hurt damage.
            if ratio is not None and ratio < 1.0:
                return
            # Soft tips need at least a small proxy gain.
            if item.kind in {"stronger_same_role", "role_mismatch", "synergy"} and (
                ratio is None or ratio < 1.05
            ):
                return
        suggestions.append(item)

    def _pick_bench_target(*, exclude_seat: int | None = None) -> FormationHero | None:
        for hero in _replaceable_heroes(formation, goal=goal, protected_ids=protected):
            if hero.hero_id in used_replace:
                continue
            if exclude_seat is not None and hero.seat == exclude_seat:
                continue
            return hero
        return None

    # 1) Missing critical roles — only seat-legal bring-in / same-seat swaps.
    for role in _ROLE_PRIORITY_BY_GOAL.get(goal, ()):
        if _party_has_role(formation, role):
            continue
        candidates = [
            champ
            for champ in bench
            if champ.hero_id not in used_candidates
            and champ.seat_id not in used_bring_in_seats
            and _hero_tags_roles_fit(champ.roles, champ.tags, role)
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda c: (_fit_score(c.roles, c.tags, role), c.ilvl), reverse=True)
        candidate = candidates[0]
        assert candidate.seat_id is not None
        occupant = _same_seat_occupant(candidate, formation_by_seat)
        role_nl = role_label(role)

        if occupant is not None:
            if occupant.hero_id in protected or occupant.hero_id in used_replace:
                continue
            # BUD: don't evict a buffer/debuffer from their seat just to fill tank/healer/etc.
            # (Halsin→Nayeli: same seat, "missing tank", but in-game BUD dropped hard.)
            if (
                goal == "bud"
                and role not in {"buffer", "debuffer"}
                and (
                    "buffer" in occupant.tags
                    or "debuffer" in occupant.tags
                    or "bud" in occupant.tags
                )
                and role not in occupant.roles
            ):
                continue
            why = (
                f"Je party mist een duidelijke {role_nl.lower()}. "
                f"{candidate.name} (seat {candidate.seat_id}) past bij die rol en vervangt "
                f"{occupant.name} op dezelfde seat"
                + (f" (ilvl {candidate.ilvl} vs {occupant.ilvl})" if candidate.ilvl or occupant.ilvl else "")
                + "."
            )
            score = 2000 + _fit_score(candidate.roles, candidate.tags, role) * 100 + candidate.ilvl
            _add(
                _suggestion(
                    candidate=candidate,
                    replace=occupant,
                    role=role,
                    kind="missing_role",
                    why=why,
                    score=score,
                    same_seat_swap=True,
                ),
                candidate=candidate,
                replace_hero=occupant,
            )
            used_candidates.add(candidate.hero_id)
            used_replace.add(occupant.hero_id)
            continue

        # Seat not in party: bring in this seat, optionally bench someone else.
        if candidate.seat_id in occupied_seats or candidate.seat_id in used_bring_in_seats:
            continue
        bench_target = _pick_bench_target()
        why_parts = [
            f"Je party mist een duidelijke {role_nl.lower()}.",
            f"{candidate.name} (seat {candidate.seat_id}) past bij die rol"
            + (f" (ilvl {candidate.ilvl})" if candidate.ilvl else "")
            + " en die seat zit nog niet in de formatie.",
        ]
        if bench_target is not None:
            why_parts.append(
                f"Om ruimte te maken kun je {bench_target.name} "
                f"(seat {bench_target.seat}) benchen — niet omdat {candidate.name} "
                f"die seat overneemt, maar omdat er maar één champion per seat mee kan."
            )
        overlap = _affiliation_overlap(candidate.tags, party_tags)
        if overlap:
            why_parts.append("Extra synergie via gedeelde affiliatie: " + ", ".join(overlap) + ".")
        score = 1900 + _fit_score(candidate.roles, candidate.tags, role) * 100 + candidate.ilvl
        _add(
            _suggestion(
                candidate=candidate,
                replace=bench_target,
                role=role,
                kind="missing_role",
                why=" ".join(why_parts),
                score=score,
                same_seat_swap=False,
            ),
            candidate=candidate,
            replace_hero=bench_target,
        )
        used_candidates.add(candidate.hero_id)
        used_bring_in_seats.add(candidate.seat_id)
        if bench_target is not None:
            used_replace.add(bench_target.hero_id)

    # 2) Role mismatch: only same-seat alternatives.
    focus_id = bud.hero_id if bud is not None else None
    for hero in formation:
        if hero.hero_id in protected or hero.hero_id in used_replace or hero.seat is None:
            continue
        role = infer_seat_role(
            hero,
            zone=_seat_zone(hero.seat),
            bud_hero_id=focus_id,
            goal=goal,
            context=context,
        )
        if role in {"flex", "bud"}:
            continue
        if role_fits_champion(hero, role):
            continue
        candidates = [
            champ
            for champ in bench
            if champ.hero_id not in used_candidates
            and champ.seat_id == hero.seat
            and _hero_tags_roles_fit(champ.roles, champ.tags, role)
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda c: (_fit_score(c.roles, c.tags, role), c.ilvl), reverse=True)
        candidate = candidates[0]
        role_nl = role_label(role)
        why = (
            f"{hero.name} (seat {hero.seat}) past slecht bij de {role_nl.lower()}-rol die deze "
            f"positie nu vraagt. {candidate.name} is een owned alternatief op dezelfde seat"
            + (f" (ilvl {candidate.ilvl} vs {hero.ilvl})" if candidate.ilvl or hero.ilvl else "")
            + "."
        )
        score = 1500 + _fit_score(candidate.roles, candidate.tags, role) * 80 + candidate.ilvl
        _add(
            _suggestion(
                candidate=candidate,
                replace=hero,
                role=role,
                kind="role_mismatch",
                why=why,
                score=score,
                same_seat_swap=True,
            ),
            candidate=candidate,
            replace_hero=hero,
        )
        used_candidates.add(candidate.hero_id)
        used_replace.add(hero.hero_id)

    # 3) Same-seat, same-role upgrade (clearly better owned option on that seat).
    for hero in formation:
        if hero.hero_id in protected or hero.hero_id in used_replace or hero.seat is None:
            continue
        role = infer_seat_role(
            hero,
            zone=_seat_zone(hero.seat),
            bud_hero_id=focus_id,
            goal=goal,
            context=context,
        )
        # Never "upgrade" the carry seat by remapping BUD → support/buffer tags.
        if role == "bud":
            continue
        if role == "flex":
            if not (goal == "gold" and role_fits_champion(hero, "gold")):
                role = "support" if "support" in hero.roles else ("tank" if "tank" in hero.roles else "flex")
        current_fit = _fit_score(hero.roles, hero.tags, role)
        candidates = []
        for champ in bench:
            if champ.hero_id in used_candidates or champ.seat_id != hero.seat:
                continue
            fit = _fit_score(champ.roles, champ.tags, role)
            if fit <= 0 and role != "flex":
                continue
            # Keep multi-role DPS carries (e.g. King of Shadows) over gold supports
            # (e.g. Makos) on the same seat when the goal is BUD damage.
            if (
                goal == "bud"
                and "dps" in hero.roles
                and ("tank" in hero.roles or hero.highest_damage > 0 or hero.is_top_damage)
                and "gold" in champ.tags
                and "tank" not in champ.roles
            ):
                continue
            if role == "flex":
                # Compare generic usefulness via ilvl only when both are flex.
                if champ.ilvl >= hero.ilvl + 200:
                    candidates.append(champ)
                continue
            # BUD: skip swaps that drop speed/debuffer tags.
            if goal == "bud" and _loses_valuable_bud_tags(hero.tags, champ.tags):
                continue
            # BUD: never promote support/buffer/tank on ilvl alone — kits dominate
            # (Omin ilvl 7 beat Nayeli 1462 in-game while proxy claimed ×3).
            if goal == "bud" and role in {"buffer", "support", "debuffer", "healer", "tank"}:
                if fit > current_fit + 0.4:
                    candidates.append(champ)
                continue
            if fit > current_fit + 0.4 or (fit >= current_fit and champ.ilvl >= hero.ilvl + 200):
                candidates.append(champ)
        if not candidates:
            continue
        candidates.sort(
            key=lambda c: (_fit_score(c.roles, c.tags, role), c.ilvl - hero.ilvl, c.ilvl),
            reverse=True,
        )
        candidate = candidates[0]
        role_nl = role_label(role)
        ilvl_bit = ""
        if candidate.ilvl or hero.ilvl:
            ilvl_bit = f" Gear: {candidate.name} ilvl {candidate.ilvl} vs {hero.name} ilvl {hero.ilvl}."
        why = (
            f"Beide zijn seat {hero.seat}-champions. {candidate.name} lijkt een sterkere owned "
            f"optie dan {hero.name} voor de {role_nl.lower()}-rol.{ilvl_bit}"
        )
        overlap = _affiliation_overlap(candidate.tags, party_tags)
        if overlap:
            why += " Affiliatie-overlap met de party: " + ", ".join(overlap) + "."
        score = (
            900
            + _fit_score(candidate.roles, candidate.tags, role) * 50
            + max(0, candidate.ilvl - hero.ilvl)
            + candidate.ilvl * 0.1
        )
        _add(
            _suggestion(
                candidate=candidate,
                replace=hero,
                role=role,
                kind="stronger_same_role",
                why=why,
                score=score,
                same_seat_swap=True,
            ),
            candidate=candidate,
            replace_hero=hero,
        )
        used_candidates.add(candidate.hero_id)
        used_replace.add(hero.hero_id)

    # 4) Soft synergy bring-in from an unused seat only.
    for champ in bench:
        if champ.hero_id in used_candidates or champ.seat_id is None:
            continue
        if champ.seat_id in occupied_seats or champ.seat_id in used_bring_in_seats:
            continue
        overlap = _affiliation_overlap(champ.tags, party_tags)
        if not overlap:
            continue
        shared_count = sum(1 for hero in formation if set(hero.tags) & set(overlap))
        if shared_count < 2:
            continue
        role: SeatRole = "support"
        if _hero_tags_roles_fit(champ.roles, champ.tags, "buffer"):
            role = "buffer"
        elif _hero_tags_roles_fit(champ.roles, champ.tags, "debuffer"):
            role = "debuffer"
        elif _hero_tags_roles_fit(champ.roles, champ.tags, "tank"):
            role = "tank"
        elif "dps" in champ.roles:
            role = "flex"
        bench_target = _pick_bench_target()
        if bench_target is None:
            continue
        why = (
            f"{champ.name} (seat {champ.seat_id}) deelt affiliatie ({', '.join(overlap)}) met "
            f"{shared_count} champions in je party. Die seat zit nog niet in de formatie; "
            f"bench {bench_target.name} (seat {bench_target.seat}) om ruimte te maken."
        )
        score = 500 + shared_count * 40 + champ.ilvl * 0.05
        _add(
            _suggestion(
                candidate=champ,
                replace=bench_target,
                role=role,
                kind="synergy",
                why=why,
                score=score,
                same_seat_swap=False,
            ),
            candidate=champ,
            replace_hero=bench_target,
        )
        used_candidates.add(champ.hero_id)
        used_bring_in_seats.add(champ.seat_id)
        used_replace.add(bench_target.hero_id)
        if len(suggestions) >= limit * 2:
            break

    suggestions.sort(key=lambda item: item.score, reverse=True)
    return tuple(suggestions[:limit])


def goal_label_short(goal: GoalMode) -> str:
    if goal == "bud":
        return "BUD/damage"
    if goal == "speed":
        return "speed"
    return "gold"
