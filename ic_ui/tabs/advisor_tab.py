"""Party Advisor tab: seat roles, formation tips, and feat recommendations."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QThreadPool
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
from ic_ui.theme import (
    advisor_text_styles,
    formation_board_stylesheet,
    on_theme_changed,
)
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar
from ic_ui.widgets.advisor_widgets import (
    FormationSeatCard,
    advisor_badge,
    advisor_card,
    advisor_card_layout,
    advisor_divider,
    advisor_lbl,
    advisor_link_btn,
    advisor_portrait,
    advisor_role_combo,
    advisor_section,
    refresh_advisor_chrome,
)
from ic_ui.workers.advisor import AdvisorRunnable
from ic_ui.workers.roster_upgrade import RosterUpgradeRunnable

if TYPE_CHECKING:
    from ic_core.game_data_service import GameDataService, SnapshotEnvelope
    from ic_gamedata.roster_upgrade_advisor import RosterUpgradeSuggestion


class AdvisorTab(QWidget):
    """Analyze party composition, seats, and formation."""

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
        self._feat_open: dict[int, bool] = {}
        self._analysing = False
        self._roster_searching = False
        self._roster_suggestions: tuple[RosterUpgradeSuggestion, ...] = ()
        self._last_report = None
        self._pending_auto_refresh = False
        self._pending_analysis: tuple[
            dict, str | None, bool, bool, tuple[Any, ...] | None
        ] | None = None
        self._current_party_changed = False
        self._has_results = False
        self._worker_signals = None
        self._roster_worker_signals = None
        self._seat_card_frames: dict[int, QFrame] = {}
        self._build_ui()
        on_theme_changed(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
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
        # Degraded timer polls keep cache; only re-analyze on force/change/first fill.
        if not should_refresh_advice(
            force=force,
            first=first,
            changed=changed,
            empty_retry=empty_retry,
            degraded=envelope.degraded,
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
        party_changed = (
            self._last_party_id is not None
            and envelope.party_id is not None
            and envelope.party_id != self._last_party_id
        )
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

    def request_analyze(self, *, auto_refresh: bool = False) -> None:
        if self._data is None:
            self._status.setText("Geen data-service — herstart de app.")
            return
        if not self._data.refresh_credentials() and self._data.credentials is None:
            if not auto_refresh:
                self._status.setText("Geen API-credentials. Ga naar Dashboard → Opnieuw zoeken.")
            return
        if not auto_refresh:
            self._btn_analyze.setEnabled(False)
            self._status.setText("Analyseren…")
        cached = self._data.last_payload
        if cached is not None:
            self.start_analysis(cached, None, auto_refresh=auto_refresh, advice_fp=None)
        self._data.request_poll(
            reason="advisor",
            force_consumers={"advisor", "specializations"},
            auto_refresh=auto_refresh,
        )

    def request_roster_upgrades(self) -> None:
        """On-demand search for owned champions that may improve the active party."""
        payload = self._last_payload
        if payload is None and self._data is not None:
            payload = self._data.last_payload
        if payload is None:
            self._status.setText("Nog geen party-data — analyseer eerst of wacht op een API-poll.")
            return
        if self._roster_searching:
            return
        self._last_goal = self._controls.goal()
        self._last_context = self._controls.context()
        self._roster_searching = True
        self._btn_roster.setEnabled(False)
        self._status.setText("Owned champions vergelijken met de huidige party…")
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
        self._btn_roster.setEnabled(True)
        self._roster_suggestions = tuple(suggestions or ())
        if not self._roster_suggestions:
            self._status.setText(
                "Geen duidelijke owned upgrade gevonden — rollen gedekt, of geen veilige "
                "BUD-swap (support-ilvl alleen is geen reden meer)."
            )
        else:
            self._status.setText(
                f"{len(self._roster_suggestions)} mogelijke party-upgrade(s) gevonden."
            )
        if self._last_report is not None:
            scroll_y = self._scroll.verticalScrollBar().value()
            self._render_report(self._last_report, reset_scroll=False)
            self._scroll.verticalScrollBar().setValue(scroll_y)
        elif self._roster_suggestions:
            self._show_results_panel()
            self._clear()
            self._render_roster_upgrade_section()
            self._layout.addStretch(1)

    def _on_roster_upgrades_error(self, msg: str) -> None:
        self._roster_worker_signals = None
        self._roster_searching = False
        self._btn_roster.setEnabled(True)
        self._status.setText(f"Betere champs mislukt: {msg}")

    def notify_fetch_inflight(self, *, manual_request: bool) -> None:
        if manual_request:
            self._btn_analyze.setEnabled(True)
            self._status.setText("Data wordt al opgehaald… Probeer zo opnieuw of wacht op de poll.")

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
        advice_fp: tuple[Any, ...] | None = None,
    ) -> None:
        if self._analysing:
            self._pending_analysis = (payload, err, auto_refresh, party_changed, advice_fp)
            return
        goal = self._controls.goal()
        context = self._controls.context()
        include_formation = self._controls.include_formation()
        self._pending_auto_refresh = auto_refresh
        self._current_party_changed = party_changed
        self._running_advice_fp = advice_fp
        self._analysing = True
        target = party_id_from_payload(payload)
        if party_changed:
            party_txt = f"party {target}" if target is not None else "nieuwe party"
            self._status.setText(f"Party gewisseld ({party_txt}) — analyseren…")
            self._btn_analyze.setEnabled(False)
        elif not auto_refresh:
            self._status.setText("Analyseren…")
            self._btn_analyze.setEnabled(False)
        worker = AdvisorRunnable(
            goal,
            context,
            include_formation,
            payload,
            err,
            signals_parent=self,
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
        self._controls = AdvisorGoalContextBar(include_formation=True)
        self._controls.changed.connect(self._on_options_changed)
        self._btn_analyze = QPushButton("Analyseren")
        self._btn_analyze.clicked.connect(lambda: self.request_analyze(auto_refresh=False))
        self._btn_roster = QPushButton("Betere champs")
        self._btn_roster.setToolTip(
            "Zoek owned champions die mogelijk beter werken in de huidige party."
        )
        self._btn_roster.clicked.connect(self.request_roster_upgrades)
        ctrl_row.addWidget(self._controls, stretch=1)
        ctrl_row.addWidget(self._btn_analyze)
        ctrl_row.addWidget(self._btn_roster)
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
        self._last_goal = self._controls.goal()
        self._last_context = self._controls.context()
        self._roster_suggestions = ()
        self._rerun_with_role_prefs()

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

    def _on_done(self, result) -> None:
        self._worker_signals = None
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
        self._last_formation_empty = not bool(report.formation_heroes)
        self._commit_advice_fp(formation_empty=self._last_formation_empty)
        self._running_advice_fp = None
        self._last_goal = report.goal
        self._last_context = report.context
        self._last_report = report
        if party_changed:
            self._roster_suggestions = ()
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
        self._worker_signals = None
        auto_refresh = self._pending_auto_refresh
        self._running_advice_fp = None
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
            include_formation=self._controls.include_formation(),
        )
        self._last_report = report
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
            advisor_goal_label = lambda g: g
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

        self._render_roster_upgrade_section()

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

    def _render_roster_upgrade_section(self) -> None:
        if not self._roster_suggestions:
            return
        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda role: role

        advisor_section(self._layout, "Betere champs (owned)")
        intro = advisor_card(highlight=False)
        intro_lyt = advisor_card_layout(intro)
        intro_lyt.addWidget(
            advisor_lbl(
                "Voorstellen op basis van rollen, seat-legaliteit, gear/ilvl, affiliatie én een "
                "relatieve BUD-proxy (live carry-damage × support/positie). Geen exacte combat-sim — "
                "gebruik dit als gerichte shortlist.",
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
                meta_parts.append(f"seat {item.candidate_seat} nieuw")
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
            lyt.addWidget(advisor_lbl(f"Waarom: {item.why}", kind="body"))
            self._layout.addWidget(card)

    def _render_seat_section(self, seat_report, *, goal: str = "bud") -> None:
        try:
            from ic_gamedata.seat_advisor.models import STANDARD_SEAT_ROLES
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"
            STANDARD_SEAT_ROLES = []

        advisor_section(self._layout, "Seats (meest relevant bovenaan)")
        self._seat_card_frames = {}

        if goal == "bud" and seat_report.bud_hero_name:
            bud_card = advisor_card(accent_bar=ui_theme.BUD_BAR)
            advisor_card_layout(bud_card).addWidget(
                advisor_lbl(f"BUD deze run: {seat_report.bud_hero_name}", kind="subtitle")
            )
            self._layout.addWidget(bud_card)
        elif goal == "speed" and seat_report.speed_hero_name:
            speed_card = advisor_card(accent_bar=ui_theme.BUD_BAR)
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
        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"

        self._render_formation_board(
            [n for n in seat_report.visual_nodes if n.hero_id is not None],
            role_label=role_label,
            intro=(
                "Klik op een slot om naar de seat-kaart te springen. "
                "Enemies → rechts (front = naar rechts)."
            ),
        )

        recommended = [
            n for n in getattr(seat_report, "recommended_visual_nodes", ()) if n.hero_id is not None
        ]
        if recommended:
            self._render_formation_board(
                recommended,
                role_label=role_label,
                title="Ideale formatie (owned)",
                intro="Veilige upgrade-projectie op basis van je huidige owned champions.",
            )
        else:
            hidden_reason = getattr(seat_report, "recommended_hidden_reason", None)
            if hidden_reason:
                card = advisor_card()
                lyt = advisor_card_layout(card)
                lyt.addWidget(advisor_lbl("Ideale formatie (owned)", kind="subtitle"))
                lyt.addWidget(advisor_lbl(hidden_reason, kind="muted"))
                self._layout.addWidget(card)

    def _render_formation_board(
        self,
        nodes,
        *,
        role_label,
        intro: str,
        title: str | None = None,
    ) -> None:
        if not nodes:
            card = advisor_card()
            advisor_card_layout(card).addWidget(
                advisor_lbl("Geen formatie-posities beschikbaar.", kind="muted")
            )
            self._layout.addWidget(card)
            return

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
        if title:
            shell_lyt.addWidget(advisor_lbl(title, kind="subtitle"))
        shell_lyt.addWidget(advisor_lbl(intro, kind="muted"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(height)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        board = QWidget()
        board.setFixedSize(width, height)
        board.setStyleSheet(formation_board_stylesheet())

        for node in nodes:
            x = int((node.x - min_x) + pad)
            y = int((node.y - min_y) + pad)
            zone_bg = ui_theme.FORMATION_ZONE_BG.get(node.zone, ui_theme.BG_HOVER)
            border = (
                ui_theme.ISSUE_BORDER
                if node.has_issue
                else (ui_theme.BUD_BORDER if node.is_bud else ui_theme.BORDER_HOVER)
            )
            role = node.effective_role or node.inferred_role or "flex"

            seat_frame = FormationSeatCard(node.seat, board)
            seat_frame.setGeometry(x, y, card_w, card_h)
            seat_frame.setStyleSheet(
                f"QFrame {{ background: {zone_bg}; border: 2px solid {border}; border-radius: 8px; }}"
                f"QFrame:hover {{ border-color: {ui_theme.ACCENT}; }}"
            )
            seat_frame.clicked.connect(self._highlight_seat_card)

            seat_lyt = QVBoxLayout(seat_frame)
            seat_lyt.setContentsMargins(6, 4, 6, 4)
            seat_lyt.setSpacing(2)
            seat_lyt.addWidget(advisor_lbl(f"Slot {node.seat} · {node.zone}", kind="muted"))
            name_lbl = advisor_lbl((node.hero_name or "?")[:14], kind="subtitle")
            if node.is_bud:
                name_lbl.setProperty("advisorKind", "seat_name")
                name_lbl.setStyleSheet(advisor_text_styles()["seat_name"])
            seat_lyt.addWidget(name_lbl)
            seat_lyt.addWidget(advisor_lbl(role_label(role), kind="muted"))

        scroll.setWidget(board)
        shell_lyt.addWidget(scroll)
        self._layout.addWidget(shell)
