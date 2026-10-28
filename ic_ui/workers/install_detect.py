"""Background game-install + credentials detection (no Qt widgets)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal


@dataclass(frozen=True)
class InstallDetectResult:
    """Outcome of ``find_game_install`` + log credential/bootstrap work."""

    info: Any  # GameInstallInfo | None
    credentials: Any  # GameCredentials | None
    bootstrap_snap: Any = None  # GameSnapshot | None
    log_byte_size: int = 0
    error: str | None = None


class InstallDetectSignals(QObject):
    done = Signal(object)  # InstallDetectResult
    error = Signal(str)


class InstallDetectRunnable(QRunnable):
    """Resolve install path, credentials, and an optional log bootstrap snapshot."""

    def __init__(self, *, signals_parent: QObject | None = None) -> None:
        super().__init__()
        self.signals = InstallDetectSignals(signals_parent)
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = detect_install_and_credentials()
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.done.emit(result)


def detect_install_and_credentials() -> InstallDetectResult:
    """Heavy I/O for startup / Search again — safe to call off the UI thread."""
    try:
        from ic_gamedata.paths import find_game_install
    except ImportError as exc:
        return InstallDetectResult(info=None, credentials=None, error=str(exc))

    info = find_game_install()
    if info is None:
        return InstallDetectResult(info=None, credentials=None)
    if info.web_request_log is None:
        return InstallDetectResult(info=info, credentials=None)

    log_path = Path(info.web_request_log)
    try:
        from ic_gamedata.credentials import extract_credentials_from_log
        from ic_gamedata.log_parser import read_latest_snapshot
    except ImportError:
        try:
            from ic_gamedata import extract_credentials_from_log, read_latest_snapshot
        except ImportError as exc:
            return InstallDetectResult(info=info, credentials=None, error=str(exc))

    credentials = extract_credentials_from_log(log_path)
    snap = None
    size = 0
    try:
        snap = read_latest_snapshot(log_path)
        size = int(log_path.stat().st_size)
    except OSError:
        snap = None
        size = 0
    return InstallDetectResult(
        info=info,
        credentials=credentials,
        bootstrap_snap=snap,
        log_byte_size=size,
    )
