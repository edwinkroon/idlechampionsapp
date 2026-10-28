"""Background CallableJob delivers results without touching Qt widgets."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from ic_ui.workers.callable_job import CallableJob


class CallableJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_run_emits_return_value(self) -> None:
        seen: list[object] = []
        errors: list[str] = []
        worker = CallableJob(lambda: {"ok": True, "n": 3})
        worker.signals.done.connect(seen.append)
        worker.signals.error.connect(errors.append)
        worker.run()
        self.assertEqual(errors, [])
        self.assertEqual(seen, [{"ok": True, "n": 3}])

    def test_run_emits_error_message(self) -> None:
        seen: list[object] = []
        errors: list[str] = []

        def work() -> None:
            raise RuntimeError("boom")

        worker = CallableJob(work)
        worker.signals.done.connect(seen.append)
        worker.signals.error.connect(errors.append)
        worker.run()
        self.assertEqual(seen, [])
        self.assertTrue(errors)
        self.assertIn("boom", errors[0])

    def test_advice_request_job_helper_is_pure(self) -> None:
        """Import path for the pure export builder (no widgets)."""
        from ic_ui.widgets.advice_inline_export import _AdviceRequestJobResult
        from ic_ui.widgets.advice_inline_export import _build_advice_request_job

        result = _build_advice_request_job(
            payload={},
            formation=(),
            snapshot_id="snap",
            snapshot_meta={"snapshot_id": "snap"},
            goal_id="push",
            context="campaign",
            fixed_dps=None,
            goal_parameters={},
            include_swap=False,
            max_swaps=1,
            research_mode="provided_only",
        )
        self.assertIsInstance(result, _AdviceRequestJobResult)
        # Must complete without raising (ok or structured failure).
        self.assertIsInstance(result.ok, bool)
        self.assertIsInstance(result.message, str)


if __name__ == "__main__":
    unittest.main()
