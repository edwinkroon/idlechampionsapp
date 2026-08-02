"""Tests for API retry policy and MemoryService."""

from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtCore import QCoreApplication

from ic_gamedata.api_client import _is_retryable_error, fetch_user_details_payload
from ic_gamedata.credentials import GameCredentials
from ic_core.memory_service import MemoryReading, MemoryService


class ApiRetryTests(unittest.TestCase):
    def test_retryable_classification(self) -> None:
        self.assertTrue(_is_retryable_error("API timeout"))
        self.assertTrue(_is_retryable_error("API netwerkfout: timed out"))
        self.assertTrue(_is_retryable_error("API HTTP 503: Unavailable"))
        self.assertTrue(_is_retryable_error("API HTTP 429: Too Many Requests"))
        self.assertFalse(_is_retryable_error("API: success=false (credentials verlopen? Herstart het spel)"))
        self.assertFalse(_is_retryable_error("API: ongeldige JSON"))
        self.assertFalse(_is_retryable_error("API HTTP 401: Unauthorized"))

    def test_retries_transient_then_succeeds(self) -> None:
        creds = GameCredentials("https://x/", "1", "h")
        calls = {"n": 0}

        def _once(_creds, *, timeout_sec: float):
            calls["n"] += 1
            if calls["n"] < 3:
                return None, None, "API timeout"
            return {"success": True}, object(), None

        with mock.patch("ic_gamedata.api_client._fetch_user_details_once", side_effect=_once):
            with mock.patch("ic_gamedata.api_client.time.sleep") as sleep:
                payload, snap, err = fetch_user_details_payload(
                    creds, timeout_sec=1.0, retries=2, backoff_sec=0.5
                )
        self.assertEqual(calls["n"], 3)
        self.assertIsNotNone(payload)
        self.assertIsNone(err)
        self.assertEqual(sleep.call_count, 2)

    def test_does_not_retry_auth_failure(self) -> None:
        creds = GameCredentials("https://x/", "1", "h")

        def _once(_creds, *, timeout_sec: float):
            return None, None, "API: success=false (credentials verlopen? Herstart het spel)"

        with mock.patch("ic_gamedata.api_client._fetch_user_details_once", side_effect=_once):
            with mock.patch("ic_gamedata.api_client.time.sleep") as sleep:
                payload, snap, err = fetch_user_details_payload(creds, retries=3)
        self.assertIsNone(payload)
        self.assertIn("success=false", err or "")
        sleep.assert_not_called()


class MemoryServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_start_stop_lifecycle(self) -> None:
        svc = MemoryService()
        self.assertFalse(svc.active)
        with mock.patch.object(svc, "_start_read"):
            svc.start()
            self.assertTrue(svc.active)
            self.assertTrue(svc._timer.isActive())
            svc.stop()
        self.assertFalse(svc.active)
        self.assertFalse(svc._timer.isActive())


if __name__ == "__main__":
    unittest.main()
