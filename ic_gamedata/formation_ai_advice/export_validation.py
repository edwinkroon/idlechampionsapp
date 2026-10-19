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
    - ``party_restriction_ok``: party is allowed under available rules
    - ``advice_ready``: suitable for unconditional formation advice
    - ``ok``: alias for ``advice_ready`` (normal copy path)
    """

    validation_ran: bool
    structural_ok: bool
    party_restriction_ok: bool
    advice_ready: bool
    issues: list[ValidationIssue] = field(default_factory=list)

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

    # Block only on real party denials — not a stale party_restriction_status
    # left at "conflict" while overrides already allow everyone seated.
    if party_denied:
        issues.append(
            ValidationIssue(
                "restriction_conflict_blocks_advice",
                "Restrictieconflict: party is niet bevestigd toegestaan; "
                "geen onvoorwaardelijk formatieadvies.",
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
        }
    ]
    structural_ok = not structural_errors
    party_restriction_ok = not restriction_errors and not party_denied
    advice_ready = structural_ok and party_restriction_ok

    return ExportValidationResult(
        validation_ran=True,
        structural_ok=structural_ok,
        party_restriction_ok=party_restriction_ok,
        advice_ready=advice_ready,
        issues=issues,
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
        "advice_ready": False,
        "ok": False,
        "issues": _group_issues_for_export(result.issues),
        "label": "diagnostisch_geldigheid_onbevestigd",
        "note": (
            "Diagnostisch: structureel "
            f"{'ok' if result.structural_ok else 'ongeldig'}, niet advice_ready "
            "(party/restricties onbevestigd of blokkerend)."
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
        "advice_ready": result.advice_ready,
        "ok": result.advice_ready,
        "warnings": _group_issues_for_export(result.warnings) or None,
    }
    out["meta"] = meta
    return out
