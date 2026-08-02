"""Resolve logical values (current_area) from configured candidates."""

from __future__ import annotations

import logging
from pathlib import Path

from ic_reader.config_loader import load_config
from ic_reader.exceptions import ConfigError, ProcessNotFoundError
from ic_reader.memory import MemoryReader, Win32MemoryReader
from ic_reader.models import (
    GameOffsetsConfig,
    ReadAttempt,
    ResolvedValue,
    ScoredCandidate,
    ValueCandidateDef,
)
from ic_reader.pointers import read_value_at_chain
from ic_reader.process import find_process, get_module_base, list_modules
from ic_reader.validators import CandidateHistory, pick_best, score_candidate

logger = logging.getLogger(__name__)


class AreaResolver:
    """Read-only resolver for game state values defined in config."""

    def __init__(
        self,
        config: GameOffsetsConfig,
        *,
        reader: MemoryReader | None = None,
        pid: int | None = None,
        debug: bool = False,
    ) -> None:
        self.config = config
        self.debug = debug
        self._owns_reader = reader is None
        self._reader = reader
        self._pid = pid
        self._module_bases: dict[str, int] = {}
        self._history = CandidateHistory()

    def connect(self) -> None:
        if self._reader is not None:
            return
        proc = find_process(self.config.process_names)
        self._pid = proc.pid
        self._reader = Win32MemoryReader.for_pid(proc.pid)
        logger.info("Attached to %s (pid=%s)", proc.name, proc.pid)

    def disconnect(self) -> None:
        if self._owns_reader and isinstance(self._reader, Win32MemoryReader):
            self._reader.close()
        self._reader = None

    def __enter__(self) -> AreaResolver:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.disconnect()

    def _get_module_base(self, module_name: str) -> int:
        if module_name in self._module_bases:
            return self._module_bases[module_name]
        if self._pid is None:
            raise ProcessNotFoundError("Not connected; call connect() first")
        if self._reader is None:
            raise ProcessNotFoundError("No memory reader available")
        mods = list_modules(self._pid)
        info = get_module_base(self._pid, module_name, modules=mods)
        self._module_bases[module_name] = info.base_address
        if self.debug:
            logger.debug(
                "Module %s base=0x%X size=%s",
                info.name,
                info.base_address,
                info.size,
            )
        return info.base_address

    def read_candidate(
        self,
        candidate: ValueCandidateDef,
    ) -> ReadAttempt:
        assert self._reader is not None
        chain = candidate.pointer_chain
        try:
            if chain.static_offset == 0 and not chain.offsets:
                return ReadAttempt(
                    candidate_id=candidate.id,
                    success=False,
                    error="VERIFY: configure static_offset and offsets in game_offsets.json",
                )
            module_base = self._get_module_base(chain.module)
            value, final_addr, steps = read_value_at_chain(
                self._reader,
                module_base,
                chain,
                candidate.value_type,
                collect_steps=self.debug,
            )
            if self.debug:
                for step in steps:
                    logger.debug(
                        "  step %s: before=0x%X off=0x%X after=%s %s",
                        step.step_index,
                        step.address_before,
                        step.offset_applied,
                        f"0x{step.address_after:X}" if step.address_after else "—",
                        step.note,
                    )
                logger.debug(
                    "Candidate %s -> %s at 0x%X",
                    candidate.id,
                    value,
                    final_addr,
                )
            return ReadAttempt(
                candidate_id=candidate.id,
                success=True,
                raw_value=value,
                final_address=final_addr,
                steps=steps,
            )
        except Exception as exc:
            if self.debug:
                logger.debug("Candidate %s rejected: %s", candidate.id, exc)
            return ReadAttempt(
                candidate_id=candidate.id,
                success=False,
                error=str(exc),
            )

    def resolve_key(
        self,
        key: str,
        *,
        ui_hint_area: int | None = None,
    ) -> ResolvedValue:
        candidates = self.config.values.get(key)
        if not candidates:
            raise ConfigError(f"No candidates configured for key '{key}'")

        attempts: list[ReadAttempt] = []
        scored: list[ScoredCandidate] = []
        for cand in candidates:
            attempt = self.read_candidate(cand)
            attempts.append(attempt)
            scored.append(
                score_candidate(
                    cand,
                    attempt,
                    history=self._history,
                    ui_hint_area=ui_hint_area,
                )
            )

        best = pick_best(scored)
        if best is None:
            reasons = []
            for s in scored:
                if s.rejection_reasons:
                    reasons.append(f"{s.candidate.id}: {', '.join(s.rejection_reasons)}")
                elif s.attempt.error:
                    reasons.append(f"{s.candidate.id}: {s.attempt.error}")
            logger.warning("No accepted candidate for '%s'. %s", key, "; ".join(reasons))
            return ResolvedValue(
                key=key,
                value=None,
                candidate_id=None,
                confidence=0.0,
                all_attempts=attempts,
            )

        if self.debug and best.rejection_reasons:
            logger.debug(
                "Accepted %s with notes: %s",
                best.candidate.id,
                best.rejection_reasons,
            )

        return ResolvedValue(
            key=key,
            value=best.attempt.raw_value,
            candidate_id=best.candidate.id,
            confidence=best.score,
            all_attempts=attempts,
        )

    def resolve_current_area(self, *, ui_hint_area: int | None = None) -> ResolvedValue:
        return self.resolve_key("current_area", ui_hint_area=ui_hint_area)

    def resolve_gems_this_reset(self) -> ResolvedValue:
        """Live gems earned this Modron/adventure reset, if offsets are configured."""
        if "gems_this_reset" not in self.config.values:
            return ResolvedValue(
                key="gems_this_reset",
                value=None,
                candidate_id=None,
                confidence=0.0,
                all_attempts=[],
            )
        return self.resolve_key("gems_this_reset")

    def resolve_modron_reset_area(self) -> ResolvedValue:
        """Modron Set Area Goal from memory, if offsets are configured."""
        if "modron_reset_area" not in self.config.values:
            return ResolvedValue(
                key="modron_reset_area",
                value=None,
                candidate_id=None,
                confidence=0.0,
                all_attempts=[],
            )
        return self.resolve_key("modron_reset_area")


def create_resolver(
    config_path: Path | None = None,
    *,
    debug: bool = False,
) -> AreaResolver:
    config = load_config(config_path)
    return AreaResolver(config, debug=debug)
