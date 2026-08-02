"""Farm health status badge for dashboard party tiles."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QSizePolicy

from ic_gamedata.gem_farm.models import FarmHealthStatus
from ic_ui.theme import SUCCESS, TEXT_MUTED, WARN, WARN_BAR


def farm_health_badge_stylesheet(level: str) -> str:
    colors = {
        "ok": (SUCCESS, "#14532d"),
        "warning": (WARN, "#78350f"),
        "critical": (WARN_BAR, "#7f1d1d"),
    }
    fg, border = colors.get(level, (TEXT_MUTED, "#3f3f46"))
    return (
        f"color: {fg}; background: #3f3f46; border: 1px solid {border}; "
        "border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
    )


def farm_health_badge_text(status: FarmHealthStatus | None) -> str:
    if status is None or not status.monitoring:
        return ""
    if status.level == "ok":
        return "Farm OK"
    if status.level == "warning":
        return "Farm !"
    if status.level == "critical":
        return "Farm !!"
    return ""


def farm_health_tooltip(status: FarmHealthStatus | None) -> str:
    if status is None:
        return ""
    if not status.monitoring:
        return "Farm health: niet actief (geen gem-farm context)."
    if not status.alerts:
        return "Farm health: OK — geen actieve waarschuwingen."
    lines = [f"[{alert.severity}] {alert.message}" for alert in status.alerts]
    return "Farm health:\n" + "\n".join(lines)


def apply_farm_health_badge(label: QLabel, status: FarmHealthStatus | None) -> None:
    text = farm_health_badge_text(status)
    if not text:
        label.hide()
        return
    level = status.level if status is not None else "ok"
    label.setText(text)
    label.setToolTip(farm_health_tooltip(status))
    label.setStyleSheet(farm_health_badge_stylesheet(level))
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    label.show()
