"""Owned champion-swap advice export (auto roster coverage, max one swap).

Builds on the standard formation advice export without changing its behaviour.
The AI selects which external owned champions to consider; the app supplies
classified roster data — no ranking or mandatory manual candidate pick.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from ic_gamedata.formation_ai_advice.export import (
    PROMPT_VERSION,
    _champion_restriction_overrides,
    _decision_gaps,
    _permanent_seat,
    _readiness_issues,
    build_champion_entry,
    build_export_payload,
)
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_advisor_models import FormationHero

SWAP_SCOPE = "owned_roster_one_swap_search"
SWAP_PROMPT_VERSION = f"{PROMPT_VERSION}-swap-auto1"

EligibilityStatus = Literal["allowed", "denied", "unknown", "conflict"]
InclusionClass = Literal[
    "included_allowed",
    "included_conditional",
    "excluded",
    "incomplete",
]


@dataclass(frozen=True)
class SwapCandidateRow:
    """Legacy UI row (optional advanced tools); not required for one-click export."""

    hero_id: int
    name: str
    seat: int | None
    roles: tuple[str, ...]
    tags: tuple[str, ...]
    eligibility: EligibilityStatus
    eligibility_reason: str | None
    selectable: bool
    select_warning: str | None = None


def _active_adventure_id(payload: dict[str, Any]) -> int | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    for inst in details.get("game_instances") or []:
        if not isinstance(inst, dict):
            continue
        if active_id is None or _parse_int(inst.get("game_instance_id")) == active_id:
            return _parse_int(inst.get("current_adventure_id"))
    return None


def _loot_ilvl_map(payload: dict[str, Any]) -> dict[int, int]:
    try:
        from ic_gamedata.party_advisor_formation import _loot_ilvl_by_hero
    except Exception:
        return {}
    details = payload.get("details")
    if not isinstance(details, dict):
        return {}
    return _loot_ilvl_by_hero(details)


def _other_party_instance(
    payload: dict[str, Any], hero_id: int
) -> dict[str, Any] | None:
    """If the hero is assigned to a non-active party, report that fact separately."""
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        if _parse_int(hero.get("hero_id")) != hero_id:
            continue
        gi = _parse_int(hero.get("game_instance_id"))
        if gi is None or gi <= 0:
            return {
                "status": "bench_or_unassigned",
                "game_instance_id": gi,
                "note": "Niet in een actieve party-instance gezet (of onbekend).",
            }
        if active_id is not None and gi == active_id:
            return {
                "status": "active_party_or_bench_slot",
                "game_instance_id": gi,
                "note": (
                    "Zelfde game_instance als de actieve party; niet automatisch "
                    "op het bord."
                ),
            }
        return {
            "status": "other_party",
            "game_instance_id": gi,
            "note": (
                "Staat in een andere party-instance; owned ≠ automatisch "
                "beschikbaar om te plaatsen. Handmatig verplaatsen kan nodig zijn."
            ),
        }
    return {
        "status": "unknown",
        "note": "Party-toewijzing niet gevonden in payload.",
    }


def _base_eligibility_for_heroes(
    payload: dict[str, Any],
    hero_ids: list[int],
    *,
    adventure_id: int | None,
) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    if not hero_ids:
        return out
    try:
        from ic_gamedata.adventure_restrictions import (
            build_adventure_roster_filter,
            evaluate_heroes_against_filter,
        )

        filt = build_adventure_roster_filter(payload, adventure_id)
        for row in evaluate_heroes_against_filter(hero_ids, filt):
            if isinstance(row, dict) and isinstance(row.get("champion_id"), int):
                out[int(row["champion_id"])] = row
    except Exception:
        for hid in hero_ids:
            out[hid] = {
                "champion_id": hid,
                "status": "unknown",
                "reason": "Restrictiefilter niet beschikbaar.",
            }
    return out


def _effective_eligibility_record(
    champ: dict[str, Any],
    *,
    base_status: str,
    base_reason: Any,
    campaign_id: int | None,
    campaign_name: str | None,
) -> dict[str, Any]:
    from ic_gamedata.formation_ai_advice.mechanics import evaluate_restriction_overrides

    reason_text = str(base_reason or "")
    if base_status == "denied" and (
        "patron" in reason_text.casefold() or "geblokkeerd" in reason_text.casefold()
    ):
        resolved_reason = "patron_blocked"
    elif base_status == "denied" and (
        "dex" in reason_text.casefold()
        or "stat" in reason_text.casefold()
        or ">=" in reason_text
    ):
        resolved_reason = base_reason if isinstance(base_reason, str) else "stat_gate"
    else:
        resolved_reason = base_reason if isinstance(base_reason, str) else None

    tags: list[str] = []
    for key in ("effective_tags", "tags", "affiliations", "raw_tags"):
        raw = champ.get(key)
        if isinstance(raw, list):
            tags.extend(str(item) for item in raw if str(item).strip())
    tags_known = champ.get("affiliations_status") != "unknown" and (
        isinstance(champ.get("raw_tags"), list) or isinstance(champ.get("tags"), list)
    )
    return evaluate_restriction_overrides(
        base_status=base_status,
        base_reason=resolved_reason,
        overrides=_champion_restriction_overrides(champ),
        champion_tags=tags,
        tags_known=tags_known,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
    )


def _seat_conflict_for_candidate(
    *,
    candidate_seat: int | None,
    party_by_seat: dict[int, dict[str, Any]],
    locked_ids: set[int],
    main_dps_id: int | None,
) -> dict[str, Any]:
    """Permanent-seat collision vs current party (not physical position)."""
    if candidate_seat is None:
        return {
            "status": "unknown",
            "reason": "Permanente seat van kandidaat onbekend.",
            "valid_one_swap": None,
        }
    occupant = party_by_seat.get(int(candidate_seat))
    if occupant is None:
        return {
            "status": "free",
            "reason": (
                "Geen huidige party-champion op deze permanente seat; "
                "AI mag een andere niet-gelockte champion laten uitgaan."
            ),
            "valid_one_swap": True,
            "must_replace_champion_id": None,
        }
    occ_id = occupant.get("champion_id")
    occ_name = occupant.get("name")
    if not isinstance(occ_id, int):
        return {
            "status": "unknown",
            "reason": "Bezetter van permanente seat onbekend.",
            "valid_one_swap": None,
        }
    if occ_id == main_dps_id or occ_id in locked_ids:
        return {
            "status": "blocked_by_lock",
            "reason": (
                f"Seat {candidate_seat} is bezet door vastgezette champion "
                f"{occ_name or occ_id}; binnen één wissel niet inpasbaar."
            ),
            "valid_one_swap": False,
            "must_replace_champion_id": occ_id,
            "occupant_locked": True,
        }
    return {
        "status": "occupied_replaceable",
        "reason": (
            f"Seat {candidate_seat} is bezet door {occ_name or occ_id}; "
            "bij één wissel moet die champion de verwijderde zijn."
        ),
        "valid_one_swap": True,
        "must_replace_champion_id": occ_id,
        "occupant_locked": False,
    }


def _candidate_loadout_notes(champ: dict[str, Any]) -> dict[str, Any]:
    """Make unknown bench loadout explicit — never imply empty effects."""
    feats = champ.get("feats") if isinstance(champ.get("feats"), dict) else {}
    feat_note = str(feats.get("note") or "")
    if feat_note == "unknown" or feats.get("active_feats") is None:
        feats_status = "unknown"
        feats_note = (
            "Actieve feats van deze benchchampion zijn niet betrouwbaar bekend; "
            "niet interpreteren als geen feats."
        )
    else:
        feats_status = "known"
        feats_note = (
            "Alleen bekende actieve feats; niet-actieve bezeten feats zijn niet "
            "meegenomen (feats mogen niet wijzigen)."
        )

    specs = champ.get("specialization_groups") or []
    statuses = [
        g.get("selection_status")
        for g in specs
        if isinstance(g, dict) and g.get("selection_status")
    ]
    if not specs:
        spec_status = "unknown"
        spec_note = "Specialisatiekeuzes niet beschikbaar of niet van toepassing."
    elif any(s == "unknown" for s in statuses) or all(
        s in ("unknown", "unselected") for s in statuses
    ):
        spec_status = "current_choice_unknown"
        spec_note = (
            "Huidige specialisatiekeuze van deze benchchampion is niet "
            "betrouwbaar waargenomen; adviseer geldige opties zonder A→B alsof A bekend was."
        )
    else:
        spec_status = "observed"
        spec_note = None

    return {
        "feats_status": feats_status,
        "feats_note": feats_note,
        "specialization_status": spec_status,
        "specialization_note": spec_note,
        "equipment_status": champ.get("equipment_status") or "unknown",
        "equipment_note": (
            "Equipment-effecten ontbreken; gemiddeld itemniveau is geen "
            "damagevermenigvuldiger."
        ),
        "live_stacks_status": "unknown",
        "live_stacks_note": (
            "Actuele stacks/fase van benchchampions zijn niet betrouwbaar bekend."
        ),
    }


def _has_usable_mechanics(entry: dict[str, Any]) -> bool:
    abilities = entry.get("abilities") or []
    specs = entry.get("specialization_groups") or []
    if abilities or specs:
        return True
    # Name + taxonomy alone is weak but still "included" if definitions exist.
    return bool(entry.get("name") and entry.get("seat") is not None)


def _classify_external(
    *,
    eligibility: dict[str, Any],
    seat_vs: dict[str, Any],
    entry: dict[str, Any] | None,
    build_error: str | None,
) -> tuple[InclusionClass, str | None]:
    if build_error or entry is None:
        return "incomplete", build_error or "Champion-export kon niet worden opgebouwd."
    if not _has_usable_mechanics(entry):
        return (
            "incomplete",
            "Geen bruikbare abilities/specialisaties uit definities beschikbaar.",
        )

    eff = str(eligibility.get("effective_eligibility") or "unknown")
    if eff == "denied":
        return (
            "excluded",
            str(
                eligibility.get("effective_reason")
                or "Definitief niet toegelaten na evaluatie van uitzonderingen."
            ),
        )

    if seat_vs.get("status") == "blocked_by_lock" or seat_vs.get("valid_one_swap") is False:
        return (
            "excluded",
            str(
                seat_vs.get("reason")
                or "Permanente seat bezet door gelockte champion (één-wisselscope)."
            ),
        )

    if eff in ("unknown", "conflict") or seat_vs.get("valid_one_swap") is None:
        return (
            "included_conditional",
            str(
                eligibility.get("effective_reason")
                or seat_vs.get("reason")
                or "Toelating of seat-inpasbaarheid voorwaardelijk/onbekend."
            ),
        )

    return "included_allowed", None


def list_owned_swap_candidates(
    payload: dict[str, Any],
    party_hero_ids: set[int] | frozenset[int],
    *,
    adventure_id: int | None = None,
) -> list[SwapCandidateRow]:
    """Owned champions not in the current party (optional advanced UI)."""
    from ic_gamedata.party_advisor_formation import _owned_heroes

    if adventure_id is None:
        adventure_id = _active_adventure_id(payload)

    owned = _owned_heroes(payload)
    bench_ids = [hid for hid, _n, _r, _t in owned if hid not in party_hero_ids]
    base_checks = _base_eligibility_for_heroes(
        payload, bench_ids, adventure_id=adventure_id
    )

    campaign_id = None
    campaign_name = None
    try:
        from ic_gamedata.specializations import _active_adventure_details, _definition_name

        _adv, campaign_id, _loc = _active_adventure_details(payload)
        if campaign_id is not None:
            campaign_name = _definition_name(payload, "campaign_defines", campaign_id)
    except Exception:
        pass

    rows: list[SwapCandidateRow] = []
    for hero_id, name, roles, tags in owned:
        if hero_id in party_hero_ids:
            continue
        check = base_checks.get(hero_id) or {
            "status": "unknown",
            "reason": "Geen restrictie-uitkomst.",
        }
        base_status = str(check.get("status") or "unknown")
        shell = {
            "champion_id": hero_id,
            "name": name,
            "tags": list(tags),
            "affiliations_status": "known" if tags else "unknown",
            "raw_tags": list(tags),
            "abilities": [],
        }
        try:
            from ic_gamedata.formation_ai_advice.export import _ability_texts

            shell["abilities"] = _ability_texts(hero_id) or []
        except Exception:
            shell["abilities"] = []

        record = _effective_eligibility_record(
            shell,
            base_status=base_status,
            base_reason=check.get("reason"),
            campaign_id=campaign_id if isinstance(campaign_id, int) else None,
            campaign_name=str(campaign_name) if campaign_name else None,
        )
        effective = str(
            record.get("effective_eligibility") or base_status or "unknown"
        )
        if effective not in ("allowed", "denied", "unknown", "conflict"):
            effective = "unknown"
        reason = record.get("effective_reason") or check.get("reason")
        reason_text = str(reason) if reason else None

        if effective == "allowed":
            selectable = True
            warning = None
        elif effective == "denied":
            selectable = False
            warning = None
        else:
            selectable = True
            warning = (
                "Toelating onzeker of conflicterend — alleen als voorwaardelijk "
                "voorstel beoordelen."
            )

        rows.append(
            SwapCandidateRow(
                hero_id=hero_id,
                name=name,
                seat=_permanent_seat(hero_id),
                roles=tuple(roles),
                tags=tuple(tags),
                eligibility=effective,  # type: ignore[arg-type]
                eligibility_reason=reason_text,
                selectable=selectable,
                select_warning=warning,
            )
        )
    rows.sort(key=lambda r: ((r.seat is None, r.seat or 0), r.name.casefold()))
    return rows


def build_swap_export_payload(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    locked_champion_ids: list[int] | tuple[int, ...] | None = None,
    candidate_ids: list[int] | tuple[int, ...] | None = None,
    goal: str = "push",
    context: str = "campaign",
    objective: str | None = None,
    main_dps_id: int | None = None,
    fixed_main_dps_id: int | None = None,
    goal_parameters: dict[str, Any] | None = None,
    manual_restriction_text: str | None = None,
    request_id: str | None = None,
    research_mode: str = "provided_data_only",
) -> dict[str, Any]:
    """Party baseline + automatic owned external roster (classified, no ranking).

    ``candidate_ids`` is optional (advanced subset). When omitted, every owned
    champion outside the party is classified and included or excluded with reason.

    Locks come only from explicit ``locked_champion_ids`` and an explicit fixed
    main DPS — never from an auto-selected carry.
    """
    fixed_dps = (
        fixed_main_dps_id
        if isinstance(fixed_main_dps_id, int)
        else (main_dps_id if isinstance(main_dps_id, int) else None)
    )
    export = build_export_payload(
        payload,
        formation,
        goal=goal,
        context=context,
        objective=objective,
        fixed_main_dps_id=fixed_dps,
        explicit_locked_champion_ids=locked_champion_ids,
        goal_parameters=goal_parameters,
        manual_restriction_text=manual_restriction_text,
        request_id=request_id,
        research_mode=research_mode,
    )

    party_ids = {
        int(c["champion_id"])
        for c in (export.get("champions") or [])
        if isinstance(c, dict) and isinstance(c.get("champion_id"), int)
    }
    locked: set[int] = set()
    for raw in (export.get("goal") or {}).get("fixed_champion_ids") or ():
        hid = _parse_int(raw)
        if hid is not None and hid in party_ids:
            locked.add(hid)
    for raw in locked_champion_ids or ():
        hid = _parse_int(raw)
        if hid is not None and hid in party_ids:
            locked.add(hid)
    carry = fixed_dps if isinstance(fixed_dps, int) and fixed_dps in party_ids else None

    from ic_gamedata.party_advisor_formation import _owned_heroes

    owned_rows = _owned_heroes(payload)
    owned_ids = {hid for hid, _n, _r, _t in owned_rows}
    owned_meta = {hid: (name, roles, tags) for hid, name, roles, tags in owned_rows}

    # Every owned hero outside the party must be classified (no silent drop).
    external_ids = sorted(hid for hid in owned_ids if hid not in party_ids)

    # Optional advanced filter: still classify everyone, but only detail the subset
    # when candidate_ids is explicitly provided. Auto mode details all includable.
    subset: set[int] | None = None
    if candidate_ids is not None:
        subset = set()
        for raw in candidate_ids:
            hid = _parse_int(raw)
            if hid is not None:
                subset.add(hid)

    adventure_id = _parse_int((export.get("goal") or {}).get("adventure_id"))
    if adventure_id is None:
        adventure_id = _active_adventure_id(payload)

    try:
        from ic_gamedata.adventure_restrictions import build_adventure_roster_filter

        roster_filter = build_adventure_roster_filter(payload, adventure_id)
    except Exception:
        roster_filter = None

    ctx = build_formation_layout_context(
        payload,
        formation,
        goal=goal,  # type: ignore[arg-type]
        context=context,  # type: ignore[arg-type]
        roster_filter=roster_filter,
    )
    from ic_gamedata.formation_ai_advice.export import _ability_score_and_attack_maps

    scores_map, attack_map = _ability_score_and_attack_maps()
    ilvl_map = _loot_ilvl_map(payload)

    goal_block = export.get("goal") if isinstance(export.get("goal"), dict) else {}
    campaign_id = (
        goal_block.get("campaign_id")
        if isinstance(goal_block.get("campaign_id"), int)
        else None
    )
    campaign_name = (
        str(goal_block.get("campaign_name"))
        if goal_block.get("campaign_name")
        else None
    )
    base_checks = _base_eligibility_for_heroes(
        payload, external_ids, adventure_id=adventure_id
    )

    party_by_seat: dict[int, dict[str, Any]] = {}
    for champ in export.get("champions") or []:
        if not isinstance(champ, dict):
            continue
        seat = champ.get("seat")
        if isinstance(seat, int):
            party_by_seat[seat] = champ

    for champ in export.get("champions") or []:
        if not isinstance(champ, dict):
            continue
        cid = champ.get("champion_id")
        if isinstance(cid, int) and cid in locked:
            champ["locked"] = True
            champ["lock_reason"] = (
                "fixed_main_dps" if cid == carry else "user_lock"
            )

    candidates_out: list[dict[str, Any]] = []
    excluded_out: list[dict[str, Any]] = []
    incomplete_out: list[dict[str, Any]] = []
    classification: list[dict[str, Any]] = []
    data_gap_ids: list[int] = []

    for hid in external_ids:
        name, roles, tags = owned_meta.get(hid, (str(hid), (), ()))
        check = base_checks.get(hid) or {
            "status": "unknown",
            "reason": "Geen restrictie-uitkomst.",
        }
        entry: dict[str, Any] | None = None
        build_error: str | None = None
        try:
            entry = build_champion_entry(
                payload,
                ctx,
                hid,
                current_position=None,
                ilvl=ilvl_map.get(hid),
                scores_map=scores_map,
                attack_map=attack_map,
            )
            entry["in_party"] = False
            entry["owned"] = True
            entry["current_position"] = None
        except Exception as exc:
            build_error = f"Exportfout: {exc}"

        if entry is not None:
            eligibility = _effective_eligibility_record(
                entry,
                base_status=str(check.get("status") or "unknown"),
                base_reason=check.get("reason"),
                campaign_id=campaign_id,
                campaign_name=campaign_name,
            )
            seat_vs = _seat_conflict_for_candidate(
                candidate_seat=entry.get("seat")
                if isinstance(entry.get("seat"), int)
                else None,
                party_by_seat=party_by_seat,
                locked_ids=locked,
                main_dps_id=carry if isinstance(carry, int) else None,
            )
            entry["eligibility"] = eligibility
            entry["base_restriction_check"] = {
                "status": check.get("status"),
                "reason": check.get("reason"),
            }
            entry["permanent_seat_vs_party"] = seat_vs
            entry["bench_loadout"] = _candidate_loadout_notes(entry)
            entry["practical_availability"] = _other_party_instance(payload, hid)
        else:
            eligibility = {
                "effective_eligibility": str(check.get("status") or "unknown"),
                "effective_reason": check.get("reason"),
                "base_eligibility": check.get("status"),
            }
            seat_vs = _seat_conflict_for_candidate(
                candidate_seat=_permanent_seat(hid),
                party_by_seat=party_by_seat,
                locked_ids=locked,
                main_dps_id=carry if isinstance(carry, int) else None,
            )

        klass, klass_reason = _classify_external(
            eligibility=eligibility if isinstance(eligibility, dict) else {},
            seat_vs=seat_vs,
            entry=entry,
            build_error=build_error,
        )

        # Advanced subset: still classify, but skip detailing non-selected.
        if subset is not None and hid not in subset:
            # Count as classified for coverage; treat as excluded from *this* export
            # detail with explicit reason (not a quality ranking).
            if klass.startswith("included"):
                klass = "excluded"
                klass_reason = (
                    "Niet in optionele advanced subset van deze export "
                    "(geen kwaliteitsfilter)."
                )

        class_row = {
            "champion_id": hid,
            "name": (entry or {}).get("name") or name,
            "seat": (entry or {}).get("seat")
            if entry is not None
            else _permanent_seat(hid),
            "classification": klass,
            "reason": klass_reason,
            "eligibility": (
                eligibility.get("effective_eligibility")
                if isinstance(eligibility, dict)
                else None
            ),
        }
        classification.append(class_row)

        if klass == "excluded":
            excluded_out.append(
                {
                    "champion_id": hid,
                    "name": class_row["name"],
                    "seat": class_row["seat"],
                    "reason": klass_reason,
                    "eligibility": class_row["eligibility"],
                }
            )
            continue

        if klass == "incomplete":
            incomplete_out.append(
                {
                    "champion_id": hid,
                    "name": class_row["name"],
                    "seat": class_row["seat"],
                    "reason": klass_reason,
                }
            )
            data_gap_ids.append(hid)
            continue

        assert entry is not None
        entry["inclusion"] = klass
        entry["inclusion_reason"] = klass_reason
        bench = entry.get("bench_loadout") or {}
        if (
            bench.get("feats_status") == "unknown"
            or bench.get("specialization_status")
            in ("unknown", "current_choice_unknown")
            or entry.get("equipment_status") == "unknown"
        ):
            data_gap_ids.append(hid)
            entry["has_relevant_data_gaps"] = True
        candidates_out.append(entry)

    n_owned = len(owned_ids)
    n_party = len(party_ids)
    n_external = len(external_ids)
    n_included = len(candidates_out)
    n_excluded = len(excluded_out)
    n_incomplete = len(incomplete_out)
    n_allowed = sum(
        1 for c in candidates_out if c.get("inclusion") == "included_allowed"
    )
    n_conditional = sum(
        1 for c in candidates_out if c.get("inclusion") == "included_conditional"
    )

    # Accounting: party + external == owned; external == included+excluded+incomplete
    accounts_ok = (
        n_party + n_external == n_owned
        and n_included + n_excluded + n_incomplete == n_external
    )
    exclusion_reasons = [
        {"reason": reason, "count": count}
        for reason, count in Counter(
            str(row.get("reason") or "onbekend") for row in excluded_out
        ).most_common()
    ]

    coverage_complete = bool(accounts_ok and n_incomplete == 0)
    incomplete_reason = None
    if not accounts_ok:
        incomplete_reason = "Interne dekkingstelling klopt niet — controleer classificatie."
        coverage_complete = False
    elif n_incomplete:
        incomplete_reason = (
            f"{n_incomplete} externe owned champion(s) niet volledig beoordeelbaar "
            "door ontbrekende brongegevens."
        )
    elif any(c.get("has_relevant_data_gaps") for c in candidates_out):
        # Still coverage_complete for roster membership; note soft gaps separately.
        pass

    meta = export.setdefault("meta", {})
    meta["scope"] = SWAP_SCOPE
    meta["prompt_version"] = SWAP_PROMPT_VERSION
    meta["default_ai_output"] = "swap_proposals_markdown"
    meta["advice_kind"] = "champion_swap_auto_roster"
    meta["sources"] = {
        **(meta.get("sources") or {}),
        "candidates": "details.heroes owned=true + same mechanics pipeline as party",
        "candidate_selection": (
            "automatic_owned_external" if subset is None else "optional_advanced_subset"
        ),
        "ranking": "none",
    }

    export["constraints"] = {
        "may_replace_champions": True,
        "max_swaps_per_proposal": 1,
        "proposals_are_independent": True,
        "proposals_must_start_from_same_baseline_party": True,
        "may_add_or_remove_champions": False,
        "must_keep_same_party_size": True,
        "must_use_each_end_party_champion_once": True,
        "candidates_are_not_all_required_in_end_party": True,
        "ai_selects_among_exported_externals": True,
        "fixed_champion_ids": sorted(locked),
        "main_dps_id": carry,
        "fixed_main_dps_id": carry,
        "main_dps_locked": isinstance(carry, int),
        "may_change_feats": False,
        "may_change_equipment": False,
        "may_change_main_dps": not isinstance(carry, int),
        "max_one_champion_per_permanent_seat": True,
        "only_active_positions": True,
        "permanent_seat_is_not_physical_position": True,
        "candidate_need_not_share_removed_champion_seat": True,
        "if_candidate_permanent_seat_occupied_must_remove_that_occupant": True,
        "if_candidate_permanent_seat_free_may_remove_any_unlocked": True,
        "do_not_derive_damage_multipliers_from_average_item_level": True,
        "no_account_damage_claim_without_equipment_effects": True,
        "no_hidden_tier_list_or_top_n": True,
        "no_swap_is_valid_outcome": True,
    }

    export["swap"] = {
        "mode": "one_owned_champion_swap_auto_roster",
        "candidate_selection": (
            "automatic_owned_external" if subset is None else "optional_advanced_subset"
        ),
        "max_swaps_per_proposal": 1,
        "max_proposals_suggested": 3,
        "fixed_champion_ids": sorted(locked),
        "main_dps_id": carry,
        "fixed_main_dps_id": carry,
        "current_party_ids": sorted(party_ids),
        "goal_id": (export.get("goal") or {}).get("id"),
        "app_goal": goal,
        "coverage": {
            "owned_known_count": n_owned,
            "party_count": n_party,
            "external_owned_count": n_external,
            "included_count": n_included,
            "included_allowed_count": n_allowed,
            "included_conditional_count": n_conditional,
            "excluded_count": n_excluded,
            "incomplete_count": n_incomplete,
            "data_gap_champion_count": len(set(data_gap_ids)),
            "coverage_complete": coverage_complete,
            "coverage_incomplete_reason": incomplete_reason,
            "accounts_reconciled": accounts_ok,
            "exclusion_reasons": exclusion_reasons or None,
            "note": (
                "Alle betrouwbaar owned champions buiten de party zijn "
                "geclassificeerd. Geen verborgen ranking of top-N. "
                "De AI kiest zelf relevante alternatieven uit de opgenomen set."
            ),
        },
        "excluded": excluded_out,
        "incomplete": incomplete_out,
        "classification": classification,
        "data_limits": [
            "Equipment-effecten ontbreken (equipment_status=unknown).",
            "Gemiddeld itemniveau is geen damagevermenigvuldiger.",
            "Bench specialisatiekeuzes/stacks kunnen unknown zijn.",
            "Vergelijking is kwalitatief (targeting/synergie), geen "
            "accountschadebewijs.",
            "other_party betekent niet automatisch beschikbaar of verboden.",
        ],
    }
    export["candidates"] = candidates_out

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
