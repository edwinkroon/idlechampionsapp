"""Tests for automation worker / controller (no real SendInput)."""

from __future__ import annotations

import queue
import time
import unittest
from unittest.mock import patch

from ic_automation import AutomationController, AutomationSettings
from ic_automation.worker import AutomationWorker, StatusEvent


class AutomationSettingsTests(unittest.TestCase):
    def test_with_updates_is_immutable(self) -> None:
        base = AutomationSettings(enable_level=True, level_interval_sec=5)
        updated = base.with_updates(level_interval_sec=10, enable_auto_click=True)
        self.assertEqual(base.level_interval_sec, 5)
        self.assertFalse(base.enable_auto_click)
        self.assertEqual(updated.level_interval_sec, 10)
        self.assertTrue(updated.enable_auto_click)


class AutomationControllerTests(unittest.TestCase):
    def test_start_stop_without_tk(self) -> None:
        controller = AutomationController()
        settings = AutomationSettings(
            enable_level=False,
            enable_grave=False,
            enable_abilities=False,
            enable_auto_progress=False,
            enable_auto_click=False,
        )
        with patch("ic_automation.worker.win_input.caps_lock_on", return_value=False):
            with patch("ic_automation.worker.win_input.ctrl_held", return_value=False):
                controller.start(settings)
                self.assertTrue(controller.running)
                time.sleep(0.15)
                controller.update_settings(settings.with_updates(enable_level=True, level_champions=(1,)))
                time.sleep(0.1)
                controller.stop()
        self.assertFalse(controller.running)

    def test_poll_status_keeps_latest(self) -> None:
        controller = AutomationController()
        controller._status_queue.put_nowait(StatusEvent("a"))
        controller._status_queue.put_nowait(StatusEvent("b"))
        event = controller.poll_status()
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.text, "b")


class AutomationWorkerTests(unittest.TestCase):
    def test_auto_click_calls_input_helper(self) -> None:
        q: queue.Queue[StatusEvent] = queue.Queue()
        settings = AutomationSettings(
            enable_auto_click=True,
            auto_click_cps=20,
            hover_gate=True,
            window_title="Idle Champions",
            pause_on_ctrl=True,
            pause_when_over_app=True,
        )
        worker = AutomationWorker(settings, q, tick_sec=0.02)
        with (
            patch("ic_automation.worker.win_input.caps_lock_on", return_value=False),
            patch("ic_automation.worker.win_input.ctrl_held", return_value=False),
            patch("ic_automation.worker.win_input.cursor_over_hwnd", return_value=False),
            patch("ic_automation.worker.win_input.foreground_is_hwnd", return_value=False),
            patch("ic_automation.worker.win_input.cursor_over_game", return_value=True) as over,
            patch("ic_automation.worker.win_input.send_left_click_at_cursor") as click,
            patch("ic_automation.worker.win_input.find_and_activate_window", return_value=False),
        ):
            worker.start()
            time.sleep(0.25)
            worker.stop()
        self.assertGreaterEqual(click.call_count, 1)
        self.assertGreaterEqual(over.call_count, 1)

    def test_ctrl_pauses_auto_click(self) -> None:
        q: queue.Queue[StatusEvent] = queue.Queue()
        settings = AutomationSettings(enable_auto_click=True, auto_click_cps=20)
        worker = AutomationWorker(settings, q, tick_sec=0.02)
        with (
            patch("ic_automation.worker.win_input.caps_lock_on", return_value=False),
            patch("ic_automation.worker.win_input.ctrl_held", return_value=True),
            patch("ic_automation.worker.win_input.cursor_over_game", return_value=True),
            patch("ic_automation.worker.win_input.send_left_click_at_cursor") as click,
        ):
            worker.start()
            time.sleep(0.2)
            worker.stop()
        self.assertEqual(click.call_count, 0)

    def test_over_app_pauses_and_skips_focus_steal(self) -> None:
        q: queue.Queue[StatusEvent] = queue.Queue()
        settings = AutomationSettings(
            enable_level=True,
            level_interval_sec=0,
            level_champions=(1,),
            exclude_hwnd=12345,
            prefer_game_already_focused=False,
        )
        worker = AutomationWorker(settings, q, tick_sec=0.02)
        with (
            patch("ic_automation.worker.win_input.caps_lock_on", return_value=False),
            patch("ic_automation.worker.win_input.ctrl_held", return_value=False),
            patch("ic_automation.worker.win_input.cursor_over_hwnd", return_value=True),
            patch("ic_automation.worker.win_input.foreground_is_hwnd", return_value=False),
            patch("ic_automation.worker.win_input.cursor_over_game", return_value=True),
            patch("ic_automation.worker.win_input.find_and_activate_window") as activate,
            patch("ic_automation.worker.win_input.do_level_cycle") as level,
        ):
            worker.start()
            time.sleep(0.25)
            worker.stop()
        activate.assert_not_called()
        level.assert_not_called()

    def test_sends_keys_when_game_already_focused(self) -> None:
        q: queue.Queue[StatusEvent] = queue.Queue()
        settings = AutomationSettings(
            enable_level=True,
            level_interval_sec=0,
            level_champions=(12,),
            prefer_game_already_focused=True,
            hover_gate=False,
        )
        worker = AutomationWorker(settings, q, tick_sec=0.02)
        with (
            patch("ic_automation.worker.win_input.caps_lock_on", return_value=False),
            patch("ic_automation.worker.win_input.ctrl_held", return_value=False),
            patch("ic_automation.worker.win_input.cursor_over_hwnd", return_value=False),
            patch("ic_automation.worker.win_input.foreground_is_hwnd", return_value=False),
            patch("ic_automation.worker.win_input.game_is_foreground", return_value=True),
            patch("ic_automation.worker.win_input.find_and_activate_window") as activate,
            patch("ic_automation.worker.win_input.do_level_cycle") as level,
        ):
            worker.start()
            time.sleep(1.2)  # first level is delayed 1s
            worker.stop()
        activate.assert_not_called()
        self.assertGreaterEqual(level.call_count, 1)


if __name__ == "__main__":
    unittest.main()
