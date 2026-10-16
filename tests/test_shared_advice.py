"""Tests for coalesced shared advice analysis."""

from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication

from ic_ui.workers.shared_advice import (
    AdviceAnalysisHub,
    SharedAdviceResult,
    reset_shared_advice_hub_for_tests,
    shared_advice_hub,
)


class SharedAdviceHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        reset_shared_advice_hub_for_tests()

    def tearDown(self) -> None:
        reset_shared_advice_hub_for_tests()

    def test_coalesces_same_job_to_one_run(self) -> None:
        hub = AdviceAnalysisHub()
        payload = {"details": {}}
        started: list[object] = []
        done_a: list[SharedAdviceResult] = []
        done_b: list[SharedAdviceResult] = []

        with mock.patch("ic_ui.workers.shared_advice.QThreadPool") as pool_cls:
            pool_cls.globalInstance.return_value.start.side_effect = started.append
            hub.submit(
                goal="bud",
                context="campaign",
                payload=payload,
                err=None,
                advice_fp=(1,),
                on_done=done_a.append,
                on_error=lambda _m: None,
            )
            hub.submit(
                goal="bud",
                context="campaign",
                payload=payload,
                err=None,
                advice_fp=(1,),
                on_done=done_b.append,
                on_error=lambda _m: None,
            )

        self.assertEqual(len(started), 1)
        result = SharedAdviceResult(
            payload=payload,
            report=object(),
            pending=(),
            err=None,
            goal="bud",
            context="campaign",
        )
        hub._on_done(result)
        self.assertEqual(len(done_a), 1)
        self.assertEqual(len(done_b), 1)
        self.assertIs(done_a[0], result)
        self.assertIs(done_b[0], result)

    def test_different_fingerprint_queues_next_job(self) -> None:
        hub = AdviceAnalysisHub()
        payload = {"details": {}}
        started: list[object] = []
        done: list[SharedAdviceResult] = []

        with mock.patch("ic_ui.workers.shared_advice.QThreadPool") as pool_cls:
            pool_cls.globalInstance.return_value.start.side_effect = started.append
            hub.submit(
                goal="bud",
                context="campaign",
                payload=payload,
                err=None,
                advice_fp=(1,),
                on_done=done.append,
                on_error=lambda _m: None,
            )
            hub.submit(
                goal="bud",
                context="campaign",
                payload=payload,
                err=None,
                advice_fp=(2,),
                on_done=done.append,
                on_error=lambda _m: None,
            )
            self.assertEqual(len(started), 1)
            hub._on_done(
                SharedAdviceResult(
                    payload=payload,
                    report=object(),
                    pending=(),
                    err=None,
                    goal="bud",
                    context="campaign",
                )
            )
            self.assertEqual(len(started), 2)
            hub._on_done(
                SharedAdviceResult(
                    payload=payload,
                    report=object(),
                    pending=(),
                    err=None,
                    goal="bud",
                    context="campaign",
                )
            )

        self.assertEqual(len(done), 2)

    def test_singleton_reset(self) -> None:
        a = shared_advice_hub()
        reset_shared_advice_hub_for_tests()
        b = shared_advice_hub()
        self.assertIsNot(a, b)


if __name__ == "__main__":
    unittest.main()
