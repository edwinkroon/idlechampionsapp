"""Unit tests for candidate scoring."""

from __future__ import annotations

import unittest

from ic_reader.models import (
    CandidateStatus,
    PointerChainDef,
    ReadAttempt,
    ValueCandidateDef,
    ValueType,
)
from ic_reader.validators import CandidateHistory, pick_best, score_candidate


def _cand(
    cid: str,
    status: CandidateStatus = CandidateStatus.UNVERIFIED,
    static: int = 0x100,
    offsets: tuple[int, ...] = (0x10,),
) -> ValueCandidateDef:
    return ValueCandidateDef(
        id=cid,
        status=status,
        pointer_chain=PointerChainDef(
            module="GameAssembly.dll",
            static_offset=static,
            offsets=offsets,
        ),
        value_type=ValueType.INT32,
        min_plausible=1,
        max_plausible=1000,
        max_delta_per_second=100,
    )


class TestValidators(unittest.TestCase):
    def test_accepts_positive_verified(self) -> None:
        cand = _cand("a", status=CandidateStatus.VERIFIED)
        attempt = ReadAttempt(candidate_id="a", success=True, raw_value=15)
        scored = score_candidate(cand, attempt)
        self.assertTrue(scored.accepted)
        self.assertGreater(scored.score, 10)

    def test_rejects_placeholder(self) -> None:
        cand = ValueCandidateDef(
            id="placeholder",
            status=CandidateStatus.UNVERIFIED,
            pointer_chain=PointerChainDef(
                module="GameAssembly.dll",
                static_offset=0,
                offsets=(),
            ),
            value_type=ValueType.INT32,
        )
        attempt = ReadAttempt(candidate_id="placeholder", success=True, raw_value=5)
        scored = score_candidate(cand, attempt)
        self.assertFalse(scored.accepted)
        self.assertIn("placeholder", scored.rejection_reasons[0])

    def test_rejects_negative_area(self) -> None:
        cand = _cand("b")
        attempt = ReadAttempt(candidate_id="b", success=True, raw_value=0)
        scored = score_candidate(cand, attempt)
        self.assertFalse(scored.accepted)

    def test_ui_hint_boost(self) -> None:
        cand = _cand("c", status=CandidateStatus.VERIFY)
        attempt = ReadAttempt(candidate_id="c", success=True, raw_value=3)
        low = score_candidate(cand, attempt, ui_hint_area=99)
        high = score_candidate(cand, attempt, ui_hint_area=3)
        self.assertTrue(high.accepted)
        self.assertGreater(high.score, low.score)

    def test_rate_limit(self) -> None:
        history = CandidateHistory()
        cand = _cand("d")
        cand = ValueCandidateDef(
            id="d",
            status=CandidateStatus.VERIFY,
            pointer_chain=cand.pointer_chain,
            value_type=ValueType.INT32,
            max_delta_per_second=5,
        )
        a1 = ReadAttempt(candidate_id="d", success=True, raw_value=10)
        score_candidate(cand, a1, history=history)
        a2 = ReadAttempt(candidate_id="d", success=True, raw_value=100)
        scored = score_candidate(cand, a2, history=history)
        self.assertFalse(scored.accepted)

    def test_pick_best(self) -> None:
        c1 = score_candidate(
            _cand("low", status=CandidateStatus.VERIFY),
            ReadAttempt(candidate_id="low", success=True, raw_value=5),
        )
        c2 = score_candidate(
            _cand("high", status=CandidateStatus.VERIFIED),
            ReadAttempt(candidate_id="high", success=True, raw_value=5),
        )
        best = pick_best([c1, c2])
        assert best is not None
        self.assertEqual("high", best.candidate.id)


if __name__ == "__main__":
    unittest.main()
