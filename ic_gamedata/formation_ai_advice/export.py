"""Build structured formation-advice export from live app data."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION, AdviceObjective
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.formation_advisor.models import FormationLayoutContext
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_advisor_models import FormationHero

PROMPT_VERSION = "1.5"

_INTERNAL_ABILITY_NAME = re.compile(r"^buff\s*fa\d+", re.IGNORECASE)
_MECHANICAL_HINT = re.compile(
    r"\b(damage|dmg|heal|adjacent|column|formation|buff|stack|tag|dps|"
    r"gold|ahead|behind|next to|multiplier|%|qualified|taunt|shield)\b",
    re.IGNORECASE,
)
_EFFECT_DEF_RE = re.compile(r"^effect_def\s*,\s*(\d+)\s*$", re.IGNORECASE)
_ROLE_TAGS = frozenset(
    {
        "tanking",
        "tank",
        "support",
        "healing",
        "healer",
        "dps",
        "gold",
        "speed",
        "clicking",
        "aoe",
        "bus",
    }
)
_ALIGNMENT_AXIS_TAGS = frozenset({"lawful", "chaotic", "good", "evil", "neutral"})
_META_TAGS = frozenset(
    {
        "evergreen",
        "core",
        "event",
        "positional",
        "unaffiliated",
        "female",
        "male",
        "non-binary",
        "nonbinary",
    }
)
# Structured gender for tag-based counts (e.g. Soprano). Not alignment/roles.
_GENDER_FROM_TAG = {
    "female": "female",
    "male": "male",
    "non-binary": "non-binary",
    "nonbinary": "non-binary",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def _data_version(payload: dict[str, Any]) -> str | None:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    for key in ("defines_updated_at", "updated_at", "current_time", "time"):
        value = details.get(key) if details else None
        if value is None:
            value = payload.get(key)
        if value is not None:
            return str(value)
    try:
        from ic_gamedata.app_version import version_label

        return version_label()
    except Exception:
        return None


def _permanent_seat(hero_id: int) -> int | None:
    try:
        from ic_gamedata.formation_seats import _definition_seat_by_hero

        return _definition_seat_by_hero().get(hero_id)
    except Exception:
        return None


def _parse_alignment(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    lower = text.casefold()
    law = None
    if "lawful" in lower:
        law = "lawful"
    elif "chaotic" in lower:
        law = "chaotic"
    elif "neutral" in lower:
        # "Neutral Evil" / "Lawful Neutral" / "True Neutral"
        parts = lower.replace("-", " ").split()
        if parts and parts[0] == "neutral" and len(parts) > 1:
            law = "neutral"
        elif "true neutral" in lower or lower == "neutral":
            law = "neutral"
        elif parts and parts[-1] == "neutral":
            law = None  # e.g. lawful neutral — law already set above
    moral = None
    if "good" in lower:
        moral = "good"
    elif "evil" in lower:
        moral = "evil"
    elif "neutral" in lower:
        parts = lower.replace("-", " ").split()
        if parts and parts[-1] == "neutral" and parts[0] in ("lawful", "chaotic"):
            moral = "neutral"
        elif "true neutral" in lower or lower == "neutral":
            moral = "neutral"
    return {
        "label": text,
        "law_chaos": law,
        "good_evil": moral,
        "source": "character_sheet_details.alignment",
    }


def _normalize_tag(tag: str) -> str:
    return str(tag).strip().casefold()


def gender_from_raw_tags(raw_tags: list[str] | None) -> dict[str, Any]:
    """Structured gender from ``hero_defines.tags`` only — never from names.

    Returns status known | unknown | conflict. ``tag`` is the mechanic tag
    used for counts (female/male/non-binary). Distinct from alignment/roles.
    """
    source = "hero_defines.tags"
    if raw_tags is None:
        return {
            "status": "unknown",
            "value": None,
            "tag": None,
            "source": None,
            "note": (
                "Genderbron ontbreekt (tags niet gelezen); niet afleiden uit "
                "naam, uiterlijk of algemene kennis."
            ),
        }
    found: list[str] = []
    for raw in raw_tags:
        mapped = _GENDER_FROM_TAG.get(_normalize_tag(raw))
        if mapped and mapped not in found:
            found.append(mapped)
    if not found:
        return {
            "status": "unknown",
            "value": None,
            "tag": None,
            "source": source,
            "note": (
                "Geen male/female/non-binary tag in hero_defines.tags; "
                "niet afleiden uit naam of herinnering."
            ),
        }
    if len(found) > 1:
        return {
            "status": "conflict",
            "value": None,
            "tag": None,
            "values": found,
            "source": source,
            "note": "Meerdere gendertags in defines — niet raden welke geldt.",
        }
    value = found[0]
    return {
        "status": "known",
        "value": value,
        "tag": value,
        "source": source,
    }


def _hero_tags_extra(hero_id: int) -> dict[str, Any]:
    """Species/classes/alignment/affiliations from authoritative defines + tag buckets."""
    out: dict[str, Any] = {
        "species": None,
        "classes": None,
        "alignment": None,
        "affiliations": None,
        "raw_tags": None,
        "gender": None,
        "tag_sources": {},
    }
    try:
        from ic_gamedata.adventure_restrictions import (
            _AFFILIATION_TAGS,
            _NON_STANDARD_RACE_TAGS,
            _STANDARD_RACE_TAGS,
        )
        from ic_gamedata.specialization_data import cached_definitions_data
    except Exception:
        return out

    rows = cached_definitions_data().get("hero_defines")
    if not isinstance(rows, list):
        return out

    race_tags = _STANDARD_RACE_TAGS | _NON_STANDARD_RACE_TAGS
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _parse_int(row.get("id") or row.get("hero_id")) != hero_id:
            continue

        details = row.get("character_sheet_details")
        details = details if isinstance(details, dict) else {}
        tags_raw = row.get("tags") if isinstance(row.get("tags"), list) else None
        if tags_raw is None:
            # Hero row found but tags field missing → unknown.
            out["raw_tags"] = None
            tag_names: list[str] = []
        else:
            tag_names = [str(t).strip() for t in tags_raw if str(t).strip()]
            # [] means known-empty tag list from defines.
            out["raw_tags"] = tag_names

        race = details.get("race") or row.get("race") or row.get("species")
        if race:
            out["species"] = str(race)
            out["tag_sources"]["species"] = "character_sheet_details.race"
        cls = details.get("class") or row.get("class") or row.get("character_class")
        if cls:
            out["classes"] = cls if isinstance(cls, list) else [str(cls)]
            out["tag_sources"]["classes"] = "character_sheet_details.class"
        align_raw = details.get("alignment") or row.get("alignment")
        parsed = _parse_alignment(str(align_raw) if align_raw else None)
        if parsed:
            out["alignment"] = parsed
            out["tag_sources"]["alignment"] = parsed["source"]

        affiliations: list[str] = []
        for tag in tag_names:
            norm = _normalize_tag(tag)
            if norm.startswith("interest_"):
                continue
            if norm in _AFFILIATION_TAGS or norm == "companion":
                affiliations.append(tag)
                continue
            # Keep explicit affiliation-like tags that are not race/class/role/meta.
            if (
                norm in race_tags
                or norm in _ROLE_TAGS
                or norm in _ALIGNMENT_AXIS_TAGS
                or norm in _META_TAGS
            ):
                continue
        # Keep [] when known-empty; never collapse to None (None = unknown source).
        out["affiliations"] = affiliations
        out["tag_sources"]["affiliations"] = "hero_defines.tags ∩ affiliation set"
        out["tag_sources"]["raw_tags"] = "hero_defines.tags"
        gender = gender_from_raw_tags(out["raw_tags"])
        out["gender"] = gender
        out["tag_sources"]["gender"] = gender.get("source") or "hero_defines.tags"
        break
    return out


@lru_cache(maxsize=1)
def _upgrade_row_map() -> dict[int, dict[str, Any]]:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data

        upgrades = cached_definitions_data().get("upgrade_defines")
    except Exception:
        return {}
    if not isinstance(upgrades, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for row in upgrades:
        if not isinstance(row, dict):
            continue
        uid = _parse_int(row.get("id") or row.get("upgrade_id"))
        if uid is not None:
            out[uid] = row
    return out


@lru_cache(maxsize=1)
def _upgrades_by_hero_id() -> dict[int, tuple[dict[str, Any], ...]]:
    by_hero: dict[int, list[dict[str, Any]]] = {}
    for row in _upgrade_row_map().values():
        hid = _parse_int(row.get("hero_id"))
        if hid is None:
            continue
        by_hero.setdefault(hid, []).append(row)
    return {hid: tuple(rows) for hid, rows in by_hero.items()}


@lru_cache(maxsize=1)
def _upgrade_name_by_id() -> dict[int, str]:
    out: dict[int, str] = {}
    for uid, item in _upgrade_row_map().items():
        name = str(item.get("name") or item.get("specialization_name") or "").strip()
        if name:
            out[uid] = name
    return out


@lru_cache(maxsize=1)
def _upgrade_ids_known() -> frozenset[int]:
    return frozenset(_upgrade_row_map())


@lru_cache(maxsize=1)
def _effect_defines_by_id() -> dict[int, dict[str, Any]]:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data

        rows = cached_definitions_data().get("effect_defines")
    except Exception:
        return {}
    if not isinstance(rows, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        eid = _parse_int(row.get("id"))
        if eid is not None:
            out[eid] = row
    return out


def clear_export_definition_caches() -> None:
    """Drop in-memory definition indexes (e.g. after definitions reload)."""
    _upgrade_row_map.cache_clear()
    _upgrades_by_hero_id.cache_clear()
    _upgrade_name_by_id.cache_clear()
    _upgrade_ids_known.cache_clear()
    _effect_defines_by_id.cache_clear()
    _hero_name_by_id.cache_clear()
    _feat_defines_by_id.cache_clear()


def _effect_def_id(raw: Any) -> int | None:
    if isinstance(raw, str):
        match = _EFFECT_DEF_RE.match(raw.strip())
        if match:
            return _parse_int(match.group(1))
    return _parse_int(raw) if not isinstance(raw, str) else None


def _normalize_effect_desc_blob(raw: str) -> str:
    """Normalize game desc blobs (^ / ^^ soft breaks)."""
    extra = raw.strip()
    extra = extra.replace("^^", "\n").replace("^", "\n").strip()
    if extra.startswith(":"):
        extra = extra[1:].strip()
    return extra


def _append_condition_descs(parts: list[str], conditions: Any) -> None:
    """Append game-authored condition ``desc`` blobs (deduped, ^^ → newlines).

    Prefer unconditional rows when present so upgrade-gated variants (nearly
    identical prose) do not double the export. When every row is gated, keep
    each unique desc once.
    """
    if not isinstance(conditions, list):
        return
    uncond: list[str] = []
    gated: list[str] = []
    seen: set[str] = set()
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        extra = _normalize_effect_desc_blob(str(cond.get("desc") or ""))
        if not extra or extra in seen:
            continue
        seen.add(extra)
        if str(cond.get("condition") or "").strip():
            gated.append(extra)
        else:
            uncond.append(extra)
    chosen = uncond if uncond else gated
    parts.extend(chosen)


def _effect_description_text(effect_row: dict[str, Any]) -> str | None:
    """Mechanical prose from effect_defines, including verified conditions.

    IC stores prose in several shapes:
    - ``description`` string
    - ``description.desc``
    - ``description.post.conditions[].desc`` (e.g. Cazrin Books thresholds)
    - ``description.conditions[].desc`` (e.g. Baeloth Morbid Excitement —
      conditional variants without a top-level ``desc``)
    """
    desc = effect_row.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    if not isinstance(desc, dict):
        return None
    parts: list[str] = []
    base = _normalize_effect_desc_blob(str(desc.get("desc") or ""))
    if base:
        parts.append(base)
    # Top-level conditions (not only under post) — ~110 defines use this shape.
    _append_condition_descs(parts, desc.get("conditions"))
    post = desc.get("post")
    if isinstance(post, dict):
        _append_condition_descs(parts, post.get("conditions"))
    text = "\n".join(parts).strip()
    return text or None


def _looks_mechanical(text: str | None) -> bool:
    if not text:
        return False
    return bool(_MECHANICAL_HINT.search(text))


def _synthetic_mechanical_text(
    facts: dict[str, Any],
    upgrade_names: dict[int, str],
) -> str | None:
    """Short mechanical line only when the verified parser supplies semantics."""
    params = facts.get("parameters") or []
    refs = facts.get("referenced_upgrade_ids") or []
    modifier = None
    for param in params:
        if not isinstance(param, dict):
            continue
        if param.get("name") == "modifier" and isinstance(param.get("value"), (int, float)):
            modifier = float(param["value"])
            break
    if modifier is not None and refs:
        names = [upgrade_names.get(int(rid)) or f"upgrade {rid}" for rid in refs]
        if modifier == 0:
            return f"Buffs {' / '.join(names)} (passthrough modifier)."
        return f"Increases {' / '.join(names)} by {modifier:g}%."
    for param in params:
        if not isinstance(param, dict):
            continue
        if param.get("value") is None or not isinstance(param.get("value"), (int, float)):
            continue
        if param.get("status") == "computed_unknown" or param.get("value_basis") == "computed":
            continue
        if param.get("meaning") in {"upgrade_id", "attack_id", "effect_id", "hero_tag"}:
            continue
        key = str(param.get("effect_key") or param.get("source") or param.get("name") or "").casefold()
        name = str(param.get("name") or "").casefold()
        value = float(param["value"])
        if name == "gold_find" or ("gold" in key and "_mult" in key):
            return f"Increases party gold find by {value:g}%."
        if name == "global_damage" or ("global_dps" in key and "_mult" in key):
            return f"Increases all champion damage by {value:g}%."
        if name == "additional_bud_damage" or "base_attack_deal_bonus_damage" in key:
            return f"Deals an additional {value:g} seconds of BUD-based damage."
        if name == "damage" or (
            "hero_dps" in key
            and "_mult" in key
            and (facts.get("effect_scope") == "positional"
                 or (isinstance(facts.get("semantics"), dict)
                     and facts["semantics"].get("scope") == "positional"))
        ):
            targets = facts.get("targets") or []
            if isinstance(facts.get("semantics"), dict):
                rec = facts["semantics"].get("recipients") or {}
                if isinstance(rec, dict) and rec.get("targets"):
                    targets = rec["targets"]
            phrase = ", ".join(str(t) for t in targets) if targets else "positional recipients"
            return f"Increases damage for {phrase} by {value:g}%."
        if name == "owner_damage" or ("hero_dps" in key and "_mult" in key):
            # hero_dps is owner-scoped unless explicit positional targets say otherwise.
            owner = None
            if isinstance(facts.get("semantics"), dict):
                owner = facts["semantics"].get("owner_ref") or facts["semantics"].get(
                    "owner"
                )
            who = f"{owner}'s" if owner else "this champion's"
            return f"Increases {who} damage by {value:g}%."
        if name == "health" or ("health" in key and ("_add" in key or "_mult" in key)):
            return f"Increases health by {value:g}%."
        if name == "healing" or ("healing" in key and "_mult" in key):
            return f"Increases healing received by {value:g}%."
        if name == "crit_chance" or "crit_chance" in key or "critchance" in key:
            return f"Increases critical hit chance by {value:g}%."
        if name == "crit_damage" or "crit_damage" in key or "critdamage" in key:
            return f"Increases critical damage by {value:g}%."
    attack = next(
        (
            p.get("value")
            for p in params
            if isinstance(p, dict) and p.get("meaning") == "attack_id"
        ),
        None,
    )
    if attack is not None:
        return f"Sets attack id to {attack}."
    hit_ids = [
        p.get("value")
        for p in params
        if isinstance(p, dict) and p.get("name") == "hit_effect_id"
    ]
    if hit_ids:
        return f"Adds monster hit effect(s): {', '.join(str(x) for x in hit_ids)}."
    return None


@lru_cache(maxsize=1)
def _hero_name_by_id() -> dict[int, str]:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data

        rows = cached_definitions_data().get("hero_defines")
    except Exception:
        return {}
    if not isinstance(rows, list):
        return {}
    out: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        hid = _parse_int(row.get("id") or row.get("hero_id"))
        name = str(row.get("name") or "").strip()
        if hid is not None and name:
            out[hid] = name
    return out


def _mechanic_fields_from_upgrade(
    row: dict[str, Any],
    *,
    owner_name: str | None = None,
    selected_upgrade_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Separate flavor vs mechanical effect text; classify usability for advice."""
    tip = str(row.get("tip_text") or "").strip() or None
    flavor = str(row.get("specialization_description") or "").strip() or None
    plain = str(row.get("description") or "").strip() or None
    unresolved: list[str] = []
    effect_id = _effect_def_id(row.get("effect"))
    mechanical: str | None = None
    mechanical_source: str | None = None
    effect_row: dict[str, Any] | None = None

    if tip and _looks_mechanical(tip):
        mechanical = tip
        mechanical_source = "upgrade_defines.tip_text"
    elif tip and not flavor:
        mechanical = tip
        mechanical_source = "upgrade_defines.tip_text"

    if effect_id is not None:
        effect_row = _effect_defines_by_id().get(effect_id)
        if effect_row is None:
            unresolved.append(f"effect_def_{effect_id}_missing")
        else:
            effect_desc = _effect_description_text(effect_row)
            effect_flavor = str(effect_row.get("flavour_text") or "").strip() or None
            if effect_flavor and not flavor:
                flavor = effect_flavor
            if effect_desc:
                # Prefer effect_defines mechanical prose over flavor tip.
                if mechanical is None or not _looks_mechanical(mechanical):
                    mechanical = effect_desc
                    mechanical_source = f"effect_defines[{effect_id}].description"
                elif mechanical != effect_desc and _looks_mechanical(effect_desc):
                    # Keep tip if mechanical; expose effect_desc as richer text.
                    mechanical = effect_desc
                    mechanical_source = f"effect_defines[{effect_id}].description"
            else:
                unresolved.append("effect_def_no_description")
            # Compact targeting hints from effect_keys (no invented prose).
            key_notes: list[str] = []
            for key in effect_row.get("effect_keys") or []:
                if not isinstance(key, dict):
                    continue
                es = key.get("effect_string")
                if not isinstance(es, str):
                    continue
                if "adjacent" in es.casefold():
                    key_notes.append("effect_key mentions adjacent")
                filt = (key.get("stack_func_data") or {}).get("target_filters")
                if isinstance(filt, list) and filt:
                    key_notes.append(f"target_filters={filt!s}"[:160])
            if key_notes and mechanical is None:
                unresolved.append("effect_keys_only:" + ";".join(key_notes[:2]))

    if mechanical is None and plain and _looks_mechanical(plain):
        mechanical = plain
        mechanical_source = "upgrade_defines.description"

    from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic

    upgrade_names = _upgrade_name_by_id()
    effect_field = str(row.get("effect") or "")
    if owner_name is None:
        hid = _parse_int(row.get("hero_id"))
        if hid is not None:
            owner_name = _hero_name_by_id().get(hid)
    # Inline effect strings (buff_upgrade,… without effect_def) still need keys.
    refine_row = effect_row if effect_id is not None else None
    if refine_row is None and effect_field and not effect_field.lower().startswith(
        "effect_def"
    ):
        refine_row = {"effect_keys": [{"effect_string": effect_field}]}
    # Prefer mechanical tip; fall back to mechanical-looking specialization_description.
    if mechanical is None and flavor and _looks_mechanical(flavor):
        mechanical = flavor
        mechanical_source = "upgrade_defines.specialization_description"
        flavor = None
    refined = refine_mechanic(
        mechanical,
        refine_row,
        effect_field or None,
        owner_name=owner_name,
        upgrade_name_by_id=upgrade_names,
        upgrade_ids_known=_upgrade_ids_known(),
        selected_upgrade_ids=selected_upgrade_ids,
    )
    if refined.get("text"):
        mechanical = refined["text"]
    for token in refined.get("unresolved_placeholders") or []:
        unresolved.append(f"unresolved_placeholder:{token}")
    quality = refined.get("quality") or {}

    facts = refined.get("effect_facts") or {}
    parsed_params = facts.get("parameters") or []
    has_parsed_mechanic = bool(
        facts.get("referenced_upgrade_ids")
        or any(
            isinstance(p, dict)
            and p.get("meaning")
            in {"percent", "upgrade_id", "attack_id", "effect_id", "hero_tag"}
            for p in parsed_params
        )
    )
    if mechanical is None and has_parsed_mechanic:
        mechanical = _synthetic_mechanical_text(facts, upgrade_names)
        if mechanical:
            mechanical_source = mechanical_source or "parsed_effect_parameters"

    # Attack-id / hit-effect wiring alone is not usable advice prose. Prefer the
    # game-authored specialization_description when that is all we have.
    if isinstance(mechanical, str) and (
        mechanical.casefold().startswith("sets attack id to")
        or mechanical.casefold().startswith("adds monster hit effect")
    ):
        fallback = flavor or plain
        if isinstance(fallback, str) and fallback.strip():
            mechanical = fallback.strip()
            mechanical_source = (
                "upgrade_defines.specialization_description"
                if fallback == flavor
                else "upgrade_defines.description"
            )
            if fallback == flavor:
                flavor = None
            unresolved.append("attack_id_wiring_supplemented_by_source_prose")
        else:
            # Keep synthetic line for parsers; projection may still strip it.
            unresolved.append("attack_id_wiring_only")

    if mechanical and quality.get("usable_for_numeric_comparison") is True:
        usability = "mechanical_usable"
    elif mechanical and quality.get("usable_for_placement") is True:
        # Targeting can be known while the percent is still unknown.
        usability = "partially_resolved"
    elif mechanical and _looks_mechanical(mechanical):
        usability = "partially_resolved" if unresolved else "description_present"
    elif mechanical:
        usability = "description_present"
    elif has_parsed_mechanic:
        usability = "partially_resolved"
        unresolved.append("parsed_effect_without_prose")
    elif flavor and not _looks_mechanical(flavor):
        usability = "flavor_only"
        unresolved.append("flavor_only_no_mechanical_effect")
    elif row.get("effect") or row.get("effects"):
        usability = "effect_unsupported_or_missing_prose"
        unresolved.append("effect_only_no_prose")
    else:
        usability = "missing"

    # Never promote flavor into mechanical_text.
    if mechanical and flavor and mechanical.strip() == flavor.strip():
        if not _looks_mechanical(mechanical) and not has_parsed_mechanic:
            mechanical = None
            usability = "flavor_only"

    primary = mechanical or tip or flavor or plain
    text_complete = bool(mechanical) and not any(
        str(item).startswith("unresolved_placeholder") for item in unresolved
    )

    return {
        "text": mechanical or primary,
        "mechanical_text": mechanical,
        "flavor_text": flavor if flavor and flavor != mechanical else None,
        "text_complete": text_complete,
        "usability": usability,
        "mechanical_usable": usability == "mechanical_usable",
        "effect_id": effect_id,
        "mechanical_source": mechanical_source,
        "unresolved_fields": unresolved or None,
        "quality": quality or None,
        "effect_facts": refined.get("effect_facts"),
        "placeholder_substitutions": refined.get("placeholder_substitutions"),
    }


