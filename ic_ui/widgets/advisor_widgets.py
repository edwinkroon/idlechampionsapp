"""Shared advisor card/label widgets used by Party Advisor and Specializations tabs."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ic_ui.theme import (
    ACCENT,
    BG_BADGE,
    BG_INPUT,
    BORDER,
    BUD_BAR,
    DIVIDER,
    FORMATION_ZONE_BG,
    PORTRAIT_H,
    PORTRAIT_W,
    TEXT_BADGE,
    TEXT_MUTED,
    WARN_BAR,
    advisor_accent_stylesheet,
    advisor_card_stylesheet,
    advisor_text_styles,
    portrait_placeholder_stylesheet,
)


def widget_device_pixel_ratio(widget: QWidget) -> float:
    dpr = widget.devicePixelRatioF()
    if dpr > 0:
        return dpr
    screen = QApplication.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


def trim_transparent_pixmap(pixmap: QPixmap) -> QPixmap:
    """Crop empty padding so square portrait assets fill the avatar box."""
    image = pixmap.toImage()
    if image.isNull():
        return pixmap

    width = image.width()
    height = image.height()
    min_x, min_y = width, height
    max_x, max_y = -1, -1
    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 16:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < min_x or max_y < min_y:
        return pixmap
    return pixmap.copy(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def fit_portrait_pixmap(source: QPixmap, width: int, height: int, device_pixel_ratio: float) -> QPixmap:
    """Scale and center-crop a portrait to an exact display size."""
    target_w = max(1, int(width * device_pixel_ratio))
    target_h = max(1, int(height * device_pixel_ratio))
    trimmed = trim_transparent_pixmap(source)
    scaled = trimmed.scaled(
        target_w,
        target_h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    crop_x = max(0, (scaled.width() - target_w) // 2)
    crop_y = max(0, (scaled.height() - target_h) // 2)
    fitted = scaled.copy(crop_x, crop_y, target_w, target_h)
    fitted.setDevicePixelRatio(device_pixel_ratio)
    return fitted


class FormationSeatCard(QFrame):
    clicked = Signal(int)

    def __init__(self, seat: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seat = seat
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._seat)
        super().mousePressEvent(event)


def advisor_lbl(text: str, *, kind: str = "body") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    styles = advisor_text_styles()
    lbl.setStyleSheet(styles.get(kind, styles["body"]))
    return lbl


def advisor_badge(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 11px; color: {TEXT_BADGE}; background: {BG_BADGE}; "
        f"border: none; border-radius: 10px; padding: 3px 10px;"
    )
    return lbl


def advisor_portrait(hero_id: int, width: int = PORTRAIT_W, height: int = PORTRAIT_H) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(width, height)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(portrait_placeholder_stylesheet())
    try:
        from ic_gamedata.champion_portraits import champion_portrait_path
    except ImportError:
        return lbl
    path = champion_portrait_path(hero_id)
    if path is None:
        return lbl
    source = QPixmap(str(path))
    if source.isNull():
        return lbl
    lbl.setPixmap(fit_portrait_pixmap(source, width, height, widget_device_pixel_ratio(lbl)))
    return lbl


def advisor_open_url(url: str) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl(url))


def advisor_link_btn(text: str, url: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("linkBtn")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda _c=False, u=url: advisor_open_url(u))
    return btn


def advisor_divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {DIVIDER}; border: none;")
    return line


def advisor_card_layout(card: QFrame) -> QVBoxLayout:
    body = card.findChild(QWidget, "advisorCardBody")
    target = body if body is not None else card
    lyt = QVBoxLayout(target)
    lyt.setContentsMargins(0, 14, 16, 14)
    lyt.setSpacing(8)
    return lyt


def advisor_card(*, highlight: bool = False, accent_bar: str | None = None) -> QFrame:
    card = QFrame()
    card.setObjectName("advisorCard")
    card.setFrameShape(QFrame.Shape.NoFrame)
    card.setStyleSheet(advisor_card_stylesheet())

    bar_color = accent_bar or (WARN_BAR if highlight else DIVIDER)
    outer = QHBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(10)

    accent = QFrame()
    accent.setObjectName("advisorAccent")
    accent.setStyleSheet(advisor_accent_stylesheet(bar_color))
    outer.addWidget(accent)

    body = QWidget()
    body.setObjectName("advisorCardBody")
    body.setStyleSheet("background: transparent; border: none;")
    outer.addWidget(body, stretch=1)
    return card


def advisor_section(layout: QVBoxLayout, text: str) -> None:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 600; letter-spacing: 0.05em; "
        f"color: {TEXT_MUTED}; padding: 18px 4px 6px 4px; "
        f"border: none; background: transparent;"
    )
    layout.addWidget(lbl)


def advisor_role_combo(
    seat,
    standard_roles,
    role_label,
    on_role_selected,
) -> tuple[QComboBox, str]:
    role_combo = QComboBox()
    for role in standard_roles:
        role_combo.addItem(role_label(role), role)
    cur_role = seat.effective_role or ""
    idx = role_combo.findData(cur_role)
    if idx >= 0:
        role_combo.setCurrentIndex(idx)
    inferred = role_label(seat.inferred_role)
    chosen = role_label(seat.chosen_role) if seat.chosen_role else None
    if chosen and seat.chosen_role != seat.inferred_role:
        hint = f"Voorgesteld: {inferred} · Jouw keuze: {chosen}"
    else:
        hint = f"Voorgesteld: {inferred}"
    role_combo.currentIndexChanged.connect(
        lambda _i, hid=seat.hero_id, cb=role_combo: on_role_selected(hid, cb.currentData())
    )
    return role_combo, hint


__all__ = [
    "ACCENT",
    "BG_INPUT",
    "BORDER",
    "BUD_BAR",
    "DIVIDER",
    "FORMATION_ZONE_BG",
    "FormationSeatCard",
    "advisor_badge",
    "advisor_card",
    "advisor_card_layout",
    "advisor_divider",
    "advisor_lbl",
    "advisor_link_btn",
    "advisor_open_url",
    "advisor_portrait",
    "advisor_role_combo",
    "advisor_section",
    "fit_portrait_pixmap",
]
