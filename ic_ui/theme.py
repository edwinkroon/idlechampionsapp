"""Central design tokens and Qt stylesheets for the Idle Champions UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

ThemeMode = Literal["dark", "light"]

# --- General ---
DEFAULT_WINDOW_TITLE = "Idle Champions"
FKEY_FAMILIAR_COLOR = "#22c55e"

# Prefer Fluent UI text fonts (Windows 11), then classic Segoe, then cross-platform.
_UI_FONT_CANDIDATES = (
    "Segoe UI Variable Text",
    "Segoe UI Variable",
    "Segoe UI",
    "IBM Plex Sans",
    "Inter",
    "Helvetica Neue",
    "Arial",
)

_resolved_ui_font: str | None = None

# --- Layout (theme-independent) ---
PORTRAIT_W = 52
PORTRAIT_H = 72

_ThemeCallback = Callable[[ThemeMode], None]
_theme_listeners: list[_ThemeCallback] = []
_current_theme: ThemeMode = "dark"

_DARK: dict[str, object] = {
    "BG_PRIMARY": "transparent",
    "BG_PAGE_TOP": "#1e1e22",
    "BG_PAGE_BOTTOM": "#16161a",
    "BG_CARD": "#2a2a2e",
    "BG_CARD_TOP": "#303036",
    "BG_CARD_BOTTOM": "#26262a",
    "BG_INPUT": "#1f1f23",
    "BG_BADGE": "#3f3f46",
    "BG_HOVER": "#35353c",
    "BG_TAB": "#25252a",
    "BG_TAB_SELECTED": "#32323a",
    "TEXT_PRIMARY": "#e5e7eb",
    "TEXT_BODY": "#d1d5db",
    "TEXT_MUTED": "#9ca3af",
    "TEXT_BADGE": "#d1d5db",
    "ACCENT": "#818cf8",
    "ACCENT_HOVER": "#a5b4fc",
    "WARN": "#fbbf24",
    "WARN_BAR": "#f59e0b",
    "SUCCESS": "#4ade80",
    "FEAT_OWNED": "#fb923c",
    "FEAT_MISSING": "#f87171",
    # Idle/status labels must stay AA-readable on page/card backgrounds.
    "STATUS_IDLE": "#b4b4be",
    "STATUS_PAUSE": "#fbbf24",
    "STATUS_WAIT": "#93c5fd",
    "STATUS_ERROR": "#fca5a5",
    "STATUS_ACTIVE": "#86efac",
    "BORDER": "#3f3f46",
    "BORDER_HOVER": "#52525b",
    "DIVIDER": "#3f3f46",
    "BUD_BAR": "#818cf8",
    "PORTRAIT_BG": "#1f1f23",
    "SEAT_NAME": "#93c5fd",
    "ISSUE_BORDER": "#dc2626",
    "BUD_BORDER": "#1f6feb",
    "PLOT_BG": "#1f1f23",
    "SHADOW_COLOR": "#000000",
    "SHADOW_ALPHA": 90,
    "FORMATION_ZONE_BG": {
        "front": "#4a3030",
        "mid": "#454028",
        "back": "#2a3548",
    },
}

_LIGHT: dict[str, object] = {
    "BG_PRIMARY": "transparent",
    "BG_PAGE_TOP": "#f4f6fb",
    "BG_PAGE_BOTTOM": "#e8ecf4",
    "BG_CARD": "#ffffff",
    "BG_CARD_TOP": "#ffffff",
    "BG_CARD_BOTTOM": "#f8fafc",
    "BG_INPUT": "#f1f5f9",
    "BG_BADGE": "#e2e8f0",
    "BG_HOVER": "#e8eef7",
    "BG_TAB": "#e8ecf4",
    "BG_TAB_SELECTED": "#ffffff",
    "TEXT_PRIMARY": "#0f172a",
    "TEXT_BODY": "#334155",
    "TEXT_MUTED": "#556274",
    "TEXT_BADGE": "#334155",
    "ACCENT": "#6366f1",
    "ACCENT_HOVER": "#4f46e5",
    "WARN": "#b45309",
    "WARN_BAR": "#d97706",
    "SUCCESS": "#15803d",
    "FEAT_OWNED": "#c2410c",
    "FEAT_MISSING": "#b91c1c",
    "STATUS_IDLE": "#475569",
    "STATUS_PAUSE": "#b45309",
    "STATUS_WAIT": "#1d4ed8",
    "STATUS_ERROR": "#b91c1c",
    "STATUS_ACTIVE": "#166534",
    "BORDER": "#e2e8f0",
    "BORDER_HOVER": "#cbd5e1",
    "DIVIDER": "#e2e8f0",
    "BUD_BAR": "#6366f1",
    "PORTRAIT_BG": "#e2e8f0",
    "SEAT_NAME": "#2563eb",
    "ISSUE_BORDER": "#dc2626",
    "BUD_BORDER": "#2563eb",
    "PLOT_BG": "#f8fafc",
    "SHADOW_COLOR": "#0f172a",
    "SHADOW_ALPHA": 40,
    "FORMATION_ZONE_BG": {
        "front": "#fde8e8",
        "mid": "#fef3c7",
        "back": "#e0e7ff",
    },
}

_PALETTES: dict[ThemeMode, dict[str, object]] = {"dark": _DARK, "light": _LIGHT}

# Module-level tokens (mutated by apply_theme; prefer helpers / re-import for live switch).
BG_PRIMARY = str(_DARK["BG_PRIMARY"])
BG_PAGE_TOP = str(_DARK["BG_PAGE_TOP"])
BG_PAGE_BOTTOM = str(_DARK["BG_PAGE_BOTTOM"])
BG_CARD = str(_DARK["BG_CARD"])
BG_CARD_TOP = str(_DARK["BG_CARD_TOP"])
BG_CARD_BOTTOM = str(_DARK["BG_CARD_BOTTOM"])
BG_INPUT = str(_DARK["BG_INPUT"])
BG_BADGE = str(_DARK["BG_BADGE"])
BG_HOVER = str(_DARK["BG_HOVER"])
BG_TAB = str(_DARK["BG_TAB"])
BG_TAB_SELECTED = str(_DARK["BG_TAB_SELECTED"])
TEXT_PRIMARY = str(_DARK["TEXT_PRIMARY"])
TEXT_BODY = str(_DARK["TEXT_BODY"])
TEXT_MUTED = str(_DARK["TEXT_MUTED"])
TEXT_BADGE = str(_DARK["TEXT_BADGE"])
ACCENT = str(_DARK["ACCENT"])
ACCENT_HOVER = str(_DARK["ACCENT_HOVER"])
WARN = str(_DARK["WARN"])
WARN_BAR = str(_DARK["WARN_BAR"])
SUCCESS = str(_DARK["SUCCESS"])
FEAT_OWNED = str(_DARK["FEAT_OWNED"])
FEAT_MISSING = str(_DARK["FEAT_MISSING"])
STATUS_IDLE = str(_DARK["STATUS_IDLE"])
STATUS_PAUSE = str(_DARK["STATUS_PAUSE"])
STATUS_WAIT = str(_DARK["STATUS_WAIT"])
STATUS_ERROR = str(_DARK["STATUS_ERROR"])
STATUS_ACTIVE = str(_DARK["STATUS_ACTIVE"])
BORDER = str(_DARK["BORDER"])
BORDER_HOVER = str(_DARK["BORDER_HOVER"])
DIVIDER = str(_DARK["DIVIDER"])
BUD_BAR = str(_DARK["BUD_BAR"])
PORTRAIT_BG = str(_DARK["PORTRAIT_BG"])
SEAT_NAME = str(_DARK["SEAT_NAME"])
ISSUE_BORDER = str(_DARK["ISSUE_BORDER"])
BUD_BORDER = str(_DARK["BUD_BORDER"])
PLOT_BG = str(_DARK["PLOT_BG"])
SHADOW_COLOR = str(_DARK["SHADOW_COLOR"])
SHADOW_ALPHA = int(_DARK["SHADOW_ALPHA"])  # type: ignore[arg-type]
FORMATION_ZONE_BG: dict[str, str] = dict(_DARK["FORMATION_ZONE_BG"])  # type: ignore[arg-type]

# Backward-compatible aliases used during UI migration.
_ADVISOR_BG = BG_PRIMARY
_ADVISOR_CARD_BG = BG_CARD
_ADVISOR_TEXT = TEXT_PRIMARY
_ADVISOR_MUTED = TEXT_MUTED
_ADVISOR_BODY = TEXT_BODY
_ADVISOR_ACCENT = ACCENT
_ADVISOR_WARN = WARN
_ADVISOR_WARN_BAR = WARN_BAR
_ADVISOR_FEAT_ACTIVE = SUCCESS
_ADVISOR_FEAT_OWNED = FEAT_OWNED
_ADVISOR_FEAT_MISSING = FEAT_MISSING
_ADVISOR_PORTRAIT_W = PORTRAIT_W
_ADVISOR_PORTRAIT_H = PORTRAIT_H
_ADVISOR_DIVIDER = DIVIDER
_ADVISOR_BUD_BAR = BUD_BAR
_ADVISOR_BADGE_BG = BG_BADGE
_ADVISOR_BADGE_TEXT = TEXT_BADGE
_ADVISOR_INPUT_BG = BG_INPUT
_ADVISOR_INPUT_BORDER = BORDER
_FORMATION_ZONE_BG = FORMATION_ZONE_BG
_FKEY_FAMILIAR_COLOR = FKEY_FAMILIAR_COLOR


def current_theme() -> ThemeMode:
    return _current_theme


def on_theme_changed(callback: _ThemeCallback) -> None:
    """Register a listener invoked after each successful apply_theme."""
    if callback not in _theme_listeners:
        _theme_listeners.append(callback)


def _sync_aliases() -> None:
    global _ADVISOR_BG, _ADVISOR_CARD_BG, _ADVISOR_TEXT, _ADVISOR_MUTED, _ADVISOR_BODY
    global _ADVISOR_ACCENT, _ADVISOR_WARN, _ADVISOR_WARN_BAR, _ADVISOR_FEAT_ACTIVE
    global _ADVISOR_FEAT_OWNED, _ADVISOR_FEAT_MISSING, _ADVISOR_DIVIDER, _ADVISOR_BUD_BAR
    global _ADVISOR_BADGE_BG, _ADVISOR_BADGE_TEXT, _ADVISOR_INPUT_BG, _ADVISOR_INPUT_BORDER
    global _FORMATION_ZONE_BG, _FKEY_FAMILIAR_COLOR
    _ADVISOR_BG = BG_PRIMARY
    _ADVISOR_CARD_BG = BG_CARD
    _ADVISOR_TEXT = TEXT_PRIMARY
    _ADVISOR_MUTED = TEXT_MUTED
    _ADVISOR_BODY = TEXT_BODY
    _ADVISOR_ACCENT = ACCENT
    _ADVISOR_WARN = WARN
    _ADVISOR_WARN_BAR = WARN_BAR
    _ADVISOR_FEAT_ACTIVE = SUCCESS
    _ADVISOR_FEAT_OWNED = FEAT_OWNED
    _ADVISOR_FEAT_MISSING = FEAT_MISSING
    _ADVISOR_DIVIDER = DIVIDER
    _ADVISOR_BUD_BAR = BUD_BAR
    _ADVISOR_BADGE_BG = BG_BADGE
    _ADVISOR_BADGE_TEXT = TEXT_BADGE
    _ADVISOR_INPUT_BG = BG_INPUT
    _ADVISOR_INPUT_BORDER = BORDER
    _FORMATION_ZONE_BG = FORMATION_ZONE_BG
    _FKEY_FAMILIAR_COLOR = FKEY_FAMILIAR_COLOR


def _apply_tokens(mode: ThemeMode) -> None:
    global BG_PRIMARY, BG_PAGE_TOP, BG_PAGE_BOTTOM, BG_CARD, BG_CARD_TOP, BG_CARD_BOTTOM
    global BG_INPUT, BG_BADGE, BG_HOVER, BG_TAB, BG_TAB_SELECTED
    global TEXT_PRIMARY, TEXT_BODY, TEXT_MUTED, TEXT_BADGE
    global ACCENT, ACCENT_HOVER, WARN, WARN_BAR, SUCCESS, FEAT_OWNED, FEAT_MISSING
    global STATUS_IDLE, STATUS_PAUSE, STATUS_WAIT, STATUS_ERROR, STATUS_ACTIVE
    global BORDER, BORDER_HOVER, DIVIDER, BUD_BAR, PORTRAIT_BG
    global SEAT_NAME, ISSUE_BORDER, BUD_BORDER, PLOT_BG, SHADOW_COLOR, SHADOW_ALPHA
    global FORMATION_ZONE_BG, _current_theme

    palette = _PALETTES[mode]
    BG_PRIMARY = str(palette["BG_PRIMARY"])
    BG_PAGE_TOP = str(palette["BG_PAGE_TOP"])
    BG_PAGE_BOTTOM = str(palette["BG_PAGE_BOTTOM"])
    BG_CARD = str(palette["BG_CARD"])
    BG_CARD_TOP = str(palette["BG_CARD_TOP"])
    BG_CARD_BOTTOM = str(palette["BG_CARD_BOTTOM"])
    BG_INPUT = str(palette["BG_INPUT"])
    BG_BADGE = str(palette["BG_BADGE"])
    BG_HOVER = str(palette["BG_HOVER"])
    BG_TAB = str(palette["BG_TAB"])
    BG_TAB_SELECTED = str(palette["BG_TAB_SELECTED"])
    TEXT_PRIMARY = str(palette["TEXT_PRIMARY"])
    TEXT_BODY = str(palette["TEXT_BODY"])
    TEXT_MUTED = str(palette["TEXT_MUTED"])
    TEXT_BADGE = str(palette["TEXT_BADGE"])
    ACCENT = str(palette["ACCENT"])
    ACCENT_HOVER = str(palette["ACCENT_HOVER"])
    WARN = str(palette["WARN"])
    WARN_BAR = str(palette["WARN_BAR"])
    SUCCESS = str(palette["SUCCESS"])
    FEAT_OWNED = str(palette["FEAT_OWNED"])
    FEAT_MISSING = str(palette["FEAT_MISSING"])
    STATUS_IDLE = str(palette["STATUS_IDLE"])
    STATUS_PAUSE = str(palette["STATUS_PAUSE"])
    STATUS_WAIT = str(palette["STATUS_WAIT"])
    STATUS_ERROR = str(palette["STATUS_ERROR"])
    STATUS_ACTIVE = str(palette["STATUS_ACTIVE"])
    BORDER = str(palette["BORDER"])
    BORDER_HOVER = str(palette["BORDER_HOVER"])
    DIVIDER = str(palette["DIVIDER"])
    BUD_BAR = str(palette["BUD_BAR"])
    PORTRAIT_BG = str(palette["PORTRAIT_BG"])
    SEAT_NAME = str(palette["SEAT_NAME"])
    ISSUE_BORDER = str(palette["ISSUE_BORDER"])
    BUD_BORDER = str(palette["BUD_BORDER"])
    PLOT_BG = str(palette["PLOT_BG"])
    SHADOW_COLOR = str(palette["SHADOW_COLOR"])
    SHADOW_ALPHA = int(palette["SHADOW_ALPHA"])  # type: ignore[arg-type]
    FORMATION_ZONE_BG = dict(palette["FORMATION_ZONE_BG"])  # type: ignore[arg-type]
    _current_theme = mode
    _sync_aliases()


def resolve_ui_font_family() -> str:
    """Pick the most modern readable UI font available on this machine."""
    global _resolved_ui_font
    if _resolved_ui_font is not None:
        return _resolved_ui_font
    families = set(QFontDatabase.families())
    for name in _UI_FONT_CANDIDATES:
        if name in families:
            _resolved_ui_font = name
            break
    else:
        _resolved_ui_font = QFont().defaultFamily() or "Segoe UI"
    return _resolved_ui_font


def apply_app_font(app: QApplication | None = None) -> QFont:
    """Apply the app-wide UI font (Fluent-style, readable at dashboard sizes)."""
    target = app or QApplication.instance()
    family = resolve_ui_font_family()
    font = QFont(family)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    # ~13px body; Variable Text is tuned for UI at this size.
    font.setPointSize(10)
    if target is not None:
        target.setFont(font)
    return font


def apply_theme(mode: ThemeMode, app: QApplication | None = None) -> None:
    """Update tokens, apply the global stylesheet, and notify listeners."""
    if mode not in _PALETTES:
        mode = "dark"
    _apply_tokens(mode)
    target = app or QApplication.instance()
    if target is not None:
        apply_app_font(target)
        target.setStyleSheet(global_app_stylesheet())
    for callback in list(_theme_listeners):
        try:
            callback(mode)
        except Exception:
            pass


def card_background_qss() -> str:
    return (
        f"qlineargradient(x1:0, y1:0, x2:0, y2:1, "
        f"stop:0 {BG_CARD_TOP}, stop:1 {BG_CARD_BOTTOM})"
    )


def apply_card_shadow(widget: QWidget, *, blur: float = 18.0, y_offset: float = 3.0) -> None:
    """Attach a soft drop shadow suitable for cards."""
    effect = QGraphicsDropShadowEffect(widget)
    color = QColor(SHADOW_COLOR)
    color.setAlpha(SHADOW_ALPHA)
    effect.setColor(color)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    widget.setGraphicsEffect(effect)


def _assets_dir() -> Path:
    path = Path(__file__).resolve().parent / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _qss_image_url(path: Path) -> str:
    return path.resolve().as_posix()


def _write_checkbox_checked_png(path: Path) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QPen

    image = QImage(32, 32, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#ffffff"))
    pen.setWidth(3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(
        [
            QPointF(7, 16),
            QPointF(13, 22),
            QPointF(25, 9),
        ]
    )
    painter.end()
    image.save(str(path), "PNG")


def _write_radio_checked_png(path: Path) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QImage, QPainter

    image = QImage(32, 32, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.drawEllipse(10, 10, 12, 12)
    painter.end()
    image.save(str(path), "PNG")


def _indicator_image_urls() -> tuple[str, str]:
    """Checked checkbox / radio indicator images for QSS (white glyph on accent fill)."""
    assets = _assets_dir()
    check_path = assets / "checkbox_checked.png"
    radio_path = assets / "radio_checked.png"
    if not check_path.exists():
        _write_checkbox_checked_png(check_path)
    if not radio_path.exists():
        _write_radio_checked_png(radio_path)
    return _qss_image_url(check_path), _qss_image_url(radio_path)


def global_app_stylesheet() -> str:
    page_bg = (
        f"qlineargradient(x1:0, y1:0, x2:0, y2:1, "
        f"stop:0 {BG_PAGE_TOP}, stop:1 {BG_PAGE_BOTTOM})"
    )
    card_bg = card_background_qss()
    check_img, radio_img = _indicator_image_urls()
    font_family = resolve_ui_font_family()
    return f"""
