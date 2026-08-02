"""Evaluate documentation CSV specialization rules."""

from __future__ import annotations

import logging

from ic_gamedata.specialization_models import SpecializationOption
from ic_gamedata.specialization_rules.context_builder import champion_names_match
from ic_gamedata.specialization_rules.loader import cached_documentation_rules
from ic_gamedata.specialization_rules.models import (
    AdviceResult,
    EvaluationContext,
    ExceptionRule,
    Rule,
    RuleDataset,
)
from ic_gamedata.specialization_rules.route_mapper import (
    map_label_to_upgrade_id,
    map_route_to_upgrade_id,
)

logger = logging.getLogger(__name__)


def _priority_score(dataset: RuleDataset, priority_code: str) -> int:
    return dataset.lookups.priority_scores.get(priority_code, 0)


def _evaluate_semantic_value(field: str, value: str, ctx: EvaluationContext) -> bool:
    normalized = value.strip().casefold()

    if field == "run_goal":
        return ctx.run_goal.casefold() == normalized

    if field == "alignment":
        if normalized == "best_alignment_count":
            leader = max(
                {"evil": ctx.evil_count, "good": ctx.good_count, "neutral": ctx.neutral_count},
                key={"evil": ctx.evil_count, "good": ctx.good_count, "neutral": ctx.neutral_count}.get,
            )
            return leader in {"evil", "good", "neutral"}
        if normalized == "alignment_distribution_changed":
            return ctx.alignment_distribution_changed
        if normalized.startswith("evil"):
            return _compare_threshold(ctx.evil_count, normalized.replace("evil", "").strip())
        if normalized.startswith("good"):
            return _compare_threshold(ctx.good_count, normalized.replace("good", "").strip())
        return False

    if field == "enemy_type":
        if normalized == "current_enemy_type":
            return ctx.enemy_type is not None
        if normalized == "boss_or_zone_enemy_type_changed":
            return ctx.enemy_type_changed
        return ctx.enemy_type is not None and ctx.enemy_type.casefold() == normalized

    if field == "formation_composition":
        if normalized == "bond_match":
            return ctx.dwarf_elf_count >= 2 or ctx.magic_count >= 3
        if normalized == "secondary_bond_outscores_primary":
            return ctx.secondary_bond_outscores_primary
        if normalized.startswith("magic"):
            return _compare_threshold(ctx.magic_count, normalized.replace("magic", "").strip())
        return False

    if field == "carry_target":
        if ctx.highest_damage_hero_id is None:
            return False
        return normalized in str(ctx.highest_damage_hero_id).casefold()

    if field == "automation_goal":
        return normalized in {ctx.run_goal.casefold(), "briv_stack_farm"}

    if field == "stat_threshold":
        return False

    if field == "adjacency_or_position":
        return normalized in {"carry_adjacent=true", "frontline=true"} and ctx.seat in {1, 2, 5, 6, 9, 10}

    return False


def _compare_threshold(actual: int, expression: str) -> bool:
    text = expression.strip()
    if text.startswith(">="):
        try:
            return actual >= int(text[2:].strip())
        except ValueError:
            return False
    if text.startswith(">"):
        try:
            return actual > int(text[1:].strip())
        except ValueError:
            return False
    return False


def evaluate_condition(rule: Rule, ctx: EvaluationContext) -> bool:
    operator = rule.condition_operator.strip().casefold()
    field = rule.condition_field.strip()
    value = rule.condition_value.strip()

    if operator == "equals":
        if field == "run_goal":
            return ctx.run_goal.casefold() == value.casefold()
        return _evaluate_semantic_value(field, value, ctx)
    if operator == "contains":
        return _evaluate_semantic_value(field, value, ctx)
    if operator == "gte":
        if field == "formation_composition" and value.startswith("magic"):
            return _compare_threshold(ctx.magic_count, value.replace("magic", "magic>=").replace("magic", "magic"))
        return _compare_threshold(ctx.evil_count, value)
    if operator in {"in_list", "any_true"}:
        options = [part.strip().casefold() for part in value.split("|") if part.strip()]
        return ctx.run_goal.casefold() in options
    return False


def evaluate_exception_trigger(exc: ExceptionRule, ctx: EvaluationContext) -> bool:
    pseudo_rule = Rule(
        rule_id=exc.exception_id,
        rule_version="v3",
        seat=exc.seat,
        champion=exc.champion,
        specialization_family="",
        run_goal=ctx.run_goal,
        decision_context="",
        condition_field=exc.trigger_field,
        condition_operator=exc.trigger_operator,
        condition_value=exc.trigger_value,
        machine_default=exc.forced_specialization,
        machine_alternative="",
        override_when=exc.reason,
        default_confidence=5,
        priority_code="critical",
        manual_review_code=exc.manual_review_code,
        tags=(),
        notes_for_cursor="",
        advice_pattern=exc.reason,
        source_basis="exception",
        active=True,
        data_source_version="v3_example",
    )
    return evaluate_condition(pseudo_rule, ctx)


