"""Low-level Windows input / window helpers for Idle Champions automation."""

from __future__ import annotations

import ctypes
import time
from typing import Any

try:
    import pyautogui
except ImportError:
    pyautogui = None
try:
    import pygetwindow as gw
except ImportError:
    gw = None
try:
    import win32gui
    import win32con
    import win32api
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    win32gui = None  # type: ignore
    win32con = None  # type: ignore
    win32api = None  # type: ignore

if pyautogui:
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

KEY_DELAY = 0.08
ACTIVATE_SLEEP = 0.5

KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002

SCANCODE_F1, SCANCODE_F12 = 0x3B, 0x58
SCANCODE_F11 = 0x57
SCANCODE_G = 0x22
SCANCODE_GRAVE = 0x29
SCANCODES_F = {
    i: (SCANCODE_F1 + (i - 1) if i <= 10 else (SCANCODE_F11 if i == 11 else SCANCODE_F12))
    for i in range(1, 13)
}


def get_window_rect(hwnd: Any):
    if not HAS_WIN32 or not hwnd:
        return None
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def point_in_rect(x: int, y: int, rect) -> bool:
    if not rect or len(rect) < 4:
        return False
    left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
    return left <= x < right and top <= y < bottom


def get_window_handle(partial_title: str, exclude_hwnd=None, exclude_title=None):
    if not gw:
        return None
    try:
        windows = gw.getWindowsWithTitle(partial_title)
        if not windows:
            return None
        for w in windows:
            w_title = getattr(w, "title", None)
            w_title = (w_title() if callable(w_title) else w_title) or ""
            if exclude_title and w_title == exclude_title:
                continue
            hwnd = getattr(w, "hWnd", None) or getattr(w, "_hWnd", None) or getattr(w, "hwnd", None)
            if hwnd and (exclude_hwnd is None or int(hwnd) != int(exclude_hwnd)):
                return hwnd
        return None
    except Exception:
        return None


def get_game_window_rect(partial_title: str, exclude_hwnd=None, exclude_title=None):
    hwnd = get_window_handle(partial_title, exclude_hwnd=exclude_hwnd, exclude_title=exclude_title)
    if not hwnd:
        return None
    r = get_window_rect(hwnd)
    if r:
        return r
    if not gw:
        return None
    try:
        for w in gw.getWindowsWithTitle(partial_title):
            w_title = getattr(w, "title", None)
            w_title = (w_title() if callable(w_title) else w_title) or ""
            if exclude_title and w_title == exclude_title:
                continue
            wh = getattr(w, "hWnd", None) or getattr(w, "_hWnd", None) or getattr(w, "hwnd", None)
            if wh and int(wh) == int(hwnd):
                return (w.left, w.top, w.left + w.width, w.top + w.height)
    except Exception:
        pass
    return None


def get_foreground_window():
    if not HAS_WIN32:
        return None
    try:
        return win32gui.GetForegroundWindow()
    except Exception:
        return None


def restore_foreground_window(hwnd) -> None:
    if not HAS_WIN32 or not hwnd:
        return
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def find_and_activate_window(partial_title: str, exclude_hwnd=None, exclude_title=None) -> bool:
    if not gw:
        return False
    try:
        windows = gw.getWindowsWithTitle(partial_title)
        if not windows:
            return False
        win = None
        for w in windows:
            w_title = getattr(w, "title", None)
            w_title = (w_title() if callable(w_title) else w_title) or ""
            if exclude_title and w_title == exclude_title:
                continue
            hwnd = getattr(w, "hWnd", None) or getattr(w, "_hWnd", None) or getattr(w, "hwnd", None)
            if hwnd and (exclude_hwnd is None or int(hwnd) != int(exclude_hwnd)):
                win = w
                break
        if not win:
            return False
        if win.isMinimized:
            win.restore()
        hwnd = getattr(win, "hWnd", None) or getattr(win, "_hWnd", None) or getattr(win, "hwnd", None)
        if HAS_WIN32 and hwnd:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                win.activate()
        else:
            win.activate()
        time.sleep(ACTIVATE_SLEEP)
        return True
    except Exception:
        return False


def get_window_title(partial_title: str, exclude_hwnd=None, exclude_title=None) -> str:
    if not gw:
        return ""
    try:
        windows = gw.getWindowsWithTitle(partial_title)
        for w in windows:
            w_title = getattr(w, "title", None)
            w_title = (w_title() if callable(w_title) else w_title) or ""
            if exclude_title and w_title == exclude_title:
                continue
            hwnd = getattr(w, "hWnd", None) or getattr(w, "_hWnd", None) or getattr(w, "hwnd", None)
            if hwnd and (exclude_hwnd is None or int(hwnd) != int(exclude_hwnd)):
                return w_title
        return ""
    except Exception:
        return ""


def caps_lock_on() -> bool:
    try:
        if HAS_WIN32:
            return bool(win32api.GetKeyState(win32con.VK_CAPITAL) & 1)
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
    except Exception:
        return False


