"""Automation settings, controls, and worker integration."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ic_automation import AutomationController, AutomationSettings, win_input
from ic_ui import theme as ui_theme
from ic_ui.theme import DEFAULT_WINDOW_TITLE, on_theme_changed
from ic_ui.widgets.option_visibility import bind_option_visibility


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
    auto_click_enabled: QCheckBox
    auto_click_cps: QLineEdit
    hover_gate: QCheckBox
    pause_ctrl: QCheckBox
    pause_over_app: QCheckBox
    prefer_game_focus: QCheckBox
    level_fkeys: dict[int, QCheckBox]


class AutomationTab(QWidget):
    """Auto-level, auto-progress, and related game input automation."""

    running_changed = Signal(bool)
    api_poll_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._automation = AutomationController()
        self._formation_seats: frozenset[int] | None = None
        self._formation_party_id: int | None = None
        self._familiar_level_seats: frozenset[int] = frozenset()
        self._formation_poll_tick = 0
        self._last_payload: dict | None = None
        self._widgets: AutomationWidgets | None = None

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._poll_status)

        self._build_ui()
        on_theme_changed(self._apply_local_theme)

    @property
    def is_running(self) -> bool:
        return self._running

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
        self._apply_formation_fkeys(party_id, seats, familiar_seats)

    def stop(self) -> None:
        if not self._running:
            return
        self._automation.stop()
        self._status_timer.stop()
        self._set_running_ui(False)
        self._status_label.setText("Status: gestopt")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        button_row = QHBoxLayout()
        self._btn_start = QPushButton("Start")
        self._btn_start.clicked.connect(self._start_automation)
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self.stop)
        button_row.addWidget(self._btn_start)
        button_row.addWidget(self._btn_stop)
        button_row.addStretch(1)
        root.addLayout(button_row)

        self._status_label = QLabel("Status: gestopt")
        root.addWidget(self._status_label)

        self._focus_indicator = QLabel("● Gestopt")
        self._focus_indicator.setStyleSheet(
            f"color: {ui_theme.STATUS_IDLE}; font-weight: bold;"
        )
        root.addWidget(self._focus_indicator)

        tip = QLabel("Tip: houd Ctrl in of beweeg de muis over deze app om te pauzeren / te scrollen.")
        tip.setWordWrap(True)
        root.addWidget(tip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form_root = QVBoxLayout(content)
        form_root.addWidget(self._build_settings_group())
        form_root.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    def _apply_local_theme(self, _mode: str = "dark") -> None:
        if not self._running:
            self._focus_indicator.setStyleSheet(
                f"color: {ui_theme.STATUS_IDLE}; font-weight: bold;"
            )
        elif self._widgets is not None:
            self._apply_formation_fkeys(
                self._formation_party_id,
                self._formation_seats or frozenset(),
                self._familiar_level_seats,
            )

    def _build_settings_group(self) -> QGroupBox:
        group = QGroupBox("Instellingen")
        outer = QVBoxLayout(group)

        level_enabled = QCheckBox("Auto levelen (F12 aflopend naar F1)")
        level_enabled.setChecked(True)
        outer.addWidget(level_enabled)

        level_options = QWidget()
        level_options_layout = QVBoxLayout(level_options)
        level_options_layout.setContentsMargins(0, 0, 0, 0)
        level_interval_sec = QLineEdit("0")
        row = QFormLayout()
        row.addRow("Level-interval (seconden, 0 = zo snel mogelijk):", level_interval_sec)
        level_options_layout.addLayout(row)

        fkeys_box = QGroupBox("F-toetsen bij levelen (alleen bij handmatige keuze)")
        fkeys_grid = QGridLayout(fkeys_box)
        fkeys: dict[int, QCheckBox] = {}
        for i in range(1, 13):
            cb = QCheckBox(f"F{i}")
            cb.setChecked(False)
            fkeys[i] = cb
            fkeys_grid.addWidget(cb, (i - 1) // 4, (i - 1) % 4)
        fkey_formation_label = QLabel("Alle seats in de actieve formatie (F-vinkjes worden genegeerd).")
        fkey_formation_label.setWordWrap(True)
        limit_level_to_formation = QCheckBox("Beperk levelen tot actieve formatie (auto-sync)")
        limit_level_to_formation.setChecked(True)
        limit_level_to_formation.toggled.connect(self._on_level_scope_changed)
        level_options_layout.addWidget(limit_level_to_formation)
        level_options_layout.addWidget(fkey_formation_label)
        level_options_layout.addWidget(fkeys_box)
        # Formatie-modus staat standaard aan: F-vinkjes zijn dan niet van toepassing.
        fkeys_box.setEnabled(False)
        self._fkeys_box = fkeys_box
        self._fkey_formation_label = fkey_formation_label
        self._limit_level_to_formation = limit_level_to_formation
        outer.addWidget(level_options)
        bind_option_visibility(level_enabled, level_options)

        auto_progress_enabled = QCheckBox("Auto progress (toets G) automatisch")
        auto_progress_enabled.setChecked(False)
        outer.addWidget(auto_progress_enabled)
        auto_progress_options = QWidget()
        auto_progress_options_layout = QVBoxLayout(auto_progress_options)
        auto_progress_options_layout.setContentsMargins(0, 0, 0, 0)
        auto_progress_interval_sec = QLineEdit("180")
        row = QFormLayout()
        row.addRow("Auto progress-interval (seconden):", auto_progress_interval_sec)
        auto_progress_options_layout.addLayout(row)
        outer.addWidget(auto_progress_options)
        bind_option_visibility(auto_progress_enabled, auto_progress_options)

        grave_enabled = QCheckBox("Backtick (`) automatisch")
        grave_enabled.setChecked(False)
        outer.addWidget(grave_enabled)
        grave_options = QWidget()
        grave_options_layout = QVBoxLayout(grave_options)
        grave_options_layout.setContentsMargins(0, 0, 0, 0)
        grave_interval_sec = QLineEdit("3")
        row = QFormLayout()
        row.addRow("Backtick-interval (seconden):", grave_interval_sec)
        grave_options_layout.addLayout(row)
        outer.addWidget(grave_options)
        bind_option_visibility(grave_enabled, grave_options)

        abilities_enabled = QCheckBox("Special abilities automatisch (timer-modus)")
        abilities_enabled.setChecked(True)
        outer.addWidget(abilities_enabled)
        abilities_options = QWidget()
        abilities_options_layout = QVBoxLayout(abilities_options)
        abilities_options_layout.setContentsMargins(0, 0, 0, 0)
        abilities_interval_sec = QLineEdit("10")
        row = QFormLayout()
        row.addRow("Abilities-interval (seconden):", abilities_interval_sec)
        abilities_options_layout.addLayout(row)
        outer.addWidget(abilities_options)
        bind_option_visibility(abilities_enabled, abilities_options)

        auto_click_enabled = QCheckBox("Muisklik click damage (linkerklik als muis boven spelvenster)")
        auto_click_enabled.setChecked(False)
        outer.addWidget(auto_click_enabled)
        auto_click_options = QWidget()
        auto_click_options_layout = QVBoxLayout(auto_click_options)
        auto_click_options_layout.setContentsMargins(0, 0, 0, 0)
        auto_click_cps = QLineEdit("10")
        row = QFormLayout()
        row.addRow("Klikken per seconde:", auto_click_cps)
        auto_click_options_layout.addLayout(row)
        outer.addWidget(auto_click_options)
        bind_option_visibility(auto_click_enabled, auto_click_options)

        hover_gate = QCheckBox("Alleen automatiseren als muis boven spelvenster staat")
        hover_gate.setChecked(True)
        pause_ctrl = QCheckBox("Pauzeer automatisering terwijl Ctrl ingedrukt is (aanbevolen)")
        pause_ctrl.setChecked(True)
        pause_over_app = QCheckBox(
            "Pauzeer als muis boven deze app staat of deze app focus heeft (aanbevolen)"
        )
        pause_over_app.setChecked(True)
        prefer_game_focus = QCheckBox(
            "Geen focus stelen: alleen toetsen sturen als Idle Champions al actief is"
        )
        prefer_game_focus.setChecked(True)
        outer.addWidget(hover_gate)
        outer.addWidget(pause_ctrl)
        outer.addWidget(pause_over_app)
        outer.addWidget(prefer_game_focus)

        self._widgets = AutomationWidgets(
            level_enabled=level_enabled,
            level_interval_sec=level_interval_sec,
            auto_progress_enabled=auto_progress_enabled,
            auto_progress_interval_sec=auto_progress_interval_sec,
            grave_enabled=grave_enabled,
            grave_interval_sec=grave_interval_sec,
            abilities_enabled=abilities_enabled,
            abilities_interval_sec=abilities_interval_sec,
            auto_click_enabled=auto_click_enabled,
            auto_click_cps=auto_click_cps,
            hover_gate=hover_gate,
            pause_ctrl=pause_ctrl,
            pause_over_app=pause_over_app,
            prefer_game_focus=prefer_game_focus,
            level_fkeys=fkeys,
        )
        return group

    @staticmethod
    def _to_int(line: QLineEdit, default: int) -> int:
        try:
            return int(float((line.text() or "").strip().replace(",", ".")))
        except ValueError:
            return default

    def _build_settings_snapshot(self) -> AutomationSettings:
        w = self._widgets
        assert w is not None
        # Actieve-formatie modus: alle formatie-seats, F-vinkjes negeren.
        if self._limit_level_to_formation.isChecked() and self._formation_seats:
            selected = tuple(
                i for i in range(12, 0, -1) if i in self._formation_seats
            )
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
        pause_app = w.pause_over_app.isChecked()
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
            enable_auto_click=w.auto_click_enabled.isChecked(),
            auto_click_cps=max(1, min(20, self._to_int(w.auto_click_cps, 10))),
            hover_gate=w.hover_gate.isChecked(),
            restore_focus=True,
            pause_on_ctrl=w.pause_ctrl.isChecked(),
            pause_when_over_app=pause_app,
            pause_when_app_focused=pause_app,
            prefer_game_already_focused=w.prefer_game_focus.isChecked(),
        )

    def _set_running_ui(self, running: bool) -> None:
        self._running = running
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        self.running_changed.emit(running)
        if not running:
            self._focus_indicator.setText("● Gestopt")
            self._focus_indicator.setStyleSheet(
                f"color: {ui_theme.STATUS_IDLE}; font-weight: bold;"
            )

    def _start_automation(self) -> None:
        if win_input.gw is None:
            QMessageBox.warning(
                self,
                "Ontbrekende dependency",
                "pygetwindow ontbreekt. Installeer dependencies via requirements.txt.",
            )
            return
        self.api_poll_requested.emit()
        settings = self._build_settings_snapshot()
        self._automation.start(settings)
        self._set_running_ui(True)
        self._status_label.setText("Status: actief (worker)")
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

    def _update_focus_indicator(self, text: str, kind: str) -> None:
        lower = text.lower()
        pause_style = f"color: {ui_theme.STATUS_PAUSE}; font-weight: bold;"
        if kind == "paused" or "gepauzeerd" in lower:
            if "shift" in lower or "ctrl" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — Ctrl ingedrukt")
                self._focus_indicator.setStyleSheet(pause_style)
            elif "caps" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — Caps Lock aan")
                self._focus_indicator.setStyleSheet(pause_style)
            elif "muis" in lower or "hover" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — muis boven deze app")
                self._focus_indicator.setStyleSheet(pause_style)
            elif "focus" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — helper heeft focus")
                self._focus_indicator.setStyleSheet(pause_style)
            else:
                self._focus_indicator.setText("⏸ Gepauzeerd")
                self._focus_indicator.setStyleSheet(pause_style)
        elif "wacht" in lower or "focus" in lower:
            self._focus_indicator.setText("⏳ Wacht op game-focus — klik in Idle Champions")
            self._focus_indicator.setStyleSheet(
                f"color: {ui_theme.STATUS_WAIT}; font-weight: bold;"
            )
        elif kind == "error":
            self._focus_indicator.setText("⚠ Fout — zie status hierboven")
            self._focus_indicator.setStyleSheet(
                f"color: {ui_theme.STATUS_ERROR}; font-weight: bold;"
            )
        else:
            self._focus_indicator.setText("● Actief")
            self._focus_indicator.setStyleSheet(
                f"color: {ui_theme.STATUS_ACTIVE}; font-weight: bold;"
            )

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
        # In formatie-modus sturen we alle seats; F-vinkjes zijn alleen informatief.
        self._fkeys_box.setEnabled(not limit_to_formation)
        party_changed = party_id != self._formation_party_id
        if not seats:
            party_txt = f"party {party_id}" if party_id is not None else "actieve party"
            if limit_to_formation:
                self._fkey_formation_label.setText(
                    f"Formatie {party_txt}: geen seats gevonden — wacht op API-sync."
                )
            else:
                self._fkey_formation_label.setText(
                    f"Formatie {party_txt}: geen seats gevonden — handmatig aanvinken."
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
                cb.setStyleSheet(
                    f"QCheckBox {{ color: {familiar}; font-weight: 600; }}"
                    f"QCheckBox:disabled {{ color: {familiar}; }}"
                )
                cb.setChecked(False)
                cb.setEnabled(False)
            else:
                cb.setStyleSheet("")
                cb.setEnabled(not limit_to_formation)
                if limit_to_formation:
                    cb.setChecked(i in seats)
        seat_list = ", ".join(f"F{s}" for s in sorted(seats))
        party_txt = f"party {party_id}" if party_id is not None else "actieve party"
        blocked = sorted(seats & familiar_seats)
        levelable = sorted(seats - familiar_seats)
        if blocked and not levelable:
            suffix = (
                f" — familiar op alle formatie-seats ({', '.join(f'F{s}' for s in blocked)}); "
                "geen F-toetsen nodig"
            )
        elif blocked:
            blocked_txt = ", ".join(f"F{s}" for s in blocked)
            suffix = f" — familiar op {blocked_txt} (groen, geen F-level)"
        else:
            suffix = ""
        if limit_to_formation:
            mode_txt = "alle actieve formatie-champs (F-vinkjes genegeerd)"
        else:
            mode_txt = "handmatige F-keuzes toegestaan"
        self._fkey_formation_label.setText(
            f"Formatie {party_txt}: {seat_list}{suffix} — {mode_txt}"
        )

    def _on_level_scope_changed(self) -> None:
        limit_to_formation = self._limit_level_to_formation.isChecked()
        self._fkeys_box.setEnabled(not limit_to_formation)
        if self._formation_seats:
            self._apply_formation_fkeys(
                self._formation_party_id,
                self._formation_seats,
                self._familiar_level_seats,
            )
        elif limit_to_formation:
            self._fkey_formation_label.setText(
                "Alle seats in de actieve formatie (F-vinkjes worden genegeerd)."
            )
        else:
            self._fkey_formation_label.setText(
                "Handmatige F-keuzes: vink aan welke seats je wilt levelen."
            )
