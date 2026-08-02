"""Tests for feat status classification."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.feat_status import (
    FeatRecommendation,
    build_feat_recommendations,
    classify_recommended_feat,
)
from ic_gamedata.seat_advisor import build_seat_advisor_report
from tests.test_seat_advisor import _hero


class FeatStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        from ic_gamedata.feat_status import _feat_id_by_hero_and_name

        _feat_id_by_hero_and_name.cache_clear()

    def test_classify_active_owned_missing(self) -> None:
        feat_map = {
            3: {
                "strong willed": 715,
                "courageous": 286,
                "tough": 16,
            }
        }
        payload = {
            "details": {
                "heroes": [
                    {
                        "hero_id": 3,
                        "unlocked_feats": [16, 286],
                        "active_feats": [286],
                    }
                ]
            }
        }
        with patch("ic_gamedata.feat_status._feat_id_by_hero_and_name", return_value=feat_map):
            self.assertEqual(classify_recommended_feat(3, "Courageous", payload), "active")
            self.assertEqual(classify_recommended_feat(3, "Tough", payload), "owned")
            self.assertEqual(classify_recommended_feat(3, "Strong Willed", payload), "missing")
            self.assertEqual(classify_recommended_feat(3, "Unknown Feat", payload), "unknown")

    def test_build_feat_recommendations_preserves_order(self) -> None:
        feat_map = {3: {"strong willed": 715, "courageous": 286}}
        payload = {
            "details": {
                "heroes": [
                    {"hero_id": 3, "unlocked_feats": [715], "active_feats": [715]},
                ]
            }
        }
        with patch("ic_gamedata.feat_status._feat_id_by_hero_and_name", return_value=feat_map):
            items = build_feat_recommendations(
                3,
                ("Strong Willed", "Courageous"),
                payload,
            )
        self.assertEqual(
            items,
            (
                FeatRecommendation(name="Strong Willed", status="active"),
                FeatRecommendation(name="Courageous", status="missing"),
            ),
        )

    def test_seat_report_includes_feat_statuses(self) -> None:
        feat_map = {3: {"strong willed": 715, "courageous": 286}}
        with patch("ic_gamedata.feat_status._feat_id_by_hero_and_name", return_value=feat_map):
            seat_report = build_seat_advisor_report(
                self.payload,
                (_hero(3, "Nayeli", 2, roles=("tank", "support")),),
                goal="bud",
                context="campaign",
            )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        seat = seat_report.seats[0]
        self.assertGreaterEqual(len(seat.recommended_feats), 1)
        statuses = {item.status for item in seat.recommended_feats}
        self.assertTrue(statuses.issubset({"active", "owned", "missing", "unknown"}))


if __name__ == "__main__":
    unittest.main()
