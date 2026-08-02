"""Load Gaarawarr-derived role advice (specs / formation / feats)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ic_gamedata.seat_advisor.models import SeatRole
else:
    SeatRole = str  # runtime; avoids circular import with seat_advisor

_CONFIG_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "config" / "champion_role_advice.json",
    Path.cwd() / "config" / "champion_role_advice.json",
)
_GUIDE_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "data" / "gaarawarr_guides",
    Path.cwd() / "data" / "gaarawarr_guides",
)

_CHAMPIONS_CONFIG_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "config" / "champions.json",
    Path.cwd() / "config" / "champions.json",
)
_SPEED_OVERRIDE_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "config" / "speed_feat_overrides.json",
    Path.cwd() / "config" / "speed_feat_overrides.json",
)

_ROLE_FEAT_TAG_HINTS: dict[str, tuple[str, ...]] = {
    "speed": ("speed", "farming"),
    "gold": ("gold",),
    "tank": ("survivability", "healing"),
    "healer": ("survivability", "healing"),
    "bud": ("pushing", "dps"),
    "debuffer": ("pushing", "dps"),
    "buffer": ("pushing", "support"),
    "support": ("pushing", "support"),
    "flex": ("pushing", "support"),
    "modron": ("speed", "farming", "support"),
}
_SPEED_FALLBACK_TAG_HINTS: tuple[str, ...] = ("survivability", "healing")
_PUSHING_FEAT_TAGS: frozenset[str] = frozenset({"pushing", "dps"})
_SPEED_EFFECT_HINTS: tuple[str, ...] = (
    "quest requirement",
    "kill requirement",
    "monsters required",
    "monsters to",
    "spawn rate",
    "spawned monsters",
    "haste",
    "skip",
    "time warp",
    "warps",
    "progress",
    "areas faster",
    "zone",
)


@dataclass(frozen=True)
class RoleAdvice:
    hero_id: int
    hero_name: str
    role: SeatRole
    specialization_names: tuple[str, ...]
    specialization_ids: tuple[int, ...]
    formation: str
    feats: tuple[str, ...]
    source: str
    source_url: str
    source_date: str | None
    wiki_url: str = ""


@lru_cache(maxsize=1)
def load_champion_role_advice() -> dict[str, Any]:
    for path in _CONFIG_CANDIDATES:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    return {}


def clear_role_advice_cache() -> None:
    load_champion_role_advice.cache_clear()
    _load_champion_role_advice.cache_clear()
    _load_guide_feat_rows.cache_clear()
    _load_speed_feat_overrides.cache_clear()
    _speed_tagged_hero_ids.cache_clear()


@lru_cache(maxsize=1)
def _load_champion_role_advice() -> dict[str, Any]:
    return load_champion_role_advice()


@lru_cache(maxsize=1)
def _speed_tagged_hero_ids() -> frozenset[int]:
    for path in _CHAMPIONS_CONFIG_CANDIDATES:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return frozenset()
        if not isinstance(payload, dict):
            return frozenset()
        tagged: set[int] = set()
        for key, entry in payload.items():
            if not isinstance(entry, dict):
                continue
            tags = entry.get("tags") or []
            if "speed" in tags:
                try:
                    tagged.add(int(key))
                except (TypeError, ValueError):
                    continue
        return frozenset(tagged)
    return frozenset()


@lru_cache(maxsize=1)
def _load_speed_feat_overrides() -> dict[int, tuple[str, ...]]:
    for path in _SPEED_OVERRIDE_CANDIDATES:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        raw = payload.get("champions") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            return {}
        overrides: dict[int, tuple[str, ...]] = {}
        for key, entry in raw.items():
            try:
                hero_id = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(entry, dict):
                feats = entry.get("feats")
            elif isinstance(entry, list):
                feats = entry
            else:
                continue
            if isinstance(feats, list):
                overrides[hero_id] = tuple(str(name) for name in feats if str(name).strip())
        return overrides
    return {}


@lru_cache(maxsize=256)
def _load_guide_feat_rows(guide_id: str) -> tuple[dict[str, Any], ...]:
    if not guide_id:
        return ()
    for base in _GUIDE_CANDIDATES:
        path = base / f"{guide_id}.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ()
        body = str(payload.get("selftext") or "")
        index = body.lower().find("##feats")
        section = body[index : index + 4000] if index >= 0 else body
        rows: list[dict[str, Any]] = []
        for line in section.splitlines():
            if not line.strip().startswith("|"):
                continue
            cols = [column.strip().strip("*") for column in line.strip().strip("|").split("|")]
            if len(cols) < 4:
                continue
            _obtained, recommended, name, effect = cols[0], cols[1], cols[2], cols[3]
            if name.lower() in {"name", "obtained", "feat slot"} or "---" in name:
                continue
            tags = tuple(
                token.strip().lower()
                for token in re.split(r"[/,; ]+", recommended)
                if token.strip() and token.strip() != "-"
            )
            rows.append(
                {
                    "name": name,
                    "recommended_tags": tags,
                    "effect": effect,
                    "obtained": _obtained,
                }
            )
        return tuple(rows)
    return ()


def _feat_row_is_pushing(row: dict[str, Any]) -> bool:
    row_tags = {str(tag).casefold() for tag in row.get("recommended_tags") or ()}
    if row_tags & _PUSHING_FEAT_TAGS:
        return True
    effect = str(row.get("effect") or "").casefold()
    if "all champions" in effect and any(token in effect for token in ("50%", "40%", "25%")):
        return "speed" not in effect and "quest" not in effect
    return False


def _feat_row_matches_speed_effect(row: dict[str, Any]) -> bool:
    if _feat_row_is_pushing(row):
        return False
    effect = str(row.get("effect") or "").casefold()
    return any(hint in effect for hint in _SPEED_EFFECT_HINTS)


def _speed_feats_from_guide_rows(rows: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    tagged = _feats_matching_tags(rows, _ROLE_FEAT_TAG_HINTS["speed"])
    if tagged:
        return tagged

    survivability = _feats_matching_tags(rows, _SPEED_FALLBACK_TAG_HINTS)
    if survivability:
        return survivability

    effect_matches: list[str] = []
    for row in rows:
        if not _feat_row_matches_speed_effect(row):
            continue
        name = str(row.get("name") or "").strip()
        if name and name not in effect_matches:
            effect_matches.append(name)
        if len(effect_matches) >= 4:
            break
    return tuple(effect_matches)


def _feats_matching_tags(
    rows: tuple[dict[str, Any], ...],
    tag_hints: tuple[str, ...],
    *,
    limit: int = 4,
) -> tuple[str, ...]:
    hints = {hint.casefold() for hint in tag_hints}
    matched: list[str] = []
    for row in rows:
        row_tags = {str(tag).casefold() for tag in row.get("recommended_tags") or ()}
        if not row_tags & hints:
            continue
        name = str(row.get("name") or "").strip()
        if name and name not in matched:
            matched.append(name)
        if len(matched) >= limit:
            break
    return tuple(matched)


def _resolve_feats_for_role(
    entry: dict[str, Any],
    role: SeatRole,
    configured: tuple[str, ...],
    *,
    hero_id: int | None = None,
) -> tuple[str, ...]:
    """Prefer Gaarawarr feat-table tags; speed must not inherit pushing feats."""
    if role == "speed" and hero_id is not None:
        override = _load_speed_feat_overrides().get(hero_id)
        if override is not None:
            return override

    if configured and role != "speed":
        guide_id = str(entry.get("guide_id") or "")
        rows = _load_guide_feat_rows(guide_id)
        if rows:
            tagged = _feats_matching_tags(rows, _ROLE_FEAT_TAG_HINTS.get(role, ("pushing",)))
            if tagged:
                return tagged
        return configured

    guide_id = str(entry.get("guide_id") or "")
    rows = _load_guide_feat_rows(guide_id)
    if role == "speed":
        if rows:
            return _speed_feats_from_guide_rows(rows)
        return ()

    if not rows:
        return configured

    tag_hints = _ROLE_FEAT_TAG_HINTS.get(role, ("pushing", "support"))
    tagged = _feats_matching_tags(rows, tag_hints)
    if tagged:
        return tagged

    return configured


def _role_fallback_order(role: SeatRole) -> tuple[str, ...]:
    if role == "bud":
        return ("bud", "flex", "support", "buffer")
    if role == "flex":
        return ("flex", "support", "bud", "buffer")
    if role == "gold":
        return ("gold", "support", "buffer")
    if role == "modron":
        return ("modron", "support", "buffer")
    if role == "speed":
        return ("speed", "support", "buffer")
    if role == "tank":
        return ("tank", "support", "buffer")
    if role == "healer":
        return ("healer", "support", "buffer")
    if role == "debuffer":
        return ("debuffer", "support", "buffer")
    if role == "buffer":
        return ("buffer", "support")
    return ("support", "buffer", "flex")


def get_role_advice(hero_id: int, role: SeatRole) -> RoleAdvice | None:
    data = load_champion_role_advice()
    entry = (data.get("champions") or {}).get(str(hero_id))
    if not isinstance(entry, dict):
        return None
    roles = entry.get("roles") if isinstance(entry.get("roles"), dict) else {}
    chosen = None
    for key in _role_fallback_order(role):
        if key in roles and isinstance(roles[key], dict):
            chosen = roles[key]
            break
    if chosen is None and roles:
        # any role block
        first = next(iter(roles.values()))
        chosen = first if isinstance(first, dict) else None
    if chosen is None:
        return None

    specs = tuple(str(x) for x in (chosen.get("specializations") or []) if str(x).strip())
    spec_ids_raw = chosen.get("specialization_ids") or []
    spec_ids = tuple(int(x) for x in spec_ids_raw if str(x).isdigit() or isinstance(x, int))
    configured_feats = tuple(str(x) for x in (chosen.get("feats") or []) if str(x).strip())
    feats = _resolve_feats_for_role(entry, role, configured_feats, hero_id=hero_id)
    formation = str(chosen.get("formation") or "").strip()
    return RoleAdvice(
        hero_id=hero_id,
        hero_name=str(entry.get("name") or f"Hero {hero_id}"),
        role=role,
        specialization_names=specs,
        specialization_ids=spec_ids,
        formation=formation,
        feats=feats,
        source=str(entry.get("source") or "Gaarawarr"),
        source_url=str(entry.get("source_url") or ""),
        source_date=str(entry.get("source_date") or "") or None,
        wiki_url=str(entry.get("wiki_url") or ""),
    )
