"""Tests for incremental log ingest (tailer, relevant-call filter, merge)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ic_gamedata.credentials import GameCredentials
from ic_gamedata.log_activity import (
    chunk_has_relevant_api_calls,
    new_log_bytes_are_relevant,
)
from ic_gamedata.log_tailer import WebRequestLogTailer
from ic_gamedata.snapshot_fetch import fetch_merged_snapshot
from ic_core.game_data_service import GameDataService, _looks_like_auth_failure
from PySide6.QtCore import QCoreApplication

_BLOCK = (
    "*" * 50
    + "\nhttps://pslt3.idlechampions.com/~idledragons/post.php?call=getuserdetails&user_id=1\n"
    + '{"success":true,"details":{"current_area":10,"current_adventure_id":14,'
    + '"stats":{"this_reset_gems_earned":"1"}}}\n'
)


class LogActivityTests(unittest.TestCase):
    def test_chunk_detects_getuserdetails(self) -> None:
        self.assertTrue(chunk_has_relevant_api_calls("?call=getuserdetails&x=1"))
        self.assertTrue(chunk_has_relevant_api_calls("?call=initializemobilesession&x=1"))
        self.assertFalse(chunk_has_relevant_api_calls("?call=opengenericchest&x=1"))
        self.assertFalse(chunk_has_relevant_api_calls(""))

    def test_new_bytes_peek(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "webRequestLog.txt"
            path.write_bytes(b"aaaa")
            path.write_bytes(b"aaaa?call=opengenericchest&z=1")
            self.assertFalse(new_log_bytes_are_relevant(path, 4, path.stat().st_size))
            path.write_bytes(b"aaaa?call=getuserdetails&z=1")
            self.assertTrue(new_log_bytes_are_relevant(path, 4, path.stat().st_size))
            self.assertTrue(new_log_bytes_are_relevant(path, 99, 10))  # truncation


class LogTailerTests(unittest.TestCase):
    def test_poll_reads_only_appended_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "webRequestLog.txt"
            path.write_text(_BLOCK, encoding="utf-8")
            tailer = WebRequestLogTailer(path)
            first = tailer.bootstrap()
            self.assertIsNotNone(first)
            self.assertIs(tailer.last_snapshot, first)

            with mock.patch(
                "ic_gamedata.log_tailer.read_latest_snapshot",
                side_effect=AssertionError("full re-read after bootstrap"),
            ):
                self.assertIsNone(tailer.poll())
                path.write_text(
                    path.read_text(encoding="utf-8")
                    + _BLOCK.replace('"current_area":10', '"current_area":20'),
                    encoding="utf-8",
                )
                second = tailer.poll()
            self.assertIsNotNone(second)
            assert second is not None
            self.assertEqual(second.current_area, 20)


class SnapshotFetchTailerTests(unittest.TestCase):
    def test_with_tailer_skips_full_log_reread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "webRequestLog.txt"
            path.write_text(_BLOCK, encoding="utf-8")
            tailer = WebRequestLogTailer(path)
            tailer.bootstrap()
            creds = GameCredentials("https://x/", "1", "h")
            with (
                mock.patch(
                    "ic_gamedata.snapshot_fetch.fetch_user_details_payload",
                    return_value=({"success": True}, None, None),
                ),
                mock.patch(
                    "ic_gamedata.snapshot_fetch.read_latest_snapshot",
                    side_effect=AssertionError("must not full-read when tailer is set"),
                ),
            ):
                out_creds, payload, _api, snap, err, detail = fetch_merged_snapshot(
                    creds, path, tailer
                )
            self.assertIs(out_creds, creds)
            self.assertIsNotNone(payload)
            self.assertIsNone(err)
            self.assertIn("API", detail)
            self.assertIsNotNone(snap)


class AuthFailureRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_auth_failure_helper(self) -> None:
        self.assertTrue(_looks_like_auth_failure("API: success=false (credentials expired?)"))
        self.assertFalse(_looks_like_auth_failure("timeout"))

    def test_fetch_done_clears_cred_cache_on_auth_error(self) -> None:
        svc = GameDataService()
        svc._credentials = GameCredentials("https://x/", "1", "old")
        svc._inflight = True
        svc._generation = 1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "webRequestLog.txt"
            path.write_text("stub", encoding="utf-8")
            svc.configure(log_path=path, credentials=svc._credentials)
            fresh = GameCredentials("https://x/", "1", "newkey")
            with mock.patch(
                "ic_gamedata.credential_cache.extract_credentials_from_log",
                return_value=fresh,
            ):
                svc._on_fetch_done(
                    {
                        "generation": 1,
                        "payload": None,
                        "api_snap": None,
                        "snap": None,
                        "err": "API: success=false (credentials expired? Restart the game)",
                        "api_detail": "fail",
                    }
                )
            self.assertEqual(svc.credentials.hash, "newkey")


if __name__ == "__main__":
    unittest.main()
