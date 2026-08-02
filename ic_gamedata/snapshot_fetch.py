"""Central API + log snapshot fetch for UI polling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ic_gamedata.api_client import fetch_user_details_payload
from ic_gamedata.credentials import GameCredentials, extract_credentials_from_log
from ic_gamedata.log_parser import merge_snapshots, read_latest_snapshot


def fetch_merged_snapshot(
    credentials: GameCredentials | None,
    log_path: Path | None,
    tailer=None,
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

    Returns (credentials, payload, api_snap, merged_snap, api_err, api_detail).
    """
    api_snap = None
    log_snap = None
    payload = None
    err = None
    api_detail = ""

    if log_path is not None:
        fresh = extract_credentials_from_log(log_path)
        if fresh is not None:
            credentials = fresh

    if credentials is not None:
        payload, api_snap, err = fetch_user_details_payload(credentials)
        if err and api_snap is None:
            api_detail = err
        else:
            api_detail = "API ok"

    log_sources = []
    if tailer is not None:
        polled = tailer.poll()
        if polled is not None:
            log_sources.append(polled)
    if log_path is not None:
        latest = read_latest_snapshot(log_path)
        if latest is not None:
            log_sources.append(latest)

    if log_sources:
        log_snap = merge_snapshots(*log_sources)

    snap = merge_snapshots(api_snap, log_snap)
    if snap is not None:
        if api_snap is not None and log_snap is not None:
            api_detail = "API + log"
        elif log_snap is not None and api_snap is None:
            api_detail = "log (API niet beschikbaar)"

    return credentials, payload, api_snap, snap, err, api_detail
