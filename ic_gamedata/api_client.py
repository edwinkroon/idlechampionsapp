"""Fetch live game state from the official Idle Champions API."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ic_gamedata.credentials import GameCredentials
from ic_gamedata.log_parser import GameSnapshot, snapshot_from_payload


def _build_getuserdetails_url(creds: GameCredentials) -> str:
    base = creds.play_server.rstrip("/") + "/post.php"
    params: dict[str, str] = {
        "call": "getuserdetails",
        "language_id": "1",
        "user_id": creds.user_id,
        "hash": creds.hash,
        "include_free_play_objectives": "true",
        "timestamp": str(int(time.time())),
        "request_id": str(random.randint(100_000_000, 999_999_999)),
        "network_id": creds.network_id,
        "mobile_client_version": creds.mobile_client_version,
        "offline_v2_build": "1",
        "egs_device": "1",
        "localization_aware": "true",
    }
    if creds.instance_key is not None:
        params["instance_key"] = str(creds.instance_key)
    return base + "?" + urllib.parse.urlencode(params)


def fetch_user_details(
    creds: GameCredentials,
    *,
    timeout_sec: float = 15.0,
) -> tuple[GameSnapshot | None, str | None]:
    """
    Call getuserdetails on the game server.

    Returns (snapshot, error_message). error_message is set on failure.
    """
    url = _build_getuserdetails_url(creds)
    request = urllib.request.Request(
        url,
        method="POST",
        headers={
            "User-Agent": "IdleChampionsApp/1.0",
            "Accept": "application/json",
        },
        data=b"",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return None, f"API HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return None, f"API netwerkfout: {exc.reason}"
    except TimeoutError:
        return None, "API timeout"

    try:
        payload: dict[str, Any] = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None, "API: ongeldige JSON"

    if not payload.get("success"):
        return None, "API: success=false (credentials verlopen? Herstart het spel)"

    snap = snapshot_from_payload(payload, api_call="getuserdetails")
    if snap is None:
        return None, "API: geen speldata in response"
    return snap, None


def fetch_user_details_payload(
    creds: GameCredentials,
    *,
    timeout_sec: float = 15.0,
) -> tuple[dict[str, Any] | None, GameSnapshot | None, str | None]:
    """
    Call getuserdetails and return (raw_payload, snapshot, error_message).
    """
    url = _build_getuserdetails_url(creds)
    request = urllib.request.Request(
        url,
        method="POST",
        headers={
            "User-Agent": "IdleChampionsApp/1.0",
            "Accept": "application/json",
        },
        data=b"",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return None, None, f"API HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return None, None, f"API netwerkfout: {exc.reason}"
    except TimeoutError:
        return None, None, "API timeout"

    try:
        payload: dict[str, Any] = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None, None, "API: ongeldige JSON"

    if not payload.get("success"):
        return None, None, "API: success=false (credentials verlopen? Herstart het spel)"

    snap = snapshot_from_payload(payload, api_call="getuserdetails")
    if snap is None:
        return payload, None, "API: geen speldata in response"
    return payload, snap, None
