"""Incremental reader for webRequestLog.txt."""

from __future__ import annotations

from pathlib import Path

from ic_gamedata.log_parser import GameSnapshot, parse_web_request_log, read_latest_snapshot


class WebRequestLogTailer:
    """Poll a growing log file and emit new snapshots."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._offset = 0
        self._carry = ""

    def bootstrap(self) -> GameSnapshot | None:
        """Load latest snapshot and mark file as fully read."""
        snap = read_latest_snapshot(self.path)
        try:
            self._offset = self.path.stat().st_size
        except OSError:
            self._offset = 0
        self._carry = ""
        return snap

    def poll(self) -> GameSnapshot | None:
        """Read appended bytes since last poll; return newest snapshot if any."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return None

        if size < self._offset:
            self._offset = 0
            self._carry = ""

        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
                self._offset = handle.tell()
        except OSError:
            return None

        if not chunk:
            return None

        text = self._carry + chunk
        snapshots = parse_web_request_log(text)
        if not snapshots:
            # Keep trailing partial block for next poll.
            split_idx = text.rfind("\n\n")
            self._carry = text[split_idx + 2 :] if split_idx >= 0 else text
            if len(self._carry) > 512_000:
                self._carry = self._carry[-256_000:]
            return None

        self._carry = ""
        return snapshots[-1]
