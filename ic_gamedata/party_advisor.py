"""Party advisor: formation and gear analysis from getuserdetails payload."""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.parsing import parse_number as _parse_number

GoalMode = Literal["bud", "gold", "speed"]
ContextMode = Literal["campaign", "events", "push", "modron"]

GOAL_LABELS: dict[str, str] = {
    "bud": "BUD / damage",
    "gold": "Gold income",
    "speed": "Speed / areas",
}


def goal_label(goal: GoalMode) -> str:
    return GOAL_LABELS.get(goal, goal)

_RELATIVE_GEAR_WEAK_PCT = 12.0

# Fallback names if champions.json is incomplete (kept in sync with common BUD picks).
_FALLBACK_DEBUFFERS = frozenset(
    {
        "Krull",
        "Aila",
        "Gromma",
        "Spurt",
        "Warden",
        "Strix",
        "Catti-brie",
        "Sisaspia",
        "Nova",
        "Freely",
        "Lark",
        "Skylla",
        "Presto",
        "Gale",
    }
)
_FALLBACK_BUFFERS = frozenset(
    {
        "Avren",
        "Celeste",
        "Birdsong",
        "Calliope",
        "Bruenor",
        "Morgaen",
        "Qillek",
        "Turiel",
    }
)


def _champions_path_candidates() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        paths.append(exe_dir / "config" / "champions.json")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / "config" / "champions.json")
    paths.append(Path(__file__).resolve().parent.parent / "config" / "champions.json")
    return paths


def _load_champion_db() -> dict[str, dict[str, Any]]:
    for path in _champions_path_candidates():
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        return data if isinstance(data, dict) else {}
    return {}


def _names_with_tag(tag: str) -> frozenset[str]:
    names: set[str] = set()
    for entry in _load_champion_db().values():
        if not isinstance(entry, dict):
            continue
        tags = entry.get("tags") or ()
        roles = entry.get("roles") or ()
        if tag in tags or tag in roles:
            name = entry.get("name")
            if isinstance(name, str) and name:
                names.add(name)
    return frozenset(names)


def _known_debuffers() -> frozenset[str]:
    return _names_with_tag("debuffer") | _FALLBACK_DEBUFFERS


def _known_buffers() -> frozenset[str]:
    return _names_with_tag("buffer") | _FALLBACK_BUFFERS


def _names_from_payload(payload: dict[str, Any]) -> dict[int, str]:
    """Best-effort champion names from upgrade tip text in the API response."""
    lookup: dict[int, str] = {}
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return lookup
    for upgrade in defines.get("upgrade_defines") or []:
        if not isinstance(upgrade, dict):
            continue
        hero_id = _parse_int(upgrade.get("hero_id"))
        tip = upgrade.get("tip_text")
        if hero_id is None or not isinstance(tip, str):
            continue
        match = re.match(
            r"^([A-Za-z][A-Za-z' \-]+?)(?:'s|\s+(?:increases|can|has|deals|gains|adds|reduces|is|are|will|extends))",
            tip.strip(),
        )
        if match:
            lookup.setdefault(hero_id, match.group(1).strip())
    return lookup


def _hero_meta(
    hero_id: int,
    db: dict[str, dict[str, Any]],
    *,
    name_lookup: dict[int, str] | None = None,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    entry = db.get(str(hero_id), {})
    name = entry.get("name") or (name_lookup or {}).get(hero_id) or f"Champion {hero_id}"
    roles = tuple(entry.get("roles") or ())
    tags = tuple(entry.get("tags") or ())
    return name, roles, tags


def _role_label(roles: tuple[str, ...], tags: tuple[str, ...]) -> str:
    if "gold" in tags or "gold" in roles:
        return "Gold"
    if "debuffer" in tags:
        return "Debuffer"
    if "buffer" in tags:
        return "Buffer"
    if "dps" in roles:
        return "DPS"
    if "support" in roles:
        return "Support"
    if "tank" in roles:
        return "Tank"
    if "healer" in roles or "healer" in tags:
        return "Healer"
    if roles:
        return roles[0].capitalize()
    return "Onbekend"


def _active_game_instance(payload: dict[str, Any]) -> dict[str, Any] | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    instances = details.get("game_instances")
    if isinstance(instances, list) and instances:
        if active_id is not None:
            for inst in instances:
                if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:
                    return inst
        first = instances[0]
        return first if isinstance(first, dict) else None
    return details


def _adventure_name(payload: dict[str, Any], adventure_id: int | None) -> str:
    if adventure_id is None:
        return "Onbekend adventure"
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return f"Adventure {adventure_id}"
    adventures = defines.get("adventure_defines")
    if not isinstance(adventures, list):
        return f"Adventure {adventure_id}"
    for adv in adventures:
        if isinstance(adv, dict) and _parse_int(adv.get("id")) == adventure_id:
            name = adv.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return f"Adventure {adventure_id}"


def _adventure_modifiers(payload: dict[str, Any], adventure_id: int | None) -> list[str]:
    if adventure_id is None:
        return []
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return []
    adventures = defines.get("adventure_defines")
    if not isinstance(adventures, list):
        return []
    for adv in adventures:
        if not isinstance(adv, dict) or _parse_int(adv.get("id")) != adventure_id:
            continue
        notes: list[str] = []
        restrictions = adv.get("restrictions_text")
        if isinstance(restrictions, str) and _is_useful_adventure_note(restrictions):
            notes.append(restrictions.strip())
        for change in adv.get("game_changes") or []:
            if not isinstance(change, dict):
                continue
            for effect in change.get("effects") or []:
                if not isinstance(effect, str) or not effect.strip():
                    continue
                if re.match(r"^[a-z_]+,", effect.strip(), re.I):
                    continue
                if _is_useful_adventure_note(effect):
                    notes.append(effect.strip())
        return notes
    return []


def _is_useful_adventure_note(text: str) -> bool:
    """Skip empty / 'no restrictions' fluff that isn't actionable."""
    cleaned = re.sub(r"\s+", " ", text.strip())
    if len(cleaned) < 8:
        return False
    if re.fullmatch(
        r"(no|none|n/?a|nothing|geen)(\s+(restrictions?|limits?|beperkingen?))?",
        cleaned,
        re.I,
    ):
        return False
    if re.search(r"\bno\s+restrictions?\b", cleaned, re.I):
        return False
    if re.search(r"\bgeen\s+beperkingen?\b", cleaned, re.I):
        return False
    return True


def _is_actionable_adventure_rule(note: str) -> bool:
    """Only surface rules that change how you build or play."""
    if not _is_useful_adventure_note(note):
        return False
    # "no restrictions" already filtered; require a real constraint/buff keyword.
    return bool(
        re.search(
            r"damage|dps|attack|gold|only|must|cannot|can't|may not|"
            r"required|banned|exclude|limit|seat|champion|familiar|"
            r"beperk|alleen|geen\s+\w+\s+champions?|schade|aanval",
            note,
            re.I,
        )
    )

def _gear_stats(stats: dict[str, Any], hero_id: int) -> tuple[float, float, float, float]:
    prefix = f"instrument_c{hero_id}_"
    dps = _parse_number(stats.get(f"{prefix}dps")) or 0.0
    d_mult = _parse_number(stats.get(f"{prefix}d_mult")) or 0.0
    hit_mult = _parse_number(stats.get(f"{prefix}hit_mult")) or 1.0
    if d_mult <= 0:
        d_mult = 0.01
    if dps <= 0:
        dps = 0.01
    score = dps * d_mult * max(hit_mult, 0.1)
    return score, dps, d_mult, hit_mult


def _loot_ilvl_by_hero(details: dict[str, Any]) -> dict[int, int]:
    """Average item level per hero — matches in-game bench ilvl (avg per gear slot)."""
    slot_levels: dict[int, dict[int, int]] = {}
    loot = details.get("loot")
    if not isinstance(loot, list):
        return {}
    for item in loot:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("hero_id"))
        slot_id = _parse_int(item.get("slot_id"))
        if hero_id is None or slot_id is None:
            continue
        enchant = _parse_int(item.get("enchant")) or 0
        slot_level = max(enchant, 0) + 1
        by_slot = slot_levels.setdefault(hero_id, {})
        by_slot[slot_id] = max(by_slot.get(slot_id, 0), slot_level)

    averages: dict[int, int] = {}
    for hero_id, by_slot in slot_levels.items():
        if not by_slot:
            continue
        averages[hero_id] = round(sum(by_slot.values()) / len(by_slot))
    return averages


