"""Dialog for BASE_SNAPSHOT / ADVICE_REQUEST / CHAMPION_DETAILS compact export."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ic_gamedata.formation_ai_advice.compact_clipboard import (
    InstructionMode,
    advice_request_section_breakdown,
    build_advice_request_clipboard_text,
    build_base_snapshot_clipboard_text,
    build_champion_details_clipboard_text,
    build_project_instructions_clipboard_text,
    evaluate_clipboard_budget,
    split_champion_details_for_budget,
    try_loss_free_shrink,
)
from ic_gamedata.formation_ai_advice.export_budget import (
    DEFAULT_CHAR_BUDGET,
    clamp_char_budget,
    count_chars,
)
from ic_gamedata.formation_ai_advice.export_validation import (
    ExportValidationResult,
    mark_request_unvalidated,
    mark_request_validated,
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
    build_champion_details,
    minify_json,
)
from ic_gamedata.formation_ai_advice.snapshot_freshness import (
    USER_HELP_NL,
    SnapshotFreshnessStatus,
    assess_snapshot_freshness,
)
from ic_gamedata.formation_ai_advice.snapshot_store import (
    get_exported_snapshot_meta,
    load_snapshot_registry,
    save_snapshot_to_path,
    set_user_declared_shared,
)
from ic_ui import theme as ui_theme

_SETTINGS_ORG = "IdleChampions"
_SETTINGS_APP = "Companion"
_BUDGET_KEY = "advice/export_char_budget"
_MODE_KEY = "advice/export_instruction_mode"


class CompactExportDialog(QDialog):
    """User-driven compact export with budget counter (no silent truncation)."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        payload: dict[str, Any],
        formation: tuple,
        goal_id: str,
        context: str,
        goal_parameters: dict[str, Any] | None,
        fixed_main_dps_id: int | None,
        locked_champion_ids: list[int] | None,
        manual_restriction_text: str | None,
        write_clipboard: Callable[[str], bool],
        owned_rows: list[tuple[int, str, tuple, tuple]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compacte export")
        self.resize(720, 520)
        self._payload = payload
        self._formation = formation
        self._goal_id = goal_id
        self._context = context
        self._goal_parameters = goal_parameters or {}
        self._fixed_main_dps_id = fixed_main_dps_id
        self._locked_champion_ids = locked_champion_ids
        self._manual_restriction_text = manual_restriction_text
        self._write_clipboard = write_clipboard
        self._owned_rows = list(owned_rows)
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._current_snapshot: dict[str, Any] | None = None
        self._current_snapshot_exported = False
        self._last_request: dict[str, Any] | None = None
        self._last_validation: ExportValidationResult | None = None
        self._export_text = ""
        self._details_parts: list[str] = []
        self._allow_unvalidated_copy = False

        root = QVBoxLayout(self)
        root.setSpacing(8)

        intro = QLabel(
            "Compacte exports: basisbestand eenmalig delen, daarna korte "
            "adviesvragen. De app controleert niet of de AI het basisbestand "
            "heeft ontvangen of nog beschikbaar heeft."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(intro)

        self._freshness_label = QLabel("")
        self._freshness_label.setWordWrap(True)
        root.addWidget(self._freshness_label)

        budget_row = QHBoxLayout()
        budget_row.addWidget(QLabel("Kopieerbudget (tekens)"))
        self._budget_spin = QSpinBox()
        self._budget_spin.setRange(2_000, 500_000)
        self._budget_spin.setSingleStep(500)
        self._budget_spin.setValue(
            clamp_char_budget(
                self._settings.value(_BUDGET_KEY, DEFAULT_CHAR_BUDGET)
            )
        )
        self._budget_spin.setToolTip(
            "Maximum voor alles wat gekopieerd wordt (instructies + JSON). "
            "Dit is jouw praktische budget, geen externe productlimiet."
        )
        self._budget_spin.valueChanged.connect(self._on_budget_changed)
        budget_row.addWidget(self._budget_spin)
        budget_row.addStretch(1)
        root.addLayout(budget_row)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_snapshot_tab(), "1. Basisgegevens")
        self._tabs.addTab(self._build_request_tab(), "2. Adviesvraag")
        self._tabs.addTab(self._build_details_tab(), "3. Championdetails")
        self._tabs.addTab(self._build_project_tab(), "Projectinstructies")
        self._tabs.addTab(self._build_help_tab(), "Uitleg")
        self._tabs.currentChanged.connect(lambda _i: self._refresh_active_export())
        root.addWidget(self._tabs, stretch=1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(self._status)

        self._counter = QLabel("")
        self._counter.setWordWrap(True)
        root.addWidget(self._counter)

        btn_row = QHBoxLayout()
        self._copy_btn = QPushButton("Kopieer")
        self._copy_btn.setObjectName("primaryBtn")
        self._copy_btn.clicked.connect(self._on_copy_export)
        btn_row.addWidget(self._copy_btn)
        self._save_file_btn = QPushButton("Opslaan als bestand…")
        self._save_file_btn.clicked.connect(self._on_save_export_file)
        btn_row.addWidget(self._save_file_btn)
        close_btn = QPushButton("Sluiten")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self._refresh_freshness_ui()
        self._load_registry_into_ui()
        self._refresh_active_export()

    # --- tabs -----------------------------------------------------------------

    def _build_snapshot_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(
            QLabel(
                "Maakt een zelfstandig basisbestand met owned roster + mechanics. "
                "Sla het op en voeg het eenmalig toe aan chat/projectbronnen. "
                "Bij relevante wijzigingen: nieuw basisbestand (nieuw ID), "
                "niet stil overschrijven onder hetzelfde ID."
            )
        )
        self._snap_meta = QLabel("Nog geen snapshot aangemaakt.")
        self._snap_meta.setWordWrap(True)
        layout.addWidget(self._snap_meta)
        row = QHBoxLayout()
        build_btn = QPushButton("Basisgegevens opbouwen")
        build_btn.clicked.connect(self._on_build_snapshot)
        row.addWidget(build_btn)
        save_btn = QPushButton("Nieuw basisbestand exporteren…")
        save_btn.setToolTip(
            "Opslaan/downloaden. Dit wordt de referentie voor volgende "
            "adviesvragen. Gebouwde maar niet-opgeslagen snapshots tellen niet."
        )
        save_btn.clicked.connect(self._on_save_snapshot)
        row.addWidget(save_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self._shared_check = QCheckBox(
            "Ik heb deze geëxporteerde snapshot gedeeld met de AI "
            "(gebruikersverklaring, geen technische check)"
        )
        self._shared_check.toggled.connect(self._on_shared_toggled)
        layout.addWidget(self._shared_check)

        note = QLabel(
            "Opslaan hier bewijst niet dat de AI het bestand heeft. "
            "Deel het bewust in je chat of project. Adviesvragen verwijzen "
            "alleen naar de laatst geëxporteerde snapshot — niet naar een "
            "alleen-lokaal opgebouwde versie."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        layout.addWidget(note)
        layout.addStretch(1)
        return w

    def _build_request_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Instructiemodus"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Voor mijn project", "project")
        self._mode_combo.addItem("Zelfstandig", "standalone")
        saved = str(self._settings.value(_MODE_KEY, "project") or "project")
        idx = self._mode_combo.findData(saved)
        self._mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self._mode_hint = QLabel("")
        self._mode_hint.setWordWrap(True)
        self._mode_hint.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        layout.addWidget(self._mode_hint)

        self._swap_scope = QComboBox()
        self._swap_scope.addItem("Plaatsing + specialisaties (huidige party)", False)
        self._swap_scope.addItem("Zoek betere champions (één wissel)", True)
        self._swap_scope.currentIndexChanged.connect(
            lambda _i: self._refresh_active_export()
        )
        layout.addWidget(self._swap_scope)

        self._request_meta = QLabel("")
        self._request_meta.setWordWrap(True)
        layout.addWidget(self._request_meta)

        self._validation_label = QLabel("")
        self._validation_label.setWordWrap(True)
        layout.addWidget(self._validation_label)

        build_btn = QPushButton("Adviesvraag opbouwen / vernieuwen")
        build_btn.clicked.connect(lambda: self._on_build_request(interactive=True))
        layout.addWidget(build_btn)
        layout.addStretch(1)
        self._update_mode_hint()
        return w

    def _build_details_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(
            QLabel(
                "Selecteer owned champions voor een aanvullende export. "
                "Werkt ook zonder basisbestand."
            )
        )
        self._champ_list = QListWidget()
        self._champ_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        for hid, name, _roles, _tags in sorted(
            self._owned_rows, key=lambda r: (r[1].casefold(), r[0])
        ):
            item = QListWidgetItem(f"{name} (id {hid})")
            item.setData(Qt.ItemDataRole.UserRole, hid)
            self._champ_list.addItem(item)
        self._champ_list.itemSelectionChanged.connect(self._on_build_details)
        layout.addWidget(self._champ_list, stretch=1)
        self._details_meta = QLabel("")
        self._details_meta.setWordWrap(True)
        layout.addWidget(self._details_meta)
        parts_row = QHBoxLayout()
        self._parts_combo = QComboBox()
        self._parts_combo.setToolTip("Bij te grote selectie: kies welk deel je kopieert.")
        self._parts_combo.currentIndexChanged.connect(self._on_parts_combo_changed)
        parts_row.addWidget(QLabel("Deel"))
        parts_row.addWidget(self._parts_combo, stretch=1)
        layout.addLayout(parts_row)
        return w

    def _build_project_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(
            QLabel(
                "Vaste projectinstructies — eenmalig kopiëren naar je project of "
                "chatregels. Geen snapshot vereist. Gebruik ‘Kopieer’ hieronder."
            )
        )
        layout.addStretch(1)
        return w

    def _build_help_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        help_view = QTextEdit()
        help_view.setReadOnly(True)
        help_view.setPlainText(USER_HELP_NL)
        layout.addWidget(help_view)
        return w

    # --- helpers --------------------------------------------------------------

    def _budget(self) -> int:
        return clamp_char_budget(self._budget_spin.value())

    def _instruction_mode(self) -> InstructionMode:
        data = self._mode_combo.currentData()
        return "standalone" if data == "standalone" else "project"

    def _on_budget_changed(self, value: int) -> None:
        self._settings.setValue(_BUDGET_KEY, clamp_char_budget(value))
        self._refresh_active_export()

    def _on_mode_changed(self, *_args) -> None:
        self._settings.setValue(_MODE_KEY, self._instruction_mode())
        self._update_mode_hint()
        self._refresh_active_export()

    def _update_mode_hint(self) -> None:
        from ic_gamedata.formation_ai_advice.compact_clipboard import (
            instruction_mode_assumption,
        )

        self._mode_hint.setText(instruction_mode_assumption(self._instruction_mode()))

    def _refresh_freshness_ui(self) -> None:
        try:
            report = assess_snapshot_freshness(
                self._payload,
                self._formation,
                goal=self._goal_id,
                context=self._context,
            )
        except Exception as exc:
            self._freshness_label.setText(
                f"Snapshotstatus: actualiteit niet vast te stellen ({exc})."
            )
            self._freshness_label.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
            return

        lines = [
            f"Snapshotstatus (lokaal): {report.label_nl}",
        ]
        if report.exported_snapshot_id:
            lines.append(f"Geëxporteerde referentie: `{report.exported_snapshot_id}`")
        if (
            report.live_snapshot_id
            and report.live_snapshot_id != report.exported_snapshot_id
            and report.recommend_new_base_export
        ):
            lines.append(
                f"Live inhoud zou nieuw ID `{report.live_snapshot_id}` krijgen — "
                "exporteer eerst een nieuw basisbestand vóór je ernaar verwijst."
            )
        if report.user_declared_shared:
            lines.append("Gedeeld-verklaring: ja (alleen jouw checkbox, geen AI-check).")
        else:
            lines.append("Gedeeld-verklaring: nee / niet van toepassing.")
        if report.recommend_new_base_export:
            lines.append("Actie: Nieuw basisbestand exporteren.")
        lines.append(
            "‘Geen gedetecteerde wijzigingen’ = lokale hash-vergelijking; "
            "geen garantie dat game defines extern actueel zijn."
        )
        self._freshness_label.setText("\n".join(lines))
        warn = report.status in {
            SnapshotFreshnessStatus.ACCOUNT_CHANGED,
            SnapshotFreshnessStatus.MECHANICS_CHANGED,
            SnapshotFreshnessStatus.ACCOUNT_AND_MECHANICS_CHANGED,
            SnapshotFreshnessStatus.NO_SNAPSHOT,
            SnapshotFreshnessStatus.ACTUALITY_UNKNOWN,
        }
        warn_color = getattr(ui_theme, "WARN", None) or ui_theme.TEXT_MUTED
        self._freshness_label.setStyleSheet(
            f"color: {warn_color if warn else ui_theme.TEXT_MUTED};"
        )

        # Sync shared checkbox without firing toggle side-effects incorrectly.
        self._shared_check.blockSignals(True)
        self._shared_check.setChecked(bool(report.user_declared_shared))
        self._shared_check.setEnabled(bool(report.exported_snapshot_id))
        self._shared_check.blockSignals(False)

    def _on_shared_toggled(self, checked: bool) -> None:
        meta = get_exported_snapshot_meta()
        sid = (meta or {}).get("snapshot_id")
        if checked and not sid:
            self._shared_check.blockSignals(True)
            self._shared_check.setChecked(False)
            self._shared_check.blockSignals(False)
            QMessageBox.information(
                self,
                "Gedeeld",
                "Exporteer eerst een basisbestand voordat je een "
                "deel-verklaring kunt vastleggen.",
            )
            return
        set_user_declared_shared(str(sid) if sid else None, declared=checked)
        self._refresh_freshness_ui()

    def _clear_export_text(self) -> None:
        self._export_text = ""
        self._counter.setText("")
        self._copy_btn.setEnabled(False)

    def _set_export_text(
        self,
        text: str,
        *,
        sections: dict[str, str] | None = None,
        allow_copy: bool | None = None,
    ) -> None:
        compact = try_loss_free_shrink(text)
        self._export_text = compact
        info = evaluate_clipboard_budget(
            compact, max_chars=self._budget(), sections=sections
        )
        self._counter.setText(info["label"])
        if info["within_budget"] and allow_copy is not False:
            self._copy_btn.setEnabled(True)
            self._copy_btn.setToolTip("Kopieert de huidige exporttekst.")
            if self._allow_unvalidated_copy:
                self._status.setText(
                    "Binnen budget — diagnostische (niet-gevalideerde) export."
                )
            else:
                self._status.setText("Binnen budget — kopiëren toegestaan.")
        elif not info["within_budget"]:
            self._copy_btn.setEnabled(False)
            breakdown = ""
            if info.get("sections"):
                top = info["sections"][:4]
                breakdown = " Grootste onderdelen: " + "; ".join(
                    f"{s['name']}={s['chars']} tekens" for s in top
                )
            self._status.setText(
                f"ADVICE_REQUEST te groot: {info['chars']} tekens "
                f"(max {info['max_chars']}; {info['over_by']} te veel). "
                "Geen stille truncatie of afgekapt JSON. "
                "Verhoog je budget of sla op als bestand."
                + breakdown
            )
            self._copy_btn.setToolTip(
                "Geblokkeerd: tekst past niet binnen het ingestelde tekenbudget."
            )
        else:
            self._copy_btn.setEnabled(False)
            self._copy_btn.setToolTip("Kopiëren geblokkeerd door validatie.")

        if allow_copy is False and info["within_budget"]:
            self._copy_btn.setEnabled(False)

    def _refresh_active_export(self) -> None:
        tab = self._tabs.currentIndex()
        self._allow_unvalidated_copy = False
        if tab == 0:
            if self._current_snapshot is not None:
                text = build_base_snapshot_clipboard_text(self._current_snapshot)
                self._set_export_text(
                    text,
                    sections={
                        "json": minify_json(self._current_snapshot),
                        "headers": text[
                            : max(
                                0,
                                len(text) - len(minify_json(self._current_snapshot)),
                            )
                        ],
                    },
                )
            else:
                self._clear_export_text()
        elif tab == 1:
            self._on_build_request(interactive=False)
        elif tab == 2:
            self._on_build_details()
        elif tab == 3:
            self._on_show_project_instructions()
        elif tab == 4:
            self._clear_export_text()

    def _load_registry_into_ui(self) -> None:
        reg = load_snapshot_registry()
        sid = reg.get("last_exported_snapshot_id") or reg.get("last_snapshot_id")
        if not sid:
            self._snap_meta.setText(
                "Nog geen geëxporteerde snapshot. Bouw basisgegevens en "
                "gebruik ‘Nieuw basisbestand exporteren’."
            )
            return
        cov = reg.get("last_exported_coverage") or reg.get("last_coverage") or {}
        self._snap_meta.setText(
            f"Laatst geëxporteerde snapshot: `{sid}`\n"
            f"Aangemaakt: {reg.get('last_exported_at') or reg.get('last_created_at') or '?'}\n"
            f"Pad: {reg.get('last_exported_path') or reg.get('last_saved_path') or '?'}\n"
            f"Omvang: {reg.get('last_exported_char_count') or reg.get('last_char_count') or '?'} "
            f"tekens / "
            f"{reg.get('last_exported_utf8_bytes') or reg.get('last_utf8_bytes') or '?'} bytes\n"
            f"Dekking: owned {cov.get('owned_known_count', '?')}, "
            f"opgenomen {cov.get('included_count', '?')}, "
            f"onvolledig {cov.get('incomplete_count', '?')}\n"
            "Let op: ‘geëxporteerd’ ≠ ‘beschikbaar bij de AI’."
        )

    # --- actions --------------------------------------------------------------

    def _on_build_snapshot(self) -> None:
        try:
            snap = build_base_snapshot(
                self._payload,
                formation=self._formation,
                goal=self._goal_id,
                context=self._context,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Snapshot", f"Opbouwen mislukt: {exc}")
            return
        self._current_snapshot = snap
        self._current_snapshot_exported = False
        meta = snap.get("meta") or {}
        cov = (snap.get("roster") or {}).get("coverage") or {}
        text = build_base_snapshot_clipboard_text(snap)
        exported = get_exported_snapshot_meta()
        exported_id = (exported or {}).get("snapshot_id")
        extra = ""
        if exported_id and exported_id != meta.get("snapshot_id"):
            extra = (
                f"\nNog niet geëxporteerd. Adviesvragen blijven naar "
                f"`{exported_id}` verwijzen tot je dit bestand exporteert."
            )
        elif not exported_id:
            extra = (
                "\nNog niet geëxporteerd — adviesvragen hebben nog geen "
                "geldige snapshotreferentie."
            )
        self._snap_meta.setText(
            f"Snapshot-ID (lokaal opgebouwd): `{meta.get('snapshot_id')}`\n"
            f"Aangemaakt: {meta.get('created_at')}\n"
            f"mechanics_hash: {meta.get('mechanics_hash')}\n"
            f"account_state_hash: {meta.get('account_state_hash')}\n"
            f"Dekking: owned {cov.get('owned_known_count')}, "
            f"opgenomen {cov.get('included_count')}, "
            f"onvolledig {cov.get('incomplete_count')}\n"
            f"Omvang: {count_chars(text)} tekens"
            f"{extra}"
        )
        self._tabs.setCurrentIndex(0)
        self._set_export_text(text)
        self._status.setText(
            "Snapshot opgebouwd — nog niet geëxporteerd als referentie. "
            "Gebruik ‘Nieuw basisbestand exporteren’."
        )
        self._refresh_freshness_ui()

    def _on_save_snapshot(self) -> None:
        if self._current_snapshot is None:
            self._on_build_snapshot()
        if self._current_snapshot is None:
            QMessageBox.information(self, "Snapshot", "Geen snapshot om te exporteren.")
            return
        meta = self._current_snapshot.get("meta") or {}
        suggested = f"{meta.get('snapshot_id') or 'base_snapshot'}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Nieuw basisbestand exporteren",
            suggested,
            "JSON (*.json);;Alle bestanden (*)",
        )
        if not path:
            return
        try:
            saved = save_snapshot_to_path(self._current_snapshot, Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Exporteren", f"Opslaan mislukt: {exc}")
            return
        self._current_snapshot_exported = True
        self._load_registry_into_ui()
        self._refresh_freshness_ui()
        QMessageBox.information(
            self,
            "Geëxporteerd",
            f"Opgeslagen als:\n{saved}\n\n"
            "Voeg dit bestand eenmalig toe aan je AI-chat of projectbronnen. "
            "Daarna kun je de checkbox ‘Ik heb deze snapshot gedeeld’ "
            "als verklaring aanvinken (geen technische verificatie).\n\n"
            "Volgende adviesvragen verwijzen naar dit nieuwe snapshot-ID.",
        )

    def _exported_snapshot_meta(self) -> dict[str, Any] | None:
        """Only the last exported snapshot — never an unsaved local build."""
        return get_exported_snapshot_meta()

    def _on_build_request(self, *, interactive: bool = True) -> None:
        self._allow_unvalidated_copy = False
        snap_meta = self._exported_snapshot_meta()
        if not snap_meta or not snap_meta.get("snapshot_id"):
            self._clear_export_text()
            self._request_meta.setText(
                "Geen geëxporteerde basis-snapshot. "
                "Maak tab ‘Basisgegevens’, exporteer met "
                "‘Nieuw basisbestand exporteren’, deel het bestand, "
                "en bouw daarna de adviesvraag."
            )
            self._validation_label.setText("")
            self._status.setText(
                "Adviesvraag geblokkeerd: geen geëxporteerde snapshot-referentie."
            )
            return

        include_swap = bool(self._swap_scope.currentData())
        try:
            req = build_advice_request(
                self._payload,
                self._formation,
                snapshot_id=str(snap_meta["snapshot_id"]),
                snapshot_meta=snap_meta,
                goal=self._goal_id,
                context=self._context,
                fixed_main_dps_id=self._fixed_main_dps_id,
                locked_champion_ids=self._locked_champion_ids,
                goal_parameters=self._goal_parameters,
                manual_restriction_text=self._manual_restriction_text,
                include_swap_scope=include_swap,
            )
        except Exception as exc:
            if interactive:
                QMessageBox.warning(self, "Adviesvraag", f"Opbouwen mislukt: {exc}")
            self._status.setText(f"Adviesvraag mislukt: {exc}")
            return

        validation = validate_advice_request_export(
            payload=self._payload,
            request=req,
            snapshot_id=str(snap_meta["snapshot_id"]),
            exported_snapshot_id=str(snap_meta["snapshot_id"]),
        )
        self._last_validation = validation

        if validation.advice_ready:
            req = mark_request_validated(req, validation)
            self._allow_unvalidated_copy = False
            warn_txt = ""
            if validation.warnings:
                warn_txt = " Waarschuwingen: " + "; ".join(
                    w.message for w in validation.warnings[:4]
                )
            self._validation_label.setText(
                "Validatie: adviesklaar "
                f"(structural_ok={validation.structural_ok}, "
                f"party_restriction_ok={validation.party_restriction_ok})."
                + warn_txt
            )
        else:
            req = mark_request_unvalidated(req, validation)
            self._validation_label.setText(
                "Niet adviesklaar — diagnostische export "
                f"(structural_ok={validation.structural_ok}, "
                f"party_restriction_ok={validation.party_restriction_ok}). "
                + validation.summary_nl()
            )
            if interactive:
                reply = QMessageBox.question(
                    self,
                    "Validatie mislukt",
                    "De adviesvraag voldoet niet aan alle checks.\n\n"
                    f"{validation.summary_nl()}\n\n"
                    "Wil je toch een diagnostische (niet-gevalideerde) export "
                    "tonen? Die mag niet als normale adviesaanvraag worden "
                    "gepresenteerd.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self._clear_export_text()
                    self._status.setText("Export geannuleerd door validatiefouten.")
                    self._last_request = None
                    self._allow_unvalidated_copy = False
                    return
                self._allow_unvalidated_copy = True
            else:
                # Auto-refresh: labeled diagnostic export, copy gated.
                self._allow_unvalidated_copy = True

        self._last_request = req
        mode = self._instruction_mode()
        text = build_advice_request_clipboard_text(req, mode=mode)
        from ic_gamedata.formation_ai_advice.compact_clipboard import (
            compact_request_for_clipboard,
            instruction_mode_assumption,
            safety_instruction,
        )

        sid = str(snap_meta["snapshot_id"])
        section_bodies = {
            "modus_en_veiligheid": "\n".join(
                [instruction_mode_assumption(mode), safety_instruction(sid)]
            ),
            "json_gegevens": minify_json(compact_request_for_clipboard(req)),
        }
        for row in advice_request_section_breakdown(req, mode=mode):
            name = row.get("name")
            if name == "algemene_instructies" and name not in section_bodies:
                from ic_gamedata.formation_ai_advice.compact_clipboard import (
                    _standalone_advice_rules,
                )

                section_bodies[name] = "\n".join(
                    _standalone_advice_rules(swap=isinstance(req.get("swap"), dict))
                )

        freshness_note = ""
        try:
            report = assess_snapshot_freshness(
                self._payload,
                self._formation,
                goal=self._goal_id,
                context=self._context,
            )
            if report.recommend_new_base_export:
                freshness_note = (
                    f"\nWaarschuwing snapshotstatus: {report.label_nl}. "
                    "Overweeg eerst een nieuw basisbestand te exporteren."
                )
        except Exception:
            freshness_note = ""

        local_pending = ""
        if (
            self._current_snapshot
            and not self._current_snapshot_exported
            and isinstance(self._current_snapshot.get("meta"), dict)
        ):
            lid = self._current_snapshot["meta"].get("snapshot_id")
            if lid and lid != sid:
                local_pending = (
                    f"\nLokaal opgebouwd maar niet geëxporteerd: `{lid}` — "
                    f"deze aanvraag verwijst bewust nog naar `{sid}`."
                )

        self._request_meta.setText(
            f"Verwijst naar geëxporteerde snapshot `{sid}`.\n"
            f"{instruction_mode_assumption(mode)}\n"
            "Actuele adventure/party/eligibility/specs komen uit de huidige "
            "toestand, niet uit een oude snapshot als waarheid."
            f"{local_pending}{freshness_note}"
        )
        allow = True
        if not validation.ok and not self._allow_unvalidated_copy:
            allow = False
        self._set_export_text(text, sections=section_bodies, allow_copy=allow)

    def _selected_champion_ids(self) -> list[int]:
        ids: list[int] = []
        for item in self._champ_list.selectedItems():
            hid = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(hid, int):
                ids.append(hid)
        return sorted(set(ids))

    def _on_build_details(self) -> None:
        ids = self._selected_champion_ids()
        if not ids:
            self._clear_export_text()
            self._details_meta.setText("Selecteer minstens één champion.")
            self._parts_combo.blockSignals(True)
            self._parts_combo.clear()
            self._parts_combo.blockSignals(False)
            self._details_parts = []
            return
        snap_meta = self._exported_snapshot_meta()
        try:
            details = build_champion_details(
                self._payload,
                ids,
                formation=self._formation,
                snapshot_id=(snap_meta or {}).get("snapshot_id"),
                goal=self._goal_id,
                context=self._context,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Championdetails", f"Opbouwen mislukt: {exc}")
            return
        cov = details.get("coverage") or {}
        self._details_meta.setText(
            f"IDs: {ids}\n"
            f"Opgenomen: {cov.get('included_count')} / gevraagd {cov.get('requested_count')}\n"
            f"Ontbrekend: {cov.get('missing') or 'geen'}\n"
            f"export_schema: {(details.get('meta') or {}).get('export_schema_version')}"
        )
        parts = split_champion_details_for_budget(details, max_chars=self._budget())
        self._details_parts = parts
        self._parts_combo.blockSignals(True)
        self._parts_combo.clear()
        for i, part in enumerate(parts):
            st = evaluate_clipboard_budget(part, max_chars=self._budget())
            label = f"Deel {i + 1}/{len(parts)} — {st['chars']} tekens"
            if not st["within_budget"]:
                label += " (boven budget)"
            self._parts_combo.addItem(label, i)
        self._parts_combo.blockSignals(False)
        if len(parts) > 1:
            self._status.setText(
                f"Selectie past niet in één stuk binnen {self._budget()} tekens. "
                f"Verdeeld in {len(parts)} delen op championgrenzen. "
                "Kopieer elk deel apart, of verklein de selectie / verhoog budget."
            )
        self._on_parts_combo_changed()

    def _on_parts_combo_changed(self, *_args) -> None:
        if not self._details_parts:
            return
        idx = self._parts_combo.currentData()
        if not isinstance(idx, int) or idx < 0 or idx >= len(self._details_parts):
            idx = 0
        text = try_loss_free_shrink(self._details_parts[idx])
        self._set_export_text(text)

    def _on_show_project_instructions(self) -> None:
        text = build_project_instructions_clipboard_text()
        self._set_export_text(text)

    def _on_copy_export(self) -> None:
        text = self._export_text
        if not text.strip():
            QMessageBox.information(self, "Kopiëren", "Geen exporttekst.")
            return
        info = evaluate_clipboard_budget(text, max_chars=self._budget())
        if not info["within_budget"]:
            QMessageBox.warning(
                self,
                "Budget",
                f"Tekst past niet ({info['chars']} > {info['max_chars']} tekens). "
                "Geen stille truncatie. Verhoog je budget of sla op als bestand.",
            )
            return
        if (
            self._tabs.currentIndex() == 1
            and self._last_validation is not None
            and not self._last_validation.ok
        ):
            confirm = QMessageBox.warning(
                self,
                "Niet gevalideerd",
                "Je kopieert een diagnostische, niet-gevalideerde export. "
                "Presenteer dit niet als normale geldige adviesaanvraag.\n\n"
                "Toch kopiëren?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        if not self._write_clipboard(text):
            QMessageBox.warning(self, "Clipboard", "Kopiëren naar klembord mislukt.")
            return
        self._status.setText(
            f"Gekopieerd ({info['chars']} tekens / {info['utf8_bytes']} bytes)."
        )

    def _on_save_export_file(self) -> None:
        text = self._export_text
        if not text.strip():
            QMessageBox.information(self, "Opslaan", "Geen exporttekst.")
            return
        # Tab 0 with current snapshot: prefer proper snapshot export path.
        if self._tabs.currentIndex() == 0 and self._current_snapshot is not None:
            self._on_save_snapshot()
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export opslaan",
            "advice_export.txt",
            "Tekst (*.txt *.md);;JSON (*.json);;Alle bestanden (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Opslaan", f"Mislukt: {exc}")
            return
        self._status.setText(f"Opgeslagen: {path}")
