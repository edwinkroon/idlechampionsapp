"""Party Advisor tab: seat roles, formation tips, and feat recommendations."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.widgets.advisor_widgets import (
    ACCENT,
    BG_INPUT,
    BORDER,
    BUD_BAR,
    FORMATION_ZONE_BG,
    FormationSeatCard,
    advisor_badge,
    advisor_card,
    advisor_card_layout,
    advisor_divider,
    advisor_link_btn,
    advisor_lbl,
    advisor_portrait,
    advisor_role_combo,
    advisor_section,
)
from ic_ui.workers.advisor import AdvisorRunnable


def party_id_from_payload(payload: dict | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    raw = details.get("active_game_instance_id")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


class AdvisorTab(QWidget):
    """Analyze party composition, seats, and formation."""

    api_poll_requested = Signal(bool)

    def __init__(self, dashboard_tab: DashboardTab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dashboard_tab = dashboard_tab
        self._last_payload = None
        self._last_goal = "bud"
        self._last_context = "campaign"
        self._last_party_id: int | None = None
        self._feat_open: dict[int, bool] = {}
        self._analysing = False
        self._pending_auto_refresh = False
        self._pending_analysis: tuple[dict, str | None, bool, bool] | None = None
        self._current_party_changed = False
        self._has_results = False
        self._seat_card_frames: dict[int, QFrame] = {}
        self._build_ui()

    @property
    def last_party_id(self) -> int | None:
        return self._last_party_id

    @property
    def has_results(self) -> bool:
        return self._has_results

    @property
    def analysing(self) -> bool:
        return self._analysing

    def refresh_credentials(self) -> bool:
        return self._dashboard_tab.refresh_credentials_from_log()

    def request_analyze(self, *, auto_refresh: bool = False) -> None:
        if self._analysing:
            return
        if not self.refresh_credentials():
            if not auto_refresh:
                self._status.setText("Geen API-credentials. Ga naar Dashboard → Opnieuw zoeken.")
            return
        if not auto_refresh:
            self._btn_analyze.setEnabled(False)
            self._status.setText("Analyseren…")
        self.api_poll_requested.emit(auto_refresh)

    def notify_fetch_inflight(self, *, manual_request: bool) -> None:
        if manual_request:
            self._status.setText("Data wordt al opgehaald…")

    def notify_fetch_credentials_error(self) -> None:
        self._on_error("Geen API-credentials.")

    def notify_fetch_error(self, err: str, *, auto_refresh: bool, advisor_after: bool) -> None:
        self._dashboard_tab.api_detail = err
        if advisor_after:
            if not auto_refresh:
                self._btn_analyze.setEnabled(True)
                self._on_error(err)
            elif not self._has_results:
                self._status.setText(f"Wachten op API-data… ({err})")

    def notify_fetch_no_payload(self, err: str | None, *, auto_refresh: bool) -> None:
        if not auto_refresh:
            self._btn_analyze.setEnabled(True)
            self._on_error(err or "Geen API-data ontvangen.")
        elif auto_refresh and not self._has_results:
            self._status.setText(err or "Wachten op API-data…")

    def start_analysis(
        self,
        payload: dict,
        err: str | None,
        *,
        auto_refresh: bool,
        party_changed: bool = False,
    ) -> None:
        if self._analysing:
            self._pending_analysis = (payload, err, auto_refresh, party_changed)
            return
        goal = self._goal.currentData() or "bud"
        context = self._context.currentData() or "campaign"
        include_formation = self._cb_formation.isChecked()
        self._pending_auto_refresh = auto_refresh
        self._current_party_changed = party_changed
        self._analysing = True
        worker = AdvisorRunnable(goal, context, include_formation, payload, err)
        worker.signals.done.connect(self._on_done)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        ctrl_row = QHBoxLayout()
        self._goal = QComboBox()
        self._goal.addItem("BUD / damage", "bud")
        self._goal.addItem("Gold income", "gold")
        self._goal.addItem("Speed / areas", "speed")

        self._context = QComboBox()
        self._context.addItem("Campaign", "campaign")
        self._context.addItem("Events", "events")
        self._context.addItem("Push", "push")
        self._context.addItem("Modron", "modron")

        self._cb_formation = QCheckBox("Formatie")
        self._cb_formation.setChecked(True)

        self._btn_analyze = QPushButton("Analyseren")
        self._btn_analyze.clicked.connect(lambda: self.request_analyze(auto_refresh=False))

        self._cb_formation.toggled.connect(self._on_options_changed)
        self._goal.currentIndexChanged.connect(self._on_options_changed)
        self._context.currentIndexChanged.connect(self._on_options_changed)

        ctrl_row.addWidget(QLabel("Doel:"))
        ctrl_row.addWidget(self._goal)
        ctrl_row.addWidget(QLabel("Context:"))
        ctrl_row.addWidget(self._context)
        ctrl_row.addWidget(self._cb_formation)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self._btn_analyze)
        root.addLayout(ctrl_row)

        self._status = QLabel("Start automatisch zodra speldata beschikbaar is.")
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
        self._last_goal = self._goal.currentData() or "bud"
        self._last_context = self._context.currentData() or "campaign"
        self._rerun_with_role_prefs()

    def _schedule_pending_analysis(self) -> None:
        pending = self._pending_analysis
        if pending is None or self._analysing:
            return
        payload, err, auto_refresh, party_changed = pending
        self._pending_analysis = None
        self.start_analysis(payload, err, auto_refresh=auto_refresh, party_changed=party_changed)

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
        self._last_goal = report.goal
        self._last_context = report.context
        self._analysing = False
        self._btn_analyze.setEnabled(True)
        status = report.summary
        if err:
            status = f"{status} ({err})"
        if party_changed:
            party_txt = f"party {party_id}" if party_id is not None else "nieuwe party"
            status = f"{status} · {party_txt}"
        if auto_refresh:
            status = f"{status} · ververst {time.strftime('%H:%M:%S')}"
        self._status.setText(status)
        reset_scroll = not auto_refresh or not self._has_results or party_changed
        self._render_report(report, reset_scroll=reset_scroll)
        self._schedule_pending_analysis()

    def _on_error(self, msg: str) -> None:
        auto_refresh = self._pending_auto_refresh
        self._analysing = False
        self._btn_analyze.setEnabled(True)
        if auto_refresh and self._has_results:
            self._status.setText(f"Verversen mislukt: {msg} (laatste resultaat behouden)")
        else:
            self._status.setText(f"Fout: {msg}")
        self._schedule_pending_analysis()

    def _rerun_with_role_prefs(self) -> None:
        if self._last_payload is None:
            return
        try:
            from ic_gamedata.party_advisor import analyze_party
        except ImportError:
            return
        report = analyze_party(
            self._last_payload,
            goal=self._last_goal,
            context=self._last_context,
            include_specializations=False,
            include_formation=self._cb_formation.isChecked(),
        )
        scroll_y = self._scroll.verticalScrollBar().value()
        self._render_report(report, reset_scroll=False)
        self._scroll.verticalScrollBar().setValue(scroll_y)
        self._status.setText(report.summary)

    def _on_role_selected(self, hero_id: int, role: str) -> None:
        try:
            from ic_gamedata.seat_advisor import set_chosen_role
        except ImportError:
            return
        set_chosen_role(hero_id, self._last_goal, role if role else None)
        self._rerun_with_role_prefs()

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

    def _render_report(self, report, *, reset_scroll: bool = True) -> None:
        self._show_results_panel()
        self._clear()

        context_labels = {"campaign": "Campaign", "events": "Events", "push": "Push", "modron": "Modron"}
        try:
            from ic_gamedata.party_advisor import goal_label as advisor_goal_label
        except ImportError:
            advisor_goal_label = lambda g: g  # noqa: E731
        goal_text = advisor_goal_label(report.goal)

        head = advisor_card(highlight=False)
        head_lyt = advisor_card_layout(head)
        head_lyt.addWidget(advisor_lbl(report.summary, kind="subtitle"))
        head_lyt.addWidget(
            advisor_lbl(
                f"{goal_text}  ·  {context_labels.get(report.context, report.context)}  ·  {report.adventure_name}",
                kind="muted",
            )
        )
        if report.gold_growth_rate is not None and report.goal == "gold":
            head_lyt.addWidget(advisor_lbl(f"Gold scaling: {report.gold_growth_rate:.2f}×", kind="body"))
        if report.adventure_buff_note:
            head_lyt.addWidget(advisor_lbl(report.adventure_buff_note, kind="body"))
        self._layout.addWidget(head)

        if report.seat_report and report.seat_report.seats:
            self._render_seat_section(report.seat_report, goal=report.goal)

        if report.formation_insights:
            advisor_section(self._layout, "Formatie & posities")
            for insight in report.formation_insights:
                seat_str = f"slot {insight.seat}" if insight.seat is not None else "—"
                extra = ""
                if insight.related_seat is not None and insight.related_hero_name:
                    extra = f" ↔ {insight.related_hero_name} (slot {insight.related_seat})"
                card = advisor_card(highlight=True)
                lyt = advisor_card_layout(card)
                lyt.addWidget(advisor_lbl(f"{insight.headline} ({seat_str}{extra})", kind="subtitle"))
                lyt.addWidget(advisor_lbl(insight.detail, kind="body"))
                self._layout.addWidget(card)

        if report.tips:
            advisor_section(self._layout, "Formation-tips")
            for tip in report.tips:
                card = advisor_card()
                lyt = advisor_card_layout(card)
                lyt.addWidget(advisor_lbl(f"Tip {tip.priority} · {tip.title}", kind="subtitle"))
                lyt.addWidget(advisor_lbl(tip.detail, kind="body"))
                self._layout.addWidget(card)

        self._layout.addStretch(1)

        if reset_scroll:
            self._scroll.verticalScrollBar().setValue(0)

    def _render_seat_section(self, seat_report, *, goal: str = "bud") -> None:
        try:
            from ic_gamedata.seat_advisor.models import STANDARD_SEAT_ROLES
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"  # noqa: E731
            STANDARD_SEAT_ROLES = []

        advisor_section(self._layout, "Seats (meest relevant bovenaan)")
        self._seat_card_frames = {}

        if goal == "bud" and seat_report.bud_hero_name:
            bud_card = advisor_card(accent_bar=BUD_BAR)
            advisor_card_layout(bud_card).addWidget(
                advisor_lbl(f"BUD deze run: {seat_report.bud_hero_name}", kind="subtitle")
            )
            self._layout.addWidget(bud_card)
        elif goal == "speed" and seat_report.speed_hero_name:
            speed_card = advisor_card(accent_bar=BUD_BAR)
            advisor_card_layout(speed_card).addWidget(
                advisor_lbl(f"Speed focus: {seat_report.speed_hero_name}", kind="subtitle")
            )
            self._layout.addWidget(speed_card)

        for seat in seat_report.seats:
            highlight = seat.priority < 20
            card = advisor_card(highlight=highlight)
            lyt = advisor_card_layout(card)

            h_row = QHBoxLayout()
            h_row.setSpacing(10)
            h_row.addWidget(advisor_portrait(seat.hero_id), alignment=Qt.AlignmentFlag.AlignTop)
            left = QVBoxLayout()
            left.setSpacing(2)
            left.addWidget(advisor_lbl(seat.hero_name, kind="title"))
            meta_parts = [f"Slot {seat.seat}", seat.zone.upper()]
            if seat.is_bud:
                meta_parts.append("BUD")
            elif seat.is_speed_focus:
                meta_parts.append("Speed")
            left.addWidget(advisor_lbl(" · ".join(meta_parts), kind="muted"))
            h_row.addLayout(left, stretch=1)
            h_row.addWidget(advisor_badge(seat.gear_label), alignment=Qt.AlignmentFlag.AlignTop)
            lyt.addLayout(h_row)

            role_row = QHBoxLayout()
            role_row.setSpacing(8)
            role_row.addWidget(advisor_lbl("Rol", kind="muted"))
            role_combo, hint = advisor_role_combo(
                seat,
                STANDARD_SEAT_ROLES,
                role_label,
                self._on_role_selected,
            )
            role_row.addWidget(role_combo)
            role_row.addWidget(advisor_lbl(hint, kind="muted"), stretch=1)
            lyt.addLayout(role_row)

            has_body = False
            if seat.relevance_reason and seat.relevance_reason != "OK":
                lyt.addWidget(advisor_lbl(seat.relevance_reason, kind="warn"))
                has_body = True

            for line in seat.insights:
                lyt.addWidget(advisor_lbl(f"· {line.headline}: {line.detail}", kind="insight"))
                has_body = True

            if seat.bench_alternatives:
                alts = ", ".join(f"{a.hero_name} ({a.reason})" for a in seat.bench_alternatives[:3])
                lyt.addWidget(advisor_lbl(f"Bench: {alts}", kind="body"))
                has_body = True

            if seat.formation_advice:
                lyt.addWidget(advisor_lbl(seat.formation_advice, kind="body"))
                has_body = True

            source = getattr(seat, "advice_source", "") or ""
            source_url = getattr(seat, "advice_source_url", "") or ""
            wiki_url = getattr(seat, "advice_wiki_url", "") or ""
            if source or source_url or wiki_url or has_body:
                lyt.addWidget(advisor_divider())

            if source or source_url or wiki_url:
                src_row = QHBoxLayout()
                src_row.addWidget(
                    advisor_lbl(
                        f"Bron: {source}" if source else "Bron: community guide",
                        kind="muted",
                    )
                )
                src_row.addStretch(1)
                if source_url:
                    src_row.addWidget(advisor_link_btn("Reddit", source_url))
                if wiki_url:
                    src_row.addWidget(advisor_link_btn("Wiki", wiki_url))
                lyt.addLayout(src_row)

            feats = seat.recommended_feats
            is_open = self._feat_open.get(seat.hero_id, bool(feats))
            role_str = seat.effective_role or ""
            count_hint = f"{len(feats)} aanbevolen" if feats else "geen data"
            feat_toggle = QPushButton(f"{'▾' if is_open else '▸'} Feats · {role_str} · {count_hint}")
            feat_toggle.setObjectName("featToggle")
            feat_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            feat_toggle.setFlat(True)
            feat_body = QWidget()
            feat_body.setStyleSheet("background: transparent; border: none;")
            feat_lyt = QVBoxLayout(feat_body)
            feat_lyt.setContentsMargins(8, 0, 0, 0)
            feat_lyt.setSpacing(4)
            if feats:
                for feat in feats[:8]:
                    feat_kind = {
                        "active": "feat_active",
                        "owned": "feat_owned",
                        "missing": "feat_missing",
                    }.get(feat.status, "body")
                    feat_lyt.addWidget(advisor_lbl(f"• {feat.name}", kind=feat_kind))
            else:
                feat_lyt.addWidget(advisor_lbl("Geen feat-advies voor deze champion/rol.", kind="muted"))
            feat_body.setVisible(is_open)

            def _make_toggle(btn, body, hid):
                def _toggle():
                    new_state = not body.isVisible()
                    body.setVisible(new_state)
                    self._feat_open[hid] = new_state
                    text = btn.text()
                    btn.setText(text.replace("▸", "▾") if new_state else text.replace("▾", "▸"))

                return _toggle

            feat_toggle.clicked.connect(_make_toggle(feat_toggle, feat_body, seat.hero_id))
            lyt.addWidget(feat_toggle)
            lyt.addWidget(feat_body)

            self._layout.addWidget(card)
            self._seat_card_frames[seat.seat] = card

        self._render_formation_visual(seat_report)

    def _highlight_seat_card(self, seat: int) -> None:
        card = self._seat_card_frames.get(seat)
        if card is None:
            return
        self._scroll.ensureWidgetVisible(card, 0, 80)

    def _render_formation_visual(self, seat_report) -> None:
        advisor_section(self._layout, f"Formatie — {seat_report.formation_name}")
        nodes = [n for n in seat_report.visual_nodes if n.hero_id is not None]
        if not nodes:
            card = advisor_card()
            advisor_card_layout(card).addWidget(
                advisor_lbl("Geen formatie-posities beschikbaar.", kind="muted")
            )
            self._layout.addWidget(card)
            return

        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"  # noqa: E731

        pad = 16
        card_w, card_h = 100, 58
        min_x = min(n.x for n in nodes)
        min_y = min(n.y for n in nodes)
        width = int(max(n.x for n in nodes) - min_x + card_w + pad * 2)
        height = int(max(n.y for n in nodes) - min_y + card_h + pad * 2)
        height = max(180, min(height, 480))
        width = max(320, width)

        shell = advisor_card()
        shell_lyt = advisor_card_layout(shell)
        shell_lyt.addWidget(
            advisor_lbl(
                "Klik op een slot om naar de seat-kaart te springen. "
                "Enemies → rechts (front = naar rechts).",
                kind="muted",
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(height)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        board = QWidget()
        board.setFixedSize(width, height)
        board.setStyleSheet(
            f"background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 8px;"
        )

        for node in nodes:
            x = int((node.x - min_x) + pad)
            y = int((node.y - min_y) + pad)
            zone_bg = FORMATION_ZONE_BG.get(node.zone, "#333338")
            border = "#dc2626" if node.has_issue else ("#1f6feb" if node.is_bud else "#52525b")
            role = node.effective_role or node.inferred_role or "flex"

            seat_frame = FormationSeatCard(node.seat, board)
            seat_frame.setGeometry(x, y, card_w, card_h)
            seat_frame.setStyleSheet(
                f"QFrame {{ background: {zone_bg}; border: 2px solid {border}; border-radius: 8px; }}"
                f"QFrame:hover {{ border-color: {ACCENT}; }}"
            )
            seat_frame.clicked.connect(self._highlight_seat_card)

            seat_lyt = QVBoxLayout(seat_frame)
            seat_lyt.setContentsMargins(6, 4, 6, 4)
            seat_lyt.setSpacing(2)
            seat_lyt.addWidget(advisor_lbl(f"Slot {node.seat} · {node.zone}", kind="muted"))
            name_lbl = advisor_lbl((node.hero_name or "?")[:14], kind="subtitle")
            if node.is_bud:
                name_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #93c5fd;")
            seat_lyt.addWidget(name_lbl)
            seat_lyt.addWidget(advisor_lbl(role_label(role), kind="muted"))

        scroll.setWidget(board)
        shell_lyt.addWidget(scroll)
        self._layout.addWidget(shell)
