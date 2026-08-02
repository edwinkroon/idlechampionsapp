"""Shared goal/context controls for Party Advisor and Specializations tabs."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QWidget

GOAL_ITEMS = (
    ("BUD / damage", "bud"),
    ("Gold income", "gold"),
    ("Speed / areas", "speed"),
)

CONTEXT_ITEMS = (
    ("Campaign", "campaign"),
    ("Events", "events"),
    ("Push", "push"),
    ("Modron", "modron"),
)


class AdvisorGoalContextBar(QWidget):
    """Doel + context selectors shared by advisor tabs."""

    changed = Signal()

    def __init__(
        self,
        *,
        include_formation: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._goal = QComboBox()
        for label, value in GOAL_ITEMS:
            self._goal.addItem(label, value)

        self._context = QComboBox()
        for label, value in CONTEXT_ITEMS:
            self._context.addItem(label, value)

        self._formation: QCheckBox | None = None
        if include_formation:
            self._formation = QCheckBox("Formatie")
            self._formation.setChecked(True)
            self._formation.toggled.connect(self.changed.emit)

        self._goal.currentIndexChanged.connect(self.changed.emit)
        self._context.currentIndexChanged.connect(self.changed.emit)

        layout.addWidget(QLabel("Doel:"))
        layout.addWidget(self._goal)
        layout.addWidget(QLabel("Context:"))
        layout.addWidget(self._context)
        if self._formation is not None:
            layout.addWidget(self._formation)
        layout.addStretch(1)

    def goal(self) -> str:
        return self._goal.currentData() or "bud"

    def context(self) -> str:
        return self._context.currentData() or "campaign"

    def include_formation(self) -> bool:
        return self._formation.isChecked() if self._formation is not None else False
