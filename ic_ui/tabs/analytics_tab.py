"""Analytics tab: Modron goal-run charts and CSV export."""

from __future__ import annotations

import csv
import io

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ic_gamedata.analytics import (
    build_goal_run_analytics,
    format_duration_minutes,
    goal_run_csv_rows,
    party_indexes_with_history,
)
from ic_gamedata.gem_farm.event_log import load_farm_events
from ic_gamedata.goal_run_history_store import load_goal_run_history
from ic_gamedata.stats import GoalRunRecord
from ic_ui.tabs.dashboard_tab import DashboardTab
from ic_ui.theme import ACCENT, BUD_BAR, SUCCESS, TEXT_MUTED, TEXT_PRIMARY

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover - optional at import time in tests
    pg = None


class AnalyticsTab(QWidget):
    """Visualize Modron area-goal run durations over time."""

    def __init__(self, dashboard_tab: DashboardTab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dashboard = dashboard_tab
        self._dashboard.game_state.state_changed.connect(self._schedule_refresh)
        self._dashboard.game_state.farm_health_changed.connect(self._schedule_farm_events_refresh)
        self._selected_party: int | None = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(1500)
        self._refresh_timer.timeout.connect(self.refresh)
        self._farm_events_timer = QTimer(self)
        self._farm_events_timer.setSingleShot(True)
        self._farm_events_timer.setInterval(800)
        self._farm_events_timer.timeout.connect(self._refresh_farm_events)
        self._build_ui()
        QTimer.singleShot(400, self.refresh)
        QTimer.singleShot(500, self._refresh_farm_events)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Party:"))
        self._party_combo = QComboBox()
        self._party_combo.currentIndexChanged.connect(self._on_party_changed)
        ctrl.addWidget(self._party_combo)
        refresh_btn = QPushButton("Verversen")
        refresh_btn.clicked.connect(self.refresh)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        ctrl.addWidget(refresh_btn)
        ctrl.addWidget(export_btn)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        self._summary = QLabel("Modron-doel runs verschijnen hier zodra je resets voltooit.")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"color: {TEXT_PRIMARY};")
        root.addWidget(self._summary)

        if pg is None:
            fallback = QLabel("PyQtGraph is niet geïnstalleerd. Voer uit: pip install pyqtgraph")
            fallback.setWordWrap(True)
            fallback.setStyleSheet(f"color: {TEXT_MUTED};")
            root.addWidget(fallback)
            self._plot = None
            self._legend = QLabel("")
        else:
            pg.setConfigOptions(antialias=True)
            self._plot = pg.PlotWidget()
            self._plot.setBackground("#252526")
            self._plot.showGrid(x=True, y=True, alpha=0.25)
            self._plot.setLabel("left", "Duur", units="min")
            self._plot.setLabel("bottom", "Run")
            self._plot.setMinimumHeight(280)
            root.addWidget(self._plot, stretch=1)

            self._legend = QLabel("")
            self._legend.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            root.addWidget(self._legend)

        farm_header = QLabel("Farm health events")
        farm_header.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 600; margin-top: 8px;")
        root.addWidget(farm_header)
        self._farm_events = QLabel("Nog geen farm events.")
        self._farm_events.setWordWrap(True)
        self._farm_events.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        root.addWidget(self._farm_events)
        root.addStretch(1)

    def _schedule_farm_events_refresh(self) -> None:
        if not self._farm_events_timer.isActive():
            self._farm_events_timer.start()

    def _refresh_farm_events(self) -> None:
        events = load_farm_events()
        if not events:
            self._farm_events.setText("Nog geen farm events.")
            return
        lines = []
        for event in reversed(events[-20:]):
            from datetime import datetime

            ts = datetime.fromtimestamp(event.timestamp).strftime("%m-%d %H:%M")
            lines.append(
                f"{ts} · P{event.party_index} · [{event.severity}] {event.message}"
            )
        self._farm_events.setText("\n".join(lines))

    def _schedule_refresh(self) -> None:
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _on_party_changed(self, index: int) -> None:
        if index < 0:
            return
        party_index = self._party_combo.currentData()
        if party_index is None:
            return
        self._selected_party = int(party_index)
        self._render_party(self._selected_party)

    def refresh(self) -> None:
        history = self._load_history()
        parties = party_indexes_with_history(history)
        current = self._selected_party
        self._party_combo.blockSignals(True)
        self._party_combo.clear()
        for party_index in parties:
            count = len(history.get(party_index, ()))
            self._party_combo.addItem(f"Party {party_index} ({count} runs)", party_index)
        self._party_combo.blockSignals(False)

        if not parties:
            self._summary.setText(
                "Nog geen Modron-doel runs opgeslagen. Voltooi een run tot je Modron-doel op het dashboard."
            )
            if self._plot is not None:
                self._plot.clear()
            if self._legend is not None:
                self._legend.setText("")
            return

        if current not in parties:
            current = parties[0]
        self._selected_party = current
        idx = self._party_combo.findData(current)
        if idx >= 0:
            self._party_combo.setCurrentIndex(idx)
        self._render_party(current)

    def _load_history(self) -> dict[int, tuple[GoalRunRecord, ...]]:
        tracker = self._dashboard.game_state.tracker
        if tracker is not None:
            persisted = load_goal_run_history()
            party_ids = set(persisted)
            stats = tracker.compute()
            if stats is not None:
                party_ids.update(
                    party.party_index for party in stats.parties if party.goal_run_history
                )
            party_ids.update(persisted)
            history: dict[int, tuple[GoalRunRecord, ...]] = {}
            for party_index in sorted(party_ids):
                records = tracker.goal_run_history(party_index)
                if records:
                    history[party_index] = records
            if history:
                return history
        persisted = load_goal_run_history()
        return {party_index: tuple(records) for party_index, records in persisted.items() if records}

    def _records_for_party(self, party_index: int) -> tuple[GoalRunRecord, ...]:
        history = self._load_history()
        return history.get(party_index, ())

    def _render_party(self, party_index: int) -> None:
        records = self._records_for_party(party_index)
        summary = build_goal_run_analytics(party_index, records)
        if summary.run_count == 0:
            if summary.excluded_unreliable_count:
                self._summary.setText(
                    f"Party {party_index}: geen betrouwbare Modron-doel runs "
                    f"({summary.excluded_unreliable_count} overgeslagen na party-wissel)."
                )
            else:
                self._summary.setText(f"Party {party_index}: nog geen voltooide Modron-doel runs.")
            if self._plot is not None:
                self._plot.clear()
            if hasattr(self, "_legend"):
                self._legend.setText("")
            return

        goal_txt = f"doel {summary.area_goal}" if summary.area_goal is not None else "doel —"
        excluded_txt = ""
        if summary.excluded_unreliable_count:
            excluded_txt = f" · {summary.excluded_unreliable_count} overgeslagen (party gewisseld)"
        self._summary.setText(
            f"Party {party_index} · {summary.run_count} runs · {goal_txt} · "
            f"beste {format_duration_minutes(summary.best_sec)} · "
            f"gemiddeld {format_duration_minutes(summary.avg_sec)} · "
            f"laatste {format_duration_minutes(summary.latest_sec)}{excluded_txt}"
        )

        if self._plot is None:
            return

        self._plot.clear()
        x_vals = [point.run_index for point in summary.points]
        y_vals = [point.duration_sec / 60.0 for point in summary.points]

        bar_item = pg.BarGraphItem(
            x=x_vals,
            height=y_vals,
            width=0.65,
            brush=pg.mkBrush(BUD_BAR),
        )
        self._plot.addItem(bar_item)

        if summary.avg_sec is not None:
            avg_min = summary.avg_sec / 60.0
            self._plot.addLine(y=avg_min, pen=pg.mkPen(ACCENT, width=1, style=Qt.PenStyle.DashLine))

        if summary.best_sec is not None:
            best_index = min(summary.points, key=lambda p: p.duration_sec).run_index
            best_min = summary.best_sec / 60.0
            best_marker = pg.ScatterPlotItem(
                [best_index],
                [best_min],
                symbol="star",
                size=14,
                brush=pg.mkBrush(SUCCESS),
                pen=pg.mkPen("#14532d"),
            )
            self._plot.addItem(best_marker)

        self._plot.setXRange(0.5, max(x_vals) + 0.5, padding=0.05)
        ymax = max(y_vals) * 1.15 if y_vals else 1.0
        self._plot.setYRange(0, max(ymax, 0.5))
        self._legend.setText("▮ run-duur · -- gemiddelde · ★ beste run")

    def _export_csv(self) -> None:
        party_index = self._selected_party
        if party_index is None:
            QMessageBox.information(self, "Export", "Geen party geselecteerd.")
            return
        records = self._records_for_party(party_index)
        if not records:
            QMessageBox.information(self, "Export", "Geen runs om te exporteren voor deze party.")
            return

        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Modron runs",
            f"modron_runs_party_{party_index}.csv",
            "CSV (*.csv)",
        )
        if not path:
            return

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for row in goal_run_csv_rows(records):
            writer.writerow(row)
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(buffer.getvalue())
        except OSError as exc:
            QMessageBox.critical(self, "Export", f"Kon bestand niet schrijven:\n{exc}")
            return
        QMessageBox.information(self, "Export", f"Opgeslagen: {path}")
