from __future__ import annotations

import json
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ic_automation import AutomationController, AutomationSettings
from ic_automation import win_input
from ic_ui.theme import (
    DEFAULT_WINDOW_TITLE,
    FKEY_FAMILIAR_COLOR,
    FORMATION_ZONE_BG,
    PORTRAIT_H,
    PORTRAIT_W,
    STATUS_IDLE,
    TEXT_MUTED,
    ACCENT as _ADVISOR_ACCENT,
    BG_CARD as _ADVISOR_CARD_BG,
    BG_INPUT as _ADVISOR_INPUT_BG,
    BORDER as _ADVISOR_INPUT_BORDER,
    BUD_BAR as _ADVISOR_BUD_BAR,
    DIVIDER as _ADVISOR_DIVIDER,
    FEAT_MISSING as _ADVISOR_FEAT_MISSING,
    FEAT_OWNED as _ADVISOR_FEAT_OWNED,
    SUCCESS as _ADVISOR_FEAT_ACTIVE,
    TEXT_BODY as _ADVISOR_BODY,
    TEXT_BADGE as _ADVISOR_BADGE_TEXT,
    BG_BADGE as _ADVISOR_BADGE_BG,
    TEXT_MUTED as _ADVISOR_MUTED,
    TEXT_PRIMARY as _ADVISOR_TEXT,
    WARN as _ADVISOR_WARN,
    WARN_BAR as _ADVISOR_WARN_BAR,
    advisor_accent_stylesheet as _advisor_accent_stylesheet,
    advisor_badge_stylesheet as _advisor_badge_stylesheet,
    advisor_card_stylesheet as _advisor_card_stylesheet,
    advisor_text_styles as _advisor_text_styles,
    portrait_placeholder_stylesheet as _portrait_placeholder_stylesheet,
)

_FORMATION_ZONE_BG = FORMATION_ZONE_BG
_FKEY_FAMILIAR_COLOR = FKEY_FAMILIAR_COLOR
_ADVISOR_PORTRAIT_W = PORTRAIT_W
_ADVISOR_PORTRAIT_H = PORTRAIT_H


@dataclass
class AutomationWidgets:
    window_title: QLineEdit
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


def _widget_device_pixel_ratio(widget: QWidget) -> float:
    dpr = widget.devicePixelRatioF()
    if dpr > 0:
        return dpr
    screen = QApplication.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


