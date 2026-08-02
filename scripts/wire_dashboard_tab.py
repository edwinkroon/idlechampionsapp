"""Wire DashboardTab into pyside_app and remove extracted dashboard code."""

from __future__ import annotations

from pathlib import Path


def find_def(lines: list[str], name: str, start: int = 0) -> int:
    needle = f"    def {name}"
    for i in range(start, len(lines)):
        if lines[i].startswith(needle):
            return i
    raise SystemExit(f"missing {name}")


def remove_range(lines: list[str], start: int, end: int) -> list[str]:
    return lines[:start] + lines[end:]


def main() -> None:
    path = Path(__file__).resolve().parent.parent / "ic_ui" / "pyside_app.py"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    api_start = next(i for i, l in enumerate(lines) if l.startswith("class _ApiFetchSignals"))
    advisor_start = next(i for i, l in enumerate(lines) if l.startswith("class _AdvisorRunnable"))
    lines = remove_range(lines, api_start, advisor_start)

    build_start = find_def(lines, "_build_dashboard_tab")
    build_end = find_def(lines, "_init_advisor_state", build_start)
    lines = remove_range(lines, build_start, build_end)

    dash_comment = next(
        i for i, l in enumerate(lines) if l.strip() == "# ------------------------------------------------------------------ dashboard"
    )
    app_title = find_def(lines, "_app_title_base", dash_comment)
    party_from = find_def(lines, "_dash_party_from_snapshot", app_title)
    lines = remove_range(lines, dash_comment, party_from)

    refresh_caption = find_def(lines, "_refresh_app_caption_from_snapshots", app_title)
    refresh_end = find_def(lines, "_dash_running_parties", refresh_caption)
    reset_end = find_def(lines, "closeEvent", refresh_end)
    lines = remove_range(lines, refresh_end, reset_end)

    text = "".join(lines)

    text = text.replace(
        "from ic_ui.tabs.sources_tab import SourcesTab\n",
        "from ic_ui.tabs.dashboard_tab import DashboardTab\n"
        "from ic_ui.tabs.sources_tab import SourcesTab\n"
        "from ic_ui.workers.api_fetch import ApiFetchRunnable\n",
    )

    old_init = """        self._init_dashboard_state()
        self._init_advisor_state()
        self._init_specializations_state()
        self._caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._init_api_poll_state()

        self._automation_tab = AutomationTab()
        self._automation_tab.running_changed.connect(self._on_automation_running_changed)
        self._automation_tab.api_poll_requested.connect(self._request_api_poll)
        self._formation_sync.connect(self._automation_tab.sync_fkeys_from_payload)

        self._sources_tab = SourcesTab()
        self._sources_tab.connect_save(self._dash_save_manual_path)
        self._sources_tab.connect_refresh(self._dash_refresh_install)

        tabs = QTabWidget()
        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        tabs.addTab(self._build_advisor_tab(), "Party Advisor")
        tabs.addTab(self._build_specializations_tab(), "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")
        self._tabs = tabs
        self.setCentralWidget(tabs)

        self._dash_timer = QTimer(self)
        self._dash_timer.setInterval(1000)
        self._dash_timer.timeout.connect(self._dash_poll_once)

        self._api_poll_timer.start()
        QTimer.singleShot(300, self._dash_auto_start)
        self._dash_refresh_install()"""

    new_init = """        self._init_advisor_state()
        self._init_specializations_state()
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
        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._build_advisor_tab(), "Party Advisor")
        tabs.addTab(self._build_specializations_tab(), "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")
        self._tabs = tabs
        self.setCentralWidget(tabs)

        self._api_poll_timer.start()
        QTimer.singleShot(300, self._dashboard_tab.auto_start)
        self._dashboard_tab.refresh_install()"""

    if old_init not in text:
        raise SystemExit("init block not found")
    text = text.replace(old_init, new_init)

    marker = "            self._tabs.setTabText(idx, f\"Automatisering [{'AAN' if running else 'UIT'}]\")\n"
    handler = marker + """
    def _on_dashboard_payload(self, payload: dict) -> None:
        self._automation_tab.set_formation_payload(payload)
        self._formation_sync.emit(payload)

"""
    text = text.replace(marker, handler, 1)

    for a, b in [
        ("self._dash_install", "self._dashboard_tab.install"),
        ("self._dash_credentials", "self._dashboard_tab.credentials"),
        ("self._dash_tailer", "self._dashboard_tab.tailer"),
        ("self._dash_last_payload", "self._dashboard_tab.last_payload"),
        ("self._dash_last_api_snap", "self._dashboard_tab.last_api_snap"),
        ("self._dash_api_detail", "self._dashboard_tab.api_detail"),
        ("self._dash_refresh_install()", "self._dashboard_tab.refresh_install()"),
        ("self._api_log_path()", "self._dashboard_tab.api_log_path()"),
        ("_ApiFetchRunnable", "ApiFetchRunnable"),
    ]:
        text = text.replace(a, b)

    old_apply = """        if api_detail:
            self._dashboard_tab.api_detail = api_detail
        if payload is not None:
            self._dashboard_tab.last_payload = payload
            self._automation_tab.set_formation_payload(payload)
            new_party_id = self._party_id_from_payload(payload)
            party_changed = (
                self._advisor_last_party_id is not None
                and new_party_id is not None
                and new_party_id != self._advisor_last_party_id
            )
            self._formation_sync.emit(payload)
            self._caption_refresh.emit()
        else:
            party_changed = False
        if api_snap is not None:
            self._dashboard_tab.last_api_snap = api_snap
        if snap is not None:
            self._dash_last_update = time.time()
            if payload is not None:
                snap = self._dash_refresh_snapshot(snap, payload)
            if self._dash_active and self._dash_tracker is not None:
                mem_area, mem_gems = self._dash_read_memory()
                if mem_area is not None or mem_gems is not None:
                    self._dash_tracker.add_memory_area(
                        mem_area,
                        gems=mem_gems,
                        active_party_index=snap.active_party_index,
                    )
                self._dash_tracker.add_snapshot(snap, api_snapshot=api_snap)
                self._dash_update_labels()"""

    new_apply = """        party_changed = False
        if payload is not None:
            new_party_id = self._party_id_from_payload(payload)
            party_changed = (
                self._advisor_last_party_id is not None
                and new_party_id is not None
                and new_party_id != self._advisor_last_party_id
            )
            self._caption_refresh.emit()
        self._dashboard_tab.ingest_api_result(result)"""

    if old_apply not in text:
        raise SystemExit("api apply chunk not found")
    text = text.replace(old_apply, new_apply)

    old_caption = """    def _refresh_app_caption_from_snapshots(self) -> None:
        latest = self._dash_tracker.latest if self._dash_tracker is not None else None
        party = self._dash_caption_party(latest)
        if party is None:
            self._update_app_caption()
            return
        adventure_id = party.adventure_id if party.adventure_id is not None and party.adventure_id >= 0 else None
        self._update_app_caption(party.party_index, adventure_id)"""

    new_caption = """    def _refresh_app_caption_from_snapshots(self) -> None:
        party = self._dashboard_tab.caption_party()
        if party is None:
            self._update_app_caption()
            return
        adventure_id = party.adventure_id if party.adventure_id is not None and party.adventure_id >= 0 else None
        self._update_app_caption(party.party_index, adventure_id)"""

    text = text.replace(old_caption, new_caption)

    text = text.replace(
        "        self._dash_stop()\n        self._dash_disconnect_memory()",
        "        self._dashboard_tab.stop()\n        self._dashboard_tab.disconnect_memory()",
    )

    text = text.replace(
        """    def _advisor_refresh_credentials(self) -> bool:
        if self._dashboard_tab.install is None or self._dashboard_tab.credentials is None:
            self._dashboard_tab.refresh_install()
        if self._dashboard_tab.install and self._dashboard_tab.install.web_request_log:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(Path(self._dashboard_tab.install.web_request_log))
            if fresh is not None:
                self._dashboard_tab.credentials = fresh
        return self._dashboard_tab.credentials is not None""",
        "    def _advisor_refresh_credentials(self) -> bool:\n        return self._dashboard_tab.refresh_credentials_from_log()",
    )

    path.write_text(text, encoding="utf-8")
    print(f"updated {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