def _ilvl_label(ilvl: int, pct_vs_avg: float) -> str:
    if abs(pct_vs_avg) < 1:
        return f"ilvl {ilvl} (≈ party-gemiddelde)"
    if pct_vs_avg >= 0:
        return f"ilvl {ilvl} (+{pct_vs_avg:.0f}% vs gem.)"
    return f"ilvl {ilvl} ({pct_vs_avg:.0f}% vs gem.)"


def _ilvl_below_avg_action(ilvl: int, pct_vs_avg: float, party_avg: float) -> str:
    below = max(0.0, -pct_vs_avg)
    return f"ilvl {ilvl} — {below:.0f}% onder party-gemiddelde ({party_avg:.0f})."


def _human_buff_note(multiplier: float | None) -> str | None:
    if multiplier is None or multiplier <= 1.5:
        return None
    if multiplier > 1000 or math.isinf(multiplier):
        return "Dit adventure heeft een zeer sterke damage-buff."
    return f"Adventure damage-buff: ongeveer {multiplier:.1f}×."


@dataclass(frozen=True)
class FormationHero:
    hero_id: int
    name: str
    seat: int | None
    level: int
    gear_score: float
    ilvl: int
    ilvl_pct_vs_avg: float
    gear_rank: int
    gear_rank_total: int
    gear_pct_of_best: float
    gear_label: str
    role_label: str
    roles: tuple[str, ...]
    tags: tuple[str, ...]
    highest_damage: float
    active_feats: int
    is_top_damage: bool


@dataclass(frozen=True)
class HeroImprovement:
    priority: int
    hero_name: str | None
    seat: int | None
    headline: str
    action: str


@dataclass(frozen=True)
class AdvisorTip:
    priority: int
    title: str
    detail: str


@dataclass(frozen=True)
class AdvisorReport:
    goal: GoalMode
    context: ContextMode
    adventure_name: str
    adventure_id: int | None
    gold_growth_rate: float | None
    adventure_buff_note: str | None
    main_dps_name: str | None
    formation_heroes: tuple[FormationHero, ...]
    improvements: tuple[HeroImprovement, ...]
    tips: tuple[AdvisorTip, ...]
    summary: str
    specialization_insights: tuple[Any, ...] = ()
    adventure_restrictions_note: str | None = None
    formation_insights: tuple[Any, ...] = ()
    seat_report: Any | None = None


