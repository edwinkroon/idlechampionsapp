"""UI-facing controller around the automation worker thread."""

from __future__ import annotations

import queue
from collections.abc import Callable

from ic_automation.settings import AutomationSettings
from ic_automation.worker import AutomationWorker, StatusEvent


class AutomationController:
    def __init__(self, *, status_queue_size: int = 64) -> None:
        self._status_queue: queue.Queue[StatusEvent] = queue.Queue(maxsize=status_queue_size)
        self._worker: AutomationWorker | None = None
        self._settings = AutomationSettings()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def settings(self) -> AutomationSettings:
        return self._settings

    def start(self, settings: AutomationSettings) -> None:
        self.stop()
        self._settings = settings
        self._worker = AutomationWorker(settings, self._status_queue)
        self._running = True
        self._worker.start()
        self._status_queue.put_nowait(StatusEvent(text="Status: actief (worker)"))

    def stop(self) -> None:
        self._running = False
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.stop()
        # Drain stale status events
        while True:
            try:
                self._status_queue.get_nowait()
            except queue.Empty:
                break

    def update_settings(self, settings: AutomationSettings) -> None:
        self._settings = settings
        if self._worker is not None and self._running:
            self._worker.update_settings(settings)

    def poll_status(self) -> StatusEvent | None:
        """Return the newest status event, discarding older ones."""
        latest: StatusEvent | None = None
        while True:
            try:
                latest = self._status_queue.get_nowait()
            except queue.Empty:
                break
        return latest

    def drain_status(self, callback: Callable[[StatusEvent], None]) -> int:
        count = 0
        while True:
            try:
                event = self._status_queue.get_nowait()
            except queue.Empty:
                break
            callback(event)
            count += 1
        return count
