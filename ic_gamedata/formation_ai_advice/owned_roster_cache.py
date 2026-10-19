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

SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 24 * 60 * 60


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
    return json.dumps(
        {
            "v": SCHEMA_VERSION,
            "hero_id": hero_id,
            "feats": feats,
            "specs": specs,
            "upgrades": upgrade_sig,
            "ilvl": ilvl,
            "data_version": data_version,
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


def get_cached_champion_entry(
    cache: dict[str, Any],
    hero_id: int,
    fingerprint: str,
) -> dict[str, Any] | None:
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
    return copy.deepcopy(entry)


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
        cached = get_cached_champion_entry(cache, hero_id, fingerprint)
        if cached is not None:
            return cached, "cache"
    entry = builder()
    put_cached_champion_entry(cache, hero_id, fingerprint, entry)
    return entry, "built"
