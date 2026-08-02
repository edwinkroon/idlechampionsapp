"""Analytics helpers for Modron goal-run history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ic_gamedata.stats import GoalRunRecord


@dataclass(frozen=True)
class GoalRunChartPoint:
    """One completed Modron run, ordered oldest → newest for charting."""

    run_index: int
    duration_sec: float
    area_goal: int
    peak_area: int | None
    recorded_at: float


@dataclass(frozen=True)
class GoalRunAnalyticsSummary:
    party_index: int
    run_count: int
    area_goal: int | None
    best_sec: float | None
    avg_sec: float | None
    latest_sec: float | None
    points: tuple[GoalRunChartPoint, ...]


def build_goal_run_analytics(
    party_index: int,
    records: Sequence[GoalRunRecord],
) -> GoalRunAnalyticsSummary:
    """Build chart points and summary stats from newest-first history records."""
    if not records:
        return GoalRunAnalyticsSummary(
            party_index=party_index,
            run_count=0,
            area_goal=None,
            best_sec=None,
            avg_sec=None,
            latest_sec=None,
            points=(),
        )

    chronological = tuple(reversed(records))
    points: list[GoalRunChartPoint] = []
    for index, record in enumerate(chronological, start=1):
        points.append(
            GoalRunChartPoint(
                run_index=index,
                duration_sec=record.duration_sec,
                area_goal=record.area_goal,
                peak_area=record.peak_area,
                recorded_at=record.recorded_at,
            )
        )

    durations = [point.duration_sec for point in points]
    latest = records[0].duration_sec
    area_goal = records[0].area_goal
    return GoalRunAnalyticsSummary(
        party_index=party_index,
        run_count=len(points),
        area_goal=area_goal,
        best_sec=min(durations),
        avg_sec=sum(durations) / len(durations),
        latest_sec=latest,
        points=tuple(points),
    )


def party_indexes_with_history(history: dict[int, list[GoalRunRecord]]) -> tuple[int, ...]:
    return tuple(sorted(idx for idx, records in history.items() if records))


def merge_goal_run_history(
    persisted: dict[int, list[GoalRunRecord]],
    live: dict[int, tuple[GoalRunRecord, ...]] | None = None,
) -> dict[int, tuple[GoalRunRecord, ...]]:
    """Merge persisted JSON history with in-memory tracker history (newest first)."""
    merged: dict[int, tuple[GoalRunRecord, ...]] = {
        party_index: tuple(records) for party_index, records in persisted.items() if records
    }
    if not live:
        return merged
    for party_index, records in live.items():
        if not records:
            continue
        existing = merged.get(party_index, ())
        seen = {(r.duration_sec, r.area_goal, r.recorded_at) for r in existing}
        combined = list(existing)
        for record in records:
            key = (record.duration_sec, record.area_goal, record.recorded_at)
            if key not in seen:
                combined.insert(0, record)
                seen.add(key)
        merged[party_index] = tuple(combined[:50])
    return merged


def format_duration_minutes(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(int(seconds), 0)
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}:{secs:02d}"
    return f"{secs}s"


def goal_run_csv_rows(records: Sequence[GoalRunRecord]) -> list[list[str]]:
    rows = [["run", "duration_sec", "duration", "area_goal", "peak_area", "recorded_at"]]
    chronological = reversed(records)
    for index, record in enumerate(chronological, start=1):
        rows.append(
            [
                str(index),
                f"{record.duration_sec:.1f}",
                format_duration_minutes(record.duration_sec),
                str(record.area_goal),
                "" if record.peak_area is None else str(record.peak_area),
                f"{record.recorded_at:.0f}",
            ]
        )
    return rows