def _formation_heroes(payload: dict[str, Any]) -> tuple[FormationHero, ...]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return ()

    instance = _active_game_instance(payload)
    if instance is None:
        return ()

    stats = instance.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    db = _load_champion_db()
    name_lookup = _names_from_payload(payload)

    highest_damage_hero_id = _parse_int(stats.get("this_reset_highest_damage_dealt_hero_id"))

    seat_by_hero: dict[int, int] = {}
    hero_in_seats = instance.get("hero_in_seats")
    if isinstance(hero_in_seats, dict):
        for seat_raw, hero_raw in hero_in_seats.items():
            seat = _parse_int(seat_raw)
            hero_id = _parse_int(hero_raw)
            if seat is not None and hero_id is not None:
                seat_by_hero[hero_id] = seat

    try:
        from ic_gamedata.formation_seats import active_formation_seats
    except ImportError:
        active_seats: frozenset[int] = frozenset()
    else:
        _active_id, active_seats = active_formation_seats(payload)

    heroes_raw = details.get("heroes")
    if not isinstance(heroes_raw, list):
        return ()

    ilvl_by_hero = _loot_ilvl_by_hero(details)

    rows: list[FormationHero] = []
    best_row_by_hero: dict[int, tuple[tuple[int, int, float], FormationHero]] = {}
    active_party_id = _parse_int(details.get("active_game_instance_id"))
    for hero in heroes_raw:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        seat = seat_by_hero.get(hero_id)
        if seat is None:
            continue
        if active_seats and seat not in active_seats:
            continue

        name, roles, tags = _hero_meta(hero_id, db, name_lookup=name_lookup)
        score, _dps, _d_mult, _hit = _gear_stats(stats, hero_id)
        level = _parse_int(hero.get("level")) or 0
        active_feats = len(hero.get("active_feats") or [])
        base_dmg = _parse_number(stats.get(f"champion_{hero_id}_base_damage_this_reset")) or 0.0
        ult_dmg = _parse_number(stats.get(f"champion_{hero_id}_ultimate_damage_this_reset")) or 0.0
        highest_damage = max(base_dmg, ult_dmg)
        ilvl = ilvl_by_hero.get(hero_id, 0)
        game_instance_id = _parse_int(hero.get("game_instance_id")) or 0
        party_match = 1 if active_party_id is not None and game_instance_id == active_party_id else 0

        candidate = FormationHero(
            hero_id=hero_id,
            name=name,
            seat=seat,
            level=level,
            gear_score=score,
            ilvl=ilvl,
            ilvl_pct_vs_avg=0.0,
            gear_rank=0,
            gear_rank_total=0,
            gear_pct_of_best=0.0,
            gear_label="",
            role_label=_role_label(roles, tags),
            roles=roles,
            tags=tags,
            highest_damage=highest_damage,
            active_feats=active_feats,
            is_top_damage=highest_damage_hero_id == hero_id,
        )
        rank = (party_match, level, score)
        existing = best_row_by_hero.get(hero_id)
        if existing is None or rank > existing[0]:
            best_row_by_hero[hero_id] = (rank, candidate)

    rows = [item[1] for item in best_row_by_hero.values()]

    if not rows:
        return ()

    party_avg_ilvl = sum(hero.ilvl for hero in rows) / len(rows)
    rows.sort(key=lambda row: row.gear_score, reverse=True)
    best = rows[0].gear_score if rows[0].gear_score > 0 else 1.0
    total = len(rows)
    ranked: list[FormationHero] = []
    for index, hero in enumerate(rows, start=1):
        pct = (hero.gear_score / best) * 100.0
        if party_avg_ilvl > 0:
            pct_vs_avg = ((hero.ilvl - party_avg_ilvl) / party_avg_ilvl) * 100.0
        else:
            pct_vs_avg = 0.0
        ranked.append(
            FormationHero(
                hero_id=hero.hero_id,
                name=hero.name,
                seat=hero.seat,
                level=hero.level,
                gear_score=hero.gear_score,
                ilvl=hero.ilvl,
                ilvl_pct_vs_avg=pct_vs_avg,
                gear_rank=index,
                gear_rank_total=total,
                gear_pct_of_best=pct,
                gear_label=_ilvl_label(hero.ilvl, pct_vs_avg),
                role_label=hero.role_label,
                roles=hero.roles,
                tags=hero.tags,
                highest_damage=hero.highest_damage,
                active_feats=hero.active_feats,
                is_top_damage=hero.is_top_damage,
            )
        )
    return tuple(ranked)


def _owned_heroes(payload: dict[str, Any]) -> list[tuple[int, str, tuple[str, ...], tuple[str, ...]]]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return []
    db = _load_champion_db()
    name_lookup = _names_from_payload(payload)
    rows: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]] = []
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict) or hero.get("owned") not in ("1", 1, True):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        name, roles, tags = _hero_meta(hero_id, db, name_lookup=name_lookup)
        rows.append((hero_id, name, roles, tags))
    return rows


def _is_debuffer(hero: FormationHero) -> bool:
    return "debuffer" in hero.tags or "bud" in hero.tags or hero.name in _known_debuffers()


def _is_buffer(hero: FormationHero) -> bool:
    return "buffer" in hero.tags or hero.name in _known_buffers()


def _is_tank(hero: FormationHero) -> bool:
    return "tank" in hero.roles


def _is_dps(hero: FormationHero) -> bool:
    return "dps" in hero.roles


def _is_speed(hero: FormationHero) -> bool:
    return "speed" in hero.tags


def _resolve_bud_hero(formation: tuple[FormationHero, ...]) -> FormationHero | None:
    """
    Champion to stack buffs/debuffers on for BUD.

    Prefer the game's hardest hit (when that champion is a DPS), else the best DPS
    by observed damage — not the best-geared support/tank (e.g. Eric).
    """
    if not formation:
        return None

    top_damage = next((h for h in formation if h.is_top_damage), None)
    dps_heroes = [h for h in formation if _is_dps(h)]

    if top_damage is not None and _is_dps(top_damage):
        return top_damage

    if dps_heroes:
        best_dps = max(dps_heroes, key=lambda h: (h.highest_damage, h.gear_score))
        if top_damage is not None and (
            _is_buffer(top_damage)
            or (_is_tank(top_damage) and not _is_dps(top_damage))
            or ("support" in top_damage.roles and not _is_dps(top_damage))
        ):
            return best_dps
        if top_damage is not None:
            return top_damage
        return best_dps

    if top_damage is not None:
        return top_damage
    return formation[0]


def _resolve_speed_hero(formation: tuple[FormationHero, ...]) -> FormationHero | None:
    speed_heroes = [hero for hero in formation if _is_speed(hero)]
    if not speed_heroes:
        return None
    return max(speed_heroes, key=lambda hero: (hero.gear_score, hero.level))


_BUFFER_PLACEMENT_RULES = frozenset(
    {"carry_no_buffer_adjacent", "buffer_far_from_carry", "support_far_from_carry"}
)


def _coverage_from_formation_insights(insights: tuple[Any, ...]) -> frozenset[str]:
    """Rule IDs already handled by the formation advisor (suppress duplicate legacy tips)."""
    covered = frozenset(
        insight.rule_id for insight in insights if getattr(insight, "rule_id", "")
    )
    if covered & _BUFFER_PLACEMENT_RULES:
        covered = covered | frozenset({"buffer_placement"})
    return covered


def _bench_suggestions(
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    in_party: set[int],
    *,
    want_roles: set[str] | None = None,
    want_tags: set[str] | None = None,
    limit: int = 3,
    roster_filter: Any | None = None,
) -> list[str]:
    if roster_filter is not None:
        from ic_gamedata.adventure_restrictions import filter_allowed_hero_names

        return filter_allowed_hero_names(
            owned,
            in_party,
            roster_filter,
            want_roles=want_roles,
            want_tags=want_tags,
            limit=limit,
        )

    names: list[str] = []
    for hero_id, name, roles, tags in owned:
        if hero_id in in_party:
            continue
        if want_roles and not (want_roles & set(roles)):
            continue
        if want_tags and not (want_tags & set(tags)):
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return names


