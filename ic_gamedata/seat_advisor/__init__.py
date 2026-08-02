"""Seat-centric party advisor."""

from ic_gamedata.seat_advisor.models import (
    STANDARD_SEAT_ROLES,
    BenchCandidate,
    SeatAdvisorReport,
    SeatReport,
    SeatRole,
    VisualSeatNode,
)
from ic_gamedata.seat_advisor.report_builder import build_seat_advisor_report
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
