"""Session stats and per-quarter-hour rates from game snapshots."""

from __future__ import annotations

import time

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
    detect_adventure_reset,
    is_plausible_goal_run_record,
)
from ic_gamedata.stats_rates import (
    DEFAULT_GEMS_PER_BOSS,
    MAX_SAMPLES_PER_PARTY,
    RATE_PERIOD_SEC,
    ROLLING_MAX_WINDOW_SEC,
    ROLLING_MIN_WINDOW_SEC,
    _delta,
    _extrapolate_gems,
    _initial_gems_per_area,
    _MetricSample,
    _party_with_effective_gems,
    _rate_per_period,
    rolling_rate,
    rolling_window_span,
)
from ic_gamedata.stats_run_history import (
    PartyTrackState as _PartyTrackState,
)
from ic_gamedata.stats_run_history import (
    _goal_run_completed,
    _goal_run_duration_sec,
    _party_modron_goal,
    _peak_area,
    _segment_goal_for_state,
    _segment_peak_after_reset,
    _segment_peak_for_state,
    _sync_segment_goal,
    _trustworthy_memory_area,
    _update_segment_peak,
)

DEFAULT_GEMS_PER_AREA = DEFAULT_GEMS_PER_BOSS / 5.0
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
