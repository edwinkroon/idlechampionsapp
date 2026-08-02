"""Session stats and per-quarter-hour rates from game snapshots."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ic_gamedata.log_parser import GameSnapshot, PartySnapshot
from ic_gamedata.stats_models import (
    GOAL_COMPLETION_AREA_TOLERANCE,
    GOAL_PEAK_SANITY_MARGIN,
    MAX_GOAL_RUN_HISTORY,
    MAX_PLAUSIBLE_GOAL_RUN_SEC,
    GoalRunRecord,
    PartySessionStats,
    SessionStats,
    _area_drop_values,
    _plausible_peak_for_goal,
    detect_adventure_reset,
    is_plausible_goal_run_record,
)

# Rates are normalized to a 15-minute period (kwartier).
RATE_PERIOD_SEC = 900.0
# Rolling window grows from 3 minutes up to 15 minutes as more samples are available.
ROLLING_MIN_WINDOW_SEC = 180.0  # 3 minutes — minimum before showing a rolling rate
ROLLING_MAX_WINDOW_SEC = 900.0  # 15 minutes — cap once enough history exists
MAX_SAMPLES_PER_PARTY = 720
DEFAULT_GEMS_PER_BOSS = 7.0
# Bosses typically every 5 areas; used when API gem counters stall before a rate is learned.
DEFAULT_GEMS_PER_AREA = DEFAULT_GEMS_PER_BOSS / 5.0
MIN_GEMS_PER_AREA = 0.01


def _initial_gems_per_area(party: PartySnapshot) -> float | None:
    if party.gems_this_reset is None or party.current_area is None or party.current_area <= 1:
        return None
    rate = party.gems_this_reset / party.current_area
    return rate if rate >= MIN_GEMS_PER_AREA else None


def _resolve_gems_per_area(
    gems_per_area: float | None,
    *,
    gems: int | None,
    area: int | None,
) -> float | None:
    """Prefer learned rate; fall back to gems/area or a default so estimates keep moving."""
    if gems_per_area is not None and gems_per_area >= MIN_GEMS_PER_AREA:
        return gems_per_area
    if gems is not None and gems > 0 and area is not None and area > 1:
        rate = gems / area
        if rate >= MIN_GEMS_PER_AREA:
            return rate
    if gems is not None and gems > 0:
        return DEFAULT_GEMS_PER_AREA
    return None


def _update_gem_rates(
    *,
    gems_per_boss: float | None,
    gems_per_area: float | None,
    anchor_gems: int | None,
    anchor_area: int | None,
    new_gems: int,
    new_area: int | None,
    prev_boss: int | None,
    new_boss: int | None,
) -> tuple[float | None, float | None]:
    updated_boss = gems_per_boss
    updated_area = gems_per_area

    if (
        anchor_gems is not None
        and anchor_area is not None
        and new_area is not None
        and new_gems > anchor_gems
        and new_area > anchor_area
    ):
        updated_area = (new_gems - anchor_gems) / (new_area - anchor_area)

    if (
        new_boss is not None
        and prev_boss is not None
        and new_boss > prev_boss
        and anchor_gems is not None
        and new_gems > anchor_gems
    ):
        delta_boss = new_boss - prev_boss
        if delta_boss > 0:
            updated_boss = (new_gems - anchor_gems) / delta_boss

    return updated_boss, updated_area


def _delta(current: int | float | None, baseline: int | float | None) -> float | None:
    if current is None or baseline is None:
        return None
    diff = float(current) - float(baseline)
    return diff if diff >= 0 else None


def _rate_per_period(delta: float | None, elapsed_sec: float) -> float | None:
    """Normalize a delta to RATE_PERIOD_SEC (per kwartier)."""
    if delta is None or elapsed_sec <= 0:
        return None
    return delta * RATE_PERIOD_SEC / elapsed_sec


@dataclass(frozen=True)
class _MetricSample:
    timestamp: float
    gems: int | None
    area: int | None
    gold: float | None
    boss_kills: int | None = None


def _effective_window_sec(usable: list[_MetricSample]) -> float | None:
    """
    Window length for rate calculation.

    Starts at 3 minutes when that much data exists, then grows with session
    length until capped at 15 minutes.
    """
    if len(usable) < 2:
        return None
    available = usable[-1].timestamp - usable[0].timestamp
    if available < ROLLING_MIN_WINDOW_SEC:
        return None
    return min(available, ROLLING_MAX_WINDOW_SEC)


def rolling_window_span(samples: list[_MetricSample]) -> float | None:
    """Actual time span used for the rolling rate (seconds), or None if warming up."""
    usable = samples
    window = _effective_window_sec(usable)
    if window is None:
        return None
    newest = usable[-1]
    cutoff = newest.timestamp - window
    oldest = usable[0]
    for sample in usable:
        if sample.timestamp >= cutoff:
            oldest = sample
            break
    span = newest.timestamp - oldest.timestamp
    return span if span >= ROLLING_MIN_WINDOW_SEC else None


def rolling_rate(
    samples: list[_MetricSample],
    *,
    field_name: str,
) -> float | None:
    """
    Gems/areas per kwartier over an adaptive rolling window (3 min → 15 min).

    Uses oldest sample within the effective window vs newest — stable for bursty
    boss-gem income while smoothing further as more history accumulates.
    """
    window = _effective_window_sec(samples)
    if window is None:
        return None

    newest = samples[-1]
    newest_val = getattr(newest, field_name)
    if newest_val is None:
        return None

    cutoff = newest.timestamp - window
    oldest = samples[0]
    for sample in samples:
        if sample.timestamp >= cutoff:
            oldest = sample
            break

    oldest_val = getattr(oldest, field_name)
    if oldest_val is None:
        return None

    span = newest.timestamp - oldest.timestamp
    if span < ROLLING_MIN_WINDOW_SEC:
        return None

    delta = float(newest_val) - float(oldest_val)
    if delta < 0:
        return None
    return delta * RATE_PERIOD_SEC / span


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


def _segment_goal_for_state(state: _PartyTrackState) -> int | None:
    for party in (state.api_latest, state.latest):
        goal = _party_modron_goal(party)
        if goal is not None:
            return goal
    if state.segment_area_goal is not None and state.segment_area_goal > 0:
        return state.segment_area_goal
    return None


def _segment_peak_for_state(state: _PartyTrackState) -> int | None:
    candidates = (
        state.segment_peak_area,
        _peak_area(state.api_latest),
        _peak_area(state.latest),
    )
    values = [value for value in candidates if value is not None]
    return max(values) if values else None


def _sync_segment_goal(state: _PartyTrackState, party: PartySnapshot) -> None:
    goal = _party_modron_goal(party)
    if goal is not None and goal > 0:
        state.segment_area_goal = goal


def _goal_run_duration_sec(state: _PartyTrackState) -> float:
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


def _goal_run_completed(state: _PartyTrackState) -> bool:
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


def _trustworthy_memory_area(state: _PartyTrackState, area: int) -> bool:
    goal = _segment_goal_for_state(state)
    if goal is None or goal <= 0:
        return True
    return area <= goal + GOAL_PEAK_SANITY_MARGIN


@dataclass
class _PartyTrackState:
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


def _update_segment_peak(state: _PartyTrackState, party: PartySnapshot) -> None:
    peak = _peak_area(party)
    if peak is None:
        return
    if state.segment_peak_area is None or peak > state.segment_peak_area:
        state.segment_peak_area = peak


def _estimate_gems_from_area(
    *,
    api_gems: int | None,
    anchor_gems: int | None,
    anchor_area: int | None,
    current_area: int | None,
    gems_per_area: float | None,
) -> int | None:
    if (
        anchor_gems is None
        or anchor_area is None
        or current_area is None
        or current_area <= anchor_area
        or gems_per_area is None
    ):
        return api_gems
    estimated = int(round(anchor_gems + (current_area - anchor_area) * gems_per_area))
    if api_gems is None:
        return estimated
    return max(api_gems, estimated)


def _extrapolate_gems(
    previous: PartySnapshot,
    current: PartySnapshot,
    *,
    gems_per_boss: float | None,
    gems_per_area: float | None,
    anchor_gems: int | None,
    anchor_area: int | None,
) -> tuple[int | None, float | None, float | None, int | None, int | None, bool]:
    """
    Return (effective_gems, gems_per_boss, gems_per_area, anchor_gems, anchor_area, is_estimated).

    The game API often updates current_area live but only syncs this_reset_gems_earned
    periodically. Estimate live gems from area progress using a learned gems/area rate.
    """
    api_gems = current.gems_this_reset
    prev_effective = previous.gems_this_reset
    prev_area = previous.current_area
    curr_area = current.current_area
    boss = current.boss_kills_this_reset
    prev_boss = previous.boss_kills_this_reset

    if api_gems is not None and prev_effective is not None and api_gems > prev_effective:
        gems_per_boss, gems_per_area = _update_gem_rates(
            gems_per_boss=gems_per_boss,
            gems_per_area=gems_per_area,
            anchor_gems=anchor_gems,
            anchor_area=anchor_area,
            new_gems=api_gems,
            new_area=curr_area,
            prev_boss=prev_boss,
            new_boss=boss,
        )
        return api_gems, gems_per_boss, gems_per_area, api_gems, curr_area, False

    estimated = api_gems if api_gems is not None else prev_effective
    is_estimated = False

    # Prefer the highest known gem count as the estimation floor (estimated or API).
    floor_gems = estimated
    if prev_effective is not None and (floor_gems is None or prev_effective > floor_gems):
        floor_gems = prev_effective

    rate = _resolve_gems_per_area(
        gems_per_area,
        gems=anchor_gems if anchor_gems is not None else api_gems,
        area=anchor_area if anchor_area is not None else curr_area,
    )
    if rate is not None and gems_per_area is None:
        gems_per_area = rate

    if (
        boss is not None
        and prev_boss is not None
        and boss > prev_boss
        and floor_gems is not None
    ):
        delta_boss = boss - prev_boss
        boss_rate = gems_per_boss if gems_per_boss is not None else DEFAULT_GEMS_PER_BOSS
        boss_est = int(round(floor_gems + delta_boss * boss_rate))
        if estimated is None or boss_est > estimated:
            estimated = boss_est
            is_estimated = True

    # Anchor-based estimate — stable even when memory area and API area diverge.
    area_est = _estimate_gems_from_area(
        api_gems=api_gems,
        anchor_gems=anchor_gems,
        anchor_area=anchor_area,
        current_area=curr_area,
        gems_per_area=rate,
    )
    if area_est is not None and (estimated is None or area_est > estimated):
        if api_gems is None or area_est > api_gems:
            estimated = area_est
            is_estimated = True

    # Never decrease below a previously shown estimate while the API counter is stalled,
    # but only within the same run (area still advancing / not after a reset drop).
    same_run = (
        curr_area is None
        or prev_area is None
        or curr_area + 2 >= prev_area
    )
    if (
        same_run
        and floor_gems is not None
        and (api_gems is None or api_gems <= floor_gems)
        and (estimated is None or floor_gems > estimated)
        and (api_gems is None or api_gems > 0 or floor_gems == 0)
    ):
        # If API reports 0 gems while we still think we have thousands, trust the API
        # only when area also dropped (handled by reset); otherwise keep floor.
        if api_gems is not None and api_gems == 0 and floor_gems > 0:
            pass
        else:
            estimated = floor_gems
            if api_gems is None or floor_gems > api_gems:
                is_estimated = True

    if (
        estimated is not None
        and prev_effective is not None
        and curr_area is not None
        and prev_area is not None
        and curr_area > prev_area
        and rate is not None
        and (api_gems is None or api_gems <= prev_effective)
    ):
        step_est = int(round(prev_effective + (curr_area - prev_area) * rate))
        if step_est > estimated:
            estimated = step_est
            is_estimated = True

    if estimated is not None and api_gems is not None:
        estimated = max(estimated, api_gems)
        if estimated > api_gems:
            is_estimated = True
        elif estimated == api_gems:
            is_estimated = False

    return estimated, gems_per_boss, gems_per_area, anchor_gems, anchor_area, is_estimated


def _party_with_effective_gems(party: PartySnapshot, *, gems: int | None) -> PartySnapshot:
    if gems is None or gems == party.gems_this_reset:
        return party
    from dataclasses import replace

    return replace(party, gems_this_reset=gems)


def _segment_gains(
    baseline: PartySnapshot,
    current: PartySnapshot,
) -> tuple[float | None, float | None, float | None]:
    areas = _delta(current.current_area, baseline.current_area)
    gold = _delta(current.gold_gained, baseline.gold_gained)
    if gold is None:
        gold = _delta(current.gold, baseline.gold)
    gems = _delta(current.gems_this_reset, baseline.gems_this_reset)
    return areas, gold, gems


def _party_session_totals(state: _PartyTrackState, party: PartySnapshot | None = None) -> tuple[float, float, float]:
    current = party if party is not None else state.latest
    seg_areas, seg_gold, seg_gems = _segment_gains(state.baseline, current)
    return (
        state.accumulated_areas + (seg_areas or 0.0),
        state.accumulated_gold + (seg_gold or 0.0),
        state.accumulated_gems + (seg_gems or 0.0),
    )


def _api_session_totals(state: _PartyTrackState) -> tuple[float, float]:
    """Session boss-kill and API gem gains (exclude area-based gem estimates)."""
    seg_boss = _delta(
        state.api_latest.boss_kills_this_reset,
        state.baseline.boss_kills_this_reset,
    )
    _, _, seg_api_gems = _segment_gains(state.baseline, state.api_latest)
    return (
        state.accumulated_boss_kills + (seg_boss or 0.0),
        state.accumulated_api_gems + (seg_api_gems or 0.0),
    )


def _boss_based_gems_rate(state: _PartyTrackState, segment_elapsed: float) -> float | None:
    seg_boss = _delta(
        state.api_latest.boss_kills_this_reset,
        state.baseline.boss_kills_this_reset,
    )
    if seg_boss is None or seg_boss <= 0:
        return None
    gems_per_boss = state.gems_per_boss or DEFAULT_GEMS_PER_BOSS
    return _rate_per_period(seg_boss * gems_per_boss, segment_elapsed)


def _resolve_gems_rate(
    state: _PartyTrackState,
    *,
    segment_elapsed: float,
) -> float | None:
    """
    Gems/kwartier from API gem deltas, with boss-kill fallback when API counters lag.

    Area-based gem estimates are for display only — using them here mirrors area/kw.
    """
    gems_rate = rolling_rate(state.samples, field_name="gems")
    if gems_rate is not None and gems_rate > 0:
        return gems_rate

    boss_rate = rolling_rate(state.samples, field_name="boss_kills")
    if boss_rate is not None and boss_rate > 0:
        gems_per_boss = state.gems_per_boss or DEFAULT_GEMS_PER_BOSS
        return boss_rate * gems_per_boss

    boss_fallback = _boss_based_gems_rate(state, segment_elapsed)
    if boss_fallback is not None:
        return boss_fallback

    _, session_api_gems = _api_session_totals(state)
    _, _, seg_api_gems = _segment_gains(state.baseline, state.api_latest)
    return _rate_per_period(seg_api_gems, segment_elapsed)


def _append_sample(state: _PartyTrackState, party: PartySnapshot, *, timestamp: float) -> None:
    session_areas, session_gold, _session_gems = _party_session_totals(state, party)
    session_boss_kills, session_api_gems = _api_session_totals(state)
    state.samples.append(
        _MetricSample(
            timestamp=timestamp,
            gems=int(round(session_api_gems)),
            area=int(round(session_areas)),
            gold=session_gold,
            boss_kills=int(round(session_boss_kills)),
        )
    )
    if len(state.samples) > MAX_SAMPLES_PER_PARTY:
        state.samples = state.samples[-MAX_SAMPLES_PER_PARTY:]


def _party_stats_from_state(
    state: _PartyTrackState,
    *,
    session_elapsed: float,
    goal_run_history: tuple[GoalRunRecord, ...] = (),
) -> PartySessionStats:
    segment_elapsed = max(time.time() - state.segment_started_at, 0.0)
    seg_areas, seg_gold, seg_gems = _segment_gains(state.baseline, state.latest)
    session_areas, _session_gold, session_gems = _party_session_totals(state)

    areas_rate = rolling_rate(state.samples, field_name="area")
    gold_rate = rolling_rate(state.samples, field_name="gold")
    gems_rate = _resolve_gems_rate(state, segment_elapsed=segment_elapsed)
    window_sec = rolling_window_span(state.samples)

    # Fallback to segment average while rolling window is still warming up (<3 min).
    if areas_rate is None:
        areas_rate = _rate_per_period(seg_areas, segment_elapsed)
    if gold_rate is None:
        gold_rate = _rate_per_period(seg_gold, segment_elapsed)
    if gems_rate is None:
        gems_rate = _boss_based_gems_rate(state, segment_elapsed)
    if gems_rate is None:
        _, _, seg_api_gems = _segment_gains(state.baseline, state.api_latest)
        gems_rate = _rate_per_period(seg_api_gems, segment_elapsed)

    return PartySessionStats(
        party_index=state.latest.party_index,
        adventure_id=state.latest.adventure_id,
        is_active=state.latest.is_active,
        elapsed_sec=session_elapsed,
        segment_elapsed_sec=segment_elapsed,
        current_area=state.latest.current_area,
        gold=state.latest.gold,
        gems_this_reset=state.latest.gems_this_reset,
        areas_gained=seg_areas,
        gold_gained=seg_gold,
        gems_gained=seg_gems,
        areas_per_quarter=areas_rate,
        gold_per_quarter=gold_rate,
        gems_per_quarter=gems_rate,
        session_areas_gained=session_areas,
        session_gems_gained=session_gems,
        rate_window_sec=window_sec,
        reset_count=state.reset_count,
        gems_estimated=state.gems_estimated,
        adventure_area_goal=state.latest.adventure_area_goal,
        modron_area_goal=state.latest.modron_area_goal,
        goal_run_history=goal_run_history,
    )


class StatsTracker:
    """Track session stats; rebaseline each party after Modron/adventure reset."""

    def __init__(self) -> None:
        self._started_at: float | None = None
        self._party_state: dict[int, _PartyTrackState] = {}
        try:
            from ic_gamedata.goal_run_history_store import load_goal_run_history

            self._goal_run_history = load_goal_run_history()
        except ImportError:
            self._goal_run_history: dict[int, list[GoalRunRecord]] = {}
        self._sample_count = 0
        self._mem_baseline_area: int | None = None
        self._mem_latest_area: int | None = None
        self._memory_sample_count = 0

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def memory_sample_count(self) -> int:
        return self._memory_sample_count

    @property
    def latest(self) -> GameSnapshot | None:
        if not self._party_state:
            return None
        parties = tuple(self._party_state[i].latest for i in sorted(self._party_state))
        active = next((p.party_index for p in parties if p.is_active), None)
        primary = next((p for p in parties if p.is_active), parties[0])
        return GameSnapshot(
            api_call="tracked",
            active_party_index=active,
            parties=parties,
            current_area=primary.current_area,
            gold=primary.gold,
            gold_gained=primary.gold_gained,
            gems_this_reset=primary.gems_this_reset,
            monster_kills=primary.monster_kills,
            boss_kills=primary.boss_kills,
        )

    @property
    def memory_area(self) -> int | None:
        return self._mem_latest_area

    def goal_run_history(self, party_index: int) -> tuple[GoalRunRecord, ...]:
        return tuple(self._goal_run_history.get(party_index, ()))

    def _record_goal_run(self, state: _PartyTrackState) -> None:
        if state.goal_run_recorded_this_segment:
            return
        if not _goal_run_completed(state):
            return
        previous = state.api_latest
        duration = _goal_run_duration_sec(state)
        if duration <= 0 or duration > MAX_PLAUSIBLE_GOAL_RUN_SEC:
            return
        goal = _segment_goal_for_state(state)
        if goal is None or goal <= 0:
            return
        peak = _segment_peak_for_state(state)
        if peak is None and previous.current_area is not None:
            peak = previous.current_area
        record = GoalRunRecord(
            duration_sec=float(duration),
            area_goal=goal,
            peak_area=peak,
            recorded_at=time.time(),
        )
        history = self._goal_run_history.setdefault(previous.party_index, [])
        history.insert(0, record)
        del history[MAX_GOAL_RUN_HISTORY:]
        state.goal_run_recorded_this_segment = True
        try:
            from ic_gamedata.goal_run_history_store import save_goal_run_history

            save_goal_run_history(self._goal_run_history)
        except ImportError:
            pass

    def _maybe_record_goal_run(self, state: _PartyTrackState) -> None:
        """Record as soon as the Modron goal is reached — do not wait for reset."""
        self._record_goal_run(state)

    def _handle_adventure_reset(
        self,
        state: _PartyTrackState,
        *,
        merged_party: PartySnapshot,
        api_party: PartySnapshot,
        now: float,
    ) -> None:
        self._record_goal_run(state)
        self._close_segment(state)
        state.reset_count += 1
        state.baseline = merged_party
        state.latest = merged_party
        state.api_latest = api_party
        state.segment_started_at = now
        state.gems_per_boss = None
        state.gems_per_area = _initial_gems_per_area(merged_party)
        state.gem_anchor_gems = merged_party.gems_this_reset
        state.gem_anchor_area = merged_party.current_area
        state.gems_estimated = False
        state.segment_peak_area = _segment_peak_after_reset(merged_party)
        state.segment_area_goal = merged_party.modron_area_goal or state.segment_area_goal
        state.last_memory_area = merged_party.current_area
        state.goal_run_recorded_this_segment = False

    def reset(self) -> None:
        self._started_at = None
        self._party_state.clear()
        self._sample_count = 0
        self._mem_baseline_area = None
        self._mem_latest_area = None
        self._memory_sample_count = 0

    def _close_segment(self, state: _PartyTrackState) -> None:
        areas, gold, gems = _segment_gains(state.baseline, state.latest)
        if areas is not None:
            state.accumulated_areas += areas
        if gold is not None:
            state.accumulated_gold += gold
        if gems is not None:
            state.accumulated_gems += gems
        _, _, api_gems = _segment_gains(state.baseline, state.api_latest)
        if api_gems is not None:
            state.accumulated_api_gems += api_gems
        api_boss = _delta(
            state.api_latest.boss_kills_this_reset,
            state.baseline.boss_kills_this_reset,
        )
        if api_boss is not None:
            state.accumulated_boss_kills += api_boss

    def add_snapshot(
        self,
        snapshot: GameSnapshot,
        *,
        api_snapshot: GameSnapshot | None = None,
    ) -> None:
        now = time.time()
        if self._started_at is None:
            self._started_at = now

        api_parties = {
            party.party_index: party
            for party in (api_snapshot or snapshot).parties
        }

        for party in snapshot.parties:
            if not party.is_running():
                continue
            idx = party.party_index
            api_party = api_parties.get(idx, party)
            state = self._party_state.get(idx)
            if state is None:
                state = _PartyTrackState(
                    baseline=party,
                    latest=party,
                    api_latest=api_party,
                    segment_started_at=now,
                    gems_per_area=_initial_gems_per_area(party),
                    gem_anchor_gems=party.gems_this_reset,
                    gem_anchor_area=party.current_area,
                    segment_peak_area=_peak_area(party),
                    segment_area_goal=_party_modron_goal(party),
                )
                self._party_state[idx] = state
                _append_sample(state, party, timestamp=now)
                continue

            _sync_segment_goal(state, party)

            # Compare raw API readings only — estimated gems must not trigger resets.
            if detect_adventure_reset(state.api_latest, api_party):
                self._handle_adventure_reset(
                    state,
                    merged_party=party,
                    api_party=api_party,
                    now=now,
                )

            state.api_latest = api_party
            _update_segment_peak(state, party)
            self._maybe_record_goal_run(state)

            effective_gems, state.gems_per_boss, state.gems_per_area, state.gem_anchor_gems, state.gem_anchor_area, state.gems_estimated = _extrapolate_gems(
                state.latest,
                party,
                gems_per_boss=state.gems_per_boss,
                gems_per_area=state.gems_per_area,
                anchor_gems=state.gem_anchor_gems,
                anchor_area=state.gem_anchor_area,
            )
            party = _party_with_effective_gems(party, gems=effective_gems)

            state.latest = party
            _update_segment_peak(state, party)
            self._maybe_record_goal_run(state)
            _append_sample(state, party, timestamp=now)

        self._sample_count += 1

    def add_memory_area(
        self,
        area: int | None = None,
        *,
        gems: int | None = None,
        active_party_index: int | None = None,
    ) -> None:
        """Apply live memory readings (area and/or gems this reset)."""
        if self._started_at is None:
            self._started_at = time.time()
        if area is not None:
            if self._mem_baseline_area is None:
                self._mem_baseline_area = area
            self._mem_latest_area = area
            self._memory_sample_count += 1
            for state in self._party_state.values():
                if active_party_index is not None:
                    if state.latest.party_index != active_party_index:
                        continue
                elif not state.latest.is_active:
                    continue

                prev_area = state.last_memory_area
                if prev_area is None:
                    prev_area = state.api_latest.current_area
                if (
                    prev_area is not None
                    and _trustworthy_memory_area(state, prev_area)
                    and _trustworthy_memory_area(state, area)
                    and _area_drop_values(prev_area, area)
                ):
                    from dataclasses import replace

                    merged_party = replace(state.latest, current_area=area)
                    api_party = replace(
                        state.api_latest,
                        current_area=area,
                        highest_area=area,
                    )
                    self._handle_adventure_reset(
                        state,
                        merged_party=merged_party,
                        api_party=api_party,
                        now=time.time(),
                    )
                elif _trustworthy_memory_area(state, area) and (
                    state.segment_peak_area is None or area > state.segment_peak_area
                ):
                    state.segment_peak_area = area
                    self._maybe_record_goal_run(state)
                state.last_memory_area = area
                break

        if gems is None:
            return

        for state in self._party_state.values():
            if not state.latest.is_active:
                continue
            api_gems = state.api_latest.gems_this_reset
            prev = state.latest.gems_this_reset
            api_area = state.api_latest.current_area
            mem_area = area if area is not None else self._mem_latest_area

            looks_like_reset = (
                (prev is not None and gems + 50 < prev)
                and (
                    (mem_area is not None and api_area is not None and mem_area < 40 and api_area < 40)
                    or (api_gems is not None and gems <= api_gems + 5)
                    or (
                        mem_area is not None
                        and state.gem_anchor_area is not None
                        and mem_area + 50 < state.gem_anchor_area
                    )
                )
            )
            if looks_like_reset:
                state.latest = _party_with_effective_gems(state.latest, gems=gems)
                state.gems_estimated = False
                state.gem_anchor_gems = gems
                state.gem_anchor_area = mem_area
                state.gems_per_area = _initial_gems_per_area(state.latest)
                break

            # Ignore stale memory that is behind both previous estimate and API.
            if prev is not None and gems < prev and api_gems is not None and gems < api_gems:
                break

            if prev is None or gems >= prev or (api_gems is not None and gems > api_gems):
                state.latest = _party_with_effective_gems(state.latest, gems=gems)
                state.gems_estimated = False
                if (
                    mem_area is not None
                    and state.gem_anchor_area is not None
                    and mem_area > state.gem_anchor_area
                    and gems > (state.gem_anchor_gems or 0)
                ):
                    state.gems_per_area = (gems - (state.gem_anchor_gems or 0)) / (
                        mem_area - state.gem_anchor_area
                    )
                state.gem_anchor_gems = gems
                if mem_area is not None:
                    state.gem_anchor_area = mem_area
            break

    def compute(self) -> SessionStats | None:
        if self._started_at is None:
            return None
        if not self._party_state and self._mem_latest_area is None:
            return None

        elapsed = max(time.time() - self._started_at, 0.0)
        party_stats: list[PartySessionStats] = []
        total_areas = 0.0
        total_gold = 0.0
        total_gems = 0.0
        total_gems_per_quarter = 0.0
        total_areas_per_quarter = 0.0
        has_rolling_gems = False
        has_rolling_areas = False

        for idx in sorted(self._party_state):
            ps = _party_stats_from_state(
                self._party_state[idx],
                session_elapsed=elapsed,
                goal_run_history=self.goal_run_history(idx),
            )
            party_stats.append(ps)
            session_areas, session_gold, session_gems = _party_session_totals(self._party_state[idx])
            total_areas += session_areas
            total_gold += session_gold
            total_gems += session_gems
            if ps.gems_per_quarter is not None:
                total_gems_per_quarter += ps.gems_per_quarter
                has_rolling_gems = True
            if ps.areas_per_quarter is not None:
                total_areas_per_quarter += ps.areas_per_quarter
                has_rolling_areas = True

        latest = self.latest
        mem_areas = _delta(self._mem_latest_area, self._mem_baseline_area)

        return SessionStats(
            elapsed_sec=elapsed,
            current_area=latest.current_area if latest is not None else None,
            memory_area=self._mem_latest_area,
            gold=latest.gold if latest is not None else None,
            gems_this_reset=latest.gems_this_reset if latest is not None else None,
            areas_gained=total_areas,
            memory_areas_gained=mem_areas,
            gold_gained=total_gold,
            gems_gained=total_gems,
            areas_per_quarter=total_areas_per_quarter if has_rolling_areas else _rate_per_period(total_areas, elapsed),
            memory_areas_per_quarter=_rate_per_period(mem_areas, elapsed),
            gold_per_quarter=_rate_per_period(total_gold, elapsed),
            gems_per_quarter=total_gems_per_quarter if has_rolling_gems else _rate_per_period(total_gems, elapsed),
            monster_kills_delta=None,
            boss_kills_delta=None,
            sample_count=self._sample_count,
            memory_sample_count=self._memory_sample_count,
            parties=tuple(party_stats),
        )


__all__ = [
    "GOAL_COMPLETION_AREA_TOLERANCE",
    "GOAL_PEAK_SANITY_MARGIN",
    "MAX_GOAL_RUN_HISTORY",
    "MAX_PLAUSIBLE_GOAL_RUN_SEC",
    "RATE_PERIOD_SEC",
    "ROLLING_MAX_WINDOW_SEC",
    "ROLLING_MIN_WINDOW_SEC",
    "GoalRunRecord",
    "PartySessionStats",
    "SessionStats",
    "StatsTracker",
    "_MetricSample",
    "detect_adventure_reset",
    "is_plausible_goal_run_record",
    "rolling_rate",
    "rolling_window_span",
]
