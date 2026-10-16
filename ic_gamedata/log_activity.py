"""Detect whether new webRequestLog bytes warrant an API poll."""

from __future__ import annotations

from pathlib import Path

from ic_gamedata.log_parser import _CALL_RE

# Calls that carry party/progress state or fresh auth material.
RELEVANT_LOG_CALLS = frozenset(
    {
        "getuserdetails",
        "initializemobilesession",
        "loginuser",
        "login",
    }
)


def chunk_has_relevant_api_calls(text: str) -> bool:
    """True when ``text`` mentions a relevant ``call=`` parameter."""
    if not text:
        return False
    for match in _CALL_RE.finditer(text):
        if match.group(1).casefold() in RELEVANT_LOG_CALLS:
            return True
    return False


def new_log_bytes_are_relevant(path: Path, start: int, end: int) -> bool:
    """Peek ``[start, end)`` of ``path`` for relevant API calls.

    Returns True (allow poll) when the range is empty/invalid, the file was
    truncated/rotated, or a relevant ``call=`` appears in the new bytes.
    """
    if end < start:
        # Truncation / rotation — force a poll so credentials/tailer reset.
        return True
    if end == start:
        return False
    try:
        with path.open("rb") as handle:
            handle.seek(start)
            raw = handle.read(end - start)
    except OSError:
        return True
    if not raw:
        return False
    text = raw.decode("utf-8", errors="replace")
    return chunk_has_relevant_api_calls(text)
