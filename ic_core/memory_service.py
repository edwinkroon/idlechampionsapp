"""Process-memory reader owned by one service — never share the resolver across threads."""

import threading
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal


@dataclass(frozen=True)
class MemoryReading:
    area: int | None
    gems: int | None
    modron_goal: int | None
    detail: str
    error: str | None = None


class _MemorySignals(QObject):
    done = Signal(object)


class _MemoryReadRunnable(QRunnable):
    def __init__(
        self,
        *,
        resolver_holder: dict,
        lock: threading.Lock,
        ui_hint: int | None,
        signals: _MemorySignals,
    ) -> None:
        super().__init__()
        self._holder = resolver_holder
        self._lock = lock
        self._ui_hint = ui_hint
        self.signals = signals

    def run(self) -> None:
        try:
            from ic_reader.resolver import create_resolver
        except ImportError:
            self.signals.done.emit(
                MemoryReading(
                    None,
                    None,
                    None,
                    "ic_reader niet beschikbaar (pip install psutil)",
                    error="ic_reader missing",
                )
            )
            return
        try:
            with self._lock:
                resolver = self._holder.get("resolver")
                if resolver is None:
                    resolver = create_resolver(debug=False)
                    resolver.connect()
                    self._holder["resolver"] = resolver
                resolved_area = resolver.resolve_current_area(ui_hint_area=self._ui_hint)
                resolved_gems = resolver.resolve_gems_this_reset()
                area = int(resolved_area.value) if resolved_area.value is not None else None
                gems = int(resolved_gems.value) if resolved_gems.value is not None else None
                modron = None
                try:
                    resolved_modron = resolver.resolve_modron_reset_area()
                    if resolved_modron.value is not None:
                        modron = int(resolved_modron.value)
                except Exception:
                    modron = None
                area_id = resolved_area.candidate_id
                area_conf = resolved_area.confidence
                gems_id = resolved_gems.candidate_id
                gems_conf = resolved_gems.confidence
            parts: list[str] = []
            if area is not None:
                parts.append(f"area={area} ({area_id or '?'}, {area_conf:.1f})")
            if gems is not None:
                parts.append(f"gems={gems} ({gems_id or '?'}, {gems_conf:.1f})")
            detail = "memory: " + " · ".join(parts) if parts else "memory: geen offsets/data"
            self.signals.done.emit(MemoryReading(area, gems, modron, detail))
        except Exception as exc:
            self.signals.done.emit(
                MemoryReading(None, None, None, str(exc), error=str(exc))
            )


class MemoryService(QObject):
    """Exclusive owner of AreaResolver; polls on a timer while active."""

    memory_updated = Signal(object)  # MemoryReading

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._holder: dict = {"resolver": None}
        self._lock = threading.Lock()
        self._active = False
        self._inflight = False
        self._disconnect_after = False
        self._ui_hint_provider: Callable[[], int | None] = lambda: None
        self._signals = _MemorySignals(self)
        self._signals.done.connect(self._on_done)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._latest: MemoryReading | None = None

    @property
    def latest(self) -> MemoryReading | None:
        return self._latest

    @property
    def active(self) -> bool:
        return self._active

    def set_ui_hint_provider(self, provider: Callable[[], int | None]) -> None:
        self._ui_hint_provider = provider

    def start(self, interval_ms: int = 1000) -> None:
        self._active = True
        self._disconnect_after = False
        self._timer.setInterval(interval_ms)
        if not self._timer.isActive():
            self._timer.start()
        self._tick()

    def stop(self) -> None:
        self._active = False
        self._timer.stop()
        if self._inflight:
            self._disconnect_after = True
        else:
            self.disconnect_resolver()

    def disconnect_resolver(self) -> None:
        with self._lock:
            resolver = self._holder.get("resolver")
            if resolver is None:
                return
            try:
                resolver.disconnect()
            except Exception:
                pass
            self._holder["resolver"] = None

    def request_read(self) -> None:
        if self._inflight:
            return
        self._start_read()

    def _tick(self) -> None:
        if not self._active or self._inflight:
            return
        self._start_read()

    def _start_read(self) -> None:
        self._inflight = True
        hint = None
        try:
            hint = self._ui_hint_provider()
        except Exception:
            hint = None
        worker = _MemoryReadRunnable(
            resolver_holder=self._holder,
            lock=self._lock,
            ui_hint=hint,
            signals=self._signals,
        )
        QThreadPool.globalInstance().start(worker)

    def _on_done(self, reading: MemoryReading) -> None:
        self._inflight = False
        self._latest = reading
        self.memory_updated.emit(reading)
        if self._disconnect_after:
            self._disconnect_after = False
            self.disconnect_resolver()
