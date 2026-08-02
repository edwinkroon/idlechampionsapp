"""Merge tracker + API (+ optional memory) readings for dashboard display."""

from __future__ import annotations

from dataclasses import replace

from ic_gamedata.log_parser import PartySnapshot


def _merge_optional_briv_stacks(
    api_stacks: int | None,
    tracked_stacks: int | None,
    *,
    tracked_area: int | None = None,
    api_area: int | None = None,
) -> int | None:
    """Merge Briv sprint stacks across polls.

    During a run stacks only increase, so we keep the highest known value.
    After a Modron reset (area drops sharply) trust the API again — even if lower.
    """
    area_reset = (
        tracked_area is not None
        and api_area is not None
        and api_area + 20 < tracked_area
    )
    if area_reset:
        return api_stacks
    if api_stacks is None:
        return tracked_stacks
    if tracked_stacks is None:
        return api_stacks
    return max(api_stacks, tracked_stacks)


def enrich_party_for_dashboard(
    tracked: PartySnapshot,
    api_party: PartySnapshot | None,
    *,
    is_active: bool,
    memory_area: int | None,
    memory_gems: int | None,
    clear_stale_memory_gems: bool = False,
) -> tuple[PartySnapshot, bool]:
    """
    Return (display party, whether memory gems were cleared as stale).

    Memory overrides apply only to the active game window.
    """
    party = tracked
    cleared_memory = False

    if api_party is not None:
        party = replace(
            tracked,
            adventure_id=api_party.adventure_id
            if api_party.adventure_id is not None
            else tracked.adventure_id,
            current_area=api_party.current_area
            if api_party.current_area is not None
            else tracked.current_area,
            gold=api_party.gold if api_party.gold is not None else tracked.gold,
            gold_gained=api_party.gold_gained
            if api_party.gold_gained is not None
            else tracked.gold_gained,
            seconds_since_reset=api_party.seconds_since_reset
            if api_party.seconds_since_reset is not None
            else tracked.seconds_since_reset,
            highest_area=api_party.highest_area
            if api_party.highest_area is not None
            else tracked.highest_area,
            modron_area_goal=api_party.modron_area_goal
            if api_party.modron_area_goal is not None
            else tracked.modron_area_goal,
            adventure_area_goal=api_party.adventure_area_goal
            if api_party.adventure_area_goal is not None
            else tracked.adventure_area_goal,
            custom_name=api_party.custom_name or tracked.custom_name,
            patron_id=api_party.patron_id
            if api_party.patron_id is not None
            else tracked.patron_id,
            patron_tier=api_party.patron_tier
            if api_party.patron_tier is not None
            else tracked.patron_tier,
            time_warps_used=api_party.time_warps_used
            if api_party.time_warps_used is not None
            else tracked.time_warps_used,
            briv_sprint_stacks=_merge_optional_briv_stacks(
                api_party.briv_sprint_stacks,
                tracked.briv_sprint_stacks,
                tracked_area=tracked.current_area,
                api_area=api_party.current_area,
            ),
            briv_steelbones_stacks=_merge_optional_briv_stacks(
                api_party.briv_steelbones_stacks,
                tracked.briv_steelbones_stacks,
                tracked_area=tracked.current_area,
                api_area=api_party.current_area,
            ),
            briv_in_formation=api_party.briv_in_formation or tracked.briv_in_formation,
            active_buffs_text=api_party.active_buffs_text or tracked.active_buffs_text,
            gems_this_reset=api_party.gems_this_reset
            if api_party.gems_this_reset is not None
            else tracked.gems_this_reset,
            boss_kills_this_reset=api_party.boss_kills_this_reset
            if api_party.boss_kills_this_reset is not None
            else tracked.boss_kills_this_reset,
        )

    gems = party.gems_this_reset
    area = party.current_area

    if (
        clear_stale_memory_gems
        and is_active
        and api_party is not None
        and api_party.gems_this_reset is not None
        and memory_gems is not None
        and api_party.current_area is not None
        and api_party.current_area < 40
        and memory_gems > api_party.gems_this_reset + 50
    ):
        cleared_memory = True
        memory_gems = None

    if is_active:
        if memory_area is not None:
            area = memory_area
        if memory_gems is not None:
            gems = memory_gems
        elif api_party is not None and api_party.gems_this_reset is not None:
            if tracked.gems_this_reset is None or (
                api_party.gems_this_reset < (tracked.gems_this_reset or 0)
                and api_party.current_area is not None
                and api_party.current_area < 40
            ):
                gems = api_party.gems_this_reset

    return replace(party, current_area=area, gems_this_reset=gems), cleared_memory
