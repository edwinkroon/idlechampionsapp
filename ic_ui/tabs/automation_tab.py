"""Automation settings, controls, and worker integration."""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import Qt, QSettings, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ic_automation import AutomationController, AutomationSettings, win_input
from ic_ui import theme as ui_theme
from ic_ui.theme import (
    DEFAULT_WINDOW_TITLE,
    apply_button_icon,
    on_theme_changed,
    status_pill_dot_stylesheet,
    style_danger_button,
    style_default_button,
    style_primary_button,
)
from ic_ui.widgets.option_visibility import bind_option_visibility

_SETTINGS_ORG = "IdleChampions"
_SETTINGS_APP = "Companion"
_SETTINGS_PREFIX = "automation/"
_ABILITY_SEATS: tuple[int, ...] = tuple(range(1, 13))
_ABILITY_HOTKEYS: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")


def classify_automation_indicator(text: str, kind: str) -> str:
    """Map a worker status line to paused | wait_focus | error | active."""
    lower = text.lower()
    if kind == "paused" or "paused" in lower or "gepauzeerd" in lower:
        return "paused"
    # Only real game-focus waits — not "waiting for formation sync".
    if (
        "focus the game" in lower
        or "waiting for game focus" in lower
        or "wacht op game focus" in lower
    ):
        return "wait_focus"
    if kind == "error":
        return "error"
    return "active"


@dataclass
class AutomationWidgets:
    level_enabled: QCheckBox
    level_interval_sec: QLineEdit
    auto_progress_enabled: QCheckBox
    auto_progress_interval_sec: QLineEdit
    grave_enabled: QCheckBox
    grave_interval_sec: QLineEdit
    abilities_enabled: QCheckBox
    abilities_interval_sec: QLineEdit
    abilities_keys: dict[int, QCheckBox]
    auto_click_enabled: QCheckBox
    auto_click_cps: QLineEdit
    level_fkeys: dict[int, QCheckBox]


