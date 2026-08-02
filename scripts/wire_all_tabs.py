"""Wire AutomationTab, SourcesTab, and DashboardTab into pyside_app."""

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

    # Remove ApiFetch classes
    api_start = next(i for i, l in enumerate(lines) if l.startswith("class _ApiFetchSignals"))
    advisor_start = next(i for i, l in enumerate(lines) if l.startswith("class _AdvisorRunnable"))
    lines = remove_range(lines, api_start, advisor_start)

    # Remove automation tab UI
    auto_start = find_def(lines, "_build_automation_tab")
    dash_build = find_def(lines, "_build_dashboard_tab", auto_start)
    lines = remove_range(lines, auto_start, dash_build)

    # Remove sources + automation logic before advisor
    sources_start = find_def(lines, "_build_sources_tab", dash_build)
    advisor_init = find_def(lines, "_init_advisor_state", sources_start)
    lines = remove_range(lines, sources_start, advisor_init)

    # Remove dashboard UI build
    dash_build = find_def(lines, "_build_dashboard_tab")
    advisor_init = find_def(lines, "_init_advisor_state", dash_build)
    lines = remove_range(lines, dash_build, advisor_init)

    # Remove dashboard state + helpers (keep window caption helpers)
    dash_comment = next(
        i for i, l in enumerate(lines) if l.strip() == "# ------------------------------------------------------------------ dashboard"
    )
    app_title = find_def(lines, "_app_title_base", dash_comment)
    party_from = find_def(lines, "_dash_party_from_snapshot", app_title)
    running = find_def(lines, "_dash_running_parties", party_from)
    close_event = find_def(lines, "closeEvent", running)

    # Remove from bottom to top so indices stay valid
    lines = remove_range(lines, party_from, close_event)
    lines = remove_range(lines, dash_comment, app_title)

    text = "".join(lines)

    # Imports
    text = text.replace(
        "from ic_automation import AutomationController, AutomationSettings\n"
        "from ic_automation import win_input\n"
        "from ic_ui.theme import (\n",
        "from ic_ui.tabs.automation_tab import AutomationTab\n"
        "from ic_ui.tabs.dashboard_tab import DashboardTab\n"
        "from ic_ui.tabs.sources_tab import SourcesTab\n"
        "from ic_ui.workers.api_fetch import ApiFetchRunnable\n"
        "from ic_ui.theme import (\n",
    )
    text = text.replace(
        "    FKEY_FAMILIAR_COLOR,\n    FORMATION_ZONE_BG,\n",
        "    FORMATION_ZONE_BG,\n",
    )
    text = text.replace(
        "    STATUS_IDLE,\n    TEXT_MUTED,\n",
        "",
    )
    text = text.replace(
        "_FKEY_FAMILIAR_COLOR = FKEY_FAMILIAR_COLOR\n",
        "",
    )

    # Remove AutomationWidgets dataclass
    start = text.find("@dataclass\nclass AutomationWidgets:")
    end = text.find("\ndef _widget_device_pixel_ratio", start)
    text = text[:start] + text[end + 1 :]

    text = text.replace("from dataclasses import dataclass\n", "")

    old_init = """        self._running = False
        self._automation = AutomationController()
        self._init_dashboard_state()
        self._init_advisor_state()
        self._init_specializations_state()
        self._formation_seats: frozenset[int] | None = None
        self._formation_party_id: int | None = None
        self._familiar_level_seats: frozenset[int] = frozenset()
        self._formation_poll_tick = 0
        self._caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._formation_sync.connect(self._sync_fkeys_from_payload)
        self._init_api_poll_state()

        tabs = QTabWidget()
        tabs.addTab(self._build_automation_tab(), "Automatisering [UIT]")
        tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        tabs.addTab(self._build_advisor_tab(), "Party Advisor")
        tabs.addTab(self._build_specializations_tab(), "Specialisaties")
        tabs.addTab(self._build_sources_tab(), "Bronnen")
        self._tabs = tabs
        self.setCentralWidget(tabs)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._poll_status)
        self._dash_timer = QTimer(self)
        self._dash_timer.setInterval(1000)
        self._dash_timer.timeout.connect(self._dash_poll_once)

        self._api_poll_timer.start()
        QTimer.singleShot(300, self._dash_auto_start)"""

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
    if marker not in text:
        insert_at = text.find("    def _build_placeholder_tab")
        handler = (
            "    def _on_automation_running_changed(self, running: bool) -> None:\n"
            "        idx = self._tabs.indexOf(self._automation_tab)\n"
            "        if idx >= 0:\n"
            "            self._tabs.setTabText(idx, f\"Automatisering [{'AAN' if running else 'UIT'}]\")\n\n"
            "    def _on_dashboard_payload(self, payload: dict) -> None:\n"
            "        self._automation_tab.set_formation_payload(payload)\n"
            "        self._formation_sync.emit(payload)\n\n"
        )
        text = text[:insert_at] + handler + text[insert_at:]
    else:
        text = text.replace(
            marker,
            marker + "\n"
            "    def _on_dashboard_payload(self, payload: dict) -> None:\n"
            "        self._automation_tab.set_formation_payload(payload)\n"
            "        self._formation_sync.emit(payload)\n\n",
            1,
        )

    old_apply = """        if api_detail:
            self._dash_api_detail = api_detail
        if payload is not None:
            self._dash_last_payload = payload
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
            self._dash_last_api_snap = api_snap
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

    text = text.replace(
        "        self._stop_automation()\n        self._dash_stop()\n        self._dash_disconnect_memory()",
        "        self._automation_tab.stop()\n        self._dashboard_tab.stop()\n        self._dashboard_tab.disconnect_memory()",
    )

    text = text.replace(
        """    def _advisor_refresh_credentials(self) -> bool:
        if self._dash_install is None or self._dash_credentials is None:
            self._dash_refresh_install()
        if self._dash_install and self._dash_install.web_request_log:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(Path(self._dash_install.web_request_log))
            if fresh is not None:
                self._dash_credentials = fresh
        return self._dash_credentials is not None""",
        "    def _advisor_refresh_credentials(self) -> bool:\n        return self._dashboard_tab.refresh_credentials_from_log()",
    )

    path.write_text(text, encoding="utf-8")
    print(f"updated {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
