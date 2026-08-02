"""Parse Idle Champions webRequestLog.txt API responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.parsing import parse_number as _parse_number

_BLOCK_SPLIT = re.compile(r"\*{10,}")
_CALL_RE = re.compile(r"[?&]call=([^&\s]+)", re.IGNORECASE)


@dataclass(frozen=True)
class PartySnapshot:
    """State for one multi-instance party slot."""

    party_index: int
    adventure_id: int | None
    current_area: int | None
    gold: float | None
    gold_gained: float | None
    gems_this_reset: int | None
    boss_kills_this_reset: int | None
    monster_kills: int | None
    boss_kills: int | None
    seconds_since_reset: int | None = None
    is_active: bool = False
    highest_area: int | None = None
    adventure_area_goal: int | None = None
    modron_area_goal: int | None = None
    custom_name: str | None = None
    patron_id: int | None = None
    patron_tier: int | None = None
    time_warps_used: int | None = None
    briv_sprint_stacks: int | None = None
    briv_steelbones_stacks: int | None = None
    briv_in_formation: bool = False
    active_buffs_text: str | None = None

    def is_running(self) -> bool:
        """True when this party slot looks like an active adventure."""
        if self.adventure_id is not None and self.adventure_id >= 0:
            return True
        return (self.current_area or 0) > 1


@dataclass(frozen=True)
class GameSnapshot:
    """Game state from one API/log entry."""

    api_call: str
    active_party_index: int | None
    parties: tuple[PartySnapshot, ...]
    current_area: int | None
    gold: float | None
    gold_gained: float | None
    gems_this_reset: int | None
    monster_kills: int | None
    boss_kills: int | None

    @property
    def running_parties(self) -> tuple[PartySnapshot, ...]:
        return tuple(p for p in self.parties if p.is_running())

    def has_progress_metrics(self) -> bool:
        if self.running_parties:
            return True
        return any(
            v is not None
            for v in (
                self.current_area,
                self.gold_gained,
                self.gems_this_reset,
                self.monster_kills,
            )
        )


def _party_index_from_instance(index: int, instance: dict[str, Any]) -> int:
    """Use game_instance_id when present; array index is not always the slot id."""
    party_index = _parse_int(instance.get("game_instance_id"))
    return index if party_index is None else party_index


def _party_from_instance(
    index: int,
    instance: dict[str, Any],
    *,
    active_party_index: int | None,
    payload: dict[str, Any] | None = None,
) -> PartySnapshot:
    from ic_gamedata.party_display import parse_instance_extras

    stats = instance.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    party_index = _party_index_from_instance(index, instance)
    extras = parse_instance_extras(instance, payload, party_index=party_index)
    return PartySnapshot(
        party_index=party_index,
        adventure_id=_parse_int(instance.get("current_adventure_id")),
        current_area=_parse_int(instance.get("current_area")),
        gold=_parse_number(instance.get("gold")),
        gold_gained=_parse_number(stats.get("gold_gained")),
        gems_this_reset=_parse_int(stats.get("this_reset_gems_earned")),
        boss_kills_this_reset=_parse_int(stats.get("this_reset_boss_kills")),
        monster_kills=_parse_int(stats.get("this_reset_monster_kills") or stats.get("monster_kills")),
        boss_kills=_parse_int(stats.get("this_reset_boss_kills") or stats.get("boss_kills")),
        seconds_since_reset=_parse_int(instance.get("seconds_since_reset")),
        is_active=active_party_index is not None and party_index == active_party_index,
        highest_area=extras["highest_area"],
        adventure_area_goal=extras["adventure_area_goal"],
        modron_area_goal=extras["modron_area_goal"],
        custom_name=extras["custom_name"],
        patron_id=extras["patron_id"],
        patron_tier=extras["patron_tier"],
        time_warps_used=extras["time_warps_used"],
        briv_sprint_stacks=extras["briv_sprint_stacks"],
        briv_steelbones_stacks=extras["briv_steelbones_stacks"],
        briv_in_formation=extras["briv_in_formation"],
        active_buffs_text=extras["active_buffs_text"],
    )


def _party_from_details(details: dict[str, Any], *, active_party_index: int | None) -> PartySnapshot:
    stats = details.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    return PartySnapshot(
        party_index=0,
        adventure_id=_parse_int(details.get("current_adventure_id")),
        current_area=_parse_int(details.get("current_area")),
        gold=_parse_number(details.get("gold")),
        gold_gained=_parse_number(stats.get("gold_gained")),
        gems_this_reset=_parse_int(stats.get("this_reset_gems_earned")),
        boss_kills_this_reset=_parse_int(stats.get("this_reset_boss_kills")),
        monster_kills=_parse_int(stats.get("this_reset_monster_kills") or stats.get("monster_kills")),
        boss_kills=_parse_int(stats.get("this_reset_boss_kills") or stats.get("boss_kills")),
        seconds_since_reset=_parse_int(details.get("seconds_since_reset")),
        is_active=True,
    )


def _merge_optional_max(current: int | float | None, other: int | float | None) -> int | float | None:
    if other is None:
        return current
    if current is None:
        return other
    return max(current, other)


def merge_party_snapshots(primary: PartySnapshot, secondary: PartySnapshot) -> PartySnapshot:
    """
    Merge two readings of the same party slot.

    Prefer the higher gems/gold counters when the game log is ahead of a lagging
    direct API poll. When the API shows a fresh reset (much lower area), keep the
    API counters instead of stale log values.
    """
    if primary.party_index != secondary.party_index:
        raise ValueError("party_index mismatch")

    api_reset_ahead = (
        primary.current_area is not None
        and secondary.current_area is not None
        and primary.current_area + 2 < secondary.current_area
    )

    gems = primary.gems_this_reset
    if not api_reset_ahead and secondary.gems_this_reset is not None:
        if gems is None or secondary.gems_this_reset > gems:
            gems = secondary.gems_this_reset

    gold_gained = primary.gold_gained
    if not api_reset_ahead:
        merged_gold = _merge_optional_max(primary.gold_gained, secondary.gold_gained)
        gold_gained = merged_gold if isinstance(merged_gold, float) else (
            float(merged_gold) if merged_gold is not None else None
        )

    boss_kills_this_reset = primary.boss_kills_this_reset
    if not api_reset_ahead:
        merged_boss = _merge_optional_max(primary.boss_kills_this_reset, secondary.boss_kills_this_reset)
        boss_kills_this_reset = int(merged_boss) if merged_boss is not None else None

    current_area = primary.current_area
    # Area always follows the live API poll — log snapshots are stale and must not
    # overwrite current_area (even when the log has a higher area from an old session).

    gold = secondary.gold if secondary.gold is not None else primary.gold
    adventure_id = primary.adventure_id if primary.adventure_id is not None else secondary.adventure_id
    seconds_since_reset = (
        primary.seconds_since_reset
        if primary.seconds_since_reset is not None
        else secondary.seconds_since_reset
    )

    def _pick_str(a: str | None, b: str | None) -> str | None:
        if a and a.strip():
            return a
        return b if b and b.strip() else None

    highest_area = primary.highest_area if primary.highest_area is not None else secondary.highest_area
    if not api_reset_ahead:
        merged_highest = _merge_optional_max(primary.highest_area, secondary.highest_area)
        highest_area = int(merged_highest) if merged_highest is not None else None

    time_warps = primary.time_warps_used
    if not api_reset_ahead:
        merged_warps = _merge_optional_max(primary.time_warps_used, secondary.time_warps_used)
        time_warps = int(merged_warps) if merged_warps is not None else None

    briv_stacks = primary.briv_sprint_stacks
    if not api_reset_ahead:
        merged_briv = _merge_optional_max(primary.briv_sprint_stacks, secondary.briv_sprint_stacks)
        briv_stacks = int(merged_briv) if merged_briv is not None else None

    steelbones = primary.briv_steelbones_stacks
    if not api_reset_ahead:
        merged_steel = _merge_optional_max(
            primary.briv_steelbones_stacks,
            secondary.briv_steelbones_stacks,
        )
        steelbones = int(merged_steel) if merged_steel is not None else None

    adventure_area_goal = (
        primary.adventure_area_goal
        if primary.adventure_area_goal is not None
        else secondary.adventure_area_goal
    )
    modron_area_goal = (
        primary.modron_area_goal
        if primary.modron_area_goal is not None
        else secondary.modron_area_goal
    )

    return PartySnapshot(
        party_index=primary.party_index,
        adventure_id=adventure_id,
        current_area=current_area,
        gold=gold,
        gold_gained=gold_gained,
        gems_this_reset=gems,
        boss_kills_this_reset=boss_kills_this_reset,
        monster_kills=primary.monster_kills,
        boss_kills=primary.boss_kills,
        seconds_since_reset=seconds_since_reset,
        # Only one party can be active — prefer the primary (live API) flag, not OR with stale log.
        is_active=primary.is_active,
        highest_area=highest_area,
        adventure_area_goal=adventure_area_goal,
        modron_area_goal=modron_area_goal,
        custom_name=_pick_str(primary.custom_name, secondary.custom_name),
        patron_id=primary.patron_id if primary.patron_id is not None else secondary.patron_id,
        patron_tier=primary.patron_tier if primary.patron_tier is not None else secondary.patron_tier,
        time_warps_used=time_warps,
        briv_sprint_stacks=briv_stacks,
        briv_steelbones_stacks=steelbones,
        briv_in_formation=primary.briv_in_formation,
        active_buffs_text=primary.active_buffs_text or secondary.active_buffs_text,
    )


def merge_snapshots(*snapshots: GameSnapshot | None) -> GameSnapshot | None:
    """Merge multiple snapshots, combining parties that share a party_index."""
    available = [snap for snap in snapshots if snap is not None]
    if not available:
        return None
    if len(available) == 1:
        return available[0]

    party_map: dict[int, PartySnapshot] = {}
    for snap in available:
        for party in snap.parties:
            existing = party_map.get(party.party_index)
            party_map[party.party_index] = (
                merge_party_snapshots(existing, party) if existing is not None else party
            )

    parties = tuple(party_map[i] for i in sorted(party_map))
    active = next(
        (snap.active_party_index for snap in reversed(available) if snap.active_party_index is not None),
        None,
    )
    primary = _primary_party(parties, active)
    if primary is None:
        return None

    return GameSnapshot(
        api_call=available[-1].api_call,
        active_party_index=active,
        parties=parties,
        current_area=primary.current_area,
        gold=primary.gold,
        gold_gained=primary.gold_gained,
        gems_this_reset=primary.gems_this_reset,
        monster_kills=primary.monster_kills,
        boss_kills=primary.boss_kills,
    )


def _primary_party(parties: tuple[PartySnapshot, ...], active_index: int | None) -> PartySnapshot | None:
    if active_index is not None:
        for party in parties:
            if party.party_index == active_index:
                return party
    running = tuple(p for p in parties if p.is_running())
    if running:
        return running[0]
    return parties[0] if parties else None


def snapshot_from_payload(payload: dict[str, Any], *, api_call: str = "") -> GameSnapshot | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None

    active_party_index = _parse_int(details.get("active_game_instance_id"))
    raw_instances = details.get("game_instances")
    parties: list[PartySnapshot] = []
    if isinstance(raw_instances, list) and raw_instances:
        for index, instance in enumerate(raw_instances):
            if isinstance(instance, dict):
                parties.append(
                    _party_from_instance(
                        index,
                        instance,
                        active_party_index=active_party_index,
                        payload=payload,
                    )
                )
    else:
        parties.append(_party_from_details(details, active_party_index=active_party_index))

    party_tuple = tuple(parties)
    primary = _primary_party(party_tuple, active_party_index)
    if primary is None:
        return None

    snap = GameSnapshot(
        api_call=api_call,
        active_party_index=active_party_index,
        parties=party_tuple,
        current_area=primary.current_area,
        gold=primary.gold,
        gold_gained=primary.gold_gained,
        gems_this_reset=primary.gems_this_reset,
        monster_kills=primary.monster_kills,
        boss_kills=primary.boss_kills,
    )
    return snap if snap.has_progress_metrics() else None


def _extract_call(url_line: str) -> str:
    match = _CALL_RE.search(url_line)
    return match.group(1) if match else ""


def parse_web_request_log(text: str) -> list[GameSnapshot]:
    """Parse full log text; returns snapshots in file order."""
    snapshots: list[GameSnapshot] = []
    for block in _BLOCK_SPLIT.split(text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if not lines:
            continue
        api_call = _extract_call(lines[0])
        body = "\n".join(lines[1:]).strip()
        if not body.startswith("{"):
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        snap = snapshot_from_payload(payload, api_call=api_call)
        if snap is not None:
            snapshots.append(snap)
    return snapshots


def read_latest_snapshot(path: Path) -> GameSnapshot | None:
    """Read log file and return the last snapshot with progress metrics."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    snapshots = parse_web_request_log(text)
    return snapshots[-1] if snapshots else None
