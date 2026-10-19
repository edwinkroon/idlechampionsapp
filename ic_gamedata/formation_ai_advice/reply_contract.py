"""``answer_contract`` for ADVICE_REQUEST — derived from the real importer.

Single source of truth:
- ``FORMATION_ADVICE_JSON_SCHEMA`` / ``SCHEMA_VERSION`` (full internal shape)
- ``_normalize_proposal_payload`` / ``parse_proposal_json`` /
  ``validate_proposal_against_export`` in ``validate.py``

Do not invent fields. Prefer generating this contract from those definitions.
"""

from __future__ import annotations

from typing import Any

from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION
from ic_gamedata.formation_ai_advice.schema import FORMATION_ADVICE_JSON_SCHEMA

# Compact chat shape accepted by ``_normalize_proposal_payload`` before it
# maps onto the full schema required keys.
_COMPACT_CHAT_FIELDS = (
    "schema_version",
    "request_id",
    "placements",
    "specializations",
)

_STATUS_ENUM: tuple[str, ...] = tuple(
    FORMATION_ADVICE_JSON_SCHEMA["properties"]["status"]["enum"]
)

_FULL_REQUIRED: tuple[str, ...] = tuple(FORMATION_ADVICE_JSON_SCHEMA["required"])

_ASSIGNMENT_REQUIRED: tuple[str, ...] = tuple(
    FORMATION_ADVICE_JSON_SCHEMA["properties"]["assignments"]["items"]["required"]
)

_SPEC_CHOICE_REQUIRED: tuple[str, ...] = tuple(
    FORMATION_ADVICE_JSON_SCHEMA["properties"]["assignments"]["items"]["properties"][
        "specialization_choices"
    ]["items"]["required"]
)

# Semantic rules from validate.py / apply.py — not expressible as JSON Schema alone.
_IMPORTER_SEMANTICS = {
    "completeness": "volledige_party_geen_changes_only",
    "position_id": "technisch_formatie_id_niet_display_niet_seat",
    "request_id": "exact_meta.request_id",
    "schema_version_major": SCHEMA_VERSION.split(".")[0],
    "omitted_champ_specializations": "geen_nieuw_spec_advies_voor_die_champ",
    "empty_specializations_array": "ok",
    "extra_top_level_keys": "niet_afgewezen_door_parse",
    "schema_additionalProperties": False,  # schema says false; parse does not enforce
    "source_refs_on_clipboard_ingest": "gewist",
    "missing_essential_data": (
        "status=needs_information of no_valid_proposal; "
        "geen gefabriceerd placements-antwoord"
    ),
    "blocked_statuses": {
        "needs_information": "can_apply=false; errors from missing_information",
        "no_valid_proposal": "can_apply=false",
    },
    "conditional_with_placements": (
        "blijft status=proposal; condition->warnings; apply mag als verder geldig"
    ),
}


def snapshot_expected_filename(snapshot_id: str) -> str:
    sid = str(snapshot_id or "").strip() or "?"
    return f"{sid.replace('/', '_')}.json"


def _schema_type(node: dict[str, Any]) -> Any:
    return node.get("type")


def _build_structure_example(
    *,
    request_id: str,
    party: list[dict[str, Any]] | None,
    valid_position_ids: list[int] | None,
) -> dict[str, Any]:
    """Minimal compact JSON shaped like a real reply, using current request ids.

    Marked as structure-only — not formation advice.
    """
    rid = str(request_id or "").strip() or "PLAK_REQUEST_ID"
    placements: list[dict[str, int]] = []
    specializations: list[dict[str, Any]] = []
    used_positions: set[int] = set()
    valid = [
        int(p)
        for p in (valid_position_ids or [])
        if isinstance(p, int) or str(p).isdigit()
    ]

    for row in party or []:
        if not isinstance(row, dict):
            continue
        cid = row.get("id")
        if not isinstance(cid, int):
            continue
        pos = row.get("position")
        if not isinstance(pos, int):
            # Fall back to first unused valid position for structure only.
            for candidate in valid:
                if candidate not in used_positions:
                    pos = candidate
                    break
        if not isinstance(pos, int):
            continue
        used_positions.add(pos)
        placements.append({"position_id": pos, "champion_id": cid})
        for choice in row.get("specialization_choices") or []:
            if not isinstance(choice, dict):
                continue
            oid = choice.get("selected_option_id")
            gid = choice.get("group_id")
            if isinstance(oid, int) and isinstance(gid, str) and gid:
                specializations.append(
                    {
                        "champion_id": cid,
                        "group_id": gid,
                        "option_id": oid,
                    }
                )

    if not placements:
        # Schema-valid placeholder when party is empty (should be rare).
        placements = [{"position_id": 1, "champion_id": 1}]

    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": rid,
        "placements": placements,
        "specializations": specializations,
    }


