"""Fetch merged game snapshots from log + API on a worker thread."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal


class ApiFetchSignals(QObject):
    done = Signal(object)


class ApiFetchRunnable(QRunnable):
    def __init__(self, credentials, log_path: Path | None, tailer) -> None:
        super().__init__()
        self.signals = ApiFetchSignals()
        self._credentials = credentials
        self._log_path = log_path
        self._tailer = tailer

    def run(self) -> None:
        try:
            from ic_gamedata.snapshot_fetch import fetch_merged_snapshot
        except ImportError as exc:
            self.signals.done.emit({"error": f"Importfout: {exc}"})
            return
        try:
            credentials, payload, api_snap, snap, err, api_detail = fetch_merged_snapshot(
                self._credentials,
                self._log_path,
                self._tailer,
            )
            self.signals.done.emit(
                {
                    "credentials": credentials,
                    "payload": payload,
                    "api_snap": api_snap,
                    "snap": snap,
                    "err": err,
                    "api_detail": api_detail,
                }
            )
        except Exception as exc:
            self.signals.done.emit({"error": str(exc)})
