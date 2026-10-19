"""Shared advisor card/label widgets used by Party Advisor and Specializations tabs."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ic_ui import theme as ui_theme
from ic_ui.theme import (
    PORTRAIT_H,
    PORTRAIT_W,
    advisor_accent_stylesheet,
    advisor_badge_stylesheet,
    advisor_bud_pill_stylesheet,
    advisor_card_stylesheet,
    advisor_speed_pill_stylesheet,
    advisor_text_styles,
    apply_card_shadow,
    formation_board_stylesheet,
    portrait_placeholder_stylesheet,
    status_pill_dot_stylesheet,
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


def rounded_portrait_pixmap(
    source: QPixmap,
    width: int,
    height: int,
    device_pixel_ratio: float,
    *,
    radius: float = 10.0,
) -> QPixmap:
    """Center-crop and clip to a rounded rect (stylesheets don't clip pixmaps)."""
    fitted = fit_portrait_pixmap(source, width, height, device_pixel_ratio)
    target_w = max(1, int(width * device_pixel_ratio))
    target_h = max(1, int(height * device_pixel_ratio))
    r = max(1.0, radius * device_pixel_ratio)
    result = QPixmap(target_w, target_h)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, target_w, target_h, r, r)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, fitted)
    painter.end()
    result.setDevicePixelRatio(device_pixel_ratio)
    return result


def circular_portrait_pixmap(
    source: QPixmap, size: int, device_pixel_ratio: float
) -> QPixmap:
    """Backward-compatible alias: soft-rounded square portrait."""
    return rounded_portrait_pixmap(source, size, size, device_pixel_ratio)


class FormationSeatCard(QFrame):
    clicked = Signal(int)

    def __init__(
        self,
        seat: int,
        parent: QWidget | None = None,
        *,
        clickable: bool = True,
    ) -> None:
        super().__init__(parent)
        self._seat = seat
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._seat)
        super().mousePressEvent(event)


def _legend_swatch(color: str, *, border: str | None = None) -> QLabel:
    swatch = QLabel()
    swatch.setFixedSize(12, 12)
    edge = border or color
    swatch.setStyleSheet(
        f"background: {color}; border: 2px solid {edge}; border-radius: 3px;"
    )
    return swatch


def _legend_item(color: str, label: str, *, border: str | None = None) -> QWidget:
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    row.addWidget(_legend_swatch(color, border=border))
    row.addWidget(advisor_lbl(label, kind="muted"))
    return wrap


def formation_board_legend(
    *,
    issue_border_label: str = "aandachtspunt",
    lang: str = "nl",
) -> QWidget:
    """Explain zone backgrounds and border colors used on formation cards."""
    if lang == "en":
        zone_labels = (
            ("back", "back (away from enemies)"),
            ("mid", "mid"),
            ("front", "front (toward enemies)"),
        )
        border_items = (
            (ui_theme.BUD_BORDER, "BUD / carry", ui_theme.BG_HOVER),
            (ui_theme.ISSUE_BORDER, issue_border_label, ui_theme.BG_HOVER),
            (ui_theme.BORDER_HOVER, "normal", ui_theme.BG_HOVER),
        )
        title = "Legend"
        note = "Card colors only — no connection lines are drawn between seats."
    else:
        zone_labels = (
            ("back", "back (van vijanden af)"),
            ("mid", "mid"),
            ("front", "front (richting vijanden)"),
        )
        border_items = (
            (ui_theme.BUD_BORDER, "BUD / carry", ui_theme.BG_HOVER),
            (ui_theme.ISSUE_BORDER, issue_border_label, ui_theme.BG_HOVER),
            (ui_theme.BORDER_HOVER, "normaal", ui_theme.BG_HOVER),
        )
        title = "Legenda"
        note = (
            "Alleen kaartkleuren betekenen iets — er worden geen "
            "verbindingslijnen tussen seats getekend."
        )

    box = QWidget()
    root = QVBoxLayout(box)
    root.setContentsMargins(0, 4, 0, 0)
    root.setSpacing(4)
    root.addWidget(advisor_lbl(title, kind="muted"))

    zones = QWidget()
    zone_row = QHBoxLayout(zones)
    zone_row.setContentsMargins(0, 0, 0, 0)
    zone_row.setSpacing(10)
    zone_row.addWidget(advisor_lbl("Zone:" if lang == "en" else "Zone:", kind="muted"))
    for zone_key, zone_label in zone_labels:
        bg = ui_theme.FORMATION_ZONE_BG.get(zone_key, ui_theme.BG_HOVER)
        zone_row.addWidget(_legend_item(bg, zone_label, border=ui_theme.BORDER_HOVER))
    zone_row.addStretch(1)
    root.addWidget(zones)

    borders = QWidget()
    border_row = QHBoxLayout(borders)
    border_row.setContentsMargins(0, 0, 0, 0)
    border_row.setSpacing(10)
    border_row.addWidget(advisor_lbl("Rand:" if lang != "en" else "Border:", kind="muted"))
    for edge, label, fill in border_items:
        border_row.addWidget(_legend_item(fill, label, border=edge))
    border_row.addStretch(1)
    root.addWidget(borders)
    root.addWidget(advisor_lbl(note, kind="muted"))
    return box


