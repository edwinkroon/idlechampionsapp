"""Dialog to configure and copy champion-swap chat advice (phase 1 trial)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ic_ui import theme as ui_theme

if TYPE_CHECKING:
    from ic_gamedata.formation_ai_advice.swap_export import SwapCandidateRow


class SwapAdviceDialog(QDialog):
    """Pick locks + owned candidates, then copy a swap-advice clipboard pack."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        objective_label: str,
        main_dps_id: int | None,
        main_dps_name: str,
        party: list[dict[str, Any]],
        candidates: list[SwapCandidateRow],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kopieer voor chat — championwissels")
        self.resize(720, 560)
        self._candidates = list(candidates)
        self._party = list(party)
        self._main_dps_id = main_dps_id
        self._accepted_copy = False
        self._selected_ids: list[int] = []
        self._locked_ids: list[int] = []

        root = QVBoxLayout(self)
        root.setSpacing(8)

        intro = QLabel(
            "Alleen adviesexport — er worden geen champions, specialisaties, "
            "feats of equipment in de app of game gewijzigd."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(intro)

        meta = QLabel(
            f"<b>Doel:</b> {objective_label}<br>"
            f"<b>Hoofd-DPS (vast):</b> {main_dps_name}"
            + (f" (id {main_dps_id})" if main_dps_id is not None else "")
        )
        meta.setTextFormat(Qt.TextFormat.RichText)
        meta.setWordWrap(True)
        root.addWidget(meta)

        equip = QLabel(
            "Beperking: betrouwbare equipment-effecten ontbreken. "
            "Dit is geen bewezen damagevergelijking met jouw gear."
        )
        equip.setWordWrap(True)
        equip.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(equip)

        root.addWidget(QLabel("Huidige party — optioneel andere champions vastzetten:"))
        self._lock_box = QWidget()
        lock_layout = QVBoxLayout(self._lock_box)
        lock_layout.setContentsMargins(0, 0, 0, 0)
        lock_layout.setSpacing(2)
        self._lock_checks: dict[int, QCheckBox] = {}
        for row in party:
            hid = row.get("champion_id")
            if not isinstance(hid, int):
                continue
            name = str(row.get("name") or hid)
            seat = row.get("seat")
            roles = ", ".join(str(r) for r in (row.get("roles") or [])[:3])
            label = f"{name}"
            if seat is not None:
                label += f" · seat {seat}"
            if roles:
                label += f" · {roles}"
            cb = QCheckBox(label)
            if hid == main_dps_id:
                cb.setChecked(True)
                cb.setEnabled(False)
                cb.setToolTip("Hoofd-DPS is in deze modus altijd vastgezet.")
            self._lock_checks[hid] = cb
            lock_layout.addWidget(cb)
        root.addWidget(self._lock_box)

        help_txt = QLabel(
            "Selecteer bijvoorbeeld 3–5 kandidaten uit je eigen roster. "
            "De adviseur vergelijkt hun mechanics en synergieën met je huidige party. "
            "Dit is geen bewezen damagevergelijking met jouw equipment."
        )
        help_txt.setWordWrap(True)
        root.addWidget(help_txt)

        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Zoek op naam…")
        self._search.textChanged.connect(self._apply_filters)
        filters.addWidget(self._search, stretch=2)

        self._seat_filter = QComboBox()
        self._seat_filter.addItem("Alle seats", None)
        seats = sorted(
            {c.seat for c in candidates if isinstance(c.seat, int)}
        )
        for seat in seats:
            self._seat_filter.addItem(f"Seat {seat}", seat)
        self._seat_filter.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self._seat_filter)

        self._role_filter = QComboBox()
        self._role_filter.addItem("Alle rollen", None)
        roles_set: set[str] = set()
        for c in candidates:
            roles_set.update(c.roles)
        for role in sorted(roles_set):
            self._role_filter.addItem(role, role)
        self._role_filter.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self._role_filter)
        root.addLayout(filters)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["", "Naam", "Seat", "Rollen", "Toelating"]
        )
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnWidth(0, 36)
        self._table.setColumnWidth(1, 160)
        self._table.setColumnWidth(2, 50)
        self._table.setColumnWidth(3, 160)
        self._table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._table, stretch=1)

        self._status = QLabel("Geen kandidaten geselecteerd.")
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(self._status)

        buttons = QDialogButtonBox()
        self._copy_btn = QPushButton("Kopieer wisseladvies voor chat")
        self._copy_btn.clicked.connect(self._on_copy)
        buttons.addButton(self._copy_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.clicked.connect(self.reject)
        root.addWidget(buttons)

        self._row_checks: dict[int, QCheckBox] = {}
        self._fill_table()

    def selected_candidate_ids(self) -> list[int]:
        return list(self._selected_ids)

    def locked_champion_ids(self) -> list[int]:
        return list(self._locked_ids)

    def copy_accepted(self) -> bool:
        return self._accepted_copy

    def _fill_table(self) -> None:
        self._table.setRowCount(0)
        self._row_checks.clear()
        for cand in self._candidates:
            if not self._row_visible(cand):
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)

            cb = QCheckBox()
            cb.setEnabled(cand.selectable)
            if cand.select_warning:
                cb.setToolTip(cand.select_warning)
            elif not cand.selectable:
                cb.setToolTip("Denied — niet selecteerbaar in deze proef.")
            cb.stateChanged.connect(self._update_selection_status)
            self._row_checks[cand.hero_id] = cb
            wrap = QWidget()
            lay = QHBoxLayout(wrap)
            lay.setContentsMargins(4, 0, 0, 0)
            lay.addWidget(cb)
            lay.addStretch(1)
            self._table.setCellWidget(row, 0, wrap)

            self._table.setItem(row, 1, QTableWidgetItem(cand.name))
            self._table.setItem(
                row,
                2,
                QTableWidgetItem("" if cand.seat is None else str(cand.seat)),
            )
            self._table.setItem(
                row, 3, QTableWidgetItem(", ".join(cand.roles) or "—")
            )
            elig = cand.eligibility
            reason = cand.eligibility_reason or ""
            text = elig
            if reason:
                text = f"{elig}: {reason}"
            if cand.select_warning:
                text = f"{text} ⚠"
            item = QTableWidgetItem(text)
            if elig == "denied":
                item.setForeground(Qt.GlobalColor.darkRed)
            elif elig in ("unknown", "conflict"):
                item.setForeground(Qt.GlobalColor.darkYellow)
            self._table.setItem(row, 4, item)
            # Store hero id on name cell for stability.
            name_item = self._table.item(row, 1)
            if name_item is not None:
                name_item.setData(Qt.ItemDataRole.UserRole, cand.hero_id)

        self._update_selection_status()

    def _row_visible(self, cand: SwapCandidateRow) -> bool:
        q = self._search.text().strip().casefold()
        if q and q not in cand.name.casefold():
            return False
        seat = self._seat_filter.currentData()
        if seat is not None and cand.seat != seat:
            return False
        role = self._role_filter.currentData()
        if role is not None and role not in cand.roles:
            return False
        return True

    def _apply_filters(self) -> None:
        previously = {
            hid for hid, cb in self._row_checks.items() if cb.isChecked()
        }
        self._fill_table()
        for hid, cb in self._row_checks.items():
            if hid in previously and cb.isEnabled():
                cb.setChecked(True)
        self._update_selection_status()

    def _update_selection_status(self) -> None:
        n = sum(1 for cb in self._row_checks.values() if cb.isChecked())
        if n == 0:
            self._status.setText("Geen kandidaten geselecteerd.")
        elif 3 <= n <= 5:
            self._status.setText(f"{n} kandidaten geselecteerd (richtlijn 3–5).")
        else:
            self._status.setText(
                f"{n} kandidaten geselecteerd (richtlijn 3–5; geen harde limiet)."
            )

    def _on_copy(self) -> None:
        selected = [hid for hid, cb in self._row_checks.items() if cb.isChecked()]
        if not selected:
            QMessageBox.information(
                self,
                "Geen kandidaten",
                "Selecteer minstens één owned kandidaat buiten de huidige party.",
            )
            return
        locked = [
            hid
            for hid, cb in self._lock_checks.items()
            if cb.isChecked()
        ]
        if self._main_dps_id is not None and self._main_dps_id not in locked:
            locked.append(self._main_dps_id)
        self._selected_ids = selected
        self._locked_ids = locked
        self._accepted_copy = True
        self.accept()
