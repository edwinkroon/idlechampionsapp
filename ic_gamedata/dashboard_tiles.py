"""Shared dashboard party-tile text (Tk + PySide)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.party_display import format_area_line, format_patron_line, party_tile_title
from ic_gamedata.stats import MAX_GOAL_RUN_HISTORY, GoalRunRecord, PartySessionStats


@dataclass(frozen=True)
class PartyTileView:
    title: str
    area: str
    run: str
    gold: str
    gold_gained: str
    gold_rate: str
    gems: str
    areas_rate: str
    patron: str | None
    briv: str | None
    warps: str | None
    buffs: str | None
    goal_runs_summary: str | None = None
    goal_runs_extra: tuple[str, ...] = ()
    modron_progress_pct: int | None = None
    modron_progress_text: str | None = None


def modron_area_progress(
    current_area: int | None,
    modron_goal: int | None,
) -> tuple[int | None, str | None]:
    if current_area is None or modron_goal is None or modron_goal <= 0:
        return None, None
    pct = min(100, max(0, int(100 * current_area / modron_goal)))
    return pct, f"Modron: {current_area} / {modron_goal}"


def format_goal_run_history(
    history: tuple[GoalRunRecord, ...],
    *,
    area_goal: int | None,
    format_duration: Callable[[float | None], str],
) -> tuple[str | None, tuple[str, ...]]:
    if not history:
        if area_goal is not None and area_goal > 0:
            return f"Doel-run: — (nog geen voltooide run, Modron-doel {area_goal})", ()
        return None, ()
    goal = area_goal if area_goal is not None and area_goal > 0 else history[0].area_goal
    summary = (
        f"Laatste doel-run: {format_duration(history[0].duration_sec)} (Modron-doel {goal})"
    )
    extra = tuple(
        f"{index + 2}. {format_duration(record.duration_sec)}"
        for index, record in enumerate(history[1:MAX_GOAL_RUN_HISTORY])
    )
    return summary, extra


def build_party_tile_view(
    party: PartySnapshot,
    *,
    ps: PartySessionStats | None,
    is_active: bool,
    adventure_name: str | None,
    run_sec: float | None,
    gems: int | None,
    gem_prefix: str,
    format_gold: Callable[[Any], str],
    format_number: Callable[[Any], str],
    format_duration: Callable[[float | None], str],
    format_rate_window: Callable[[float | None], str],
) -> PartyTileView:
    reset_note = f" · {ps.reset_count}× Modron" if ps is not None and ps.reset_count else ""
    window_note = format_rate_window(ps.rate_window_sec if ps is not None else None)

    if ps is not None and ps.gold_per_quarter is not None:
        gold_rate = f"{format_gold(ps.gold_per_quarter)} gold/kw ({window_note}{reset_note})"
    elif ps is not None:
        gold_rate = f"gold/kw: — ({window_note}{reset_note})"
    else:
        gold_rate = "gold/kw: rates na sessiestart…"

    if ps is not None and ps.areas_per_quarter is not None:
        areas_rate = f"{format_number(ps.areas_per_quarter)} areas/kw ({window_note}{reset_note})"
    elif ps is not None:
        areas_rate = f"areas/kw: — ({window_note}{reset_note})"
    else:
        areas_rate = "areas/kw: rates na sessiestart…"

    gold_gained_val = party.gold_gained

    patron = format_patron_line(party.patron_id, party.patron_tier)
    briv = None
    if party.briv_in_formation:
        stacks = party.briv_sprint_stacks
        stacks_txt = format_number(stacks) if stacks is not None else "—"
        briv = f"Briv sprint: {stacks_txt}"
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
    goal_runs_summary, goal_runs_extra = format_goal_run_history(
        ps.goal_run_history if ps is not None else (),
        area_goal=modron_goal,
        format_duration=format_duration,
    )
    progress_pct, progress_text = modron_area_progress(party.current_area, modron_goal)

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
            modron_area_goal=modron_goal,
            area_goal=milestone if milestone != modron_goal else None,
        ),
        run=f"Run: {format_duration(run_sec) if run_sec is not None else '—'}",
        gold=f"Gold: {format_gold(party.gold)}",
        gold_gained=f"Gold verdiend: {format_gold(gold_gained_val)}",
        gold_rate=gold_rate,
        gems=f"Gems deze run: {gem_prefix}{gems if gems is not None else '—'}",
        areas_rate=areas_rate,
        patron=patron,
        briv=briv,
        warps=warps,
        buffs=buffs,
        goal_runs_summary=goal_runs_summary,
        goal_runs_extra=goal_runs_extra,
        modron_progress_pct=progress_pct,
        modron_progress_text=progress_text,
    )
