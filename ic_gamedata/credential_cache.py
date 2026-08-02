"""Cached credential extraction — avoid full-log scans every poll."""

from __future__ import annotations

from pathlib import Path

from ic_gamedata.credentials import GameCredentials, extract_credentials_from_log


class CredentialCache:
    """Re-read webRequestLog only when mtime/size changes."""

    def __init__(self) -> None:
        self._key: tuple[int, int] | None = None
        self._creds: GameCredentials | None = None
        self._path: Path | None = None

    def clear(self) -> None:
        self._key = None
        self._creds = None
        self._path = None

    def get(self, path: Path | None) -> GameCredentials | None:
        if path is None:
            return None
        try:
            stat = path.stat()
        except OSError:
            return self._creds if self._path == path else None
        key = (stat.st_mtime_ns, stat.st_size)
        if self._path == path and self._key == key:
            return self._creds
        creds = extract_credentials_from_log(path)
        self._path = path
        self._key = key
        self._creds = creds
        return creds
