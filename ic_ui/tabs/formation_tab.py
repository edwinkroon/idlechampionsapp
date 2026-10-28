"""Formation tab: active party layout and owned optimal projection.

External AI export / paste / before-after preview lives on the Advice tab.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ic_gamedata.advice_fingerprint import (
    commit_advice_fingerprint,
    party_id_from_payload,
    should_refresh_advice,
)
from ic_ui import theme as ui_theme
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.theme import on_theme_changed
from ic_ui.widgets.advisor_controls import (
    read_shared_advice_context,
    read_shared_advice_goal,
)
from ic_ui.widgets.advisor_widgets import (
    add_formation_board,
    add_gear_investment_section,
    add_next_actions_section,
    advisor_card,
    advisor_card_layout,
    advisor_lbl,
    advisor_section,
    clear_advisor_layout,
    refresh_advisor_chrome,
)
from ic_ui.workers.shared_advice import SharedAdviceResult, shared_advice_hub

if TYPE_CHECKING:
    from ic_core.game_data_service import GameDataService, SnapshotEnvelope


def _formation_render_key(report: Any) -> tuple[Any, ...] | None:
    """Stable key for skipping identical auto-refresh board rebuilds."""
    if report is None:
        return None
    seat = getattr(report, "seat_report", None)
    nodes: tuple[Any, ...] = ()
    if seat is not None:
        nodes = tuple(
            (getattr(n, "seat", None), getattr(n, "hero_id", None))
            for n in (getattr(seat, "visual_nodes", None) or ())
        )
    return (
        getattr(report, "goal", None),
        getattr(report, "context", None),
        getattr(report, "summary", None),
        nodes,
    )


class FormationTab(QWidget):
    """Show the live formation and the owned optimal projection when available."""

    formation_updated = Signal()

    def __init__(
        self,
        dashboard_tab: DashboardTab,
        parent: QWidget | None = None,
        *,
        data_service: GameDataService | None = None,
    ) -> None:
        super().__init__(parent)
        self._dashboard_tab = dashboard_tab
        self._data = data_service
        self._last_party_id: int | None = None
        self._last_advice_fp: tuple[Any, ...] | None = None
        self._last_formation_empty = False
        self._running_advice_fp: tuple[Any, ...] | None = None
        self._analysing = False
        self._has_results = False
        self._last_report = None
        self._last_payload: dict | None = None
        self._pending_auto_refresh = False
        self._pending_analysis: tuple[
            dict, str | None, bool, bool, tuple[Any, ...] | None
        ] | None = None
        self._build_ui()
        on_theme_changed(self._on_theme_changed)

    @property
    def last_payload(self) -> dict | None:
        return self._last_payload

    @property
    def last_report(self):
        return self._last_report

    @property
    def last_party_id(self) -> int | None:
        return self._last_party_id

    def _on_theme_changed(self, _mode: str) -> None:
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        if self._last_report is not None:
            self._render_report(self._last_report, reset_scroll=False)
        else:
            refresh_advisor_chrome(self)

    @property
    def last_formation_empty(self) -> bool:
        return self._last_formation_empty

    @property
    def analysing(self) -> bool:
        return self._analysing

    def on_snapshot(self, envelope: SnapshotEnvelope) -> None:
        force = "formation" in envelope.force_consumers
        fp = envelope.advice_fp
        first = not self._has_results and envelope.payload is not None
        changed = (
            envelope.payload is not None
            and fp is not None
            and fp != self._last_advice_fp
        )
        empty_retry = (
            envelope.payload is not None
            and self._last_formation_empty
            and self._has_results
            and not self._analysing
        )
        # Detect party switch before the refresh gate — otherwise degraded polls
        # can skip re-analysis and Advies keeps showing the previous party.
        party_changed = (
            self._last_party_id is not None
            and envelope.party_id is not None
            and envelope.party_id != self._last_party_id
        )
        if not should_refresh_advice(
            force=force,
            first=first,
            changed=changed,
            empty_retry=empty_retry,
            degraded=envelope.degraded,
            party_changed=party_changed,
        ):
            return
        if envelope.payload is None:
            if force and not envelope.auto_refresh:
                self._status.setText(envelope.err or "No API data received.")
            return
        self.start_analysis(
            envelope.payload,
            envelope.err,
            auto_refresh=envelope.auto_refresh or not force,
            party_changed=party_changed,
            advice_fp=fp,
        )

    def notify_waiting_for_data(self) -> None:
        self._status.setText("Waiting for API data…")

    def request_refresh(self, *, auto_refresh: bool = False) -> None:
        """Re-analyze from cache and force a poll (used when advice goal changes)."""
        if self._data is None:
            self._status.setText("No data service — restart the app.")
            return
        if not auto_refresh:
            self._status.setText("Loading formation…")
        if not self._data.refresh_credentials() and self._data.credentials is None:
            if not auto_refresh:
                self._status.setText(
                    "No API credentials. Go to Dashboard → Search again."
                )
            return
        cached = self._data.last_payload
        if cached is not None:
            from ic_gamedata.advice_fingerprint import advice_fingerprint

            self.start_analysis(
                cached,
                None,
                auto_refresh=auto_refresh,
                advice_fp=advice_fingerprint(cached),
            )
        self._data.request_poll(
            reason="formation",
            force_consumers={"formation"},
            auto_refresh=auto_refresh,
        )

    def start_analysis(
        self,
        payload: dict,
        err: str | None,
        *,
        auto_refresh: bool,
        party_changed: bool = False,
        advice_fp: tuple[Any, ...] | None = None,
    ) -> None:
        if self._analysing:
            self._pending_analysis = (
                payload,
                err,
                auto_refresh,
                party_changed,
                advice_fp,
            )
            return
        goal = read_shared_advice_goal() or "push"
        context = read_shared_advice_context()
        self._pending_auto_refresh = auto_refresh
        self._running_advice_fp = advice_fp
        self._set_analysing(True)
        self._last_payload = payload
        target = party_id_from_payload(payload)
        if party_changed:
            party_txt = f"party {target}" if target is not None else "new party"
            self._status.setText(f"Party switched ({party_txt}) — loading formation…")
        elif not auto_refresh:
            self._status.setText("Loading formation…")
        else:
            self._status.setText("Updating formation…")
        shared_advice_hub().submit(
            goal=goal,
            context=context,
            payload=payload,
            err=err,
            advice_fp=advice_fp,
            on_done=self._on_shared_done,
            on_error=self._on_error,
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        hint = QLabel(
            "Live formatie en optimale projectie. "
            "Externe AI-export/plak staat op de tab Advies."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        status_row.addWidget(hint, stretch=1)
        from ic_ui.widgets.busy_indicator import BusySpinner

        self._busy_spinner = BusySpinner(self, size=14)
        status_row.addWidget(self._busy_spinner, stretch=0)
        self._status = QLabel("Formatie laden… Refresh (F5) voor een update.")
        self._status.setWordWrap(False)
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        status_row.addWidget(self._status, stretch=0)
        root.addLayout(status_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll = scroll

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._content)
        self._layout.setSpacing(10)
        self._layout.setContentsMargins(4, 4, 8, 20)
        scroll.setWidget(self._content)
        root.addWidget(scroll, stretch=1)

        empty = advisor_card(compact=True)
        empty_lyt = advisor_card_layout(empty, compact=True)
        empty_lyt.addWidget(
            advisor_lbl(
                "Nog geen formatie. Zet champions in Idle Champions "
                "of druk op Refresh (F5).",
                kind="muted",
            )
        )
        self._layout.addWidget(empty)
        self._layout.addStretch(1)

    def _clear(self) -> None:
        clear_advisor_layout(self._layout)

    def _on_shared_done(self, result: SharedAdviceResult) -> None:
        self._on_done((result.payload, result.report, result.err))

    def _on_done(self, result) -> None:
        auto_refresh = self._pending_auto_refresh
        self._set_analysing(False)
        payload, report, err = result
        prev_key = _formation_render_key(self._last_report)
        self._last_report = report
        self._last_payload = payload
        self._has_results = True
        self._last_party_id = party_id_from_payload(payload)
        seat = report.seat_report
        active_nodes = (
            any(n.hero_id is not None for n in seat.visual_nodes) if seat else False
        )
        self._last_formation_empty = not bool(seat and (active_nodes or seat.seats))
        self._last_advice_fp = commit_advice_fingerprint(
            self._running_advice_fp,
            formation_empty=self._last_formation_empty,
        )
        self._running_advice_fp = None
        status = f"Bijgewerkt {time.strftime('%H:%M:%S')}"
        if err:
            status = f"{status} · {err}"
        self._status.setText(status)
        new_key = _formation_render_key(report)
        if auto_refresh and prev_key is not None and prev_key == new_key:
            # Same board — skip widget rebuild; still notify Advies for freshness.
            self.formation_updated.emit()
            self._drain_pending_analysis()
        else:
            # Yield so the title bar can paint before board/portrait rebuild.
            QTimer.singleShot(
                0,
                lambda r=report, rs=not auto_refresh: self._finish_render(r, rs),
            )

    def _finish_render(self, report, reset_scroll: bool) -> None:
        self._render_report(report, reset_scroll=reset_scroll)
        self.formation_updated.emit()
        self._drain_pending_analysis()

    def _drain_pending_analysis(self) -> None:
        pending = self._pending_analysis
        self._pending_analysis = None
        if pending is not None:
            p_payload, p_err, p_auto, p_changed, p_fp = pending
            self.start_analysis(
                p_payload,
                p_err,
                auto_refresh=p_auto,
                party_changed=p_changed,
                advice_fp=p_fp,
            )

    def _on_error(self, msg: str) -> None:
        self._set_analysing(False)
        self._running_advice_fp = None
        self._status.setText(msg)
        pending = self._pending_analysis
        self._pending_analysis = None
        if pending is not None:
            p_payload, p_err, p_auto, p_changed, p_fp = pending
            self.start_analysis(
                p_payload,
                p_err,
                auto_refresh=p_auto,
                party_changed=p_changed,
                advice_fp=p_fp,
            )

    def _set_analysing(self, busy: bool) -> None:
        self._analysing = busy
        if busy:
            self._busy_spinner.start()
        else:
            self._busy_spinner.stop()

    def _render_report(self, report, *, reset_scroll: bool) -> None:
        self._clear()
        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"

        seat_report = report.seat_report
        formation_name = (
            getattr(seat_report, "formation_name", None) if seat_report else None
        )
        section_title = (
            f"Active formation — {formation_name}"
            if formation_name
            else "Active formation"
        )
        advisor_section(self._layout, section_title)

        active_nodes = []
        if seat_report is not None:
            active_nodes = [
                n for n in seat_report.visual_nodes if n.hero_id is not None
            ]

        if not active_nodes:
            empty = advisor_card(compact=True)
            empty_lyt = advisor_card_layout(empty, compact=True)
            empty_lyt.addWidget(
                advisor_lbl(
                    "No champions found in formation. Place heroes in seats in "
                    "Idle Champions and click Refresh (top right / F5), or wait "
                    "for the next API poll.",
                    kind="muted",
                )
            )
            self._layout.addWidget(empty)
        else:
            add_formation_board(
                self._layout,
                active_nodes,
                role_label=role_label,
                intro="Enemies → right (front = toward the right).",
                issue_border_label="attention / mismatch",
                legend_lang="en",
            )

        advisor_section(self._layout, "Optimal formation")
        recommended = []
        if seat_report is not None:
            recommended = [
                n
                for n in getattr(seat_report, "recommended_visual_nodes", ())
                if n.hero_id is not None
            ]
        if recommended:
            add_formation_board(
                self._layout,
                recommended,
                role_label=role_label,
                intro="Safe upgrade projection based on your current owned champions.",
                issue_border_label="attention / mismatch",
                legend_lang="en",
            )
        else:
            hidden_reason = (
                getattr(seat_report, "recommended_hidden_reason", None)
                if seat_report
                else None
            )
            card = advisor_card(compact=True)
            lyt = advisor_card_layout(card, compact=True)
            lyt.addWidget(
                advisor_lbl(
                    hidden_reason
                    or "No optimal formation available yet for this party/goal.",
                    kind="muted",
                )
            )
            self._layout.addWidget(card)

        try:
            from ic_gamedata.next_actions import build_next_actions
        except ImportError:
            build_next_actions = None
        if build_next_actions is not None:
            add_next_actions_section(self._layout, build_next_actions(report))

        try:
            from ic_gamedata.gear_investment import recommend_gear_investment
        except ImportError:
            recommend_gear_investment = None
        if recommend_gear_investment is not None:
            add_gear_investment_section(
                self._layout,
                recommend_gear_investment(
                    report.formation_heroes,
                    goal=getattr(report, "goal", "bud") or "bud",
                ),
            )

        self._layout.addStretch(1)
        if reset_scroll:
            self._scroll.verticalScrollBar().setValue(0)
        refresh_advisor_chrome(self)
