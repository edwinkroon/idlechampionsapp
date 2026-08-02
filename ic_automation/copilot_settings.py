"""Settings for Co-Pilot formation key sending."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CopilotKeySettings:
    window_title: str = "Idle Champions"
    exclude_hwnd: int | None = None
    exclude_title: str = ""

    send_keys_enabled: bool = False
    allow_auto_progress_g: bool = True
    action_debounce_sec: float = 60.0

    hover_gate: bool = True
    restore_focus: bool = True
    pause_on_ctrl: bool = True
    pause_when_over_app: bool = True
    pause_when_app_focused: bool = True
    prefer_game_already_focused: bool = True

    def with_updates(self, **kwargs) -> CopilotKeySettings:
        return replace(self, **kwargs)
