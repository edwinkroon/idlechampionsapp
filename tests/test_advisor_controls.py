"""Tests for shared Goal/Context bar sync."""

from __future__ import annotations

import unittest

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar, _SHARED_SETTINGS_KEY
from ic_ui.widgets.advisor_widgets import clear_advisor_layout


class AdvisorGoalContextBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        AdvisorGoalContextBar._live.clear()
        self._settings = QSettings("IdleChampions", "Companion")
        for key in (
            f"{_SHARED_SETTINGS_KEY}/goal",
            f"{_SHARED_SETTINGS_KEY}/context",
            f"{_SHARED_SETTINGS_KEY}/goal_confirmed",
            "advisor/goal",
            "advisor/context",
            "formation/goal",
            "formation/context",
            "specializations/goal",
            "specializations/context",
        ):
            self._settings.remove(key)

    def test_bars_share_goal_and_context(self) -> None:
        a = AdvisorGoalContextBar()
        b = AdvisorGoalContextBar()
        self.addCleanup(lambda: AdvisorGoalContextBar._live.clear())

        seen: list[str] = []
        b.changed.connect(lambda: seen.append(b.goal()))

        a.set_goal_context("favor_farm")

        self.assertEqual(a.goal(), "favor_farm")
        self.assertEqual(b.goal(), "favor_farm")
        self.assertEqual(seen, ["favor_farm"])
        self.assertEqual(
            str(self._settings.value(f"{_SHARED_SETTINGS_KEY}/goal")),
            "favor_farm",
        )

    def test_migrates_legacy_advisor_pref_with_confirm(self) -> None:
        self._settings.setValue("advisor/goal", "speed")
        self._settings.setValue("advisor/context", "push")
        bar = AdvisorGoalContextBar()
        self.addCleanup(lambda: AdvisorGoalContextBar._live.clear())
        self.assertTrue(bar.needs_goal_confirm())
        self.assertIsNone(bar.goal_or_none())
        self.assertEqual(bar.context(), "push")
        # Scoring fallback must not invent gem_farm.
        self.assertEqual(bar.goal(), "push")


class ClearAdvisorLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_clear_removes_orphaned_cards_immediately(self) -> None:
        """Regression: status refreshed while champ cards stayed painted."""
        parent = QWidget()
        layout = QVBoxLayout(parent)
        old = QLabel("old party")
        layout.addWidget(old)
        parent.show()
        self._app.processEvents()

        clear_advisor_layout(layout)
        new = QLabel("new party")
        layout.addWidget(new)
        self._app.processEvents()

        labels = [w.text() for w in parent.findChildren(QLabel)]
        self.assertIn("new party", labels)
        self.assertNotIn("old party", labels)


if __name__ == "__main__":
    unittest.main()
