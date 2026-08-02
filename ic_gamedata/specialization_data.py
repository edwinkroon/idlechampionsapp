"""Shared loaders for specialization-related local game and config data."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int


def _config_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def champions_config_path() -> Path:
    return _config_base() / "config" / "champions.json"


def specialization_meta_path() -> Path:
    return _config_base() / "config" / "specialization_meta.json"


@lru_cache(maxsize=1)
def load_champion_config() -> dict[str, Any]:
    path = champions_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_meta_static_defaults() -> dict[int, list[int]]:
    path = specialization_meta_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw = data.get("defaults")
    if not isinstance(raw, dict):
        return {}
    out: dict[int, list[int]] = {}
    for hero_id_raw, ids in raw.items():
        hero_id = _parse_int(hero_id_raw)
        if hero_id is None or not isinstance(ids, list):
            continue
        parsed = [_parse_int(item) for item in ids]
        out[hero_id] = [item for item in parsed if item is not None]
    return out


@lru_cache(maxsize=1)
def cached_definitions_data() -> dict[str, Any]:
    try:
        from ic_gamedata.paths import get_downloaded_files_dir
    except ImportError:
        from ic_gamedata import get_downloaded_files_dir

    downloaded_files = get_downloaded_files_dir()
    if downloaded_files is None:
        return {}
    path = downloaded_files / "cached_definitions.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def hero_name_map_from_cached_definitions() -> dict[int, str]:
    heroes = cached_definitions_data().get("hero_defines")
    if not isinstance(heroes, list):
        return {}
    out: dict[int, str] = {}
    for item in heroes:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        name = item.get("name")
        if hero_id is None or not isinstance(name, str) or not name.strip():
            continue
        out[hero_id] = name.strip()
    return out


@lru_cache(maxsize=1)
def hero_name_map_from_champion_config() -> dict[int, str]:
    data = load_champion_config()
    out: dict[int, str] = {}
    for hero_id_raw, cfg in data.items():
        hero_id = _parse_int(hero_id_raw)
        if hero_id is None or not isinstance(cfg, dict):
            continue
        name = cfg.get("name")
        if isinstance(name, str) and name.strip():
            out[hero_id] = name.strip()
    return out


@lru_cache(maxsize=1)
def hero_roles_map_from_champion_config() -> dict[int, tuple[str, ...]]:
    data = load_champion_config()
    out: dict[int, tuple[str, ...]] = {}
    for hero_id_raw, cfg in data.items():
        hero_id = _parse_int(hero_id_raw)
        if hero_id is None or not isinstance(cfg, dict):
            continue
        raw_roles = cfg.get("roles")
        if isinstance(raw_roles, list):
            roles = tuple(str(role).strip().lower() for role in raw_roles if str(role).strip())
            if roles:
                out[hero_id] = roles
    return out


@lru_cache(maxsize=1)
def hero_tags_map_from_champion_config() -> dict[int, tuple[str, ...]]:
    data = load_champion_config()
    out: dict[int, tuple[str, ...]] = {}
    for hero_id_raw, cfg in data.items():
        hero_id = _parse_int(hero_id_raw)
        if hero_id is None or not isinstance(cfg, dict):
            continue
        raw_tags = cfg.get("tags")
        if isinstance(raw_tags, list):
            tags = tuple(str(tag).strip().lower() for tag in raw_tags if str(tag).strip())
            if tags:
                out[hero_id] = tags
    return out


@lru_cache(maxsize=1)
def hero_tags_map_from_cached_definitions() -> dict[int, tuple[str, ...]]:
    heroes = cached_definitions_data().get("hero_defines")
    if not isinstance(heroes, list):
        return {}
    out: dict[int, tuple[str, ...]] = {}
    for item in heroes:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        raw_tags = item.get("tags")
        if hero_id is None or not isinstance(raw_tags, list):
            continue
        tags = tuple(str(tag).strip().lower() for tag in raw_tags if str(tag).strip())
        if tags:
            out[hero_id] = tags
    return out


@lru_cache(maxsize=1)
def hero_attack_types_map_from_cached_definitions() -> dict[int, frozenset[str]]:
    data = cached_definitions_data()
    hero_defs = data.get("hero_defines")
    attack_defs = data.get("attack_defines")
    if not isinstance(hero_defs, list) or not isinstance(attack_defs, list):
        return {}
    attacks: dict[int, frozenset[str]] = {}
    for item in attack_defs:
        if not isinstance(item, dict):
            continue
        attack_id = _parse_int(item.get("id"))
        raw_types = item.get("damage_types") or item.get("tags")
        if attack_id is None or not isinstance(raw_types, list):
            continue
        types = frozenset(str(tag).strip().lower() for tag in raw_types if str(tag).strip())
        if types:
            attacks[attack_id] = types
    out: dict[int, frozenset[str]] = {}
    for item in hero_defs:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        attack_id = _parse_int(item.get("base_attack_id"))
        if hero_id is None or attack_id is None:
            continue
        types = attacks.get(attack_id)
        if types:
            out[hero_id] = types
    return out


@lru_cache(maxsize=1)
def hero_ability_scores_map_from_cached_definitions() -> dict[int, dict[str, int]]:
    heroes = cached_definitions_data().get("hero_defines")
    if not isinstance(heroes, list):
        return {}
    out: dict[int, dict[str, int]] = {}
    for item in heroes:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        details = item.get("character_sheet_details")
        scores = details.get("ability_scores") if isinstance(details, dict) else None
        if hero_id is None or not isinstance(scores, dict):
            continue
        parsed = {
            key: value
            for key, value in (
                ("str", _parse_int(scores.get("str"))),
                ("dex", _parse_int(scores.get("dex"))),
                ("con", _parse_int(scores.get("con"))),
                ("int", _parse_int(scores.get("int"))),
                ("wis", _parse_int(scores.get("wis"))),
                ("cha", _parse_int(scores.get("cha"))),
            )
            if value is not None
        }
        if parsed:
            out[hero_id] = parsed
    return out


@lru_cache(maxsize=1)
def hero_age_map_from_cached_definitions() -> dict[int, int]:
    heroes = cached_definitions_data().get("hero_defines")
    if not isinstance(heroes, list):
        return {}
    out: dict[int, int] = {}
    for item in heroes:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        details = item.get("character_sheet_details")
        age = _parse_int(details.get("age")) if isinstance(details, dict) else None
        if hero_id is None or age is None:
            continue
        out[hero_id] = age
    return out
