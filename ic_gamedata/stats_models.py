"""Shared stats dataclasses, goal-run validation, and adventure reset detection."""

from __future__ import annotations

from dataclasses import dataclass

from ic_gamedata.log_parser import PartySnapshot

MAX_GOAL_RUN_HISTORY = 50
GOAL_COMPLETION_AREA_TOLERANCE = 3
# Ignore memory/API peaks far above the Modron goal (bad memory reads).
# Briv can overshoot the goal by a wide margin before Modron reset lands.
GOAL_PEAK_SANITY_MARGIN = 120
# Runs longer than this are treated as corrupt timer data and not recorded.
MAX_PLAUSIBLE_GOAL_RUN_SEC = 4 * 3600
# Champions like Thellora skip early areas — Modron reset often lands around 45, not 1.
MODRON_RESET_LANDING_MAX_AREA = 55


def _plausible_peak_for_goal(peak: int, goal: int) -> bool:
    return peak <= goal + GOAL_PEAK_SANITY_MARGIN


# Party was inactive this long during a segment — likely inflated wall-clock timing.
PARTY_INACTIVE_DURATION_THRESHOLD_SEC = 30.0
# Wall-clock duration this far above the in-game timer is treated as unreliable.
GOAL_RUN_DURATION_MISMATCH_SEC = 60.0


@dataclass(frozen=True)
class GoalRunRecord:
    """One completed run to an adventure area goal (recorded on Modron reset)."""

    duration_sec: float
    area_goal: int
    peak_area: int | None
    recorded_at: float
    duration_unreliable: bool = False
    gems_earned: int | None = None


@dataclass(frozen=True)
class PartySessionStats:
    party_index: int
    adventure_id: int | None
    is_active: bool
    elapsed_sec: float
    segment_elapsed_sec: float
    current_area: int | None
    gold: float | None
    gems_this_reset: int | None
    areas_gained: float | None
    gold_gained: float | None
    gems_gained: float | None
    areas_per_quarter: float | None
    gold_per_quarter: float | None
    gems_per_quarter: float | None
    session_areas_gained: float | None
    session_gems_gained: float | None
    rate_window_sec: float | None = None
    reset_count: int = 0
    gems_estimated: bool = False
    adventure_area_goal: int | None = None
    modron_area_goal: int | None = None
    goal_run_history: tuple[GoalRunRecord, ...] = ()


@dataclass(frozen=True)
class SessionStats:
    elapsed_sec: float
    current_area: int | None
    memory_area: int | None
    gold: float | None
    gems_this_reset: int | None
    areas_gained: float | None
    memory_areas_gained: float | None
    gold_gained: float | None
    gems_gained: float | None
    areas_per_quarter: float | None
    memory_areas_per_quarter: float | None
    gold_per_quarter: float | None
    gems_per_quarter: float | None
    monster_kills_delta: float | None
    boss_kills_delta: float | None
    sample_count: int
    memory_sample_count: int
    parties: tuple[PartySessionStats, ...]


def is_plausible_goal_run_record(record: GoalRunRecord) -> bool:
    """Keep stored runs unless the duration itself is clearly corrupt.

    Peak-vs-goal sanity is enforced when *recording* new runs (bad memory spikes).
    Applying it again on load deleted real history after Briv jumps / offset glitches.
    """
    return 0 < record.duration_sec <= MAX_PLAUSIBLE_GOAL_RUN_SEC


def _area_drop_values(prev_area: int, cur_area: int) -> bool:
    """True when area falls far enough to indicate a real adventure restart."""
    if cur_area >= prev_area:
        return False
    # Typical Modron: high area → low teens/ones. Ignore small API jitter.
    if prev_area - cur_area >= 50:
        return True
    # Standard reset to area 1, or skip-champion landing zone (e.g. Thellora ~45).
    if prev_area >= 30 and cur_area <= MODRON_RESET_LANDING_MAX_AREA:
        return True
    return False


def _area_drop_looks_like_modron(previous: PartySnapshot, current: PartySnapshot) -> bool:
    """True when area falls far enough to indicate a real adventure restart."""
    if previous.current_area is None or current.current_area is None:
        return False
    return _area_drop_values(previous.current_area, current.current_area)


def detect_adventure_reset(previous: PartySnapshot, current: PartySnapshot) -> bool:
    """
    Detect Modron/adventure reset between two consecutive *raw* API readings.

    Do not pass estimated gem values here — gem/boss counters from the API often
    lag behind live area and must not alone trigger a reset.
    """
    if (
        previous.seconds_since_reset is not None
        and current.seconds_since_reset is not None
        and current.seconds_since_reset + 60 < previous.seconds_since_reset
    ):
        return True

    if _area_drop_looks_like_modron(previous, current):
        return True

    if (
        previous.adventure_id is not None
        and current.adventure_id is not None
        and previous.adventure_id >= 0
        and current.adventure_id >= 0
        and previous.adventure_id != current.adventure_id
    ):
        return True

    return False