QMainWindow, QDialog {{
  background: {page_bg};
  color: {TEXT_PRIMARY};
}}
QWidget {{
  color: {TEXT_PRIMARY};
  font-family: "{font_family}";
  font-size: 13px;
}}
QTabWidget::pane {{
  border: 1px solid {BORDER};
  border-radius: 10px;
  top: -1px;
  background: {card_bg};
  padding: 8px;
}}
QTabBar::tab {{
  background: {BG_TAB};
  color: {TEXT_MUTED};
  border: 1px solid {BORDER};
  border-bottom: none;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  padding: 8px 16px;
  margin-right: 4px;
  min-width: 72px;
}}
QTabBar::tab:selected {{
  background: {BG_TAB_SELECTED};
  color: {TEXT_PRIMARY};
  font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
  background: {BG_HOVER};
  color: {TEXT_BODY};
}}
QGroupBox {{
  background: {card_bg};
  border: 1px solid {BORDER};
  border-radius: 12px;
  margin-top: 14px;
  padding: 14px 12px 12px 12px;
  font-weight: 600;
}}
QGroupBox::title {{
  subcontrol-origin: margin;
  left: 12px;
  padding: 0 6px;
  color: {TEXT_MUTED};
  font-size: 11px;
  font-weight: 600;
}}
QPushButton {{
  background: {BG_INPUT};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 6px 14px;
  min-height: 26px;
}}
QPushButton:hover {{
  background: {BG_HOVER};
  border-color: {BORDER_HOVER};
}}
QPushButton:pressed {{
  background: {BG_BADGE};
}}
QPushButton:disabled {{
  color: {TEXT_MUTED};
  background: {BG_TAB};
}}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
  background: {BG_INPUT};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 4px 10px;
  min-height: 26px;
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
  border-color: {BORDER_HOVER};
}}
QComboBox::drop-down {{
  border: none;
  width: 22px;
}}
QComboBox QAbstractItemView {{
  background: {BG_CARD};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  selection-background-color: {ACCENT};
  selection-color: #ffffff;
}}
QCheckBox, QRadioButton {{
  color: {TEXT_BODY};
  spacing: 8px;
}}
QCheckBox::indicator {{
  width: 16px;
  height: 16px;
  border: 1px solid {BORDER};
  border-radius: 4px;
  background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
  background: {ACCENT};
  border-color: {ACCENT};
  image: url("{check_img}");
}}
QCheckBox::indicator:disabled {{
  background: {BG_TAB};
  border-color: {BORDER};
}}
QCheckBox::indicator:checked:disabled {{
  background: {BORDER_HOVER};
  border-color: {BORDER_HOVER};
  image: url("{check_img}");
}}
QRadioButton::indicator {{
  width: 16px;
  height: 16px;
  border: 1px solid {BORDER};
  border-radius: 8px;
  background: {BG_INPUT};
}}
QRadioButton::indicator:checked {{
  background: {ACCENT};
  border-color: {ACCENT};
  image: url("{radio_img}");
}}
QScrollArea {{
  background: transparent;
  border: none;
}}
QScrollBar:vertical {{
  background: transparent;
  width: 10px;
  margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
  background: {BORDER_HOVER};
  border-radius: 5px;
  min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
  background: {TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
  background: none;
  height: 0;
}}
QScrollBar:horizontal {{
  background: transparent;
  height: 10px;
  margin: 0 4px 2px 4px;
}}
QScrollBar::handle:horizontal {{
  background: {BORDER_HOVER};
  border-radius: 5px;
  min-width: 28px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
  background: none;
  width: 0;
}}
QMenuBar {{
  background: {BG_PAGE_TOP};
  color: {TEXT_PRIMARY};
  border-bottom: 1px solid {BORDER};
  padding: 2px 4px;
}}
QMenuBar::item {{
  background: transparent;
  padding: 6px 10px;
  border-radius: 6px;
}}
QMenuBar::item:selected {{
  background: {BG_HOVER};
}}
QMenu {{
  background: {BG_CARD};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 4px;
}}
QMenu::item {{
  padding: 6px 24px 6px 12px;
  border-radius: 6px;
}}
QMenu::item:selected {{
  background: {BG_HOVER};
}}
QMenu::indicator {{
  width: 14px;
  height: 14px;
}}
QProgressBar {{
  background: {BG_BADGE};
  border: none;
  border-radius: 4px;
  text-align: center;
  color: {TEXT_PRIMARY};
}}
QProgressBar::chunk {{
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 #6366f1, stop:1 {BUD_BAR});
  border-radius: 4px;
}}
QLabel {{
  background: transparent;
}}
QStatusBar {{
  background: {BG_PAGE_BOTTOM};
  color: {TEXT_MUTED};
}}
QToolTip {{
  background: {BG_CARD};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  padding: 4px 8px;
}}
"""


def advisor_card_stylesheet() -> str:
    return f"""
QFrame#advisorCard {{
  background: {card_background_qss()};
  border: 1px solid {BORDER};
  border-radius: 12px;
}}
QFrame#advisorAccent {{
  border: none;
  min-width: 2px;
  max-width: 2px;
  margin: 14px 0 14px 16px;
  border-radius: 1px;
}}
QFrame#advisorCard QLabel {{
  border: none;
  background: transparent;
  color: {TEXT_PRIMARY};
  padding: 0;
  margin: 0;
}}
QFrame#advisorCard QComboBox {{
  border: 1px solid {BORDER};
  border-radius: 6px;
  padding: 4px 10px;
  background: {BG_INPUT};
  color: {TEXT_PRIMARY};
  min-height: 26px;
}}
QFrame#advisorCard QComboBox:hover {{
  border-color: {BORDER_HOVER};
}}
QFrame#advisorCard QPushButton#linkBtn {{
  border: 1px solid {BORDER};
  border-radius: 6px;
  background: {BG_INPUT};
  color: {TEXT_BADGE};
  padding: 4px 12px;
  font-size: 12px;
}}
QFrame#advisorCard QPushButton#linkBtn:hover {{
  background: {BG_HOVER};
  border-color: {BORDER_HOVER};
  color: {TEXT_PRIMARY};
}}
QFrame#advisorCard QPushButton#featToggle {{
  border: none;
  background: transparent;
  color: {TEXT_MUTED};
  font-size: 12px;
  font-weight: 500;
  text-align: left;
  padding: 4px 0 2px 0;
}}
QFrame#advisorCard QPushButton#featToggle:hover {{
  color: {ACCENT};
}}
"""


def advisor_accent_stylesheet(color: str) -> str:
    return f"""
