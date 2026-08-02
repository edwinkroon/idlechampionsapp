"""Classify specialization rule provenance (authored vs heuristic).

v2_full rows mix hand-authored champion rules with generic placeholder rows.
This module derives ``rule_source_type`` until explicit provenance columns exist
in the CSV (e.g. a future V3 ``source_basis`` or ``rule_quality`` field).
"""

from __future__ import annotations

import re
from typing import Literal

RuleSourceType = Literal["authored", "heuristic"]

_GENERIC_ROUTE_LABELS = frozenset(
    {
        "support route",
        "other route",
        "other scaling",
        "other bond route",
        "other utility",
        "damage/support route",
        "support routing",
        "fiend route",
        "stack route",
        "ranged route",
        "djinn route",
        "puzzle route",
        "alignment route",
    }
)

_PLACEHOLDER_NOTE = re.compile(r"placeholder\s+rule", re.IGNORECASE)


def classify_rule_provenance(
    *,
    usually_choose: str,
    alternative: str = "",
    tags: tuple[str, ...] = (),
    notes_for_cursor: str = "",
    explicit_source_type: str = "",
) -> RuleSourceType:
    """Return authored vs heuristic for a v2_full (or future explicit) row."""
    explicit = explicit_source_type.strip().casefold()
    if explicit in {"authored", "trusted_authored_rule", "trusted"}:
        return "authored"
    if explicit in {"heuristic", "heuristic_placeholder_rule", "placeholder"}:
        return "heuristic"

    notes = notes_for_cursor.strip()
    if notes and _PLACEHOLDER_NOTE.search(notes):
        return "heuristic"

    tag_set = {tag.casefold() for tag in tags}
    if "generic" in tag_set:
        return "heuristic"

    usually = usually_choose.strip().casefold()
    alternative_cf = alternative.strip().casefold()
    if usually in _GENERIC_ROUTE_LABELS:
        return "heuristic"
    if alternative_cf in _GENERIC_ROUTE_LABELS and usually in _GENERIC_ROUTE_LABELS:
        return "heuristic"

    return "authored"
