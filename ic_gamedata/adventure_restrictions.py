"""Parse adventure champion restrictions and filter roster suggestions."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    # GetStat / get_stat are evaluated by _eval_atom — do not mark unknown.
)

_GETSTAT_GATE_RE = re.compile(
    r"GetStat\s*\(\s*[`']?(\w+)[`']?\s*\)\s*(>=|<=|==|>|<)\s*(\d+)",
    re.IGNORECASE,
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


# Supported ability-score comparators from API by_stat / restrictions_text.
_STAT_COMPARATORS = frozenset({">=", ">", "<=", "<"})


def _invert_comparator(operator: str) -> str | None:
    """Inclusive/exclusive-safe negation of a comparison operator."""
    mapping = {
        "<": ">=",
        "<=": ">",
        ">": "<=",
        ">=": "<",
        "==": "!=",
    }
    return mapping.get(operator)


def _sole_getstat_comparison(
    expr: str,
) -> tuple[str, str, int] | None:
    """Return (stat, operator, value) when expr is exactly one GetStat comparison."""
    cleaned = expr.strip()
    if not cleaned:
        return None
    if "||" in cleaned or "&&" in cleaned or cleaned.count("GetStat") != 1:
        return None
    # Reject surrounding NOT / function wrappers for this sole-gate helper.
    if re.search(r"\bnot\s*\(", cleaned, re.I) or cleaned.startswith("!"):
        return None
    match = _GETSTAT_GATE_RE.fullmatch(cleaned)
    if not match:
        # Allow optional outer whitespace already stripped; reject extras.
        match = _GETSTAT_GATE_RE.search(cleaned)
        if not match or match.group(0).strip() != cleaned:
            return None
    stat_raw = match.group(1).strip().lower()
    stat_key = _STAT_ALIASES.get(stat_raw, stat_raw)
    value = _parse_int(match.group(3))
    if value is None:
        return None
    return stat_key, match.group(2), value


def _normalize_inclusive_gate(
    gate: tuple[str, str, int],
) -> tuple[str, str, int] | None:
    """Normalize exclusive bounds to inclusive for integer ability scores."""
    stat, operator, value = gate
    if operator == "<":
        return (stat, "<=", value - 1)
    if operator == ">":
        return (stat, ">=", value + 1)
    if operator in ("<=", ">=", "=="):
        return (stat, operator, value)
    return None


def _gates_are_negations(
    gate_a: tuple[str, str, int],
    gate_b: tuple[str, str, int],
) -> bool:
    """True when gate_b is the integer-safe logical negation of gate_a."""
    na = _normalize_inclusive_gate(gate_a)
    nb = _normalize_inclusive_gate(gate_b)
    if na is None or nb is None or na[0] != nb[0]:
        return False
    inv_op = _invert_comparator(na[1])
    if inv_op is None:
        return False
    inv_norm = _normalize_inclusive_gate((na[0], inv_op, na[2]))
    return inv_norm == nb


def _gates_are_equivalent(
    gate_a: tuple[str, str, int],
    gate_b: tuple[str, str, int],
) -> bool:
    na = _normalize_inclusive_gate(gate_a)
    nb = _normalize_inclusive_gate(gate_b)
    return na is not None and na == nb


@dataclass
class AdventureRosterFilter:
    required_tags: set[str] = field(default_factory=set)
    banned_tags: set[str] = field(default_factory=set)
    # Legacy hard lower bounds (operator ">="). Prefer ability_score_gates.
    min_stats: list[tuple[str, int]] = field(default_factory=list)
    # Hard ability-score gates: (stat, operator, value) with operator in _STAT_COMPARATORS.
    ability_score_gates: list[tuple[str, str, int]] = field(default_factory=list)
    allow_exprs: list[str] = field(default_factory=list)
    # Expressions where true means blocked (deny-predicate).
    deny_exprs: list[str] = field(default_factory=list)
    # Audit trail for allow/deny interpretation decisions.
    expr_interpretations: list[dict[str, Any]] = field(default_factory=list)
    # True when API expr and restrictions_text disagree without safe reconciliation.
    has_restriction_semantics_conflict: bool = False
    exempt_hero_ids: set[int] = field(default_factory=set)
    banned_hero_ids: set[int] = field(default_factory=set)
    active_notes: list[str] = field(default_factory=list)
    has_unknown_rules: bool = False
    # True when a by_stat comparator could not be mapped — must not imply allowed.
    has_unevaluable_stat_rules: bool = False
    uses_api_game_changes: bool = False
    patron_id: int | None = None
    patron_blocked_hero_ids: set[int] = field(default_factory=set)
    # Undergeared-style: only lowest/highest average ilevel per permanent F-seat.
    # comparison: "least" | "most". Resolved ids filled at build time from loot.
    ilvl_seat_comparison: str | None = None
    ilvl_allowed_hero_ids: set[int] | None = None
    # Elminster-style: disallow when TimeAvailable(days) op threshold.
    # Example: days > 1095 → ban heroes whose release/rework is older than that.
    time_available_rule: dict[str, Any] | None = None
    # Human-readable restriction strings from adventure + patron defines.
    raw_restriction_texts: list[str] = field(default_factory=list)

    def merge(self, other: AdventureRosterFilter) -> None:
        self.required_tags.update(other.required_tags)
        self.banned_tags.update(other.banned_tags)
        self.min_stats.extend(other.min_stats)
        self.ability_score_gates.extend(other.ability_score_gates)
        self.allow_exprs.extend(other.allow_exprs)
        self.deny_exprs.extend(other.deny_exprs)
        self.expr_interpretations.extend(other.expr_interpretations)
        self.has_restriction_semantics_conflict = (
            self.has_restriction_semantics_conflict
            or other.has_restriction_semantics_conflict
        )
        self.exempt_hero_ids.update(other.exempt_hero_ids)
        self.banned_hero_ids.update(other.banned_hero_ids)
        self.active_notes.extend(other.active_notes)
        self.has_unknown_rules = self.has_unknown_rules or other.has_unknown_rules
        self.has_unevaluable_stat_rules = (
            self.has_unevaluable_stat_rules or other.has_unevaluable_stat_rules
        )
        self.uses_api_game_changes = self.uses_api_game_changes or other.uses_api_game_changes
        if other.patron_id is not None:
            self.patron_id = other.patron_id
        self.patron_blocked_hero_ids.update(other.patron_blocked_hero_ids)
        if other.ilvl_seat_comparison:
            self.ilvl_seat_comparison = other.ilvl_seat_comparison
        if other.ilvl_allowed_hero_ids is not None:
            if self.ilvl_allowed_hero_ids is None:
                self.ilvl_allowed_hero_ids = set(other.ilvl_allowed_hero_ids)
            else:
                self.ilvl_allowed_hero_ids &= other.ilvl_allowed_hero_ids
        if other.time_available_rule is not None:
            self.time_available_rule = dict(other.time_available_rule)
        for text in other.raw_restriction_texts:
            if text and text not in self.raw_restriction_texts:
                self.raw_restriction_texts.append(text)

    def has_roster_rules(self) -> bool:
        return bool(
            self.required_tags
            or self.banned_tags
            or self.min_stats
            or self.ability_score_gates
            or self.allow_exprs
            or self.deny_exprs
            or self.banned_hero_ids
            or self.has_restriction_semantics_conflict
            or self.uses_api_game_changes
            or self.ilvl_seat_comparison
            or self.ilvl_allowed_hero_ids is not None
            or self.time_available_rule is not None
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
# e.g. !(good|evil) or (good|evil) — OR-group of simple tags, optional outer negation.
_TAG_OR_GROUP = re.compile(r"^(!)?\(([a-z0-9_|]+)\)\s*$", re.I)


def _allow_expr_from_or_tags(tags: list[str]) -> str:
    parts = [f"HasTag(`{tag}`)" for tag in tags]
    return " || ".join(parts)


def _filter_from_by_tags(tags_value: str, *, disallow: bool) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    raw = tags_value.strip()
    or_match = _TAG_OR_GROUP.fullmatch(raw)
    if or_match:
        negated = bool(or_match.group(1))
        tags = [
            _normalize_tag(part)
            for part in or_match.group(2).split("|")
            if part.strip()
        ]
        if not tags:
            filt.has_unknown_rules = True
            filt.active_notes.append("Empty tag OR-group from API")
            return filt
        expr = _allow_expr_from_or_tags(tags)
        # disallow + !(good|evil)  →  allow good|evil
        # only_allow + (good|evil) →  allow good|evil
        # disallow + (good|evil)   →  deny good|evil (rare)
        # only_allow + !(good|evil)→  allow when neither (unusual)
        if (disallow and negated) or (not disallow and not negated):
            filt.allow_exprs.append(expr)
            filt.active_notes.append(
                "Alleen tags: " + " of ".join(tags)
            )
        elif disallow and not negated:
            filt.deny_exprs.append(expr)
            filt.active_notes.append(
                "Verboden tags: " + " of ".join(tags)
            )
        else:
            # only_allow + negated OR — keep as unknown rather than invent semantics.
            filt.has_unknown_rules = True
            filt.active_notes.append(
                f"Complex negated only_allow tag-group niet volledig geëvalueerd: {raw}"
            )
        return filt
    if not _SIMPLE_TAG.fullmatch(raw):
        filt.has_unknown_rules = True
        filt.active_notes.append("Complex tag rule from API (not fully evaluable)")
        return filt
    if raw.startswith("!") or disallow:
        filt.banned_tags.add(_normalize_tag(raw))
    else:
        filt.required_tags.add(_normalize_tag(raw))
    return filt


def _resolve_ilvl_allowed_hero_ids(
    payload: dict[str, Any],
    *,
    comparison: str,
) -> set[int] | None:
    """Heroes that win the per-seat average-ilevel contest (ties included)."""
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    try:
        from ic_gamedata.party_advisor_formation import _loot_ilvl_by_hero
        from ic_gamedata.specialization_data import (
            hero_seat_id_map_from_cached_definitions,
        )
    except ImportError:
        return None

    ilvl_map = _loot_ilvl_by_hero(details)
    seat_map = hero_seat_id_map_from_cached_definitions()
    if not seat_map:
        return None

    owned: set[int] = set()
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        owned_flag = hero.get("owned")
        if owned_flag in (True, 1, "1", "true", "True"):
            owned.add(hero_id)

    if not owned:
        return None

    by_seat: dict[int, list[tuple[int, int]]] = {}
    for hero_id in owned:
        seat = seat_map.get(hero_id)
        if seat is None or not (1 <= int(seat) <= 12):
            continue
        # Missing loot → treat as 0 average (worst gear), matching undergeared intent.
        ilvl = int(ilvl_map.get(hero_id, 0))
        by_seat.setdefault(int(seat), []).append((ilvl, hero_id))

    if not by_seat:
        return None

    want_least = comparison.strip().lower() in {"least", "lowest", "min"}
    allowed: set[int] = set()
    for rows in by_seat.values():
        target = min(ilvl for ilvl, _ in rows) if want_least else max(ilvl for ilvl, _ in rows)
        for ilvl, hero_id in rows:
            if ilvl == target:
                allowed.add(hero_id)
    return allowed


def _format_stat_gate_label(stat: str, operator: str, value: int) -> str:
    """Human-readable label sharing meaning with evaluation (not min-only)."""
    op = operator.strip()
    key = stat.upper()
    if op == ">=":
        return f"Min. {key} {value}"
    if op == ">":
        return f"{key} > {value}"
    if op == "<=":
        return f"Max. {key} {value}"
    if op == "<":
        return f"{key} < {value}"
    return f"{key} {op} {value}"


def _iter_hard_stat_gates(
    roster_filter: AdventureRosterFilter,
) -> list[tuple[str, str, int]]:
    """Unified hard ability-score gates (legacy min_stats + explicit gates)."""
    gates: list[tuple[str, str, int]] = []
    for stat, minimum in roster_filter.min_stats:
        gates.append((stat, ">=", minimum))
    for stat, operator, value in roster_filter.ability_score_gates:
        op = str(operator).strip()
        if op in _STAT_COMPARATORS:
            gates.append((stat, op, value))
    return gates


def _stat_value_passes(value: int, operator: str, threshold: int) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == ">":
        return value > threshold
    if operator == "<=":
        return value <= threshold
    if operator == "<":
        return value < threshold
    return False


def _stat_gate_fail_reason(
    stat: str,
    value: int | None,
    operator: str,
    threshold: int,
) -> str:
    key = stat.upper()
    if value is None:
        bound = _format_stat_gate_label(stat, operator, threshold)
        return f"{key} onbekend (basisscore ontbreekt); vereiste {bound}."
    if operator == "<=":
        return (
            f"{key} {value} overschrijdt de toegestane bovengrens van {threshold}."
        )
    if operator == "<":
        return f"{key} {value} moet lager zijn dan {threshold}."
    if operator == ">=":
        return f"{key} {value} < min {threshold} (character_sheet basis)."
    if operator == ">":
        return f"{key} {value} moet hoger zijn dan {threshold}."
    return f"{key} {value} voldoet niet aan {operator} {threshold}."


def _filter_from_by_stat(
    stats_list: list[dict[str, Any]],
    *,
    disallow: bool,
    pass_any: bool = False,
) -> AdventureRosterFilter:
    """Build gates from by_stat.

    For ``disallow_crusaders`` + ``pass_any: true`` (Zariel): blocked when *any*
    deny comparison is true ≡ must satisfy *all* inverted allow gates (AND).
    That matches text like \"STR ≥ 10 and CHA ≥ 13\".
    """
    filt = AdventureRosterFilter()
    deny_gates: list[tuple[str, str, int]] = []
    for entry in stats_list:
        if not isinstance(entry, dict):
            continue
        stat = entry.get("stat")
        raw_comp = entry.get("comp")
        # Missing comparator defaults to ">=" (historical API behaviour for mins).
        # Explicit unknown comparators must not be invented as a minimum.
        if raw_comp is None or (isinstance(raw_comp, str) and not raw_comp.strip()):
            comp = ">="
        else:
            comp = str(raw_comp).strip()
        value = _parse_int(entry.get("value"))
        if not isinstance(stat, str) or value is None:
            continue
        stat_key = _STAT_ALIASES.get(stat.strip().lower(), stat.strip().lower())
        if disallow:
            if comp in _STAT_COMPARATORS:
                # Proven API shape (e.g. Trials adventure 909 live getuserdetails):
                #   type=disallow_crusaders, by_stat={stat,comp,value}
                # When the comparison is true the champion is blocked (deny-when-true).
                # Historical bug: the same comparator was wrongly copied into
                # allow_exprs (true→allowed), inverting the rule for the AI/export.
                raw_expr = f"GetStat(`{stat_key}`) {comp} {value}"
                filt.deny_exprs.append(raw_expr)
                inv = _invert_comparator(comp)
                norm_gate: dict[str, Any] | None = None
                if inv is not None:
                    # Integer-safe equivalent allow gate, e.g. deny dex<12 ≡ allow dex>=12.
                    # Multiple deny comps with pass_any → AND of allow gates (Zariel).
                    filt.ability_score_gates.append((stat_key, inv, value))
                    deny_gates.append((stat_key, comp, value))
                    norm_gate = {
                        "stat": stat_key,
                        "operator": inv,
                        "value": value,
                    }
                    filt.active_notes.append(
                        f"{_format_stat_gate_label(stat_key, inv, value)} "
                        "(disallow by_stat)"
                    )
                filt.expr_interpretations.append(
                    {
                        "raw_expr": raw_expr,
                        "source": "by_stat",
                        "change_type": "disallow_crusaders",
                        "source_field": "game_changes.by_stat.stats",
                        "true_means": "denied",
                        "predicate_kind": "deny",
                        "pass_any": pass_any,
                        "sole_gate": {
                            "stat": stat_key,
                            "operator": comp,
                            "value": value,
                        },
                        "action": "treat_as_deny_normalize_allow",
                        "normalized_allow_gate": norm_gate,
                        "deny_to_allow_note": (
                            f"deny {stat_key} {comp} {value} ≡ allow "
                            f"{stat_key} {inv} {value}"
                            if inv is not None
                            else None
                        ),
                        "evidence": (
                            "disallow_crusaders + by_stat: true betekent geblokkeerd "
                            "(deny-when-true). Genormaliseerd naar equivalente "
                            "allow-gate; niet als allow_expr met dezelfde comparator."
                            + (
                                " pass_any=true → OR van deny-comps ≡ AND van allow-gates."
                                if pass_any
                                else ""
                            )
                        ),
                    }
                )
            else:
                filt.has_unknown_rules = True
                filt.has_unevaluable_stat_rules = True
                filt.active_notes.append(
                    f"Onbekende stat-comparator in disallow-regel: {comp!r}"
                )
            continue
        if comp in _STAT_COMPARATORS:
            filt.ability_score_gates.append((stat_key, comp, value))
        else:
            filt.has_unknown_rules = True
            filt.has_unevaluable_stat_rules = True
            filt.active_notes.append(
                f"Onbekende stat-comparator: {comp!r} (niet als min/max geïnterpreteerd)"
            )
    if disallow and pass_any and len(deny_gates) > 1:
        filt.active_notes.append(
            "Patron/adventure pass_any: alle genormaliseerde min-eisen gelden tegelijk"
        )
    return filt


def _safe_int_arith(expr: str) -> int | None:
    """Evaluate a tiny integer expression (digits, + − *, parentheses)."""
    cleaned = expr.strip()
    if not cleaned:
        return None
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError:
        return None

    def _eval(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return int(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult)
        ):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            return left * right
        raise ValueError("unsupported")

    try:
        return _eval(tree)
    except (ValueError, TypeError):
        return None


_TIME_AVAILABLE_RE = re.compile(
    r"TimeAvailable\s*\(\s*[`']days[`']\s*\)\s*(>=|<=|>|<)\s*(.+)$",
    re.IGNORECASE,
)


def _parse_time_available_rule(expr: str) -> dict[str, Any] | None:
    match = _TIME_AVAILABLE_RE.fullmatch(expr.strip())
    if not match:
        return None
    operator = match.group(1)
    threshold = _safe_int_arith(match.group(2))
    if threshold is None:
        return None
    return {
        "operator": operator,
        "threshold_days": threshold,
        "raw_expr": expr.strip(),
    }


def _parse_hero_date(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _hero_availability_dates() -> dict[int, datetime]:
    """hero_id → most recent of date_available / last_rework_date."""
    try:
        from ic_gamedata.specialization_data import cached_definitions_data
    except ImportError:
        return {}
    data = cached_definitions_data()
    out: dict[int, datetime] = {}
    for row in data.get("hero_defines") or []:
        if not isinstance(row, dict):
            continue
        hero_id = _parse_int(row.get("id"))
        if hero_id is None:
            continue
        dates = [
            d
            for d in (
                _parse_hero_date(row.get("date_available")),
                _parse_hero_date(row.get("last_rework_date")),
            )
            if d is not None
        ]
        if dates:
            out[hero_id] = max(dates)
    return out


def _payload_now(payload: dict[str, Any]) -> datetime:
    for source in (payload, payload.get("details") if isinstance(payload.get("details"), dict) else {}):
        if not isinstance(source, dict):
            continue
        for key in ("current_time", "time", "defines_updated_at"):
            raw = source.get(key)
            if isinstance(raw, (int, float)) and raw > 1_000_000_000:
                # seconds since epoch
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            parsed = _parse_hero_date(raw)
            if parsed is not None:
                return parsed
    return datetime.now(tz=timezone.utc)


def _resolve_time_available_banned_ids(
    payload: dict[str, Any],
    rule: dict[str, Any],
) -> set[int] | None:
    """Heroes for whom TimeAvailable(days) matches the disallow predicate."""
    operator = str(rule.get("operator") or "")
    threshold = _parse_int(rule.get("threshold_days"))
    if threshold is None or operator not in _STAT_COMPARATORS:
        return None
    dates = _hero_availability_dates()
    if not dates:
        return None
    now = _payload_now(payload)
    banned: set[int] = set()
    for hero_id, when in dates.items():
        days = max(0, int((now - when).total_seconds() // 86400))
        if _stat_value_passes(days, operator, threshold):
            banned.add(hero_id)
    return banned


def _stat_gates_from_expr(expr: str, *, source: str = "by_expr") -> list[dict[str, Any]]:
    """Extract GetStat comparisons for structured export (not always hard mins)."""
    cleaned = expr.strip()
    if not cleaned:
        return []
    scope = "allow_expr_or_clause" if "||" in cleaned else "allow_expr"
    if "||" not in cleaned and "&&" not in cleaned and cleaned.count("GetStat") == 1:
        # Sole gate in the expression — still allow_expr unless also in min_stats.
        scope = "allow_expr_sole_gate"
    gates: list[dict[str, Any]] = []
    for match in _GETSTAT_GATE_RE.finditer(cleaned):
        stat_raw = match.group(1).strip().lower()
        stat_key = _STAT_ALIASES.get(stat_raw, stat_raw)
        value = _parse_int(match.group(3))
        if value is None:
            continue
        gates.append(
            {
                "stat": stat_key,
                "operator": match.group(2),
                "value": value,
                "scope": scope,
                "source": source,
                "raw_expr": cleaned,
                "stats_basis": "character_sheet_ability_scores",
            }
        )
    return gates


def _reconcile_only_allow_getstat_expr(
    cleaned: str,
    *,
    text_hard_gates: list[tuple[str, str, int]],
) -> dict[str, Any]:
    """Classify a sole GetStat by_expr under only_allow_crusaders.

    Proven convention (cached adventure defines): under only_allow_crusaders,
    by_expr is allow-when-true (e.g. GetStat(int)>=16 with text "16 or higher").

    When restrictions_text yields a sole hard gate that is the integer-safe
    negation of that sole GetStat expr, treat the expr as a deny-predicate and
    normalize to the equivalent allow gate (text side). This is reconciliation
    after conflict detection — not blindly preferring text.
    """
    sole = _sole_getstat_comparison(cleaned)
    base = {
        "raw_expr": cleaned,
        "source": "by_expr",
        "change_type": "only_allow_crusaders",
        "source_field": "game_changes.by_expr.expr",
    }
    if sole is None:
        return {
            **base,
            "true_means": "allowed",
            "predicate_kind": "allow",
            "action": "keep_allow_expr",
            "evidence": (
                "Niet-eenvoudige of samengestelde expressie; "
                "standaard only_allow allow-when-true."
            ),
        }

    same_stat_text = [g for g in text_hard_gates if g[0] == sole[0]]
    if not same_stat_text:
        # Without confirming text: >=/> is the common proven allow-when-true form
        # in CNE defines. Sole < / <= under only_allow is ambiguous (909-class:
        # readable min-text vs upper-bound expr) — do NOT claim proven allow.
        if sole[1] in (">=", ">"):
            return {
                **base,
                "true_means": "allowed",
                "predicate_kind": "allow",
                "sole_gate": {
                    "stat": sole[0],
                    "operator": sole[1],
                    "value": sole[2],
                },
                "action": "keep_allow_expr",
                "evidence": (
                    "Geen restrictions_text-gate op dezelfde stat; sole GetStat "
                    "met ondergrens (>=/>) onder only_allow → allow-when-true "
                    "(conventie uit adventure defines)."
                ),
            }
        return {
            **base,
            "true_means": "unknown",
            "predicate_kind": "unknown",
            "sole_gate": {
                "stat": sole[0],
                "operator": sole[1],
                "value": sole[2],
            },
            "action": "mark_unconfirmed_semantics",
            "evidence": (
                "Geen parseerbare restrictions_text-gate op dezelfde stat ter "
                "bevestiging. Sole GetStat met bovengrens-comparator (< / <=) "
                "onder only_allow is ambigu (kan allow-max of misplaatste "
                "deny-predicate zijn). Niet als bewezen allow behandeld."
            ),
        }

    # Prefer a single clear text gate on this stat.
    matching = [g for g in same_stat_text if _gates_are_equivalent(sole, g)]
    negating = [g for g in same_stat_text if _gates_are_negations(sole, g)]
    min_ops = {">=", ">"}
    max_ops = {"<=", "<"}
    same_direction = [
        g
        for g in same_stat_text
        if (sole[1] in min_ops and g[1] in min_ops)
        or (sole[1] in max_ops and g[1] in max_ops)
    ]

    if matching and not negating:
        return {
            **base,
            "true_means": "allowed",
            "predicate_kind": "allow",
            "sole_gate": {"stat": sole[0], "operator": sole[1], "value": sole[2]},
            "action": "keep_allow_expr",
            "evidence": (
                "restrictions_text-gate komt overeen met by_expr "
                "(allow-when-true bevestigd)."
            ),
            "text_gate": {
                "stat": matching[0][0],
                "operator": matching[0][1],
                "value": matching[0][2],
            },
        }

    if negating and not matching:
        text_gate = negating[0]
        inv = _invert_comparator(sole[1])
        # Normalized allow = text gate (already the negation of deny-expr).
        return {
            **base,
            "true_means": "denied",
            "predicate_kind": "deny",
            "sole_gate": {"stat": sole[0], "operator": sole[1], "value": sole[2]},
            "action": "treat_as_deny_normalize_allow",
            "normalized_allow_gate": {
                "stat": text_gate[0],
                "operator": text_gate[1],
                "value": text_gate[2],
            },
            "deny_to_allow_note": (
                f"deny {sole[0]} {sole[1]} {sole[2]} ≡ allow "
                f"{text_gate[0]} {text_gate[1]} {text_gate[2]}"
                + (f" (invert `{sole[1]}`→`{inv}`)" if inv else "")
            ),
            "evidence": (
                "by_expr sole GetStat is de integer-veilige negatie van de "
                "restrictions_text-gate op dezelfde stat. Bij only_allow is "
                "by_expr normaliter allow-when-true en gelijkgericht aan de "
                "tekst; deze inversie → geverifieerde deny-predicate, "
                "genormaliseerd naar equivalente allow-gate."
            ),
            "text_gate": {
                "stat": text_gate[0],
                "operator": text_gate[1],
                "value": text_gate[2],
            },
        }

    if same_direction and not negating:
        # e.g. expr dex < 12 with text dex <= 12 — same upper-bound direction.
        return {
            **base,
            "true_means": "allowed",
            "predicate_kind": "allow",
            "sole_gate": {"stat": sole[0], "operator": sole[1], "value": sole[2]},
            "action": "keep_allow_expr",
            "evidence": (
                "by_expr en restrictions_text zijn gelijkgericht "
                "(beide min- of beide max-bound); allow-when-true behouden. "
                "API-expressie is leidend voor evaluatie."
            ),
            "text_gate": {
                "stat": same_direction[0][0],
                "operator": same_direction[0][1],
                "value": same_direction[0][2],
            },
        }

    # Both matching and negating, or neither with multiple conflicting text gates.
    return {
        **base,
        "true_means": "unknown",
        "predicate_kind": "conflict",
        "sole_gate": {"stat": sole[0], "operator": sole[1], "value": sole[2]},
        "action": "mark_conflict",
        "evidence": (
            "by_expr en restrictions_text op dezelfde stat zijn niet eenduidig "
            "te verzoenen (match en/of conflict). Geen ungegronde toelating."
        ),
        "text_gates": [
            {"stat": g[0], "operator": g[1], "value": g[2]} for g in same_stat_text
        ],
    }


def _filter_from_by_expr(
    expr: str,
    *,
    disallow: bool,
    text_hard_gates: list[tuple[str, str, int]] | None = None,
) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    cleaned = expr.strip()
    lowered = cleaned.casefold()

    # Elminster: TimeAvailable(`days`) > (365 * 3) under disallow_crusaders.
    time_rule = _parse_time_available_rule(cleaned)
    if time_rule is not None and disallow:
        filt.time_available_rule = time_rule
        years = time_rule["threshold_days"] / 365.0
        filt.active_notes.append(
            f"Alleen champions beschikbaar/reworked ≤ "
            f"{time_rule['threshold_days']} dagen "
            f"(≈{years:.0f} jaar; Elminster TimeAvailable)"
        )
        filt.expr_interpretations.append(
            {
                "raw_expr": cleaned,
                "source": "by_expr",
                "change_type": "disallow_crusaders",
                "source_field": "game_changes.by_expr.expr",
                "true_means": "denied",
                "predicate_kind": "deny",
                "action": "resolve_time_available_days",
                "time_available_rule": time_rule,
                "evidence": (
                    "disallow + TimeAvailable(days): true ⇒ champion te oud "
                    "t.o.v. date_available/last_rework_date."
                ),
            }
        )
        return filt

    if any(marker in lowered for marker in _UNHANDLED_EXPR_MARKERS):
        filt.has_unknown_rules = True
    if disallow:
        # disallow_crusaders + by_expr: HasTag names are banned; GetStat alone
        # is recorded as deny-predicate when it is a sole comparison.
        filt.banned_tags.update(_extract_has_tags(cleaned))
        sole = _sole_getstat_comparison(cleaned)
        if sole is not None and not _extract_has_tags(cleaned):
            filt.deny_exprs.append(cleaned)
            filt.expr_interpretations.append(
                {
                    "raw_expr": cleaned,
                    "source": "by_expr",
                    "change_type": "disallow_crusaders",
                    "source_field": "game_changes.by_expr.expr",
                    "true_means": "denied",
                    "predicate_kind": "deny",
                    "action": "keep_deny_expr",
                    "evidence": (
                        "disallow_crusaders + sole GetStat: true betekent geblokkeerd."
                    ),
                }
            )
            filt.active_notes.append(
                f"{_format_stat_gate_label(sole[0], sole[1], sole[2])} "
                "(disallow expr, deny-when-true)"
            )
        elif sole is not None:
            filt.has_unknown_rules = True
            filt.active_notes.append(
                "disallow by_expr combineert tags en GetStat; niet volledig "
                "genormaliseerd."
            )
        elif "timeavailable" not in lowered:
            # Unknown disallow expr without GetStat/TimeAvailable — keep visible.
            filt.has_unknown_rules = True
            filt.active_notes.append(f"Onbekende disallow by_expr: {cleaned[:80]}")
        return filt

    decision = _reconcile_only_allow_getstat_expr(
        cleaned,
        text_hard_gates=list(text_hard_gates or []),
    )
    filt.expr_interpretations.append(decision)
    action = decision.get("action")

    if action == "treat_as_deny_normalize_allow":
        filt.deny_exprs.append(cleaned)
        norm = decision.get("normalized_allow_gate") or {}
        stat = norm.get("stat")
        operator = norm.get("operator")
        value = norm.get("value")
        if (
            isinstance(stat, str)
            and isinstance(operator, str)
            and isinstance(value, int)
            and operator in _STAT_COMPARATORS
        ):
            filt.ability_score_gates.append((stat, operator, value))
            filt.active_notes.append(
                f"{_format_stat_gate_label(stat, operator, value)} "
                "(by_expr als deny genormaliseerd)"
            )
        else:
            filt.has_unknown_rules = True
        return filt

    if action == "mark_conflict":
        filt.has_restriction_semantics_conflict = True
        filt.has_unknown_rules = True
        # Keep both sides visible; do not evaluate the disputed expr as allow.
        filt.active_notes.append(
            "Conflict by_expr vs restrictions_text (stat-semantiek onzeker)"
        )
        return filt

    if action == "mark_unconfirmed_semantics":
        filt.has_restriction_semantics_conflict = True
        filt.has_unknown_rules = True
        filt.active_notes.append(
            "by_expr-statcomparator semantiek onbevestigd "
            "(geen betrouwbare allow/deny zonder tekstbevestiging)"
        )
        return filt

    # Default / keep_allow_expr
    filt.allow_exprs.append(cleaned)
    for hero_id in _extract_hero_id_equals(cleaned):
        filt.exempt_hero_ids.add(hero_id)
    gates = _stat_gates_from_expr(cleaned)
    if gates and "||" not in cleaned:
        g0 = gates[0]
        filt.active_notes.append(
            f"{_format_stat_gate_label(g0['stat'], g0['operator'], g0['value'])} (expr)"
        )
    elif gates:
        g0 = gates[0]
        filt.active_notes.append(
            f"{g0['stat'].upper()} {g0['operator']} {g0['value']} "
            f"of andere uitzondering (OR-expr)"
        )
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


def _patron_define(patron_id: int) -> dict[str, Any] | None:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data
    except ImportError:
        return None
    data = cached_definitions_data()
    for row in data.get("patron_defines") or []:
        if isinstance(row, dict) and _parse_int(row.get("id")) == patron_id:
            return row
    return None


def _patron_challenge_key(payload: dict[str, Any]) -> str:
    """Patron restrictions_text / game_changes are keyed by challenge level (usually '1')."""
    instance = _active_instance(payload) or {}
    for key in ("patron_challenge_id", "difficulty_id", "tier"):
        value = _parse_int(instance.get(key))
        if value is not None and value > 0:
            return str(value)
    return "1"


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
    filt.patron_id = patron_id
    patron_name = PATRON_NAMES.get(patron_id, f"Patron {patron_id}")
    filt.active_notes.append(f"Actieve patron: {patron_name}")

    if not roster:
        filt.has_unknown_rules = True
        filt.active_notes.append("Patron roster missing — update config/patron_roster.json")
    else:
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
            filt.active_notes.append(
                f"Patron {patron_name}: {blocked} champions unavailable"
            )

    # API patron rules (e.g. Mirt: Only Good or Evil — by_tags !(good|evil)).
    patron_def = _patron_define(patron_id)
    if patron_def is None:
        return filt

    challenge = _patron_challenge_key(payload)
    raw_text = patron_def.get("restrictions_text")
    patron_text: str | None = None
    if isinstance(raw_text, dict):
        candidate = raw_text.get(challenge) or raw_text.get("1")
        if isinstance(candidate, str) and candidate.strip():
            patron_text = candidate.strip()
    elif isinstance(raw_text, str) and raw_text.strip():
        patron_text = raw_text.strip()
    if patron_text:
        filt.raw_restriction_texts.append(patron_text)
        text_filt = _parse_restrictions_text(patron_text)
        # Prefer API game_changes when present; text is evidence + fallback.
        text_hard_gates = list(_iter_hard_stat_gates(text_filt))
    else:
        text_filt = AdventureRosterFilter()
        text_hard_gates = []

    changes_raw = patron_def.get("game_changes")
    change_list: list[Any] = []
    if isinstance(changes_raw, dict):
        change_list = list(changes_raw.get(challenge) or changes_raw.get("1") or [])
    elif isinstance(changes_raw, list):
        change_list = changes_raw

    applied_api = False
    for change in change_list:
        if not isinstance(change, dict):
            continue
        filt.merge(
            _filter_from_game_change(change, text_hard_gates=text_hard_gates)
        )
        applied_api = True
        note = _note_from_game_change(change)
        if note and note not in filt.active_notes:
            filt.active_notes.append(note)

    if not applied_api and (text_filt.has_roster_rules() or text_filt.active_notes):
        filt.merge(text_filt)
    return filt


def _filter_from_game_change(
    change: dict[str, Any],
    *,
    text_hard_gates: list[tuple[str, str, int]] | None = None,
) -> AdventureRosterFilter:
    filt = AdventureRosterFilter()
    change_type = str(change.get("type") or "").strip().lower()

    if change_type == "force_allow_hero":
        for hid in change.get("hero_ids") or []:
            hero_id = _parse_int(hid)
            if hero_id is not None:
                filt.exempt_hero_ids.add(hero_id)
        if filt.exempt_hero_ids:
            filt.uses_api_game_changes = True
            filt.active_notes.append(
                f"Force-allow heroes: {', '.join(str(i) for i in sorted(filt.exempt_hero_ids))}"
            )
        return filt

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
            pass_any = bool(by_stat.get("pass_any"))
            filt.merge(
                _filter_from_by_stat(
                    stats_list, disallow=disallow, pass_any=pass_any
                )
            )

    by_expr = change.get("by_expr")
    if isinstance(by_expr, dict):
        expr = by_expr.get("expr")
        if isinstance(expr, str) and expr.strip():
            filt.merge(
                _filter_from_by_expr(
                    expr,
                    disallow=disallow,
                    text_hard_gates=text_hard_gates if allow else None,
                )
            )

    by_i_levels = change.get("by_i_levels")
    if isinstance(by_i_levels, dict):
        comparison = str(by_i_levels.get("comparison") or "").strip().lower()
        if comparison in {"least", "lowest", "min", "most", "highest", "max"}:
            filt.ilvl_seat_comparison = (
                "least" if comparison in {"least", "lowest", "min"} else "most"
            )
            label = (
                "laagste gemiddelde ilevel per F-seat"
                if filt.ilvl_seat_comparison == "least"
                else "hoogste gemiddelde ilevel per F-seat"
            )
            filt.active_notes.append(f"Alleen champions met de {label}")
            filt.expr_interpretations.append(
                {
                    "source": "by_i_levels",
                    "change_type": change_type,
                    "source_field": "game_changes.by_i_levels",
                    "comparison": filt.ilvl_seat_comparison,
                    "action": "resolve_owned_ilvl_per_seat",
                    "evidence": (
                        "only_allow/disallow by_i_levels: per permanente F-seat "
                        "alleen de owned champion(s) met de "
                        f"{filt.ilvl_seat_comparison} average item level."
                    ),
                }
            )
        else:
            filt.has_unknown_rules = True
            filt.active_notes.append(
                f"Onbekende by_i_levels comparison: {comparison!r}"
            )
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
            filt.active_notes.append("Support champions only")
            continue

        if re.search(r"tanking role can not be used|may not use tanking champions", lower):
            filt.banned_tags.add("tanking")
            filt.active_notes.append("No tanking champions")
            continue

        if match := re.search(
            r"only champions with a (\w+) of (\d+) or higher|"
            r"may only use champions with (?:a |an )?(\w+) of (\d+) or higher|"
            r"only champions with a (\w+) score of (\d+) or higher|"
            r"champions with (?:an? )?(\w+)(?: score)? of (\d+) or higher",
            lower,
        ):
            stat_raw = next(g for g in match.groups()[::2] if g)
            value_raw = next(g for g in match.groups()[1::2] if g)
            stat_key = _STAT_ALIASES.get(stat_raw.strip(), stat_raw.strip())
            value = _parse_int(value_raw)
            if value is not None:
                filt.ability_score_gates.append((stat_key, ">=", value))
                filt.active_notes.append(_format_stat_gate_label(stat_key, ">=", value))
            continue

        if match := re.search(
            r"only champions with (?:an? )?(\w+)(?: score)? of (\d+) or (?:less|fewer|lower)|"
            r"may only use champions with (?:an? )?(\w+)(?: score)? of (\d+) or (?:less|fewer|lower)|"
            r"champions with (?:an? )?(\w+)(?: score)? of (\d+) or (?:less|fewer|lower)",
            lower,
        ):
            stat_raw = next(g for g in match.groups()[::2] if g)
            value_raw = next(g for g in match.groups()[1::2] if g)
            stat_key = _STAT_ALIASES.get(stat_raw.strip(), stat_raw.strip())
            value = _parse_int(value_raw)
            if value is not None:
                filt.ability_score_gates.append((stat_key, "<=", value))
                filt.active_notes.append(_format_stat_gate_label(stat_key, "<=", value))
            continue

        if re.search(r"may only use good champions", lower):
            filt.allow_exprs.append("HasTag(`good`)")
            filt.active_notes.append("Good champions only (+ other exceptions)")
            continue

        if re.search(
            r"only good or evil champions|"
            r"only champions that are good or evil|"
            r"good or evil champions can be used",
            lower,
        ):
            filt.allow_exprs.append("HasTag(`good`) || HasTag(`evil`)")
            filt.active_notes.append("Alleen Good of Evil champions")
            continue

        if re.search(
            r"lowest average ilevels|lowest average item levels|"
            r"lowest average ilevel",
            lower,
        ):
            filt.ilvl_seat_comparison = "least"
            filt.active_notes.append(
                "Alleen champions met de laagste gemiddelde ilevel per F-seat"
            )
            continue

        if re.search(r"positional formation abilities", lower):
            filt.has_unknown_rules = True
            filt.active_notes.append("Champions with positional abilities only")
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
                    return f"Missing tag: {_normalize_tag(raw)}"
                return f"Required tag: {raw}"
        by_stat = change.get("by_stat")
        if isinstance(by_stat, dict):
            stats_list = by_stat.get("stats")
            if isinstance(stats_list, list) and stats_list:
                entry = stats_list[0]
                if isinstance(entry, dict):
                    stat = entry.get("stat")
                    value = _parse_int(entry.get("value"))
                    raw_comp = entry.get("comp")
                    if raw_comp is None or (
                        isinstance(raw_comp, str) and not str(raw_comp).strip()
                    ):
                        comp = ">="
                    else:
                        comp = str(raw_comp).strip()
                    if isinstance(stat, str) and value is not None:
                        if comp in _STAT_COMPARATORS:
                            return (
                                f"{_format_stat_gate_label(stat, comp, value)} (API)"
                            )
                        return f"{stat.upper()} {comp} {value} (API, comparator onbekend)"
        by_expr = change.get("by_expr")
        if isinstance(by_expr, dict):
            expr = by_expr.get("expr")
            if isinstance(expr, str) and expr.strip():
                gates = _stat_gates_from_expr(expr)
                if gates and "||" in expr:
                    g0 = gates[0]
                    return (
                        f"{g0['stat'].upper()} {g0['operator']} {g0['value']} "
                        f"of tag-uitzondering (API OR-expr)"
                    )
                if gates:
                    g0 = gates[0]
                    return (
                        f"{_format_stat_gate_label(g0['stat'], g0['operator'], g0['value'])}"
                        f" (API expr)"
                    )
                return "Expression rule from API"
    if change_type in {"disallow_crusaders", "only_allow_crusaders"}:
        by_tags = change.get("by_tags")
        if isinstance(by_tags, dict):
            tags_value = by_tags.get("tags")
            if isinstance(tags_value, str) and tags_value.strip():
                prefix = "Forbidden tag" if change_type == "disallow_crusaders" else "Required tag"
                return f"{prefix}: {tags_value.strip()}"
        by_i_levels = change.get("by_i_levels")
        if isinstance(by_i_levels, dict):
            comparison = str(by_i_levels.get("comparison") or "").strip().lower()
            if comparison in {"least", "lowest", "min"}:
                return "Alleen laagste gemiddelde ilevel per F-seat (API by_i_levels)"
            if comparison in {"most", "highest", "max"}:
                return "Alleen hoogste gemiddelde ilevel per F-seat (API by_i_levels)"
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
        filt.active_notes.append(f"Trials: {len(unavailable)} champions unavailable")

    if adv is not None:
        # Parse restrictions_text first for reconciliation evidence only —
        # do not apply it yet when API game_changes supply roster rules.
        text_filt = AdventureRosterFilter()
        restrictions = adv.get("restrictions_text")
        if isinstance(restrictions, str) and restrictions.strip():
            cleaned_text = restrictions.strip()
            # Placeholder is not evidence for reconciliation.
            if cleaned_text.casefold() not in {
                "[filled in automatically]",
                "filled in automatically",
            }:
                filt.raw_restriction_texts.append(cleaned_text)
                text_filt = _parse_restrictions_text(cleaned_text)
        text_hard_gates = list(_iter_hard_stat_gates(text_filt))

        adventure_had_api = False
        for change in adv.get("game_changes") or []:
            if isinstance(change, dict):
                before = filt.uses_api_game_changes
                filt.merge(
                    _filter_from_game_change(
                        change,
                        text_hard_gates=text_hard_gates,
                    )
                )
                if filt.uses_api_game_changes and not before:
                    adventure_had_api = True
                elif change.get("type"):
                    adventure_had_api = True
                note = _note_from_game_change(change)
                if note and note not in filt.active_notes:
                    filt.active_notes.append(note)

        # Apply text rules that API did not already cover (e.g. ilevel prose
        # when by_i_levels is missing). Prefer API when both exist.
        if not adventure_had_api:
            if text_filt.has_roster_rules() or text_filt.active_notes:
                filt.merge(text_filt)
        else:
            # Still pick up text-only rules like ilevel when API lacked them.
            if text_filt.ilvl_seat_comparison and not filt.ilvl_seat_comparison:
                filt.ilvl_seat_comparison = text_filt.ilvl_seat_comparison
                for note in text_filt.active_notes:
                    if note not in filt.active_notes:
                        filt.active_notes.append(note)

    if filt.ilvl_seat_comparison and filt.ilvl_allowed_hero_ids is None:
        resolved = _resolve_ilvl_allowed_hero_ids(
            payload, comparison=filt.ilvl_seat_comparison
        )
        if resolved is not None:
            filt.ilvl_allowed_hero_ids = resolved
            filt.active_notes.append(
                f"Ilevel-seatregel: {len(resolved)} owned champions toegestaan"
            )
        else:
            filt.has_unknown_rules = True
            filt.active_notes.append(
                "Ilevel-seatregel niet evalueerbaar (geen loot/seat-data)"
            )

    if filt.time_available_rule is not None:
        banned = _resolve_time_available_banned_ids(payload, filt.time_available_rule)
        if banned is not None:
            filt.banned_hero_ids.update(banned)
            filt.active_notes.append(
                f"TimeAvailable: {len(banned)} champions te oud t.o.v. drempel"
            )
            filt.time_available_rule = {
                **filt.time_available_rule,
                "banned_count": len(banned),
                "resolved": True,
            }
        else:
            filt.has_unknown_rules = True
            filt.active_notes.append(
                "TimeAvailable-regel niet evalueerbaar (geen hero-dates)"
            )
            filt.time_available_rule = {
                **filt.time_available_rule,
                "resolved": False,
            }

    if filt.required_tags and not any("tag" in note.casefold() for note in filt.active_notes):
        filt.active_notes.append(
            "Champions with tag only: " + ", ".join(sorted(filt.required_tags))
        )
    if filt.banned_tags and not any("tanking" in note.casefold() or "forbidden" in note.casefold() for note in filt.active_notes):
        filt.active_notes.append(
            "Forbidden tags: " + ", ".join(sorted(filt.banned_tags))
        )
    for stat, operator, value in _iter_hard_stat_gates(filt):
        note = _format_stat_gate_label(stat, operator, value)
        if note not in filt.active_notes and not any(
            str(value) in n and stat.upper() in n.upper() for n in filt.active_notes
        ):
            filt.active_notes.append(note)

    if filt.min_stats or filt.ability_score_gates or filt.allow_exprs:
        if not hero_ability_scores_map_from_cached_definitions() and not hero_tags_map_from_cached_definitions():
            filt.has_unknown_rules = True
            note = "cached_definitions.json missing — download via the game for a full check"
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

    if (
        roster_filter.ilvl_allowed_hero_ids is not None
        and hero_id not in roster_filter.ilvl_allowed_hero_ids
    ):
        return False

    meta = _hero_meta(hero_id)

    if roster_filter.banned_tags & meta.all_tags:
        return False

    if roster_filter.required_tags and not roster_filter.required_tags.issubset(meta.all_tags):
        return False

    if roster_filter.has_restriction_semantics_conflict:
        return False

    for stat, operator, threshold in _iter_hard_stat_gates(roster_filter):
        value = meta.stats.get(stat)
        if value is None or not _stat_value_passes(value, operator, threshold):
            return False

    if roster_filter.deny_exprs:
        deny_results = [_eval_expr(expr, meta) for expr in roster_filter.deny_exprs]
        if any(result is True for result in deny_results):
            return False
        if any(result is None for result in deny_results):
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

    # Unevaluable stat comparator with no other hard rule: fail closed for suggestions.
    if roster_filter.has_unevaluable_stat_rules:
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
    # Keep enough notes for adventure gates + patron tag/ilevel rules.
    return " · ".join(unique[:8])


def structured_stat_gates(roster_filter: AdventureRosterFilter | None) -> list[dict[str, Any]]:
    """Hard ability-score gates + GetStat gates mined from allow/deny exprs."""
    if roster_filter is None:
        return []
    gates: list[dict[str, Any]] = []
    for stat, operator, value in _iter_hard_stat_gates(roster_filter):
        if operator in (">=", ">"):
            scope = "hard_min"
        elif operator in ("<=", "<"):
            scope = "hard_max"
        else:
            scope = "hard_gate"
        # Prefer richer interpretation metadata when this gate came from deny→allow.
        from_deny = any(
            isinstance(row, dict)
            and row.get("action") == "treat_as_deny_normalize_allow"
            and (row.get("normalized_allow_gate") or {}).get("stat") == stat
            and (row.get("normalized_allow_gate") or {}).get("operator") == operator
            and (row.get("normalized_allow_gate") or {}).get("value") == value
            for row in roster_filter.expr_interpretations
        )
        entry = {
            "stat": stat,
            "operator": operator,
            "value": value,
            "scope": scope,
            "source": "by_expr_deny_normalized" if from_deny else "by_stat_or_text",
            "stats_basis": "character_sheet_ability_scores",
            "label": _format_stat_gate_label(stat, operator, value),
            # predicate_kind/true_means apply to THIS gate (operator/value), never
            # to a nested raw deny expression.
            "predicate_kind": "allow",
            "true_means": "allowed",
        }
        if from_deny:
            for row in roster_filter.expr_interpretations:
                if (
                    isinstance(row, dict)
                    and row.get("action") == "treat_as_deny_normalize_allow"
                    and (row.get("normalized_allow_gate") or {}).get("stat") == stat
                    and (row.get("normalized_allow_gate") or {}).get("operator")
                    == operator
                    and (row.get("normalized_allow_gate") or {}).get("value") == value
                ):
                    entry["raw_predicate"] = {
                        "raw_expr": row.get("raw_expr"),
                        "predicate_kind": "deny",
                        "true_means": "denied",
                        "change_type": row.get("change_type"),
                        "source_field": row.get("source_field"),
                    }
                    entry["conversion"] = row.get("deny_to_allow_note")
                    entry["evidence"] = row.get("evidence")
                    break
        gates.append(entry)
    for expr in roster_filter.allow_exprs:
        for gate in _stat_gates_from_expr(expr):
            gate = dict(gate)
            gate["predicate_kind"] = "allow"
            gate["true_means"] = "allowed"
            gates.append(gate)
    for expr in roster_filter.deny_exprs:
        # Skip raw deny gates already represented via normalized hard allow.
        already = any(
            isinstance(row, dict)
            and row.get("action") == "treat_as_deny_normalize_allow"
            and row.get("raw_expr") == expr
            for row in roster_filter.expr_interpretations
        )
        if already:
            continue
        for gate in _stat_gates_from_expr(expr, source="by_expr_deny"):
            gate = dict(gate)
            gate["predicate_kind"] = "deny"
            gate["true_means"] = "denied"
            gate["scope"] = "deny_expr_sole_gate" if gate.get("scope", "").startswith(
                "allow_expr_sole"
            ) else "deny_expr"
            gates.append(gate)
    # Surface unconfirmed sole GetStat predicates that were intentionally not
    # added to allow_exprs/deny_exprs (no proven allow/deny without text).
    for row in roster_filter.expr_interpretations:
        if not isinstance(row, dict):
            continue
        if row.get("action") != "mark_unconfirmed_semantics":
            continue
        sole = row.get("sole_gate") or {}
        gates.append(
            {
                "stat": sole.get("stat"),
                "operator": sole.get("operator"),
                "value": sole.get("value"),
                "scope": "unconfirmed_by_expr_sole_gate",
                "source": "by_expr",
                "raw_expr": row.get("raw_expr"),
                "stats_basis": "character_sheet_ability_scores",
                "predicate_kind": "unknown",
                "true_means": "unknown",
                "change_type": row.get("change_type"),
                "evidence": row.get("evidence"),
            }
        )
    return gates


def evaluate_heroes_against_filter(
    hero_ids: list[int] | tuple[int, ...],
    roster_filter: AdventureRosterFilter | None,
) -> list[dict[str, Any]]:
    """Per-hero restriction outcome without formation-trust bypass.

    Returns status: allowed | denied | unknown.
    """
    results: list[dict[str, Any]] = []
    if roster_filter is None:
        for hid in hero_ids:
            results.append(
                {
                    "champion_id": hid,
                    "status": "unknown",
                    "reason": "Geen restrictiefilter beschikbaar.",
                    "ability_scores": _hero_meta(hid).stats or None,
                }
            )
        return results

    for hid in hero_ids:
        meta = _hero_meta(hid)
        # Do not pass formation_hero_ids — seated ≠ proven eligible.
        if hid in roster_filter.banned_hero_ids or hid in roster_filter.patron_blocked_hero_ids:
            results.append(
                {
                    "champion_id": hid,
                    "status": "denied",
                    "reason": "Champion geblokkeerd door adventure/patron/trials.",
                    "ability_scores": meta.stats or None,
                }
            )
            continue
        if hid in roster_filter.exempt_hero_ids:
            results.append(
                {
                    "champion_id": hid,
                    "status": "allowed",
                    "reason": "Uitzondering (hero_id) in restrictieregel.",
                    "ability_scores": meta.stats or None,
                }
            )
            continue

        if (
            roster_filter.ilvl_allowed_hero_ids is not None
            and hid not in roster_filter.ilvl_allowed_hero_ids
        ):
            results.append(
                {
                    "champion_id": hid,
                    "status": "denied",
                    "reason": (
                        "Niet de laagste/hoogste gemiddelde ilevel in deze F-seat "
                        f"(by_i_levels={roster_filter.ilvl_seat_comparison or 'least'})."
                    ),
                    "ability_scores": meta.stats or None,
                }
            )
            continue

        if (
            roster_filter.ilvl_seat_comparison
            and roster_filter.ilvl_allowed_hero_ids is None
        ):
            results.append(
                {
                    "champion_id": hid,
                    "status": "unknown",
                    "reason": "Ilevel-seatregel niet evalueerbaar (geen loot/seat-data).",
                    "ability_scores": meta.stats or None,
                }
            )
            continue

        if roster_filter.has_restriction_semantics_conflict:
            results.append(
                {
                    "champion_id": hid,
                    "status": "unknown",
                    "reason": (
                        "Restrictiesemantiek conflict (by_expr vs restrictions_text); "
                        "niet als allowed behandeld."
                    ),
                    "ability_scores": meta.stats or None,
                }
            )
            continue

        hard_fail_reasons: list[str] = []
        for stat, operator, threshold in _iter_hard_stat_gates(roster_filter):
            value = meta.stats.get(stat)
            if value is None or not _stat_value_passes(value, operator, threshold):
                hard_fail_reasons.append(
                    _stat_gate_fail_reason(stat, value, operator, threshold)
                )

        if roster_filter.banned_tags & meta.all_tags:
            hard_fail_reasons.append(
                "Verboden tag: "
                + ", ".join(sorted(roster_filter.banned_tags & meta.all_tags))
            )
        if roster_filter.required_tags and not roster_filter.required_tags.issubset(
            meta.all_tags
        ):
            missing = roster_filter.required_tags - meta.all_tags
            hard_fail_reasons.append(
                "Vereiste tags ontbreken: " + ", ".join(sorted(missing))
            )

        if roster_filter.deny_exprs:
            deny_results = [
                _eval_expr(expr, meta) for expr in roster_filter.deny_exprs
            ]
            if any(result is True for result in deny_results):
                hard_fail_reasons.append("Voldoet aan deny_expr (geblokkeerd).")
            elif any(result is None for result in deny_results):
                results.append(
                    {
                        "champion_id": hid,
                        "status": "unknown",
                        "reason": "deny_expr niet volledig evalueerbaar.",
                        "ability_scores": meta.stats or None,
                    }
                )
                continue

        expr_status: str | None = None
        expr_detail = None
        if roster_filter.allow_exprs:
            expr_results = [_eval_expr(expr, meta) for expr in roster_filter.allow_exprs]
            if any(result is True for result in expr_results):
                expr_status = "allowed"
                expr_detail = "Voldoet aan allow_expr (tag/stat/OR)."
            elif any(result is None for result in expr_results):
                expr_status = "unknown"
                expr_detail = "allow_expr niet volledig evalueerbaar."
            else:
                expr_status = "denied"
                expr_detail = "Voldoet niet aan allow_expr."

        # Hard gates (stat/tag) always AND with allow_exprs. An allow_expr is an
        # extra eligibility path (e.g. Good|Evil), not a bypass of INT/DEX caps.
        if hard_fail_reasons:
            results.append(
                {
                    "champion_id": hid,
                    "status": "denied" if all(
                        "onbekend" not in r for r in hard_fail_reasons
                    ) else "unknown",
                    "reason": "; ".join(hard_fail_reasons),
                    "ability_scores": meta.stats or None,
                }
            )
            continue

        if roster_filter.allow_exprs:
            if expr_status == "allowed":
                results.append(
                    {
                        "champion_id": hid,
                        "status": "allowed",
                        "reason": expr_detail,
                        "ability_scores": meta.stats or None,
                    }
                )
            elif expr_status == "unknown":
                results.append(
                    {
                        "champion_id": hid,
                        "status": "unknown",
                        "reason": expr_detail,
                        "ability_scores": meta.stats or None,
                    }
                )
            else:
                results.append(
                    {
                        "champion_id": hid,
                        "status": "denied",
                        "reason": expr_detail or "Niet toegestaan.",
                        "ability_scores": meta.stats or None,
                    }
                )
            continue

        if hard_fail_reasons:
            results.append(
                {
                    "champion_id": hid,
                    "status": "unknown"
                    if any("onbekend" in r for r in hard_fail_reasons)
                    else "denied",
                    "reason": "; ".join(hard_fail_reasons),
                    "ability_scores": meta.stats or None,
                }
            )
        elif roster_filter.has_unevaluable_stat_rules:
            results.append(
                {
                    "champion_id": hid,
                    "status": "unknown",
                    "reason": (
                        "Stat-restrictie niet evalueerbaar (onbekende comparator); "
                        "niet stilzwijgend als toegestaan behandeld."
                    ),
                    "ability_scores": meta.stats or None,
                }
            )
        else:
            results.append(
                {
                    "champion_id": hid,
                    "status": "allowed",
                    "reason": "Geen blokkerende restrictie voor deze champion.",
                    "ability_scores": meta.stats or None,
                }
            )
    return results
