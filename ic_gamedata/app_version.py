"""Application version metadata."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def app_version() -> str:
    pyproject = _PROJECT_ROOT / "pyproject.toml"
    if pyproject.is_file():
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1)
    return "0.0.0"


def build_number() -> str | None:
    try:
        from build_info import BUILD_NUMBER
    except ImportError:
        return None
    return BUILD_NUMBER if BUILD_NUMBER else None


def version_label() -> str:
    build = build_number()
    if build:
        return f"v{app_version()} ({build})"
    return f"v{app_version()}"
