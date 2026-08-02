"""Formation parsing, champion metadata, and role helpers for party advisor."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.parsing import parse_number as _parse_number
from ic_gamedata.party_advisor_models import FormationHero

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


