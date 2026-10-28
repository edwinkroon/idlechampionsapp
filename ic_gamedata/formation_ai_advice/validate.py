"""Pre- and post-validation for formation AI advice (hard rules stay local)."""

from __future__ import annotations

import json
import re
from typing import Any

from ic_gamedata.formation_ai_advice.models import (
    SCHEMA_VERSION,
    AdviceSource,
    AssignmentProposal,
    ExpectedKeyBuff,
    FormationAdviceProposal,
    LocalValidationResult,
    SpecializationChoice,
)
from ic_gamedata.formation_ai_advice.schema import FORMATION_ADVICE_JSON_SCHEMA


def preflight_export(export_payload: dict[str, Any]) -> LocalValidationResult:
    """Validate export readiness before copying to chat."""
    champions = export_payload.get("champions") if isinstance(export_payload, dict) else None
    if not isinstance(champions, list) or not champions:
        return LocalValidationResult(
            status="invalid",
            errors=("Geen geselecteerde champions om te adviseren.",),
            can_apply=False,
        )

    readiness = export_payload.get("readiness") if isinstance(export_payload, dict) else None
    if isinstance(readiness, dict) and readiness.get("status") in (
        "ready",
        "ready_with_warnings",
        "blocked",
    ):
        issues = readiness.get("issues") or []
        errors = [
            str(i.get("message") or i.get("code") or "exportfout")
            for i in issues
            if isinstance(i, dict) and i.get("severity") == "error"
        ]
        warnings = [
            str(i.get("message") or i.get("code") or "waarschuwing")
            for i in issues
            if isinstance(i, dict) and i.get("severity") != "error"
        ]
        status = readiness["status"]
        if status == "blocked":
            return LocalValidationResult(
                status="invalid",
                errors=tuple(errors) or ("Export geblokkeerd: geometrie of party onbetrouwbaar.",),
                warnings=tuple(warnings),
                can_apply=False,
            )
        return LocalValidationResult(
            status="unchecked",
            errors=(),
            warnings=tuple(warnings),
            can_apply=False,
        )

    # Fallback for older exports without readiness block.
    errors: list[str] = []
    warnings: list[str] = []

    champions = export_payload.get("champions")
    formation = export_payload.get("formation") or {}
    if not isinstance(champions, list) or not champions:
        errors.append("Geen geselecteerde champions om te adviseren.")
        return LocalValidationResult(status="invalid", errors=tuple(errors), can_apply=False)

    hero_ids = []
    seats: list[int] = []
    for row in champions:
        if not isinstance(row, dict):
            errors.append("Ongeldige championrij in export.")
            continue
        cid = row.get("champion_id")
        if not isinstance(cid, int):
            errors.append("Onbekende of ontbrekende champion_id.")
            continue
        hero_ids.append(cid)
        seat = row.get("seat")
        if isinstance(seat, int):
            seats.append(seat)
        if row.get("current_position") is None:
            warnings.append(f"Champion {cid} heeft geen huidige positie.")

    if len(hero_ids) != len(set(hero_ids)):
        errors.append("Dubbele champion_id in selectie.")
    if seats and len(seats) != len(set(seats)):
        errors.append("Dubbele permanente seats in selectie.")

    # Champion-capable seats only — escorts stay in valid_position_ids.
    positions = (
        formation.get("active_position_ids")
        or [
            row.get("position_id")
            for row in (formation.get("slot_states") or [])
            if isinstance(row, dict) and row.get("placeability") == "placeable"
        ]
        or formation.get("valid_position_ids")
        or []
    )
    positions = [p for p in positions if isinstance(p, int)]
    current = formation.get("current_champion_by_position") or {}
    occupied = [pid for pid, hid in current.items() if hid is not None]
    if positions and len(hero_ids) != len(occupied):
        if len(hero_ids) > len(positions):
            errors.append(
                f"Aantal champions ({len(hero_ids)}) overschrijdt "
                f"plaatsbare posities ({len(positions)})."
            )
        else:
            warnings.append(
                f"Aantal champions ({len(hero_ids)}) wijkt af van bezette posities ({len(occupied)})."
            )

    goal = export_payload.get("goal") or {}
    if goal.get("id") == "custom_task" and not (
        (goal.get("parameters") or {}).get("task_description")
    ):
        errors.append("Specifieke taak vereist een taakomschrijving.")

    if not formation.get("adjacency_by_position"):
        errors.append("Adjacency-gegevens ontbreken; advies niet veilig te vragen.")

    if formation.get("geometry_issues"):
        errors.append("Geometrieproblemen in export; advies geblokkeerd.")

    if errors:
        return LocalValidationResult(
            status="invalid",
            errors=tuple(errors),
            warnings=tuple(warnings),
            can_apply=False,
        )
    return LocalValidationResult(
        status="unchecked",
        errors=(),
        warnings=tuple(warnings),
        can_apply=False,
    )


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(x) for x in value if x is not None)


