"""Animated startup splash so cold-start work does not look like a hung app."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ic_ui import theme as ui_theme
from ic_ui.widgets.busy_indicator import BusySpinner


class StartupSplash(QWidget):
    """Centered loading window shown while the main UI is built."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setObjectName("startupSplash")
        self.setWindowTitle("Idle Champions — Starting")
        # Real top-level window (not Tool) so Windows actually maps/paints it.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(340, 200)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 32, 28, 28)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Idle Champions")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {ui_theme.TEXT_PRIMARY}; font-size: 16px; font-weight: 600;"
        )
        root.addWidget(title)

        self._spinner = BusySpinner(self, size=44)
        self._spinner.start()
        root.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignCenter)

        self._status = QLabel("Starting…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {ui_theme.TEXT_MUTED}; font-size: 12px;")
        root.addWidget(self._status)

        self.setStyleSheet(
            f"#startupSplash {{"
            f"  background-color: {ui_theme.BG_PAGE_BOTTOM};"
            f"  border: 1px solid {ui_theme.BORDER};"
            f"  border-radius: 10px;"
            f"}}"
        )

    def present(self) -> None:
        """Show, center, and force a paint so the splash is visible before UI build."""
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )
        self.show()
        self.raise_()
        self.activateWindow()
        self._spinner.start()
        self.repaint()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._spinner.start()

    def set_status(self, message: str) -> None:
        self._status.setText(message or "Starting…")
        self._status.repaint()
        self.repaint()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def finish(self, main_window: QWidget | None = None) -> None:
        self._spinner.stop()
        self.close()
        if main_window is not None:
            main_window.raise_()
            main_window.activateWindow()