def add_formation_board(
    layout: QVBoxLayout,
    nodes,
    *,
    role_label,
    intro: str,
    title: str | None = None,
    on_seat_clicked=None,
    node_caption=None,
    node_subcaption=None,
    show_legend: bool = True,
    issue_border_label: str | None = None,
    legend_lang: str = "nl",
) -> None:
    """Render a formation grid board into ``layout`` (active or recommended).

    ``node_caption(node)`` / ``node_subcaption(node)`` override the default
    ``Slot {seat} · {zone}`` header when provided (e.g. AI preview separates
    physical position from champion F-seat).

    Card background = formation zone (back/mid/front). Border: blue = BUD,
    red = issue/changed (see ``issue_border_label``), grey = normal.
    No adjacency lines are drawn between seats.
    """
    if not nodes:
        card = advisor_card()
        advisor_card_layout(card).addWidget(
            advisor_lbl("No formation positions available.", kind="muted")
        )
        layout.addWidget(card)
        return

    pad = 16
    card_w, card_h = (112, 72) if node_caption is not None else (100, 58)
    min_x = min(n.x for n in nodes)
    min_y = min(n.y for n in nodes)
    width = int(max(n.x for n in nodes) - min_x + card_w + pad * 2)
    height = int(max(n.y for n in nodes) - min_y + card_h + pad * 2)
    height = max(180, min(height, 520))
    width = max(320, width)

    shell = advisor_card()
    shell_lyt = advisor_card_layout(shell)
    if title:
        shell_lyt.addWidget(advisor_lbl(title, kind="subtitle"))
    shell_lyt.addWidget(advisor_lbl(intro, kind="muted"))

    scroll = QScrollArea()
    scroll.setWidgetResizable(False)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setFixedHeight(height)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

    board = QWidget()
    board.setFixedSize(width, height)
    board.setStyleSheet(formation_board_stylesheet())

    clickable = on_seat_clicked is not None
    for node in nodes:
        x = int((node.x - min_x) + pad)
        y = int((node.y - min_y) + pad)
        zone_bg = ui_theme.FORMATION_ZONE_BG.get(node.zone, ui_theme.BG_HOVER)
        border = (
            ui_theme.ISSUE_BORDER
            if node.has_issue
            else (ui_theme.BUD_BORDER if node.is_bud else ui_theme.BORDER_HOVER)
        )
        role = node.effective_role or node.inferred_role or "flex"

        seat_frame = FormationSeatCard(node.seat, board, clickable=clickable)
        seat_frame.setGeometry(x, y, card_w, card_h)
        hover = (
            f"QFrame:hover {{ border-color: {ui_theme.ACCENT}; }}" if clickable else ""
        )
        seat_frame.setStyleSheet(
            f"QFrame {{ background: {zone_bg}; border: 1px solid {border}; border-radius: 8px; }}"
            f"{hover}"
        )
        if on_seat_clicked is not None:
            seat_frame.clicked.connect(on_seat_clicked)

        seat_lyt = QVBoxLayout(seat_frame)
        seat_lyt.setContentsMargins(6, 4, 6, 4)
        seat_lyt.setSpacing(2)
        if node_caption is not None:
            caption = str(node_caption(node) or "")
        else:
            caption = f"Slot {node.seat} · {node.zone}"
        seat_lyt.addWidget(advisor_lbl(caption, kind="muted"))
        if node_subcaption is not None:
            sub = str(node_subcaption(node) or "")
            if sub:
                seat_lyt.addWidget(advisor_lbl(sub, kind="muted"))
        name_lbl = advisor_lbl((node.hero_name or "?")[:14], kind="subtitle")
        if node.is_bud:
            name_lbl.setProperty("advisorKind", "seat_name")
            name_lbl.setStyleSheet(advisor_text_styles()["seat_name"])
        seat_lyt.addWidget(name_lbl)
        seat_lyt.addWidget(advisor_lbl(role_label(role), kind="muted"))

    scroll.setWidget(board)
    shell_lyt.addWidget(scroll)
    if show_legend:
        if issue_border_label is None:
            issue_border_label = (
                "attention / mismatch"
                if legend_lang == "en"
                else "aandachtspunt"
            )
        shell_lyt.addWidget(
            formation_board_legend(
                issue_border_label=issue_border_label,
                lang=legend_lang,
            )
        )
    layout.addWidget(shell)


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


