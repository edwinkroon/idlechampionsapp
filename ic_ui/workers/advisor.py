"""Background party advisor analysis."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal


class AdvisorSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class AdvisorRunnable(QRunnable):
    def __init__(
        self,
        goal: str,
        context: str,
        include_formation: bool,
        payload: dict,
        err: str | None = None,
    ) -> None:
        super().__init__()
        self.signals = AdvisorSignals()
        self._goal = goal
        self._context = context
        self._include_formation = include_formation
        self._payload = payload
        self._err = err

    def run(self) -> None:
        try:
            from ic_gamedata.party_advisor import analyze_party
        except ImportError as exc:
            self.signals.error.emit(f"Importfout: {exc}")
            return

        try:
            report = analyze_party(
                self._payload,
                goal=self._goal,
                context=self._context,
                include_specializations=False,
                include_formation=self._include_formation,
            )
        except Exception as exc:
            self.signals.error.emit(f"Analysefout: {exc}")
            return

        self.signals.done.emit((self._payload, report, self._err))
