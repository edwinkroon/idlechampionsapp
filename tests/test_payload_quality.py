"""Tests for payload quality assessment and degraded API handling."""

from __future__ import annotations

import unittest

from PySide6.QtCore import QCoreApplication

from ic_core.game_data_service import GameDataService, SnapshotEnvelope
from ic_gamedata.credentials import GameCredentials
from ic_gamedata.payload_quality import assess_payload_quality


class PayloadQualityTests(unittest.TestCase):
    def test_missing_payload(self) -> None:
        q = assess_payload_quality(None)
        self.assertFalse(q.usable)
        self.assertEqual(q.formation_source, "none")
        self.assertTrue(q.warnings)

    def test_prefers_formation_grid(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "formation": [164, 168, -1],
                        "hero_in_seats": {"3": 3, "8": 164, "9": 168},
                    }
                ],
                "heroes": [],
            }
        }
        q = assess_payload_quality(payload)
        self.assertTrue(q.formation_reliable)
        self.assertEqual(q.formation_source, "grid")
        self.assertEqual(q.formation_hero_count, 2)
        self.assertEqual(q.warnings, ())

    def test_warns_on_hero_in_seats_fallback(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "formation": [-1, -1],
                        "hero_in_seats": {"3": 3, "8": 164},
                    }
                ],
                "heroes": [],
            }
        }
        q = assess_payload_quality(payload)
        self.assertEqual(q.formation_source, "hero_in_seats")
        self.assertFalse(q.formation_reliable)
        self.assertTrue(any("hero_in_seats" in w for w in q.warnings))


class DegradedApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_failure_keeps_cache_and_backs_off(self) -> None:
        svc = GameDataService()
        received: list[SnapshotEnvelope] = []
        svc.snapshot_updated.connect(received.append)
        svc._credentials = GameCredentials("https://x/", "1", "h")
        svc._latest = SnapshotEnvelope(
            version=1,
            generation=1,
            payload={"details": {}},
            api_snap=None,
            snap=None,
            err=None,
            api_detail="API ok",
            credentials=svc._credentials,
            fetched_at=1.0,
            advice_fp=(1,),
            party_id=1,
            last_success_at=1.0,
        )
        svc._last_success_at = 1.0
        svc._base_poll_ms = 30000
        svc._poll_timer.setInterval(30000)
        svc._note_failure("API timeout")
        self.assertEqual(svc._consecutive_failures, 1)
        self.assertEqual(svc._current_poll_interval(), 60000)
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].degraded)
        self.assertIs(received[0].payload, svc._latest.payload)
        self.assertIn("cache", received[0].api_detail.lower())


if __name__ == "__main__":
    unittest.main()
