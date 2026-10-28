"""Disk cache for owned-roster champion export rows (swap advice).

Cold builds parse every owned champion's abilities/feats/specs. That is fast
after in-memory definition indexes, but a full roster is still multi-second.
Cached rows are reused for up to 24h; individual rows invalidate when the
live loadout fingerprint (feats, specs, ilvl, data version) changes.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.paths import OWNED_ROSTER_CACHE_PATH

SCHEMA_VERSION = 2
DEFAULT_TTL_SECONDS = 24 * 60 * 60


def _definitions_checksum() -> str | None:
    """Stable definitions identity — cache must invalidate when defs change."""
    try:
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    checksum = data.get("checksum")
    if checksum is None:
        return None
    return str(checksum)


def _definition_seat_for_hero(hero_id: int) -> int | None:
    """Permanent F-key seat from hero_defines, or None when unavailable."""
    try:
        from ic_gamedata.specialization_data import hero_seat_id_map_from_cached_definitions

        seat = hero_seat_id_map_from_cached_definitions().get(int(hero_id))
    except Exception:
        return None
    if isinstance(seat, int) and 1 <= seat <= 12:
        return seat
    return None


def _apply_definition_seat(entry: dict[str, Any], hero_id: int) -> dict[str, Any]:
    """Overwrite ``entry['seat']`` from hero_defines when a permanent seat is known."""
    seat = _definition_seat_for_hero(hero_id)
    if seat is not None:
        entry["seat"] = seat
    return entry


def _seat_matches_definitions(entry: dict[str, Any], hero_id: int) -> bool:
    """False when cached seat disagrees with hero_defines.seat_id."""
    expected = _definition_seat_for_hero(hero_id)
    if expected is None:
        return True  # cannot verify — do not force rebuild on seat alone
    actual = entry.get("seat")
    return isinstance(actual, int) and actual == expected


def _entry_looks_mechanics_complete(entry: dict[str, Any], hero_id: int) -> bool:
    """Reject cached rows that lack kit abilities while definitions have them.

    Prevents a stale incomplete cache (defs unloaded at build time) from
    poisoning BASE_SNAPSHOT exports after definitions become available.
    Also rejects rows whose permanent ``seat`` disagrees with hero_defines
    (e.g. stub/poisoned seat=1 for newer champions).
    """
    if not _seat_matches_definitions(entry, hero_id):
        return False
    abilities = entry.get("abilities")
    if isinstance(abilities, list) and abilities:
        # At least one ability should carry mechanical prose when defs are rich.
        if any(
            isinstance(a, dict)
            and (
                a.get("mechanical_text")
                or a.get("text")
                or a.get("effect")
            )
            for a in abilities
        ):
            return True
        # Named abilities without prose still count as "attempted" export.
        if any(isinstance(a, dict) and a.get("name") for a in abilities):
            return True
    try:
        from ic_gamedata.formation_ai_advice.export import _upgrades_by_hero_id

        rows = _upgrades_by_hero_id().get(int(hero_id), ())
    except Exception:
        return True  # cannot verify — keep cache
    kit = [
        r
        for r in rows
        if isinstance(r, dict) and not r.get("specialization_name")
    ]
    if not kit:
        return True  # hero truly has no kit upgrades in defs
    # Definitions have kit upgrades but cache entry has none — stale/incomplete.
    return False


def _hero_row(payload: dict[str, Any], hero_id: int) -> dict[str, Any] | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        if _parse_int(hero.get("hero_id")) == hero_id:
            return hero
    return None


def loadout_fingerprint(
    payload: dict[str, Any],
    hero_id: int,
    *,
    ilvl: int | None = None,
    slot_ilvls: dict[int, int] | None = None,
    data_version: str | None = None,
) -> str:
    """Stable key for whether a cached champion row is still valid."""
    hero = _hero_row(payload, hero_id) or {}
    feats = sorted(
        x
        for x in (_parse_int(v) for v in (hero.get("active_feats") or []))
        if x is not None
    )
    specs = sorted(
        x
        for x in (_parse_int(v) for v in (hero.get("specialization_choices") or []))
        if x is not None
    )
    upgrades = hero.get("upgrades")
    upgrade_sig: list[int] = []
    if isinstance(upgrades, list):
        for item in upgrades:
            if isinstance(item, dict):
                uid = _parse_int(item.get("id") or item.get("upgrade_id"))
            else:
                uid = _parse_int(item)
            if uid is not None:
                upgrade_sig.append(uid)
        upgrade_sig.sort()
    slot_sig = (
        [[int(slot_id), int(level)] for slot_id, level in sorted(slot_ilvls.items())]
        if slot_ilvls
        else None
    )
    return json.dumps(
        {
            "v": SCHEMA_VERSION,
            "hero_id": hero_id,
            "feats": feats,
            "specs": specs,
            "upgrades": upgrade_sig,
            "ilvl": ilvl,
            "slot_ilvls": slot_sig,
            "data_version": data_version,
            "definitions_checksum": _definitions_checksum(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _empty_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "cached_at": 0.0,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
        "entries": {},
    }


def load_owned_roster_cache(
    path: Path | None = None,
    *,
    now: float | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """Load cache file; return empty structure when missing, stale, or corrupt."""
    target = path or OWNED_ROSTER_CACHE_PATH
    if not target.is_file():
        return _empty_payload()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_payload()
    if not isinstance(raw, dict):
        return _empty_payload()
    if raw.get("schema_version") != SCHEMA_VERSION:
        return _empty_payload()
    cached_at = raw.get("cached_at")
    try:
        cached_at_f = float(cached_at)
    except (TypeError, ValueError):
        return _empty_payload()
    age = (time.time() if now is None else now) - cached_at_f
    file_ttl = raw.get("ttl_seconds")
    try:
        effective_ttl = int(file_ttl) if file_ttl is not None else ttl_seconds
    except (TypeError, ValueError):
        effective_ttl = ttl_seconds
    if age < 0 or age > effective_ttl:
        return _empty_payload()
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        return _empty_payload()
    return {
        "schema_version": SCHEMA_VERSION,
        "cached_at": cached_at_f,
        "ttl_seconds": effective_ttl,
        "entries": entries,
    }


def save_owned_roster_cache(
    entries: dict[int, dict[str, Any]],
    *,
    path: Path | None = None,
    cached_at: float | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> None:
    target = path or OWNED_ROSTER_CACHE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "cached_at": time.time() if cached_at is None else cached_at,
        "ttl_seconds": ttl_seconds,
        "entries": {
            str(hid): entry
            for hid, entry in sorted(entries.items(), key=lambda kv: kv[0])
            if isinstance(entry, dict)
        },
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _raw_cached_entry(
    cache: dict[str, Any],
    hero_id: int,
    fingerprint: str,
) -> dict[str, Any] | None:
    """Return the stored entry dict when fingerprint matches (no copy/sanitize)."""
    entries = cache.get("entries")
    if not isinstance(entries, dict):
        return None
    row = entries.get(str(hero_id))
    if not isinstance(row, dict):
        return None
    if row.get("fingerprint") != fingerprint:
        return None
    entry = row.get("entry")
    if not isinstance(entry, dict):
        return None
    return entry


def get_cached_champion_entry(
    cache: dict[str, Any],
    hero_id: int,
    fingerprint: str,
) -> dict[str, Any] | None:
    entry = _raw_cached_entry(cache, hero_id, fingerprint)
    if entry is None:
        return None
    return _apply_definition_seat(copy.deepcopy(entry), hero_id)


def put_cached_champion_entry(
    cache: dict[str, Any],
    hero_id: int,
    fingerprint: str,
    entry: dict[str, Any],
) -> None:
    entries = cache.setdefault("entries", {})
    if not isinstance(entries, dict):
        cache["entries"] = {}
        entries = cache["entries"]
    # Store a copy without transient swap-only fields.
    stored = copy.deepcopy(entry)
    for key in (
        "eligibility",
        "base_restriction_check",
        "permanent_seat_vs_party",
        "bench_loadout",
        "practical_availability",
        "inclusion",
        "inclusion_reason",
        "has_relevant_data_gaps",
        "in_party",
        "owned",
        "locked",
        "lock_reason",
    ):
        stored.pop(key, None)
    _apply_definition_seat(stored, hero_id)
    entries[str(hero_id)] = {
        "fingerprint": fingerprint,
        "entry": stored,
    }


def entries_for_save(cache: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Flatten cache entries for ``save_owned_roster_cache``."""
    raw = cache.get("entries")
    if not isinstance(raw, dict):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for key, row in raw.items():
        hid = _parse_int(key)
        if hid is None or not isinstance(row, dict):
            continue
        out[hid] = row
    return out


def resolve_champion_entry(
    *,
    cache: dict[str, Any],
    hero_id: int,
    fingerprint: str,
    builder,
    force_refresh: bool = False,
) -> tuple[dict[str, Any], str]:
    """Return ``(entry, source)`` where source is ``cache`` or ``built``."""
    if not force_refresh:
        # Completeness (incl. seat vs defines) on the raw stored row — sanitizing
        # seat first would hide poisoned seat=1 stubs and skip a needed rebuild.
        raw = _raw_cached_entry(cache, hero_id, fingerprint)
        if raw is not None and _entry_looks_mechanics_complete(raw, hero_id):
            return _apply_definition_seat(copy.deepcopy(raw), hero_id), "cache"
    entry = builder()
    put_cached_champion_entry(cache, hero_id, fingerprint, entry)
    return _apply_definition_seat(copy.deepcopy(entry), hero_id), "built"
