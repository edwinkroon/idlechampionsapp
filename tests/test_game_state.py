"""Tests for dashboard progress helpers and game state service."""

from __future__ import annotations

import unittest

from ic_core.game_state import GameStateService
from ic_gamedata.dashboard_tiles import modron_area_progress


class ModronProgressTests(unittest.TestCase):
    def test_progress_mid_run(self) -> None:
        pct, text = modron_area_progress(250, 500)
        self.assertEqual(pct, 50)
        self.assertEqual(text, "Modron: 250 / 500")

    def test_progress_caps_at_100(self) -> None:
        pct, text = modron_area_progress(600, 500)
        self.assertEqual(pct, 100)
        self.assertEqual(text, "Modron: 600 / 500")

    def test_progress_missing_data(self) -> None:
        self.assertEqual(modron_area_progress(None, 500), (None, None))
        self.assertEqual(modron_area_progress(100, None), (None, None))
        self.assertEqual(modron_area_progress(100, 0), (None, None))


class GameStateServiceTests(unittest.TestCase):
    def test_ingest_emits_payload_changed(self) -> None:
        service = GameStateService()
        seen: list[dict] = []
        service.payload_changed.connect(seen.append)
        service.ingest_api_result(
            {"payload": {"details": {}}, "api_snap": None, "api_detail": "API ok"},
            active=False,
            refreshed_snap=None,
            mem_area=None,
            mem_gems=None,
        )
        self.assertEqual(len(seen), 1)
        self.assertIs(service.last_payload, seen[0])

    def test_connection_status_without_credentials(self) -> None:
        service = GameStateService()
        api_text, _, _, _, session_text, _ = service.connection_status(
            active=False,
            credentials_ok=False,
        )
        self.assertIn("geen credentials", api_text.lower())
        self.assertIn("gestopt", session_text.lower())


if __name__ == "__main__":
    unittest.main()
