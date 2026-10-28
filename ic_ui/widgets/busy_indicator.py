"""Reusable busy feedback for background jobs.

Rule: never run heavy ``ic_gamedata.*`` work on the UI thread from click
handlers. Set busy *before* ``QThreadPool.start``, and always clear busy in
done/error handlers (including superseded jobs).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ic_ui import theme as ui_theme


class BusySpinner(QWidget):
    """Compact arc spinner; advances on a timer so the UI stays animated."""

    def __init__(self, parent: QWidget | None = None, *, size: int = 16) -> None:
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self.setFixedSize(size, size)
        self.setVisible(False)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.setVisible(True)
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.setVisible(False)

    @property
    def is_spinning(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = max(2, self._size // 8)
        rect = QRectF(margin, margin, self._size - 2 * margin, self._size - 2 * margin)
        track = QPen(QColor(ui_theme.BORDER))
        track.setWidth(max(2, self._size // 8))
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawEllipse(rect)
        arc = QPen(QColor(ui_theme.ACCENT))
        arc.setWidth(max(2, self._size // 8))
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        # Qt arcs: 1/16th degree, counter-clockwise from 3 o'clock.
        painter.drawArc(rect, int(-self._angle * 16), 90 * 16)


class StatusBusyRow(QWidget):
    """Status label with an optional inline spinner for background analysis."""

    def __init__(self, parent: QWidget | None = None, *, spinner_size: int = 14) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._spinner = BusySpinner(self, size=spinner_size)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._label, stretch=1)

    @property
    def label(self) -> QLabel:
        return self._label

    @property
    def spinner(self) -> BusySpinner:
        return self._spinner

    def setText(self, text: str) -> None:  # noqa: N802 — Qt-style API
        self._label.setText(text)

    def text(self) -> str:
        return self._label.text()

    def setStyleSheet(self, sheet: str) -> None:  # noqa: N802
        self._label.setStyleSheet(sheet)

    def set_busy(self, busy: bool, *, message: str | None = None) -> None:
        if message is not None:
            self._label.setText(message)
        if busy:
            self._spinner.start()
        else:
            self._spinner.stop()


class BusyScope:
    """Disable action buttons and show busy label text while a job runs.

    Does **not** install a WaitCursor — the UI must keep responding.
    """

    def __init__(
        self,
        *,
        buttons: Sequence[QPushButton] = (),
        status: Callable[[str], None] | QLabel | StatusBusyRow | None = None,
        busy_texts: dict[QPushButton, str] | None = None,
        on_busy_widgets: Sequence[QWidget] = (),
    ) -> None:
        self._buttons = tuple(buttons)
        self._status = status
        self._busy_texts = busy_texts or {}
        self._on_busy_widgets = tuple(on_busy_widgets)
        self._saved_texts: dict[QPushButton, str] = {}
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def begin(self, message: str | None = None) -> None:
        self._active = True
        self._saved_texts.clear()
        for btn in self._buttons:
            self._saved_texts[btn] = btn.text()
            btn.setEnabled(False)
            if btn in self._busy_texts:
                btn.setText(self._busy_texts[btn])
        for widget in self._on_busy_widgets:
            widget.setEnabled(False)
        if message is not None:
            self._set_status(message)
        if isinstance(self._status, StatusBusyRow):
            self._status.set_busy(True, message=message)

    def end(self, *, message: str | None = None) -> None:
        for btn in self._buttons:
            saved = self._saved_texts.get(btn)
            if saved is not None:
                btn.setText(saved)
            btn.setEnabled(True)
        self._saved_texts.clear()
        for widget in self._on_busy_widgets:
            widget.setEnabled(True)
        if isinstance(self._status, StatusBusyRow):
            self._status.set_busy(False, message=message)
        elif message is not None:
            self._set_status(message)
        self._active = False

    def _set_status(self, message: str) -> None:
        status = self._status
        if status is None:
            return
        if callable(status) and not isinstance(status, (QLabel, StatusBusyRow)):
            status(message)
            return
        if isinstance(status, StatusBusyRow):
            status.setText(message)
            return
        if isinstance(status, QLabel):
            status.setText(message)
