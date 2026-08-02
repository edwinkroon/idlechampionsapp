"""Data models for memory reading and candidate resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValueType(str, Enum):
    INT32 = "int32"
    INT64 = "int64"
    FLOAT = "float"
    STRING = "string"


class CandidateStatus(str, Enum):
    """Whether offsets are trusted for production use."""

    UNVERIFIED = "unverified"
    VERIFY = "verify"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class PointerChainDef:
    """Static module offset + multi-level pointer offsets (Cheat Engine style)."""

    module: str
    static_offset: int
    offsets: tuple[int, ...]
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PointerChainDef:
        static = _parse_hex_int(data.get("static_offset", 0))
        raw_offsets = data.get("offsets") or []
        offsets = tuple(_parse_hex_int(o) for o in raw_offsets)
        return cls(
            module=str(data.get("module", "GameAssembly.dll")),
            static_offset=static,
            offsets=offsets,
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class ValueCandidateDef:
    """One possible memory location for a logical value (e.g. current_area)."""

    id: str
    status: CandidateStatus
    pointer_chain: PointerChainDef
    value_type: ValueType
    description: str = ""
    min_plausible: int | None = None
    max_plausible: int | None = None
    max_delta_per_second: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValueCandidateDef:
        chain = PointerChainDef.from_dict(data.get("pointer_chain") or {})
        status_raw = str(data.get("status", "unverified")).lower()
        try:
            status = CandidateStatus(status_raw)
        except ValueError:
            status = CandidateStatus.UNVERIFIED
        vt_raw = str(data.get("value_type", "int32")).lower()
        value_type = ValueType(vt_raw) if vt_raw in ValueType._value2member_map_ else ValueType.INT32
        return cls(
            id=str(data["id"]),
            status=status,
            pointer_chain=chain,
            value_type=value_type,
            description=str(data.get("description", "")),
            min_plausible=data.get("min_plausible"),
            max_plausible=data.get("max_plausible"),
            max_delta_per_second=data.get("max_delta_per_second"),
        )


@dataclass(frozen=True)
class GameOffsetsConfig:
    """Root configuration loaded from game_offsets.json."""

    version: str
    game_version_note: str
    process_names: tuple[str, ...]
    preferred_modules: tuple[str, ...]
    values: dict[str, tuple[ValueCandidateDef, ...]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameOffsetsConfig:
        proc = data.get("process") or {}
        names = tuple(proc.get("executable_names") or ["IdleChampions.exe"])
        modules = tuple(proc.get("modules") or ["GameAssembly.dll", "UnityPlayer.dll"])
        values: dict[str, tuple[ValueCandidateDef, ...]] = {}
        for key, spec in (data.get("values") or {}).items():
            raw_candidates = spec.get("candidates") if isinstance(spec, dict) else spec
            if not raw_candidates:
                values[key] = ()
                continue
            values[key] = tuple(ValueCandidateDef.from_dict(c) for c in raw_candidates)
        return cls(
            version=str(data.get("version", "0.0.0")),
            game_version_note=str(data.get("game_version_note", "")),
            process_names=names,
            preferred_modules=modules,
            values=values,
        )


@dataclass
class PointerStep:
    """One step while resolving a chain (for debug output)."""

    step_index: int
    address_before: int
    offset_applied: int
    address_after: int | None
    read_pointer: bool
    note: str = ""


@dataclass
class ReadAttempt:
    """Result of reading one candidate once."""

    candidate_id: str
    success: bool
    raw_value: int | float | str | None = None
    final_address: int | None = None
    steps: list[PointerStep] = field(default_factory=list)
    error: str | None = None


@dataclass
class ScoredCandidate:
    """Candidate after validation scoring."""

    candidate: ValueCandidateDef
    attempt: ReadAttempt
    score: float
    accepted: bool
    rejection_reasons: list[str] = field(default_factory=list)


@dataclass
class ResolvedValue:
    """Best resolved value for a logical key."""

    key: str
    value: int | float | str | None
    candidate_id: str | None
    confidence: float
    all_attempts: list[ReadAttempt] = field(default_factory=list)


def _parse_hex_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s or s.lower() in ("null", "none"):
        return 0
    return int(s, 0)
