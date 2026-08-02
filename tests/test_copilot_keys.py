"""Tests for Co-Pilot hotkey phase mapping."""

from __future__ import annotations

import unittest

from ic_gamedata.gem_farm.copilot_keys import (
    companion_auto_progress_key,
    keys_on_area_reset,
    keys_on_phase_change,
    should_send_on_area_reset,
    should_send_on_phase_change,
)


class CopilotKeyMappingTests(unittest.TestCase):
    def test_no_send_when_disabled(self) -> None:
        self.assertIsNone(
            should_send_on_phase_change(
                previous_phase="progress",
                new_phase="stacking",
                send_keys_enabled=False,
            )
        )

    def test_send_w_on_enter_stacking(self) -> None:
        self.assertEqual(
            should_send_on_phase_change(
                previous_phase="progress",
                new_phase="stacking",
                send_keys_enabled=True,
            ),
            "W",
        )

    def test_no_resend_same_phase(self) -> None:
        self.assertIsNone(
            should_send_on_phase_change(
                previous_phase="stacking",
                new_phase="stacking",
                send_keys_enabled=True,
            )
        )

    def test_send_g_on_enter_stuck(self) -> None:
        self.assertEqual(
            should_send_on_phase_change(
                previous_phase="stacking",
                new_phase="stuck",
                send_keys_enabled=True,
            ),
            "G",
        )

    def test_no_key_on_pre_reset(self) -> None:
        self.assertIsNone(
            should_send_on_phase_change(
                previous_phase="swap_ready",
                new_phase="pre_reset",
                send_keys_enabled=True,
            )
        )

    def test_send_q_after_modron_area_reset(self) -> None:
        self.assertEqual(
            should_send_on_area_reset(
                previous_area=290,
                new_area=12,
                phase="progress",
                send_keys_enabled=True,
            ),
            "Q",
        )

    def test_no_area_reset_on_small_drop(self) -> None:
        self.assertIsNone(
            should_send_on_area_reset(
                previous_area=100,
                new_area=80,
                phase="progress",
                send_keys_enabled=True,
            )
        )

    def test_stacking_sends_w_then_g(self) -> None:
        keys, ap = keys_on_phase_change(
            previous_phase="progress",
            new_phase="stacking",
            send_keys_enabled=True,
            ap_assumed_on=None,
            allow_auto_progress_g=True,
        )
        self.assertEqual(keys, ("W", "G"))
        self.assertIs(ap, False)

    def test_swap_ready_reenables_auto_progress(self) -> None:
        keys, ap = keys_on_phase_change(
            previous_phase="stacking",
            new_phase="swap_ready",
            send_keys_enabled=True,
            ap_assumed_on=False,
            allow_auto_progress_g=True,
        )
        self.assertEqual(keys, ("E", "G"))
        self.assertIs(ap, True)

    def test_progress_skips_g_when_ap_unknown(self) -> None:
        keys, ap = keys_on_phase_change(
            previous_phase="idle",
            new_phase="progress",
            send_keys_enabled=True,
            ap_assumed_on=None,
            allow_auto_progress_g=True,
        )
        self.assertEqual(keys, ("Q",))
        self.assertIsNone(ap)

    def test_companion_disabled(self) -> None:
        key, ap = companion_auto_progress_key(
            phase="stacking",
            ap_assumed_on=None,
            allow_auto_progress_g=False,
        )
        self.assertIsNone(key)
        self.assertIsNone(ap)

    def test_area_reset_reenables_g_when_ap_was_off(self) -> None:
        keys, ap = keys_on_area_reset(
            previous_area=310,
            new_area=5,
            phase="progress",
            send_keys_enabled=True,
            ap_assumed_on=False,
            allow_auto_progress_g=True,
        )
        self.assertEqual(keys, ("Q", "G"))
        self.assertIs(ap, True)


if __name__ == "__main__":
    unittest.main()
