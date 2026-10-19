"""Formation advice via clipboard/chat export + local hard-rule validation."""

from __future__ import annotations

from ic_gamedata.formation_ai_advice.compact_clipboard import (
    build_advice_request_clipboard_text,
    build_project_instructions_clipboard_text,
)
from ic_gamedata.formation_ai_advice.service import ingest_pasted_proposal
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
    build_champion_details,
    format_advice_request_markdown,
    format_base_snapshot_markdown,
    format_champion_details_markdown,
)

__all__ = [
    "ingest_pasted_proposal",
    "build_base_snapshot",
    "build_advice_request",
    "build_champion_details",
    "format_base_snapshot_markdown",
    "format_advice_request_markdown",
    "format_champion_details_markdown",
    "build_advice_request_clipboard_text",
    "build_project_instructions_clipboard_text",
]