QFrame#advisorAccent {{
  background: {color};
}}
"""


def advisor_text_styles() -> dict[str, str]:
    return {
        "title": f"font-size: 15px; font-weight: 600; color: {TEXT_PRIMARY};",
        "subtitle": f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};",
        "body": f"font-size: 13px; color: {TEXT_BODY};",
        "muted": f"font-size: 12px; color: {TEXT_MUTED};",
        "warn": f"font-size: 13px; color: {WARN}; font-weight: 500;",
        "insight": f"font-size: 13px; color: {TEXT_MUTED};",
        "feat_active": f"font-size: 13px; color: {SUCCESS}; font-weight: 500;",
        "feat_owned": f"font-size: 13px; color: {FEAT_OWNED}; font-weight: 500;",
        "feat_missing": f"font-size: 13px; color: {FEAT_MISSING}; font-weight: 500;",
        "spec_match": f"font-size: 13px; color: {SUCCESS}; font-weight: 500;",
        "spec_pending": f"font-size: 13px; color: {TEXT_BODY};",
        "spec_mismatch": f"font-size: 13px; color: {FEAT_MISSING}; font-weight: 500;",
        "seat_name": f"font-size: 13px; font-weight: 600; color: {SEAT_NAME};",
    }


def advisor_badge_stylesheet() -> str:
    return (
        f"font-size: 11px; color: {TEXT_BADGE}; background: {BG_BADGE}; "
        "border: none; border-radius: 10px; padding: 3px 10px;"
    )


def status_pill_stylesheet() -> str:
    return (
        f"font-size: 11px; color: {TEXT_BADGE}; background: {BG_BADGE}; "
        f"border: none; border-radius: 10px; padding: 4px 10px;"
    )


def portrait_placeholder_stylesheet() -> str:
    return (
        f"background: {PORTRAIT_BG}; border: 1px solid {DIVIDER}; border-radius: 6px;"
    )


def formation_board_stylesheet() -> str:
    return f"background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 8px;"


def area_progress_bar_stylesheet(*, complete: bool = False) -> str:
    """Dashboard area-goal progress bar (Modron or Adventure)."""
    if complete:
        chunk = (
            "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 #16a34a, stop:1 {SUCCESS})"
        )
    else:
        chunk = (
            "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 #6366f1, stop:1 {BUD_BAR})"
        )
    return (
        f"QProgressBar {{ background: {BG_BADGE}; border: none; border-radius: 4px; }}"
        f"QProgressBar::chunk {{ background: {chunk}; border-radius: 4px; }}"
    )