def _ability_text_from_row(row: dict[str, Any]) -> tuple[str | None, bool, list[str]]:
    """Backward-compatible wrapper around mechanic field resolution."""
    fields = _mechanic_fields_from_upgrade(row)
    return (
        fields.get("text"),
        bool(fields.get("text_complete")),
        list(fields.get("unresolved_fields") or []),
    )


def _is_internal_ability(row: dict[str, Any]) -> bool:
    name = str(row.get("name") or row.get("specialization_name") or "").strip()
    level = _parse_int(row.get("required_level"))
    if level is not None and level >= 9999:
        return True
    if name and _INTERNAL_ABILITY_NAME.match(name):
        return True
    if not name and not str(row.get("tip_text") or "").strip():
        # Nameless, tip-less upgrades are noise for AI advice.
        if not str(row.get("specialization_description") or "").strip():
            return True
    return False


def _ability_texts(
    hero_id: int,
    *,
    selected_upgrade_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    abilities: list[dict[str, Any]] = []
    for row in _upgrades_by_hero_id().get(hero_id, ()):
        if row.get("specialization_name"):
            # Spec options are exported under specialization_groups.
            continue
        if _is_internal_ability(row):
            continue
        upgrade_id = _parse_int(row.get("id") or row.get("upgrade_id"))
        name = str(row.get("name") or "").strip()
        fields = _mechanic_fields_from_upgrade(
            row, selected_upgrade_ids=selected_upgrade_ids
        )
        if not name and not fields.get("text"):
            continue
        # Skip pure noise without any usable signal.
        if fields.get("usability") == "missing" and not name:
            continue
        abilities.append(
            {
                "ability_id": upgrade_id,
                "name": name or None,
                "text": fields.get("text"),
                "mechanical_text": fields.get("mechanical_text"),
                "flavor_text": fields.get("flavor_text"),
                "text_complete": fields.get("text_complete"),
                "usability": fields.get("usability"),
                "mechanical_usable": fields.get("mechanical_usable"),
                "effect_id": fields.get("effect_id"),
                "mechanical_source": fields.get("mechanical_source"),
                "unresolved_fields": fields.get("unresolved_fields"),
                "quality": fields.get("quality"),
                "effect_facts": fields.get("effect_facts"),
                "placeholder_substitutions": fields.get("placeholder_substitutions"),
                "required_level": _parse_int(row.get("required_level")),
                "source": "upgrade_defines",
                "active_state": "kit",
                "simultaneously_active": True,
            }
        )
    return _expand_ability_dependencies(hero_id, abilities)


def _expand_ability_dependencies(
    hero_id: int,
    abilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pull upgrades referenced by kit effects. Specs stay choices, not kit."""
    from ic_gamedata.formation_ai_advice.mechanics import referenced_upgrade_ids

    upgrades = _upgrade_row_map()
    effects = _effect_defines_by_id()
    seen = {
        int(item["ability_id"])
        for item in abilities
        if isinstance(item.get("ability_id"), int)
    }
    queue: list[tuple[int, int]] = []
    for row in _upgrades_by_hero_id().get(hero_id, ()):
        parent = _parse_int(row.get("id") or row.get("upgrade_id"))
        if parent is None:
            continue
        effect_id = _effect_def_id(row.get("effect"))
        effect_row = effects.get(effect_id) if effect_id is not None else None
        for ref in referenced_upgrade_ids(str(row.get("effect") or ""), effect_row):
            queue.append((ref, parent))
    for item in abilities:
        parent = item.get("ability_id")
        facts = item.get("effect_facts") or {}
        for ref in facts.get("referenced_upgrade_ids") or []:
            if isinstance(ref, int) and isinstance(parent, int):
                queue.append((ref, parent))
    while queue:
        ref, parent = queue.pop(0)
        if ref in seen:
            continue
        seen.add(ref)
        row = upgrades.get(ref)
        if row is None:
            abilities.append(
                {
                    "ability_id": ref,
                    "name": None,
                    "text": None,
                    "mechanical_text": None,
                    "usability": "missing",
                    "mechanical_usable": False,
                    "active_state": "missing_dependency",
                    "simultaneously_active": False,
                    "included_because": f"referenced_by:{parent}",
                    "quality": {
                        "dependencies_resolved": False,
                        "usable_for_placement": "unknown",
                        "usable_for_numeric_comparison": False,
                    },
                }
            )
            continue
        if _parse_int(row.get("hero_id")) not in (None, hero_id):
            continue
        is_spec = bool(row.get("specialization_name"))
        fields = _mechanic_fields_from_upgrade(row)
        name = str(row.get("name") or row.get("specialization_name") or "").strip() or None
        entry = {
            "ability_id": ref,
            "name": name,
            "text": fields.get("text"),
            "mechanical_text": fields.get("mechanical_text"),
            "flavor_text": fields.get("flavor_text"),
            "text_complete": fields.get("text_complete"),
            "usability": fields.get("usability"),
            "mechanical_usable": fields.get("mechanical_usable"),
            "effect_id": fields.get("effect_id"),
            "mechanical_source": fields.get("mechanical_source"),
            "unresolved_fields": fields.get("unresolved_fields"),
            "quality": fields.get("quality"),
            "effect_facts": fields.get("effect_facts"),
            "required_level": _parse_int(row.get("required_level")),
            "source": "upgrade_defines",
            "active_state": "only_when_selected" if is_spec else "referenced_dependency",
            "simultaneously_active": False if is_spec else True,
            "included_because": f"referenced_by:{parent}",
        }
        abilities.append(entry)
        facts = fields.get("effect_facts") or {}
        for child in facts.get("referenced_upgrade_ids") or []:
            if isinstance(child, int) and child not in seen:
                queue.append((child, ref))
        # Also catch ids that quality saw on the raw effect field.
        for child in referenced_upgrade_ids(str(row.get("effect") or ""), None):
            if child not in seen:
                queue.append((child, ref))
    return abilities


def _specialization_groups(
    payload: dict[str, Any],
    hero_id: int,
) -> list[dict[str, Any]]:
    try:
        from ic_gamedata.specializations import (
            _merge_known_options,
            _current_choices,
            load_specialization_rules,
            merged_hero_record_for_specializations,
        )
    except Exception:
        return []

    from ic_gamedata.formation_ai_advice.mechanics import selection_status

    rules = load_specialization_rules()
    known = _merge_known_options(payload, rules).get(hero_id, [])
    if not known:
        return []
    hero = merged_hero_record_for_specializations(payload, hero_id) or {}
    selected = set(_current_choices(hero, known))
    choices_observed = isinstance(hero.get("specialization_choices"), list) or isinstance(
        hero.get("upgrades"), list
    )
    hero_level = _parse_int(hero.get("level"))
    by_tier: dict[int, list] = {}
    for opt in known:
        by_tier.setdefault(opt.tier_index, []).append(opt)
    from ic_gamedata.formation_ai_advice.labels import specialization_group_label

    upgrades = _upgrade_row_map()
    groups: list[dict[str, Any]] = []
    for tier in sorted(by_tier):
        options = []
        for opt in sorted(by_tier[tier], key=lambda o: o.upgrade_id):
            row = upgrades.get(opt.upgrade_id) or {}
            fields = _mechanic_fields_from_upgrade(row)
            req = _parse_int(row.get("required_upgrade_id"))
            if req is None or req <= 0:
                req = None
            if req is None:
                available: bool | str = True
            elif not choices_observed:
                available = "unknown"
            else:
                available = req in selected
            options.append(
                {
                    "option_id": opt.upgrade_id,
                    "name": opt.name,
                    "text": fields.get("text"),
                    "mechanical_text": fields.get("mechanical_text"),
                    "flavor_text": fields.get("flavor_text"),
                    "text_complete": fields.get("text_complete"),
                    "usability": fields.get("usability"),
                    "mechanical_usable": fields.get("mechanical_usable"),
                    "effect_id": fields.get("effect_id"),
                    "mechanical_source": fields.get("mechanical_source"),
                    "unresolved_fields": fields.get("unresolved_fields"),
                    "quality": fields.get("quality"),
                    "effect_facts": fields.get("effect_facts"),
                    "placeholder_substitutions": fields.get(
                        "placeholder_substitutions"
                    ),
                    "required_level": opt.required_level,
                    "selected": opt.upgrade_id in selected,
                    "simultaneously_active": False,
                    "owner_champion_id": hero_id,
                    "required_upgrade_id": req,
                    "requires_selected_option_id": req,
                    "available_in_current_state": available,
                }
            )
        levels = [opt.required_level for opt in by_tier[tier] if opt.required_level]
        min_level = min(levels) if levels else None
        chosen = [opt["option_id"] for opt in options if opt["selected"]]
        chosen_id = chosen[0] if len(chosen) == 1 else None
        for opt in options:
            opt["simultaneously_active"] = bool(
                chosen_id is not None and opt["option_id"] == chosen_id
            )
        choice_order = tier + 1
        group_id = f"tier_{tier}"
        groups.append(
            {
                "group_id": group_id,
                "tier_index": tier,
                "choice_order": choice_order,
                "group_label": specialization_group_label(
                    group_id=group_id,
                    tier_index=tier,
                    required_level=min_level,
                    choice_order=choice_order,
                ),
                # Mutual exclusion lives on the group, not as N×(N-1) option lists.
                "selection_mode": "exactly_one",
                "selection_status": (
                    "unknown"
                    if len(chosen) > 1
                    else selection_status(
                        choices_observed=choices_observed,
                        selected_option_id=chosen_id,
                        required_level=min_level,
                        hero_level=hero_level,
                    )
                ),
                "selected_option_id": chosen_id,
                "options": options,
            }
        )
    return groups


@lru_cache(maxsize=1)
def _feat_defines_by_id() -> dict[int, dict[str, Any]]:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
    except Exception:
        return {}
    rows = data.get("hero_feat_defines")
    if not isinstance(rows, list):
        rows = data.get("feat_defines")
    if not isinstance(rows, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = _parse_int(row.get("id"))
        if fid is not None:
            out[fid] = row
    return out


def _feat_effect_row(raw_effects: Any) -> dict[str, Any] | None:
    """Feats store effect_keys inline under ``effects`` (not effect_def)."""
    if not isinstance(raw_effects, list) or not raw_effects:
        return None
    keys = [item for item in raw_effects if isinstance(item, dict)]
    if not keys:
        return None
    return {"effect_keys": keys}


def _feat_mechanical_parts(raw_effects: Any) -> tuple[str | None, bool]:
    """Join non-empty effect descriptions; flag if already embedded in other values."""
    if not isinstance(raw_effects, list):
        return None, False
    parts: list[str] = []
    for item in raw_effects:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description") or "").strip()
        if desc:
            parts.append(desc)
    return (" ".join(parts) if parts else None), False


def _feat_info(payload: dict[str, Any], hero_id: int) -> dict[str, Any]:
    from ic_gamedata.formation_ai_advice.mechanics import (
        refine_mechanic,
        trait_changes_from_keys,
    )

    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    defines = _feat_defines_by_id()
    upgrade_names = _upgrade_name_by_id()
    known_ids = _upgrade_ids_known()
    owner = _hero_name_by_id().get(hero_id)
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        if _parse_int(hero.get("hero_id")) != hero_id:
            continue
        active_ids = [_parse_int(x) for x in (hero.get("active_feats") or [])]
        active_ids = [x for x in active_ids if x is not None]
        active_feats: list[dict[str, Any]] = []
        for fid in active_ids:
            row = defines.get(fid) or {}
            flavor = str(row.get("description") or "").strip() or None
            effect_row = _feat_effect_row(row.get("effects"))
            # Only effect-key descriptions are mechanical; feat.description is flavor.
            mech_text, _ = _feat_mechanical_parts(row.get("effects"))
            primary = mech_text
            effect_field = None
            for key in (effect_row or {}).get("effect_keys") or []:
                if isinstance(key, dict) and isinstance(key.get("effect_string"), str):
                    effect_field = key["effect_string"]
                    break
            refined = refine_mechanic(
                primary,
                effect_row,
                effect_field,
                owner_name=owner,
                upgrade_ids_known=known_ids,
                upgrade_name_by_id=upgrade_names,
            )
            keys = (effect_row or {}).get("effect_keys") or []
            trait_changes = trait_changes_from_keys(
                [k for k in keys if isinstance(k, dict)]
            )
            facts = refined.get("effect_facts") or {}
            if isinstance(facts, dict):
                facts = {
                    k: v
                    for k, v in facts.items()
                    if k not in {"effect_strings"}
                    or refined.get("quality", {}).get("usable_for_placement")
                }
            has_parsed = bool(
                (facts or {}).get("referenced_upgrade_ids")
                or (facts or {}).get("parameters")
                or trait_changes
            )
            mech = refined.get("text") or primary
            if has_parsed:
                synthetic = _synthetic_mechanical_text(facts or {}, upgrade_names)
                if mech is None:
                    mech = synthetic
                elif flavor and mech.strip() == flavor.strip():
                    mech = synthetic
            elif flavor and mech and mech.strip() == flavor.strip():
                mech = None
            if refined.get("quality", {}).get("usable_for_numeric_comparison") is True and mech:
                usability = "mechanical_usable"
            elif mech or has_parsed:
                usability = "partially_resolved"
            elif flavor:
                usability = "flavor_only"
            else:
                usability = "missing"
            active_feats.append(
                {
                    "feat_id": fid,
                    "name": str(row.get("name") or "").strip() or None,
                    "mechanical_text": mech,
                    "flavor_text": None,  # never for advice; debug keeps raw defines
                    "usability": usability,
                    "quality": refined.get("quality"),
                    "effect_facts": facts or refined.get("effect_facts"),
                    "placeholder_substitutions": refined.get("placeholder_substitutions"),
                    "trait_changes": trait_changes or None,
                    "already_applied_in_export": {
                        "tags": any(
                            c.get("trait") == "tag" and c.get("mode") == "add"
                            for c in trait_changes
                        ),
                        "roles": any(
                            c.get("trait") == "role" and c.get("mode") == "add"
                            for c in trait_changes
                        ),
                    },
                }
            )
        return {
            "active_feats": active_feats,
            "active_feat_ids": active_ids,
            "note": (
                "Alleen actieve feats; niet-actieve feats worden niet geëxporteerd "
                "omdat feats niet mogen wijzigen in dit advies."
            ),
        }
    return {
        "active_feats": None,
        "active_feat_ids": None,
        "note": "unknown",
    }


def _restriction_block(
    payload: dict[str, Any],
    *,
    manual_restriction_text: str | None,
    adventure_id: int | None,
    selected_hero_ids: list[int] | None = None,
) -> dict[str, Any]:
    instance = _active_instance(payload) or {}
    if adventure_id is None:
        adventure_id = _parse_int(instance.get("current_adventure_id"))
    patron_id = _parse_int(instance.get("current_patron_id") or instance.get("patron_id"))
    area = _parse_int(instance.get("current_area") or instance.get("area"))
    adventure_name = None
    variant_id = _parse_int(instance.get("current_variant_id") or instance.get("variant_id"))
    variant_name = None
    patron_name = None
    structured: dict[str, Any] | None = None
    checked = False
    has_unknown = False
    restriction_text = None
    raw_restrictions_text = None
    local_evidence: list[str] = []
    party_checks: list[dict[str, Any]] = []
    filt = None

    try:
        from ic_gamedata.adventure_restrictions import (
            _adventure_define,
            _parse_restrictions_text,
            build_adventure_roster_filter,
            evaluate_heroes_against_filter,
            restriction_summary,
            structured_stat_gates,
        )

        adv = _adventure_define(payload, adventure_id)
        if isinstance(adv, dict):
            adventure_name = str(adv.get("name") or "") or None
            raw = adv.get("restrictions_text")
            if isinstance(raw, str) and raw.strip():
                raw_restrictions_text = raw.strip()
        filt = build_adventure_roster_filter(payload, adventure_id)
        checked = True
        has_unknown = bool(filt.has_unknown_rules)
        restriction_text = restriction_summary(filt)
        gates = structured_stat_gates(filt)
        hard_gates = [
            g
            for g in (gates or [])
            if isinstance(g, dict) and g.get("source") == "by_stat_or_text"
        ]
        raw_texts = list(getattr(filt, "raw_restriction_texts", None) or [])
        if raw_restrictions_text and raw_restrictions_text not in raw_texts:
            raw_texts.insert(0, raw_restrictions_text)
        elif raw_texts and not raw_restrictions_text:
            raw_restrictions_text = " | ".join(raw_texts)

        structured = {
            "required_tags": sorted(filt.required_tags) or None,
            "banned_tags": sorted(filt.banned_tags) or None,
            "min_stats": [
                g
                for g in hard_gates
                if g.get("operator") in (">=", ">")
            ]
            or None,
            "max_stats": [
                g
                for g in hard_gates
                if g.get("operator") in ("<=", "<")
            ]
            or None,
            "stat_gates": gates or None,
            "allow_exprs": list(filt.allow_exprs) or None,
            "deny_exprs": list(filt.deny_exprs) or None,
            "expr_interpretations": list(filt.expr_interpretations) or None,
            "has_restriction_semantics_conflict": (
                filt.has_restriction_semantics_conflict or None
            ),
            "banned_hero_ids": sorted(filt.banned_hero_ids) or None,
            "patron_blocked_hero_ids": sorted(filt.patron_blocked_hero_ids) or None,
            "ilvl_seat_rule": (
                {
                    "comparison": filt.ilvl_seat_comparison,
                    "meaning": (
                        "Per permanente F-seat (1–12) alleen owned champions "
                        "met de laagste gemiddelde item level "
                        "(avg enchant+1 over equipment loot slots)."
                        if filt.ilvl_seat_comparison == "least"
                        else "Per permanente F-seat alleen owned champions "
                        "met de hoogste gemiddelde item level."
                    ),
                    "allowed_champion_ids": (
                        sorted(filt.ilvl_allowed_hero_ids)
                        if filt.ilvl_allowed_hero_ids is not None
                        else None
                    ),
                    "allowed_count": (
                        len(filt.ilvl_allowed_hero_ids)
                        if filt.ilvl_allowed_hero_ids is not None
                        else None
                    ),
                }
                if filt.ilvl_seat_comparison
                else None
            ),
            "time_available_rule": (
                dict(filt.time_available_rule)
                if getattr(filt, "time_available_rule", None)
                else None
            ),
            "active_notes": list(filt.active_notes) or None,
            "has_unknown_rules": filt.has_unknown_rules,
            "uses_api_game_changes": filt.uses_api_game_changes,
            "raw_restrictions_text": raw_restrictions_text,
            "raw_restriction_texts": raw_texts or None,
            "checked_means": (
                "Filter is opgebouwd en party is geëvalueerd tegen harde "
                "ability-score gates (min én max), allow/deny exprs, "
                "patron-tags en eventuele by_i_levels seat-regel; "
                "'checked' ≠ bewezen toelating bij unknown."
            ),
        }
        if selected_hero_ids:
            party_checks = evaluate_heroes_against_filter(selected_hero_ids, filt)
        if filt.has_roster_rules():
            local_evidence.append(
                "Restrictieregels komen uit active adventure game_changes / patron "
                f"(adventure_id={adventure_id})."
            )
    except Exception:
        checked = False
        restriction_text = None

    if manual_restriction_text and manual_restriction_text.strip():
        restriction_text = manual_restriction_text.strip()
        local_evidence.append("Restrictietekst handmatig aangevuld door gebruiker.")
        try:
            from ic_gamedata.adventure_restrictions import (
                _parse_restrictions_text,
                structured_stat_gates,
            )

            manual_filt = _parse_restrictions_text(manual_restriction_text)
            if structured is None:
                structured = {}
            # Merge soft structured fields from manual text without inventing certainty.
            manual_gates = structured_stat_gates(manual_filt)
            if manual_gates:
                existing = list(structured.get("stat_gates") or [])
                structured["stat_gates"] = existing + manual_gates
                structured["manual_text_parsed"] = True
                structured["manual_text_note"] = (
                    "Handmatige tekst is geparsed; scope/bron blijft onzeker "
                    "tenzij ook in API-rules aanwezig."
                )
                has_unknown = True
        except Exception:
            has_unknown = True

    if patron_id:
        try:
            from ic_gamedata.patron_roster import PATRON_NAMES

            patron_name = PATRON_NAMES.get(patron_id)
        except Exception:
            patron_name = None

    from ic_gamedata.formation_ai_advice.mechanics import merge_restriction_sources

    denied = [r for r in party_checks if r.get("status") == "denied"]
    unknown = [r for r in party_checks if r.get("status") == "unknown"]
    party_status = "ok"
    if not checked:
        party_status = "unchecked"
    elif denied:
        party_status = "conflict"
    elif unknown or has_unknown:
        party_status = "unconfirmed"
    elif party_checks and all(r.get("status") == "allowed" for r in party_checks):
        party_status = "ok"
    elif not party_checks:
        party_status = "unchecked"

    api_has_rules = bool(filt is not None and filt.has_roster_rules())
    party_status = merge_restriction_sources(
        party_status,
        api_has_rules=api_has_rules,
        manual_text=manual_restriction_text,
    )

    fully_known = bool(
        checked
        and not has_unknown
        and party_status == "ok"
        and (
            bool(restriction_text)
            or bool(
                structured
                and (
                    structured.get("required_tags")
                    or structured.get("banned_tags")
                    or structured.get("min_stats")
                    or structured.get("max_stats")
                    or structured.get("stat_gates")
                    or structured.get("allow_exprs")
                    or structured.get("banned_hero_ids")
                )
            )
            or (
                checked
                and filt is not None
                and not getattr(filt, "has_roster_rules", lambda: True)()
            )
        )
    )

    campaign_id = None
    campaign_name = None
    try:
        from ic_gamedata.specializations import _active_adventure_details

        _adv, campaign_id, _loc = _active_adventure_details(payload)
        if campaign_id is not None:
            from ic_gamedata.specializations import _definition_name

            campaign_name = _definition_name(payload, "campaign_defines", campaign_id)
    except Exception:
        campaign_id = None
        campaign_name = None

    return {
        "adventure_id": adventure_id,
        "adventure_name": adventure_name,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "variant_id": variant_id,
        "variant_name": variant_name,
        "patron_id": patron_id,
        "patron_name": patron_name,
        "tier": _parse_int(instance.get("difficulty_id") or instance.get("tier")),
        "target_area": area,
        "restriction_text": restriction_text,
        "structured_restrictions": structured,
        "party_restriction_checks": party_checks or None,
        "party_restriction_status": party_status,
        "source_priority": (
            "API game_changes/patron filter is leading for base eligibility. "
            "Kit overrides: unconditional_adventure_eligibility (e.g. Dark Inheritance) "
            "allows when present; campaign_scoped_eligibility allows only when the "
            "active campaign matches; force_allow_hero_by_tag allows only when the "
            "required tag is verified. Manual restriction text on top of API rules "
            "is a conflict, not a replacement."
        ),
        "restrictions_checked_by_app": checked,
        "restrictions_fully_known": fully_known,
        "local_evidence": local_evidence or None,
        "stats_basis_note": (
            "ability_scores komen uit character_sheet_details (basisstats uit defines); "
            "geen dubbele featbonussen toegepast in deze check."
        ),
        "note": (
            None
            if checked
            else "Restricties niet lokaal opgelost — behandel ontbrekende restricties "
            "niet als 'geen restrictie'."
        ),
    }


def _geometry_issues(
    positions: list[int],
    adjacency: dict[int, list[int]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    known = set(positions)
    for seat, neighbors in adjacency.items():
        if seat not in known:
            issues.append(
                {
                    "code": "adjacency_unknown_position",
                    "severity": "error",
                    "position_ids": [seat],
                    "message": f"Adjacency verwijst naar onbekende positie {seat}.",
                    "fix": "Exporteer opnieuw of herstel formatiegeometrie.",
                }
            )
            continue
        seen: set[int] = set()
        for other in neighbors:
            if other == seat:
                issues.append(
                    {
                        "code": "adjacency_self_loop",
                        "severity": "error",
                        "position_ids": [seat],
                        "message": f"Self-loop op positie {seat}.",
                        "fix": "Geometriebron controleren.",
                    }
                )
            if other in seen:
                issues.append(
                    {
                        "code": "adjacency_duplicate_neighbor",
                        "severity": "warning",
                        "position_ids": [seat, other],
                        "message": f"Dubbele buur {other} bij positie {seat}.",
                        "fix": "Duplicaten worden genegeerd bij hop-telling.",
                    }
                )
            seen.add(other)
            if other not in known:
                issues.append(
                    {
                        "code": "adjacency_edge_to_unknown",
                        "severity": "error",
                        "position_ids": [seat, other],
                        "message": f"Rand {seat}→{other} wijst buiten actieve formatie.",
                        "fix": "Phantom-posities verwijderen uit export.",
                    }
                )
            elif seat not in adjacency.get(other, []):
                issues.append(
                    {
                        "code": "adjacency_not_symmetric",
                        "severity": "error",
                        "position_ids": [seat, other],
                        "message": f"Niet-wederzijdse adjacency {seat}→{other}.",
                        "fix": "Geometriebron herstellen; niet blind samenvoegen.",
                    }
                )
    return issues


def _formation_block(
    payload: dict[str, Any],
    ctx: FormationLayoutContext,
    *,
    adventure_id: int | None,
) -> dict[str, Any]:
    from ic_gamedata.adventure_restrictions import (
        _layout_formation_seat_count,
        player_formation_capacity,
        reserved_formation_seats,
    )
    from ic_gamedata.formation_advisor.topology import fallback_seat_column
    from ic_gamedata.formation_ai_advice.labels import (
        assign_display_positions,
        position_caption,
        position_display_convention_block,
        sort_positions_for_display,
    )

    topo = ctx.topology
    layout_seats = _layout_formation_seat_count(payload)
    capacity = ctx.formation_capacity
    if capacity is None:
        capacity = player_formation_capacity(payload, adventure_id)
    reserved = sorted(reserved_formation_seats(payload, adventure_id))

    # Prefer topology seats that belong to the live/API graph (no 1–12 pad).
    topo_seats = sorted(set(topo.seat_column) | set(topo.seat_adjacency))
    occupied = sorted(set(ctx.seat_by_hero.values()))
    if layout_seats and topo_seats:
        # Keep graph seats; if topology still over-includes, clip to layout size
        # only when seats are the contiguous 1..N legacy mapping.
        if len(topo_seats) > layout_seats and topo_seats == list(range(1, len(topo_seats) + 1)):
            positions = list(range(1, layout_seats + 1))
        else:
            positions = topo_seats
    elif layout_seats:
        positions = list(range(1, layout_seats + 1))
    elif topo_seats:
        positions = topo_seats
    else:
        positions = occupied

    # Always include currently occupied seats so selected party remains placeable.
    for seat in occupied:
        if seat not in positions:
            positions.append(seat)
    positions = sorted(set(positions))

    adjacency: dict[int, list[int]] = {}
    for seat in positions:
        raw = [n for n in sorted(ctx.adjacent_seats(seat)) if n in positions and n != seat]
        # Deduplicate while preserving order
        seen: set[int] = set()
        clean: list[int] = []
        for n in raw:
            if n not in seen:
                seen.add(n)
                clean.append(n)
        adjacency[seat] = clean

    # Symmetrize within the exported active set (physical neighbors).
    for seat, neighbors in list(adjacency.items()):
        for other in neighbors:
            if seat not in adjacency.get(other, []):
                adjacency.setdefault(other, []).append(seat)
                adjacency[other] = sorted(set(adjacency[other]))

    geo_issues = _geometry_issues(positions, adjacency)

    positions_detail: list[dict[str, Any]] = []
    column_by_position: dict[str, dict[str, Any]] = {}
    current: dict[str, int | None] = {}
    hero_at = {seat: hid for hid, seat in ctx.seat_by_hero.items()}

    # Vertical order within column: graph y (top = smaller y), else seat id.
    seat_y: dict[int, float] = {}
    try:
        from ic_gamedata.seat_advisor.formation_visual import load_formation_graph

        _name, graph_nodes = load_formation_graph(payload, adventure_id)
        # Rebuild index→seat like topology bridge (occupied UI seats + free ids).
        from ic_gamedata.formation_advisor.topology import (
            _bridge_seat_layout,
            _formation_grid_hero_ids,
            _seat_by_hero,
            _active_instance,
        )

        inst = _active_instance(payload) or {}
        fid = _formation_grid_hero_ids(inst, payload)
        sbh = _seat_by_hero(inst)
        if graph_nodes:
            bridged_col, _bridged_adj = _bridge_seat_layout(graph_nodes, fid, sbh)
            # Prefer y from the node that maps to each seat.
            index_to_seat: dict[int, int] = {}
            used = set()
            for index, hero_id in enumerate(fid):
                if index >= len(graph_nodes) or hero_id <= 0:
                    continue
                seat = sbh.get(hero_id)
                if seat is not None and seat not in used:
                    index_to_seat[index] = seat
                    used.add(seat)
            for index in range(len(graph_nodes)):
                if index in index_to_seat:
                    continue
                preferred = index + 1
                seat = (
                    preferred
                    if preferred not in used and 1 <= preferred <= 12
                    else next((s for s in range(1, 13) if s not in used), None)
                )
                if seat is None:
                    continue
                index_to_seat[index] = seat
                used.add(seat)
            for index, node in enumerate(graph_nodes):
                seat = index_to_seat.get(index)
                if seat is None:
                    continue
                y_raw = node.get("y")
                try:
                    seat_y[seat] = float(y_raw) if y_raw is not None else float(index)
                except (TypeError, ValueError):
                    seat_y[seat] = float(index)
            _ = bridged_col
    except Exception:
        seat_y = {}

    by_col: dict[int, list[int]] = {}
    for seat in positions:
        col = topo.seat_column.get(seat)
        if col is None:
            col = fallback_seat_column(seat)
        by_col.setdefault(col, []).append(seat)
    row_order: dict[int, int] = {}
    for col, seats in by_col.items():
        ordered = sorted(
            seats,
            key=lambda s: (seat_y.get(s, float(s)), s),
        )
        for idx, seat in enumerate(ordered):
            row_order[seat] = idx

    active_ids: list[int] = []
    blocked_ids: list[int] = []
    for seat in positions:
        col = topo.seat_column.get(seat)
        if col is None:
            col = fallback_seat_column(seat)
        zone = topo.seat_zone.get(seat, "mid")
        hid = hero_at.get(seat)
        if seat in reserved:
            state = "blocked"
            blocked_ids.append(seat)
        else:
            state = "active"
            active_ids.append(seat)
        positions_detail.append(
            {
                "position_id": seat,
                "column_index": col,
                "row_order": row_order.get(seat, 0),
                "zone": zone,
                "state": state,
                "current_champion_id": hid,
                "adjacent_position_ids": adjacency.get(seat, []),
                "label": position_caption(
                    position_id=seat,
                    column=int(col) if isinstance(col, int) else None,
                    zone=str(zone) if zone else None,
                    row_order=row_order.get(seat, 0),
                ),
            }
        )
        column_by_position[str(seat)] = {
            "column": col,
            "zone": zone,
            "visual_order_note": "lower column_index = closer to front (enemies)",
        }
        current[str(seat)] = hid

    physical_count = layout_seats if layout_seats is not None else len(positions)
    from ic_gamedata.formation_ai_advice.geometry import assess_active_graph

    graph_report = assess_active_graph(
        active_ids,
        blocked_ids,
        adjacency,
        authoritative=topo.source != "heuristic",
    )
    geo_issues = list(geo_issues) + list(graph_report["issues"])

    front_direction = {
        "rule": "lower_column_is_front",
        "ui_note": "Enemies → right (front = toward the right / lower column_index).",
        "source": topo.source,
        "row_direction": "lower_row_is_top",
        "row_direction_note": (
            "Binnen een kolom: laagste row_order / y = bovenste plek."
        ),
    }
    positions_with_display, display_issues = assign_display_positions(
        positions_detail,
        column_direction=front_direction,
        active_only=True,
    )
    geo_issues = list(geo_issues) + list(display_issues)
    # Re-sort after display fields (stable back→front, top→bottom).
    positions_with_display = sort_positions_for_display(
        positions_with_display,
        column_direction_rule=front_direction["rule"],
    )

    return {
        "formation_id": topo.source,
        "geometry_source": topo.source,
        "physical_position_count": physical_count,
        "active_position_ids": active_ids,
        "blocked_position_ids": blocked_ids,
        "valid_position_ids": active_ids,  # placeable slots only
        # Reading order for tables: back column → front, top → bottom in column.
        "positions": positions_with_display,
        "position_display_convention": position_display_convention_block(
            technical_id_field="position_id"
        ),
        "table_order_note": (
            "Tabelvolgorde: display_position kolom-plek (achter→voor, "
            "boven→beneden), bijv. 1-1, 1-2, 2-1. Technisch id blijft "
            "position_id voor import-JSON."
        ),
        "column_by_position": column_by_position,
        "front_direction": front_direction,
        "adjacency_by_position": {str(k): v for k, v in adjacency.items() if k in active_ids},
        "distance_definition": {
            "type": "graph_hops",
            "paths_through_blocked": "excluded",
            "escorts_count_as_adjacent": "unknown",
            "front_column_is_attacked_slots": "unknown",
            "note": graph_report["distance"]["note"],
        },
        "distance": graph_report["distance"],
        "active_components": graph_report["components"],
        "current_champion_by_position": {
            str(k): current.get(str(k)) for k in active_ids
        },
        "party_size": ctx.party_size,
        "formation_capacity": capacity,
        "max_party_size": capacity,
        "reserved_position_ids": reserved or None,
        "geometry_issues": geo_issues or None,
        "position_vs_seat_note": (
            "position_id is the physical formation place (geometry/adjacency key). "
            "champions[].seat is the permanent F-key seat and follows the champion. "
            "A swap changes which champion occupies a position_id; it does not change "
            "position identity or permanent seat."
        ),
    }


def _ability_score_and_attack_maps() -> tuple[dict[int, Any], dict[int, Any]]:
    try:
        from ic_gamedata.specialization_data import (
            hero_ability_scores_map_from_cached_definitions,
            hero_attack_types_map_from_cached_definitions,
        )

        return (
            hero_ability_scores_map_from_cached_definitions(),
            hero_attack_types_map_from_cached_definitions(),
        )
    except Exception:
        return {}, {}


def build_champion_entry(
    payload: dict[str, Any],
    ctx: FormationLayoutContext,
    hero_id: int,
    *,
    current_position: int | None = None,
    ilvl: int | None = None,
    scores_map: dict[int, Any] | None = None,
    attack_map: dict[int, Any] | None = None,
) -> dict[str, Any]:
    """Build one champion export row (party or owned candidate) with shared mechanics."""
    if scores_map is None or attack_map is None:
        default_scores, default_attacks = _ability_score_and_attack_maps()
        if scores_map is None:
            scores_map = default_scores
        if attack_map is None:
            attack_map = default_attacks

    extra = _hero_tags_extra(hero_id)
    attacks = attack_map.get(hero_id)
    attack_types = sorted(attacks) if attacks else None
    basic_attack = None
    if attack_types:
        for key in ("melee", "ranged", "magic"):
            if any(key in t.casefold() for t in attack_types):
                basic_attack = key
                break
    base_roles = list(ctx.roles(hero_id))
    base_tags = list(ctx.tags(hero_id))
    specs = _specialization_groups(payload, hero_id)
    feats = _feat_info(payload, hero_id)
    selected_ids: set[int] = set()
    for group in specs:
        for opt in group.get("options") or []:
            if (
                isinstance(opt, dict)
                and opt.get("selected")
                and isinstance(opt.get("option_id"), int)
            ):
                selected_ids.add(int(opt["option_id"]))
    abilities = _ability_texts(hero_id, selected_upgrade_ids=selected_ids) or None
    specs = _attach_spec_state_changes(specs)
    effective = _effective_traits_for_champion(
        base_alignment=extra["alignment"]
        if isinstance(extra.get("alignment"), dict)
        else None,
        base_roles=base_roles,
        base_tags=base_tags,
        specialization_groups=specs,
        feats=feats,
    )
    affiliations_status = "unknown" if extra.get("raw_tags") is None else "known"
    gender = extra.get("gender")
    if not isinstance(gender, dict):
        gender = gender_from_raw_tags(
            extra["raw_tags"] if isinstance(extra.get("raw_tags"), list) else None
        )
    position = (
        current_position
        if current_position is not None
        else ctx.seat_of(hero_id)
    )
    return {
        "champion_id": hero_id,
        "name": ctx.name(hero_id),
        "seat": _permanent_seat(hero_id),
        "species": extra["species"],
        "classes": extra["classes"],
        "gender": gender,
        "alignment": effective.get("alignment") or extra["alignment"],
        "base_alignment": extra["alignment"],
        "effective_alignment": effective.get("alignment") or extra["alignment"],
        "affiliations": extra["affiliations"],
        "affiliations_status": affiliations_status,
        "affiliations_note": (
            "Affiliaties onbekend — niet interpreteren als Unaffiliated."
            if affiliations_status == "unknown"
            else None
        ),
        "roles": effective.get("roles") or base_roles,
        "base_roles": base_roles,
        "effective_roles": effective.get("roles") or base_roles,
        "raw_tags": extra["raw_tags"],
        "tags": effective.get("tags") or base_tags,
        "base_tags": base_tags,
        "effective_tags": effective.get("tags") or base_tags,
        "trait_modifiers_applied": effective.get("applied_changes"),
        "tag_sources": extra.get("tag_sources") or None,
        "basic_attack_type": basic_attack,
        "attack_types": attack_types,
        "ability_scores": scores_map.get(hero_id) or None,
        "current_position": position,
        "abilities": abilities,
        "specialization_groups": specs,
        "feats": feats,
        "item_levels": {
            "value": ilvl,
            "meaning": "average_item_level" if ilvl is not None else None,
            "note": (
                "Gemiddeld itemniveau; geen damage-multipliers afleiden."
                if ilvl is not None
                else "Itemniveau onbekend."
            ),
        },
        "equipment": None,
        "equipment_status": "unknown",
        "data_source": "app_export+cached_definitions",
        "data_as_of": _data_version(payload),
    }


def _champions_block(
    payload: dict[str, Any],
    ctx: FormationLayoutContext,
    formation: tuple[FormationHero, ...],
) -> list[dict[str, Any]]:
    by_id = {h.hero_id: h for h in formation}
    scores_map, attack_map = _ability_score_and_attack_maps()
    champions: list[dict[str, Any]] = []
    for hero_id in sorted(ctx.active_hero_ids):
        hero = by_id.get(hero_id)
        ilvl = hero.ilvl if hero is not None else None
        champions.append(
            build_champion_entry(
                payload,
                ctx,
                hero_id,
                current_position=ctx.seat_of(hero_id),
                ilvl=ilvl,
                scores_map=scores_map,
                attack_map=attack_map,
            )
        )
    return champions


def _attach_spec_state_changes(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from ic_gamedata.formation_ai_advice.mechanics import trait_changes_from_keys

    upgrades = _upgrade_row_map()
    effects = _effect_defines_by_id()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for opt in group.get("options") or []:
            if not isinstance(opt, dict):
                continue
            uid = opt.get("option_id")
            row = upgrades.get(uid) if isinstance(uid, int) else None
            if not isinstance(row, dict):
                continue
            effect_id = _effect_def_id(row.get("effect"))
            effect_row = effects.get(effect_id) if effect_id is not None else None
            keys = []
            if isinstance(effect_row, dict):
                keys = [k for k in (effect_row.get("effect_keys") or []) if isinstance(k, dict)]
            changes = trait_changes_from_keys(keys)
            if changes:
                opt["state_changes"] = changes
                opt["state_changes_note"] = (
                    "Evaluate this option from base traits + these changes only; "
                    "do not stack on top of another selected option in the same group."
                )
    return groups


def _effective_traits_for_champion(
    *,
    base_alignment: dict[str, Any] | None,
    base_roles: list[str],
    base_tags: list[str],
    specialization_groups: list[dict[str, Any]],
    feats: dict[str, Any],
) -> dict[str, Any]:
    from ic_gamedata.formation_ai_advice.mechanics import apply_trait_changes

    changes: list[dict[str, Any]] = []
    sources: list[str] = []
    for group in specialization_groups or []:
        if not isinstance(group, dict):
            continue
        if group.get("selection_status") != "selected":
            continue
        for opt in group.get("options") or []:
            if not isinstance(opt, dict) or not opt.get("selected"):
                continue
            for change in opt.get("state_changes") or []:
                if isinstance(change, dict):
                    changes.append(change)
                    sources.append(f"spec:{opt.get('option_id')}")
    for feat in (feats or {}).get("active_feats") or []:
        if not isinstance(feat, dict):
            continue
        for change in feat.get("trait_changes") or []:
            if isinstance(change, dict):
                changes.append(change)
                sources.append(f"feat:{feat.get('feat_id')}")
    return apply_trait_changes(
        base_alignment=base_alignment,
        base_roles=base_roles,
        base_tags=base_tags,
        changes=changes,
        sources=sources,
    )


def _readiness_issues(
    export: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Return (ready|ready_with_warnings|blocked, issues, dimensions).

    Dimensions (advice-facing):
    - schema_validity: sufficient|insufficient — export shape usable
    - party_legality: allowed|denied|unknown|conflict
    - placement_advice: sufficient|partial|insufficient
    - specialization_advice: sufficient|partial|insufficient
    - numeric_comparison: sufficient|partial|insufficient

    Legacy aliases (geometry/party_identity/…) are kept for older consumers.
    """
    issues: list[dict[str, Any]] = []
    formation = export.get("formation") or {}
    champions = export.get("champions") or []
    goal = export.get("goal") or {}

    dimensions: dict[str, Any] = {
        "schema_validity": "sufficient",
        "party_legality": "allowed",
        "placement_advice": "sufficient",
        "specialization_advice": "sufficient",
        "numeric_comparison": "sufficient",
        # Legacy mirrors:
        "geometry": "ok",
        "party_identity": "ok",
        "restrictions": "ok",
        "placement_mechanics": "ok",
        "specialization_mechanics": "ok",
    }

    def _set_advice(dim: str, status: str) -> None:
        order = {"sufficient": 0, "partial": 1, "insufficient": 2}
        cur = dimensions.get(dim, "sufficient")
        if order.get(status, 0) > order.get(str(cur), 0):
            dimensions[dim] = status

    for geo in formation.get("geometry_issues") or []:
        if isinstance(geo, dict):
            issues.append({**geo, "dimension": "geometry"})
            if geo.get("severity") == "error":
                dimensions["geometry"] = "blocked"
                dimensions["schema_validity"] = "insufficient"

    positions = formation.get("valid_position_ids") or formation.get("active_position_ids") or []
    if not positions:
        issues.append(
            {
                "code": "no_active_positions",
                "severity": "error",
                "dimension": "geometry",
                "message": "Geen actieve plaatsbare posities in de export.",
                "fix": "Formatie verversen in de Formation-tab.",
            }
        )
        dimensions["geometry"] = "blocked"
        dimensions["schema_validity"] = "insufficient"
    if not champions:
        issues.append(
            {
                "code": "no_champions",
                "severity": "error",
                "dimension": "party_identity",
                "message": "Geen geselecteerde champions.",
                "fix": "Zet champions in de formatie en ververs.",
            }
        )
        dimensions["party_identity"] = "blocked"
        dimensions["schema_validity"] = "insufficient"

    seats = [c.get("seat") for c in champions if isinstance(c, dict)]
    seat_ints = [s for s in seats if isinstance(s, int)]
    if seat_ints and len(seat_ints) != len(set(seat_ints)):
        issues.append(
            {
                "code": "duplicate_permanent_seats",
                "severity": "error",
                "dimension": "party_identity",
                "message": "Dubbele permanente seats in de selectie.",
                "fix": "Controleer champion-defines / partyselectie.",
            }
        )
        dimensions["party_identity"] = "blocked"
        dimensions["schema_validity"] = "insufficient"

    if positions and len(champions) > len(positions):
        issues.append(
            {
                "code": "party_exceeds_positions",
                "severity": "error",
                "dimension": "geometry",
                "message": (
                    f"Aantal champions ({len(champions)}) overschrijdt "
                    f"actieve posities ({len(positions)})."
                ),
                "fix": "Formatiegeometrie controleren.",
            }
        )
        dimensions["geometry"] = "blocked"
        dimensions["schema_validity"] = "insufficient"

    flavor_only_specs: list[int] = []
    missing_mech_specs: list[int] = []
    source_unknown_specs: list[int] = []
    numeric_incomplete: list[int] = []
    for c in champions:
        if not isinstance(c, dict):
            continue
        cid = c.get("champion_id")
        for g in c.get("specialization_groups") or []:
            if not isinstance(g, dict):
                continue
            for opt in g.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                usability = opt.get("usability")
                if usability == "flavor_only":
                    flavor_only_specs.append(cid)
                elif usability in (
                    "missing",
                    "effect_unsupported_or_missing_prose",
                ) or (
                    not opt.get("mechanical_usable") and not opt.get("mechanical_text")
                ):
                    missing_mech_specs.append(cid)
                unresolved = opt.get("unresolved_fields") or []
                if any(
                    "bron onbekend" in str(u).casefold()
                    or "source_unknown" in str(u).casefold()
                    or "placeholder:$target" in str(u).casefold()
                    or "unresolved_placeholder:$target" in str(u).casefold()
                    or "unresolved_placeholder:$(target)" in str(u).casefold()
                    for u in unresolved
                ):
                    source_unknown_specs.append(cid)
                quality = opt.get("quality") or {}
                if quality.get("usable_for_numeric_comparison") is not True:
                    if opt.get("selected") or opt.get("simultaneously_active"):
                        numeric_incomplete.append(cid)
        for ability in c.get("abilities") or []:
            if not isinstance(ability, dict):
                continue
            quality = ability.get("quality") or {}
            if quality.get("usable_for_numeric_comparison") is not True:
                numeric_incomplete.append(cid)
            unresolved = ability.get("unresolved_fields") or []
            if any(
                "bron onbekend" in str(u).casefold()
                or "unresolved_placeholder:$target" in str(u).casefold()
                or "unresolved_placeholder:$(target)" in str(u).casefold()
                for u in unresolved
            ):
                source_unknown_specs.append(cid)
            if quality.get("usable_for_placement") is False:
                _set_advice("placement_advice", "insufficient")

    if flavor_only_specs or missing_mech_specs:
        dims_ids = sorted({x for x in flavor_only_specs + missing_mech_specs if x})
        issues.append(
            {
                "code": "incomplete_specialization_mechanics",
                "severity": "warning",
                "dimension": "specialization_advice",
                "affected_champion_ids": dims_ids,
                "message": (
                    "Sommige specialisaties missen een beslisrelevante mechanic. "
                    "Gebruik 'Keuze open — effect ontbreekt' alleen dan, niet "
                    "voor elk ontbrekend percentage. Blokkeer plaatsing niet."
                ),
                "fix": "Plaatsingsvoorstel mag; spec-keuze niet raden.",
            }
        )
        dimensions["specialization_mechanics"] = "degraded"
        _set_advice("specialization_advice", "partial")

    if source_unknown_specs:
        ids = sorted({x for x in source_unknown_specs if x})
        issues.append(
            {
                "code": "unknown_positional_source",
                "severity": "warning",
                "dimension": "placement_advice",
                "affected_champion_ids": ids,
                "message": (
                    "Positionele bron ($(target)/emanatiebron) is onbekend voor "
                    "één of meer abilities/specs — targeting niet volledig beslisbaar."
                ),
                "fix": "Geen definitieve bronafhankelijke plaatsing claimen.",
            }
        )
        _set_advice("placement_advice", "partial")
        dimensions["placement_mechanics"] = "degraded"

    if numeric_incomplete:
        _set_advice("numeric_comparison", "partial")
        issues.append(
            {
                "code": "numeric_comparison_incomplete",
                "severity": "info",
                "dimension": "numeric_comparison",
                "affected_champion_ids": sorted({x for x in numeric_incomplete if x}),
                "message": (
                    "Niet alle magnitudes zijn bekend — kwalitatieve vergelijking "
                    "mag; geen bewezen optimale numerieke ranking."
                ),
                "fix": "Ontbrekende percentages blokkeren plaatsing niet automatisch.",
            }
        )

    weak_placement = 0
    for c in champions:
        if not isinstance(c, dict):
            continue
        abs_ = c.get("abilities") or []
        if not abs_:
            weak_placement += 1
            continue
        if not any(
            isinstance(a, dict)
            and (
                a.get("mechanical_usable")
                or a.get("quality", {}).get("usable_for_placement") is True
            )
            for a in abs_
        ):
            weak_placement += 1
    if weak_placement:
        issues.append(
            {
                "code": "limited_placement_mechanics",
                "severity": "warning",
                "dimension": "placement_advice",
                "message": (
                    f"{weak_placement} champion(s) zonder mechanisch bruikbare "
                    "abilitytekst — plaatsing voorwaardelijk onderbouwen."
                ),
                "fix": "Geen exacte buffwinst claimen.",
            }
        )
        dimensions["placement_mechanics"] = "degraded"
        _set_advice("placement_advice", "partial")

    if (
        goal.get("id") == "custom_task"
        and not ((goal.get("parameters") or {}).get("task_description"))
    ):
        issues.append(
            {
                "code": "missing_task_description",
                "severity": "error",
                "dimension": "placement_advice",
                "message": "Specifieke taak vereist een taakomschrijving.",
                "fix": "Vul de taakomschrijving in vóór kopiëren.",
            }
        )
        dimensions["placement_advice"] = "conflict"
        _set_advice("placement_advice", "blocked")

    party_status = goal.get("party_restriction_status") or "unchecked"
    if not goal.get("restrictions_checked_by_app"):
        issues.append(
            {
                "code": "unknown_restrictions",
                "severity": "warning",
                "dimension": "restrictions",
                "message": (
                    "Adventure-/patronrestricties zijn niet lokaal gecontroleerd. "
                    "Dat is niet hetzelfde als 'geen restrictie'."
                ),
                "fix": "Vul restrictietekst handmatig in of download game defines.",
            }
        )
        dimensions["restrictions"] = "unconfirmed"
        dimensions["party_legality"] = "unknown"
    elif party_status == "conflict":
        denied_ids: list[Any] = []
        seen_denied: set[Any] = set()
        for row in goal.get("party_restriction_checks") or []:
            if not isinstance(row, dict):
                continue
            # Prefer post-override eligibility; raw CHA denies must not block
            # when Dark Inheritance (etc.) already made the champion allowed.
            resolved = row.get("effective_status")
            if resolved is None:
                resolved = row.get("status")
            if resolved != "denied":
                continue
            hid = row.get("champion_id")
            if hid in seen_denied:
                continue
            seen_denied.add(hid)
            denied_ids.append(hid)
        if denied_ids:
            issues.append(
                {
                    "code": "restriction_conflict",
                    "severity": "warning",
                    "dimension": "restrictions",
                    "affected_champion_ids": denied_ids,
                    "message": (
                        "Bevestigd conflict tussen restrictieregels en championgegevens "
                        "(geen formation-trust bypass). Party-geldigheid niet bevestigd. "
                        f"Denied: {', '.join(str(i) for i in denied_ids)}."
                    ),
                    "fix": (
                        "Kopieer mag; vermeld conflict in het advies en stel legale "
                        "swaps voor. Geen 'ready' party claimen."
                    ),
                }
            )
            dimensions["restrictions"] = "conflict"
            dimensions["party_legality"] = "conflict"
        else:
            # Status said conflict but no champion is denied (e.g. stale label).
            issues.append(
                {
                    "code": "incomplete_restrictions",
                    "severity": "warning",
                    "dimension": "restrictions",
                    "message": (
                        "Restrictiestatus is conflict zonder denied champions — "
                        "behandeld als onbevestigd, niet als harde party-blokkade."
                    ),
                    "fix": "Voorwaardelijk adviseren; geen geldige party claimen.",
                }
            )
            dimensions["restrictions"] = "unconfirmed"
            dimensions["party_legality"] = "unknown"
    elif party_status in ("unconfirmed", "unchecked") or not goal.get(
        "restrictions_fully_known"
    ):
        issues.append(
            {
                "code": "incomplete_restrictions",
                "severity": "warning",
                "dimension": "restrictions",
                "message": (
                    "Restrictiecheck incompleet of onzeker (OR-uitzonderingen / "
                    "ontbrekende data). Onbekende uitzondering ≠ automatische goedkeuring."
                ),
                "fix": "Voorwaardelijk voorstel met zichtbare onzekerheid in de tabel.",
            }
        )
        dimensions["restrictions"] = "unconfirmed"
        dimensions["party_legality"] = "unknown"
    elif party_status == "allowed":
        dimensions["party_legality"] = "allowed"

    for c in champions:
        if not isinstance(c, dict):
            continue
        ilvl = c.get("item_levels") or {}
        if isinstance(ilvl, dict) and ilvl.get("value") is None:
            issues.append(
                {
                    "code": "missing_item_levels",
                    "severity": "info",
                    "dimension": "numeric_comparison",
                    "affected_champion_ids": [c.get("champion_id")],
                    "message": (
                        "Itemniveaus ontbreken — geen damage-multipliers afleiden."
                    ),
                    "fix": "Geen exacte winst claimen.",
                }
            )
            _set_advice("numeric_comparison", "partial")
            break

    # Overall: geometry/party_identity errors → blocked (export unsafe).
    # Restriction conflicts stay copyable as ready_with_warnings so chat/AI can
    # propose legal swaps; do not hard-block the clipboard on party vs rules.
    errors = [i for i in issues if i.get("severity") == "error"]
    hard_block = any(
        i.get("dimension") in ("geometry", "party_identity") and i.get("severity") == "error"
        for i in issues
    )
    advice_incomplete = any(
        dimensions.get(k) in ("partial", "insufficient")
        for k in (
            "placement_advice",
            "specialization_advice",
            "numeric_comparison",
        )
    )
    warnings = [i for i in issues if i.get("severity") != "error"]
    if hard_block:
        return "blocked", issues, dimensions
    if (
        errors
        or warnings
        or advice_incomplete
        or dimensions["restrictions"] in ("conflict", "unconfirmed")
        or dimensions["party_legality"] in ("conflict", "unknown", "denied")
    ):
        return "ready_with_warnings", issues, dimensions
    return "ready", issues, dimensions


def _champion_restriction_overrides(champ: dict[str, Any]) -> list[dict[str, Any]]:
    """Overrides that apply to *this* champion (from their own kit abilities)."""
    from ic_gamedata.formation_ai_advice.mechanics import detect_restriction_override

    overrides: list[dict[str, Any]] = []
    cid = champ.get("champion_id")
    for ability in champ.get("abilities") or []:
        if not isinstance(ability, dict):
            continue
        if ability.get("active_state") not in (None, "kit", "referenced_dependency"):
            continue
        if ability.get("simultaneously_active") is False:
            continue
        facts = ability.get("effect_facts") or {}
        strings = [
            item
            for item in (facts.get("effect_strings") or [])
            if isinstance(item, str)
        ]
        detected = detect_restriction_override(
            mechanical_text=ability.get("mechanical_text") or ability.get("text"),
            effect_strings=strings,
            source_ability_id=ability.get("ability_id")
            if isinstance(ability.get("ability_id"), int)
            else None,
            source_champion_id=cid if isinstance(cid, int) else None,
        )
        if detected:
            overrides.append(detected)
            continue
        # Legacy force_allow via tags only.
        for es in strings:
            if not es.startswith("force_allow_hero_by_tag"):
                continue
            for tag in facts.get("target_tags") or []:
                if isinstance(tag, str) and tag.strip():
                    overrides.append(
                        {
                            "kind": "force_allow_hero_by_tag",
                            "source_ability_id": ability.get("ability_id"),
                            "source_champion_id": cid,
                            "required_tag": tag.strip(),
                            "condition": "target_has_tag",
                            "evidence": "effect_string",
                        }
                    )
    return overrides


def _enrich_eligibility(export: dict[str, Any]) -> None:
    from ic_gamedata.formation_ai_advice.mechanics import evaluate_restriction_overrides

    champions = [c for c in (export.get("champions") or []) if isinstance(c, dict)]
    goal = export.get("goal") if isinstance(export.get("goal"), dict) else {}
    checks = {
        row.get("champion_id"): row
        for row in (goal.get("party_restriction_checks") or [])
        if isinstance(row, dict)
    }
    campaign_id = goal.get("campaign_id") if isinstance(goal.get("campaign_id"), int) else None
    campaign_name = (
        str(goal.get("campaign_name")) if goal.get("campaign_name") else None
    )
    effective: list[str] = []
    for champ in champions:
        check = checks.get(champ.get("champion_id")) or {}
        base = str(check.get("status") or "unknown")
        reason = check.get("reason")
        reason_text = str(reason or "")
        if base == "denied" and (
            "patron" in reason_text.casefold() or "geblokkeerd" in reason_text.casefold()
        ):
            base_reason = "patron_blocked"
        elif base == "denied" and (
            "dex" in reason_text.casefold()
            or "str" in reason_text.casefold()
            or "int" in reason_text.casefold()
            or "wis" in reason_text.casefold()
            or "con" in reason_text.casefold()
            or "cha" in reason_text.casefold()
            or "stat" in reason_text.casefold()
            or "bovengrens" in reason_text.casefold()
            or ">=" in reason_text
            or "<=" in reason_text
        ):
            base_reason = reason if isinstance(reason, str) else "stat_gate"
        else:
            base_reason = reason if isinstance(reason, str) else None
        tags: list[str] = []
        for key in ("effective_tags", "tags", "affiliations", "raw_tags"):
            raw = champ.get(key)
            if isinstance(raw, list):
                tags.extend(str(item) for item in raw if str(item).strip())
        tags_known = champ.get("affiliations_status") != "unknown" and (
            isinstance(champ.get("raw_tags"), list) or isinstance(champ.get("tags"), list)
        )
        overrides = _champion_restriction_overrides(champ)
        record = evaluate_restriction_overrides(
            base_status=base,
            base_reason=base_reason,
            overrides=overrides,
            champion_tags=tags,
            tags_known=tags_known,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
        )
        champ["eligibility"] = record
        # Party check rows: keep raw base, but make ``status`` the effective
        # truth so clipboard/AI do not keep warning about already-resolved
        # overrides (e.g. Dark Urge CHA deny + Dark Inheritance allow).
        if isinstance(check, dict) and check.get("champion_id") == champ.get(
            "champion_id"
        ):
            if "base_status" not in check:
                check["base_status"] = check.get("status")
            if "base_reason" not in check and check.get("reason") is not None:
                check["base_reason"] = check.get("reason")
            check["effective_status"] = record.get("effective_eligibility")
            check["effective_reason"] = record.get("effective_reason")
            eff = record.get("effective_eligibility")
            if isinstance(eff, str):
                check["status"] = eff
                if record.get("effective_reason"):
                    check["reason"] = record.get("effective_reason")
        value = record.get("effective_eligibility")
        if isinstance(value, str):
            effective.append(value)

    manual = any(
        "handmatig" in str(item).casefold() for item in (goal.get("local_evidence") or [])
    )
    if not effective:
        return
    if any(value == "denied" for value in effective):
        goal["party_restriction_status"] = "conflict"
    elif any(value == "unknown" for value in effective):
        if goal.get("party_restriction_status") in {"ok", None, "conflict"}:
            goal["party_restriction_status"] = "unconfirmed"
    elif all(value == "allowed" for value in effective):
        # Overrides can clear a raw conflict even with manual restriction text.
        if manual and goal.get("party_restriction_status") not in {"ok"}:
            goal["party_restriction_status"] = "unconfirmed"
        elif goal.get("party_restriction_status") in {
            "conflict",
            "unconfirmed",
            None,
        }:
            goal["party_restriction_status"] = "ok"


def _decision_gaps(export: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def add(problem: str, affects: str, champion_id: int | None = None) -> None:
        key = (problem, affects, champion_id)
        if key in seen:
            return
        seen.add(key)
        gaps.append(
            {
                "problem": problem,
                "affects": affects,
                "champion_id": champion_id,
            }
        )

    champ_lists = [
        export.get("champions") or [],
        export.get("candidates") or [],
    ]
    for champ_list in champ_lists:
        for champ in champ_list:
            if not isinstance(champ, dict):
                continue
            cid = (
                champ.get("champion_id")
                if isinstance(champ.get("champion_id"), int)
                else None
            )
            for ability in champ.get("abilities") or []:
                if not isinstance(ability, dict):
                    continue
                name = ability.get("name") or ability.get("ability_id")
                if ability.get("active_state") == "missing_dependency":
                    add(
                        f"Ability {name} ontbreekt. Targeting die daarvan afhangt kan niet volledig worden beoordeeld.",
                        "placement",
                        cid,
                    )
                quality = ability.get("quality") or {}
                if quality.get("dependencies_resolved") is False:
                    add(
                        f"{name}: onderliggende ability is niet opgelost.",
                        "placement",
                        cid,
                    )
            for group in champ.get("specialization_groups") or []:
                if not isinstance(group, dict):
                    continue
                for opt in group.get("options") or []:
                    if not isinstance(opt, dict):
                        continue
                    if opt.get("usability") == "flavor_only" or (
                        not opt.get("mechanical_text")
                        and opt.get("usability") != "partially_resolved"
                    ):
                        add(
                            f"{opt.get('name') or opt.get('option_id')}: "
                            "beslisrelevante mechanic ontbreekt.",
                            "specialization",
                            cid,
                        )
                        facts = opt.get("effect_facts") or {}
                        refs = facts.get("referenced_upgrade_ids") or []
                        if refs and not opt.get("mechanical_text"):
                            kit_ids = {
                                a.get("ability_id")
                                for a in (champ.get("abilities") or [])
                                if isinstance(a, dict)
                            }
                            present = [r for r in refs if r in kit_ids]
                            missing = [r for r in refs if r not in kit_ids]
                            if missing:
                                add(
                                    f"{opt.get('name')}: versterkt upgrade {missing} "
                                    "maar die ability ontbreekt in de export.",
                                    "specialization",
                                    cid,
                                )
                            elif present:
                                add(
                                    f"{opt.get('name')}: versterkt upgrade {present} "
                                    "(mechanic staat bij abilities; optietekst zelf "
                                    "is incompleet).",
                                    "specialization",
                                    cid,
                                )
            eligibility = champ.get("eligibility") or {}
            if eligibility.get("effective_eligibility") in {"unknown", "conflict"}:
                add(
                    f"Toelating is {eligibility.get('effective_eligibility')}"
                    + (
                        f" (vereiste affiliation "
                        f"{eligibility.get('required_affiliation')} niet geverifieerd)."
                        if eligibility.get("affiliation_verified") == "unknown"
                        else "."
                    ),
                    "party_validity",
                    cid,
                )
    return gaps


def _normalize_export_goal_id(
    goal: str,
    *,
    objective: AdviceObjective | str | None = None,
) -> str:
    """Resolve the user goal id for export. Never maps gold→favor or speed→gems."""
    from ic_gamedata.advice_goals import USER_GOAL_IDS, is_user_goal_id

    if is_user_goal_id(goal):
        return goal
    # Legacy technical objective/goal — only bud/push_damage may become push.
    if goal in ("bud",) or objective in ("push_damage", "push"):
        return "push"
    if goal in USER_GOAL_IDS:
        return goal
    raise ValueError(
        f"Kan geen export-doel bepalen uit goal={goal!r} objective={objective!r}. "
        "Kies Push, Quest, Gems, Favor of Specifieke taak."
    )


def build_export_payload(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    goal: str,
    context: str,
    objective: AdviceObjective | str | None = None,
    main_dps_id: int | None = None,
    fixed_main_dps_id: int | None = None,
    explicit_locked_champion_ids: list[int] | tuple[int, ...] | None = None,
    goal_parameters: dict[str, Any] | None = None,
    manual_restriction_text: str | None = None,
    request_id: str | None = None,
    research_mode: str = "provided_data_only",
) -> dict[str, Any]:
    """Serialize selected-party formation advice request for clipboard/chat.

    ``main_dps_id`` is accepted as a legacy alias for an *explicit* fixed main DPS.
    Without an explicit fixed DPS, no main DPS is invented and none is locked.
    """
    from ic_gamedata.adventure_restrictions import build_adventure_roster_filter
    from ic_gamedata.advice_goals import (
        build_goal_export_object,
        scoring_lane,
        validate_goal_parameters,
    )

    goal_id = _normalize_export_goal_id(goal, objective=objective)
    fixed_dps = (
        fixed_main_dps_id
        if isinstance(fixed_main_dps_id, int)
        else (main_dps_id if isinstance(main_dps_id, int) else None)
    )

    ok, err = validate_goal_parameters(goal_id, goal_parameters)
    if not ok:
        raise ValueError(err or "Ongeldige doelparameters.")

    instance = _active_instance(payload) or {}
    adventure_id = _parse_int(instance.get("current_adventure_id"))

    roster_filter = None
    try:
        roster_filter = build_adventure_roster_filter(payload, adventure_id)
    except Exception:
        roster_filter = None

    score_goal = scoring_lane(goal_id)
    ctx = build_formation_layout_context(
        payload,
        formation,
        goal=score_goal,  # type: ignore[arg-type]
        context=context,  # type: ignore[arg-type]
        roster_filter=roster_filter,
    )
    rid = request_id or str(uuid.uuid4())
    data_version = _data_version(payload)
    selected_ids = sorted(ctx.active_hero_ids)
    restrictions = _restriction_block(
        payload,
        manual_restriction_text=manual_restriction_text,
        adventure_id=adventure_id,
        selected_hero_ids=selected_ids,
    )
    if research_mode not in ("provided_data_only", "web_research_allowed"):
        research_mode = "provided_data_only"

    name_by_id = {int(h.hero_id): str(h.name) for h in formation}
    goal_block = build_goal_export_object(
        goal_id,
        user_parameters=goal_parameters,
        payload=payload,
        app_context=context,
        fixed_main_dps_id=fixed_dps,
        explicit_locked_ids=explicit_locked_champion_ids,
        name_by_id=name_by_id,
        restriction_fields=restrictions,
    )

    export: dict[str, Any] = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "request_id": rid,
            "requested_at": _utc_now_iso(),
            "exported_at": _utc_now_iso(),
            "data_version": data_version,
            "data_fetched_at": data_version,
            "prompt_version": PROMPT_VERSION,
            "scope": "optimize_placement_and_specializations_selected_only",
            "research_mode": research_mode,
            "default_ai_output": "markdown_table_only",
            "sources": {
                "champion_data": "cached_definitions.hero_defines + party payload",
                "geometry": "adventure/campaign formation graph via formation topology",
                "ability_texts": "upgrade_defines + effect_defines.description",
                "feat_texts": "cached_definitions.hero_feat_defines",
            },
        },
        "goal": goal_block,
        "formation": _formation_block(payload, ctx, adventure_id=adventure_id),
        "champions": _champions_block(payload, ctx, formation),
        "constraints": {
            "may_replace_champions": False,
            "may_add_or_remove_champions": False,
            "must_use_each_selected_champion_once": True,
            "may_change_feats": False,
            "may_change_equipment": False,
            "max_one_champion_per_permanent_seat": True,
            "only_active_positions": True,
            "do_not_derive_damage_multipliers_from_average_item_level": True,
            "fixed_champion_ids": list(goal_block.get("fixed_champion_ids") or []),
            "fixed_main_dps_id": fixed_dps,
            "main_dps_locked": isinstance(fixed_dps, int),
        },
        "damage_focus": goal_block.get("damage_focus"),
    }
    _enrich_eligibility(export)
    export["gaps"] = _decision_gaps(export) or None
    status, issues, dimensions = _readiness_issues(export)
    export["readiness"] = {
        "status": status,
        "dimensions": dimensions,
        "issues": issues,
    }
    export["meta"]["known_gaps"] = [
        i.get("message")
        for i in issues
        if isinstance(i, dict) and i.get("severity") != "error"
    ] or None
    return export


def request_fingerprint(export_payload: dict[str, Any]) -> str:
    """Stable hash of advice-relevant context (excludes request_id / timestamp)."""
    clone = json.loads(json.dumps(export_payload))
    meta = clone.get("meta")
    if isinstance(meta, dict):
        meta.pop("request_id", None)
        meta.pop("requested_at", None)
        meta.pop("exported_at", None)
    blob = json.dumps(clone, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def formation_layout_fingerprint_from_export(export_payload: dict[str, Any]) -> str:
    """Fingerprint of formation placement + advice goal — used for stale detection.

    Deliberately excludes ``meta.data_version``: that often comes from payload
    ``current_time``, which changes on every API poll and would falsely mark
    proposals stale between copy and paste.
    """
    formation = export_payload.get("formation") or {}
    champions = export_payload.get("champions") or []
    subset = {
        "current": formation.get("current_champion_by_position"),
        "positions": formation.get("valid_position_ids")
        or formation.get("active_position_ids"),
        "champion_ids": sorted(
            c.get("champion_id") for c in champions if isinstance(c, dict)
        ),
        "goal_id": (export_payload.get("goal") or {}).get("id"),
        "fixed_main_dps_id": (export_payload.get("goal") or {}).get(
            "fixed_main_dps_id"
        ),
    }
    blob = json.dumps(subset, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]
