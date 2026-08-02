"""Central hub for live game data shared across dashboard and advisor tabs."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal


class GameStateService(QObject):
    """Owns session tracker state and merged API/memory readings."""

    state_changed = Signal()
    payload_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.tracker = None
        self.last_payload: dict | None = None
        self.last_api_snap = None
        self.api_detail: str = ""
        self.last_update: float | None = None
        self.memory_area: int | None = None
        self.memory_gems: int | None = None
        self.memory_modron_goal: int | None = None
        self.memory_detail: str = ""

    def load_tracker(self) -> None:
        if self.tracker is not None:
            return
        try:
            from ic_gamedata.stats import StatsTracker
        except ImportError:
            from ic_gamedata import StatsTracker
        self.tracker = StatsTracker()

    def reset_tracker(self) -> None:
        if self.tracker is not None:
            self.tracker.reset()

    def update_memory_fields(
        self,
        *,
        area: int | None = None,
        gems: int | None = None,
        modron_goal: int | None = None,
        detail: str | None = None,
    ) -> None:
        if area is not None:
            self.memory_area = area
        if gems is not None:
            self.memory_gems = gems
        if modron_goal is not None:
            self.memory_modron_goal = modron_goal
        if detail is not None:
            self.memory_detail = detail

    def clear_stale_memory_gems(self) -> None:
        self.memory_gems = None

    def ingest_api_result(
        self,
        result: dict,
        *,
        active: bool,
        refreshed_snap,
        mem_area: int | None,
        mem_gems: int | None,
    ) -> None:
        payload = result.get("payload")
        api_snap = result.get("api_snap")
        snap = result.get("snap")
        api_detail = result.get("api_detail")

        if api_detail:
            self.api_detail = api_detail
        if payload is not None:
            self.last_payload = payload
            self.payload_changed.emit(payload)
        if api_snap is not None:
            self.last_api_snap = api_snap

        if refreshed_snap is not None:
            snap = refreshed_snap
        if snap is not None:
            self.last_update = time.time()
            if active and self.tracker is not None:
                if mem_area is not None or mem_gems is not None:
                    self.tracker.add_memory_area(
                        mem_area,
                        gems=mem_gems,
                        active_party_index=snap.active_party_index,
                    )
                self.tracker.add_snapshot(snap, api_snapshot=api_snap)

        self.state_changed.emit()

    def apply_memory_reading(
        self,
        mem_area: int | None,
        mem_gems: int | None,
        *,
        active: bool,
        active_party_index: int | None,
    ) -> bool:
        if not active or self.tracker is None:
            return False
        if mem_area is None and mem_gems is None:
            return False
        self.tracker.add_memory_area(
            mem_area,
            gems=mem_gems,
            active_party_index=active_party_index,
        )
        self.state_changed.emit()
        return True

    def add_snapshot(self, snap, *, api_snapshot=None) -> None:
        if self.tracker is None:
            return
        self.tracker.add_snapshot(snap, api_snapshot=api_snapshot)
        self.last_update = time.time()
        self.state_changed.emit()

    def connection_status(self, *, active: bool, credentials_ok: bool) -> tuple[str, str, str, str, str, str]:
        """Return api/memory/session label and color pairs."""
        from ic_ui.theme import STATUS_IDLE, SUCCESS, WARN

        if not credentials_ok:
            api_text, api_color = "API: geen credentials", WARN
        elif "ok" in self.api_detail.lower() or "log" in self.api_detail.lower():
            api_text, api_color = f"API: {self.api_detail or 'ok'}", SUCCESS
        elif self.api_detail:
            api_text, api_color = f"API: {self.api_detail}", WARN
        else:
            api_text, api_color = "API: wachten…", STATUS_IDLE

        if "niet beschikbaar" in self.memory_detail.lower() or "geen offsets" in self.memory_detail.lower():
            mem_text, mem_color = "Memory: offline", WARN
        elif self.memory_area is not None or self.memory_gems is not None:
            mem_text, mem_color = "Memory: live", SUCCESS
        elif self.memory_detail:
            mem_text, mem_color = "Memory: geen data", STATUS_IDLE
        else:
            mem_text, mem_color = "Memory: —", STATUS_IDLE

        if active:
            if self.last_update is not None:
                age = max(0, int(time.time() - self.last_update))
                session_text, session_color = f"Sessie: actief ({age}s)", SUCCESS
            else:
                session_text, session_color = "Sessie: actief", SUCCESS
        else:
            session_text, session_color = "Sessie: gestopt", STATUS_IDLE

        return api_text, api_color, mem_text, mem_color, session_text, session_color
