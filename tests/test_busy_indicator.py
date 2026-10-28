"""BusySpinner / BusyScope / StatusBusyRow smoke tests."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QPushButton

from ic_ui.widgets.busy_indicator import BusyScope, BusySpinner, StatusBusyRow


class BusyIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_spinner_start_stop(self) -> None:
        spinner = BusySpinner(size=16)
        self.assertFalse(spinner.is_spinning)
        spinner.start()
        self.assertTrue(spinner.isVisible())
        self.assertTrue(spinner.is_spinning)
        spinner.stop()
        self.assertFalse(spinner.isVisible())
        self.assertFalse(spinner.is_spinning)

    def test_status_busy_row(self) -> None:
        row = StatusBusyRow()
        row.setText("idle")
        self.assertEqual(row.text(), "idle")
        row.set_busy(True, message="working")
        self.assertEqual(row.text(), "working")
        self.assertTrue(row.spinner.is_spinning)
        row.set_busy(False)
        self.assertFalse(row.spinner.is_spinning)

    def test_busy_scope_disables_buttons(self) -> None:
        btn = QPushButton("Copy")
        status = StatusBusyRow()
        scope = BusyScope(
            buttons=(btn,),
            status=status,
            busy_texts={btn: "Bezig…"},
        )
        scope.begin("Building…")
        self.assertTrue(scope.active)
        self.assertFalse(btn.isEnabled())
        self.assertEqual(btn.text(), "Bezig…")
        self.assertEqual(status.text(), "Building…")
        self.assertTrue(status.spinner.is_spinning)
        scope.end(message="done")
        self.assertFalse(scope.active)
        self.assertTrue(btn.isEnabled())
        self.assertEqual(btn.text(), "Copy")
        self.assertEqual(status.text(), "done")
        self.assertFalse(status.spinner.is_spinning)


if __name__ == "__main__":
    unittest.main()
