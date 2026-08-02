"""UI-facing controller for Co-Pilot key worker."""

from __future__ import annotations

import queue

from ic_automation.copilot_settings import CopilotKeySettings
from ic_automation.copilot_worker import CopilotStatusEvent, CopilotWorker
from ic_gamedata.gem_farm.models import GemFarmSnapshot


class CopilotController:
    def __init__(self, *, status_queue_size: int = 32) -> None:
        self._status_queue: queue.Queue[CopilotStatusEvent] = queue.Queue(maxsize=status_queue_size)
        self._worker: CopilotWorker | None = None
        self._settings = CopilotKeySettings()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def settings(self) -> CopilotKeySettings:
        return self._settings

    def start(self, settings: CopilotKeySettings | None = None) -> None:
        if settings is not None:
            self._settings = settings
        if self._worker is None or not self._running:
            self._worker = CopilotWorker(self._settings, self._status_queue)
            self._worker.start()
            self._running = True
        else:
            self._worker.update_settings(self._settings)

    def stop(self) -> None:
        worker = self._worker
        self._worker = None
        self._running = False
        if worker is not None:
            worker.stop()
        while True:
            try:
                self._status_queue.get_nowait()
            except queue.Empty:
                break

    def update_settings(self, settings: CopilotKeySettings) -> None:
        self._settings = settings
        if self._worker is not None and self._running:
            self._worker.update_settings(settings)

    def notify_snapshot(self, snapshot: GemFarmSnapshot | None) -> None:
        if self._worker is None:
            self.start(self._settings)
        if self._worker is not None:
            self._worker.update_snapshot(snapshot)

    def poll_status(self) -> CopilotStatusEvent | None:
        latest: CopilotStatusEvent | None = None
        while True:
            try:
                latest = self._status_queue.get_nowait()
            except queue.Empty:
                break
        return latest
