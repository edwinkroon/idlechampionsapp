"""Single owner for live game API snapshots — poll, coalesce, publish."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from ic_core.api_fetch_worker import ApiFetchRunnable, ApiFetchSignals
from ic_gamedata.advice_fingerprint import advice_fingerprint, party_id_from_payload
from ic_gamedata.credential_cache import CredentialCache
from ic_gamedata.credentials import GameCredentials
from ic_gamedata.payload_quality import PayloadQuality, assess_payload_quality

# Slow heartbeat keeps data fresh when the game is quiet.
_BASE_POLL_MS = 30000
_MAX_POLL_MS = 120000
# Cheap mtime/size probe — reacts when the game writes webRequestLog.
_LOG_PROBE_MS = 1000
# Avoid stampeding the API when the log grows in bursts.
_MIN_CHANGE_POLL_GAP_MS = 2000


def _format_cache_age(seconds: float) -> str:
    age = max(0, int(seconds))
    if age < 60:
        return f"{age}s"
    mins = age // 60
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}u{mins % 60:02d}m"


@dataclass(frozen=True)
class SnapshotEnvelope:
    """Immutable view of the latest merged API/log snapshot."""

    version: int
    generation: int
    payload: dict[str, Any] | None
    api_snap: Any
    snap: Any
    err: str | None
    api_detail: str
    credentials: GameCredentials | None
    fetched_at: float
    advice_fp: tuple[Any, ...] | None
    party_id: int | None
    force_consumers: frozenset[str] = field(default_factory=frozenset)
    auto_refresh: bool = True
    degraded: bool = False
    last_success_at: float | None = None
    quality: PayloadQuality | None = None


class GameDataService(QObject):
    """Central game-data client: one HTTP path, coalesced polls, versioned store.

    UI tabs subscribe to ``snapshot_updated`` and must not call urllib themselves.
    On API failure the last good snapshot is kept and marked ``degraded``.

    Polling is hybrid: a slow heartbeat plus an immediate poll when
    ``webRequestLog.txt`` grows (game API activity), debounced to avoid storms.
    """

    snapshot_updated = Signal(object)  # SnapshotEnvelope
    fetch_failed = Signal(str)
    fetch_state_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._credentials: GameCredentials | None = None
        self._log_path: Path | None = None
        self._cred_cache = CredentialCache()
        self._version = 0
        self._latest: SnapshotEnvelope | None = None
        self._last_success_at: float | None = None
        self._consecutive_failures = 0
        self._base_poll_ms = _BASE_POLL_MS
        self._inflight = False
        self._generation = 0
        self._pending_reasons: set[str] = set()
        self._pending_force: set[str] = set()
        self._pending_auto_refresh = True
        self._log_stat_key: tuple[int, int] | None = None
        self._last_change_poll_mono = 0.0
        self._signals = ApiFetchSignals(self)
        self._signals.done.connect(self._on_fetch_done)
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        # 10s timeout × 3 attempts + backoff (~3s) + margin
        self._watchdog.setInterval(40000)
        self._watchdog.timeout.connect(self._on_watchdog)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._base_poll_ms)
        self._poll_timer.timeout.connect(self._on_timer)
        self._log_probe_timer = QTimer(self)
        self._log_probe_timer.setInterval(_LOG_PROBE_MS)
        self._log_probe_timer.timeout.connect(self._on_log_probe)
        self._deferred_change_timer = QTimer(self)
        self._deferred_change_timer.setSingleShot(True)
        self._deferred_change_timer.timeout.connect(self._on_deferred_log_change)

    # ------------------------------------------------------------------ config

    @property
    def credentials(self) -> GameCredentials | None:
        return self._credentials

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    @property
    def latest(self) -> SnapshotEnvelope | None:
        return self._latest

    @property
    def last_payload(self) -> dict[str, Any] | None:
        return self._latest.payload if self._latest is not None else None

    @property
    def last_success_at(self) -> float | None:
        return self._last_success_at

    @property
    def inflight(self) -> bool:
        return self._inflight

    def configure(
        self,
        *,
        log_path: Path | None,
        credentials: GameCredentials | None = None,
    ) -> None:
        path_changed = log_path != self._log_path
        self._log_path = log_path
        if path_changed:
            self._cred_cache.clear()
            self._log_stat_key = None
            self._deferred_change_timer.stop()
            # Seed baseline so the first probe does not treat an existing log as "new".
            self._peek_log_stat(update=True)
        if credentials is not None:
            self._credentials = credentials
        elif log_path is not None:
            cached = self._cred_cache.get(log_path)
            if cached is not None:
                self._credentials = cached

    def start_polling(self, interval_ms: int = _BASE_POLL_MS) -> None:
        self._base_poll_ms = interval_ms
        self._poll_timer.setInterval(self._current_poll_interval())
        if not self._poll_timer.isActive():
            self._poll_timer.start()
        if not self._log_probe_timer.isActive():
            self._peek_log_stat(update=True)
            self._log_probe_timer.start()

    def stop_polling(self) -> None:
        self._poll_timer.stop()
        self._log_probe_timer.stop()
        self._deferred_change_timer.stop()
        self._watchdog.stop()

    def refresh_credentials(self) -> bool:
        if self._log_path is None:
            return self._credentials is not None
        self._cred_cache.clear()
        creds = self._cred_cache.get(self._log_path)
        if creds is not None:
            self._credentials = creds
        return self._credentials is not None

    def _current_poll_interval(self) -> int:
        if self._consecutive_failures <= 0:
            return self._base_poll_ms
        # 30s → 60s → 120s max while API is down
        factor = min(2 ** min(self._consecutive_failures, 3), _MAX_POLL_MS // max(self._base_poll_ms, 1))
        return min(self._base_poll_ms * factor, _MAX_POLL_MS)

    def _apply_poll_backoff(self) -> None:
        if self._poll_timer.isActive():
            self._poll_timer.setInterval(self._current_poll_interval())

    def _peek_log_stat(self, *, update: bool) -> tuple[int, int] | None:
        if self._log_path is None:
            return None
        try:
            stat = self._log_path.stat()
        except OSError:
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        if update:
            self._log_stat_key = key
        return key

    def _on_log_probe(self) -> None:
        key = self._peek_log_stat(update=False)
        if key is None:
            return
        if self._log_stat_key is None:
            self._log_stat_key = key
            return
        if key == self._log_stat_key:
            return
        self._log_stat_key = key
        self._request_change_poll()

    def _request_change_poll(self) -> None:
        """Poll soon after game log activity; debounce bursts, restart heartbeat."""
        now = time.monotonic()
        elapsed_ms = (now - self._last_change_poll_mono) * 1000.0
        if elapsed_ms >= _MIN_CHANGE_POLL_GAP_MS:
            self._deferred_change_timer.stop()
            self._fire_change_poll()
            return
        remaining = max(50, int(_MIN_CHANGE_POLL_GAP_MS - elapsed_ms))
        if not self._deferred_change_timer.isActive():
            self._deferred_change_timer.start(remaining)

    def _on_deferred_log_change(self) -> None:
        self._fire_change_poll()

    def _fire_change_poll(self) -> None:
        self._last_change_poll_mono = time.monotonic()
        self.request_poll(reason="log_change", auto_refresh=True)
        # Push the slow heartbeat out so we don't double-fetch shortly after.
        if self._poll_timer.isActive():
            self._poll_timer.start()

    # ------------------------------------------------------------------ poll API

    def request_poll(
        self,
        *,
        reason: str = "manual",
        force_consumers: frozenset[str] | set[str] | None = None,
        auto_refresh: bool = True,
    ) -> None:
        """Coalesced poll request.

        ``force_consumers`` examples: ``{"advisor", "specializations"}``.
        While a fetch is in flight, reasons/forces merge and a single follow-up runs.
        """
        force = set(force_consumers or ())
        if self._inflight:
            self._pending_reasons.add(reason)
            self._pending_force |= force
            if not auto_refresh:
                self._pending_auto_refresh = False
            return

        self._pending_reasons.clear()
        self._pending_force = set(force)
        self._pending_auto_refresh = auto_refresh
        self._start_fetch(reason=reason)

    def _on_timer(self) -> None:
        self.request_poll(reason="timer", auto_refresh=True)

    def _start_fetch(self, *, reason: str) -> None:
        if self._log_path is not None:
            fresh = self._cred_cache.get(self._log_path)
            if fresh is not None:
                self._credentials = fresh
        if self._credentials is None:
            self._note_failure("Geen API-credentials.")
            self._drain_pending_after_failure()
            return

        self._generation += 1
        generation = self._generation
        self._inflight = True
        self.fetch_state_changed.emit(True)
        self._watchdog.start()
        worker = ApiFetchRunnable(
            self._credentials,
            self._log_path,
            generation=generation,
            signals=self._signals,
        )
        QThreadPool.globalInstance().start(worker)

    def _cache_age_text(self) -> str:
        if self._last_success_at is None:
            return "geen eerdere succesvolle poll"
        return f"cache {_format_cache_age(time.time() - self._last_success_at)} oud"

    def _note_failure(self, err: str) -> None:
        self._consecutive_failures += 1
        self._apply_poll_backoff()
        detail = f"{err} ({self._cache_age_text()})"
        self.fetch_failed.emit(detail)
        self._publish_degraded(err=detail)

    def _publish_degraded(self, *, err: str) -> None:
        """Keep serving last good data; mark degraded for UI."""
        force = frozenset(self._pending_force)
        auto = self._pending_auto_refresh
        if self._latest is None:
            # Nothing to serve — still bump a stub so UI can show the error.
            quality = assess_payload_quality(None)
            stub = SnapshotEnvelope(
                version=self._version,
                generation=self._generation,
                payload=None,
                api_snap=None,
                snap=None,
                err=err,
                api_detail=err,
                credentials=self._credentials,
                fetched_at=time.time(),
                advice_fp=None,
                party_id=None,
                force_consumers=force,
                auto_refresh=auto,
                degraded=True,
                last_success_at=self._last_success_at,
                quality=quality,
            )
            self._latest = stub
            self.snapshot_updated.emit(stub)
            return

        bumped = SnapshotEnvelope(
            version=self._latest.version,
            generation=self._generation,
            payload=self._latest.payload,
            api_snap=self._latest.api_snap,
            snap=self._latest.snap,
            err=err,
            api_detail=err,
            credentials=self._latest.credentials or self._credentials,
            fetched_at=self._latest.fetched_at,
            advice_fp=self._latest.advice_fp,
            party_id=self._latest.party_id,
            force_consumers=force,
            auto_refresh=auto,
            degraded=True,
            last_success_at=self._last_success_at,
            quality=self._latest.quality,
        )
        self._latest = bumped
        self.snapshot_updated.emit(bumped)

    def _on_watchdog(self) -> None:
        if not self._inflight:
            return
        self._generation += 1
        self._inflight = False
        self.fetch_state_changed.emit(False)
        self._note_failure("API-poll timeout")
        self._drain_pending()

    def _on_fetch_done(self, result: dict) -> None:
        generation = int(result.get("generation") or 0)
        if generation != self._generation or not self._inflight:
            return
        self._watchdog.stop()
        self._inflight = False
        self.fetch_state_changed.emit(False)

        if result.get("error"):
            self._note_failure(str(result["error"]))
            self._drain_pending()
            return

        api_err = result.get("err")
        payload = result.get("payload")
        api_snap = result.get("api_snap")
        # Soft failure: HTTP ok path returned error string and no usable payload
        if payload is None and api_snap is None and api_err:
            self._note_failure(str(api_err))
            self._drain_pending()
            return

        credentials = result.get("credentials")
        if credentials is not None:
            self._credentials = credentials

        self._consecutive_failures = 0
        self._apply_poll_backoff()
        self._version += 1
        now = time.time()
        self._last_success_at = now
        force = frozenset(self._pending_force)
        auto = self._pending_auto_refresh
        self._pending_force.clear()
        self._pending_reasons.clear()
        self._pending_auto_refresh = True

        payload_dict = payload if isinstance(payload, dict) else None
        quality = assess_payload_quality(payload_dict)
        api_detail = str(result.get("api_detail") or "")
        if quality.warnings:
            api_detail = (api_detail + " · " if api_detail else "") + quality.warnings[0]

        envelope = SnapshotEnvelope(
            version=self._version,
            generation=generation,
            payload=payload_dict,
            api_snap=api_snap,
            snap=result.get("snap"),
            err=str(api_err) if api_err else None,
            api_detail=api_detail or "API ok",
            credentials=self._credentials,
            fetched_at=now,
            advice_fp=advice_fingerprint(payload_dict),
            party_id=party_id_from_payload(payload_dict),
            force_consumers=force,
            auto_refresh=auto,
            degraded=bool(quality.warnings) or bool(api_err),
            last_success_at=self._last_success_at,
            quality=quality,
        )
        self._latest = envelope
        self.snapshot_updated.emit(envelope)
        self._drain_pending()

    def _drain_pending_after_failure(self) -> None:
        self._pending_force.clear()
        self._pending_reasons.clear()
        self._pending_auto_refresh = True

    def _drain_pending(self) -> None:
        if not self._pending_reasons and not self._pending_force:
            return
        reasons = set(self._pending_reasons)
        force = set(self._pending_force)
        auto = self._pending_auto_refresh
        self._pending_reasons.clear()
        self._pending_force.clear()
        self._pending_auto_refresh = True
        reason = next(iter(reasons), "coalesced")
        self._pending_force = force
        self._pending_auto_refresh = auto
        self._start_fetch(reason=reason)