def _normalize_proposal_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Map compact AI replies (placements/specializations) onto the full schema.

    Chat models often return a shorter shape than FORMATION_ADVICE_JSON_SCHEMA.
    Accept that and fill required empties so Plak can ingest the proposal.
    """
    out = dict(data)

    if "assignments" not in out and isinstance(out.get("placements"), list):
        specs_by_champ: dict[int, list[dict[str, Any]]] = {}
        for raw in out.get("specializations") or []:
            if not isinstance(raw, dict):
                continue
            try:
                cid = int(raw["champion_id"])
                specs_by_champ.setdefault(cid, []).append(
                    {
                        "group_id": str(raw.get("group_id") or ""),
                        "option_id": int(raw["option_id"]),
                        "reason": str(raw.get("reason") or ""),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        assignments: list[dict[str, Any]] = []
        for raw in out["placements"]:
            if not isinstance(raw, dict):
                continue
            try:
                cid = int(raw["champion_id"])
                assignments.append(
                    {
                        "position_id": int(raw["position_id"]),
                        "champion_id": cid,
                        "specialization_choices": specs_by_champ.get(cid, []),
                        "placement_reason": str(
                            raw.get("placement_reason") or raw.get("reason") or ""
                        ),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        out["assignments"] = assignments

    has_assignments = isinstance(out.get("assignments"), list) and bool(out["assignments"])

    if "status" not in out:
        # Compact replies with placements are usable proposals. Keep
        # needs_information only when there is nothing to place.
        if has_assignments:
            out["status"] = "proposal"
        elif out.get("conditional") is True:
            out["status"] = "needs_information"
        else:
            out["status"] = "needs_information"

    if "summary" not in out:
        cond = out.get("condition")
        if isinstance(cond, str) and cond.strip():
            out["summary"] = cond.strip()
        else:
            out["summary"] = "Voorstel uit chat."

    for key in (
        "expected_key_buffs",
        "assumptions",
        "missing_information",
        "warnings",
        "source_refs",
    ):
        if key not in out:
            out[key] = []

    if out.get("conditional") is True:
        cond = str(out.get("condition") or "").strip()
        if cond:
            warnings = [str(w) for w in (out.get("warnings") or []) if w is not None]
            if cond not in warnings:
                warnings.append(cond)
            out["warnings"] = warnings

    return out


def parse_proposal_json(
    text: str,
    *,
    expected_request_id: str,
) -> tuple[FormationAdviceProposal | None, list[str]]:
    errors: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"Ongeldige JSON: {exc}"]

    if not isinstance(data, dict):
        return None, ["Antwoord is geen JSON-object."]

    data = _normalize_proposal_payload(data)

    for key in FORMATION_ADVICE_JSON_SCHEMA["required"]:
        if key not in data:
            errors.append(f"Ontbrekend veld: {key}")
    if errors:
        return None, errors

    status = data.get("status")
    if status not in ("proposal", "needs_information", "no_valid_proposal"):
        return None, [f"Ongeldige status: {status!r}"]

    if str(data.get("request_id")) != expected_request_id:
        errors.append(
            f"request_id komt niet overeen (verwacht {expected_request_id}, "
            f"kreeg {data.get('request_id')!r})."
        )

    schema_version = str(data.get("schema_version") or "")
    if schema_version and schema_version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        errors.append(
            f"Niet-ondersteunde schema_version: {schema_version} "
            f"(verwacht major {SCHEMA_VERSION.split('.')[0]}.x)."
        )

    assignments: list[AssignmentProposal] = []
    for raw in data.get("assignments") or []:
        if not isinstance(raw, dict):
            errors.append("Ongeldige assignment.")
            continue
        specs: list[SpecializationChoice] = []
        for sc in raw.get("specialization_choices") or []:
            if not isinstance(sc, dict):
                continue
            try:
                specs.append(
                    SpecializationChoice(
                        group_id=str(sc.get("group_id") or ""),
                        option_id=int(sc["option_id"]),
                        reason=str(sc.get("reason") or ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                errors.append("Ongeldige specialization_choice.")
        try:
            assignments.append(
                AssignmentProposal(
                    position_id=int(raw["position_id"]),
                    champion_id=int(raw["champion_id"]),
                    specialization_choices=tuple(specs),
                    placement_reason=str(raw.get("placement_reason") or ""),
                )
            )
        except (KeyError, TypeError, ValueError):
            errors.append("Ongeldige assignment (position/champion).")

    buffs: list[ExpectedKeyBuff] = []
    for raw in data.get("expected_key_buffs") or []:
        if not isinstance(raw, dict):
            continue
        try:
            ability_raw = raw.get("ability_id")
            ability_id = int(ability_raw) if ability_raw is not None else None
            buffs.append(
                ExpectedKeyBuff(
                    source_champion_id=int(raw["source_champion_id"]),
                    target_champion_id=int(raw["target_champion_id"]),
                    explanation=str(raw.get("explanation") or ""),
                    ability_id=ability_id,
                )
            )
        except (KeyError, TypeError, ValueError):
            errors.append("Ongeldige expected_key_buff.")

    if errors:
        return None, errors

    proposal = FormationAdviceProposal(
        schema_version=schema_version or SCHEMA_VERSION,
        request_id=str(data.get("request_id")),
        status=status,
        summary=str(data.get("summary") or ""),
        assignments=tuple(assignments),
        expected_key_buffs=tuple(buffs),
        assumptions=_as_str_tuple(data.get("assumptions")),
        missing_information=_as_str_tuple(data.get("missing_information")),
        warnings=_as_str_tuple(data.get("warnings")),
        source_refs=_as_str_tuple(data.get("source_refs")),
    )
    return proposal, []


def _option_index(export_payload: dict[str, Any]) -> dict[int, dict[str, set[int]]]:
    """champion_id → group_id → option_ids."""
    out: dict[int, dict[str, set[int]]] = {}
    for row in export_payload.get("champions") or []:
        if not isinstance(row, dict):
            continue
        cid = row.get("champion_id")
        if not isinstance(cid, int):
            continue
        groups: dict[str, set[int]] = {}
        for g in row.get("specialization_groups") or []:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("group_id") or "")
            opts = set()
            for opt in g.get("options") or []:
                if isinstance(opt, dict) and isinstance(opt.get("option_id"), int):
                    opts.add(opt["option_id"])
            groups[gid] = opts
        out[cid] = groups
    return out


def _option_owner_index(export_payload: dict[str, Any]) -> dict[int, int]:
    """option_id → owning champion_id (from export only; no global name lookup)."""
    owners: dict[int, int] = {}
    for row in export_payload.get("champions") or []:
        if not isinstance(row, dict):
            continue
        cid = row.get("champion_id")
        if not isinstance(cid, int):
            continue
        for g in row.get("specialization_groups") or []:
            if not isinstance(g, dict):
                continue
            for opt in g.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                oid = opt.get("option_id")
                if isinstance(oid, int):
                    owners[oid] = cid
    return owners


def validate_proposal_against_export(
    proposal: FormationAdviceProposal,
    export_payload: dict[str, Any],
    *,
    api_sources: tuple[AdviceSource, ...],
    formation_fingerprint_at_request: str,
    current_formation_fingerprint: str,
) -> LocalValidationResult:
    """Hard local checks after AI response. AI cannot self-declare validated."""
    errors: list[str] = []
    warnings: list[str] = list(proposal.warnings)
    unchecked: list[str] = []

    if formation_fingerprint_at_request != current_formation_fingerprint:
        return LocalValidationResult(
            status="stale",
            errors=("Formatie of gamegegevens zijn gewijzigd sinds de aanvraag.",),
            warnings=tuple(warnings),
            unchecked_mechanics=(),
            can_apply=False,
        )

    if proposal.status != "proposal":
        return LocalValidationResult(
            status="needs_information" if proposal.status == "needs_information" else "invalid",
            errors=tuple(proposal.missing_information)
            or (f"AI-status is {proposal.status}; geen toepasbaar voorstel.",),
            warnings=tuple(warnings),
            can_apply=False,
        )

    champions = export_payload.get("champions") or []
    # ADVICE_REQUEST uses party[].id; legacy export uses champions[].champion_id.
    party_rows = export_payload.get("party") if isinstance(export_payload.get("party"), list) else []
    selected_ids = {
        row["champion_id"]
        for row in champions
        if isinstance(row, dict) and isinstance(row.get("champion_id"), int)
    }
    if not selected_ids:
        selected_ids = {
            int(row["id"])
            for row in party_rows
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        }
    permanent_seat = {
        row["champion_id"]: row.get("seat")
        for row in champions
        if isinstance(row, dict) and isinstance(row.get("champion_id"), int)
    }
    for row in party_rows:
        if isinstance(row, dict) and isinstance(row.get("id"), int):
            permanent_seat.setdefault(int(row["id"]), row.get("seat"))
    # Per-champion locks from ADVICE_REQUEST party rows (key_champion etc.).
    must_remain: dict[int, dict[str, Any]] = {}
    for row in party_rows:
        if not isinstance(row, dict):
            continue
        hid = row.get("id")
        if not isinstance(hid, int):
            continue
        if row.get("must_remain_in_party") or row.get("replacement_locked") or row.get("locked"):
            must_remain[hid] = row
    for row in champions:
        if not isinstance(row, dict):
            continue
        hid = row.get("champion_id")
        if not isinstance(hid, int):
            continue
        if row.get("must_remain_in_party") or row.get("replacement_locked"):
            must_remain.setdefault(hid, row)
    formation = export_payload.get("formation") or {}
    geometry = (
        export_payload.get("geometry")
        if isinstance(export_payload.get("geometry"), dict)
        else {}
    )
    valid_positions = set(
        formation.get("valid_position_ids")
        or formation.get("active_position_ids")
        or geometry.get("valid_position_ids")
        or []
    )
    if not valid_positions:
        valid_positions = {
            int(k)
            for k, v in (formation.get("current_champion_by_position") or {}).items()
            if v is not None
        }

    slot_states = (
        formation.get("slot_states")
        if isinstance(formation.get("slot_states"), list)
        else None
    )
    if not slot_states and isinstance(geometry.get("slot_states"), list):
        slot_states = geometry.get("slot_states")
    from ic_gamedata.formation_ai_advice.slot_states import (
        format_position_ref,
        slot_state_by_position,
    )

    states_by_id = slot_state_by_position(slot_states)
    # Current champion positions (reassignments stay allowed on those seats).
    current_champion_positions: set[int] = set()
    for row in formation.get("positions") or []:
        if isinstance(row, dict) and isinstance(row.get("position_id"), int):
            if row.get("current_champion_id") is not None:
                current_champion_positions.add(int(row["position_id"]))
    for row in geometry.get("occupied") or []:
        if isinstance(row, dict) and isinstance(row.get("id"), int):
            if row.get("champion_id") is not None:
                current_champion_positions.add(int(row["id"]))
    # current_champion_by_position is position_id → hero_id.
    for key, hid in (formation.get("current_champion_by_position") or {}).items():
        if hid is None:
            continue
        try:
            current_champion_positions.add(int(key))
        except (TypeError, ValueError):
            pass

    assigned_heroes = [a.champion_id for a in proposal.assignments]
    assigned_positions = [a.position_id for a in proposal.assignments]
    assigned_pos_by_hero = {
        a.champion_id: a.position_id for a in proposal.assignments
    }

    # Replacement-locked / must-remain champions must appear in every full proposal.
    # Global may_replace_champions must not override these per-champion locks.
    constraints = (
        export_payload.get("constraints")
        if isinstance(export_payload.get("constraints"), dict)
        else {}
    )
    may_replace = bool(constraints.get("may_replace_champions"))
    for hid, lock_row in must_remain.items():
        if lock_row.get("must_remain_in_party") or lock_row.get("replacement_locked"):
            if hid not in set(assigned_heroes):
                errors.append(
                    f"Verplichte champion {hid} ontbreekt in voorstel "
                    f"(replacement_locked; may_replace={may_replace})."
                )
            locked_pos = lock_row.get("locked_position_id")
            if (
                lock_row.get("position_locked")
                and isinstance(locked_pos, int)
                and hid in assigned_pos_by_hero
                and assigned_pos_by_hero[hid] != locked_pos
            ):
                errors.append(
                    f"Champion {hid} is position-locked op technische positie "
                    f"{locked_pos}; voorstel heeft {assigned_pos_by_hero[hid]}."
                )

    if set(assigned_heroes) != selected_ids and not may_replace:
        missing = selected_ids - set(assigned_heroes)
        extra = set(assigned_heroes) - selected_ids
        if missing:
            errors.append(f"Ontbrekende champions in voorstel: {sorted(missing)}")
        if extra:
            errors.append(f"Onbekende/extra champions in voorstel: {sorted(extra)}")
    elif may_replace:
        # Swaps allowed, but still reject dropping replacement-locked members
        # (checked above) and unknown ids outside owned scope when provided.
        extra = set(assigned_heroes) - selected_ids
        owned = export_payload.get("roster_eligibility") or {}
        # Soft: extras are OK for swap mode; hard locks already enforced.
        _ = (extra, owned)
    if len(assigned_heroes) != len(set(assigned_heroes)):
        errors.append("Dubbele champion in voorstel.")
    if len(assigned_positions) != len(set(assigned_positions)):
        errors.append("Dubbele positie in voorstel.")
    for pos in assigned_positions:
        if valid_positions and pos not in valid_positions:
            errors.append(f"Onbekende of niet-actieve positie: {pos}")
            continue
        state = states_by_id.get(int(pos))
        if state is None:
            # Legacy exports without slot_states: missing placeability ≠ free.
            # Only reject when we know the seat is outside the placeable set.
            active = set(
                formation.get("active_position_ids")
                or geometry.get("available_position_ids")
                or []
            )
            blocked = set(
                formation.get("blocked_position_ids")
                or geometry.get("blocked_position_ids")
                or []
            )
            if blocked and pos in blocked:
                errors.append(
                    f"Plaatsing geweigerd op "
                    f"{format_position_ref(pos, reason='bevestigde blokkade')}."
                )
            elif active and pos not in active and pos not in current_champion_positions:
                errors.append(
                    f"Plaatsing geweigerd op "
                    f"{format_position_ref(pos, reason='geen plaatsbare championplek')}."
                )
            continue
        placeability = state.get("placeability")
        occupancy = state.get("occupancy")
        display = state.get("display_position")
        reason = state.get("reason")
        # Key-champion force_slot may show as npc/blocked while empty; the
        # replacement-locked champion whose locked_position_id equals this seat
        # is the only allowed placement onto that overlay.
        key_slot_exception = False
        if placeability == "blocked" or occupancy in ("npc", "escort", "object"):
            for asn in proposal.assignments:
                if asn.position_id != pos:
                    continue
                lock_row = must_remain.get(asn.champion_id) or {}
                locked_pos = lock_row.get("locked_position_id")
                blocker = state.get("blocker") if isinstance(state.get("blocker"), dict) else {}
                btype = str(blocker.get("type") or "").strip().casefold()
                source = str(state.get("source") or "").casefold()
                if (
                    lock_row.get("position_locked")
                    and isinstance(locked_pos, int)
                    and locked_pos == pos
                    and (
                        btype in ("npc", "key_champion")
                        or "key_champion" in source
                    )
                ):
                    key_slot_exception = True
                    break
        if (
            (placeability == "blocked" or occupancy in ("npc", "escort", "object"))
            and not key_slot_exception
        ):
            errors.append(
                "Plaatsing geweigerd op "
                + format_position_ref(
                    pos,
                    display_position=display if isinstance(display, str) else None,
                    reason=str(reason or f"bezet/geblokkeerd ({occupancy})"),
                )
            )
        elif placeability == "unknown" and pos not in current_champion_positions:
            errors.append(
                "Automatische plaatsing geweigerd op "
                + format_position_ref(
                    pos,
                    display_position=display if isinstance(display, str) else None,
                    reason=str(
                        reason
                        or "plaatsbaarheid unknown — geen bevestigde vrije plek"
                    ),
                )
            )

    seat_owners: dict[int, int] = {}
    for hid in assigned_heroes:
        seat = permanent_seat.get(hid)
        if not isinstance(seat, int):
            continue
        if seat in seat_owners:
            errors.append(
                f"Dubbele permanente seat {seat} "
                f"(champions {seat_owners[seat]} en {hid})."
            )
        else:
            seat_owners[seat] = hid

    option_index = _option_index(export_payload)
    option_owners = _option_owner_index(export_payload)
    for asn in proposal.assignments:
        groups = option_index.get(asn.champion_id, {})
        seen_groups: set[str] = set()
        for choice in asn.specialization_choices:
            if choice.group_id in seen_groups:
                errors.append(
                    f"Dubbele specialisatiegroep {choice.group_id} "
                    f"voor champion {asn.champion_id}."
                )
            seen_groups.add(choice.group_id)
            owner = option_owners.get(choice.option_id)
            if owner is not None and owner != asn.champion_id:
                errors.append(
                    f"Specialisatie-optie {choice.option_id} hoort bij champion {owner}, "
                    f"niet bij champion {asn.champion_id} "
                    f"(groep {choice.group_id!r})."
                )
                continue
            allowed = groups.get(choice.group_id)
            if allowed is None:
                errors.append(
                    f"Onbekende specialisatiegroep {choice.group_id!r} "
                    f"voor champion {asn.champion_id}."
                )
            elif choice.option_id not in allowed:
                errors.append(
                    f"Ongeldige specialisatie-optie {choice.option_id} "
                    f"in groep {choice.group_id} voor champion {asn.champion_id}."
                )

    api_ids = {s.source_id for s in api_sources}
    for ref in proposal.source_refs:
        if ref not in api_ids:
            errors.append(f"Bronverwijzing zonder bestaande API-bron: {ref!r}")

    goal = export_payload.get("goal") or {}
    if goal.get("restrictions_checked_by_app"):
        unchecked.append(
            "Adventure-restricties: gemarkeerd als door app gecontroleerd in export; "
            "hercontrole bij apply gebeurt met live payload waar mogelijk."
        )
    else:
        unchecked.append(
            "Adventure-restricties niet door de app gecontroleerd "
            "(onbekend ≠ geen restrictie)."
        )

    adjacency = formation.get("adjacency_by_position") or {}
    if adjacency:
        seat_by_hero = {a.champion_id: a.position_id for a in proposal.assignments}

        def _adjacent(a: int, b: int) -> bool:
            sa = seat_by_hero.get(a)
            sb = seat_by_hero.get(b)
            if sa is None or sb is None:
                return False
            return sb in set(adjacency.get(str(sa), []))

        for buff in proposal.expected_key_buffs:
            if not _adjacent(buff.source_champion_id, buff.target_champion_id):
                unchecked.append(
                    f"Buff {buff.source_champion_id}→{buff.target_champion_id}: "
                    "niet-adjacent of niet lokaal gecontroleerde mechanic."
                )
    else:
        unchecked.append("Geen adjacency voor lokale buffcontrole.")

    unchecked.append(
        "Niet-ondersteunde buffmechanics worden niet als geldig behandeld "
        "(geen schijnzekerheid)."
    )

    if errors:
        return LocalValidationResult(
            status="invalid",
            errors=tuple(errors),
            warnings=tuple(warnings),
            unchecked_mechanics=tuple(unchecked),
            can_apply=False,
        )
    return LocalValidationResult(
        status="valid",
        errors=(),
        warnings=tuple(warnings),
        unchecked_mechanics=tuple(unchecked),
        can_apply=True,
    )


_POSITIONAL_TOKENS = frozenset(
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


def validate_advice_semantics(advice: dict[str, Any]) -> list[dict[str, Any]]:
    """Invariant checks on the advice projection before clipboard copy.

    Returns concrete gap rows (not a generic prose regex). Unresolved conflicts
    stay as gaps — they do not invent corrected magnitudes.
    """
    gaps: list[dict[str, Any]] = []
    effects = advice.get("effects") if isinstance(advice, dict) else None
    if not isinstance(effects, dict):
        return gaps

    for effect_ref, effect in effects.items():
        if not isinstance(effect, dict):
            continue
        sem = effect.get("semantics") if isinstance(effect.get("semantics"), dict) else {}
        scope = sem.get("scope")
        recipients = (
            sem.get("recipients") if isinstance(sem.get("recipients"), dict) else {}
        )
        targets = recipients.get("targets") if isinstance(recipients, dict) else None
        target_list = targets if isinstance(targets, list) else []

        # Duplicate canonical magnitude fields.
        if effect.get("value") is not None and effect.get("values"):
            single = effect.get("value")
            multi = effect.get("values")
            if (
                isinstance(single, dict)
                and isinstance(multi, list)
                and len(multi) == 1
                and multi[0] == single
            ):
                gaps.append(
                    {
                        "code": "duplicate_canonical_value",
                        "message": (
                            f"Effect {effect_ref} has identical value and values."
                        ),
                        "affects_decision": False,
                    }
                )

        # Owner-scope must not claim external positional recipients.
        if scope == "owner" and any(t in _POSITIONAL_TOKENS for t in target_list):
            if target_list not in (["self"], ["s"]):
                gaps.append(
                    {
                        "code": "owner_scope_positional_recipients",
                        "message": (
                            f"Effect {effect_ref}: owner scope with positional "
                            f"recipients {target_list}."
                        ),
                        "affects_decision": True,
                        "decision": "placement_advice",
                    }
                )

        # BUD-seconds mislabeled as percent.
        for row in _iter_magnitude_rows(effect):
            if row.get("name") == "additional_bud_damage" or row.get(
                "effect_key"
            ) == "base_attack_deal_bonus_damage":
                if row.get("unit") == "percent" or row.get("meaning") == "percent":
                    gaps.append(
                        {
                            "code": "bud_seconds_labeled_percent",
                            "message": (
                                f"Effect {effect_ref}: BUD-seconds labeled as percent."
                            ),
                            "affects_decision": True,
                            "decision": "numeric_comparison",
                        }
                    )

        subeffects = sem.get("subeffects") if isinstance(sem.get("subeffects"), list) else []
        # Opposing magic predicates flattened into one top-level filter.
        filters = []
        for sub in subeffects:
            if not isinstance(sub, dict):
                continue
            rec = sub.get("recipients") if isinstance(sub.get("recipients"), dict) else {}
            filt = rec.get("filter") if isinstance(rec, dict) else None
            if isinstance(filt, dict) and filt.get("requires_magic_attack") is not None:
                filters.append(filt.get("requires_magic_attack"))
        if True in filters and False in filters:
            top_pred = sem.get("predicate")
            top_rec = recipients
            # Conflict if top-level still claims one shared predicate/recipients.
            if top_pred or (
                isinstance(top_rec, dict)
                and (top_rec.get("targets") or top_rec.get("tags"))
            ):
                gaps.append(
                    {
                        "code": "merged_opposing_predicates",
                        "message": (
                            f"Effect {effect_ref}: magic and non-magic subeffects "
                            "share a flattened top-level predicate/recipients."
                        ),
                        "affects_decision": True,
                        "decision": "placement_advice",
                    }
                )

        # Self vs other health under one incorrect recipient set.
        self_health = False
        other_health = False
        for sub in subeffects:
            if not isinstance(sub, dict):
                continue
            op = str(sub.get("effect_key") or "")
            rec = sub.get("recipients") if isinstance(sub.get("recipients"), dict) else {}
            t = rec.get("targets") if isinstance(rec, dict) else None
            if "health" in op and t == ["self"]:
                self_health = True
            if "health" in op and t == ["other"]:
                other_health = True
        if self_health and other_health and isinstance(recipients, dict):
            top_t = recipients.get("targets")
            if top_t in (["self"], ["other"], ["all"]):
                gaps.append(
                    {
                        "code": "merged_self_other_health",
                        "message": (
                            f"Effect {effect_ref}: self and other health subeffects "
                            f"collapsed to recipients {top_t}."
                        ),
                        "affects_decision": True,
                        "decision": "placement_advice",
                    }
                )

        # Placeholder text vs structured binding: own health per Toughness must
        # not display the health-sharing magnitude.
        text = str(effect.get("mechanical_text") or "")
        if "toughness" in text.casefold():
            health_mult = None
            health_share = None
            for sub in subeffects:
                if not isinstance(sub, dict):
                    continue
                op = str(sub.get("effect_key") or "")
                params = sub.get("parameters") or []
                for p in params if isinstance(params, list) else []:
                    if not isinstance(p, dict):
                        continue
                    if op == "health_mult" and p.get("value") is not None:
                        health_mult = p.get("value")
                    if (
                        op == "increase_health_by_source_percent"
                        and p.get("value") is not None
                    ):
                        health_share = p.get("value")
            if (
                health_mult is not None
                and health_share is not None
                and float(health_mult) != float(health_share)
            ):
                share_txt = (
                    f"{int(health_share)}"
                    if float(health_share) == int(health_share)
                    else f"{health_share:g}"
                )
                if re.search(
                    rf"increased by {re.escape(share_txt)}%\s+for each\s+Toughness",
                    text,
                    flags=re.IGNORECASE,
                ):
                    gaps.append(
                        {
                            "code": "phase_two_placeholder_mismatch",
                            "message": (
                                f"Effect {effect_ref}: own health text appears to use "
                                f"health-sharing magnitude {health_share} instead of "
                                f"health_mult {health_mult}."
                            ),
                            "affects_decision": True,
                            "decision": "numeric_comparison",
                        }
                    )

    # Dangling effect_ref from champions.
    for champ in advice.get("champions") or []:
        if not isinstance(champ, dict):
            continue
        refs: list[str] = []
        for ab in champ.get("abilities") or []:
            if isinstance(ab, dict) and ab.get("effect_ref"):
                refs.append(str(ab["effect_ref"]))
        for feat in champ.get("active_feats") or []:
            if isinstance(feat, dict) and feat.get("effect_ref"):
                refs.append(str(feat["effect_ref"]))
        for group in champ.get("specialization_groups") or []:
            if not isinstance(group, dict):
                continue
            for opt in group.get("options") or []:
                if isinstance(opt, dict) and opt.get("effect_ref"):
                    refs.append(str(opt["effect_ref"]))
        for ref in refs:
            if ref not in effects:
                gaps.append(
                    {
                        "code": "missing_effect_ref",
                        "message": f"Champion references missing effect_ref {ref}.",
                        "affected_champion_ids": [champ.get("champion_id")],
                        "affects_decision": True,
                    }
                )
    return gaps


def _iter_magnitude_rows(effect: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(effect.get("value"), dict):
        rows.append(effect["value"])
    for row in effect.get("values") or []:
        if isinstance(row, dict):
            rows.append(row)
    sem = effect.get("semantics") if isinstance(effect.get("semantics"), dict) else {}
    for sub in sem.get("subeffects") or []:
        if not isinstance(sub, dict):
            continue
        for row in sub.get("parameters") or []:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def link_sources(
    proposal: FormationAdviceProposal,
    api_sources: tuple[AdviceSource, ...],
) -> FormationAdviceProposal:
    """Attach only validated API sources referenced by source_refs."""
    by_id = {s.source_id: s for s in api_sources}
    linked = tuple(by_id[ref] for ref in proposal.source_refs if ref in by_id)
    return FormationAdviceProposal(
        schema_version=proposal.schema_version,
        request_id=proposal.request_id,
        status=proposal.status,
        summary=proposal.summary,
        assignments=proposal.assignments,
        expected_key_buffs=proposal.expected_key_buffs,
        assumptions=proposal.assumptions,
        missing_information=proposal.missing_information,
        warnings=proposal.warnings,
        source_refs=proposal.source_refs,
        sources=linked,
    )
