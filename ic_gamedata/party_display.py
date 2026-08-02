"""Format party/instance fields for the dashboard."""

from __future__ import annotations

from typing import Any

from ic_gamedata.buff_names import buff_display_name, build_buff_name_map
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.patron_roster import PATRON_NAMES

BRIV_HERO_ID = 58

# Centiseconds (1/100 s) — matches typical getuserdetails remaining_time scale.
_TIME_CS = 100.0


def _hero_in_formation(
    instance: dict[str, Any],
    hero_id: int,
    payload: dict[str, Any] | None = None,
    *,
    party_index: int | None = None,
) -> bool:
    formation = instance.get("formation")
    if isinstance(formation, list):
        for raw in formation:
            hid = _parse_int(raw)
            if hid is not None and hid > 0 and hid == hero_id:
                return True

    seats = instance.get("hero_in_seats")
    if isinstance(seats, dict):
        for raw in seats.values():
            if _parse_int(raw) == hero_id:
                return True

    saves = instance.get("formation_saves_v2")
    if isinstance(saves, list):
        for save in saves:
            if not isinstance(save, dict):
                continue
            grid = save.get("formation")
            if not isinstance(grid, list):
                continue
            for raw in grid:
                hid = _parse_int(raw)
                if hid is not None and hid > 0 and hid == hero_id:
                    return True

    if payload is not None and party_index is not None:
        details = payload.get("details")
        if isinstance(details, dict):
            for hero in details.get("heroes") or []:
                if not isinstance(hero, dict):
                    continue
                if _parse_int(hero.get("hero_id")) != hero_id:
                    continue
                if hero.get("in_seat") not in (1, "1", True):
                    continue
                game_id = _parse_int(hero.get("game_instance_id"))
                if game_id is None or game_id <= 0 or game_id == party_index:
                    return True

    return False


