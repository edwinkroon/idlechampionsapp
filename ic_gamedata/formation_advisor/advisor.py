"""Orchestrate formation placement insights and tips."""

from __future__ import annotations

from typing import Any

from ic_gamedata.adventure_restrictions import AdventureRosterFilter
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.formation_advisor.evaluator import evaluate_formation_rules
from ic_gamedata.formation_advisor.handlers import evaluate_placement_handlers
from ic_gamedata.formation_advisor.models import FormationInsight
from ic_gamedata.party_advisor import AdvisorTip, ContextMode, FormationHero, GoalMode

MAX_FORMATION_INSIGHTS = 6


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
    seen_keys: set[str] = set()

    for insight in evaluate_formation_rules(layout_ctx) + evaluate_placement_handlers(layout_ctx):
        key = insight.rule_id or f"{insight.insight_type}:{insight.headline}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        insights.append(insight)

    insights.sort(key=lambda item: (item.priority, item.hero_name))
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
