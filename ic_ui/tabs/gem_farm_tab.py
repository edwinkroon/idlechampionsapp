"""Gem Farm tab: Briv intelligence, Co-Pilot advise, health, events."""

from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
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

from ic_automation import win_input
from ic_automation.copilot_settings import CopilotKeySettings
from ic_gamedata.gem_farm.config_store import GemFarmConfigStore
from ic_gamedata.gem_farm.event_log import append_farm_event, load_farm_events
from ic_gamedata.gem_farm.models import (
    BrivGearOverride,
    CopilotSettings,
    FarmEvent,
    FarmHealthThresholds,
    FarmProfile,
)
from ic_gamedata.gem_farm.formation_hotkeys import (
    format_hotkeys_summary,
    formation_save_names_for_party,
    suggest_formation_names,
)
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.theme import ACCENT, SUCCESS, TEXT_MUTED, TEXT_PRIMARY, WARN, WARN_BAR, input_combobox_stylesheet
from ic_ui.widgets.farm_health_badge import farm_health_tooltip
from ic_ui.widgets.popup_combo import PopupComboBox


class GemFarmTab(QWidget):
    """Briv zones, Co-Pilot advice, farm health, and profile settings."""

    def __init__(self, dashboard_tab: DashboardTab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dashboard = dashboard_tab
        self._config_store = GemFarmConfigStore()
        self._dashboard.game_state.state_changed.connect(self._schedule_refresh)
        self._dashboard.game_state.farm_health_changed.connect(self._schedule_refresh)
        self._dashboard.game_state.payload_changed.connect(self._on_payload_changed)
        self._copilot_status_timer = QTimer(self)
        self._copilot_status_timer.setInterval(400)
        self._copilot_status_timer.timeout.connect(self._poll_copilot_status)
        self._copilot_status_timer.start()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(600)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._formation_names_cache: tuple[str, ...] | None = None
        self._formation_combo_party: int | None = None
        self._formation_selection_cache: tuple[str | None, str | None, str | None] | None = None
        self._build_ui()
        QTimer.singleShot(500, self._refresh_all)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        intro = QLabel(
            "Gem farm voor actieve party: Modron-doel + Briv in formation. "
            "Co-Pilot adviseert; Script Hub (indien gebruikt) blijft de piloot."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {TEXT_MUTED};")
        root.addWidget(intro)

        # Co-Pilot
        copilot_box = QGroupBox("Co-Pilot (advies + optionele toetsen)")
        copilot_layout = QVBoxLayout(copilot_box)
        self._copilot_headline = QLabel("—")
        self._copilot_headline.setStyleSheet(f"color: {ACCENT}; font-weight: 600;")
        self._copilot_detail = QLabel("Start dashboard voor live fase-detectie.")
        self._copilot_detail.setWordWrap(True)
        self._copilot_detail.setStyleSheet(f"color: {TEXT_PRIMARY};")
        copilot_layout.addWidget(self._copilot_headline)
        copilot_layout.addWidget(self._copilot_detail)
        self._formation_hotkeys = QLabel("—")
        self._formation_hotkeys.setWordWrap(True)
        self._formation_hotkeys.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self._formation_hotkeys.setToolTip(
            "Formation 1/2/3 hotkeys (Q/W/E) uit modron_saves in de API. "
            "Ontbreekt de party-binding, dan van een andere party op dezelfde campaign."
        )
        copilot_layout.addWidget(self._formation_hotkeys)
        formations_form = QFormLayout()
        self._formation_q = PopupComboBox()
        self._formation_w = PopupComboBox()
        self._formation_e = PopupComboBox()
        combo_style = input_combobox_stylesheet()
        for combo in (self._formation_q, self._formation_w, self._formation_e):
            combo.setStyleSheet(combo_style)
            combo.setMinimumWidth(220)
            combo.addItem("(kies formation)")
            combo.currentIndexChanged.connect(self._on_formation_combo_changed)
        formations_form.addRow("Q-team:", self._formation_q)
        formations_form.addRow("W-team:", self._formation_w)
        formations_form.addRow("E-team:", self._formation_e)
        for combo in (self._formation_q, self._formation_w, self._formation_e):
            combo.setToolTip(
                "Optioneel: kies de saved formation voor deze hotkey als de API "
                "Q/W/E niet volledig toont. Wordt opgeslagen in het profile."
            )
        copilot_layout.addLayout(formations_form)
        self._formation_combo_hint = QLabel("")
        self._formation_combo_hint.setWordWrap(True)
        self._formation_combo_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        copilot_layout.addWidget(self._formation_combo_hint)
        self._send_keys_cb = QCheckBox("Co-Pilot toetsen sturen (Q/W/E/G bij fase-wissel)")
        self._send_keys_cb.setChecked(False)
        self._send_keys_cb.setToolTip(
            "Aan: Co-Pilot stuurt Q/W/E/G bij fase-wissel (debounce ~60s), "
            "ook terwijl je deze app gebruikt. Het spel krijgt kort focus. "
            "Uit: alleen advies, geen toetsen. Geen Modron-reset (R). "
            "Zet uit als je Script Hub gebruikt."
        )
        self._send_keys_cb.toggled.connect(self._on_send_keys_toggled)
        copilot_layout.addWidget(self._send_keys_cb)
        self._copilot_status = QLabel("")
        self._copilot_status.setWordWrap(True)
        self._copilot_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        copilot_layout.addWidget(self._copilot_status)
        root.addWidget(copilot_box)

        # Briv gear
        gear_box = QGroupBox("Briv slot 4 gear")
        gear_form = QFormLayout(gear_box)
        self._gear_auto = QLabel("—")
        self._gear_auto.setWordWrap(True)
        gear_form.addRow("API:", self._gear_auto)
        self._override_level = QLineEdit()
        self._override_level.setPlaceholderText("optioneel item level")
        self._override_rarity = QComboBox()
        for label in ("—", "Common", "Uncommon", "Rare", "Epic"):
            self._override_rarity.addItem(label)
        self._override_rarity.setStyleSheet(combo_style)
        self._override_gild = QComboBox()
        for label in ("—", "None", "Shiny", "Golden"):
            self._override_gild.addItem(label)
        self._override_gild.setStyleSheet(combo_style)
        gear_form.addRow("Override level:", self._override_level)
        gear_form.addRow("Override rarity:", self._override_rarity)
        gear_form.addRow("Override gild:", self._override_gild)
        root.addWidget(gear_box)

        # Zones
        zones_box = QGroupBox("Zones (profile + advies)")
        zones_form = QFormLayout(zones_box)
        self._advice_zones = QLabel("—")
        self._advice_zones.setWordWrap(True)
        zones_form.addRow("Aanbevolen:", self._advice_zones)
        self._profile_stack = QLineEdit()
        self._profile_reset = QLineEdit()
        self._profile_stack_target = QLineEdit()
        self._profile_stack.setPlaceholderText("jouw stack-zone")
        self._profile_reset.setPlaceholderText("jouw reset-zone")
        self._profile_stack_target.setPlaceholderText("optioneel stack target")
        zones_form.addRow("Stack-zone:", self._profile_stack)
        zones_form.addRow("Reset-zone:", self._profile_reset)
        zones_form.addRow("Stack target:", self._profile_stack_target)
        link_row = QHBoxLayout()
        btn_byteglow = QPushButton("Byteglow Speed")
        btn_byteglow.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://ic.byteglow.com/speed"))
        )
        btn_emmotes = QPushButton("Emmotes routes")
        btn_emmotes.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://emmotes.github.io/ic_scripting_routes/"))
        )
        link_row.addWidget(btn_byteglow)
        link_row.addWidget(btn_emmotes)
        link_row.addStretch(1)
        zones_form.addRow("Verifieer:", link_row)
        root.addWidget(zones_box)

        # Live
        live_box = QGroupBox("Live")
        live_form = QFormLayout(live_box)
        self._live_area = QLabel("—")
        self._live_stacks = QLabel("—")
        self._live_steelbones = QLabel("—")
        self._live_gems = QLabel("—")
        live_form.addRow("Area:", self._live_area)
        live_form.addRow("Briv sprint:", self._live_stacks)
        live_form.addRow("Briv steelbones:", self._live_steelbones)
        live_form.addRow("Gem/kw:", self._live_gems)
        root.addWidget(live_box)

        # Health
        health_box = QGroupBox("Farm health")
        health_layout = QVBoxLayout(health_box)
        self._status_headline = QLabel("—")
        self._status_headline.setStyleSheet(f"font-weight: 600; color: {TEXT_PRIMARY};")
        self._status_detail = QLabel("")
        self._status_detail.setWordWrap(True)
        self._monitoring_hint = QLabel("")
        self._monitoring_hint.setWordWrap(True)
        self._monitoring_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        health_layout.addWidget(self._status_headline)
        health_layout.addWidget(self._status_detail)
        health_layout.addWidget(self._monitoring_hint)
        thresholds_form = QFormLayout()
        self._lbl_slowdown = QLabel("")
        self._lbl_gem_drop = QLabel("")
        self._lbl_stall = QLabel("")
        thresholds_form.addRow("Run-vertraging:", self._lbl_slowdown)
        thresholds_form.addRow("Gem-daling:", self._lbl_gem_drop)
        thresholds_form.addRow("Area-stagnatie:", self._lbl_stall)
        health_layout.addLayout(thresholds_form)
        root.addWidget(health_box)

        save_row = QHBoxLayout()
        self._save_btn = QPushButton("Profile opslaan")
        self._save_btn.clicked.connect(self._save_profile)
        save_row.addWidget(self._save_btn)
        save_row.addStretch(1)
        root.addLayout(save_row)

        # Events
        events_box = QGroupBox("Recente farm events")
        self._events_layout = QVBoxLayout(events_box)
        root.addWidget(events_box)

        root.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _schedule_refresh(self) -> None:
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _on_payload_changed(self, payload: object) -> None:
        self._formation_names_cache = None
        self._formation_selection_cache = None
        if isinstance(payload, dict):
            # Signal can fire before tracker has parties — still fill dropdowns.
            party_index = self._active_party_index(payload)
            config = self._config_store.load()
            profile = (
                config.profiles.get(party_index, FarmProfile())
                if party_index is not None
                else FarmProfile()
            )
            snapshot = self._dashboard.game_state.gem_farm_snapshot
            hotkeys = snapshot.formation_hotkeys if snapshot is not None else None
            self._refresh_formation_combos(
                party_index,
                profile,
                hotkeys=hotkeys,
                force=True,
                payload=payload,
            )
            return
        self._schedule_refresh()

    def _formation_combos_busy(self) -> bool:
        for combo in (self._formation_q, self._formation_w, self._formation_e):
            if combo.hasFocus():
                return True
            try:
                if combo.view() is not None and combo.view().isVisible():
                    return True
            except RuntimeError:
                pass
        return False

    def _last_payload(self) -> dict | None:
        payload = self._dashboard.game_state.last_payload
        if isinstance(payload, dict):
            return payload
        payload = self._dashboard.last_payload
        return payload if isinstance(payload, dict) else None

    def _active_party_index(self, payload: dict | None = None) -> int | None:
        tracker = self._dashboard.game_state.tracker
        if tracker is not None and tracker.latest is not None:
            active = self._dashboard._active_party(tracker.latest)
            if active is not None:
                return active.party_index
        raw = payload if isinstance(payload, dict) else self._last_payload()
        if not isinstance(raw, dict):
            return None
        details = raw.get("details")
        if not isinstance(details, dict):
            return None
        from ic_gamedata.parsing import parse_int

        return parse_int(details.get("active_game_instance_id"))

    def _level_color(self, level: str) -> str:
        if level == "critical":
            return WARN_BAR
        if level == "warning":
            return WARN
        if level == "ok":
            return SUCCESS
        return TEXT_MUTED

    def _refresh_threshold_labels(self, health: FarmHealthThresholds) -> None:
        self._lbl_slowdown.setText(
            f"Laatste 3 runs > {health.run_slowdown_pct:.0f}% van mediaan"
        )
        self._lbl_gem_drop.setText(
            f"Gem/kw < {health.gem_drop_pct:.0f}% baseline gedurende "
            f"{health.gem_drop_min_sec / 60:.0f} min"
        )
        self._lbl_stall.setText(f"Area ongewijzigd ≥ {health.area_stall_sec:.0f}s")

    def _refresh_events(self) -> None:
        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        events = load_farm_events()
        if not events:
            empty = QLabel("Nog geen farm events.")
            empty.setStyleSheet(f"color: {TEXT_MUTED};")
            self._events_layout.addWidget(empty)
            return
        for event in reversed(events[-30:]):
            from datetime import datetime

            ts = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M")
            line = QLabel(f"{ts} · P{event.party_index} · [{event.severity}] {event.message}")
            line.setWordWrap(True)
            line.setStyleSheet(f"color: {self._level_color(event.severity)}; font-size: 11px;")
            if event.detail:
                line.setToolTip(event.detail)
            self._events_layout.addWidget(line)

    def _formation_combo_names(
        self,
        party_index: int | None,
        payload: dict | None = None,
    ) -> list[str]:
        return formation_save_names_for_party(payload or self._last_payload(), party_index)

    def _populate_formation_combo(self, combo: QComboBox, names: list[str], selected: str | None) -> None:
        combo.blockSignals(True)
        previous = combo.currentText().strip()
        combo.clear()
        combo.addItem("(kies formation)")
        for name in names:
            combo.addItem(name)
        choose = selected or (previous if previous and previous not in ("(auto uit API)", "(kies formation)") else None)
        if choose:
            idx = combo.findText(choose)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.addItem(choose)
                combo.setCurrentIndex(combo.count() - 1)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _refresh_formation_combos(
        self,
        party_index: int | None,
        profile: FarmProfile,
        *,
        hotkeys=None,
        force: bool = False,
        payload: dict | None = None,
    ) -> None:
        if self._formation_combos_busy():
            return
        names = self._formation_combo_names(party_index, payload)
        names_key = tuple(names)
        q_name = profile.formation_q_name
        w_name = profile.formation_w_name
        e_name = profile.formation_e_name
        if hotkeys is not None:
            slots = hotkeys.slots
            if not q_name and len(slots) > 0 and slots[0].save_name:
                q_name = slots[0].save_name
            if not w_name and len(slots) > 1 and slots[1].save_name:
                w_name = slots[1].save_name
            if not e_name and len(slots) > 2 and slots[2].save_name:
                e_name = slots[2].save_name
        # API often only binds Q; suggest W/E from save names when still empty.
        q_name, w_name, e_name = suggest_formation_names(
            names,
            known=(q_name, w_name, e_name),
        )
        selection_key = (q_name, w_name, e_name)
        if (
            not force
            and self._formation_names_cache == names_key
            and self._formation_combo_party == party_index
            and self._formation_selection_cache == selection_key
        ):
            return
        self._formation_names_cache = names_key
        self._formation_combo_party = party_index
        self._formation_selection_cache = selection_key
        self._populate_formation_combo(self._formation_q, names, q_name)
        self._populate_formation_combo(self._formation_w, names, w_name)
        self._populate_formation_combo(self._formation_e, names, e_name)
        if (
            party_index is not None
            and (
                profile.formation_q_name != q_name
                or profile.formation_w_name != w_name
                or profile.formation_e_name != e_name
            )
            and (q_name or w_name or e_name)
        ):
            # Persist API/heuristic fill so W/E survive restarts.
            from dataclasses import replace

            config = self._config_store.load()
            old = config.profiles.get(party_index, FarmProfile())
            profiles = dict(config.profiles)
            profiles[party_index] = replace(
                old,
                formation_q_name=q_name,
                formation_w_name=w_name,
                formation_e_name=e_name,
            )
            self._config_store.save(replace(config, profiles=profiles))
        if not names:
            self._formation_combo_hint.setText(
                "Geen saved formations in API — start het dashboard en wacht op een poll."
            )
        elif not profile.formation_w_name or not profile.formation_e_name:
            self._formation_combo_hint.setText(
                f"{len(names)} saved formations. API heeft vaak alleen Q; "
                "W/E zijn voorgesteld — controleer en ze worden auto-opgeslagen."
            )
        else:
            self._formation_combo_hint.setText(
                f"{len(names)} saved formations · Q/W/E uit profile."
            )

    def _on_formation_combo_changed(self, _index: int = 0) -> None:
        party_index = self._active_party_index()
        if party_index is None:
            return
        q_name = self._combo_save_name(self._formation_q)
        w_name = self._combo_save_name(self._formation_w)
        e_name = self._combo_save_name(self._formation_e)
        config = self._config_store.load()
        old = config.profiles.get(party_index, FarmProfile())
        if (
            old.formation_q_name == q_name
            and old.formation_w_name == w_name
            and old.formation_e_name == e_name
        ):
            return
        from dataclasses import replace

        profiles = dict(config.profiles)
        profiles[party_index] = replace(
            old,
            formation_q_name=q_name,
            formation_w_name=w_name,
            formation_e_name=e_name,
        )
        self._config_store.save(replace(config, profiles=profiles))
        self._formation_selection_cache = (q_name, w_name, e_name)
        self._formation_combo_hint.setText(
            f"Q/W/E opgeslagen voor party {party_index}."
        )

    def _combo_save_name(self, combo: QComboBox) -> str | None:
        if combo.currentIndex() <= 0:
            return None
        name = combo.currentText().strip()
        return name or None

    def _load_profile_fields(self, party_index: int) -> None:
        config = self._config_store.load()
        profile = config.profiles.get(party_index, FarmProfile())
        self._profile_stack.setText(str(profile.stack_zone) if profile.stack_zone else "")
        self._profile_reset.setText(str(profile.reset_zone) if profile.reset_zone else "")
        self._profile_stack_target.setText(
            str(profile.stack_target_stacks) if profile.stack_target_stacks else ""
        )
        self._send_keys_cb.blockSignals(True)
        self._send_keys_cb.setChecked(profile.copilot.send_keys_enabled)
        self._send_keys_cb.blockSignals(False)
        override = profile.briv_gear_override
        if override is None:
            self._override_level.clear()
            self._override_rarity.setCurrentIndex(0)
            self._override_gild.setCurrentIndex(0)
            return
        self._override_level.setText(str(override.enchant) if override.enchant else "")
        self._override_rarity.setCurrentIndex(override.rarity if override.rarity else 0)
        self._override_gild.setCurrentIndex(override.gild + 1 if override.gild is not None else 0)

    def _parse_optional_int(self, text: str) -> int | None:
        raw = text.strip()
        if not raw:
            return None
        return int(raw)

    def _build_override(self) -> BrivGearOverride | None:
        level = self._override_level.text().strip()
        rarity_idx = self._override_rarity.currentIndex()
        gild_idx = self._override_gild.currentIndex()
        if not level and rarity_idx == 0 and gild_idx == 0:
            return None
        return BrivGearOverride(
            enchant=int(level) if level else None,
            rarity=rarity_idx if rarity_idx > 0 else None,
            gild=gild_idx - 1 if gild_idx > 0 else None,
        )

    def _save_profile(self) -> None:
        party_index = self._active_party_index()
        if party_index is None:
            QMessageBox.information(self, "Opslaan", "Geen actieve party — start het dashboard.")
            return
        config = self._config_store.load()
        old = config.profiles.get(party_index, FarmProfile())
        try:
            stack_zone = self._parse_optional_int(self._profile_stack.text())
            reset_zone = self._parse_optional_int(self._profile_reset.text())
            stack_target = self._parse_optional_int(self._profile_stack_target.text())
        except ValueError:
            QMessageBox.warning(self, "Opslaan", "Zones moeten gehele getallen zijn.")
            return

        zones_changed = stack_zone != old.stack_zone or reset_zone != old.reset_zone
        if zones_changed and (old.stack_zone is not None or old.reset_zone is not None):
            answer = QMessageBox.question(
                self,
                "Baseline resetten?",
                "Je wijzigde stack- of reset-zone. Farm health baseline resetten?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._dashboard.game_state.farm_health_monitor.clear_party_baselines(party_index)

        new_profile = FarmProfile(
            enabled=True,
            stack_zone=stack_zone,
            reset_zone=reset_zone,
            stack_target_stacks=stack_target,
            briv_gear_override=self._build_override(),
            formation_q_name=self._combo_save_name(self._formation_q),
            formation_w_name=self._combo_save_name(self._formation_w),
            formation_e_name=self._combo_save_name(self._formation_e),
            copilot=CopilotSettings(
                send_keys_enabled=self._send_keys_cb.isChecked(),
                advise_only=not self._send_keys_cb.isChecked(),
                allow_formation_q=self._send_keys_cb.isChecked(),
                allow_formation_w=self._send_keys_cb.isChecked(),
                allow_formation_e=self._send_keys_cb.isChecked(),
                allow_auto_progress_g=self._send_keys_cb.isChecked(),
            ),
        )
        profiles = dict(config.profiles)
        profiles[party_index] = new_profile
        from dataclasses import replace

        self._config_store.save(replace(config, profiles=profiles))

        if zones_changed:
            import time

            append_farm_event(
                FarmEvent(
                    timestamp=time.time(),
                    party_index=party_index,
                    kind="profile",
                    rule_id="zone_change",
                    severity="info",
                    message="Profile zones bijgewerkt",
                    detail=f"stack={stack_zone} reset={reset_zone}",
                )
            )
        QMessageBox.information(self, "Opslaan", f"Profile opgeslagen voor party {party_index}.")
        self._apply_copilot_settings()
        self._refresh_all()

    def _build_copilot_key_settings(self, send_keys_enabled: bool) -> CopilotKeySettings:
        win = self.window()
        hwnd = None
        title = ""
        if win is not None:
            try:
                hwnd = win_input.toplevel_hwnd(int(win.winId()))
            except (TypeError, ValueError, AttributeError):
                hwnd = None
            title = win.windowTitle()
        return CopilotKeySettings(
            send_keys_enabled=send_keys_enabled,
            allow_auto_progress_g=send_keys_enabled,
            exclude_hwnd=hwnd,
            exclude_title=title,
            hover_gate=not send_keys_enabled,
            pause_when_app_focused=not send_keys_enabled,
            pause_when_over_app=not send_keys_enabled,
            prefer_game_already_focused=not send_keys_enabled,
        )

    def _apply_copilot_settings(self) -> None:
        controller = self._dashboard.game_state.copilot_controller
        settings = self._build_copilot_key_settings(self._send_keys_cb.isChecked())
        controller.update_settings(settings)
        controller.notify_snapshot(self._dashboard.game_state.gem_farm_snapshot)

    def _on_send_keys_toggled(self, checked: bool) -> None:
        if checked:
            answer = QMessageBox.question(
                self,
                "Co-Pilot toetsen",
                "Co-Pilot gaat Q/W/E sturen bij fase-wissels, plus G om auto-progress "
                "uit te zetten tijdens stacken en weer aan na de stack.\n\n"
                "Zet dit uit als je IC Script Hub gebruikt.\n\nDoorgaan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._send_keys_cb.blockSignals(True)
                self._send_keys_cb.setChecked(False)
                self._send_keys_cb.blockSignals(False)
                return
        party_index = self._active_party_index()
        if party_index is not None:
            config = self._config_store.load()
            old = config.profiles.get(party_index, FarmProfile())
            profiles = dict(config.profiles)
            profiles[party_index] = FarmProfile(
                enabled=old.enabled,
                stack_zone=old.stack_zone,
                reset_zone=old.reset_zone,
                stack_target_stacks=old.stack_target_stacks,
                briv_gear_override=old.briv_gear_override,
                formation_q_name=old.formation_q_name,
                formation_w_name=old.formation_w_name,
                formation_e_name=old.formation_e_name,
                copilot=CopilotSettings(
                    send_keys_enabled=self._send_keys_cb.isChecked(),
                    advise_only=not self._send_keys_cb.isChecked(),
                    allow_formation_q=self._send_keys_cb.isChecked(),
                    allow_formation_w=self._send_keys_cb.isChecked(),
                    allow_formation_e=self._send_keys_cb.isChecked(),
                    allow_auto_progress_g=self._send_keys_cb.isChecked(),
                ),
            )
            from dataclasses import replace

            self._config_store.save(replace(config, profiles=profiles))
        self._apply_copilot_settings()
        self._refresh_all()

    def _poll_copilot_status(self) -> None:
        event = self._dashboard.game_state.copilot_controller.poll_status()
        if event is None:
            return
        self._copilot_status.setText(event.text)

    def _refresh_all(self) -> None:
        config = self._config_store.load()
        self._refresh_threshold_labels(config.health)
        snapshot = self._dashboard.game_state.gem_farm_snapshot

        party_index = self._active_party_index()
        profile = config.profiles.get(party_index, FarmProfile()) if party_index is not None else FarmProfile()
        if party_index is not None and not self._profile_stack.hasFocus() and not self._profile_reset.hasFocus():
            self._load_profile_fields(party_index)

        self._apply_copilot_settings()

        if snapshot is None:
            self._copilot_headline.setText("Co-Pilot")
            self._copilot_detail.setText("Start dashboard voor live data.")
            self._status_headline.setText("Geen data")
            self._refresh_formation_combos(party_index, profile)
            self._refresh_events()
            return

        if snapshot.copilot is not None:
            self._copilot_headline.setText(snapshot.copilot.headline)
            self._copilot_detail.setText(snapshot.copilot.detail)
        else:
            self._copilot_headline.setText("Co-Pilot")
            self._copilot_detail.setText("—")

        hotkey_text = format_hotkeys_summary(snapshot.formation_hotkeys)
        self._formation_hotkeys.setText(hotkey_text if hotkey_text else "Formations Q/W/E: —")
        self._refresh_formation_combos(
            party_index,
            profile,
            hotkeys=snapshot.formation_hotkeys,
        )

        if snapshot.briv_gear is not None:
            g = snapshot.briv_gear
            self._gear_auto.setText(
                f"{g.item_level_label} · {g.rarity_label} · {g.gild_label} ({g.source})"
            )
        else:
            self._gear_auto.setText("Niet gevonden in API — gebruik override.")

        if snapshot.zone_advice is not None:
            z = snapshot.zone_advice
            self._advice_zones.setText(
                f"Stack {z.stack_zone_min}–{z.stack_zone_max} (advies {z.stack_zone_recommended}), "
                f"reset ~{z.reset_zone}"
                + (f", target stacks {z.stack_target}" if z.stack_target else "")
                + f"\n{z.explanation}"
            )
        else:
            self._advice_zones.setText("Modron-doel onbekend — stel doel in op dashboard.")

        self._live_area.setText(str(snapshot.current_area) if snapshot.current_area else "—")
        self._live_stacks.setText(
            str(snapshot.briv_stacks) if snapshot.briv_stacks is not None else "—"
        )
        self._live_steelbones.setText(
            str(snapshot.briv_steelbones_stacks)
            if snapshot.briv_steelbones_stacks is not None
            else "—"
        )
        gems = snapshot.gems_per_quarter
        self._live_gems.setText(f"{gems:.1f}/kw" if gems is not None else "—")

        status = snapshot.health
        if not status.monitoring:
            self._status_headline.setText("Monitoring uit")
            self._status_headline.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: 600;")
            self._status_detail.setText("")
            self._monitoring_hint.setText(
                "Actieve party heeft Modron-doel én Briv in formation nodig."
            )
        else:
            color = self._level_color(status.level)
            self._status_headline.setText(f"Party {status.party_index}: {status.level.upper()}")
            self._status_headline.setStyleSheet(f"color: {color}; font-weight: 600;")
            self._status_detail.setText(farm_health_tooltip(status).replace("\n", " · "))
            self._monitoring_hint.setText("")

        self._refresh_events()
