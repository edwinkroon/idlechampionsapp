"""Coalesced party analysis shared by Formation / Advisor / Specs tabs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


@dataclass(frozen=True)
class SharedAdviceResult:
    payload: dict[str, Any]
    report: Any
    pending: tuple[Any, ...]
    err: str | None
    goal: str
    context: str


DoneCallback = Callable[[SharedAdviceResult], None]
ErrorCallback = Callable[[str], None]


class _SharedAdviceSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class _SharedAdviceRunnable(QRunnable):
    """One full analyze_party (+ pending specs) for all advice tabs."""

    def __init__(
        self,
        goal: str,
        context: str,
        payload: dict[str, Any],
        err: str | None,
        *,
        signals: _SharedAdviceSignals,
    ) -> None:
        super().__init__()
        self._goal = goal
        self._context = context
        self._payload = payload
        self._err = err
        self.signals = signals

    def run(self) -> None:
        try:
            from ic_gamedata.party_advisor import analyze_party
            from ic_gamedata.party_advisor_specializations import advisor_run_goal
            from ic_gamedata.specializations import (
                load_specialization_rules,
                pending_specializations,
            )
        except ImportError as exc:
            self.signals.error.emit(f"Import error: {exc}")
            return

        try:
            report = analyze_party(
                self._payload,
                goal=self._goal,
                context=self._context,
                include_specializations=True,
                include_formation=True,
            )
            rules = load_specialization_rules()
            pending = pending_specializations(
                self._payload,
                rules,
                context=self._context,
                run_goal=advisor_run_goal(self._goal, self._context),
            )
        except Exception as exc:
            self.signals.error.emit(f"Analysis error: {exc}")
            return

        self.signals.done.emit(
            SharedAdviceResult(
                payload=self._payload,
                report=report,
                pending=tuple(pending or ()),
                err=self._err,
                goal=self._goal,
                context=self._context,
            )
        )


class AdviceAnalysisHub(QObject):
    """Merge concurrent tab analyzes into a single background job.

    Formation, Party Advisor, and Specializations often refresh on the same
    snapshot. Running ``analyze_party`` three times wastes CPU; waiters with the
    same goal/context/fingerprint share one result.

    ``busy_changed`` is True while a job is in flight (including pending drain).
    Tabs should show a spinner/status; do not disable goal/context combos.
    """

    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._inflight = False
        self._key: tuple[Any, ...] | None = None
        self._waiters: list[tuple[DoneCallback, ErrorCallback]] = []
        self._pending: dict[str, Any] | None = None
        self._signals: _SharedAdviceSignals | None = None

    @property
    def busy(self) -> bool:
        return self._inflight

    @staticmethod
    def _job_key(
        goal: str,
        context: str,
        advice_fp: tuple[Any, ...] | None,
        payload: dict[str, Any],
    ) -> tuple[Any, ...]:
        try:
            from ic_gamedata.seat_advisor.role_prefs import role_prefs_stamp

            prefs_stamp = role_prefs_stamp()
        except ImportError:
            prefs_stamp = ()
        return (goal, context, advice_fp, id(payload), prefs_stamp)

    def submit(
        self,
        *,
        goal: str,
        context: str,
        payload: dict[str, Any],
        err: str | None,
        advice_fp: tuple[Any, ...] | None,
        on_done: DoneCallback,
        on_error: ErrorCallback,
    ) -> None:
        key = self._job_key(goal, context, advice_fp, payload)
        waiter = (on_done, on_error)
        if self._inflight:
            if key == self._key:
                self._waiters.append(waiter)
                return
            if self._pending is not None and self._pending["key"] == key:
                self._pending["waiters"].append(waiter)
                self._pending["err"] = err
                return
            self._pending = {
                "key": key,
                "goal": goal,
                "context": context,
                "payload": payload,
                "err": err,
                "advice_fp": advice_fp,
                "waiters": [waiter],
            }
            return
        self._launch(
            key=key,
            goal=goal,
            context=context,
            payload=payload,
            err=err,
            waiters=[waiter],
        )

    def _launch(
        self,
        *,
        key: tuple[Any, ...],
        goal: str,
        context: str,
        payload: dict[str, Any],
        err: str | None,
        waiters: list[tuple[DoneCallback, ErrorCallback]],
    ) -> None:
        was_busy = self._inflight
        self._inflight = True
        self._key = key
        self._waiters = list(waiters)
        if not was_busy:
            self.busy_changed.emit(True)
        signals = _SharedAdviceSignals(self)
        self._signals = signals
        signals.done.connect(self._on_done)
        signals.error.connect(self._on_error)
        worker = _SharedAdviceRunnable(
            goal, context, payload, err, signals=signals
        )
        QThreadPool.globalInstance().start(worker)

    def _on_done(self, result: object) -> None:
        waiters = self._waiters
        self._waiters = []
        self._inflight = False
        self._key = None
        self._signals = None
        assert isinstance(result, SharedAdviceResult)
        for on_done, _on_error in waiters:
            on_done(result)
        if self._pending is None:
            self.busy_changed.emit(False)
        self._drain_pending()

    def _on_error(self, msg: str) -> None:
        waiters = self._waiters
        self._waiters = []
        self._inflight = False
        self._key = None
        self._signals = None
        for _on_done, on_error in waiters:
            on_error(msg)
        if self._pending is None:
            self.busy_changed.emit(False)
        self._drain_pending()

    def _drain_pending(self) -> None:
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        self._launch(
            key=pending["key"],
            goal=pending["goal"],
            context=pending["context"],
            payload=pending["payload"],
            err=pending["err"],
            waiters=pending["waiters"],
        )


_HUB: AdviceAnalysisHub | None = None


def shared_advice_hub() -> AdviceAnalysisHub:
    """Process-wide hub (created lazily on the UI thread)."""
    global _HUB
    if _HUB is None:
        _HUB = AdviceAnalysisHub()
    return _HUB


def reset_shared_advice_hub_for_tests() -> None:
    """Drop the singleton between unit tests."""
    global _HUB
    _HUB = None
