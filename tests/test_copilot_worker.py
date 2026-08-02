"""Tests for Co-Pilot worker guard messaging."""

from __future__ import annotations

import queue
import unittest
from unittest.mock import patch

from ic_automation.copilot_settings import CopilotKeySettings
from ic_automation.copilot_worker import CopilotWorker


class CopilotWorkerGuardTests(unittest.TestCase):
    def test_guard_reports_focus_reason(self) -> None:
        worker = CopilotWorker(CopilotKeySettings(), queue.Queue())
        settings = CopilotKeySettings(
            send_keys_enabled=False,
            exclude_hwnd=123,
            pause_when_app_focused=True,
        )
        status: queue.Queue = queue.Queue()
        worker._status_queue = status

        with patch("ic_automation.copilot_worker.win_input.foreground_is_hwnd", return_value=True):
            reason = worker._guards_ok(settings)
        self.assertEqual(reason, "helper-app heeft focus")

    def test_guard_skipped_when_send_keys_enabled(self) -> None:
        worker = CopilotWorker(CopilotKeySettings(), queue.Queue())
        settings = CopilotKeySettings(
            send_keys_enabled=True,
            exclude_hwnd=123,
            pause_when_app_focused=True,
            hover_gate=True,
        )
        with patch("ic_automation.copilot_worker.win_input.foreground_is_hwnd", return_value=True):
            self.assertIsNone(worker._guards_ok(settings))

    def test_guard_allows_when_helper_focus_allowed(self) -> None:
        worker = CopilotWorker(CopilotKeySettings(), queue.Queue())
        settings = CopilotKeySettings(
            send_keys_enabled=True,
            pause_when_app_focused=False,
            hover_gate=False,
        )
        with patch("ic_automation.copilot_worker.win_input.foreground_is_hwnd", return_value=True):
            self.assertIsNone(worker._guards_ok(settings))


if __name__ == "__main__":
    unittest.main()
