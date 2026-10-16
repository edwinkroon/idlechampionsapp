"""Tests for ranked Formation next-actions."""

from __future__ import annotations

import unittest

from ic_gamedata.formation_advisor.models import FormationInsight
from ic_gamedata.next_actions import build_next_actions
from ic_gamedata.party_advisor_models import AdvisorReport, AdvisorTip


def _insight(
    *,
    insight_type: str = "swap",
    hero_id: int = 1,
    hero_name: str = "A",
    seat: int | None = 1,
    related_hero_id: int | None = 2,
    related_hero_name: str | None = "B",
    related_seat: int | None = 2,
    priority: int = 10,
    headline: str = "Move",
    detail: str = "Detail",
    bud_ratio: float | None = 1.2,
    rule_id: str = "r1",
) -> FormationInsight:
    return FormationInsight(
        insight_type=insight_type,  # type: ignore[arg-type]
        hero_id=hero_id,
        hero_name=hero_name,
        seat=seat,
        related_hero_id=related_hero_id,
        related_hero_name=related_hero_name,
        related_seat=related_seat,
        priority=priority,
        headline=headline,
        detail=detail,
        rule_source_type="heuristic",
        data_source_version="handler",
        confidence=70,
        rule_id=rule_id,
        bud_ratio=bud_ratio,
    )


def _report(
    *,
    insights: tuple[FormationInsight, ...] = (),
    tips: tuple[AdvisorTip, ...] = (),
) -> AdvisorReport:
    return AdvisorReport(
        goal="bud",
        context="campaign",
        adventure_name="Test",
        adventure_id=1,
        gold_growth_rate=None,
        adventure_buff_note=None,
        main_dps_name=None,
        formation_heroes=(),
        improvements=(),
        tips=tips,
        summary="ok",
        formation_insights=insights,
    )


class NextActionsTests(unittest.TestCase):
    def test_prefers_higher_bud_ratio_swap(self) -> None:
        low = _insight(
            hero_id=10,
            related_hero_id=11,
            related_seat=3,
            bud_ratio=1.05,
            rule_id="low",
            headline="Low",
        )
        high = _insight(
            hero_id=20,
            related_hero_id=21,
            related_seat=4,
            bud_ratio=1.5,
            rule_id="high",
            headline="High",
        )
        actions = build_next_actions(_report(insights=(low, high)))
        self.assertGreaterEqual(len(actions), 1)
        self.assertIn("Swap", actions[0].headline)
        self.assertEqual(actions[0].bud_ratio, 1.5)

    def test_drops_swap_with_bud_ratio_below_one(self) -> None:
        bad = _insight(bud_ratio=0.8, rule_id="bad")
        tip = AdvisorTip(priority=1, title="Buffer gap", detail="Add a buffer")
        actions = build_next_actions(_report(insights=(bad,), tips=(tip,)))
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].kind, "tip")
        self.assertEqual(actions[0].headline, "Buffer gap")

    def test_dedupes_same_swap_pair(self) -> None:
        a = _insight(rule_id="a", headline="First")
        b = _insight(rule_id="b", headline="Second", priority=20)
        actions = build_next_actions(_report(insights=(a, b)))
        self.assertEqual(len(actions), 1)

    def test_tips_fill_when_no_placement(self) -> None:
        tips = (
            AdvisorTip(priority=2, title="Second", detail="b"),
            AdvisorTip(priority=1, title="First", detail="a"),
        )
        actions = build_next_actions(_report(tips=tips))
        self.assertEqual([a.headline for a in actions], ["First", "Second"])

    def test_limits_to_three(self) -> None:
        insights = tuple(
            _insight(
                hero_id=i,
                related_hero_id=100 + i,
                related_seat=i,
                bud_ratio=1.0 + i * 0.1,
                rule_id=f"r{i}",
            )
            for i in range(1, 6)
        )
        actions = build_next_actions(_report(insights=insights))
        self.assertEqual(len(actions), 3)


if __name__ == "__main__":
    unittest.main()
