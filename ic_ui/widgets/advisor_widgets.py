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

from ic_ui import theme as ui_theme
from ic_ui.theme import (
    PORTRAIT_H,
    PORTRAIT_W,
    advisor_accent_stylesheet,
    advisor_badge_stylesheet,
    advisor_card_stylesheet,
    advisor_text_styles,
    apply_card_shadow,
    portrait_placeholder_stylesheet,
)

# Re-exports for callers that import tokens via this module (prefer ui_theme.* for live switch).
ACCENT = ui_theme.ACCENT
BG_INPUT = ui_theme.BG_INPUT
BORDER = ui_theme.BORDER
BUD_BAR = ui_theme.BUD_BAR
DIVIDER = ui_theme.DIVIDER
FORMATION_ZONE_BG = ui_theme.FORMATION_ZONE_BG


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
    lbl.setProperty("advisorKind", kind)
    styles = advisor_text_styles()
    lbl.setStyleSheet(styles.get(kind, styles["body"]))
    return lbl


def advisor_badge(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("advisorBadge", True)
    lbl.setStyleSheet(advisor_badge_stylesheet())
    return lbl


def advisor_portrait(hero_id: int, width: int = PORTRAIT_W, height: int = PORTRAIT_H) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(width, height)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setProperty("advisorPortrait", True)
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
    line.setProperty("advisorDivider", True)
    line.setStyleSheet(f"background: {ui_theme.DIVIDER}; border: none;")
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
    card.setProperty("advisorHighlight", highlight)
    card.setProperty("advisorAccentCustom", accent_bar is not None)
    bar_color = accent_bar or (ui_theme.WARN_BAR if highlight else ui_theme.DIVIDER)
    card.setProperty("advisorAccentColor", bar_color)
    card.setStyleSheet(advisor_card_stylesheet())
    apply_card_shadow(card)

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
    lbl.setProperty("advisorSection", True)
    lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 600; letter-spacing: 0.05em; "
        f"color: {ui_theme.TEXT_MUTED}; padding: 18px 4px 6px 4px; "
        f"border: none; background: transparent;"
    )
    layout.addWidget(lbl)


def refresh_advisor_chrome(root: QWidget) -> None:
    """Re-apply advisor local styles after a theme change."""
    styles = advisor_text_styles()
    for lbl in root.findChildren(QLabel):
        kind = lbl.property("advisorKind")
        if kind:
            lbl.setStyleSheet(styles.get(kind, styles["body"]))
        elif lbl.property("advisorBadge"):
            lbl.setStyleSheet(advisor_badge_stylesheet())
        elif lbl.property("advisorPortrait"):
            lbl.setStyleSheet(portrait_placeholder_stylesheet())
        elif lbl.property("advisorSection"):
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 600; letter-spacing: 0.05em; "
                f"color: {ui_theme.TEXT_MUTED}; padding: 18px 4px 6px 4px; "
                f"border: none; background: transparent;"
            )
    for line in root.findChildren(QFrame):
        if line.property("advisorDivider"):
            line.setStyleSheet(f"background: {ui_theme.DIVIDER}; border: none;")
        if line.objectName() == "advisorCard":
            line.setStyleSheet(advisor_card_stylesheet())
            apply_card_shadow(line)
            accent = line.findChild(QFrame, "advisorAccent")
            if accent is not None:
                if line.property("advisorAccentCustom"):
                    color = str(line.property("advisorAccentColor") or ui_theme.DIVIDER)
                elif line.property("advisorHighlight"):
                    color = ui_theme.WARN_BAR
                else:
                    color = ui_theme.DIVIDER
                line.setProperty("advisorAccentColor", color)
                accent.setStyleSheet(advisor_accent_stylesheet(color))


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
    "refresh_advisor_chrome",
]
