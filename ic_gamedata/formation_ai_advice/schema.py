"""JSON Schema for structured formation advice responses."""

from __future__ import annotations

from typing import Any

FORMATION_ADVICE_SCHEMA_NAME = "formation_advice"

FORMATION_ADVICE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "request_id",
        "status",
        "summary",
        "assignments",
        "expected_key_buffs",
        "assumptions",
        "missing_information",
        "warnings",
        "source_refs",
    ],
    "properties": {
        "schema_version": {"type": "string"},
        "request_id": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["proposal", "needs_information", "no_valid_proposal"],
        },
        "summary": {"type": "string"},
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "position_id",
                    "champion_id",
                    "specialization_choices",
                    "placement_reason",
                ],
                "properties": {
                    "position_id": {"type": "integer"},
                    "champion_id": {"type": "integer"},
                    "placement_reason": {"type": "string"},
                    "specialization_choices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["group_id", "option_id", "reason"],
                            "properties": {
                                "group_id": {"type": "string"},
                                "option_id": {"type": "integer"},
                                "reason": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "expected_key_buffs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_champion_id",
                    "target_champion_id",
                    "explanation",
                ],
                "properties": {
                    "source_champion_id": {"type": "integer"},
                    "target_champion_id": {"type": "integer"},
                    "ability_id": {"type": ["integer", "null"]},
                    "explanation": {"type": "string"},
                },
            },
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "source_refs": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "IDs of API search results only (e.g. '1', '2'). "
                "Do not invent URLs."
            ),
        },
    },
}
