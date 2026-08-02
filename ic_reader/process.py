"""Discover Idle Champions process and module base addresses."""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
from typing import Sequence

from ic_reader.exceptions import ModuleNotFoundError, ProcessNotFoundError

logger = logging.getLogger(__name__)

# Read-only access
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
MAX_MODULE_NAME = 255


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("th32ModuleID", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("GlblcntUsage", ctypes.c_ulong),
        ("ProccntUsage", ctypes.c_ulong),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", ctypes.c_ulong),
        ("hModule", ctypes.c_void_p),
        ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    exe_path: str | None


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    base_address: int
    size: int


def find_process(
    executable_names: Sequence[str] | None = None,
) -> ProcessInfo:
    """Return the first running process matching one of executable_names."""
    try:
        import psutil
    except ImportError as exc:
        raise ProcessNotFoundError(
            "psutil is required for process discovery. Install with: pip install psutil"
        ) from exc

    names = {n.lower() for n in (executable_names or ("IdleChampions.exe",))}
    matches: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname not in names:
                continue
            matches.append(
                ProcessInfo(
                    pid=int(proc.info["pid"]),
                    name=proc.info.get("name") or pname,
                    exe_path=proc.info.get("exe"),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not matches:
        raise ProcessNotFoundError(
            f"No running process found for: {', '.join(sorted(names))}. "
            "Start Idle Champions and ensure the reader runs with sufficient privileges."
        )
    if len(matches) > 1:
        logger.warning("Multiple Idle Champions processes found; using pid=%s", matches[0].pid)
    return matches[0]


def open_process_handle(pid: int) -> int:
    """Open a read-only handle to the target process. Returns Win32 HANDLE as int."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
        False,
        pid,
    )
    if not handle:
        err = ctypes.get_last_error()
        raise ProcessNotFoundError(
            f"OpenProcess failed for pid={pid} (error {err}). "
            "Try running the reader as Administrator if the game runs elevated."
        )
    return handle


def close_process_handle(handle: int) -> None:
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)


def list_modules(pid: int) -> list[ModuleInfo]:
    """Enumerate loaded modules for a process (64-bit friendly)."""
    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == -1 or snap is None:
        err = ctypes.get_last_error()
        raise ModuleNotFoundError(f"CreateToolhelp32Snapshot failed (error {err}) for pid={pid}")

    modules: list[ModuleInfo] = []
    entry = MODULEENTRY32W()
    entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
    try:
        if not kernel32.Module32FirstW(snap, ctypes.byref(entry)):
            err = ctypes.get_last_error()
            raise ModuleNotFoundError(f"Module32FirstW failed (error {err})")
        while True:
            base = entry.modBaseAddr
            if base is None:
                base_int = 0
            else:
                base_int = int(ctypes.cast(base, ctypes.c_void_p).value or 0)
            modules.append(
                ModuleInfo(
                    name=entry.szModule,
                    base_address=base_int,
                    size=int(entry.modBaseSize),
                )
            )
            if not kernel32.Module32NextW(snap, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snap)
    return modules


def get_module_base(
    pid: int,
    module_name: str,
    *,
    modules: list[ModuleInfo] | None = None,
) -> ModuleInfo:
    """Resolve module base address by name (case-insensitive)."""
    target = module_name.lower()
    mod_list = modules if modules is not None else list_modules(pid)
    for mod in mod_list:
        if mod.name.lower() == target:
            return mod
    available = ", ".join(m.name for m in mod_list[:12])
    suffix = "..." if len(mod_list) > 12 else ""
    raise ModuleNotFoundError(
        f"Module '{module_name}' not found in pid={pid}. "
        f"Loaded modules (sample): {available}{suffix}"
    )
