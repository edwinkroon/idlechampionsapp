"""Shared goal/context controls for Formation, Party Advisor, and Specializations."""

from __future__ import annotations

import weakref

from PySide6.QtCore import QSettings, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from ic_ui import theme as ui_theme

from ic_gamedata.advice_goals import (
    GOAL_COMBO_ITEMS,
    UserGoalId,
    is_user_goal_id,
    migrate_stored_goal,
)

CONTEXT_ITEMS = (
    ("Campagne", "campaign"),
    ("Events", "events"),
    ("Push", "push"),
    ("Modron", "modron"),
)

_SETTINGS_ORG = "IdleChampions"
_SETTINGS_APP = "Companion"
# One prefs namespace for all advice tabs so Formation / Advisor / Specs agree.
_SHARED_SETTINGS_KEY = "advice"
_LEGACY_SETTINGS_KEYS = ("advisor", "formation", "specializations")


def read_shared_advice_goal() -> str | None:
    """Goal id from shared QSettings (no UI). ``None`` if unset/ambiguous."""
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    raw = settings.value(f"{_SHARED_SETTINGS_KEY}/goal", None)
    if raw is None:
        for legacy in _LEGACY_SETTINGS_KEYS:
            raw = settings.value(f"{legacy}/goal", None)
            if raw is not None:
                break
    confirmed = settings.value(f"{_SHARED_SETTINGS_KEY}/goal_confirmed", False, type=bool)
    migration = migrate_stored_goal(str(raw) if raw is not None else None)
    if migration.needs_confirm and not confirmed:
        return None
    if migration.goal_id:
        return str(migration.goal_id)
    if raw is not None and is_user_goal_id(str(raw)):
        return str(raw)
    return None


def read_shared_advice_context() -> str:
    """Context id from shared QSettings (default ``campaign``)."""
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    raw = settings.value(f"{_SHARED_SETTINGS_KEY}/context", None)
    if raw is None:
        for legacy in _LEGACY_SETTINGS_KEYS:
            raw = settings.value(f"{legacy}/context", None)
            if raw is not None:
                break
    return str(raw or "campaign")


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
        inline_migration_hint: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Prefer the shared key; callers may still pass a legacy key.
        self._settings_key = settings_key or _SHARED_SETTINGS_KEY
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._syncing = False
        self._needs_confirm = False
        self._migration_message: str | None = None
        self._inline_migration_hint = inline_migration_hint
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._goal = QComboBox()
        self._goal.setMinimumContentsLength(16)
        self._goal.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._goal.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._goal.addItem("Kies doel…", None)
        for label, value in GOAL_COMBO_ITEMS:
            self._goal.addItem(label, value)

        self._context = QComboBox()
        self._context.setMinimumContentsLength(8)
        self._context.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._context.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        for label, value in CONTEXT_ITEMS:
            self._context.addItem(label, value)

        self._apply_combo_readable_palette(self._goal)
        self._apply_combo_readable_palette(self._context)

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

        self._goal_lbl = QLabel("Doel")
        self._context_lbl = QLabel("Context")
        layout.addWidget(self._goal_lbl)
        layout.addWidget(self._goal)
        layout.addWidget(self._context_lbl)
        layout.addWidget(self._context)
        self._apply_local_theme()
        ui_theme.on_theme_changed(self._on_theme_changed)
        if self._formation is not None:
            layout.addWidget(self._formation)

        self._migrate_hint = QLabel("")
        self._migrate_hint.setWordWrap(True)
        self._migrate_hint.setStyleSheet("color: #b45309;")
        self._migrate_hint.setVisible(False)
        if inline_migration_hint:
            layout.addWidget(self._migrate_hint, stretch=1)
        else:
            self._migrate_hint.setParent(self)
            self._migrate_hint.hide()

        self._load_prefs()
        AdvisorGoalContextBar._live.add(self)

    def _on_theme_changed(self, _mode: str) -> None:
        self._apply_local_theme()

    def _apply_local_theme(self) -> None:
        muted = f"color: {ui_theme.TEXT_MUTED};"
        self._goal_lbl.setStyleSheet(muted)
        self._context_lbl.setStyleSheet(muted)
        self._apply_combo_readable_palette(self._goal)
        self._apply_combo_readable_palette(self._context)

    @staticmethod
    def _apply_combo_readable_palette(combo: QComboBox) -> None:
        """Keep closed-state text readable under Windows QSS focus painting."""
        palette = combo.palette()
        text = QColor(ui_theme.TEXT_PRIMARY)
        base = QColor(ui_theme.BG_INPUT)
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            palette.setColor(group, QPalette.ColorRole.Text, text)
            palette.setColor(group, QPalette.ColorRole.WindowText, text)
            palette.setColor(group, QPalette.ColorRole.ButtonText, text)
            palette.setColor(group, QPalette.ColorRole.Base, base)
            palette.setColor(group, QPalette.ColorRole.Button, base)
            palette.setColor(group, QPalette.ColorRole.Window, base)
            # Focused closed combo must not flip to system HighlightedText.
            palette.setColor(group, QPalette.ColorRole.HighlightedText, text)
            palette.setColor(group, QPalette.ColorRole.Highlight, base)
        combo.setPalette(palette)

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
        if not self._inline_migration_hint:
            self._migrate_hint.clear()
            self._migrate_hint.setVisible(False)
            return
        if self._needs_confirm and self._migration_message:
            self._migrate_hint.setText(self._migration_message)
            self._migrate_hint.setVisible(True)
        else:
            self._migrate_hint.clear()
            self._migrate_hint.setVisible(False)

    def _apply_values(
        self, goal: str | None, context: str, *, emit: bool
    ) -> None:
        changed = False
        self._syncing = True
        try:
            if goal is None:
                if self._goal.currentIndex() != 0:
                    self._goal.setCurrentIndex(0)
                    changed = True
            else:
                g_idx = self._goal.findData(goal)
                if g_idx >= 0 and self._goal.currentIndex() != g_idx:
                    self._goal.setCurrentIndex(g_idx)
                    changed = True
            c_idx = self._context.findData(context)
            if c_idx >= 0 and self._context.currentIndex() != c_idx:
                self._context.setCurrentIndex(c_idx)
                changed = True
        finally:
            self._syncing = False
        if emit and changed:
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
        """Confirm migration when the same goal is re-chosen (no index change).

        A real index change already went through ``currentIndexChanged`` →
        ``_on_changed``; emitting again here caused a double refresh cascade.
        """
        if self._syncing:
            return
        data = self._goal.itemData(index)
        if data is None:
            return
        if not self._needs_confirm:
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
            # Emit only when sibling values actually change — source emits below.
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