def _rules_for_champion(dataset: RuleDataset, ctx: EvaluationContext) -> list[Rule]:
    matched = [
        rule
        for rule in dataset.rules
        if rule.active and champion_names_match(rule.champion, ctx.hero_name)
    ]
    if ctx.seat is not None:
        seat_matches = [rule for rule in matched if rule.seat == ctx.seat]
        if seat_matches:
            return seat_matches
    return matched


def _pick_base_rule(dataset: RuleDataset, ctx: EvaluationContext) -> Rule | None:
    candidates = _rules_for_champion(dataset, ctx)
    if not candidates:
        return None

    if len(candidates) == 1 and candidates[0].is_v2_full:
        return candidates[0]

    matching = [rule for rule in candidates if evaluate_condition(rule, ctx)]
    if matching:
        return max(
            matching,
            key=lambda rule: (_priority_score(dataset, rule.priority_code), rule.default_confidence),
        )

    run_goal_matches = [rule for rule in candidates if rule.run_goal == ctx.run_goal]
    if run_goal_matches:
        return max(
            run_goal_matches,
            key=lambda rule: (_priority_score(dataset, rule.priority_code), rule.default_confidence),
        )

    return max(
        candidates,
        key=lambda rule: (_priority_score(dataset, rule.priority_code), rule.default_confidence),
    )


def _label_matches_route(label: str, route_name: str) -> bool:
    text = label.casefold()
    keywords = {
        "speed": ("speed", "boss wants", "rapid", "fast friends"),
        "gold": ("gold", "favor", "piracy", "ohhh yeah", "battle master", "law", "chaos"),
        "tank": ("tank", "devotion", "frontline", "oath", "wild shape"),
        "healing": ("heal", "life", "spores", "war domain"),
        "formation": ("bond", "potpourri", "pack tactics", "kobold", "hall"),
        "enemy": ("enemy", "humanoid", "fiend", "favored"),
        "support": ("support", "valor", "ahead", "behind", "confidence"),
    }.get(route_name, ())
    return any(keyword in text for keyword in keywords)


def _choose_v2_full_label(rule: Rule, ctx: EvaluationContext) -> tuple[str, str]:
    """Pick usually_choose vs alternative for v2_full rows; returns (label, condition_used)."""
    default = rule.default_label or rule.machine_default
    alternative = rule.alternative_label or rule.machine_alternative
    tags = {tag.casefold() for tag in rule.tags}

    if ctx.run_goal == "speed_farm" and "speed" in tags:
        if _label_matches_route(default, "speed"):
            return default, f"run_goal=speed_farm + speed tag -> {default}"
        if alternative and _label_matches_route(alternative, "speed"):
            return alternative, f"run_goal=speed_farm + speed tag -> {alternative}"

    if ctx.run_goal == "gold_farm" and ("gold" in tags or "favor" in tags):
        if _label_matches_route(default, "gold"):
            return default, f"run_goal=gold_farm + gold/favor tag -> {default}"
        if alternative and _label_matches_route(alternative, "gold"):
            return alternative, f"run_goal=gold_farm + gold/favor tag -> {alternative}"

    if ctx.run_goal in {"survival", "push"} and (
        ctx.survival_blocks_progress or ctx.run_goal == "survival"
    ):
        if "healing" in tags or "survival" in tags:
            if alternative and _label_matches_route(alternative, "healing"):
                return alternative, f"survival context -> {alternative}"
            if _label_matches_route(default, "healing"):
                return default, f"survival context -> {default}"
        if "tank" in tags:
            if alternative and _label_matches_route(alternative, "tank"):
                return alternative, f"survival context -> {alternative}"
            if _label_matches_route(default, "tank"):
                return default, f"survival context -> {default}"

    if "formation-dependent" in tags:
        if ctx.dwarf_elf_count >= 2 or ctx.magic_count >= 3 or ctx.secondary_bond_outscores_primary:
            if _label_matches_route(default, "formation"):
                return default, f"formation bond match -> {default}"
            if alternative and _label_matches_route(alternative, "formation"):
                return alternative, f"formation bond match -> {alternative}"

    if "alignment" in tags:
        if ctx.alignment_distribution_changed and alternative:
            return alternative, "alignment distribution changed -> alternative"
        return default, "alignment tag -> default"

    if "adventure-specific" in tags and ctx.enemy_type:
        if _label_matches_route(default, "enemy"):
            return default, f"enemy_type={ctx.enemy_type} -> {default}"
        if alternative and _label_matches_route(alternative, "enemy"):
            return alternative, f"enemy_type={ctx.enemy_type} -> {alternative}"

    if ctx.run_goal == "speed_farm" and alternative and _label_matches_route(alternative, "speed"):
        return alternative, f"run_goal=speed_farm fallback -> {alternative}"

    return default, f"v2_full default -> {default}"