def _seat_zone_guess(seat: int) -> str:
    column = ((seat - 1) % 4) + 1
    if column == 1:
        return "front"
    if column == 4:
        return "back"
    return "mid"


def _disallowed_replacement_detail(
    formation: tuple[FormationHero, ...],
    disallowed_heroes: list[FormationHero],
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    roster_filter: Any,
    *,
    goal: GoalMode,
    context: ContextMode,
    ilvl_by_hero: dict[int, int] | None = None,
    limit_per_hero: int = 2,
) -> str | None:
    if not disallowed_heroes or roster_filter is None:
        return None

    from ic_gamedata.seat_advisor.bench_ranker import rank_bench_alternatives
    from ic_gamedata.seat_advisor.role_inference import infer_seat_role

    in_party = {hero.hero_id for hero in formation}
    bud = _resolve_bud_hero(formation)
    bud_id = bud.hero_id if bud else None
    ilvl_map = ilvl_by_hero or {}
    parts: list[str] = []

    for hero in disallowed_heroes:
        seat = hero.seat or 1
        role = infer_seat_role(
            hero,
            zone=_seat_zone_guess(seat),
            bud_hero_id=bud_id,
            goal=goal,
            context=context,
        )
        alternatives = rank_bench_alternatives(
            role=role,
            current_hero=hero,
            owned=owned,
            in_party=in_party,
            roster_filter=roster_filter,
            ilvl_by_hero=ilvl_map,
            limit=limit_per_hero,
        )
        seat_txt = f" (slot {hero.seat})" if hero.seat is not None else ""
        if alternatives:
            names = ", ".join(alt.hero_name for alt in alternatives)
            parts.append(f"{hero.name}{seat_txt} → {names}")
            continue

        fallback = _bench_suggestions(
            owned,
            in_party,
            roster_filter=roster_filter,
            limit=limit_per_hero,
        )
        if fallback:
            parts.append(f"{hero.name}{seat_txt} → {', '.join(fallback)} (bench)")
        else:
            parts.append(f"{hero.name}: geen toegestane vervanger op bench")

    if not parts:
        return None
    return "Alternatieven: " + " · ".join(parts)


def _composition_advice(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    roster_filter: Any | None = None,
    covered: frozenset[str] = frozenset(),
    player_capacity: int | None = None,
) -> list[AdvisorTip]:
    """Formatie-/samenstellingsadvies — alleen als er iets nuttigs te verbeteren valt."""
    if len(formation) < 2:
        return []

    tips: list[AdvisorTip] = []
    main = _resolve_bud_hero(formation) or formation[0]
    in_party = {h.hero_id for h in formation}
    tanks = [h for h in formation if _is_tank(h)]
    dps = [h for h in formation if _is_dps(h)]
    supports = [h for h in formation if "support" in h.roles]
    speed = [h for h in formation if _is_speed(h)]
    buffers = [h for h in formation if _is_buffer(h)]

    # Te weinig champions in formation (formation advisor covers this when enabled)
    if player_capacity is not None:
        is_underfilled = len(formation) < player_capacity
        capacity_label = player_capacity
    else:
        is_underfilled = len(formation) <= 7
        capacity_label = None

    if is_underfilled and "formation_not_full" not in covered:
        if capacity_label is not None:
            detail = (
                f"Je hebt {len(formation)} van {capacity_label} beschikbare champion-slots gevuld "
                "(NPC-slots tellen niet mee). "
                "Vul lege slots met supports/buffers — dat levert meestal meer op dan een extra DPS."
            )
        else:
            detail = (
                f"Je hebt {len(formation)} champions in formation. "
                "Vul lege slots met supports/buffers — dat levert meestal meer op dan een extra DPS."
            )
        tips.append(_tip(2, "Formatie niet vol", detail))

    # Geen tank waar overleving telt
    if not tanks and context in ("push", "campaign"):
        suggestions = _bench_suggestions(
            owned, in_party, want_roles={"tank"}, roster_filter=roster_filter
        )
        detail = "Zet een tank vooraan (bijv. Nayeli, Briv, Torogar) om langer te overleven."
        if suggestions:
            detail += f" Op de bank: {', '.join(suggestions)}."
        tips.append(_tip(2, "Geen tank in formation", detail))

    # Te veel DPS, te weinig support — alleen bij BUD
    if goal == "bud" and len(dps) >= 3 and len(buffers) <= 1:
        dps_names = ", ".join(h.name for h in dps[:4])
        tips.append(
            _tip(
                2,
                "Te veel DPS t.o.v. support",
                f"DPS in party: {dps_names}. Focus buffs op één carry ({main.name}) "
                "of wissel een DPS om voor een buffer/support.",
            )
        )

    # Carry heeft geen DPS-rol
    if goal == "bud" and not _is_dps(main) and dps:
        tips.append(
            _tip(
                2,
                f"Carry-focus: {main.name} is geen DPS",
                f"{main.name} heeft de sterkste instrument-score, maar {dps[0].name} "
                "heeft wel een DPS-rol. Overweeg buffs/debuffers op die DPS te richten.",
            )
        )

    # Speed / Modron zonder speed champion
    if (goal == "speed" or context == "modron") and not speed and "modron_no_speed" not in covered:
        suggestions = _bench_suggestions(
            owned, in_party, want_tags={"speed"}, roster_filter=roster_filter
        )
        detail = "Voor areas/uur helpt een speed champion (Briv, Hank, Widdle, Deekin)."
        if suggestions:
            detail += f" Beschikbaar: {', '.join(suggestions)}."
        priority = 1 if goal == "speed" else 2
        tips.append(_tip(priority, "Geen speed champion", detail))

    # Push zonder debuffer + zonder tank is already covered separately;
    # Push met veel healers/tanks maar weinig DPS
    if context == "push" and goal == "bud" and len(dps) == 0:
        tips.append(
            _tip(
                1,
                "Geen DPS in push-formation",
                "Aan je wall wil je minstens één dedicated single-target DPS als carry.",
            )
        )

    # Support-arme party — skip when formation advisor already flagged buffer placement
    if (
        goal == "bud"
        and len(supports) <= 1
        and len(formation) >= 8
        and "buffer_placement" not in covered
        and not any(t.title.startswith("Te veel DPS") for t in tips)
    ):
        tips.append(
            _tip(
                3,
                "Weinig support in formation",
                f"Met bijna alleen DPS/tank mist je positional buffs. "
                f"Voeg een buffer toe naast BUD {main.name} ({_seat_text(main.seat)}).",
            )
        )

    return tips


