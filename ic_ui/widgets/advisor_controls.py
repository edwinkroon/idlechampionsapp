"""Shared goal/context controls for Formation, Party Advisor, and Specializations."""

from __future__ import annotations

import weakref

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QWidget

from ic_gamedata.advice_goals import (
    GOAL_COMBO_ITEMS,
    UserGoalId,
    is_user_goal_id,
    migrate_stored_goal,
)

CONTEXT_ITEMS = (
    ("Campaign", "campaign"),
    ("Events", "events"),
    ("Push", "push"),
    ("Modron", "modron"),
)

_SETTINGS_ORG = "IdleChampions"
_SETTINGS_APP = "Companion"
# One prefs namespace for all advice tabs so Formation / Advisor / Specs agree.
_SHARED_SETTINGS_KEY = "advice"
_LEGACY_SETTINGS_KEYS = ("advisor", "formation", "specializations")


class AdvisorGoalContextBar(QWidget):
    """Goal + context selectors shared by advisor tabs.

    All bars share the same QSettings keys and keep combo values in sync while
    the app runs, so changing Goal on Formation also updates Advisor/Specs.
    """

    changed = Signal()
    _live: weakref.WeakSet[AdvisorGoalContextBar] = weakref.WeakSet()

    def __init__(
        self,
        *,
        include_formation: bool = False,
        settings_key: str = _SHARED_SETTINGS_KEY,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Prefer the shared key; callers may still pass a legacy key.
        self._settings_key = settings_key or _SHARED_SETTINGS_KEY
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._syncing = False
        self._needs_confirm = False
        self._migration_message: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._goal = QComboBox()
        self._goal.addItem("Kies doel…", None)
        for label, value in GOAL_COMBO_ITEMS:
            self._goal.addItem(label, value)

        self._context = QComboBox()
        for label, value in CONTEXT_ITEMS:
            self._context.addItem(label, value)

        self._formation: QCheckBox | None = None
        if include_formation:
            self._formation = QCheckBox("Formation")
            self._formation.setChecked(True)
            self._formation.toggled.connect(self._on_changed)

        self._goal.currentIndexChanged.connect(self._on_changed)
        # activated fires even when the same item is re-chosen — used to confirm
        # a migration proposal (e.g. bud → Push) without forcing a different goal.
        self._goal.activated.connect(self._on_goal_activated)
        self._context.currentIndexChanged.connect(self._on_changed)

        layout.addWidget(QLabel("Doel:"))
        layout.addWidget(self._goal)
        layout.addWidget(QLabel("Context:"))
        layout.addWidget(self._context)
        if self._formation is not None:
            layout.addWidget(self._formation)

        self._migrate_hint = QLabel("")
        self._migrate_hint.setWordWrap(True)
        self._migrate_hint.setStyleSheet("color: #b45309;")
        self._migrate_hint.setVisible(False)
        layout.addWidget(self._migrate_hint, stretch=1)
        layout.addStretch(1)

        self._load_prefs()
        AdvisorGoalContextBar._live.add(self)

    def _pref(self, name: str, *, key: str | None = None) -> str:
        return f"{key or self._settings_key}/{name}"

    def _read_pref(self, name: str, default: str | None = None) -> str | None:
        raw = self._settings.value(self._pref(name), None)
        if raw is None and self._settings_key == _SHARED_SETTINGS_KEY:
            for legacy in _LEGACY_SETTINGS_KEYS:
                raw = self._settings.value(self._pref(name, key=legacy), None)
                if raw is not None:
                    break
        if raw is None:
            return default
        return str(raw)

    def _load_prefs(self) -> None:
        raw_goal = self._read_pref("goal", None)
        context = self._read_pref("context", "campaign") or "campaign"
        confirmed = self._settings.value(
            f"{_SHARED_SETTINGS_KEY}/goal_confirmed", False, type=bool
        )
        migration = migrate_stored_goal(raw_goal)
        if migration.needs_confirm and not confirmed:
            self._needs_confirm = True
            self._migration_message = migration.message
            # bud → propose Push; gold/speed stay unselected until user chooses.
            goal = migration.proposed_id
        else:
            self._needs_confirm = False
            self._migration_message = None
            goal = migration.goal_id or (
                raw_goal if is_user_goal_id(raw_goal or "") else "push"
            )
        self._apply_values(goal, context, emit=False)
        self._update_migration_hint()
        if self._formation is not None:
            formation = self._settings.value(self._pref("formation"), True, type=bool)
            self._formation.blockSignals(True)
            self._formation.setChecked(bool(formation))
            self._formation.blockSignals(False)

    def _update_migration_hint(self) -> None:
        if self._needs_confirm and self._migration_message:
            self._migrate_hint.setText(self._migration_message)
            self._migrate_hint.setVisible(True)
        else:
            self._migrate_hint.clear()
            self._migrate_hint.setVisible(False)

    def _apply_values(
        self, goal: str | None, context: str, *, emit: bool
    ) -> None:
        self._syncing = True
        try:
            if goal is None:
                if self._goal.currentIndex() != 0:
                    self._goal.setCurrentIndex(0)
            else:
                g_idx = self._goal.findData(goal)
                if g_idx >= 0 and self._goal.currentIndex() != g_idx:
                    self._goal.setCurrentIndex(g_idx)
            c_idx = self._context.findData(context)
            if c_idx >= 0 and self._context.currentIndex() != c_idx:
                self._context.setCurrentIndex(c_idx)
        finally:
            self._syncing = False
        if emit:
            self.changed.emit()

    def _confirm_goal_choice(self, goal: str | None) -> None:
        if goal is None:
            return
        self._needs_confirm = False
        self._migration_message = None
        self._settings.setValue(f"{_SHARED_SETTINGS_KEY}/goal_confirmed", True)
        self._settings.setValue(f"{_SHARED_SETTINGS_KEY}/goal", goal)
        if self._settings_key != _SHARED_SETTINGS_KEY:
            self._settings.setValue(self._pref("goal"), goal)
        self._update_migration_hint()

    def _on_goal_activated(self, index: int) -> None:
        if self._syncing:
            return
        data = self._goal.itemData(index)
        if data is None:
            return
        self._confirm_goal_choice(str(data))
        for other in list(AdvisorGoalContextBar._live):
            if other is self:
                continue
            other._needs_confirm = False
            other._migration_message = None
            other._update_migration_hint()
        self.changed.emit()

    def _on_changed(self, *_args) -> None:
        if self._syncing:
            return
        goal = self.goal_or_none()
        context = self.context()
        # User interaction clears ambiguous legacy confirmation.
        if goal is not None:
            self._confirm_goal_choice(goal)
        self._settings.setValue(f"{_SHARED_SETTINGS_KEY}/context", context)
        if self._settings_key != _SHARED_SETTINGS_KEY:
            self._settings.setValue(self._pref("context"), context)
        if self._formation is not None:
            self._settings.setValue(self._pref("formation"), self.include_formation())
        self._update_migration_hint()
        for other in list(AdvisorGoalContextBar._live):
            if other is self:
                continue
            other._needs_confirm = self._needs_confirm
            other._migration_message = self._migration_message
            other._apply_values(goal, context, emit=True)
            other._update_migration_hint()
        self.changed.emit()

    def goal(self) -> UserGoalId | str:
        """Selected user goal id, or ``push`` scoring fallback when unset.

        Export/copy paths must also check ``needs_goal_confirm()`` / ``goal_or_none()``
        so ambiguous legacy values are not treated as a confirmed user choice.
        """
        data = self._goal.currentData()
        if data is None:
            return "push"
        return str(data)

    def goal_or_none(self) -> str | None:
        data = self._goal.currentData()
        return str(data) if data is not None else None

    def needs_goal_confirm(self) -> bool:
        return bool(self._needs_confirm) or self._goal.currentData() is None

    def migration_message(self) -> str | None:
        return self._migration_message

    def context(self) -> str:
        return self._context.currentData() or "campaign"

    def set_goal_context(self, goal: str, context: str | None = None) -> None:
        """Set goal/context from code (persists and syncs sibling bars)."""
        ctx = context if context is not None else self.context()
        self._apply_values(goal, ctx, emit=False)
        self._on_changed()

    def include_formation(self) -> bool:
        return self._formation.isChecked() if self._formation is not None else False
