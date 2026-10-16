"""Orchestrate formation placement insights and tips."""

from __future__ import annotations

from typing import Any

from ic_gamedata.adventure_restrictions import AdventureRosterFilter
from ic_gamedata.formation_advisor.champion_placement import evaluate_champion_placement_rules
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.formation_advisor.evaluator import evaluate_formation_rules
from ic_gamedata.formation_advisor.handlers import evaluate_placement_handlers
from ic_gamedata.formation_advisor.models import FormationInsight
from ic_gamedata.party_advisor import AdvisorTip, ContextMode, FormationHero, GoalMode

MAX_FORMATION_INSIGHTS = 6


def _insight_action_key(insight: FormationInsight) -> str:
    """Collapse duplicate tips that prescribe the same action (e.g. buffer+support)."""
    if insight.insight_type == "swap":
        heroes = tuple(
            sorted(h for h in (insight.hero_id, insight.related_hero_id) if h is not None)
        )
        seats = tuple(
            sorted(s for s in (insight.seat, insight.related_seat) if s is not None)
        )
        if heroes:
            return f"swap:{heroes}:{seats}"
    if insight.insight_type == "bench" and insight.hero_id is not None:
        return f"bench:{insight.hero_id}:{insight.related_hero_id}"
    return insight.rule_id or f"{insight.insight_type}:{insight.headline}"


def _candidate_sort_key(insight: FormationInsight) -> tuple:
    """Prefer stronger BUD proxy swaps first, then authored priority."""
    ratio = insight.bud_ratio if insight.bud_ratio is not None else 0.0
    # Swaps/bench first so they claim destination seats before softer warnings.
    kind_rank = 0 if insight.insight_type in {"swap", "bench"} else 1
    return (kind_rank, -ratio, insight.priority, insight.hero_name)


def build_formation_insights(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    roster_filter: AdventureRosterFilter | None = None,
) -> tuple[FormationInsight, ...]:
    if len(formation) < 2:
        return ()

    layout_ctx = build_formation_layout_context(
        payload,
        formation,
        goal=goal,
        context=context,
        roster_filter=roster_filter,
    )

    insights: list[FormationInsight] = []
    seen_actions: set[str] = set()
    claimed_target_seats: set[int] = set()
    claimed_movers: set[int] = set()

    candidates = (
        evaluate_formation_rules(layout_ctx)
        + evaluate_champion_placement_rules(layout_ctx)
        + evaluate_placement_handlers(layout_ctx)
    )
    candidates.sort(key=_candidate_sort_key)

    for insight in candidates:
        key = _insight_action_key(insight)
        if key in seen_actions:
            continue

        # One tip per destination seat: Lark→slot2 and Tess→slot2 must not both show.
        if insight.insight_type == "swap" and insight.related_seat is not None:
            if insight.related_seat in claimed_target_seats:
                continue
            if insight.hero_id is not None and insight.hero_id in claimed_movers:
                continue

        if insight.insight_type == "bench" and insight.related_seat is not None:
            if insight.related_seat in claimed_target_seats:
                continue

        seen_actions.add(key)
        if insight.related_seat is not None and insight.insight_type in {"swap", "bench"}:
            claimed_target_seats.add(insight.related_seat)
        if insight.insight_type == "swap" and insight.hero_id is not None:
            claimed_movers.add(insight.hero_id)
        insights.append(insight)

    return tuple(insights[:MAX_FORMATION_INSIGHTS])


def formation_insights_to_tips(insights: tuple[FormationInsight, ...]) -> list[AdvisorTip]:
    tips: list[AdvisorTip] = []
    for index, insight in enumerate(insights, start=1):
        title = insight.headline
        if insight.insight_type == "swap" and insight.related_hero_name and insight.related_seat:
            title = f"Swap: {insight.hero_name} ↔ {insight.related_hero_name}"
        elif insight.insight_type == "bench":
            title = f"Bench: {insight.headline}"
        tips.append(
            AdvisorTip(
                priority=index,
                title=title,
                detail=insight.detail,
            )
        )
    return tips
