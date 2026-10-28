"""Clipboard-friendly export for offline chat advice (no paid API).

Advice export: self-contained Dutch brief + compact readable JSON.
Debug export: full internal payload with provenance/parser details.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Literal

from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION

OutputMode = Literal["table", "json"]

_KEEP_EMPTY_LIST_KEYS = frozenset(
    {"affiliations", "active_feats", "active_feat_ids"}
)


def _goal_label_from_block(goal: dict[str, Any] | None) -> str:
    if not isinstance(goal, dict):
        return "onbekend doel"
    label = goal.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    goal_id = str(goal.get("id") or goal.get("objective") or "")
    try:
        from ic_gamedata.advice_goals import goal_label

        return goal_label(goal_id) or goal_id or "onbekend doel"
    except Exception:
        return goal_id or "onbekend doel"


def _objective_nl(objective: str | None) -> str:
    """Legacy helper — prefer ``_goal_label_from_block`` for new exports."""
    try:
        from ic_gamedata.advice_goals import goal_label

        return goal_label(objective) or str(objective or "onbekend doel")
    except Exception:
        if objective == "speed":
            return "Speed / areas"
        if objective == "push_damage":
            return "Push"
        return str(objective or "onbekend doel")


def _prune_empty(value: Any, *, keep_empty_list: bool = False) -> Any:
    """Drop None / empty containers recursively. Keep False/0."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            pruned = _prune_empty(
                item, keep_empty_list=key in _KEEP_EMPTY_LIST_KEYS
            )
            if pruned is None or pruned == {}:
                continue
            if pruned == [] and not (key in _KEEP_EMPTY_LIST_KEYS):
                continue
            out[key] = pruned
        return out
    if isinstance(value, list):
        if keep_empty_list and not value:
            return []
        out_list = []
        for item in value:
            pruned = _prune_empty(item)
            if pruned is None or pruned == {} or pruned == []:
                continue
            out_list.append(pruned)
        return out_list
    return value


