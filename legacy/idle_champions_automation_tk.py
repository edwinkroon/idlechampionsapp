# Idle Champions of the Forgotten Realms - Automatisering (Python + GUI)
# Vereist: pip install -r requirements.txt

import ctypes
import tkinter as tk
from tkinter import ttk, messagebox
import pyautogui
import pygetwindow as gw
import threading
import time
from datetime import datetime

# Voorkom dat pyautogui bij fout de muis naar hoek stuurt
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# Windows API voor focus terugzetten (geen extra dependency)
_user32 = ctypes.windll.user32
_user32.GetForegroundWindow.restype = ctypes.c_void_p


def _get_foreground_window():
    """Handle van het venster dat nu focus heeft."""
    return _user32.GetForegroundWindow()


def _restore_foreground_window(hwnd):
    """Zet het gegeven venster weer op de voorgrond."""
    if hwnd:
        _user32.SetForegroundWindow(hwnd)

# Standaard venstertitel (deel van titel)
DEFAULT_WINDOW_TITLE = "Idle Champions"
LEVEL_INTERVAL_DEFAULT = 0      # seconden (0 = zo snel mogelijk)
AUTO_PROGRESS_INTERVAL_DEFAULT = 5  # minuten
ABILITIES_INTERVAL_MIN = 1       # minuten (elke minuut 1 t/m 9 en 0 voor special abilities)
KEY_DELAY = 0.08                 # seconden tussen F-toetsen (snel achter elkaar)


def find_and_activate_window(partial_title: str) -> bool:
    """Zoek venster dat partial_title bevat en geef het focus. Returns True als gevonden."""
    try:
        windows = gw.getWindowsWithTitle(partial_title)
        if not windows:
            return False
        win = windows[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.15)
        return True
    except Exception:
        return False


def do_level_cycle(click_damage: bool, champions: list):
    """Stuur backtick + F1..F12 (of subset) naar het actieve venster."""
    if click_damage:
        pyautogui.press("`")
        time.sleep(KEY_DELAY)
    for i in champions:
        if 1 <= i <= 12:
            pyautogui.press(f"f{i}")
            time.sleep(KEY_DELAY)


def do_auto_progress():
    """Stuur toets G (toggle auto progress)."""
    pyautogui.press("g")


def do_abilities_cycle():
    """Stuur toetsen 1 t/m 9 en 0 voor special abilities."""
    for key in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"):
        pyautogui.press(key)
        time.sleep(KEY_DELAY)


