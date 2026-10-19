"""Immutable settings snapshot for the automation worker."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class AutomationSettings:
    window_title: str = "Idle Champions"
    exclude_hwnd: int | None = None
    exclude_title: str = ""

    enable_level: bool = False
    level_interval_sec: int = 0
    level_champions: tuple[int, ...] = field(default_factory=tuple)

    enable_auto_progress: bool = False
    auto_progress_interval_sec: int = 180

    enable_grave: bool = False
    grave_interval_sec: int = 3

    enable_abilities: bool = False
    abilities_interval_sec: int = 10
    # Ultimate hotkeys 1-9 then 0 in live formation order (includes seat 11/12 champs).
    abilities_keys: tuple[str, ...] = field(
        default_factory=lambda: ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
    )

    enable_auto_click: bool = False
    auto_click_cps: int = 10

    # Fixed safety policy (not user-configurable in the UI).
    hover_gate: bool = True
    restore_focus: bool = True
    pause_on_ctrl: bool = True
    pause_when_over_app: bool = True
    pause_when_app_focused: bool = True
    prefer_game_already_focused: bool = True

    def with_updates(self, **kwargs) -> AutomationSettings:
        return replace(self, **kwargs)