def shift_held() -> bool:
    """True als linker- of rechter-Shift ingedrukt is."""
    try:
        # VK_SHIFT=0x10 — covers either shift via GetAsyncKeyState
        if HAS_WIN32:
            return bool(win32api.GetAsyncKeyState(0x10) & 0x8000)
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
    except Exception:
        return False


def ctrl_held() -> bool:
    """True als linker- of rechter-Ctrl ingedrukt is."""
    try:
        # VK_CONTROL=0x11 — covers either ctrl via GetAsyncKeyState
        if HAS_WIN32:
            return bool(win32api.GetAsyncKeyState(0x11) & 0x8000)
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
    except Exception:
        return False


def toplevel_hwnd(hwnd) -> int | None:
    """Map child HWND (bijv. Tk winfo_id) naar top-level venster."""
    if hwnd is None:
        return None
    try:
        value = int(hwnd)
    except (TypeError, ValueError):
        return None
    if not HAS_WIN32:
        return value
    try:
        # GA_ROOT = 2
        root = win32gui.GetAncestor(value, 2)
        return int(root) if root else value
    except Exception:
        return value


def cursor_over_hwnd(hwnd) -> bool:
    """True als de muiscursor binnen het (top-level) venster ligt."""
    top = toplevel_hwnd(hwnd)
    if top is None:
        return False
    rect = get_window_rect(top)
    if not rect:
        return False
    try:
        if HAS_WIN32:
            x, y = win32api.GetCursorPos()
        elif pyautogui:
            x, y = pyautogui.position()
        else:
            return False
    except Exception:
        return False
    return point_in_rect(x, y, rect)


def foreground_is_hwnd(hwnd) -> bool:
    top = toplevel_hwnd(hwnd)
    if top is None:
        return False
    fg = get_foreground_window()
    if not fg:
        return False
    try:
        return int(toplevel_hwnd(fg) or fg) == int(top)
    except (TypeError, ValueError):
        return False


def game_is_foreground(partial_title: str, exclude_hwnd=None, exclude_title=None) -> bool:
    hwnd = get_window_handle(partial_title, exclude_hwnd=exclude_hwnd, exclude_title=exclude_title)
    if not hwnd:
        return False
    return foreground_is_hwnd(hwnd)


def cursor_over_game(partial_title: str, exclude_hwnd=None, exclude_title=None) -> bool:
    try:
        if HAS_WIN32:
            x, y = win32api.GetCursorPos()
        elif pyautogui:
            x, y = pyautogui.position()
        else:
            return False
    except Exception:
        return False
    gr = get_game_window_rect(partial_title, exclude_hwnd=exclude_hwnd, exclude_title=exclude_title)
    return bool(gr and point_in_rect(x, y, gr))


def send_left_click_at_cursor() -> bool:
    try:
        if HAS_WIN32:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.01)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return True
        if pyautogui:
            pyautogui.click()
            return True
    except Exception:
        pass
    return False


def _sendinput_key(scancode: int, key_up: bool) -> None:
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KeyBdInput(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class HardwareInput(ctypes.Structure):
        _fields_ = [
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_short),
            ("wParamH", ctypes.c_ushort),
        ]

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class Input_I(ctypes.Union):
        _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

    extra = ctypes.c_ulong(0)
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
    ii = Input_I()
    ii.ki = KeyBdInput(0, scancode, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii)
    ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(Input))


def send_key_scancode(scancode: int) -> None:
    _sendinput_key(scancode, key_up=False)
    time.sleep(KEY_DELAY)
    _sendinput_key(scancode, key_up=True)


def do_level_cycle(champions: list, use_sendinput: bool = True) -> None:
    if use_sendinput:
        for i in champions:
            if 1 <= i <= 12:
                send_key_scancode(SCANCODES_F[i])
        return
    if not pyautogui:
        return
    for i in champions:
        if 1 <= i <= 12:
            pyautogui.press(f"f{i}")
            time.sleep(KEY_DELAY)


def do_auto_progress(use_sendinput: bool = True) -> None:
    if use_sendinput:
        send_key_scancode(SCANCODE_G)
        return
    if pyautogui:
        pyautogui.press("g")


def do_abilities_cycle(keys: list[str] | None = None, use_sendinput: bool = True) -> None:
    if keys is None:
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
    if not keys:
        return
    key_to_scancode = {
        "1": 0x02,
        "2": 0x03,
        "3": 0x04,
        "4": 0x05,
        "5": 0x06,
        "6": 0x07,
        "7": 0x08,
        "8": 0x09,
        "9": 0x0A,
        "0": 0x0B,
    }
    if use_sendinput:
        for key in keys:
            sc = key_to_scancode.get(key)
            if sc is not None:
                send_key_scancode(sc)
        return
    if pyautogui:
        for key in keys:
            if key in key_to_scancode:
                pyautogui.press(key)
                time.sleep(KEY_DELAY)


def do_grave_key(use_sendinput: bool = True) -> None:
    if use_sendinput:
        send_key_scancode(SCANCODE_GRAVE)
        return
    if pyautogui:
        pyautogui.press("`")
