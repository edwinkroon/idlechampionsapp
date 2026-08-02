"""Score and filter memory read candidates for plausibility."""

from __future__ import annotations

import time
from typing import Any

from ic_reader.models import ReadAttempt, ScoredCandidate, ValueCandidateDef, ValueType


class CandidateHistory:
    """Tracks recent readings per candidate for rate-of-change checks."""

    def __init__(self) -> None:
        self._last: dict[str, tuple[float, int | float]] = {}

    def observe(self, candidate_id: str, value: int | float, timestamp: float | None = None) -> float | None:
        """Return delta per second vs previous sample, or None if first sample."""
        ts = timestamp if timestamp is not None else time.monotonic()
        prev = self._last.get(candidate_id)
        self._last[candidate_id] = (ts, value)
        if prev is None:
            return None
        prev_ts, prev_val = prev
        dt = ts - prev_ts
        if dt <= 0:
            return None
        return abs(float(value) - float(prev_val)) / dt


def score_candidate(
    candidate: ValueCandidateDef,
    attempt: ReadAttempt,
    *,
    history: CandidateHistory | None = None,
    ui_hint_area: int | None = None,
) -> ScoredCandidate:
    """
    Score a successful read. Higher is better.

    Rejects: failed reads, unverified empty chains, non-numeric area, out of range,
    absurd rate of change, mismatch with optional UI hint.
    """
    reasons: list[str] = []
    score = 0.0

    if not attempt.success or attempt.raw_value is None:
        return ScoredCandidate(
            candidate=candidate,
            attempt=attempt,
            score=0.0,
            accepted=False,
            rejection_reasons=[attempt.error or "read failed"],
        )

    if candidate.status.value == "deprecated":
        reasons.append("candidate marked deprecated")
        return ScoredCandidate(candidate, attempt, 0.0, False, reasons)

    # Unverified with no real offsets should not win automatically
    chain = candidate.pointer_chain
    if (
        candidate.status.value in ("unverified", "verify")
        and chain.static_offset == 0
        and not chain.offsets
    ):
        reasons.append("placeholder chain (no offsets configured)")
        return ScoredCandidate(candidate, attempt, 0.0, False, reasons)

    raw = attempt.raw_value
    if candidate.value_type in (ValueType.INT32, ValueType.INT64):
        if not isinstance(raw, (int, float)):
            reasons.append("expected numeric value")
            return ScoredCandidate(candidate, attempt, 0.0, False, reasons)
        num = int(raw)
        min_ok = candidate.min_plausible if candidate.min_plausible is not None else 0
        if num < min_ok:
            reasons.append(f"below min_plausible ({num} < {min_ok})")
            return ScoredCandidate(candidate, attempt, 0.0, False, reasons)
        if candidate.max_plausible is not None and num > candidate.max_plausible:
            reasons.append(f"above max_plausible ({num} > {candidate.max_plausible})")
            return ScoredCandidate(candidate, attempt, 0.0, False, reasons)
        if history and candidate.max_delta_per_second is not None:
            dps = history.observe(candidate.id, num)
            if dps is not None and dps > candidate.max_delta_per_second:
                reasons.append(
                    f"changes too fast ({dps:.1f}/s > {candidate.max_delta_per_second}/s)"
                )
                return ScoredCandidate(candidate, attempt, 0.0, False, reasons)
        if ui_hint_area is not None and abs(num - ui_hint_area) > 2:
            reasons.append(f"differs from UI hint ({num} vs {ui_hint_area})")
            score -= 5.0
        else:
            if ui_hint_area is not None and num == ui_hint_area:
                score += 10.0
        score += 5.0
        if candidate.status.value == "verified":
            score += 20.0
        elif candidate.status.value == "verify":
            score += 2.0
        return ScoredCandidate(candidate, attempt, score, True, reasons)

    # Non-area types: accept if read succeeded
    score += 1.0
    return ScoredCandidate(candidate, attempt, score, True, reasons)


def pick_best(scored: list[ScoredCandidate]) -> ScoredCandidate | None:
    accepted = [s for s in scored if s.accepted]
    if not accepted:
        return None
    return max(accepted, key=lambda s: s.score)