def _build_improvements(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    modifiers: list[str],
) -> list[HeroImprovement]:
    if not formation:
        return [
            HeroImprovement(
                priority=1,
                hero_name=None,
                seat=None,
                headline="Geen actieve formation gevonden",
                action="Start een adventure in Idle Champions en klik opnieuw op Analyseer party.",
            )
        ]

    items: list[HeroImprovement] = []
    main = _resolve_bud_hero(formation) or formation[0]
    top_damage = next((h for h in formation if h.is_top_damage), None)
    party_avg_ilvl = sum(hero.ilvl for hero in formation) / len(formation)

    if goal == "bud":
        if (
            top_damage is not None
            and top_damage.hero_id != main.hero_id
            and not main.is_top_damage
        ):
            items.append(
                HeroImprovement(
                    priority=2,
                    hero_name=top_damage.name,
                    seat=top_damage.seat,
                    headline="Hardste hit deze run",
                    action=(
                        f"De game registreerde de zwaarste hit op {top_damage.name} "
                        f"({_seat_text(top_damage.seat)}), niet op BUD-focus {main.name}. "
                        "Overweeg buffs te verschuiven als dit consistent blijft."
                    ),
                )
            )

        for hero in formation:
            if hero.hero_id == main.hero_id:
                continue
            if hero.ilvl_pct_vs_avg < -_RELATIVE_GEAR_WEAK_PCT:
                items.append(
                    HeroImprovement(
                        priority=2,
                        hero_name=hero.name,
                        seat=hero.seat,
                        headline="Gear onder party-gemiddelde",
                        action=_ilvl_below_avg_action(hero.ilvl, hero.ilvl_pct_vs_avg, party_avg_ilvl),
                    )
                )

        for hero in formation:
            if hero.active_feats == 0 and hero.role_label in ("DPS", "Onbekend"):
                items.append(
                    HeroImprovement(
                        priority=3,
                        hero_name=hero.name,
                        seat=hero.seat,
                        headline="Geen actief feat",
                        action="Zet een damage- of speed-feat aan als je die unlocked hebt.",
                    )
                )

        if context == "push" or context == "modron":
            pass

    elif goal == "speed":
        speed_main = _resolve_speed_hero(formation)
        if speed_main is None:
            suggestions = _bench_suggestions(
                owned, {h.hero_id for h in formation}, want_tags={"speed"}, roster_filter=None
            )
            action = "Zet een speed champion in party voor kortere runs (Briv, Widdle, Deekin, Hank)."
            if suggestions:
                action += f" Op bench: {', '.join(suggestions)}."
            items.append(
                HeroImprovement(
                    priority=1,
                    hero_name=None,
                    seat=None,
                    headline="Geen speed champion in formation",
                    action=action,
                )
            )
        else:
            if speed_main.active_feats == 0:
                items.append(
                    HeroImprovement(
                        priority=2,
                        hero_name=speed_main.name,
                        seat=speed_main.seat,
                        headline="Geen actief feat",
                        action="Zet een speed- of utility-feat aan op je speed carry.",
                    )
                )
            for hero in formation:
                if hero.hero_id == speed_main.hero_id:
                    continue
                if hero.ilvl_pct_vs_avg < -_RELATIVE_GEAR_WEAK_PCT:
                    items.append(
                        HeroImprovement(
                            priority=3,
                            hero_name=hero.name,
                            seat=hero.seat,
                            headline="Gear onder party-gemiddelde",
                            action=_ilvl_below_avg_action(
                                hero.ilvl, hero.ilvl_pct_vs_avg, party_avg_ilvl
                            ),
                        )
                    )

    elif goal == "gold":
        for hero in formation:
            if hero.ilvl_pct_vs_avg < -_RELATIVE_GEAR_WEAK_PCT and hero.hero_id != main.hero_id:
                items.append(
                    HeroImprovement(
                        priority=2,
                        hero_name=hero.name,
                        seat=hero.seat,
                        headline="Gear onder party-gemiddelde",
                        action=_ilvl_below_avg_action(hero.ilvl, hero.ilvl_pct_vs_avg, party_avg_ilvl),
                    )
                )

    items.sort(key=lambda item: item.priority)
    return items


