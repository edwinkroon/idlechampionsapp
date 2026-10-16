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

from ic_ui import theme as ui_theme
from ic_ui.theme import apply_button_icon, on_theme_changed, style_primary_button


class SourcesTab(QWidget):
    """Paths and memory hints; refresh/save handled by the main window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.install_lbl = QLabel("—")
        self.install_lbl.setWordWrap(True)
        self.log_lbl = QLabel("—")
        self.log_lbl.setWordWrap(True)
        self.manual_path = QLineEdit("")
        self.manual_path.setPlaceholderText("Path to Idle Champions install folder…")
        self.ui_hint = QLineEdit("")
        self.ui_hint.setPlaceholderText("optional — memory offset hint")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        source = QGroupBox("Game data")
        source_form = QFormLayout(source)
        source_form.setSpacing(10)
        source_form.setContentsMargins(12, 18, 12, 12)
        source_form.addRow("Installation:", self.install_lbl)
        source_form.addRow("Log file:", self.log_lbl)
        source_form.addRow("Manual path:", self.manual_path)
        source_form.addRow("Memory UI hint:", self.ui_hint)
        root.addWidget(source)

        tip = QLabel(
            "Tip: start Idle Champions first. If credentials or memory offsets are missing, "
            "use Search again. Manual path is only needed when auto-detect fails."
        )
        tip.setWordWrap(True)
        tip.setObjectName("sourcesTip")
        tip.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; font-size: 12px;")
        root.addWidget(tip)

        controls = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        apply_button_icon(self._save_btn, "save")
        self._refresh_btn = QPushButton("Search again")
        apply_button_icon(self._refresh_btn, "refresh")
        style_primary_button(self._refresh_btn)
        controls.addWidget(self._refresh_btn)
        controls.addWidget(self._save_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self._feedback = QLabel("")
        self._feedback.setWordWrap(True)
        self._feedback.setObjectName("sourcesFeedback")
        self._feedback.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; font-size: 12px;")
        root.addWidget(self._feedback)
        root.addStretch(1)

        on_theme_changed(self._apply_local_theme)

    def _apply_local_theme(self, _mode: str = "dark") -> None:
        tip = self.findChild(QLabel, "sourcesTip")
        if tip is not None:
            tip.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; font-size: 12px;")
        self._feedback.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; font-size: 12px;")

    def set_feedback(self, text: str, *, ok: bool = True) -> None:
        color = ui_theme.SUCCESS if ok else ui_theme.WARN
        self._feedback.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._feedback.setText(text)

    def connect_save(self, callback) -> None:
        self._save_btn.clicked.connect(callback)

    def connect_refresh(self, callback) -> None:
        self._refresh_btn.clicked.connect(callback)
