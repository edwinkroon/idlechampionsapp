"""Tests for GameDataService, advice fingerprints, and credential cache."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication

from ic_gamedata.advice_fingerprint import advice_fingerprint, party_id_from_payload
from ic_gamedata.credential_cache import CredentialCache
from ic_gamedata.credentials import GameCredentials
from ic_core.game_data_service import GameDataService, SnapshotEnvelope


def _payload(*, party: int = 1, formation: list | None = None, adventure: int = 14) -> dict:
    return {
        "details": {
            "active_game_instance_id": party,
            "game_instances": [
                {
                    "game_instance_id": party,
                    "current_adventure_id": adventure,
                    "hero_in_seats": {"8": 164, "9": 168},
                    "formation": formation if formation is not None else [164, 168, -1],
                }
            ],
            "heroes": [
                {
                    "hero_id": 164,
                    "owned": 1,
                    "specialization_choices": [{"upgrade_id": 1}],
                    "active_feats": [10],
                },
                {"hero_id": 168, "owned": 1, "specialization_choices": [], "active_feats": []},
            ],
        }
    }


class AdviceFingerprintTests(unittest.TestCase):
    def test_party_and_formation_change_fingerprint(self) -> None:
        a = advice_fingerprint(_payload(formation=[164, 168]))
        b = advice_fingerprint(_payload(formation=[164]))
        self.assertIsNotNone(a)
        self.assertNotEqual(a, b)
        self.assertEqual(party_id_from_payload(_payload(party=2)), 2)

    def test_spec_choice_changes_fingerprint(self) -> None:
        p1 = _payload()
        p2 = json.loads(json.dumps(p1))
        p2["details"]["heroes"][0]["specialization_choices"] = [{"upgrade_id": 99}]
        self.assertNotEqual(advice_fingerprint(p1), advice_fingerprint(p2))


class CredentialCacheTests(unittest.TestCase):
    def test_caches_until_mtime_changes(self) -> None:
        cache = CredentialCache()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "webRequestLog.txt"
            path.write_text("not a real log", encoding="utf-8")
            with mock.patch(
                "ic_gamedata.credential_cache.extract_credentials_from_log",
                return_value=GameCredentials("https://x/", "1", "h"),
            ) as extract:
                first = cache.get(path)
                second = cache.get(path)
                self.assertEqual(extract.call_count, 1)
                self.assertIs(first, second)
                path.write_text("changed", encoding="utf-8")
                cache.get(path)
                self.assertEqual(extract.call_count, 2)


class GameDataServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_coalesce_forces_while_inflight(self) -> None:
        svc = GameDataService()
        svc._credentials = GameCredentials("https://x/", "1", "h")
        svc._inflight = True
        svc.request_poll(reason="timer", auto_refresh=True)
        svc.request_poll(
            reason="advisor",
            force_consumers={"advisor"},
            auto_refresh=False,
        )
        self.assertIn("advisor", svc._pending_force)
        self.assertFalse(svc._pending_auto_refresh)
        self.assertIn("advisor", svc._pending_reasons)
        self.assertIn("timer", svc._pending_reasons)

    def test_stale_generation_ignored(self) -> None:
        svc = GameDataService()
        received: list[SnapshotEnvelope] = []
        svc.snapshot_updated.connect(received.append)
        svc._credentials = GameCredentials("https://x/", "1", "h")
        svc._inflight = True
        svc._generation = 5
        svc._on_fetch_done(
            {
                "generation": 4,
                "payload": _payload(),
                "api_snap": None,
                "snap": None,
                "err": None,
                "api_detail": "API ok",
            }
        )
        self.assertEqual(received, [])
        self.assertTrue(svc._inflight)

    def test_successful_fetch_publishes_version(self) -> None:
        svc = GameDataService()
        received: list[SnapshotEnvelope] = []
        svc.snapshot_updated.connect(received.append)
        svc._credentials = GameCredentials("https://x/", "1", "h")
        svc._inflight = True
        svc._generation = 1
        svc._pending_force = {"advisor"}
        svc._on_fetch_done(
            {
                "generation": 1,
                "payload": _payload(),
                "api_snap": None,
                "snap": None,
                "err": None,
                "api_detail": "API ok",
                "credentials": svc._credentials,
            }
        )
        self.assertFalse(svc._inflight)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].version, 1)
        self.assertIn("advisor", received[0].force_consumers)
        self.assertIsNotNone(received[0].advice_fp)


if __name__ == "__main__":
    unittest.main()