def advisor_tag_pill(text: str, *, kind: str = "bud") -> QLabel:
    """Compact pill for BUD / Speed focus on seat cards."""
    lbl = QLabel(text)
    lbl.setProperty("advisorTagPill", kind)
    if kind == "speed":
        lbl.setStyleSheet(advisor_speed_pill_stylesheet())
    else:
        lbl.setStyleSheet(advisor_bud_pill_stylesheet())
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
    lbl.setPixmap(
        rounded_portrait_pixmap(
            source, width, height, widget_device_pixel_ratio(lbl)
        )
    )
    return lbl


def advisor_open_url(url: str) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl(url))


def advisor_link_btn(text: str, url: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("linkBtn")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFlat(True)
    btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    btn.clicked.connect(lambda _c=False, u=url: advisor_open_url(u))
    return btn


def advisor_divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setProperty("advisorDivider", True)
    line.setStyleSheet(f"background: {ui_theme.DIVIDER}; border: none;")
    return line


def advisor_card_layout(card: QFrame, *, compact: bool = False) -> QVBoxLayout:
    body = card.findChild(QWidget, "advisorCardBody")
    target = body if body is not None else card
    lyt = QVBoxLayout(target)
    if compact:
        # Slightly less bottom than top: last widgets (labels/buttons) already
        # carry font descent / button padding, which otherwise looks heavier.
        lyt.setContentsMargins(0, 8, 12, 6)
        lyt.setSpacing(4)
    else:
        lyt.setContentsMargins(0, 14, 16, 10)
        lyt.setSpacing(8)
    return lyt


def advisor_status_dot(color: str) -> QLabel:
    """Small status circle (same language as dashboard status pills)."""
    dot = QLabel()
    dot.setFixedSize(8, 8)
    dot.setProperty("advisorStatusDot", True)
    dot.setProperty("advisorStatusDotColor", color)
    dot.setStyleSheet(status_pill_dot_stylesheet(color))
    return dot


def advisor_card(
    *,
    highlight: bool = False,
    accent_bar: str | None = None,
    compact: bool = False,
    show_accent: bool = True,
) -> QFrame:
    card = QFrame()
    card.setObjectName("advisorCard")
    card.setFrameShape(QFrame.Shape.NoFrame)
    card.setProperty("advisorHighlight", highlight)
    card.setProperty("advisorAccentCustom", accent_bar is not None)
    card.setProperty("advisorCompact", compact)
    card.setProperty("advisorShowAccent", show_accent)
    bar_color = accent_bar or (ui_theme.WARN_BAR if highlight else ui_theme.DIVIDER)
    card.setProperty("advisorAccentColor", bar_color)
    card.setStyleSheet(advisor_card_stylesheet())
    apply_card_shadow(card, soft=compact)

    outer = QHBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(8 if compact else 10)

    if show_accent:
        accent = QFrame()
        accent.setObjectName("advisorAccent")
        accent.setStyleSheet(advisor_accent_stylesheet(bar_color))
        outer.addWidget(accent)
    else:
        # Keep left padding similar to accent + spacing when the bar is omitted.
        outer.setContentsMargins(12 if compact else 16, 0, 0, 0)

    body = QWidget()
    body.setObjectName("advisorCardBody")
    # Scope to this widget only — unscoped `border: none` wipes child QComboBox borders.
    body.setStyleSheet("QWidget#advisorCardBody { background: transparent; border: none; }")
    outer.addWidget(body, stretch=1)
    return card


def clear_advisor_layout(layout: QVBoxLayout) -> None:
    """Remove all items from an advisor results layout without leaving ghosts.

    ``QLayout.takeAt`` detaches widgets from the layout but leaves them as
    children of the parent. Calling only ``deleteLater`` keeps those orphans
    painted until the next event-loop tick — status/tips look refreshed while
    the champ overview still shows the previous party.
    """
    while layout.count() > 0:
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def advisor_section(layout: QVBoxLayout, text: str) -> None:
    lbl = QLabel(text)
    lbl.setProperty("advisorSection", True)
    lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 600; letter-spacing: 0.04em; "
        f"color: {ui_theme.TEXT_MUTED}; padding: 14px 4px 4px 4px; "
        f"border: none; background: transparent;"
    )
    layout.addWidget(lbl)


