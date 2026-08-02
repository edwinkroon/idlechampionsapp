"""Central design tokens and Qt stylesheets for the Idle Champions UI."""

from __future__ import annotations

# --- General ---
DEFAULT_WINDOW_TITLE = "Idle Champions"
FKEY_FAMILIAR_COLOR = "#22c55e"

# --- Surfaces ---
BG_PRIMARY = "transparent"
BG_CARD = "#2d2d30"
BG_INPUT = "#252526"
BG_BADGE = "#3f3f46"
BG_HOVER = "#333338"

# --- Text ---
TEXT_PRIMARY = "#e5e7eb"
TEXT_BODY = "#d1d5db"
TEXT_MUTED = "#9ca3af"
TEXT_BADGE = "#d1d5db"

# --- Accent & status ---
ACCENT = "#818cf8"
WARN = "#fbbf24"
WARN_BAR = "#f59e0b"
SUCCESS = "#4ade80"
FEAT_OWNED = "#fb923c"
FEAT_MISSING = "#f87171"
STATUS_IDLE = "#6b7280"

# --- Borders & dividers ---
BORDER = "#3f3f46"
BORDER_HOVER = "#52525b"
DIVIDER = "#3f3f46"
BUD_BAR = "#818cf8"
PORTRAIT_BG = "#1f1f23"

# --- Layout ---
PORTRAIT_W = 52
PORTRAIT_H = 72

FORMATION_ZONE_BG = {
    "front": "#4a3030",
    "mid": "#454028",
    "back": "#2a3548",
}

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


def input_combobox_stylesheet() -> str:
    return f"""
QComboBox {{
  border: 1px solid {BORDER};
  border-radius: 6px;
  padding: 4px 28px 4px 10px;
  background: {BG_INPUT};
  color: {TEXT_PRIMARY};
  min-height: 28px;
}}
QComboBox:hover {{
  border-color: {BORDER_HOVER};
}}
QComboBox::drop-down {{
  subcontrol-origin: padding;
  subcontrol-position: top right;
  width: 24px;
  border-left: 1px solid {BORDER};
}}
QComboBox QAbstractItemView {{
  background: {BG_INPUT};
  color: {TEXT_PRIMARY};
  selection-background-color: {BG_HOVER};
  selection-color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  outline: none;
}}
"""


def advisor_card_stylesheet() -> str:
    return f"""
QFrame#advisorCard {{
  background: {BG_CARD};
  border: none;
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
    }


def advisor_badge_stylesheet() -> str:
    return (
        f"font-size: 11px; color: {TEXT_BADGE}; background: {BG_BADGE}; "
        "border-radius: 4px; padding: 2px 6px;"
    )


def portrait_placeholder_stylesheet() -> str:
    return (
        f"background: {PORTRAIT_BG}; border: 1px solid {DIVIDER}; border-radius: 6px;"
    )
