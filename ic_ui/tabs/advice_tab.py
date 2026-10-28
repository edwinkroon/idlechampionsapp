"""External AI advice tab: inline export → chat → paste → before/after preview.

Owns compact advice export (basis + request), paste/apply, and visual comparison.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QMimeData, QSettings, QTimer
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ic_ui import theme as ui_theme
from ic_ui.theme import apply_button_icon, on_theme_changed, style_primary_button
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar
from ic_ui.widgets.advice_inline_export import AdviceInlineExportBar
from ic_ui.widgets.advisor_widgets import (
    add_formation_board,
    advisor_card,
    advisor_card_layout,
    advisor_lbl,
    advisor_section,
    clear_advisor_layout,
    refresh_advisor_chrome,
)
from ic_ui.widgets.busy_indicator import BusyScope, StatusBusyRow
from ic_ui.ui_action_log import note_ui_action
from ic_ui.workers.callable_job import start_callable_job

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
        self._options_timer = QTimer(self)
        self._options_timer.setSingleShot(True)
        self._options_timer.setInterval(80)
        self._options_timer.timeout.connect(self._apply_options_side_effects)
        self._build_ui()
        self._formation.formation_updated.connect(self._on_formation_updated)
        data = getattr(formation_tab, "_data", None)
        if data is not None and hasattr(data, "snapshot_updated"):
            data.snapshot_updated.connect(self._on_snapshot_party_guard)
        on_theme_changed(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        if hasattr(self, "_dps_combo"):
            from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar

            AdvisorGoalContextBar._apply_combo_readable_palette(self._dps_combo)
        self._refresh_preview(reset_scroll=False)

    def _on_snapshot_party_guard(self, envelope: object) -> None:
        """If the active party changed but Formation has not caught up, nudge it.

        Advies only redraws on ``formation_updated``. A skipped formation
        re-analysis after a party switch left this tab on the previous party.
        """
        payload = getattr(envelope, "payload", None)
        party_id = getattr(envelope, "party_id", None)
        if not isinstance(payload, dict) or not isinstance(party_id, int):
            return
        if self._formation.last_party_id == party_id:
            return
        if getattr(self._formation, "_analysing", False):
            return
        # Clear stale pasted AI for the previous party immediately.
        if (
            self._goal_params_party_id is not None
            and party_id != self._goal_params_party_id
            and (self._ai_result is not None or self._clipboard_export is not None)
        ):
            self._reset_ai_session(party_changed=True)
        fp = getattr(envelope, "advice_fp", None)
        if fp is None:
            try:
                from ic_gamedata.advice_fingerprint import advice_fingerprint

                fp = advice_fingerprint(payload)
            except Exception:
                fp = None
        self._formation.start_analysis(
            payload,
            getattr(envelope, "err", None),
            auto_refresh=True,
            party_changed=True,
            advice_fp=fp,
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # Row 1: selectors only (full width — same readability as Coach).
        selectors = QHBoxLayout()
        selectors.setSpacing(8)
        self._controls = AdvisorGoalContextBar(
            include_formation=False,
            inline_migration_hint=False,
        )
        self._controls.changed.connect(self._on_options_changed)
        selectors.addWidget(self._controls, stretch=1)

        dps_lbl = QLabel("Hoofd-DPS")
        dps_lbl.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        selectors.addWidget(dps_lbl)
        self._dps_combo = QComboBox()
        self._dps_combo.setMinimumContentsLength(14)
        self._dps_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._dps_combo.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        AdvisorGoalContextBar._apply_combo_readable_palette(self._dps_combo)
        self._dps_combo.setToolTip(
            "Optioneel. Alleen een gekozen vaste hoofd-DPS wordt gelockt in exports."
        )
        self._dps_combo.currentIndexChanged.connect(self._on_fixed_dps_changed)
        selectors.addWidget(self._dps_combo)
        root.addLayout(selectors)

        # Row 2: export actions under the selects so they never squeeze the combos.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._advice_btn = QPushButton("Kopieer partijsetup")
        style_primary_button(self._advice_btn)
        apply_button_icon(self._advice_btn, "copy")
        self._advice_btn.setToolTip(
            "Kopieert je huidige partij en instellingen (plaatsing, "
            "specialisaties, doel/restricties; optioneel wisselruimte) "
            "als AI-vraag naar het klembord (max 17.000 UTF-8-bytes)."
        )
        self._advice_btn.clicked.connect(self._on_copy_advice)
        actions.addWidget(self._advice_btn)

        self._buffs_btn = QPushButton("Kopieer DPS-buffs")
        apply_button_icon(self._buffs_btn, "copy")
        self._buffs_btn.setToolTip(
            "Kopieert de inkomende formation-buffs die de geselecteerde "
            "hoofd-DPS raken (plus eigen buffs) naar het klembord. "
            "Kies eerst een hoofd-DPS."
        )
        self._buffs_btn.clicked.connect(self._on_copy_dps_buffs)
        actions.addWidget(self._buffs_btn)

        self._paste_btn = QPushButton("Plak")
        apply_button_icon(self._paste_btn, "check")
        self._paste_btn.setToolTip("Plak JSON-voorstel uit de externe AI.")
        self._paste_btn.clicked.connect(self._on_paste_proposal)
        actions.addWidget(self._paste_btn)
        actions.addStretch(1)
        root.addLayout(actions)

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

        self._status = StatusBusyRow()
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        self._status.setVisible(False)
        self._action_busy = BusyScope(
            buttons=(self._advice_btn, self._buffs_btn, self._paste_btn),
            status=self._status,
            busy_texts={
                self._advice_btn: "Bezig…",
                self._buffs_btn: "Bezig…",
            },
        )
        self._analysis_busy = False

        self._export_bar = AdviceInlineExportBar(
            self,
            write_clipboard=self._write_clipboard,
            live_source=self._live_payload_and_formation,
            goal_context=self._export_goal_context,
            refresh_live=self._refresh_live_for_export,
            confirm_eligibility=self._confirm_eligibility_conflicts,
        )
        self._export_bar.request_copied.connect(self._stash_paste_baseline)
        self._export_bar.status_message.connect(self._on_export_status)
        self._export_bar.busy_changed.connect(self._on_export_bar_busy)
        root.addWidget(self._export_bar)
        root.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll
        body = QWidget()
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(4, 8, 4, 12)
        self._layout.setSpacing(10)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        self._sync_goal_param_visibility()
        self._update_goal_help()
        self._refresh_dps_combo()
        self._refresh_preview(reset_scroll=True)

    # --- formation feed -------------------------------------------------------

    def _on_formation_updated(self) -> None:
        party = self._formation.last_party_id
        party_changed = party != self._goal_params_party_id
        scope_now = self._party_settings_prefix(party)
        scope_changed = scope_now != getattr(self, "_goal_params_scope_key", None)
        if party_changed:
            # Other party → drop pasted AI proposal + export baseline so the
            # preview never keeps showing the previous party's advice.
            self._reset_ai_session(party_changed=True)
            self._load_party_goal_settings(party)
        elif scope_changed:
            # Same party, different adventure/patron — reload scoped goal params.
            self._load_party_goal_settings(party)
        self._refresh_dps_combo()
        # Same party, but formation/loadout fingerprint moved → stale clipboard.
        if not party_changed and self._clipboard_export is not None:
            live_fp = self._current_formation_fingerprint()
            if (
                live_fp is not None
                and self._clipboard_form_fp is not None
                and live_fp != self._clipboard_form_fp
            ):
                self._clipboard_export = None
                self._clipboard_form_fp = None
                if self._ai_result is not None:
                    self._reset_ai_session(party_changed=False)
        self._export_bar.refresh_freshness()
        self._set_analysis_busy(False)
        self._refresh_preview(reset_scroll=party_changed)

    def _reset_ai_session(self, *, party_changed: bool) -> None:
        """Clear pasted AI proposal and export baseline used for Plak/validatie."""
        had_ai = self._ai_result is not None
        self._ai_result = None
        self._ai_request_form_fp = None
        self._clipboard_export = None
        self._clipboard_form_fp = None
        if party_changed and had_ai:
            self._set_status(
                "Andere party — vorig AI-advies gewist. Kopieer opnieuw indien nodig."
            )
        elif party_changed:
            self._set_status("")
        elif had_ai:
            self._set_status(
                "Formatie gewijzigd — vorig AI-advies gewist. Kopieer opnieuw."
            )

    def _export_goal_context(
        self,
    ) -> tuple[str, str, dict[str, Any], int | None]:
        return (
            self._advice_goal_id(),
            self._controls.context(),
            self._collect_goal_parameters(),
            self._fixed_main_dps_id(),
        )

    def _set_status(self, message: str) -> None:
        text = (message or "").strip()
        self._status.setText(text)
        show = bool(text) or self._status.spinner.is_spinning or self._action_busy.active
        self._status.setVisible(show)

    def _on_export_status(self, message: str) -> None:
        self._set_status(message)

    def _on_export_bar_busy(self, busy: bool) -> None:
        """Mirror export-bar jobs onto the shared Advies action BusyScope."""
        if busy:
            if not self._action_busy.active:
                self._action_busy.begin()
            self._set_status(self._status.text() or "Bezig…")
            return
        if self._action_busy.active and not self._analysis_busy:
            self._action_busy.end()
        self._set_status(self._status.text())

    def _set_analysis_busy(self, busy: bool) -> None:
        self._analysis_busy = busy
        if busy:
            self._status.set_busy(True, message="Formatie bijwerken…")
            self._status.setVisible(True)
        else:
            self._status.set_busy(False)
            if not (self._status.text() or "").strip() and not self._action_busy.active:
                self._status.setVisible(False)

    # --- goal / params (same persistence keys as before) ----------------------

    def _advice_goal_id(self) -> str:
        goal = self._controls.goal_or_none()
        if goal:
            return str(goal)
        if self._controls.needs_goal_confirm():
            return ""
        return "push"

    def _live_context_ids(self) -> tuple[int | None, int | None, int | None]:
        """party_id, adventure_id, patron_id from the current payload."""
        payload = self._formation.last_payload
        party_id = self._formation.last_party_id
        adventure_id = None
        patron_id = None
        if isinstance(payload, dict):
            try:
                from ic_gamedata.advice_fingerprint import party_id_from_payload
                from ic_gamedata.party_advisor_formation import _active_game_instance

                if party_id is None:
                    party_id = party_id_from_payload(payload)
                inst = _active_game_instance(payload) or {}
                if isinstance(inst, dict):
                    adventure_id = inst.get("current_adventure_id")
                    patron_id = inst.get("current_patron_id")
                    try:
                        adventure_id = (
                            int(adventure_id) if adventure_id is not None else None
                        )
                    except (TypeError, ValueError):
                        adventure_id = None
                    try:
                        patron_id = int(patron_id) if patron_id is not None else None
                    except (TypeError, ValueError):
                        patron_id = None
            except Exception:
                pass
        return party_id, adventure_id, patron_id

    def _party_settings_prefix(self, party_id: int | None = None) -> str:
        """Scope goal params by party + adventure + patron to prevent leaks."""
        pid = party_id if party_id is not None else self._formation.last_party_id
        _party, adventure_id, patron_id = self._live_context_ids()
        if party_id is not None:
            # Caller fixed party; still attach live adventure/patron when known.
            pass
        if pid is None:
            base = "advice/party/_none"
        else:
            base = f"advice/party/{pid}"
        adv = adventure_id if adventure_id is not None else "na"
        pat = patron_id if patron_id is not None else "np"
        return f"{base}/a{adv}/p{pat}"

    def _refresh_live_for_export(
        self,
        on_success: object,
        on_error: object,
    ) -> None:
        data = getattr(self._formation, "_data", None)
        if data is None or not hasattr(data, "refresh_snapshot_once"):
            # No service — proceed with whatever live_source already has.
            if callable(on_success):
                on_success()  # type: ignore[operator]
            return

        def _ok(_envelope: object) -> None:
            # FormationTab will update from snapshot_updated; give it a tick.
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, on_success)  # type: ignore[arg-type]

        data.refresh_snapshot_once(
            on_success=_ok,
            on_error=on_error,
            reason="advice_copy",
            force_consumers=frozenset({"advice", "formation"}),
        )

    def _confirm_eligibility_conflicts(
        self, conflicts: list[dict],
    ) -> list[int] | None:
        """Ask the user to confirm seated-but-denied champions for this scope.

        Returns confirmed champion ids (and persists corrections), or None/[] when
        the user declines. Never treats bare presence as allow.
        """
        from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QVBoxLayout

        from ic_gamedata.formation_ai_advice.eligibility_corrections import (
            make_user_confirmation,
            upsert_correction,
        )

        unresolved = [
            c
            for c in conflicts
            if isinstance(c, dict)
            and c.get("status") == "unresolved"
            and isinstance(c.get("champion_id"), int)
        ]
        if not unresolved:
            return None

        party_id, adventure_id, patron_id = self._live_context_ids()
        dialog = QDialog(self)
        dialog.setWindowTitle("Eligibility bevestigen")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Deze champions staan in de formatie maar falen de statische "
                "eligibility-check. Bevestig alleen als ze in-game in deze "
                "adventure/patron-context echt bruikbaar zijn.\n"
                "Dit is een gebruikersbevestiging, geen API-verificatie."
            )
        )
        boxes: list[tuple[QCheckBox, dict]] = []
        for row in unresolved:
            hid = int(row["champion_id"])
            reason = str(row.get("base_reason") or row.get("note") or "denied")
            box = QCheckBox(f"Champion {hid}: bevestig bruikbaar — {reason}")
            layout.addWidget(box)
            boxes.append((box, row))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        confirmed: list[int] = []
        for box, row in boxes:
            if not box.isChecked():
                continue
            hid = int(row["champion_id"])
            corr = make_user_confirmation(
                champion_id=hid,
                party_id=party_id,
                adventure_id=adventure_id,
                patron_id=patron_id,
                base_status="denied",
                base_reason=str(row.get("base_reason") or "") or None,
                note="confirmed_via_advice_export_dialog",
            )
            upsert_correction(corr)
            confirmed.append(hid)
        return confirmed

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
        self._quest_area.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        self._quest_area.setMinimumWidth(88)
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
        self._gem_reset_area.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        self._gem_reset_area.setMinimumWidth(100)
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

        goal_id = self._advice_goal_id()
        if goal_id:
            self._settings.setValue(f"{prefix}/goal_id", goal_id)
        self._settings.setValue(
            f"{prefix}/goal_parameters",
            json.dumps(self._collect_goal_parameters(), ensure_ascii=False),
        )
        self._clipboard_export = None
        self._clipboard_form_fp = None

    def _load_party_goal_settings(self, party_id: int | None) -> None:
        # Always reload when party OR adventure/patron scope changes.
        prefix = self._party_settings_prefix(party_id)
        scope_key = prefix
        if (
            party_id == self._goal_params_party_id
            and party_id is not None
            and getattr(self, "_goal_params_scope_key", None) == scope_key
        ):
            return
        self._goal_params_party_id = party_id
        self._goal_params_scope_key = scope_key
        import json

        from ic_gamedata.advice_goals import is_user_goal_id

        stored_goal = self._settings.value(f"{prefix}/goal_id", None)
        if stored_goal is not None and is_user_goal_id(str(stored_goal)):
            try:
                self._controls.set_goal_context(str(stored_goal))
            except Exception:
                pass
        elif stored_goal is None:
            # New party/adventure/patron scope — do not silently reuse another
            # context's goal; user must (re)confirm via the shared selector.
            self._set_status(
                "Nieuwe adventure/patron-context — controleer het adviesdoel."
            )

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
        goal = self._controls.goal_or_none() or "(onbevestigd)"
        note_ui_action(
            f"Advies: doel/context → {goal} / {self._controls.context()}"
        )
        self._sync_goal_param_visibility()
        self._update_goal_help()
        self._clipboard_export = None
        self._clipboard_form_fp = None
        # Defer heavy work so the combo popup closes without freezing the UI.
        self._options_timer.start()

    def _apply_options_side_effects(self) -> None:
        """Re-analyze from cache + refresh freshness (no force API poll)."""
        self._export_bar.refresh_freshness()
        data = getattr(self._formation, "_data", None)
        payload = getattr(data, "last_payload", None) if data is not None else None
        if payload is None:
            payload = getattr(self._formation, "_last_payload", None)
        if not isinstance(payload, dict):
            return
        fp = None
        try:
            from ic_gamedata.advice_fingerprint import advice_fingerprint

            fp = advice_fingerprint(payload)
        except Exception:
            fp = None
        self._set_analysis_busy(True)
        self._formation.start_analysis(
            payload, None, auto_refresh=True, advice_fp=fp
        )

    # --- export / paste -------------------------------------------------------

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
        """Busy feedback for Advies action buttons (UI stays responsive)."""
        if busy:
            if not self._action_busy.active:
                self._action_busy.begin(message)
            self._export_bar.set_controls_enabled(False)
            self._set_status(message or self._status.text())
            return
        self._export_bar.set_controls_enabled(True)
        if self._action_busy.active:
            self._action_busy.end(message=message)
        apply_button_icon(self._advice_btn, "copy")
        apply_button_icon(self._buffs_btn, "copy")
        self._set_status(message if message is not None else self._status.text())

    def _live_payload_and_formation(self) -> tuple[dict | None, tuple]:
        """Always re-parse the live board from the current payload."""
        from ic_gamedata.party_advisor_formation import resolve_live_formation

        payload = self._formation.last_payload
        report = self._formation.last_report
        fallback = tuple(getattr(report, "formation_heroes", ()) or ()) if report else ()
        heroes = resolve_live_formation(payload, fallback=fallback)
        return payload, heroes

    def _on_copy_advice(self) -> None:
        if self._controls.needs_goal_confirm():
            self._set_status(
                self._controls.migration_message()
                or "Bevestig eerst het adviesdoel."
            )
            return
        from ic_gamedata.advice_goals import validate_goal_parameters

        goal_id = self._advice_goal_id()
        if not goal_id:
            self._set_status("Kies eerst een gebruikersdoel.")
            return
        params = self._collect_goal_parameters()
        ok, err = validate_goal_parameters(goal_id, params)
        if not ok:
            self._set_status(err or "Ongeldige doelparameters.")
            return
        note_ui_action("Advies: Kopieer partijsetup")
        # Busy is driven by export_bar.busy_changed while the worker runs.
        self._export_bar.start_copy_advice_request()

    def _on_copy_dps_buffs(self) -> None:
        if self._action_busy.active:
            return
        note_ui_action("Advies: Kopieer DPS-buffs")
        dps_id = self._fixed_main_dps_id()
        if dps_id is None:
            self._set_status("Kies eerst een hoofd-DPS om inkomende buffs te kopiëren.")
            return
        payload, heroes = self._live_payload_and_formation()
        if payload is None:
            self._set_status("Geen formatiegegevens — druk Refresh (F5).")
            return
        if not heroes:
            self._set_status("Geen champions in formatie — niets te kopiëren.")
            return
        if not any(getattr(h, "hero_id", None) == dps_id for h in heroes):
            self._set_status(
                "De gekozen hoofd-DPS staat niet in de huidige formatie."
            )
            return
        goal_id = self._advice_goal_id() or "push"
        context = self._controls.context()
        self._set_copy_busy(True, message="Inkomende DPS-buffs opbouwen…")

        def work() -> dict:
            from ic_gamedata.formation_ai_advice.incoming_buffs import (
                collect_incoming_buffs,
                format_incoming_buffs_clipboard,
            )

            report = collect_incoming_buffs(
                payload,
                heroes,
                main_dps_id=dps_id,
                goal=goal_id,
                context=context,
            )
            text = format_incoming_buffs_clipboard(report)
            return {"report": report, "text": text}

        def on_done(result: object) -> None:
            if not isinstance(result, dict):
                self._set_copy_busy(False)
                return
            report = result.get("report") or {}
            text = str(result.get("text") or "")
            if not report.get("ok"):
                self._set_copy_busy(False, message=text)
                return
            if not self._write_clipboard(text):
                self._set_copy_busy(False, message="Kopiëren naar klembord mislukt.")
                return
            n_in = len(report.get("incoming") or [])
            n_own = len(report.get("own") or [])
            n_unk = len(report.get("uncertain") or [])
            self._set_copy_busy(
                False,
                message=(
                    f"DPS-buffs gekopieerd voor {report.get('main_dps_name')}: "
                    f"{n_in} inkomend, {n_own} eigen, {n_unk} onzeker."
                ),
            )

        def on_error(message: str) -> None:
            self._set_copy_busy(False, message=f"DPS-buffs mislukt: {message}")

        start_callable_job(
            work,
            on_done=on_done,
            on_error=on_error,
            signals_parent=self,
        )

    def _export_build_kwargs(self) -> dict[str, Any] | None:
        """Collect args for ``build_export_payload`` or None with status set."""
        payload, heroes = self._live_payload_and_formation()
        if payload is None:
            self._set_status("Geen formatiegegevens — druk Refresh (F5).")
            return None
        if not heroes:
            self._set_status("Geen champions in formatie — niets te exporteren.")
            return None
        if self._controls.needs_goal_confirm():
            self._set_status(
                self._controls.migration_message()
                or "Bevestig eerst het adviesdoel."
            )
            return None
        goal_id = self._advice_goal_id()
        if not goal_id:
            self._set_status("Kies eerst een gebruikersdoel.")
            return None
        from ic_gamedata.advice_goals import validate_goal_parameters

        params = self._collect_goal_parameters()
        ok, err = validate_goal_parameters(goal_id, params)
        if not ok:
            self._set_status(err or "Ongeldige doelparameters.")
            return None
        # ``build_export_payload`` takes ``formation=`` (FormationHero tuple),
        # not ``heroes=`` — a rename leftover caused Baseline mislukt TypeError.
        return {
            "payload": payload,
            "formation": heroes,
            "goal": goal_id,
            "context": self._controls.context(),
            "fixed_main_dps_id": self._fixed_main_dps_id(),
            "goal_parameters": params,
            "manual_restriction_text": None,
        }

    def _build_advice_export(self) -> dict | None:
        """Sync helper for light call sites; prefer async for click handlers."""
        kwargs = self._export_build_kwargs()
        if kwargs is None:
            return None
        from ic_gamedata.formation_ai_advice.export import build_export_payload

        try:
            return build_export_payload(**kwargs)
        except ValueError as exc:
            self._set_status(str(exc))
            return None

    def _stash_paste_baseline(self) -> None:
        """Keep a formation baseline so Plak can validate AI replies (background)."""
        kwargs = self._export_build_kwargs()
        if kwargs is None:
            return

        def work() -> dict | None:
            from ic_gamedata.formation_ai_advice.export import build_export_payload

            return build_export_payload(**kwargs)

        def on_done(export: object) -> None:
            if not isinstance(export, dict):
                return
            from ic_gamedata.formation_ai_advice.export import (
                formation_layout_fingerprint_from_export,
            )

            self._clipboard_export = export
            self._clipboard_form_fp = formation_layout_fingerprint_from_export(export)
            self._ai_request_form_fp = self._clipboard_form_fp

        start_callable_job(
            work,
            on_done=on_done,
            on_error=lambda msg: self._set_status(f"Baseline mislukt: {msg}"),
            signals_parent=self,
        )

    def _on_paste_proposal(self) -> None:
        note_ui_action("Advies: Plak AI-voorstel")
        if self._clipboard_export is None:
            kwargs = self._export_build_kwargs()
            if kwargs is None:
                self._set_status(
                    "Eerst kopiëren (of formatie laden) vóór plakken."
                )
                return
            self._set_copy_busy(True, message="Baseline opbouwen…")

            def work() -> dict:
                from ic_gamedata.formation_ai_advice.export import build_export_payload

                return build_export_payload(**kwargs)

            def on_done(export: object) -> None:
                self._set_copy_busy(False)
                if not isinstance(export, dict):
                    self._set_status(
                        "Eerst kopiëren (of formatie laden) vóór plakken."
                    )
                    return
                from ic_gamedata.formation_ai_advice.export import (
                    formation_layout_fingerprint_from_export,
                )

                self._clipboard_export = export
                self._clipboard_form_fp = formation_layout_fingerprint_from_export(
                    export
                )
                self._run_paste_dialog()

            def on_error(message: str) -> None:
                self._set_copy_busy(False, message=f"Baseline mislukt: {message}")

            start_callable_job(
                work,
                on_done=on_done,
                on_error=on_error,
                signals_parent=self,
            )
            return
        self._run_paste_dialog()

    def _run_paste_dialog(self) -> None:
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
            self._set_status(result.error)
        elif (
            result.proposal
            and result.local_validation.status == "valid"
            and result.local_validation.can_apply
        ):
            self._set_status(
                "Voorstel lokaal gevalideerd. Vergelijk voor/na hieronder."
            )
        else:
            self._set_status(
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

        # Same slot_states source as exporter / import validation.
        slot_overlay: list = []
        position_geometry: dict[int, tuple[float, float, str]] = {}
        payload = self._formation.last_payload
        if payload is not None:
            try:
                from ic_gamedata.seat_advisor.formation_visual import (
                    build_position_geometry,
                    build_slot_overlay_nodes,
                )

                position_geometry = build_position_geometry(payload)
            except Exception:
                position_geometry = {}
            try:
                slot_overlay = list(
                    self._slot_overlay_nodes(payload, position_geometry)
                )
            except Exception:
                slot_overlay = []

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
            # BUD highlight must follow the export/proposal hoofd-DPS, not whoever
            # was marked BUD on the live board (roles still follow the champion).
            bud_id = result.main_dps_id
            if not isinstance(bud_id, int):
                bud_id = self._fixed_main_dps_id()
            preview = remap_visual_nodes(
                seat_report.visual_nodes,
                after_map,
                hero_name_by_id=names,
                permanent_seat_by_hero=permanent_seats,
                position_geometry=position_geometry,
                bud_hero_id=bud_id if isinstance(bud_id, int) else None,
            )
            after_nodes = mark_changed_nodes(
                preview, changed_seats(before_map, after_map)
            )

        live_board = list(before_nodes) + list(slot_overlay)
        advisor_section(self._layout, "Nu (live)")
        if live_board:
            add_formation_board(
                self._layout,
                live_board,
                role_label=role_label,
                intro=(
                    "Vijanden → rechts (front). "
                    "Gestippeld = NPC/escort/geblokkeerd of onbekende plaatsbaarheid "
                    "(geen vrije championplek)."
                ),
                issue_border_label="Aandacht",
                legend_lang="nl",
            )
        else:
            card = advisor_card(compact=True)
            advisor_card_layout(card, compact=True).addWidget(
                advisor_lbl("Geen champions in formatie.", kind="muted")
            )
            self._layout.addWidget(card)

        # Only show the AI proposal block once there is something to compare.
        if after_nodes is not None:
            advisor_section(self._layout, "Voorstel (AI)")
            proposed = [n for n in after_nodes if n.hero_id is not None]
            add_formation_board(
                self._layout,
                list(proposed) + list(slot_overlay),
                role_label=role_label,
                intro=(
                    "Rood = gewijzigd t.o.v. live. "
                    "Gestippeld = NPC/escort/blokkade (niet plaatsbaar)."
                ),
                issue_border_label="Gewijzigd",
                legend_lang="nl",
            )

        if result is not None:
            self._render_proposal_details(report, result)

        self._layout.addStretch(1)
        refresh_advisor_chrome(self)
        if reset_scroll:
            self._scroll.verticalScrollBar().setValue(0)

    def _slot_overlay_nodes(
        self,
        payload: dict,
        position_geometry: dict[int, tuple[float, float, str]],
    ) -> tuple:
        """Blocked/unknown markers from the same slot_states as the exporter."""
        from ic_gamedata.formation_ai_advice.export import build_export_payload
        from ic_gamedata.seat_advisor.formation_visual import build_slot_overlay_nodes

        report = self._formation.last_report
        heroes = tuple(getattr(report, "formation_heroes", ()) or ())
        if not heroes:
            return ()
        goal_id = self._advice_goal_id() or "push"
        export = build_export_payload(
            payload,
            heroes,
            goal=goal_id,
            context=self._controls.context(),
            fixed_main_dps_id=self._fixed_main_dps_id(),
            goal_parameters=self._collect_goal_parameters(),
            manual_restriction_text=None,
        )
        formation = export.get("formation") if isinstance(export, dict) else {}
        slot_states = (
            formation.get("slot_states") if isinstance(formation, dict) else None
        )
        champion_seats: set[int] = set()
        seat_report = getattr(report, "seat_report", None) if report is not None else None
        if seat_report is not None:
            champion_seats = {
                int(n.seat)
                for n in seat_report.visual_nodes
                if n.hero_id is not None
            }
        return build_slot_overlay_nodes(
            slot_states,
            position_geometry,
            skip_position_ids=champion_seats,
        )

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
