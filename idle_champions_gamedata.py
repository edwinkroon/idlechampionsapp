"""Compatibility entry point for game install discovery and stats."""

from ic_gamedata import (
    GameInstallInfo,
    GameSnapshot,
    SessionStats,
    StatsTracker,
    WebRequestLogTailer,
    find_game_install,
    get_downloaded_files_dir,
    get_web_request_log_path,
    parse_web_request_log,
    read_latest_snapshot,
)

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
