"""Local registry of BASE_SNAPSHOT files the user explicitly saved/exported.

Distinction:
- Built locally (in-memory / mirror) ≠ exported (saved path recorded).
- User-declared shared ≠ technical proof that any AI still has the file.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ic_gamedata.formation_ai_advice.export_budget import count_chars, count_utf8_bytes
from ic_gamedata.formation_ai_advice.snapshot_export import minify_json
from ic_gamedata.paths import (
    ADVICE_SNAPSHOT_REGISTRY_PATH,
    ADVICE_SNAPSHOTS_DIR,
    BASISGEGEVENS_DIR,
)

REGISTRY_SCHEMA = 2
_MAX_HISTORY = 20


def _empty_registry() -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_SCHEMA,
        # Last explicitly exported (saved/downloaded) snapshot — advice refs use this.
        "last_exported_snapshot_id": None,
        "last_exported_path": None,
        # Basename of the real export file (e.g. basicdata_DDMMYYYY_HHMMSS.json).
        # Search aid only — identity remains snapshot_id + hashes.
        "last_exported_filename": None,
        "last_exported_at": None,
        "last_exported_char_count": None,
        "last_exported_utf8_bytes": None,
        "last_exported_coverage": None,
        "last_exported_mechanics_hash": None,
        "last_exported_account_state_hash": None,
        # Legacy aliases kept in sync for older readers / freshness fallback.
        "last_snapshot_id": None,
        "last_saved_path": None,
        "last_created_at": None,
        "last_char_count": None,
        "last_utf8_bytes": None,
        "last_coverage": None,
        "last_mechanics_hash": None,
        "last_account_state_hash": None,
        # User declaration only — not AI verification.
        "user_declared_shared_snapshot_id": None,
        "user_declared_shared_at": None,
        "history": [],
    }


def exported_basename_from_registry(registry: dict[str, Any] | None = None) -> str | None:
    """Real export filename for snapshot_ref, or ``None`` when unknown (legacy).

    Never invents ``{snapshot_id}.json`` — that is not the on-disk name for
    ``basicdata_*.json`` exports.
    """
    reg = registry if isinstance(registry, dict) else load_snapshot_registry()
    explicit = reg.get("last_exported_filename")
    if isinstance(explicit, str) and explicit.strip():
        return Path(explicit.strip()).name
    for key in ("last_exported_path", "last_saved_path"):
        raw = reg.get(key)
        if not raw:
            continue
        name = Path(str(raw)).name
        if name:
            return name
    return None


def load_snapshot_registry() -> dict[str, Any]:
    path = ADVICE_SNAPSHOT_REGISTRY_PATH
    if not path.is_file():
        return _empty_registry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_registry()
    if not isinstance(raw, dict):
        return _empty_registry()
    out = _empty_registry()
    for key in out:
        if key == "history":
            continue
        if key in raw:
            out[key] = raw[key]
    hist = raw.get("history")
    out["history"] = hist if isinstance(hist, list) else []

    # Migrate v1 registries that only had last_snapshot_id.
    if not out.get("last_exported_snapshot_id") and out.get("last_snapshot_id"):
        out["last_exported_snapshot_id"] = out["last_snapshot_id"]
        out["last_exported_path"] = out.get("last_saved_path")
        out["last_exported_at"] = out.get("last_created_at")
        out["last_exported_char_count"] = out.get("last_char_count")
        out["last_exported_utf8_bytes"] = out.get("last_utf8_bytes")
        out["last_exported_coverage"] = out.get("last_coverage")
        out["last_exported_mechanics_hash"] = out.get("last_mechanics_hash")
        out["last_exported_account_state_hash"] = out.get("last_account_state_hash")
    # Backfill basename from path when an older registry omitted the field.
    if not out.get("last_exported_filename"):
        derived = exported_basename_from_registry(out)
        if derived:
            out["last_exported_filename"] = derived
    return out


def save_snapshot_registry(registry: dict[str, Any]) -> None:
    path = ADVICE_SNAPSHOT_REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_exported_snapshot_meta(registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return meta suitable for advice_request snapshot_ref (exported only)."""
    reg = registry if isinstance(registry, dict) else load_snapshot_registry()
    sid = reg.get("last_exported_snapshot_id") or reg.get("last_snapshot_id")
    if not sid:
        return None
    # ``None`` when unknown (legacy) — callers must not invent ``{id}.json``.
    expected_filename = exported_basename_from_registry(reg)
    return {
        "snapshot_id": sid,
        "expected_filename": expected_filename,
        "mechanics_hash": reg.get("last_exported_mechanics_hash")
        or reg.get("last_mechanics_hash"),
        "account_state_hash": reg.get("last_exported_account_state_hash")
        or reg.get("last_account_state_hash"),
        "created_at": reg.get("last_exported_at") or reg.get("last_created_at"),
        "account_state_hash_covers": (
            "owned champion ids + snapshot loadout selections/feats/"
            "equipment status fields + item_levels (avg/by_slot)"
        ),
    }


