"""Generic QRunnable for pure-Python work off the UI thread.

Rule: pass only plain data into ``fn``; never touch Qt widgets from the
worker. Set busy on the UI *before* starting the job, and clear busy in the
done/error handlers.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class CallableJobSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class CallableJob(QRunnable):
    """Run ``fn()`` on the global thread pool and emit the return value."""

    def __init__(
        self,
        fn: Callable[[], Any],
        *,
        signals_parent: QObject | None = None,
    ) -> None:
        super().__init__()
        self.signals = CallableJobSignals(signals_parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.done.emit(result)


def start_callable_job(
    fn: Callable[[], Any],
    *,
    on_done: Callable[[Any], None],
    on_error: Callable[[str], None],
    signals_parent: QObject | None = None,
) -> CallableJob:
    """Start ``fn`` on the pool; keep a reference to the returned job if needed."""
    worker = CallableJob(fn, signals_parent=signals_parent)
    worker.signals.done.connect(on_done)
    worker.signals.error.connect(on_error)
    QThreadPool.globalInstance().start(worker)
    return worker
