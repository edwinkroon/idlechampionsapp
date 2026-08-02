"""Seat-centric party advisor."""

from __future__ import annotations

from typing import Any

from ic_gamedata.seat_advisor.models import (
    STANDARD_SEAT_ROLES,
    BenchCandidate,
    SeatAdvisorReport,
    SeatReport,
    SeatRole,
    VisualSeatNode,
)
from ic_gamedata.seat_advisor.role_prefs import (
    get_chosen_role,
    load_role_preferences,
    set_chosen_role,
)

__all__ = [
    "STANDARD_SEAT_ROLES",
    "BenchCandidate",
    "SeatAdvisorReport",
    "SeatReport",
    "SeatRole",
    "VisualSeatNode",
    "build_seat_advisor_report",
    "get_chosen_role",
    "load_role_preferences",
    "set_chosen_role",
]


def build_seat_advisor_report(*args: Any, **kwargs: Any):
    """Lazy wrapper — avoids circular imports via seat_advisor.__init__."""
    from ic_gamedata.seat_advisor.report_builder import build_seat_advisor_report as _build

    return _build(*args, **kwargs)
