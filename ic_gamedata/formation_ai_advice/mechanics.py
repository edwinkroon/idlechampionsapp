"""Resolve effect placeholders and classify what an effect is safe to use for.

Values come only from the upgrade/feat row and its effect_keys. A missing
number stays unknown; a reference id is never treated as a buff percent.
"""

from __future__ import annotations

import json
import re
from typing import Any

_PLACEHOLDER = re.compile(r"\$\(([^)]+)\)|\$([A-Za-z_][A-Za-z0-9_]*)")
_CHANGE_UPGRADE_TARGETS = re.compile(r"change_upgrade_targets\s*,\s*(\d+)", re.IGNORECASE)
_UPGRADE_AMOUNT = re.compile(r"upgrade_amount\(\s*(\d+)", re.IGNORECASE)
# Singular buff_upgrade: amount, upgrade_id[, selector/index — NOT an upgrade id]
_BUFF_UPGRADE_SINGULAR = re.compile(
    r"^buff_upgrade\s*,\s*([\d.]+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\s*$",
    re.IGNORECASE,
)
# Plural buff_upgrades: amount, id1[, id2…]
_BUFF_UPGRADES_PLURAL = re.compile(
    r"^buff_upgrades\s*,\s*([\d.]+)\s*,\s*((?:\d+\s*,\s*)*\d+)\s*$",
    re.IGNORECASE,
)
_ROLE_TOKENS = frozenset({"dps", "tank", "support", "healer", "gold", "control", "hunter"})
_TARGET_WORDS = {
    "adj": "adjacent Champions",
    "non_adj": "non-adjacent Champions",
    "col": "Champions in the same column",
    "behind": "Champions behind",
    "ahead": "Champions ahead",
    "all": "all Champions in the formation",
    "self": "this Champion",
    "next_col": "Champions in the column ahead",
    "next_two_col": "Champions in the two columns ahead",
    "prev_col": "Champions in the column behind",
    "top_row_of_each_column": "Champions at the top of each column",
    "bottom_row_of_each_column": "Champions at the bottom of each column",
}
_AMOUNT_NAMES = frozenset(
    {
        "amount",
        "not_buffed amount",
        "amount___2",
        "amount___3",
        "amount___4",
        "amount___5",
        "not_buffed amount___2",
        "not_buffed amount___3",
    }
)
# Second CSV field is an id / count of something else — not a damage percent.
_NON_MAGNITUDE_OPS = frozenset(
    {
        "change_base_attack",
        "set_ultimate_attack",
        "add_monster_hit_effects",
        "change_upgrade_targets",
        "change_upgrade_data",
        "set_ultimate_attack_id",
        "add_attack",
        "change_attack",
        "do_nothing",
        "favored_foe",
        "add_hero_tags",
        "change_hero_alignment_tag",
        "remove_hero_tags",
        "force_allow_hero_by_tag",
    }
)
# Only these patterns may produce a numeric magnitude. No "first number" fallback.
_MAGNITUDE_TOKEN_HINTS = (
    "_mult",
    "dps",
    "damage",
    "gold",
    "heal",
    "health",
    "chance",
    "crit",
    "_add",
    "cooldown",
    "percent",
)
_ALIGNMENT_TAGS = frozenset({"lawful", "chaotic", "good", "evil", "neutral"})


def _tri(value: bool | None) -> bool | str:
    if value is None:
        return "unknown"
    return value


