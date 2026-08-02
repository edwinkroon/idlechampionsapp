"""Background specialization analysis."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal


class SpecializationsSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class SpecializationsRunnable(QRunnable):
    def __init__(
        self,
        goal: str,
        context: str,
        payload: dict,
        err: str | None = None,
        *,
        signals_parent: QObject | None = None,
    ) -> None:
        super().__init__()
        self.signals = SpecializationsSignals(signals_parent)
        self._goal = goal
        self._context = context
        self._payload = payload
        self._err = err

    def run(self) -> None:
        try:
            from ic_gamedata.party_advisor import analyze_party
            from ic_gamedata.party_advisor_specializations import advisor_run_goal
            from ic_gamedata.specializations import (
                load_specialization_rules,
                pending_specializations,
            )
        except ImportError as exc:
            self.signals.error.emit(f"Importfout: {exc}")
            return

        try:
            report = analyze_party(
                self._payload,
                goal=self._goal,
                context=self._context,
                include_specializations=True,
                include_formation=False,
            )
            rules = load_specialization_rules()
            pending = pending_specializations(
                self._payload,
                rules,
                context=self._context,
                run_goal=advisor_run_goal(self._goal, self._context),
            )
        except Exception as exc:
            self.signals.error.emit(f"Analysefout: {exc}")
            return

        self.signals.done.emit((self._payload, report, pending, self._err))
