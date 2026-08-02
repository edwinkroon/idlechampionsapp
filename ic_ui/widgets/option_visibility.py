"""Toggle-linked visibility for option panels."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QWidget


def bind_option_visibility(checkbox: QCheckBox, *widgets: QWidget) -> None:
    def update(checked: bool) -> None:
        for widget in widgets:
            widget.setVisible(checked)

    checkbox.toggled.connect(update)
    update(checkbox.isChecked())
