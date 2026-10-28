"""Ring buffer of recent UI actions for pasteable hang/diagnose reports.

Call ``note_ui_action`` from click/select handlers. Copying the report is done
from the main window corner button — keep notes short and user-facing.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque


@dataclass(frozen=True)
class UiAction:
    at: float
    message: str

    def line(self) -> str:
        stamp = time.strftime("%H:%M:%S", time.localtime(self.at))
        return f"{stamp}  {self.message}"


_MAX = 12
_actions: Deque[UiAction] = deque(maxlen=_MAX)


def note_ui_action(message: str) -> None:
    text = (message or "").strip()
    if not text:
        return
    _actions.append(UiAction(at=time.time(), message=text))


def recent_actions(*, limit: int = _MAX) -> tuple[UiAction, ...]:
    items = list(_actions)
    if limit < len(items):
        items = items[-limit:]
    return tuple(items)


def last_action() -> UiAction | None:
    return _actions[-1] if _actions else None


def clear_ui_actions() -> None:
    _actions.clear()


def format_diagnose_clipboard(
    *,
    active_tab: str,
    extra_lines: tuple[str, ...] = (),
) -> str:
    """Build a paste-ready block for the AI chat."""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    last = last_action()
    last_txt = last.line() if last is not None else "(nog geen actie gelogd)"
    recent = recent_actions()
    recent_block = (
        "\n".join(f"  - {a.line()}" for a in recent)
        if recent
        else "  - (leeg)"
    )
    extras = "\n".join(f"- {line}" for line in extra_lines if line) or "- (geen extra status)"
    return (
        "## Idle Champions Companion — UI diagnose\n"
        "Plak dit in de Cursor-chat als de app haperde of Not Responding toonde.\n"
        "\n"
        f"- Rapporttijd: {now}\n"
        f"- Actieve tab: {active_tab}\n"
        f"- Laatste actie: {last_txt}\n"
        f"{extras}\n"
        "- Recente acties (nieuwste onderaan):\n"
        f"{recent_block}\n"
    )
