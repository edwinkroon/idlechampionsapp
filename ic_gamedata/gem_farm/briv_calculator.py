"""Conservative Briv stack/reset zone heuristics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ic_gamedata.gem_farm.models import BrivGear, BrivZoneAdvice, FarmProfile
from ic_gamedata.paths import BRIV_HEURISTICS_PATH


@dataclass(frozen=True)
class BrivHeuristics:
    conservative_margin: int = 8
    phase_margin: int = 5
    jump_buffer: int = 5
    reset_buffer: int = 15
    stack_above_reset_min: int = 14
    stack_above_reset_max: int = 24
    rarity_factor: dict[int, float] = field(default_factory=lambda: {1: 0.98, 2: 1.0, 3: 1.01, 4: 1.03})
    gild_factor: dict[int, float] = field(default_factory=lambda: {0: 1.0, 1: 1.02, 2: 1.04})
    enchant_buckets: tuple[tuple[int, int], ...] = ()


def load_briv_heuristics(path: Path | None = None) -> BrivHeuristics:
    file_path = path or BRIV_HEURISTICS_PATH
    if not file_path.is_file():
        return BrivHeuristics()
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return BrivHeuristics()
    if not isinstance(raw, dict):
        return BrivHeuristics()

    rarity_raw = raw.get("rarity_factor") if isinstance(raw.get("rarity_factor"), dict) else {}
    gild_raw = raw.get("gild_factor") if isinstance(raw.get("gild_factor"), dict) else {}
    buckets: list[tuple[int, int]] = []
    for entry in raw.get("enchant_buckets") or []:
        if not isinstance(entry, dict):
            continue
        try:
            buckets.append((int(entry["max_enchant"]), int(entry["stack_target"])))
        except (KeyError, TypeError, ValueError):
            continue
    buckets.sort(key=lambda pair: pair[0])

    return BrivHeuristics(
        conservative_margin=int(raw.get("conservative_margin", 8)),
        phase_margin=int(raw.get("phase_margin", 5)),
        jump_buffer=int(raw.get("jump_buffer", 5)),
        reset_buffer=int(raw.get("reset_buffer", 15)),
        stack_above_reset_min=int(raw.get("stack_above_reset_min", 14)),
        stack_above_reset_max=int(raw.get("stack_above_reset_max", 24)),
        rarity_factor={int(k): float(v) for k, v in rarity_raw.items()},
        gild_factor={int(k): float(v) for k, v in gild_raw.items()},
        enchant_buckets=tuple(buckets),
    )


def _stack_target_for_enchant(heuristics: BrivHeuristics, enchant: int) -> int | None:
    for max_enchant, target in heuristics.enchant_buckets:
        if enchant <= max_enchant:
            return target
    if heuristics.enchant_buckets:
        return heuristics.enchant_buckets[-1][1]
    return None


def _gear_quality_factor(heuristics: BrivHeuristics, gear: BrivGear | None) -> float:
    if gear is None:
        return 1.0
    rarity = heuristics.rarity_factor.get(gear.rarity, 1.0)
    gild = heuristics.gild_factor.get(gear.gild, 1.0)
    return rarity * gild


def advise_briv_zones(
    *,
    modron_goal: int | None,
    gear: BrivGear | None,
    profile: FarmProfile | None = None,
    heuristics: BrivHeuristics | None = None,
) -> BrivZoneAdvice | None:
    if modron_goal is None or modron_goal <= 0:
        return None
    rules = heuristics or load_briv_heuristics()
    quality = _gear_quality_factor(rules, gear)

    reset_buffer = max(rules.reset_buffer, rules.conservative_margin)
    # Stack BEFORE reset (progress → W stack → E swap → reset). Values from
    # stack_above_reset_* are used as "areas before reset" for the stack park.
    stack_before_min = rules.stack_above_reset_min + rules.conservative_margin
    stack_before_max = rules.stack_above_reset_max + rules.conservative_margin

    # Better gear → slightly lower zones (still conservative via margin).
    adjust = int(round((1.0 - min(quality, 1.06)) * 10))
    reset_zone = max(1, modron_goal - reset_buffer - adjust)
    stack_zone_max = max(1, reset_zone - stack_before_min)
    stack_zone_min = max(1, reset_zone - stack_before_max)
    if stack_zone_min > stack_zone_max:
        stack_zone_min, stack_zone_max = stack_zone_max, stack_zone_min
    stack_zone_recommended = stack_zone_max

    stack_target = None
    if profile is not None and profile.stack_target_stacks is not None:
        stack_target = profile.stack_target_stacks
    elif gear is not None:
        stack_target = _stack_target_for_enchant(rules, gear.enchant)

    gear_txt = "onbekende gear"
    if gear is not None:
        gear_txt = f"{gear.item_level_label} {gear.rarity_label} {gear.gild_label}"

    explanation = (
        f"Conservatief advies voor Modron-doel {modron_goal} met Briv slot 4 ({gear_txt}). "
        f"Stack vóór reset: zone rond {stack_zone_recommended} "
        f"(range {stack_zone_min}–{stack_zone_max}), reset rond {reset_zone}. "
        f"Verifieer op Byteglow/Emmotes als je agressiever wilt."
    )

    return BrivZoneAdvice(
        modron_goal=modron_goal,
        reset_zone=reset_zone,
        stack_zone_min=stack_zone_min,
        stack_zone_max=stack_zone_max,
        stack_zone_recommended=stack_zone_recommended,
        stack_target=stack_target,
        explanation=explanation,
    )
