"""Load advisor-facing specialization models (safe/push/farm/conditionals)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


def _config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "specialization_advisor_models.json"
    return Path(__file__).resolve().parent.parent / "config" / "specialization_advisor_models.json"


@dataclass(frozen=True)
class AdvisorChoice:
    upgrade_id: int
    name: str


@dataclass(frozen=True)
class AdvisorConditional:
    when: str
    upgrade_id: int | None
    name: str | None


@dataclass(frozen=True)
class AdvisorContextFlags:
    formation_dependent: bool
    adventure_dependent: bool
    farm_push_split: bool


@dataclass(frozen=True)
class SpecializationAdvisorModel:
    hero_id: int
    name: str
    has_dynamic_handler: bool
    advice_model: str
    safe_default: AdvisorChoice | None
    push_default: AdvisorChoice | None
    farm_default: AdvisorChoice | None
    conditionals: tuple[AdvisorConditional, ...]
    context_flags: AdvisorContextFlags
    explanation_summary: str
    review_needed: bool
    review_reasons: tuple[str, ...]
    options_by_tier: dict[str, tuple[dict[str, Any], ...]]


def _parse_choice(raw: Any) -> AdvisorChoice | None:
    if not isinstance(raw, dict):
        return None
    try:
        upgrade_id = int(raw["upgrade_id"])
        name = str(raw["name"])
    except (KeyError, TypeError, ValueError):
        return None
    if not name:
        return None
    return AdvisorChoice(upgrade_id=upgrade_id, name=name)


def _parse_model(raw: dict[str, Any]) -> SpecializationAdvisorModel | None:
    try:
        hero_id = int(raw["hero_id"])
        name = str(raw["name"])
    except (KeyError, TypeError, ValueError):
        return None
    flags_raw = raw.get("context_flags") if isinstance(raw.get("context_flags"), dict) else {}
    flags = AdvisorContextFlags(
        formation_dependent=bool(flags_raw.get("formation_dependent")),
        adventure_dependent=bool(flags_raw.get("adventure_dependent")),
        farm_push_split=bool(flags_raw.get("farm_push_split")),
    )
    conditionals: list[AdvisorConditional] = []
    for item in raw.get("conditionals") or []:
        if not isinstance(item, dict):
            continue
        upgrade_id = item.get("upgrade_id")
        try:
            parsed_id = int(upgrade_id) if upgrade_id is not None else None
        except (TypeError, ValueError):
            parsed_id = None
        name_val = item.get("name")
        conditionals.append(
            AdvisorConditional(
                when=str(item.get("when") or ""),
                upgrade_id=parsed_id,
                name=str(name_val) if name_val is not None else None,
            )
        )
    options_by_tier: dict[str, tuple[dict[str, Any], ...]] = {}
    raw_tiers = raw.get("options_by_tier")
    if isinstance(raw_tiers, dict):
        for tier, opts in raw_tiers.items():
            if not isinstance(opts, list):
                continue
            options_by_tier[str(tier)] = tuple(o for o in opts if isinstance(o, dict))

    reasons = raw.get("review_reasons") or []
    summary = str(raw.get("explanation_summary") or "")
    if len(summary) > 140:
        summary = summary[:137] + "..."

    return SpecializationAdvisorModel(
        hero_id=hero_id,
        name=name,
        has_dynamic_handler=bool(raw.get("has_dynamic_handler")),
        advice_model=str(raw.get("advice_model") or "conditional_only"),
        safe_default=_parse_choice(raw.get("safe_default")),
        push_default=_parse_choice(raw.get("push_default")),
        farm_default=_parse_choice(raw.get("farm_default")),
        conditionals=tuple(conditionals),
        context_flags=flags,
        explanation_summary=summary,
        review_needed=bool(raw.get("review_needed")),
        review_reasons=tuple(str(r) for r in reasons if r),
        options_by_tier=options_by_tier,
    )


@lru_cache(maxsize=1)
def load_specialization_advisor_models() -> dict[int, SpecializationAdvisorModel]:
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    heroes = data.get("heroes") if isinstance(data, dict) else None
    if not isinstance(heroes, dict):
        return {}
    out: dict[int, SpecializationAdvisorModel] = {}
    for raw in heroes.values():
        if not isinstance(raw, dict):
            continue
        model = _parse_model(raw)
        if model is not None:
            out[model.hero_id] = model
    return out


def clear_specialization_advisor_models_cache() -> None:
    load_specialization_advisor_models.cache_clear()


def advisor_model_for_hero(hero_id: int) -> SpecializationAdvisorModel | None:
    return load_specialization_advisor_models().get(hero_id)


def format_advisor_model_lines(model: SpecializationAdvisorModel) -> list[str]:
    """Compact UI lines for Specializations tab cards."""
    lines: list[str] = []
    if model.explanation_summary:
        lines.append(model.explanation_summary)
    bits: list[str] = []
    if model.safe_default is not None:
        bits.append(f"safe: {model.safe_default.name}")
    if model.push_default is not None:
        bits.append(f"push: {model.push_default.name}")
    if model.farm_default is not None:
        bits.append(f"farm: {model.farm_default.name}")
    if model.advice_model == "conditional_only" and model.safe_default is None:
        bits.append("geen universele default")
    flags = model.context_flags
    if flags.formation_dependent:
        bits.append("formation")
    if flags.adventure_dependent:
        bits.append("adventure")
    if flags.farm_push_split:
        bits.append("farm/push-split")
    if bits:
        lines.append(" · ".join(bits))
    if model.review_needed:
        reason = model.review_reasons[0] if model.review_reasons else "interne twijfel"
        lines.append(f"Review nodig: {reason}")
    return lines


def review_needed_models_for_heroes(
    hero_ids: set[int] | list[int],
) -> list[SpecializationAdvisorModel]:
    """Advisor models marked review_needed for the given formation hero ids."""
    models = load_specialization_advisor_models()
    out = [
        models[hero_id]
        for hero_id in sorted(set(hero_ids))
        if hero_id in models and models[hero_id].review_needed
    ]
    return out


def preferred_ids_for_run_goal(
    model: SpecializationAdvisorModel,
    *,
    run_goal: str | None,
) -> list[int]:
    """Pick preferred upgrade ids without collapsing conflicting defaults silently.

    If review_needed and no safe_default, return farm/push only when run_goal selects
    that lane; otherwise empty (caller keeps config/handler behavior).
    """
    goal = (run_goal or "").casefold()
    if model.context_flags.farm_push_split:
        if goal in {"gold_farm", "speed_farm", "farm"}:
            choice = model.farm_default or model.safe_default
            if choice is not None:
                return [choice.upgrade_id]
        if goal in {"push", "bud", "survival"}:
            choice = model.push_default or model.safe_default
            if choice is not None:
                return [choice.upgrade_id]
    if model.safe_default is not None:
        return [model.safe_default.upgrade_id]
    if model.push_default is not None and not model.review_needed:
        return [model.push_default.upgrade_id]
    if model.farm_default is not None and not model.review_needed:
        return [model.farm_default.upgrade_id]
    return []
