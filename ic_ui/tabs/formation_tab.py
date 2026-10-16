"""Formation tab: active party layout, optimal projection, and AI formation advice."""

from __future__ import annotations

import html
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import (
    QAction,
    QBrush,
    QClipboard,
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
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
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar
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
    from ic_gamedata.formation_ai_advice.models import AppliedFormationSnapshot, FormationAdviceResult


class FormationTab(QWidget):
    """Show the live formation and the owned optimal projection when available."""

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
        self._ai_result: FormationAdviceResult | None = None
        self._ai_request_form_fp: str | None = None
        self._clipboard_export: dict | None = None
        self._clipboard_form_fp: str | None = None
        self._applied_seat_by_hero: dict[int, int] | None = None
        self._applied_spec_advice: dict[int, tuple] = {}
        self._undo_snapshot: AppliedFormationSnapshot | None = None
        self._settings = QSettings("IdleChampions", "Companion")
        self._goal_params_party_id: int | None = None
        self._pending_fixed_dps: int | None = None
        self._build_ui()
        on_theme_changed(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_BODY};")
        if self._last_report is not None:
            self._render_report(self._last_report, reset_scroll=False)
        else:
            refresh_advisor_chrome(self)

    @property
    def last_formation_empty(self) -> bool:
        return self._last_formation_empty

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
        if not should_refresh_advice(
            force=force,
            first=first,
            changed=changed,
            empty_retry=empty_retry,
            degraded=envelope.degraded,
        ):
            return
        if envelope.payload is None:
            if force and not envelope.auto_refresh:
                self._status.setText(envelope.err or "No API data received.")
            return
        party_changed = (
            self._last_party_id is not None
            and envelope.party_id is not None
            and envelope.party_id != self._last_party_id
        )
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
        """Re-analyze from cache and force a poll (used by goal changes)."""
        if self._data is None:
            self._status.setText("No data service — restart the app.")
            return
        if not auto_refresh:
            self._status.setText("Loading formation…")
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
            self._pending_analysis = (payload, err, auto_refresh, party_changed, advice_fp)
            return
        goal = self._advice_goal_id() or "push"
        context = self._controls.context()
        self._pending_auto_refresh = auto_refresh
        self._running_advice_fp = advice_fp
        self._analysing = True
        self._last_payload = payload
        target = party_id_from_payload(payload)
        if party_changed:
            self._load_party_goal_settings(target)
            party_txt = f"party {target}" if target is not None else "new party"
            self._status.setText(f"Party switched ({party_txt}) — loading formation…")
        elif not auto_refresh:
            self._status.setText("Loading formation…")
        shared_advice_hub().submit(
            goal=goal,
            context=context,
            payload=payload,
            err=err,
            advice_fp=advice_fp,
            on_done=self._on_shared_done,
            on_error=self._on_error,
        )

    def _advice_goal_id(self) -> str:
        """Current user-facing advice goal (never invent favor/gems from legacy)."""
        goal = self._controls.goal_or_none()
        if goal:
            return str(goal)
        if self._controls.needs_goal_confirm():
            return ""
        return "push"

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # One compact bar: shared goal/context + fixed DPS + chat actions.
        bar = QHBoxLayout()
        self._controls = AdvisorGoalContextBar(include_formation=False)
        self._controls.changed.connect(self._on_options_changed)
        bar.addWidget(self._controls, stretch=0)

        bar.addWidget(QLabel("Vaste hoofd-DPS:"))
        self._dps_combo = QComboBox()
        self._dps_combo.setMinimumWidth(160)
        self._dps_combo.setToolTip(
            "Optioneel. Alleen ‘Vaste hoofd-DPS’ lockt die champion in exports. "
            "‘Geen vaste hoofd-DPS’ is geldig voor elk doel."
        )
        self._dps_combo.currentIndexChanged.connect(self._on_fixed_dps_changed)
        bar.addWidget(self._dps_combo)

        # Split control: ▾ alleen modus kiezen (knoptekst); knop klikt → klembord.
        self._copy_mode = "standard"
        self._copy_mode_labels = {
            "standard": "Kopieer voor chat — standaard",
            "json": "Kopieer voor chat — + JSON",
            "swap": "Kopieer voor chat — zoek betere champions",
            "debug": "Kopieer voor chat — debugexport",
        }
        self._copy_chat_btn = QPushButton(self._copy_mode_labels["standard"])
        self._copy_chat_btn.setMinimumWidth(380)
        self._copy_chat_btn.setToolTip(
            "Kopieert de geselecteerde modus naar het klembord. "
            "Kies eerst een modus via ▾; die tekst verschijnt op deze knop."
        )
        self._copy_chat_btn.clicked.connect(lambda: self._on_copy_chat_primary())
        bar.addWidget(self._copy_chat_btn)

        self._copy_chat_menu_btn = QToolButton()
        self._copy_chat_menu_btn.setText("▾")
        self._copy_chat_menu_btn.setToolTip(
            "Kies een kopieermodus. Dit vult het klembord nog niet — klik daarna op de knop."
        )
        self._copy_chat_menu_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        copy_menu = QMenu(self._copy_chat_menu_btn)
        act_table = QAction("Standaard (plaatsing + specs)", self)
        act_table.triggered.connect(lambda: self._set_copy_mode("standard"))
        act_json = QAction("+ JSON (voor Plak voorstel)", self)
        act_json.triggered.connect(lambda: self._set_copy_mode("json"))
        act_swap = QAction("Zoek betere champions", self)
        act_swap.triggered.connect(lambda: self._set_copy_mode("swap"))
        act_debug = QAction("Debugexport (volledig)", self)
        act_debug.triggered.connect(lambda: self._set_copy_mode("debug"))
        copy_menu.addAction(act_table)
        copy_menu.addAction(act_json)
        copy_menu.addAction(act_swap)
        copy_menu.addSeparator()
        copy_menu.addAction(act_debug)
        self._copy_chat_menu_btn.setMenu(copy_menu)
        bar.addWidget(self._copy_chat_menu_btn)

        self._paste_proposal_btn = QPushButton("Plak")
        self._paste_proposal_btn.setToolTip(
            "Plak JSON-voorstel (alleen na ‘Kopieer met JSON’)."
        )
        self._paste_proposal_btn.clicked.connect(self._on_paste_proposal)
        bar.addWidget(self._paste_proposal_btn)

        # Overnemen / Undo removed from the bar to free space for the copy button.
        self._apply_advice_btn = None
        self._undo_advice_btn = None

        bar.addStretch(1)
        root.addLayout(bar)

        # Goal help + goal-specific parameters (lightweight; no blocking popups).
        self._goal_help = QLabel("")
        self._goal_help.setWordWrap(True)
        self._goal_help.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(self._goal_help)

        self._goal_params_stack = QStackedWidget()
        self._build_goal_param_pages()
        root.addWidget(self._goal_params_stack)

        # Optional restriction + status on one quiet row.
        meta_row = QHBoxLayout()
        self._restriction_edit = QLineEdit()
        self._restriction_edit.setPlaceholderText("Restricties (optioneel)…")
        self._restriction_edit.setMaximumWidth(280)
        self._restriction_edit.setToolTip(
            "Alleen nodig als adventure-/variantrestricties niet uit de API komen."
        )
        meta_row.addWidget(self._restriction_edit)

        self._goal_note_edit = QLineEdit()
        self._goal_note_edit.setPlaceholderText("Optionele toelichting…")
        self._goal_note_edit.setMaximumWidth(220)
        self._goal_note_edit.setToolTip("Korte toelichting bij het gekozen doel.")
        self._goal_note_edit.textChanged.connect(self._persist_party_goal_settings)
        meta_row.addWidget(self._goal_note_edit)

        self._ai_status = QLabel("")
        self._ai_status.setWordWrap(True)
        self._ai_status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        meta_row.addWidget(self._ai_status, stretch=1)
        root.addLayout(meta_row)

        self._status = QLabel(
            "Formatie + chat-advies. Refresh (F5) voor een volledige update."
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
        root.addWidget(scroll, stretch=1)

        empty = advisor_card(compact=True)
        empty_lyt = advisor_card_layout(empty, compact=True)
        empty_lyt.addWidget(
            advisor_lbl(
                "No formation loaded yet. Place champions in seats in Idle Champions "
                "and wait for the API poll, or click Refresh (top right / F5).",
                kind="muted",
            )
        )
        self._layout.addWidget(empty)
        self._layout.addStretch(1)
        self._sync_goal_param_visibility()

    def _build_goal_param_pages(self) -> None:
        """Create stacked pages for goal-dependent inputs (index by goal id)."""
        self._goal_page_index: dict[str, int] = {}

        def _page(*widgets: QWidget) -> QWidget:
            wrap = QWidget()
            row = QHBoxLayout(wrap)
            row.setContentsMargins(0, 0, 0, 0)
            for w in widgets:
                row.addWidget(w)
            row.addStretch(1)
            return wrap

        # push — mostly live context; no extra required fields
        push_lbl = QLabel("Push gebruikt huidige/hoogste area uit de live context indien bekend.")
        push_lbl.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        self._goal_page_index["push"] = self._goal_params_stack.addWidget(_page(push_lbl))

        # quest
        self._quest_area = QSpinBox()
        self._quest_area.setRange(0, 99999)
        self._quest_area.setSpecialValueText("auto/onbekend")
        self._quest_area.setToolTip(
            "Vereist gebied. 0 = gebruik adventure-data indien bekend, anders onbekend."
        )
        self._quest_area.valueChanged.connect(self._persist_party_goal_settings)
        self._quest_end = QLineEdit()
        self._quest_end.setPlaceholderText("Andere eindvoorwaarde (optioneel)…")
        self._quest_end.setMinimumWidth(220)
        self._quest_end.textChanged.connect(self._persist_party_goal_settings)
        self._quest_source_lbl = QLabel("")
        self._quest_source_lbl.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        self._goal_page_index["quest_clear"] = self._goal_params_stack.addWidget(
            _page(
                QLabel("Vereist gebied:"),
                self._quest_area,
                self._quest_end,
                self._quest_source_lbl,
            )
        )

        # gems
        self._gem_play_mode = QComboBox()
        for label, value in (
            ("Onbekend", "unknown"),
            ("Voorgrond", "foreground"),
            ("Achtergrond", "background"),
            ("Offline", "offline"),
        ):
            self._gem_play_mode.addItem(label, value)
        self._gem_play_mode.currentIndexChanged.connect(self._persist_party_goal_settings)
        self._gem_auto_reset = QComboBox()
        for label, value in (
            ("Onbekend", "unknown"),
            ("Ja", "yes"),
            ("Nee", "no"),
        ):
            self._gem_auto_reset.addItem(label, value)
        self._gem_auto_reset.currentIndexChanged.connect(self._persist_party_goal_settings)
        self._gem_reset_area = QSpinBox()
        self._gem_reset_area.setRange(0, 99999)
        self._gem_reset_area.setSpecialValueText("onbekend")
        self._gem_reset_area.setToolTip("Resetgebied. 0 = onbekend (geen area 0).")
        self._gem_reset_area.valueChanged.connect(self._persist_party_goal_settings)
        self._goal_page_index["gem_farm"] = self._goal_params_stack.addWidget(
            _page(
                QLabel("Speelmodus:"),
                self._gem_play_mode,
                QLabel("Auto-reset:"),
                self._gem_auto_reset,
                QLabel("Resetgebied:"),
                self._gem_reset_area,
            )
        )

        # favor
        self._favor_horizon = QComboBox()
        for label, value in (
            ("Geen voorkeur / onbekend", "unknown"),
            ("Meer favor per run", "per_run"),
            ("Meer favor per tijdseenheid", "per_time"),
        ):
            self._favor_horizon.addItem(label, value)
        self._favor_horizon.currentIndexChanged.connect(self._persist_party_goal_settings)
        self._favor_campaign_lbl = QLabel("Campagne: actueel indien bekend")
        self._favor_campaign_lbl.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        self._goal_page_index["favor_farm"] = self._goal_params_stack.addWidget(
            _page(
                QLabel("Tijdshorizon:"),
                self._favor_horizon,
                self._favor_campaign_lbl,
            )
        )

        # custom task
        self._task_description = QLineEdit()
        self._task_description.setPlaceholderText("Taakomschrijving (verplicht)…")
        self._task_description.setMinimumWidth(280)
        self._task_description.textChanged.connect(self._persist_party_goal_settings)
        self._task_target = QLineEdit()
        self._task_target.setPlaceholderText("Doelwaarde (optioneel)")
        self._task_target.setMaximumWidth(140)
        self._task_target.textChanged.connect(self._persist_party_goal_settings)
        self._task_time_limit = QLineEdit()
        self._task_time_limit.setPlaceholderText("Tijdslimiet (optioneel)")
        self._task_time_limit.setMaximumWidth(140)
        self._task_time_limit.textChanged.connect(self._persist_party_goal_settings)
        self._goal_page_index["custom_task"] = self._goal_params_stack.addWidget(
            _page(
                self._task_description,
                self._task_target,
                self._task_time_limit,
            )
        )

        # empty / unconfirmed
        empty = QLabel("Kies eerst een gebruikersdoel om door te gaan.")
        empty.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        self._goal_page_index[""] = self._goal_params_stack.addWidget(_page(empty))

    def _party_settings_prefix(self, party_id: int | None = None) -> str:
        pid = party_id if party_id is not None else self._last_party_id
        if pid is None:
            return "advice/party/_none"
        return f"advice/party/{pid}"

    def _fixed_main_dps_id(self) -> int | None:
        data = self._dps_combo.currentData()
        return data if isinstance(data, int) else None

    def _collect_goal_parameters(self) -> dict:
        goal_id = self._advice_goal_id()
        params: dict = {}
        note = self._goal_note_edit.text().strip()
        if note:
            params["note"] = note
        if goal_id == "quest_clear":
            area = self._quest_area.value()
            if area > 0:
                params["required_area"] = area
            end = self._quest_end.text().strip()
            if end:
                params["end_condition"] = end
        elif goal_id == "gem_farm":
            params["play_mode"] = self._gem_play_mode.currentData() or "unknown"
            params["auto_reset"] = self._gem_auto_reset.currentData() or "unknown"
            reset = self._gem_reset_area.value()
            if reset > 0:
                params["reset_area"] = reset
        elif goal_id == "favor_farm":
            params["time_horizon"] = self._favor_horizon.currentData() or "unknown"
        elif goal_id == "custom_task":
            params["task_description"] = self._task_description.text().strip()
            target = self._task_target.text().strip()
            if target:
                params["target_value"] = target
            limit = self._task_time_limit.text().strip()
            if limit:
                params["time_limit"] = limit
        return params

    def _persist_party_goal_settings(self, *_args) -> None:
        prefix = self._party_settings_prefix()
        self._settings.setValue(
            f"{prefix}/fixed_main_dps_id",
            self._fixed_main_dps_id() if self._fixed_main_dps_id() is not None else "",
        )
        self._settings.setValue(f"{prefix}/goal_note", self._goal_note_edit.text())
        import json

        self._settings.setValue(
            f"{prefix}/goal_parameters",
            json.dumps(self._collect_goal_parameters(), ensure_ascii=False),
        )
        # Invalidate prior clipboard snapshot when goal inputs change.
        self._clipboard_export = None
        self._clipboard_form_fp = None

    def _load_party_goal_settings(self, party_id: int | None) -> None:
        if party_id == self._goal_params_party_id and party_id is not None:
            return
        self._goal_params_party_id = party_id
        prefix = self._party_settings_prefix(party_id)
        import json

        raw_params = self._settings.value(f"{prefix}/goal_parameters", "{}")
        try:
            params = json.loads(str(raw_params or "{}"))
        except Exception:
            params = {}
        if not isinstance(params, dict):
            params = {}

        self._goal_note_edit.blockSignals(True)
        self._goal_note_edit.setText(
            str(self._settings.value(f"{prefix}/goal_note", "") or params.get("note") or "")
        )
        self._goal_note_edit.blockSignals(False)

        self._quest_area.blockSignals(True)
        self._quest_area.setValue(int(params.get("required_area") or 0))
        self._quest_area.blockSignals(False)
        self._quest_end.blockSignals(True)
        self._quest_end.setText(str(params.get("end_condition") or ""))
        self._quest_end.blockSignals(False)

        play_idx = self._gem_play_mode.findData(params.get("play_mode") or "unknown")
        self._gem_play_mode.blockSignals(True)
        if play_idx >= 0:
            self._gem_play_mode.setCurrentIndex(play_idx)
        self._gem_play_mode.blockSignals(False)
        reset_idx = self._gem_auto_reset.findData(params.get("auto_reset") or "unknown")
        self._gem_auto_reset.blockSignals(True)
        if reset_idx >= 0:
            self._gem_auto_reset.setCurrentIndex(reset_idx)
        self._gem_auto_reset.blockSignals(False)
        self._gem_reset_area.blockSignals(True)
        self._gem_reset_area.setValue(int(params.get("reset_area") or 0))
        self._gem_reset_area.blockSignals(False)

        horizon_idx = self._favor_horizon.findData(params.get("time_horizon") or "unknown")
        self._favor_horizon.blockSignals(True)
        if horizon_idx >= 0:
            self._favor_horizon.setCurrentIndex(horizon_idx)
        self._favor_horizon.blockSignals(False)

        self._task_description.blockSignals(True)
        self._task_description.setText(str(params.get("task_description") or ""))
        self._task_description.blockSignals(False)
        self._task_target.blockSignals(True)
        self._task_target.setText(str(params.get("target_value") or ""))
        self._task_target.blockSignals(False)
        self._task_time_limit.blockSignals(True)
        self._task_time_limit.setText(str(params.get("time_limit") or ""))
        self._task_time_limit.blockSignals(False)

        # Restore fixed DPS preference for this party (may apply after combo populate).
        raw_dps = self._settings.value(f"{prefix}/fixed_main_dps_id", "")
        self._pending_fixed_dps: int | None
        try:
            self._pending_fixed_dps = int(raw_dps) if str(raw_dps).strip() else None
        except (TypeError, ValueError):
            self._pending_fixed_dps = None

        self._sync_goal_param_visibility()
        self._update_quest_source_label()
        self._update_favor_campaign_label()

    def _sync_goal_param_visibility(self) -> None:
        from ic_gamedata.advice_goals import GOAL_DEFINITIONS

        goal_id = self._advice_goal_id()
        if self._controls.needs_goal_confirm() and not self._controls.goal_or_none():
            goal_id = ""
        idx = self._goal_page_index.get(goal_id, self._goal_page_index.get("", 0))
        self._goal_params_stack.setCurrentIndex(idx)
        if goal_id in GOAL_DEFINITIONS:
            definition = GOAL_DEFINITIONS[goal_id]  # type: ignore[index]
            self._goal_help.setText(
                f"{definition.label}: {definition.description} "
                f"(hoofdmaat: {definition.primary_metric})"
            )
        elif self._controls.needs_goal_confirm():
            self._goal_help.setText(
                self._controls.migration_message()
                or "Bevestig het adviesdoel vóór je kopieert."
            )
        else:
            self._goal_help.setText("")

    def _update_quest_source_label(self) -> None:
        if self._last_payload is None:
            self._quest_source_lbl.setText("")
            return
        from ic_gamedata.advice_goals import extract_live_goal_context

        live = extract_live_goal_context(self._last_payload)
        auto = live.get("adventure_area_goal")
        if self._quest_area.value() > 0:
            self._quest_source_lbl.setText("bron: gebruiker")
        elif isinstance(auto, int) and auto > 0:
            self._quest_source_lbl.setText(f"auto uitgelezen: {auto}")
        else:
            self._quest_source_lbl.setText("eindvoorwaarde: onbekend")

    def _update_favor_campaign_label(self) -> None:
        if self._last_payload is None:
            self._favor_campaign_lbl.setText("Campagne: onbekend")
            return
        from ic_gamedata.advice_goals import extract_live_goal_context

        live = extract_live_goal_context(self._last_payload)
        name = live.get("campaign_name")
        cid = live.get("campaign_id")
        if name or cid is not None:
            self._favor_campaign_lbl.setText(
                f"Campagne: {name or cid} (actueel)"
            )
        else:
            self._favor_campaign_lbl.setText("Campagne: onbekend")

    def _on_fixed_dps_changed(self, *_args) -> None:
        self._persist_party_goal_settings()

    def _on_options_changed(self) -> None:
        self._sync_goal_param_visibility()
        self._clipboard_export = None
        self._clipboard_form_fp = None
        if self._has_results and not self._analysing:
            self.request_refresh(auto_refresh=True)

    def _build_advice_export(self) -> dict | None:
        if self._last_payload is None or self._last_report is None:
            return None
        heroes = tuple(self._last_report.formation_heroes or ())
        if not heroes:
            return None
        if self._controls.needs_goal_confirm():
            self._ai_status.setText(
                self._controls.migration_message()
                or "Bevestig eerst het adviesdoel (oude technische waarde)."
            )
            return None
        goal_id = self._advice_goal_id()
        if not goal_id:
            self._ai_status.setText("Kies eerst een gebruikersdoel.")
            return None
        from ic_gamedata.advice_goals import validate_goal_parameters
        from ic_gamedata.formation_ai_advice.export import build_export_payload

        params = self._collect_goal_parameters()
        ok, err = validate_goal_parameters(goal_id, params)
        if not ok:
            self._ai_status.setText(err or "Ongeldige doelparameters.")
            return None
        try:
            return build_export_payload(
                self._last_payload,
                heroes,
                goal=goal_id,
                context=self._controls.context(),
                fixed_main_dps_id=self._fixed_main_dps_id(),
                goal_parameters=params,
                manual_restriction_text=self._restriction_edit.text().strip() or None,
            )
        except ValueError as exc:
            self._ai_status.setText(str(exc))
            return None

    def _write_clipboard(self, text: str) -> bool:
        """Write text to the system clipboard.

        Read-back can fail with large payloads or clipboard managers; treat a
        successful ``setText`` as enough. Retry once via QMimeData if needed.
        """
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        cleaned = text.replace("\x00", "")
        if not cleaned.strip():
            return False
        try:
            clipboard.setText(cleaned, QClipboard.Mode.Clipboard)
        except Exception:
            return False
        got = clipboard.text(QClipboard.Mode.Clipboard)
        if got:
            return True
        # Large text / clipboard hooks: setText may succeed while text() is empty.
        try:
            from PySide6.QtCore import QMimeData

            mime = QMimeData()
            mime.setText(cleaned)
            clipboard.setMimeData(mime, QClipboard.Mode.Clipboard)
        except Exception:
            # Assume setText already delivered the payload.
            return True
        return True

    def _set_copy_mode(self, mode: str) -> None:
        """Dropdown: only update the selected mode + button label (no clipboard)."""
        if mode not in self._copy_mode_labels:
            mode = "standard"
        self._copy_mode = mode
        self._copy_chat_btn.setText(self._copy_mode_labels[mode])
        self._ai_status.setText(
            f"Modus geselecteerd: {self._copy_mode_labels[mode]}. "
            "Klik op de knop om naar het klembord te kopiëren."
        )

    def _on_copy_chat_primary(self) -> None:
        """Main button: copy the mode currently shown on the button."""
        mode = self._copy_mode
        if mode == "json":
            self._on_copy_for_chat(True)
        elif mode == "swap":
            self._on_copy_swap_advice()
        elif mode == "debug":
            self._on_copy_debug_export()
        else:
            self._on_copy_for_chat(False)

    def _on_copy_for_chat(self, with_json: bool = False) -> None:
        try:
            # Guard: QAction.triggered / clicked may pass a checked bool.
            if not isinstance(with_json, bool):
                with_json = False

            export = self._build_advice_export()
            if export is None:
                self._ai_status.setText(
                    "Geen formatiegegevens om te kopiëren — ververs eerst de Formation-tab."
                )
                return
            from ic_gamedata.formation_ai_advice.clipboard_export import (
                format_clipboard_markdown,
            )
            from ic_gamedata.formation_ai_advice.export import (
                formation_layout_fingerprint_from_export,
            )
            from ic_gamedata.formation_ai_advice.validate import preflight_export

            preflight = preflight_export(export)
            readiness = (export.get("readiness") or {}).get("status")
            if readiness == "blocked" or preflight.status == "invalid":
                detail = "; ".join(preflight.errors[:3]) or "geometrie/party onbetrouwbaar"
                self._ai_status.setText(f"Export geblokkeerd — {detail}")
                return

            output_mode = "json" if with_json else "table"
            text = format_clipboard_markdown(export, output_mode=output_mode)
            if not text.strip():
                self._ai_status.setText("Export leverde lege tekst — niets gekopieerd.")
                return
            if not self._write_clipboard(text):
                self._ai_status.setText(
                    "Klembord schrijven mislukt (leeg na setText). "
                    "Probeer opnieuw of controleer clipboard-software."
                )
                return
            self._clipboard_export = export
            self._clipboard_form_fp = formation_layout_fingerprint_from_export(export)
            self._ai_request_form_fp = self._clipboard_form_fp
            warn = ""
            if readiness == "ready_with_warnings" and preflight.warnings:
                warn = f" (waarschuwingen: {len(preflight.warnings)})"
            if output_mode == "table":
                self._ai_status.setText(
                    f"Compact advies gekopieerd ({len(text):,} tekens). "
                    f"AI moet alleen een Markdown-tabel teruggeven{warn}."
                )
            else:
                self._ai_status.setText(
                    f"Compact advies + JSON-modus gekopieerd ({len(text):,} tekens). "
                    f"Plak JSON terug via ‘Plak’{warn}."
                )
        except Exception as exc:
            self._ai_status.setText(f"Kopiëren mislukt: {exc}")

    def _on_copy_debug_export(self) -> None:
        export = self._build_advice_export()
        if export is None:
            self._ai_status.setText(
                "Geen formatiegegevens om te kopiëren — ververs eerst de Formation-tab."
            )
            return
        from ic_gamedata.formation_ai_advice.clipboard_export import format_debug_markdown

        text = format_debug_markdown(export)
        if not self._write_clipboard(text):
            self._ai_status.setText("Klembord schrijven mislukt voor debugexport.")
            return
        self._ai_status.setText(
            f"Debugexport gekopieerd ({len(text):,} tekens) — volledige brongegevens, "
            "niet bedoeld als standaard chatprompt."
        )

    def _advice_objective_label(self) -> str:
        from ic_gamedata.advice_goals import goal_label

        goal_id = self._advice_goal_id()
        return goal_label(goal_id) if goal_id else "doel onbevestigd"

    def _on_copy_swap_advice(self) -> None:
        """Auto roster swap export — copies only when the main button is clicked."""
        from PySide6.QtWidgets import QApplication

        if self._last_payload is None or self._last_report is None:
            self._ai_status.setText(
                "Geen formatiegegevens — ververs eerst de Formation-tab."
            )
            return
        heroes = tuple(self._last_report.formation_heroes or ())
        if not heroes:
            self._ai_status.setText("Geen actieve formatie om te vergelijken.")
            return
        if self._controls.needs_goal_confirm():
            self._ai_status.setText(
                self._controls.migration_message()
                or "Bevestig eerst het adviesdoel (oude technische waarde)."
            )
            return
        goal_id = self._advice_goal_id()
        if not goal_id:
            self._ai_status.setText("Kies eerst een gebruikersdoel vóór kopiëren.")
            return
        from ic_gamedata.advice_goals import validate_goal_parameters

        params = self._collect_goal_parameters()
        ok, err = validate_goal_parameters(goal_id, params)
        if not ok:
            self._ai_status.setText(err or "Ongeldige doelparameters.")
            return

        fixed_dps = self._fixed_main_dps_id()
        self._ai_status.setText(
            "Owned roster verzamelen voor championwisseladvies… (even geduld)"
        )
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        try:
            from ic_gamedata.formation_ai_advice.clipboard_export import (
                format_swap_clipboard_markdown,
            )
            from ic_gamedata.formation_ai_advice.swap_export import (
                build_swap_export_payload,
            )

            export = build_swap_export_payload(
                self._last_payload,
                heroes,
                locked_champion_ids=None,
                goal=goal_id,
                context=self._controls.context(),
                fixed_main_dps_id=fixed_dps,
                goal_parameters=params,
                manual_restriction_text=self._restriction_edit.text().strip()
                or None,
            )
            if app is not None:
                app.processEvents()
            text = format_swap_clipboard_markdown(export)
            if not text.strip():
                self._ai_status.setText(
                    "Wisseladvies leverde lege tekst — niets gekopieerd."
                )
                return
            self._ai_status.setText(
                f"Klembord schrijven ({len(text):,} tekens)…"
            )
            if app is not None:
                app.processEvents()
            if not self._write_clipboard(text):
                self._ai_status.setText(
                    f"Klembord schrijven mislukt voor wisseladvies "
                    f"({len(text):,} tekens)."
                )
                return
            cov = (export.get("swap") or {}).get("coverage") or {}
            # Do not overwrite standard paste/apply clipboard snapshot.
            self._ai_status.setText(
                f"Wisseladvies gekopieerd ({len(text):,} tekens) — "
                f"owned {cov.get('owned_known_count', '?')}, "
                f"opgenomen {cov.get('included_count', '?')}, "
                f"uitgesloten {cov.get('excluded_count', '?')}. "
                "Alleen advies — party/loadouts ongewijzigd."
            )
        except Exception as exc:
            self._ai_status.setText(f"Wisseladvies mislukt: {type(exc).__name__}: {exc}")

    def _on_paste_proposal(self) -> None:
        if self._clipboard_export is None:
            # Allow paste using a freshly built export if user forgot to copy,
            # but prefer the copied snapshot for request_id consistency.
            export = self._build_advice_export()
            if export is None:
                self._ai_status.setText(
                    "Eerst ‘Kopieer voor chat’ gebruiken (of formatie laden)."
                )
                return
            self._clipboard_export = export
            from ic_gamedata.formation_ai_advice.export import (
                formation_layout_fingerprint_from_export,
            )

            self._clipboard_form_fp = formation_layout_fingerprint_from_export(export)

        dialog = QDialog(self)
        dialog.setWindowTitle("Plak chat-voorstel (JSON)")
        dialog.resize(640, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Plak hier het JSON-voorstel uit de chat "
                "(of de hele chattekst met een JSON-blok)."
            )
        )
        editor = QTextEdit()
        editor.setAcceptRichText(False)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and clipboard.text().strip().startswith("{"):
            editor.setPlainText(clipboard.text())
        layout.addWidget(editor, stretch=1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        from ic_gamedata.formation_ai_advice.service import ingest_pasted_proposal

        live_fp = self._current_formation_fingerprint()
        result = ingest_pasted_proposal(
            editor.toPlainText(),
            export_payload=self._clipboard_export,
            current_formation_fingerprint=live_fp or self._clipboard_form_fp,
        )
        self._ai_request_form_fp = self._clipboard_form_fp
        self._on_ai_done(result)

    def _clear(self) -> None:
        clear_advisor_layout(self._layout)

    def _on_shared_done(self, result: SharedAdviceResult) -> None:
        self._on_done((result.payload, result.report, result.err))

    def _on_done(self, result) -> None:
        self._analysing = False
        payload, report, err = result
        self._last_report = report
        self._last_payload = payload
        self._has_results = True
        new_party = party_id_from_payload(payload)
        party_switched = new_party != self._last_party_id
        self._last_party_id = new_party
        if party_switched:
            self._load_party_goal_settings(new_party)
            self._clipboard_export = None
            self._clipboard_form_fp = None
        else:
            self._update_quest_source_label()
            self._update_favor_campaign_label()
        seat = report.seat_report
        active_nodes = (
            any(n.hero_id is not None for n in seat.visual_nodes) if seat else False
        )
        self._last_formation_empty = not bool(
            seat and (active_nodes or seat.seats)
        )
        self._last_advice_fp = commit_advice_fingerprint(
            self._running_advice_fp,
            formation_empty=self._last_formation_empty,
        )
        self._running_advice_fp = None
        status = "Formation updated"
        if err:
            status = f"{status} · {err}"
        status = f"{status} · refreshed {time.strftime('%H:%M:%S')}"
        self._status.setText(status)
        self._populate_dps_combo(report)
        self._sync_goal_param_visibility()
        self._render_report(report, reset_scroll=True)
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
        self._analysing = False
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

    def _populate_dps_combo(self, report) -> None:
        prev = self._dps_combo.currentData()
        pending = getattr(self, "_pending_fixed_dps", None)
        self._dps_combo.blockSignals(True)
        self._dps_combo.clear()
        self._dps_combo.addItem("Geen vaste hoofd-DPS", None)
        heroes = getattr(report, "formation_heroes", ()) or ()
        for hero in heroes:
            self._dps_combo.addItem(f"{hero.name} ({hero.hero_id})", hero.hero_id)
        # Only restore an explicit fixed DPS — never auto-lock BUD/top damage.
        pick = pending if pending is not None else prev
        if pick is not None:
            idx = self._dps_combo.findData(pick)
            if idx >= 0:
                self._dps_combo.setCurrentIndex(idx)
            else:
                self._dps_combo.setCurrentIndex(0)
        else:
            self._dps_combo.setCurrentIndex(0)
        self._pending_fixed_dps = None
        self._dps_combo.blockSignals(False)

    def _active_nodes_for_display(self, seat_report) -> list:
        if seat_report is None:
            return []
        nodes = [n for n in seat_report.visual_nodes if n.hero_id is not None]
        if self._applied_seat_by_hero is None:
            return nodes
        from ic_gamedata.formation_ai_advice.apply import remap_visual_nodes

        names = {
            int(n.hero_id): str(n.hero_name)
            for n in seat_report.visual_nodes
            if n.hero_id is not None and n.hero_name
        }
        remapped = remap_visual_nodes(
            seat_report.visual_nodes,
            self._applied_seat_by_hero,
            hero_name_by_id=names,
        )
        return [n for n in remapped if n.hero_id is not None]

    def _render_report(self, report, *, reset_scroll: bool) -> None:
        self._clear()
        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"

        seat_report = report.seat_report
        formation_name = getattr(seat_report, "formation_name", None) if seat_report else None
        section_title = f"Active formation — {formation_name}" if formation_name else "Active formation"
        if self._applied_seat_by_hero is not None:
            section_title = f"{section_title} (AI-voorstel overgenomen)"
        advisor_section(self._layout, section_title)

        active_nodes = self._active_nodes_for_display(seat_report)

        if not active_nodes:
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
            add_formation_board(
                self._layout,
                active_nodes,
                role_label=role_label,
                intro="Enemies → right (front = toward the right).",
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
            )
        else:
            hidden_reason = (
                getattr(seat_report, "recommended_hidden_reason", None) if seat_report else None
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

        self._render_ai_advice_section(report, role_label=role_label)

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

    def _hero_name(self, report, hero_id: int | None) -> str:
        if hero_id is None:
            return "—"
        for hero in getattr(report, "formation_heroes", ()) or ():
            if hero.hero_id == hero_id:
                return hero.name
        return f"Champion {hero_id}"

    def _permanent_seat(self, champion_id: int) -> int | None:
        try:
            from ic_gamedata.formation_seats import _definition_seat_by_hero

            return _definition_seat_by_hero().get(champion_id)
        except Exception:
            return None

    def _position_meta(self, position_id: int) -> tuple[int | None, str | None]:
        """Return (column, zone) for a physical position_id."""
        report = self._last_report
        seat_report = getattr(report, "seat_report", None) if report else None
        if seat_report is not None:
            for n in seat_report.visual_nodes:
                if n.seat == position_id:
                    col = None
                    try:
                        from ic_gamedata.formation_advisor.topology import (
                            fallback_seat_column,
                            load_formation_topology,
                        )

                        if self._last_payload is not None:
                            topo = load_formation_topology(self._last_payload, None)
                            col = topo.seat_column.get(position_id)
                            if col is None:
                                col = fallback_seat_column(position_id)
                    except Exception:
                        col = None
                    return col, n.zone
        return None, None

    def _position_label(self, position_id: int) -> str:
        from ic_gamedata.formation_ai_advice.labels import position_caption

        col, zone = self._position_meta(position_id)
        return position_caption(position_id=position_id, column=col, zone=zone)

    def _spec_label(self, champion_id: int, option_id: int) -> str:
        """Resolve option name only within that champion's options (no global name lookup)."""
        try:
            from ic_gamedata.specializations import (
                _merge_known_options,
                load_specialization_rules,
            )

            if self._last_payload is None:
                return f"optie {option_id}"
            known = _merge_known_options(
                self._last_payload, load_specialization_rules()
            ).get(champion_id, [])
            for opt in known:
                if opt.upgrade_id == option_id:
                    return opt.name
        except Exception:
            pass
        return f"optie {option_id}"

    def _group_label(self, champion_id: int, group_id: str) -> str:
        from ic_gamedata.formation_ai_advice.labels import specialization_group_label

        try:
            from ic_gamedata.formation_ai_advice.export import _specialization_groups

            if self._last_payload is None:
                return specialization_group_label(group_id=group_id)
            for g in _specialization_groups(self._last_payload, champion_id):
                if str(g.get("group_id")) == group_id:
                    from ic_gamedata.formation_ai_advice.labels import (
                        group_label_from_export_group,
                    )

                    return group_label_from_export_group(g)
        except Exception:
            pass
        return specialization_group_label(group_id=group_id)

    def _current_spec_ids_by_group(self, champion_id: int) -> dict[str, int]:
        """Map group_id → currently selected upgrade_id for this champion only."""
        if self._last_payload is None:
            return {}
        try:
            from ic_gamedata.specializations import (
                _current_choices,
                _merge_known_options,
                load_specialization_rules,
                merged_hero_record_for_specializations,
            )
        except Exception:
            return {}
        rules = load_specialization_rules()
        known = _merge_known_options(self._last_payload, rules).get(champion_id, [])
        if not known:
            return {}
        hero = merged_hero_record_for_specializations(self._last_payload, champion_id) or {}
        selected = set(_current_choices(hero, known))
        out: dict[str, int] = {}
        for opt in known:
            if opt.upgrade_id in selected:
                out[f"tier_{opt.tier_index}"] = opt.upgrade_id
        return out

    def _format_spec_cell(
        self,
        champion_id: int,
        proposed_choices: tuple,
    ) -> tuple[str, bool]:
        """Return (HTML display text, has_spec_change).

        Changed specializations are wrapped in ``<b>`` so only those lines
        stand out in the advice table.
        """
        current = self._current_spec_ids_by_group(champion_id)
        if not proposed_choices:
            if not current:
                return "—", False
            labels = [
                f"{html.escape(self._group_label(champion_id, gid))}: "
                f"{html.escape(self._spec_label(champion_id, oid))}"
                for gid, oid in sorted(current.items())
            ]
            return "huidig: " + ", ".join(labels), False

        parts: list[str] = []
        changed = False
        for choice in proposed_choices:
            gid = choice.group_id
            glabel = html.escape(self._group_label(champion_id, gid))
            proposed_id = choice.option_id
            proposed_name = html.escape(self._spec_label(champion_id, proposed_id))
            cur_id = current.get(gid)
            if cur_id is None:
                parts.append(f"<b>{glabel}: → {proposed_name}</b>")
                changed = True
            elif cur_id == proposed_id:
                parts.append(f"{glabel}: {proposed_name} <span style='opacity:0.7'>(zelfde)</span>")
            else:
                cur_name = html.escape(self._spec_label(champion_id, cur_id))
                parts.append(
                    f"<b>{glabel}: {cur_name} → {proposed_name}</b>"
                )
                changed = True
        return "<br/>".join(parts) or "—", changed

    def _make_spec_cell_widget(self, html_text: str, *, emphasize: bool) -> QLabel:
        label = QLabel(html_text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setMargin(4)
        # Changed specs are <b> inside; cell tint reinforces that action is needed.
        color = ui_theme.WARN if emphasize else ui_theme.TEXT_MUTED
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    @staticmethod
    def _style_table_item(
        item: QTableWidgetItem,
        *,
        muted: bool = False,
        emphasize: bool = False,
    ) -> None:
        if muted:
            item.setForeground(QBrush(QColor(ui_theme.TEXT_MUTED)))
        elif emphasize:
            item.setForeground(QBrush(QColor(ui_theme.WARN)))
            font = QFont(item.font())
            font.setBold(True)
            item.setFont(font)
        else:
            item.setForeground(QBrush(QColor(ui_theme.TEXT_BODY)))

    def _render_ai_advice_section(self, report, *, role_label) -> None:
        result = self._ai_result
        if result is None:
            return
        advisor_section(self._layout, "Formatieadvies — Clipboard / chat")

        provider_card = advisor_card(compact=True)
        provider_lyt = advisor_card_layout(provider_card, compact=True)
        provider_lyt.addWidget(
            advisor_lbl(
                result.provider_label or "Clipboard / chat-voorstel",
                kind="subtitle",
            )
        )
        provider_lyt.addWidget(
            advisor_lbl(
                "Geen API-call — voorstel uit chat, lokaal gevalideerd.",
                kind="muted",
            )
        )
        self._layout.addWidget(provider_card)

        meta_bits = [
            f"status chat: {result.proposal.status if result.proposal else '—'}",
            f"lokaal: {result.local_validation.status}",
        ]
        if result.data_version:
            meta_bits.append(f"data: {result.data_version}")
        if result.requested_at:
            meta_bits.append(f"tijd: {result.requested_at}")

        card = advisor_card(compact=True)
        lyt = advisor_card_layout(card, compact=True)
        lyt.addWidget(advisor_lbl(" · ".join(meta_bits), kind="muted"))
        if result.error:
            lyt.addWidget(advisor_lbl(result.error, kind="body"))
        if result.proposal and result.proposal.summary:
            lyt.addWidget(advisor_lbl(result.proposal.summary, kind="subtitle"))
        self._layout.addWidget(card)

        if result.local_validation.errors:
            err_card = advisor_card(highlight=True)
            err_lyt = advisor_card_layout(err_card)
            err_lyt.addWidget(advisor_lbl("Lokale validatiefouten", kind="subtitle"))
            for err in result.local_validation.errors:
                err_lyt.addWidget(advisor_lbl(f"• {err}", kind="body"))
            self._layout.addWidget(err_card)

        if result.local_validation.unchecked_mechanics:
            uc = advisor_card(compact=True)
            uc_lyt = advisor_card_layout(uc, compact=True)
            uc_lyt.addWidget(advisor_lbl("Niet lokaal gecontroleerd", kind="subtitle"))
            for line in result.local_validation.unchecked_mechanics:
                uc_lyt.addWidget(advisor_lbl(f"• {line}", kind="muted"))
            self._layout.addWidget(uc)

        proposal = result.proposal
        if proposal is None:
            return

        # Advice table
        current_by_seat: dict[int, int] = {}
        current_seat_by_hero: dict[int, int] = {}
        seat_report = report.seat_report
        if seat_report is not None:
            for n in seat_report.visual_nodes:
                if n.hero_id is not None:
                    current_by_seat[n.seat] = n.hero_id
                    current_seat_by_hero[n.hero_id] = n.seat

        legend = advisor_card(compact=True)
        legend_lyt = advisor_card_layout(legend, compact=True)
        legend_lyt.addWidget(
            advisor_lbl(
                "Legenda: Positie = fysieke plaats (kolom/zone) · "
                "Seat = permanente F-seat van de voorgestelde champion · "
                "gedempte tekst = geen verplaatsing · "
                "vet/oranje in Specialisaties = deze keuze moet je aanpassen "
                "(ongewijzigde specs blijven normaal)",
                kind="muted",
            )
        )
        self._layout.addWidget(legend)

        table = QTableWidget(len(proposal.assignments), 7)
        table.setHorizontalHeaderLabels(
            [
                "Positie",
                "Huidig",
                "Voorstel",
                "Seat",
                "Verplaatsing",
                "Specialisaties",
                "Reden",
            ]
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setWordWrap(True)
        from ic_gamedata.formation_ai_advice.labels import champion_seat_caption

        from ic_gamedata.formation_ai_advice.labels import formation_display_sort_key

        # Visual y per seat (top of board = smaller y) for within-column order.
        y_by_seat: dict[int, float] = {}
        if seat_report is not None:
            for n in seat_report.visual_nodes:
                y_by_seat[int(n.seat)] = float(n.y)

        def _assignment_sort_key(a):
            col, _zone = self._position_meta(a.position_id)
            return formation_display_sort_key(
                column_index=col,
                row_order=y_by_seat.get(a.position_id),
                position_id=a.position_id,
            )

        for row, asn in enumerate(sorted(proposal.assignments, key=_assignment_sort_key)):
            cur_id = current_by_seat.get(asn.position_id)
            prev_pos = current_seat_by_hero.get(asn.champion_id)
            stays = prev_pos == asn.position_id
            move_txt = "blijft" if stays else (
                f"van positie {prev_pos}" if prev_pos is not None else "nieuw"
            )
            specs_html, spec_changed = self._format_spec_cell(
                asn.champion_id,
                asn.specialization_choices,
            )
            perm_seat = self._permanent_seat(asn.champion_id)
            values = [
                self._position_label(asn.position_id),
                self._hero_name(report, cur_id),
                self._hero_name(report, asn.champion_id),
                champion_seat_caption(perm_seat),
                move_txt,
                None,  # specializations via rich-text widget
                asn.placement_reason or "—",
            ]
            for col, text in enumerate(values):
                if col == 5:
                    table.setCellWidget(
                        row,
                        col,
                        self._make_spec_cell_widget(
                            specs_html,
                            emphasize=spec_changed,
                        ),
                    )
                    continue
                item = QTableWidgetItem(text or "")
                if stays:
                    self._style_table_item(item, muted=True)
                else:
                    self._style_table_item(item)
                table.setItem(row, col, item)
            # Extra height when multiple spec lines are shown.
            line_count = max(1, specs_html.count("<br/>") + 1)
            table.setRowHeight(row, max(36, 22 * line_count + 12))
        table.resizeColumnsToContents()
        # Spec column needs room for "oud → nieuw" lines.
        table.setColumnWidth(5, max(table.columnWidth(5), 280))
        table.setMinimumHeight(min(360, 48 + 44 * max(1, len(proposal.assignments))))
        self._layout.addWidget(table)

        # Visual preview (no mutation until apply)
        if seat_report is not None and proposal.assignments:
            from ic_gamedata.formation_ai_advice.apply import (
                changed_seats,
                mark_changed_nodes,
                remap_visual_nodes,
            )

            before = {
                int(n.hero_id): int(n.seat)
                for n in seat_report.visual_nodes
                if n.hero_id is not None
            }
            after = {a.champion_id: a.position_id for a in proposal.assignments}
            names = {
                int(n.hero_id): str(n.hero_name)
                for n in seat_report.visual_nodes
                if n.hero_id is not None and n.hero_name
            }
            for a in proposal.assignments:
                names.setdefault(a.champion_id, self._hero_name(report, a.champion_id))
            preview = remap_visual_nodes(
                seat_report.visual_nodes,
                after,
                hero_name_by_id=names,
            )
            preview = mark_changed_nodes(preview, changed_seats(before, after))
            advisor_section(self._layout, "Voorstel-preview (niet toegepast)")

            def _ai_caption(node) -> str:
                return self._position_label(int(node.seat))

            def _ai_subcaption(node) -> str:
                from ic_gamedata.formation_ai_advice.labels import champion_seat_caption

                if node.hero_id is None:
                    return ""
                return champion_seat_caption(self._permanent_seat(int(node.hero_id)))

            add_formation_board(
                self._layout,
                [n for n in preview if n.hero_id is not None],
                role_label=role_label,
                intro=(
                    "Fysieke plaats = kolom/zone (blijft bij de kaart). "
                    "Seat = permanente F-seat van de geplaatste champion."
                ),
                node_caption=_ai_caption,
                node_subcaption=_ai_subcaption,
            )

        if proposal.expected_key_buffs:
            buff_card = advisor_card(compact=True)
            buff_lyt = advisor_card_layout(buff_card, compact=True)
            buff_lyt.addWidget(advisor_lbl("Belangrijkste verwachte DPS-buffs", kind="subtitle"))
            for buff in proposal.expected_key_buffs:
                src = self._hero_name(report, buff.source_champion_id)
                tgt = self._hero_name(report, buff.target_champion_id)
                buff_lyt.addWidget(
                    advisor_lbl(f"• {src} → {tgt}: {buff.explanation}", kind="body")
                )
            self._layout.addWidget(buff_card)

        for title, lines in (
            ("Aannames", proposal.assumptions),
            ("Ontbrekende gegevens", proposal.missing_information),
            ("Waarschuwingen", proposal.warnings + result.local_validation.warnings),
        ):
            if not lines:
                continue
            c = advisor_card(compact=True)
            cl = advisor_card_layout(c, compact=True)
            cl.addWidget(advisor_lbl(title, kind="subtitle"))
            for line in lines:
                cl.addWidget(advisor_lbl(f"• {line}", kind="muted"))
            self._layout.addWidget(c)

        sources = result.sources or (proposal.sources if proposal else ())
        if sources:
            src_card = advisor_card(compact=True)
            src_lyt = advisor_card_layout(src_card, compact=True)
            src_lyt.addWidget(advisor_lbl("Bronnen (API-metadata)", kind="subtitle"))
            for src in sources:
                label = src.title or src.source_id
                link = QLabel(
                    f'<a href="{src.url}">{label}</a>' if src.url else label
                )
                link.setOpenExternalLinks(False)
                link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                if src.url:
                    link.linkActivated.connect(
                        lambda _u, url=src.url: QDesktopServices.openUrl(QUrl(url))
                    )
                src_lyt.addWidget(link)
            self._layout.addWidget(src_card)

        if result.specializations_advice_only:
            note = advisor_card(compact=True)
            note_lyt = advisor_card_layout(note, compact=True)
            note_lyt.addWidget(
                advisor_lbl(
                    "Specialisaties worden alleen als advies opgeslagen; "
                    "de app kan ze niet in de game instellen.",
                    kind="muted",
                )
            )
            self._layout.addWidget(note)

    def _current_formation_fingerprint(self) -> str | None:
        if self._last_payload is None or self._last_report is None:
            return None
        try:
            from ic_gamedata.formation_ai_advice.export import (
                build_export_payload,
                formation_layout_fingerprint_from_export,
            )

            goal_id = self._advice_goal_id() or "push"
            export = build_export_payload(
                self._last_payload,
                tuple(self._last_report.formation_heroes or ()),
                goal=goal_id,
                context=self._controls.context(),
                fixed_main_dps_id=self._fixed_main_dps_id(),
                goal_parameters=self._collect_goal_parameters(),
                manual_restriction_text=self._restriction_edit.text().strip() or None,
            )
            return formation_layout_fingerprint_from_export(export)
        except Exception:
            return None

    def _on_ai_done(self, result: FormationAdviceResult) -> None:
        self._ai_result = result
        live_fp = self._current_formation_fingerprint()
        if (
            live_fp is not None
            and self._ai_request_form_fp is not None
            and live_fp != self._ai_request_form_fp
        ):
            from ic_gamedata.formation_ai_advice.models import LocalValidationResult

            self._ai_result = replace(
                result,
                local_validation=LocalValidationResult(
                    status="stale",
                    errors=(
                        "Formatie of gamegegevens zijn gewijzigd sinds de aanvraag.",
                    ),
                    can_apply=False,
                ),
                error="Advies is verouderd — kopieer opnieuw en plak een nieuw voorstel.",
            )
            result = self._ai_result

        can_apply = bool(
            result.proposal
            and result.local_validation.can_apply
            and result.local_validation.status == "valid"
        )
        if self._apply_advice_btn is not None:
            self._apply_advice_btn.setEnabled(can_apply)
        if result.error:
            self._ai_status.setText(result.error)
        elif can_apply:
            self._ai_status.setText(
                "Chat-voorstel lokaal gevalideerd. Controleer de preview vóór overnemen."
            )
        else:
            self._ai_status.setText(
                f"Voorstel ontvangen (lokaal: {result.local_validation.status}). "
                "Niets toegepast."
            )
        if self._last_report is not None:
            self._render_report(self._last_report, reset_scroll=False)

    def _on_apply_advice(self) -> None:
        result = self._ai_result
        if result is None or result.proposal is None:
            return
        live_fp = self._current_formation_fingerprint()
        if (
            live_fp is not None
            and self._ai_request_form_fp is not None
            and live_fp != self._ai_request_form_fp
        ):
            self._ai_status.setText(
                "Advies is verouderd — overnemen geblokkeerd. Vraag opnieuw aan."
            )
            if self._apply_advice_btn is not None:
                self._apply_advice_btn.setEnabled(False)
            return
        if not result.local_validation.can_apply:
            self._ai_status.setText("Overnemen geblokkeerd: lokale validatie faalde.")
            return

        confirm = QMessageBox.question(
            self,
            "Voorstel overnemen",
            "Dit wijzigt alleen de formatieweergave in de app, niet de game.\n"
            "Specialisaties worden als advies bewaard.\n\nDoorgaan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        seat_report = getattr(self._last_report, "seat_report", None) if self._last_report else None
        if seat_report is None:
            self._ai_status.setText("Geen visuele formatie om over te nemen.")
            return

        from ic_gamedata.formation_ai_advice.apply import apply_proposal

        current_nodes = self._active_nodes_for_display(seat_report)
        state = apply_proposal(
            result.proposal,
            current_nodes=tuple(current_nodes),
            previous_spec_advice=self._applied_spec_advice,
        )
        self._undo_snapshot = state.undo
        self._applied_seat_by_hero = dict(state.seat_by_hero)
        self._applied_spec_advice = dict(state.specialization_advice)
        if self._undo_advice_btn is not None:
            self._undo_advice_btn.setEnabled(True)
        if self._apply_advice_btn is not None:
            self._apply_advice_btn.setEnabled(False)
        self._ai_status.setText(
            "Voorstel overgenomen in de app. " + state.note
        )
        if self._last_report is not None:
            self._render_report(self._last_report, reset_scroll=False)

    def _on_undo_advice(self) -> None:
        snap = self._undo_snapshot
        if snap is None:
            self._applied_seat_by_hero = None
            self._applied_spec_advice = {}
            if self._undo_advice_btn is not None:
                self._undo_advice_btn.setEnabled(False)
            if self._last_report is not None:
                self._render_report(self._last_report, reset_scroll=False)
            return
        self._applied_seat_by_hero = dict(snap.seat_by_hero) if snap.seat_by_hero else None
        # Undo restores pre-apply overlay; if that was empty, clear overlay.
        if not snap.seat_by_hero:
            self._applied_seat_by_hero = None
        # After first apply, undo goes back to live board (clear overlay).
        self._applied_seat_by_hero = None
        self._applied_spec_advice = dict(snap.specialization_advice)
        self._undo_snapshot = None
        if self._undo_advice_btn is not None:
            self._undo_advice_btn.setEnabled(False)
        if (
            self._apply_advice_btn is not None
            and self._ai_result
            and self._ai_result.local_validation.can_apply
        ):
            self._apply_advice_btn.setEnabled(True)
        self._ai_status.setText("Overnemen ongedaan gemaakt.")
        if self._last_report is not None:
            self._render_report(self._last_report, reset_scroll=False)
