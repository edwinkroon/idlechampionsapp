from __future__ import annotations

import sys

from PySide6.QtCore import QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QMenuBar, QMessageBox, QTabWidget

from ic_ui.tabs.advisor_tab import AdvisorTab, party_id_from_payload
from ic_ui.tabs.analytics_tab import AnalyticsTab
from ic_ui.tabs.automation_tab import AutomationTab
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.tabs.gem_farm_tab import GemFarmTab
from ic_ui.tabs.sources_tab import SourcesTab
from ic_ui.tabs.specializations_tab import SpecializationsTab
from ic_ui.workers.api_fetch import ApiFetchRunnable


class IdleChampionsMainWindow(QMainWindow):
    _caption_refresh = Signal()
    _formation_sync = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Idle Champions")
        self.resize(980, 760)
        self._caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._init_api_poll_state()

        self._sources_tab = SourcesTab()

        self._automation_tab = AutomationTab()
        self._automation_tab.running_changed.connect(self._on_automation_running_changed)
        self._automation_tab.api_poll_requested.connect(self._request_api_poll)
        self._formation_sync.connect(self._automation_tab.sync_fkeys_from_payload)

        self._dashboard_tab = DashboardTab(self._sources_tab)
        self._dashboard_tab.payload_updated.connect(self._on_dashboard_payload)
        self._dashboard_tab.caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._dashboard_tab.api_poll_requested.connect(
            lambda: self._request_api_poll(advisor_after=False, auto_refresh=False)
        )
        self._sources_tab.connect_save(self._dashboard_tab.save_manual_path)
        self._sources_tab.connect_refresh(self._dashboard_tab.refresh_install)

        tabs = QTabWidget()
        self._advisor_tab = AdvisorTab(self._dashboard_tab)
        self._advisor_tab.api_poll_requested.connect(
            lambda auto_refresh: self._request_api_poll(advisor_after=True, auto_refresh=auto_refresh)
        )

        self._specializations_tab = SpecializationsTab(self._dashboard_tab)
        self._analytics_tab = AnalyticsTab(self._dashboard_tab)
        self._gem_farm_tab = GemFarmTab(self._dashboard_tab)

        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._analytics_tab, "Analytics")
        tabs.addTab(self._gem_farm_tab, "Gem Farm")
        tabs.addTab(self._advisor_tab, "Party Advisor")
        tabs.addTab(self._specializations_tab, "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")
        self._tabs = tabs
        self.setCentralWidget(tabs)
        self._build_menu_bar()

        self._api_poll_timer.start()
        QTimer.singleShot(300, self._dashboard_tab.auto_start)
        self._dashboard_tab.refresh_install()

    def _on_automation_running_changed(self, running: bool) -> None:
        idx = self._tabs.indexOf(self._automation_tab)
        if idx >= 0:
            self._tabs.setTabText(idx, f"Automatisering [{'AAN' if running else 'UIT'}]")

    def _on_dashboard_payload(self, payload: dict) -> None:
        self._automation_tab.set_formation_payload(payload)
        self._formation_sync.emit(payload)

    # ------------------------------------------------------------------ central API poll

    def _init_api_poll_state(self) -> None:
        self._api_fetch_inflight = False
        self._api_advisor_after = False
        self._api_auto_refresh = False
        self._api_poll_timer = QTimer(self)
        self._api_poll_timer.setInterval(5000)
        self._api_poll_timer.timeout.connect(
            lambda: self._request_api_poll(advisor_after=False, auto_refresh=True)
        )

    def _request_api_poll(self, *, advisor_after: bool = False, auto_refresh: bool = False) -> None:
        if self._api_fetch_inflight:
            if advisor_after and not auto_refresh:
                self._advisor_tab.notify_fetch_inflight(manual_request=True)
            return
        if self._dashboard_tab.install is None or self._dashboard_tab.credentials is None:
            self._dashboard_tab.refresh_install()
        log_path = self._dashboard_tab.api_log_path()
        if log_path is not None:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(log_path)
            if fresh is not None:
                self._dashboard_tab.credentials = fresh
        if self._dashboard_tab.credentials is None:
            if advisor_after and not auto_refresh:
                self._advisor_tab.notify_fetch_credentials_error()
            return

        self._api_fetch_inflight = True
        self._api_advisor_after = advisor_after
        self._api_auto_refresh = auto_refresh
        worker = ApiFetchRunnable(self._dashboard_tab.credentials, log_path, self._dashboard_tab.tailer)
        worker.signals.done.connect(self._api_on_fetch_done)
        QThreadPool.globalInstance().start(worker)

    def _api_on_fetch_done(self, result: dict) -> None:
        self._api_fetch_inflight = False
        advisor_after = self._api_advisor_after
        auto_refresh = self._api_auto_refresh
        if result.get("error"):
            err = str(result["error"])
            self._dashboard_tab.api_detail = err
            if advisor_after:
                self._advisor_tab.notify_fetch_error(
                    err, auto_refresh=auto_refresh, advisor_after=True
                )
            return

        credentials = result.get("credentials")
        if credentials is not None:
            self._dashboard_tab.credentials = credentials
        self._api_apply_fetch_result(
            result,
            advisor_after=advisor_after,
            auto_refresh=auto_refresh,
        )

    def _api_apply_fetch_result(
        self,
        result: dict,
        *,
        advisor_after: bool,
        auto_refresh: bool,
    ) -> None:
        payload = result.get("payload")
        err = result.get("err")
        party_changed = False
        if payload is not None:
            new_party_id = party_id_from_payload(payload)
            party_changed = (
                self._advisor_tab.last_party_id is not None
                and new_party_id is not None
                and new_party_id != self._advisor_tab.last_party_id
            )
            self._caption_refresh.emit()
        self._dashboard_tab.ingest_api_result(result)
        if (
            payload is not None
            and not self._advisor_tab.has_results
            and not self._advisor_tab.analysing
        ):
            self._advisor_tab.start_analysis(
                payload,
                err,
                auto_refresh=True,
                party_changed=False,
            )
            if not self._specializations_tab.has_results and not self._specializations_tab.analysing:
                self._specializations_tab.start_analysis(
                    payload,
                    err,
                    auto_refresh=True,
                )
        elif party_changed and payload is not None:
            self._advisor_tab.start_analysis(
                payload,
                err,
                auto_refresh=True,
                party_changed=True,
            )
            self._specializations_tab.start_analysis(
                payload,
                err,
                auto_refresh=True,
            )
        elif advisor_after:
            if payload is not None:
                self._advisor_tab.start_analysis(
                    payload,
                    err,
                    auto_refresh=auto_refresh,
                    party_changed=party_changed,
                )
                self._specializations_tab.start_analysis(
                    payload,
                    err,
                    auto_refresh=auto_refresh,
                )
            else:
                self._advisor_tab.notify_fetch_no_payload(err, auto_refresh=auto_refresh)

    def _refresh_app_caption_from_snapshots(self) -> None:
        party = self._dashboard_tab.caption_party()
        if party is None:
            self._update_app_caption()
            return
        adventure_id = party.adventure_id if party.adventure_id is not None and party.adventure_id >= 0 else None
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
        self._automation_tab.stop()
        self._dashboard_tab.stop()
        self._dashboard_tab.disconnect_memory()
        super().closeEvent(event)


def run_pyside_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IdleChampionsMainWindow()
    window.show()
    return app.exec()

