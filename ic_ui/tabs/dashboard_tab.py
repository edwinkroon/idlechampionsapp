"""Live dashboard: party tiles, rates, memory reads."""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ic_core.game_state import GameStateService
from ic_ui.tabs.sources_tab import SourcesTab
from ic_ui.theme import BG_BADGE, BUD_BAR, TEXT_BADGE


class DashboardTab(QWidget):
    """Dashboard UI and session stats tracking."""

    payload_updated = Signal(object)
    caption_refresh = Signal()
    api_poll_requested = Signal()

    def __init__(self, sources_tab: SourcesTab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources_tab = sources_tab
        self._state = GameStateService(self)
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
        mem_area, mem_gems = None, None
        if self._dash_active and refreshed_snap is not None:
            mem_area, mem_gems = self._read_memory()
        self._state.ingest_api_result(
            result,
            active=self._dash_active,
            refreshed_snap=refreshed_snap,
            mem_area=mem_area,
            mem_gems=mem_gems,
        )

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

    def disconnect_memory(self) -> None:
        self._disconnect_memory()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._dash_parties_container = QWidget()
        self._dash_parties_layout = QGridLayout(self._dash_parties_container)
        self._dash_parties_layout.setContentsMargins(0, 0, 0, 0)
        self._dash_parties_layout.setHorizontalSpacing(12)
        self._dash_parties_layout.setVerticalSpacing(12)
        self._dash_parties_layout.setColumnStretch(0, 1)
        self._dash_parties_layout.setColumnStretch(1, 1)
        self._dash_party_widgets: dict[int, dict[str, QWidget]] = {}
        root.addWidget(self._dash_parties_container, stretch=1)

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
            pill.setStyleSheet(
                f"font-size: 11px; color: {TEXT_BADGE}; background: {BG_BADGE}; "
                f"border: none; border-radius: 10px; padding: 4px 10px;"
            )
            status_row.addWidget(pill)
        status_row.addStretch(1)
        root.addLayout(status_row)

        self._dash_status = QLabel("Dashboard gebruikt gecentraliseerde API-poll (elke 5 s). Start voor memory-updates.")
        self._dash_status.setWordWrap(True)
        root.addWidget(self._dash_status)

        root.addStretch(1)

    def _init_state(self) -> None:
        self._dash_install = None
        self._dash_tailer = None
        self._dash_credentials = None
        self._dash_active = False
        self._dash_poll_tick = 0
        self._dash_resolver = None
        self._dash_result_queue: queue.Queue[dict] = queue.Queue(maxsize=2)
        self._dash_fetch_inflight = False
        self._dash_fetch_thread: threading.Thread | None = None
        self._dash_goal_runs_expanded: dict[int, bool] = {}

    def _get_ui_hint(self) -> int | None:
        raw = (self._sources_tab.ui_hint.text() or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _read_memory(self, ui_hint: int | None = None) -> tuple[int | None, int | None]:
        try:
            from ic_reader.resolver import create_resolver
        except ImportError:
            self._state.update_memory_fields(detail="ic_reader niet beschikbaar (pip install psutil)")
            return None, None
        try:
            if self._dash_resolver is None:
                self._dash_resolver = create_resolver(debug=False)
                self._dash_resolver.connect()
            resolved_area = self._dash_resolver.resolve_current_area(
                ui_hint_area=self._get_ui_hint() if ui_hint is None else ui_hint
            )
            resolved_gems = self._dash_resolver.resolve_gems_this_reset()
        except Exception as exc:
            self._state.update_memory_fields(detail=str(exc))
            return None, None

        area = int(resolved_area.value) if resolved_area.value is not None else None
        gems = int(resolved_gems.value) if resolved_gems.value is not None else None
        parts: list[str] = []
        if area is not None:
            parts.append(f"area={area} ({resolved_area.candidate_id or '?'}, {resolved_area.confidence:.1f})")
        if gems is not None:
            parts.append(f"gems={gems} ({resolved_gems.candidate_id or '?'}, {resolved_gems.confidence:.1f})")
        detail = "memory: " + " · ".join(parts) if parts else "memory: geen offsets/data"
        self._state.update_memory_fields(area=area, gems=gems, detail=detail)
        return area, gems

    def _read_modron_reset_area(self) -> int | None:
        try:
            from ic_reader.resolver import create_resolver
        except ImportError:
            return None
        try:
            if self._dash_resolver is None:
                self._dash_resolver = create_resolver(debug=False)
                self._dash_resolver.connect()
            resolved = self._dash_resolver.resolve_modron_reset_area()
            if resolved.value is None:
                return None
            return int(resolved.value)
        except Exception:
            return None

    def _refresh_snapshot(self, snap, payload):
        mem_modron = self._read_modron_reset_area()
        if mem_modron is not None:
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

    def _disconnect_memory(self) -> None:
        if self._dash_resolver is not None:
            try:
                self._dash_resolver.disconnect()
            except Exception:
                pass
            self._dash_resolver = None

    @staticmethod
    def _format_gold(value) -> str:
        try:
            from ic_gamedata.formatting import format_gold
        except ImportError:
            return DashboardTab._format_number(value)
        return format_gold(value)

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
        if self._dash_credentials is not None:
            self._dash_status.setText("Klaar. API wordt elke 5 seconden automatisch ververst.")
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

    def _fetch_snapshot(self):
        log_path = self._api_log_path()
        if log_path is not None:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(log_path)
            if fresh is not None:
                self._dash_credentials = fresh
        try:
            from ic_gamedata.snapshot_fetch import fetch_merged_snapshot
        except ImportError:
            from ic_gamedata import fetch_merged_snapshot
        credentials, payload, api_snap, snap, _err, api_detail = fetch_merged_snapshot(
            self._dash_credentials,
            log_path,
            self._dash_tailer,
        )
        if credentials is not None:
            self._dash_credentials = credentials
        if api_detail:
            self._state.api_detail = api_detail
        if payload is not None:
            self._state.last_payload = payload
        if api_snap is not None:
            self._state.last_api_snap = api_snap
        if snap is not None:
            self._state.last_update = time.time()
        return snap

    def _start(self) -> None:
        if self._dash_active:
            return
        if self._dash_credentials is None and self._dash_tailer is None:
            self.refresh_install()
        self._load_tracker()
        if self._state.tracker is None:
            return
        self._state.reset_tracker()
        snap = self._fetch_snapshot()
        if snap is not None and self._state.last_payload is not None:
            snap = self._refresh_snapshot(snap, self._state.last_payload)
        if snap is not None:
            self._state.add_snapshot(snap, api_snapshot=self._state.last_api_snap)
        mem_area, mem_gems = self._read_memory()
        if mem_area is not None or mem_gems is not None:
            self._state.apply_memory_reading(
                mem_area,
                mem_gems,
                active=True,
                active_party_index=snap.active_party_index if snap is not None else None,
            )
        self._dash_active = True
        self._dash_poll_tick = 0
        self._toggle_btn.setText("Stop dashboard")
        self._dash_status.setText("Dashboard actief.")
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
        self._dash_fetch_inflight = False
        self._poll_timer.stop()
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
        self._apply_pending_results()
        self._request_async_poll()

    def _request_async_poll(self) -> None:
        if self._dash_fetch_inflight or self._state.tracker is None:
            return
        self._dash_fetch_inflight = True
        ui_hint = self._get_ui_hint()

        def _worker() -> None:
            result = {"mem_area": None, "mem_gems": None, "error": None}
            try:
                mem_area, mem_gems = self._read_memory(ui_hint=ui_hint)
                result["mem_area"] = mem_area
                result["mem_gems"] = mem_gems
            except Exception as exc:
                result["error"] = str(exc)
            finally:
                try:
                    self._dash_result_queue.put_nowait(result)
                except queue.Full:
                    try:
                        self._dash_result_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._dash_result_queue.put_nowait(result)

        self._dash_fetch_thread = threading.Thread(target=_worker, daemon=True, name="ic-pyside-dash")
        self._dash_fetch_thread.start()

    def _apply_pending_results(self) -> None:
        needs_refresh = False
        while True:
            try:
                result = self._dash_result_queue.get_nowait()
            except queue.Empty:
                break
            self._dash_fetch_inflight = False
            if result.get("error"):
                self._state.api_detail = str(result["error"])
                needs_refresh = True
                continue
            mem_area = result.get("mem_area")
            mem_gems = result.get("mem_gems")
            active_party_index = (
                self._state.tracker.latest.active_party_index
                if self._state.tracker is not None and self._state.tracker.latest is not None
                else None
            )
            if self._state.apply_memory_reading(
                mem_area,
                mem_gems,
                active=self._dash_active,
                active_party_index=active_party_index,
            ):
                needs_refresh = True
        if needs_refresh:
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
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(box)
        lbl_area = QLabel("Area: —")
        lbl_modron_progress = QLabel("")
        modron_bar = QProgressBar()
        modron_bar.setRange(0, 100)
        modron_bar.setTextVisible(False)
        modron_bar.setFixedHeight(8)
        modron_bar.setStyleSheet(
            f"QProgressBar {{ background: #3f3f46; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {BUD_BAR}; border-radius: 4px; }}"
        )
        modron_bar.hide()
        lbl_modron_progress.hide()
        lbl_run = QLabel("Run: —")
        lbl_gold = QLabel("Gold: —")
        lbl_gold_gained = QLabel("Gold verdiend: —")
        lbl_gold_rate = QLabel("Gold/kw: —")
        lbl_gems = QLabel("Gems deze run: —")
        lbl_areas_rate = QLabel("Areas/kw: —")
        goal_runs_row = QWidget()
        goal_runs_row_layout = QHBoxLayout(goal_runs_row)
        goal_runs_row_layout.setContentsMargins(0, 0, 0, 0)
        lbl_goal_runs = QLabel("")
        btn_goal_runs_expand = QPushButton("▶")
        btn_goal_runs_expand.setFixedWidth(28)
        btn_goal_runs_expand.setToolTip("Toon eerdere doel-runs")
        goal_runs_row_layout.addWidget(lbl_goal_runs, stretch=1)
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
            lbl_gold,
            lbl_gold_gained,
            lbl_gold_rate,
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
            lbl_gold,
            lbl_gold_gained,
            lbl_gold_rate,
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
        widgets: dict[str, QWidget] = {
            "frame": box,
            "area": lbl_area,
            "modron_progress_label": lbl_modron_progress,
            "modron_progress": modron_bar,
            "run": lbl_run,
            "gold": lbl_gold,
            "gold_gained": lbl_gold_gained,
            "gold_rate": lbl_gold_rate,
            "gems": lbl_gems,
            "areas_rate": lbl_areas_rate,
            "goal_runs_row": goal_runs_row,
            "goal_runs": lbl_goal_runs,
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

    def _apply_goal_runs(self, widgets: dict[str, QWidget], view) -> None:
        summary = view.goal_runs_summary
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
        row.show()

        while extra_layout.count():
            item = extra_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for line in view.goal_runs_extra:
            line_label = QLabel(line)
            line_label.setWordWrap(True)
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
        widgets["gold"].setText(view.gold)
        widgets["gold_gained"].setText(view.gold_gained)
        widgets["gold_rate"].setText(view.gold_rate)
        widgets["gems"].setText(view.gems)
        widgets["areas_rate"].setText(view.areas_rate)
        progress_bar = widgets.get("modron_progress")
        progress_label = widgets.get("modron_progress_label")
        if progress_bar is not None and progress_label is not None:
            if view.modron_progress_pct is not None:
                progress_bar.setValue(view.modron_progress_pct)
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
                f"font-size: 11px; color: {TEXT_BADGE}; background: {BG_BADGE}; "
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
                    format_gold=self._format_gold,
                    format_number=self._format_number,
                    format_duration=self._format_duration,
                    format_rate_window=self._format_rate_window,
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
        snap = self._fetch_snapshot()
        if snap is not None and self._state.last_payload is not None:
            snap = self._refresh_snapshot(snap, self._state.last_payload)
        if snap is not None:
            self._state.add_snapshot(snap, api_snapshot=self._state.last_api_snap)
        mem_area, mem_gems = self._read_memory()
        if mem_area is not None or mem_gems is not None:
            self._state.apply_memory_reading(
                mem_area,
                mem_gems,
                active=self._dash_active,
                active_party_index=snap.active_party_index if snap is not None else None,
            )
        self._update_labels()
        self._dash_status.setText("Sessie gereset — nieuwe baseline gezet.")

