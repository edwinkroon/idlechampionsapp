"""Patron roster availability for champions."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int

PATRON_NAMES: dict[int, str] = {
    1: "Mirt",
    2: "Vajra",
    3: "Strahd",
    4: "Zariel",
    5: "Elminster",
}

_ALLOWED_WITHOUT_FEAT = frozenset({"available", "always", "timed"})


def _config_path_candidates() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        paths.append(exe_dir / "config" / "patron_roster.json")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / "config" / "patron_roster.json")
    paths.append(Path(__file__).resolve().parent.parent / "config" / "patron_roster.json")
    return paths


@lru_cache(maxsize=1)
def load_patron_roster() -> dict[int, dict[str, str]]:
    """hero_id -> patron_key (mirt/vajra/...) -> availability string."""
    for path in _config_path_candidates():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        heroes = data.get("heroes")
        if not isinstance(heroes, list):
            continue
        out: dict[int, dict[str, str]] = {}
        for item in heroes:
            if not isinstance(item, dict):
                continue
            hero_id = _parse_int(item.get("hero_id"))
            patrons = item.get("patrons")
            if hero_id is None or not isinstance(patrons, dict):
                continue
            out[hero_id] = {
                str(key).strip().lower(): str(value).strip().lower()
                for key, value in patrons.items()
                if str(key).strip() and str(value).strip()
            }
        if out:
            return out
    return {}


def _patron_key(patron_id: int) -> str | None:
    mapping = {
        1: "mirt",
        2: "vajra",
        3: "strahd",
        4: "zariel",
        5: "elminster",
    }
    return mapping.get(patron_id)


@lru_cache(maxsize=1)
def _patron_unlock_feats_from_definitions() -> dict[tuple[int, int], set[int]]:
    """Map (hero_id, patron_id) -> feat ids that unlock the champion for that patron."""
    try:
        from ic_gamedata.specialization_data import cached_definitions_data
    except ImportError:
        return {}

    data = cached_definitions_data()
    feats = data.get("feat_defines")
    if not isinstance(feats, list):
        return {}

    out: dict[tuple[int, int], set[int]] = {}
    for item in feats:
        if not isinstance(item, dict):
            continue
        feat_id = _parse_int(item.get("id"))
        hero_id = _parse_int(item.get("hero_id"))
        patron_id = _parse_int(item.get("patron_id"))
        if feat_id is None:
            continue

        effect = item.get("effect")
        effect_text = str(effect or "").casefold()
        name = str(item.get("name") or "").casefold()
        if patron_id is None and "patron" not in effect_text and "patron" not in name:
            continue
        if hero_id is None or patron_id is None:
            continue
        out.setdefault((hero_id, patron_id), set()).add(feat_id)
    return out


def _unlocked_feat_ids_by_hero(payload: dict[str, Any]) -> dict[int, set[int]]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return {}
    out: dict[int, set[int]] = {}
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        feats: set[int] = set()
        for raw in hero.get("unlocked_feats") or []:
            feat_id = _parse_int(raw)
            if feat_id is not None:
                feats.add(feat_id)
        if feats:
            out[hero_id] = feats
    return out


def _has_patron_unlock_feat(hero_id: int, patron_id: int, payload: dict[str, Any]) -> bool:
    unlock_map = _patron_unlock_feats_from_definitions()
    required = unlock_map.get((hero_id, patron_id))
    if not required:
        return False
    owned = _unlocked_feat_ids_by_hero(payload).get(hero_id, set())
    return bool(required & owned)


def hero_patron_availability(hero_id: int, patron_id: int) -> str | None:
    key = _patron_key(patron_id)
    if key is None:
        return None
    return load_patron_roster().get(hero_id, {}).get(key)


def is_hero_allowed_on_patron(
    hero_id: int,
    patron_id: int,
    payload: dict[str, Any] | None = None,
) -> bool | None:
    """
    Return True/False when patron roster is known, None when hero/patron is unknown.
    """
    if patron_id <= 0:
        return True

    availability = hero_patron_availability(hero_id, patron_id)
    if availability is None:
        return None

    if availability in _ALLOWED_WITHOUT_FEAT:
        return True
    if availability == "unavailable":
        return False
    if availability == "feat":
        if payload is None:
            return False
        if _has_patron_unlock_feat(hero_id, patron_id, payload):
            return True
        return False
    return None


def patron_restriction_note(hero_id: int, patron_id: int, payload: dict[str, Any] | None = None) -> str | None:
    availability = hero_patron_availability(hero_id, patron_id)
    patron_name = PATRON_NAMES.get(patron_id, f"Patron {patron_id}")
    if availability == "unavailable":
        return f"Niet beschikbaar voor {patron_name}"
    if availability == "feat":
        if payload and _has_patron_unlock_feat(hero_id, patron_id, payload):
            return None
        return f"Patron-feat vereist voor {patron_name}"
    return None
