"""Farm health anomaly rules (pure evaluation)."""

from __future__ import annotations

import statistics

from ic_gamedata.gem_farm.models import (
    FarmHealthAlert,
    FarmHealthStatus,
    FarmHealthThresholds,
    HealthEvaluationInput,
    HealthLevel,
)
from ic_gamedata.stats_models import GoalRunRecord, is_plausible_goal_run_record

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def median_run_duration_sec(records: tuple[GoalRunRecord, ...]) -> float | None:
    durations = [
        record.duration_sec
        for record in records
        if is_plausible_goal_run_record(record) and not record.duration_unreliable
    ]
    if len(durations) < 3:
        return None
    recent = durations[:20]
    return float(statistics.median(recent))


def _level_from_alerts(alerts: list[FarmHealthAlert]) -> HealthLevel:
    if not alerts:
        return "ok"
    worst = max(_SEVERITY_RANK[alert.severity] for alert in alerts)
    if worst >= _SEVERITY_RANK["critical"]:
        return "critical"
    if worst >= _SEVERITY_RANK["warning"]:
        return "warning"
    return "ok"


def is_gem_farm_monitoring_context(
    *,
    is_active: bool,
    modron_goal: int | None,
    briv_in_formation: bool,
) -> bool:
    return bool(is_active and modron_goal is not None and modron_goal > 0 and briv_in_formation)


def evaluate_farm_health(
    data: HealthEvaluationInput,
    *,
    thresholds: FarmHealthThresholds,
    gem_baseline: float | None,
) -> FarmHealthStatus:
    if not thresholds.enabled or not is_gem_farm_monitoring_context(
        is_active=data.is_active,
        modron_goal=data.modron_goal,
        briv_in_formation=data.briv_in_formation,
    ):
        return FarmHealthStatus(
            party_index=data.party_index,
            level="ok",
            monitoring=False,
            alerts=(),
        )

    alerts: list[FarmHealthAlert] = []

    median_duration = median_run_duration_sec(data.goal_run_history)
    if median_duration is not None:
        recent = [
            record
            for record in data.goal_run_history[:3]
            if is_plausible_goal_run_record(record) and not record.duration_unreliable
        ]
        if len(recent) == 3 and all(
            record.duration_sec > median_duration * (thresholds.run_slowdown_pct / 100.0)
            for record in recent
        ):
            alerts.append(
                FarmHealthAlert(
                    rule_id="run_slowdown",
                    severity="warning",
                    message="Runs trager dan normaal — check dash, Briv, formation",
                    detail=(
                        f"Mediaan {median_duration / 60:.1f} min; "
                        f"laatste 3 runs boven {thresholds.run_slowdown_pct:.0f}%."
                    ),
                )
            )

    if (
        gem_baseline is not None
        and data.gems_per_quarter is not None
        and data.gem_below_threshold_sec is not None
        and data.gem_below_threshold_sec >= thresholds.gem_drop_min_sec
    ):
        threshold_rate = gem_baseline * (thresholds.gem_drop_pct / 100.0)
        if data.gems_per_quarter < threshold_rate:
            alerts.append(
                FarmHealthAlert(
                    rule_id="gem_drop",
                    severity="warning",
                    message="Gem-rate onder baseline",
                    detail=(
                        f"Huidig {data.gems_per_quarter:.1f}/kw vs. baseline {gem_baseline:.1f}/kw "
                        f"({data.gem_below_threshold_sec / 60:.0f} min)."
                    ),
                )
            )

    if (
        data.area_unchanged_sec is not None
        and data.area_unchanged_sec >= thresholds.area_stall_sec
    ):
        alerts.append(
            FarmHealthAlert(
                rule_id="area_stall",
                severity="critical",
                message="Area stagneert — mogelijk stuck",
                detail=f"Area ongewijzigd {data.area_unchanged_sec:.0f}s op {data.current_area}.",
            )
        )

    if data.goal_run_history:
        latest = data.goal_run_history[0]
        if latest.duration_unreliable:
            alerts.append(
                FarmHealthAlert(
                    rule_id="unreliable_run",
                    severity="info",
                    message="Timer onbetrouwbaar — baseline run-duur niet bijgewerkt",
                    detail="Laatste doel-run had onbetrouwbare timing (party gewisseld?).",
                )
            )

    return FarmHealthStatus(
        party_index=data.party_index,
        level=_level_from_alerts(alerts),
        monitoring=True,
        alerts=tuple(alerts),
    )