def add_next_actions_section(layout: QVBoxLayout, actions: object) -> None:
    """Render ranked next actions (replaces separate tip/insight card lists)."""
    items = tuple(actions or ())
    if not items:
        return
    advisor_section(layout, "Volgende acties")
    for index, action in enumerate(items, start=1):
        headline = getattr(action, "headline", None) or "Action"
        detail = getattr(action, "detail", None) or ""
        card = advisor_card(highlight=index == 1)
        lyt = advisor_card_layout(card)
        lyt.addWidget(advisor_lbl(f"{index}. {headline}", kind="subtitle"))
        if detail:
            lyt.addWidget(advisor_lbl(detail, kind="body"))
        layout.addWidget(card)


def add_gear_investment_section(layout: QVBoxLayout, advice: object | None) -> None:
    """Show which current-party champion should get item levels first."""
    if advice is None:
        return
    name = getattr(advice, "hero_name", None)
    if not name:
        return
    seat = getattr(advice, "seat", None)
    ilvl = getattr(advice, "ilvl", 0)
    reason = getattr(advice, "reason", "") or ""
    seat_bit = f" · seat {seat}" if seat is not None else ""
    advisor_section(layout, "Gear investment")
    card = advisor_card(highlight=True)
    lyt = advisor_card_layout(card)
    lyt.addWidget(
        advisor_lbl(f"Invest item levels first in {name}{seat_bit} (ilvl {ilvl})", kind="subtitle")
    )
    if reason:
        lyt.addWidget(advisor_lbl(f"Why: {reason}", kind="body"))
    layout.addWidget(card)


def refresh_advisor_chrome(root: QWidget) -> None:
    """Re-apply advisor local styles after a theme change."""
    styles = advisor_text_styles()
    for lbl in root.findChildren(QLabel):
        kind = lbl.property("advisorKind")
        if kind:
            lbl.setStyleSheet(styles.get(kind, styles["body"]))
        elif lbl.property("advisorBadge"):
            lbl.setStyleSheet(advisor_badge_stylesheet())
        elif lbl.property("advisorTagPill"):
            kind = str(lbl.property("advisorTagPill") or "bud")
            if kind == "speed":
                lbl.setStyleSheet(advisor_speed_pill_stylesheet())
            else:
                lbl.setStyleSheet(advisor_bud_pill_stylesheet())
        elif lbl.property("advisorPortrait"):
            lbl.setStyleSheet(portrait_placeholder_stylesheet())
        elif lbl.property("advisorSection"):
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 600; letter-spacing: 0.04em; "
                f"color: {ui_theme.TEXT_MUTED}; padding: 14px 4px 4px 4px; "
                f"border: none; background: transparent;"
            )
        elif lbl.property("advisorStatusDot"):
            color = str(lbl.property("advisorStatusDotColor") or ui_theme.TEXT_MUTED)
            lbl.setStyleSheet(status_pill_dot_stylesheet(color))
    for line in root.findChildren(QFrame):
        if line.property("advisorDivider"):
            line.setStyleSheet(f"background: {ui_theme.DIVIDER}; border: none;")
        if line.objectName() == "advisorCard":
            line.setStyleSheet(advisor_card_stylesheet())
            apply_card_shadow(line)
            body = line.findChild(QWidget, "advisorCardBody")
            if body is not None:
                body.setStyleSheet(
                    "QWidget#advisorCardBody { background: transparent; border: none; }"
                )
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
    role_combo.setObjectName("advisorRoleCombo")
    role_combo.setCursor(Qt.CursorShape.PointingHandCursor)
    role_combo.setToolTip("Choose the role for this seat")
    role_combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    role_combo.setMinimumContentsLength(8)
    for role in standard_roles:
        role_combo.addItem(role_label(role), role)
    cur_role = seat.effective_role or ""
    idx = role_combo.findData(cur_role)
    if idx >= 0:
        role_combo.setCurrentIndex(idx)
    inferred = role_label(seat.inferred_role)
    chosen = role_label(seat.chosen_role) if seat.chosen_role else None
    if chosen and seat.chosen_role != seat.inferred_role:
        hint = f"Suggested: {inferred} · Your pick: {chosen}"
    else:
        hint = f"Suggested: {inferred}"
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
    "add_formation_board",
    "formation_board_legend",
    "advisor_badge",
    "advisor_tag_pill",
    "advisor_card",
    "advisor_card_layout",
    "advisor_divider",
    "advisor_lbl",
    "advisor_link_btn",
    "advisor_open_url",
    "advisor_portrait",
    "advisor_role_combo",
    "advisor_section",
    "advisor_status_dot",
    "clear_advisor_layout",
    "circular_portrait_pixmap",
    "rounded_portrait_pixmap",
    "fit_portrait_pixmap",
    "refresh_advisor_chrome",
]
