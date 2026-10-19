"""Clipboard/chat ingest + local validation for formation advice."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from ic_gamedata.formation_ai_advice.clipboard_export import extract_json_object
from ic_gamedata.formation_ai_advice.export import (
    formation_layout_fingerprint_from_export,
    request_fingerprint,
)
from ic_gamedata.formation_ai_advice.models import (
    AdviceObjective,
    FormationAdviceResult,
    LocalValidationResult,
)
from ic_gamedata.formation_ai_advice.validate import (
    parse_proposal_json,
    validate_proposal_against_export,
)


def ingest_pasted_proposal(
    pasted_text: str,
    *,
    export_payload: dict[str, Any],
    current_formation_fingerprint: str | None = None,
    objective: AdviceObjective | None = None,
    main_dps_id: int | None = None,
) -> FormationAdviceResult:
    """Validate a chat-pasted JSON proposal against a previously copied export."""
    meta = export_payload.get("meta") or {}
    request_id = str(meta.get("request_id") or "")
    requested_at = str(meta.get("requested_at") or "")
    data_version = meta.get("data_version")
    if data_version is not None:
        data_version = str(data_version)
    goal = export_payload.get("goal") or {}
    raw_obj = objective or goal.get("id") or goal.get("objective") or "push"
    allowed = (
        "push",
        "quest_clear",
        "gem_farm",
        "gold_farm",
        "favor_farm",
        "custom_task",
        "push_damage",
        "speed",
    )
    obj: AdviceObjective = raw_obj if raw_obj in allowed else "push"  # type: ignore[assignment]
    dps = main_dps_id if main_dps_id is not None else goal.get("fixed_main_dps_id")
    if dps is None:
        focus = goal.get("damage_focus")
        if isinstance(focus, dict) and focus.get("kind") == "fixed":
            dps = focus.get("champion_id")
    if dps is not None and not isinstance(dps, int):
        try:
            dps = int(dps)
        except (TypeError, ValueError):
            dps = None

    form_fp = formation_layout_fingerprint_from_export(export_payload)
    live_fp = current_formation_fingerprint or form_fp
    provider_label = "Clipboard / chat-voorstel (geen API)"
    req_fp = request_fingerprint(export_payload)
    dps_i = dps if isinstance(dps, int) else None

    data = extract_json_object(pasted_text)
    if data is None:
        return FormationAdviceResult(
            request_id=request_id,
            request_fingerprint=req_fp,
            data_version=data_version,
            requested_at=requested_at,
            objective=obj,
            main_dps_id=dps_i,
            proposal=None,
            local_validation=LocalValidationResult(
                status="invalid",
                errors=("Geen geldig JSON-object gevonden in de geplakte tekst.",),
            ),
            error="Geen geldig JSON-object gevonden in de geplakte tekst.",
            provider_label=provider_label,
        )

    if not data.get("request_id"):
        data["request_id"] = request_id
    proposal, parse_errors = parse_proposal_json(
        json.dumps(data, ensure_ascii=False),
        expected_request_id=request_id,
    )
    if proposal is None:
        data["request_id"] = request_id
        proposal, parse_errors = parse_proposal_json(
            json.dumps(data, ensure_ascii=False),
            expected_request_id=request_id,
        )
    if proposal is None:
        return FormationAdviceResult(
            request_id=request_id,
            request_fingerprint=req_fp,
            data_version=data_version,
            requested_at=requested_at,
            objective=obj,
            main_dps_id=dps_i,
            proposal=None,
            local_validation=LocalValidationResult(
                status="invalid",
                errors=tuple(parse_errors) or ("Kon geplakt voorstel niet parsen.",),
            ),
            error="; ".join(parse_errors) or "Ongeldig geplakt voorstel.",
            provider_label=provider_label,
        )

    if proposal.source_refs:
        proposal = replace(
            proposal,
            warnings=proposal.warnings
            + ("Bronverwijzingen uit chat genegeerd (geen API-bronmetadata).",),
            source_refs=(),
            sources=(),
        )

    local = validate_proposal_against_export(
        proposal,
        export_payload,
        api_sources=(),
        formation_fingerprint_at_request=form_fp,
        current_formation_fingerprint=live_fp,
    )
    return FormationAdviceResult(
        request_id=request_id,
        request_fingerprint=req_fp,
        data_version=data_version,
        requested_at=requested_at,
        objective=obj,
        main_dps_id=dps_i,
        proposal=proposal,
        local_validation=local,
        sources=(),
        error=None
        if local.can_apply or local.status == "needs_information"
        else "; ".join(local.errors),
        provider_label=provider_label,
        specializations_advice_only=True,
    )
