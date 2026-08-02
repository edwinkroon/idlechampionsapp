"""Game data discovery and stats from Idle Champions webRequestLog."""

from ic_gamedata.api_client import fetch_user_details, fetch_user_details_payload
from ic_gamedata.party_advisor import AdvisorReport, analyze_party, format_report
from ic_gamedata.credentials import GameCredentials, extract_credentials_from_log
from ic_gamedata.log_parser import GameSnapshot, PartySnapshot, merge_snapshots, parse_web_request_log, read_latest_snapshot
from ic_gamedata.paths import (
    GameInstallInfo,
    find_game_install,
    get_downloaded_files_dir,
    get_web_request_log_path,
)
from ic_gamedata.stats import PartySessionStats, SessionStats, StatsTracker
from ic_gamedata.log_tailer import WebRequestLogTailer

__all__ = [
    "GameInstallInfo",
    "PartySnapshot",
    "PartySessionStats",
    "GameCredentials",
    "extract_credentials_from_log",
    "fetch_user_details",
    "fetch_user_details_payload",
    "AdvisorReport",
    "analyze_party",
    "format_report",
    "SessionStats",
    "StatsTracker",
    "WebRequestLogTailer",
    "find_game_install",
    "get_downloaded_files_dir",
    "get_web_request_log_path",
    "parse_web_request_log",
    "merge_snapshots",
    "read_latest_snapshot",
]
