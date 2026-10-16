"""Modern line icons for toolbar/action buttons (Lucide-like strokes)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap


def button_icon(kind: str, color: str, *, size: int = 16, dpr: float = 2.0) -> QIcon:
    """Return a crisp stroked icon for ``kind`` in ``color``."""
    px = max(16, int(size * max(dpr, 1.0)))
    image = QImage(px, px, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    pen = QPen(QColor(color))
    pen.setWidthF(max(1.6, px * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Work in a 24×24 logical canvas.
    scale = px / 24.0
    painter.scale(scale, scale)
    pen.setWidthF(max(1.5, 1.75))
    painter.setPen(pen)

    drawer = _DRAWERS.get(kind)
    if drawer is not None:
        drawer(painter)

    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr if dpr > 0 else 1.0)
    icon = QIcon()
    icon.addPixmap(pixmap)
    return icon


def _draw_start(p: QPainter) -> None:
    p.setBrush(p.pen().color())
    p.drawPolygon(
        [
            QPointF(8.5, 6.0),
            QPointF(18.5, 12.0),
            QPointF(8.5, 18.0),
        ]
    )


def _draw_stop(p: QPainter) -> None:
    p.setBrush(p.pen().color())
    p.drawRoundedRect(QRectF(7.0, 7.0, 10.0, 10.0), 1.5, 1.5)


def _draw_refresh(p: QPainter) -> None:
    # Circular arrow (reload).
    p.drawArc(QRectF(5.5, 5.5, 13.0, 13.0), 45 * 16, 270 * 16)
    p.setBrush(p.pen().color())
    p.drawPolygon(
        [
            QPointF(16.2, 5.2),
            QPointF(19.8, 8.0),
            QPointF(15.0, 9.4),
        ]
    )


def _draw_reset(p: QPainter) -> None:
    # Counter-clockwise rotate.
    p.drawArc(QRectF(5.5, 5.5, 13.0, 13.0), -40 * 16, -260 * 16)
    p.setBrush(p.pen().color())
    p.drawPolygon(
        [
            QPointF(7.0, 5.0),
            QPointF(5.0, 9.2),
            QPointF(9.8, 8.6),
        ]
    )


def _draw_save(p: QPainter) -> None:
    # Download-to-tray.
    p.drawLine(QPointF(12.0, 5.0), QPointF(12.0, 14.0))
    p.drawLine(QPointF(8.5, 11.0), QPointF(12.0, 14.5))
    p.drawLine(QPointF(15.5, 11.0), QPointF(12.0, 14.5))
    p.drawLine(QPointF(6.0, 18.0), QPointF(18.0, 18.0))
    p.drawLine(QPointF(6.0, 18.0), QPointF(6.0, 15.5))
    p.drawLine(QPointF(18.0, 18.0), QPointF(18.0, 15.5))


def _draw_copy(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(9.0, 5.5, 9.0, 11.0), 1.5, 1.5)
    p.drawRoundedRect(QRectF(6.0, 8.0, 9.0, 11.0), 1.5, 1.5)


def _draw_search(p: QPainter) -> None:
    p.drawEllipse(QRectF(5.5, 5.5, 10.0, 10.0))
    p.drawLine(QPointF(13.8, 13.8), QPointF(18.5, 18.5))


def _draw_analyze(p: QPainter) -> None:
    # Sparkles / insight.
    p.drawLine(QPointF(12.0, 4.5), QPointF(12.0, 7.5))
    p.drawLine(QPointF(12.0, 16.5), QPointF(12.0, 19.5))
    p.drawLine(QPointF(4.5, 12.0), QPointF(7.5, 12.0))
    p.drawLine(QPointF(16.5, 12.0), QPointF(19.5, 12.0))
    p.drawEllipse(QRectF(9.0, 9.0, 6.0, 6.0))
    p.drawLine(QPointF(7.2, 7.2), QPointF(8.8, 8.8))
    p.drawLine(QPointF(15.2, 15.2), QPointF(16.8, 16.8))
    p.drawLine(QPointF(16.8, 7.2), QPointF(15.2, 8.8))
    p.drawLine(QPointF(8.8, 15.2), QPointF(7.2, 16.8))


def _draw_roster(p: QPainter) -> None:
    # Person + up chevron.
    p.drawEllipse(QRectF(9.0, 5.0, 6.0, 6.0))
    p.drawArc(QRectF(6.0, 12.5, 12.0, 10.0), 20 * 16, 140 * 16)
    p.drawLine(QPointF(18.5, 10.5), QPointF(18.5, 16.5))
    p.drawLine(QPointF(16.2, 12.5), QPointF(18.5, 10.0))
    p.drawLine(QPointF(20.8, 12.5), QPointF(18.5, 10.0))


def _draw_select_all(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(5.0, 5.0, 14.0, 14.0), 2.0, 2.0)
    p.drawLine(QPointF(8.0, 12.0), QPointF(10.5, 14.5))
    p.drawLine(QPointF(10.5, 14.5), QPointF(16.0, 9.0))


def _draw_check(p: QPainter) -> None:
    # Simple success checkmark (no box).
    p.drawLine(QPointF(6.0, 12.5), QPointF(10.5, 17.0))
    p.drawLine(QPointF(10.5, 17.0), QPointF(18.5, 7.0))


def _draw_clear(p: QPainter) -> None:
    # Trash can.
    p.drawLine(QPointF(8.0, 9.0), QPointF(8.5, 18.0))
    p.drawLine(QPointF(16.0, 9.0), QPointF(15.5, 18.0))
    p.drawLine(QPointF(8.5, 18.0), QPointF(15.5, 18.0))
    p.drawLine(QPointF(7.0, 9.0), QPointF(17.0, 9.0))
    p.drawLine(QPointF(10.0, 6.5), QPointF(14.0, 6.5))
    p.drawLine(QPointF(12.0, 6.5), QPointF(12.0, 9.0))
    p.drawLine(QPointF(10.5, 11.5), QPointF(10.5, 15.5))
    p.drawLine(QPointF(13.5, 11.5), QPointF(13.5, 15.5))


def status_dot_icon(color: str, *, size: int = 10, dpr: float = 2.0) -> QIcon:
    """Filled circle for tab/status indicators."""
    px = max(10, int(size * max(dpr, 1.0)))
    image = QImage(px, px, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    # Leave a 1px margin so the circle doesn't clip.
    margin = max(1.0, px * 0.08)
    painter.drawEllipse(QRectF(margin, margin, px - 2 * margin, px - 2 * margin))
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr if dpr > 0 else 1.0)
    icon = QIcon()
    icon.addPixmap(pixmap)
    return icon


_DRAWERS = {
    "start": _draw_start,
    "stop": _draw_stop,
    "refresh": _draw_refresh,
    "reset": _draw_reset,
    "save": _draw_save,
    "copy": _draw_copy,
    "search": _draw_search,
    "analyze": _draw_analyze,
    "roster": _draw_roster,
    "select_all": _draw_select_all,
    "check": _draw_check,
    "clear": _draw_clear,
}