def _keys(effect_row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(effect_row, dict):
        return []
    raw = effect_row.get("effect_keys")
    if not isinstance(raw, list):
        return []
    return [key for key in raw if isinstance(key, dict)]


def _op_name(effect_string: str) -> str:
    return effect_string.split(",", 1)[0].strip().casefold()


def _second_number(effect_string: str) -> float | None:
    parts = [part.strip() for part in effect_string.split(",")]
    if len(parts) < 2:
        return None
    try:
        return float(parts[1])
    except ValueError:
        return None


def parse_effect_string(effect_string: str) -> dict[str, Any]:
    """Effect-specific argument schema. Unknown trailing args stay unknown."""
    parts = [p.strip() for p in effect_string.split(",")]
    op = parts[0].casefold() if parts else ""
    parsed: dict[str, Any] = {
        "op": op,
        "raw": effect_string,
        "upgrade_ids": [],
        "parameters": [],
        "unknown_args": [],
    }

    def _num(raw: str) -> float | None:
        try:
            return float(raw)
        except ValueError:
            return None

    if op == "buff_upgrade":
        match = _BUFF_UPGRADE_SINGULAR.match(effect_string.strip())
        if match:
            amount = float(match.group(1))
            upgrade_id = int(match.group(2))
            parsed["upgrade_ids"] = [upgrade_id]
            parsed["parameters"].append(
                {
                    "name": "modifier",
                    "value": amount,
                    "meaning": "percent" if amount != 0 else "passthrough",
                    "unit": "percent" if amount != 0 else None,
                    "value_basis": "definition_base",
                }
            )
            parsed["parameters"].append(
                {
                    "name": "upgrade_id",
                    "value": upgrade_id,
                    "meaning": "upgrade_id",
                    "unit": None,
                    "value_basis": "definition_base",
                }
            )
            if match.group(3) is not None:
                parsed["parameters"].append(
                    {
                        "name": "selector",
                        "value": int(match.group(3)),
                        "meaning": "effect_index_or_flag",
                        "unit": None,
                        "value_basis": "definition_base",
                        "certainty": "unknown_semantics",
                    }
                )
                parsed["unknown_args"].append(
                    {
                        "position": 3,
                        "value": int(match.group(3)),
                        "note": "Trailing buff_upgrade arg is not treated as upgrade_id",
                    }
                )
        else:
            parsed["unknown_args"].append({"raw": effect_string})
        return parsed

    if op == "buff_upgrades":
        match = _BUFF_UPGRADES_PLURAL.match(effect_string.strip())
        if match:
            amount = float(match.group(1))
            ids = [int(p.strip()) for p in match.group(2).split(",") if p.strip().isdigit()]
            parsed["upgrade_ids"] = [i for i in ids if i > 0]
            parsed["parameters"].append(
                {
                    "name": "modifier",
                    "value": amount,
                    "meaning": "percent" if amount != 0 else "passthrough",
                    "unit": "percent" if amount != 0 else None,
                    "value_basis": "definition_base",
                }
            )
            for upgrade_id in parsed["upgrade_ids"]:
                parsed["parameters"].append(
                    {
                        "name": "upgrade_id",
                        "value": upgrade_id,
                        "meaning": "upgrade_id",
                        "unit": None,
                        "value_basis": "definition_base",
                    }
                )
        else:
            parsed["unknown_args"].append({"raw": effect_string})
        return parsed

    if op == "add_monster_hit_effects":
        # Schema: amount_or_chance[, hit_effect_id…]
        if len(parts) >= 2:
            amount = _num(parts[1])
            if amount is not None:
                parsed["parameters"].append(
                    {
                        "name": "amount_or_chance",
                        "value": amount,
                        "meaning": "percent_or_chance",
                        "unit": "percent",
                        "value_basis": "definition_base",
                    }
                )
            for raw in parts[2:]:
                if raw.isdigit():
                    parsed["parameters"].append(
                        {
                            "name": "hit_effect_id",
                            "value": int(raw),
                            "meaning": "effect_id",
                            "unit": None,
                            "value_basis": "definition_base",
                        }
                    )
                else:
                    parsed["unknown_args"].append({"value": raw})
        return parsed

    if op in {"change_base_attack", "set_ultimate_attack"} and len(parts) >= 2 and parts[1].isdigit():
        parsed["parameters"].append(
            {
                "name": "attack_id" if op == "change_base_attack" else "ultimate_attack_id",
                "value": int(parts[1]),
                "meaning": "attack_id",
                "unit": None,
                "value_basis": "definition_base",
            }
        )
        for raw in parts[2:]:
            parsed["unknown_args"].append({"value": raw})
        return parsed

    if op == "change_upgrade_targets" and len(parts) >= 2 and parts[1].isdigit():
        parsed["upgrade_ids"] = [int(parts[1])]
        parsed["parameters"].append(
            {
                "name": "upgrade_id",
                "value": int(parts[1]),
                "meaning": "upgrade_id",
                "unit": None,
                "value_basis": "definition_base",
            }
        )
        return parsed

    if op == "change_upgrade_data" and len(parts) >= 2 and parts[1].isdigit():
        # Schema: change_upgrade_data,UPGRADE_ID[,effect_index_or_flag…]
        # First number is the upgrade being rewritten — never a magnitude.
        upgrade_id = int(parts[1])
        parsed["upgrade_ids"] = [upgrade_id]
        parsed["parameters"].append(
            {
                "name": "upgrade_id",
                "value": upgrade_id,
                "meaning": "upgrade_id",
                "unit": None,
                "value_basis": "definition_base",
            }
        )
        for idx, raw in enumerate(parts[2:], start=2):
            if raw.isdigit():
                parsed["parameters"].append(
                    {
                        "name": "selector",
                        "value": int(raw),
                        "meaning": "effect_index_or_flag",
                        "unit": None,
                        "value_basis": "definition_base",
                        "certainty": "unknown_semantics",
                    }
                )
                parsed["unknown_args"].append(
                    {
                        "position": idx,
                        "value": int(raw),
                        "note": "Trailing change_upgrade_data arg is not a magnitude",
                    }
                )
            else:
                parsed["unknown_args"].append({"position": idx, "value": raw})
        return parsed

    # Unsupported / unknown ops: keep raw args without inventing magnitude.
    if len(parts) >= 2:
        for idx, raw in enumerate(parts[1:], start=1):
            parsed["unknown_args"].append({"position": idx, "value": raw})
    return parsed


def referenced_upgrade_ids(effect_field: str | None, effect_row: dict[str, Any] | None) -> list[int]:
    """Upgrade ids from effect-specific schemas only (no selector false-positives)."""
    blobs: list[str] = []
    if isinstance(effect_field, str) and not effect_field.startswith("effect_def,"):
        blobs.append(effect_field)
    for key in _keys(effect_row):
        es = key.get("effect_string")
        if isinstance(es, str):
            blobs.append(es)
    found: list[int] = []
    seen: set[int] = set()

    def _add(value: int) -> None:
        if value > 0 and value not in seen:
            seen.add(value)
            found.append(value)

    for blob in blobs:
        parsed = parse_effect_string(blob)
        for upgrade_id in parsed.get("upgrade_ids") or []:
            _add(int(upgrade_id))
        # Also catch ops that parse_effect_string leaves generic.
        for match in _CHANGE_UPGRADE_TARGETS.finditer(blob):
            _add(int(match.group(1)))
        for match in _UPGRADE_AMOUNT.finditer(blob):
            _add(int(match.group(1)))
        # buff_upgrade_effect_stacks_max_mult,PCT,UPGRADE_ID — treat like singular.
        if blob.casefold().startswith("buff_upgrade_effect_stacks_max_mult,"):
            parts = [p.strip() for p in blob.split(",")]
            if len(parts) >= 3 and parts[2].isdigit():
                _add(int(parts[2]))
        if blob.casefold().startswith("change_upgrade_data,"):
            parts = [p.strip() for p in blob.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                _add(int(parts[1]))
    return found


def _is_magnitude_op(op: str) -> bool:
    """True only for verified magnitude-bearing effect ops (no numeric fallback)."""
    if not op or op in _NON_MAGNITUDE_OPS:
        return False
    if op.startswith("buff_upgrade"):
        return True
    if op == "pre_stack":
        return False  # stack base, not a damage magnitude slot for $amount
    if op.startswith(("global_", "hero_")):
        return True
    if any(token in op for token in _MAGNITUDE_TOKEN_HINTS):
        return True
    return False


def _is_magnitude_string(effect_string: str) -> bool:
    return _is_magnitude_op(_op_name(effect_string))


def _amount_status(keys: list[dict[str, Any]]) -> tuple[float | None, str]:
    """Return (number, known|computed_unknown|absent|unknown|not_applicable|partial).

    - known: single verified magnitude
    - unknown: a numeric value is expected but not established
    - computed_unknown: defines mark the amount as computed / expression-based
    - partial: some magnitude slots known, others missing/computed
    - not_applicable: effect truly has no numeric magnitude (tags, attack swap, …)
    - absent: no magnitude-bearing keys and no signal either way
    """
    if any(
        key.get("use_computed_amount_for_description") or key.get("amount_expr")
        for key in keys
    ):
        slots_preview = _magnitude_slots(keys)
        known_slots = [s for s in slots_preview if s["status"] == "known"]
        if known_slots and any(s["status"] == "computed_unknown" for s in slots_preview):
            return None, "partial"
        return None, "computed_unknown"
    slots = _magnitude_slots(keys)
    if any(slot["status"] == "computed_unknown" for slot in slots):
        known_slots = [s for s in slots if s["status"] == "known"]
        if known_slots:
            return None, "partial"
        return None, "computed_unknown"
    numbers = [float(slot["value"]) for slot in slots if slot["value"] is not None]
    unique = {n for n in numbers}
    if len(unique) == 1 and len(slots) == len(numbers):
        return next(iter(unique)), "known"
    if len(unique) > 1:
        return None, "unknown"  # multiple distinct magnitudes — use per-slot params
    if numbers and len(numbers) < len(slots):
        return None, "partial"
    if numbers:
        return None, "unknown"
    # Custom ops that carry a numeric field but are not verified magnitude ops
    # still imply an unknown value (e.g. uggie_handler,100 with computed flag already
    # handled above). Plain structural ops → not_applicable.
    saw_structural = False
    saw_unknown_numeric = False
    for key in keys:
        es = key.get("effect_string")
        if not isinstance(es, str) or es.startswith("pre_stack,"):
            continue
        op = _op_name(es)
        if op in _NON_MAGNITUDE_OPS or op in {
            "add_hero_tags",
            "remove_hero_tags",
            "change_hero_alignment_tag",
        }:
            saw_structural = True
            continue
        if _is_magnitude_string(es):
            continue
        if _second_number(es) is not None:
            saw_unknown_numeric = True
        else:
            # Unsupported op without a parseable magnitude — still may have $amount
            # in prose; treat as unknown rather than not_applicable.
            if op and op not in {"do_nothing"}:
                saw_unknown_numeric = True
            else:
                saw_structural = True
    prestack = []
    for key in keys:
        es = key.get("effect_string")
        if isinstance(es, str) and es.startswith("pre_stack,"):
            number = _second_number(es)
            if number is not None:
                prestack.append(number)
    if len(set(prestack)) == 1 and not saw_unknown_numeric:
        return prestack[0], "known"
    if saw_unknown_numeric:
        return None, "unknown"
    if saw_structural and not numbers:
        return None, "not_applicable"
    return None, "absent"


def typed_parameters(keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Semantic parameters — reference ids are never labeled as percents."""
    out: list[dict[str, Any]] = []
    for key in keys:
        es = key.get("effect_string")
        if not isinstance(es, str) or not es.strip():
            continue
        parts = [p.strip() for p in es.split(",")]
        op = parts[0].casefold()
        basis = (
            "computed"
            if key.get("use_computed_amount_for_description") or key.get("amount_expr")
            else "definition_base"
        )
        parsed = parse_effect_string(es)
        if parsed.get("parameters"):
            for param in parsed["parameters"]:
                row = dict(param)
                row["source"] = es
                if "value_basis" not in row:
                    row["value_basis"] = basis
                elif basis == "computed":
                    row["value_basis"] = "computed"
                out.append(row)
            continue
        if op == "add_hero_tags" and len(parts) >= 3:
            out.append(
                {
                    "name": "tag",
                    "value": parts[2],
                    "meaning": "hero_tag",
                    "unit": None,
                    "source": es,
                    "value_basis": "definition_base",
                }
            )
            continue
        if op == "change_hero_alignment_tag" and len(parts) >= 3:
            out.append(
                {
                    "name": "alignment",
                    "value": f"{parts[1]} {parts[2]}",
                    "meaning": "alignment_axes",
                    "unit": None,
                    "source": es,
                    "value_basis": "definition_base",
                }
            )
            continue
        if not _is_magnitude_op(op):
            # Unknown ops stay as unknown_args via parse_effect_string — never amount.
            continue
        if len(parts) >= 2:
            try:
                value = float(parts[1])
            except ValueError:
                continue
            # Passthrough 0 on buffs is not a real bonus magnitude for advice.
            if value == 0 and op.startswith("buff_upgrade"):
                continue
            computed = basis == "computed" or bool(
                key.get("use_computed_amount_for_description") or key.get("amount_expr")
            )
            key_targets = _target_tokens([key])
            meaning, unit = _param_unit_meaning(op)
            role = _param_role(op, targets=key_targets)
            if computed:
                out.append(
                    {
                        "name": role,
                        "value": None,
                        "meaning": meaning,
                        "unit": unit,
                        "source": es,
                        "value_basis": "computed",
                        "status": "computed_unknown",
                        "effect_key": op,
                        # Raw 0 passthrough stays in debug only via this flag.
                        "raw_passthrough": value if value == 0 else None,
                    }
                )
                continue
            out.append(
                {
                    "name": role,
                    "value": value,
                    "meaning": meaning,
                    "unit": unit,
                    "source": es,
                    "value_basis": basis,
                    "status": "known",
                    "effect_key": op,
                }
            )
    # Stable unique by (name, value, meaning).
    dedup: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in out:
        key = (row.get("name"), row.get("value"), row.get("meaning"))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(row)
    return dedup


def _fmt_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def _target_tokens(keys: list[dict[str, Any]]) -> list[str]:
    tokens: list[str] = []
    for key in keys:
        raw = key.get("targets")
        if isinstance(raw, str) and raw.strip():
            tokens.append(raw.strip())
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    tokens.append(item.strip())
        new_targets = key.get("new_targets")
        if isinstance(new_targets, str) and new_targets.strip():
            tokens.append(new_targets.strip())
        elif isinstance(new_targets, dict):
            typ = str(new_targets.get("type") or "").strip()
            if typ:
                tokens.append(typ)
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _hero_expr_from_key(key: dict[str, Any]) -> str | None:
    """Recipient-filter expressions only — not per_hero_expr scaling."""
    filt = key.get("filter_targets")
    if isinstance(filt, list):
        for item in filt:
            if isinstance(item, dict):
                expr = item.get("hero_expr")
                if isinstance(expr, str) and expr.strip():
                    return expr.strip()
    return None


_UPGRADE_GATED_CLAUSE = re.compile(
    r"\(\("
    r"((?:GetUpgradeUnlocked\(\d+\)(?:\s*\|\|\s*)?)+)"
    r"\)\s*&&\s*"
    r"(HasTag\(`[^`]+`\)|has_base_attack_dmg_type_magic)"
    r"\)",
    re.IGNORECASE,
)


def parse_conditional_targeting(
    keys: list[dict[str, Any]],
    *,
    selected_upgrade_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Split base vs upgrade-gated targeting from hero_expr (Baldric-style).

    Does not invent tags. Conditional clauses with GetUpgradeUnlocked stay
    scoped to their prerequisite upgrades.
    """
    base_clauses: list[str] = []
    base_tags: list[str] = []
    base_stat_gates: list[dict[str, Any]] = []
    extensions: list[dict[str, Any]] = []
    selected = selected_upgrade_ids  # None = unknown selection state
    selected_set = selected_upgrade_ids or set()

    for key in keys:
        expr = _hero_expr_from_key(key)
        if not expr:
            continue
        # First pull nested ((GetUpgradeUnlocked…) && condition) extensions.
        gated_spans: list[tuple[int, int]] = []
        for match in _UPGRADE_GATED_CLAUSE.finditer(expr):
            gated_spans.append(match.span())
            clause = match.group(0)
            unlocks = [
                int(m.group(1))
                for m in re.finditer(r"GetUpgradeUnlocked\((\d+)\)", match.group(1))
            ]
            cond = match.group(2).strip()
            tags = [m.group(1) for m in re.finditer(r"HasTag\(`([^`]+)`\)", cond)]
            magic = "has_base_attack_dmg_type_magic" in cond.casefold()
            if selected is None:
                active: bool | str = "unknown"
            else:
                active = any(uid in selected_set for uid in unlocks)
            extensions.append(
                {
                    "requires_any_upgrade_id": unlocks,
                    "active_in_current_state": active,
                    "tags": tags or None,
                    "requires_magic_attack": True if magic else None,
                    "clause": clause,
                }
            )
        # Remainder after removing gated clauses = base targeting.
        remainder = expr
        for start, end in sorted(gated_spans, reverse=True):
            remainder = remainder[:start] + remainder[end:]
        remainder = re.sub(r"(\|\|\s*){2,}", "||", remainder).strip(" |")
        for part in [p.strip() for p in re.split(r"\|\|", remainder) if p.strip()]:
            if "GetUpgradeUnlocked" in part:
                continue
            base_clauses.append(part)
            base_tags.extend(
                m.group(1) for m in re.finditer(r"HasTag\(`([^`]+)`\)", part)
            )
            stat_m = re.search(
                r"GetStat\(`([^`]+)`\)\s*>=\s*(\d+)",
                part,
                flags=re.IGNORECASE,
            )
            if stat_m:
                base_stat_gates.append(
                    {"stat": stat_m.group(1), "min": int(stat_m.group(2))}
                )
    seen: set[str] = set()
    unique_base: list[str] = []
    for tag in base_tags:
        if tag not in seen:
            seen.add(tag)
            unique_base.append(tag)
    active_tags: list[str] = list(unique_base)
    for ext in extensions:
        if ext.get("active_in_current_state") is True:
            for tag in ext.get("tags") or []:
                if tag not in active_tags:
                    active_tags.append(tag)
    return {
        "base_clauses": base_clauses or None,
        "base_tags": unique_base or None,
        "base_stat_gates": base_stat_gates or None,
        "extensions": extensions or None,
        "active_tags": active_tags or None,
        "predicate_status": (
            "resolved"
            if (base_clauses or extensions) and selected is not None
            else "partial"
            if (base_clauses or extensions)
            else "absent"
        ),
    }


def _target_tags(
    keys: list[dict[str, Any]],
    *,
    selected_upgrade_ids: set[int] | None = None,
) -> list[str]:
    """Active targeting tags only — not the union of all alternate branches."""
    conditional = parse_conditional_targeting(
        keys, selected_upgrade_ids=selected_upgrade_ids
    )
    if conditional.get("base_clauses") or conditional.get("extensions"):
        return list(conditional.get("active_tags") or [])

    tags: list[str] = []
    for key in keys:
        filt = key.get("filter_targets")
        if isinstance(filt, list):
            for item in filt:
                if isinstance(item, dict):
                    raw = item.get("tags") or item.get("tag")
                    if isinstance(raw, str) and raw.strip():
                        tags.append(raw.strip())
                    elif isinstance(raw, list):
                        tags.extend(str(x).strip() for x in raw if str(x).strip())
        tag = key.get("tag")
        if isinstance(tag, str) and tag.strip():
            tags.append(tag.strip())
        new_targets = key.get("new_targets")
        if isinstance(new_targets, dict):
            raw = new_targets.get("tags") or new_targets.get("tag")
            if isinstance(raw, str) and raw.strip():
                tags.append(raw.strip())
            elif isinstance(raw, list):
                tags.extend(str(x).strip() for x in raw if str(x).strip())
        # per_hero_expr is scaling_population, not recipient filter — skip here.
        es = key.get("effect_string")
        if isinstance(es, str):
            parts = [p.strip() for p in es.split(",")]
            op = parts[0].casefold() if parts else ""
            # per_tagged in the op name is scaling, not recipients.
            if op == "force_allow_hero_by_tag" and len(parts) >= 2:
                tags.append(parts[-1])
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _scaling_population(keys: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Who counts toward magnitude/stacks — not who receives the buff."""
    tags: list[str] = []
    exprs: list[str] = []
    for key in keys:
        expr = key.get("per_hero_expr")
        if isinstance(expr, str) and expr.strip():
            exprs.append(expr.strip())
            for match in re.finditer(r"HasTag\(`([^`]+)`\)", expr):
                tags.append(match.group(1))
        es = key.get("effect_string")
        if isinstance(es, str):
            parts = [p.strip() for p in es.split(",")]
            op = parts[0].casefold() if parts else ""
            if "per_tagged" in op and len(parts) >= 3:
                tags.append(parts[2])
    if not tags and not exprs:
        return None
    unique: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique.append(tag)
    return {
        "tags": unique or None,
        "expressions": exprs or None,
        "combine": "count_matching",
    }


_POSITIONAL_TARGET_TOKENS = frozenset(
    {
        "adj",
        "non_adj",
        "col",
        "ahead",
        "behind",
        "next_col",
        "prev_col",
        "col_and_ahead",
        "col_and_behind",
        "col_and_next_col",
        "prev_two_col",
        "self_and_prev_two_col",
        "self_and_next_col",
    }
)


def _effect_scope(keys: list[dict[str, Any]]) -> str:
    """owner | global | positional | filtered | mixed | unknown.

    Targeting tokens win over effect-key family. ``hero_dps_*`` alone does
    **not** imply owner-scope when recipients are positional.
    """
    ops = [
        _op_name(str(k.get("effect_string") or ""))
        for k in keys
        if isinstance(k.get("effect_string"), str)
    ]
    tokens = _target_tokens(keys)
    has_pos = any(t in _POSITIONAL_TARGET_TOKENS for t in tokens)
    # Explicit self-only (no other geometry) stays owner.
    self_only = tokens == ["self"] or tokens == ["s"]
    has_global = any("global_dps" in op or op.startswith("global_") for op in ops)
    has_owner_op = any("hero_dps" in op for op in ops)
    has_filter = bool(_target_tags(keys)) or any(
        isinstance(k.get("filter_targets"), list) and k.get("filter_targets")
        for k in keys
    )
    if has_pos:
        return "positional"
    if self_only:
        return "owner"
    if has_global and has_filter:
        return "mixed"
    # ``all`` + recipient filter is filtered, not a blanket global.
    if has_filter and tokens in (["all"], ["formation"], []):
        return "filtered"
    if has_global or tokens in (["all"], ["formation"]):
        return "global"
    if has_filter:
        return "filtered"
    if has_owner_op and (not tokens or self_only):
        return "owner"
    if has_owner_op and tokens:
        # hero_dps with non-empty non-positional targets (e.g. all) → not owner.
        if tokens == ["all"]:
            return "global"
        return "filtered"
    return "unknown"


def _scope_from_subeffects(
    base_scope: str,
    subeffects: list[dict[str, Any]],
) -> str:
    """Upgrade to mixed when subeffects disagree on recipient sets."""
    target_sets: list[tuple[str, ...]] = []
    for sub in subeffects:
        rec = sub.get("recipients") if isinstance(sub.get("recipients"), dict) else {}
        targets = rec.get("targets") if isinstance(rec, dict) else None
        if isinstance(targets, list) and targets:
            target_sets.append(tuple(targets))
    if len(set(target_sets)) > 1:
        return "mixed"
    return base_scope


def _uggie_position_source(keys: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Companion source for Uggie non-adjacent buffs."""
    for key in keys:
        es = key.get("effect_string")
        if not isinstance(es, str):
            continue
        if not _op_name(es).startswith("uggie"):
            continue
        buff_id = key.get("uggie_buff_effect_id")
        return {
            "kind": "uggie_companion",
            "buff_effect_id": int(buff_id) if isinstance(buff_id, int) else buff_id,
            "position_status": "unknown",
            "note": (
                "Adjacency is measured from Uggie's companion position, not from "
                "a formation seat. Host/spawn rules are separate from recipients."
            ),
        }
    return None


def _filter_predicate(key: dict[str, Any]) -> dict[str, Any] | None:
    """Structured recipient filter from filter_targets (not scaling)."""
    filt = key.get("filter_targets")
    if not isinstance(filt, list) or not filt:
        return None
    clauses: list[str] = []
    tags: list[str] = []
    requires_magic: bool | None = None
    for item in filt:
        if not isinstance(item, dict):
            continue
        expr = item.get("hero_expr")
        if isinstance(expr, str) and expr.strip():
            clauses.append(expr.strip())
            tags.extend(m.group(1) for m in re.finditer(r"HasTag\(`([^`]+)`\)", expr))
            low = expr.casefold()
            if re.search(r"!\s*has_base_attack_dmg_type_magic", low):
                requires_magic = False
            elif "has_base_attack_dmg_type_magic" in low:
                requires_magic = True
    if not clauses and not tags and requires_magic is None:
        return None
    return {
        "expressions": clauses or None,
        "tags": tags or None,
        "requires_magic_attack": requires_magic,
        "combine": "and",
    }


_ACTIVATION_ONLY_OPS = frozenset(
    {
        "apply_effects_at_stacks",
        "do_nothing",
        "pre_stack",
    }
)


def build_subeffects(keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One subeffect per meaningful effect_key — own recipients and parameters."""
    out: list[dict[str, Any]] = []
    for index, key in enumerate(keys, start=1):
        es = key.get("effect_string")
        if not isinstance(es, str) or not es.strip():
            continue
        op = _op_name(es)
        if op in _ACTIVATION_ONLY_OPS or op.startswith("disallow_"):
            continue
        if op.endswith("_handler") and not _is_magnitude_op(op):
            # Handlers are activation/control — not magnitude subeffects.
            continue
        if op in {"set_ultimate_attack", "change_base_attack"}:
            # Attack-id wiring is a reference, not a recipient subeffect.
            continue
        tokens = _target_tokens([key])
        filt = _filter_predicate(key)
        number = _second_number(es)
        computed = bool(
            key.get("use_computed_amount_for_description") or key.get("amount_expr")
        )
        params: list[dict[str, Any]] = []
        if number is not None and (
            _is_magnitude_op(op) or op == "base_attack_deal_bonus_damage"
        ):
            meaning, unit = _param_unit_meaning(op)
            role = _param_role(op, targets=tokens)
            if computed:
                params.append(
                    {
                        "name": role,
                        "value": None,
                        "meaning": meaning,
                        "unit": unit,
                        "value_basis": "computed",
                        "status": "computed_unknown",
                    }
                )
            elif not (op.startswith("buff_upgrade") and number == 0):
                params.append(
                    {
                        "name": role,
                        "value": number,
                        "meaning": meaning,
                        "unit": unit,
                        "value_basis": "definition_base",
                        "status": "known",
                    }
                )
        # Recipient defaults: missing targets on health_mult → self/owner.
        recipients_targets = tokens or (
            ["self"]
            if ("health_mult" in op or op == "health_add") and "global" not in op
            else None
        )
        if op.startswith("global_"):
            recipients_targets = recipients_targets or ["all"]
        activation = None
        if op.startswith("if_stunned") or "when_monster_stunned" in op:
            activation = {
                "kind": "target_enemy_stunned",
                "status": "known",
                "note": "Applies when the attacked enemy is stunned.",
            }
        sub: dict[str, Any] = {
            "id": f"sub_{index}",
            "effect_key_index": index,
            "effect_key": op,
            "operation": op,
            "parameters": params or None,
            "recipients": {
                "targets": recipients_targets,
                "filter": filt,
            },
            "activation_conditions": activation,
            "stacking": _stacking_info([key], None),
        }
        # Drop empty filter/targets shells.
        rec = {k: v for k, v in (sub["recipients"] or {}).items() if v is not None}
        sub["recipients"] = rec or None
        out.append({k: v for k, v in sub.items() if v is not None})
    return out


def _load_effect_row(effect_id: int) -> dict[str, Any] | None:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data

        rows = cached_definitions_data().get("effect_defines")
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and int(row.get("id") or 0) == effect_id:
            return row
    return None


def _role_filter(keys: list[dict[str, Any]]) -> str | None:
    for key in keys:
        es = key.get("effect_string")
        if not isinstance(es, str):
            continue
        parts = [part.strip().casefold() for part in es.split(",") if part.strip()]
        if parts and parts[-1] in _ROLE_TOKENS:
            return parts[-1]
    return None


def _stacking_info(keys: list[dict[str, Any]], text: str | None) -> dict[str, str]:
    """Unambiguous stacking: mode + status (not a single boolean)."""
    modes: list[str] = []
    for key in keys:
        if key.get("stacks_multiply") is True:
            modes.append("multiplicative")
            continue
        if key.get("stacks_multiply") is False:
            modes.append("additive")
            continue
        if key.get("amount_func") == "mult":
            modes.append("multiplicative")
            continue
        if key.get("amount_func") == "add":
            modes.append("additive")
            continue
        if key.get("manual_stacking") is True:
            modes.append("unknown")
            continue
        es = key.get("effect_string")
        if isinstance(es, str):
            op = _op_name(es)
            if op.endswith("_mult") or "per_tagged_crusader_mult" in op:
                modes.append("multiplicative")
    if text:
        lowered = text.casefold()
        if "stacking multiplicatively" in lowered or "stacks multiplicatively" in lowered:
            modes.append("multiplicative")
        if "stacking additively" in lowered or "stacks additively" in lowered:
            modes.append("additive")
    unique = {m for m in modes if m != "unknown"}
    if not modes:
        return {"mode": "unknown", "status": "unknown"}
    if "unknown" in modes and not unique:
        return {"mode": "unknown", "status": "unknown"}
    if len(unique) > 1:
        return {"mode": "mixed", "status": "partial"}
    if unique == {"multiplicative"}:
        return {"mode": "multiplicative", "status": "known"}
    if unique == {"additive"}:
        return {"mode": "additive", "status": "known"}
    return {"mode": "unknown", "status": "unknown"}


def _stacking(keys: list[dict[str, Any]], text: str | None) -> bool | None:
    """Legacy bool: True=multiplicative, False=additive, None=unknown/mixed."""
    info = _stacking_info(keys, text)
    if info["mode"] == "multiplicative":
        return True
    if info["mode"] == "additive":
        return False
    return None


def _modifier_percent(effect_field: str | None) -> float | None:
    if not isinstance(effect_field, str):
        return None
    match = re.match(r"buff_upgrades?\s*,\s*([\d.]+)\s*,\s*\d+", effect_field.strip())
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def effect_facts(
    effect_field: str | None,
    effect_row: dict[str, Any] | None,
    *,
    selected_upgrade_ids: set[int] | None = None,
    owner_name: str | None = None,
) -> dict[str, Any]:
    keys = list(_keys(effect_row))
    # Follow Uggie companion buff definition for recipient geometry.
    uggie_source = _uggie_position_source(keys)
    linked_buff_keys: list[dict[str, Any]] = []
    if uggie_source and uggie_source.get("buff_effect_id"):
        linked = _load_effect_row(int(uggie_source["buff_effect_id"]))
        linked_buff_keys = _keys(linked)
        # Prefer buff-effect geometry over unrelated sibling keys (e.g. ultimate).
        if linked_buff_keys:
            keys = keys + linked_buff_keys

    amount, amount_status = _amount_status(keys)
    params = typed_parameters(keys)
    stack_info = _stacking_info(keys, None)
    conditional = parse_conditional_targeting(
        keys, selected_upgrade_ids=selected_upgrade_ids
    )
    recipient_tokens = _target_tokens(keys)
    # Recipient tags from filter_targets only (not per_hero_expr scaling).
    recipient_tags = _target_tags(keys, selected_upgrade_ids=selected_upgrade_ids)
    scaling = _scaling_population(_keys(effect_row))  # original keys only
    scope = _effect_scope(keys)

    # When Uggie links a non_adj buff, recipients are non-adjacent to Uggie —
    # never "all" from an unrelated ultimate key on the same ability.
    if uggie_source:
        buff_tokens = _target_tokens(linked_buff_keys) if linked_buff_keys else []
        if "non_adj" in buff_tokens or "non_adj" in recipient_tokens:
            recipient_tokens = ["non_adj"]
            # Fallbacks filter on ultimate is host/strike context, not recipients.
            recipient_tags = [
                t for t in recipient_tags if t.casefold() != "fallbacks"
            ]

    activation = None
    for key in _keys(effect_row):
        es = key.get("effect_string")
        if not isinstance(es, str):
            continue
        op = _op_name(es)
        if op == "apply_effects_at_stacks":
            activation = {
                "kind": "stack_threshold",
                "status": "partial",
                "note": (
                    "Sibling keys activate at a stack/phase threshold; "
                    "exact stack count is not fully numeric here."
                ),
            }
            break
        if "lantern" in op and "handler" in op:
            activation = {
                "kind": "health_threshold_handler",
                "status": "partial",
                "note": (
                    "Activation threshold comes from ability handler/prose; "
                    "not fully numeric in this export."
                ),
            }
            break
        if op.startswith("uggie_handler"):
            activation = {
                "kind": "uggie_spawn_host",
                "status": "partial",
                "note": (
                    "Uggie host/spawn rules are separate from non-adjacent recipients."
                ),
            }
            break

    subeffects = build_subeffects(_keys(effect_row))
    scope = _scope_from_subeffects(scope, subeffects)

    # Position source for positional buffs defaults to owner when not a companion.
    position_source = uggie_source
    if position_source is None and scope == "positional" and owner_name:
        position_source = {
            "kind": "owner",
            "owner": owner_name,
            "position_status": "formation_seat",
        }

    # When subeffects disagree on recipients/filters, do not flatten to one set.
    distinct_filters = [
        s.get("recipients", {}).get("filter")
        for s in subeffects
        if isinstance(s.get("recipients"), dict) and s["recipients"].get("filter")
    ]
    distinct_targets = [
        tuple(s.get("recipients", {}).get("targets") or ())
        for s in subeffects
        if isinstance(s.get("recipients"), dict)
        and s["recipients"].get("targets")
    ]
    merge_recipients = (
        len({json.dumps(f, sort_keys=True, default=str) for f in distinct_filters if f})
        <= 1
        and len(set(distinct_targets)) <= 1
    )

    semantics: dict[str, Any] = {
        "scope": scope,
        "owner_ref": owner_name,
        "recipients": {
            "targets": recipient_tokens or None,
            "tags": recipient_tags or None,
            "combine": "or" if conditional.get("extensions") else None,
        }
        if merge_recipients
        else None,
        "scaling_population": scaling,
        "position_source": position_source,
        "activation_conditions": activation,
        "subeffects": subeffects or None,
        "predicate": {
            "base_tags": conditional.get("base_tags"),
            "base_clauses": conditional.get("base_clauses"),
            "base_stat_gates": conditional.get("base_stat_gates"),
            "active_tags": conditional.get("active_tags"),
            "extensions": conditional.get("extensions"),
            "combine": "or",
            "status": conditional.get("predicate_status"),
        }
        if merge_recipients
        and (conditional.get("base_clauses") or conditional.get("extensions"))
        else None,
    }
    # Drop empty nested shells.
    for nest in ("recipients", "predicate"):
        if isinstance(semantics.get(nest), dict):
            cleaned = {k: v for k, v in semantics[nest].items() if v is not None}
            semantics[nest] = cleaned or None
    semantics = {k: v for k, v in semantics.items() if v is not None}

    # Internal mirrors for quality/debug; advice projection uses semantics only.
    facts: dict[str, Any] = {
        "targets": (recipient_tokens or None) if merge_recipients else None,
        "target_tags": (recipient_tags or None) if merge_recipients else None,
        "targeting": semantics.get("predicate"),
        "semantics": semantics or None,
        "effect_scope": scope,
        "role_filter": _role_filter(keys),
        "referenced_upgrade_ids": referenced_upgrade_ids(effect_field, effect_row)
        or None,
        "amount": amount if amount_status == "known" else None,
        "amount_status": amount_status,
        "stacking": stack_info,
        "stacking_multiplicative": (
            True
            if stack_info["mode"] == "multiplicative"
            else False
            if stack_info["mode"] == "additive"
            else "unknown"
        ),
        "parameters": params or None,
        "effect_strings": [
            key.get("effect_string")
            for key in _keys(effect_row)
            if isinstance(key.get("effect_string"), str)
        ]
        or None,
        "unknown_effect_args": [
            arg
            for key in _keys(effect_row)
            for arg in (
                parse_effect_string(str(key.get("effect_string") or "")).get(
                    "unknown_args"
                )
                or []
            )
            if isinstance(key.get("effect_string"), str)
        ]
        or None,
    }
    return {key: value for key, value in facts.items() if value is not None}


def _prose_targets(text: str | None) -> set[str]:
    if not text:
        return set()
    lowered = text.casefold()
    found: set[str] = set()
    if "adjacent" in lowered and "non-adjacent" not in lowered and "non adjacent" not in lowered:
        found.add("adj")
    if "non-adjacent" in lowered or "non adjacent" in lowered:
        found.add("non_adj")
    if "same column" in lowered or "in the column" in lowered:
        found.add("col")
    if "behind" in lowered:
        found.add("behind")
    if "in front" in lowered or "ahead" in lowered:
        found.add("ahead")
    if "lawful" in lowered:
        found.add("lawful")
    if "chaotic" in lowered:
        found.add("chaotic")
    if re.search(r"\bgood\b", lowered) and "lawful good" not in lowered:
        found.add("good")
    if re.search(r"\bevil\b", lowered):
        found.add("evil")
    return found


def _targeting_known(
    text: str | None,
    tokens: list[str],
    tags: list[str],
) -> bool | None:
    known_tokens = [token for token in tokens if token in _TARGET_WORDS or token == "by_tags"]
    prose = _prose_targets(text)
    if tags:
        return True
    if known_tokens and prose and not prose.intersection(known_tokens) and "by_tags" not in known_tokens:
        # Soft conflict — still treat tag/prose alignment tags as known.
        if prose.intersection(_ALIGNMENT_TAGS):
            return True
        return None
    if known_tokens or prose:
        return True
    if text and re.search(r"\b(formation|all champions)\b", text, re.IGNORECASE):
        return True
    return None


def _amount_index(raw_key: str) -> int | None:
    """Map amount / amount___N → 1-based effect_key index (IC convention)."""
    key = raw_key.casefold().strip()
    key = re.sub(r"^not_buffed\s+", "", key)
    key = re.sub(r"^buffed\s+", "", key)
    # Indexed amounts first — amount___2 must not collapse to index 1.
    match = re.fullmatch(r"amount(?:___|_)(\d+)", key)
    if match:
        index = int(match.group(1))
        return index if index >= 1 else 1
    if key == "amount" or key in _AMOUNT_NAMES:
        return 1
    return None


def _indexed_field_placeholder(raw_key: str) -> tuple[str, int] | None:
    """Map amount|amount_desc|chance(+___N) → (field, 1-based effect_key index)."""
    key = raw_key.casefold().strip()
    key = re.sub(r"^not_buffed\s+", "", key)
    key = re.sub(r"^buffed\s+", "", key)
    # Indexed forms first — amount___2 must not collapse via _AMOUNT_NAMES to 1.
    for field in ("amount_desc", "chance", "amount"):
        match = re.fullmatch(rf"{field}(?:___|_)(\d+)", key)
        if match:
            index = int(match.group(1))
            return field, index if index >= 1 else 1
        if key == field:
            return field, 1
    if key in _AMOUNT_NAMES:
        return "amount", 1
    return None


def _value_from_effect_key_field(
    keys: list[dict[str, Any]],
    index_1based: int,
    field: str,
) -> dict[str, Any] | None:
    """Resolve amount / amount_desc / chance from the Nth effect_key."""
    if field == "amount":
        return _amount_from_effect_key(keys, index_1based)
    if index_1based < 1 or index_1based > len(keys):
        return None
    key = keys[index_1based - 1]
    es = key.get("effect_string") if isinstance(key.get("effect_string"), str) else None
    op = _op_name(es) if es else None
    raw = key.get(field)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return {
            "value": float(raw),
            "status": "known",
            "effect_string": es,
            "effect_key": op,
            "param_role": field,
            "meaning": "percent" if field in {"amount_desc", "chance"} else "number",
            "unit": "percent" if field in {"amount_desc", "chance"} else None,
            "value_basis": "definition_base",
        }
    # Fall back to the effect_string magnitude for amount_desc when only that exists.
    if field == "amount_desc":
        return _amount_from_effect_key(keys, index_1based)
    return {
        "value": None,
        "status": "absent",
        "effect_string": es,
        "effect_key": op,
        "param_role": field,
        "value_basis": None,
    }


def _amount_from_effect_key(
    keys: list[dict[str, Any]],
    index_1based: int,
) -> dict[str, Any] | None:
    """Resolve placeholder against the Nth effect_key (1-based), not magnitude-slot order.

    This prevents Phase Two ``$(amount___2)`` from borrowing the health-sharing 25
    when ``health_mult,1`` is effect_key index 2.
    """
    if index_1based < 1 or index_1based > len(keys):
        return None
    key = keys[index_1based - 1]
    es = key.get("effect_string")
    if not isinstance(es, str) or not es.strip():
        return {
            "value": None,
            "status": "absent",
            "effect_string": None,
            "effect_key": None,
            "value_basis": None,
        }
    op = _op_name(es)
    number = _second_number(es)
    computed = bool(
        key.get("use_computed_amount_for_description") or key.get("amount_expr")
    )
    if computed:
        return {
            "value": None,
            "status": "computed_unknown",
            "effect_string": es,
            "effect_key": op,
            "param_role": _param_role(op, targets=_target_tokens([key])),
            "meaning": _param_unit_meaning(op)[0],
            "unit": _param_unit_meaning(op)[1],
            "value_basis": "computed",
        }
    if number is None:
        return {
            "value": None,
            "status": "absent",
            "effect_string": es,
            "effect_key": op,
            "value_basis": "definition_base",
        }
    meaning, unit = _param_unit_meaning(op)
    return {
        "value": number,
        "status": "known",
        "effect_string": es,
        "effect_key": op,
        "param_role": _param_role(op, targets=_target_tokens([key])),
        "meaning": meaning,
        "unit": unit,
        "value_basis": "definition_base",
    }


def _param_role(op: str, *, targets: list[str] | None = None) -> str:
    """Stable semantic name for a magnitude-bearing effect key."""
    if op == "base_attack_deal_bonus_damage":
        return "additional_bud_damage"
    if "dps_multiplier_reduce" in op or op.endswith("_reduce"):
        return "damage_reduction"
    if "crit_chance" in op or "critchance" in op:
        return "crit_chance"
    if "crit_damage" in op or "critdamage" in op:
        return "crit_damage"
    if "gold" in op:
        return "gold_find"
    if "healing" in op:
        return "healing"
    if "health" in op:
        return "health"
    if "global_dps" in op:
        return "global_damage"
    if "hero_dps" in op:
        tokens = targets or []
        if any(t in _POSITIONAL_TARGET_TOKENS for t in tokens):
            return "damage"
        if tokens in (["all"], ["formation"]):
            return "damage"
        return "owner_damage"
    if op.startswith("buff_upgrade"):
        return "modifier"
    return "amount"


def positional_recipient_applies(
    token: str,
    *,
    owner_column: int,
    candidate_column: int,
    candidate_is_owner: bool = False,
) -> bool | None:
    """Whether a candidate seat receives a positional buff.

    Front of formation = lower ``column_index``. ``None`` means the token is
    not a verified positional pattern handled here.
    """
    t = (token or "").strip().casefold()
    if t == "col_and_behind":
        return candidate_column >= owner_column
    if t == "col_and_ahead":
        return candidate_column <= owner_column
    if t == "next_col":
        return candidate_column == owner_column - 1
    if t == "prev_col":
        return candidate_column == owner_column + 1
    if t == "self_and_prev_two_col":
        if candidate_is_owner:
            return True
        return owner_column < candidate_column <= owner_column + 2
    if t == "prev_two_col":
        return owner_column < candidate_column <= owner_column + 2
    if t == "col":
        return candidate_column == owner_column
    if t in {"self", "s"}:
        return candidate_is_owner
    if t == "all":
        return True
    if t == "other":
        return not candidate_is_owner
    return None


def _param_unit_meaning(op: str) -> tuple[str, str | None]:
    """Return (meaning, unit) for a verified effect op — no damage→percent fallback."""
    if op == "base_attack_deal_bonus_damage":
        return "seconds_of_bud", "seconds_of_bud"
    if op.startswith("buff_upgrade"):
        return "percent", "percent"
    if any(
        token in op
        for token in ("_mult", "percent", "chance", "crit", "healing", "health", "dps")
    ):
        return "percent", "percent"
    if op.endswith("_add") and "health" in op:
        return "number", None
    return "number", None


def _magnitude_slots(keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One slot per verified magnitude-bearing effect_key, in definition order."""
    slots: list[dict[str, Any]] = []
    for key in keys:
        es = key.get("effect_string")
        if not isinstance(es, str) or not es.strip():
            continue
        op = _op_name(es)
        if not _is_magnitude_op(op):
            continue
        number = _second_number(es)
        if number is None:
            continue
        computed = bool(
            key.get("use_computed_amount_for_description") or key.get("amount_expr")
        )
        key_targets = _target_tokens([key])
        role = _param_role(op, targets=key_targets)
        meaning, unit = _param_unit_meaning(op)
        # Passthrough 0 with amount_expr / computed flag is not a real bonus.
        if computed:
            slots.append(
                {
                    "value": None,
                    "status": "computed_unknown",
                    "effect_string": es,
                    "effect_key": op,
                    "param_role": role,
                    "meaning": meaning,
                    "unit": unit,
                    "value_basis": "computed",
                    "raw_passthrough": number if number == 0 else None,
                }
            )
            continue
        # buff_upgrade,0,… is a dependency/passthrough, not an $amount slot.
        if op.startswith("buff_upgrade") and number == 0:
            continue
        slots.append(
            {
                "value": number,
                "status": "known",
                "effect_string": es,
                "effect_key": op,
                "param_role": role,
                "meaning": meaning,
                "unit": unit,
                "value_basis": "definition_base",
            }
        )
    return slots


def resolve_placeholders(
    text: str | None,
    *,
    effect_row: dict[str, Any] | None,
    effect_field: str | None,
    owner_name: str | None,
    upgrade_name_by_id: dict[int, str] | None,
) -> tuple[str | None, list[str], list[dict[str, Any]]]:
    """Substitute per-placeholder amounts. Never reuse one slot for another."""
    if isinstance(text, dict):
        text = str(text.get("desc") or text.get("description") or "").strip() or None
    if not text:
        return text, [], []
    keys = _keys(effect_row)
    tokens = _target_tokens(keys)
    target_phrase = None
    if len(tokens) == 1 and tokens[0] in _TARGET_WORDS:
        target_phrase = _TARGET_WORDS[tokens[0]]
    refs = referenced_upgrade_ids(effect_field, effect_row)
    upgrade_name = None
    if len(refs) == 1 and upgrade_name_by_id:
        upgrade_name = upgrade_name_by_id.get(refs[0])
    unresolved: list[str] = []
    substitutions: list[dict[str, Any]] = []

    def _replace(match: re.Match[str]) -> str:
        raw = (match.group(1) or match.group(2) or "").strip()
        key = raw.casefold()
        original = match.group(0)
        indexed = _indexed_field_placeholder(key)
        if indexed is not None:
            field, amount_idx = indexed
            # 1-based effect_key index — never borrow another key's magnitude.
            slot = _value_from_effect_key_field(keys, amount_idx, field)
            if slot and slot.get("status") == "known" and slot.get("value") is not None:
                formatted = _fmt_number(float(slot["value"]))
                substitutions.append(
                    {
                        "placeholder": original,
                        "effect": slot.get("effect_string"),
                        "effect_key": slot.get("effect_key"),
                        "source_parameter": slot.get("param_role") or field,
                        "effect_key_index": amount_idx,
                        "value": slot["value"],
                        "unit": slot.get("unit"),
                        "value_basis": slot.get("value_basis"),
                    }
                )
                return formatted
            unresolved.append(original)
            substitutions.append(
                {
                    "placeholder": original,
                    "effect": (slot or {}).get("effect_string"),
                    "effect_key": (slot or {}).get("effect_key"),
                    "source_parameter": field,
                    "effect_key_index": amount_idx,
                    "value": None,
                    "value_basis": (slot or {}).get("value_basis"),
                    "status": (slot or {}).get("status") or "absent",
                }
            )
            return f"{original} (onbekend)"
        if key in {"source", "source_hero"}:
            return owner_name or "deze champion"
        if key == "target":
            # "$target increases…" → emanation source (owner), not geometry.
            source_style = bool(
                text
                and re.search(
                    r"\$\(?target\)?\s+(increases|deals|buffs|provides)|"
                    r"\$\(?target\)?'s\b",
                    text,
                    flags=re.IGNORECASE,
                )
            )
            if source_style:
                if owner_name:
                    substitutions.append(
                        {
                            "placeholder": original,
                            "effect": None,
                            "source_parameter": "owner_champion",
                            "value": owner_name,
                            "value_basis": "definition_base",
                        }
                    )
                    return owner_name
                unresolved.append(original)
                substitutions.append(
                    {
                        "placeholder": original,
                        "effect": None,
                        "source_parameter": "owner_champion",
                        "value": None,
                        "status": "source_unknown",
                    }
                )
                return f"{original} (bron onbekend)"
            if target_phrase:
                return target_phrase
            if owner_name:
                return owner_name
            unresolved.append(original)
            return f"{original} (bron onbekend)"
        if key in {"upgrade_name id", "upgrade_name upgrade_id"} and upgrade_name:
            return upgrade_name
        if key in {"max_stacks", "duration"}:
            field = "max_stacks" if "stack" in key else "duration"
            for effect_key in keys:
                value = effect_key.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return _fmt_number(float(value))
            unresolved.append(original)
            return f"{original} (onbekend)"
        unresolved.append(original)
        return f"{original} (onbekend)"

    resolved = _PLACEHOLDER.sub(_replace, text)
    seen: set[str] = set()
    unique: list[str] = []
    for item in unresolved:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return resolved, unique, substitutions


def quality_flags(
    text: str | None,
    effect_row: dict[str, Any] | None,
    effect_field: str | None,
    *,
    unresolved_placeholders: list[str],
    upgrade_ids_known: set[int] | None = None,
    upgrade_ids_resolved: set[int] | None = None,
    selected_upgrade_ids: set[int] | None = None,
) -> dict[str, Any]:
    keys = _keys(effect_row)
    tokens = _target_tokens(keys)
    tags = _target_tags(keys, selected_upgrade_ids=selected_upgrade_ids)
    amount, amount_status = _amount_status(keys)
    targeting = _targeting_known(text, tokens, tags)
    source_unresolved = any(
        "target" in str(p).casefold() or "bron" in str(p).casefold()
        for p in unresolved_placeholders
    )
    amount_unresolved = any(
        "amount" in str(p).casefold() for p in unresolved_placeholders
    )
    if source_unresolved:
        targeting = False if targeting is False else None
    has_condition = bool(
        tags
        or _role_filter(keys)
        or any(_hero_expr_from_key(key) for key in keys)
    )
    if has_condition:
        conditions: bool | None = True
    elif targeting is True:
        conditions = True
    else:
        conditions = None

    if amount_status == "not_applicable":
        magnitude: bool | str | None = "not_applicable"
    elif amount_unresolved or amount_status in {
        "computed_unknown",
        "unknown",
        "partial",
    }:
        magnitude = False
    elif amount_status == "known" and amount is not None:
        magnitude = True
    else:
        magnitude = None

    stack_info = _stacking_info(keys, text)
    refs = referenced_upgrade_ids(effect_field, effect_row)
    if not refs:
        dependencies: bool | None = True
        deps_present = True
    elif upgrade_ids_known is None:
        dependencies = None
        deps_present = None
    else:
        deps_present = all(ref in upgrade_ids_known for ref in refs)
        if not deps_present:
            dependencies = False
        elif upgrade_ids_resolved is not None:
            dependencies = all(ref in upgrade_ids_resolved for ref in refs)
        else:
            # Present in catalog is not the same as mechanically resolved.
            dependencies = None

    usable_placement: bool | None
    if targeting is True:
        usable_placement = True
    elif targeting is False:
        usable_placement = False
    else:
        usable_placement = None

    # Numeric comparison requires a real magnitude (not a reference id) plus
    # resolved dependencies and known targeting/conditions.
    usable_numeric: bool | None
    if magnitude is True and dependencies is True and targeting is not False:
        usable_numeric = True
    elif magnitude in (False, "not_applicable") or dependencies is False:
        usable_numeric = False
    elif not text and magnitude is not True:
        usable_numeric = False
    else:
        usable_numeric = None

    stacking_known: bool | str
    if stack_info["status"] == "known":
        stacking_known = True
    elif stack_info["status"] == "partial":
        stacking_known = "partial"
    else:
        stacking_known = "unknown"

    return {
        "targeting_known": _tri(targeting),
        "conditions_known": _tri(conditions),
        "magnitude_known": magnitude if magnitude == "not_applicable" else _tri(
            magnitude if isinstance(magnitude, bool) else None
        ),
        "stacking": stack_info,
        "stacking_known": stacking_known,
        "stacking_multiplicative": (
            True
            if stack_info["mode"] == "multiplicative"
            else False
            if stack_info["mode"] == "additive"
            else "unknown"
        ),
        "dependencies_found": bool(refs),
        "dependencies_present": _tri(deps_present if refs else True),
        "dependencies_resolved": _tri(dependencies),
        "usable_for_placement": _tri(usable_placement),
        "usable_for_numeric_comparison": _tri(usable_numeric),
        "numeric_scope": (
            "local_definition"
            if magnitude is True
            else "unknown"
            if magnitude is None
            else "not_applicable"
            if magnitude == "not_applicable"
            else "incomplete"
        ),
    }


def refine_mechanic(
    text: str | None,
    effect_row: dict[str, Any] | None,
    effect_field: str | None,
    *,
    owner_name: str | None = None,
    upgrade_name_by_id: dict[int, str] | None = None,
    upgrade_ids_known: set[int] | None = None,
    upgrade_ids_resolved: set[int] | None = None,
    selected_upgrade_ids: set[int] | None = None,
) -> dict[str, Any]:
    resolved, unresolved, substitutions = resolve_placeholders(
        text,
        effect_row=effect_row,
        effect_field=effect_field,
        owner_name=owner_name,
        upgrade_name_by_id=upgrade_name_by_id,
    )
    facts = effect_facts(
        effect_field,
        effect_row,
        selected_upgrade_ids=selected_upgrade_ids,
        owner_name=owner_name,
    )
    # Restack using resolved text so multiplicative/additive prose is seen.
    if (facts.get("stacking") or {}).get("status") == "unknown":
        stack_info = _stacking_info(_keys(effect_row), resolved or text)
        facts["stacking"] = stack_info
    quality = quality_flags(
        resolved or text,
        effect_row,
        effect_field,
        unresolved_placeholders=unresolved,
        upgrade_ids_known=upgrade_ids_known,
        upgrade_ids_resolved=upgrade_ids_resolved,
        selected_upgrade_ids=selected_upgrade_ids,
    )
    return {
        "text": resolved if resolved else text,
        "unresolved_placeholders": unresolved or None,
        "placeholder_substitutions": substitutions or None,
        "effect_facts": facts or None,
        "quality": quality,
    }


def selection_status(
    *,
    choices_observed: bool,
    selected_option_id: int | None,
    required_level: int | None,
    hero_level: int | None,
) -> str:
    """selected | not_unlocked | unselected | unknown."""
    if selected_option_id is not None:
        return "selected"
    if not choices_observed:
        return "unknown"
    if (
        required_level is not None
        and required_level > 0
        and hero_level is not None
        and hero_level < required_level
    ):
        return "not_unlocked"
    return "unselected"


def trait_changes_from_keys(keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Structured trait mutations from effect_keys (add/replace)."""
    changes: list[dict[str, Any]] = []
    for key in keys:
        es = key.get("effect_string")
        if not isinstance(es, str):
            continue
        parts = [p.strip() for p in es.split(",")]
        op = parts[0].casefold() if parts else ""
        if op == "change_hero_alignment_tag" and len(parts) >= 3:
            changes.append(
                {
                    "trait": "alignment",
                    "mode": "replace",
                    "law_chaos": parts[1].casefold(),
                    "good_evil": parts[2].casefold(),
                    "source_effect": es,
                }
            )
        elif op == "add_hero_tags" and len(parts) >= 3:
            tag = parts[2].casefold()
            trait = "role" if tag in _ROLE_TOKENS else "tag"
            changes.append(
                {
                    "trait": trait,
                    "mode": "add",
                    "value": tag,
                    "source_effect": es,
                }
            )
        elif op == "remove_hero_tags" and len(parts) >= 3:
            tag = parts[2].casefold()
            trait = "role" if tag in _ROLE_TOKENS else "tag"
            changes.append(
                {
                    "trait": trait,
                    "mode": "remove",
                    "value": tag,
                    "source_effect": es,
                }
            )
    return changes


def apply_trait_changes(
    *,
    base_alignment: dict[str, Any] | None,
    base_roles: list[str],
    base_tags: list[str],
    changes: list[dict[str, Any]],
    sources: list[str],
) -> dict[str, Any]:
    """Derive effective traits; add does not erase existing values."""
    alignment = dict(base_alignment or {})
    roles = list(base_roles)
    tags = list(base_tags)
    applied: list[dict[str, Any]] = []
    for change, source in zip(changes, sources):
        row = {**change, "source": source}
        if change.get("trait") == "alignment" and change.get("mode") == "replace":
            alignment = {
                **alignment,
                "law_chaos": change.get("law_chaos"),
                "good_evil": change.get("good_evil"),
                "label": f"{str(change.get('law_chaos') or '').title()} "
                f"{str(change.get('good_evil') or '').title()}".strip(),
                "effective_from": source,
            }
        elif change.get("trait") == "role" and change.get("mode") == "add":
            value = str(change.get("value") or "")
            if value and value not in {r.casefold() for r in roles}:
                roles.append(value)
        elif change.get("trait") == "tag" and change.get("mode") == "add":
            value = str(change.get("value") or "")
            if value and value not in {t.casefold() for t in tags}:
                tags.append(value)
        elif change.get("mode") == "remove":
            value = str(change.get("value") or "").casefold()
            if change.get("trait") == "role":
                roles = [r for r in roles if r.casefold() != value]
            else:
                tags = [t for t in tags if t.casefold() != value]
        applied.append(row)
    return {
        "alignment": alignment or None,
        "roles": roles,
        "tags": tags,
        "applied_changes": applied or None,
    }


def detect_restriction_override(
    *,
    mechanical_text: str | None,
    effect_strings: list[str] | None,
    source_ability_id: int | None,
    source_champion_id: int | None,
) -> dict[str, Any] | None:
    """Restriction bypass from effect keys + description evidence.

    Requires a concrete effect_string signal (force_allow_* or do_nothing).
    Prose alone is not enough; prose refines the condition kind.
    """
    strings = [s for s in (effect_strings or []) if isinstance(s, str)]
    text = (mechanical_text or "").strip()
    lowered = text.casefold()

    for es in strings:
        if es.casefold().startswith("force_allow_hero_by_tag"):
            parts = [p.strip() for p in es.split(",")]
            tag = parts[-1] if len(parts) >= 2 else None
            return {
                "kind": "force_allow_hero_by_tag",
                "source_ability_id": source_ability_id,
                "source_champion_id": source_champion_id,
                "required_tag": tag,
                "condition": "target_has_tag",
                "evidence": "effect_string",
            }

    if any(_op_name(s) == "do_nothing" for s in strings) and text:
        if (
            "eligible to start in all adventures" in lowered
            or "even if the patron, variant, or other restrictions" in lowered
        ):
            return {
                "kind": "unconditional_adventure_eligibility",
                "source_ability_id": source_ability_id,
                "source_champion_id": source_champion_id,
                "condition": "none",
                "evidence": "effect_string_do_nothing+description",
            }
        if "campaign" in lowered and (
            "can be used in any" in lowered
            or "even if he would not normally be available" in lowered
            or "even if they would not normally be available" in lowered
        ):
            scope = None
            match = re.search(
                r"any\s+(.+?)\s+campaign",
                text,
                flags=re.IGNORECASE,
            )
            if match:
                scope = match.group(1).strip()
            return {
                "kind": "campaign_scoped_eligibility",
                "source_ability_id": source_ability_id,
                "source_champion_id": source_champion_id,
                "condition": "active_campaign_matches_scope",
                "campaign_scope_text": scope,
                "evidence": "effect_string_do_nothing+description",
            }
    return None


def evaluate_restriction_overrides(
    *,
    base_status: str,
    base_reason: str | None,
    overrides: list[dict[str, Any]],
    champion_tags: list[str] | None,
    tags_known: bool,
    campaign_id: int | None,
    campaign_name: str | None,
) -> dict[str, Any]:
    """Full eligibility record with override condition results."""
    base = base_status if base_status in {"allowed", "denied", "unknown"} else "unknown"
    record: dict[str, Any] = {
        "base_eligibility": base,
        "base_reason": base_reason,
        "blocking_rules": [base_reason] if base == "denied" and base_reason else None,
        "overrides_considered": overrides or None,
        "override_condition_results": [],
        "override_source": None,
        "required_affiliation": None,
        "affiliation_verified": "unknown" if not tags_known else False,
        "effective_eligibility": base,
        "effective_reason": base_reason,
    }
    if base != "denied" or not overrides:
        if base == "allowed":
            record["effective_reason"] = base_reason or "allowed"
            record["affiliation_verified"] = True if tags_known else "unknown"
        return record

    tags = {tag.casefold() for tag in (champion_tags or [])}
    results: list[dict[str, Any]] = []
    for override in overrides:
        kind = override.get("kind") or (
            "force_allow_hero_by_tag" if override.get("required_tag") else "unknown"
        )
        result: dict[str, Any] = {
            "kind": kind,
            "source_ability_id": override.get("source_ability_id"),
            "condition": override.get("condition"),
            "verified": False,
            "outcome": "not_applicable",
        }
        if kind == "unconditional_adventure_eligibility":
            result["verified"] = True
            result["outcome"] = "allows"
            results.append(result)
            record["override_condition_results"] = results
            record["effective_eligibility"] = "allowed"
            record["effective_reason"] = (
                f"Unconditional eligibility via ability "
                f"{override.get('source_ability_id')}"
            )
            return record
        if kind == "campaign_scoped_eligibility":
            scope = str(override.get("campaign_scope_text") or "").casefold()
            name = str(campaign_name or "").casefold()
            if not scope or campaign_name is None and campaign_id is None:
                result["verified"] = False
                result["outcome"] = "unknown"
                results.append(result)
                record["override_condition_results"] = results
                record["effective_eligibility"] = "unknown"
                record["effective_reason"] = (
                    "Campaign-scoped eligibility: active campaign not verified"
                )
                return record
            if scope and scope in name:
                result["verified"] = True
                result["outcome"] = "allows"
                results.append(result)
                record["override_condition_results"] = results
                record["effective_eligibility"] = "allowed"
                record["effective_reason"] = (
                    f"Campaign scope matched ({campaign_name})"
                )
                return record
            result["verified"] = True
            result["outcome"] = "does_not_apply"
            results.append(result)
            continue
        if kind == "force_allow_hero_by_tag":
            tag = str(override.get("required_tag") or "").strip()
            result["required_tag"] = tag
            record["override_source"] = override.get("source_ability_id")
            record["required_affiliation"] = tag
            if not tag:
                result["outcome"] = "unknown"
                results.append(result)
                continue
            if not tags_known:
                result["outcome"] = "unknown"
                results.append(result)
                record["override_condition_results"] = results
                record["affiliation_verified"] = "unknown"
                record["effective_eligibility"] = "unknown"
                record["effective_reason"] = (
                    f"force_allow requires tag {tag}; affiliations not verified"
                )
                return record
            if tag.casefold() in tags:
                result["verified"] = True
                result["outcome"] = "allows"
                results.append(result)
                record["override_condition_results"] = results
                record["affiliation_verified"] = True
                record["effective_eligibility"] = "allowed"
                record["effective_reason"] = f"force_allow via tag {tag}"
                return record
            result["verified"] = True
            result["outcome"] = "does_not_apply"
            results.append(result)
            record["affiliation_verified"] = False
            continue
        result["outcome"] = "unknown"
        results.append(result)

    record["override_condition_results"] = results or None
    if results and all(r.get("outcome") == "does_not_apply" for r in results):
        record["effective_eligibility"] = "denied"
        record["effective_reason"] = base_reason
    elif results and any(r.get("outcome") == "unknown" for r in results):
        record["effective_eligibility"] = "unknown"
        record["effective_reason"] = "Override condition not verified"
    return record


def eligibility_record(
    *,
    base_status: str,
    base_reason: str | None,
    overrides: list[dict[str, Any]],
    champion_tags: list[str] | None,
    tags_known: bool,
    campaign_id: int | None = None,
    campaign_name: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around evaluate_restriction_overrides."""
    return evaluate_restriction_overrides(
        base_status=base_status,
        base_reason=base_reason,
        overrides=overrides,
        champion_tags=champion_tags,
        tags_known=tags_known,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
    )


def merge_restriction_sources(
    party_status: str,
    *,
    api_has_rules: bool,
    manual_text: str | None,
) -> str:
    """Manual text does not silently replace an API verdict."""
    if party_status == "conflict":
        return "conflict"
    if api_has_rules and manual_text and manual_text.strip():
        return "conflict"
    return party_status
