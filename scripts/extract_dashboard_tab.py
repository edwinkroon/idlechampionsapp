"""One-off helper to extract DashboardTab from pyside_app.py."""

from __future__ import annotations

from pathlib import Path


def find_def(lines: list[str], name: str, start: int = 0) -> int:
    needle = f"    def {name}"
    for i in range(start, len(lines)):
        if lines[i].startswith(needle):
            return i
    raise SystemExit(f"missing {name}")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    src_path = root / "ic_ui" / "pyside_app.py"
    lines = src_path.read_text(encoding="utf-8").splitlines(keepends=True)

    build_start = find_def(lines, "_build_dashboard_tab")
    build_end = find_def(lines, "_init_advisor_state", build_start)
    dash_start = find_def(lines, "_init_dashboard_state")
    dash_end = find_def(lines, "closeEvent", dash_start)

    build_body = lines[build_start + 1 : build_end]
    dash_body = lines[dash_start:dash_end]

    header = '''"""Live dashboard: party tiles, rates, memory reads."""

from __future__ import annotations

import json
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
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ic_ui.tabs.sources_tab import SourcesTab


class DashboardTab(QWidget):
    """Dashboard UI and session stats tracking."""

    payload_updated = Signal(object)
    caption_refresh = Signal()
    api_poll_requested = Signal()

    def __init__(self, sources_tab: SourcesTab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources_tab = sources_tab
        self._init_state()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_once)
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
        return self._dash_last_payload

    @property
    def last_api_snap(self):
        return self._dash_last_api_snap

    @property
    def api_detail(self) -> str:
        return self._dash_api_detail

    @api_detail.setter
    def api_detail(self, value: str) -> None:
        self._dash_api_detail = value

    @property
    def tracker(self):
        return self._dash_tracker

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
        api_snap = result.get("api_snap")
        snap = result.get("snap")
        api_detail = result.get("api_detail")
        if api_detail:
            self._dash_api_detail = api_detail
        if payload is not None:
            self._dash_last_payload = payload
            self.payload_updated.emit(payload)
        if api_snap is not None:
            self._dash_last_api_snap = api_snap
        if snap is not None:
            self._dash_last_update = time.time()
            if payload is not None:
                snap = self._refresh_snapshot(snap, payload)
            if self._dash_active and self._dash_tracker is not None:
                mem_area, mem_gems = self._read_memory()
                if mem_area is not None or mem_gems is not None:
                    self._dash_tracker.add_memory_area(
                        mem_area,
                        gems=mem_gems,
                        active_party_index=snap.active_party_index,
                    )
                self._dash_tracker.add_snapshot(snap, api_snapshot=api_snap)
                self._update_labels()

    def caption_party(self):
        latest = self._dash_tracker.latest if self._dash_tracker is not None else None
        return self._caption_party(latest)

    def auto_start(self) -> None:
        self._auto_start()

    def stop(self) -> None:
        self._stop()

    def disconnect_memory(self) -> None:
        self._disconnect_memory()

'''

    build_text = "".join(build_body)
    build_text = build_text.replace(
        "        refresh_btn.clicked.connect(self._dash_refresh_install)\n",
        "        refresh_btn.clicked.connect(self.refresh_install)\n",
    )
    build_text = build_text.replace("self._dash_toggle", "self._toggle")
    build_text = build_text.replace("self._dash_reset_session", "self.reset_session")

    dash_text = "".join(dash_body)
    dash_text = dash_text.replace("def _init_dashboard_state", "def _init_state")
    dash_text = dash_text.replace("def _dash_", "def _")
    dash_text = dash_text.replace("self._request_api_poll()", "self.api_poll_requested.emit()")
    dash_text = dash_text.replace(
        "self._refresh_app_caption_from_snapshots()",
        "self.caption_refresh.emit()",
    )
    dash_text = dash_text.replace(
        "IdleChampionsMainWindow._dash_format_number",
        "DashboardTab._format_number",
    )
    dash_text = dash_text.replace(
        "            self._automation_tab.set_formation_payload(payload)\n"
        "            self._formation_sync.emit(payload)\n",
        "",
    )
    dash_text = dash_text.replace("def _refresh_install", "def refresh_install")
    dash_text = dash_text.replace("def _save_manual_path", "def save_manual_path")
    dash_text = dash_text.replace("def _reset_session", "def reset_session")
    dash_text = dash_text.replace("self._dash_timer", "self._poll_timer")

    # Remove caption/window helpers moved to main window
    for fn in ("_app_title_base", "_update_app_caption", "_refresh_app_caption_from_snapshots"):
        start = dash_text.find(f"    def {fn}")
        if start == -1:
            continue
        end = dash_text.find("\n    def ", start + 1)
        if end == -1:
            end = len(dash_text)
        dash_text = dash_text[:start] + dash_text[end:]

    out_path = root / "ic_ui" / "tabs" / "dashboard_tab.py"
    out_path.write_text(header + build_text + "\n" + dash_text, encoding="utf-8")
    print(f"wrote {out_path} ({len(out_path.read_text(encoding='utf-8').splitlines())} lines)")


if __name__ == "__main__":
    main()
