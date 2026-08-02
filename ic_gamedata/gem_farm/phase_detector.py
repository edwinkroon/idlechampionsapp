"""Detect gem-farm phase from live area/stacks and profile zones."""

from __future__ import annotations

from dataclasses import dataclass

from ic_gamedata.gem_farm.briv_calculator import load_briv_heuristics
from ic_gamedata.gem_farm.health_rules import is_gem_farm_monitoring_context
from ic_gamedata.gem_farm.models import BrivZoneAdvice, CopilotPhase, FarmHealthStatus, FarmProfile


@dataclass(frozen=True)
class PhaseDetection:
    phase: CopilotPhase
    stack_zone: int
    reset_zone: int
    stack_target: int | None
    reasons: tuple[str, ...]


def _effective_zones(
    zone_advice: BrivZoneAdvice | None,
    profile: FarmProfile | None,
) -> tuple[int | None, int | None, int | None]:
    stack_zone = profile.stack_zone if profile and profile.stack_zone else None
    reset_zone = profile.reset_zone if profile and profile.reset_zone else None
    stack_target = profile.stack_target_stacks if profile and profile.stack_target_stacks else None
    if zone_advice is not None:
        if stack_zone is None:
            stack_zone = zone_advice.stack_zone_recommended
        if reset_zone is None:
            reset_zone = zone_advice.reset_zone
        if stack_target is None:
            stack_target = zone_advice.stack_target
    return stack_zone, reset_zone, stack_target


def detect_copilot_phase(
    *,
    is_active: bool,
    modron_goal: int | None,
    briv_in_formation: bool,
    current_area: int | None,
    briv_stacks: int | None,
    zone_advice: BrivZoneAdvice | None,
    profile: FarmProfile | None,
    health: FarmHealthStatus | None,
) -> PhaseDetection | None:
    if not is_gem_farm_monitoring_context(
        is_active=is_active,
        modron_goal=modron_goal,
        briv_in_formation=briv_in_formation,
    ):
        return PhaseDetection(
            phase="idle",
            stack_zone=0,
            reset_zone=0,
            stack_target=None,
            reasons=("Geen gem-farm context",),
        )

    stack_zone, reset_zone, stack_target = _effective_zones(zone_advice, profile)
    if stack_zone is None or reset_zone is None or current_area is None:
        return PhaseDetection(
            phase="idle",
            stack_zone=stack_zone or 0,
            reset_zone=reset_zone or 0,
            stack_target=stack_target,
            reasons=("Zones of area onbekend",),
        )

    rules = load_briv_heuristics()
    margin = rules.phase_margin
    jump = rules.jump_buffer
    reasons: list[str] = []

    if health is not None and any(alert.rule_id == "area_stall" for alert in health.alerts):
        reasons.append("Area-stagnatie alert actief")
        return PhaseDetection(
            phase="stuck",
            stack_zone=stack_zone,
            reset_zone=reset_zone,
            stack_target=stack_target,
            reasons=tuple(reasons),
        )

    pre_reset_line = reset_zone - jump
    stack_entry = stack_zone - margin
    # Swap shortly before pre-reset so E can fire after stacking.
    swap_line = max(stack_entry + 1, pre_reset_line - max(jump, 3))

    if current_area >= pre_reset_line:
        reasons.append(f"Area {current_area} ≥ pre-reset {pre_reset_line}")
        return PhaseDetection(
            phase="pre_reset",
            stack_zone=stack_zone,
            reset_zone=reset_zone,
            stack_target=stack_target,
            reasons=tuple(reasons),
        )

    stacks_ready = (
        stack_target is not None
        and briv_stacks is not None
        and briv_stacks >= stack_target
    )
    if stacks_ready or current_area >= swap_line:
        if stacks_ready:
            reasons.append(f"Briv stacks {briv_stacks} ≥ target {stack_target}")
        else:
            reasons.append(f"Area {current_area} ≥ swap-line {swap_line}")
        return PhaseDetection(
            phase="swap_ready",
            stack_zone=stack_zone,
            reset_zone=reset_zone,
            stack_target=stack_target,
            reasons=tuple(reasons),
        )

    if current_area >= stack_entry:
        reasons.append(f"Area {current_area} in stack-zone (≥ {stack_entry})")
        return PhaseDetection(
            phase="stacking",
            stack_zone=stack_zone,
            reset_zone=reset_zone,
            stack_target=stack_target,
            reasons=tuple(reasons),
        )

    reasons.append(f"Area {current_area} < stack-entry {stack_entry}")
    return PhaseDetection(
        phase="progress",
        stack_zone=stack_zone,
        reset_zone=reset_zone,
        stack_target=stack_target,
        reasons=tuple(reasons),
    )
