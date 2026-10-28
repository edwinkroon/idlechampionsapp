from __future__ import annotations

import os
import sys
from collections.abc import Callable

from PySide6.QtCore import QProcess, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QClipboard, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ic_core.game_data_service import GameDataService, SnapshotEnvelope
from ic_ui.tabs.advice_tab import AdviceTab
from ic_ui.tabs.advisor_tab import AdvisorTab
from ic_ui.tabs.automation_tab import AutomationTab
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.tabs.formation_tab import FormationTab
from ic_ui.tabs.sources_tab import SourcesTab
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
from ic_ui.ui_action_log import format_diagnose_clipboard, note_ui_action

_ALL_ADVICE_CONSUMERS = frozenset({"advisor", "formation"})
_REFRESH_DONE_MS = 2500


_SETTINGS_ORG = "IdleChampions"
_SETTINGS_APP = "Companion"
_THEME_KEY = "ui/theme"
_TAB_KEY = "ui/last_tab"
_TAB_LAYOUT_VERSION_KEY = "ui/tab_layout_version"
# Bump when visible tabs change so old last_tab indices are not reused blindly.
_TAB_LAYOUT_VERSION = 3
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

    def __init__(
        self,
        *,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        report = on_progress or (lambda _msg: None)

        def step(message: str) -> None:
            report(message)
            QApplication.processEvents()

        self.setWindowTitle("Idle Champions")
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self._caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        step("Preparing data service…")
        self._data = GameDataService(self)
        self._fetch_inflight = False
        self._data.snapshot_updated.connect(self._on_snapshot_updated)
        self._data.fetch_failed.connect(self._on_fetch_failed)
        self._data.fetch_state_changed.connect(self._on_fetch_state_changed)

        step("Loading sources…")
        self._sources_tab = SourcesTab(self)
        self._sources_tab.hide()

        step("Loading Automation…")
        self._automation_tab = AutomationTab()
        self._automation_tab.indicator_changed.connect(self._set_automation_tab_indicator)
        self._automation_tab.api_poll_requested.connect(
            lambda: self._data.request_poll(reason="automation")
        )
        self._formation_sync.connect(self._automation_tab.sync_fkeys_from_payload)

        step("Loading Dashboard…")
        self._dashboard_tab = DashboardTab(self._sources_tab, data_service=self._data)
        self._dashboard_tab.payload_updated.connect(self._on_dashboard_payload)
        self._dashboard_tab.caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._dashboard_tab.api_poll_requested.connect(
            lambda: self._data.request_poll(reason="dashboard")
        )
        self._sources_tab.connect_save(self._dashboard_tab.save_manual_path)
        self._sources_tab.connect_refresh(self._dashboard_tab.refresh_install)

        tabs = QTabWidget()
        step("Loading Coach…")
        self._advisor_tab = AdvisorTab(self._dashboard_tab, data_service=self._data)
        # Formation analysis still feeds Advies; no longer a visible tab.
        step("Loading formation tools…")
        self._formation_tab = FormationTab(
            self._dashboard_tab, parent=self, data_service=self._data
        )
        self._formation_tab.hide()
        step("Loading Advies…")
        self._advice_tab = AdviceTab(self._formation_tab)
        self._advisor_tab.advice_resync_requested.connect(self._resync_advice_after_role_change)

        tabs.addTab(self._automation_tab, "Automation")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._advice_tab, "Advies")
        tabs.addTab(self._advisor_tab, "Coach")
        tabs.setTabToolTip(0, "Auto-level, progress, abilities (Ctrl+1)")
        tabs.setTabToolTip(1, "Live party status, Modron progress, rates (Ctrl+2)")
        tabs.setTabToolTip(2, "Externe AI: kopieer partijsetup, plak voorstel (Ctrl+3)")
        tabs.setTabToolTip(3, "Seats, feats, better champs, specializations (Ctrl+4)")
        self._tabs = tabs
        self._set_automation_tab_indicator("off")
        on_theme_changed(lambda _mode: self._set_automation_tab_indicator())
        self._install_global_refresh_button(tabs)
        self.setCentralWidget(tabs)
        step("Finishing window…")
        self._build_menu_bar()
        self._build_status_bar()
        self._restore_geometry()
        self._restore_last_tab()
        tabs.currentChanged.connect(self._on_tab_changed)

        self._data.start_polling()
        # Install detect + credentials can take a while — run after the window
        # is visible so startup does not sit on a blank/hung frame.
        QTimer.singleShot(0, self._startup_after_show)

    def _startup_after_show(self) -> None:
        bar = self.statusBar()
        if bar is not None:
            bar.showMessage("Detecting game install and credentials…", 0)
        # Install detect runs on a worker; clear the status once it finishes.
        dash = self._dashboard_tab

        def _clear_when_idle() -> None:
            if getattr(dash, "_install_detect_inflight", False):
                QTimer.singleShot(150, _clear_when_idle)
                return
            if bar is not None:
                bar.clearMessage()
            dash.auto_start()

        dash.refresh_install()
        QTimer.singleShot(150, _clear_when_idle)

    def _install_global_refresh_button(self, tabs: QTabWidget) -> None:
        """Refresh + diagnose-copy at the far right of the tab bar."""
        self._global_refresh_pending = False
        self._refresh_done_timer = QTimer(self)
        self._refresh_done_timer.setSingleShot(True)
        self._refresh_done_timer.timeout.connect(self._restore_global_refresh_button)

        corner = QWidget()
        row = QHBoxLayout(corner)
        row.setContentsMargins(0, 2, 8, 2)
        row.setSpacing(4)
        row.setAlignment(Qt.AlignmentFlag.AlignRight)

        copy_btn = QToolButton()
        copy_btn.setAutoRaise(True)
        copy_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        apply_button_icon(copy_btn, "copy", size=16)
        copy_btn.setToolTip(
            "Kopieer UI-diagnose naar het klembord (laatste actie + tab-status).\n"
            "Plak dat in de Cursor-chat bij Not Responding / haperingen."
        )
        copy_btn.clicked.connect(self._copy_ui_diagnose)
        row.addWidget(copy_btn)
        self._btn_diag_copy = copy_btn

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
            "Refresh all game data: Dashboard, Advies, and Coach (F5).\n"
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

    def _copy_ui_diagnose(self) -> None:
        """Copy a paste-ready diagnose block for the AI chat."""
        note_ui_action("Diagnose gekopieerd")
        text = format_diagnose_clipboard(
            active_tab=self._active_tab_label(),
            extra_lines=self._diagnose_extra_lines(),
        )
        clipboard = QGuiApplication.clipboard()
        ok = False
        if clipboard is not None:
            try:
                clipboard.setText(text, QClipboard.Mode.Clipboard)
                ok = True
            except Exception:
                ok = False
        bar = self.statusBar()
        if bar is not None:
            if ok:
                bar.showMessage(
                    "UI-diagnose gekopieerd — plak in de Cursor-chat.",
                    5000,
                )
            else:
                bar.showMessage("Klembord schrijven mislukt.", 5000)

    def _active_tab_label(self) -> str:
        idx = self._tabs.currentIndex()
        if idx < 0:
            return "(geen)"
        return self._tabs.tabText(idx) or f"tab {idx}"

    def _diagnose_extra_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        try:
            from ic_ui.widgets.advisor_controls import (
                read_shared_advice_context,
                read_shared_advice_goal,
            )

            goal = read_shared_advice_goal() or "(niet bevestigd)"
            ctx = read_shared_advice_context()
            lines.append(f"Doel/context: {goal} / {ctx}")
        except Exception:
            pass
        lines.append(
            f"API fetch bezig: {'ja' if self._data_fetch_inflight() else 'nee'}"
        )
        lines.append(
            f"Global refresh pending: {'ja' if self._global_refresh_pending else 'nee'}"
        )
        for label, tab in (
            ("Formation analysing", self._formation_tab),
            ("Coach analysing", self._advisor_tab),
        ):
            analysing = bool(getattr(tab, "analysing", False))
            lines.append(f"{label}: {'ja' if analysing else 'nee'}")
        latest = self._data.latest
        if latest is not None:
            age = ""
            if latest.last_success_at:
                import time as _time

                age = f", leeftijd {max(0, int(_time.time() - latest.last_success_at))}s"
            lines.append(
                f"Snapshot v{latest.version}{age}"
                + (f", degraded={latest.degraded}" if latest.degraded else "")
            )
        else:
            lines.append("Snapshot: (nog geen)")
        return tuple(lines)

    def _refresh_all(self) -> None:
        """One poll + forced re-analyze for every advice surface."""
        if self._global_refresh_pending or not self._btn_global_refresh.isEnabled():
            return
        note_ui_action("Refresh all (F5)")
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
            # Shared hub coalesces — Formation (hidden) + Coach join one analyze.
            self._formation_tab.start_analysis(
                cached, None, auto_refresh=False, advice_fp=fp
            )
            self._advisor_tab.start_analysis(
                cached, None, auto_refresh=False, advice_fp=fp
            )
        else:
            self._advisor_tab.notify_waiting_for_data()
            self._formation_tab.notify_waiting_for_data()

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
        """Role prefs changed: one shared analyze for Formation (hidden) + Coach."""
        payload = self._data.last_payload
        if payload is None:
            return
        from ic_gamedata.advice_fingerprint import advice_fingerprint

        fp = advice_fingerprint(payload)
        self._formation_tab.start_analysis(
            payload, None, auto_refresh=True, advice_fp=fp
        )
        self._advisor_tab.start_analysis(
            payload, None, auto_refresh=True, advice_fp=fp
        )

    def _on_snapshot_updated(self, envelope: SnapshotEnvelope) -> None:
        """Apply a new API snapshot without blocking the title bar in one chunk.

        First-poll ingest + Coach/Formation kickoff can be heavy; yield to the
        event loop between steps so Windows does not mark the window hung.
        """
        if envelope.credentials is not None:
            self._dashboard_tab.credentials = envelope.credentials
        self._finish_global_refresh(envelope)
        # Defer heavy consumers so fetch_state / paint can run first.
        QTimer.singleShot(0, lambda env=envelope: self._apply_snapshot_deferred(env))

    def _apply_snapshot_deferred(self, envelope: SnapshotEnvelope) -> None:
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
        # Stagger advice tabs so their first start_analysis/render do not stack.
        QTimer.singleShot(0, lambda env=envelope: self._formation_tab.on_snapshot(env))
        QTimer.singleShot(0, lambda env=envelope: self._advisor_tab.on_snapshot(env))

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
        settings_action = QAction("Settings…", self)
        settings_action.setToolTip("Install path, log, and memory hint")
        settings_action.triggered.connect(self._show_settings_dialog)
        view_menu.addAction(settings_action)
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

    def _show_settings_dialog(self) -> None:
        """Former Sources tab — install path / memory hint."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.resize(520, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self._sources_tab)
        self._sources_tab.show()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        try:
            dialog.exec()
        finally:
            # Keep SourcesTab owned by the main window (not destroyed with dialog).
            self._sources_tab.setParent(self)
            self._sources_tab.hide()

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
            "F5 refresh · Ctrl+1…4 tabs · View → Settings · Ctrl+R reload"
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
        try:
            layout_ver = int(self._settings.value(_TAB_LAYOUT_VERSION_KEY, 0) or 0)
        except (TypeError, ValueError):
            layout_ver = 0
        raw = self._settings.value(_TAB_KEY, 1)
        try:
            index = int(raw)
        except (TypeError, ValueError):
            index = 1
        if layout_ver < _TAB_LAYOUT_VERSION:
            # Old layout had Formation/Specs/Sources — default to Dashboard.
            index = 1
            self._settings.setValue(_TAB_LAYOUT_VERSION_KEY, _TAB_LAYOUT_VERSION)
        if 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)
        self._settings.setValue(_TAB_LAYOUT_VERSION_KEY, _TAB_LAYOUT_VERSION)

    def _on_tab_changed(self, index: int) -> None:
        self._settings.setValue(_TAB_KEY, index)
        name = self._tabs.tabText(index) if 0 <= index < self._tabs.count() else "?"
        note_ui_action(f"Tab → {name}")

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
            "Ctrl+1 … Ctrl+4 — Automation / Dashboard / Advies / Coach\n"
            "Ctrl+R — reload app\n"
            "View → Settings — install path & memory hint\n"
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
    # Prefer the newly started process: close any leftover companion instance
    # (older exe / previous pythonw app_launcher) before the splash/UI appears.
    try:
        from ic_ui.single_instance import ensure_single_instance

        ensure_single_instance()
    except Exception:
        # Startup must not fail if process enumeration is unavailable.
        pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(_load_saved_theme(), app)

    from ic_ui.widgets.startup_splash import StartupSplash

    splash = StartupSplash()
    splash.present()
    splash.set_status("Starting…")

    # Keep a reference so the window is not GC'd; build after the splash has
    # mapped so Windows actually shows it (sync construction before exec hid it).
    hold: dict[str, IdleChampionsMainWindow] = {}

    def _build_main_window() -> None:
        window = IdleChampionsMainWindow(on_progress=splash.set_status)
        hold["window"] = window
        window.show()
        splash.finish(window)

    QTimer.singleShot(50, _build_main_window)
    return app.exec()
