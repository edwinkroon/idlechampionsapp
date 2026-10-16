"""Specializations tab: pending choices and recommended specs."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
from ic_ui.theme import apply_button_icon, on_theme_changed
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar
from ic_ui.widgets.advisor_widgets import (
    advisor_card,
    advisor_card_layout,
    advisor_lbl,
    advisor_status_dot,
    clear_advisor_layout,
    refresh_advisor_chrome,
)
from ic_ui.workers.shared_advice import SharedAdviceResult, shared_advice_hub

if TYPE_CHECKING:
    from ic_core.game_data_service import GameDataService, SnapshotEnvelope


class SpecializationsTab(QWidget):
    """Specialization advice for the active party."""

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
        self._pending_analysis: tuple[dict, str | None, bool, tuple[Any, ...] | None] | None = None
        self._pending_auto_refresh = False
        self._has_results = False
        self._last_report = None
        self._last_pending_items = None
        self._build_ui()
        on_theme_changed(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_BODY};")
        if self._last_report is not None:
            self._render_report(
                self._last_report,
                self._last_pending_items or (),
                reset_scroll=False,
            )
        else:
            refresh_advisor_chrome(self)

    @property
    def has_results(self) -> bool:
        return self._has_results

    @property
    def analysing(self) -> bool:
        return self._analysing

    @property
    def last_party_id(self) -> int | None:
        return self._last_party_id

    @property
    def last_formation_empty(self) -> bool:
        return self._last_formation_empty

    def on_snapshot(self, envelope: SnapshotEnvelope) -> None:
        force = "specializations" in envelope.force_consumers
        fp = envelope.advice_fp
        first = not self._has_results and envelope.payload is not None
        changed = (
            envelope.payload is not None
            and fp is not None
            and fp != self._last_advice_fp
        )
        # After party activate, formation layout can fingerprint before hero rows
        # resolve — keep retrying until analyze_party finds champions.
        empty_retry = (
            envelope.payload is not None
            and self._last_formation_empty
            and self._has_results
            and not self._analysing
        )
        if not should_refresh_advice(
            force=force,
            first=first,
            changed=changed,
            empty_retry=empty_retry,
            degraded=envelope.degraded,
        ):
            if envelope.degraded and envelope.err and self._has_results:
                base = self._status.text().split(" · ")[0] if self._status.text() else "Specializations"
                self._status.setText(f"{base} · {envelope.err}")
            return
        if envelope.payload is None:
            if force and not envelope.auto_refresh:
                self._status.setText(envelope.err or "No API data received.")
            return
        err = envelope.err
        if envelope.quality and envelope.quality.warnings:
            warn = envelope.quality.warnings[0]
            err = f"{err} · {warn}" if err else warn
        self.start_analysis(
            envelope.payload,
            err,
            auto_refresh=envelope.auto_refresh or not force,
            advice_fp=fp,
        )

    def notify_waiting_for_data(self) -> None:
        self._status.setText("Waiting for API data…")

    def request_refresh(self, *, auto_refresh: bool = False) -> None:
        """Re-analyze from cache and force a poll (used by goal changes)."""
        if self._data is None:
            self._status.setText("No data service — restart the app.")
            return
        if not auto_refresh:
            self._status.setText("Analyzing specializations…")
        if not self._data.refresh_credentials() and self._data.credentials is None:
            if not auto_refresh:
                self._status.setText("No API credentials. Go to Dashboard → Search again.")
            return
        # Re-analyze cached snapshot immediately — fingerprint gating may have
        # skipped a later complete poll; waiting only on a new HTTP round-trip
        # left Refresh looking broken until a party switch changed the fp.
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
            reason="specializations",
            force_consumers={"specializations"},
            auto_refresh=auto_refresh,
        )

    def start_analysis(
        self,
        payload: dict,
        err: str | None,
        *,
        auto_refresh: bool,
        advice_fp: tuple[Any, ...] | None = None,
    ) -> None:
        if self._analysing:
            self._pending_analysis = (payload, err, auto_refresh, advice_fp)
            return
        goal = self._controls.goal()
        context = self._controls.context()
        self._pending_auto_refresh = auto_refresh
        self._running_advice_fp = advice_fp
        self._analysing = True
        if not auto_refresh:
            self._status.setText("Analyzing specializations…")
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
        self._controls = AdvisorGoalContextBar()
        self._controls.changed.connect(self._on_options_changed)
        self._btn_copy = QPushButton("Copy")
        apply_button_icon(self._btn_copy, "copy")
        self._btn_copy.setToolTip("Copy specialization summary to the clipboard")
        self._btn_copy.setEnabled(False)
        self._btn_copy.clicked.connect(self._copy_summary)
        ctrl_row.addWidget(self._controls, stretch=1)
        ctrl_row.addWidget(self._btn_copy)
        root.addLayout(ctrl_row)

        self._status = QLabel(
            "Data refreshes on game activity (webRequestLog) or within 30 seconds. "
            "Use Refresh (top right / F5) for a full update."
        )
        self._status.setWordWrap(True)
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
        self.request_refresh(auto_refresh=False)

    def _schedule_pending_analysis(self) -> None:
        pending = self._pending_analysis
        if pending is None or self._analysing:
            return
        payload, err, auto_refresh, advice_fp = pending
        self._pending_analysis = None
        self.start_analysis(payload, err, auto_refresh=auto_refresh, advice_fp=advice_fp)

    def _commit_advice_fp(self, *, formation_empty: bool) -> None:
        """Only lock the fingerprint once formation heroes resolved.

        Committing early on an empty formation made later identical fingerprints
        skip — specs then only reappeared after a party switch changed the fp.
        """
        self._last_advice_fp = commit_advice_fingerprint(
            self._running_advice_fp,
            formation_empty=formation_empty,
        )

    def _on_shared_done(self, result: SharedAdviceResult) -> None:
        self._on_done((result.payload, result.report, result.pending, result.err))

    def _on_done(self, result) -> None:
        payload, report, pending_items, err = result
        auto_refresh = self._pending_auto_refresh

        self._last_payload = payload
        self._last_party_id = party_id_from_payload(payload)
        # Champ lists (All good / No advice) need seat_report.seats — keep
        # retrying when tips/summary already work from formation_heroes alone.
        self._last_formation_empty = not bool(
            report.seat_report and report.seat_report.seats
        )
        self._commit_advice_fp(formation_empty=self._last_formation_empty)
        self._running_advice_fp = None
        self._last_goal = report.goal
        self._last_context = report.context
        self._analysing = False
        status = f"Specialization advice — {report.adventure_name}"
        if err:
            status = f"{status} ({err})"
        status = f"{status} · refreshed {time.strftime('%H:%M:%S')}"
        self._status.setText(status)
        reset_scroll = not auto_refresh or not self._has_results
        self._last_report = report
        self._last_pending_items = pending_items
        self._render_report(report, pending_items, reset_scroll=reset_scroll)
        self._schedule_pending_analysis()

    def _on_error(self, msg: str) -> None:
        auto_refresh = self._pending_auto_refresh
        # Do not lock the fingerprint on failure — allow the next poll to retry.
        self._running_advice_fp = None
        self._analysing = False
        if auto_refresh and self._has_results:
            self._status.setText(f"Refresh failed: {msg} (keeping last result)")
        else:
            self._status.setText(f"Error: {msg}")
        self._schedule_pending_analysis()

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

    def _section(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setProperty("advisorSection", True)
        lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; letter-spacing: 0.04em; "
            f"color: {ui_theme.TEXT_MUTED}; padding: 12px 4px 2px 4px; "
            f"border: none; background: transparent;"
        )
        self._layout.addWidget(lbl)

    @staticmethod
    def _dot_color(kind: str) -> str:
        return {
            "warn": ui_theme.WARN,
            "spec_match": ui_theme.SUCCESS,
            "spec_pending": ui_theme.TEXT_BODY,
            "spec_mismatch": ui_theme.FEAT_MISSING,
            "muted": ui_theme.TEXT_MUTED,
        }.get(kind, ui_theme.TEXT_MUTED)

    def _add_dot_line(self, layout: QVBoxLayout, text: str, *, kind: str) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(
            advisor_status_dot(self._dot_color(kind)),
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        row.addWidget(advisor_lbl(text, kind=kind), stretch=1)
        layout.addLayout(row)

    def _render_review_needed(self, hero_ids: set[int]) -> None:
        """Show review warnings only when formation heroes still have review_needed."""
        if not hero_ids:
            return
        try:
            from ic_gamedata.specialization_advisor_model import review_needed_models_for_heroes
        except ImportError:
            return
        review_models = review_needed_models_for_heroes(hero_ids)
        if not review_models:
            return
        self._section("Review needed")
        card = advisor_card()
        lyt = advisor_card_layout(card)
        lyt.addWidget(
            advisor_lbl(
                "Conflicting or incomplete specialization data for this party.",
                kind="body",
            )
        )
        for model in review_models:
            reason = model.review_reasons[0] if model.review_reasons else "internal uncertainty"
            self._add_dot_line(lyt, f"{model.name}: {reason}", kind="warn")
        self._layout.addWidget(card)

    @staticmethod
    def _label_kind(status: str | None) -> str:
        return {
            "match": "spec_match",
            "matches": "spec_match",
            "pending": "spec_pending",
            "open_tier": "spec_pending",
            "mismatch": "spec_mismatch",
        }.get(status or "", "spec_pending")

    def _summary_lines(
        self,
        seats,
        *,
        statuses: set[str] | None = None,
    ) -> list[tuple[str, str]]:
        try:
            from ic_gamedata.party_advisor_specializations import spec_summary_line
        except ImportError:
            spec_summary_line = None

        lines: list[tuple[str, str]] = []
        for seat in sorted(seats, key=lambda item: item.seat):
            if not seat.best_spec:
                continue
            status = getattr(seat, "spec_status", None) or "pending"
            if statuses is not None and status not in statuses:
                continue
            if spec_summary_line is not None:
                text = spec_summary_line(
                    seat.hero_name,
                    recommended=seat.best_spec,
                    current_labels=seat.current_specs,
                    status=status,
                    is_bud=seat.is_bud,
                )
            else:
                name = seat.hero_name
                if seat.is_bud:
                    name += " (BUD)"
                current = ", ".join(seat.current_specs) if seat.current_specs else None
                if status == "mismatch" and current:
                    text = f"{name}: {current} → {seat.best_spec}"
                else:
                    text = f"{name}: {seat.best_spec}"
            lines.append((text, self._label_kind(status)))
        return lines

    def _insight_cards(self, insights, *, statuses: set[str]) -> None:
        seen_heroes: set[int] = set()
        for insight in insights:
            if insight.status not in statuses:
                continue
            if insight.hero_id in seen_heroes:
                continue
            seen_heroes.add(insight.hero_id)
            highlight = insight.status in {"open_tier", "mismatch"}
            card = advisor_card(highlight=highlight)
            lyt = advisor_card_layout(card)
            seat_str = f"slot {insight.seat}" if insight.seat is not None else "bench"
            lyt.addWidget(advisor_lbl(f"{insight.headline} · {seat_str}", kind="subtitle"))
            detail = insight.detail
            if insight.rule_source_type == "heuristic":
                detail = f"{detail} (generic placeholder rule)"
            lyt.addWidget(advisor_lbl(detail, kind=self._label_kind(insight.status)))
            meta_str = f"{insight.status} · {insight.rule_source_type}"
            if insight.confidence:
                meta_str += f" · confidence {insight.confidence}/5"
            lyt.addWidget(advisor_lbl(meta_str, kind="muted"))
            self._layout.addWidget(card)

    def _render_pending(self, pending_items) -> None:
        if not pending_items:
            card = advisor_card(compact=True)
            lyt = advisor_card_layout(card, compact=True)
            lyt.addWidget(
                advisor_lbl(
                    "No open specialization choices for the active party.",
                    kind="muted",
                )
            )
            self._layout.addWidget(card)
            return

        try:
            from ic_gamedata.specialization_advice_text import (
                human_specialization_reason,
            )
            from ic_gamedata.specializations import _active_adventure_context
        except ImportError:
            human_specialization_reason = None
            _active_adventure_context = None

        context = _active_adventure_context(self._last_payload or {}) if _active_adventure_context else {}
        for item in pending_items:
            highlight = item.desired_option_index is not None
            card = advisor_card(highlight=highlight)
            lyt = advisor_card_layout(card)
            seat_str = f"slot {item.seat}" if item.seat is not None else "unknown seat"
            lyt.addWidget(advisor_lbl(f"{item.hero_name} · {seat_str}", kind="subtitle"))
            options = " / ".join(option.name for option in item.options)
            if item.desired_option_index is not None:
                chosen = item.options[item.desired_option_index].name
                lyt.addWidget(advisor_lbl(f"Advice: {chosen}", kind="spec_pending"))
            elif item.reason == "insufficient data":
                lyt.addWidget(
                    advisor_lbl("Advice: unknown — not enough data", kind="spec_pending")
                )
            else:
                lyt.addWidget(advisor_lbl("Advice: no fixed choice yet", kind="spec_pending"))
            try:
                from ic_gamedata.specialization_advisor_model import (
                    advisor_model_for_hero,
                    advisor_model_line_kind,
                    format_advisor_model_lines,
                )

                model = advisor_model_for_hero(item.hero_id)
            except ImportError:
                model = None
            if model is not None:
                for line in format_advisor_model_lines(model):
                    lyt.addWidget(advisor_lbl(line, kind=advisor_model_line_kind(model, line)))
            if human_specialization_reason is not None:
                lyt.addWidget(
                    advisor_lbl(
                        f"Why: {human_specialization_reason(item, context)}",
                        kind="body",
                    )
                )
            elif item.rationale:
                lyt.addWidget(advisor_lbl(f"Why: {item.rationale}", kind="body"))
            lyt.addWidget(advisor_lbl(f"Open options: {options}", kind="muted"))
            meta_parts: list[str] = []
            if item.data_source_version:
                meta_parts.append(f"dataset {item.data_source_version}")
            if item.rule_source_type:
                meta_parts.append(item.rule_source_type)
            if item.confidence:
                meta_parts.append(f"confidence {item.confidence}/5")
            if meta_parts:
                lyt.addWidget(advisor_lbl(" · ".join(meta_parts), kind="muted"))
            self._layout.addWidget(card)

    def _render_report(self, report, pending_items, *, reset_scroll: bool = True) -> None:
        self._show_results_panel()
        self._clear()

        context_labels = {"campaign": "Campaign", "events": "Events", "push": "Push", "modron": "Modron"}
        try:
            from ic_gamedata.party_advisor import goal_label as advisor_goal_label
        except ImportError:
            advisor_goal_label = lambda g: g
        goal_text = advisor_goal_label(report.goal)

        head = advisor_card(compact=True)
        head_lyt = advisor_card_layout(head, compact=True)
        head_lyt.addWidget(
            advisor_lbl(
                f"{goal_text}  ·  {context_labels.get(report.context, report.context)}  ·  {report.adventure_name}",
                kind="muted",
            )
        )
        self._layout.addWidget(head)

        review_ids = {item.hero_id for item in (pending_items or ())}
        if report.seat_report and report.seat_report.seats:
            review_ids.update(seat.hero_id for seat in report.seat_report.seats if seat.hero_id)
        for insight in report.specialization_insights or ():
            if insight.status != "bench_suggestion":
                review_ids.add(insight.hero_id)
        self._render_review_needed(review_ids)

        # Only champions currently in the formation (not bench / seat assignees).
        formation_ids = {
            seat.hero_id
            for seat in (report.seat_report.seats if report.seat_report else ())
            if seat.hero_id
        }
        if not formation_ids:
            formation_ids = {
                ins.hero_id
                for ins in (report.specialization_insights or ())
                if ins.status != "bench_suggestion" and ins.seat is not None
            }

        formation_pending = [
            item
            for item in (pending_items or ())
            if not formation_ids or item.hero_id in formation_ids
        ]

        # 1) In-game dialogs still open
        self._section("Open choices")
        self._render_pending(formation_pending)

        insights = tuple(
            ins
            for ins in (report.specialization_insights or ())
            if ins.status != "bench_suggestion"
            and (not formation_ids or ins.hero_id in formation_ids)
        )
        actionable = {"mismatch", "open_tier"}
        extras = {"formation_synergy"}

        # Prefer seat_report as the complete formation roster — insights omit
        # matching heroes on purpose and are capped, which hid most champs.
        formation_seats = []
        if report.seat_report and report.seat_report.seats:
            formation_seats = [
                seat
                for seat in report.seat_report.seats
                if not formation_ids or seat.hero_id in formation_ids
            ]
        insight_action_ids = {
            ins.hero_id for ins in insights if ins.status in actionable
        }

        # 2) Detailed cards for open_tier/mismatch insights
        actionable_insights = [ins for ins in insights if ins.status in actionable]
        if actionable_insights:
            self._section("Action needed")
            self._insight_cards(insights, statuses=actionable)

        # Seat-level mismatches/pending not covered by an insight card
        seat_action_seats = [
            s for s in formation_seats if s.hero_id not in insight_action_ids
        ]
        mismatch_lines = self._summary_lines(seat_action_seats, statuses={"mismatch"})
        pending_lines = self._summary_lines(seat_action_seats, statuses={"pending"})
        if mismatch_lines or pending_lines:
            if not actionable_insights:
                self._section("Action needed")
            card = advisor_card(compact=True)
            lyt = advisor_card_layout(card, compact=True)
            for line, kind in mismatch_lines + pending_lines:
                self._add_dot_line(lyt, line, kind=kind)
            self._layout.addWidget(card)

        # 3) Compact list for specs that already match
        ok_lines = self._summary_lines(formation_seats, statuses={"match"})
        if ok_lines:
            self._section("All good")
            card = advisor_card(compact=True)
            lyt = advisor_card_layout(card, compact=True)
            for line, kind in ok_lines:
                self._add_dot_line(lyt, line, kind=kind)
            self._layout.addWidget(card)

        # 4) Formation champs with no recommendation / no status yet
        no_advice_lines: list[tuple[str, str]] = []
        for seat in sorted(formation_seats, key=lambda item: item.seat):
            if seat.best_spec and seat.spec_status in {"match", "mismatch", "pending"}:
                continue
            name = seat.hero_name or f"hero {seat.hero_id}"
            if seat.is_bud:
                name += " (BUD)"
            if seat.current_specs:
                text = f"{name}: {' / '.join(seat.current_specs)} (no advice)"
            else:
                text = f"{name}: no specialization data"
            no_advice_lines.append((text, "muted"))
        if no_advice_lines:
            self._section("No advice")
            card = advisor_card(compact=True)
            lyt = advisor_card_layout(card, compact=True)
            for line, kind in no_advice_lines:
                self._add_dot_line(lyt, line, kind=kind)
            self._layout.addWidget(card)

        # 5) Formation synergy for in-party champions only (no bench cards)
        extra_insights = [ins for ins in insights if ins.status in extras]
        if extra_insights:
            self._section("Formation")
            self._insight_cards(insights, statuses=extras)

        if report.tips:
            self._section("Composition tips")
            for tip in report.tips:
                card = advisor_card()
                lyt = advisor_card_layout(card)
                lyt.addWidget(advisor_lbl(f"Tip {tip.priority} · {tip.title}", kind="subtitle"))
                lyt.addWidget(advisor_lbl(tip.detail, kind="body"))
                self._layout.addWidget(card)

        self._layout.addStretch(1)
        self._btn_copy.setEnabled(True)
        if reset_scroll:
            self._scroll.verticalScrollBar().setValue(0)

    def _copy_summary(self) -> None:
        report = self._last_report
        if report is None:
            return
        lines: list[str] = [
            f"Specializations — {report.adventure_name}",
            f"Goal: {report.goal} · Context: {report.context}",
        ]
        pending = self._last_pending_items or ()
        if pending:
            lines.append("Open choices:")
            for item in pending[:10]:
                choice = (
                    item.options[item.desired_option_index].name
                    if item.desired_option_index is not None and item.options
                    else "no fixed choice"
                )
                lines.append(f"- {item.hero_name}: {choice}")
        insights = tuple(
            ins
            for ins in (report.specialization_insights or ())
            if ins.status in {"mismatch", "open_tier", "match"}
        )
        if insights:
            lines.append("Status:")
            for ins in insights[:12]:
                lines.append(f"- {ins.hero_name}: {ins.status} · {ins.detail or ins.headline or ''}")
        if report.tips:
            lines.append("Tips:")
            for tip in report.tips[:5]:
                lines.append(f"- {tip.title}: {tip.detail}")
        from PySide6.QtGui import QGuiApplication

        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n".join(lines))
            base = self._status.text().split(" · ")[0] if self._status.text() else "Specializations"
            self._status.setText(f"{base} · copied")
