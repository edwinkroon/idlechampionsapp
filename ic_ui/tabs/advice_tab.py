"""External AI advice tab: export → chat → paste → before/after preview.

Formation analysis stays on the Formation tab. This tab owns the clipboard
workflow and visual comparison so those controls are not duplicated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QSettings, QMimeData
from PySide6.QtGui import QAction, QClipboard, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ic_ui import theme as ui_theme
from ic_ui.theme import on_theme_changed
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar
from ic_ui.widgets.advisor_widgets import (
    add_formation_board,
    advisor_card,
    advisor_card_layout,
    advisor_lbl,
    advisor_section,
    clear_advisor_layout,
    refresh_advisor_chrome,
)

if TYPE_CHECKING:
    from ic_ui.tabs.formation_tab import FormationTab
    from ic_gamedata.formation_ai_advice.models import FormationAdviceResult


class AdviceTab(QWidget):
    """Export formation advice for an external AI and preview pasted proposals."""

    def __init__(
        self,
        formation_tab: FormationTab,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._formation = formation_tab
        self._settings = QSettings("IdleChampions", "Companion")
        self._goal_params_party_id: int | None = None
        self._pending_fixed_dps: int | None = None
        self._ai_result: FormationAdviceResult | None = None
        self._ai_request_form_fp: str | None = None
        self._clipboard_export: dict | None = None
        self._clipboard_form_fp: str | None = None
        self._build_ui()
        self._formation.formation_updated.connect(self._on_formation_updated)
        on_theme_changed(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        self._refresh_preview(reset_scroll=False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)

        left = QHBoxLayout()
        left.setSpacing(8)
        self._controls = AdvisorGoalContextBar(
            include_formation=False,
            inline_migration_hint=False,
        )
        self._controls.changed.connect(self._on_options_changed)
        left.addWidget(self._controls)

        dps_lbl = QLabel("Hoofd-DPS")
        dps_lbl.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        left.addWidget(dps_lbl)
        self._dps_combo = QComboBox()
        self._dps_combo.setMinimumContentsLength(14)
        self._dps_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._dps_combo.setToolTip(
            "Optioneel. Alleen een gekozen vaste hoofd-DPS wordt gelockt in exports."
        )
        self._dps_combo.currentIndexChanged.connect(self._on_fixed_dps_changed)
        left.addWidget(self._dps_combo)
        top.addLayout(left, stretch=0)
        top.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        self._copy_mode = "json"
        self._copy_mode_labels = {
            "standard": "Kopieer voor chat",
            "json": "Kopieer + JSON",
            "swap": "Zoek betere champions",
            "debug": "Debugexport",
        }
        self._copy_mode_hints = {
            "standard": "Plaatsing + specialisaties van de huidige party.",
            "json": "Zelfde advies plus JSON om terug te plakken.",
            "swap": "Zoekt automatisch betere owned champions (max. 1 wissel).",
            "debug": "Volledige bronexport — niet voor standaard chatadvies.",
        }
        self._copy_chat_btn = QPushButton(self._copy_mode_labels["json"])
        self._copy_chat_btn.setObjectName("compactBtn")
        self._copy_chat_btn.setMinimumWidth(168)
        self._copy_chat_btn.setMaximumWidth(220)
        self._copy_chat_btn.setToolTip(self._copy_mode_hints["json"])
        self._copy_chat_btn.clicked.connect(self._on_copy_chat_primary)
        actions.addWidget(self._copy_chat_btn)

        self._copy_chat_menu_btn = QToolButton()
        self._copy_chat_menu_btn.setText("▾")
        self._copy_chat_menu_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        copy_menu = QMenu(self._copy_chat_menu_btn)
        for mode, label in (
            ("standard", "Standaard (plaatsing + specs)"),
            ("json", "+ JSON (voor Plak)"),
            ("swap", "Zoek betere champions"),
            ("debug", "Debugexport (volledig)"),
        ):
            act = QAction(label, self)
            act.triggered.connect(lambda _c=False, m=mode: self._set_copy_mode(m))
            copy_menu.addAction(act)
            if mode == "swap":
                copy_menu.addSeparator()
        self._copy_chat_menu_btn.setMenu(copy_menu)
        actions.addWidget(self._copy_chat_menu_btn)

        self._paste_btn = QPushButton("Plak")
        self._paste_btn.setObjectName("compactBtn")
        self._paste_btn.setToolTip("Plak JSON-voorstel uit de externe AI.")
        self._paste_btn.clicked.connect(self._on_paste_proposal)
        actions.addWidget(self._paste_btn)

        self._compact_btn = QPushButton("Compact…")
        self._compact_btn.setObjectName("compactBtn")
        self._compact_btn.setToolTip(
            "Basis-snapshot, compacte adviesvraag en championdetails."
        )
        self._compact_btn.clicked.connect(self._on_open_compact_export)
        actions.addWidget(self._compact_btn)
        top.addLayout(actions)
        root.addLayout(top)

        self._goal_help = QLabel("")
        self._goal_help.setWordWrap(True)
        self._goal_help.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(self._goal_help)

        params_row = QHBoxLayout()
        params_row.setSpacing(8)
        self._goal_params_stack = QStackedWidget()
        self._goal_params_stack.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._build_goal_param_pages()
        params_row.addWidget(self._goal_params_stack, stretch=1)
        root.addLayout(params_row)

        self._status = QLabel(
            "Laad een formatie (Formation-tab / Refresh), kopieer voor de AI, "
            "plak het JSON-antwoord hier terug."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll
        body = QWidget()
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(0, 4, 0, 8)
        self._layout.setSpacing(8)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        self._sync_goal_param_visibility()
        self._update_goal_help()
        self._refresh_dps_combo()
        self._refresh_preview(reset_scroll=True)

    # --- formation feed -------------------------------------------------------

    def _on_formation_updated(self) -> None:
        party = self._formation.last_party_id
        if party != self._goal_params_party_id:
            self._load_party_goal_settings(party)
        self._refresh_dps_combo()
        # Stale clipboard when live party changes.
        if self._clipboard_export is not None:
            live_fp = self._current_formation_fingerprint()
            if (
                live_fp is not None
                and self._clipboard_form_fp is not None
                and live_fp != self._clipboard_form_fp
            ):
                self._clipboard_export = None
                self._clipboard_form_fp = None
        self._refresh_preview(reset_scroll=False)

    # --- goal / params (same persistence keys as before) ----------------------

    def _advice_goal_id(self) -> str:
        goal = self._controls.goal_or_none()
        if goal:
            return str(goal)
        if self._controls.needs_goal_confirm():
            return ""
        return "push"

    def _party_settings_prefix(self, party_id: int | None = None) -> str:
        pid = party_id if party_id is not None else self._formation.last_party_id
        if pid is None:
            return "advice/party/_none"
        return f"advice/party/{pid}"

    def _fixed_main_dps_id(self) -> int | None:
        data = self._dps_combo.currentData()
        return data if isinstance(data, int) else None

    def _build_goal_param_pages(self) -> None:
        self._goal_page_index: dict[str, int] = {}

        def _muted(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
            return lbl

        def _page(*widgets: QWidget) -> QWidget:
            wrap = QWidget()
            row = QHBoxLayout(wrap)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            for w in widgets:
                row.addWidget(w)
            row.addStretch(1)
            return wrap

        self._goal_page_index["push"] = self._goal_params_stack.addWidget(_page())

        self._quest_area = QSpinBox()
        self._quest_area.setRange(0, 99999)
        self._quest_area.setSpecialValueText("auto")
        self._quest_area.valueChanged.connect(self._persist_party_goal_settings)
        self._quest_end = QLineEdit()
        self._quest_end.setPlaceholderText("Andere eindvoorwaarde…")
        self._quest_end.setMinimumWidth(180)
        self._quest_end.textChanged.connect(self._persist_party_goal_settings)
        self._quest_source_lbl = _muted("")
        self._goal_page_index["quest_clear"] = self._goal_params_stack.addWidget(
            _page(_muted("Gebied"), self._quest_area, self._quest_end, self._quest_source_lbl)
        )

        self._gem_play_mode = QComboBox()
        for label, value in (
            ("Modus onbekend", "unknown"),
            ("Voorgrond", "foreground"),
            ("Achtergrond", "background"),
            ("Offline", "offline"),
        ):
            self._gem_play_mode.addItem(label, value)
        self._gem_play_mode.currentIndexChanged.connect(self._persist_party_goal_settings)
        self._gem_auto_reset = QComboBox()
        for label, value in (
            ("Reset onbekend", "unknown"),
            ("Auto-reset ja", "yes"),
            ("Auto-reset nee", "no"),
        ):
            self._gem_auto_reset.addItem(label, value)
        self._gem_auto_reset.currentIndexChanged.connect(self._persist_party_goal_settings)
        self._gem_reset_area = QSpinBox()
        self._gem_reset_area.setRange(0, 99999)
        self._gem_reset_area.setSpecialValueText("resetgebied?")
        self._gem_reset_area.valueChanged.connect(self._persist_party_goal_settings)
        self._goal_page_index["gem_farm"] = self._goal_params_stack.addWidget(
            _page(self._gem_play_mode, self._gem_auto_reset, self._gem_reset_area)
        )

        self._gold_horizon = QComboBox()
        for label, value in (
            ("Horizon onbekend", "unknown"),
            ("Meer gold per uur", "per_hour"),
            ("Meer gold per run", "per_run"),
        ):
            self._gold_horizon.addItem(label, value)
        self._gold_horizon.currentIndexChanged.connect(self._persist_party_goal_settings)
        self._goal_page_index["gold_farm"] = self._goal_params_stack.addWidget(
            _page(self._gold_horizon)
        )

        self._favor_horizon = QComboBox()
        for label, value in (
            ("Horizon onbekend", "unknown"),
            ("Meer favor per run", "per_run"),
            ("Meer favor per tijd", "per_time"),
        ):
            self._favor_horizon.addItem(label, value)
        self._favor_horizon.currentIndexChanged.connect(self._persist_party_goal_settings)
        self._favor_campaign_lbl = _muted("Campagne: actueel indien bekend")
        self._goal_page_index["favor_farm"] = self._goal_params_stack.addWidget(
            _page(self._favor_horizon, self._favor_campaign_lbl)
        )

        self._task_description = QLineEdit()
        self._task_description.setPlaceholderText("Taakomschrijving (verplicht)…")
        self._task_description.setMinimumWidth(220)
        self._task_description.textChanged.connect(self._persist_party_goal_settings)
        self._task_target = QLineEdit()
        self._task_target.setPlaceholderText("Doelwaarde")
        self._task_target.setMaximumWidth(110)
        self._task_target.textChanged.connect(self._persist_party_goal_settings)
        self._task_time_limit = QLineEdit()
        self._task_time_limit.setPlaceholderText("Tijdslimiet")
        self._task_time_limit.setMaximumWidth(110)
        self._task_time_limit.textChanged.connect(self._persist_party_goal_settings)
        self._goal_page_index["custom_task"] = self._goal_params_stack.addWidget(
            _page(self._task_description, self._task_target, self._task_time_limit)
        )
        self._goal_page_index[""] = self._goal_params_stack.addWidget(
            _page(_muted("Kies een doel om door te gaan."))
        )

    def _collect_goal_parameters(self) -> dict:
        goal_id = self._advice_goal_id()
        params: dict = {}
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
        elif goal_id == "gold_farm":
            params["time_horizon"] = self._gold_horizon.currentData() or "unknown"
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
        import json

        self._settings.setValue(
            f"{prefix}/goal_parameters",
            json.dumps(self._collect_goal_parameters(), ensure_ascii=False),
        )
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

        gold_hz = self._gold_horizon.findData(params.get("time_horizon") or "unknown")
        self._gold_horizon.blockSignals(True)
        if gold_hz >= 0:
            self._gold_horizon.setCurrentIndex(gold_hz)
        self._gold_horizon.blockSignals(False)

        hz_idx = self._favor_horizon.findData(params.get("time_horizon") or "unknown")
        self._favor_horizon.blockSignals(True)
        if hz_idx >= 0:
            self._favor_horizon.setCurrentIndex(hz_idx)
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

        raw_dps = self._settings.value(f"{prefix}/fixed_main_dps_id", "")
        try:
            self._pending_fixed_dps = int(raw_dps) if str(raw_dps).strip() else None
        except (TypeError, ValueError):
            self._pending_fixed_dps = None
        self._refresh_dps_combo()

    def _sync_goal_param_visibility(self) -> None:
        goal = self._advice_goal_id() if not self._controls.needs_goal_confirm() else ""
        idx = self._goal_page_index.get(goal, self._goal_page_index.get("", 0))
        self._goal_params_stack.setCurrentIndex(idx)

    def _update_goal_help(self) -> None:
        from ic_gamedata.advice_goals import GOAL_DEFINITIONS

        goal = self._controls.goal_or_none()
        if self._controls.needs_goal_confirm():
            self._goal_help.setText(
                self._controls.migration_message()
                or "Bevestig eerst een adviesdoel."
            )
            return
        if not goal:
            self._goal_help.setText("Kies een doel voor de export.")
            return
        meta = GOAL_DEFINITIONS.get(goal)  # type: ignore[arg-type]
        if meta is None:
            self._goal_help.setText("")
            return
        self._goal_help.setText(str(meta.description or meta.label or ""))

    def _refresh_dps_combo(self) -> None:
        report = self._formation.last_report
        heroes = tuple(getattr(report, "formation_heroes", ()) or ()) if report else ()
        current = self._fixed_main_dps_id()
        if self._pending_fixed_dps is not None:
            current = self._pending_fixed_dps
        self._dps_combo.blockSignals(True)
        self._dps_combo.clear()
        self._dps_combo.addItem("Geen vaste", None)
        for h in heroes:
            hid = getattr(h, "hero_id", None)
            name = getattr(h, "name", None) or str(hid)
            if isinstance(hid, int):
                self._dps_combo.addItem(str(name), hid)
        if current is not None:
            idx = self._dps_combo.findData(current)
            if idx >= 0:
                self._dps_combo.setCurrentIndex(idx)
        self._dps_combo.blockSignals(False)
        self._pending_fixed_dps = None

    def _on_fixed_dps_changed(self, *_args) -> None:
        self._persist_party_goal_settings()

    def _on_options_changed(self) -> None:
        self._sync_goal_param_visibility()
        self._update_goal_help()
        self._clipboard_export = None
        self._clipboard_form_fp = None
        self._formation.request_refresh(auto_refresh=True)

    # --- export / paste -------------------------------------------------------

    def _set_copy_mode(self, mode: str) -> None:
        if mode not in self._copy_mode_labels:
            mode = "json"
        self._copy_mode = mode
        self._copy_chat_btn.setText(self._copy_mode_labels[mode])
        self._copy_chat_btn.setToolTip(self._copy_mode_hints[mode])

    def _write_clipboard(self, text: str) -> bool:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        cleaned = text.replace("\x00", "")
        if not cleaned.strip():
            return False
        try:
            clipboard.setText(cleaned, QClipboard.Mode.Clipboard)
            return True
        except Exception:
            try:
                mime = QMimeData()
                mime.setText(cleaned)
                clipboard.setMimeData(mime, QClipboard.Mode.Clipboard)
                return True
            except Exception:
                return False

    def _set_copy_busy(self, busy: bool, *, message: str | None = None) -> None:
        """Show immediate UI feedback while a heavy export runs on the UI thread."""
        self._copy_chat_btn.setEnabled(not busy)
        self._copy_chat_menu_btn.setEnabled(not busy)
        self._paste_btn.setEnabled(not busy)
        self._compact_btn.setEnabled(not busy)
        if busy:
            self._copy_chat_btn.setText("Bezig…")
            if message:
                self._status.setText(message)
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            QApplication.processEvents()
        else:
            self._copy_chat_btn.setText(self._copy_mode_labels[self._copy_mode])
            QApplication.restoreOverrideCursor()

    def _build_advice_export(self) -> dict | None:
        payload = self._formation.last_payload
        report = self._formation.last_report
        if payload is None or report is None:
            self._status.setText(
                "Geen formatiegegevens — open Formation of druk Refresh (F5)."
            )
            return None
        heroes = tuple(report.formation_heroes or ())
        if not heroes:
            self._status.setText("Geen champions in formatie — niets te exporteren.")
            return None
        if self._controls.needs_goal_confirm():
            self._status.setText(
                self._controls.migration_message()
                or "Bevestig eerst het adviesdoel."
            )
            return None
        goal_id = self._advice_goal_id()
        if not goal_id:
            self._status.setText("Kies eerst een gebruikersdoel.")
            return None
        from ic_gamedata.advice_goals import validate_goal_parameters
        from ic_gamedata.formation_ai_advice.export import build_export_payload

        params = self._collect_goal_parameters()
        ok, err = validate_goal_parameters(goal_id, params)
        if not ok:
            self._status.setText(err or "Ongeldige doelparameters.")
            return None
        try:
            return build_export_payload(
                payload,
                heroes,
                goal=goal_id,
                context=self._controls.context(),
                fixed_main_dps_id=self._fixed_main_dps_id(),
                goal_parameters=params,
                manual_restriction_text=None,
            )
        except ValueError as exc:
            self._status.setText(str(exc))
            return None

    def _on_copy_chat_primary(self) -> None:
        mode = self._copy_mode
        if mode == "json":
            self._on_copy_for_chat(True)
        elif mode == "swap":
            self._on_copy_swap_advice()
        elif mode == "debug":
            self._on_copy_debug_export()
        else:
            self._on_copy_for_chat(False)

    def _on_open_compact_export(self) -> None:
        payload = self._formation.last_payload
        report = self._formation.last_report
        if payload is None or report is None:
            self._status.setText("Geen actieve formatie voor compacte export.")
            return
        heroes = tuple(report.formation_heroes or ())
        if not heroes:
            self._status.setText("Geen actieve formatie voor compacte export.")
            return
        if self._controls.needs_goal_confirm():
            self._status.setText(
                self._controls.migration_message()
                or "Bevestig eerst het adviesdoel."
            )
            return
        goal_id = self._advice_goal_id()
        if not goal_id:
            self._status.setText("Kies eerst een gebruikersdoel.")
            return
        from ic_gamedata.advice_goals import validate_goal_parameters
        from ic_gamedata.party_advisor_formation import _owned_heroes
        from ic_ui.widgets.compact_export_dialog import CompactExportDialog

        params = self._collect_goal_parameters()
        ok, err = validate_goal_parameters(goal_id, params)
        if not ok:
            self._status.setText(err or "Ongeldige doelparameters.")
            return
        dialog = CompactExportDialog(
            self,
            payload=payload,
            formation=heroes,
            goal_id=goal_id,
            context=self._controls.context(),
            goal_parameters=params,
            fixed_main_dps_id=self._fixed_main_dps_id(),
            locked_champion_ids=None,
            manual_restriction_text=None,
            write_clipboard=self._write_clipboard,
            owned_rows=_owned_heroes(payload),
        )
        dialog.exec()

    def _on_copy_for_chat(self, with_json: bool = False) -> None:
        label = "Advies + JSON" if with_json else "Advies"
        self._set_copy_busy(
            True,
            message=f"{label} opbouwen… even geduld (kan enkele seconden duren).",
        )
        try:
            export = self._build_advice_export()
            if export is None:
                return
            from ic_gamedata.formation_ai_advice.clipboard_export import (
                format_clipboard_markdown,
            )
            from ic_gamedata.formation_ai_advice.export import (
                formation_layout_fingerprint_from_export,
            )
            from ic_gamedata.formation_ai_advice.validate import preflight_export

            self._status.setText(f"{label}: export controleren…")
            QApplication.processEvents()
            preflight = preflight_export(export)
            readiness = (export.get("readiness") or {}).get("status")
            if readiness == "blocked" or preflight.status == "invalid":
                detail = "; ".join(preflight.errors[:3]) or "geometrie/party onbetrouwbaar"
                self._status.setText(f"Export geblokkeerd — {detail}")
                return

            output_mode = "json" if with_json else "table"
            self._status.setText(f"{label}: tekst opbouwen…")
            QApplication.processEvents()
            text = format_clipboard_markdown(export, output_mode=output_mode)
            if not text.strip():
                self._status.setText("Export leverde lege tekst — niets gekopieerd.")
                return
            self._status.setText(f"{label}: naar klembord…")
            QApplication.processEvents()
            if not self._write_clipboard(text):
                self._status.setText("Klembord schrijven mislukt.")
                return
            self._clipboard_export = export
            self._clipboard_form_fp = formation_layout_fingerprint_from_export(export)
            self._ai_request_form_fp = self._clipboard_form_fp
            restriction_note = ""
            readiness_issues = (export.get("readiness") or {}).get("issues") or []
            conflict = next(
                (
                    i
                    for i in readiness_issues
                    if isinstance(i, dict) and i.get("code") == "restriction_conflict"
                ),
                None,
            )
            if conflict is not None:
                ids = conflict.get("affected_champion_ids") or []
                restriction_note = (
                    f" (restrictieconflict: {len(ids)} champion(s) — "
                    "zichtbaar in export; AI mag legale swaps voorstellen)"
                )
            warn = ""
            if readiness == "ready_with_warnings" and preflight.warnings:
                warn = f" (waarschuwingen: {len(preflight.warnings)})"
            warn = f"{warn}{restriction_note}"
            if output_mode == "table":
                self._status.setText(
                    f"Advies gekopieerd ({len(text):,} tekens). "
                    f"AI moet een Markdown-tabel teruggeven{warn}."
                )
            else:
                self._status.setText(
                    f"Advies + JSON gekopieerd ({len(text):,} tekens). "
                    f"Plak JSON-antwoord hier terug{warn}."
                )
        except Exception as exc:
            self._status.setText(f"Kopiëren mislukt: {exc}")
        finally:
            self._set_copy_busy(False)

    def _on_copy_debug_export(self) -> None:
        self._set_copy_busy(True, message="Debugexport opbouwen…")
        try:
            export = self._build_advice_export()
            if export is None:
                return
            import json

            text = json.dumps(export, ensure_ascii=False, indent=2)
            if not self._write_clipboard(text):
                self._status.setText("Klembord schrijven mislukt.")
                return
            self._status.setText(f"Debugexport gekopieerd ({len(text):,} tekens).")
        except Exception as exc:
            self._status.setText(f"Debugexport mislukt: {exc}")
        finally:
            self._set_copy_busy(False)

    def _on_copy_swap_advice(self) -> None:
        self._set_copy_busy(True, message="Wisseladvies opbouwen… even geduld.")
        try:
            payload = self._formation.last_payload
            report = self._formation.last_report
            if payload is None or report is None:
                self._status.setText("Geen formatie voor wisseladvies.")
                return
            heroes = tuple(report.formation_heroes or ())
            if not heroes:
                self._status.setText("Geen formatie voor wisseladvies.")
                return
            if self._controls.needs_goal_confirm():
                self._status.setText(
                    self._controls.migration_message()
                    or "Bevestig eerst het adviesdoel."
                )
                return
            goal_id = self._advice_goal_id()
            if not goal_id:
                self._status.setText("Kies eerst een gebruikersdoel.")
                return
            from ic_gamedata.advice_goals import validate_goal_parameters
            from ic_gamedata.formation_ai_advice.clipboard_export import (
                format_swap_clipboard_markdown,
            )
            from ic_gamedata.formation_ai_advice.swap_export import (
                build_swap_export_payload,
            )

            params = self._collect_goal_parameters()
            ok, err = validate_goal_parameters(goal_id, params)
            if not ok:
                self._status.setText(err or "Ongeldige doelparameters.")
                return
            export = build_swap_export_payload(
                payload,
                heroes,
                locked_champion_ids=None,
                goal=goal_id,
                context=self._controls.context(),
                fixed_main_dps_id=self._fixed_main_dps_id(),
                goal_parameters=params,
                manual_restriction_text=None,
            )
            text = format_swap_clipboard_markdown(export)
            if not text.strip():
                self._status.setText("Wisseladvies leverde lege tekst.")
                return
            if not self._write_clipboard(text):
                self._status.setText("Klembord schrijven mislukt.")
                return
            self._status.setText(
                f"Wisseladvies gekopieerd ({len(text):,} tekens)."
            )
        except Exception as exc:
            self._status.setText(f"Wisseladvies mislukt: {exc}")
        finally:
            self._set_copy_busy(False)

    def _on_paste_proposal(self) -> None:
        if self._clipboard_export is None:
            export = self._build_advice_export()
            if export is None:
                self._status.setText(
                    "Eerst kopiëren (of formatie laden) vóór plakken."
                )
                return
            self._clipboard_export = export
            from ic_gamedata.formation_ai_advice.export import (
                formation_layout_fingerprint_from_export,
            )

            self._clipboard_form_fp = formation_layout_fingerprint_from_export(export)

        dialog = QDialog(self)
        dialog.setWindowTitle("Plak AI-voorstel (JSON)")
        dialog.resize(640, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Plak hier het JSON-voorstel uit de externe AI "
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

    def _current_formation_fingerprint(self) -> str | None:
        payload = self._formation.last_payload
        report = self._formation.last_report
        if payload is None or report is None:
            return None
        try:
            from ic_gamedata.formation_ai_advice.export import (
                build_export_payload,
                formation_layout_fingerprint_from_export,
            )

            goal_id = self._advice_goal_id() or "push"
            export = build_export_payload(
                payload,
                tuple(report.formation_heroes or ()),
                goal=goal_id,
                context=self._controls.context(),
                fixed_main_dps_id=self._fixed_main_dps_id(),
                goal_parameters=self._collect_goal_parameters(),
                manual_restriction_text=None,
            )
            return formation_layout_fingerprint_from_export(export)
        except Exception:
            return None

    def _on_ai_done(self, result: FormationAdviceResult) -> None:
        from dataclasses import replace
        from ic_gamedata.formation_ai_advice.models import LocalValidationResult

        self._ai_result = result
        live_fp = self._current_formation_fingerprint()
        if (
            live_fp is not None
            and self._ai_request_form_fp is not None
            and live_fp != self._ai_request_form_fp
        ):
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

        if result.error:
            self._status.setText(result.error)
        elif (
            result.proposal
            and result.local_validation.status == "valid"
            and result.local_validation.can_apply
        ):
            self._status.setText(
                "Voorstel lokaal gevalideerd. Vergelijk voor/na hieronder."
            )
        else:
            self._status.setText(
                f"Voorstel ontvangen (lokaal: {result.local_validation.status})."
            )
        self._refresh_preview(reset_scroll=True)

    # --- preview --------------------------------------------------------------

    def _refresh_preview(self, *, reset_scroll: bool) -> None:
        clear_advisor_layout(self._layout)
        report = self._formation.last_report
        if report is None:
            empty = advisor_card(compact=True)
            lyt = advisor_card_layout(empty, compact=True)
            lyt.addWidget(
                advisor_lbl(
                    "Nog geen formatie — open Formation of druk Refresh (F5).",
                    kind="muted",
                )
            )
            self._layout.addWidget(empty)
            self._layout.addStretch(1)
            refresh_advisor_chrome(self)
            return

        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"

        seat_report = report.seat_report
        before_nodes = []
        if seat_report is not None:
            before_nodes = [n for n in seat_report.visual_nodes if n.hero_id is not None]

        result = self._ai_result
        after_nodes = None
        if (
            result is not None
            and result.proposal is not None
            and result.proposal.assignments
            and seat_report is not None
        ):
            from ic_gamedata.formation_ai_advice.apply import (
                changed_seats,
                mark_changed_nodes,
                remap_visual_nodes,
            )

            before_map = {
                int(n.hero_id): int(n.seat)
                for n in seat_report.visual_nodes
                if n.hero_id is not None
            }
            after_map = {
                a.champion_id: a.position_id for a in result.proposal.assignments
            }
            names = {
                int(n.hero_id): str(n.hero_name)
                for n in seat_report.visual_nodes
                if n.hero_id is not None and n.hero_name
            }
            permanent_seats: dict[int, int] = {}
            for a in result.proposal.assignments:
                if a.champion_id not in names:
                    names[a.champion_id] = self._hero_name(report, a.champion_id)
                seat = self._permanent_seat(a.champion_id)
                if seat is not None:
                    permanent_seats[a.champion_id] = seat
            # Live board seats are F-seats while occupied — fill gaps for party champs.
            for n in seat_report.visual_nodes:
                if n.hero_id is not None:
                    permanent_seats.setdefault(int(n.hero_id), int(n.seat))
            position_geometry: dict[int, tuple[float, float, str]] = {}
            payload = self._formation.last_payload
            if payload is not None:
                try:
                    from ic_gamedata.seat_advisor.formation_visual import (
                        build_position_geometry,
                    )

                    position_geometry = build_position_geometry(payload)
                except Exception:
                    position_geometry = {}
            preview = remap_visual_nodes(
                seat_report.visual_nodes,
                after_map,
                hero_name_by_id=names,
                permanent_seat_by_hero=permanent_seats,
                position_geometry=position_geometry,
            )
            after_nodes = mark_changed_nodes(
                preview, changed_seats(before_map, after_map)
            )

        advisor_section(self._layout, "Nu (live)")
        if before_nodes:
            add_formation_board(
                self._layout,
                before_nodes,
                role_label=role_label,
                intro="Huidige formatie uit de game. Vijanden → rechts (front).",
                issue_border_label="aandachtspunt (advisor)",
                legend_lang="nl",
            )
        else:
            card = advisor_card(compact=True)
            advisor_card_layout(card, compact=True).addWidget(
                advisor_lbl("Geen champions in formatie.", kind="muted")
            )
            self._layout.addWidget(card)

        advisor_section(self._layout, "Voorstel (AI)")
        if after_nodes is not None:
            add_formation_board(
                self._layout,
                [n for n in after_nodes if n.hero_id is not None],
                role_label=role_label,
                intro=(
                    "Kaartpositie = fysieke plek uit het voorstel; "
                    "Slot-nummer = permanente F-seat van de champion."
                ),
                issue_border_label="gewijzigd t.o.v. live",
                legend_lang="nl",
            )
        else:
            card = advisor_card(compact=True)
            advisor_card_layout(card, compact=True).addWidget(
                advisor_lbl(
                    "Nog geen voorstel. Kopieer → externe AI → Plak JSON.",
                    kind="muted",
                )
            )
            self._layout.addWidget(card)

        if result is not None:
            self._render_proposal_details(report, result)

        self._layout.addStretch(1)
        refresh_advisor_chrome(self)
        if reset_scroll:
            self._scroll.verticalScrollBar().setValue(0)

    def _hero_name(self, report: Any, hero_id: int | None) -> str:
        if hero_id is None:
            return "—"
        for h in getattr(report, "formation_heroes", ()) or ():
            if getattr(h, "hero_id", None) == hero_id:
                return str(getattr(h, "name", None) or hero_id)
        # Champions newly proposed (e.g. Briv) are often absent from the live party.
        try:
            from ic_gamedata.formation_ai_advice.export import _hero_name_by_id

            name = _hero_name_by_id().get(int(hero_id))
            if name:
                return str(name)
        except Exception:
            pass
        return f"Champion {hero_id}"

    def _permanent_seat(self, champion_id: int) -> int | None:
        try:
            from ic_gamedata.formation_seats import _definition_seat_by_hero

            seat = _definition_seat_by_hero().get(int(champion_id))
            if isinstance(seat, int) and 1 <= seat <= 12:
                return seat
        except Exception:
            pass
        return None

    def _render_proposal_details(
        self, report: Any, result: FormationAdviceResult
    ) -> None:
        meta = advisor_card(compact=True)
        meta_lyt = advisor_card_layout(meta, compact=True)
        bits = [
            f"status chat: {result.proposal.status if result.proposal else '—'}",
            f"lokaal: {result.local_validation.status}",
        ]
        meta_lyt.addWidget(advisor_lbl(" · ".join(bits), kind="muted"))
        if result.proposal and result.proposal.summary:
            meta_lyt.addWidget(advisor_lbl(result.proposal.summary, kind="subtitle"))
        self._layout.addWidget(meta)

        if result.local_validation.errors:
            err = advisor_card(highlight=True)
            err_lyt = advisor_card_layout(err)
            err_lyt.addWidget(advisor_lbl("Lokale validatiefouten", kind="subtitle"))
            for line in result.local_validation.errors:
                err_lyt.addWidget(advisor_lbl(f"• {line}", kind="body"))
            self._layout.addWidget(err)

        proposal = result.proposal
        if proposal is None:
            return

        for title, lines in (
            ("Waarschuwingen", proposal.warnings + result.local_validation.warnings),
            ("Ontbrekende gegevens", proposal.missing_information),
            ("Aannames", proposal.assumptions),
        ):
            if not lines:
                continue
            card = advisor_card(compact=True)
            cl = advisor_card_layout(card, compact=True)
            cl.addWidget(advisor_lbl(title, kind="subtitle"))
            for line in lines:
                cl.addWidget(advisor_lbl(f"• {line}", kind="muted"))
            self._layout.addWidget(card)

        if proposal.assignments:
            seat_report = report.seat_report
            current_by_seat: dict[int, int] = {}
            if seat_report is not None:
                for n in seat_report.visual_nodes:
                    if n.hero_id is not None:
                        current_by_seat[int(n.seat)] = int(n.hero_id)
            lines_card = advisor_card(compact=True)
            lines_lyt = advisor_card_layout(lines_card, compact=True)
            lines_lyt.addWidget(advisor_lbl("Plaatsingen", kind="subtitle"))
            for asn in proposal.assignments:
                cur = current_by_seat.get(asn.position_id)
                cur_name = self._hero_name(report, cur)
                new_name = self._hero_name(report, asn.champion_id)
                if cur == asn.champion_id:
                    txt = f"• Positie {asn.position_id}: {new_name} (blijft)"
                else:
                    txt = (
                        f"• Positie {asn.position_id}: {cur_name} → {new_name}"
                    )
                lines_lyt.addWidget(advisor_lbl(txt, kind="body"))
            self._layout.addWidget(lines_card)
