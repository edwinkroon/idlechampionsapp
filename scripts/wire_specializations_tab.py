"""Extract Specializations tab from pyside_app."""

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

    spec_start = next(i for i, l in enumerate(lines) if l.startswith("class _SpecializationsSignals"))
    main_window = next(i for i, l in enumerate(lines) if l.startswith("class IdleChampionsMainWindow"))
    lines = remove_range(lines, spec_start, main_window)

    spec_init = find_def(lines, "_init_specializations_state")
    api_poll = next(
        i for i, l in enumerate(lines) if l.strip() == "# ------------------------------------------------------------------ central API poll"
    )
    lines = remove_range(lines, spec_init, api_poll)

    text = "".join(lines)

    text = text.replace(
        "from ic_ui.tabs.sources_tab import SourcesTab\n"
        "from ic_ui.widgets.advisor_widgets import advisor_card, advisor_card_layout, advisor_lbl\n",
        "from ic_ui.tabs.sources_tab import SourcesTab\n"
        "from ic_ui.tabs.specializations_tab import SpecializationsTab\n",
    )

    text = text.replace(
        "        self._init_specializations_state()\n        self._caption_refresh.connect",
        "        self._caption_refresh.connect",
    )

    old_tabs = """        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._advisor_tab, "Party Advisor")
        tabs.addTab(self._build_specializations_tab(), "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")"""

    new_tabs = """        self._specializations_tab = SpecializationsTab(self._dashboard_tab)

        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._advisor_tab, "Party Advisor")
        tabs.addTab(self._specializations_tab, "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")"""

    if old_tabs not in text:
        raise SystemExit("tabs block not found")
    text = text.replace(old_tabs, new_tabs)

    text = text.replace(
        "            if not self._spec_has_results and not self._spec_analysing:\n"
        "                self._start_specializations_analysis(\n",
        "            if not self._specializations_tab.has_results and not self._specializations_tab.analysing:\n"
        "                self._specializations_tab.start_analysis(\n",
    )
    text = text.replace(
        "            self._start_specializations_analysis(\n",
        "            self._specializations_tab.start_analysis(\n",
    )
    text = text.replace(
        "                self._start_specializations_analysis(\n",
        "                self._specializations_tab.start_analysis(\n",
    )

    # Remove unused imports if any remain
    for unused in [
        "import json\n",
        "import queue\n",
        "import threading\n",
        "    QCheckBox,\n",
        "    QFormLayout,\n",
        "    QGridLayout,\n",
        "    QGroupBox,\n",
        "    QLineEdit,\n",
        "    QMessageBox,\n",
        "    QSizePolicy,\n",
    ]:
        text = text.replace(unused, "")

    text = text.replace("from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool", "from PySide6.QtCore import QThreadPool")

    path.write_text(text, encoding="utf-8")
    print(f"updated {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
