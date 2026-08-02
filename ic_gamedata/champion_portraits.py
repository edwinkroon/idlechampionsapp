"""Resolve champion portrait PNGs from local Idle Champions game assets."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ic_gamedata.specialization_data import _parse_int, cached_definitions_data


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").casefold())


@lru_cache(maxsize=1)
def _graphic_by_id() -> dict[int, dict[str, Any]]:
    rows = cached_definitions_data().get("graphic_defines")
    if not isinstance(rows, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        graphic_id = _parse_int(item.get("id"))
        if graphic_id is not None:
            out[graphic_id] = item
    return out


@lru_cache(maxsize=1)
def _hero_portrait_graphic_id() -> dict[int, int]:
    rows = cached_definitions_data().get("hero_defines")
    if not isinstance(rows, list):
        return {}
    out: dict[int, int] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        portrait_id = _parse_int(item.get("portrait_graphic_id"))
        if hero_id is not None and portrait_id is not None:
            out[hero_id] = portrait_id
    return out


@lru_cache(maxsize=1)
def _console_portrait_graphic_by_hero_id() -> dict[int, dict[str, Any]]:
    heroes = cached_definitions_data().get("hero_defines")
    graphics = cached_definitions_data().get("graphic_defines")
    if not isinstance(heroes, list) or not isinstance(graphics, list):
        return {}

    hero_ids_by_name: dict[str, int] = {}
    for item in heroes:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        if hero_id is None:
            continue
        for field in ("english_name", "name"):
            norm = _normalize_name(str(item.get(field) or ""))
            if norm:
                hero_ids_by_name.setdefault(norm, hero_id)

    out: dict[int, dict[str, Any]] = {}
    for item in graphics:
        if not isinstance(item, dict):
            continue
        graphic_path = str(item.get("graphic") or "")
        match = re.match(r"Icons/Champions/Console/Portrait_Champion_(.+)", graphic_path)
        if not match:
            continue
        hero_id = hero_ids_by_name.get(_normalize_name(match.group(1)))
        if hero_id is not None:
            out[hero_id] = item
    return out


def _graphic_base_name(graphic: dict[str, Any]) -> str | None:
    path = str(graphic.get("graphic") or "").strip()
    if not path:
        return None
    return path.rsplit("/", 1)[-1]


def _resolve_graphic_png(root: Path, graphic: dict[str, Any]) -> Path | None:
    base = _graphic_base_name(graphic)
    if not base:
        return None
    fs = _parse_int(graphic.get("fs")) or 0
    version = _parse_int(graphic.get("v")) or 0

    exact = root / f"{base}_{fs}_{version}.png"
    if exact.is_file():
        return exact

    version_matches = sorted(root.glob(f"{base}_{fs}_*.png"))
    if version_matches:
        return version_matches[-1]

    default_matches = sorted(
        path
        for path in root.glob(f"{base}_*.png")
        if re.fullmatch(rf"{re.escape(base)}_0_\d+\.png", path.name)
    )
    if default_matches:
        return default_matches[-1]

    any_matches = sorted(root.glob(f"{base}_*.png"))
    return any_matches[-1] if any_matches else None


def _downloaded_files_dir() -> Path | None:
    try:
        from ic_gamedata.paths import get_downloaded_files_dir
    except ImportError:
        from ic_gamedata import get_downloaded_files_dir

    path = get_downloaded_files_dir()
    return path if path is not None and path.is_dir() else None


def champion_portrait_path(hero_id: int) -> Path | None:
    """Return a local PNG portrait for a champion, preferring in-game UI icons."""
    root = _downloaded_files_dir()
    if root is None:
        return None

    graphics = _graphic_by_id()
    for candidate in (
        _console_portrait_graphic_by_hero_id().get(hero_id),
        graphics.get(_hero_portrait_graphic_id().get(hero_id, -1)),
    ):
        if not isinstance(candidate, dict):
            continue
        resolved = _resolve_graphic_png(root, candidate)
        if resolved is not None:
            return resolved
    return None
