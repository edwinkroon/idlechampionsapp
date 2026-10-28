"""Background worker for GameDataService snapshot fetches."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, Signal

if TYPE_CHECKING:
    from ic_gamedata.log_tailer import WebRequestLogTailer


class ApiFetchSignals(QObject):
    done = Signal(object)


class ApiFetchRunnable(QRunnable):
    """Background getuserdetails + incremental log merge."""

    def __init__(
        self,
        credentials,
        log_path: Path | None,
        *,
        generation: int,
        signals: ApiFetchSignals,
        tailer: WebRequestLogTailer | None = None,
    ) -> None:
        super().__init__()
        self.signals = signals
        self._credentials = credentials
        self._log_path = log_path
        self._generation = generation
        self._tailer = tailer

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
                self._tailer,
            )
            # Fingerprint / quality on the worker so the UI slot stays light.
            advice_fp = None
            party_id = None
            quality = None
            if isinstance(payload, dict):
                try:
                    from ic_gamedata.advice_fingerprint import (
                        advice_fingerprint,
                        party_id_from_payload,
                    )
                    from ic_gamedata.payload_quality import assess_payload_quality

                    advice_fp = advice_fingerprint(payload)
                    party_id = party_id_from_payload(payload)
                    quality = assess_payload_quality(payload)
                except Exception:
                    advice_fp = None
                    party_id = None
                    quality = None
            self.signals.done.emit(
                {
                    "generation": self._generation,
                    "credentials": credentials,
                    "payload": payload,
                    "api_snap": api_snap,
                    "snap": snap,
                    "err": err,
                    "api_detail": api_detail,
                    "advice_fp": advice_fp,
                    "party_id": party_id,
                    "quality": quality,
                }
            )
        except Exception as exc:
            self.signals.done.emit(
                {"error": str(exc), "generation": self._generation}
            )
