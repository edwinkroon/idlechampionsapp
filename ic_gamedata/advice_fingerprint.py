"""Advice-relevant fingerprint of a getuserdetails payload."""

from __future__ import annotations

from typing import Any

from ic_gamedata.formation_seats import formation_layout_fingerprint
from ic_gamedata.parsing import parse_int as _parse_int


def party_id_from_payload(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    return _parse_int(details.get("active_game_instance_id"))


def adventure_id_from_payload(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    for inst in details.get("game_instances") or []:
        if not isinstance(inst, dict):
            continue
        if _parse_int(inst.get("game_instance_id")) == active_id:
            return _parse_int(inst.get("current_adventure_id"))
    return _parse_int(details.get("current_adventure_id"))


def _spec_choices_fingerprint(payload: dict[str, Any]) -> tuple[tuple[int, tuple[int, ...]], ...]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return ()
    rows: list[tuple[int, tuple[int, ...]]] = []
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        chosen: list[int] = []
        for key in ("specialization_choices", "upgrades"):
            raw = hero.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                uid = None
                if isinstance(item, dict):
                    uid = _parse_int(item.get("upgrade_id") or item.get("id"))
                else:
                    uid = _parse_int(item)
                if uid is not None and uid > 0:
                    chosen.append(uid)
        if chosen:
            rows.append((hero_id, tuple(sorted(set(chosen)))))
    return tuple(sorted(rows))


def _feat_fingerprint(payload: dict[str, Any]) -> tuple[tuple[int, tuple[int, ...]], ...]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return ()
    rows: list[tuple[int, tuple[int, ...]]] = []
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        raw = hero.get("active_feats")
        if not isinstance(raw, list) or not raw:
            continue
        feats = tuple(sorted({fid for fid in (_parse_int(x) for x in raw) if fid is not None}))
        if feats:
            rows.append((hero_id, feats))
    return tuple(sorted(rows))


def _formation_levels_fingerprint(payload: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    """``(hero_id, level)`` for champions on the live board.

    Pending specialization popups unlock on level thresholds. Without levels in
    the advice fingerprint, advisor/specs stay locked after party start until a
    party switch changes another fingerprint component.
    """
    layout = formation_layout_fingerprint(payload)
    if not layout:
        return ()
    hero_ids = {hid for _seat, hid in layout if hid > 0}
    if not hero_ids:
        return ()

    details = payload.get("details")
    if not isinstance(details, dict):
        return ()
    active_party = party_id_from_payload(payload)
    best: dict[int, int] = {}
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None or hero_id not in hero_ids:
            continue
        game_id = _parse_int(hero.get("game_instance_id"))
        # Prefer party-specific rows; shared roster (0/None) is a fallback.
        if game_id is not None and game_id > 0 and active_party is not None and game_id != active_party:
            continue
        level = _parse_int(hero.get("level")) or 0
        prev = best.get(hero_id)
        if prev is None or level > prev:
            best[hero_id] = level
    return tuple(sorted(best.items()))


def _formation_ilvl_fingerprint(payload: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    """Coarse ``(hero_id, ilvl//100)`` for champions on the live board.

    Bucketed so tiny enchant ticks do not thrash advice, while meaningful gear
    upgrades still invalidate formation/advisor results.
    """
    layout = formation_layout_fingerprint(payload)
    if not layout:
        return ()
    hero_ids = {hid for _seat, hid in layout if hid > 0}
    if not hero_ids:
        return ()
    details = payload.get("details")
    if not isinstance(details, dict):
        return ()
    try:
        from ic_gamedata.party_advisor_formation import _loot_ilvl_by_hero
    except ImportError:
        return ()
    ilvl_by_hero = _loot_ilvl_by_hero(details)
    rows = [
        (hid, int(ilvl_by_hero.get(hid, 0)) // 100)
        for hid in sorted(hero_ids)
    ]
    return tuple(rows)


def _highest_damage_hero_id(payload: dict[str, Any]) -> int | None:
    """Live BUD/top-damage hero for the active party, if the API has reported one.

    Early in a reset this is often missing; when it first appears (or switches),
    carry-relative tips must refresh even if the seat layout did not change.
    """
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    for inst in details.get("game_instances") or []:
        if not isinstance(inst, dict):
            continue
        if active_id is not None and _parse_int(inst.get("game_instance_id")) != active_id:
            continue
        stats = inst.get("stats")
        if isinstance(stats, dict):
            hid = _parse_int(stats.get("this_reset_highest_damage_dealt_hero_id"))
            if hid is not None and hid > 0:
                return hid
        if active_id is not None:
            break
    stats = details.get("stats")
    if isinstance(stats, dict):
        hid = _parse_int(stats.get("this_reset_highest_damage_dealt_hero_id"))
        if hid is not None and hid > 0:
            return hid
    return None


def advice_fingerprint(payload: dict[str, Any] | None) -> tuple[Any, ...] | None:
    """Stable fingerprint of data that should trigger advisor/specs refresh.

    Covers party, adventure, live formation layout, formation hero levels,
    specialization picks, active feats, top-damage (carry) hero, and coarse
    formation item levels.
    """
    if not isinstance(payload, dict):
        return None
    formation = formation_layout_fingerprint(payload)
    if formation is None:
        formation = ()
    return (
        party_id_from_payload(payload),
        adventure_id_from_payload(payload),
        formation,
        _formation_levels_fingerprint(payload),
        _spec_choices_fingerprint(payload),
        _feat_fingerprint(payload),
        _highest_damage_hero_id(payload),
        _formation_ilvl_fingerprint(payload),
    )


def should_refresh_advice(
    *,
    force: bool,
    first: bool,
    changed: bool,
    empty_retry: bool,
    degraded: bool,
) -> bool:
    """Whether a snapshot should re-run advisor/specializations analysis."""
    if degraded and not (force or first or changed or empty_retry):
        return False
    return bool(force or first or changed or empty_retry)


def commit_advice_fingerprint(
    running_fp: tuple[Any, ...] | None,
    *,
    formation_empty: bool,
) -> tuple[Any, ...] | None:
    """Lock a fingerprint only after formation heroes resolved.

    Empty-formation analyses must not lock the fp — otherwise later polls with
    the same layout fingerprint skip until a party switch changes it.
    """
    if formation_empty:
        return None
    return running_fp