def _formation_tips(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    modifiers: list[str],
    adventure_buff_note: str | None,
    gold_growth_rate: float | None,
    roster_filter: Any | None = None,
    covered: frozenset[str] = frozenset(),
    ilvl_by_hero: dict[int, int] | None = None,
    player_capacity: int | None = None,
) -> list[AdvisorTip]:
    """Tactische formation-tips met uitleg (zoals debuffer-advies)."""
    if not formation:
        return [
            _tip(
                1,
                "Geen formation gevonden",
                "Start een adventure in Idle Champions en klik opnieuw op Analyseer party.",
            )
        ]

    tips: list[AdvisorTip] = []
    main = _resolve_bud_hero(formation) or formation[0]
    debuffers = [h for h in formation if _is_debuffer(h)]
    buffers = [h for h in formation if _is_buffer(h)]

    if goal == "bud":
        if main.is_top_damage:
            tips.append(
                _tip(
                    1,
                    f"BUD deze run: {main.name}",
                    (
                        f"De game registreerde de hardste hit op {main.name} "
                        f"({_seat_text(main.seat)}, {main.gear_label}). "
                        "Richt buffers, debuffers en positional buffs op deze champion."
                    ),
                )
            )
        else:
            tips.append(
                _tip(
                    1,
                    f"BUD-focus: {main.name}",
                    (
                        f"Verwachte carry voor BUD-stacking: {main.name} "
                        f"({_seat_text(main.seat)}, {main.gear_label}). "
                        "Nog geen harde hit geregistreerd deze reset — stack buffs hier naarmate damage opbouwt."
                    ),
                )
            )

        if not debuffers and "carry_no_debuffer" not in covered:
            tips.append(
                _tip(
                    2,
                    f"Geen debuffer voor {main.name}",
                    (
                        f"Debuffers verhogen BUD op {main.name} via zware debuff-hits. "
                        "Overweeg Krull, Aila, Gromma, Spurt, Warden of Sisaspia in party."
                    ),
                )
            )

        if len(buffers) == 0 and "buffer_placement" not in covered:
            tips.append(
                _tip(
                    3,
                    f"Weinig buffers voor {main.name}",
                    (
                        f"Champions als Avren, Celeste, Birdsong en Gale verhogen single-target hits. "
                        f"Zet een buffer naast BUD {main.name} ({_seat_text(main.seat)})."
                    ),
                )
            )

        if context == "push":
            tips.append(
                _tip(
                    2,
                    "Push-modus",
                    f"Focus op één single-target DPS ({main.name}) plus debuffers. "
                    "AoE-champions zijn minder efficiënt aan je wall.",
                )
            )
        elif context == "modron":
            tips.append(
                _tip(
                    3,
                    "Modron-modus",
                    "BUD is hier minder belangrijk dan areas/uur. "
                    "Kies speed/support (Briv, Hank) boven pure BUD-stacking.",
                )
            )
        elif context == "events":
            tips.append(
                _tip(
                    3,
                    "Events-modus",
                    f"Check event-boons en variant-restrictions. "
                    f"Debuffer-stacking blijft sterk voor BUD {main.name}.",
                )
            )

        if adventure_buff_note:
            tips.append(
                _tip(
                    3,
                    "Adventure damage-buff",
                    adventure_buff_note,
                )
            )

    elif goal == "speed":
        speed_main = _resolve_speed_hero(formation)
        speed = [h for h in formation if _is_speed(h)]
        in_party = {h.hero_id for h in formation}
        from ic_gamedata.adventure_restrictions import is_hero_allowed

        if speed_main is not None:
            tips.append(
                _tip(
                    1,
                    f"Speed focus: {speed_main.name}",
                    (
                        f"Areas/uur draait om snelle clears — focus specs/feats op "
                        f"{speed_main.name} ({_seat_text(speed_main.seat)}, {speed_main.gear_label}). "
                        "Combineer met genoeg DPS/support om areas vlot te resetten."
                    ),
                )
            )
        else:
            bench_speed = [
                name
                for hid, name, roles, tags in owned
                if "speed" in tags
                and hid not in in_party
                and is_hero_allowed(hid, roster_filter)
            ]
            detail = "Zonder speed champion mis je areas/uur. Briv, Widdle, Deekin en Hank zijn gangbare keuzes."
            if bench_speed:
                detail += " Op bench: " + ", ".join(bench_speed[:4]) + "."
            tips.append(_tip(1, "Geen speed champion in formation", detail))

        if len(speed) > 1:
            names = ", ".join(h.name for h in speed)
            tips.append(
                _tip(
                    3,
                    f"Meerdere speed champions: {names}",
                    "Meestal volstaat één primary speed carry; extra slots zijn beter voor DPS/support.",
                )
            )

        dps = [h for h in formation if _is_dps(h)]
        if len(dps) == 0:
            tips.append(
                _tip(
                    2,
                    "Weinig DPS voor speed runs",
                    "Speed stacking helpt pas als je areas snel genoeg cleart — voeg minstens één carry toe.",
                )
            )

        if context == "modron":
            tips.append(
                _tip(
                    2,
                    "Modron farming",
                    "Korte resets en hoge areas/uur zijn het doel — prioriteer speed-specs en snelle kills.",
                )
            )
        elif context == "campaign":
            tips.append(
                _tip(
                    3,
                    "Campaign speed",
                    "Farm favor/gold sneller door areas kort te houden met speed + burst DPS.",
                )
            )

    elif goal == "gold":
        if gold_growth_rate is not None:
            tips.append(
                _tip(
                    1,
                    f"Gold growth rate: {gold_growth_rate:.2f}×",
                    "Hogere waarde = meer gold per kill op dit adventure.",
                )
            )

        gold_in_party = [h for h in formation if "gold" in h.tags or "gold" in h.roles]
        in_party = {h.hero_id for h in formation}
        from ic_gamedata.adventure_restrictions import is_hero_allowed

        bench_gold = [
            name
            for hid, name, roles, tags in owned
            if ("gold" in tags or "gold" in roles)
            and hid not in in_party
            and is_hero_allowed(hid, roster_filter)
        ]

        if gold_in_party:
            names = ", ".join(h.name for h in gold_in_party)
            tips.append(
                _tip(
                    1,
                    f"Gold champion(s) in formation: {names}",
                    "Houd gold-champions in party voor campaign/event farming.",
                )
            )
        elif bench_gold and "gold_no_gold_role" not in covered:
            tips.append(
                _tip(
                    1,
                    "Geen gold champion in formation",
                    "Overweeg: "
                    + ", ".join(bench_gold[:4])
                    + ". Jarlaxle, Pisl, Freely en Ellywick zijn gangbare keuzes.",
                )
            )
        else:
            tips.append(
                _tip(
                    2,
                    "Geen gold specialist gevonden",
                    "Unlock Jarlaxle (gold) of Pisl voor dedicated gold income.",
                )
            )

        tips.append(
            _tip(
                2,
                "Kill speed = gold speed",
                f"Sterkste gear: {main.name}. Sneller areas clearen levert meer gold op, "
                "vooral zonder dedicated gold champion.",
            )
        )

        if context == "campaign":
            tips.append(
                _tip(
                    2,
                    "Campaign farming",
                    "Combineer gold champion met voldoende DPS om areas snel te clearen. "
                    "Patron currency is apart — kies de juiste patron per adventure.",
                )
            )
        elif context == "events":
            tips.append(
                _tip(
                    2,
                    "Event farming",
                    "Prioriteit: event tokens (Strongheart e.a.) boven raw gold. "
                    "Check event-boons in game voor bonuses.",
                )
            )
        elif context == "push":
            tips.append(
                _tip(
                    3,
                    "Push / wall",
                    "Gold income is hier niet de bottleneck — focus op DPS om verder te push.",
                )
            )
        elif context == "modron":
            tips.append(
                _tip(
                    2,
                    "Modron farming",
                    "Areas/uur telt meer dan gold/uur. Gebruik speed champions (Briv) en korte resets.",
                )
            )

    for note in modifiers[:2]:
        if _is_actionable_adventure_rule(note):
            tips.append(_tip(3, "Adventure-regel", note))

    if roster_filter is not None and formation:
        from ic_gamedata.adventure_restrictions import is_hero_allowed, restriction_summary

        formation_ids = frozenset(hero.hero_id for hero in formation)
        disallowed_heroes = [
            hero
            for hero in formation
            if not is_hero_allowed(hero.hero_id, roster_filter, formation_hero_ids=formation_ids)
        ]
        if disallowed_heroes:
            summary = restriction_summary(roster_filter)
            detail = (
                f"{', '.join(hero.name for hero in disallowed_heroes)} voldoen niet aan de adventure-beperkingen"
                + (f" ({summary})." if summary else ".")
            )
            replacement = _disallowed_replacement_detail(
                formation,
                disallowed_heroes,
                owned,
                roster_filter,
                goal=goal,
                context=context,
                ilvl_by_hero=ilvl_by_hero,
            )
            if replacement:
                detail = f"{detail} {replacement}"
            tips.append(_tip(1, "Champions niet toegestaan op dit adventure", detail))

    tips.extend(
        _composition_advice(
            formation,
            goal=goal,
            context=context,
            owned=owned,
            roster_filter=roster_filter,
            covered=covered,
            player_capacity=player_capacity,
        )
    )

    tips.sort(key=lambda t: t.priority)
    return [
        AdvisorTip(priority=index, title=tip.title, detail=tip.detail)
        for index, tip in enumerate(tips, start=1)
    ]


