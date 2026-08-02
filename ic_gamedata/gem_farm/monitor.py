"""Stateful farm health evaluation for the active party."""

from __future__ import annotations

import time

from ic_gamedata.gem_farm.baselines import GemRateBaselineStore
from ic_gamedata.gem_farm.config_store import GemFarmConfigStore, load_gem_farm_config
from ic_gamedata.gem_farm.event_log import log_health_alerts
from ic_gamedata.gem_farm.health_rules import evaluate_farm_health, is_gem_farm_monitoring_context
from ic_gamedata.gem_farm.models import FarmHealthStatus, GemFarmConfig, HealthEvaluationInput
from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.stats_models import GoalRunRecord, PartySessionStats


class FarmHealthMonitor:
    """Track area/gem timing and evaluate health rules for the active gem farm."""

    def __init__(self, *, config_store: GemFarmConfigStore | None = None) -> None:
        self._config_store = config_store or GemFarmConfigStore()
        self._gem_baselines = GemRateBaselineStore()
        self._area_anchor: dict[int, tuple[int, float]] = {}
        self._gem_low_since: dict[int, float] = {}
        self._active_alert_ids: dict[int, frozenset[str]] = {}
        self._last_status: FarmHealthStatus | None = None

    @property
    def last_status(self) -> FarmHealthStatus | None:
        return self._last_status

    def reload_config(self) -> GemFarmConfig:
        return self._config_store.load()

    def clear_party_baselines(self, party_index: int) -> None:
        self._gem_baselines.clear_party(party_index)
        self._area_anchor.pop(party_index, None)
        self._gem_low_since.pop(party_index, None)
        self._active_alert_ids.pop(party_index, None)

    def _resolve_modron_goal(
        self,
        party: PartySnapshot,
        ps: PartySessionStats | None,
        memory_modron_goal: int | None,
    ) -> int | None:
        if memory_modron_goal is not None and memory_modron_goal > 0:
            return memory_modron_goal
        if ps is not None and ps.modron_area_goal is not None and ps.modron_area_goal > 0:
            return ps.modron_area_goal
        if party.modron_area_goal is not None and party.modron_area_goal > 0:
            return party.modron_area_goal
        return None

    def _update_trackers(
        self,
        party_index: int,
        *,
        is_active: bool,
        current_area: int | None,
        gems_per_quarter: float | None,
        rate_window_sec: float | None,
        gem_baseline: float | None,
        thresholds_pct: float,
        now: float,
    ) -> tuple[float | None, float | None]:
        if not is_active:
            self._area_anchor.pop(party_index, None)
            self._gem_low_since.pop(party_index, None)
            return None, None

        area_unchanged_sec: float | None = None
        if current_area is not None:
            anchor = self._area_anchor.get(party_index)
            if anchor is None or anchor[0] != current_area:
                self._area_anchor[party_index] = (current_area, now)
            else:
                area_unchanged_sec = now - anchor[1]

        gem_below_sec: float | None = None
        if gem_baseline is not None and gems_per_quarter is not None:
            threshold = gem_baseline * (thresholds_pct / 100.0)
            if gems_per_quarter < threshold:
                low_since = self._gem_low_since.get(party_index)
                if low_since is None:
                    low_since = now
                    self._gem_low_since[party_index] = now
                gem_below_sec = now - low_since
            else:
                self._gem_low_since.pop(party_index, None)

        self._gem_baselines.observe(
            party_index,
            gems_per_quarter=gems_per_quarter,
            rate_window_sec=rate_window_sec,
            now=now,
        )
        return area_unchanged_sec, gem_below_sec

    def evaluate_active_party(
        self,
        *,
        party: PartySnapshot,
        ps: PartySessionStats | None,
        is_active: bool,
        memory_modron_goal: int | None,
        goal_run_history: tuple[GoalRunRecord, ...],
        config: GemFarmConfig | None = None,
        now: float | None = None,
    ) -> FarmHealthStatus:
        if config is None:
            config = load_gem_farm_config()

        ts = now if now is not None else time.time()
        party_index = party.party_index
        modron_goal = self._resolve_modron_goal(party, ps, memory_modron_goal)

        if not is_active:
            status = FarmHealthStatus(
                party_index=party_index,
                level="ok",
                monitoring=False,
                alerts=(),
            )
            self._last_status = status
            self._active_alert_ids.pop(party_index, None)
            return status

        gems_per_quarter = ps.gems_per_quarter if ps is not None else None
        rate_window_sec = ps.rate_window_sec if ps is not None else None
        gem_baseline = self._gem_baselines.baseline_gems_per_quarter(party_index)

        area_unchanged_sec, gem_below_sec = self._update_trackers(
            party_index,
            is_active=is_active,
            current_area=party.current_area,
            gems_per_quarter=gems_per_quarter,
            rate_window_sec=rate_window_sec,
            gem_baseline=gem_baseline,
            thresholds_pct=config.health.gem_drop_pct,
            now=ts,
        )
        gem_baseline = self._gem_baselines.baseline_gems_per_quarter(party_index)

        status = evaluate_farm_health(
            data=HealthEvaluationInput(
                party_index=party_index,
                is_active=is_active,
                modron_goal=modron_goal,
                briv_in_formation=party.briv_in_formation,
                current_area=party.current_area,
                gems_per_quarter=gems_per_quarter,
                rate_window_sec=rate_window_sec,
                goal_run_history=goal_run_history,
                area_unchanged_sec=area_unchanged_sec,
                gem_below_threshold_sec=gem_below_sec,
                now=ts,
            ),
            thresholds=config.health,
            gem_baseline=gem_baseline,
        )

        if status.monitoring:
            prev_ids = self._active_alert_ids.get(party_index, frozenset())
            self._active_alert_ids[party_index] = log_health_alerts(
                party_index=party_index,
                alerts=status.alerts,
                previous_rule_ids=prev_ids,
                now=ts,
            )
        else:
            self._active_alert_ids.pop(party_index, None)

        self._last_status = status
        return status

    def monitoring_hint(
        self,
        *,
        party: PartySnapshot,
        is_active: bool,
        memory_modron_goal: int | None,
        ps: PartySessionStats | None = None,
    ) -> str | None:
        modron_goal = self._resolve_modron_goal(party, ps, memory_modron_goal)
        if is_gem_farm_monitoring_context(
            is_active=is_active,
            modron_goal=modron_goal,
            briv_in_formation=party.briv_in_formation,
        ):
            return None
        if not is_active:
            return "Alleen actieve party wordt gemonitord."
        if modron_goal is None or modron_goal <= 0:
            return "Geen Modron-doel — farm health uitgeschakeld."
        if not party.briv_in_formation:
            return "Briv niet in formation — farm health uitgeschakeld."
        return None
