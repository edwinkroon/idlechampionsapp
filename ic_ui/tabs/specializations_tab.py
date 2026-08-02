"""Specializations tab: pending choices and recommended specs."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ic_gamedata.advice_fingerprint import party_id_from_payload
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar
from ic_ui.widgets.advisor_widgets import advisor_card, advisor_card_layout, advisor_lbl
from ic_ui.workers.specializations import SpecializationsRunnable

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
        self._analysing = False
        self._pending_analysis: tuple[dict, str | None, bool] | None = None
        self._pending_auto_refresh = False
        self._has_results = False
        self._worker_signals = None
        self._build_ui()

    @property
    def has_results(self) -> bool:
        return self._has_results

    @property
    def analysing(self) -> bool:
        return self._analysing

    @property
    def last_party_id(self) -> int | None:
        return self._last_party_id

    def on_snapshot(self, envelope: SnapshotEnvelope) -> None:
        force = "specializations" in envelope.force_consumers or "advisor" in envelope.force_consumers
        fp = envelope.advice_fp
        first = not self._has_results and envelope.payload is not None
        changed = (
            envelope.payload is not None
            and fp is not None
            and fp != self._last_advice_fp
        )
        if envelope.degraded and not (force or first or changed):
            if envelope.err and self._has_results:
                base = self._status.text().split(" · ")[0] if self._status.text() else "Specialisaties"
                self._status.setText(f"{base} · {envelope.err}")
            return
        if not (force or first or changed):
            return
        if envelope.payload is None:
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

    def request_refresh(self, *, auto_refresh: bool = False) -> None:
        if self._data is None:
            self._status.setText("Geen data-service — herstart de app.")
            return
        if not self._data.refresh_credentials() and self._data.credentials is None:
            if not auto_refresh:
                self._status.setText("Geen API-credentials. Ga naar Dashboard → Opnieuw zoeken.")
            return
        if not auto_refresh:
            self._btn_refresh.setEnabled(False)
            self._status.setText("Specialisaties analyseren…")
        self._data.request_poll(
            reason="specializations",
            force_consumers={"specializations", "advisor"},
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
            self._pending_analysis = (payload, err, auto_refresh)
            if advice_fp is not None:
                self._last_advice_fp = advice_fp
            return
        if advice_fp is not None:
            self._last_advice_fp = advice_fp
        goal = self._controls.goal()
        context = self._controls.context()
        self._pending_auto_refresh = auto_refresh
        self._analysing = True
        worker = SpecializationsRunnable(
            goal, context, payload, err, signals_parent=self
        )
        self._worker_signals = worker.signals
        worker.signals.done.connect(self._on_done)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        ctrl_row = QHBoxLayout()
        self._controls = AdvisorGoalContextBar()
        self._controls.changed.connect(self._on_options_changed)
        self._btn_refresh = QPushButton("Verversen")
        self._btn_refresh.clicked.connect(lambda: self.request_refresh(auto_refresh=False))
        ctrl_row.addWidget(self._controls, stretch=1)
        ctrl_row.addWidget(self._btn_refresh)
        root.addLayout(ctrl_row)

        self._status = QLabel("Data wordt elke 5 seconden automatisch ververst.")
        self._status.setWordWrap(True)
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
        self._layout.setContentsMargins(12, 8, 12, 16)
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
        payload, err, auto_refresh = pending
        self._pending_analysis = None
        self.start_analysis(payload, err, auto_refresh=auto_refresh)

    def _on_done(self, result) -> None:
        self._worker_signals = None
        payload, report, pending_items, err = result
        auto_refresh = self._pending_auto_refresh

        self._last_payload = payload
        self._last_party_id = party_id_from_payload(payload)
        self._last_goal = report.goal
        self._last_context = report.context
        self._analysing = False
        self._btn_refresh.setEnabled(True)
        status = f"Specialisatie-advies — {report.adventure_name}"
        if err:
            status = f"{status} ({err})"
        if auto_refresh:
            status = f"{status} · ververst {time.strftime('%H:%M:%S')}"
        self._status.setText(status)
        reset_scroll = not auto_refresh or not self._has_results
        self._render_report(report, pending_items, reset_scroll=reset_scroll)
        self._schedule_pending_analysis()

    def _on_error(self, msg: str) -> None:
        self._worker_signals = None
        auto_refresh = self._pending_auto_refresh
        self._analysing = False
        self._btn_refresh.setEnabled(True)
        if auto_refresh and self._has_results:
            self._status.setText(f"Verversen mislukt: {msg} (laatste resultaat behouden)")
        else:
            self._status.setText(f"Fout: {msg}")
        self._schedule_pending_analysis()

    def _clear(self) -> None:
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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
        lbl = advisor_lbl(text, kind="title")
        lbl.setContentsMargins(0, 8, 0, 4)
        self._layout.addWidget(lbl)

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
            lyt.addWidget(advisor_lbl(f"{insight.headline} ({seat_str})", kind="subtitle"))
            detail = insight.detail
            if insight.rule_source_type == "heuristic":
                detail = f"{detail} (generieke placeholder-regel)"
            lyt.addWidget(advisor_lbl(detail, kind=self._label_kind(insight.status)))
            meta_str = f"{insight.status} · {insight.rule_source_type}"
            if insight.confidence:
                meta_str += f" · confidence {insight.confidence}/5"
            lyt.addWidget(advisor_lbl(meta_str, kind="muted"))
            self._layout.addWidget(card)

    def _render_pending(self, pending_items) -> None:
        if not pending_items:
            card = advisor_card()
            lyt = advisor_card_layout(card)
            lyt.addWidget(
                advisor_lbl(
                    "Geen open specialization-keuzes voor de actieve party.",
                    kind="body",
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
            seat_str = f"slot {item.seat}" if item.seat is not None else "onbekende seat"
            lyt.addWidget(advisor_lbl(f"{item.hero_name} ({seat_str})", kind="subtitle"))
            options = " / ".join(option.name for option in item.options)
            if item.desired_option_index is not None:
                chosen = item.options[item.desired_option_index].name
                lyt.addWidget(advisor_lbl(f"Advies: {chosen}", kind="spec_pending"))
            else:
                lyt.addWidget(advisor_lbl("Advies: nog geen vaste keuze", kind="spec_pending"))
            if human_specialization_reason is not None:
                lyt.addWidget(
                    advisor_lbl(
                        f"Waarom: {human_specialization_reason(item, context)}",
                        kind="body",
                    )
                )
            elif item.rationale:
                lyt.addWidget(advisor_lbl(f"Waarom: {item.rationale}", kind="body"))
            lyt.addWidget(advisor_lbl(f"Open opties: {options}", kind="muted"))
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

        head = advisor_card()
        head_lyt = advisor_card_layout(head)
        head_lyt.addWidget(advisor_lbl("Specialization-advies", kind="subtitle"))
        head_lyt.addWidget(
            advisor_lbl(
                f"{goal_text}  ·  {context_labels.get(report.context, report.context)}  ·  {report.adventure_name}",
                kind="muted",
            )
        )
        self._layout.addWidget(head)

        # 1) In-game dialogs still open
        self._section("Open keuzes")
        self._render_pending(pending_items)

        insights = tuple(report.specialization_insights or ())
        actionable = {"mismatch", "open_tier"}
        extras = {"bench_suggestion", "formation_synergy"}

        # 2) One detailed card per hero that needs a change (no summary/per-champion echo)
        actionable_insights = [ins for ins in insights if ins.status in actionable]
        if actionable_insights:
            self._section("Actie nodig")
            self._insight_cards(insights, statuses=actionable)

        # 3) Compact green list for specs that already match — no per-hero cards
        if report.seat_report and report.seat_report.seats:
            ok_lines = self._summary_lines(report.seat_report.seats, statuses={"match"})
            if ok_lines:
                self._section("In orde")
                card = advisor_card()
                lyt = advisor_card_layout(card)
                for line, kind in ok_lines:
                    lyt.addWidget(advisor_lbl(f"· {line}", kind=kind))
                self._layout.addWidget(card)

        # 4) Bench / formation suggestions (not the same as in-formation mismatches)
        extra_insights = [ins for ins in insights if ins.status in extras]
        if extra_insights:
            self._section("Bench & formatie")
            self._insight_cards(insights, statuses=extras)

        if report.tips:
            self._section("Composition-tips")
            for tip in report.tips:
                card = advisor_card()
                lyt = advisor_card_layout(card)
                lyt.addWidget(advisor_lbl(f"Tip {tip.priority} · {tip.title}", kind="subtitle"))
                lyt.addWidget(advisor_lbl(tip.detail, kind="body"))
                self._layout.addWidget(card)

        self._layout.addStretch(1)
        if reset_scroll:
            self._scroll.verticalScrollBar().setValue(0)
