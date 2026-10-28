"""Pasteable UI diagnose report."""

from __future__ import annotations

import unittest

from ic_ui.ui_action_log import (
    clear_ui_actions,
    format_diagnose_clipboard,
    last_action,
    note_ui_action,
    recent_actions,
)


class UiActionLogTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_ui_actions()

    def tearDown(self) -> None:
        clear_ui_actions()

    def test_note_and_recent(self) -> None:
        note_ui_action("Tab → Advies")
        note_ui_action("Advies: Kopieer partijsetup")
        self.assertEqual(len(recent_actions()), 2)
        self.assertIsNotNone(last_action())
        self.assertIn("Kopieer partijsetup", last_action().message)

    def test_format_contains_paste_hint(self) -> None:
        note_ui_action("Refresh all (F5)")
        text = format_diagnose_clipboard(
            active_tab="Coach",
            extra_lines=("API fetch bezig: nee",),
        )
        self.assertIn("Plak dit in de Cursor-chat", text)
        self.assertIn("Actieve tab: Coach", text)
        self.assertIn("Refresh all (F5)", text)
        self.assertIn("API fetch bezig: nee", text)


if __name__ == "__main__":
    unittest.main()
