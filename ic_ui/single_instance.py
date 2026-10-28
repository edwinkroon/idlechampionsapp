"""Ensure only one Idle Champions companion process is running.

On startup the new process closes any other matching instance (exe or
``app_launcher.py`` / pyside entry), then continues. That prefers the
freshly started build over a leftover older window.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

# Frozen PyInstaller name (IdleChampionsApp.spec).
_FROZEN_IMAGE_NAMES = frozenset(
    {
        "idlechampionsapp.exe",
        "idlechampionsapp",
    }
)

# Dev / pythonw entry markers in cmdline.
_CMDLINE_MARKERS = (
    "app_launcher.py",
    "ic_ui.pyside_app",
    "ic_ui\\pyside_app",
    "ic_ui/pyside_app",
)


def _norm(text: str) -> str:
    return text.replace("\\", "/").casefold()


def _cmdline_tokens(proc_info: dict[str, Any]) -> list[str]:
    raw = proc_info.get("cmdline") or []
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(part) for part in raw if part]


def is_companion_process(proc_info: dict[str, Any], *, frozen: bool | None = None) -> bool:
    """Return True when ``proc_info`` looks like this companion app.

    Matches the frozen exe **or** a python/pythonw process whose cmdline
    runs our launcher — so starting either form can close the other.
    ``frozen`` is accepted for call-site compatibility and ignored.
    """
    del frozen  # detection is by image name / cmdline, not by our own mode
    name = str(proc_info.get("name") or "").casefold()
    if name in _FROZEN_IMAGE_NAMES:
        return True
    # Dev / pythonw: require an explicit launcher marker (never bare python).
    joined = _norm(" ".join(_cmdline_tokens(proc_info)))
    if not joined:
        return False
    return any(_norm(marker) in joined for marker in _CMDLINE_MARKERS)


def iter_other_companion_pids(
    *,
    current_pid: int | None = None,
    process_iter=None,
) -> list[int]:
    """PIDs of other companion processes (excludes ``current_pid``)."""
    import psutil

    me = int(current_pid if current_pid is not None else os.getpid())
    frozen = bool(getattr(sys, "frozen", False))
    iterator = process_iter or psutil.process_iter
    found: list[int] = []
    for proc in iterator(["pid", "name", "cmdline"]):
        try:
            info = proc.as_dict(attrs=["pid", "name", "cmdline"])
        except (psutil.Error, AttributeError):
            continue
        pid = info.get("pid")
        if not isinstance(pid, int) or pid == me:
            continue
        try:
            if is_companion_process(info, frozen=frozen):
                found.append(pid)
        except (psutil.Error, TypeError, ValueError):
            continue
    return found


def close_other_instances(
    *,
    current_pid: int | None = None,
    wait_s: float = 4.0,
    process_iter=None,
    process_factory=None,
) -> list[int]:
    """Terminate other companion instances; return closed PIDs.

    Tries ``terminate()`` first, then ``kill()`` after ``wait_s`` if still alive.
    Never targets ``current_pid``.
    """
    import psutil

    factory = process_factory or psutil.Process
    closed: list[int] = []
    for pid in iter_other_companion_pids(
        current_pid=current_pid, process_iter=process_iter
    ):
        try:
            proc = factory(pid)
        except (psutil.Error, ValueError):
            continue
        try:
            if not proc.is_running():
                continue
            proc.terminate()
        except psutil.Error:
            continue
        deadline = time.monotonic() + max(0.1, float(wait_s))
        while time.monotonic() < deadline:
            try:
                if not proc.is_running():
                    break
            except psutil.Error:
                break
            time.sleep(0.05)
        try:
            if proc.is_running():
                proc.kill()
        except psutil.Error:
            pass
        try:
            gone = not proc.is_running()
        except psutil.Error:
            gone = True
        if gone:
            closed.append(pid)
    return closed


def ensure_single_instance(*, wait_s: float = 4.0) -> list[int]:
    """Close leftover companion windows, then allow this process to start."""
    return close_other_instances(wait_s=wait_s)
