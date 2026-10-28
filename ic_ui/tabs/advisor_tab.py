"""Coach tab: seat roles, feats, and specializations."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
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
from ic_ui.theme import (
    apply_button_icon,
    on_theme_changed,
)
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar
from ic_ui.widgets.advisor_widgets import (
    advisor_card,
    advisor_card_layout,
    advisor_lbl,
    advisor_link_btn,
    advisor_portrait,
    advisor_role_combo,
    advisor_section,
    advisor_status_dot,
    advisor_tag_pill,
    clear_advisor_layout,
    refresh_advisor_chrome,
)
from ic_ui.widgets.busy_indicator import StatusBusyRow
from ic_ui.ui_action_log import note_ui_action
from ic_ui.widgets.specialization_advice_ui import (
    render_compact_specializations_section,
)
from ic_ui.workers.roster_upgrade import RosterUpgradeRunnable
from ic_ui.workers.shared_advice import SharedAdviceResult, shared_advice_hub

if TYPE_CHECKING:
    from ic_core.game_data_service import GameDataService, SnapshotEnvelope
    from ic_gamedata.roster_upgrade_advisor import RosterUpgradeSuggestion


def _advisor_render_key(report: Any) -> tuple[Any, ...] | None:
    if report is None:
        return None
    seats: tuple[Any, ...] = ()
    seat_report = getattr(report, "seat_report", None)
    if seat_report is not None:
        seats = tuple(
            (
                getattr(s, "seat", None),
                getattr(s, "hero_id", None),
                getattr(s, "effective_role", None) or getattr(s, "inferred_role", None),
            )
            for s in (getattr(seat_report, "seats", None) or ())
        )
    return (
        getattr(report, "goal", None),
        getattr(report, "context", None),
        getattr(report, "summary", None),
        seats,
    )


class AdvisorTab(QWidget):
    """Analyze party composition, seats, feats, and specializations."""

    # Role prefs are outside the payload fingerprint — ask the main window to
    # re-run the shared advice hub so Formation optimal / next actions refresh.
    advice_resync_requested = Signal()

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
        self._last_payload = None
        self._last_goal = "bud"
        self._last_context = "campaign"
        self._last_party_id: int | None = None
        self._last_advice_fp: tuple[Any, ...] | None = None
        self._last_formation_empty = False
        self._running_advice_fp: tuple[Any, ...] | None = None
        self._analysing = False
        self._roster_searching = False
        self._roster_suggestions: tuple[RosterUpgradeSuggestion, ...] = ()
        self._last_report = None
        self._last_pending_items: tuple[Any, ...] = ()
        self._pending_auto_refresh = False
        self._pending_analysis: tuple[
            dict, str | None, bool, bool, tuple[Any, ...] | None
        ] | None = None
        self._current_party_changed = False
        self._has_results = False
        self._roster_worker_signals = None
        self._options_timer = QTimer(self)
        self._options_timer.setSingleShot(True)
        self._options_timer.setInterval(80)
        self._options_timer.timeout.connect(self._apply_options_reanalyze)
        self._build_ui()
        on_theme_changed(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_BODY};")
        if self._last_report is not None:
            self._render_report(self._last_report, reset_scroll=False)
        else:
            refresh_advisor_chrome(self)

    @property
    def last_party_id(self) -> int | None:
        return self._last_party_id

    @property
    def has_results(self) -> bool:
        return self._has_results

    @property
    def analysing(self) -> bool:
        return self._analysing

    @property
    def last_formation_empty(self) -> bool:
        return self._last_formation_empty

    def on_snapshot(self, envelope: SnapshotEnvelope) -> None:
        """React to GameDataService updates — refresh when advice-relevant data changes."""
        force = "advisor" in envelope.force_consumers
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
        party_changed = (
            self._last_party_id is not None
            and envelope.party_id is not None
            and envelope.party_id != self._last_party_id
        )
        # Degraded timer polls keep cache; party switches always re-analyze.
        if not should_refresh_advice(
            force=force,
            first=first,
            changed=changed,
            empty_retry=empty_retry,
            degraded=envelope.degraded,
            party_changed=party_changed,
        ):
            if envelope.degraded and envelope.err and self._has_results:
                self._status.setText(
                    f"{self._status.text().split(' · ')[0]} · {envelope.err}"
                    if self._status.text()
                    else envelope.err
                )
            return
        if envelope.payload is None:
            if force and not envelope.auto_refresh:
                self.notify_fetch_no_payload(envelope.err, auto_refresh=False)
            return
        err = envelope.err
        if envelope.quality and envelope.quality.warnings:
            warn = envelope.quality.warnings[0]
            err = f"{err} · {warn}" if err else warn
        self.start_analysis(
            envelope.payload,
            err,
            auto_refresh=envelope.auto_refresh or not force,
            party_changed=party_changed,
            advice_fp=fp,
        )

    def notify_waiting_for_data(self) -> None:
        self._status.setText("Waiting for API data…")

    def request_analyze(self, *, auto_refresh: bool = False) -> None:
        """Re-analyze from cache and force a poll (used by goal changes / tests)."""
        if self._data is None:
            self._status.setText("No data service — restart the app.")
            return
        if not auto_refresh:
            self._status.setText("Analyzing…")
        if not self._data.refresh_credentials() and self._data.credentials is None:
            if not auto_refresh:
                self._status.setText("No API credentials. Go to Dashboard → Search again.")
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
            reason="advisor",
            force_consumers={"advisor"},
            auto_refresh=auto_refresh,
        )

    def request_roster_upgrades(self) -> None:
        """On-demand search for owned champions that may improve the active party."""
        payload = self._last_payload
        if payload is None and self._data is not None:
            payload = self._data.last_payload
        if payload is None:
            self._status.setText("No party data yet — analyze first or wait for an API poll.")
            return
        if self._roster_searching:
            return
        self._last_goal = self._controls.goal()
        self._last_context = self._controls.context()
        self._roster_searching = True
        self._status.setText("Comparing owned champions to the current party…")
        worker = RosterUpgradeRunnable(
            self._last_goal,
            self._last_context,
            payload,
            signals_parent=self,
        )
        self._roster_worker_signals = worker.signals
        worker.signals.done.connect(self._on_roster_upgrades_done)
        worker.signals.error.connect(self._on_roster_upgrades_error)
        QThreadPool.globalInstance().start(worker)

    def _on_roster_upgrades_done(self, suggestions) -> None:
        self._roster_worker_signals = None
        self._roster_searching = False
        self._roster_suggestions = tuple(suggestions or ())
        if not self._roster_suggestions:
            self._status.setText(
                "No clear owned upgrade found — roles covered, or no safe "
                "BUD swap (support ilvl alone is no longer a reason)."
            )
        else:
            self._status.setText(
                f"Found {len(self._roster_suggestions)} possible party upgrade(s)."
            )
        if self._last_report is not None:
            scroll_y = self._scroll.verticalScrollBar().value()
            self._render_report(self._last_report, reset_scroll=False)
            self._scroll.verticalScrollBar().setValue(scroll_y)

    def _on_roster_upgrades_error(self, msg: str) -> None:
        self._roster_worker_signals = None
        self._roster_searching = False
        self._status.setText(f"Better champs failed: {msg}")

    def notify_fetch_inflight(self, *, manual_request: bool) -> None:
        if manual_request:
            self._status.setText(
                "Data is already being fetched… Try again shortly or wait for the poll."
            )

    def notify_fetch_credentials_error(self) -> None:
        self._on_error("No API credentials.")

    def notify_fetch_error(self, err: str, *, auto_refresh: bool, advisor_after: bool) -> None:
        self._dashboard_tab.api_detail = err
        if advisor_after:
            if not auto_refresh:
                self._on_error(err)
            elif not self._has_results:
                self._status.setText(f"Waiting for API data… ({err})")

    def notify_fetch_no_payload(self, err: str | None, *, auto_refresh: bool) -> None:
        if not auto_refresh:
            self._on_error(err or "No API data received.")
        elif auto_refresh and not self._has_results:
            self._status.setText(err or "Waiting for API data…")

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
            self._pending_analysis = (payload, err, auto_refresh, party_changed, advice_fp)
            return
        goal = self._controls.goal()
        context = self._controls.context()
        self._pending_auto_refresh = auto_refresh
        self._current_party_changed = party_changed
        self._running_advice_fp = advice_fp
        # Drop Better champs as soon as advice-relevant data changes — they are
        # scored for a prior formation/carry and look stale until re-clicked.
        fp_changed = advice_fp is not None and advice_fp != self._last_advice_fp
        if (party_changed or fp_changed) and self._roster_suggestions:
            self._roster_suggestions = ()
            if self._last_report is not None:
                self._render_report(self._last_report, reset_scroll=False)
        self._set_analysing(True)
        target = party_id_from_payload(payload)
        if party_changed:
            party_txt = f"party {target}" if target is not None else "new party"
            self._status.setText(f"Party switched ({party_txt}) — analyzing…")
        elif not auto_refresh:
            self._status.setText("Analyzing…")
        else:
            self._status.setText("Updating…")
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
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        ctrl_row = QHBoxLayout()
        self._controls = AdvisorGoalContextBar(include_formation=False)
        self._controls.changed.connect(self._on_options_changed)
        ctrl_row.addWidget(self._controls, stretch=1)
        self._btn_copy = QPushButton("Copy")
        apply_button_icon(self._btn_copy, "copy")
        self._btn_copy.setToolTip("Copy a short advice summary to the clipboard")
        self._btn_copy.setEnabled(False)
        self._btn_copy.clicked.connect(self._copy_advice_summary)
        ctrl_row.addWidget(self._btn_copy)
        root.addLayout(ctrl_row)

        self._status = StatusBusyRow()
        self._status.setText(
            "Starts automatically once game data is available. "
            "Use Refresh (top right / F5) for a full update. "
            "For active/optimal layout, see Advies."
        )
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_BODY};")
        root.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll = scroll

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._content)
        self._layout.setSpacing(10)
        self._layout.setContentsMargins(12, 8, 16, 28)
        scroll.setWidget(self._content)
        scroll.setVisible(False)
        root.addWidget(scroll, stretch=1)

    def _on_options_changed(self, *_args) -> None:
        if self._last_payload is None:
            return
        self._last_goal = self._controls.goal()
        self._last_context = self._controls.context()
        note_ui_action(
            f"Coach: doel/context → {self._last_goal} / {self._last_context}"
        )
        self._roster_suggestions = ()
        # Defer so the combo popup can close before analysis starts.
        self._options_timer.start()

    def _apply_options_reanalyze(self) -> None:
        """Re-run shared advice off the UI thread after goal/context change."""
        if self._last_payload is None:
            return
        fp = None
        try:
            from ic_gamedata.advice_fingerprint import advice_fingerprint

            fp = advice_fingerprint(self._last_payload)
        except Exception:
            fp = None
        self.start_analysis(
            self._last_payload,
            None,
            auto_refresh=True,
            advice_fp=fp,
        )

    def _schedule_pending_analysis(self) -> None:
        pending = self._pending_analysis
        if pending is None or self._analysing:
            return
        payload, err, auto_refresh, party_changed, advice_fp = pending
        self._pending_analysis = None
        self.start_analysis(
            payload,
            err,
            auto_refresh=auto_refresh,
            party_changed=party_changed,
            advice_fp=advice_fp,
        )

    def _commit_advice_fp(self, *, formation_empty: bool) -> None:
        self._last_advice_fp = commit_advice_fingerprint(
            self._running_advice_fp,
            formation_empty=formation_empty,
        )

    def _on_shared_done(self, result: SharedAdviceResult) -> None:
        self._last_pending_items = tuple(result.pending or ())
        self._on_done((result.payload, result.report, result.err))

    def _on_done(self, result) -> None:
        payload, report, err = result
        auto_refresh = self._pending_auto_refresh
        party_id = party_id_from_payload(payload)
        party_changed = self._current_party_changed or (
            self._last_party_id is not None
            and party_id is not None
            and party_id != self._last_party_id
        )
        self._last_payload = payload
        self._last_party_id = party_id
        # Seat cards are the champ overview — retry while seats fail to resolve
        # even if formation_heroes/tips already populated the status line.
        self._last_formation_empty = not bool(
            report.seat_report and report.seat_report.seats
        )
        fp_changed = (
            self._running_advice_fp is not None
            and self._running_advice_fp != self._last_advice_fp
        )
        if party_changed or fp_changed:
            self._roster_suggestions = ()
        self._commit_advice_fp(formation_empty=self._last_formation_empty)
        self._running_advice_fp = None
        self._last_goal = report.goal
        self._last_context = report.context
        prev_key = _advisor_render_key(self._last_report)
        self._last_report = report
        self._set_analysing(False)
        status = report.summary
        if err:
            status = f"{status} ({err})"
        if party_changed:
            party_txt = f"party {party_id}" if party_id is not None else "new party"
            status = f"{status} · {party_txt}"
        status = f"{status} · refreshed {time.strftime('%H:%M:%S')}"
        self._status.setText(status)
        new_key = _advisor_render_key(report)
        skip_render = (
            auto_refresh
            and not party_changed
            and self._has_results
            and prev_key is not None
            and prev_key == new_key
        )
        if skip_render:
            self._schedule_pending_analysis()
            return
        reset_scroll = not auto_refresh or not self._has_results or party_changed
        # Yield so status/spinner clear before seat-card rebuild (first poll).
        QTimer.singleShot(
            0,
            lambda r=report, rs=reset_scroll: self._finish_render(r, rs),
        )

    def _finish_render(self, report, reset_scroll: bool) -> None:
        self._render_report(report, reset_scroll=reset_scroll)
        self._schedule_pending_analysis()

    def _on_error(self, msg: str) -> None:
        auto_refresh = self._pending_auto_refresh
        self._running_advice_fp = None
        self._set_analysing(False)
        if auto_refresh and self._has_results:
            self._status.setText(f"Refresh failed: {msg} (kept last result)")
        else:
            self._status.setText(f"Error: {msg}")
        self._schedule_pending_analysis()

    def _set_analysing(self, busy: bool) -> None:
        self._analysing = busy
        self._status.set_busy(busy)
        self.setToolTip("Analyzing…" if busy else "")

    def _on_role_selected(self, hero_id: int, role: str) -> None:
        try:
            from ic_gamedata.seat_advisor import set_chosen_role
        except ImportError:
            return
        set_chosen_role(hero_id, self._last_goal, role if role else None)
        # Shared hub (background) refreshes Coach + Formation — never sync analyze.
        self.advice_resync_requested.emit()

    def _clear(self) -> None:
        clear_advisor_layout(self._layout)

    def _show_results_panel(self) -> None:
        if self._has_results:
            return
        self._has_results = True
        self._scroll.setVisible(True)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._content.setStyleSheet("background: transparent;")

    def _render_report(self, report, *, reset_scroll: bool = True) -> None:
        self._show_results_panel()
        self._clear()

        if not (report.seat_report and report.seat_report.seats):
            empty = advisor_card(compact=True)
            empty_lyt = advisor_card_layout(empty, compact=True)
            empty_lyt.addWidget(
                advisor_lbl(
                    "No champions found in formation. Place heroes in seats in Idle Champions "
                    "and click Refresh (top right / F5), or wait for the next API poll.",
                    kind="muted",
                )
            )
            self._layout.addWidget(empty)
        else:
            self._render_seat_section(report.seat_report)

        render_compact_specializations_section(
            self._layout,
            report,
            self._last_pending_items,
            payload=self._last_payload,
        )

        self._layout.addStretch(1)
        self._btn_copy.setEnabled(True)

        if reset_scroll:
            self._scroll.verticalScrollBar().setValue(0)

    def _copy_advice_summary(self) -> None:
        report = self._last_report
        if report is None:
            return
        lines: list[str] = [report.summary or "Coach"]
        if report.adventure_name:
            lines.append(f"Adventure: {report.adventure_name}")
        if report.adventure_buff_note:
            lines.append(report.adventure_buff_note)
        if report.seat_report and report.seat_report.seats:
            for seat in report.seat_report.seats[:8]:
                role = seat.effective_role or seat.inferred_role or "?"
                name = seat.hero_name or f"hero {seat.hero_id}"
                lines.append(f"Slot {seat.seat}: {name} · {role}")
        pending = self._last_pending_items or ()
        if pending:
            lines.append("Specializations (open):")
            for item in pending[:8]:
                choice = (
                    item.options[item.desired_option_index].name
                    if item.desired_option_index is not None and item.options
                    else "no fixed choice"
                )
                lines.append(f"- {item.hero_name}: {choice}")
        text = "\n".join(lines)
        from PySide6.QtGui import QGuiApplication

        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            base = self._status.text().split(" · ")[0] if self._status.text() else "Advice"
            self._status.setText(f"{base} · copied")

    def _render_roster_upgrade_section(self) -> None:
        if not self._roster_suggestions:
            return
        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda role: role

        advisor_section(self._layout, "Better champs (owned)")
        intro = advisor_card(highlight=False)
        intro_lyt = advisor_card_layout(intro)
        intro_lyt.addWidget(
            advisor_lbl(
                "Suggestions based on roles, seat legality, gear/ilvl, affiliation, and a "
                "relative BUD proxy (live carry damage × support/position). Not an exact combat sim — "
                "use this as a targeted shortlist.",
                kind="muted",
            )
        )
        self._layout.addWidget(intro)

        for item in self._roster_suggestions:
            card = advisor_card(highlight=True)
            lyt = advisor_card_layout(card)
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(
                advisor_portrait(item.candidate_hero_id),
                alignment=Qt.AlignmentFlag.AlignTop,
            )
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            text_col.addWidget(advisor_lbl(item.title, kind="subtitle"))
            meta_parts = [role_label(item.role)]
            if item.same_seat_swap and item.replace_seat is not None:
                meta_parts.append(f"seat {item.replace_seat}")
            elif item.candidate_seat is not None:
                meta_parts.append(f"seat {item.candidate_seat} new")
                if item.replace_seat is not None:
                    meta_parts.append(f"bench seat {item.replace_seat}")
            bud_ratio = getattr(item, "bud_ratio", None)
            if isinstance(bud_ratio, (int, float)) and bud_ratio > 0:
                try:
                    from ic_gamedata.bud_proxy import format_bud_ratio, meaningful_bud_ratio
                except ImportError:
                    format_bud_ratio = None
                    meaningful_bud_ratio = None
                if (
                    format_bud_ratio is not None
                    and meaningful_bud_ratio is not None
                    and meaningful_bud_ratio(float(bud_ratio))
                ):
                    meta_parts.append(f"BUD-proxy {format_bud_ratio(float(bud_ratio))}")
            text_col.addWidget(advisor_lbl(" · ".join(meta_parts), kind="muted"))
            row.addLayout(text_col, stretch=1)
            lyt.addLayout(row)
            lyt.addWidget(advisor_lbl(f"Why: {item.why}", kind="body"))
            self._layout.addWidget(card)

    def _render_seat_section(self, seat_report) -> None:
        try:
            from ic_gamedata.seat_advisor.models import STANDARD_SEAT_ROLES
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"
            STANDARD_SEAT_ROLES = []

        advisor_section(self._layout, "Seats — most relevant first")

        for seat in seat_report.seats:
            highlight = seat.priority < 20
            card = advisor_card(highlight=highlight, show_accent=False)
            lyt = advisor_card_layout(card)
            lyt.setSpacing(6)

            columns = QHBoxLayout()
            columns.setSpacing(14)
            columns.setAlignment(Qt.AlignmentFlag.AlignTop)

            # Left: portrait/name header + role/advice/links (feats align with name)
            left_col = QVBoxLayout()
            left_col.setSpacing(6)
            left_col.setAlignment(Qt.AlignmentFlag.AlignTop)

            header = QHBoxLayout()
            header.setSpacing(10)
            header.addWidget(advisor_portrait(seat.hero_id), alignment=Qt.AlignmentFlag.AlignTop)
            title_col = QVBoxLayout()
            title_col.setSpacing(2)
            name_row = QHBoxLayout()
            name_row.setContentsMargins(0, 0, 0, 0)
            name_row.setSpacing(8)
            name_row.addWidget(advisor_lbl(seat.hero_name, kind="title"))
            if seat.is_bud:
                name_row.addWidget(
                    advisor_tag_pill("BUD", kind="bud"),
                    alignment=Qt.AlignmentFlag.AlignVCenter,
                )
            elif seat.is_speed_focus:
                name_row.addWidget(
                    advisor_tag_pill("Speed", kind="speed"),
                    alignment=Qt.AlignmentFlag.AlignVCenter,
                )
            if highlight:
                name_row.addWidget(
                    advisor_status_dot(ui_theme.WARN),
                    alignment=Qt.AlignmentFlag.AlignVCenter,
                )
            name_row.addStretch(1)
            title_col.addLayout(name_row)
            title_col.addWidget(
                advisor_lbl(f"Slot {seat.seat} · {seat.zone.upper()}", kind="muted")
            )
            header.addLayout(title_col, stretch=1)
            left_col.addLayout(header)

            advice_col = QVBoxLayout()
            advice_col.setSpacing(4)
            advice_col.setAlignment(Qt.AlignmentFlag.AlignTop)

            role_row = QHBoxLayout()
            role_row.setSpacing(8)
            role_row.addWidget(advisor_lbl("Role", kind="muted"))
            role_combo, hint = advisor_role_combo(
                seat,
                STANDARD_SEAT_ROLES,
                role_label,
                self._on_role_selected,
            )
            role_row.addWidget(role_combo)
            role_row.addWidget(advisor_lbl(hint, kind="muted"), stretch=1)
            advice_col.addLayout(role_row)

            if seat.relevance_reason and seat.relevance_reason != "OK":
                advice_col.addWidget(advisor_lbl(seat.relevance_reason, kind="warn"))

            for line in seat.insights:
                advice_col.addWidget(
                    advisor_lbl(f"· {line.headline}: {line.detail}", kind="insight")
                )

            if seat.bench_alternatives:
                alts = ", ".join(
                    f"{a.hero_name} ({a.reason})" for a in seat.bench_alternatives[:3]
                )
                advice_col.addWidget(advisor_lbl(f"Bench: {alts}", kind="body"))

            source_url = getattr(seat, "advice_source_url", "") or ""
            wiki_url = getattr(seat, "advice_wiki_url", "") or ""
            if source_url or wiki_url:
                # Spacing(4) + 4px top ≈ 8px — clearly separate, not a big gap.
                link_row = QHBoxLayout()
                link_row.setContentsMargins(0, 4, 0, 0)
                link_row.setSpacing(12)
                if source_url:
                    link_row.addWidget(advisor_link_btn("Reddit", source_url))
                if wiki_url:
                    link_row.addWidget(advisor_link_btn("Wiki", wiki_url))
                link_row.addStretch(1)
                advice_col.addLayout(link_row)

            left_col.addLayout(advice_col)

            # Right: feats — top-aligned with champion name
            feats_col = QVBoxLayout()
            feats_col.setSpacing(4)
            feats_col.setAlignment(Qt.AlignmentFlag.AlignTop)
            feats = seat.recommended_feats
            role_str = seat.effective_role or ""
            count_hint = f"{len(feats)} recommended" if feats else "no data"
            feats_col.addWidget(
                advisor_lbl(f"Feats · {role_str} · {count_hint}", kind="muted")
            )
            if feats:
                for feat in feats[:8]:
                    color = {
                        "active": ui_theme.SUCCESS,
                        "owned": ui_theme.FEAT_OWNED,
                        "missing": ui_theme.FEAT_MISSING,
                    }.get(feat.status, ui_theme.TEXT_MUTED)
                    feat_row = QHBoxLayout()
                    feat_row.setContentsMargins(0, 0, 0, 0)
                    feat_row.setSpacing(8)
                    feat_row.addWidget(
                        advisor_status_dot(color),
                        alignment=Qt.AlignmentFlag.AlignVCenter,
                    )
                    feat_row.addWidget(advisor_lbl(feat.name, kind="body"), stretch=1)
                    feats_col.addLayout(feat_row)
            else:
                feats_col.addWidget(
                    advisor_lbl("No feat advice for this champion/role.", kind="muted")
                )

            columns.addLayout(left_col, stretch=3)
            columns.addLayout(feats_col, stretch=2)
            lyt.addLayout(columns)

            self._layout.addWidget(card)
