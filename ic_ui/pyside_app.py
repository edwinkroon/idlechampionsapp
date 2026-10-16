from __future__ import annotations

import os
import sys

from PySide6.QtCore import QProcess, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from ic_core.game_data_service import GameDataService, SnapshotEnvelope
from ic_ui.tabs.advisor_tab import AdvisorTab
from ic_ui.tabs.automation_tab import AutomationTab
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.tabs.formation_tab import FormationTab
from ic_ui.tabs.sources_tab import SourcesTab
from ic_ui.tabs.specializations_tab import SpecializationsTab
from ic_ui.theme import (
    ThemeMode,
    apply_button_icon,
    apply_theme,
    current_theme,
    on_theme_changed,
    style_primary_button,
)
from ic_ui import theme as ui_theme
from ic_ui.button_icons import status_dot_icon

_ALL_ADVICE_CONSUMERS = frozenset({"advisor", "specializations", "formation"})
_REFRESH_DONE_MS = 2500


_SETTINGS_ORG = "IdleChampions"
_SETTINGS_APP = "Companion"
_THEME_KEY = "ui/theme"
_TAB_KEY = "ui/last_tab"
_GEOMETRY_KEY = "ui/geometry"
_GEOMETRY_VERSION_KEY = "ui/geometry_version"
# Bump when default size changes so existing installs pick up the new height once.
_GEOMETRY_VERSION = 2
_DEFAULT_WIDTH = 1040
_DEFAULT_HEIGHT = 1180
_MIN_WIDTH = 860
_MIN_HEIGHT = 760


