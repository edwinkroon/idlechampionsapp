"""Shared dashboard party-tile text (Tk + PySide)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.party_display import format_area_line, format_patron_line, party_tile_title
from ic_gamedata.stats import MAX_GOAL_RUN_HISTORY, GoalRunRecord, PartySessionStats


@dataclass(frozen=True)
class GoalRunHistoryDisplay:
    summary: str | None
    summary_unreliable: bool
    extra: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class PartyTileView:
    title: str
    area: str
    run: str
    gems: str
    areas_rate: str
    patron: str | None
    briv: str | None
    warps: str | None
    buffs: str | None
    goal_runs_summary: str | None = None
    goal_runs_summary_unreliable: bool = False
    goal_runs_extra: tuple[tuple[str, bool], ...] = ()
    modron_progress_pct: int | None = None
    modron_progress_text: str | None = None


def _progress_pct(current_area: int, goal: int) -> int:
    return min(100, max(0, int(100 * current_area / goal)))


def modron_area_progress(
    current_area: int | None,
    modron_goal: int | None,
) -> tuple[int | None, str | None]:
    if current_area is None or modron_goal is None or modron_goal <= 0:
        return None, None
    return (
        _progress_pct(current_area, modron_goal),
        f"Modron: {current_area} / {modron_goal}",
    )


def area_goal_progress(
    current_area: int | None,
    *,
    modron_goal: int | None = None,
    modron_goal_enabled: bool = False,
    adventure_goal: int | None = None,
) -> tuple[int | None, str | None]:
    """Progress bar for Modron Set Area Goal, else adventure completion goal."""
    if current_area is None:
        return None, None
    if modron_goal_enabled and modron_goal is not None and modron_goal > 0:
        return (
            _progress_pct(current_area, modron_goal),
            f"Modron: {current_area} / {modron_goal}",
        )
    if adventure_goal is not None and adventure_goal > 0:
        return (
            _progress_pct(current_area, adventure_goal),
            f"Adventure: {current_area} / {adventure_goal}",
        )
    return None, None


def _goal_run_gems_suffix(gems_earned: int | None) -> str:
    if gems_earned is None:
        return ""
    return f" · {gems_earned} gems"


def format_goal_run_history(
    history: tuple[GoalRunRecord, ...],
    *,
    area_goal: int | None,
    area_goal_enabled: bool = True,
    format_duration: Callable[[float | None], str],
) -> GoalRunHistoryDisplay:
    if not area_goal_enabled:
        return GoalRunHistoryDisplay(summary=None, summary_unreliable=False, extra=())
    if not history:
        if area_goal is not None and area_goal > 0:
            return GoalRunHistoryDisplay(
                summary=f"Modron run: — (no completed run yet, goal {area_goal})",
                summary_unreliable=False,
                extra=(),
            )
        return GoalRunHistoryDisplay(summary=None, summary_unreliable=False, extra=())
    goal = area_goal if area_goal is not None and area_goal > 0 else history[0].area_goal
    latest = history[0]
    summary = (
        f"Last Modron run: {format_duration(latest.duration_sec)}"
        f"{_goal_run_gems_suffix(latest.gems_earned)} (goal {goal})"
    )
    extra = tuple(
        (
            f"{index + 2}. {format_duration(record.duration_sec)}"
            f"{_goal_run_gems_suffix(record.gems_earned)}",
            record.duration_unreliable,
        )
        for index, record in enumerate(history[1:MAX_GOAL_RUN_HISTORY])
    )
    return GoalRunHistoryDisplay(
        summary=summary,
        summary_unreliable=latest.duration_unreliable,
        extra=extra,
    )


def build_party_tile_view(
    party: PartySnapshot,
    *,
    ps: PartySessionStats | None,
    is_active: bool,
    adventure_name: str | None,
    run_sec: float | None,
    gems: int | None,
    gem_prefix: str,
    format_number: Callable[[Any], str],
    format_duration: Callable[[float | None], str],
    format_rate_window: Callable[[float | None], str],
    goal_run_history: tuple[GoalRunRecord, ...] | None = None,
) -> PartyTileView:
    reset_note = f" · {ps.reset_count}× Modron" if ps is not None and ps.reset_count else ""
    window_note = format_rate_window(ps.rate_window_sec if ps is not None else None)

    if ps is not None and ps.areas_per_quarter is not None:
        areas_rate = f"{format_number(ps.areas_per_quarter)} areas/kw ({window_note}{reset_note})"
    elif ps is not None:
        areas_rate = f"areas/kw: — ({window_note}{reset_note})"
    else:
        areas_rate = "areas/qtr: waiting for measurement…"

    patron = format_patron_line(party.patron_id, party.patron_tier)
    briv = None
    if party.briv_in_formation:
        stacks = party.briv_sprint_stacks
        stacks_txt = format_number(stacks) if stacks is not None else "—"
        steel = party.briv_steelbones_stacks
        steel_txt = format_number(steel) if steel is not None else "—"
        briv = f"Briv sprint: {stacks_txt} · steelbones: {steel_txt}"
    warps = None
    if party.time_warps_used is not None:
        warps = f"Time warps: {party.time_warps_used}"
    buffs = party.active_buffs_text

    modron_goal = party.modron_area_goal
    if ps is not None and ps.modron_area_goal is not None:
        modron_goal = ps.modron_area_goal
    milestone = party.adventure_area_goal
    if ps is not None and ps.adventure_area_goal is not None:
        milestone = ps.adventure_area_goal
    modron_enabled = party.modron_set_area_goal_enabled is True
    display_modron_goal = modron_goal if modron_enabled else None
    history = (
        goal_run_history
        if goal_run_history is not None
        else (ps.goal_run_history if ps is not None else ())
    )
    goal_display = format_goal_run_history(
        history,
        area_goal=modron_goal,
        area_goal_enabled=modron_enabled,
        format_duration=format_duration,
    )
    progress_pct, progress_text = area_goal_progress(
        party.current_area,
        modron_goal=modron_goal,
        modron_goal_enabled=modron_enabled,
        adventure_goal=milestone,
    )

    return PartyTileView(
        title=party_tile_title(
            party_index=party.party_index,
            custom_name=party.custom_name,
            adventure_name=adventure_name,
            is_active=is_active,
        ),
        area=format_area_line(
            party.current_area,
            party.highest_area,
            modron_area_goal=display_modron_goal,
            area_goal=milestone if milestone != display_modron_goal else None,
        ),
        run=f"Run: {format_duration(run_sec) if run_sec is not None else '—'}",
        gems=f"Gems this run: {gem_prefix}{gems if gems is not None else '—'}",
        areas_rate=areas_rate,
        patron=patron,
        briv=briv,
        warps=warps,
        buffs=buffs,
        goal_runs_summary=goal_display.summary,
        goal_runs_summary_unreliable=goal_display.summary_unreliable,
        goal_runs_extra=goal_display.extra,
        modron_progress_pct=progress_pct,
        modron_progress_text=progress_text,
    )