def format_buff_remaining(raw: int | None) -> str | None:
    if raw is None or raw <= 0:
        return None
    sec = raw / _TIME_CS
    if sec >= 3600:
        hours = int(sec // 3600)
        mins = int((sec % 3600) // 60)
        return f"{hours}u {mins}m" if mins else f"{hours}u"
    if sec >= 60:
        return f"{int(sec // 60)}m"
    return f"{int(sec)}s"


def format_buffs_block(parts: list[str]) -> str | None:
    """Format active buffs for the dashboard tile."""
    if not parts:
        return None
    if len(parts) == 1:
        return f"Buffs: {parts[0]}"
    return "Buffs:\n" + "\n".join(f"· {part}" for part in parts)


def _account_briv_stat_matches_other_party(
    payload: dict[str, Any],
    *,
    party_index: int,
    account_stacks: int,
    stat_key: str,
) -> bool:
    """True when account stacks equal another party's instance value (likely stale)."""
    details = payload.get("details")
    if not isinstance(details, dict):
        return False
    instances = details.get("game_instances")
    if not isinstance(instances, list):
        return False
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        gid = _parse_int(inst.get("game_instance_id"))
        if gid is None or gid == party_index:
            continue
        other_stats = inst.get("stats")
        if not isinstance(other_stats, dict):
            continue
        other = _parse_int(other_stats.get(stat_key))
        if other is not None and other == account_stacks:
            return True
    return False


def _briv_stat_stacks_for_instance(
    instance: dict[str, Any],
    stats: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    party_index: int | None,
    briv_in: bool,
    stat_key: str,
) -> int | None:
    """Read Briv sprint or steelbones stacks for one party from instance/account stats."""
    if not briv_in:
        return None

    instance_stacks = _parse_int(stats.get(stat_key))
    account_stacks: int | None = None
    is_active = False

    if payload is not None and party_index is not None:
        details = payload.get("details")
        if isinstance(details, dict):
            active_id = _parse_int(details.get("active_game_instance_id"))
            is_active = active_id == party_index
            if is_active:
                account_stats = details.get("stats")
                if isinstance(account_stats, dict):
                    account_stacks = _parse_int(account_stats.get(stat_key))

    if is_active:
        # details.stats tracks the focused window — but after a party switch it can
        # still hold the previous party's stacks. Ignore that stale fallback.
        if (
            instance_stacks is None
            and account_stacks is not None
            and payload is not None
            and party_index is not None
            and _account_briv_stat_matches_other_party(
                payload,
                party_index=party_index,
                account_stacks=account_stacks,
                stat_key=stat_key,
            )
        ):
            return None
        if account_stacks is None:
            return instance_stacks
        if instance_stacks is None:
            return account_stacks
        return max(account_stacks, instance_stacks)

    return instance_stacks


def _briv_sprint_stacks_for_instance(
    instance: dict[str, Any],
    stats: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    party_index: int | None,
    briv_in: bool,
) -> int | None:
    return _briv_stat_stacks_for_instance(
        instance,
        stats,
        payload,
        party_index=party_index,
        briv_in=briv_in,
        stat_key="briv_sprint_stacks",
    )


def _briv_steelbones_stacks_for_instance(
    instance: dict[str, Any],
    stats: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    party_index: int | None,
    briv_in: bool,
) -> int | None:
    return _briv_stat_stacks_for_instance(
        instance,
        stats,
        payload,
        party_index=party_index,
        briv_in=briv_in,
        stat_key="briv_steelbones_stacks",
    )


def summarize_active_buffs(instance: dict[str, Any], payload: dict[str, Any] | None) -> str | None:
    """Active potions/buffs with remaining time (one per line when multiple)."""
    active_ids: set[int] = set()
    for raw in instance.get("active_buff_ids") or []:
        buff_id = _parse_int(raw)
        if buff_id is not None:
            active_ids.add(buff_id)

    buffs = instance.get("buffs")
    if not isinstance(buffs, list):
        return None

    name_map = build_buff_name_map(payload)
    parts: list[str] = []
    for item in buffs:
        if not isinstance(item, dict):
            continue
        buff_id = _parse_int(item.get("buff_id"))
        if buff_id is None:
            continue
        remaining = _parse_int(item.get("remaining_time"))
        if remaining is None or remaining <= 0:
            continue
        if active_ids and buff_id not in active_ids:
            continue
        label = name_map.get(buff_id) or buff_display_name(buff_id, payload)
        time_txt = format_buff_remaining(remaining)
        if time_txt:
            parts.append(f"{label} ({time_txt} rest)")
        else:
            parts.append(label)

    if not parts:
        return None
    return format_buffs_block(parts)


def format_patron_line(patron_id: int | None, patron_tier: int | None) -> str | None:
    if patron_id is None or patron_id <= 0:
        return None
    name = PATRON_NAMES.get(patron_id, f"Patron {patron_id}")
    if patron_tier is not None and patron_tier > 0:
        return f"Patron: {name} · tier {patron_tier}"
    return f"Patron: {name}"


def party_tile_title(
    *,
    party_index: int,
    custom_name: str | None,
    adventure_name: str | None,
    is_active: bool,
) -> str:
    name = (custom_name or "").strip()
    if name:
        title = f"Party {party_index} · {name}"
    else:
        title = f"Party {party_index}"
    if adventure_name:
        title += f", {adventure_name}"
    elif not name:
        pass
    if is_active:
        title += " · actief venster"
    return title


def format_area_line(
    current_area: int | None,
    highest_area: int | None,
    *,
    modron_area_goal: int | None = None,
    area_goal: int | None = None,
) -> str:
    cur = current_area if current_area is not None else "—"
    if highest_area is not None and highest_area > 0:
        if current_area is not None and highest_area != current_area:
            base = f"Area: {cur} (wall {highest_area})"
        elif current_area is None:
            base = f"Area: — (wall {highest_area})"
        else:
            base = f"Area: {cur}"
    else:
        base = f"Area: {cur}"
    if modron_area_goal is not None and modron_area_goal > 0:
        return f"{base} · Modron-doel {modron_area_goal}"
    if area_goal is not None and area_goal > 0:
        return f"{base} · milestone {area_goal}"
    return base


def instance_for_party(payload: dict[str, Any] | None, party_index: int) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    instances = details.get("game_instances")
    if not isinstance(instances, list):
        return None
    for index, inst in enumerate(instances):
        if not isinstance(inst, dict):
            continue
        game_id = _parse_int(inst.get("game_instance_id"))
        slot = game_id if game_id is not None else index
        if slot == party_index:
            return inst
    return None


def refresh_party_from_payload(
    party,
    payload: dict[str, Any] | None,
    *,
    memory_modron_area: int | None = None,
):
    """Re-resolve instance-bound dashboard fields from the latest API payload."""
    from dataclasses import replace

    from ic_gamedata.log_parser import PartySnapshot

    if not isinstance(party, PartySnapshot):
        return party
    instance = instance_for_party(payload, party.party_index)
    if instance is None:
        return party
    extras = parse_instance_extras(
        instance,
        payload,
        party_index=party.party_index,
        memory_modron_area=memory_modron_area,
    )
    return replace(party, **extras)


def refresh_snapshot_from_payload(
    snapshot,
    payload: dict[str, Any] | None,
    *,
    memory_modron_area: int | None = None,
):
    """Refresh all party instance fields on a snapshot from the live payload."""
    from dataclasses import replace

    from ic_gamedata.log_parser import GameSnapshot

    if not isinstance(snapshot, GameSnapshot) or not isinstance(payload, dict):
        return snapshot
    parties = tuple(
        refresh_party_from_payload(
            party,
            payload,
            memory_modron_area=memory_modron_area if party.is_active else None,
        )
        for party in snapshot.parties
    )
    return replace(snapshot, parties=parties)


def refresh_party_buff_text(party, payload: dict[str, Any] | None):
    """Backward-compatible alias — refreshes all instance fields, not only buffs."""
    return refresh_party_from_payload(party, payload)


def parse_instance_extras(
    instance: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    party_index: int | None = None,
    memory_modron_area: int | None = None,
) -> dict[str, Any]:
    """Extract dashboard fields from one game_instances[] entry."""
    if party_index is None:
        party_index = _parse_int(instance.get("game_instance_id"))
    stats = instance.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    custom_raw = instance.get("custom_name")
    custom_name = str(custom_raw).strip() if custom_raw else None
    if not custom_name:
        custom_name = None
    briv_in = _hero_in_formation(
        instance,
        BRIV_HERO_ID,
        payload,
        party_index=party_index,
    )
    briv_stacks = _briv_sprint_stacks_for_instance(
        instance,
        stats,
        payload,
        party_index=party_index,
        briv_in=briv_in,
    )
    steelbones = _briv_steelbones_stacks_for_instance(
        instance,
        stats,
        payload,
        party_index=party_index,
        briv_in=briv_in,
    )
    from ic_gamedata.modron_area_goal import resolve_modron_area_goal

    modron_area_goal = resolve_modron_area_goal(
        instance,
        payload,
        party_index=party_index,
        memory_modron_area=memory_modron_area,
    )
    return {
        "highest_area": _parse_int(instance.get("highest_area")),
        "adventure_area_goal": _parse_int(stats.get("adventure_area_goal")),
        "modron_area_goal": modron_area_goal,
        "custom_name": custom_name,
        "patron_id": _parse_int(instance.get("current_patron_id")),
        "patron_tier": _parse_int(instance.get("current_patron_tier")),
        "time_warps_used": _parse_int(stats.get("time_warps_used_this_reset")),
        "briv_sprint_stacks": briv_stacks,
        "briv_steelbones_stacks": steelbones,
        "briv_in_formation": briv_in,
        "active_buffs_text": summarize_active_buffs(instance, payload),
    }
