"""Install paths and data source configuration."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SourcesTab(QWidget):
    """Paths and memory hints; refresh/save handled by the main window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.install_lbl = QLabel("—")
        self.install_lbl.setWordWrap(True)
        self.log_lbl = QLabel("—")
        self.log_lbl.setWordWrap(True)
        self.manual_path = QLineEdit("")
        self.ui_hint = QLineEdit("")
        self.ui_hint.setPlaceholderText("optioneel")

        root = QVBoxLayout(self)
        source = QGroupBox("Bronnen")
        source_form = QFormLayout(source)
        source_form.addRow("Installatie:", self.install_lbl)
        source_form.addRow("Logbestand:", self.log_lbl)
        source_form.addRow("Handmatig pad:", self.manual_path)
        source_form.addRow("Memory UI-hint:", self.ui_hint)
        root.addWidget(source)

        controls = QHBoxLayout()
        self._save_btn = QPushButton("Opslaan")
        self._refresh_btn = QPushButton("Opnieuw zoeken")
        controls.addWidget(self._save_btn)
        controls.addWidget(self._refresh_btn)
        controls.addStretch(1)
        root.addLayout(controls)
        root.addStretch(1)

    def connect_save(self, callback) -> None:
        self._save_btn.clicked.connect(callback)

    def connect_refresh(self, callback) -> None:
        self._refresh_btn.clicked.connect(callback)