def _tip(priority: int, title: str, detail: str) -> AdvisorTip:
    return AdvisorTip(priority=priority, title=title, detail=detail)


_GENERIC_FORMATION_TIP_TITLES = frozenset(
    {
        "adventure damage-buff",
        "adventure-regel",
        "push-modus",
        "modron-modus",
        "events-modus",
        "campaign farming",
        "event farming",
        "push / wall",
        "modron farming",
        "kill speed = gold speed",
    }
)


def _is_relevant_formation_tip(tip: AdvisorTip, *, has_seat_report: bool) -> bool:
    """Drop open-deur tips that duplicate seat cards or state the obvious."""
    title = tip.title.casefold().strip()
    if has_seat_report and (
        title.startswith("bud deze run:")
        or title.startswith("bud-focus:")
        or title.startswith("speed focus:")
    ):
        return False
    if title in _GENERIC_FORMATION_TIP_TITLES:
        return False
    if title.startswith("gold growth rate:"):
        return False
    if title.startswith("gold champion(s) in formation:"):
        return False
    return True


def _filter_relevant_formation_tips(
    tips: list[AdvisorTip] | tuple[AdvisorTip, ...],
    *,
    has_seat_report: bool,
) -> tuple[AdvisorTip, ...]:
    filtered = [
        tip for tip in tips if _is_relevant_formation_tip(tip, has_seat_report=has_seat_report)
    ]
    return tuple(
        AdvisorTip(priority=index, title=tip.title, detail=tip.detail)
        for index, tip in enumerate(filtered, start=1)
    )


def analyze_party(
    payload: dict[str, Any],
    *,
    goal: GoalMode,
    context: ContextMode,
    include_specializations: bool = True,
    include_formation: bool = True,
) -> AdvisorReport:
    """Build advisor report from raw getuserdetails JSON."""
    instance = _active_game_instance(payload) or {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}

    adventure_id = _parse_int(instance.get("current_adventure_id") or details.get("current_adventure_id"))
    adventure_name = _adventure_name(payload, adventure_id)
    modifiers = _adventure_modifiers(payload, adventure_id)

    from ic_gamedata.adventure_restrictions import (
        build_adventure_roster_filter,
        player_formation_capacity,
        restriction_summary,
    )

    roster_filter = build_adventure_roster_filter(payload, adventure_id)
    restrictions_note = restriction_summary(roster_filter)
    player_capacity = player_formation_capacity(payload, adventure_id)

    adventure_data = instance.get("adventure_data")
    if not isinstance(adventure_data, dict):
        adventure_data = details.get("adventure_data") if isinstance(details.get("adventure_data"), dict) else {}
    gold_growth = _parse_number(adventure_data.get("gold_growth_rate"))

    stats = instance.get("stats") if isinstance(instance.get("stats"), dict) else {}
    global_mult = _parse_number(stats.get("global_dps_multiplier"))

    formation = _formation_heroes(payload)
    owned = _owned_heroes(payload)
    adventure_buff_note = _human_buff_note(global_mult)
    improvements = _build_improvements(
        formation,
        goal=goal,
        context=context,
        owned=owned,
        modifiers=modifiers,
    )

    formation_insights: tuple[Any, ...] = ()
    if include_formation and formation:
        from ic_gamedata.formation_advisor import build_formation_insights

        formation_insights = build_formation_insights(
            payload,
            formation,
            goal=goal,
            context=context,
            roster_filter=roster_filter,
        )

    covered = _coverage_from_formation_insights(formation_insights)

    ilvl_by_hero = _loot_ilvl_by_hero(details) if isinstance(details, dict) else {}

    tips = _formation_tips(
        formation,
        goal=goal,
        context=context,
        owned=owned,
        modifiers=modifiers,
        adventure_buff_note=adventure_buff_note,
        gold_growth_rate=gold_growth,
        roster_filter=roster_filter,
        covered=covered,
        ilvl_by_hero=ilvl_by_hero,
        player_capacity=player_capacity,
    )

    specialization_insights: tuple[Any, ...] = ()
    if include_specializations and formation:
        from ic_gamedata.party_advisor_specializations import (
            build_specialization_insights,
            party_specialization_composition_tips,
        )

        specialization_insights = build_specialization_insights(
            payload,
            formation,
            goal=goal,
            context=context,
            roster_filter=roster_filter,
        )
        spec_tips = party_specialization_composition_tips(
            formation,
            specialization_insights,
            goal=goal,
            context=context,
            owned=owned,
        )
        if spec_tips:
            combined = list(tips) + spec_tips
            combined.sort(key=lambda item: item.priority)
            tips = tuple(
                AdvisorTip(priority=index, title=tip.title, detail=tip.detail)
                for index, tip in enumerate(combined, start=1)
            )

    seat_report = None
    if formation:
        from ic_gamedata.seat_advisor import build_seat_advisor_report

        seat_report = build_seat_advisor_report(
            payload,
            formation,
            goal=goal,
            context=context,
            formation_insights=formation_insights,
            specialization_insights=specialization_insights,
            roster_filter=roster_filter,
        )

    tips = _filter_relevant_formation_tips(
        tips,
        has_seat_report=seat_report is not None and bool(seat_report.seats),
    )

    main_name = (_resolve_bud_hero(formation) or formation[0]).name if formation else None
    if goal == "bud":
        summary = (
            f"BUD-advies — {adventure_name}: focus op {main_name}."
            if main_name
            else f"BUD-advies — {adventure_name}."
        )
    elif goal == "speed":
        speed_name = (_resolve_speed_hero(formation) or (formation[0] if formation else None))
        speed_label = speed_name.name if speed_name is not None else None
        summary = (
            f"Speed-advies — {adventure_name}: focus op {speed_label}."
            if speed_label
            else f"Speed-advies — {adventure_name}."
        )
    else:
        summary = f"Gold-advies — {adventure_name}."

    return AdvisorReport(
        goal=goal,
        context=context,
        adventure_name=adventure_name,
        adventure_id=adventure_id,
        gold_growth_rate=gold_growth,
        adventure_buff_note=adventure_buff_note,
        main_dps_name=main_name,
        formation_heroes=formation,
        improvements=tuple(improvements),
        tips=tuple(tips),
        summary=summary,
        specialization_insights=specialization_insights,
        adventure_restrictions_note=restrictions_note,
        formation_insights=formation_insights,
        seat_report=seat_report,
    )


