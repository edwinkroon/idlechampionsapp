"""Locate Idle Champions install (Epic, Steam, or manual override)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Epic Games Store catalog id for Idle Champions (fixed by Codename).
EPIC_APP_NAME = "40cb42e38c0b4a14a1bb133eb3291572"

DOWNLOADED_FILES_REL = Path("IdleDragons_Data") / "StreamingAssets" / "downloaded_files"
WEB_REQUEST_LOG_NAMES = ("webRequestLog.txt", "webrequestlog.txt")

# Next to exe / project config.
if getattr(__import__("sys"), "frozen", False):
    _CONFIG_BASE = Path(__import__("sys").executable).parent
else:
    _CONFIG_BASE = Path(__file__).resolve().parent.parent

GAMEDATA_CONFIG_PATH = _CONFIG_BASE / "config" / "gamedata.json"
GOAL_RUN_HISTORY_PATH = _CONFIG_BASE / "config" / "goal_run_history.json"
OWNED_ROSTER_CACHE_PATH = _CONFIG_BASE / "config" / "owned_roster_cache.json"
ADVICE_SNAPSHOT_REGISTRY_PATH = _CONFIG_BASE / "config" / "advice_snapshot_registry.json"
ADVICE_SNAPSHOTS_DIR = _CONFIG_BASE / "config" / "advice_snapshots"
# Canonical folder for "Basis bijwerken" exports (one current snapshot at a time).
BASISGEGEVENS_DIR = _CONFIG_BASE / "basisgegevens"


class InstallSource(str, Enum):
    EPIC = "epic"
    STEAM = "steam"
    MANUAL = "manual"
    RUNNING = "running"
    UNKNOWN = "unknown"


_GAME_EXES = ("idledragons.exe", "idlechampions.exe")


@dataclass(frozen=True)
class GameInstallInfo:
    install_dir: Path
    source: InstallSource
    downloaded_files_dir: Path
    web_request_log: Path | None


def _is_valid_game_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    exe_ok = (path / "IdleChampions.exe").is_file() or (path / "IdleDragons.exe").is_file()
    data_ok = (path / "IdleDragons_Data").is_dir()
    return exe_ok and data_ok


def _pick_log_file(downloaded_files: Path) -> Path | None:
    for name in WEB_REQUEST_LOG_NAMES:
        candidate = downloaded_files / name
        if candidate.is_file():
            return candidate
    return None


def _build_install_info(install_dir: Path, source: InstallSource) -> GameInstallInfo:
    install_dir = install_dir.resolve()
    downloaded = install_dir / DOWNLOADED_FILES_REL
    return GameInstallInfo(
        install_dir=install_dir,
        source=source,
        downloaded_files_dir=downloaded,
        web_request_log=_pick_log_file(downloaded) if downloaded.is_dir() else None,
    )


def _load_manual_override() -> Path | None:
    if not GAMEDATA_CONFIG_PATH.is_file():
        return None
    try:
        data = json.loads(GAMEDATA_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = (data.get("install_path") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if _is_valid_game_dir(path) else None


def find_epic_install() -> Path | None:
    """Read Epic LauncherInstalled.dat for Idle Champions."""
    program_data = os.environ.get("ProgramData") or r"C:\ProgramData"
    launcher_file = Path(program_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    if not launcher_file.is_file():
        return None
    try:
        payload = json.loads(launcher_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    entries: Iterable[dict] = payload.get("InstallationList") or []
    fallback: Path | None = None
    for entry in entries:
        location = (entry.get("InstallLocation") or "").strip()
        if not location:
            continue
        path = Path(location)
        if not _is_valid_game_dir(path):
            continue
        if entry.get("AppName") == EPIC_APP_NAME:
            return path
        if path.name.lower() == "idlechampions":
            fallback = path
    return fallback


def _steam_path_from_registry() -> Path | None:
    try:
        import winreg
    except ImportError:
        return None
    keys = (
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    )
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                loc, _ = winreg.QueryValueEx(key, "SteamPath")
        except OSError:
            continue
        if loc:
            path = Path(str(loc))
            if path.is_dir():
                return path
    return None


def _steam_library_roots() -> list[Path]:
    roots: list[Path] = []
    registry = _steam_path_from_registry()
    if registry is not None:
        roots.append(registry)
    pf86 = os.environ.get("ProgramFiles(x86)")
    if pf86:
        roots.append(Path(pf86) / "Steam")
    pf = os.environ.get("ProgramFiles")
    if pf:
        steam_pf = Path(pf) / "Steam"
        if steam_pf not in roots:
            roots.append(steam_pf)

    for steam_root in list(roots):
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            lib = Path(match.group(1).replace("\\\\", "\\"))
            if lib not in roots:
                roots.append(lib)
    return roots


def find_steam_install() -> Path | None:
    """Search Steam libraries for Idle Champions."""
    for library in _steam_library_roots():
        candidate = library / "steamapps" / "common" / "IdleChampions"
        if _is_valid_game_dir(candidate):
            return candidate

    try:
        import winreg
    except ImportError:
        return None

    subkeys = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 627690",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 627690",
    )
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for subkey in subkeys:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    loc, _ = winreg.QueryValueEx(key, "InstallLocation")
            except OSError:
                continue
            if loc:
                path = Path(str(loc))
                if _is_valid_game_dir(path):
                    return path
    return None


def find_running_install() -> Path | None:
    """Use the directory of a running Idle Champions process."""
    try:
        import psutil
    except ImportError:
        return None
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname not in _GAME_EXES:
                continue
            exe = proc.info.get("exe")
            if not exe:
                continue
            path = Path(str(exe)).resolve().parent
            if _is_valid_game_dir(path):
                return path
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, TypeError):
            continue
    return None


def find_game_install(*, prefer_manual: bool = True) -> GameInstallInfo | None:
    """
    Resolve game install directory.

    Order: manual config override → Epic → Steam → running process.
    """
    if prefer_manual:
        manual = _load_manual_override()
        if manual is not None:
            return _build_install_info(manual, InstallSource.MANUAL)

    epic = find_epic_install()
    if epic is not None:
        return _build_install_info(epic, InstallSource.EPIC)

    steam = find_steam_install()
    if steam is not None:
        return _build_install_info(steam, InstallSource.STEAM)

    running = find_running_install()
    if running is not None:
        return _build_install_info(running, InstallSource.RUNNING)

    return None


def get_downloaded_files_dir(install: GameInstallInfo | None = None) -> Path | None:
    info = install or find_game_install()
    if info is None:
        return None
    return info.downloaded_files_dir if info.downloaded_files_dir.is_dir() else None


def get_web_request_log_path(install: GameInstallInfo | None = None) -> Path | None:
    info = install or find_game_install()
    if info is None:
        return None
    return info.web_request_log
