"""Live dashboard: party tiles, rates, memory reads."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ic_core.game_state import GameStateService
from ic_core.memory_service import MemoryReading, MemoryService
from ic_ui import theme as ui_theme
from ic_ui.tabs.sources_tab import SourcesTab
from ic_ui.theme import (
    apply_button_icon,
    apply_card_shadow,
    area_progress_bar_stylesheet,
    on_theme_changed,
    status_pill_dot_stylesheet,
    status_pill_stylesheet,
    style_primary_button,
)

if TYPE_CHECKING:
    from ic_core.game_data_service import GameDataService


class DashboardTab(QWidget):
    """Dashboard UI and session stats tracking."""

    payload_updated = Signal(object)
    caption_refresh = Signal()
    api_poll_requested = Signal()

    def __init__(
        self,
        sources_tab: SourcesTab,
        parent: QWidget | None = None,
        *,
        data_service: GameDataService | None = None,
    ) -> None:
        super().__init__(parent)
        self._sources_tab = sources_tab
        self._data = data_service
        self._state = GameStateService(self)
        self._memory = MemoryService(self)
        self._memory.set_ui_hint_provider(self._get_ui_hint)
        self._memory.memory_updated.connect(self._on_memory_updated)
        self._state.state_changed.connect(self._schedule_label_refresh)
        self._state.payload_changed.connect(self.payload_updated.emit)
        self._init_state()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_once)
        self._label_refresh_timer = QTimer(self)
        self._label_refresh_timer.setSingleShot(True)
        self._label_refresh_timer.setInterval(1000)
        self._label_refresh_timer.timeout.connect(self._update_labels)
        self._build_ui()
        on_theme_changed(self._apply_local_theme)

    @property
    def credentials(self):
        return self._dash_credentials

    @credentials.setter
    def credentials(self, value) -> None:
        self._dash_credentials = value

    @property
    def tailer(self):
        return self._dash_tailer

    @property
    def install(self):
        return self._dash_install

    @property
    def last_payload(self):
        return self._state.last_payload

    @property
    def last_api_snap(self):
        return self._state.last_api_snap

    @property
    def api_detail(self) -> str:
        return self._state.api_detail

    @api_detail.setter
    def api_detail(self, value: str) -> None:
        self._state.api_detail = value

    @property
    def tracker(self):
        return self._state.tracker

    @property
    def game_state(self) -> GameStateService:
        return self._state

    def api_log_path(self) -> Path | None:
        if self._dash_install and self._dash_install.web_request_log:
            return Path(self._dash_install.web_request_log)
        return None

    def refresh_credentials_from_log(self) -> bool:
        if self._data is not None:
            self._data.configure(log_path=self.api_log_path(), credentials=self._dash_credentials)
            ok = self._data.refresh_credentials(force=True)
            if self._data.credentials is not None:
                self._dash_credentials = self._data.credentials
            return ok
        if self._dash_install is None or self._dash_credentials is None:
            self.refresh_install()
        if self._dash_install and self._dash_install.web_request_log:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(Path(self._dash_install.web_request_log))
            if fresh is not None:
                self._dash_credentials = fresh
        return self._dash_credentials is not None

    def ingest_api_result(self, result: dict) -> None:
        payload = result.get("payload")
        snap = result.get("snap")
        refreshed_snap = None
        if snap is not None:
            if payload is not None:
                refreshed_snap = self._refresh_snapshot(snap, payload)
            else:
                refreshed_snap = snap
        # Memory is owned by MemoryService — use latest reading, never read on UI thread.
        mem = self._memory.latest
        mem_area = mem.area if mem is not None else None
        mem_gems = mem.gems if mem is not None else None
        self._state.ingest_api_result(
            result,
            active=self._dash_active,
            refreshed_snap=refreshed_snap,
            mem_area=mem_area if self._dash_active else None,
            mem_gems=mem_gems if self._dash_active else None,
        )
        if self._pending_session_seed and refreshed_snap is not None:
            self._pending_session_seed = False
            self._set_dash_status("Dashboard active.")
            self._schedule_label_refresh()

    def disconnect_memory(self) -> None:
        self._memory.stop()

    def _schedule_label_refresh(self) -> None:
        if not self._label_refresh_timer.isActive():
            self._label_refresh_timer.start()

    def caption_party(self):
        latest = self._state.tracker.latest if self._state.tracker is not None else None
        return self._caption_party(latest)

    def auto_start(self) -> None:
        self._auto_start()

    def stop(self) -> None:
        self._stop()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # Header above tiles: actions left, status pills + detail right.
        header = QHBoxLayout()
        header.setSpacing(16)
        header.setAlignment(Qt.AlignmentFlag.AlignTop)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self._toggle_btn = QPushButton("Start dashboard")
        style_primary_button(self._toggle_btn)
        apply_button_icon(self._toggle_btn, "start")
        self._toggle_btn.clicked.connect(self._toggle)
        refresh_btn = QPushButton("Search again")
        apply_button_icon(refresh_btn, "refresh")
        refresh_btn.clicked.connect(self.refresh_install)
        reset_btn = QPushButton("Reset session")
        apply_button_icon(reset_btn, "reset")
        reset_btn.clicked.connect(self.reset_session)
        controls.addWidget(self._toggle_btn)
        controls.addWidget(reset_btn)
        controls.addWidget(refresh_btn)
        header.addLayout(controls, stretch=0)

        header.addStretch(1)

        status_col = QVBoxLayout()
        status_col.setSpacing(6)
        status_col.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._status_pills: dict[str, dict[str, QWidget]] = {}
        for key, tooltip in (
            ("api", "Status of CNE API / webRequestLog credentials"),
            ("memory", "Live memory read from the game process"),
            ("session", "Dashboard session and last successful update"),
        ):
            frame, dot, text = self._make_status_pill(tooltip)
            self._status_pills[key] = {"frame": frame, "dot": dot, "text": text}
            status_row.addWidget(frame)
        status_col.addLayout(status_row)

        self._dash_detail = QLabel("")
        self._dash_detail.setWordWrap(True)
        self._dash_detail.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._dash_detail.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; font-size: 12px;")
        status_col.addWidget(self._dash_detail)
        header.addLayout(status_col, stretch=0)
        root.addLayout(header)

        self._dash_status = QLabel("")
        self._dash_status.setWordWrap(True)
        self._dash_status.setStyleSheet(f"color: {ui_theme.TEXT_BODY};")
        self._dash_status.hide()
        root.addWidget(self._dash_status)

        # Transparent scroll host — the rounded panel hugs the tiles; leftover
        # viewport space stays empty (page/tab background), not a giant black box.
        self._dash_parties_container = QWidget()
        self._dash_parties_container.setObjectName("partiesScrollHost")
        self._dash_parties_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._dash_parties_container.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, False
        )
        parties_outer = QVBoxLayout(self._dash_parties_container)
        parties_outer.setContentsMargins(0, 0, 0, 0)
        parties_outer.setSpacing(0)
        parties_outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._dash_parties_panel = QFrame()
        self._dash_parties_panel.setObjectName("partiesPanel")
        self._dash_parties_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._dash_parties_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        panel_layout = QVBoxLayout(self._dash_parties_panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(0)

        self._dash_parties_grid_host = QWidget()
        self._dash_parties_grid_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self._dash_parties_layout = QGridLayout(self._dash_parties_grid_host)
        self._dash_parties_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        # Extra margin for QGraphicsDropShadowEffect so shadows are not clipped.
        self._dash_parties_layout.setContentsMargins(4, 4, 4, 8)
        self._dash_parties_layout.setHorizontalSpacing(16)
        self._dash_parties_layout.setVerticalSpacing(10)
        self._dash_parties_layout.setColumnStretch(0, 1)
        self._dash_parties_layout.setColumnStretch(1, 1)
        self._dash_parties_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        panel_layout.addWidget(self._dash_parties_grid_host)

        parties_outer.addWidget(self._dash_parties_panel, 0, Qt.AlignmentFlag.AlignTop)
        parties_outer.addStretch(1)
        self._dash_party_widgets: dict[int, dict[str, QWidget]] = {}

        self._parties_scroll = QScrollArea()
        self._parties_scroll.setWidgetResizable(True)
        self._parties_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._parties_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._parties_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._parties_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._parties_scroll.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._parties_scroll.setWidget(self._dash_parties_container)
        root.addWidget(self._parties_scroll, stretch=1)

        self._parties_empty = QLabel(
            "No party data yet. Start the dashboard (and the game) to see party cards."
        )
        self._parties_empty.setWordWrap(True)
        self._parties_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._parties_empty.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; padding: 24px;")
        self._parties_empty.hide()
        root.addWidget(self._parties_empty)

    def _set_dash_status(self, text: str = "") -> None:
        """Show a short status only for actionable messages (not idle 'active')."""
        cleaned = (text or "").strip()
        if not cleaned or cleaned.startswith("Dashboard active"):
            self._dash_status.clear()
            self._dash_status.hide()
            return
        self._dash_status.setText(cleaned)
        self._dash_status.show()

    def _make_status_pill(self, tooltip: str) -> tuple[QFrame, QLabel, QLabel]:
        frame = QFrame()
        frame.setObjectName("statusPill")
        frame.setStyleSheet(status_pill_stylesheet())
        frame.setToolTip(tooltip)
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 4, 10, 4)
        row.setSpacing(6)
        dot = QLabel()
        dot.setObjectName("statusPillDot")
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(status_pill_dot_stylesheet(ui_theme.TEXT_MUTED))
        text = QLabel("—")
        text.setObjectName("statusPillText")
        row.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(text, alignment=Qt.AlignmentFlag.AlignVCenter)
        return frame, dot, text

    def _apply_local_theme(self, _mode: str = "dark") -> None:
        for pill in self._status_pills.values():
            pill["frame"].setStyleSheet(status_pill_stylesheet())
        self._dash_detail.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; font-size: 12px;")
        self._dash_status.setStyleSheet(f"color: {ui_theme.TEXT_BODY};")
        self._parties_empty.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; padding: 24px;")
        self._parties_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        panel = getattr(self, "_dash_parties_panel", None)
        if panel is not None:
            panel.style().unpolish(panel)
            panel.style().polish(panel)
        for widgets in self._dash_party_widgets.values():
            frame = widgets.get("frame")
            if frame is not None:
                is_active = bool(frame.property("partyActive"))
                frame.setObjectName("activePartyCard" if is_active else "partyCard")
                frame.style().unpolish(frame)
                frame.style().polish(frame)
                apply_card_shadow(frame, soft=True)
            progress_bar = widgets.get("modron_progress")
            if progress_bar is not None and progress_bar.isVisible():
                progress_bar.setStyleSheet(
                    area_progress_bar_stylesheet(complete=progress_bar.value() >= 100)
                )
        self._schedule_label_refresh()

    def _init_state(self) -> None:
        self._dash_install = None
        self._dash_tailer = None
        self._dash_credentials = None
        self._dash_active = False
        self._dash_poll_tick = 0
        self._pending_session_seed = False
        self._dash_goal_runs_expanded: dict[int, bool] = {}

    def _get_ui_hint(self) -> int | None:
        raw = (self._sources_tab.ui_hint.text() or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _on_memory_updated(self, reading: MemoryReading) -> None:
        if reading.error and (
            "unavailable" in (reading.detail or "").lower()
            or "niet beschikbaar" in (reading.detail or "")
        ):
            self._state.update_memory_fields(detail=reading.detail)
        else:
            self._state.update_memory_fields(
                area=reading.area,
                gems=reading.gems,
                modron_goal=reading.modron_goal,
                detail=reading.detail,
            )
        if not self._dash_active or self._state.tracker is None:
            self._schedule_label_refresh()
            return
        active_party_index = (
            self._state.tracker.latest.active_party_index
            if self._state.tracker.latest is not None
            else None
        )
        if self._state.apply_memory_reading(
            reading.area,
            reading.gems,
            active=True,
            active_party_index=active_party_index,
        ):
            self._schedule_label_refresh()
        else:
            self._schedule_label_refresh()

    def _refresh_snapshot(self, snap, payload):
        mem_modron = self._state.memory_modron_goal
        latest_mem = self._memory.latest
        if latest_mem is not None and latest_mem.modron_goal is not None:
            mem_modron = latest_mem.modron_goal
            self._state.memory_modron_goal = mem_modron
        try:
            from ic_gamedata.party_display import refresh_snapshot_from_payload
        except ImportError:
            return snap
        if payload is None:
            return snap
        return refresh_snapshot_from_payload(
            snap,
            payload,
            memory_modron_area=mem_modron,
        )

    @staticmethod
    def _format_number(value) -> str:
        if value is None:
            return "—"
        try:
            num = float(value)
        except (TypeError, ValueError):
            return "—"
        if abs(num) >= 1000:
            return f"{num:,.0f}"
        if abs(num) >= 10:
            return f"{num:.1f}"
        return f"{num:.2f}"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = max(int(seconds), 0)
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def _format_rate_window(window_sec: float | None) -> str:
        if window_sec is None:
            return "warming up (<3 min)"
        minutes = max(round(window_sec / 60), 1)
        if minutes >= 15:
            return "15 min window"
        return f"{minutes} min window"

    def _load_tracker(self) -> None:
        self._state.load_tracker()

    def refresh_install(self) -> None:
        try:
            from ic_gamedata.paths import InstallSource, find_game_install
        except ImportError as exc:
            self._sources_tab.install_lbl.setText(f"ic_gamedata missing: {exc}")
            self._sources_tab.log_lbl.setText("—")
            return
        info = find_game_install()
        self._dash_install = info
        if info is None:
            self._sources_tab.install_lbl.setText("Not found (Epic/Steam/manual path)")
            self._sources_tab.log_lbl.setText("—")
            self._set_dash_status("No installation found. Start the game or use a manual path.")
            self._sources_tab.set_feedback(
                "No installation found — enter a manual path or start the game.",
                ok=False,
            )
            self._dash_tailer = None
            return
        source_labels = {
            InstallSource.EPIC: "Epic Games",
            InstallSource.STEAM: "Steam",
            InstallSource.MANUAL: "Manual",
            InstallSource.RUNNING: "Running process",
            InstallSource.UNKNOWN: "Unknown",
        }
        self._sources_tab.install_lbl.setText(f"{source_labels.get(info.source, info.source.value)} — {info.install_dir}")
        self._sources_tab.manual_path.setText(str(info.install_dir))
        if info.web_request_log is None:
            self._sources_tab.log_lbl.setText("webRequestLog.txt not present yet")
            self._dash_tailer = None
            self._dash_credentials = None
            return
        self._sources_tab.log_lbl.setText(str(info.web_request_log))
        try:
            from ic_gamedata.credentials import extract_credentials_from_log
            from ic_gamedata.log_tailer import WebRequestLogTailer
        except ImportError:
            from ic_gamedata import WebRequestLogTailer, extract_credentials_from_log
        self._dash_tailer = WebRequestLogTailer(info.web_request_log)
        self._dash_tailer.bootstrap()
        self._dash_credentials = extract_credentials_from_log(info.web_request_log)
        if self._data is not None:
            self._data.configure(
                log_path=Path(info.web_request_log),
                credentials=self._dash_credentials,
            )
        if self._dash_credentials is not None:
            self._set_dash_status(
                "Ready. API refreshes on game activity (log) or within 30 seconds."
            )
            self._sources_tab.set_feedback("Installation and credentials found.")
            self.api_poll_requested.emit()
        else:
            self._set_dash_status("Log found but no credentials yet.")
            self._sources_tab.set_feedback(
                "Log found, but no credentials yet — play in-game briefly or search again.",
                ok=False,
            )

    def save_manual_path(self) -> None:
        try:
            from ic_gamedata.config_manager import ConfigManager
        except ImportError:
            QMessageBox.critical(self, "Dashboard", "ic_gamedata module missing.")
            return
        raw = (self._sources_tab.manual_path.text() or "").strip()
        try:
            ConfigManager().set_install_path(raw)
        except OSError as exc:
            self._sources_tab.set_feedback(f"Save failed: {exc}", ok=False)
            return
        self.refresh_install()
        if raw:
            self._sources_tab.set_feedback("Manual path saved to config/gamedata.json.")
        else:
            self._sources_tab.set_feedback("Manual path cleared; auto-detect is used.")

    def _seed_session_from_store(self) -> bool:
        """Use latest GameDataService snap if available; otherwise wait for async poll."""
        if self._data is None or self._data.latest is None or self._data.latest.snap is None:
            return False
        snap = self._data.latest.snap
        payload = self._data.latest.payload
        if payload is not None:
            snap = self._refresh_snapshot(snap, payload)
        if self._data.latest.api_detail:
            self._state.api_detail = self._data.latest.api_detail
        if payload is not None:
            self._state.last_payload = payload
        if self._data.latest.api_snap is not None:
            self._state.last_api_snap = self._data.latest.api_snap
        self._state.add_snapshot(snap, api_snapshot=self._state.last_api_snap)
        return True

    def _start(self) -> None:
        if self._dash_active:
            return
        if self._dash_credentials is None and self._dash_tailer is None:
            self.refresh_install()
        self._load_tracker()
        if self._state.tracker is None:
            return
        self._state.reset_tracker()
        seeded = self._seed_session_from_store()
        self._pending_session_seed = not seeded
        self._dash_active = True
        self._dash_poll_tick = 0
        self._toggle_btn.setText("Stop dashboard")
        apply_button_icon(self._toggle_btn, "stop")
        self._memory.start()
        self.api_poll_requested.emit()
        if seeded:
            self._set_dash_status("Dashboard active.")
        else:
            self._set_dash_status("Dashboard active — waiting for API data…")
        self._update_labels()
        self._poll_timer.start()

    def _auto_start(self) -> None:
        if self._dash_active:
            return
        if self._dash_credentials is None and self._dash_tailer is None:
            self.refresh_install()
        self._start()
        if not self._dash_active:
            self._set_dash_status(
                "Dashboard could not start — will retry once Idle Champions is running."
            )
            QTimer.singleShot(15000, self._auto_start)
            return
        if self._state.last_update is None and self._state.memory_area is None:
            self._set_dash_status(
                "Dashboard active — waiting for game data. Start Idle Champions for live rates."
            )

    def _stop(self) -> None:
        self._dash_active = False
        self._pending_session_seed = False
        self._poll_timer.stop()
        self._memory.stop()
        self._toggle_btn.setText("Start dashboard")
        apply_button_icon(self._toggle_btn, "start")
        self._set_dash_status("Dashboard stopped.")

    def _toggle(self) -> None:
        if self._dash_active:
            self._stop()
        else:
            self._start()

    def _poll_once(self) -> None:
        if not self._dash_active:
            return
        self._dash_poll_tick += 1
        # MemoryService polls itself; this timer only refreshes labels periodically.
        self._schedule_label_refresh()



    def _party_from_snapshot(self, snap, party_index: int):
        if snap is None:
            return None
        for party in snap.parties:
            if party.party_index == party_index:
                return party
        return None

    def _caption_party(self, latest):
        if self._state.last_api_snap is not None and self._state.last_api_snap.active_party_index is not None:
            api_party = self._party_from_snapshot(
                self._state.last_api_snap,
                self._state.last_api_snap.active_party_index,
            )
            if api_party is not None:
                return api_party
        return self._active_party(latest)


    def _running_parties(self, latest):
        snap = self._state.last_api_snap if self._state.last_api_snap is not None else latest
        if snap is None:
            return ()
        running = tuple(sorted(snap.running_parties, key=lambda p: p.party_index))
        if running:
            return running
        return tuple(sorted(snap.parties, key=lambda p: p.party_index))

    def _is_active_party(self, party_index: int) -> bool:
        if self._state.last_api_snap is not None and self._state.last_api_snap.active_party_index is not None:
            return party_index == self._state.last_api_snap.active_party_index
        latest = self._state.tracker.latest if self._state.tracker is not None else None
        if latest is not None and latest.active_party_index is not None:
            return party_index == latest.active_party_index
        return False

    def _party_title(self, party_index: int, adventure_id: int | None, is_active: bool) -> str:
        if adventure_id is not None and adventure_id >= 0:
            try:
                from ic_gamedata.adventure_names import adventure_display_name
            except ImportError:
                adventure_display_name = None  # type: ignore[assignment,misc]
            name = (
                adventure_display_name(self._state.last_payload, adventure_id)
                if adventure_display_name is not None
                else None
            )
            adv = f", {name}" if name else f", adventure {adventure_id}"
        else:
            adv = ""
        active = " · active window" if is_active else ""
        return f"Party {party_index}{adv}{active}"

    def _enriched_party(self, tracked):
        api_party = None
        if self._state.last_api_snap is not None:
            api_party = self._party_from_snapshot(
                self._state.last_api_snap,
                tracked.party_index,
            )
        is_active = self._is_active_party(tracked.party_index)
        try:
            from ic_gamedata.dashboard_enrich import enrich_party_for_dashboard
        except ImportError:
            return tracked
        party, cleared = enrich_party_for_dashboard(
            tracked,
            api_party,
            is_active=is_active,
            memory_area=self._state.memory_area if is_active else None,
            memory_gems=self._state.memory_gems if is_active else None,
            clear_stale_memory_gems=True,
        )
        if cleared:
            self._state.clear_stale_memory_gems()
        try:
            from ic_gamedata.party_display import refresh_party_from_payload
        except ImportError:
            return party
        return refresh_party_from_payload(
            party,
            self._state.last_payload,
            memory_modron_area=self._state.memory_modron_goal if is_active else None,
        )

    def _run_duration_sec(self, party) -> float | None:
        if party.seconds_since_reset is None:
            return None
        elapsed = float(party.seconds_since_reset)
        if self._state.last_update is not None:
            elapsed += max(0.0, time.time() - self._state.last_update)
        return elapsed

    def _ensure_party_tile(self, party_index: int) -> dict[str, QWidget]:
        if party_index in self._dash_party_widgets:
            return self._dash_party_widgets[party_index]

        box = QGroupBox(f"Party {party_index}")
        box.setProperty("party_index", party_index)
        box.setObjectName("partyCard")
        # Expanding so a shorter tile grows to the tallest tile in the same row.
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        apply_card_shadow(box, soft=True)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        lbl_area = QLabel("Area: —")
        lbl_modron_progress = QLabel("")
        modron_bar = QProgressBar()
        modron_bar.setRange(0, 100)
        modron_bar.setTextVisible(False)
        modron_bar.setFixedHeight(8)
        modron_bar.setStyleSheet(area_progress_bar_stylesheet())
        modron_bar.hide()
        lbl_modron_progress.hide()
        lbl_run = QLabel("Run: —")
        lbl_gems = QLabel("Gems this run: —")
        lbl_areas_rate = QLabel("Areas/kw: —")
        goal_runs_row = QWidget()
        goal_runs_row_layout = QHBoxLayout(goal_runs_row)
        goal_runs_row_layout.setContentsMargins(0, 0, 0, 0)
        goal_runs_row_layout.setSpacing(6)
        goal_runs_row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_goal_runs = QLabel("")
        lbl_goal_runs.setWordWrap(True)
        btn_goal_runs_clear = QPushButton("Clear")
        btn_goal_runs_clear.setObjectName("compactBtn")
        apply_button_icon(btn_goal_runs_clear, "clear", size=16)
        btn_goal_runs_clear.setToolTip("Clear Modron run history for this party")
        btn_goal_runs_clear.setFixedHeight(24)
        btn_goal_runs_expand = QPushButton("▶")
        btn_goal_runs_expand.setObjectName("compactBtn")
        btn_goal_runs_expand.setFixedSize(24, 24)
        btn_goal_runs_expand.setToolTip("Show earlier Modron runs")
        goal_runs_row_layout.addWidget(lbl_goal_runs, stretch=1)
        goal_runs_row_layout.addWidget(btn_goal_runs_clear, alignment=Qt.AlignmentFlag.AlignVCenter)
        goal_runs_row_layout.addWidget(btn_goal_runs_expand, alignment=Qt.AlignmentFlag.AlignVCenter)
        goal_runs_extra = QWidget()
        goal_runs_extra_layout = QVBoxLayout(goal_runs_extra)
        goal_runs_extra_layout.setContentsMargins(0, 0, 0, 0)
        goal_runs_extra_layout.setSpacing(1)
        lbl_patron = QLabel("")
        lbl_briv = QLabel("")
        lbl_warps = QLabel("")
        lbl_buffs = QLabel("")
        all_labels = (
            lbl_area,
            lbl_run,
            lbl_gems,
            lbl_areas_rate,
            lbl_patron,
            lbl_briv,
            lbl_warps,
            lbl_buffs,
        )
        for widget in all_labels:
            widget.setWordWrap(True)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lbl_modron_progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        for widget in (
            lbl_area,
            lbl_modron_progress,
            modron_bar,
            lbl_run,
            lbl_gems,
            lbl_areas_rate,
        ):
            layout.addWidget(widget)
        layout.addWidget(goal_runs_row)
        goal_runs_row.hide()
        layout.addWidget(goal_runs_extra)
        goal_runs_extra.hide()
        for widget in (lbl_patron, lbl_briv, lbl_warps, lbl_buffs):
            layout.addWidget(widget)
            widget.hide()

        btn_goal_runs_expand.clicked.connect(
            lambda _checked=False, idx=party_index: self._toggle_goal_runs(idx)
        )
        btn_goal_runs_clear.clicked.connect(
            lambda _checked=False, idx=party_index: self._clear_goal_runs(idx)
        )
        widgets: dict[str, QWidget] = {
            "frame": box,
            "area": lbl_area,
            "modron_progress_label": lbl_modron_progress,
            "modron_progress": modron_bar,
            "run": lbl_run,
            "gems": lbl_gems,
            "areas_rate": lbl_areas_rate,
            "goal_runs_row": goal_runs_row,
            "goal_runs": lbl_goal_runs,
            "goal_runs_clear": btn_goal_runs_clear,
            "goal_runs_expand": btn_goal_runs_expand,
            "goal_runs_extra": goal_runs_extra,
            "goal_runs_extra_layout": goal_runs_extra_layout,
            "patron": lbl_patron,
            "briv": lbl_briv,
            "warps": lbl_warps,
            "buffs": lbl_buffs,
        }
        self._dash_party_widgets[party_index] = widgets
        return widgets

    def _active_party(self, latest):
        if latest is None:
            return None
        active_id = latest.active_party_index
        if active_id is not None:
            for party in latest.parties:
                if party.party_index == active_id and party.is_running():
                    return party
        for party in latest.running_parties:
            if party.is_active:
                return party
        running = latest.running_parties
        return running[0] if running else None

    def _adventure_name(self, adventure_id: int | None) -> str | None:
        if adventure_id is None or adventure_id < 0:
            return None
        try:
            from ic_gamedata.adventure_names import adventure_display_name
        except ImportError:
            return None
        return adventure_display_name(self._state.last_payload, adventure_id)

    @staticmethod
    def _apply_optional_label(label: QLabel, text: str | None) -> None:
        if text:
            label.setText(text)
            label.show()
        else:
            label.hide()

    def _toggle_goal_runs(self, party_index: int) -> None:
        expanded = self._dash_goal_runs_expanded.get(party_index, False)
        self._dash_goal_runs_expanded[party_index] = not expanded
        widgets = self._dash_party_widgets.get(party_index)
        if widgets is None:
            return
        extra = widgets.get("goal_runs_extra")
        expand_btn = widgets.get("goal_runs_expand")
        if extra is not None:
            extra.setVisible(self._dash_goal_runs_expanded[party_index])
        if expand_btn is not None:
            expand_btn.setText("▼" if self._dash_goal_runs_expanded[party_index] else "▶")

    def _clear_goal_runs(self, party_index: int) -> None:
        reply = QMessageBox.question(
            self,
            "Clear Modron runs",
            f"Clear all saved Modron run times for party {party_index}?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._state.clear_goal_run_history(party_index)
        self._dash_goal_runs_expanded[party_index] = False
        self._update_labels()

    def _goal_run_label_style(self, unreliable: bool) -> str:
        color = ui_theme.FEAT_OWNED if unreliable else ui_theme.TEXT_BADGE
        return f"color: {color};"

    def _apply_goal_runs(self, widgets: dict[str, QWidget], view) -> None:
        summary = view.goal_runs_summary
        summary_unreliable = getattr(view, "goal_runs_summary_unreliable", False)
        row = widgets.get("goal_runs_row")
        label = widgets.get("goal_runs")
        expand_btn = widgets.get("goal_runs_expand")
        extra = widgets.get("goal_runs_extra")
        extra_layout = widgets.get("goal_runs_extra_layout")
        if (
            summary is None
            or row is None
            or label is None
            or expand_btn is None
            or extra is None
            or extra_layout is None
        ):
            if row is not None:
                row.hide()
            if extra is not None:
                extra.hide()
            return

        label.setText(summary)
        label.setStyleSheet(self._goal_run_label_style(summary_unreliable))
        row.show()

        while extra_layout.count():
            item = extra_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for line, unreliable in view.goal_runs_extra:
            line_label = QLabel(line)
            line_label.setWordWrap(True)
            line_label.setStyleSheet(self._goal_run_label_style(unreliable))
            extra_layout.addWidget(line_label)

        has_extra = bool(view.goal_runs_extra)
        expand_btn.setVisible(has_extra)
        if not has_extra:
            extra.hide()
            expand_btn.setText("▶")
            return

        party_index = widgets["frame"].property("party_index")
        expanded = (
            self._dash_goal_runs_expanded.get(party_index, False)
            if party_index is not None
            else False
        )
        expand_btn.setText("▼" if expanded else "▶")
        extra.setVisible(expanded)

    def _apply_party_tile(self, widgets: dict[str, QWidget], view, *, is_active: bool = False) -> None:
        widgets["frame"].setTitle(view.title)
        frame = widgets["frame"]
        frame.setProperty("partyActive", is_active)
        frame.setObjectName("activePartyCard" if is_active else "partyCard")
        frame.style().unpolish(frame)
        frame.style().polish(frame)
        apply_card_shadow(frame, soft=True)
        widgets["area"].setText(view.area)
        widgets["run"].setText(view.run)
        widgets["gems"].setText(view.gems)
        widgets["areas_rate"].setText(view.areas_rate)
        progress_bar = widgets.get("modron_progress")
        progress_label = widgets.get("modron_progress_label")
        if progress_bar is not None and progress_label is not None:
            if view.modron_progress_pct is not None:
                progress_bar.setValue(view.modron_progress_pct)
                progress_bar.setStyleSheet(
                    area_progress_bar_stylesheet(complete=view.modron_progress_pct >= 100)
                )
                progress_bar.show()
                if view.modron_progress_text:
                    progress_label.setText(view.modron_progress_text)
                    progress_label.show()
                else:
                    progress_label.hide()
            else:
                progress_bar.hide()
                progress_label.hide()
        self._apply_goal_runs(widgets, view)
        self._apply_optional_label(widgets["patron"], view.patron)
        self._apply_optional_label(widgets["briv"], view.briv)
        self._apply_optional_label(widgets["warps"], view.warps)
        self._apply_optional_label(widgets["buffs"], view.buffs)

    def _update_status_pills(self) -> None:
        api_text, api_color, mem_text, mem_color, session_text, session_color = (
            self._state.connection_status(
                active=self._dash_active,
                credentials_ok=self._dash_credentials is not None,
            )
        )
        for key, text, color in (
            ("api", api_text, api_color),
            ("memory", mem_text, mem_color),
            ("session", session_text, session_color),
        ):
            pill = self._status_pills[key]
            pill["text"].setText(text)
            pill["dot"].setStyleSheet(status_pill_dot_stylesheet(color))
            pill["frame"].setStyleSheet(status_pill_stylesheet())

    def _update_labels(self) -> None:
        tracker = self._state.tracker
        if tracker is None:
            self._parties_scroll.hide()
            self._parties_empty.show()
            return
        stats = tracker.compute()
        latest = tracker.latest
        detail_parts = []
        if self._state.memory_detail:
            detail_parts.append(self._state.memory_detail)
        if self._state.api_detail:
            detail_parts.append(self._state.api_detail)
        if self._state.last_update:
            detail_parts.append(f"last update: {time.strftime('%H:%M:%S', time.localtime(self._state.last_update))}")
        self._dash_detail.setText(" · ".join(detail_parts))
        self._update_status_pills()

        self.caption_refresh.emit()

        party_stats_map = {p.party_index: p for p in stats.parties} if stats else {}
        base_parties = self._running_parties(latest)
        seen: set[int] = set()
        has_parties = bool(base_parties)
        self._parties_scroll.setVisible(has_parties)
        self._parties_empty.setVisible(not has_parties)

        for tile_index, base in enumerate(base_parties):
            tracked = None
            if latest is not None:
                for party in latest.parties:
                    if party.party_index == base.party_index:
                        tracked = party
                        break
            if tracked is None:
                tracked = base
            party = self._enriched_party(tracked)
            seen.add(party.party_index)
            widgets = self._ensure_party_tile(party.party_index)
            tile = widgets["frame"]
            is_active = self._is_active_party(party.party_index)
            self._dash_parties_layout.removeWidget(tile)
            # Always one column wide (same as tiles above). Grid row height matches
            # the tallest tile; Expanding policy equalizes heights within the row.
            self._dash_parties_layout.addWidget(
                tile, tile_index // 2, tile_index % 2
            )

            ps = party_stats_map.get(party.party_index)
            try:
                from ic_gamedata.dashboard_enrich import resolve_dashboard_gems
            except ImportError:
                resolve_dashboard_gems = None  # type: ignore[assignment]
            if resolve_dashboard_gems is not None:
                gems, gem_prefix = resolve_dashboard_gems(
                    is_active=is_active,
                    memory_gems=self._state.memory_gems if is_active else None,
                    api_gems=party.gems_this_reset,
                    tracked_gems=ps.gems_this_reset if ps is not None else None,
                    tracked_estimated=bool(ps.gems_estimated) if ps is not None else False,
                    area=party.current_area,
                )
            else:
                gems = ps.gems_this_reset if ps is not None else party.gems_this_reset
                gem_prefix = "~" if ps is not None and ps.gems_estimated else ""

            try:
                from ic_gamedata.dashboard_tiles import build_party_tile_view
            except ImportError:
                build_party_tile_view = None  # type: ignore[assignment,misc]

            if build_party_tile_view is not None:
                view = build_party_tile_view(
                    party,
                    ps=ps,
                    is_active=is_active,
                    adventure_name=self._adventure_name(party.adventure_id),
                    run_sec=self._run_duration_sec(party),
                    gems=gems,
                    gem_prefix=gem_prefix,
                    format_number=self._format_number,
                    format_duration=self._format_duration,
                    format_rate_window=self._format_rate_window,
                    goal_run_history=tracker.goal_run_history(party.party_index),
                )
                self._apply_party_tile(widgets, view, is_active=is_active)
            else:
                tile.setTitle(self._party_title(party.party_index, party.adventure_id, is_active))
                widgets["area"].setText(
                    f"Area: {party.current_area if party.current_area is not None else '—'}"
                )

        for idx in list(self._dash_party_widgets):
            if idx not in seen:
                widget = self._dash_party_widgets[idx]["frame"]
                self._dash_parties_layout.removeWidget(widget)
                widget.deleteLater()
                del self._dash_party_widgets[idx]

    def reset_session(self) -> None:
        self._load_tracker()
        self._state.reset_tracker()
        self._pending_session_seed = True
        if self._dash_active:
            self._memory.request_read()
        self.api_poll_requested.emit()
        if self._seed_session_from_store():
            self._pending_session_seed = False
            self._set_dash_status("Session reset — new baseline set.")
        else:
            self._set_dash_status("Session reset — waiting for fresh API data…")
        self._update_labels()

