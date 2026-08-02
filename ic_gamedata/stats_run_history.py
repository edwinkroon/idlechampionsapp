"""Modron goal tracking state and run-completion helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.stats_models import (
    GOAL_PEAK_SANITY_MARGIN,
    GOAL_RUN_DURATION_MISMATCH_SEC,
    MAX_PLAUSIBLE_GOAL_RUN_SEC,
    PARTY_INACTIVE_DURATION_THRESHOLD_SEC,
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


def _accumulate_inactive_time(state: PartyTrackState, party: PartySnapshot, now: float) -> None:
    """Track wall time while this party slot was not the active game instance."""
    if state.last_poll_at is None:
        state.last_poll_at = now
        return
    delta = max(now - state.last_poll_at, 0.0)
    if delta > 0 and not party.is_active:
        state.segment_inactive_sec += delta
    state.last_poll_at = now


def _goal_run_duration_sec(state: PartyTrackState) -> tuple[float, bool]:
    """
    Return run duration and whether the value may be inflated by party switches.

    When the dashboard tracked inactive wall time, prefer the in-game timer.
    """
    segment_duration = max(time.time() - state.segment_started_at, 0.0)
    api_raw = state.api_latest.seconds_since_reset
    had_inactive = state.segment_inactive_sec >= PARTY_INACTIVE_DURATION_THRESHOLD_SEC

    if had_inactive and api_raw is not None:
        api_duration = float(api_raw)
        if 0 < api_duration <= MAX_PLAUSIBLE_GOAL_RUN_SEC:
            return api_duration, False

    if api_raw is None:
        return segment_duration, had_inactive

    api_duration = float(api_raw)
    if api_duration > MAX_PLAUSIBLE_GOAL_RUN_SEC:
        duration = segment_duration if segment_duration > 0 else MAX_PLAUSIBLE_GOAL_RUN_SEC
        return duration, had_inactive

    # Tracker often starts mid-run — trust the in-game timer when it is ahead.
    if api_duration > segment_duration + 30:
        return api_duration, False

    duration = segment_duration if segment_duration > 0 else api_duration
    unreliable = had_inactive or (
        segment_duration > api_duration + GOAL_RUN_DURATION_MISMATCH_SEC
    )
    return duration, unreliable


def _goal_completion_margin(goal: int, *, on_reset: bool) -> int:
    """How close peak/area must get to the Modron goal to count as finished."""
    if not on_reset:
        # Live near-goal recording (same as previous ``area >= goal - 10``).
        return 10
    # Briv farms often skip far past the last polled area before Modron lands.
    # Keep this wide enough for poll gaps, but below "clearly abandoned" peaks.
    return max(80, min(150, goal // 2))


def _goal_run_completed(state: PartyTrackState, *, on_reset: bool = False) -> bool:
    goal = _segment_goal_for_state(state)
    if goal is None or goal <= 0:
        return False
    margin = _goal_completion_margin(goal, on_reset=on_reset)
    peak = _segment_peak_for_state(state)
    prev_area = state.api_latest.current_area
    candidates = [value for value in (peak, prev_area) if value is not None]
    if not candidates:
        return False
    best = max(candidates)
    # At or past the goal always counts (Briv overshoot / noisy peak reads).
    if best >= goal:
        return True
    return best + margin >= goal


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
    segment_inactive_sec: float = 0.0
    last_poll_at: float | None = None
    samples: list[_MetricSample] = field(default_factory=list)


# Backward-compatible alias for internal imports/tests.
_PartyTrackState = PartyTrackState


def _update_segment_peak(state: PartyTrackState, party: PartySnapshot) -> None:
    peak = _peak_area(party)
    if peak is None:
        return
    if state.segment_peak_area is None or peak > state.segment_peak_area:
        state.segment_peak_area = peak