def _trim_transparent_pixmap(pixmap: QPixmap) -> QPixmap:
    """Crop empty padding so square portrait assets fill the avatar box."""
    image = pixmap.toImage()
    if image.isNull():
        return pixmap

    width = image.width()
    height = image.height()
    min_x, min_y = width, height
    max_x, max_y = -1, -1
    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 16:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y

    if max_x < min_x or max_y < min_y:
        return pixmap
    return pixmap.copy(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def _fit_portrait_pixmap(source: QPixmap, width: int, height: int, device_pixel_ratio: float) -> QPixmap:
    """Scale and center-crop a portrait to an exact display size."""
    target_w = max(1, int(width * device_pixel_ratio))
    target_h = max(1, int(height * device_pixel_ratio))
    trimmed = _trim_transparent_pixmap(source)
    scaled = trimmed.scaled(
        target_w,
        target_h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    crop_x = max(0, (scaled.width() - target_w) // 2)
    crop_y = max(0, (scaled.height() - target_h) // 2)
    fitted = scaled.copy(crop_x, crop_y, target_w, target_h)
    fitted.setDevicePixelRatio(device_pixel_ratio)
    return fitted


class _FormationSeatCard(QFrame):
    clicked = Signal(int)

    def __init__(self, seat: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seat = seat
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._seat)
        super().mousePressEvent(event)


class _AdvisorSignals(QObject):
    done = Signal(object)   # report object
    error = Signal(str)


class _ApiFetchSignals(QObject):
    done = Signal(object)


class _ApiFetchRunnable(QRunnable):
    def __init__(self, credentials, log_path: Path | None, tailer) -> None:
        super().__init__()
        self.signals = _ApiFetchSignals()
        self._credentials = credentials
        self._log_path = log_path
        self._tailer = tailer

    def run(self) -> None:
        try:
            from ic_gamedata.snapshot_fetch import fetch_merged_snapshot
        except ImportError as exc:
            self.signals.done.emit({"error": f"Importfout: {exc}"})
            return
        try:
            credentials, payload, api_snap, snap, err, api_detail = fetch_merged_snapshot(
                self._credentials,
                self._log_path,
                self._tailer,
            )
            self.signals.done.emit(
                {
                    "credentials": credentials,
                    "payload": payload,
                    "api_snap": api_snap,
                    "snap": snap,
                    "err": err,
                    "api_detail": api_detail,
                }
            )
        except Exception as exc:
            self.signals.done.emit({"error": str(exc)})


class _AdvisorRunnable(QRunnable):
    def __init__(
        self,
        goal: str,
        context: str,
        include_formation: bool,
        payload: dict,
        err: str | None = None,
    ) -> None:
        super().__init__()
        self.signals = _AdvisorSignals()
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


class _SpecializationsSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class _SpecializationsRunnable(QRunnable):
    def __init__(
        self,
        goal: str,
        context: str,
        payload: dict,
        err: str | None = None,
    ) -> None:
        super().__init__()
        self.signals = _SpecializationsSignals()
        self._goal = goal
        self._context = context
        self._payload = payload
        self._err = err

    def run(self) -> None:
        try:
            from ic_gamedata.party_advisor import analyze_party
            from ic_gamedata.party_advisor_specializations import advisor_run_goal
            from ic_gamedata.specializations import load_specialization_rules, pending_specializations
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


class IdleChampionsMainWindow(QMainWindow):
    _caption_refresh = Signal()
    _formation_sync = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Idle Champions")
        self.resize(980, 760)
        self._running = False
        self._automation = AutomationController()
        self._init_dashboard_state()
        self._init_advisor_state()
        self._init_specializations_state()
        self._formation_seats: frozenset[int] | None = None
        self._formation_party_id: int | None = None
        self._familiar_level_seats: frozenset[int] = frozenset()
        self._formation_poll_tick = 0
        self._caption_refresh.connect(self._refresh_app_caption_from_snapshots)
        self._formation_sync.connect(self._sync_fkeys_from_payload)
        self._init_api_poll_state()

        tabs = QTabWidget()
        tabs.addTab(self._build_automation_tab(), "Automatisering [UIT]")
        tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        tabs.addTab(self._build_advisor_tab(), "Party Advisor")
        tabs.addTab(self._build_specializations_tab(), "Specialisaties")
        tabs.addTab(self._build_sources_tab(), "Bronnen")
        self._tabs = tabs
        self.setCentralWidget(tabs)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._poll_status)
        self._dash_timer = QTimer(self)
        self._dash_timer.setInterval(1000)
        self._dash_timer.timeout.connect(self._dash_poll_once)

        self._api_poll_timer.start()
        QTimer.singleShot(300, self._dash_auto_start)

    def _build_placeholder_tab(self, text: str) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return panel

    def _build_automation_tab(self) -> QWidget:
        container = QWidget()
        root = QVBoxLayout(container)

        button_row = QHBoxLayout()
        self._btn_start = QPushButton("Start")
        self._btn_start.clicked.connect(self._start_automation)
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_automation)
        button_row.addWidget(self._btn_start)
        button_row.addWidget(self._btn_stop)
        button_row.addStretch(1)
        root.addLayout(button_row)

        self._status_label = QLabel("Status: gestopt")
        root.addWidget(self._status_label)

        self._focus_indicator = QLabel("● Gestopt")
        self._focus_indicator.setStyleSheet(f"color: {STATUS_IDLE}; font-weight: bold;")
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
        return container

    def _build_dashboard_tab(self) -> QWidget:
        container = QWidget()
        root = QVBoxLayout(container)

        self._dash_parties_container = QWidget()
        self._dash_parties_layout = QGridLayout(self._dash_parties_container)
        self._dash_parties_layout.setContentsMargins(0, 0, 0, 0)
        self._dash_parties_layout.setHorizontalSpacing(12)
        self._dash_parties_layout.setVerticalSpacing(12)
        self._dash_parties_layout.setColumnStretch(0, 1)
        self._dash_parties_layout.setColumnStretch(1, 1)
        self._dash_party_widgets: dict[int, dict[str, QWidget]] = {}
        root.addWidget(self._dash_parties_container, stretch=1)

        self._dash_detail = QLabel("")
        self._dash_detail.setWordWrap(True)
        root.addWidget(self._dash_detail)

        controls = QHBoxLayout()
        self._dash_toggle_btn = QPushButton("Start dashboard")
        self._dash_toggle_btn.clicked.connect(self._dash_toggle)
        refresh_btn = QPushButton("Opnieuw zoeken")
        refresh_btn.clicked.connect(self._dash_refresh_install)
        reset_btn = QPushButton("Reset sessie")
        reset_btn.clicked.connect(self._dash_reset_session)
        controls.addWidget(self._dash_toggle_btn)
        controls.addWidget(reset_btn)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self._dash_status = QLabel("Dashboard gebruikt gecentraliseerde API-poll (elke 5 s). Start voor memory-updates.")
        self._dash_status.setWordWrap(True)
        root.addWidget(self._dash_status)

        root.addStretch(1)
        return container

    def _build_sources_tab(self) -> QWidget:
        container = QWidget()
        root = QVBoxLayout(container)
        source = QGroupBox("Bronnen")
        source_form = QFormLayout(source)
        self._src_install_lbl = QLabel("—")
        self._src_install_lbl.setWordWrap(True)
        self._src_log_lbl = QLabel("—")
        self._src_log_lbl.setWordWrap(True)
        self._src_manual_path = QLineEdit("")
        self._src_ui_hint = QLineEdit("")
        self._src_ui_hint.setPlaceholderText("optioneel")
        source_form.addRow("Installatie:", self._src_install_lbl)
        source_form.addRow("Logbestand:", self._src_log_lbl)
        source_form.addRow("Handmatig pad:", self._src_manual_path)
        source_form.addRow("Memory UI-hint:", self._src_ui_hint)
        root.addWidget(source)

        controls = QHBoxLayout()
        save_btn = QPushButton("Opslaan")
        save_btn.clicked.connect(self._dash_save_manual_path)
        refresh_btn = QPushButton("Opnieuw zoeken")
        refresh_btn.clicked.connect(self._dash_refresh_install)
        controls.addWidget(save_btn)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)
        root.addLayout(controls)
        root.addStretch(1)
        self._dash_refresh_install()
        return container

    @staticmethod
    def _bind_option_visibility(checkbox: QCheckBox, *widgets: QWidget) -> None:
        def update(checked: bool) -> None:
            for widget in widgets:
                widget.setVisible(checked)

        checkbox.toggled.connect(update)
        update(checkbox.isChecked())

    def _build_settings_group(self) -> QGroupBox:
        group = QGroupBox("Instellingen")
        outer = QVBoxLayout(group)

        form = QFormLayout()
        entry_window = QLineEdit(DEFAULT_WINDOW_TITLE)
        form.addRow("Venstertitel (deel van):", entry_window)
        outer.addLayout(form)

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

        fkeys_box = QGroupBox("F-toetsen bij levelen")
        fkeys_grid = QGridLayout(fkeys_box)
        fkeys: dict[int, QCheckBox] = {}
        for i in range(1, 13):
            cb = QCheckBox(f"F{i}")
            cb.setChecked(False)
            fkeys[i] = cb
            fkeys_grid.addWidget(cb, (i - 1) // 4, (i - 1) % 4)
        fkey_formation_label = QLabel("Alleen seats in de actieve formatie (auto-sync).")
        fkey_formation_label.setWordWrap(True)
        limit_level_to_formation = QCheckBox("Beperk levelen tot actieve formatie (auto-sync)")
        limit_level_to_formation.setChecked(True)
        limit_level_to_formation.toggled.connect(self._on_level_scope_changed)
        level_options_layout.addWidget(fkeys_box)
        level_options_layout.addWidget(fkey_formation_label)
        level_options_layout.addWidget(limit_level_to_formation)
        self._fkey_formation_label = fkey_formation_label
        self._limit_level_to_formation = limit_level_to_formation
        outer.addWidget(level_options)
        self._bind_option_visibility(level_enabled, level_options)

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
        self._bind_option_visibility(auto_progress_enabled, auto_progress_options)

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
        self._bind_option_visibility(grave_enabled, grave_options)

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
        self._bind_option_visibility(abilities_enabled, abilities_options)

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
        self._bind_option_visibility(auto_click_enabled, auto_click_options)

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

        self._automation_widgets = AutomationWidgets(
            window_title=entry_window,
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
        w = self._automation_widgets
        selected = tuple(
            i
            for i in range(12, 0, -1)
            if w.level_fkeys[i].isChecked() and w.level_fkeys[i].isEnabled()
        )
        if self._limit_level_to_formation.isChecked() and self._formation_seats:
            selected = tuple(i for i in selected if i in self._formation_seats)
        if self._familiar_level_seats:
            selected = tuple(i for i in selected if i not in self._familiar_level_seats)
        hwnd = int(self.winId())
        exclude_hwnd = win_input.toplevel_hwnd(hwnd)
        window_title = (w.window_title.text() or "").strip() or DEFAULT_WINDOW_TITLE
        pause_app = w.pause_over_app.isChecked()
        return AutomationSettings(
            window_title=window_title,
            exclude_hwnd=exclude_hwnd,
            # Don't exclude by title; app/game titles can be identical on some setups.
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
        self._tabs.setTabText(0, f"Automatisering [{'AAN' if running else 'UIT'}]")
        if not running:
            self._focus_indicator.setText("● Gestopt")
            self._focus_indicator.setStyleSheet(f"color: {STATUS_IDLE}; font-weight: bold;")

    def _start_automation(self) -> None:
        if win_input.gw is None:
            QMessageBox.warning(
                self,
                "Ontbrekende dependency",
                "pygetwindow ontbreekt. Installeer dependencies via requirements.txt.",
            )
            return
        self._request_api_poll()
        settings = self._build_settings_snapshot()
        self._automation.start(settings)
        self._set_running_ui(True)
        self._status_label.setText("Status: actief (worker)")
        self._status_timer.start()

    def _stop_automation(self) -> None:
        self._automation.stop()
        self._status_timer.stop()
        self._set_running_ui(False)
        self._status_label.setText("Status: gestopt")

    def _poll_status(self) -> None:
        if not self._running:
            return
        self._formation_poll_tick += 1
        # Formatie F-toetsen: gebruik gecentraliseerde API-cache (elke ~2s).
        if self._formation_poll_tick % 8 == 0 and self._dash_last_payload is not None:
            self._sync_fkeys_from_payload(self._dash_last_payload)
        self._automation.update_settings(self._build_settings_snapshot())
        event = self._automation.poll_status()
        if event is not None and event.text:
            self._status_label.setText(event.text)
            self._update_focus_indicator(event.text, event.kind)

    def _update_focus_indicator(self, text: str, kind: str) -> None:
        lower = text.lower()
        if kind == "paused" or "gepauzeerd" in lower:
            if "shift" in lower or "ctrl" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — Ctrl ingedrukt")
                self._focus_indicator.setStyleSheet("color: #b45309; font-weight: bold;")
            elif "caps" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — Caps Lock aan")
                self._focus_indicator.setStyleSheet("color: #b45309; font-weight: bold;")
            elif "muis" in lower or "hover" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — muis boven deze app")
                self._focus_indicator.setStyleSheet("color: #b45309; font-weight: bold;")
            elif "focus" in lower:
                self._focus_indicator.setText("⏸ Gepauzeerd — helper heeft focus")
                self._focus_indicator.setStyleSheet("color: #b45309; font-weight: bold;")
            else:
                self._focus_indicator.setText("⏸ Gepauzeerd")
                self._focus_indicator.setStyleSheet("color: #b45309; font-weight: bold;")
        elif "wacht" in lower or "focus" in lower:
            self._focus_indicator.setText("⏳ Wacht op game-focus — klik in Idle Champions")
            self._focus_indicator.setStyleSheet("color: #1d4ed8; font-weight: bold;")
        elif kind == "error":
            self._focus_indicator.setText("⚠ Fout — zie status hierboven")
            self._focus_indicator.setStyleSheet("color: #dc2626; font-weight: bold;")
        else:
            self._focus_indicator.setText("● Actief")
            self._focus_indicator.setStyleSheet("color: #15803d; font-weight: bold;")

    def _sync_fkeys_from_payload(self, payload: dict | None) -> None:
        if payload is None:
            return
        try:
            from ic_gamedata.formation_seats import active_formation_seats
            from ic_gamedata.familiar_seats import familiar_level_seats
        except ImportError:
            return
        party_id, seats = active_formation_seats(payload)
        familiar_seats = familiar_level_seats(payload)
        self._apply_formation_fkeys(party_id, seats, familiar_seats)

    def _apply_formation_fkeys(
        self,
        party_id: int | None,
        seats: frozenset[int],
        familiar_seats: frozenset[int] | None = None,
    ) -> None:
        if familiar_seats is None:
            familiar_seats = self._familiar_level_seats
        if not hasattr(self, "_automation_widgets"):
            return
        w = self._automation_widgets
        limit_to_formation = self._limit_level_to_formation.isChecked()
        party_changed = party_id != self._formation_party_id
        if not seats:
            party_txt = f"party {party_id}" if party_id is not None else "actieve party"
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
                cb.setStyleSheet(
                    f"QCheckBox {{ color: {_FKEY_FAMILIAR_COLOR}; font-weight: 600; }}"
                    f"QCheckBox:disabled {{ color: {_FKEY_FAMILIAR_COLOR}; }}"
                )
                cb.setChecked(False)
                cb.setEnabled(False)
            else:
                cb.setStyleSheet("")
                cb.setEnabled(True)
                if limit_to_formation:
                    cb.setChecked(i in seats)
        seat_list = ", ".join(f"F{s}" for s in sorted(seats))
        party_txt = f"party {party_id}" if party_id is not None else "actieve party"
        blocked = sorted(seats & familiar_seats)
        if blocked:
            blocked_txt = ", ".join(f"F{s}" for s in blocked)
            suffix = f" — familiar op {blocked_txt} (groen, geen vinkje)"
        else:
            suffix = ""
        mode_txt = "alleen actieve formatie" if limit_to_formation else "handmatige F-keuzes toegestaan"
        self._fkey_formation_label.setText(
            f"Formatie {party_txt}: {seat_list}{suffix} — {mode_txt}"
        )

    def _on_level_scope_changed(self) -> None:
        if self._formation_seats:
            self._apply_formation_fkeys(
                self._formation_party_id,
                self._formation_seats,
                self._familiar_level_seats,
            )

    # ------------------------------------------------------------------ advisor

    def _init_advisor_state(self) -> None:
        self._advisor_last_payload = None
        self._advisor_last_goal = "bud"
        self._advisor_last_context = "campaign"
        self._advisor_last_party_id: int | None = None
        self._advisor_feat_open: dict[int, bool] = {}
        self._advisor_analysing = False
        self._advisor_pending_auto_refresh = False
        self._advisor_pending_analysis: tuple[dict, str | None, bool, bool] | None = None
        self._advisor_current_party_changed = False
        self._advisor_has_results = False
        self._advisor_seat_card_frames: dict[int, QFrame] = {}

    def _build_advisor_tab(self) -> QWidget:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- controls row ---
        ctrl_row = QHBoxLayout()

        self._advisor_goal = QComboBox()
        self._advisor_goal.addItem("BUD / damage", "bud")
        self._advisor_goal.addItem("Gold income", "gold")
        self._advisor_goal.addItem("Speed / areas", "speed")

        self._advisor_context = QComboBox()
        self._advisor_context.addItem("Campaign", "campaign")
        self._advisor_context.addItem("Events", "events")
        self._advisor_context.addItem("Push", "push")
        self._advisor_context.addItem("Modron", "modron")

        self._advisor_cb_formation = QCheckBox("Formatie")
        self._advisor_cb_formation.setChecked(True)

        self._advisor_btn_analyze = QPushButton("Analyseren")
        self._advisor_btn_analyze.clicked.connect(lambda: self._advisor_analyze(auto_refresh=False))

        self._advisor_cb_formation.toggled.connect(self._advisor_on_options_changed)
        self._advisor_goal.currentIndexChanged.connect(self._advisor_on_options_changed)
        self._advisor_context.currentIndexChanged.connect(self._advisor_on_options_changed)

        ctrl_row.addWidget(QLabel("Doel:"))
        ctrl_row.addWidget(self._advisor_goal)
        ctrl_row.addWidget(QLabel("Context:"))
        ctrl_row.addWidget(self._advisor_context)
        ctrl_row.addWidget(self._advisor_cb_formation)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self._advisor_btn_analyze)
        root.addLayout(ctrl_row)

        self._advisor_status = QLabel("Start automatisch zodra speldata beschikbaar is.")
        self._advisor_status.setWordWrap(True)
        root.addWidget(self._advisor_status)

        # --- scroll area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._advisor_scroll = scroll

        self._advisor_content = QWidget()
        self._advisor_content.setStyleSheet("background: transparent;")
        self._advisor_layout = QVBoxLayout(self._advisor_content)
        self._advisor_layout.setSpacing(10)
        self._advisor_layout.setContentsMargins(12, 8, 12, 16)
        scroll.setWidget(self._advisor_content)
        scroll.setVisible(False)
        root.addWidget(scroll, stretch=1)

        return container

    def _advisor_on_options_changed(self, *_args) -> None:
        if self._advisor_last_payload is None:
            return
        self._advisor_last_goal = self._advisor_goal.currentData() or "bud"
        self._advisor_last_context = self._advisor_context.currentData() or "campaign"
        self._advisor_rerun_with_role_prefs()

    def _advisor_analyze(self, *, auto_refresh: bool = False) -> None:
        if self._advisor_analysing:
            return
        if not self._advisor_refresh_credentials():
            if not auto_refresh:
                self._advisor_status.setText(
                    "Geen API-credentials. Ga naar Dashboard → Opnieuw zoeken."
                )
            return
        if not auto_refresh:
            self._advisor_btn_analyze.setEnabled(False)
            self._advisor_status.setText("Analyseren…")
        self._request_api_poll(advisor_after=True, auto_refresh=auto_refresh)

    def _party_id_from_payload(self, payload: dict | None) -> int | None:
        if not isinstance(payload, dict):
            return None
        details = payload.get("details")
        if not isinstance(details, dict):
            return None
        raw = details.get("active_game_instance_id")
        if raw is None or isinstance(raw, bool):
            return None
        try:
            return int(float(str(raw).strip()))
        except (TypeError, ValueError):
            return None

    def _start_advisor_analysis(
        self,
        payload: dict,
        err: str | None,
        *,
        auto_refresh: bool,
        party_changed: bool = False,
    ) -> None:
        if self._advisor_analysing:
            self._advisor_pending_analysis = (payload, err, auto_refresh, party_changed)
            return
        goal = self._advisor_goal.currentData() or "bud"
        context = self._advisor_context.currentData() or "campaign"
        include_formation = self._advisor_cb_formation.isChecked()
        self._advisor_pending_auto_refresh = auto_refresh
        self._advisor_current_party_changed = party_changed
        self._advisor_analysing = True
        worker = _AdvisorRunnable(
            goal,
            context,
            include_formation,
            payload,
            err,
        )
        worker.signals.done.connect(self._advisor_on_done)
        worker.signals.error.connect(self._advisor_on_error)
        QThreadPool.globalInstance().start(worker)

    def _schedule_pending_advisor_analysis(self) -> None:
        pending = self._advisor_pending_analysis
        if pending is None or self._advisor_analysing:
            return
        payload, err, auto_refresh, party_changed = pending
        self._advisor_pending_analysis = None
        self._start_advisor_analysis(
            payload,
            err,
            auto_refresh=auto_refresh,
            party_changed=party_changed,
        )

    def _advisor_on_done(self, result) -> None:
        payload, report, err = result
        auto_refresh = self._advisor_pending_auto_refresh
        party_id = self._party_id_from_payload(payload)
        party_changed = self._advisor_current_party_changed or (
            self._advisor_last_party_id is not None
            and party_id is not None
            and party_id != self._advisor_last_party_id
        )
        self._advisor_last_payload = payload
        self._advisor_last_party_id = party_id
        self._advisor_last_goal = report.goal
        self._advisor_last_context = report.context
        self._advisor_analysing = False
        self._advisor_btn_analyze.setEnabled(True)
        status = report.summary
        if err:
            status = f"{status} ({err})"
        if party_changed:
            party_txt = f"party {party_id}" if party_id is not None else "nieuwe party"
            status = f"{status} · {party_txt}"
        if auto_refresh:
            status = f"{status} · ververst {time.strftime('%H:%M:%S')}"
        self._advisor_status.setText(status)
        reset_scroll = not auto_refresh or not self._advisor_has_results or party_changed
        self._advisor_render_report(report, reset_scroll=reset_scroll)
        self._schedule_pending_advisor_analysis()

    def _advisor_on_error(self, msg: str) -> None:
        auto_refresh = self._advisor_pending_auto_refresh
        self._advisor_analysing = False
        self._advisor_btn_analyze.setEnabled(True)
        if auto_refresh and self._advisor_has_results:
            self._advisor_status.setText(f"Verversen mislukt: {msg} (laatste resultaat behouden)")
        else:
            self._advisor_status.setText(f"Fout: {msg}")
        self._schedule_pending_advisor_analysis()

    def _advisor_refresh_credentials(self) -> bool:
        if self._dash_install is None or self._dash_credentials is None:
            self._dash_refresh_install()
        if self._dash_install and self._dash_install.web_request_log:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(Path(self._dash_install.web_request_log))
            if fresh is not None:
                self._dash_credentials = fresh
        return self._dash_credentials is not None

    def _advisor_rerun_with_role_prefs(self) -> None:
        if self._advisor_last_payload is None:
            return
        try:
            from ic_gamedata.party_advisor import analyze_party
        except ImportError:
            return
        report = analyze_party(
            self._advisor_last_payload,
            goal=self._advisor_last_goal,
            context=self._advisor_last_context,
            include_specializations=False,
            include_formation=self._advisor_cb_formation.isChecked(),
        )
        scroll_y = self._advisor_scroll.verticalScrollBar().value()
        self._advisor_render_report(report, reset_scroll=False)
        self._advisor_scroll.verticalScrollBar().setValue(scroll_y)
        self._advisor_status.setText(report.summary)

    def _advisor_on_role_selected(self, hero_id: int, role: str) -> None:
        try:
            from ic_gamedata.seat_advisor import set_chosen_role
        except ImportError:
            return
        set_chosen_role(hero_id, self._advisor_last_goal, role if role else None)
        self._advisor_rerun_with_role_prefs()

    def _advisor_clear(self) -> None:
        layout = self._advisor_layout
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _advisor_lbl(self, text: str, *, kind: str = "body") -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        styles = _advisor_text_styles()
        lbl.setStyleSheet(styles.get(kind, styles["body"]))
        return lbl

    def _advisor_badge(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 11px; color: {_ADVISOR_BADGE_TEXT}; background: {_ADVISOR_BADGE_BG}; "
            f"border: none; border-radius: 10px; padding: 3px 10px;"
        )
        return lbl

    def _advisor_portrait(self, hero_id: int) -> QLabel:
        lbl = QLabel()
        lbl.setFixedSize(_ADVISOR_PORTRAIT_W, _ADVISOR_PORTRAIT_H)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(_portrait_placeholder_stylesheet())
        try:
            from ic_gamedata.champion_portraits import champion_portrait_path
        except ImportError:
            return lbl
        path = champion_portrait_path(hero_id)
        if path is None:
            return lbl
        source = QPixmap(str(path))
        if source.isNull():
            return lbl
        lbl.setPixmap(
            _fit_portrait_pixmap(
                source,
                _ADVISOR_PORTRAIT_W,
                _ADVISOR_PORTRAIT_H,
                _widget_device_pixel_ratio(lbl),
            )
        )
        return lbl

    def _advisor_link_btn(self, text: str, url: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("linkBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _c=False, u=url: self._advisor_open_url(u))
        return btn

    def _advisor_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {_ADVISOR_DIVIDER}; border: none;")
        return line

    def _advisor_card_layout(self, card: QFrame) -> QVBoxLayout:
        body = card.findChild(QWidget, "advisorCardBody")
        target = body if body is not None else card
        lyt = QVBoxLayout(target)
        lyt.setContentsMargins(0, 14, 16, 14)
        lyt.setSpacing(8)
        return lyt

    def _advisor_show_results_panel(self) -> None:
        if self._advisor_has_results:
            return
        self._advisor_has_results = True
        self._advisor_scroll.setVisible(True)
        self._advisor_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._advisor_content.setStyleSheet("background: transparent;")

    def _advisor_render_report(self, report, *, reset_scroll: bool = True) -> None:
        self._advisor_show_results_panel()
        self._advisor_clear()

        context_labels = {"campaign": "Campaign", "events": "Events", "push": "Push", "modron": "Modron"}
        try:
            from ic_gamedata.party_advisor import goal_label as advisor_goal_label
        except ImportError:
            advisor_goal_label = lambda g: g  # noqa: E731
        goal_text = advisor_goal_label(report.goal)

        head = self._advisor_card(highlight=False)
        head_lyt = self._advisor_card_layout(head)
        head_lyt.addWidget(self._advisor_lbl(report.summary, kind="subtitle"))
        head_lyt.addWidget(
            self._advisor_lbl(
                f"{goal_text}  ·  {context_labels.get(report.context, report.context)}  ·  {report.adventure_name}",
                kind="muted",
            )
        )
        if report.gold_growth_rate is not None and report.goal == "gold":
            head_lyt.addWidget(self._advisor_lbl(f"Gold scaling: {report.gold_growth_rate:.2f}×", kind="body"))
        if report.adventure_buff_note:
            head_lyt.addWidget(self._advisor_lbl(report.adventure_buff_note, kind="body"))
        self._advisor_layout.addWidget(head)

        if report.seat_report and report.seat_report.seats:
            self._advisor_render_seat_section(report.seat_report, goal=report.goal)

        if report.formation_insights:
            self._advisor_section("Formatie & posities")
            for insight in report.formation_insights:
                seat_str = f"slot {insight.seat}" if insight.seat is not None else "—"
                extra = ""
                if insight.related_seat is not None and insight.related_hero_name:
                    extra = f" ↔ {insight.related_hero_name} (slot {insight.related_seat})"
                card = self._advisor_card(highlight=True)
                lyt = self._advisor_card_layout(card)
                lyt.addWidget(self._advisor_lbl(f"{insight.headline} ({seat_str}{extra})", kind="subtitle"))
                lyt.addWidget(self._advisor_lbl(insight.detail, kind="body"))
                self._advisor_layout.addWidget(card)

        if report.tips:
            self._advisor_section("Formation-tips")
            for tip in report.tips:
                card = self._advisor_card()
                lyt = self._advisor_card_layout(card)
                lyt.addWidget(self._advisor_lbl(f"Tip {tip.priority} · {tip.title}", kind="subtitle"))
                lyt.addWidget(self._advisor_lbl(tip.detail, kind="body"))
                self._advisor_layout.addWidget(card)

        self._advisor_layout.addStretch(1)

        if reset_scroll:
            self._advisor_scroll.verticalScrollBar().setValue(0)

    def _advisor_render_seat_section(self, seat_report, *, goal: str = "bud") -> None:
        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
            from ic_gamedata.seat_advisor.models import STANDARD_SEAT_ROLES
        except ImportError:
            role_label = lambda r: r or "?"  # noqa: E731
            STANDARD_SEAT_ROLES = []

        self._advisor_section("Seats (meest relevant bovenaan)")
        self._advisor_seat_card_frames = {}

        if goal == "bud" and seat_report.bud_hero_name:
            bud_card = self._advisor_card(accent_bar=_ADVISOR_BUD_BAR)
            self._advisor_card_layout(bud_card).addWidget(
                self._advisor_lbl(f"BUD deze run: {seat_report.bud_hero_name}", kind="subtitle")
            )
            self._advisor_layout.addWidget(bud_card)
        elif goal == "speed" and seat_report.speed_hero_name:
            speed_card = self._advisor_card(accent_bar=_ADVISOR_BUD_BAR)
            self._advisor_card_layout(speed_card).addWidget(
                self._advisor_lbl(f"Speed focus: {seat_report.speed_hero_name}", kind="subtitle")
            )
            self._advisor_layout.addWidget(speed_card)

        for seat in seat_report.seats:
            highlight = seat.priority < 20
            card = self._advisor_card(highlight=highlight)
            lyt = self._advisor_card_layout(card)

            h_row = QHBoxLayout()
            h_row.setSpacing(10)
            h_row.addWidget(
                self._advisor_portrait(seat.hero_id),
                alignment=Qt.AlignmentFlag.AlignTop,
            )
            left = QVBoxLayout()
            left.setSpacing(2)
            left.addWidget(self._advisor_lbl(seat.hero_name, kind="title"))
            meta_parts = [f"Slot {seat.seat}", seat.zone.upper()]
            if seat.is_bud:
                meta_parts.append("BUD")
            elif seat.is_speed_focus:
                meta_parts.append("Speed")
            left.addWidget(self._advisor_lbl(" · ".join(meta_parts), kind="muted"))
            h_row.addLayout(left, stretch=1)
            h_row.addWidget(self._advisor_badge(seat.gear_label), alignment=Qt.AlignmentFlag.AlignTop)
            lyt.addLayout(h_row)

            role_row = QHBoxLayout()
            role_row.setSpacing(8)
            role_row.addWidget(self._advisor_lbl("Rol", kind="muted"))
            role_combo = QComboBox()
            for r in STANDARD_SEAT_ROLES:
                role_combo.addItem(role_label(r), r)
            cur_role = seat.effective_role or ""
            idx = role_combo.findData(cur_role)
            if idx >= 0:
                role_combo.setCurrentIndex(idx)
            inferred = role_label(seat.inferred_role)
            chosen = role_label(seat.chosen_role) if seat.chosen_role else None
            if chosen and seat.chosen_role != seat.inferred_role:
                hint = f"Voorgesteld: {inferred} · Jouw keuze: {chosen}"
            else:
                hint = f"Voorgesteld: {inferred}"
            role_combo.currentIndexChanged.connect(
                lambda _i, hid=seat.hero_id, cb=role_combo: self._advisor_on_role_selected(hid, cb.currentData())
            )
            role_row.addWidget(role_combo)
            role_row.addWidget(self._advisor_lbl(hint, kind="muted"), stretch=1)
            lyt.addLayout(role_row)

            has_body = False
            if seat.relevance_reason and seat.relevance_reason != "OK":
                lyt.addWidget(self._advisor_lbl(seat.relevance_reason, kind="warn"))
                has_body = True

            for line in seat.insights:
                lyt.addWidget(
                    self._advisor_lbl(f"· {line.headline}: {line.detail}", kind="insight")
                )
                has_body = True

            if seat.bench_alternatives:
                alts = ", ".join(f"{a.hero_name} ({a.reason})" for a in seat.bench_alternatives[:3])
                lyt.addWidget(self._advisor_lbl(f"Bench: {alts}", kind="body"))
                has_body = True

            if seat.formation_advice:
                lyt.addWidget(self._advisor_lbl(seat.formation_advice, kind="body"))
                has_body = True

            source = getattr(seat, "advice_source", "") or ""
            source_url = getattr(seat, "advice_source_url", "") or ""
            wiki_url = getattr(seat, "advice_wiki_url", "") or ""
            if source or source_url or wiki_url or has_body:
                lyt.addWidget(self._advisor_divider())

            if source or source_url or wiki_url:
                src_row = QHBoxLayout()
                src_row.addWidget(
                    self._advisor_lbl(
                        f"Bron: {source}" if source else "Bron: community guide",
                        kind="muted",
                    )
                )
                src_row.addStretch(1)
                if source_url:
                    src_row.addWidget(self._advisor_link_btn("Reddit", source_url))
                if wiki_url:
                    src_row.addWidget(self._advisor_link_btn("Wiki", wiki_url))
                lyt.addLayout(src_row)

            feats = seat.recommended_feats
            is_open = self._advisor_feat_open.get(seat.hero_id, bool(feats))
            role_str = seat.effective_role or ""
            count_hint = f"{len(feats)} aanbevolen" if feats else "geen data"
            feat_toggle = QPushButton(f"{'▾' if is_open else '▸'} Feats · {role_str} · {count_hint}")
            feat_toggle.setObjectName("featToggle")
            feat_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            feat_toggle.setFlat(True)
            feat_body = QWidget()
            feat_body.setStyleSheet("background: transparent; border: none;")
            feat_lyt = QVBoxLayout(feat_body)
            feat_lyt.setContentsMargins(8, 0, 0, 0)
            feat_lyt.setSpacing(4)
            if feats:
                for feat in feats[:8]:
                    feat_kind = {
                        "active": "feat_active",
                        "owned": "feat_owned",
                        "missing": "feat_missing",
                    }.get(feat.status, "body")
                    feat_lyt.addWidget(self._advisor_lbl(f"• {feat.name}", kind=feat_kind))
            else:
                feat_lyt.addWidget(self._advisor_lbl("Geen feat-advies voor deze champion/rol.", kind="muted"))
            feat_body.setVisible(is_open)

            def _make_toggle(btn, body, hid):
                def _toggle():
                    new_state = not body.isVisible()
                    body.setVisible(new_state)
                    self._advisor_feat_open[hid] = new_state
                    text = btn.text()
                    btn.setText(
                        text.replace("▸", "▾") if new_state else text.replace("▾", "▸")
                    )
                return _toggle

            feat_toggle.clicked.connect(_make_toggle(feat_toggle, feat_body, seat.hero_id))
            lyt.addWidget(feat_toggle)
            lyt.addWidget(feat_body)

            self._advisor_layout.addWidget(card)
            self._advisor_seat_card_frames[seat.seat] = card

        self._advisor_render_formation_visual(seat_report)

    def _advisor_highlight_seat_card(self, seat: int) -> None:
        card = self._advisor_seat_card_frames.get(seat)
        if card is None:
            return
        self._advisor_scroll.ensureWidgetVisible(card, 0, 80)

    def _advisor_render_formation_visual(self, seat_report) -> None:
        self._advisor_section(f"Formatie — {seat_report.formation_name}")
        nodes = [n for n in seat_report.visual_nodes if n.hero_id is not None]
        if not nodes:
            card = self._advisor_card()
            self._advisor_card_layout(card).addWidget(
                self._advisor_lbl("Geen formatie-posities beschikbaar.", kind="muted")
            )
            self._advisor_layout.addWidget(card)
            return

        try:
            from ic_gamedata.seat_advisor.role_inference import role_label
        except ImportError:
            role_label = lambda r: r or "?"  # noqa: E731

        pad = 16
        card_w, card_h = 100, 58
        min_x = min(n.x for n in nodes)
        min_y = min(n.y for n in nodes)
        width = int(max(n.x for n in nodes) - min_x + card_w + pad * 2)
        height = int(max(n.y for n in nodes) - min_y + card_h + pad * 2)
        height = max(180, min(height, 480))
        width = max(320, width)

        shell = self._advisor_card()
        shell_lyt = self._advisor_card_layout(shell)
        shell_lyt.addWidget(
            self._advisor_lbl(
                "Klik op een slot om naar de seat-kaart te springen. "
                "Enemies → rechts (front = naar rechts).",
                kind="muted",
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(height)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        board = QWidget()
        board.setFixedSize(width, height)
        board.setStyleSheet(
            f"background: {_ADVISOR_INPUT_BG}; border: 1px solid {_ADVISOR_INPUT_BORDER}; border-radius: 8px;"
        )

        for node in nodes:
            x = int((node.x - min_x) + pad)
            y = int((node.y - min_y) + pad)
            zone_bg = _FORMATION_ZONE_BG.get(node.zone, "#333338")
            border = "#dc2626" if node.has_issue else ("#1f6feb" if node.is_bud else "#52525b")
            role = node.effective_role or node.inferred_role or "flex"

            seat_frame = _FormationSeatCard(node.seat, board)
            seat_frame.setGeometry(x, y, card_w, card_h)
            seat_frame.setStyleSheet(
                f"QFrame {{ background: {zone_bg}; border: 2px solid {border}; border-radius: 8px; }}"
                f"QFrame:hover {{ border-color: {_ADVISOR_ACCENT}; }}"
            )
            seat_frame.clicked.connect(self._advisor_highlight_seat_card)

            seat_lyt = QVBoxLayout(seat_frame)
            seat_lyt.setContentsMargins(6, 4, 6, 4)
            seat_lyt.setSpacing(2)
            seat_lyt.addWidget(self._advisor_lbl(f"Slot {node.seat} · {node.zone}", kind="muted"))
            name_lbl = self._advisor_lbl((node.hero_name or "?")[:14], kind="subtitle")
            if node.is_bud:
                name_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #93c5fd;")
            seat_lyt.addWidget(name_lbl)
            seat_lyt.addWidget(self._advisor_lbl(role_label(role), kind="muted"))

        scroll.setWidget(board)
        shell_lyt.addWidget(scroll)
        self._advisor_layout.addWidget(shell)

    def _advisor_section(self, text: str) -> None:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; letter-spacing: 0.05em; "
            f"color: {_ADVISOR_MUTED}; padding: 18px 4px 6px 4px; "
            f"border: none; background: transparent;"
        )
        self._advisor_layout.addWidget(lbl)

    def _advisor_card(self, *, highlight: bool = False, accent_bar: str | None = None) -> QFrame:
        card = QFrame()
        card.setObjectName("advisorCard")
        card.setFrameShape(QFrame.Shape.NoFrame)
        card.setStyleSheet(_advisor_card_stylesheet())

        bar_color = accent_bar or (_ADVISOR_WARN_BAR if highlight else _ADVISOR_DIVIDER)
        outer = QHBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        accent = QFrame()
        accent.setObjectName("advisorAccent")
        accent.setStyleSheet(_advisor_accent_stylesheet(bar_color))
        outer.addWidget(accent)

        body = QWidget()
        body.setObjectName("advisorCardBody")
        body.setStyleSheet("background: transparent; border: none;")
        outer.addWidget(body, stretch=1)
        return card

    @staticmethod
    def _advisor_open_url(url: str) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------------ specializations tab

    def _init_specializations_state(self) -> None:
        self._spec_last_payload = None
        self._spec_last_goal = "bud"
        self._spec_last_context = "campaign"
        self._spec_analysing = False
        self._spec_pending_analysis: tuple[dict, str | None, bool] | None = None
        self._spec_pending_auto_refresh = False
        self._spec_has_results = False

    def _build_specializations_tab(self) -> QWidget:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        ctrl_row = QHBoxLayout()
        self._spec_goal = QComboBox()
        self._spec_goal.addItem("BUD / damage", "bud")
        self._spec_goal.addItem("Gold income", "gold")
        self._spec_goal.addItem("Speed / areas", "speed")
        self._spec_context = QComboBox()
        self._spec_context.addItem("Campaign", "campaign")
        self._spec_context.addItem("Events", "events")
        self._spec_context.addItem("Push", "push")
        self._spec_context.addItem("Modron", "modron")
        self._spec_btn_refresh = QPushButton("Verversen")
        self._spec_btn_refresh.clicked.connect(lambda: self._spec_analyze(auto_refresh=False))

        self._spec_goal.currentIndexChanged.connect(self._spec_on_options_changed)
        self._spec_context.currentIndexChanged.connect(self._spec_on_options_changed)

        ctrl_row.addWidget(QLabel("Doel:"))
        ctrl_row.addWidget(self._spec_goal)
        ctrl_row.addWidget(QLabel("Context:"))
        ctrl_row.addWidget(self._spec_context)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self._spec_btn_refresh)
        root.addLayout(ctrl_row)

        self._spec_status = QLabel("Data wordt elke 5 seconden automatisch ververst.")
        self._spec_status.setWordWrap(True)
        root.addWidget(self._spec_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._spec_scroll = scroll

        self._spec_content = QWidget()
        self._spec_content.setStyleSheet("background: transparent;")
        self._spec_layout = QVBoxLayout(self._spec_content)
        self._spec_layout.setSpacing(10)
        self._spec_layout.setContentsMargins(12, 8, 12, 16)
        scroll.setWidget(self._spec_content)
        scroll.setVisible(False)
        root.addWidget(scroll, stretch=1)
        return container

    def _spec_on_options_changed(self, *_args) -> None:
        if self._spec_last_payload is None:
            return
        self._spec_last_goal = self._spec_goal.currentData() or "bud"
        self._spec_last_context = self._spec_context.currentData() or "campaign"
        self._spec_analyze(auto_refresh=False)

    def _spec_analyze(self, *, auto_refresh: bool = False) -> None:
        if self._spec_analysing:
            return
        if not self._advisor_refresh_credentials():
            if not auto_refresh:
                self._spec_status.setText("Geen API-credentials. Ga naar Dashboard → Opnieuw zoeken.")
            return
        if self._dash_last_payload is None:
            if not auto_refresh:
                self._spec_status.setText("Nog geen API-data. Wacht op de volgende poll of start het dashboard.")
            return
        if not auto_refresh:
            self._spec_btn_refresh.setEnabled(False)
            self._spec_status.setText("Specialisaties analyseren…")
        self._start_specializations_analysis(
            self._dash_last_payload,
            None,
            auto_refresh=auto_refresh,
        )

    def _start_specializations_analysis(
        self,
        payload: dict,
        err: str | None,
        *,
        auto_refresh: bool,
    ) -> None:
        if self._spec_analysing:
            self._spec_pending_analysis = (payload, err, auto_refresh)
            return
        goal = self._spec_goal.currentData() or "bud"
        context = self._spec_context.currentData() or "campaign"
        self._spec_pending_auto_refresh = auto_refresh
        self._spec_analysing = True
        worker = _SpecializationsRunnable(goal, context, payload, err)
        worker.signals.done.connect(self._spec_on_done)
        worker.signals.error.connect(self._spec_on_error)
        QThreadPool.globalInstance().start(worker)

    def _schedule_pending_specializations_analysis(self) -> None:
        pending = self._spec_pending_analysis
        if pending is None or self._spec_analysing:
            return
        payload, err, auto_refresh = pending
        self._spec_pending_analysis = None
        self._start_specializations_analysis(payload, err, auto_refresh=auto_refresh)

    def _spec_on_done(self, result) -> None:
        payload, report, pending_items, err = result
        auto_refresh = self._spec_pending_auto_refresh
        self._spec_last_payload = payload
        self._spec_last_goal = report.goal
        self._spec_last_context = report.context
        self._spec_analysing = False
        self._spec_btn_refresh.setEnabled(True)
        status = f"Specialisatie-advies — {report.adventure_name}"
        if err:
            status = f"{status} ({err})"
        if auto_refresh:
            status = f"{status} · ververst {time.strftime('%H:%M:%S')}"
        self._spec_status.setText(status)
        reset_scroll = not auto_refresh or not self._spec_has_results
        self._spec_render_report(report, pending_items, reset_scroll=reset_scroll)
        self._schedule_pending_specializations_analysis()

    def _spec_on_error(self, msg: str) -> None:
        auto_refresh = self._spec_pending_auto_refresh
        self._spec_analysing = False
        self._spec_btn_refresh.setEnabled(True)
        if auto_refresh and self._spec_has_results:
            self._spec_status.setText(f"Verversen mislukt: {msg} (laatste resultaat behouden)")
        else:
            self._spec_status.setText(f"Fout: {msg}")
        self._schedule_pending_specializations_analysis()

    def _spec_clear(self) -> None:
        layout = self._spec_layout
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _spec_show_results_panel(self) -> None:
        if self._spec_has_results:
            return
        self._spec_has_results = True
        self._spec_scroll.setVisible(True)
        self._spec_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._spec_content.setStyleSheet("background: transparent;")

    def _spec_section(self, text: str) -> None:
        lbl = self._advisor_lbl(text, kind="title")
        lbl.setContentsMargins(0, 8, 0, 4)
        self._spec_layout.addWidget(lbl)

    def _spec_label_kind(self, status: str | None) -> str:
        return {
            "match": "spec_match",
            "pending": "spec_pending",
            "mismatch": "spec_mismatch",
        }.get(status or "", "spec_pending")

    def _spec_summary_lines(self, seats) -> list[tuple[str, str]]:
        try:
            from ic_gamedata.party_advisor_specializations import spec_summary_line
        except ImportError:
            spec_summary_line = None

        lines: list[tuple[str, str]] = []
        for seat in sorted(seats, key=lambda item: item.seat):
            if not seat.best_spec:
                continue
            status = getattr(seat, "spec_status", None) or "pending"
            if spec_summary_line is not None:
                text = spec_summary_line(
                    seat.hero_name,
                    recommended=seat.best_spec,
                    current_labels=seat.current_specs,
                    status=status,
                    is_bud=seat.is_bud,
                )
            else:
                name = seat.hero_name
                if seat.is_bud:
                    name += " (BUD)"
                current = ", ".join(seat.current_specs) if seat.current_specs else None
                if status == "mismatch" and current:
                    text = f"{name}: {current} → {seat.best_spec}"
                else:
                    text = f"{name}: {seat.best_spec}"
            lines.append((text, self._spec_label_kind(status)))
        return lines

    def _spec_render_pending(self, pending_items) -> None:
        if not pending_items:
            card = self._advisor_card()
            lyt = self._advisor_card_layout(card)
            lyt.addWidget(
                self._advisor_lbl(
                    "Geen open specialization-keuzes voor de actieve party.",
                    kind="body",
                )
            )
            self._spec_layout.addWidget(card)
            return

        try:
            from ic_gamedata.specialization_advice_text import human_specialization_reason
            from ic_gamedata.specializations import _active_adventure_context
        except ImportError:
            human_specialization_reason = None
            _active_adventure_context = None

        context = _active_adventure_context(self._spec_last_payload or {}) if _active_adventure_context else {}
        for item in pending_items:
            highlight = item.desired_option_index is not None
            card = self._advisor_card(highlight=highlight)
            lyt = self._advisor_card_layout(card)
            seat_str = f"slot {item.seat}" if item.seat is not None else "onbekende seat"
            lyt.addWidget(self._advisor_lbl(f"{item.hero_name} ({seat_str})", kind="subtitle"))
            options = " / ".join(option.name for option in item.options)
            if item.desired_option_index is not None:
                chosen = item.options[item.desired_option_index].name
                lyt.addWidget(self._advisor_lbl(f"Advies: {chosen}", kind="spec_pending"))
            else:
                lyt.addWidget(self._advisor_lbl("Advies: nog geen vaste keuze", kind="spec_pending"))
            if human_specialization_reason is not None:
                lyt.addWidget(
                    self._advisor_lbl(
                        f"Waarom: {human_specialization_reason(item, context)}",
                        kind="body",
                    )
                )
            elif item.rationale:
                lyt.addWidget(self._advisor_lbl(f"Waarom: {item.rationale}", kind="body"))
            lyt.addWidget(self._advisor_lbl(f"Open opties: {options}", kind="muted"))
            meta_parts: list[str] = []
            if item.data_source_version:
                meta_parts.append(f"dataset {item.data_source_version}")
            if item.rule_source_type:
                meta_parts.append(item.rule_source_type)
            if item.confidence:
                meta_parts.append(f"confidence {item.confidence}/5")
            if meta_parts:
                lyt.addWidget(self._advisor_lbl(" · ".join(meta_parts), kind="muted"))
            self._spec_layout.addWidget(card)

    def _spec_render_report(self, report, pending_items, *, reset_scroll: bool = True) -> None:
        self._spec_show_results_panel()
        self._spec_clear()

        context_labels = {"campaign": "Campaign", "events": "Events", "push": "Push", "modron": "Modron"}
        try:
            from ic_gamedata.party_advisor import goal_label as advisor_goal_label
        except ImportError:
            advisor_goal_label = lambda g: g  # noqa: E731
        goal_text = advisor_goal_label(report.goal)

        head = self._advisor_card()
        head_lyt = self._advisor_card_layout(head)
        head_lyt.addWidget(self._advisor_lbl("Specialization-advies", kind="subtitle"))
        head_lyt.addWidget(
            self._advisor_lbl(
                f"{goal_text}  ·  {context_labels.get(report.context, report.context)}  ·  {report.adventure_name}",
                kind="muted",
            )
        )
        self._spec_layout.addWidget(head)

        self._spec_section("Open keuzes")
        self._spec_render_pending(pending_items)

        if report.seat_report and report.seat_report.seats:
            summary_lines = self._spec_summary_lines(report.seat_report.seats)
            if summary_lines:
                self._spec_section("Aanbevolen specialisaties")
                card = self._advisor_card()
                lyt = self._advisor_card_layout(card)
                for line, kind in summary_lines:
                    lyt.addWidget(self._advisor_lbl(f"· {line}", kind=kind))
                self._spec_layout.addWidget(card)

        if report.formation_heroes and report.specialization_insights:
            self._spec_section("Per champion")
            try:
                from ic_gamedata.party_advisor_specializations import (
                    current_spec_labels_for_hero,
                    resolve_spec_display_status,
                    spec_summary_for_hero,
                )
            except ImportError:
                current_spec_labels_for_hero = None
                resolve_spec_display_status = None
                spec_summary_for_hero = None
            payload = self._spec_last_payload or {}
            for hero in sorted(
                report.formation_heroes,
                key=lambda h: (h.seat is None, h.seat or 0, h.name),
            ):
                if spec_summary_for_hero is None:
                    break
                spec_line = spec_summary_for_hero(hero.hero_id, report.specialization_insights)
                if not spec_line:
                    continue
                seat_str = f"slot {hero.seat}" if hero.seat is not None else "—"
                card = self._advisor_card()
                lyt = self._advisor_card_layout(card)
                lyt.addWidget(self._advisor_lbl(f"{hero.name} ({seat_str})", kind="subtitle"))
                spec_kind = "spec_pending"
                if resolve_spec_display_status is not None and current_spec_labels_for_hero is not None:
                    seat_match = next(
                        (s for s in (report.seat_report.seats if report.seat_report else []) if s.hero_id == hero.hero_id),
                        None,
                    )
                    recommended = seat_match.best_spec if seat_match and seat_match.best_spec else None
                    if recommended:
                        current_labels = current_spec_labels_for_hero(
                            payload, hero.hero_id, report.specialization_insights
                        )
                        status = resolve_spec_display_status(
                            hero.hero_id,
                            report.specialization_insights,
                            recommended=recommended,
                            current_labels=current_labels,
                        )
                        spec_kind = self._spec_label_kind(status)
                lyt.addWidget(self._advisor_lbl(spec_line, kind=spec_kind))
                self._spec_layout.addWidget(card)

        if report.specialization_insights:
            self._spec_section("Specialization & formatie")
            for insight in report.specialization_insights:
                highlight = insight.status in {"open_tier", "mismatch"}
                card = self._advisor_card(highlight=highlight)
                lyt = self._advisor_card_layout(card)
                seat_str = f"slot {insight.seat}" if insight.seat is not None else "bench"
                lyt.addWidget(self._advisor_lbl(f"{insight.headline} ({seat_str})", kind="subtitle"))
                detail = insight.detail
                if insight.rule_source_type == "heuristic":
                    detail = f"{detail} (generieke placeholder-regel)"
                detail_kind = {
                    "open_tier": "spec_pending",
                    "mismatch": "spec_mismatch",
                    "matches": "spec_match",
                }.get(insight.status, "body")
                lyt.addWidget(self._advisor_lbl(detail, kind=detail_kind))
                meta_str = f"{insight.status} · {insight.rule_source_type}"
                if insight.confidence:
                    meta_str += f" · confidence {insight.confidence}/5"
                lyt.addWidget(self._advisor_lbl(meta_str, kind="muted"))
                self._spec_layout.addWidget(card)

        if report.tips:
            self._spec_section("Composition-tips")
            for tip in report.tips:
                card = self._advisor_card()
                lyt = self._advisor_card_layout(card)
                lyt.addWidget(self._advisor_lbl(f"Tip {tip.priority} · {tip.title}", kind="subtitle"))
                lyt.addWidget(self._advisor_lbl(tip.detail, kind="body"))
                self._spec_layout.addWidget(card)

        self._spec_layout.addStretch(1)
        if reset_scroll:
            self._spec_scroll.verticalScrollBar().setValue(0)

    # ------------------------------------------------------------------ central API poll

    def _init_api_poll_state(self) -> None:
        self._api_fetch_inflight = False
        self._api_advisor_after = False
        self._api_auto_refresh = False
        self._api_poll_timer = QTimer(self)
        self._api_poll_timer.setInterval(5000)
        self._api_poll_timer.timeout.connect(
            lambda: self._request_api_poll(advisor_after=False, auto_refresh=True)
        )

    def _api_log_path(self) -> Path | None:
        if self._dash_install and self._dash_install.web_request_log:
            return Path(self._dash_install.web_request_log)
        return None

    def _request_api_poll(self, *, advisor_after: bool = False, auto_refresh: bool = False) -> None:
        if self._api_fetch_inflight:
            if advisor_after and not auto_refresh:
                self._advisor_status.setText("Data wordt al opgehaald…")
            return
        if self._dash_install is None or self._dash_credentials is None:
            self._dash_refresh_install()
        log_path = self._api_log_path()
        if log_path is not None:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(log_path)
            if fresh is not None:
                self._dash_credentials = fresh
        if self._dash_credentials is None:
            if advisor_after and not auto_refresh:
                self._advisor_on_error("Geen API-credentials.")
            return

        self._api_fetch_inflight = True
        self._api_advisor_after = advisor_after
        self._api_auto_refresh = auto_refresh
        worker = _ApiFetchRunnable(self._dash_credentials, log_path, self._dash_tailer)
        worker.signals.done.connect(self._api_on_fetch_done)
        QThreadPool.globalInstance().start(worker)

    def _api_on_fetch_done(self, result: dict) -> None:
        self._api_fetch_inflight = False
        advisor_after = self._api_advisor_after
        auto_refresh = self._api_auto_refresh
        if result.get("error"):
            err = str(result["error"])
            self._dash_api_detail = err
            if advisor_after:
                if not auto_refresh:
                    self._advisor_btn_analyze.setEnabled(True)
                    self._advisor_on_error(err)
                elif not self._advisor_has_results:
                    self._advisor_status.setText(f"Wachten op API-data… ({err})")
            return

        credentials = result.get("credentials")
        if credentials is not None:
            self._dash_credentials = credentials
        self._api_apply_fetch_result(
            result,
            advisor_after=advisor_after,
            auto_refresh=auto_refresh,
        )

    def _api_apply_fetch_result(
        self,
        result: dict,
        *,
        advisor_after: bool,
        auto_refresh: bool,
    ) -> None:
        payload = result.get("payload")
        api_snap = result.get("api_snap")
        snap = result.get("snap")
        err = result.get("err")
        api_detail = result.get("api_detail")
        if api_detail:
            self._dash_api_detail = api_detail
        if payload is not None:
            self._dash_last_payload = payload
            new_party_id = self._party_id_from_payload(payload)
            party_changed = (
                self._advisor_last_party_id is not None
                and new_party_id is not None
                and new_party_id != self._advisor_last_party_id
            )
            self._formation_sync.emit(payload)
            self._caption_refresh.emit()
        else:
            party_changed = False
        if api_snap is not None:
            self._dash_last_api_snap = api_snap
        if snap is not None:
            self._dash_last_update = time.time()
            if payload is not None:
                snap = self._dash_refresh_snapshot(snap, payload)
            if self._dash_active and self._dash_tracker is not None:
                mem_area, mem_gems = self._dash_read_memory()
                if mem_area is not None or mem_gems is not None:
                    self._dash_tracker.add_memory_area(
                        mem_area,
                        gems=mem_gems,
                        active_party_index=snap.active_party_index,
                    )
                self._dash_tracker.add_snapshot(snap, api_snapshot=api_snap)
                self._dash_update_labels()
        if (
            payload is not None
            and not self._advisor_has_results
            and not self._advisor_analysing
        ):
            self._start_advisor_analysis(
                payload,
                err,
                auto_refresh=True,
                party_changed=False,
            )
            if not self._spec_has_results and not self._spec_analysing:
                self._start_specializations_analysis(
                    payload,
                    err,
                    auto_refresh=True,
                )
        elif party_changed and payload is not None:
            self._start_advisor_analysis(
                payload,
                err,
                auto_refresh=True,
                party_changed=True,
            )
            self._start_specializations_analysis(
                payload,
                err,
                auto_refresh=True,
            )
        elif advisor_after:
            if payload is not None:
                self._start_advisor_analysis(
                    payload,
                    err,
                    auto_refresh=auto_refresh,
                    party_changed=party_changed,
                )
                self._start_specializations_analysis(
                    payload,
                    err,
                    auto_refresh=auto_refresh,
                )
            elif not auto_refresh:
                self._advisor_btn_analyze.setEnabled(True)
                self._advisor_on_error(err or "Geen API-data ontvangen.")
            elif auto_refresh and not self._advisor_has_results:
                self._advisor_status.setText(err or "Wachten op API-data…")

    # ------------------------------------------------------------------ dashboard

    def _init_dashboard_state(self) -> None:
        self._dash_install = None
        self._dash_tailer = None
        self._dash_tracker = None
        self._dash_credentials = None
        self._dash_active = False
        self._dash_poll_tick = 0
        self._dash_resolver = None
        self._dash_memory_detail = ""
        self._dash_api_detail = ""
        self._dash_last_update = None
        self._dash_last_api_snap = None
        self._dash_last_memory_area = None
        self._dash_last_memory_gems = None
        self._dash_last_memory_modron_goal = None
        self._dash_result_queue: queue.Queue[dict] = queue.Queue(maxsize=2)
        self._dash_fetch_inflight = False
        self._dash_fetch_thread: threading.Thread | None = None
        self._dash_last_payload = None
        self._dash_goal_runs_expanded: dict[int, bool] = {}

    def _dash_get_ui_hint(self) -> int | None:
        raw = (self._src_ui_hint.text() or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _dash_read_memory(self, ui_hint: int | None = None) -> tuple[int | None, int | None]:
        try:
            from ic_reader.resolver import create_resolver
        except ImportError:
            self._dash_memory_detail = "ic_reader niet beschikbaar (pip install psutil)"
            return None, None
        try:
            if self._dash_resolver is None:
                self._dash_resolver = create_resolver(debug=False)
                self._dash_resolver.connect()
            resolved_area = self._dash_resolver.resolve_current_area(
                ui_hint_area=self._dash_get_ui_hint() if ui_hint is None else ui_hint
            )
            resolved_gems = self._dash_resolver.resolve_gems_this_reset()
        except Exception as exc:
            self._dash_memory_detail = str(exc)
            return None, None

        area = int(resolved_area.value) if resolved_area.value is not None else None
        gems = int(resolved_gems.value) if resolved_gems.value is not None else None
        if area is not None:
            self._dash_last_memory_area = area
        if gems is not None:
            self._dash_last_memory_gems = gems
        parts: list[str] = []
        if area is not None:
            parts.append(f"area={area} ({resolved_area.candidate_id or '?'}, {resolved_area.confidence:.1f})")
        if gems is not None:
            parts.append(f"gems={gems} ({resolved_gems.candidate_id or '?'}, {resolved_gems.confidence:.1f})")
        self._dash_memory_detail = "memory: " + " · ".join(parts) if parts else "memory: geen offsets/data"
        return area, gems

    def _dash_read_modron_reset_area(self) -> int | None:
        try:
            from ic_reader.resolver import create_resolver
        except ImportError:
            return None
        try:
            if self._dash_resolver is None:
                self._dash_resolver = create_resolver(debug=False)
                self._dash_resolver.connect()
            resolved = self._dash_resolver.resolve_modron_reset_area()
            if resolved.value is None:
                return None
            return int(resolved.value)
        except Exception:
            return None

    def _dash_refresh_snapshot(self, snap, payload):
        mem_modron = self._dash_read_modron_reset_area()
        if mem_modron is not None:
            self._dash_last_memory_modron_goal = mem_modron
        try:
            from ic_gamedata.party_display import refresh_snapshot_from_payload
        except ImportError:
            return snap
        if payload is None:
            return snap
        return refresh_snapshot_from_payload(
            snap,
            payload,
            memory_modron_area=mem_modron,
        )

    def _dash_disconnect_memory(self) -> None:
        if self._dash_resolver is not None:
            try:
                self._dash_resolver.disconnect()
            except Exception:
                pass
            self._dash_resolver = None

    @staticmethod
    def _format_gold(value) -> str:
        try:
            from ic_gamedata.formatting import format_gold
        except ImportError:
            return IdleChampionsMainWindow._dash_format_number(value)
        return format_gold(value)

    @staticmethod
    def _dash_format_number(value) -> str:
        if value is None:
            return "—"
        try:
            num = float(value)
        except (TypeError, ValueError):
            return "—"
        if abs(num) >= 1000:
            return f"{num:,.0f}"
        if abs(num) >= 10:
            return f"{num:.1f}"
        return f"{num:.2f}"

    @staticmethod
    def _dash_format_duration(seconds: float) -> str:
        total = max(int(seconds), 0)
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def _dash_format_rate_window(window_sec: float | None) -> str:
        if window_sec is None:
            return "warmt op (<3 min)"
        minutes = max(int(round(window_sec / 60)), 1)
        if minutes >= 15:
            return "15 min venster"
        return f"{minutes} min venster"

    def _dash_load_tracker(self) -> None:
        if self._dash_tracker is None:
            try:
                from ic_gamedata.stats import StatsTracker
            except ImportError:
                from ic_gamedata import StatsTracker
            self._dash_tracker = StatsTracker()

    def _dash_refresh_install(self) -> None:
        try:
            from ic_gamedata.paths import InstallSource, find_game_install
        except ImportError as exc:
            self._src_install_lbl.setText(f"ic_gamedata ontbreekt: {exc}")
            self._src_log_lbl.setText("—")
            return
        info = find_game_install()
        self._dash_install = info
        if info is None:
            self._src_install_lbl.setText("Niet gevonden (Epic/Steam/handmatig pad)")
            self._src_log_lbl.setText("—")
            self._dash_status.setText("Geen installatie gevonden. Start het spel of gebruik handmatig pad.")
            self._dash_tailer = None
            return
        source_labels = {
            InstallSource.EPIC: "Epic Games",
            InstallSource.STEAM: "Steam",
            InstallSource.MANUAL: "Handmatig",
            InstallSource.UNKNOWN: "Onbekend",
        }
        self._src_install_lbl.setText(f"{source_labels.get(info.source, info.source.value)} — {info.install_dir}")
        self._src_manual_path.setText(str(info.install_dir))
        if info.web_request_log is None:
            self._src_log_lbl.setText("webRequestLog.txt nog niet aanwezig")
            self._dash_tailer = None
            self._dash_credentials = None
            return
        self._src_log_lbl.setText(str(info.web_request_log))
        try:
            from ic_gamedata.log_tailer import WebRequestLogTailer
            from ic_gamedata.credentials import extract_credentials_from_log
        except ImportError:
            from ic_gamedata import WebRequestLogTailer, extract_credentials_from_log
        self._dash_tailer = WebRequestLogTailer(info.web_request_log)
        self._dash_tailer.bootstrap()
        self._dash_credentials = extract_credentials_from_log(info.web_request_log)
        if self._dash_credentials is not None:
            self._dash_status.setText("Klaar. API wordt elke 5 seconden automatisch ververst.")
            self._request_api_poll()
        else:
            self._dash_status.setText("Log gevonden maar nog geen credentials.")

    def _dash_save_manual_path(self) -> None:
        try:
            from ic_gamedata.paths import GAMEDATA_CONFIG_PATH
        except ImportError:
            QMessageBox.critical(self, "Dashboard", "ic_gamedata module ontbreekt.")
            return
        raw = (self._src_manual_path.text() or "").strip()
        config_path = Path(GAMEDATA_CONFIG_PATH)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"install_path": raw}
        try:
            config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Dashboard", f"Kon config niet opslaan:\n{exc}")
            return
        self._dash_refresh_install()
        if raw:
            QMessageBox.information(self, "Dashboard", "Handmatig pad opgeslagen in config/gamedata.json")

    def _dash_fetch_snapshot(self):
        log_path = self._api_log_path()
        if log_path is not None:
            try:
                from ic_gamedata.credentials import extract_credentials_from_log
            except ImportError:
                from ic_gamedata import extract_credentials_from_log
            fresh = extract_credentials_from_log(log_path)
            if fresh is not None:
                self._dash_credentials = fresh
        try:
            from ic_gamedata.snapshot_fetch import fetch_merged_snapshot
        except ImportError:
            from ic_gamedata import fetch_merged_snapshot
        credentials, payload, api_snap, snap, err, api_detail = fetch_merged_snapshot(
            self._dash_credentials,
            log_path,
            self._dash_tailer,
        )
        if credentials is not None:
            self._dash_credentials = credentials
        if api_detail:
            self._dash_api_detail = api_detail
        if payload is not None:
            self._dash_last_payload = payload
            self._formation_sync.emit(payload)
        if api_snap is not None:
            self._dash_last_api_snap = api_snap
        if snap is not None:
            self._dash_last_update = time.time()
        return snap

    def _dash_start(self) -> None:
        if self._dash_active:
            return
        if self._dash_credentials is None and self._dash_tailer is None:
            self._dash_refresh_install()
        self._dash_load_tracker()
        if self._dash_tracker is None:
            return
        self._dash_tracker.reset()
        snap = self._dash_fetch_snapshot()
        if snap is not None and self._dash_last_payload is not None:
            snap = self._dash_refresh_snapshot(snap, self._dash_last_payload)
        if snap is not None:
            self._dash_tracker.add_snapshot(snap, api_snapshot=self._dash_last_api_snap)
        mem_area, mem_gems = self._dash_read_memory()
        if (mem_area is not None or mem_gems is not None) and self._dash_tracker is not None:
            self._dash_tracker.add_memory_area(
                mem_area,
                gems=mem_gems,
                active_party_index=snap.active_party_index if snap is not None else None,
            )
        self._dash_active = True
        self._dash_poll_tick = 0
        self._dash_toggle_btn.setText("Stop dashboard")
        self._dash_status.setText("Dashboard actief.")
        self._dash_update_labels()
        self._dash_timer.start()

    def _dash_auto_start(self) -> None:
        if self._dash_active:
            return
        if self._dash_credentials is None and self._dash_tailer is None:
            self._dash_refresh_install()
        self._dash_start()
        if not self._dash_active:
            self._dash_status.setText(
                "Dashboard kon niet starten — opnieuw proberen zodra Idle Champions draait."
            )
            QTimer.singleShot(15000, self._dash_auto_start)
            return
        if self._dash_last_update is None and self._dash_last_memory_area is None:
            self._dash_status.setText(
                "Dashboard actief — wachten op speldata. Start Idle Champions voor live rates."
            )

    def _dash_stop(self) -> None:
        self._dash_active = False
        self._dash_fetch_inflight = False
        self._dash_timer.stop()
        self._dash_toggle_btn.setText("Start dashboard")
        self._dash_status.setText("Dashboard gestopt.")

    def _dash_toggle(self) -> None:
        if self._dash_active:
            self._dash_stop()
        else:
            self._dash_start()

    def _dash_poll_once(self) -> None:
        if not self._dash_active:
            return
        self._dash_poll_tick += 1
        self._dash_apply_pending_results()
        self._dash_request_async_poll()

    def _dash_request_async_poll(self) -> None:
        if self._dash_fetch_inflight or self._dash_tracker is None:
            return
        self._dash_fetch_inflight = True
        ui_hint = self._dash_get_ui_hint()

        def _worker() -> None:
            result = {"mem_area": None, "mem_gems": None, "error": None}
            try:
                mem_area, mem_gems = self._dash_read_memory(ui_hint=ui_hint)
                result["mem_area"] = mem_area
                result["mem_gems"] = mem_gems
            except Exception as exc:
                result["error"] = str(exc)
            finally:
                try:
                    self._dash_result_queue.put_nowait(result)
                except queue.Full:
                    try:
                        self._dash_result_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._dash_result_queue.put_nowait(result)

        self._dash_fetch_thread = threading.Thread(target=_worker, daemon=True, name="ic-pyside-dash")
        self._dash_fetch_thread.start()

    def _dash_apply_pending_results(self) -> None:
        applied = False
        while True:
            try:
                result = self._dash_result_queue.get_nowait()
            except queue.Empty:
                break
            self._dash_fetch_inflight = False
            applied = True
            if result.get("error"):
                self._dash_api_detail = str(result["error"])
                continue
            if self._dash_tracker is not None:
                mem_area = result.get("mem_area")
                mem_gems = result.get("mem_gems")
                if mem_area is not None or mem_gems is not None:
                    self._dash_tracker.add_memory_area(
                        mem_area,
                        gems=mem_gems,
                        active_party_index=self._dash_tracker.latest.active_party_index
                        if self._dash_tracker.latest is not None
                        else None,
                    )
        if applied:
            self._dash_update_labels()

    def _app_title_base(self) -> str:
        return "Idle Champions"

    def _update_app_caption(
        self,
        party_index: int | None = None,
        adventure_id: int | None = None,
    ) -> None:
        title = self._app_title_base()
        if party_index is not None:
            title += f" · Party {party_index}"
            try:
                from ic_gamedata.adventure_names import adventure_display_name
            except ImportError:
                adventure_display_name = None  # type: ignore[assignment,misc]
            adventure_name = (
                adventure_display_name(self._dash_last_payload, adventure_id)
                if adventure_display_name is not None
                else None
            )
            if adventure_name:
                title += f" - {adventure_name}"
        self.setWindowTitle(title)

    def _dash_party_from_snapshot(self, snap, party_index: int):
        if snap is None:
            return None
        for party in snap.parties:
            if party.party_index == party_index:
                return party
        return None

    def _dash_caption_party(self, latest):
        if self._dash_last_api_snap is not None and self._dash_last_api_snap.active_party_index is not None:
            api_party = self._dash_party_from_snapshot(
                self._dash_last_api_snap,
                self._dash_last_api_snap.active_party_index,
            )
            if api_party is not None:
                return api_party
        return self._dash_active_party(latest)

    def _refresh_app_caption_from_snapshots(self) -> None:
        latest = self._dash_tracker.latest if self._dash_tracker is not None else None
        party = self._dash_caption_party(latest)
        if party is None:
            self._update_app_caption()
            return
        adventure_id = party.adventure_id if party.adventure_id is not None and party.adventure_id >= 0 else None
        self._update_app_caption(party.party_index, adventure_id)

    def _dash_running_parties(self, latest):
        snap = self._dash_last_api_snap if self._dash_last_api_snap is not None else latest
        if snap is None:
            return ()
        running = tuple(sorted(snap.running_parties, key=lambda p: p.party_index))
        if running:
            return running
        return tuple(sorted(snap.parties, key=lambda p: p.party_index))

    def _dash_is_active_party(self, party_index: int) -> bool:
        if self._dash_last_api_snap is not None and self._dash_last_api_snap.active_party_index is not None:
            return party_index == self._dash_last_api_snap.active_party_index
        latest = self._dash_tracker.latest if self._dash_tracker is not None else None
        if latest is not None and latest.active_party_index is not None:
            return party_index == latest.active_party_index
        return False

    def _dash_party_title(self, party_index: int, adventure_id: int | None, is_active: bool) -> str:
        if adventure_id is not None and adventure_id >= 0:
            try:
                from ic_gamedata.adventure_names import adventure_display_name
            except ImportError:
                adventure_display_name = None  # type: ignore[assignment,misc]
            name = (
                adventure_display_name(self._dash_last_payload, adventure_id)
                if adventure_display_name is not None
                else None
            )
            adv = f", {name}" if name else f", adventure {adventure_id}"
        else:
            adv = ""
        active = " · actief venster" if is_active else ""
        return f"Party {party_index}{adv}{active}"

    def _dash_enriched_party(self, tracked):
        api_party = None
        if self._dash_last_api_snap is not None:
            api_party = self._dash_party_from_snapshot(
                self._dash_last_api_snap,
                tracked.party_index,
            )
        is_active = self._dash_is_active_party(tracked.party_index)
        try:
            from ic_gamedata.dashboard_enrich import enrich_party_for_dashboard
        except ImportError:
            return tracked
        party, cleared = enrich_party_for_dashboard(
            tracked,
            api_party,
            is_active=is_active,
            memory_area=self._dash_last_memory_area if is_active else None,
            memory_gems=self._dash_last_memory_gems if is_active else None,
            clear_stale_memory_gems=True,
        )
        if cleared:
            self._dash_last_memory_gems = None
        try:
            from ic_gamedata.party_display import refresh_party_from_payload
        except ImportError:
            return party
        return refresh_party_from_payload(
            party,
            self._dash_last_payload,
            memory_modron_area=self._dash_last_memory_modron_goal if is_active else None,
        )

    def _dash_run_duration_sec(self, party) -> float | None:
        if party.seconds_since_reset is None:
            return None
        elapsed = float(party.seconds_since_reset)
        if self._dash_last_update is not None:
            elapsed += max(0.0, time.time() - self._dash_last_update)
        return elapsed

    def _dash_ensure_party_tile(self, party_index: int) -> dict[str, QWidget]:
        if party_index in self._dash_party_widgets:
            return self._dash_party_widgets[party_index]

        box = QGroupBox(f"Party {party_index}")
        box.setProperty("party_index", party_index)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(box)
        lbl_area = QLabel("Area: —")
        lbl_run = QLabel("Run: —")
        lbl_gold = QLabel("Gold: —")
        lbl_gold_gained = QLabel("Gold verdiend: —")
        lbl_gold_rate = QLabel("Gold/kw: —")
        lbl_gems = QLabel("Gems deze run: —")
        lbl_areas_rate = QLabel("Areas/kw: —")
        goal_runs_row = QWidget()
        goal_runs_row_layout = QHBoxLayout(goal_runs_row)
        goal_runs_row_layout.setContentsMargins(0, 0, 0, 0)
        lbl_goal_runs = QLabel("")
        btn_goal_runs_expand = QPushButton("▶")
        btn_goal_runs_expand.setFixedWidth(28)
        btn_goal_runs_expand.setToolTip("Toon eerdere doel-runs")
        goal_runs_row_layout.addWidget(lbl_goal_runs, stretch=1)
        goal_runs_row_layout.addWidget(btn_goal_runs_expand)
        goal_runs_extra = QWidget()
        goal_runs_extra_layout = QVBoxLayout(goal_runs_extra)
        goal_runs_extra_layout.setContentsMargins(0, 0, 0, 0)
        goal_runs_extra_layout.setSpacing(2)
        lbl_patron = QLabel("")
        lbl_briv = QLabel("")
        lbl_warps = QLabel("")
        lbl_buffs = QLabel("")
        all_labels = (
            lbl_area,
            lbl_run,
            lbl_gold,
            lbl_gold_gained,
            lbl_gold_rate,
            lbl_gems,
            lbl_areas_rate,
            lbl_patron,
            lbl_briv,
            lbl_warps,
            lbl_buffs,
        )
        for widget in all_labels:
            widget.setWordWrap(True)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        for widget in (
            lbl_area,
            lbl_run,
            lbl_gold,
            lbl_gold_gained,
            lbl_gold_rate,
            lbl_gems,
            lbl_areas_rate,
        ):
            layout.addWidget(widget)
        layout.addWidget(goal_runs_row)
        goal_runs_row.hide()
        layout.addWidget(goal_runs_extra)
        goal_runs_extra.hide()
        for widget in (lbl_patron, lbl_briv, lbl_warps, lbl_buffs):
            layout.addWidget(widget)
            widget.hide()

        btn_goal_runs_expand.clicked.connect(
            lambda _checked=False, idx=party_index: self._dash_toggle_goal_runs(idx)
        )
        widgets: dict[str, QWidget] = {
            "frame": box,
            "area": lbl_area,
            "run": lbl_run,
            "gold": lbl_gold,
            "gold_gained": lbl_gold_gained,
            "gold_rate": lbl_gold_rate,
            "gems": lbl_gems,
            "areas_rate": lbl_areas_rate,
            "goal_runs_row": goal_runs_row,
            "goal_runs": lbl_goal_runs,
            "goal_runs_expand": btn_goal_runs_expand,
            "goal_runs_extra": goal_runs_extra,
            "goal_runs_extra_layout": goal_runs_extra_layout,
            "patron": lbl_patron,
            "briv": lbl_briv,
            "warps": lbl_warps,
            "buffs": lbl_buffs,
        }
        self._dash_party_widgets[party_index] = widgets
        return widgets

    def _dash_active_party(self, latest):
        if latest is None:
            return None
        active_id = latest.active_party_index
        if active_id is not None:
            for party in latest.parties:
                if party.party_index == active_id and party.is_running():
                    return party
        for party in latest.running_parties:
            if party.is_active:
                return party
        running = latest.running_parties
        return running[0] if running else None

    def _dash_adventure_name(self, adventure_id: int | None) -> str | None:
        if adventure_id is None or adventure_id < 0:
            return None
        try:
            from ic_gamedata.adventure_names import adventure_display_name
        except ImportError:
            return None
        return adventure_display_name(self._dash_last_payload, adventure_id)

    @staticmethod
    def _dash_apply_optional_label(label: QLabel, text: str | None) -> None:
        if text:
            label.setText(text)
            label.show()
        else:
            label.hide()

    def _dash_toggle_goal_runs(self, party_index: int) -> None:
        expanded = self._dash_goal_runs_expanded.get(party_index, False)
        self._dash_goal_runs_expanded[party_index] = not expanded
        widgets = self._dash_party_widgets.get(party_index)
        if widgets is None:
            return
        extra = widgets.get("goal_runs_extra")
        expand_btn = widgets.get("goal_runs_expand")
        if extra is not None:
            extra.setVisible(self._dash_goal_runs_expanded[party_index])
        if expand_btn is not None:
            expand_btn.setText("▼" if self._dash_goal_runs_expanded[party_index] else "▶")

    def _dash_apply_goal_runs(self, widgets: dict[str, QWidget], view) -> None:
        summary = view.goal_runs_summary
        row = widgets.get("goal_runs_row")
        label = widgets.get("goal_runs")
        expand_btn = widgets.get("goal_runs_expand")
        extra = widgets.get("goal_runs_extra")
        extra_layout = widgets.get("goal_runs_extra_layout")
        if (
            summary is None
            or row is None
            or label is None
            or expand_btn is None
            or extra is None
            or extra_layout is None
        ):
            if row is not None:
                row.hide()
            if extra is not None:
                extra.hide()
            return

        label.setText(summary)
        row.show()

        while extra_layout.count():
            item = extra_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for line in view.goal_runs_extra:
            line_label = QLabel(line)
            line_label.setWordWrap(True)
            extra_layout.addWidget(line_label)

        has_extra = bool(view.goal_runs_extra)
        expand_btn.setVisible(has_extra)
        if not has_extra:
            extra.hide()
            expand_btn.setText("▶")
            return

        party_index = widgets["frame"].property("party_index")
        expanded = (
            self._dash_goal_runs_expanded.get(party_index, False)
            if party_index is not None
            else False
        )
        expand_btn.setText("▼" if expanded else "▶")
        extra.setVisible(expanded)

    def _dash_apply_party_tile(self, widgets: dict[str, QWidget], view) -> None:
        widgets["frame"].setTitle(view.title)
        widgets["area"].setText(view.area)
        widgets["run"].setText(view.run)
        widgets["gold"].setText(view.gold)
        widgets["gold_gained"].setText(view.gold_gained)
        widgets["gold_rate"].setText(view.gold_rate)
        widgets["gems"].setText(view.gems)
        widgets["areas_rate"].setText(view.areas_rate)
        self._dash_apply_goal_runs(widgets, view)
        self._dash_apply_optional_label(widgets["patron"], view.patron)
        self._dash_apply_optional_label(widgets["briv"], view.briv)
        self._dash_apply_optional_label(widgets["warps"], view.warps)
        self._dash_apply_optional_label(widgets["buffs"], view.buffs)

    def _dash_update_labels(self) -> None:
        tracker = self._dash_tracker
        if tracker is None:
            return
        stats = tracker.compute()
        latest = tracker.latest
        detail_parts = []
        if self._dash_memory_detail:
            detail_parts.append(self._dash_memory_detail)
        if self._dash_api_detail:
            detail_parts.append(self._dash_api_detail)
        if self._dash_last_update:
            detail_parts.append(f"laatste update: {time.strftime('%H:%M:%S', time.localtime(self._dash_last_update))}")
        self._dash_detail.setText(" · ".join(detail_parts))

        self._refresh_app_caption_from_snapshots()

        party_stats_map = {p.party_index: p for p in stats.parties} if stats else {}
        base_parties = self._dash_running_parties(latest)
        seen: set[int] = set()

        for tile_index, base in enumerate(base_parties):
            tracked = None
            if latest is not None:
                for party in latest.parties:
                    if party.party_index == base.party_index:
                        tracked = party
                        break
            if tracked is None:
                tracked = base
            party = self._dash_enriched_party(tracked)
            seen.add(party.party_index)
            widgets = self._dash_ensure_party_tile(party.party_index)
            tile = widgets["frame"]
            is_active = self._dash_is_active_party(party.party_index)
            self._dash_parties_layout.removeWidget(tile)
            self._dash_parties_layout.addWidget(tile, tile_index // 2, tile_index % 2)

            ps = party_stats_map.get(party.party_index)
            use_memory_gems = is_active and self._dash_last_memory_gems is not None
            if use_memory_gems and not (
                party.gems_this_reset is not None
                and party.current_area is not None
                and party.current_area < 40
                and self._dash_last_memory_gems > party.gems_this_reset + 50
            ):
                gems = self._dash_last_memory_gems
                gem_prefix = ""
            else:
                gems = ps.gems_this_reset if ps is not None else party.gems_this_reset
                gem_prefix = "~" if ps is not None and ps.gems_estimated else ""

            try:
                from ic_gamedata.dashboard_tiles import build_party_tile_view
            except ImportError:
                build_party_tile_view = None  # type: ignore[assignment,misc]

            if build_party_tile_view is not None:
                view = build_party_tile_view(
                    party,
                    ps=ps,
                    is_active=is_active,
                    adventure_name=self._dash_adventure_name(party.adventure_id),
                    run_sec=self._dash_run_duration_sec(party),
                    gems=gems,
                    gem_prefix=gem_prefix,
                    format_gold=self._format_gold,
                    format_number=self._dash_format_number,
                    format_duration=self._dash_format_duration,
                    format_rate_window=self._dash_format_rate_window,
                )
                self._dash_apply_party_tile(widgets, view)
            else:
                tile.setTitle(self._dash_party_title(party.party_index, party.adventure_id, is_active))
                widgets["area"].setText(
                    f"Area: {party.current_area if party.current_area is not None else '—'}"
                )

        for idx in list(self._dash_party_widgets):
            if idx not in seen:
                widget = self._dash_party_widgets[idx]["frame"]
                self._dash_parties_layout.removeWidget(widget)
                widget.deleteLater()
                del self._dash_party_widgets[idx]

    def _dash_reset_session(self) -> None:
        self._dash_load_tracker()
        if self._dash_tracker is not None:
            self._dash_tracker.reset()
        snap = self._dash_fetch_snapshot()
        if snap is not None and self._dash_last_payload is not None:
            snap = self._dash_refresh_snapshot(snap, self._dash_last_payload)
        if snap is not None and self._dash_tracker is not None:
            self._dash_tracker.add_snapshot(snap, api_snapshot=self._dash_last_api_snap)
        mem_area, mem_gems = self._dash_read_memory()
        if (mem_area is not None or mem_gems is not None) and self._dash_tracker is not None:
            self._dash_tracker.add_memory_area(
                mem_area,
                gems=mem_gems,
                active_party_index=snap.active_party_index if snap is not None else None,
            )
        self._dash_update_labels()
        self._dash_status.setText("Sessie gereset — nieuwe baseline gezet.")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_automation()
        self._dash_stop()
        self._dash_disconnect_memory()
        super().closeEvent(event)


def run_pyside_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IdleChampionsMainWindow()
    window.show()
    return app.exec()