class AutomationTab(QWidget):
    """Auto-level, auto-progress, and related game input automation."""

    running_changed = Signal(bool)
    indicator_changed = Signal(str)  # "off" | "on" | "paused"
    api_poll_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._paused = False
        self._indicator_state = "off"
        self._automation = AutomationController()
        self._formation_seats: frozenset[int] | None = None
        self._formation_party_id: int | None = None
        self._familiar_level_seats: frozenset[int] = frozenset()
        # party_id → seat → user wants this seat's ultimate when it is on the board.
        self._abilities_seats_by_party: dict[int, dict[int, bool]] = {}
        self._formation_ability_seats: frozenset[int] = frozenset()
        self._seat_ultimate_hotkeys: dict[int, str] = {}
        self._formation_poll_tick = 0
        self._last_payload: dict | None = None
        self._widgets: AutomationWidgets | None = None
        self._abilities_keys_grid: QGridLayout | None = None
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(400)
        self._persist_timer.timeout.connect(self._save_settings)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._poll_status)

        self._build_ui()
        self._load_settings()
        self._connect_persist_signals()
        on_theme_changed(self._apply_local_theme)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def indicator_state(self) -> str:
        return self._indicator_state

    def _sync_indicator_state(self) -> None:
        if not self._running:
            state = "off"
        elif self._paused:
            state = "paused"
        else:
            state = "on"
        if state == self._indicator_state:
            return
        self._indicator_state = state
        self.indicator_changed.emit(state)

    def set_formation_payload(self, payload: dict | None) -> None:
        self._last_payload = payload

    def sync_fkeys_from_payload(self, payload: dict | None) -> None:
        if payload is None:
            return
        self._last_payload = payload
        try:
            from ic_gamedata.familiar_seats import familiar_level_seats
            from ic_gamedata.formation_seats import active_formation_seats
        except ImportError:
            return
        party_id, seats = active_formation_seats(payload)
        familiar_seats = familiar_level_seats(payload)
        self._switch_ability_keys_for_party(party_id)
        self._apply_formation_fkeys(party_id, seats, familiar_seats)
        self._apply_ability_key_labels(payload)

    def stop(self) -> None:
        if not self._running:
            return
        self._automation.stop()
        self._status_timer.stop()
        self._set_running_ui(False)
        self._status_label.setText("Status: stopped")
        self._save_settings()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        button_row = QHBoxLayout()
        self._btn_start = QPushButton("Start")
        style_primary_button(self._btn_start)
        apply_button_icon(self._btn_start, "start")
        self._btn_start.setToolTip("Start automation with the current settings")
        self._btn_start.clicked.connect(self._start_automation)
        self._btn_stop = QPushButton("Stop")
        style_default_button(self._btn_stop)
        apply_button_icon(self._btn_stop, "stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.setToolTip("Stop all automation actions")
        self._btn_stop.clicked.connect(self.stop)
        button_row.addWidget(self._btn_start)
        button_row.addWidget(self._btn_stop)
        button_row.addStretch(1)
        root.addLayout(button_row)

        self._status_label = QLabel("Status: stopped")
        root.addWidget(self._status_label)

        indicator_row = QHBoxLayout()
        indicator_row.setContentsMargins(0, 0, 0, 0)
        indicator_row.setSpacing(8)
        self._focus_dot = QLabel()
        self._focus_dot.setFixedSize(8, 8)
        self._focus_label = QLabel("Stopped")
        self._focus_label.setStyleSheet(f"color: {ui_theme.STATUS_IDLE}; font-weight: bold;")
        indicator_row.addWidget(self._focus_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        indicator_row.addWidget(self._focus_label, stretch=1)
        root.addLayout(indicator_row)
        self._set_focus_indicator(ui_theme.STATUS_IDLE, "Stopped")

        tip = QLabel(
            "Safety (always on): only active with the mouse over the game and Idle Champions "
            "in the foreground. Hold Ctrl or move over this app to pause. "
            "Settings are saved automatically."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        root.addWidget(tip)

        # Same rounded panel language as Dashboard partiesPanel.
        scroll_host = QWidget()
        scroll_host.setObjectName("partiesScrollHost")
        scroll_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        scroll_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        host_layout = QVBoxLayout(scroll_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        host_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        panel = QFrame()
        panel.setObjectName("partiesPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        form_root = QVBoxLayout(panel)
        form_root.setContentsMargins(20, 20, 20, 20)
        form_root.setSpacing(12)
        form_root.addWidget(self._build_level_group())
        form_root.addWidget(self._build_actions_group())
        host_layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignTop)
        host_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(scroll_host)
        root.addWidget(scroll, stretch=1)
        self._finish_widgets()

    def _apply_local_theme(self, _mode: str = "dark") -> None:
        if not self._running:
            self._set_focus_indicator(ui_theme.STATUS_IDLE, "Stopped")
        elif self._widgets is not None:
            self._apply_formation_fkeys(
                self._formation_party_id,
                self._formation_seats or frozenset(),
                self._familiar_level_seats,
            )

    def _build_level_group(self) -> QGroupBox:
        group = QGroupBox("Leveling")
        outer = QVBoxLayout(group)
        outer.setSpacing(10)

        level_enabled = QCheckBox("Auto level (F12 down to F1)")
        level_enabled.setChecked(True)
        outer.addWidget(level_enabled)

        level_options = QWidget()
        level_options_layout = QVBoxLayout(level_options)
        level_options_layout.setContentsMargins(0, 0, 0, 0)
        level_options_layout.setSpacing(8)
        level_interval_sec = QLineEdit("0")
        row = QFormLayout()
        row.setSpacing(8)
        row.addRow("Level interval (seconds, 0 = as fast as possible):", level_interval_sec)
        level_options_layout.addLayout(row)

        limit_level_to_formation = QCheckBox("Limit leveling to active formation (auto-sync)")
        limit_level_to_formation.setChecked(True)
        limit_level_to_formation.toggled.connect(self._on_level_scope_changed)
        level_options_layout.addWidget(limit_level_to_formation)

        fkey_formation_label = QLabel(
            "All seats in the active formation (F-key checkboxes are ignored)."
        )
        fkey_formation_label.setWordWrap(True)
        level_options_layout.addWidget(fkey_formation_label)

        fkeys_box = QGroupBox("F-keys while leveling (manual selection only)")
        fkeys_outer = QVBoxLayout(fkeys_box)
        fkeys_outer.setSpacing(8)
        fkeys_grid = QGridLayout()
        fkeys_grid.setHorizontalSpacing(6)
        fkeys_grid.setVerticalSpacing(6)
        fkeys_grid.setContentsMargins(0, 0, 0, 0)
        for col in range(4):
            fkeys_grid.setColumnStretch(col, 0)
        fkeys_grid.setColumnStretch(4, 1)
        fkeys: dict[int, QCheckBox] = {}
        for i in range(1, 13):
            cb = QCheckBox(f"F{i}")
            cb.setChecked(False)
            fkeys[i] = cb
            fkeys_grid.addWidget(cb, (i - 1) // 4, (i - 1) % 4, Qt.AlignmentFlag.AlignLeft)
        btn_select_all = QPushButton("Select all")
        btn_select_all.setObjectName("compactBtn")
        apply_button_icon(btn_select_all, "select_all", size=16)
        btn_select_all.setToolTip("Enable all available F-keys")
        btn_select_all.clicked.connect(self._select_all_level_fkeys)
        # Same row as F9–F12, right-aligned in the stretch column.
        fkeys_grid.addWidget(
            btn_select_all,
            2,
            4,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        fkeys_outer.addLayout(fkeys_grid)
        level_options_layout.addWidget(fkeys_box)
        fkeys_box.setEnabled(False)
        self._fkeys_box = fkeys_box
        self._fkey_formation_label = fkey_formation_label
        self._limit_level_to_formation = limit_level_to_formation
        self._btn_select_all_fkeys = btn_select_all
        outer.addWidget(level_options)
        bind_option_visibility(level_enabled, level_options)

        self._w_level_enabled = level_enabled
        self._w_level_interval = level_interval_sec
        self._w_level_fkeys = fkeys
        return group

    def _build_actions_group(self) -> QGroupBox:
        group = QGroupBox("Progress & abilities")
        outer = QVBoxLayout(group)
        outer.setSpacing(10)

        auto_progress_enabled = QCheckBox("Auto progress (G key) automatically")
        auto_progress_enabled.setChecked(False)
        outer.addWidget(auto_progress_enabled)
        auto_progress_options = QWidget()
        auto_progress_options_layout = QVBoxLayout(auto_progress_options)
        auto_progress_options_layout.setContentsMargins(0, 0, 0, 0)
        auto_progress_interval_sec = QLineEdit("180")
        row = QFormLayout()
        row.addRow("Auto progress interval (seconds):", auto_progress_interval_sec)
        auto_progress_options_layout.addLayout(row)
        outer.addWidget(auto_progress_options)
        bind_option_visibility(auto_progress_enabled, auto_progress_options)

        grave_enabled = QCheckBox("Backtick (`) automatically")
        grave_enabled.setChecked(False)
        outer.addWidget(grave_enabled)
        grave_options = QWidget()
        grave_options_layout = QVBoxLayout(grave_options)
        grave_options_layout.setContentsMargins(0, 0, 0, 0)
        grave_interval_sec = QLineEdit("3")
        row = QFormLayout()
        row.addRow("Backtick interval (seconds):", grave_interval_sec)
        grave_options_layout.addLayout(row)
        outer.addWidget(grave_options)
        bind_option_visibility(grave_enabled, grave_options)

        abilities_enabled = QCheckBox("Special abilities automatically (timer mode)")
        abilities_enabled.setChecked(True)
        outer.addWidget(abilities_enabled)
        abilities_options = QWidget()
        abilities_options_layout = QVBoxLayout(abilities_options)
        abilities_options_layout.setContentsMargins(0, 0, 0, 0)
        abilities_options_layout.setSpacing(8)
        abilities_interval_sec = QLineEdit("10")
        row = QFormLayout()
        row.addRow("Abilities interval (seconds):", abilities_interval_sec)
        abilities_options_layout.addLayout(row)

        abilities_keys_label = QLabel(
            "Ultimates per seat (1–12). Hotkeys 1–0 follow who is on the board, "
            "so seat 11/12 also work when those champions are in the party:"
        )
        abilities_keys_label.setWordWrap(True)
        abilities_options_layout.addWidget(abilities_keys_label)
        abilities_keys_grid = QGridLayout()
        abilities_keys_grid.setHorizontalSpacing(12)
        abilities_keys_grid.setVerticalSpacing(4)
        abilities_keys_grid.setContentsMargins(0, 0, 0, 0)
        abilities_keys_grid.setColumnStretch(0, 1)
        abilities_keys_grid.setColumnStretch(1, 1)
        abilities_keys: dict[int, QCheckBox] = {}
        for index, seat in enumerate(_ABILITY_SEATS):
            cb = QCheckBox(f"Seat {seat}")
            cb.setChecked(True)
            cb.setEnabled(False)
            cb.setStyleSheet(
                f"QCheckBox {{ font-size: 11px; color: {ui_theme.TEXT_BODY}; }}"
                f"QCheckBox:disabled {{ color: {ui_theme.TEXT_MUTED}; }}"
            )
            abilities_keys[seat] = cb
            abilities_keys_grid.addWidget(
                cb, index // 2, index % 2, Qt.AlignmentFlag.AlignLeft
            )
        abilities_options_layout.addLayout(abilities_keys_grid)
        outer.addWidget(abilities_options)
        bind_option_visibility(abilities_enabled, abilities_options)

        auto_click_enabled = QCheckBox(
            "Mouse click damage (left click when mouse is over the game window)"
        )
        auto_click_enabled.setChecked(False)
        outer.addWidget(auto_click_enabled)
        auto_click_options = QWidget()
        auto_click_options_layout = QVBoxLayout(auto_click_options)
        auto_click_options_layout.setContentsMargins(0, 0, 0, 0)
        auto_click_cps = QLineEdit("10")
        row = QFormLayout()
        row.addRow("Clicks per second:", auto_click_cps)
        auto_click_options_layout.addLayout(row)
        outer.addWidget(auto_click_options)
        bind_option_visibility(auto_click_enabled, auto_click_options)

        self._w_auto_progress_enabled = auto_progress_enabled
        self._w_auto_progress_interval = auto_progress_interval_sec
        self._w_grave_enabled = grave_enabled
        self._w_grave_interval = grave_interval_sec
        self._w_abilities_enabled = abilities_enabled
        self._w_abilities_interval = abilities_interval_sec
        self._w_abilities_keys = abilities_keys
        self._abilities_keys_grid = abilities_keys_grid
        self._w_auto_click_enabled = auto_click_enabled
        self._w_auto_click_cps = auto_click_cps
        return group

    def _finish_widgets(self) -> None:
        self._widgets = AutomationWidgets(
            level_enabled=self._w_level_enabled,
            level_interval_sec=self._w_level_interval,
            auto_progress_enabled=self._w_auto_progress_enabled,
            auto_progress_interval_sec=self._w_auto_progress_interval,
            grave_enabled=self._w_grave_enabled,
            grave_interval_sec=self._w_grave_interval,
            abilities_enabled=self._w_abilities_enabled,
            abilities_interval_sec=self._w_abilities_interval,
            abilities_keys=self._w_abilities_keys,
            auto_click_enabled=self._w_auto_click_enabled,
            auto_click_cps=self._w_auto_click_cps,
            level_fkeys=self._w_level_fkeys,
        )

    def _connect_persist_signals(self) -> None:
        if self._widgets is None:
            return
        w = self._widgets
        for cb in (
            w.level_enabled,
            w.auto_progress_enabled,
            w.grave_enabled,
            w.abilities_enabled,
            w.auto_click_enabled,
            self._limit_level_to_formation,
            *w.level_fkeys.values(),
            *w.abilities_keys.values(),
        ):
            cb.toggled.connect(self._schedule_save_settings)
        for line in (
            w.level_interval_sec,
            w.auto_progress_interval_sec,
            w.grave_interval_sec,
            w.abilities_interval_sec,
            w.auto_click_cps,
        ):
            line.textChanged.connect(self._schedule_save_settings)
        w.abilities_enabled.toggled.connect(self._on_abilities_enabled_toggled)
        for cb in w.abilities_keys.values():
            cb.toggled.connect(self._on_ability_key_toggled)
        w.abilities_interval_sec.textChanged.connect(self._push_live_settings)

    def _schedule_save_settings(self, *_args) -> None:
        self._persist_timer.start()

    def _ability_seats_selection(self) -> tuple[int, ...]:
        """Checked seats that currently have a champion on the board."""
        w = self._widgets
        assert w is not None
        active = self._formation_ability_seats
        return tuple(
            seat
            for seat in _ABILITY_SEATS
            if seat in active and w.abilities_keys[seat].isChecked()
        )

    def _ability_keys_to_fire(self) -> tuple[str, ...]:
        """Keyboard keys for checked seats that are currently on the board."""
        keys: list[str] = []
        for seat in self._ability_seats_selection():
            hotkey = self._seat_ultimate_hotkeys.get(seat)
            if hotkey in _ABILITY_HOTKEYS:
                keys.append(hotkey)
        return tuple(keys)

    def _set_ability_seats_selection(self, prefs: dict[int, bool]) -> None:
        if self._widgets is None:
            return
        for seat, cb in self._widgets.abilities_keys.items():
            cb.blockSignals(True)
            cb.setChecked(bool(prefs.get(seat, True)))
            cb.blockSignals(False)

    def _remember_ability_keys_for_party(self, party_id: int | None) -> None:
        if party_id is None or self._widgets is None:
            return
        prefs = dict(self._abilities_seats_by_party.get(party_id) or {})
        for seat in self._formation_ability_seats:
            prefs[seat] = self._widgets.abilities_keys[seat].isChecked()
        self._abilities_seats_by_party[party_id] = prefs

    def _restore_ability_keys_for_party(self, party_id: int | None) -> None:
        if party_id is None or self._widgets is None:
            return
        prefs = self._abilities_seats_by_party.get(party_id)
        if prefs is None:
            prefs = {seat: True for seat in _ABILITY_SEATS}
            self._abilities_seats_by_party[party_id] = prefs
        self._set_ability_seats_selection(prefs)

    def _switch_ability_keys_for_party(self, party_id: int | None) -> None:
        if party_id == self._formation_party_id:
            return
        if self._formation_party_id is None and party_id is not None:
            # First known party after startup: restore saved prefs if any.
            # Do not remember yet — formation seats are applied right after this,
            # and remembering against an empty board would store an empty selection.
            if party_id in self._abilities_seats_by_party:
                self._restore_ability_keys_for_party(party_id)
        else:
            self._remember_ability_keys_for_party(self._formation_party_id)
            self._restore_ability_keys_for_party(party_id)
        self._schedule_save_settings()
        self._push_live_settings()

    def _load_abilities_keys_by_party(self) -> None:
        raw = self._settings.value(f"{_SETTINGS_PREFIX}abilities_seats_by_party", "")
        if not str(raw or "").strip():
            # Migrate older hotkey-based party prefs (seats 1-10 only).
            raw = self._settings.value(f"{_SETTINGS_PREFIX}abilities_keys_by_party", "")
        text = str(raw or "").strip()
        if not text:
            return
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        loaded: dict[int, dict[int, bool]] = {}
        for party_raw, seats_raw in data.items():
            try:
                party_id = int(party_raw)
            except (TypeError, ValueError):
                continue
            prefs: dict[int, bool] = {seat: True for seat in _ABILITY_SEATS}
            if isinstance(seats_raw, dict):
                for seat_raw, want in seats_raw.items():
                    try:
                        seat = int(seat_raw)
                    except (TypeError, ValueError):
                        continue
                    if seat in _ABILITY_SEATS:
                        prefs[seat] = bool(want)
            elif isinstance(seats_raw, list):
                # Legacy: list of selected seats / hotkeys.
                selected: set[int] = set()
                for item in seats_raw:
                    try:
                        seat = int(item)
                    except (TypeError, ValueError):
                        if str(item) == "0":
                            seat = 10
                        else:
                            continue
                    if seat in _ABILITY_SEATS:
                        selected.add(seat)
                if selected and max(selected) <= 10:
                    selected.update({11, 12})
                for seat in _ABILITY_SEATS:
                    prefs[seat] = seat in selected if selected else True
            else:
                continue
            loaded[party_id] = prefs
        self._abilities_seats_by_party = loaded

    def _save_abilities_keys_by_party(self) -> None:
        self._remember_ability_keys_for_party(self._formation_party_id)
        payload = {
            str(party_id): {str(seat): bool(want) for seat, want in sorted(prefs.items())}
            for party_id, prefs in sorted(self._abilities_seats_by_party.items())
        }
        self._settings.setValue(
            f"{_SETTINGS_PREFIX}abilities_seats_by_party",
            json.dumps(payload, separators=(",", ":")),
        )

    def _on_abilities_enabled_toggled(self, checked: bool) -> None:
        """Turning special abilities back on selects every occupied formation seat."""
        if checked and self._widgets is not None:
            for seat, cb in self._widgets.abilities_keys.items():
                if seat not in self._formation_ability_seats:
                    continue
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)
            self._remember_ability_keys_for_party(self._formation_party_id)
            self._schedule_save_settings()
        self._push_live_settings()

    def _on_ability_key_toggled(self, *_args) -> None:
        self._remember_ability_keys_for_party(self._formation_party_id)
        self._schedule_save_settings()
        self._push_live_settings()

    def _push_live_settings(self, *_args) -> None:
        """Push ability seat/interval changes to the worker without restarting."""
        if not self._running or self._widgets is None:
            return
        self._automation.update_settings(self._build_settings_snapshot())

    def _load_settings(self) -> None:
        if self._widgets is None:
            return
        w = self._widgets
        s = self._settings

        def _bool(key: str, default: bool) -> bool:
            return bool(s.value(f"{_SETTINGS_PREFIX}{key}", default, type=bool))

        def _text(key: str, default: str) -> str:
            return str(s.value(f"{_SETTINGS_PREFIX}{key}", default) or default)

        w.level_enabled.setChecked(_bool("level_enabled", True))
        w.level_interval_sec.setText(_text("level_interval_sec", "0"))
        self._limit_level_to_formation.setChecked(_bool("limit_level_to_formation", True))
        w.auto_progress_enabled.setChecked(_bool("auto_progress_enabled", False))
        w.auto_progress_interval_sec.setText(_text("auto_progress_interval_sec", "180"))
        w.grave_enabled.setChecked(_bool("grave_enabled", False))
        w.grave_interval_sec.setText(_text("grave_interval_sec", "3"))
        w.abilities_enabled.setChecked(_bool("abilities_enabled", True))
        w.abilities_interval_sec.setText(_text("abilities_interval_sec", "10"))
        self._load_abilities_keys_by_party()
        for seat, cb in w.abilities_keys.items():
            # Prefer seat prefs; fall back to legacy hotkey prefs for seats 1-10.
            legacy_key = "0" if seat == 10 else str(seat)
            default = _bool(f"ability_key_{legacy_key}", True) if seat <= 10 else True
            cb.setChecked(_bool(f"ability_seat_{seat}", default))
        w.auto_click_enabled.setChecked(_bool("auto_click_enabled", False))
        w.auto_click_cps.setText(_text("auto_click_cps", "10"))
        for i, cb in w.level_fkeys.items():
            cb.setChecked(_bool(f"fkey_{i}", False))
        self._on_level_scope_changed(self._limit_level_to_formation.isChecked())

    def _save_settings(self) -> None:
        if self._widgets is None:
            return
        w = self._widgets
        s = self._settings
        s.setValue(f"{_SETTINGS_PREFIX}level_enabled", w.level_enabled.isChecked())
        s.setValue(f"{_SETTINGS_PREFIX}level_interval_sec", w.level_interval_sec.text())
        s.setValue(
            f"{_SETTINGS_PREFIX}limit_level_to_formation",
            self._limit_level_to_formation.isChecked(),
        )
        s.setValue(
            f"{_SETTINGS_PREFIX}auto_progress_enabled", w.auto_progress_enabled.isChecked()
        )
        s.setValue(
            f"{_SETTINGS_PREFIX}auto_progress_interval_sec",
            w.auto_progress_interval_sec.text(),
        )
        s.setValue(f"{_SETTINGS_PREFIX}grave_enabled", w.grave_enabled.isChecked())
        s.setValue(f"{_SETTINGS_PREFIX}grave_interval_sec", w.grave_interval_sec.text())
        s.setValue(f"{_SETTINGS_PREFIX}abilities_enabled", w.abilities_enabled.isChecked())
        s.setValue(
            f"{_SETTINGS_PREFIX}abilities_interval_sec", w.abilities_interval_sec.text()
        )
        self._save_abilities_keys_by_party()
        for seat, cb in w.abilities_keys.items():
            s.setValue(f"{_SETTINGS_PREFIX}ability_seat_{seat}", cb.isChecked())
        s.setValue(f"{_SETTINGS_PREFIX}auto_click_enabled", w.auto_click_enabled.isChecked())
        s.setValue(f"{_SETTINGS_PREFIX}auto_click_cps", w.auto_click_cps.text())
        for i, cb in w.level_fkeys.items():
            s.setValue(f"{_SETTINGS_PREFIX}fkey_{i}", cb.isChecked())
        if not self._running:
            self._status_label.setText("Status: stopped · settings saved")

    @staticmethod
    def _to_int(line: QLineEdit, default: int) -> int:
        try:
            return int(float((line.text() or "").strip().replace(",", ".")))
        except ValueError:
            return default

    def _on_level_scope_changed(self, checked: bool) -> None:
        self._fkeys_box.setEnabled(not checked)
        if self._last_payload is not None:
            self.sync_fkeys_from_payload(self._last_payload)
        self._schedule_save_settings()

    def _select_all_level_fkeys(self) -> None:
        if self._widgets is None or not self._fkeys_box.isEnabled():
            return
        for cb in self._widgets.level_fkeys.values():
            if cb.isEnabled():
                cb.setChecked(True)
        self._schedule_save_settings()

    def _build_settings_snapshot(self) -> AutomationSettings:
        w = self._widgets
        assert w is not None
        # Actieve-formatie modus: alle formatie-seats, F-vinkjes negeren.
        if self._limit_level_to_formation.isChecked() and self._formation_seats:
            selected = tuple(i for i in range(12, 0, -1) if i in self._formation_seats)
        else:
            selected = tuple(
                i
                for i in range(12, 0, -1)
                if w.level_fkeys[i].isChecked() and w.level_fkeys[i].isEnabled()
            )
        if self._familiar_level_seats:
            selected = tuple(i for i in selected if i not in self._familiar_level_seats)
        window = self.window()
        hwnd = int(window.winId()) if window is not None else 0
        exclude_hwnd = win_input.toplevel_hwnd(hwnd)
        # Safety flags stay at AutomationSettings defaults (always on, not configurable).
        return AutomationSettings(
            window_title=DEFAULT_WINDOW_TITLE,
            exclude_hwnd=exclude_hwnd,
            exclude_title="",
            enable_level=w.level_enabled.isChecked(),
            level_interval_sec=max(0, self._to_int(w.level_interval_sec, 0)),
            level_champions=selected,
            enable_auto_progress=w.auto_progress_enabled.isChecked(),
            auto_progress_interval_sec=max(1, self._to_int(w.auto_progress_interval_sec, 180)),
            enable_grave=w.grave_enabled.isChecked(),
            grave_interval_sec=max(1, self._to_int(w.grave_interval_sec, 3)),
            enable_abilities=w.abilities_enabled.isChecked(),
            abilities_interval_sec=max(3, self._to_int(w.abilities_interval_sec, 10)),
            abilities_keys=self._ability_keys_to_fire(),
            enable_auto_click=w.auto_click_enabled.isChecked(),
            auto_click_cps=max(1, min(20, self._to_int(w.auto_click_cps, 10))),
        )

    def _set_running_ui(self, running: bool) -> None:
        self._running = running
        if not running:
            self._paused = False
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        if running:
            style_default_button(self._btn_start)
            style_danger_button(self._btn_stop)
        else:
            style_primary_button(self._btn_start)
            style_default_button(self._btn_stop)
        self.running_changed.emit(running)
        self._sync_indicator_state()
        if not running:
            self._set_focus_indicator(ui_theme.STATUS_IDLE, "Stopped")

    def _start_automation(self) -> None:
        if win_input.gw is None:
            QMessageBox.warning(
                self,
                "Missing dependency",
                "pygetwindow is missing. Install dependencies via requirements.txt.",
            )
            return
        self.api_poll_requested.emit()
        self._save_settings()
        settings = self._build_settings_snapshot()
        self._automation.start(settings)
        self._set_running_ui(True)
        self._status_label.setText("Status: active (worker)")
        self._status_timer.start()

    def _poll_status(self) -> None:
        if not self._running:
            return
        self._formation_poll_tick += 1
        if self._formation_poll_tick % 8 == 0 and self._last_payload is not None:
            self.sync_fkeys_from_payload(self._last_payload)
        self._automation.update_settings(self._build_settings_snapshot())
        event = self._automation.poll_status()
        if event is not None and event.text:
            self._status_label.setText(event.text)
            self._update_focus_indicator(event.text, event.kind)

    def _set_focus_indicator(self, color: str, text: str) -> None:
        self._focus_dot.setStyleSheet(status_pill_dot_stylesheet(color))
        self._focus_label.setText(text)
        self._focus_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _update_focus_indicator(self, text: str, kind: str) -> None:
        lower = text.lower()
        state = classify_automation_indicator(text, kind)
        paused = state == "paused"
        if paused:
            color = ui_theme.STATUS_PAUSE
            if "shift" in lower or "ctrl" in lower:
                label = "Paused — Ctrl held"
            elif "caps" in lower:
                label = "Paused — Caps Lock on"
            elif "mouse" in lower or "muis" in lower or "hover" in lower:
                label = "Paused — mouse over this app"
            elif "focus" in lower or "helper" in lower:
                label = "Paused — helper has focus"
            else:
                label = "Paused"
            self._set_focus_indicator(color, label)
        elif state == "wait_focus":
            self._set_focus_indicator(
                ui_theme.STATUS_WAIT,
                "Waiting for game focus — click in Idle Champions",
            )
        elif state == "error":
            self._set_focus_indicator(ui_theme.STATUS_ERROR, "Error — see status above")
        else:
            self._set_focus_indicator(ui_theme.STATUS_ACTIVE, "Active")
        self._paused = paused
        self._sync_indicator_state()

    def _apply_ability_key_labels(self, payload: dict | None) -> None:
        """Always show seats 1–12; enable those currently on the board with their hotkey."""
        if self._widgets is None:
            return
        labels: dict[int, str] = {}
        seat_hotkeys: dict[int, str] = {}
        if payload is not None:
            try:
                from ic_gamedata.ability_cooldowns import (
                    formation_ultimate_seat_hotkeys,
                    formation_ultimate_seat_labels,
                )
            except ImportError:
                pass
            else:
                labels = formation_ultimate_seat_labels(payload)
                seat_hotkeys = formation_ultimate_seat_hotkeys(payload)

        previous_active = self._formation_ability_seats
        self._seat_ultimate_hotkeys = dict(seat_hotkeys)
        self._formation_ability_seats = frozenset(seat_hotkeys)
        party_id = self._formation_party_id
        prefs = (
            self._abilities_seats_by_party.get(party_id, {})
            if party_id is not None
            else {}
        )

        for seat, cb in self._widgets.abilities_keys.items():
            in_formation = seat in seat_hotkeys
            was_in_formation = seat in previous_active
            detail = labels.get(seat) or ""
            hotkey = seat_hotkeys.get(seat)
            if detail:
                cb.setText(f"{seat}  {detail}")
            elif hotkey:
                cb.setText(f"{seat}  (toets {hotkey})")
            else:
                cb.setText(f"Seat {seat}")
            cb.setVisible(True)
            cb.setEnabled(in_formation)
            cb.blockSignals(True)
            if in_formation:
                if not was_in_formation:
                    # Seat just joined the board: restore saved pref or default on.
                    cb.setChecked(bool(prefs[seat]) if seat in prefs else True)
                # else: keep the user's current checked state
            else:
                cb.setChecked(False)
            cb.blockSignals(False)
            if detail:
                tip = f"Seat {seat}: {detail}"
            elif in_formation and hotkey:
                tip = f"Seat {seat} fires ultimate hotkey {hotkey}"
            else:
                tip = f"Seat {seat}: geen champion van deze seat in de formatie"
            cb.setToolTip(tip)

        # Keep party memory aligned with occupied seats only.
        self._remember_ability_keys_for_party(self._formation_party_id)

    def _apply_formation_fkeys(
        self,
        party_id: int | None,
        seats: frozenset[int],
        familiar_seats: frozenset[int] | None = None,
    ) -> None:
        if familiar_seats is None:
            familiar_seats = self._familiar_level_seats
        if self._widgets is None:
            return
        w = self._widgets
        limit_to_formation = self._limit_level_to_formation.isChecked()
        self._fkeys_box.setEnabled(not limit_to_formation)
        party_changed = party_id != self._formation_party_id
        if not seats:
            party_txt = f"party {party_id}" if party_id is not None else "active party"
            if limit_to_formation:
                self._fkey_formation_label.setText(
                    f"Formation {party_txt}: no seats found — waiting for API sync."
                )
            else:
                self._fkey_formation_label.setText(
                    f"Formation {party_txt}: no seats found — check F-keys manually."
                )
            if party_changed:
                self._formation_party_id = party_id
                self._formation_seats = frozenset()
                if limit_to_formation:
                    for i in range(1, 13):
                        w.level_fkeys[i].setChecked(False)
            return
        self._formation_party_id = party_id
        self._formation_seats = seats
        self._familiar_level_seats = familiar_seats
        for i in range(1, 13):
            cb = w.level_fkeys[i]
            has_familiar = i in familiar_seats
            font = cb.font()
            font.setBold(has_familiar)
            cb.setFont(font)
            if has_familiar:
                familiar = ui_theme.FKEY_FAMILIAR_COLOR
                cb.setToolTip("Familiar on this seat — F-key leveling skipped")
                cb.setStyleSheet(
                    f"QCheckBox {{ color: {familiar}; font-weight: 600; }}"
                    f"QCheckBox:disabled {{ color: {familiar}; }}"
                )
                cb.setChecked(False)
                cb.setEnabled(False)
            else:
                cb.setToolTip("")
                cb.setStyleSheet("")
                cb.setEnabled(not limit_to_formation)
                if limit_to_formation:
                    cb.setChecked(i in seats)
        seat_list = ", ".join(f"F{s}" for s in sorted(seats))
        party_txt = f"party {party_id}" if party_id is not None else "active party"
        blocked = sorted(seats & familiar_seats)
        if limit_to_formation:
            extra = ""
            if blocked:
                extra = f" · familiars not leveled: {', '.join(f'F{s}' for s in blocked)}"
            self._fkey_formation_label.setText(
                f"Formation {party_txt}: leveling {seat_list}{extra}."
            )
        else:
            self._fkey_formation_label.setText(
                f"Formation {party_txt} detected ({seat_list}) — manual F-key selection active."
            )