def _resolve_route_key(rule: Rule, ctx: EvaluationContext, dataset: RuleDataset) -> tuple[str, str]:
    if rule.is_v2_full:
        return _choose_v2_full_label(rule, ctx)

    route_key = rule.machine_default
    condition_used = f"{rule.condition_field} {rule.condition_operator} {rule.condition_value}"
    if not evaluate_condition(rule, ctx) and rule.machine_alternative:
        route_key = rule.machine_alternative
        condition_used = f"fallback to alternative ({route_key})"
    return route_key, condition_used


def apply_exception_rules(
    base: AdviceResult,
    dataset: RuleDataset,
    ctx: EvaluationContext,
    options: list[SpecializationOption],
    *,
    tier_index: int | None = None,
) -> AdviceResult:
    for exc in dataset.exceptions:
        if not champion_names_match(exc.champion, ctx.hero_name):
            continue
        if exc.seat is not None and ctx.seat is not None and exc.seat != ctx.seat:
            continue
        if not evaluate_exception_trigger(exc, ctx):
            continue
        upgrade_id = map_route_to_upgrade_id(
            exc.forced_specialization,
            options,
            tier_index=tier_index,
            champion_name=ctx.hero_name,
        )
        if upgrade_id is None:
            upgrade_id = map_label_to_upgrade_id(
                exc.forced_specialization,
                options,
                tier_index=tier_index,
                champion_name=ctx.hero_name,
            )
        return AdviceResult(
            champion=ctx.hero_name,
            seat=ctx.seat,
            specialization_key=exc.forced_specialization,
            upgrade_id=upgrade_id,
            rule_id=base.rule_id,
            exception_id=exc.exception_id,
            rationale=exc.reason or base.rationale,
            condition_used=f"{exc.trigger_field} {exc.trigger_operator} {exc.trigger_value}",
            manual_review=exc.manual_review_code,
            confidence=base.confidence,
            source=base.source,
            priority_code="critical",
            data_source_version=base.data_source_version,
            rule_source_type=base.rule_source_type,
            chosen_label=exc.forced_specialization,
        )
    return base


def _advice_from_rule(
    rule: Rule,
    route_key: str,
    ctx: EvaluationContext,
    dataset: RuleDataset,
    options: list[SpecializationOption],
    *,
    tier_index: int | None = None,
    condition_used: str,
    chosen_label: str,
) -> AdviceResult:
    upgrade_id = map_label_to_upgrade_id(
        chosen_label or route_key,
        options,
        tier_index=tier_index,
        champion_name=ctx.hero_name,
    )
    if upgrade_id is None:
        upgrade_id = map_route_to_upgrade_id(
            route_key,
            options,
            tier_index=tier_index,
            champion_name=ctx.hero_name,
        )
    if upgrade_id is None and ctx.run_goal == "speed_farm":
        upgrade_id = map_route_to_upgrade_id(
            "speed_route",
            options,
            tier_index=tier_index,
            champion_name=ctx.hero_name,
        )
    if upgrade_id is None and ctx.run_goal == "gold_farm":
        upgrade_id = map_route_to_upgrade_id(
            "gold_route",
            options,
            tier_index=tier_index,
            champion_name=ctx.hero_name,
        )

    display_label = chosen_label or route_key
    if upgrade_id is not None:
        by_id = {opt.upgrade_id: opt.name for opt in options}
        display_label = by_id.get(upgrade_id, display_label)

    rationale = rule.advice_pattern or rule.override_when or f"Default {display_label}"
    return AdviceResult(
        champion=ctx.hero_name,
        seat=ctx.seat,
        specialization_key=route_key,
        upgrade_id=upgrade_id,
        rule_id=rule.rule_id,
        exception_id=None,
        rationale=rationale,
        condition_used=condition_used,
        manual_review=rule.manual_review_code,
        confidence=rule.default_confidence,
        source=dataset.source,
        priority_code=rule.priority_code,
        data_source_version=rule.data_source_version,
        rule_source_type=rule.rule_source_type,
        chosen_label=display_label,
    )


def evaluate_specialization(
    ctx: EvaluationContext,
    options: list[SpecializationOption],
    dataset: RuleDataset | None = None,
    *,
    tier_index: int | None = None,
) -> AdviceResult | None:
    data = dataset or cached_documentation_rules()
    if not data.is_usable:
        if data.validation_errors:
            logger.warning("CSV specialization dataset invalid: %s", "; ".join(data.validation_errors[:3]))
        return None
    if data.source == "v2_full":
        logger.debug("CSV specialization advice uses v2_full production dataset")

    base_rule = _pick_base_rule(data, ctx)
    if base_rule is None:
        return None

    route_key, condition_used = _resolve_route_key(base_rule, ctx, data)
    chosen_label = route_key

    base_advice = _advice_from_rule(
        base_rule,
        route_key,
        ctx,
        data,
        options,
        tier_index=tier_index,
        condition_used=condition_used,
        chosen_label=chosen_label,
    )
    return apply_exception_rules(base_advice, data, ctx, options, tier_index=tier_index)