def build_answer_contract(
    request_id: str,
    *,
    party: list[dict[str, Any]] | None = None,
    valid_position_ids: list[int] | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Self-contained importer contract for every ADVICE_REQUEST.

    Preferred chat shape is compact ``placements``/``specializations``; the
    importer normalizes that onto full ``assignments`` before required-key checks.
    """
    rid = str(request_id or "").strip() or "PLAK_REQUEST_ID"
    props = FORMATION_ADVICE_JSON_SCHEMA["properties"]
    assign_item = props["assignments"]["items"]["properties"]
    spec_item = assign_item["specialization_choices"]["items"]["properties"]
    example = _build_structure_example(
        request_id=rid,
        party=party,
        valid_position_ids=valid_position_ids,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "schema_name": "formation_advice",
        "preferred_shape": "compact",
        "request_id_exact": rid,
        "snapshot_id_echo": snapshot_id,
        # --- compact (what chat should produce) ---
        "compact": {
            "required_top_level": list(_COMPACT_CHAT_FIELDS),
            "types": {
                "schema_version": "string",
                "request_id": "string",
                "placements": "array",
                "specializations": "array",
            },
            "placements_item": {
                "required": ["position_id", "champion_id"],
                "types": {"position_id": "integer", "champion_id": "integer"},
            },
            "specializations_item": {
                "required": ["champion_id", "group_id", "option_id"],
                "types": {
                    "champion_id": "integer",
                    "group_id": "string",
                    "option_id": "integer",
                },
            },
            "optional": {
                "status": {"type": "string", "enum": list(_STATUS_ENUM)},
                "summary": "string",
                "conditional": "boolean",
                "condition": "string",
            },
            "normalize_fills": {
                "status": (
                    "proposal if placements non-empty else needs_information"
                ),
                "summary": "condition or 'Voorstel uit chat.'",
                "expected_key_buffs": [],
                "assumptions": [],
                "missing_information": [],
                "warnings": [],
                "source_refs": [],
            },
        },
        # --- full internal (after normalize; FORMATION_ADVICE_JSON_SCHEMA) ---
        "full_after_normalize": {
            "required_top_level": list(_FULL_REQUIRED),
            "status_enum": list(_STATUS_ENUM),
            "assignments_item_required": list(_ASSIGNMENT_REQUIRED),
            "assignments_item_types": {
                key: _schema_type(spec) for key, spec in assign_item.items()
            },
            "specialization_choice_required": list(_SPEC_CHOICE_REQUIRED),
            "specialization_choice_types": {
                key: _schema_type(spec) for key, spec in spec_item.items()
            },
        },
        "semantics": dict(_IMPORTER_SEMANTICS),
        "display_vs_import": {
            "table_columns": ["Plek", "Champion"],
            "table_sort": ["display_column", "display_slot"],
            "table_uses": "display_position (kolom-plek)",
            "json_uses": "technical position_id only",
            "permanent_seat": "not a formation position_id",
        },
        "structure_example": {
            "not_advice": True,
            "note": (
                "Structuurvoorbeeld met ids uit deze aanvraag; "
                "geen formatieadvies."
            ),
            "json": example,
        },
    }


# Backwards-compatible alias (previous field name).
def build_advice_reply_contract(
    request_id: str,
    *,
    party: list[dict[str, Any]] | None = None,
    valid_position_ids: list[int] | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    return build_answer_contract(
        request_id,
        party=party,
        valid_position_ids=valid_position_ids,
        snapshot_id=snapshot_id,
    )


def reply_format_pointer_nl() -> str:
    """Short clipboard pointer — full rules live in ``answer_contract`` JSON."""
    return (
        "Antwoordvorm (verplicht):\n"
        "1. Leesbare tabel met kolommen ‘Plek’ en ‘Champion’, gesorteerd op "
        "display_column daarna display_slot (formaat kolom-plek, bijv. 1-1).\n"
        "2. Eventuele korte uitleg en specialisatieadviezen.\n"
        "3. Precies één JSON-object in één afgesloten Markdown-codeblok "
        "(taal json) volgens answer_contract in deze ADVICE_REQUEST "
        "(technische position_id’s; nooit display_position als id; "
        "permanente seat is geen formatiepositie).\n"
        "\n"
        "| Plek | Champion |\n"
        "| --- | --- |"
    )
