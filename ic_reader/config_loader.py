"""Load game_offsets.json configuration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ic_reader.exceptions import ConfigError
from ic_reader.models import GameOffsetsConfig

DEFAULT_CONFIG_PATH = Path("config") / "game_offsets.json"
EXAMPLE_CONFIG_PATH = Path("config") / "game_offsets.example.json"


def _config_search_paths() -> list[Path]:
    """Paths to try for game_offsets.json (exe dir first when frozen)."""
    paths: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        paths.append(exe_dir / "config" / "game_offsets.json")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / "config" / "game_offsets.json")
    paths.append(DEFAULT_CONFIG_PATH.resolve())
    paths.append(EXAMPLE_CONFIG_PATH.resolve())
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
        paths.append(Path(sys._MEIPASS) / "config" / "game_offsets.example.json")
    paths.append(EXAMPLE_CONFIG_PATH.resolve())
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in paths:
        rp = p.resolve() if p.is_absolute() or p.exists() else p
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def resolve_config_path(path: Path | None = None) -> Path:
    """Pick first existing config file."""
    if path is not None:
        if path.is_file():
            return path
        raise ConfigError(f"Config not found: {path}")
    for candidate in _config_search_paths():
        if candidate.is_file():
            return candidate
    raise ConfigError(
        f"No config found. Tried: {', '.join(str(p) for p in _config_search_paths())}. "
        "Place config/game_offsets.json next to IdleChampionsApp.exe or in the project config/ folder."
    )


def load_config(path: Path | None = None) -> GameOffsetsConfig:
    """Load offsets config; falls back through search paths."""
    path = resolve_config_path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be an object: {path}")
    return GameOffsetsConfig.from_dict(data)
