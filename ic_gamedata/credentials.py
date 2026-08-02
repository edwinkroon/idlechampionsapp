"""Extract game API credentials from webRequestLog.txt."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from ic_gamedata.log_parser import _BLOCK_SPLIT

_PARAM_RE = re.compile(
    r"[?&](user_id|hash|instance_key|network_id|mobile_client_version)=([^&\s]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GameCredentials:
    play_server: str
    user_id: str
    hash: str
    instance_key: int | None = None
    network_id: str = "21"
    mobile_client_version: str = "650"


def _parse_url_params(url_line: str) -> dict[str, str]:
    return {key: unquote(value) for key, value in _PARAM_RE.findall(url_line)}


def _parse_instance_key(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def credentials_from_block(url_line: str, payload: dict[str, Any]) -> GameCredentials | None:
    """Build credentials from one log block (URL + JSON response)."""
    params = _parse_url_params(url_line)
    user_id = params.get("user_id") or payload.get("internal_user_id")
    if user_id is not None:
        user_id = str(user_id)
    hash_val = params.get("hash") or payload.get("hash")
    if hash_val is not None:
        hash_val = str(hash_val)

    if not user_id or user_id == "0" or not hash_val:
        return None

    play_server = payload.get("play_server")
    if not play_server or not isinstance(play_server, str):
        return None

    instance_key = _parse_instance_key(params.get("instance_key"))
    if instance_key is None:
        instance_key = _parse_instance_key(payload.get("instance_key"))

    return GameCredentials(
        play_server=play_server,
        user_id=user_id,
        hash=hash_val,
        instance_key=instance_key,
        network_id=params.get("network_id") or "21",
        mobile_client_version=params.get("mobile_client_version") or "650",
    )


def extract_credentials_from_log(path: Path) -> GameCredentials | None:
    """Return the most recent usable credentials found in the log."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    latest: GameCredentials | None = None
    for block in _BLOCK_SPLIT.split(text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if not lines:
            continue
        body = "\n".join(lines[1:]).strip()
        if not body.startswith("{"):
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        creds = credentials_from_block(lines[0], payload)
        if creds is not None:
            latest = creds
    return latest