def set_user_declared_shared(
    snapshot_id: str | None,
    *,
    declared: bool,
) -> dict[str, Any]:
    """Record the user's declaration that they shared a specific exported snapshot."""
    from datetime import datetime, timezone

    registry = load_snapshot_registry()
    exported = registry.get("last_exported_snapshot_id") or registry.get(
        "last_snapshot_id"
    )
    if declared and snapshot_id and exported and str(snapshot_id) == str(exported):
        registry["user_declared_shared_snapshot_id"] = str(snapshot_id)
        registry["user_declared_shared_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
    else:
        registry["user_declared_shared_snapshot_id"] = None
        registry["user_declared_shared_at"] = None
    save_snapshot_registry(registry)
    return registry


def record_saved_snapshot(
    snapshot: dict[str, Any],
    *,
    saved_path: Path,
    markdown_text: str | None = None,
) -> dict[str, Any]:
    """Update registry after the user saved/exported a snapshot file.

    Always records a new export identity from ``snapshot`` meta — never mutates
    an older snapshot under the same ID in place when content hashes differ
    (caller must build a fresh snapshot with a new content-derived ID).
    """
    meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else {}
    coverage = (
        (snapshot.get("roster") or {}).get("coverage")
        if isinstance(snapshot.get("roster"), dict)
        else None
    )
    text = markdown_text or minify_json(snapshot)
    saved = Path(saved_path)
    entry = {
        "snapshot_id": meta.get("snapshot_id"),
        "saved_path": str(saved),
        "exported_filename": saved.name,
        "created_at": meta.get("created_at"),
        "mechanics_hash": meta.get("mechanics_hash"),
        "account_state_hash": meta.get("account_state_hash"),
        "char_count": count_chars(text),
        "utf8_bytes": count_utf8_bytes(text),
        "coverage": coverage,
    }
    registry = load_snapshot_registry()
    previous_id = registry.get("last_exported_snapshot_id") or registry.get(
        "last_snapshot_id"
    )

    # Exported fields (authoritative for advice refs).
    registry["last_exported_snapshot_id"] = entry["snapshot_id"]
    registry["last_exported_path"] = entry["saved_path"]
    registry["last_exported_filename"] = entry["exported_filename"]
    registry["last_exported_at"] = entry["created_at"]
    registry["last_exported_char_count"] = entry["char_count"]
    registry["last_exported_utf8_bytes"] = entry["utf8_bytes"]
    registry["last_exported_coverage"] = coverage
    registry["last_exported_mechanics_hash"] = entry["mechanics_hash"]
    registry["last_exported_account_state_hash"] = entry["account_state_hash"]

    # Legacy aliases.
    registry["last_snapshot_id"] = entry["snapshot_id"]
    registry["last_saved_path"] = entry["saved_path"]
    registry["last_created_at"] = entry["created_at"]
    registry["last_char_count"] = entry["char_count"]
    registry["last_utf8_bytes"] = entry["utf8_bytes"]
    registry["last_coverage"] = coverage
    registry["last_mechanics_hash"] = entry["mechanics_hash"]
    registry["last_account_state_hash"] = entry["account_state_hash"]

    # Sharing declaration applies only to the previously declared ID; clear when
    # a different snapshot is exported.
    if previous_id and entry["snapshot_id"] and str(previous_id) != str(entry["snapshot_id"]):
        registry["user_declared_shared_snapshot_id"] = None
        registry["user_declared_shared_at"] = None

    history = [
        h
        for h in (registry.get("history") or [])
        if isinstance(h, dict) and h.get("snapshot_id") != entry["snapshot_id"]
    ]
    history.insert(0, entry)
    registry["history"] = history[:_MAX_HISTORY]
    save_snapshot_registry(registry)
    return registry


def mirror_snapshot_locally(snapshot: dict[str, Any]) -> Path:
    """Write a local copy under config/advice_snapshots/ (best-effort).

    Uses the content-derived snapshot_id as filename so a new build never
    silently overwrites an older ID's file under the same name unless IDs match.
    """
    meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else {}
    snap_id = str(meta.get("snapshot_id") or "unknown").replace("/", "_")
    ADVICE_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ADVICE_SNAPSHOTS_DIR / f"{snap_id}.json"
    path.write_text(minify_json(snapshot) + "\n", encoding="utf-8")
    return path


def save_snapshot_to_path(snapshot: dict[str, Any], dest: Path) -> Path:
    """Write snapshot JSON to ``dest`` and update the local registry as exported."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = minify_json(snapshot) + "\n"
    dest.write_text(body, encoding="utf-8")
    try:
        mirror_snapshot_locally(snapshot)
    except OSError:
        pass
    record_saved_snapshot(snapshot, saved_path=dest, markdown_text=body)
    return dest


def clear_basisgegevens_dir(directory: Path | None = None) -> None:
    """Remove all files and subdirectories under the basisgegevens folder."""
    target = Path(directory) if directory is not None else BASISGEGEVENS_DIR
    if not target.exists():
        return
    if not target.is_dir():
        raise NotADirectoryError(f"basisgegevens pad is geen map: {target}")
    for child in target.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _basicdata_filename(when: datetime | None = None) -> str:
    """Filename like ``basicdata_21102026_094815.json`` (DDMMYYYY_HHMMSS, local time)."""
    stamp = when or datetime.now()
    return f"basicdata_{stamp.strftime('%d%m%Y_%H%M%S')}.json"


def save_base_snapshot_to_basisgegevens(
    snapshot: dict[str, Any],
    *,
    directory: Path | None = None,
    when: datetime | None = None,
) -> Path:
    """Clear ``basisgegevens``, write the new snapshot there, update registry.

    Always replaces prior contents of the folder so only the current export remains.
    File name: ``basicdata_DDMMYYYY_HHMMSS.json``.
    """
    target_dir = Path(directory) if directory is not None else BASISGEGEVENS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    clear_basisgegevens_dir(target_dir)
    dest = target_dir / _basicdata_filename(when)
    return save_snapshot_to_path(snapshot, dest)


def _fallback_snapshot_path(snap_id: str) -> Path | None:
    """Prefer basisgegevens, then the local advice_snapshots mirror."""
    if BASISGEGEVENS_DIR.is_dir():
        # Folder holds at most one current export (basicdata_*.json).
        basics = sorted(BASISGEGEVENS_DIR.glob("basicdata_*.json"))
        if len(basics) == 1 and basics[0].is_file():
            return basics[0]
        named = BASISGEGEVENS_DIR / f"{snap_id}.json"
        if named.is_file():
            return named
    mirror = ADVICE_SNAPSHOTS_DIR / f"{snap_id}.json"
    if mirror.is_file():
        return mirror
    return None


def load_snapshot_from_registry_path() -> dict[str, Any] | None:
    """Load the last exported snapshot JSON if the path still exists."""
    registry = load_snapshot_registry()
    raw_path = registry.get("last_exported_path") or registry.get("last_saved_path")
    if not raw_path:
        snap_id = registry.get("last_exported_snapshot_id") or registry.get(
            "last_snapshot_id"
        )
        if snap_id:
            found = _fallback_snapshot_path(str(snap_id))
            if found is not None:
                raw_path = str(found)
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.is_file():
        mirror_id = registry.get("last_exported_snapshot_id") or registry.get(
            "last_snapshot_id"
        )
        if mirror_id:
            found = _fallback_snapshot_path(str(mirror_id))
            if found is not None:
                path = found
            else:
                return None
        else:
            return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def copy_registry_file_to(dest: Path) -> Path | None:
    """Copy last exported snapshot file to ``dest`` if available."""
    registry = load_snapshot_registry()
    src_raw = registry.get("last_exported_path") or registry.get("last_saved_path")
    if not src_raw:
        return None
    src = Path(str(src_raw))
    if not src.is_file():
        return None
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