class IdleChampionsMainWindow(QMainWindow):
    _caption_refresh = Signal()
    _formation_sync = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Idle Champions")
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self._caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        self._data = GameDataService(self)
        self._fetch_inflight = False
        self._data.snapshot_updated.connect(self._on_snapshot_updated)
        self._data.fetch_failed.connect(self._on_fetch_failed)
        self._data.fetch_state_changed.connect(self._on_fetch_state_changed)

        self._sources_tab = SourcesTab()

        self._automation_tab = AutomationTab()
        self._automation_tab.indicator_changed.connect(self._set_automation_tab_indicator)
        self._automation_tab.api_poll_requested.connect(
            lambda: self._data.request_poll(reason="automation")
        )
        self._formation_sync.connect(self._automation_tab.sync_fkeys_from_payload)

        self._dashboard_tab = DashboardTab(self._sources_tab, data_service=self._data)
        self._dashboard_tab.payload_updated.connect(self._on_dashboard_payload)
        self._dashboard_tab.caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._dashboard_tab.api_poll_requested.connect(
            lambda: self._data.request_poll(reason="dashboard")
        )
        self._sources_tab.connect_save(self._dashboard_tab.save_manual_path)
        self._sources_tab.connect_refresh(self._dashboard_tab.refresh_install)

        tabs = QTabWidget()
        self._advisor_tab = AdvisorTab(self._dashboard_tab, data_service=self._data)
        self._specializations_tab = SpecializationsTab(
            self._dashboard_tab, data_service=self._data
        )
        self._formation_tab = FormationTab(self._dashboard_tab, data_service=self._data)
        self._advisor_tab.advice_resync_requested.connect(self._resync_advice_after_role_change)

        tabs.addTab(self._automation_tab, "Automation")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._formation_tab, "Formation")
        tabs.addTab(self._advisor_tab, "Party Advisor")
        tabs.addTab(self._specializations_tab, "Specializations")
        tabs.addTab(self._sources_tab, "Sources")
        tabs.setTabToolTip(0, "Auto-level, progress, abilities (Ctrl+1)")
        tabs.setTabToolTip(1, "Live party status, Modron progress, rates (Ctrl+2)")
        tabs.setTabToolTip(2, "Active and optimal formation (Ctrl+3)")
        tabs.setTabToolTip(3, "Seat roles, tips, and feats (Ctrl+4)")
        tabs.setTabToolTip(4, "Specialization choices and tips (Ctrl+5)")
        tabs.setTabToolTip(5, "Install path, log, and memory hint (Ctrl+6)")
        self._tabs = tabs
        self._set_automation_tab_indicator("off")
        on_theme_changed(lambda _mode: self._set_automation_tab_indicator())
        self._install_global_refresh_button(tabs)
        self.setCentralWidget(tabs)
        self._build_menu_bar()
        self._build_status_bar()
        self._restore_geometry()
        self._restore_last_tab()
        tabs.currentChanged.connect(self._on_tab_changed)

        self._data.start_polling()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(300, self._dashboard_tab.auto_start)
        self._dashboard_tab.refresh_install()

    def _install_global_refresh_button(self, tabs: QTabWidget) -> None:
        """Refresh control at the far right of the tab bar — updates every tab."""
        self._global_refresh_pending = False
        self._refresh_done_timer = QTimer(self)
        self._refresh_done_timer.setSingleShot(True)
        self._refresh_done_timer.timeout.connect(self._restore_global_refresh_button)

        corner = QWidget()
        row = QHBoxLayout(corner)
        row.setContentsMargins(0, 2, 8, 2)
        row.setSpacing(0)
        btn = QPushButton("Refresh")
        style_primary_button(btn)
        apply_button_icon(btn, "refresh")
        btn.setToolTip(self._global_refresh_idle_tooltip())
        btn.clicked.connect(self._refresh_all)
        row.addWidget(btn)
        self._btn_global_refresh = btn
        tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        refresh_action = QAction("Refresh all", self)
        refresh_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        refresh_action.triggered.connect(self._refresh_all)
        self.addAction(refresh_action)

    @staticmethod
    def _global_refresh_idle_tooltip() -> str:
        return (
            "Refresh all game data: Dashboard, Formation, Party Advisor, and "
            "Specializations (F5).\n"
            "Fetches getuserdetails from the game API — usually a second or two, "
            "not instantaneous."
        )

    def _set_global_refresh_visual(self, state: str) -> None:
        """idle | busy | done — icon/label feedback for the corner Refresh button."""
        btn = self._btn_global_refresh
        if state == "busy":
            btn.setText("Refreshing…")
            apply_button_icon(btn, "refresh")
            btn.setToolTip("Fetching latest game data from the API…")
        elif state == "done":
            btn.setText("Updated")
            apply_button_icon(btn, "check")
            btn.setToolTip("API refresh completed")
        else:
            btn.setText("Refresh")
            apply_button_icon(btn, "refresh")
            btn.setToolTip(self._global_refresh_idle_tooltip())

    def _restore_global_refresh_button(self) -> None:
        self._set_global_refresh_visual("idle")
        self._btn_global_refresh.setEnabled(not self._data_fetch_inflight())

    def _data_fetch_inflight(self) -> bool:
        # GameDataService does not expose inflight; mirror via button/fetch signals.
        return bool(getattr(self, "_fetch_inflight", False))

    def _refresh_all(self) -> None:
        """One poll + forced re-analyze for every advice surface."""
        if self._global_refresh_pending or not self._btn_global_refresh.isEnabled():
            return
        self._refresh_done_timer.stop()
        self._global_refresh_pending = True
        self._set_global_refresh_visual("busy")
        self._btn_global_refresh.setEnabled(False)
        bar = self.statusBar()
        if bar is not None:
            bar.showMessage("Refreshing all game data…", 0)

        if not self._data.refresh_credentials() and self._data.credentials is None:
            self._global_refresh_pending = False
            self._set_global_refresh_visual("idle")
            if bar is not None:
                bar.showMessage("No API credentials. Go to Dashboard → Search again.", 6000)
            self._btn_global_refresh.setEnabled(True)
            return

        latest = self._data.latest
        self._refresh_baseline_version = latest.version if latest is not None else 0

        cached = self._data.last_payload
        if cached is not None:
            from ic_gamedata.advice_fingerprint import advice_fingerprint

            fp = advice_fingerprint(cached)
            # Shared hub coalesces identical jobs — all three tabs join one analyze.
            self._formation_tab.start_analysis(
                cached, None, auto_refresh=False, advice_fp=fp
            )
            self._specializations_tab.start_analysis(
                cached, None, auto_refresh=False, advice_fp=fp
            )
            self._advisor_tab.start_analysis(
                cached, None, auto_refresh=False, advice_fp=fp
            )
        else:
            for tab in (
                self._advisor_tab,
                self._formation_tab,
                self._specializations_tab,
            ):
                tab.notify_waiting_for_data()

        self._data.request_poll(
            reason="global_refresh",
            force_consumers=_ALL_ADVICE_CONSUMERS,
            auto_refresh=False,
        )

    def _finish_global_refresh(self, envelope: SnapshotEnvelope) -> None:
        """Show a checkmark only after a new API snapshot for this Refresh click.

        Failed polls republish the previous cache at the same version — those must
        not flash a success check (data is polled, not realtime).
        """
        if not self._global_refresh_pending:
            return
        if not (envelope.force_consumers & _ALL_ADVICE_CONSUMERS):
            return
        baseline = getattr(self, "_refresh_baseline_version", 0)
        got_new_snapshot = envelope.version > baseline and envelope.payload is not None
        if not got_new_snapshot and not envelope.degraded:
            return
        self._global_refresh_pending = False
        bar = self.statusBar()
        if got_new_snapshot:
            self._set_global_refresh_visual("done")
            self._btn_global_refresh.setEnabled(True)
            if bar is not None:
                bar.showMessage("Refresh completed", _REFRESH_DONE_MS)
            self._refresh_done_timer.start(_REFRESH_DONE_MS)
            return
        self._set_global_refresh_visual("idle")
        self._btn_global_refresh.setEnabled(True)
        if bar is not None:
            bar.showMessage(envelope.err or "Refresh failed — no API data", 6000)

    def _on_fetch_state_changed(self, inflight: bool) -> None:
        self._fetch_inflight = inflight
        if inflight:
            self._btn_global_refresh.setEnabled(False)
            return
        # Keep "Refreshing…" until _finish_global_refresh sees the snapshot.
        if not self._global_refresh_pending:
            self._btn_global_refresh.setEnabled(True)
            bar = self.statusBar()
            if bar is not None and bar.currentMessage().startswith("Refreshing"):
                bar.clearMessage()

    def _set_automation_tab_indicator(self, state: str | None = None) -> None:
        idx = self._tabs.indexOf(self._automation_tab)
        if idx < 0:
            return
        resolved = state or self._automation_tab.indicator_state
        if resolved == "on":
            color = ui_theme.SUCCESS
            label = "on"
        elif resolved == "paused":
            color = ui_theme.STATUS_PAUSE
            label = "paused"
        else:
            color = ui_theme.FEAT_MISSING
            label = "off"
        self._tabs.setTabText(idx, "Automation")
        self._tabs.setTabIcon(idx, status_dot_icon(color, size=12))
        self._tabs.setTabToolTip(
            idx,
            f"Automation {label} — auto-level, progress, abilities (Ctrl+1)",
        )

    def _on_dashboard_payload(self, payload: dict) -> None:
        self._automation_tab.set_formation_payload(payload)
        self._formation_sync.emit(payload)

    def _resync_advice_after_role_change(self) -> None:
        """Role prefs changed: one shared analyze for Formation / Advisor / Specs."""
        payload = self._data.last_payload
        if payload is None:
            return
        from ic_gamedata.advice_fingerprint import advice_fingerprint

        fp = advice_fingerprint(payload)
        self._formation_tab.start_analysis(
            payload, None, auto_refresh=True, advice_fp=fp
        )
        self._specializations_tab.start_analysis(
            payload, None, auto_refresh=True, advice_fp=fp
        )
        self._advisor_tab.start_analysis(
            payload, None, auto_refresh=True, advice_fp=fp
        )

    def _on_snapshot_updated(self, envelope: SnapshotEnvelope) -> None:
        if envelope.credentials is not None:
            self._dashboard_tab.credentials = envelope.credentials
        if envelope.degraded:
            # Keep serving cached party data; only refresh status text.
            self._dashboard_tab.api_detail = envelope.api_detail or ""
        else:
            self._dashboard_tab.ingest_api_result(
                {
                    "payload": envelope.payload,
                    "api_snap": envelope.api_snap,
                    "snap": envelope.snap,
                    "err": envelope.err,
                    "api_detail": envelope.api_detail,
                }
            )
            if envelope.payload is not None:
                self._caption_refresh.emit()
        self._advisor_tab.on_snapshot(envelope)
        self._specializations_tab.on_snapshot(envelope)
        self._formation_tab.on_snapshot(envelope)
        self._finish_global_refresh(envelope)

    def _on_fetch_failed(self, err: str) -> None:
        self._dashboard_tab.api_detail = err
        # Degraded snapshot_updated already carries cache for consumers.
        if not self._advisor_tab.has_results:
            self._advisor_tab.notify_fetch_error(err, auto_refresh=True, advisor_after=False)

    def _refresh_app_caption_from_snapshots(self) -> None:
        # Prefer live payload (same source as Party Advisor) — snapshot
        # adventure_id / active index can lag after a party or adventure swap.
        payload = self._dashboard_tab.last_payload
        if isinstance(payload, dict):
            party_index, adventure_id = self._active_party_caption_ids(payload)
            if party_index is not None:
                self._update_app_caption(party_index, adventure_id)
                return
        party = self._dashboard_tab.caption_party()
        if party is None:
            self._update_app_caption()
            return
        adventure_id = (
            party.adventure_id if party.adventure_id is not None and party.adventure_id >= 0 else None
        )
        self._update_app_caption(party.party_index, adventure_id)

    @staticmethod
    def _active_party_caption_ids(
        payload: dict,
    ) -> tuple[int | None, int | None]:
        """Return (active_party_index, adventure_id) from getuserdetails payload."""
        try:
            from ic_gamedata.parsing import parse_int
        except ImportError:
            return None, None
        details = payload.get("details")
        if not isinstance(details, dict):
            return None, None
        active_id = parse_int(details.get("active_game_instance_id"))
        adventure_id = None
        instances = details.get("game_instances")
        if isinstance(instances, list) and active_id is not None:
            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                if parse_int(inst.get("game_instance_id")) != active_id:
                    continue
                adventure_id = parse_int(inst.get("current_adventure_id"))
                break
        if adventure_id is None:
            adventure_id = parse_int(details.get("current_adventure_id"))
        if adventure_id is not None and adventure_id < 0:
            adventure_id = None
        return active_id, adventure_id

    def _build_menu_bar(self) -> None:
        menu_bar = QMenuBar(self)

        view_menu = QMenu("View", self)
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        dark_action = QAction("Dark", self)
        dark_action.setCheckable(True)
        light_action = QAction("Light", self)
        light_action.setCheckable(True)
        theme_group.addAction(dark_action)
        theme_group.addAction(light_action)
        view_menu.addAction(dark_action)
        view_menu.addAction(light_action)
        dark_action.triggered.connect(lambda: self._set_theme("dark"))
        light_action.triggered.connect(lambda: self._set_theme("light"))
        self._theme_dark_action = dark_action
        self._theme_light_action = light_action
        self._sync_theme_menu()
        view_menu.addSeparator()
        reload_action = QAction("Reload app", self)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.setToolTip("Close the app and start again")
        reload_action.triggered.connect(self._reload_app)
        view_menu.addAction(reload_action)
        menu_bar.addMenu(view_menu)

        help_menu = QMenu("Help", self)
        reload_help = help_menu.addAction("Reload app")
        reload_help.triggered.connect(self._reload_app)
        help_menu.addSeparator()
        shortcuts_action = help_menu.addAction("Keyboard shortcuts…")
        shortcuts_action.triggered.connect(self._show_shortcuts_dialog)
        about_action = help_menu.addAction("About Idle Champions App…")
        about_action.triggered.connect(self._show_about_dialog)
        menu_bar.addMenu(help_menu)
        self.setMenuBar(menu_bar)
        self._bind_tab_shortcuts()

    def _bind_tab_shortcuts(self) -> None:
        for index in range(min(9, self._tabs.count())):
            action = QAction(self)
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(lambda _checked=False, i=index: self._tabs.setCurrentIndex(i))
            self.addAction(action)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self._status_theme = QLabel("")
        self._status_version = QLabel("")
        self._status_hint = QLabel(
            "F5 refresh all · Ctrl+1…6 tabs · Ctrl+R reload · Help → Keyboard shortcuts"
        )
        bar.addWidget(self._status_theme, 0)
        bar.addWidget(self._status_version, 0)
        bar.addPermanentWidget(self._status_hint, 0)
        self.setStatusBar(bar)
        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        mode = "Dark" if current_theme() == "dark" else "Light"
        self._status_theme.setText(f"Theme: {mode}")
        try:
            from ic_gamedata.app_version import version_label

            self._status_version.setText(f" · {version_label()}")
        except ImportError:
            self._status_version.setText("")

    def _restore_geometry(self) -> None:
        try:
            saved_version = int(self._settings.value(_GEOMETRY_VERSION_KEY, 0) or 0)
        except (TypeError, ValueError):
            saved_version = 0
        geometry = self._settings.value(_GEOMETRY_KEY)
        if geometry is not None and saved_version >= _GEOMETRY_VERSION:
            try:
                self.restoreGeometry(geometry)
                return
            except Exception:
                pass
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self._settings.setValue(_GEOMETRY_VERSION_KEY, _GEOMETRY_VERSION)

    def _restore_last_tab(self) -> None:
        raw = self._settings.value(_TAB_KEY, 1)
        try:
            index = int(raw)
        except (TypeError, ValueError):
            index = 1
        if 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)

    def _on_tab_changed(self, index: int) -> None:
        self._settings.setValue(_TAB_KEY, index)

    def _sync_theme_menu(self) -> None:
        mode = current_theme()
        self._theme_dark_action.setChecked(mode == "dark")
        self._theme_light_action.setChecked(mode == "light")

    def _set_theme(self, mode: ThemeMode) -> None:
        apply_theme(mode)
        self._settings.setValue(_THEME_KEY, mode)
        self._sync_theme_menu()
        self._refresh_status_bar()

    def _reload_app(self) -> None:
        if self._automation_tab.is_running:
            reply = QMessageBox.question(
                self,
                "Reload app",
                "Automation is still running. Stop it and reload the app?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        args = list(sys.argv)
        if getattr(sys, "frozen", False):
            program = sys.executable
            arguments = args[1:]
        else:
            program = sys.executable
            arguments = args if args else []
        cwd = os.getcwd()
        # Start the replacement process first so a failed relaunch still leaves
        # the current window open.
        if not QProcess.startDetached(program, arguments, cwd):
            QMessageBox.warning(
                self,
                "Reload app",
                "Could not restart the app. The current session stays open.",
            )
            return
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _show_shortcuts_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard shortcuts",
            "F5 — refresh all game data and advice\n"
            "Ctrl+1 … Ctrl+6 — switch tabs\n"
            "Ctrl+R — reload app\n"
            "View → Dark/Light — switch theme\n\n"
            "Automation:\n"
            "• Ctrl held = pause\n"
            "• Mouse over this app = pause (when enabled)",
        )

    def _show_about_dialog(self) -> None:
        try:
            from ic_gamedata.app_version import version_label

            version = version_label()
        except ImportError:
            version = "unknown version"
        QMessageBox.about(
            self,
            "Idle Champions App",
            f"Idle Champions companion for Windows.\n\nVersion {version}\n\n"
            "Start: python app_launcher.py",
        )

    def _app_title_base(self) -> str:
        try:
            from ic_gamedata.app_version import app_version

            return f"Idle Champions v{app_version()}"
        except ImportError:
            return "Idle Champions"

    def _update_app_caption(
        self,
        party_index: int | None = None,
        adventure_id: int | None = None,
    ) -> None:
        title = self._app_title_base()
        if party_index is not None:
            title += f" · Party {party_index}"
            try:
                from ic_gamedata.adventure_names import adventure_display_name
            except ImportError:
                adventure_display_name = None  # type: ignore[assignment,misc]
            adventure_name = (
                adventure_display_name(self._dashboard_tab.last_payload, adventure_id)
                if adventure_display_name is not None
                else None
            )
            if adventure_name:
                title += f" - {adventure_name}"
        self.setWindowTitle(title)

    def closeEvent(self, event) -> None:
        self._settings.setValue(_GEOMETRY_KEY, self.saveGeometry())
        self._settings.setValue(_GEOMETRY_VERSION_KEY, _GEOMETRY_VERSION)
        self._data.stop_polling()
        self._automation_tab.stop()
        self._dashboard_tab.stop()
        self._dashboard_tab.disconnect_memory()
        super().closeEvent(event)

def _load_saved_theme() -> ThemeMode:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    raw = str(settings.value(_THEME_KEY, "dark") or "dark").lower()
    return "light" if raw == "light" else "dark"


def run_pyside_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(_load_saved_theme(), app)
    window = IdleChampionsMainWindow()
    window.show()
    return app.exec()
