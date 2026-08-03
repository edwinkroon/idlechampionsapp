"""Background automation worker — no tkinter calls."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ic_automation import win_input
from ic_automation.settings import AutomationSettings


@dataclass(frozen=True)
class StatusEvent:
    text: str
    kind: str = "status"  # status | paused | error


class AutomationWorker:
    """Runs level / grave / abilities / auto-progress / auto-click off the UI thread."""

    def __init__(
        self,
        settings: AutomationSettings,
        status_queue: queue.Queue[StatusEvent],
        *,
        tick_sec: float = 0.05,
    ) -> None:
        self._lock = threading.Lock()
        self._settings = settings
        self._status_queue = status_queue
        self._tick_sec = max(0.02, float(tick_sec))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_level = 0.0
        self._next_progress = 0.0
        self._next_grave = 0.0
        self._next_abilities = 0.0
        self._next_click = 0.0
        self._last_pause_emit = 0.0
        self._last_pause_reason: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        now = time.monotonic()
        # Stagger first runs slightly so Start doesn't blast everything at once.
        self._next_level = now + 1.0
        self._next_progress = now
        self._next_grave = now
        self._next_abilities = now
        self._next_click = now
        self._last_pause_emit = 0.0
        self._last_pause_reason = None
        self._thread = threading.Thread(target=self._run, name="ic-automation-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def update_settings(self, settings: AutomationSettings) -> None:
        with self._lock:
            self._settings = settings

    def _get_settings(self) -> AutomationSettings:
        with self._lock:
            return self._settings

    def _emit(self, text: str, kind: str = "status") -> None:
        try:
            self._status_queue.put_nowait(StatusEvent(text=text, kind=kind))
        except queue.Full:
            pass

    def _emit_pause(self, reason: str) -> None:
        now = time.monotonic()
        if reason == self._last_pause_reason and (now - self._last_pause_emit) < 0.8:
            return
        self._last_pause_reason = reason
        self._last_pause_emit = now
        self._emit(f"Status: gepauzeerd — {reason}", "paused")

    def _ui_pause_reason(self, settings: AutomationSettings) -> str | None:
        """Hard pause: user is interacting with helper or holding Ctrl."""
        if win_input.caps_lock_on():
            return "Caps Lock staat aan"
        if settings.pause_on_ctrl and win_input.ctrl_held():
            return "Ctrl ingedrukt (laat los om door te gaan)"
        if settings.exclude_hwnd is not None:
            if settings.pause_when_over_app and win_input.cursor_over_hwnd(settings.exclude_hwnd):
                return "muis boven helper-app"
            if settings.pause_when_app_focused and win_input.foreground_is_hwnd(settings.exclude_hwnd):
                return "helper-app heeft focus"
        return None

    def _guards_ok(self, settings: AutomationSettings, *, for_auto_click: bool = False) -> bool:
        ui_reason = self._ui_pause_reason(settings)
        if ui_reason:
            self._emit_pause(ui_reason)
            return False
        if for_auto_click:
            # Auto-click always requires cursor over the game.
            return win_input.cursor_over_game(
                settings.window_title,
                exclude_hwnd=settings.exclude_hwnd,
                exclude_title=settings.exclude_title or None,
            )
        if settings.hover_gate and not win_input.cursor_over_game(
            settings.window_title,
            exclude_hwnd=settings.exclude_hwnd,
            exclude_title=settings.exclude_title or None,
        ):
            return False
        return True

    def _with_focus(self, settings: AutomationSettings, action: Callable[[], None]) -> bool:
        # Never steal focus while the helper is in use (belt-and-suspenders).
        if self._ui_pause_reason(settings):
            return False

        game_focused = win_input.game_is_foreground(
            settings.window_title,
            exclude_hwnd=settings.exclude_hwnd,
            exclude_title=settings.exclude_title or None,
        )
        if game_focused:
            action()
            return True

        if settings.prefer_game_already_focused:
            # Don't yank focus away from other windows (browser, Discord, …).
            return False

        prev = win_input.get_foreground_window() if settings.restore_focus else None
        ok = win_input.find_and_activate_window(
            settings.window_title,
            exclude_hwnd=settings.exclude_hwnd,
            exclude_title=settings.exclude_title or None,
        )
        if not ok:
            return False
        # If activate somehow brought us to the helper, abort.
        if self._ui_pause_reason(settings):
            return False
        time.sleep(0.25)
        action()
        time.sleep(0.05)
        if prev and not win_input.foreground_is_hwnd(settings.exclude_hwnd):
            win_input.restore_foreground_window(prev)
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            settings = self._get_settings()
            now = time.monotonic()

            # Clear pause banner when we resume.
            if self._last_pause_reason and self._ui_pause_reason(settings) is None:
                self._last_pause_reason = None
                self._emit("Status: actief (worker)")

            if settings.enable_auto_click and now >= self._next_click:
                cps = max(1, min(20, int(settings.auto_click_cps)))
                interval = max(0.05, 1.0 / cps)
                self._next_click = now + interval
                if self._guards_ok(settings, for_auto_click=True):
                    win_input.send_left_click_at_cursor()

            if settings.enable_grave and now >= self._next_grave:
                self._next_grave = now + max(1, int(settings.grave_interval_sec))
                if self._guards_ok(settings):
                    self._with_focus(settings, lambda: win_input.do_grave_key(True))

            if settings.enable_auto_progress and now >= self._next_progress:
                self._next_progress = now + max(1, int(settings.auto_progress_interval_sec))
                if self._guards_ok(settings):
                    self._with_focus(settings, lambda: win_input.do_auto_progress(True))

            if settings.enable_abilities and now >= self._next_abilities:
                self._next_abilities = now + max(3, int(settings.abilities_interval_sec))
                if self._guards_ok(settings):
                    ok = self._with_focus(
                        settings,
                        lambda: win_input.do_abilities_cycle(
                            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"], True
                        ),
                    )
                    if ok:
                        self._emit(
                            f"Status: abilities → alle toetsen 1-0 verstuurd "
                            f"(elke {settings.abilities_interval_sec}s)"
                        )
                    elif self._ui_pause_reason(settings) is None:
                        self._emit(
                            "Status: abilities wacht — zet focus op het spel (of zet "
                            "'alleen bij spel-focus' uit)",
                            "error",
                        )

            if settings.enable_level and now >= self._next_level:
                interval = max(0, int(settings.level_interval_sec))
                self._next_level = now + (0.05 if interval <= 0 else float(interval))
                if not settings.level_champions:
                    self._emit(
                        "Status: actief — geen seats om te levelen "
                        "(wacht op formatie-sync, of vink F-toetsen handmatig aan)"
                    )
                elif self._guards_ok(settings):
                    champs = list(settings.level_champions)

                    def _level() -> None:
                        win_input.do_level_cycle(champs, True)

                    if self._with_focus(settings, _level):
                        if interval <= 0:
                            self._emit("Status: actief — level zo snel mogelijk")
                        else:
                            self._emit(f"Status: actief — level elke {interval} sec")

            self._stop.wait(self._tick_sec)
