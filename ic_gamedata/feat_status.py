"""Classify recommended feats against the player's unlocked/active feats."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from ic_gamedata.parsing import parse_int as _parse_int

FeatStatus = Literal["active", "owned", "missing", "unknown"]


@dataclass(frozen=True)
class FeatRecommendation:
    name: str
    status: FeatStatus


def _normalize_feat_name(name: str) -> str:
    return " ".join(str(name).casefold().split())


@lru_cache(maxsize=1)
def _feat_id_by_hero_and_name() -> dict[int, dict[str, int]]:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data
    except ImportError:
        return {}

    data = cached_definitions_data()
    rows = data.get("hero_feat_defines")
    if not isinstance(rows, list):
        rows = data.get("feat_defines")
    if not isinstance(rows, list):
        return {}

    out: dict[int, dict[str, int]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("hero_id"))
        feat_id = _parse_int(item.get("id"))
        name = str(item.get("name") or "").strip()
        if hero_id is None or feat_id is None or not name:
            continue
        out.setdefault(hero_id, {})[_normalize_feat_name(name)] = feat_id
    return out


def _hero_feat_sets(payload: dict[str, Any]) -> dict[int, tuple[set[int], set[int]]]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return {}

    out: dict[int, tuple[set[int], set[int]]] = {}
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hero_id = _parse_int(hero.get("hero_id"))
        if hero_id is None:
            continue
        unlocked: set[int] = set()
        active: set[int] = set()
        for raw in hero.get("unlocked_feats") or []:
            feat_id = _parse_int(raw)
            if feat_id is not None:
                unlocked.add(feat_id)
        for raw in hero.get("active_feats") or []:
            feat_id = _parse_int(raw)
            if feat_id is not None:
                active.add(feat_id)
        out[hero_id] = (unlocked, active)
    return out


def classify_recommended_feat(
    hero_id: int,
    feat_name: str,
    payload: dict[str, Any],
) -> FeatStatus:
    normalized = _normalize_feat_name(feat_name)
    if not normalized:
        return "unknown"

    feat_id = _feat_id_by_hero_and_name().get(hero_id, {}).get(normalized)
    if feat_id is None:
        return "unknown"

    unlocked, active = _hero_feat_sets(payload).get(hero_id, (set(), set()))
    if feat_id in active:
        return "active"
    if feat_id in unlocked:
        return "owned"
    return "missing"


def build_feat_recommendations(
    hero_id: int,
    feat_names: tuple[str, ...],
    payload: dict[str, Any],
) -> tuple[FeatRecommendation, ...]:
    return tuple(
        FeatRecommendation(name=name, status=classify_recommended_feat(hero_id, name, payload))
        for name in feat_names
        if str(name).strip()
    )
