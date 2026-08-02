"""Compatibility entry point for game install discovery and stats."""

from ic_gamedata import (
    GameInstallInfo,
    SessionStats,
    StatsTracker,
    WebRequestLogTailer,
    find_game_install,
    get_downloaded_files_dir,
    get_web_request_log_path,
    parse_web_request_log,
    read_latest_snapshot,
)
from ic_gamedata.log_parser import GameSnapshot

__all__ = [
    "GameInstallInfo",
    "GameSnapshot",
    "SessionStats",
    "StatsTracker",
    "WebRequestLogTailer",
    "find_game_install",
    "get_downloaded_files_dir",
    "get_web_request_log_path",
    "parse_web_request_log",
    "read_latest_snapshot",
]
