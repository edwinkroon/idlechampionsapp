"""Modron goal tracking state and run-completion helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.stats_models import (
    GOAL_COMPLETION_AREA_TOLERANCE,
    GOAL_PEAK_SANITY_MARGIN,
    MAX_PLAUSIBLE_GOAL_RUN_SEC,
    _plausible_peak_for_goal,
)
from ic_gamedata.stats_rates import _MetricSample


def _segment_peak_after_reset(party: PartySnapshot) -> int | None:
    """Peak for a fresh segment — ignore stale highest_area from the API payload."""
    if party.current_area is not None:
        return party.current_area
    return _peak_area(party)


def _peak_area(party: PartySnapshot) -> int | None:
    values = [value for value in (party.current_area, party.highest_area) if value is not None]
    return max(values) if values else None


def _party_modron_goal(party: PartySnapshot) -> int | None:
    goal = party.modron_area_goal
    if goal is not None and goal > 0:
        return goal
    try:
        from ic_gamedata.modron_area_goal import party_modron_goal_override

        return party_modron_goal_override(party.party_index)
    except ImportError:
        return None


def _segment_goal_for_state(state: PartyTrackState) -> int | None:
    for party in (state.api_latest, state.latest):
        goal = _party_modron_goal(party)
        if goal is not None:
            return goal
    if state.segment_area_goal is not None and state.segment_area_goal > 0:
        return state.segment_area_goal
    return None


def _segment_peak_for_state(state: PartyTrackState) -> int | None:
    candidates = (
        state.segment_peak_area,
        _peak_area(state.api_latest),
        _peak_area(state.latest),
    )
    values = [value for value in candidates if value is not None]
    return max(values) if values else None


def _sync_segment_goal(state: PartyTrackState, party: PartySnapshot) -> None:
    goal = _party_modron_goal(party)
    if goal is not None and goal > 0:
        state.segment_area_goal = goal


def _goal_run_duration_sec(state: PartyTrackState) -> float:
    segment_duration = max(time.time() - state.segment_started_at, 0.0)
    api_duration = state.api_latest.seconds_since_reset
    if api_duration is None:
        return segment_duration
    api_duration = float(api_duration)
    if api_duration > MAX_PLAUSIBLE_GOAL_RUN_SEC:
        return segment_duration if segment_duration > 0 else MAX_PLAUSIBLE_GOAL_RUN_SEC
    # Tracker often starts mid-run — trust the in-game timer when it is ahead.
    if api_duration > segment_duration + 30:
        return api_duration
    return segment_duration if segment_duration > 0 else api_duration


def _goal_run_completed(state: PartyTrackState) -> bool:
    goal = _segment_goal_for_state(state)
    if goal is None or goal <= 0:
        return False
    peak = _segment_peak_for_state(state)
    if peak is not None:
        if peak + GOAL_COMPLETION_AREA_TOLERANCE >= goal and _plausible_peak_for_goal(peak, goal):
            return True
    # API polls can skip the exact goal area before Modron reset.
    prev_area = state.api_latest.current_area
    if prev_area is not None and prev_area >= goal - 10:
        return True
    return False


def _trustworthy_memory_area(state: PartyTrackState, area: int) -> bool:
    goal = _segment_goal_for_state(state)
    if goal is None or goal <= 0:
        return True
    return area <= goal + GOAL_PEAK_SANITY_MARGIN


@dataclass
class PartyTrackState:
    baseline: PartySnapshot
    latest: PartySnapshot
    api_latest: PartySnapshot
    segment_started_at: float
    accumulated_areas: float = 0.0
    accumulated_gold: float = 0.0
    accumulated_gems: float = 0.0
    accumulated_api_gems: float = 0.0
    accumulated_boss_kills: float = 0.0
    reset_count: int = 0
    gems_per_boss: float | None = None
    gems_per_area: float | None = None
    gem_anchor_gems: int | None = None
    gem_anchor_area: int | None = None
    gems_estimated: bool = False
    segment_peak_area: int | None = None
    segment_area_goal: int | None = None
    last_memory_area: int | None = None
    goal_run_recorded_this_segment: bool = False
    samples: list[_MetricSample] = field(default_factory=list)


# Backward-compatible alias for internal imports/tests.
_PartyTrackState = PartyTrackState


def _update_segment_peak(state: PartyTrackState, party: PartySnapshot) -> None:
    peak = _peak_area(party)
    if peak is None:
        return
    if state.segment_peak_area is None or peak > state.segment_peak_area:
        state.segment_peak_area = peak
