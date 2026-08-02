"""Evaluate formation placement CSV rules."""

from __future__ import annotations

from ic_gamedata.formation_advisor.loader import (
    cached_formation_rules,
    rule_matches_context,
    rule_matches_goal,
)
from ic_gamedata.formation_advisor.models import FormationInsight, FormationLayoutContext, PlacementRule


def _format_template(template: str, ctx: FormationLayoutContext, **extra: str) -> str:
    carry_id = ctx.carry_hero_id
    carry_seat = ctx.seat_of(carry_id) if carry_id is not None else None
    values = {
        "hero": extra.get("hero", ""),
        "seat": extra.get("seat", ""),
        "zone": extra.get("zone", ""),
        "carry": ctx.name(carry_id) if carry_id is not None else "carry",
        "carry_seat": str(carry_seat) if carry_seat is not None else "—",
        "party_size": str(ctx.party_size),
        "related_hero": extra.get("related_hero", ""),
        "related_seat": extra.get("related_seat", ""),
    }
    try:
        return template.format(**values)
    except KeyError:
        return template


def _hero_matches_selector(rule: PlacementRule, ctx: FormationLayoutContext, hero_id: int) -> bool:
    if rule.champion and rule.champion.casefold() != ctx.name(hero_id).casefold():
        return False
    if rule.role and rule.role not in ctx.roles(hero_id):
        return False
    if rule.tag and rule.tag not in ctx.tags(hero_id):
        return False
    return True


def _party_has_tag(ctx: FormationLayoutContext, tag: str) -> bool:
    for hero_id in ctx.active_hero_ids:
        if tag in ctx.tags(hero_id) or tag in ctx.roles(hero_id):
            return True
    return False


def _carry_has_adjacent_tag(ctx: FormationLayoutContext, tag: str) -> bool:
    carry_id = ctx.carry_hero_id
    if carry_id is None:
        return False
    carry_seat = ctx.seat_of(carry_id)
    if carry_seat is None:
        return False
    for neighbor_seat in ctx.adjacent_seats(carry_seat):
        neighbor_id = ctx.hero_at_seat(neighbor_seat)
        if neighbor_id is None:
            continue
        if tag in ctx.tags(neighbor_id) or tag in ctx.roles(neighbor_id):
            return True
    return False


def _buffers_and_debuffers(ctx: FormationLayoutContext) -> list[int]:
    result: list[int] = []
    for hero_id in ctx.active_hero_ids:
        if hero_id == ctx.carry_hero_id:
            continue
        if "buffer" in ctx.tags(hero_id) or "debuffer" in ctx.tags(hero_id):
            result.append(hero_id)
        elif "support" in ctx.roles(hero_id) and ("buffer" in ctx.tags(hero_id) or ctx.goal == "bud"):
            result.append(hero_id)
    return result


def _find_swap_partner(ctx: FormationLayoutContext, hero_id: int) -> tuple[int | None, int | None]:
    """Seat adjacent to carry that hero could swap with."""
    carry_id = ctx.carry_hero_id
    if carry_id is None or hero_id == carry_id:
        return None, None
    carry_seat = ctx.seat_of(carry_id)
    hero_seat = ctx.seat_of(hero_id)
    if carry_seat is None or hero_seat is None:
        return None, None
    if ctx.is_adjacent(hero_id, carry_id):
        return None, None

    best_partner: int | None = None
    best_seat: int | None = None
    for neighbor_seat in ctx.adjacent_seats(carry_seat):
        if neighbor_seat == hero_seat:
            continue
        partner_id = ctx.hero_at_seat(neighbor_seat)
        if partner_id is None:
            return None, neighbor_seat
        partner_roles = ctx.roles(partner_id)
        if "tank" not in partner_roles and partner_id != carry_id:
            best_partner = partner_id
            best_seat = neighbor_seat
    return best_partner, best_seat