def _effect_fingerprint(facts: dict[str, Any], mechanical_text: str | None) -> str:
    """Stable id for debug/shared catalogs — not used in compact advice UI."""
    sem = facts.get("semantics") if isinstance(facts.get("semantics"), dict) else {}
    payload = {
        "mechanical_text": mechanical_text,
        "semantics": sem,
        "parameters": facts.get("parameters"),
        "owner_ref": sem.get("owner_ref"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _project_value(facts: dict[str, Any] | None) -> dict[str, Any] | None:
    """Legacy structured projection — kept for tests/debug helpers."""
    if not isinstance(facts, dict):
        return None
    params = facts.get("parameters") or []
    values: list[dict[str, Any]] = []
    for param in params:
        if not isinstance(param, dict):
            continue
        if param.get("meaning") in {
            "upgrade_id",
            "attack_id",
            "effect_id",
            "hero_tag",
            "passthrough",
        }:
            continue
        if param.get("name") in {
            "upgrade_id",
            "selector",
            "hit_effect_id",
            "attack_id",
            "tag",
            "ultimate_attack_id",
        }:
            continue
        if param.get("status") == "computed_unknown" or param.get("value_basis") == "computed":
            values.append(
                {
                    "name": param.get("name"),
                    "value": None,
                    "meaning": param.get("meaning"),
                    "unit": param.get("unit"),
                    "value_basis": "computed",
                    "status": "computed_unknown",
                }
            )
            continue
        if param.get("value") is None:
            continue
        values.append(
            {
                "name": param.get("name"),
                "value": param.get("value"),
                "meaning": param.get("meaning"),
                "unit": param.get("unit"),
                "value_basis": param.get("value_basis") or "definition_base",
                "status": param.get("status") or "known",
                "effect_key": param.get("effect_key"),
            }
        )
    single = None
    if len(values) == 1 and values[0].get("status") == "known":
        single = values[0]
        values = []
    out = {
        "value": single,
        "values": values or None,
        "semantics": facts.get("semantics"),
        "stacking": facts.get("stacking"),
        "amount_status": facts.get("amount_status")
        if facts.get("amount_status") not in (None, "known")
        else None,
    }
    return _prune_empty(out)


def _effect_kind(item: dict[str, Any]) -> str | None:
    """bron = reliable source prose; gegenereerd = synthetic from parser."""
    source = str(item.get("mechanical_source") or item.get("text_source") or "").casefold()
    if "synthetic" in source or "generated" in source:
        return "gegenereerd"
    if item.get("mechanical_text") or item.get("text"):
        if "effect_defines" in source or "tip_text" in source or "description" in source:
            return "bron"
        if source:
            return "bron"
    return None


_HINT_SPEC_MISSING = "Keuze open — effect ontbreekt."
_HINT_ABILITY_MISSING = "Effect ontbreekt — bijdrage niet volledig te beoordelen."


def _mechanic_entry(
    item: dict[str, Any],
    *,
    kind: str = "ability",
) -> dict[str, Any] | None:
    """Readable mechanic for advice — text first, only essential extras.

    ``kind``: ability | feat | specialization — controls missing-effect wording.
    """
    if not isinstance(item, dict):
        return None
    tip = item.get("mechanical_text") or item.get("text")
    if isinstance(tip, str):
        tip = tip.strip() or None
    # Skip flavor-only / attack-id-only noise (not a usable mechanic).
    if tip and tip.casefold().startswith("sets attack id to"):
        tip = None
    if tip and tip.casefold().startswith("adds monster hit effect"):
        tip = None
    usability = item.get("usability")
    advice_hint = None
    missing_effect = usability == "flavor_only" or (
        not tip
        and usability
        in ("missing", "effect_unsupported_or_missing_prose", "partially_resolved")
    )
    # Attack-id-only / empty tip with a named ability still counts as missing.
    if not tip and item.get("name") and usability not in (None, "mechanical_usable"):
        missing_effect = True
    if not tip and item.get("name") and not usability:
        # Named row without any mechanic prose.
        missing_effect = True
    if missing_effect and not tip:
        advice_hint = (
            _HINT_SPEC_MISSING if kind == "specialization" else _HINT_ABILITY_MISSING
        )
    if not tip and not advice_hint and not item.get("name"):
        return None

    facts = item.get("effect_facts") if isinstance(item.get("effect_facts"), dict) else {}
    sem = facts.get("semantics") if isinstance(facts.get("semantics"), dict) else {}
    extras: dict[str, Any] = {}

    # Uggie / unknown position source — conditional only for that buff.
    pos = sem.get("position_source") if isinstance(sem.get("position_source"), dict) else None
    if pos and pos.get("kind") == "uggie_companion":
        if pos.get("position_status") == "unknown":
            extras["position_source"] = (
                "Uggie-companionpositie onbekend — alleen Uggie-afhankelijke "
                "bufftoerekening is voorwaardelijk."
            )
        else:
            extras["position_source"] = (
                f"Uggie-companion (buff_effect_id={pos.get('buff_effect_id')})"
            )

    amount_status = facts.get("amount_status")
    if tip and amount_status == "computed_unknown":
        # Basis bekend of niet: actuele totaalwaarde is niet berekend (zie bronregels).
        extras["magnitude"] = "basis_of_actueel_niet_berekend"
    elif tip and amount_status in {"partial", "unknown"} and "(onbekend)" in tip:
        extras["magnitude"] = "parameter_onbekend"

    stacking = facts.get("stacking") if isinstance(facts.get("stacking"), dict) else {}
    if stacking.get("mode") in {"multiplicative", "additive"} and tip:
        mode_nl = (
            "multiplicatief"
            if stacking["mode"] == "multiplicative"
            else "additief"
        )
        if "stack" not in tip.casefold():
            extras["stacking"] = mode_nl

    refs = facts.get("referenced_upgrade_ids")
    if isinstance(refs, list) and refs:
        extras["depends_on_upgrade_ids"] = [int(r) for r in refs if isinstance(r, int)]

    row = {
        "id": item.get("ability_id") or item.get("option_id") or item.get("feat_id"),
        "name": item.get("name"),
        "effect": tip,
        "effect_kind": _effect_kind(item) if tip else None,
        "advice_hint": advice_hint,
        **extras,
    }
    return _prune_empty(row)


def _project_spec_group(group: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(group, dict):
        return None
    options_out: list[dict[str, Any]] = []
    for opt in group.get("options") or []:
        if not isinstance(opt, dict):
            continue
        entry = _mechanic_entry(opt, kind="specialization") or {
            "name": opt.get("name"),
            "id": opt.get("option_id"),
        }
        entry["id"] = opt.get("option_id")
        entry["name"] = opt.get("name")
        if opt.get("selected"):
            entry["selected"] = True
        req = opt.get("requires_selected_option_id")
        if req is not None:
            entry["requires_option_id"] = req
        available = opt.get("available_in_current_state")
        if available is not None:
            entry["available"] = available
            # available mirrors current-branch prerequisite check only — not level.
            if available is False and req is not None:
                entry["unavailable_reason"] = "requires_other_option"
            elif available == "unknown":
                entry["unavailable_reason"] = "prerequisite_unknown"
        if opt.get("required_level") is not None:
            entry["required_level"] = opt.get("required_level")
        state = opt.get("state_changes")
        if isinstance(state, dict) and state:
            # Compact trait deltas only.
            entry["state_changes"] = _prune_empty(
                {
                    "alignment": state.get("alignment"),
                    "roles_add": state.get("roles_add") or state.get("add_roles"),
                    "tags_add": state.get("tags_add") or state.get("add_tags"),
                    "tags_remove": state.get("tags_remove") or state.get("remove_tags"),
                    "attack": state.get("attack") or state.get("basic_attack_type"),
                }
            )
        options_out.append(_prune_empty(entry))
    selected = None
    sid = group.get("selected_option_id")
    if sid is not None:
        for opt in options_out:
            if opt.get("id") == sid:
                selected = {"id": sid, "name": opt.get("name")}
                break
        if selected is None:
            selected = {"id": sid}
    return _prune_empty(
        {
            "group_id": group.get("group_id"),
            "label": group.get("group_label") or group.get("group_id"),
            "selection_mode": group.get("selection_mode") or "exactly_one",
            "status": group.get("selection_status"),
            "selected": selected,
            "options": options_out or None,
        }
    )


def _collect_uncertainties(
    export_payload: dict[str, Any],
    champions_out: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Bundled decision-relevant unknowns — not every missing number."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(wat: str, gevolg: str) -> None:
        key = f"{wat}|{gevolg}"
        if key in seen:
            return
        seen.add(key)
        rows.append({"wat": wat, "gevolg": gevolg})

    readiness = export_payload.get("readiness") if isinstance(export_payload, dict) else {}
    if isinstance(readiness, dict):
        for issue in readiness.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            msg = str(issue.get("message") or "")
            if code in {"numeric_comparison_incomplete", "synthetic_fixture"}:
                continue
            if issue.get("severity") == "error" or "restrict" in code.casefold():
                add(msg or code, "Partytoelating of plaatsing kan voorwaardelijk zijn.")
            elif "geometry" in code.casefold() or "adjacency" in code.casefold():
                add(msg or code, "Afstands- of adjacency-afhankelijke buffs onzeker.")

    goal = export_payload.get("goal") if isinstance(export_payload, dict) else {}
    if isinstance(goal, dict):
        status = goal.get("party_restriction_status")
        if status in {"blocked", "conflict", "unknown"}:
            add(
                f"Partyrestrictie-status: {status}",
                "Alleen een voorwaardelijk voorstel; claim geen geldig speelbare party.",
            )

    for champ in champions_out:
        name = str(champ.get("name") or champ.get("id") or "?")
        if champ.get("affiliations_status") == "unknown":
            add(
                f"Affiliaties van {name} onbekend",
                "Affiliation-filters kunnen targeting wijzigen.",
            )
        if champ.get("equipment") == "unknown":
            # Too noisy per champion — one bundled note.
            pass
        for ab in champ.get("abilities") or []:
            if not isinstance(ab, dict):
                continue
            if ab.get("position_source") and "onbekend" in str(
                ab.get("position_source")
            ).casefold():
                add(
                    f"{name}: {ab.get('name') or 'ability'} — bronpositie onbekend",
                    "Alleen de daarvan afhankelijke targeting is voorwaardelijk.",
                )
            if ab.get("advice_hint") and not ab.get("effect"):
                add(
                    f"{name}: {ab.get('name') or 'ability'} — mechanic ontbreekt",
                    "Bijdrage van deze ability niet volledig te beoordelen.",
                )
            if ab.get("magnitude") == "parameter_onbekend":
                add(
                    f"{name}: {ab.get('name') or 'ability'} — parameter onbekend",
                    "Kwalitatieve targeting blijft bruikbaar waar de tekst dat toelaat.",
                )
        for feat in champ.get("active_feats") or []:
            if isinstance(feat, dict) and feat.get("advice_hint") and not feat.get("effect"):
                add(
                    f"{name}: feat {feat.get('name') or '?'} — mechanic ontbreekt",
                    "Feat-bijdrage niet volledig te beoordelen.",
                )
        for group in champ.get("specializations") or []:
            if not isinstance(group, dict):
                continue
            if group.get("status") == "unknown":
                add(
                    f"{name}: specialisatiegroep {group.get('label') or group.get('group_id')} onbekend",
                    "Gebruik geen A → B; huidige keuze is niet vastgesteld.",
                )
            for opt in group.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                if opt.get("comparison_limit"):
                    add(str(opt["comparison_limit"]), "Alleen deze specvergelijking beperken.")
                elif opt.get("advice_hint"):
                    add(
                        f"{name}: {opt.get('name') or 'optie'} — mechanic ontbreekt",
                        "Specialisatiekeuze open of alleen kwalitatief te wegen.",
                    )
    if any(c.get("equipment") == "unknown" for c in champions_out):
        add(
            "Equipment-effecten onbekend",
            "Geen gear-buffs meewegen tenzij elders expliciet gegeven.",
        )
    return rows


def _project_item_levels(raw: Any) -> dict[str, Any] | None:
    """Compact avg + per-slot ilvls for BASE / projected champion rows."""
    if not isinstance(raw, dict):
        return None
    avg = raw.get("value")
    if avg is None:
        avg = raw.get("avg")
    by_slot_raw = raw.get("by_slot")
    by_slot: dict[str, int] | None = None
    if isinstance(by_slot_raw, dict) and by_slot_raw:
        parsed: dict[str, int] = {}
        for slot_id, level in by_slot_raw.items():
            try:
                parsed[str(int(slot_id))] = int(level)
            except (TypeError, ValueError):
                continue
        if parsed:
            by_slot = {
                slot: parsed[slot]
                for slot in sorted(parsed.keys(), key=lambda s: int(s))
            }
    if avg is None and by_slot is None:
        return None
    return _prune_empty({"avg": avg, "by_slot": by_slot})


def _project_champion_for_advice(
    champ: dict[str, Any],
    *,
    include_bench_notes: bool = False,
) -> dict[str, Any] | None:
    """Shared readable champion projection for party members and swap candidates."""
    if not isinstance(champ, dict):
        return None
    abilities = []
    for ab in champ.get("abilities") or []:
        if not isinstance(ab, dict):
            continue
        entry = _mechanic_entry(ab, kind="ability")
        if entry:
            abilities.append(entry)
        elif ab.get("name"):
            abilities.append(
                _prune_empty(
                    {
                        "id": ab.get("ability_id"),
                        "name": ab.get("name"),
                        "advice_hint": _HINT_ABILITY_MISSING,
                    }
                )
            )

    groups = []
    for group in champ.get("specialization_groups") or []:
        projected = _project_spec_group(group)
        if projected:
            groups.append(projected)

    missing_ability = {
        int(a["id"]): str(a.get("name") or a["id"])
        for a in abilities
        if isinstance(a.get("id"), int)
        and not a.get("effect")
        and a.get("advice_hint")
    }
    for group in groups:
        for opt in group.get("options") or []:
            if not isinstance(opt, dict):
                continue
            deps = opt.get("depends_on_upgrade_ids") or []
            blocked = [missing_ability[d] for d in deps if d in missing_ability]
            if blocked:
                base = blocked[0]
                opt["depends_on_missing"] = blocked
                opt["comparison_limit"] = (
                    f"De vergelijking van {opt.get('name') or 'deze optie'} met "
                    f"de alternatieven is beperkt doordat de basismechanic van "
                    f"{base} ontbreekt."
                )

    feats_block = champ.get("feats") if isinstance(champ.get("feats"), dict) else {}
    active_feats = []
    for feat in feats_block.get("active_feats") or []:
        if not isinstance(feat, dict):
            continue
        entry = _mechanic_entry(feat, kind="feat")
        if not entry and feat.get("name"):
            entry = _prune_empty(
                {
                    "id": feat.get("feat_id"),
                    "name": feat.get("name"),
                    "advice_hint": _HINT_ABILITY_MISSING,
                }
            )
        if not entry:
            continue
        applied = feat.get("already_applied_in_export")
        if isinstance(applied, dict) and (
            applied.get("tags") or applied.get("roles")
        ):
            entry["traits_already_in_effective"] = True
        active_feats.append(entry)

    eff_align = champ.get("effective_alignment") or champ.get("alignment")
    base_align = champ.get("base_alignment")
    eff_roles = champ.get("effective_roles") or champ.get("roles")
    base_roles = champ.get("base_roles")
    eff_tags = champ.get("effective_tags") or champ.get("tags")
    base_tags = champ.get("base_tags")

    live_state = _prune_empty(
        {
            "phase": champ.get("phase") or champ.get("current_phase"),
            "toughness_stacks": champ.get("toughness_stacks"),
            "brutality_stacks": champ.get("brutality_stacks"),
            "stacks": champ.get("stacks"),
        }
    )

    eligibility = champ.get("eligibility")
    if isinstance(eligibility, dict):
        eligibility = _prune_empty(
            {
                "status": eligibility.get("effective_eligibility")
                or eligibility.get("base_eligibility"),
                "reason": eligibility.get("effective_reason"),
                "affiliation_verified": eligibility.get("affiliation_verified"),
            }
        )

    gender = champ.get("gender") if isinstance(champ.get("gender"), dict) else None

    projected = {
        "id": champ.get("champion_id"),
        "name": champ.get("name"),
        "seat": champ.get("seat"),
        "position": champ.get("current_position"),
        "species": champ.get("species"),
        "classes": champ.get("classes"),
        "gender": gender,
        "alignment": eff_align,
        "base_alignment": base_align if base_align != eff_align else None,
        "roles": eff_roles,
        "base_roles": base_roles if base_roles != eff_roles else None,
        "tags": eff_tags,
        "base_tags": base_tags if base_tags != eff_tags else None,
        "affiliations": champ.get("affiliations")
        if champ.get("affiliations") is not None
        else (
            []
            if champ.get("affiliations_status") == "known"
            else None
        ),
        "affiliations_status": champ.get("affiliations_status") or "unknown",
        "attack": champ.get("basic_attack_type"),
        "stats": champ.get("ability_scores"),
        "eligibility": eligibility,
        "live_state": live_state or None,
        "abilities": abilities or None,
        "specializations": groups or None,
        "active_feats": active_feats or None,
        "equipment": champ.get("equipment_status") or "unknown",
        "item_levels": _project_item_levels(champ.get("item_levels")),
        "locked": champ.get("locked") or None,
        "lock_reason": champ.get("lock_reason"),
    }

    if include_bench_notes:
        bench = champ.get("bench_loadout") if isinstance(champ.get("bench_loadout"), dict) else {}
        feats_status = bench.get("feats_status")
        if feats_status == "unknown":
            projected["active_feats"] = None
            projected["feats_status"] = "unknown"
            projected["feats_note"] = bench.get("feats_note")
        elif feats_status == "known" and not active_feats:
            projected["feats_status"] = "known_empty"
            projected["feats_note"] = bench.get("feats_note")
        if bench.get("specialization_status"):
            projected["specialization_status"] = bench.get("specialization_status")
            projected["specialization_note"] = bench.get("specialization_note")
        projected["equipment_note"] = bench.get("equipment_note")
        projected["live_stacks_status"] = bench.get("live_stacks_status")
        projected["live_stacks_note"] = bench.get("live_stacks_note")
        seat_vs = champ.get("permanent_seat_vs_party")
        if isinstance(seat_vs, dict):
            projected["permanent_seat_vs_party"] = _prune_empty(
                {
                    "status": seat_vs.get("status"),
                    "reason": seat_vs.get("reason"),
                    "valid_one_swap": seat_vs.get("valid_one_swap"),
                    "must_replace_champion_id": seat_vs.get(
                        "must_replace_champion_id"
                    ),
                }
            )
        projected["owned"] = True
        projected["in_party"] = False

    return _prune_empty(projected)


def build_advice_payload(export_payload: dict[str, Any]) -> dict[str, Any]:
    """Compact advice projection: readable mechanics, no internal dump."""
    src = export_payload if isinstance(export_payload, dict) else {}
    meta = src.get("meta") if isinstance(src.get("meta"), dict) else {}
    goal = src.get("goal") if isinstance(src.get("goal"), dict) else {}
    formation = src.get("formation") if isinstance(src.get("formation"), dict) else {}
    readiness = src.get("readiness") if isinstance(src.get("readiness"), dict) else {}

    name_by_id = {
        int(c["champion_id"]): str(c.get("name") or c["champion_id"])
        for c in (src.get("champions") or [])
        if isinstance(c, dict) and isinstance(c.get("champion_id"), int)
    }
    fixed_dps = goal.get("fixed_main_dps_id")
    if not isinstance(fixed_dps, int):
        # Legacy field only when it was an explicit fixed DPS.
        legacy = goal.get("main_dps_id")
        focus = goal.get("damage_focus")
        if isinstance(focus, dict) and focus.get("kind") == "fixed":
            fixed_dps = focus.get("champion_id")
        elif isinstance(legacy, int) and goal.get("id") in (None, "push", "push_damage"):
            # Do not revive auto-carry as fixed DPS for new goal exports.
            fixed_dps = None
    main_dps_name = (
        name_by_id.get(int(fixed_dps), str(fixed_dps))
        if isinstance(fixed_dps, int)
        else None
    )
    damage_focus = goal.get("damage_focus")
    if damage_focus is None and isinstance(fixed_dps, int):
        damage_focus = {
            "champion_id": fixed_dps,
            "name": main_dps_name,
            "kind": "fixed",
        }

    context = _prune_empty(
        {
            "goal": _prune_empty(
                {
                    "id": goal.get("id") or goal.get("objective"),
                    "label": goal.get("label")
                    or _goal_label_from_block(goal),
                    "description": goal.get("description"),
                    "primary_metric": goal.get("primary_metric"),
                    "priorities": goal.get("priorities"),
                    "parameters": goal.get("parameters"),
                    "missing_context": goal.get("missing_context"),
                }
            ),
            "damage_focus": damage_focus,
            "fixed_champions": goal.get("fixed_champions"),
            "fixed_champion_ids": goal.get("fixed_champion_ids"),
            "fixed_main_dps": _prune_empty(
                {"id": fixed_dps, "name": main_dps_name}
            )
            if isinstance(fixed_dps, int)
            else None,
            "adventure": goal.get("adventure_name") or goal.get("adventure_id"),
            "campaign": goal.get("campaign_name") or goal.get("campaign_id"),
            "patron": goal.get("patron_name") or goal.get("patron_id"),
            "variant_id": goal.get("variant_id"),
            "party_restriction_status": goal.get("party_restriction_status"),
            "restriction_text": goal.get("restriction_text"),
            "restriction_checks": [
                _prune_empty(
                    {
                        "champion_id": row.get("champion_id"),
                        "name": name_by_id.get(int(row["champion_id"]))
                        if isinstance(row.get("champion_id"), int)
                        else None,
                        # Prefer effective (post-override) status for AI.
                        "status": row.get("effective_status") or row.get("status"),
                        "reason": row.get("effective_reason") or row.get("reason"),
                        "base_status": row.get("base_status"),
                    }
                )
                for row in (goal.get("party_restriction_checks") or [])
                if isinstance(row, dict)
            ]
            or None,
        }
    )

    positions = []
    for row in formation.get("positions") or []:
        if not isinstance(row, dict):
            continue
        positions.append(
            _prune_empty(
                {
                    "id": row.get("position_id"),
                    "column": row.get("column_index"),
                    "row": row.get("row_order"),
                    "zone": row.get("zone"),
                    "state": row.get("state"),
                    "label": row.get("label"),
                    "champion_id": row.get("current_champion_id"),
                    "display_column": row.get("display_column"),
                    "display_slot": row.get("display_slot"),
                    "display_position": row.get("display_position"),
                }
            )
        )

    distance = formation.get("distance") if isinstance(formation.get("distance"), dict) else {}
    front_direction = formation.get("front_direction") or {
        "rule": "lower_column_is_front",
    }
    from ic_gamedata.formation_ai_advice.labels import position_display_convention_block

    convention = formation.get("position_display_convention")
    if not isinstance(convention, dict):
        convention = position_display_convention_block(technical_id_field="id")
    else:
        convention = {**convention, "technical_id_field": "id"}
    geometry = _prune_empty(
        {
            "source": formation.get("geometry_source") or formation.get("formation_id"),
            "column_direction": front_direction,
            "row_direction": (
                front_direction.get("row_direction")
                if isinstance(front_direction, dict)
                else None
            )
            or "lower_row_is_top",
            "position_display_convention": convention,
            "distance_rule": distance.get("rule")
            or (formation.get("distance_definition") or {}).get("type")
            or "hops_on_active_adjacency",
            "escorts_in_adjacency": distance.get("escorts_count_as_adjacent")
            or "unknown",
            "valid_position_ids": formation.get("valid_position_ids")
            or formation.get("active_position_ids"),
            "blocked_position_ids": formation.get("blocked_position_ids"),
            "adjacency": formation.get("adjacency_by_position"),
            "positions": positions,
            "geometry_issues": formation.get("geometry_issues"),
            "table_order_note": formation.get("table_order_note"),
        }
    )

    champions_out: list[dict[str, Any]] = []
    for champ in src.get("champions") or []:
        projected = _project_champion_for_advice(champ)
        if projected:
            champions_out.append(projected)

    uncertainties = _collect_uncertainties(src, champions_out)

    # Decision gaps from export (affects_decision only).
    for gap in src.get("gaps") or []:
        if not isinstance(gap, dict) or gap.get("affects_decision") is False:
            continue
        msg = str(gap.get("message") or gap.get("summary") or gap.get("code") or "")
        if msg:
            uncertainties.append(
                {
                    "wat": msg,
                    "gevolg": str(
                        gap.get("decision")
                        or "Aanbeveling kan hierdoor onzeker zijn."
                    ),
                }
            )

    dims = readiness.get("dimensions") if isinstance(readiness.get("dimensions"), dict) else {}
    advice = {
        "meta": _prune_empty(
            {
                "schema_version": SCHEMA_VERSION,
                "request_id": meta.get("request_id"),
                "data_version": meta.get("data_version"),
                "research_mode": meta.get("research_mode") or "provided_data_only",
            }
        ),
        "bronregels": (
            "Gebruik complete, betrouwbare mechanicbeschrijvingen (effect) voor "
            "kwalitatieve interpretatie. effect_kind=bron is bronproza; "
            "effect_kind=gegenereerd is afgeleid. Ondersteunende ontbrekende "
            "parservelden zijn geen reden om duidelijke broninformatie te negeren. "
            "Bij een echte tegenspraak die de aanbeveling beïnvloedt: meld het "
            "conflict; raad niet welke waarde klopt. "
            "Bekende basiswaarden (definition_base) zijn geen actuele totale buffs "
            "na gear, upgrades en stacks — magnitude=basis_of_actueel_niet_berekend "
            "betekent dat de actuele totaalwaarde niet is berekend, niet dat de "
            "mechanic ontbreekt. magnitude=parameter_onbekend: een relevante "
            "parameter ontbreekt echt. "
            "Trait-wijzigingen van actieve feats met traits_already_in_effective=true "
            "zitten al in alignment/roles/tags — niet dubbel toepassen. "
            "available geldt voor de huidige specialisatiekeuzes. Bij wijziging van "
            "een eerdere keuze beoordeel je de bereikbaarheid van vervolgopties "
            "opnieuw via requires_option_id. available=false met "
            "unavailable_reason=requires_other_option is dus geen permanent verbod. "
            "Levelblokkades staan op required_level / group status not_unlocked; "
            "available=unknown betekent dat de prerequisite-status niet vaststaat."
        ),
        "context": context,
        "geometry": geometry,
        "champions": champions_out,
        "onzekerheden": uncertainties or None,
        "readiness": _prune_empty(
            {
                "status": readiness.get("status"),
                "party_legality": (dims.get("party_legality") or {}).get("status")
                if isinstance(dims.get("party_legality"), dict)
                else dims.get("party_legality"),
                "placement_advice": (dims.get("placement_advice") or {}).get("status")
                if isinstance(dims.get("placement_advice"), dict)
                else dims.get("placement_advice"),
                "specialization_advice": (
                    dims.get("specialization_advice") or {}
                ).get("status")
                if isinstance(dims.get("specialization_advice"), dict)
                else dims.get("specialization_advice"),
            }
        ),
    }
    return _prune_empty(advice)


def build_debug_payload(export_payload: dict[str, Any]) -> dict[str, Any]:
    """Full export for local diagnosis — not for default chat paste."""
    return copy.deepcopy(export_payload)


def _format_priorities(priorities: Any) -> str:
    if isinstance(priorities, list) and priorities:
        return "; ".join(str(p).rstrip(".") for p in priorities if p)
    return "volgens de aangeleverde doelprioriteiten"


def _readable_table_format_lines() -> list[str]:
    from ic_gamedata.formation_ai_advice.labels import (
        ADVICE_REPLY_FORMAT_INSTRUCTION,
        ADVICE_TABLE_HEADER_EXAMPLE,
    )

    return [
        "### Leesbare formatietabel + import-JSON",
        "",
        ADVICE_REPLY_FORMAT_INSTRUCTION,
        "",
        "Tabelkop (Champion = Naam (seat N); Specialisatie(s) = catalogusnamen):",
        "",
        ADVICE_TABLE_HEADER_EXAMPLE,
        "",
    ]


def _json_reply_format_lines(*, request_id: str) -> list[str]:
    """Machine-readable reply contract for clipboard JSON mode (e.g. Perplexity)."""
    example = {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id or "PLAK_DEZE_REQUEST_ID",
        "conditional": False,
        "placements": [
            {"position_id": 1, "champion_id": 3},
            {"position_id": 2, "champion_id": 2},
        ],
        "specializations": [
            {
                "champion_id": 3,
                "group_id": "tier_0",
                "option_id": 101,
            }
        ],
    }
    example_json = json.dumps(example, ensure_ascii=False, indent=2)
    lines = _readable_table_format_lines()
    lines.extend(
        [
            "### Verwacht antwoord-JSON (verplicht voor Plak)",
            "",
            "Na de leesbare tabel en eventuele uitleg: precies **één** JSON-object "
            "in één afgesloten Markdown-codeblok met taal json. "
            "Dat blok is wat de app inleest (Plak).",
            "",
            "Verplichte velden:",
            f"- `schema_version`: `\"{SCHEMA_VERSION}\"`",
            f"- `request_id`: exact `\"{request_id}\"` (niet wijzigen)",
            "- `placements`: array van `{position_id, champion_id}` "
            "(iedere geselecteerde champion precies éénmaal; geldige actieve "
            "posities — technische id’s, niet `1-1`)",
            "- `specializations`: array van `{champion_id, group_id, option_id}` "
            "(alleen echte keuzes uit de aangeleverde gegevens)",
            "",
            "Optioneel:",
            "- `conditional`: `true` als toelating/restricties onzeker zijn "
            "(anders `false` of weglaten)",
            "- `condition`: korte toelichting bij `conditional: true`",
            "",
            "Regels:",
            "- Gebruik integer IDs uit de gegevens, geen namen als ID.",
            "- `position_id` = technische fysieke formatiepositie "
            "(niet display_position, niet permanente F-seat).",
            "- Plakbaar voorbeeld (pas IDs aan op jouw voorstel):",
            "",
            "```json",
            example_json,
            "```",
        ]
    )
    return lines


def _instruction_block(
    *,
    output_mode: OutputMode,
    goal: dict[str, Any],
    main_dps_name: str | None,
    main_dps_id: Any,
    research_mode: str,
    request_id: str,
    char_count: int,
) -> list[str]:
    doel = _goal_label_from_block(goal)
    description = str(goal.get("description") or "").strip()
    primary = str(goal.get("primary_metric") or "").strip()
    priorities = _format_priorities(goal.get("priorities"))
    has_fixed_dps = isinstance(main_dps_id, int)
    if has_fixed_dps:
        hoofd_line = (
            f"Vaste hoofd-DPS (behouden): {main_dps_name} (`{main_dps_id}`)."
        )
        targeting_line = (
            "- Targeting en buffs rond de vaste hoofd-DPS controleren waar relevant."
        )
    else:
        hoofd_line = (
            "Geen vaste hoofd-DPS: beoordeel targeting op de relevante champions, "
            "functies en het gekozen doel; verzin geen verplichte damagebron."
        )
        targeting_line = (
            "- Targeting beoordelen op doelrelevante champions en functies "
            "(geen verplichte single-carry optimalisatie)."
        )

    lines = [
        "Je bent een Idle Champions-formatieadviseur.",
        "Dit is een zelfstandige game-adviesaanvraag, geen programmeer- of "
        "exportreviewtaak.",
        "",
        "Adviseer de plaatsing en specialisaties van uitsluitend de geselecteerde "
        "champions voor het hieronder genoemde gebruikersdoel.",
        "Vervang geen champions. Wijzig geen equipment. "
        "Feat-verbetervoorstellen mogen.",
        "",
        f"Doel: {doel}.",
    ]
    if description:
        lines.append(f"Uitleg: {description}")
    if primary:
        lines.append(f"Hoofdmaat: {primary}.")
    lines.extend(
        [
            hoofd_line,
            f"Prioriteiten: {priorities}.",
            "",
            "Gebruik BASE_SNAPSHOT en ADVICE_REQUEST als primaire bronnen.",
            "Zoek standaard niet op internet en vul ontbrekende mechanics niet in "
            "op basis van abilitynamen, flavor of herinneringen "
            "(tenzij de research_mode hieronder gerichte research toestaat).",
            "Behandel lokale eligibility=unknown niet automatisch als allowed.",
            "",
            "Wat jij als adviseur zelf moet doen:",
            "- Plaatsingen vergelijken.",
            "- Doelrelevante mechanics afwegen.",
            "- Afstanden uit de aangeleverde adjacency bepalen waar nodig.",
            targeting_line,
            "- Relevante champions, rollen en andere kwalificaties tellen.",
            "- Synergieën en positionele conflicten afwegen.",
            "- Specialisaties kiezen binnen hun echte keuzegroepen.",
            "- Rekenen als waarden en voorwaarden daarvoor voldoende bekend zijn.",
            "- Anders een onderbouwd kwalitatief voorstel geven.",
            "",
            "Harde regels:",
            "- Gebruik iedere geselecteerde champion precies eenmaal.",
            "- Gebruik uitsluitend geldige actieve posities.",
            "- Maximaal één champion per permanente seat.",
            "- Position_id is niet hetzelfde als permanente seat.",
            "- Wijzig geen champions of equipment.",
            "- Feat-verbetervoorstellen mogen; noem onzekerheid als het "
            "alternatief niet in de aangeleverde gegevens staat.",
            "- Specialisaties mogen worden geadviseerd binnen hun echte keuzegroepen "
            "en prerequisites.",
            "- Beoordeel een alternatief inclusief relevante veranderingen aan "
            "alignment, rollen, aanvalstype, tags of andere kenmerken.",
            "- Houd rekening met restricties en geverifieerde uitzonderingen.",
            "",
            "Interpretatie:",
            "- Kolomrichting en afstandsregel staan bij de geometrie.",
            "- Neutral op de Lawful/Chaotic-as is iets anders dan Neutral op de "
            "Good/Evil-as.",
            "- Basiswaarden zijn geen actuele totale buffs na gear, upgrades en stacks "
            "(zie bronregels).",
            "- Leid geen damagevermenigvuldigers af uit gemiddelde itemlevels.",
            "- Extra schade op basis van bestaande BUD is niet automatisch hogere BUD.",
            "- available geldt voor de huidige specialisatiekeuzes. Bij wijziging van "
            "een eerdere keuze beoordeel je de bereikbaarheid van vervolgopties opnieuw "
            "via requires_option_id. available=false is dus niet automatisch een "
            "permanent verbod. Respecteer overige prerequisites en beperkingen "
            "(required_level, not_unlocked, available=unknown).",
            "",
            "Omgaan met onzekerheid:",
            "- Een onbekend percentage blokkeert bekende targeting niet.",
            "- Een onbekende positionele bron maakt alleen de daarvan afhankelijke "
            "targeting voorwaardelijk.",
            "- Beperk onzekerheid tot de daardoor beïnvloede afweging.",
            "- Geef concrete keuzes als de informatie dat ondersteunt.",
            "- Als een ontbrekend gegeven de keuze kan omdraaien, vermeld de relevante "
            "alternatieven en de beslisfactor kort.",
            "- Claim geen bewezen optimum zonder voldoende bewijs.",
            "- Bij restrictieconflict of onbekende toelating: geef uitsluitend een "
            "voorwaardelijk voorstel en claim geen geldig speelbare party.",
            "",
        ]
    )
    # Both modes: readable Plek/Champion/Specialisatie(s) table + one import JSON.
    # Table-only mode previously forbade JSON; that conflicted with paste/import.
    if output_mode == "json":
        lines.extend(_json_reply_format_lines(request_id=request_id))
    else:
        lines.extend(_readable_table_format_lines())
        lines.extend(
            [
                "Extra toelichting kort onder de tabel. "
                "Gebruik A → B alleen als de actuele keuze A daadwerkelijk bekend is.",
                "Vermeld onzekerheden kort bij de betreffende champion.",
                "",
                "Als een andere opstelling nodig is om stacks of een fase op te bouwen, "
                "vermeld de noodzakelijke tijdelijke plaatsing kort in de relevante rij "
                "(ook met display_position).",
                "De tabel beschrijft de aanbevolen hoofdopstelling.",
                "",
                "Sluit af met precies één importeerbaar JSON-object in één "
                "afgesloten Markdown-codeblok met taal json en technische "
                f"position_id’s (request_id=`{request_id}`).",
            ]
        )
    from ic_gamedata.formation_ai_advice.research_mode import (
        research_mode_instruction_lines,
    )

    lines.extend(research_mode_instruction_lines(research_mode))
    if char_count >= 120_000:
        lines.extend(
            [
                "",
                f"**Let op:** adviesgegevens zijn groot ({char_count} tekens). "
                "Niet stil afgekapt — controleer of de chatcontext alles bevat.",
            ]
        )
    return lines


def format_clipboard_markdown(
    export_payload: dict[str, Any],
    *,
    output_mode: OutputMode = "table",
) -> str:
    """Compact advice pack: self-contained brief + one JSON block."""
    if output_mode not in ("table", "json"):
        output_mode = "table"

    goal = export_payload.get("goal") or {}
    champions = export_payload.get("champions") or []
    meta = export_payload.get("meta") or {}
    request_id = str(meta.get("request_id") or "")
    research_mode = str(meta.get("research_mode") or "provided_data_only")

    name_by_id = {
        int(c["champion_id"]): str(c.get("name") or c["champion_id"])
        for c in champions
        if isinstance(c, dict) and isinstance(c.get("champion_id"), int)
    }
    fixed_dps = None
    if isinstance(goal, dict):
        fixed_dps = goal.get("fixed_main_dps_id")
        focus = goal.get("damage_focus")
        if not isinstance(fixed_dps, int) and isinstance(focus, dict):
            if focus.get("kind") == "fixed":
                fixed_dps = focus.get("champion_id")
    main_dps_name = (
        name_by_id.get(int(fixed_dps), str(fixed_dps))
        if isinstance(fixed_dps, int)
        else None
    )

    advice = build_advice_payload(export_payload)
    advice_json = json.dumps(advice, ensure_ascii=False, separators=(",", ":"))
    char_count = len(advice_json)

    lines = _instruction_block(
        output_mode=output_mode,
        goal=goal if isinstance(goal, dict) else {},
        main_dps_name=main_dps_name,
        main_dps_id=fixed_dps,
        research_mode=research_mode,
        request_id=request_id,
        char_count=char_count,
    )
    lines.extend(
        [
            "",
            "## Gegevens",
            "```json",
            advice_json,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def format_debug_markdown(export_payload: dict[str, Any]) -> str:
    """Full debug dump for local inspection — not the default chat paste."""
    debug = build_debug_payload(export_payload)
    return "\n".join(
        [
            "# Idle Champions — formatieadvies DEBUG",
            "",
            "Volledige bronexport (provenance, ruwe velden, technische metadata).",
            "Niet bedoeld als standaard plaktekst voor chatadvies.",
            "",
            "```json",
            json.dumps(debug, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


def build_swap_advice_payload(export_payload: dict[str, Any]) -> dict[str, Any]:
    """Compact swap-mode projection: party baseline + auto-included externals."""
    base = build_advice_payload(export_payload)
    src = export_payload if isinstance(export_payload, dict) else {}
    swap = src.get("swap") if isinstance(src.get("swap"), dict) else {}
    constraints = (
        src.get("constraints") if isinstance(src.get("constraints"), dict) else {}
    )

    name_by_id = {
        int(c["id"]): str(c.get("name") or c["id"])
        for c in (base.get("champions") or [])
        if isinstance(c, dict) and isinstance(c.get("id"), int)
    }
    candidates_out: list[dict[str, Any]] = []
    for champ in src.get("candidates") or []:
        projected = _project_champion_for_advice(champ, include_bench_notes=True)
        if not projected:
            continue
        if champ.get("inclusion"):
            projected["inclusion"] = champ.get("inclusion")
            projected["inclusion_reason"] = champ.get("inclusion_reason")
        avail = champ.get("practical_availability")
        if isinstance(avail, dict):
            projected["practical_availability"] = _prune_empty(
                {
                    "status": avail.get("status"),
                    "note": avail.get("note"),
                    "game_instance_id": avail.get("game_instance_id"),
                }
            )
        candidates_out.append(projected)
        cid = projected.get("id")
        if isinstance(cid, int):
            name_by_id[cid] = str(projected.get("name") or cid)

    coverage = swap.get("coverage") if isinstance(swap.get("coverage"), dict) else {}
    fixed_ids = constraints.get("fixed_champion_ids") or swap.get("fixed_champion_ids") or []
    fixed_out = [
        {"id": fid, "name": name_by_id.get(int(fid), str(fid))}
        for fid in fixed_ids
        if isinstance(fid, int) or (isinstance(fid, str) and str(fid).isdigit())
    ]

    excluded_compact = [
        _prune_empty(
            {
                "id": row.get("champion_id"),
                "name": row.get("name"),
                "seat": row.get("seat"),
                "reason": row.get("reason"),
            }
        )
        for row in (swap.get("excluded") or [])
        if isinstance(row, dict)
    ]
    incomplete_compact = [
        _prune_empty(
            {
                "id": row.get("champion_id"),
                "name": row.get("name"),
                "reason": row.get("reason"),
            }
        )
        for row in (swap.get("incomplete") or [])
        if isinstance(row, dict)
    ]

    base["meta"] = _prune_empty(
        {
            **(base.get("meta") or {}),
            "scope": src.get("meta", {}).get("scope")
            if isinstance(src.get("meta"), dict)
            else None,
            "advice_kind": "champion_swap_auto_roster",
        }
    )
    base["constraints"] = _prune_empty(
        {
            "may_replace_champions": True,
            "max_swaps_per_proposal": constraints.get("max_swaps_per_proposal") or 3,
            "proposals_are_independent": True,
            "fixed_champion_ids": fixed_out or None,
            "main_dps_locked": bool(
                constraints.get("main_dps_locked")
                or (
                    isinstance(
                        (src.get("goal") or {}).get("fixed_main_dps_id"), int
                    )
                    if isinstance(src.get("goal"), dict)
                    else False
                )
            ),
            "may_change_feats": True,
            "may_change_equipment": False,
            "must_keep_same_party_size": True,
            "max_one_champion_per_permanent_seat": True,
            "ai_selects_among_exported_externals": True,
            "no_hidden_tier_list_or_top_n": True,
            "no_swap_is_valid": True,
            "no_account_damage_claim_without_equipment": True,
        }
    )
    base["swap"] = _prune_empty(
        {
            "candidate_selection": swap.get("candidate_selection")
            or "automatic_owned_external",
            "coverage": {
                "owned_known": coverage.get("owned_known_count"),
                "party": coverage.get("party_count"),
                "external_owned": coverage.get("external_owned_count"),
                "included": coverage.get("included_count"),
                "included_allowed": coverage.get("included_allowed_count"),
                "included_conditional": coverage.get("included_conditional_count"),
                "excluded": coverage.get("excluded_count"),
                "incomplete": coverage.get("incomplete_count"),
                "data_gap_champions": coverage.get("data_gap_champion_count"),
                "coverage_complete": coverage.get("coverage_complete"),
                "coverage_incomplete_reason": coverage.get(
                    "coverage_incomplete_reason"
                ),
                "exclusion_reasons": coverage.get("exclusion_reasons"),
                "note": coverage.get("note"),
            },
            "excluded": excluded_compact or None,
            "incomplete": incomplete_compact or None,
            "data_limits": swap.get("data_limits"),
        }
    )
    base["candidates"] = candidates_out or None
    base["bronregels"] = (
        str(base.get("bronregels") or "")
        + " Externe champions zijn automatisch opgenomen owned alternatieven "
        "(geen handmatige voorselectie, geen tierlijst). De AI kiest zelf tot "
        "drie onafhankelijke voorstellen. Niet iedereen hoeft in de eindparty. "
        "Per voorstel: max. drie wissels. Equipment-effecten ontbreken."
    ).strip()
    return _prune_empty(base)


def _swap_instruction_block(
    *,
    goal: dict[str, Any],
    main_dps_name: str | None,
    main_dps_id: Any,
    research_mode: str,
    request_id: str,
    char_count: int,
    fixed_names: list[str],
    coverage: dict[str, Any] | None,
) -> list[str]:
    doel = _goal_label_from_block(goal)
    description = str(goal.get("description") or "").strip()
    primary = str(goal.get("primary_metric") or "").strip()
    priorities = _format_priorities(goal.get("priorities"))
    has_fixed_dps = isinstance(main_dps_id, int)
    if has_fixed_dps:
        hoofd_line = (
            f"Vaste hoofd-DPS (niet vervangbaar): {main_dps_name} (`{main_dps_id}`)."
        )
        dps_rule = (
            "- Wijzig geen equipment of vaste hoofd-DPS. "
            "Feat-verbetervoorstellen mogen."
        )
    else:
        hoofd_line = (
            "Geen vaste hoofd-DPS: vergelijk kandidaten op het gekozen doel; "
            "schakel geen automatische DPS-lock in."
        )
        dps_rule = (
            "- Wijzig geen equipment. Feat-verbetervoorstellen mogen."
        )
    vast = (
        ", ".join(fixed_names)
        if fixed_names
        else "geen expliciete gebruikerslocks"
    )
    cov = coverage if isinstance(coverage, dict) else {}
    cov_line = (
        f"Rosterdekking: owned {cov.get('owned_known', '?')}, "
        f"party {cov.get('party', '?')}, "
        f"extern opgenomen {cov.get('included', '?')} "
        f"(allowed {cov.get('included_allowed', '?')}, "
        f"voorwaardelijk {cov.get('included_conditional', '?')}), "
        f"uitgesloten {cov.get('excluded', '?')}, "
        f"onvolledig {cov.get('incomplete', '?')}; "
        f"coverage_complete={cov.get('coverage_complete', '?')}."
    )

    lines = [
        "Je bent een Idle Champions-formatieadviseur.",
        "Dit is een zelfstandige game-adviesaanvraag, geen programmeer- of "
        "exportreviewtaak.",
        "",
        "Onderzoek zelf welke externe champions uit het geëxporteerde owned roster "
        "de huidige party beter kunnen laten aansluiten op het opgegeven "
        "gebruikersdoel.",
        "De gebruiker heeft geen vervanger of kandidaten aangewezen.",
        "",
        f"Doel: {doel}.",
    ]
    if description:
        lines.append(f"Uitleg: {description}")
    if primary:
        lines.append(f"Hoofdmaat: {primary}.")
    lines.extend(
        [
            hoofd_line,
            f"Vastgezette champions: {vast}.",
            f"Prioriteiten: {priorities}.",
            cov_line,
            "",
            "Gebruik BASE_SNAPSHOT en ADVICE_REQUEST als primaire bronnen.",
            "Zoek standaard niet op internet en vul ontbrekende mechanics niet in "
            "op basis van namen, flavor of herinneringen "
            "(tenzij research_mode gerichte research toestaat).",
            "Behandel lokale eligibility=unknown niet automatisch als allowed; "
            "sluit vervangingen niet definitief uit alleen omdat de lokale parser "
            "een regel niet ondersteunt — zie research_gaps.",
            "",
            "Werkwijze:",
            "- Gebruik de huidige party als baseline.",
            "- Zoek zelf relevante alternatieven in de opgenomen externe champions.",
            "- Bepaal zelf welke champions erin/eruit gaan (1–3 wissels).",
            "- Benoem per wissel welke champion eruit gaat en welke erin komt.",
            "- Controleer toelating, permanente seats, locks en partygrootte.",
            "- Vergelijk kandidaten op het gekozen gebruikersdoel "
            "(push ≠ gems ≠ favor ≠ quest).",
            "- Beoordeel gewonnen én verloren doelrelevante functies "
            "(buffs/synergieën, tank/heal/control/speed waar relevant).",
            "- Beoordeel na logische herplaatsing en geldige specialisaties.",
            "- Verkoop pure baseline-herplaatsingswinst niet als championwinst.",
            "- Kandidaten hoeven niet dezelfde fysieke plek over te nemen.",
            "- Permanente seat ≠ fysieke formatiepositie.",
            "- Als de permanente seat van een inkomende kandidaat bezet is, moet "
            "die bezetter tot de verwijderde champions in ditzelfde voorstel "
            "behoren (tenzij gelockt — dan ongeldig).",
            "- Als die seat vrij is, mag een andere niet-gelockte champion eruit.",
            "- Alleen echte locks en harde vereisten sluiten een seat uit; "
            "zonder lock blijft die seat in de rosterdekking.",
            "- Ieder voorstel is onafhankelijk en begint bij dezelfde baseline.",
            "- Voorstellen niet cumulatief toepassen.",
            "- Maximaal drie championwissels per voorstel (minder mag).",
            "- Geen wissel is een geldig resultaat.",
            "",
            "Harde regels:",
            "- Behoud dezelfde partygrootte.",
            "- In de eindparty: iedere champion precies eenmaal; alleen geldige "
            "actieve posities; max. één champion per permanente seat.",
            "- Externe champions hoeven niet allemaal in de eindparty.",
            dps_rule,
            "- Specialisaties binnen echte keuzegroepen en prerequisites.",
            "- Alleen owned champions uit deze export.",
            "",
            "Beperkingen:",
            "- Geen accountspecifieke damagewinst zonder voldoende gegevens.",
            "- Geen bewezen rosteroptimum bij onvolledige coverage.",
            "- Unknown/conflict-toelating → alleen voorwaardelijk voorstel.",
            "- Ontbrekende benchloadout ≠ lege loadout; geen gefabriceerde A→B "
            "als A onbekend is.",
            "- Leid geen damagevermenigvuldigers af uit gemiddelde itemlevels.",
            "- Beperk onzekerheid tot de daardoor beïnvloede afweging.",
            "",
            "Conclusies — onderscheid:",
            "- Mechanisch beter passend voor het gekozen doel.",
            "- Voorwaardelijk voordeel met expliciete beslisfactor.",
            "- Geen onderbouwde verbetering.",
            "",
            "Antwoordvorm:",
            "Begin met één korte conclusie: “Wissel aanbevolen”, "
            "“Voorwaardelijke wissel” of “Geen onderbouwde wissel”, plus één zin.",
            "",
            "Daarna max. drie sterkste onafhankelijke voorstellen "
            "(minder of nul mag; niet iedere kandidaat bespreken; "
            "per voorstel tot drie wissels, komma-gescheiden in Eruit/Erin):",
            "",
            "| Voorstel | Eruit (Plek) | Erin (Plek) | Verwacht voordeel | Verlies / onzekerheid |",
            "| --- | --- | --- | --- | --- |",
            "",
            "Per aanbevolen of expliciet voorwaardelijk voorstel: complete "
            "eindformatietabel (Champion = Naam (seat N); "
            "Specialisatie(s) = catalogusnamen):",
            "",
        ]
    )
    from ic_gamedata.formation_ai_advice.labels import (
        ADVICE_TABLE_HEADER_EXAMPLE,
        POSITION_DISPLAY_AI_INSTRUCTION,
    )

    lines.extend(
        [
            ADVICE_TABLE_HEADER_EXAMPLE,
            "",
            POSITION_DISPLAY_AI_INSTRUCTION,
            "A→B alleen als A bekend is.",
            "Geen verzonnen exacte winstpercentages.",
            "",
            "Bij geen onderbouwde wissel: kort waarom; geef één geoptimaliseerde "
            "baselineformatietabel. Optioneel één korte dekkingsbeperking als "
            "coverage_complete false is.",
            "Sluit af met precies één importeerbaar JSON-object in één "
            "afgesloten Markdown-codeblok met taal json en technische "
            "position_id’s.",
        ]
    )
    from ic_gamedata.formation_ai_advice.research_mode import (
        research_mode_instruction_lines,
    )

    lines.extend(research_mode_instruction_lines(research_mode))
    if char_count >= 120_000:
        lines.extend(
            [
                "",
                f"**Let op:** adviesgegevens zijn groot ({char_count} tekens). "
                "Niet stil afgekapt — controleer of de chatcontext alles bevat.",
            ]
        )
    if cov.get("coverage_complete") is False and cov.get("coverage_incomplete_reason"):
        lines.extend(
            [
                "",
                f"Dekkingsbeperking: {cov.get('coverage_incomplete_reason')}",
            ]
        )
    lines.extend(
        [
            "",
            f"(request_id `{request_id}` — alleen ter referentie; geen code wijzigen.)",
        ]
    )
    return lines


def format_swap_clipboard_markdown(export_payload: dict[str, Any]) -> str:
    """Self-contained auto-roster swap-advice pack for a new chat agent."""
    goal = export_payload.get("goal") or {}
    meta = export_payload.get("meta") or {}
    request_id = str(meta.get("request_id") or "")
    research_mode = str(meta.get("research_mode") or "provided_data_only")

    advice = build_swap_advice_payload(export_payload)
    advice_json = json.dumps(advice, ensure_ascii=False, separators=(",", ":"))
    char_count = len(advice_json)

    name_by_id: dict[int, str] = {}
    for c in (advice.get("champions") or []) + (advice.get("candidates") or []):
        if isinstance(c, dict) and isinstance(c.get("id"), int):
            name_by_id[int(c["id"])] = str(c.get("name") or c["id"])

    fixed_dps = None
    if isinstance(goal, dict):
        fixed_dps = goal.get("fixed_main_dps_id")
        focus = goal.get("damage_focus")
        if not isinstance(fixed_dps, int) and isinstance(focus, dict):
            if focus.get("kind") == "fixed":
                fixed_dps = focus.get("champion_id")
    main_dps_name = (
        name_by_id.get(int(fixed_dps), str(fixed_dps))
        if isinstance(fixed_dps, int)
        else None
    )
    fixed_ids = (export_payload.get("constraints") or {}).get("fixed_champion_ids") or []
    if not fixed_ids and isinstance(goal, dict):
        fixed_ids = goal.get("fixed_champion_ids") or []
    fixed_names = [
        name_by_id.get(int(fid), str(fid))
        for fid in fixed_ids
        if isinstance(fid, int)
    ]
    cov = (advice.get("swap") or {}).get("coverage") if isinstance(advice.get("swap"), dict) else {}

    lines = _swap_instruction_block(
        goal=goal if isinstance(goal, dict) else {},
        main_dps_name=main_dps_name,
        main_dps_id=fixed_dps,
        research_mode=research_mode,
        request_id=request_id,
        char_count=char_count,
        fixed_names=fixed_names,
        coverage=cov if isinstance(cov, dict) else None,
    )
    lines.extend(
        [
            "",
            "## Gegevens",
            "```json",
            advice_json,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from pasted chat / markdown fences.

    Prefers fenced json code blocks so a preceding readable Markdown table
    does not break import. Falls back to the first fenced block, then brace
    scan. Does not relax schema validation of the extracted object.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except Exception:
        pass

    # Prefer explicit ```json fences (table + explanation may precede).
    lower = stripped.casefold()
    search_from = 0
    while True:
        idx = lower.find("```json", search_from)
        if idx < 0:
            break
        rest = stripped[idx + len("```json") :]
        end = rest.find("```")
        if end >= 0:
            chunk = rest[:end].strip()
            try:
                value = json.loads(chunk)
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
        search_from = idx + len("```json")

    start = stripped.find("```")
    if start >= 0:
        rest = stripped[start + 3 :]
        if rest.lstrip().lower().startswith("json"):
            rest = rest.lstrip()[4:]
        end = rest.find("```")
        if end >= 0:
            chunk = rest[:end].strip()
            try:
                value = json.loads(chunk)
                return value if isinstance(value, dict) else None
            except Exception:
                pass
    # Brace scan fallback.
    left = stripped.find("{")
    right = stripped.rfind("}")
    if left >= 0 and right > left:
        try:
            value = json.loads(stripped[left : right + 1])
            return value if isinstance(value, dict) else None
        except Exception:
            return None
    return None
