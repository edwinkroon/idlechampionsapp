"""Map normalized specialization route keys to concrete upgrade options."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ic_gamedata.specialization_models import SpecializationOption

_ROUTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "speed_route": (
        "speed",
        "dash",
        "phlo",
        "swift",
        "fast",
        "haste",
        "boss wants speed",
        "rapid",
        "quick",
        "tempo",
        "spawn",
        "human",
    ),
    "gold_route": ("gold", "favor", "rich", "fortune", "business", "riches", "treasure", "piracy", "ohhh yeah"),
    "support_route": ("support", "allies", "grace", "lathander", "mentor", "buff", "valor", "lore", "ahead", "behind"),
    "tank_route": ("tank", "guard", "protection", "devotion", "duel", "compel", "shield", "surviv", "frontline", "oath"),
    "healing_route": ("heal", "life", "mercy", "restoration", "sustain", "spores"),
    "debuff_route": ("debuff", "ward", "plague", "curse", "withering", "hex", "brake", "pain", "efficient bookkeeping"),
    "damage_route": (
        "damage",
        "dps",
        "battle",
        "assassin",
        "arrow",
        "piercing",
        "war",
        "observe",
        "usurp",
        "bulk up",
        "outflank",
        "thief",
        "trickster",
        "min-max",
        "min max",
    ),
    "utility_route": ("utility", "control", "switch", "observance", "confidence", "group tactics"),
    "formation_route": ("bond", "formation", "species", "family", "fellowship", "hall", "legacy", "potpourri", "pack tactics", "kobold"),
    "enemy_type_route": ("enemy", "foe", "fiend", "undead", "humanoid", "dragon", "aberration", "monstrosity", "favored"),
    "alignment_route": ("alignment", "law", "chaos", "good", "evil", "neutral"),
}

_LABEL_SPLIT = re.compile(r"[/|,]| or ", re.IGNORECASE)

_OVERRIDE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "config" / "specialization_route_overrides.json",
    Path.cwd() / "config" / "specialization_route_overrides.json",
)


@lru_cache(maxsize=1)
def _route_override_table() -> dict[str, dict[str, int]]:
    for path in _OVERRIDE_CANDIDATES:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        champions = data.get("champions") if isinstance(data, dict) else None
        if not isinstance(champions, dict):
            return {}
        out: dict[str, dict[str, int]] = {}
        for name, routes in champions.items():
            if not isinstance(routes, dict):
                continue
            mapped: dict[str, int] = {}
            for label, upgrade_id in routes.items():
                try:
                    mapped[str(label).strip()] = int(upgrade_id)
                except (TypeError, ValueError):
                    continue
            if mapped:
                out[str(name).strip()] = mapped
        return out
    return {}


def clear_route_override_cache() -> None:
    _route_override_table.cache_clear()


def _override_upgrade_id(
    champion_name: str | None,
    label: str,
    tier_options: list[SpecializationOption],
    *,
    tier_index: int | None = None,
) -> int | None:
    if not champion_name:
        return None
    table = _route_override_table()
    routes = table.get(champion_name)
    if not routes:
        for key, value in table.items():
            if key.casefold() == champion_name.casefold():
                routes = value
                break
    if not routes:
        return None

    candidates = _label_candidates(label) or [label]
    valid_ids = {opt.upgrade_id for opt in tier_options}
    lookup_keys: list[str] = []
    for candidate in candidates:
        lookup_keys.extend([candidate, candidate.casefold().replace(" ", "_")])
        if tier_index is not None:
            lookup_keys.extend(
                [
                    f"{candidate}@{tier_index}",
                    f"{candidate.casefold().replace(' ', '_')}@{tier_index}",
                ]
            )
    for lookup in lookup_keys:
        for key in (lookup, lookup.casefold()):
            upgrade_id = routes.get(key)
            if upgrade_id is not None and upgrade_id in valid_ids:
                return upgrade_id
    return None


def _tier_options(
    options: list[SpecializationOption],
    *,
    tier_index: int | None,
) -> list[SpecializationOption]:
    tier_options = [
        opt for opt in options if tier_index is None or opt.tier_index == tier_index
    ]
    return tier_options or list(options)


def _keyword_in_option_name(name: str, keyword: str) -> bool:
    needle = keyword.casefold().strip()
    if not needle:
        return False
    haystack = name.casefold()
    if any(ch in needle for ch in (" ", ":", "'")):
        return needle in haystack
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def _score_option(option: SpecializationOption, keywords: tuple[str, ...]) -> int:
    name = option.name.lower()
    return sum(2 if _keyword_in_option_name(name, keyword) else 0 for keyword in keywords)


def map_route_to_upgrade_id(
    route_key: str,
    options: list[SpecializationOption],
    *,
    tier_index: int | None = None,
    champion_name: str | None = None,
) -> int | None:
    tier_options = _tier_options(options, tier_index=tier_index)
    if not tier_options:
        return None

    override = _override_upgrade_id(
        champion_name,
        route_key,
        tier_options,
        tier_index=tier_index,
    )
    if override is not None:
        return override

    keywords = _ROUTE_KEYWORDS.get(route_key, (route_key.replace("_", " "),))
    ranked = sorted(
        tier_options,
        key=lambda opt: (_score_option(opt, keywords), -opt.upgrade_id),
        reverse=True,
    )
    best = ranked[0]
    if _score_option(best, keywords) <= 0:
        return None
    return best.upgrade_id


def _label_candidates(label: str) -> list[str]:
    text = label.strip()
    if not text:
        return []
    parts = [part.strip() for part in _LABEL_SPLIT.split(text) if part.strip()]
    ordered: list[str] = []
    for candidate in [text, *parts]:
        if candidate and candidate not in ordered:
            ordered.append(candidate)
    return ordered


def _score_label_against_option(label: str, option: SpecializationOption) -> int:
    label_cf = label.casefold()
    name_cf = option.name.casefold()
    if label_cf == name_cf:
        return 100
    if label_cf in name_cf or name_cf in label_cf:
        return 80

    route_key = label_cf.replace(" ", "_")
    route_keywords = _ROUTE_KEYWORDS.get(route_key)
    if route_keywords:
        return _score_option(option, route_keywords)

    words = tuple(word for word in re.findall(r"[a-z0-9]+", label_cf) if len(word) > 2)
    if not words:
        return 0
    return _score_option(option, words)


def map_label_to_upgrade_id(
    label: str,
    options: list[SpecializationOption],
    *,
    tier_index: int | None = None,
    champion_name: str | None = None,
) -> int | None:
    """Map a human label from v2_full (or V3 display text) to an upgrade id."""
    tier_options = _tier_options(options, tier_index=tier_index)
    if not tier_options or not label.strip():
        return None

    override = _override_upgrade_id(
        champion_name,
        label,
        tier_options,
        tier_index=tier_index,
    )
    if override is not None:
        return override

    best_score = 0
    best_id: int | None = None
    for candidate in _label_candidates(label):
        route_key = candidate.casefold().replace(" ", "_")
        route_match = map_route_to_upgrade_id(
            route_key,
            tier_options,
            tier_index=tier_index,
            champion_name=champion_name,
        )
        if route_match is not None:
            return route_match

        for option in tier_options:
            score = _score_label_against_option(candidate, option)
            if score > best_score:
                best_score = score
                best_id = option.upgrade_id

    if best_score > 0:
        return best_id
    return map_route_to_upgrade_id(
        label.casefold().replace(" ", "_"),
        options,
        tier_index=tier_index,
        champion_name=champion_name,
    )