class AutomationApp:
    def __init__(self):
        self.running = False
        self.level_timer = None
        self.auto_progress_timer = None
        self.abilities_timer = None
        self.window_title = DEFAULT_WINDOW_TITLE
        self.level_interval_sec = LEVEL_INTERVAL_DEFAULT
        self.auto_progress_interval_min = AUTO_PROGRESS_INTERVAL_DEFAULT
        self.level_click_damage = True
        # F12 eerst, dan aflopend naar F1
        self.level_champions = [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]

        self.root = tk.Tk()
        self.root.title("Idle Champions – Automatisering")
        self.root.minsize(320, 280)
        self.root.resizable(True, True)

        # Frame instellingen
        frm = ttk.LabelFrame(self.root, text="Instellingen", padding=10)
        frm.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(frm, text="Venstertitel (deel van):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.entry_window = ttk.Entry(frm, width=35)
        self.entry_window.insert(0, DEFAULT_WINDOW_TITLE)
        self.entry_window.grid(row=0, column=1, padx=5, pady=2)

        self.cb_level = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="Auto levelen (backtick + F12→F1)", variable=self.cb_level).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=4
        )

        ttk.Label(frm, text="Level-interval (seconden):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.entry_level_interval = ttk.Entry(frm, width=8)
        self.entry_level_interval.insert(0, str(LEVEL_INTERVAL_DEFAULT))
        self.entry_level_interval.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        self.cb_auto_progress = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Auto progress (elke X min toets G)", variable=self.cb_auto_progress).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=4
        )

        ttk.Label(frm, text="Auto-progress-interval (minuten):").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.entry_auto_progress_interval = ttk.Entry(frm, width=8)
        self.entry_auto_progress_interval.insert(0, str(AUTO_PROGRESS_INTERVAL_DEFAULT))
        self.entry_auto_progress_interval.grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)

        self.cb_abilities = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm, text="Special abilities (elke minuut toetsen 1 t/m 9 en 0)",
            variable=self.cb_abilities,
        ).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=4)

        self.cb_restore_focus = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm,
            text="Focus na toetsen terugzetten (zodat je door kunt werken)",
            variable=self.cb_restore_focus,
        ).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=4)

        # Knoppen
        btn_frm = ttk.Frame(self.root, padding=10)
        btn_frm.pack(fill=tk.X)

        self.btn_start = ttk.Button(btn_frm, text="Start", command=self.start)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(btn_frm, text="Stop", command=self.stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(self.root, text="Status: gestopt", font=("Segoe UI", 9))
        self.lbl_status.pack(pady=5)
        self.lbl_last_level = ttk.Label(self.root, text="Laatste level: —", font=("Segoe UI", 8), foreground="gray")
        self.lbl_last_level.pack(pady=0)

        ttk.Label(
            self.root,
            text="Zorg dat Idle Champions draait. Venster wordt op titel gezocht.",
            font=("Segoe UI", 8),
            foreground="gray",
        ).pack(pady=5)

    def read_settings(self):
        self.window_title = self.entry_window.get().strip() or DEFAULT_WINDOW_TITLE
        try:
            self.level_interval_sec = max(0, int(self.entry_level_interval.get()))
        except ValueError:
            self.level_interval_sec = LEVEL_INTERVAL_DEFAULT
        try:
            self.auto_progress_interval_min = max(1, int(self.entry_auto_progress_interval.get()))
        except ValueError:
            self.auto_progress_interval_min = AUTO_PROGRESS_INTERVAL_DEFAULT
        self.level_click_damage = self.cb_level.get()
        self.level_champions = [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]  # F12 aflopend naar F1

    def start(self):
        self.read_settings()
        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text=f"Status: actief (level elke {self.level_interval_sec} sec)")
        self.lbl_last_level.config(text="Laatste level: —")

        if self.cb_level.get():
            # Eerste level-ronde na 1 sec, daarna om de level_interval_sec
            self.root.after(1000, self.schedule_level)
        if self.cb_auto_progress.get():
            self.schedule_auto_progress()
        if self.cb_abilities.get():
            self.schedule_abilities()

    def stop(self):
        self.running = False
        if self.level_timer is not None:
            self.root.after_cancel(self.level_timer)
            self.level_timer = None
        if self.auto_progress_timer is not None:
            self.root.after_cancel(self.auto_progress_timer)
            self.auto_progress_timer = None
        if self.abilities_timer is not None:
            self.root.after_cancel(self.abilities_timer)
            self.abilities_timer = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text="Status: gestopt")
        self.lbl_last_level.config(text="Laatste level: —")

    def schedule_level(self):
        if not self.running:
            return
        prev_hwnd = _get_foreground_window() if self.cb_restore_focus.get() else None
        if find_and_activate_window(self.window_title):
            do_level_cycle(self.level_click_damage, self.level_champions)
            if prev_hwnd:
                _restore_foreground_window(prev_hwnd)
            self.lbl_last_level.config(
                text="Laatste level: " + datetime.now().strftime("%H:%M:%S")
            )
        if self.running:
            self.level_timer = self.root.after(
                self.level_interval_sec * 1000,
                self.schedule_level,
            )

    def schedule_auto_progress(self):
        if not self.running:
            return
        prev_hwnd = _get_foreground_window() if self.cb_restore_focus.get() else None
        if find_and_activate_window(self.window_title):
            do_auto_progress()
            if prev_hwnd:
                _restore_foreground_window(prev_hwnd)
        if self.running:
            self.auto_progress_timer = self.root.after(
                self.auto_progress_interval_min * 60 * 1000,
                self.schedule_auto_progress,
            )

    def schedule_abilities(self):
        if not self.running:
            return
        prev_hwnd = _get_foreground_window() if self.cb_restore_focus.get() else None
        if find_and_activate_window(self.window_title):
            do_abilities_cycle()
            if prev_hwnd:
                _restore_foreground_window(prev_hwnd)
        if self.running:
            self.abilities_timer = self.root.after(
                ABILITIES_INTERVAL_MIN * 60 * 1000,
                self.schedule_abilities,
            )

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AutomationApp()
    app.run()
