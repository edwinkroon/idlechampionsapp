"""Ranked next actions for the Formation tab (one truth over tips/insights)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ic_gamedata.formation_advisor.models import FormationInsight
from ic_gamedata.party_advisor_models import AdvisorReport, AdvisorTip

NextActionKind = Literal["swap", "bench", "placement", "warning", "tip", "seat"]

MAX_NEXT_ACTIONS = 3


@dataclass(frozen=True)
class NextAction:
    kind: NextActionKind
    headline: str
    detail: str
    score: float
    seat: int | None = None
    hero_id: int | None = None
    related_hero_id: int | None = None
    bud_ratio: float | None = None


def _insight_dedupe_key(insight: FormationInsight) -> str:
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
    if insight.seat is not None and insight.hero_id is not None:
        return f"{insight.insight_type}:{insight.hero_id}:{insight.seat}"
    return insight.rule_id or f"{insight.insight_type}:{insight.headline}"


def _insight_passes_bud_gate(insight: FormationInsight) -> bool:
    """Swap/bench actions need a non-regressive BUD proxy ratio."""
    if insight.insight_type not in {"swap", "bench"}:
        return True
    ratio = insight.bud_ratio
    if ratio is None:
        return False
    return ratio >= 1.0


def _insight_sort_key(insight: FormationInsight) -> tuple:
    ratio = insight.bud_ratio if insight.bud_ratio is not None else 0.0
    kind_rank = 0 if insight.insight_type in {"swap", "bench"} else 1
    return (kind_rank, -ratio, insight.priority, insight.hero_name)


def _insight_to_action(insight: FormationInsight) -> NextAction:
    kind: NextActionKind
    if insight.insight_type in {"swap", "bench", "placement", "warning"}:
        kind = insight.insight_type  # type: ignore[assignment]
    else:
        kind = "placement"
    headline = insight.headline
    if insight.insight_type == "swap" and insight.related_hero_name and insight.related_seat:
        headline = f"Swap: {insight.hero_name} ↔ {insight.related_hero_name}"
    elif insight.insight_type == "bench":
        peer = insight.related_hero_name or "bench"
        headline = f"Bench: bring in {insight.hero_name} (replace {peer})"
    ratio = insight.bud_ratio if insight.bud_ratio is not None else 0.0
    # Higher score = stronger action (for display/tests); sort uses _insight_sort_key.
    score = float(ratio) * 1000.0 - float(insight.priority)
    return NextAction(
        kind=kind,
        headline=headline,
        detail=insight.detail,
        score=score,
        seat=insight.seat if insight.seat is not None else insight.related_seat,
        hero_id=insight.hero_id,
        related_hero_id=insight.related_hero_id,
        bud_ratio=insight.bud_ratio,
    )


def _tip_to_action(tip: AdvisorTip) -> NextAction:
    return NextAction(
        kind="tip",
        headline=tip.title,
        detail=tip.detail,
        score=100.0 - float(tip.priority),
        seat=None,
        hero_id=None,
        related_hero_id=None,
        bud_ratio=None,
    )


def _seat_actions(report: AdvisorReport) -> list[NextAction]:
    seat_report = report.seat_report
    if seat_report is None:
        return []
    seats = getattr(seat_report, "seats", None) or ()
    out: list[NextAction] = []
    for seat in seats:
        priority = getattr(seat, "priority", 99)
        if priority >= 20:
            continue
        insights = getattr(seat, "insights", ()) or ()
        if not insights:
            continue
        line = insights[0]
        hero_name = getattr(seat, "hero_name", "Champion")
        seat_no = getattr(seat, "seat", None)
        out.append(
            NextAction(
                kind="seat",
                headline=getattr(line, "headline", None) or f"{hero_name}: seat issue",
                detail=getattr(line, "detail", "") or getattr(seat, "relevance_reason", ""),
                score=500.0 - float(priority),
                seat=seat_no,
                hero_id=getattr(seat, "hero_id", None),
            )
        )
    out.sort(key=lambda a: -a.score)
    return out


def build_next_actions(
    report: AdvisorReport,
    *,
    limit: int = MAX_NEXT_ACTIONS,
) -> tuple[NextAction, ...]:
    """Collapse formation insights + tips (+ urgent seats) into a short action list."""
    if limit <= 0:
        return ()

    insights = tuple(report.formation_insights or ())
    gated = [ins for ins in insights if _insight_passes_bud_gate(ins)]
    gated.sort(key=_insight_sort_key)

    placement_actions: list[NextAction] = []
    seen: set[str] = set()
    claimed_seats: set[int] = set()
    claimed_heroes: set[int] = set()

    for insight in gated:
        key = _insight_dedupe_key(insight)
        if key in seen:
            continue
        target = insight.related_seat if insight.insight_type in {"swap", "bench"} else insight.seat
        if target is not None and target in claimed_seats and insight.insight_type in {"swap", "bench"}:
            continue
        if insight.hero_id is not None and insight.hero_id in claimed_heroes and insight.insight_type == "swap":
            continue
        seen.add(key)
        if target is not None and insight.insight_type in {"swap", "bench"}:
            claimed_seats.add(target)
        if insight.insight_type == "swap" and insight.hero_id is not None:
            claimed_heroes.add(insight.hero_id)
        placement_actions.append(_insight_to_action(insight))

    has_strong_placement = any(a.kind in {"swap", "bench"} for a in placement_actions)
    actions = list(placement_actions)

    # Seat urgency fills gaps; keep below strong placement moves.
    for seat_action in _seat_actions(report):
        if len(actions) >= limit:
            break
        dedupe = f"seat:{seat_action.hero_id}:{seat_action.seat}"
        if dedupe in seen:
            continue
        if seat_action.seat is not None and seat_action.seat in claimed_seats:
            continue
        seen.add(dedupe)
        actions.append(seat_action)

    # Composition tips: only when no strong placement moves, or to fill remaining slots.
    tips = tuple(report.tips or ())
    if tips and (not has_strong_placement or len(actions) < limit):
        for tip in sorted(tips, key=lambda t: t.priority):
            if len(actions) >= limit:
                break
            if has_strong_placement and any(a.kind in {"swap", "bench"} for a in actions):
                # Fill only; do not outrank placement.
                pass
            key = f"tip:{tip.title}"
            if key in seen:
                continue
            seen.add(key)
            actions.append(_tip_to_action(tip))

    return tuple(actions[:limit])


def next_actions_from_report(report: Any, *, limit: int = MAX_NEXT_ACTIONS) -> tuple[NextAction, ...]:
    """UI-safe wrapper when report typing is loose."""
    if not isinstance(report, AdvisorReport):
        return ()
    return build_next_actions(report, limit=limit)
