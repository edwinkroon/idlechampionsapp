"""QComboBox that works inside QScrollArea (popup is not clipped)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox


class PopupComboBox(QComboBox):
    """Ensure the dropdown list is a top-level popup, not clipped by scroll views."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMaxVisibleItems(20)

    def showPopup(self) -> None:
        super().showPopup()
        view = self.view()
        if view is None:
            return
        popup = view.window()
        if popup is not None and popup is not self.window():
            popup.setWindowFlags(
                Qt.WindowType.Popup
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
            popup.show()
