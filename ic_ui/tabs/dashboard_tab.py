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
from ic_ui.theme import apply_card_shadow, area_progress_bar_stylesheet, on_theme_changed, status_pill_stylesheet

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
            ok = self._data.refresh_credentials()
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
            self._dash_status.setText("Dashboard actief.")
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

        self._dash_parties_container = QWidget()
        self._dash_parties_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._dash_parties_layout = QGridLayout(self._dash_parties_container)
        # Margins leave room for QGraphicsDropShadowEffect (otherwise cards clip).
        self._dash_parties_layout.setContentsMargins(10, 10, 10, 14)
        self._dash_parties_layout.setHorizontalSpacing(16)
        self._dash_parties_layout.setVerticalSpacing(16)
        self._dash_parties_layout.setColumnStretch(0, 1)
        self._dash_parties_layout.setColumnStretch(1, 1)
        self._dash_party_widgets: dict[int, dict[str, QWidget]] = {}

        parties_scroll = QScrollArea()
        parties_scroll.setWidgetResizable(True)
        parties_scroll.setFrameShape(QFrame.Shape.NoFrame)
        parties_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        parties_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        parties_scroll.setWidget(self._dash_parties_container)
        root.addWidget(parties_scroll, stretch=1)

        self._dash_detail = QLabel("")
        self._dash_detail.setWordWrap(True)
        root.addWidget(self._dash_detail)

        controls = QHBoxLayout()
        self._toggle_btn = QPushButton("Start dashboard")
        self._toggle_btn.clicked.connect(self._toggle)
        refresh_btn = QPushButton("Opnieuw zoeken")
        refresh_btn.clicked.connect(self.refresh_install)
        reset_btn = QPushButton("Reset sessie")
        reset_btn.clicked.connect(self.reset_session)
        controls.addWidget(self._toggle_btn)
        controls.addWidget(reset_btn)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        status_row = QHBoxLayout()
        self._status_api = QLabel("API: —")
        self._status_memory = QLabel("Memory: —")
        self._status_session = QLabel("Sessie: —")
        for pill in (self._status_api, self._status_memory, self._status_session):
            pill.setStyleSheet(status_pill_stylesheet())
            status_row.addWidget(pill)
        status_row.addStretch(1)
        root.addLayout(status_row)

        self._dash_status = QLabel(
            "Dashboard gebruikt hybride API-refresh (log-wijziging + max. 30 s). Start voor memory-updates."
        )
        self._dash_status.setWordWrap(True)
        root.addWidget(self._dash_status)

    def _apply_local_theme(self, _mode: str = "dark") -> None:
        for pill in (self._status_api, self._status_memory, self._status_session):
            pill.setStyleSheet(status_pill_stylesheet())
        for widgets in self._dash_party_widgets.values():
            frame = widgets.get("frame")
            if frame is not None:
                apply_card_shadow(frame)
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
        if reading.error and "niet beschikbaar" in (reading.detail or ""):
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
            return "warmt op (<3 min)"
        minutes = max(round(window_sec / 60), 1)
        if minutes >= 15:
            return "15 min venster"
        return f"{minutes} min venster"

    def _load_tracker(self) -> None:
        self._state.load_tracker()

    def refresh_install(self) -> None:
        try:
            from ic_gamedata.paths import InstallSource, find_game_install
        except ImportError as exc:
            self._sources_tab.install_lbl.setText(f"ic_gamedata ontbreekt: {exc}")
            self._sources_tab.log_lbl.setText("—")
            return
        info = find_game_install()
        self._dash_install = info
        if info is None:
            self._sources_tab.install_lbl.setText("Niet gevonden (Epic/Steam/handmatig pad)")
            self._sources_tab.log_lbl.setText("—")
            self._dash_status.setText("Geen installatie gevonden. Start het spel of gebruik handmatig pad.")
            self._dash_tailer = None
            return
        source_labels = {
            InstallSource.EPIC: "Epic Games",
            InstallSource.STEAM: "Steam",
            InstallSource.MANUAL: "Handmatig",
            InstallSource.UNKNOWN: "Onbekend",
        }
        self._sources_tab.install_lbl.setText(f"{source_labels.get(info.source, info.source.value)} — {info.install_dir}")
        self._sources_tab.manual_path.setText(str(info.install_dir))
        if info.web_request_log is None:
            self._sources_tab.log_lbl.setText("webRequestLog.txt nog niet aanwezig")
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
            self._dash_status.setText(
                "Klaar. API ververst bij spelactiviteit (log) en anders binnen 30 seconden."
            )
            self.api_poll_requested.emit()
        else:
            self._dash_status.setText("Log gevonden maar nog geen credentials.")

    def save_manual_path(self) -> None:
        try:
            from ic_gamedata.config_manager import ConfigManager
        except ImportError:
            QMessageBox.critical(self, "Dashboard", "ic_gamedata module ontbreekt.")
            return
        raw = (self._sources_tab.manual_path.text() or "").strip()
        try:
            ConfigManager().set_install_path(raw)
        except OSError as exc:
            QMessageBox.critical(self, "Dashboard", f"Kon config niet opslaan:\n{exc}")
            return
        self.refresh_install()
        if raw:
            QMessageBox.information(self, "Dashboard", "Handmatig pad opgeslagen in config/gamedata.json")

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
        self._memory.start()
        self.api_poll_requested.emit()
        if seeded:
            self._dash_status.setText("Dashboard actief.")
        else:
            self._dash_status.setText("Dashboard actief — wachten op API-data…")
        self._update_labels()
        self._poll_timer.start()

    def _auto_start(self) -> None:
        if self._dash_active:
            return
        if self._dash_credentials is None and self._dash_tailer is None:
            self.refresh_install()
        self._start()
        if not self._dash_active:
            self._dash_status.setText(
                "Dashboard kon niet starten — opnieuw proberen zodra Idle Champions draait."
            )
            QTimer.singleShot(15000, self._auto_start)
            return
        if self._state.last_update is None and self._state.memory_area is None:
            self._dash_status.setText(
                "Dashboard actief — wachten op speldata. Start Idle Champions voor live rates."
            )

    def _stop(self) -> None:
        self._dash_active = False
        self._pending_session_seed = False
        self._poll_timer.stop()
        self._memory.stop()
        self._toggle_btn.setText("Start dashboard")
        self._dash_status.setText("Dashboard gestopt.")

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
        active = " · actief venster" if is_active else ""
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
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        apply_card_shadow(box)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(6)
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
        lbl_gems = QLabel("Gems deze run: —")
        lbl_areas_rate = QLabel("Areas/kw: —")
        goal_runs_row = QWidget()
        goal_runs_row_layout = QHBoxLayout(goal_runs_row)
        goal_runs_row_layout.setContentsMargins(0, 0, 0, 0)
        lbl_goal_runs = QLabel("")
        btn_goal_runs_clear = QPushButton("Wis")
        btn_goal_runs_clear.setFixedWidth(40)
        btn_goal_runs_clear.setToolTip("Wis Modron-run historie voor deze party")
        btn_goal_runs_expand = QPushButton("▶")
        btn_goal_runs_expand.setFixedWidth(28)
        btn_goal_runs_expand.setToolTip("Toon eerdere Modron-runs")
        goal_runs_row_layout.addWidget(lbl_goal_runs, stretch=1)
        goal_runs_row_layout.addWidget(btn_goal_runs_clear)
        goal_runs_row_layout.addWidget(btn_goal_runs_expand)
        goal_runs_extra = QWidget()
        goal_runs_extra_layout = QVBoxLayout(goal_runs_extra)
        goal_runs_extra_layout.setContentsMargins(0, 0, 0, 0)
        goal_runs_extra_layout.setSpacing(2)
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
            "Modron-runs wissen",
            f"Alle opgeslagen Modron-run tijden voor party {party_index} wissen?\n"
            "Dit kan niet ongedaan worden gemaakt.",
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

    def _apply_party_tile(self, widgets: dict[str, QWidget], view) -> None:
        widgets["frame"].setTitle(view.title)
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
        for pill, text, color in (
            (self._status_api, api_text, api_color),
            (self._status_memory, mem_text, mem_color),
            (self._status_session, session_text, session_color),
        ):
            pill.setText(text)
            pill.setStyleSheet(
                f"font-size: 11px; color: {ui_theme.TEXT_BADGE}; background: {ui_theme.BG_BADGE}; "
                f"border-left: 4px solid {color}; border-radius: 10px; padding: 4px 10px;"
            )

    def _update_labels(self) -> None:
        tracker = self._state.tracker
        if tracker is None:
            return
        stats = tracker.compute()
        latest = tracker.latest
        detail_parts = []
        if self._state.memory_detail:
            detail_parts.append(self._state.memory_detail)
        if self._state.api_detail:
            detail_parts.append(self._state.api_detail)
        if self._state.last_update:
            detail_parts.append(f"laatste update: {time.strftime('%H:%M:%S', time.localtime(self._state.last_update))}")
        self._dash_detail.setText(" · ".join(detail_parts))
        self._update_status_pills()

        self.caption_refresh.emit()

        party_stats_map = {p.party_index: p for p in stats.parties} if stats else {}
        base_parties = self._running_parties(latest)
        seen: set[int] = set()

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
            self._dash_parties_layout.addWidget(tile, tile_index // 2, tile_index % 2)

            ps = party_stats_map.get(party.party_index)
            use_memory_gems = is_active and self._state.memory_gems is not None
            if use_memory_gems and not (
                party.gems_this_reset is not None
                and party.current_area is not None
                and party.current_area < 40
                and self._state.memory_gems > party.gems_this_reset + 50
            ):
                gems = self._state.memory_gems
                gem_prefix = ""
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
                self._apply_party_tile(widgets, view)
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
            self._dash_status.setText("Sessie gereset — nieuwe baseline gezet.")
        else:
            self._dash_status.setText("Sessie gereset — wachten op verse API-data…")
        self._update_labels()

