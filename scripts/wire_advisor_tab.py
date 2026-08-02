"""Extract Party Advisor tab from pyside_app into ic_ui/tabs/advisor_tab.py."""

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

    # Remove portrait helpers + FormationSeatCard + AdvisorRunnable
    portrait_start = next(i for i, l in enumerate(lines) if l.startswith("def _widget_device_pixel_ratio"))
    spec_signals = next(i for i, l in enumerate(lines) if l.startswith("class _SpecializationsSignals"))
    lines = remove_range(lines, portrait_start, spec_signals)

    # Remove advisor tab methods (state through open_url)
    advisor_init = find_def(lines, "_init_advisor_state")
    spec_init = find_def(lines, "_init_specializations_state", advisor_init)
    lines = remove_range(lines, advisor_init, spec_init)

    text = "".join(lines)

    # Trim advisor-only theme imports
    old_theme = """from ic_ui.theme import (
    DEFAULT_WINDOW_TITLE,
    FORMATION_ZONE_BG,
    PORTRAIT_H,
    PORTRAIT_W,
    ACCENT as _ADVISOR_ACCENT,
    BG_CARD as _ADVISOR_CARD_BG,
    BG_INPUT as _ADVISOR_INPUT_BG,
    BORDER as _ADVISOR_INPUT_BORDER,
    BUD_BAR as _ADVISOR_BUD_BAR,
    DIVIDER as _ADVISOR_DIVIDER,
    FEAT_MISSING as _ADVISOR_FEAT_MISSING,
    FEAT_OWNED as _ADVISOR_FEAT_OWNED,
    SUCCESS as _ADVISOR_FEAT_ACTIVE,
    TEXT_BODY as _ADVISOR_BODY,
    TEXT_BADGE as _ADVISOR_BADGE_TEXT,
    BG_BADGE as _ADVISOR_BADGE_BG,
    TEXT_MUTED as _ADVISOR_MUTED,
    TEXT_PRIMARY as _ADVISOR_TEXT,
    WARN as _ADVISOR_WARN,
    WARN_BAR as _ADVISOR_WARN_BAR,
    advisor_accent_stylesheet as _advisor_accent_stylesheet,
    advisor_badge_stylesheet as _advisor_badge_stylesheet,
    advisor_card_stylesheet as _advisor_card_stylesheet,
    advisor_text_styles as _advisor_text_styles,
    portrait_placeholder_stylesheet as _portrait_placeholder_stylesheet,
)

_FORMATION_ZONE_BG = FORMATION_ZONE_BG
_ADVISOR_PORTRAIT_W = PORTRAIT_W
_ADVISOR_PORTRAIT_H = PORTRAIT_H


"""
    new_theme = ""
    if old_theme not in text:
        raise SystemExit("theme import block not found")
    text = text.replace(old_theme, new_theme)

    text = text.replace(
        "from ic_ui.tabs.automation_tab import AutomationTab\n"
        "from ic_ui.tabs.dashboard_tab import DashboardTab\n"
        "from ic_ui.tabs.sources_tab import SourcesTab\n",
        "from ic_ui.tabs.advisor_tab import AdvisorTab, party_id_from_payload\n"
        "from ic_ui.tabs.automation_tab import AutomationTab\n"
        "from ic_ui.tabs.dashboard_tab import DashboardTab\n"
        "from ic_ui.tabs.sources_tab import SourcesTab\n"
        "from ic_ui.widgets.advisor_widgets import advisor_card, advisor_card_layout, advisor_lbl\n",
    )

    text = text.replace(
        "from PySide6.QtGui import QColor, QPalette, QPixmap\n",
        "",
    )

    text = text.replace(
        "        self._init_advisor_state()\n        self._init_specializations_state()\n",
        "        self._init_specializations_state()\n",
    )

    old_tabs = """        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._build_advisor_tab(), "Party Advisor")
        tabs.addTab(self._build_specializations_tab(), "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")"""

    new_tabs = """        self._advisor_tab = AdvisorTab(self._dashboard_tab)
        self._advisor_tab.api_poll_requested.connect(
            lambda auto_refresh: self._request_api_poll(advisor_after=True, auto_refresh=auto_refresh)
        )

        tabs.addTab(self._automation_tab, "Automatisering [UIT]")
        tabs.addTab(self._dashboard_tab, "Dashboard")
        tabs.addTab(self._advisor_tab, "Party Advisor")
        tabs.addTab(self._build_specializations_tab(), "Specialisaties")
        tabs.addTab(self._sources_tab, "Bronnen")"""

    if old_tabs not in text:
        raise SystemExit("tabs block not found")
    text = text.replace(old_tabs, new_tabs)

    # Spec tab credential refresh
    text = text.replace(
        "        if not self._advisor_refresh_credentials():",
        "        if not self._dashboard_tab.refresh_credentials_from_log():",
    )

    # Spec tab UI helpers
    for old, new in [
        ("self._advisor_lbl(", "advisor_lbl("),
        ("self._advisor_card(", "advisor_card("),
        ("self._advisor_card_layout(", "advisor_card_layout("),
    ]:
        text = text.replace(old, new)

    # API poll: inflight message
    text = text.replace(
        """        if self._api_fetch_inflight:
            if advisor_after and not auto_refresh:
                self._advisor_status.setText("Data wordt al opgehaald…")
            return""",
        """        if self._api_fetch_inflight:
            if advisor_after and not auto_refresh:
                self._advisor_tab.notify_fetch_inflight(manual_request=True)
            return""",
    )

    text = text.replace(
        """        if self._dashboard_tab.credentials is None:
            if advisor_after and not auto_refresh:
                self._advisor_on_error("Geen API-credentials.")
            return""",
        """        if self._dashboard_tab.credentials is None:
            if advisor_after and not auto_refresh:
                self._advisor_tab.notify_fetch_credentials_error()
            return""",
    )

    text = text.replace(
        """            if advisor_after:
                if not auto_refresh:
                    self._advisor_btn_analyze.setEnabled(True)
                    self._advisor_on_error(err)
                elif not self._advisor_has_results:
                    self._advisor_status.setText(f"Wachten op API-data… ({err})")
            return""",
        """            if advisor_after:
                self._advisor_tab.notify_fetch_error(
                    err, auto_refresh=auto_refresh, advisor_after=True
                )
            return""",
    )

    old_apply = """        party_changed = False
        if payload is not None:
            new_party_id = self._party_id_from_payload(payload)
            party_changed = (
                self._advisor_last_party_id is not None
                and new_party_id is not None
                and new_party_id != self._advisor_last_party_id
            )
            self._caption_refresh.emit()
        self._dashboard_tab.ingest_api_result(result)
        if (
            payload is not None
            and not self._advisor_has_results
            and not self._advisor_analysing
        ):
            self._start_advisor_analysis(
                payload,
                err,
                auto_refresh=True,
                party_changed=False,
            )
            if not self._spec_has_results and not self._spec_analysing:
                self._start_specializations_analysis(
                    payload,
                    err,
                    auto_refresh=True,
                )
        elif party_changed and payload is not None:
            self._start_advisor_analysis(
                payload,
                err,
                auto_refresh=True,
                party_changed=True,
            )
            self._start_specializations_analysis(
                payload,
                err,
                auto_refresh=True,
            )
        elif advisor_after:
            if payload is not None:
                self._start_advisor_analysis(
                    payload,
                    err,
                    auto_refresh=auto_refresh,
                    party_changed=party_changed,
                )
                self._start_specializations_analysis(
                    payload,
                    err,
                    auto_refresh=auto_refresh,
                )
            elif not auto_refresh:
                self._advisor_btn_analyze.setEnabled(True)
                self._advisor_on_error(err or "Geen API-data ontvangen.")
            elif auto_refresh and not self._advisor_has_results:
                self._advisor_status.setText(err or "Wachten op API-data…")"""

    new_apply = """        party_changed = False
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
            if not self._spec_has_results and not self._spec_analysing:
                self._start_specializations_analysis(
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
            self._start_specializations_analysis(
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
                self._start_specializations_analysis(
                    payload,
                    err,
                    auto_refresh=auto_refresh,
                )
            else:
                self._advisor_tab.notify_fetch_no_payload(err, auto_refresh=auto_refresh)"""

    if old_apply not in text:
        raise SystemExit("api apply block not found")
    text = text.replace(old_apply, new_apply)

    path.write_text(text, encoding="utf-8")
    print(f"updated {path} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
