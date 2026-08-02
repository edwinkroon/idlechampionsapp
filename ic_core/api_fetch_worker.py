"""Background worker for GameDataService snapshot fetches."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal


class ApiFetchSignals(QObject):
    done = Signal(object)


class ApiFetchRunnable(QRunnable):
    """Background getuserdetails + log merge (no shared log tailer)."""

    def __init__(
        self,
        credentials,
        log_path: Path | None,
        *,
        generation: int,
        signals: ApiFetchSignals,
    ) -> None:
        super().__init__()
        self.signals = signals
        self._credentials = credentials
        self._log_path = log_path
        self._generation = generation

    def run(self) -> None:
        try:
            from ic_gamedata.snapshot_fetch import fetch_merged_snapshot
        except ImportError as exc:
            self.signals.done.emit(
                {"error": f"Importfout: {exc}", "generation": self._generation}
            )
            return
        try:
            credentials, payload, api_snap, snap, err, api_detail = fetch_merged_snapshot(
                self._credentials,
                self._log_path,
                None,
            )
            self.signals.done.emit(
                {
                    "generation": self._generation,
                    "credentials": credentials,
                    "payload": payload,
                    "api_snap": api_snap,
                    "snap": snap,
                    "err": err,
                    "api_detail": api_detail,
                }
            )
        except Exception as exc:
            self.signals.done.emit(
                {"error": str(exc), "generation": self._generation}
            )
