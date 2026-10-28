"""Independent validation before compact advice export."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"  # error | warning
    ids: list[int] | None = None


def _issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    """Compact serialisation: one row per code, optional shared ``ids``."""
    row: dict[str, Any] = {
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
    }
    if issue.ids:
        row["ids"] = sorted({int(i) for i in issue.ids})
    return row


def _group_issues_for_export(
    issues: list[ValidationIssue],
) -> list[dict[str, Any]]:
    """Collapse repeated per-champion messages into one row with ``ids``."""
    order: list[tuple[str, str]] = []
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for issue in issues:
        key = (issue.code, issue.severity)
        if key not in buckets:
            order.append(key)
            buckets[key] = _issue_to_dict(issue)
            continue
        existing = buckets[key]
        ids = list(existing.get("ids") or [])
        if issue.ids:
            ids.extend(int(i) for i in issue.ids)
        # Recover an id embedded in older per-champion messages.
        if not issue.ids:
            for token in issue.message.replace(",", " ").split():
                if token.isdigit():
                    ids.append(int(token))
                    break
        if ids:
            existing["ids"] = sorted(set(ids))
    return [buckets[k] for k in order]


@dataclass
class ExportValidationResult:
    """Validation outcome with explicit layers.

    - ``validation_ran``: checks were executed
    - ``structural_ok``: document/party structure is consistent
    - ``party_restriction_ok``: current party is demonstrably legal under
      available rules (presence alone is not proof; unresolved
      presence_conflicts make this false). Does **not** imply every swap
      candidate is eligible.
    - ``swap_candidates_restriction_ok``: included_allowed swap candidates are
      consistent with roster eligibility (separate from party)
    - ``advice_ready``: suitable for unconditional formation advice
      (requires structural_ok and party_restriction_ok). Replaceable
      contested members may still allow conditional proposals that exclude
      them; that is readiness.placement_advice=partial, not advice_ready.
    - ``ok``: alias for ``advice_ready`` (normal copy path)
    """

    validation_ran: bool
    structural_ok: bool
    party_restriction_ok: bool
    advice_ready: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    swap_candidates_restriction_ok: bool = True

    @property
    def ok(self) -> bool:
        return self.advice_ready

    @property
    def validated(self) -> bool:
        return self.validation_ran

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary_nl(self) -> str:
        if self.advice_ready and not self.warnings:
            return "Validatie OK — adviesklaar."
        parts: list[str] = []
        if self.validation_ran:
            parts.append(
                f"structural_ok={self.structural_ok}, "
                f"party_restriction_ok={self.party_restriction_ok}, "
                f"swap_candidates_restriction_ok="
                f"{self.swap_candidates_restriction_ok}, "
                f"advice_ready={self.advice_ready}."
            )
        for row in _group_issues_for_export(self.issues):
            msg = str(row.get("message") or "")
            ids = row.get("ids") or []
            if ids:
                msg = f"{msg} ids={ids}"
            parts.append(f"[{row.get('severity')}] {msg}")
        return " ".join(parts)


def _owned_id_set(payload: dict[str, Any]) -> set[int]:
    from ic_gamedata.party_advisor_formation import _owned_heroes

    return {hid for hid, *_ in _owned_heroes(payload)}


def _as_geo_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _validate_geometry_layout_consistency(
    geometry: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    """Validate full/current geometry when present; thin ref stays lightweight."""
    if geometry.get("layout_incomplete"):
        missing = geometry.get("missing_layout_fields") or []
        detail = (
            f" Ontbrekend: {', '.join(str(x) for x in missing[:12])}."
            if missing
            else ""
        )
        issues.append(
            ValidationIssue(
                "geometry_layout_incomplete",
                "Actuele formatielayout is incompleet; plaatsingsadvies niet "
                f"gereed.{detail} Nieuwe basissnapshot of formatie-verversing "
                "nodig. Roster-eligibility blijft apart beoordeelbaar.",
            )
        )
        return

    # Thin verified ref: layout lives on BASE_SNAPSHOT.
    if geometry.get("ref") and not geometry.get("positions"):
        if geometry.get("overrides_base_snapshot_geometry"):
            issues.append(
                ValidationIssue(
                    "geometry_ref_with_override_flag",
                    "geometry.ref mag niet samen met "
                    "overrides_base_snapshot_geometry voorkomen.",
                )
            )
        return

    positions = geometry.get("positions")
    if not isinstance(positions, list) or not positions:
        # No full layout in request — nothing further to check here.
        return

    valid_raw = geometry.get("valid_position_ids") or []
    valid = {
        vid
        for vid in (_as_geo_int(x) for x in valid_raw)
        if vid is not None
    }
    blocked = {
        vid
        for vid in (
            _as_geo_int(x) for x in (geometry.get("blocked_position_ids") or [])
        )
        if vid is not None
    }
    for row in geometry.get("slot_states") or []:
        if isinstance(row, dict) and row.get("placeability") == "blocked":
            pid = _as_geo_int(row.get("position_id"))
            if pid is not None:
                blocked.add(pid)
    pos_by_id: dict[int, dict[str, Any]] = {}
    display_labels: list[str] = []
    for row in positions:
        if not isinstance(row, dict):
            continue
        pid = _as_geo_int(row.get("id"))
        if pid is None:
            issues.append(
                ValidationIssue(
                    "geometry_position_missing_id",
                    "Geometry.positions-rij zonder technische id.",
                )
            )
            continue
        if pid in pos_by_id:
            issues.append(
                ValidationIssue(
                    "geometry_duplicate_position_record",
                    f"Positie {pid} heeft meer dan één layoutrecord.",
                    ids=[pid],
                )
            )
        pos_by_id[pid] = row
        required_fields = ("column", "row")
        if pid not in blocked:
            required_fields = (
                "column",
                "row",
                "display_column",
                "display_slot",
                "display_position",
            )
        for field in required_fields:
            if row.get(field) is None:
                issues.append(
                    ValidationIssue(
                        "geometry_position_incomplete",
                        f"Positie {pid} mist layoutveld {field}.",
                        ids=[pid],
                    )
                )
        label = row.get("display_position")
        if isinstance(label, str) and label:
            display_labels.append(label)

    if valid:
        for pid in sorted(valid):
            if pid not in pos_by_id:
                issues.append(
                    ValidationIssue(
                        "geometry_missing_position_record",
                        f"Actieve positie {pid} heeft geen layoutrecord.",
                        ids=[pid],
                    )
                )
        for pid in sorted(pos_by_id):
            if pid not in valid:
                issues.append(
                    ValidationIssue(
                        "geometry_inactive_position_record",
                        f"Layoutrecord voor inactieve positie {pid}.",
                        ids=[pid],
                        severity="warning",
                    )
                )

    if len(display_labels) != len(set(display_labels)):
        issues.append(
            ValidationIssue(
                "geometry_duplicate_display_position",
                "Displayposities zijn niet uniek.",
            )
        )

    # Occupied must reference technical valid positions when known.
    for row in geometry.get("occupied") or []:
        if not isinstance(row, dict):
            continue
        oid = _as_geo_int(row.get("id"))
        if oid is None:
            continue
        if valid and oid not in valid:
            issues.append(
                ValidationIssue(
                    "occupied_not_active",
                    f"Bezetting op positie {oid} die niet in valid_position_ids staat.",
                    ids=[oid],
                )
            )

    slot_states = geometry.get("slot_states")
    if isinstance(slot_states, list) and slot_states:
        from ic_gamedata.formation_ai_advice.slot_states import (
            derive_position_id_lists,
            validate_slot_states,
        )

        for msg in validate_slot_states(
            slot_states,
            valid_position_ids=valid,
            occupied=geometry.get("occupied"),
        ):
            issues.append(
                ValidationIssue("slot_state_invalid", msg)
            )
        # Derived lists must match slot_states (single source of truth).
        derived = derive_position_id_lists(slot_states)
        for key in (
            "blocked_position_ids",
            "available_position_ids",
            "unknown_placeability_position_ids",
        ):
            exported = {
                _as_geo_int(x)
                for x in (geometry.get(key) or [])
                if _as_geo_int(x) is not None
            }
            expected = set(derived[key])
            if geometry.get(key) is not None and exported != expected:
                issues.append(
                    ValidationIssue(
                        "slot_state_derived_mismatch",
                        f"geometry.{key} komt niet overeen met slot_states.",
                    )
                )

    adj = geometry.get("adjacency")
    if isinstance(adj, dict) and valid:
        for key, neighbors in adj.items():
            kid = _as_geo_int(key)
            if kid is not None and kid not in valid:
                issues.append(
                    ValidationIssue(
                        "adjacency_inactive_key",
                        f"Adjacency-sleutel {kid} is geen geldige technische positie.",
                        ids=[kid],
                    )
                )
            if not isinstance(neighbors, (list, tuple)):
                continue
            for n in neighbors:
                nid = _as_geo_int(n)
                if nid is None:
                    continue
                if nid not in valid:
                    issues.append(
                        ValidationIssue(
                            "adjacency_edge_to_inactive",
                            f"Adjacency {key} → {nid} wijst naar ongeldige positie.",
                            ids=[nid],
                        )
                    )
                if kid is not None and nid == kid:
                    issues.append(
                        ValidationIssue(
                            "adjacency_self_loop",
                            f"Self-loop op positie {kid}.",
                            ids=[kid],
                        )
                    )


def validate_advice_request_export(
    *,
    payload: dict[str, Any],
    request: dict[str, Any],
    snapshot_id: str | None,
    exported_snapshot_id: str | None,
) -> ExportValidationResult:
    """Validate a compact ADVICE_REQUEST against live payload invariants."""
    issues: list[ValidationIssue] = []
    owned = _owned_id_set(payload)
    party = [p for p in (request.get("party") or []) if isinstance(p, dict)]
    party_ids = [
        int(p["id"]) for p in party if isinstance(p.get("id"), int)
    ]
    goal = request.get("goal") if isinstance(request.get("goal"), dict) else {}
    readiness = (
        request.get("readiness") if isinstance(request.get("readiness"), dict) else {}
    )

    # Snapshot reference consistency.
    meta = request.get("meta") if isinstance(request.get("meta"), dict) else {}
    ref = meta.get("snapshot_ref") if isinstance(meta.get("snapshot_ref"), dict) else {}
    req_snap = ref.get("snapshot_id")
    if not snapshot_id and not req_snap:
        issues.append(
            ValidationIssue(
                "missing_snapshot_ref",
                "Geen snapshotreferentie in de aanvraag.",
            )
        )
    if exported_snapshot_id and req_snap and str(req_snap) != str(exported_snapshot_id):
        issues.append(
            ValidationIssue(
                "snapshot_ref_mismatch",
                "Aanvraag verwijst niet naar de laatst geëxporteerde snapshot.",
            )
        )
    if snapshot_id and req_snap and str(req_snap) != str(snapshot_id):
        issues.append(
            ValidationIssue(
                "snapshot_ref_internal_mismatch",
                "Interne snapshot_id komt niet overeen met snapshot_ref.",
            )
        )

    # Party ownership + uniqueness.
    if len(party_ids) != len(set(party_ids)):
        issues.append(
            ValidationIssue(
                "duplicate_champion_id",
                "Dubbele champion-ID in de party.",
            )
        )
    not_owned = [hid for hid in party_ids if hid not in owned]
    if not_owned:
        issues.append(
            ValidationIssue(
                "party_not_owned",
                "Party-champions staan niet als owned in de payload.",
                ids=not_owned,
            )
        )

    # Permanent seats: at most one champion per seat.
    seats: dict[int, list[int]] = {}
    for row in party:
        hid = row.get("id")
        seat = row.get("seat")
        if isinstance(hid, int) and isinstance(seat, int):
            seats.setdefault(seat, []).append(hid)
    for seat, hids in seats.items():
        if len(hids) > 1:
            issues.append(
                ValidationIssue(
                    "duplicate_permanent_seat",
                    f"Meer dan één champion op permanente seat {seat}: {hids}.",
                )
            )

    # Positions: unique, and within geometry valid set when known.
    geometry = request.get("geometry") if isinstance(request.get("geometry"), dict) else {}
    valid_positions = geometry.get("valid_position_ids") or []
    valid_set = {
        int(x) for x in valid_positions if isinstance(x, int) or str(x).isdigit()
    }
    occupied: dict[int, list[int]] = {}
    for row in party:
        hid = row.get("id")
        pos = row.get("position")
        if not isinstance(hid, int):
            continue
        if pos is None:
            issues.append(
                ValidationIssue(
                    "missing_position",
                    f"Champion {hid} heeft geen actuele positie.",
                    severity="warning",
                )
            )
            continue
        if not isinstance(pos, int):
            issues.append(
                ValidationIssue(
                    "invalid_position_type",
                    f"Champion {hid} heeft ongeldige positie {pos!r}.",
                )
            )
            continue
        occupied.setdefault(pos, []).append(hid)
        if valid_set and pos not in valid_set:
            # Occupied seats in geometry.occupied are live truth — do not block
            # advice solely because valid_position_ids omitted them (e.g. escort
            # slot that still has a mapped champion after seat-fallback fixes).
            geo_occupied_ids = {
                int(row["id"])
                for row in (geometry.get("occupied") or [])
                if isinstance(row, dict)
                and (isinstance(row.get("id"), int) or str(row.get("id") or "").isdigit())
            }
            if pos in geo_occupied_ids:
                issues.append(
                    ValidationIssue(
                        "position_not_active",
                        f"Champion {hid} op positie {pos} die niet in geldige "
                        f"actieve posities staat (wel bezet in geometry.occupied).",
                        severity="warning",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        "position_not_active",
                        f"Champion {hid} op positie {pos} die niet in geldige "
                        f"actieve posities staat.",
                    )
                )
    for pos, hids in occupied.items():
        if len(hids) > 1:
            issues.append(
                ValidationIssue(
                    "duplicate_position",
                    f"Positie {pos} is dubbel bezet door {hids}.",
                )
            )

    # Specialization choices.
    for row in party:
        hid = row.get("id")
        for choice in row.get("specialization_choices") or []:
            if not isinstance(choice, dict):
                continue
            sid = choice.get("selected_option_id")
            status = choice.get("selection_status")
            if status == "not_unlocked" and sid is None:
                # Valid state: choice not yet unlocked — not an error.
                continue
            if status == "selected" and sid is None:
                issues.append(
                    ValidationIssue(
                        "selected_spec_missing_option_id",
                        f"Champion {hid}: selection_status=selected zonder "
                        "geldige option_id.",
                    )
                )
            elif sid is None and status not in (None, "unselected", "unknown", "not_unlocked"):
                issues.append(
                    ValidationIssue(
                        "spec_choice_missing_id",
                        f"Champion {hid}: specialisatiekeuze zonder option_id "
                        f"(status={status}).",
                        severity="warning",
                    )
                )
            if status == "unknown" and isinstance(hid, int):
                issues.append(
                    ValidationIssue(
                        "spec_choice_unknown",
                        "Specialisatiekeuze unknown (niet als vaststaand "
                        "behandelen; niet vullen vanuit oudere snapshot).",
                        severity="warning",
                        ids=[hid],
                    )
                )
            if status == "not_unlocked" and isinstance(hid, int):
                issues.append(
                    ValidationIssue(
                        "spec_not_unlocked",
                        "Specialisatie nog niet vrijgespeeld — alleen "
                        "adviseren als latere keuze vanaf vereist level, "
                        "niet als direct toepasbaar.",
                        severity="warning",
                        ids=[hid],
                    )
                )

    # Material conflicts from snapshot↔request reconciliation (not expected overrides).
    deviations = (
        request.get("snapshot_deviations")
        if isinstance(request.get("snapshot_deviations"), dict)
        else {}
    )
    for row in deviations.get("material_source_conflicts") or []:
        if not isinstance(row, dict):
            continue
        issues.append(
            ValidationIssue(
                str(row.get("code") or "material_source_conflict"),
                str(
                    row.get("note")
                    or "Materieel bronconflict tussen aanvraag en mechanics."
                ),
                severity="error",
            )
        )
    # missing_comparison_data is informational for the AI — warning, not block.
    for row in deviations.get("missing_comparison_data") or []:
        if not isinstance(row, dict):
            continue
        if row.get("blocks_other_formation_advice"):
            issues.append(
                ValidationIssue(
                    str(row.get("code") or "missing_comparison_data"),
                    str(row.get("note") or "Ontbrekende vergelijkingsgegevens."),
                    severity="error",
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    str(row.get("code") or "missing_comparison_data"),
                    str(row.get("note") or "Ontbrekende vergelijkingsgegevens."),
                    severity="warning",
                )
            )

    # Eligibility vs party visibility.
    elig = (
        request.get("roster_eligibility")
        if isinstance(request.get("roster_eligibility"), dict)
        else {}
    )
    denied = {
        int(row["id"])
        for row in (elig.get("denied") or [])
        if isinstance(row, dict) and isinstance(row.get("id"), int)
    }
    # Also denied_groups compact form.
    for group in elig.get("denied_groups") or []:
        if not isinstance(group, dict):
            continue
        for hid in group.get("ids") or []:
            if isinstance(hid, int):
                denied.add(hid)
    unknown = {
        int(row["id"])
        for row in (elig.get("unknown") or [])
        if isinstance(row, dict) and isinstance(row.get("id"), int)
    }
    for group in elig.get("unknown_groups") or []:
        if not isinstance(group, dict):
            continue
        for hid in group.get("ids") or []:
            if isinstance(hid, int):
                unknown.add(hid)

    party_denied = [hid for hid in party_ids if hid in denied]
    party_unknown = [hid for hid in party_ids if hid in unknown]
    if party_denied:
        issues.append(
            ValidationIssue(
                "party_denied_by_restrictions",
                "Party-champions denied door actuele restricties "
                "(zichtbaar conflict party vs eligibility).",
                severity="error",
                ids=party_denied,
            )
        )
    if party_unknown:
        issues.append(
            ValidationIssue(
                "party_unknown_eligibility",
                "Party-champions met eligibility=unknown "
                "(niet stilzwijgend als allowed behandelen).",
                severity="warning",
                ids=party_unknown,
            )
        )

    # Party member eligibility field must not contradict roster tables.
    party_elig_allowed_but_denied: list[int] = []
    for row in party:
        hid = row.get("id")
        if not isinstance(hid, int):
            continue
        if row.get("eligibility") == "allowed" and hid in denied:
            party_elig_allowed_but_denied.append(hid)
    if party_elig_allowed_but_denied:
        issues.append(
            ValidationIssue(
                "party_eligibility_contradicts_denied",
                "party[].eligibility=allowed terwijl roster denied is.",
                severity="error",
                ids=party_elig_allowed_but_denied,
            )
        )

    allowed_ids_raw = elig.get("allowed_ids") or []
    allowed_id_set = {
        int(hid)
        for hid in allowed_ids_raw
        if isinstance(hid, int) or (isinstance(hid, str) and str(hid).isdigit())
    }
    allowed_and_denied = sorted(allowed_id_set & denied)
    if allowed_and_denied:
        issues.append(
            ValidationIssue(
                "allowed_ids_contradict_denied",
                "allowed_ids overlapt denied_groups/denied — "
                "eligibility-uitkomsten zijn inconsistent.",
                severity="error",
                ids=allowed_and_denied,
            )
        )

    presence_conflicts = [
        c
        for c in (elig.get("presence_conflicts") or [])
        if isinstance(c, dict)
    ]
    unresolved_presence = [
        c for c in presence_conflicts if c.get("status") == "unresolved"
    ]
    unresolved_presence_ids = [
        int(c["champion_id"])
        for c in unresolved_presence
        if isinstance(c.get("champion_id"), int)
    ]
    locked_unresolved_presence = [
        c for c in unresolved_presence if c.get("replacement_locked")
    ]
    if unresolved_presence_ids:
        issues.append(
            ValidationIssue(
                "unresolved_presence_conflict",
                "Onopgelost presence-conflict: champion zit in de formatie "
                "maar is niet bewezen eligible (aanwezigheid ≠ toelating).",
                severity="error",
                ids=unresolved_presence_ids,
            )
        )
    user_confirmed_presence = [
        c
        for c in presence_conflicts
        if c.get("status") == "resolved"
        and c.get("resolution") == "user_confirmation"
    ]
    if user_confirmed_presence:
        issues.append(
            ValidationIssue(
                "user_eligibility_confirmation",
                "Handmatige eligibility-bevestiging (user_confirmation) — "
                "geen API-verificatie; oorspronkelijke deny blijft zichtbaar.",
                severity="warning",
                ids=[
                    int(c["champion_id"])
                    for c in user_confirmed_presence
                    if isinstance(c.get("champion_id"), int)
                ],
            )
        )
    if locked_unresolved_presence:
        issues.append(
            ValidationIssue(
                "replacement_locked_presence_conflict",
                "Onopgelost presence-conflict met replacement_locked — "
                "advies dat deze champion behoudt/verplaatst is geblokkeerd "
                "tot toelating is onderbouwd.",
                severity="error",
                ids=[
                    int(c["champion_id"])
                    for c in locked_unresolved_presence
                    if isinstance(c.get("champion_id"), int)
                ],
            )
        )

    # Block unconditional advice on real party denials / unresolved presence.
    # Replaceable contested members do not prove the current party is legal,
    # but proposals that exclude them may still be considered (see advice_ready).
    if party_denied or unresolved_presence_ids:
        issues.append(
            ValidationIssue(
                "restriction_conflict_blocks_advice",
                "Restrictieconflict: huidige party is niet bevestigd toegestaan; "
                "geen onvoorwaardelijk formatieadvies. "
                "Vervangbare conflicten blokkeren geen voorstellen zonder hen.",
                severity="error",
            )
        )
    elif goal.get("party_restriction_status") == "conflict" and not party_denied:
        issues.append(
            ValidationIssue(
                "stale_restriction_conflict_label",
                "party_restriction_status=conflict zonder denied party-leden "
                "(waarschijnlijk opgelost via overrides); niet als harde blokkade.",
                severity="warning",
            )
        )

    structured = goal.get("structured_restrictions")
    if isinstance(structured, dict) and structured.get(
        "has_restriction_semantics_conflict"
    ):
        issues.append(
            ValidationIssue(
                "restriction_semantics_conflict",
                "by_expr en restrictions_text zijn niet eenduidig verzoend.",
                severity="error",
            )
        )

    if readiness.get("status") == "blocked":
        issues.append(
            ValidationIssue(
                "readiness_blocked",
                "readiness.status=blocked — niet als normale adviesaanvraag presenteren.",
                severity="error",
            )
        )

    # Mechanics: snapshot-ID ≠ usable effect prose; omitted essential deltas are unsafe.
    mech_cov = None
    mech_block = request.get("mechanics_completeness")
    if isinstance(mech_block, dict):
        mech_cov = mech_block.get("base_mechanics_export_coverage")
    if not isinstance(mech_cov, dict):
        mech_cov = request.get("base_mechanics_export_coverage")
    if isinstance(mech_cov, dict) and not mech_cov.get("usable_for_qualitative_advice"):
        cov_reason = mech_cov.get("reason")
        has_delta = bool(request.get("mechanics_delta"))
        omitted = bool(request.get("mechanics_delta_omitted_for_budget"))
        if cov_reason == "no_snapshot":
            issues.append(
                ValidationIssue(
                    "base_snapshot_body_unavailable_locally",
                    "BASE_SNAPSHOT-inhoud lokaal niet geladen — mechanicdekking "
                    "niet geverifieerd. Snapshot-ID alleen bewijst geen effectproza.",
                    severity="warning",
                )
            )
        elif omitted or not has_delta:
            issues.append(
                ValidationIssue(
                    "base_mechanics_missing_and_delta_unavailable",
                    "BASE_SNAPSHOT mist bruikbare mechanic-effectproza en "
                    "essentiële mechanics_delta ontbreekt of is weggelaten "
                    "voor budget. Plaatsingsadvies niet advice_ready; "
                    "exporteer een nieuwe basissnapshot of behoud de delta.",
                )
            )

    if request.get("mechanics_delta_omitted_for_budget"):
        # Only safe when BASE was assessed complete / usable.
        if (
            isinstance(mech_cov, dict)
            and mech_cov.get("reason") != "no_snapshot"
            and not mech_cov.get("export_complete")
        ):
            issues.append(
                ValidationIssue(
                    "mechanics_delta_omitted_despite_incomplete_base",
                    "mechanics_delta is weggelaten voor budget terwijl "
                    "BASE_SNAPSHOT-mechanics-export incompleet is "
                    f"(reason={mech_cov.get('reason')}). "
                    "delta_omitted_use_BASE_SNAPSHOT is hier ongeldig.",
                )
            )

    for iss in readiness.get("issues") or []:
        if not isinstance(iss, dict):
            continue
        if iss.get("code") == "base_mechanics_export_incomplete":
            issues.append(
                ValidationIssue(
                    "base_mechanics_export_incomplete",
                    str(iss.get("message") or "BASE_SNAPSHOT mechanics incompleet."),
                )
            )

    # Coverage counts when swap block present.
    swap = request.get("swap") if isinstance(request.get("swap"), dict) else None
    if swap:
        cov = swap.get("coverage") if isinstance(swap.get("coverage"), dict) else {}
        classification = [
            r for r in (swap.get("classification") or []) if isinstance(r, dict)
        ]
        if isinstance(cov.get("external_owned_count"), int) and classification:
            if cov["external_owned_count"] != len(classification):
                issues.append(
                    ValidationIssue(
                        "coverage_mismatch",
                        "Coverage external_owned_count komt niet overeen met "
                        "classification-lengte.",
                    )
                )
        allowed_ids = elig.get("allowed_ids") or []
        if isinstance(allowed_ids, list):
            overlap = set(allowed_ids) & unknown
            if overlap:
                issues.append(
                    ValidationIssue(
                        "unknown_marked_allowed",
                        f"Eligibility unknown ook in allowed_ids: {sorted(overlap)}.",
                    )
                )

        # party_restriction_ok must not imply all swap candidates are eligible.
        # included_allowed candidates that are denied/unknown are inconsistent.
        included_allowed_ids: list[int] = []
        for row in classification:
            if str(row.get("classification") or "") != "included_allowed":
                continue
            hid = row.get("id")
            if isinstance(hid, int):
                included_allowed_ids.append(hid)
        compact_included = swap.get("included_candidate_ids")
        # Compact budget form collapses allowed+conditional; only flag when
        # a candidate is explicitly denied in roster eligibility.
        denied_included = [hid for hid in included_allowed_ids if hid in denied]
        if not denied_included and isinstance(compact_included, list):
            denied_included = [
                int(hid)
                for hid in compact_included
                if isinstance(hid, int) and hid in denied
            ]
        if denied_included:
            issues.append(
                ValidationIssue(
                    "swap_candidate_denied_but_included",
                    "Swapkandidaat staat als included terwijl roster_eligibility "
                    "denied is — party_ok ≠ kandidaat-eligible.",
                    severity="error",
                    ids=denied_included,
                )
            )
        unknown_included_allowed = [
            hid for hid in included_allowed_ids if hid in unknown
        ]
        if unknown_included_allowed:
            issues.append(
                ValidationIssue(
                    "swap_candidate_unknown_marked_allowed",
                    "Swapkandidaat included_allowed terwijl eligibility=unknown.",
                    severity="warning",
                    ids=unknown_included_allowed,
                )
            )

    if not goal.get("id"):
        issues.append(
            ValidationIssue(
                "missing_goal_id",
                "Doel ontbreekt in de aanvraag.",
            )
        )
    if not geometry:
        issues.append(
            ValidationIssue(
                "missing_geometry",
                "Geometrie ontbreekt in de aanvraag.",
            )
        )
    elif not (
        geometry.get("valid_position_ids")
        or geometry.get("occupied")
        or geometry.get("positions")
        or geometry.get("ref")
    ):
        issues.append(
            ValidationIssue(
                "incomplete_geometry",
                "Geometrie mist valid_position_ids/occupied én snapshot-ref.",
                severity="warning",
            )
        )
    else:
        _validate_geometry_layout_consistency(geometry, issues)
    live_unclear = [
        int(row["id"])
        for row in party
        if isinstance(row.get("id"), int)
        and (
            not isinstance(row.get("live_state"), dict)
            or row["live_state"].get("status") not in {"unknown", "known"}
        )
    ]
    if live_unclear:
        issues.append(
            ValidationIssue(
                "live_state_not_explicit",
                "live_state niet expliciet (unknown/known).",
                severity="warning",
                ids=live_unclear,
            )
        )

    structural_errors = [
        i
        for i in issues
        if i.severity == "error"
        and i.code
        not in {
            "party_denied_by_restrictions",
            "restriction_conflict_blocks_advice",
            "restriction_semantics_conflict",
            "readiness_blocked",
            "unresolved_presence_conflict",
            "replacement_locked_presence_conflict",
            "party_eligibility_contradicts_denied",
            "allowed_ids_contradict_denied",
        }
    ]
    restriction_errors = [
        i
        for i in issues
        if i.severity == "error"
        and i.code
        in {
            "party_denied_by_restrictions",
            "restriction_conflict_blocks_advice",
            "restriction_semantics_conflict",
            "readiness_blocked",
            "unresolved_presence_conflict",
            "replacement_locked_presence_conflict",
            "party_eligibility_contradicts_denied",
            "allowed_ids_contradict_denied",
        }
    ]
    structural_ok = not structural_errors
    # Current party legality — presence conflicts mean not unconditionally ok.
    party_restriction_ok = (
        not restriction_errors
        and not party_denied
        and not unresolved_presence_ids
        and not party_elig_allowed_but_denied
        and not allowed_and_denied
    )
    swap_candidate_errors = [
        i
        for i in issues
        if i.severity == "error" and i.code == "swap_candidate_denied_but_included"
    ]
    swap_candidates_restriction_ok = not swap_candidate_errors
    # Unconditional advice requires a proven-legal current party.
    # Replaceable unresolved conflicts still leave party_restriction_ok false
    # (current party not proven legal) but do not add structural blockers;
    # consumers may propose end-formations that exclude those champions.
    advice_ready = structural_ok and party_restriction_ok

    return ExportValidationResult(
        validation_ran=True,
        structural_ok=structural_ok,
        party_restriction_ok=party_restriction_ok,
        advice_ready=advice_ready,
        issues=issues,
        swap_candidates_restriction_ok=swap_candidates_restriction_ok,
    )


def mark_request_unvalidated(
    request: dict[str, Any],
    result: ExportValidationResult,
) -> dict[str, Any]:
    """Attach explicit not-advice-ready labeling for diagnostic exports."""
    out = dict(request)
    meta = dict(out.get("meta") or {})
    meta["validation"] = {
        "validated": True,
        "validation_ran": True,
        "structural_ok": result.structural_ok,
        "party_restriction_ok": result.party_restriction_ok,
        "swap_candidates_restriction_ok": result.swap_candidates_restriction_ok,
        "advice_ready": False,
        "ok": False,
        "issues": _group_issues_for_export(result.issues),
        "label": "diagnostisch_geldigheid_onbevestigd",
        "note": (
            "Diagnostisch: structureel "
            f"{'ok' if result.structural_ok else 'ongeldig'}, niet advice_ready "
            "(party/restricties onbevestigd of blokkerend). "
            "party_restriction_ok dekt niet automatisch swapkandidaten."
        ),
    }
    out["meta"] = meta
    return out


def mark_request_validated(
    request: dict[str, Any],
    result: ExportValidationResult,
) -> dict[str, Any]:
    out = dict(request)
    meta = dict(out.get("meta") or {})
    meta["validation"] = {
        "validated": True,
        "validation_ran": True,
        "structural_ok": result.structural_ok,
        "party_restriction_ok": result.party_restriction_ok,
        "swap_candidates_restriction_ok": result.swap_candidates_restriction_ok,
        "advice_ready": result.advice_ready,
        "ok": result.advice_ready,
        "warnings": _group_issues_for_export(result.warnings) or None,
    }
    out["meta"] = meta
    return out
