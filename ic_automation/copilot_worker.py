"""Background worker for Co-Pilot formation hotkeys (Q/W/E/G)."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

from ic_automation import win_input
from ic_automation.copilot_settings import CopilotKeySettings
from ic_gamedata.gem_farm.copilot_keys import keys_on_area_reset, keys_on_phase_change
from ic_gamedata.gem_farm.models import CopilotPhase, GemFarmSnapshot


@dataclass(frozen=True)
class CopilotStatusEvent:
    text: str
    kind: str = "status"  # status | paused | action | error


class CopilotWorker:
    def __init__(
        self,
        settings: CopilotKeySettings,
        status_queue: queue.Queue[CopilotStatusEvent],
        *,
        tick_sec: float = 0.25,
    ) -> None:
        self._lock = threading.Lock()
        self._settings = settings
        self._status_queue = status_queue
        self._tick_sec = max(0.1, float(tick_sec))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot: GemFarmSnapshot | None = None
        self._last_phase: CopilotPhase | None = None
        self._last_area: int | None = None
        self._last_action_at: dict[str, float] = {}
        self._pending_keys: deque[str] = deque()
        self._ap_assumed_on: bool | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ic-copilot-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def update_settings(self, settings: CopilotKeySettings) -> None:
        with self._lock:
            self._settings = settings

    def update_snapshot(self, snapshot: GemFarmSnapshot | None) -> None:
        with self._lock:
            self._snapshot = snapshot

    def _get_settings(self) -> CopilotKeySettings:
        with self._lock:
            return self._settings

    def _get_snapshot(self) -> GemFarmSnapshot | None:
        with self._lock:
            return self._snapshot

    def _emit(self, text: str, kind: str = "status") -> None:
        try:
            self._status_queue.put_nowait(CopilotStatusEvent(text=text, kind=kind))
        except queue.Full:
            pass

    def _ui_pause_reason(self, settings: CopilotKeySettings) -> str | None:
        if settings.send_keys_enabled:
            return None
        if win_input.caps_lock_on():
            return "Caps Lock staat aan"
        if settings.pause_on_ctrl and win_input.ctrl_held():
            return "Ctrl ingedrukt"
        if settings.exclude_hwnd is not None:
            if settings.pause_when_over_app and win_input.cursor_over_hwnd(settings.exclude_hwnd):
                return "muis boven helper-app"
            if settings.pause_when_app_focused and win_input.foreground_is_hwnd(settings.exclude_hwnd):
                return "helper-app heeft focus"
        return None

    def _guards_ok(self, settings: CopilotKeySettings) -> str | None:
        """Return pause reason when sending should be blocked, else None."""
        if settings.send_keys_enabled:
            return None
        reason = self._ui_pause_reason(settings)
        if reason:
            return reason
        if settings.hover_gate and not win_input.cursor_over_game(
            settings.window_title,
            exclude_hwnd=settings.exclude_hwnd,
            exclude_title=settings.exclude_title or None,
        ):
            return "muis niet boven spelvenster"
        return None

    def _with_focus(self, settings: CopilotKeySettings, action) -> bool:
        if not settings.send_keys_enabled and self._ui_pause_reason(settings):
            return False
        if win_input.game_is_foreground(
            settings.window_title,
            exclude_hwnd=settings.exclude_hwnd,
            exclude_title=settings.exclude_title or None,
        ):
            action()
            return True
        if not settings.send_keys_enabled and settings.prefer_game_already_focused:
            return False
        prev = win_input.get_foreground_window() if settings.restore_focus else None
        ok = win_input.find_and_activate_window(
            settings.window_title,
            exclude_hwnd=settings.exclude_hwnd,
            exclude_title=settings.exclude_title or None,
        )
        if not ok:
            return False
        if not settings.send_keys_enabled and self._ui_pause_reason(settings):
            return False
        time.sleep(0.25)
        action()
        time.sleep(0.05)
        if prev and not win_input.foreground_is_hwnd(settings.exclude_hwnd):
            win_input.restore_foreground_window(prev)
        return True

    def _debounce_ok(self, key: str, settings: CopilotKeySettings) -> bool:
        now = time.monotonic()
        last = self._last_action_at.get(key)
        if last is not None and (now - last) < settings.action_debounce_sec:
            return False
        return True

    def _mark_sent(self, key: str) -> None:
        self._last_action_at[key] = time.monotonic()

    def _clear_debounce(self) -> None:
        self._last_action_at.clear()

    def _enqueue_keys(self, keys: tuple[str, ...]) -> None:
        for key in keys:
            if key and (not self._pending_keys or self._pending_keys[-1] != key):
                self._pending_keys.append(key)

    def _send_hotkey(self, settings: CopilotKeySettings, key: str) -> bool:
        if not self._debounce_ok(key, settings):
            self._pending_keys.appendleft(key)
            self._emit(f"Co-Pilot: {key} overgeslagen (debounce)", "paused")
            return False
        guard_reason = self._guards_ok(settings)
        if guard_reason:
            self._pending_keys.appendleft(key)
            self._emit(f"Co-Pilot: {key} niet verstuurd ({guard_reason})", "paused")
            return False

        def _action() -> None:
            win_input.do_formation_hotkey(key, True)

        if self._with_focus(settings, _action):
            self._mark_sent(key)
            self._emit(f"Co-Pilot: toets {key} verstuurd", "action")
            snapshot = self._get_snapshot()
            if snapshot is not None:
                try:
                    from ic_gamedata.gem_farm.event_log import append_farm_event
                    from ic_gamedata.gem_farm.models import FarmEvent

                    append_farm_event(
                        FarmEvent(
                            timestamp=time.time(),
                            party_index=snapshot.party_index,
                            kind="copilot",
                            rule_id=f"key_{key.lower()}",
                            severity="info",
                            message=f"Co-Pilot stuurde toets {key}",
                            detail=f"Fase: {snapshot.copilot.phase if snapshot.copilot else '—'}",
                        )
                    )
                except ImportError:
                    pass
            return True

        self._pending_keys.appendleft(key)
        self._emit(f"Co-Pilot: {key} wacht op spel-focus", "paused")
        return False

    def _run(self) -> None:
        while not self._stop.is_set():
            settings = self._get_settings()
            snapshot = self._get_snapshot()

            if not settings.send_keys_enabled or snapshot is None or not snapshot.monitoring:
                self._last_phase = None
                self._pending_keys.clear()
            elif snapshot.copilot is not None:
                phase = snapshot.copilot.phase
                area = snapshot.current_area
                keys, ap_next = keys_on_phase_change(
                    previous_phase=self._last_phase,
                    new_phase=phase,
                    send_keys_enabled=True,
                    ap_assumed_on=self._ap_assumed_on,
                    allow_auto_progress_g=settings.allow_auto_progress_g,
                )
                reset_keys, reset_ap = keys_on_area_reset(
                    previous_area=self._last_area,
                    new_area=area,
                    phase=phase,
                    send_keys_enabled=True,
                    ap_assumed_on=self._ap_assumed_on,
                    allow_auto_progress_g=settings.allow_auto_progress_g,
                )
                if reset_keys:
                    self._clear_debounce()
                    keys = reset_keys
                    ap_next = reset_ap
                    self._emit(
                        f"Co-Pilot: reset gedetecteerd (area {self._last_area}→{area})",
                        "status",
                    )
                if keys:
                    self._ap_assumed_on = ap_next
                    self._enqueue_keys(keys)

                if self._pending_keys:
                    next_key = self._pending_keys.popleft()
                    self._send_hotkey(settings, next_key)

                self._last_phase = phase
                if area is not None:
                    self._last_area = area

            self._stop.wait(self._tick_sec)
