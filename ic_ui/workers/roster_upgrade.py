"""Background roster-upgrade suggestions for Party Advisor."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal


class RosterUpgradeSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class RosterUpgradeRunnable(QRunnable):
    def __init__(
        self,
        goal: str,
        context: str,
        payload: dict,
        *,
        signals_parent: QObject | None = None,
    ) -> None:
        super().__init__()
        self.signals = RosterUpgradeSignals(signals_parent)
        self._goal = goal
        self._context = context
        self._payload = payload

    def run(self) -> None:
        try:
            from ic_gamedata.roster_upgrade_advisor import suggest_roster_upgrades
        except ImportError as exc:
            self.signals.error.emit(f"Importfout: {exc}")
            return
        try:
            suggestions = suggest_roster_upgrades(
                self._payload,
                goal=self._goal,  # type: ignore[arg-type]
                context=self._context,  # type: ignore[arg-type]
            )
        except Exception as exc:
            self.signals.error.emit(f"Roster-upgrade fout: {exc}")
            return
        self.signals.done.emit(suggestions)
