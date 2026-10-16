"""Central API + log snapshot fetch for UI polling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ic_gamedata.api_client import fetch_user_details_payload
from ic_gamedata.credentials import GameCredentials, extract_credentials_from_log
from ic_gamedata.log_parser import merge_snapshots, read_latest_snapshot
from ic_gamedata.log_tailer import WebRequestLogTailer


def fetch_merged_snapshot(
    credentials: GameCredentials | None,
    log_path: Path | None,
    tailer: WebRequestLogTailer | None = None,
) -> tuple[
    GameCredentials | None,
    dict[str, Any] | None,
    Any,
    Any,
    str | None,
    str,
]:
    """
    Fetch getuserdetails and merge with log tail data.

    When ``tailer`` is provided, only appended log bytes are read (no full-file
    rescan). Scripts may pass ``tailer=None`` to fall back to a full read.

    Returns (credentials, payload, api_snap, merged_snap, api_err, api_detail).
    """
    api_snap = None
    log_snap = None
    payload = None
    err = None
    api_detail = ""

    if log_path is not None and credentials is None:
        fresh = extract_credentials_from_log(log_path)
        if fresh is not None:
            credentials = fresh

    if credentials is not None:
        payload, api_snap, err = fetch_user_details_payload(credentials)
        if err and api_snap is None:
            api_detail = err
        else:
            api_detail = "API ok"

    if tailer is not None:
        # Always advance the tail so unread growth does not pile up.
        polled = tailer.poll()
        log_snap = polled or tailer.last_snapshot
    elif log_path is not None:
        log_snap = read_latest_snapshot(log_path)

    snap = merge_snapshots(api_snap, log_snap)
    if snap is not None:
        if api_snap is not None and log_snap is not None:
            api_detail = "API + log"
        elif log_snap is not None and api_snap is None:
            api_detail = "log (API unavailable)"

    return credentials, payload, api_snap, snap, err, api_detail
