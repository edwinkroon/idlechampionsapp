"""Parse adventure champion restrictions and filter roster suggestions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.specialization_data import (
    hero_ability_scores_map_from_cached_definitions,
    hero_age_map_from_cached_definitions,
    hero_attack_types_map_from_cached_definitions,
    hero_roles_map_from_champion_config,
    hero_tags_map_from_cached_definitions,
    hero_tags_map_from_champion_config,
)

_ROLE_TO_GAME_TAG = {
    "tank": "tanking",
    "support": "support",
    "healer": "healer",
    "dps": "dps",
    "gold": "gold",
}

_STAT_ALIASES = {
    "strength": "str",
    "str": "str",
    "dexterity": "dex",
    "dex": "dex",
    "constitution": "con",
    "con": "con",
    "intelligence": "int",
    "int": "int",
    "wisdom": "wis",
    "wis": "wis",
    "charisma": "cha",
    "cha": "cha",
}

_UNHANDLED_EXPR_MARKERS = (
    "is_any_upgrade_positional",
    "timeavailable",
    "numequipment",
    "numilevels",
    "get_stat(",
)

_STANDARD_RACE_TAGS = frozenset(
    {
        "human",
        "elf",
        "dwarf",
        "halfling",
        "halfing",
        "gnome",
        "half-elf",
        "halfelf",
        "half-orc",
        "half_orc",
    }
)
_NON_STANDARD_RACE_TAGS = frozenset(
    {
        "aasimar",
        "dragonborn",
        "goliath",
        "orc",
        "tiefling",
        "tabaxi",
        "gith",
        "githyanki",
        "githzerai",
        "firbolg",
        "kenku",
        "triton",
        "yuan-ti",
        "yuanti",
        "warforged",
        "changeling",
        "kalashtar",
        "shifter",
        "genasi",
        "fairy",
        "harengon",
        "loxodon",
        "minotaur",
        "centaur",
        "vedalken",
        "kobold",
        "goblin",
        "plasmoid",
        "kender",
        "leonin",
        "satyr",
        "tortle",
        "lizardfolk",
        "bugbear",
        "hobgoblin",
        "bullywug",
    }
)


_AFFILIATION_TAGS = frozenset(
    {
        "acqinc",
        "awfulones",
        "companion",
        "cteam",
        "emeraldenclave",
        "heroeslance",
        "majestics",
        "morndinsamman",
        "rivals",
        "wafflecrew",
    }
)


@dataclass(frozen=True)
class HeroRosterMeta:
    hero_id: int
    roles: frozenset[str]
    tags: frozenset[str]
    stats: dict[str, int]
    attack_types: frozenset[str]
    age: int | None = None

    @property
    def all_tags(self) -> frozenset[str]:
        role_tags = frozenset(_ROLE_TO_GAME_TAG.get(role, role) for role in self.roles)
        return self.tags | role_tags


@dataclass
class AdventureRosterFilter:
    required_tags: set[str] = field(default_factory=set)
    banned_tags: set[str] = field(default_factory=set)
    min_stats: list[tuple[str, int]] = field(default_factory=list)
    allow_exprs: list[str] = field(default_factory=list)
    exempt_hero_ids: set[int] = field(default_factory=set)
    banned_hero_ids: set[int] = field(default_factory=set)
    active_notes: list[str] = field(default_factory=list)
    has_unknown_rules: bool = False
    uses_api_game_changes: bool = False
    patron_id: int | None = None
    patron_blocked_hero_ids: set[int] = field(default_factory=set)

    def merge(self, other: AdventureRosterFilter) -> None:
        self.required_tags.update(other.required_tags)
        self.banned_tags.update(other.banned_tags)
        self.min_stats.extend(other.min_stats)
        self.allow_exprs.extend(other.allow_exprs)
        self.exempt_hero_ids.update(other.exempt_hero_ids)
        self.banned_hero_ids.update(other.banned_hero_ids)
        self.active_notes.extend(other.active_notes)
        self.has_unknown_rules = self.has_unknown_rules or other.has_unknown_rules
        self.uses_api_game_changes = self.uses_api_game_changes or other.uses_api_game_changes
        if other.patron_id is not None:
            self.patron_id = other.patron_id
        self.patron_blocked_hero_ids.update(other.patron_blocked_hero_ids)

    def has_roster_rules(self) -> bool:
        return bool(
            self.required_tags
            or self.banned_tags
            or self.min_stats
            or self.allow_exprs
            or self.banned_hero_ids
        )


def _hero_meta(hero_id: int) -> HeroRosterMeta:
    config_roles = hero_roles_map_from_champion_config().get(hero_id, ())
    config_tags = hero_tags_map_from_champion_config().get(hero_id, ())
    cached_tags = hero_tags_map_from_cached_definitions().get(hero_id, ())
    stats = hero_ability_scores_map_from_cached_definitions().get(hero_id, {})
    attack_types = hero_attack_types_map_from_cached_definitions().get(hero_id, frozenset())
    age = hero_age_map_from_cached_definitions().get(hero_id)
    return HeroRosterMeta(
        hero_id=hero_id,
        roles=frozenset(config_roles),
        tags=frozenset(config_tags) | frozenset(cached_tags),
        stats=stats,
        attack_types=attack_types,
        age=age,
    )


def _normalize_tag(tag: str) -> str:
    return tag.strip().lower().lstrip("!")


_SIMPLE_TAG = re.compile(r"^!?[a-z0-9_]+$")


def _filter_from_by_tags(tags_value: str, *, disallow: bool) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    raw = tags_value.strip()
    if not _SIMPLE_TAG.fullmatch(raw):
        filt.has_unknown_rules = True
        filt.active_notes.append("Complexe tag-regel uit API (niet volledig evalueerbaar)")
        return filt
    if raw.startswith("!") or disallow:
        filt.banned_tags.add(_normalize_tag(raw))
    else:
        filt.required_tags.add(_normalize_tag(raw))
    return filt


def _filter_from_by_stat(stats_list: list[dict[str, Any]], *, disallow: bool) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    for entry in stats_list:
        if not isinstance(entry, dict):
            continue
        stat = entry.get("stat")
        comp = str(entry.get("comp") or ">=").strip()
        value = _parse_int(entry.get("value"))
        if not isinstance(stat, str) or value is None:
            continue
        stat_key = _STAT_ALIASES.get(stat.strip().lower(), stat.strip().lower())
        if disallow:
            if comp in (">=", ">"):
                filt.allow_exprs.append(f"GetStat(`{stat_key}`) {comp} {value}")
            continue
        if comp in (">=", ">"):
            filt.min_stats.append((stat_key, value))
    return filt


def _filter_from_by_expr(expr: str, *, disallow: bool) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    cleaned = expr.strip()
    lowered = cleaned.casefold()
    if any(marker in lowered for marker in _UNHANDLED_EXPR_MARKERS):
        filt.has_unknown_rules = True
    if disallow:
        filt.banned_tags.update(_extract_has_tags(cleaned))
        return filt
    filt.allow_exprs.append(cleaned)
    for hero_id in _extract_hero_id_equals(cleaned):
        filt.exempt_hero_ids.add(hero_id)
    return filt


def _extract_has_tags(expr: str) -> set[str]:
    tags: set[str] = set()
    for match in re.finditer(r"HasTag\s*\(\s*[`']([^`']+)[`']\s*\)", expr, re.I):
        tags.add(match.group(1).strip().lower())
    return tags


def _extract_hero_id_equals(expr: str) -> set[int]:
    ids: set[int] = set()
    for match in re.finditer(r"hero_id\s*==\s*(\d+)", expr, re.I):
        hero_id = _parse_int(match.group(1))
        if hero_id is not None:
            ids.add(hero_id)
    return ids


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


def _active_patron_id(payload: dict[str, Any]) -> int | None:
    instance = _active_instance(payload)
    if isinstance(instance, dict):
        patron_id = _parse_int(instance.get("current_patron_id"))
        if patron_id is not None:
            return patron_id
    details = payload.get("details")
    if isinstance(details, dict):
        return _parse_int(details.get("current_patron_id"))
    return None


def _filter_from_patron(payload: dict[str, Any], patron_id: int | None) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    if patron_id is None or patron_id <= 0:
        return filt

    from ic_gamedata.patron_roster import (
        PATRON_NAMES,
        is_hero_allowed_on_patron,
        load_patron_roster,
    )

    roster = load_patron_roster()
    if not roster:
        filt.has_unknown_rules = True
        filt.active_notes.append("Patron-rooster ontbreekt — update config/patron_roster.json")
        return filt

    filt.patron_id = patron_id
    patron_name = PATRON_NAMES.get(patron_id, f"Patron {patron_id}")
    filt.active_notes.append(f"Actieve patron: {patron_name}")

    candidate_ids: set[int] = set(roster)
    details = payload.get("details")
    if isinstance(details, dict):
        for hero in details.get("heroes") or []:
            if isinstance(hero, dict):
                hero_id = _parse_int(hero.get("hero_id"))
                if hero_id is not None:
                    candidate_ids.add(hero_id)

    blocked = 0
    for hero_id in candidate_ids:
        allowed = is_hero_allowed_on_patron(hero_id, patron_id, payload)
        if allowed is False:
            filt.patron_blocked_hero_ids.add(hero_id)
            blocked += 1
    if blocked:
        filt.active_notes.append(f"Patron {patron_name}: {blocked} champions niet bruikbaar")
    return filt


def _filter_from_game_change(change: dict[str, Any]) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    change_type = str(change.get("type") or "").strip().lower()
    disallow = change_type == "disallow_crusaders"
    allow = change_type == "only_allow_crusaders"
    if not allow and not disallow:
        return filt

    filt.uses_api_game_changes = True

    by_tags = change.get("by_tags")
    if isinstance(by_tags, dict):
        tags_value = by_tags.get("tags")
        if isinstance(tags_value, str) and tags_value.strip():
            filt.merge(_filter_from_by_tags(tags_value, disallow=disallow))

    by_stat = change.get("by_stat")
    if isinstance(by_stat, dict):
        stats_list = by_stat.get("stats")
        if isinstance(stats_list, list):
            filt.merge(_filter_from_by_stat(stats_list, disallow=disallow))

    by_expr = change.get("by_expr")
    if isinstance(by_expr, dict):
        expr = by_expr.get("expr")
        if isinstance(expr, str) and expr.strip():
            filt.merge(_filter_from_by_expr(expr, disallow=disallow))
    return filt


def _parse_restrictions_text(text: str) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    if not text or not text.strip():
        return filt

    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = cleaned.replace("\r", "\n")
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]

    for line in lines:
        lower = line.casefold()

        if re.search(r"only champions with the support tag", lower):
            filt.required_tags.add("support")
            filt.active_notes.append("Alleen Support-champions")
            continue

        if re.search(r"tanking role can not be used|may not use tanking champions", lower):
            filt.banned_tags.add("tanking")
            filt.active_notes.append("Geen tanking-champions")
            continue

        if match := re.search(
            r"only champions with a (\w+) of (\d+) or higher|"
            r"may only use champions with (?:a |an )?(\w+) of (\d+) or higher|"
            r"only champions with a (\w+) score of (\d+) or higher",
            lower,
        ):
            stat_raw = next(g for g in match.groups()[::2] if g)
            value_raw = next(g for g in match.groups()[1::2] if g)
            stat_key = _STAT_ALIASES.get(stat_raw.strip(), stat_raw.strip())
            value = _parse_int(value_raw)
            if value is not None:
                filt.min_stats.append((stat_key, value))
                filt.active_notes.append(f"Min. {stat_key.upper()} {value}")
            continue

        if re.search(r"may only use good champions", lower):
            filt.allow_exprs.append("HasTag(`good`)")
            filt.active_notes.append("Alleen Good-champions (+ andere uitzonderingen)")
            continue

        if re.search(r"positional formation abilities", lower):
            filt.has_unknown_rules = True
            filt.active_notes.append("Alleen champions met positional abilities")
            continue

    return filt


def _adventure_define(payload: dict[str, Any], adventure_id: int | None) -> dict[str, Any] | None:
    if adventure_id is None:
        return None
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return None
    adventures = defines.get("adventure_defines")
    if not isinstance(adventures, list):
        return None
    for adv in adventures:
        if isinstance(adv, dict) and _parse_int(adv.get("id")) == adventure_id:
            return adv
    return None


def reserved_formation_seats(payload: dict[str, Any], adventure_id: int | None) -> frozenset[int]:
    """Seat numbers occupied by adventure NPCs (e.g. slot_escort treants)."""
    adv = _adventure_define(payload, adventure_id)
    if adv is None:
        return frozenset()

    reserved: set[int] = set()
    for change in adv.get("game_changes") or []:
        if not isinstance(change, dict):
            continue
        if str(change.get("type") or "").strip().lower() != "slot_escort":
            continue
        slot_ids = change.get("slot_ids")
        if not isinstance(slot_ids, list):
            continue
        for slot_raw in slot_ids:
            slot = _parse_int(slot_raw)
            if slot is not None:
                reserved.add(slot)
    return frozenset(reserved)


def _layout_formation_seat_count(payload: dict[str, Any]) -> int | None:
    """Total seats in the active formation layout (including empty / NPC slots)."""
    instance = _active_instance(payload)
    if isinstance(instance, dict):
        formation_list = instance.get("formation")
        if isinstance(formation_list, list) and formation_list:
            return len(formation_list)
        # Some payloads keep the live grid on details instead of the instance.
        details = payload.get("details")
        if isinstance(details, dict):
            details_formation = details.get("formation")
            if isinstance(details_formation, list) and details_formation:
                return len(details_formation)
        saves = instance.get("formation_saves_v2")
        if not isinstance(saves, list) or not saves:
            details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
            saves = details.get("formation_saves_v2") if isinstance(details, dict) else None
        if isinstance(saves, list):
            for save in saves:
                if not isinstance(save, dict):
                    continue
                grid = save.get("formation")
                if isinstance(grid, list) and grid:
                    return len(grid)
    return None


def player_formation_capacity(payload: dict[str, Any], adventure_id: int | None) -> int | None:
    """How many player champion seats are available after NPC/reserved slots."""
    layout_seats = _layout_formation_seat_count(payload)
    if layout_seats is None:
        return None
    reserved = reserved_formation_seats(payload, adventure_id)
    return max(layout_seats - len(reserved), 1)


def player_formation_filled_count(payload: dict[str, Any]) -> int | None:
    """How many live formation-grid slots currently hold a champion (id > 0)."""
    instance = _active_instance(payload)
    formation_list: list[Any] | None = None
    if isinstance(instance, dict) and "formation" in instance:
        raw = instance.get("formation")
        if isinstance(raw, list):
            formation_list = raw
    if formation_list is None:
        details = payload.get("details")
        if isinstance(details, dict):
            raw = details.get("formation")
            if isinstance(raw, list):
                formation_list = raw
    if formation_list is None:
        return None
    filled = 0
    for item in formation_list:
        hero_id = _parse_int(item)
        if hero_id is not None and hero_id > 0:
            filled += 1
    return filled


def _trials_unavailable_hero_ids(payload: dict[str, Any]) -> set[int]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return set()
    trials = details.get("trials_data")
    if not isinstance(trials, dict):
        return set()
    raw_ids = trials.get("unavailable_hero_ids")
    if not isinstance(raw_ids, list):
        return set()
    ids: set[int] = set()
    for item in raw_ids:
        hero_id = _parse_int(item)
        if hero_id is not None:
            ids.add(hero_id)
    return ids


def _note_from_game_change(change: dict[str, Any]) -> str | None:
    change_type = str(change.get("type") or "").strip().lower()
    if change_type == "only_allow_crusaders":
        by_tags = change.get("by_tags")
        if isinstance(by_tags, dict):
            tags_value = by_tags.get("tags")
            if isinstance(tags_value, str) and tags_value.strip():
                raw = tags_value.strip()
                if raw.startswith("!"):
                    return f"Geen tag: {_normalize_tag(raw)}"
                return f"Tag vereist: {raw}"
        by_stat = change.get("by_stat")
        if isinstance(by_stat, dict):
            stats_list = by_stat.get("stats")
            if isinstance(stats_list, list) and stats_list:
                entry = stats_list[0]
                if isinstance(entry, dict):
                    stat = entry.get("stat")
                    value = _parse_int(entry.get("value"))
                    if isinstance(stat, str) and value is not None:
                        return f"Min. {stat.upper()} {value} (API)"
        by_expr = change.get("by_expr")
        if isinstance(by_expr, dict):
            expr = by_expr.get("expr")
            if isinstance(expr, str) and expr.strip():
                return "Expressie-regel uit API"
    if change_type == "disallow_crusaders":
        by_tags = change.get("by_tags")
        if isinstance(by_tags, dict):
            tags_value = by_tags.get("tags")
            if isinstance(tags_value, str) and tags_value.strip():
                return f"Verboden tag: {tags_value.strip()}"
    return None


def build_adventure_roster_filter(
    payload: dict[str, Any],
    adventure_id: int | None,
) -> AdventureRosterFilter:
    """Build champion availability rules for the active adventure."""
    filt = AdventureRosterFilter()
    patron_id = _active_patron_id(payload)
    filt.merge(_filter_from_patron(payload, patron_id))
    adv = _adventure_define(payload, adventure_id)

    unavailable = _trials_unavailable_hero_ids(payload)
    if unavailable:
        filt.banned_hero_ids.update(unavailable)
        filt.active_notes.append(f"Trials: {len(unavailable)} champions niet beschikbaar")

    if adv is not None:
        for change in adv.get("game_changes") or []:
            if isinstance(change, dict):
                filt.merge(_filter_from_game_change(change))
                note = _note_from_game_change(change)
                if note and note not in filt.active_notes:
                    filt.active_notes.append(note)

        if not filt.has_roster_rules():
            restrictions = adv.get("restrictions_text")
            if isinstance(restrictions, str):
                filt.merge(_parse_restrictions_text(restrictions))

    if filt.required_tags and not any("tag" in note.casefold() for note in filt.active_notes):
        filt.active_notes.append(
            "Alleen champions met tag: " + ", ".join(sorted(filt.required_tags))
        )
    if filt.banned_tags and not any("tanking" in note.casefold() or "verboden" in note.casefold() for note in filt.active_notes):
        filt.active_notes.append(
            "Verboden tags: " + ", ".join(sorted(filt.banned_tags))
        )
    for stat, value in filt.min_stats:
        note = f"Min. {stat.upper()} {value}"
        if note not in filt.active_notes and not any(str(value) in n for n in filt.active_notes):
            filt.active_notes.append(note)

    if filt.min_stats or filt.allow_exprs:
        if not hero_ability_scores_map_from_cached_definitions() and not hero_tags_map_from_cached_definitions():
            filt.has_unknown_rules = True
            note = "cached_definitions.json ontbreekt — download via game voor volledige check"
            if note not in filt.active_notes:
                filt.active_notes.append(note)

    return filt


def _split_top_level(expr: str, operator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    index = 0
    op_len = len(operator)
    while index < len(expr):
        if expr[index] == "(":
            depth += 1
        elif expr[index] == ")":
            depth = max(0, depth - 1)
        if depth == 0 and expr[index : index + op_len] == operator:
            parts.append("".join(current).strip())
            current = []
            index += op_len
            continue
        current.append(expr[index])
        index += 1
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _normalize_specialization_expr(expr: str) -> str:
    """Normalize game per_hero_expr syntax into forms _eval_atom understands."""
    cleaned = expr.strip()
    if not cleaned:
        return cleaned
    previous = None
    while previous != cleaned:
        previous = cleaned
        if match := re.search(r"as_int\s*\(\s*(.+?)\s*\)", cleaned, re.I):
            cleaned = f"{cleaned[: match.start()]}{match.group(1)}{cleaned[match.end() :]}"
    cleaned = re.sub(r"\bmin_age\b", "age", cleaned, flags=re.I)
    return cleaned


def _hero_min_stat_amount(stats: dict[str, int]) -> int | None:
    if len(stats) < 6:
        return None
    return min(stats.get(key, 0) for key in ("str", "dex", "con", "int", "wis", "cha"))


def _hero_has_non_standard_race(meta: HeroRosterMeta) -> bool:
    tags = meta.all_tags
    if tags & _NON_STANDARD_RACE_TAGS:
        return True
    if tags & _STANDARD_RACE_TAGS:
        return False
    return False


def _eval_atom(atom: str, meta: HeroRosterMeta) -> bool | None:
    cleaned = atom.strip()
    if not cleaned:
        return True

    if cleaned.casefold() in _UNHANDLED_EXPR_MARKERS:
        return None

    if match := re.fullmatch(r"hero_id\s*==\s*(\d+)", cleaned, re.I):
        return meta.hero_id == _parse_int(match.group(1))

    if match := re.fullmatch(r"hero_id\s*!=\s*(\d+)", cleaned, re.I):
        target_id = _parse_int(match.group(1))
        if target_id is None:
            return None
        return meta.hero_id != target_id

    if match := re.fullmatch(r"age\s*(>=|<=|>|<)\s*(\d+)", cleaned, re.I):
        if meta.age is None:
            return None
        comp = match.group(1)
        threshold = _parse_int(match.group(2))
        if threshold is None:
            return None
        if comp == ">=":
            return meta.age >= threshold
        if comp == ">":
            return meta.age > threshold
        if comp == "<=":
            return meta.age <= threshold
        if comp == "<":
            return meta.age < threshold

    if cleaned.startswith("!"):
        negated = _eval_atom(cleaned[1:].strip(), meta)
        if negated is None:
            return None
        return not negated

    if re.fullmatch(r"has_base_attack_dmg_type_melee", cleaned, re.I):
        return "melee" in meta.attack_types if meta.attack_types else None

    if re.fullmatch(r"has_base_attack_dmg_type_ranged", cleaned, re.I):
        return "ranged" in meta.attack_types if meta.attack_types else None

    if re.fullmatch(r"has_base_attack_dmg_type_magic", cleaned, re.I):
        return "magic" in meta.attack_types if meta.attack_types else None

    if match := re.fullmatch(r"HasAttackDamageType\s*\(\s*[`'](\w+)[`']\s*\)", cleaned, re.I):
        attack = match.group(1).strip().lower()
        if not meta.attack_types:
            return None
        return attack in meta.attack_types

    if match := re.fullmatch(r"HasTag\s*\(\s*[`']([^`']+)[`']\s*\)", cleaned, re.I):
        return match.group(1).strip().lower() in meta.all_tags

    if re.fullmatch(r"has_affiliation", cleaned, re.I):
        return bool(meta.all_tags & _AFFILIATION_TAGS) or "companion" in meta.all_tags

    if match := re.fullmatch(
        r"GetStat\s*\(\s*[`'](\w+)[`']\s*\)\s*(>=|<=|>|<)\s*(\d+)",
        cleaned,
        re.I,
    ):
        stat_key = _STAT_ALIASES.get(match.group(1).strip().lower(), match.group(1).strip().lower())
        comp = match.group(2)
        threshold = _parse_int(match.group(3))
        if threshold is None:
            return None
        if stat_key == "total_ability_score":
            if len(meta.stats) < 6:
                return None
            value = sum(meta.stats.get(key, 0) for key in ("str", "dex", "con", "int", "wis", "cha"))
        else:
            value = meta.stats.get(stat_key)
            if value is None:
                return None
        if comp == ">=":
            return value >= threshold
        if comp == ">":
            return value > threshold
        if comp == "<=":
            return value <= threshold
        if comp == "<":
            return value < threshold

    if re.fullmatch(r"has_tag_speed", cleaned, re.I):
        return "speed" in meta.all_tags

    if re.fullmatch(r"has_non_standard_race", cleaned, re.I):
        return _hero_has_non_standard_race(meta)

    if cleaned.lower().startswith("clamp("):
        min_stat = _hero_min_stat_amount(meta.stats)
        if min_stat is None:
            return None
        if match := re.fullmatch(r"clamp\((\w+)\+1-min_stat_amount,0,1\)", cleaned, re.I):
            stat_key = _STAT_ALIASES.get(match.group(1).strip().lower(), match.group(1).strip().lower())
            stat_val = meta.stats.get(stat_key)
            if stat_val is None:
                return None
            return max(0, min(1, stat_val + 1 - min_stat)) == 1
        if match := re.fullmatch(r"clamp\(min_stat_amount\+1-(\w+),0,1\)", cleaned, re.I):
            stat_key = _STAT_ALIASES.get(match.group(1).strip().lower(), match.group(1).strip().lower())
            stat_val = meta.stats.get(stat_key)
            if stat_val is None:
                return None
            return max(0, min(1, min_stat + 1 - stat_val)) == 1

    if "is_any_upgrade_positional" in cleaned.casefold():
        return None

    return None


def _eval_expr(expr: str, meta: HeroRosterMeta) -> bool | None:
    or_parts = _split_top_level(expr, "||")
    results: list[bool | None] = []
    for or_part in or_parts:
        and_parts = _split_top_level(or_part, "&&")
        and_results = [_eval_atom(part, meta) for part in and_parts]
        if any(item is False for item in and_results):
            results.append(False)
        elif any(item is None for item in and_results):
            results.append(None)
        else:
            results.append(True)
    if any(item is True for item in results):
        return True
    if any(item is None for item in results):
        return None
    return False


def hero_matches_specialization_expr(hero_id: int, expr: str) -> bool | None:
    """Evaluate a per_hero_expr specialization qualifier for one champion."""
    cleaned = _normalize_specialization_expr(expr)
    if not cleaned:
        return None
    return _eval_expr(cleaned, _hero_meta(hero_id))


def is_hero_allowed(
    hero_id: int,
    roster_filter: AdventureRosterFilter | None,
    *,
    formation_hero_ids: frozenset[int] | None = None,
) -> bool:
    """Return True when the champion may be used on this adventure."""
    if roster_filter is None:
        return True

    if formation_hero_ids and hero_id in formation_hero_ids:
        return True

    if hero_id in roster_filter.banned_hero_ids:
        return False

    if hero_id in roster_filter.patron_blocked_hero_ids:
        return False

    if hero_id in roster_filter.exempt_hero_ids:
        return True

    meta = _hero_meta(hero_id)

    if roster_filter.banned_tags & meta.all_tags:
        return False

    if roster_filter.required_tags and not roster_filter.required_tags.issubset(meta.all_tags):
        return False

    for stat, minimum in roster_filter.min_stats:
        value = meta.stats.get(stat)
        if value is None or value < minimum:
            return False

    if roster_filter.allow_exprs:
        expr_results = [_eval_expr(expr, meta) for expr in roster_filter.allow_exprs]
        if any(result is True for result in expr_results):
            return True
        if all(result is False for result in expr_results):
            return False
        if roster_filter.has_unknown_rules:
            return False
        return False

    return True


def allowed_hero_ids(
    hero_ids: list[int] | tuple[int, ...],
    roster_filter: AdventureRosterFilter | None,
) -> frozenset[int]:
    """Evaluate API rules against candidate hero ids and return the allowed subset."""
    return frozenset(hid for hid in hero_ids if is_hero_allowed(hid, roster_filter))


def filter_allowed_hero_names(
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    in_party: set[int],
    roster_filter: AdventureRosterFilter | None,
    *,
    want_roles: set[str] | None = None,
    want_tags: set[str] | None = None,
    limit: int = 3,
) -> list[str]:
    names: list[str] = []
    for hero_id, name, roles, tags in owned:
        if hero_id in in_party:
            continue
        if want_roles and not (want_roles & set(roles)):
            continue
        if want_tags and not (want_tags & set(tags)):
            continue
        if not is_hero_allowed(hero_id, roster_filter):
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return names


def restriction_summary(roster_filter: AdventureRosterFilter | None) -> str | None:
    if roster_filter is None or not roster_filter.active_notes:
        return None
    unique = []
    seen: set[str] = set()
    for note in roster_filter.active_notes:
        key = note.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(note)
    if not unique:
        return None
    return " · ".join(unique[:4])