def _seat_text(seat: int | None) -> str:
    return f"slot {seat}" if seat is not None else "—"


def _improvements_for_hero(
    improvements: tuple[HeroImprovement, ...] | list[HeroImprovement],
    hero: FormationHero,
) -> list[HeroImprovement]:
    matched: list[HeroImprovement] = []
    for item in improvements:
        if (item.seat is not None and hero.seat is not None and item.seat == hero.seat) or (item.seat is None and item.hero_name == hero.name):
            matched.append(item)
    return matched


def _global_improvements(
    improvements: tuple[HeroImprovement, ...] | list[HeroImprovement],
) -> list[HeroImprovement]:
    return [item for item in improvements if item.hero_name is None]


def _heroes_by_seat(formation: tuple[FormationHero, ...]) -> list[FormationHero]:
    return sorted(formation, key=lambda hero: (hero.seat is None, hero.seat or 0, hero.name))


def format_report(report: AdvisorReport) -> str:
    """Human-readable report: party list with inline improve notes + tips."""
    goal_label_text = goal_label(report.goal)
    context_labels = {
        "campaign": "Campaign",
        "events": "Events",
        "push": "Push",
        "modron": "Modron",
    }

    lines = [
        report.summary,
        "",
        f"Doel: {goal_label_text}   ·   Context: {context_labels.get(report.context, report.context)}",
        f"Adventure: {report.adventure_name}",
    ]
    if report.gold_growth_rate is not None and report.goal == "gold":
        lines.append(f"Gold scaling adventure: {report.gold_growth_rate:.2f}×")
    if report.adventure_restrictions_note:
        lines.append(f"Champion-beperkingen: {report.adventure_restrictions_note}")

    lines.extend(["", "Party", "-" * 40])
    for item in _global_improvements(report.improvements):
        lines.append(f"! {item.headline}")
        lines.append(f"  → {item.action}")
        lines.append("")

    if not report.formation_heroes:
        lines.append("  Geen champions in actieve slots.")
    else:
        main_id = None
        bud = _resolve_bud_hero(report.formation_heroes)
        if bud is not None:
            main_id = bud.hero_id
        for hero in _heroes_by_seat(report.formation_heroes):
            notes: list[str] = []
            if hero.hero_id == main_id:
                notes.append("main focus")
            if hero.is_top_damage:
                notes.append("hardste hit")
            note_text = f" · {' · '.join(notes)}" if notes else ""
            lines.append(
                f"{hero.name} · {_seat_text(hero.seat)} · {hero.role_label} · {hero.gear_label}{note_text}"
            )
            for item in _improvements_for_hero(report.improvements, hero):
                if item.headline.lower() in item.action.lower():
                    lines.append(f"  → {item.action}")
                else:
                    lines.append(f"  → {item.headline}: {item.action}")
            if report.specialization_insights:
                from ic_gamedata.party_advisor_specializations import spec_summary_for_hero

                spec_line = spec_summary_for_hero(hero.hero_id, report.specialization_insights)
                if spec_line:
                    lines.append(f"  → {spec_line}")
            lines.append("")

    if report.specialization_insights:
        lines.extend(["Specialization & formatie", "-" * 40])
        for insight in report.specialization_insights:
            seat = _seat_text(insight.seat)
            lines.append(f"[{insight.priority}] {insight.headline} ({seat})")
            lines.append(f"    {insight.detail}")
            if insight.rule_source_type == "heuristic":
                lines.append("    (generieke placeholder-regel)")
            lines.append("")

    if report.formation_insights:
        lines.extend(["Formatie & posities", "-" * 40])
        for insight in report.formation_insights:
            seat = _seat_text(insight.seat)
            extra = ""
            if insight.related_seat is not None and insight.related_hero_name:
                extra = f" ↔ {insight.related_hero_name} ({_seat_text(insight.related_seat)})"
            elif insight.related_seat is not None:
                extra = f" → slot {insight.related_seat}"
            lines.append(f"[{insight.priority}] {insight.headline} ({seat}{extra})")
            lines.append(f"    {insight.detail}")
            if insight.rule_source_type == "heuristic":
                lines.append("    (heuristiek)")
            lines.append("")

    if report.tips:
        lines.extend(["Formation-tips", "-" * 40])
        for tip in report.tips:
            lines.append(f"[{tip.priority}] {tip.title}")
            lines.append(f"    {tip.detail}")
            lines.append("")

    return "\n".join(lines).rstrip()
