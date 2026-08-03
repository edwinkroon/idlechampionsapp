from __future__ import annotations

import sys

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QMenuBar, QMessageBox, QTabWidget

from ic_core.game_data_service import GameDataService, SnapshotEnvelope
from ic_ui.tabs.advisor_tab import AdvisorTab
from ic_ui.tabs.analytics_tab import AnalyticsTab
from ic_ui.tabs.automation_tab import AutomationTab
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.tabs.sources_tab import SourcesTab
from ic_ui.tabs.specializations_tab import SpecializationsTab


class IdleChampionsMainWindow(QMainWindow):
    _caption_refresh = Signal()
    _formation_sync = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Idle Champions")
        self.resize(980, 760)
        self._caption_refresh.connect(self._refresh_app_caption_from_snapshots)

        self._data = GameDataService(self)
        self._data.snapshot_updated.connect(self._on_snapshot_updated)
        self._data.fetch_failed.connect(self._on_fetch_failed)

        self._sources_tab = SourcesTab()

        self._automation_tab = AutomationTab()
        self._automation_tab.running_changed.connect(self._on_automation_running_changed)
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
        self._analytics_tab = AnalyticsTab(self._dashboard_tab)

        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._analytics_tab, "Analytics")
        tabs.addTab(self._advisor_tab, "Party Advisor")
        tabs.addTab(self._specializations_tab, "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")
        self._tabs = tabs
        self.setCentralWidget(tabs)
        self._build_menu_bar()

        self._data.start_polling()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(300, self._dashboard_tab.auto_start)
        self._dashboard_tab.refresh_install()

    def _on_automation_running_changed(self, running: bool) -> None:
        idx = self._tabs.indexOf(self._automation_tab)
        if idx >= 0:
            self._tabs.setTabText(idx, f"Automatisering [{'AAN' if running else 'UIT'}]")

    def _on_dashboard_payload(self, payload: dict) -> None:
        self._automation_tab.set_formation_payload(payload)
        self._formation_sync.emit(payload)

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

    def _on_fetch_failed(self, err: str) -> None:
        self._dashboard_tab.api_detail = err
        # Degraded snapshot_updated already carries cache for consumers.
        if not self._advisor_tab.has_results:
            self._advisor_tab.notify_fetch_error(err, auto_refresh=True, advisor_after=False)

    def _refresh_app_caption_from_snapshots(self) -> None:
        party = self._dashboard_tab.caption_party()
        if party is None:
            self._update_app_caption()
            return
        adventure_id = (
            party.adventure_id if party.adventure_id is not None and party.adventure_id >= 0 else None
        )
        self._update_app_caption(party.party_index, adventure_id)

    def _build_menu_bar(self) -> None:
        menu_bar = QMenuBar(self)
        help_menu = QMenu("Help", self)
        about_action = help_menu.addAction("Over Idle Champions App…")
        about_action.triggered.connect(self._show_about_dialog)
        menu_bar.addMenu(help_menu)
        self.setMenuBar(menu_bar)

    def _show_about_dialog(self) -> None:
        try:
            from ic_gamedata.app_version import version_label

            version = version_label()
        except ImportError:
            version = "onbekende versie"
        QMessageBox.about(
            self,
            "Idle Champions App",
            f"Idle Champions companion voor Windows.\n\nVersie {version}\n\n"
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
        self._data.stop_polling()
        self._automation_tab.stop()
        self._dashboard_tab.stop()
        self._dashboard_tab.disconnect_memory()
        super().closeEvent(event)


def run_pyside_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IdleChampionsMainWindow()
    window.show()
    return app.exec()
