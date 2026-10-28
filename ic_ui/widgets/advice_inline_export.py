"""Inline export-mode controls for the Advies tab (basis + partijsetup).

Heavy ``ic_gamedata`` work (request build, base snapshot, freshness) runs on
``QThreadPool`` via :mod:`ic_ui.workers.callable_job`. Qt widgets and clipboard
I/O stay on the UI thread.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QSettings, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ic_gamedata.formation_ai_advice.export_budget import DEFAULT_CHAR_BUDGET
from ic_gamedata.formation_ai_advice.export_clipboard import (
    advice_request_section_breakdown,
    build_advice_request_clipboard_text,
    evaluate_clipboard_budget,
    try_loss_free_shrink,
)
from ic_gamedata.formation_ai_advice.export_validation import (
    mark_request_unvalidated,
    mark_request_validated,
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.formation_ai_advice.snapshot_freshness import (
    SnapshotFreshnessStatus,
    assess_snapshot_freshness,
)
from ic_gamedata.formation_ai_advice.snapshot_store import (
    get_exported_snapshot_meta,
    save_base_snapshot_to_basisgegevens,
)
from ic_gamedata.paths import BASISGEGEVENS_DIR
from ic_ui import theme as ui_theme
from ic_ui.theme import apply_button_icon
from ic_ui.ui_action_log import note_ui_action
from ic_ui.widgets.busy_indicator import BusySpinner
from ic_ui.workers.callable_job import start_callable_job

_SETTINGS_ORG = "IdleChampions"
_SETTINGS_APP = "Companion"
_SEARCH_BETTER_KEY = "advice/export_search_better_champs"
_MAX_SWAPS_KEY = "advice/export_max_swaps"
_RESEARCH_MODE_KEY = "advice/export_research_mode"
_MODE: str = "project"  # primary UX always uses project instructions mode


@dataclass(frozen=True)
class _AdviceRequestJobResult:
    ok: bool
    message: str
    text: str | None = None
    needs_confirm: bool = False
    validation_summary: str = ""
    chars: int = 0
    stale_note: str = ""
    presence_conflicts: tuple[dict[str, Any], ...] = ()
    copy_generation: int = 0


@dataclass(frozen=True)
class _FreshnessJobResult:
    token: int
    text: str
    warn: bool
    tooltip: str


@dataclass(frozen=True)
class _BaseSnapshotJobResult:
    ok: bool
    message: str
    saved_name: str | None = None


class AdviceInlineExportBar(QWidget):
    """Export mode: freshness, basis update, and partijsetup copy."""

    request_copied = Signal()
    status_message = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        write_clipboard: Callable[[str], bool],
        live_source: Callable[[], tuple[dict[str, Any] | None, tuple]],
        goal_context: Callable[[], tuple[str, str, dict[str, Any], int | None]],
        refresh_live: Callable[[Callable[[], None], Callable[[str], None]], None]
        | None = None,
        confirm_eligibility: Callable[[list[dict[str, Any]]], list[int] | None]
        | None = None,
    ) -> None:
        super().__init__(parent)
        self._write_clipboard = write_clipboard
        self._live_source = live_source
        self._goal_context = goal_context
        self._refresh_live = refresh_live
        self._confirm_eligibility = confirm_eligibility
        self._copy_generation = 0
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._job_busy = False
        self._fresh_token = 0
        self._fresh_timer = QTimer(self)
        self._fresh_timer.setSingleShot(True)
        self._fresh_timer.setInterval(100)
        self._fresh_timer.timeout.connect(self._start_freshness_job)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        fresh_row = QHBoxLayout()
        fresh_row.setSpacing(8)
        self._fresh_spinner = BusySpinner(self, size=14)
        fresh_row.addWidget(self._fresh_spinner)
        self._freshness = QLabel("")
        self._freshness.setWordWrap(True)
        fresh_row.addWidget(self._freshness, stretch=1)
        self._base_btn = QPushButton("Basis bijwerken")
        apply_button_icon(self._base_btn, "save")
        self._base_btn.setToolTip(
            "Bouw een nieuw basisbestand (roster/mechanics) en schrijf het naar "
            f"de map ‘{BASISGEGEVENS_DIR.name}’ (oude bestanden daar worden "
            "verwijderd). Aangeraden bij nieuwe champions of mechanicwijzigingen "
            "— niet verplicht. Mag groter zijn dan 17.000 UTF-8-bytes; die limiet "
            "geldt alleen voor ‘Kopieer partijsetup’."
        )
        self._base_btn.clicked.connect(self._on_update_base)
        fresh_row.addWidget(self._base_btn)
        root.addLayout(fresh_row)

        scope_row = QHBoxLayout()
        scope_row.setSpacing(10)
        self._allow_swaps = QCheckBox("Nieuwe champs toestaan")
        raw = self._settings.value(_SEARCH_BETTER_KEY, False)
        self._allow_swaps.setChecked(
            raw is True or str(raw).strip().lower() in {"1", "true", "yes"}
        )
        self._allow_swaps.setToolTip(
            "Uit: alleen herschikken + specialisaties van de huidige party.\n"
            "Aan: AI mag owned champions als vervanging voorstellen."
        )
        self._allow_swaps.toggled.connect(self._on_scope_changed)
        scope_row.addWidget(self._allow_swaps)

        scope_row.addWidget(QLabel("Max. wissels"))
        self._max_swaps = QSpinBox()
        self._max_swaps.setRange(1, 3)
        self._max_swaps.setFixedWidth(64)
        self._max_swaps.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        try:
            self._max_swaps.setValue(
                max(1, min(3, int(self._settings.value(_MAX_SWAPS_KEY, 3) or 3)))
            )
        except (TypeError, ValueError):
            self._max_swaps.setValue(3)
        self._max_swaps.setEnabled(self._allow_swaps.isChecked())
        self._max_swaps.valueChanged.connect(self._on_scope_changed)
        scope_row.addWidget(self._max_swaps)

        from ic_gamedata.formation_ai_advice.research_mode import (
            RESEARCH_MODE_COMBO_ITEMS,
            RESEARCH_MODE_PROVIDED_ONLY,
            normalize_research_mode,
        )

        scope_row.addWidget(QLabel("Research"))
        self._research_mode = QComboBox()
        self._research_mode.setMinimumContentsLength(18)
        for label, value in RESEARCH_MODE_COMBO_ITEMS:
            self._research_mode.addItem(label, value)
        saved_mode = normalize_research_mode(
            self._settings.value(_RESEARCH_MODE_KEY, RESEARCH_MODE_PROVIDED_ONLY)
        )
        idx = self._research_mode.findData(saved_mode)
        self._research_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self._research_mode.setToolTip(
            "Alleen exportgegevens: geen externe research.\n"
            "Export + gerichte research: AI mag ontbrekende openbare "
            "restricties/mechanics opzoeken (research_gaps); "
            "actuele account-/runstatus blijft leidend."
        )
        self._research_mode.currentIndexChanged.connect(self._on_scope_changed)
        scope_row.addWidget(self._research_mode)
        scope_row.addStretch(1)
        root.addLayout(scope_row)

        self.refresh_freshness()

    def set_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable export controls without emitting ``busy_changed``."""
        self._base_btn.setEnabled(enabled)
        self._allow_swaps.setEnabled(enabled)
        self._max_swaps.setEnabled(enabled and self._allow_swaps.isChecked())
        self._research_mode.setEnabled(enabled)

    def set_busy(self, busy: bool) -> None:
        self._job_busy = busy
        self.set_controls_enabled(not busy)
        self.busy_changed.emit(busy)

    def _selected_research_mode(self) -> str:
        from ic_gamedata.formation_ai_advice.research_mode import (
            RESEARCH_MODE_PROVIDED_ONLY,
            normalize_research_mode,
        )

        data = self._research_mode.currentData()
        return normalize_research_mode(data or RESEARCH_MODE_PROVIDED_ONLY)

    def refresh_freshness(self) -> None:
        """Debounced background freshness check (safe to call from click handlers)."""
        self._fresh_timer.start()

    def _start_freshness_job(self) -> None:
        payload, formation = self._safe_live()
        if not payload or not formation:
            self._fresh_spinner.stop()
            self._freshness.setText("Geen formatie — vernieuw eerst (F5).")
            self._freshness.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
            self._freshness.setToolTip("")
            return
        goal_id, context, _, _ = self._goal_context()
        self._fresh_token += 1
        token = self._fresh_token
        goal = goal_id or "push"
        ctx = context or "campaign"
        self._fresh_spinner.start()

        def work() -> _FreshnessJobResult:
            report = assess_snapshot_freshness(
                payload, formation, goal=goal, context=ctx
            )
            warn = report.status in {
                SnapshotFreshnessStatus.ACCOUNT_CHANGED,
                SnapshotFreshnessStatus.MECHANICS_CHANGED,
                SnapshotFreshnessStatus.ACCOUNT_AND_MECHANICS_CHANGED,
                SnapshotFreshnessStatus.NO_SNAPSHOT,
                SnapshotFreshnessStatus.ACTUALITY_UNKNOWN,
            }
            if report.status == SnapshotFreshnessStatus.NO_SNAPSHOT:
                text = (
                    "Nog geen basisgegevens — exporteer eenmalig met Basis bijwerken."
                )
            elif report.recommend_new_base_export:
                text = (
                    "Basisgegevens verouderd (roster/mechanics) — "
                    "updaten aangeraden, niet verplicht."
                )
            else:
                text = "Basisgegevens actueel."
            tip = "\n".join(report.notes) if report.notes else ""
            return _FreshnessJobResult(token=token, text=text, warn=warn, tooltip=tip)

        start_callable_job(
            work,
            on_done=self._on_freshness_done,
            on_error=self._on_freshness_error,
            signals_parent=self,
        )

    def _on_freshness_done(self, result: object) -> None:
        if not isinstance(result, _FreshnessJobResult):
            return
        if result.token != self._fresh_token:
            return
        self._fresh_spinner.stop()
        warn_color = getattr(ui_theme, "WARN", None) or ui_theme.TEXT_MUTED
        self._freshness.setText(result.text)
        self._freshness.setStyleSheet(
            f"color: {warn_color if result.warn else ui_theme.TEXT_MUTED};"
        )
        self._freshness.setToolTip(result.tooltip)

    def _on_freshness_error(self, message: str) -> None:
        self._fresh_spinner.stop()
        self._freshness.setText(f"Basisstatus onbekend ({message}).")
        self._freshness.setStyleSheet(f"color: {ui_theme.TEXT_MUTED};")
        self._freshness.setToolTip("")

    def start_copy_advice_request(self) -> None:
        """Refresh live party, then build ADVICE_REQUEST off the UI thread.

        Re-clicks bump ``_copy_generation`` so in-flight work is discarded
        instead of mixing payloads. A party switch during refresh aborts.
        """
        goal_id, context, goal_parameters, fixed_dps = self._goal_context()
        if not goal_id:
            self.status_message.emit("Kies eerst een gebruikersdoel.")
            return

        snap_meta = get_exported_snapshot_meta()
        if not snap_meta or not snap_meta.get("snapshot_id"):
            self.status_message.emit(
                "Nog geen basisbestand — gebruik eerst Basis bijwerken."
            )
            return

        pre_payload, pre_formation = self._safe_live()
        if not pre_payload or not pre_formation:
            self.status_message.emit("Geen actieve formatie — vernieuw eerst (F5).")
            return
        expected_party_id: int | None = None
        try:
            from ic_gamedata.advice_fingerprint import party_id_from_payload

            expected_party_id = party_id_from_payload(pre_payload)
        except Exception:
            expected_party_id = None

        include_swap = self._allow_swaps.isChecked()
        max_swaps = int(self._max_swaps.value())
        research_mode = self._selected_research_mode()
        snapshot_id = str(snap_meta["snapshot_id"])
        # Cancel-and-restart: bump even while a prior copy is busy.
        self._copy_generation += 1
        copy_gen = self._copy_generation
        self.set_busy(True)
        self.status_message.emit("Actuele party verversen…")

        def _after_refresh() -> None:
            if copy_gen != self._copy_generation:
                # A newer copy click superseded this refresh.
                return
            payload, formation = self._safe_live()
            if not payload or not formation:
                self.set_busy(False)
                self.status_message.emit(
                    "Geen actieve formatie na verversen — export geannuleerd."
                )
                return
            live_party_id: int | None = None
            try:
                from ic_gamedata.advice_fingerprint import party_id_from_payload

                live_party_id = party_id_from_payload(payload)
            except Exception:
                live_party_id = None
            if (
                expected_party_id is not None
                and live_party_id is not None
                and int(live_party_id) != int(expected_party_id)
            ):
                self.set_busy(False)
                self.status_message.emit(
                    "Party gewisseld tijdens verversen — export geannuleerd. "
                    "Klik opnieuw voor de actuele party."
                )
                return
            self.status_message.emit("Partijsetup opbouwen…")

            def work() -> _AdviceRequestJobResult:
                return _build_advice_request_job(
                    payload=payload,
                    formation=formation,
                    snapshot_id=snapshot_id,
                    snapshot_meta=snap_meta,
                    goal_id=goal_id,
                    context=context,
                    fixed_dps=fixed_dps,
                    goal_parameters=goal_parameters,
                    include_swap=include_swap,
                    max_swaps=max_swaps,
                    research_mode=research_mode,
                    copy_generation=copy_gen,
                )

            def _on_build_error(message: str) -> None:
                if copy_gen != self._copy_generation:
                    return
                self._on_advice_request_error(message)

            start_callable_job(
                work,
                on_done=lambda result: self._on_advice_request_built(
                    result, expected_generation=copy_gen
                ),
                on_error=_on_build_error,
                signals_parent=self,
            )

        def _on_refresh_error(message: str) -> None:
            if copy_gen != self._copy_generation:
                return
            self.set_busy(False)
            self.status_message.emit(
                f"Verversen mislukt — niet gekopieerd: {message}"
            )

        if self._refresh_live is not None:
            self._refresh_live(_after_refresh, _on_refresh_error)
        else:
            # Tests / callers without a data service still build from live_source.
            _after_refresh()

    def copy_advice_request(self) -> bool:
        """Compatibility entry: kick off async copy (always returns True if started)."""
        self.start_copy_advice_request()
        return True

    def _on_advice_request_built(
        self,
        result: object,
        *,
        expected_generation: int | None = None,
    ) -> None:
        if (
            expected_generation is not None
            and expected_generation != self._copy_generation
        ):
            # Stale worker result after a newer copy click — drop silently.
            return
        if not isinstance(result, _AdviceRequestJobResult):
            self.set_busy(False)
            return
        if not result.ok:
            self.set_busy(False)
            self.status_message.emit(result.message)
            return
        if result.needs_confirm:
            # Offer scoped eligibility confirmations when presence conflicts exist.
            if result.presence_conflicts and self._confirm_eligibility is not None:
                confirmed_ids = self._confirm_eligibility(result.presence_conflicts)
                if confirmed_ids:
                    self.set_busy(False)
                    self.status_message.emit(
                        "Eligibility bevestigd — bouw partijsetup opnieuw…"
                    )
                    # Re-run copy so validation uses the new corrections.
                    QTimer.singleShot(0, self.start_copy_advice_request)
                    return
            reply = QMessageBox.question(
                self,
                "Validatie",
                "De partijsetup voldoet niet aan alle checks.\n\n"
                f"{result.validation_summary}\n\n"
                "Toch een diagnostische export kopiëren?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.set_busy(False)
                self.status_message.emit("Export geannuleerd.")
                return
        text = result.text or ""
        if not self._write_clipboard(text):
            self.set_busy(False)
            self.status_message.emit("Klembord schrijven mislukt.")
            return
        self.request_copied.emit()
        self.status_message.emit(
            f"Partijsetup gekopieerd ({result.chars} tekens){result.stale_note}."
        )
        self.set_busy(False)
        self.refresh_freshness()

    def _on_advice_request_error(self, message: str) -> None:
        self.set_busy(False)
        self.status_message.emit(f"Partijsetup mislukt: {message}")

    def _on_update_base(self) -> None:
        if self._job_busy:
            return
        note_ui_action("Advies: Basis bijwerken")
        payload, formation = self._safe_live()
        if not payload or not formation:
            self.status_message.emit("Geen formatie — vernieuw eerst (F5).")
            return
        goal_id, context, _, _ = self._goal_context()
        goal = goal_id or "push"
        ctx = context or "campaign"
        self.set_busy(True)
        self.status_message.emit("Basisgegevens opbouwen…")
        saved_base_text = self._base_btn.text()
        self._base_btn.setText("Bezig…")

        def work() -> _BaseSnapshotJobResult:
            try:
                snap = build_base_snapshot(
                    payload,
                    formation=formation,
                    goal=goal,
                    context=ctx,
                )
            except Exception as exc:
                return _BaseSnapshotJobResult(
                    ok=False, message=f"Opbouwen mislukt: {exc}"
                )
            try:
                saved = save_base_snapshot_to_basisgegevens(snap)
            except OSError as exc:
                return _BaseSnapshotJobResult(
                    ok=False, message=f"Opslaan mislukt: {exc}"
                )
            return _BaseSnapshotJobResult(
                ok=True,
                message=(
                    f"Basis opgeslagen in {BASISGEGEVENS_DIR.name}/{saved.name}."
                ),
                saved_name=saved.name,
            )

        def on_done(result: object) -> None:
            self._base_btn.setText(saved_base_text)
            self.set_busy(False)
            if not isinstance(result, _BaseSnapshotJobResult):
                return
            if not result.ok:
                QMessageBox.warning(self, "Basis", result.message)
                self.status_message.emit(result.message)
                return
            self.status_message.emit(result.message)
            self.refresh_freshness()

        def on_error(message: str) -> None:
            self._base_btn.setText(saved_base_text)
            self.set_busy(False)
            QMessageBox.warning(self, "Basis", message)
            self.status_message.emit(message)

        start_callable_job(
            work,
            on_done=on_done,
            on_error=on_error,
            signals_parent=self,
        )

    def _on_scope_changed(self, *_args) -> None:
        checked = self._allow_swaps.isChecked()
        self._max_swaps.setEnabled(checked and not self._job_busy)
        self._settings.setValue(_SEARCH_BETTER_KEY, checked)
        self._settings.setValue(_MAX_SWAPS_KEY, int(self._max_swaps.value()))
        self._settings.setValue(_RESEARCH_MODE_KEY, self._selected_research_mode())

    def _safe_live(self) -> tuple[dict[str, Any] | None, tuple]:
        try:
            payload, formation = self._live_source()
        except Exception:
            return None, ()
        if isinstance(payload, dict) and formation:
            return payload, formation
        return None, ()


def _build_advice_request_job(
    *,
    payload: dict[str, Any],
    formation: tuple,
    snapshot_id: str,
    snapshot_meta: dict[str, Any],
    goal_id: str,
    context: str,
    fixed_dps: int | None,
    goal_parameters: dict[str, Any],
    include_swap: bool,
    max_swaps: int,
    research_mode: str,
    copy_generation: int = 0,
) -> _AdviceRequestJobResult:
    """Pure build path — safe for worker threads (no Qt)."""
    try:
        req = build_advice_request(
            payload,
            formation,
            snapshot_id=snapshot_id,
            snapshot_meta=snapshot_meta,
            goal=goal_id,
            context=context,
            fixed_main_dps_id=fixed_dps,
            goal_parameters=goal_parameters,
            include_swap_scope=include_swap,
            research_mode=research_mode,
        )
    except Exception as exc:
        return _AdviceRequestJobResult(ok=False, message=f"Partijsetup mislukt: {exc}")

    if include_swap:
        _apply_max_swaps(req, max_swaps)

    validation = validate_advice_request_export(
        payload=payload,
        request=req,
        snapshot_id=snapshot_id,
        exported_snapshot_id=snapshot_id,
    )
    needs_confirm = False
    validation_summary = ""
    if validation.advice_ready:
        req = mark_request_validated(req, validation)
    else:
        req = mark_request_unvalidated(req, validation)
        needs_confirm = True
        validation_summary = validation.summary_nl()

    elig = req.get("roster_eligibility") if isinstance(req, dict) else None
    conflicts_raw = (
        (elig.get("presence_conflicts") or [])
        if isinstance(elig, dict)
        else []
    )
    presence_conflicts = tuple(
        c
        for c in conflicts_raw
        if isinstance(c, dict) and c.get("status") == "unresolved"
    )

    text = try_loss_free_shrink(
        build_advice_request_clipboard_text(
            req, mode=_MODE, max_chars=DEFAULT_CHAR_BUDGET
        )
    )
    info = evaluate_clipboard_budget(text, max_chars=DEFAULT_CHAR_BUDGET)
    if not info["within_budget"]:
        top_bits = [
            f"{row['name']}={row.get('utf8_bytes', row['chars'])}B"
            for row in advice_request_section_breakdown(req, mode=_MODE)[:3]
        ]
        top = f" Grootste: {', '.join(top_bits)}." if top_bits else ""
        return _AdviceRequestJobResult(
            ok=False,
            message=(
                f"Partijsetup te groot: {info['utf8_bytes']} > "
                f"{info['max_chars']} UTF-8-bytes."
                f"{top} Geen stille truncatie."
            ),
        )

    stale_note = ""
    try:
        report = assess_snapshot_freshness(
            payload, formation, goal=goal_id, context=context
        )
        if report.recommend_new_base_export:
            stale_note = " (verwijst nog naar oude basis — updaten mag later)"
    except Exception:
        pass

    return _AdviceRequestJobResult(
        ok=True,
        message="ok",
        text=text,
        needs_confirm=needs_confirm,
        validation_summary=validation_summary,
        chars=int(info["chars"]),
        stale_note=stale_note,
        presence_conflicts=presence_conflicts,
        copy_generation=copy_generation,
    )


def _apply_max_swaps(request: dict[str, Any], max_swaps: int) -> None:
    n = max(1, min(3, int(max_swaps)))
    constraints = request.get("constraints")
    if isinstance(constraints, dict):
        constraints["max_swaps_per_proposal"] = n
        constraints["may_replace_champions"] = True
    swap = request.get("swap")
    if isinstance(swap, dict):
        swap["max_swaps_per_proposal"] = n