def _evaluate_rule_for_hero(
    rule: PlacementRule,
    ctx: FormationLayoutContext,
    hero_id: int,
) -> FormationInsight | None:
    seat = ctx.seat_of(hero_id)
    if seat is None:
        return None
    field = rule.condition_field
    op = rule.condition_operator
    value = rule.condition_value

    triggered = False
    related_hero_id: int | None = None
    related_seat: int | None = None

    if field == "seat_zone":
        zone = ctx.zone_of_seat(seat)
        if op == "not_in" and zone != value:
            triggered = True
        elif op == "equals" and zone == value:
            triggered = True

    elif field == "adjacent_to_carry":
        carry_id = ctx.carry_hero_id
        if carry_id is None or hero_id == carry_id:
            return None
        is_adj = ctx.is_adjacent(hero_id, carry_id)
        if op == "false" and not is_adj:
            triggered = True
            related_hero_id = carry_id
            related_seat = ctx.seat_of(carry_id)
            partner, partner_seat = _find_swap_partner(ctx, hero_id)
            if partner is not None:
                related_hero_id = partner
                related_seat = partner_seat

    if not triggered:
        return None

    hero_name = ctx.name(hero_id)
    related_name = ctx.name(related_hero_id) if related_hero_id is not None else None
    headline = _format_template(rule.headline, ctx, hero=hero_name, seat=str(seat), zone=ctx.zone_of_seat(seat))
    detail = _format_template(
        rule.detail,
        ctx,
        hero=hero_name,
        seat=str(seat),
        zone=ctx.zone_of_seat(seat),
        related_hero=related_name or "",
        related_seat=str(related_seat) if related_seat is not None else "",
    )
    if rule.tip_type == "swap" and related_hero_id is not None and related_seat is not None:
        detail += f" Suggestie: wissel {hero_name} (slot {seat}) met {related_name} (slot {related_seat})."
    elif rule.tip_type == "swap" and related_seat is not None and related_hero_id is None:
        detail += f" Suggestie: schuif {hero_name} naar leeg slot {related_seat} naast carry."

    return FormationInsight(
        insight_type=rule.tip_type,
        hero_id=hero_id,
        hero_name=hero_name,
        seat=seat,
        related_hero_id=related_hero_id,
        related_hero_name=related_name,
        related_seat=related_seat,
        priority=rule.priority,
        headline=headline,
        detail=detail,
        rule_source_type=rule.rule_source_type,
        data_source_version="formation_rules_v1",
        confidence=4 if rule.rule_source_type == "authored" else 3,
        rule_id=rule.rule_id,
    )


def _evaluate_party_rule(rule: PlacementRule, ctx: FormationLayoutContext) -> FormationInsight | None:
    field = rule.condition_field
    op = rule.condition_operator
    value = rule.condition_value
    triggered = False

    if field == "party_size" and op == "lt":
        threshold = int(value) if value.isdigit() else 10
        triggered = ctx.party_size < threshold
    elif field == "party_has_tag" and op == "false":
        triggered = not _party_has_tag(ctx, value)
    elif field == "carry_has_adjacent_tag" and op == "false":
        triggered = not _carry_has_adjacent_tag(ctx, value)

    if not triggered:
        return None

    carry_id = ctx.carry_hero_id
    carry_name = ctx.name(carry_id) if carry_id is not None else "carry"
    carry_seat = str(ctx.seat_of(carry_id)) if carry_id and ctx.seat_of(carry_id) else "—"
    headline = _format_template(rule.headline, ctx, hero=carry_name, seat=carry_seat)
    detail = _format_template(rule.detail, ctx, hero=carry_name, seat=carry_seat)

    return FormationInsight(
        insight_type=rule.tip_type,
        hero_id=carry_id,
        hero_name=carry_name,
        seat=ctx.seat_of(carry_id) if carry_id else None,
        related_hero_id=None,
        related_hero_name=None,
        related_seat=None,
        priority=rule.priority,
        headline=headline,
        detail=detail,
        rule_source_type=rule.rule_source_type,
        data_source_version="formation_rules_v1",
        confidence=4 if rule.rule_source_type == "authored" else 3,
        rule_id=rule.rule_id,
    )


def evaluate_formation_rules(ctx: FormationLayoutContext) -> list[FormationInsight]:
    dataset = cached_formation_rules()
    insights: list[FormationInsight] = []
    seen_rules: set[str] = set()

    for rule in dataset.rules:
        if not rule_matches_goal(rule, ctx.run_goal):
            continue
        if not rule_matches_context(rule, ctx.context):
            continue
        if rule.rule_id in seen_rules:
            continue

        if rule.condition_field in ("party_size", "party_has_tag", "carry_has_adjacent_tag"):
            insight = _evaluate_party_rule(rule, ctx)
            if insight is not None:
                insights.append(insight)
                seen_rules.add(rule.rule_id)
            continue

        for hero_id in ctx.active_hero_ids:
            if not _hero_matches_selector(rule, ctx, hero_id):
                continue
            insight = _evaluate_rule_for_hero(rule, ctx, hero_id)
            if insight is not None:
                insights.append(insight)
                seen_rules.add(rule.rule_id)
                break

    return insights
