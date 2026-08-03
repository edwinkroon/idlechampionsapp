"""Tests for relative BUD proxy (MVP)."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from ic_gamedata.bud_proxy import (
    bud_proxy_ratio,
    estimate_bud_proxy,
    format_bud_ratio,
    score_boost_from_ratio,
)


@dataclass(frozen=True)
class _H:
    hero_id: int
    name: str
    seat: int | None
    roles: tuple[str, ...]
    tags: tuple[str, ...]
    gear_score: float = 100.0
    ilvl: int = 100
    highest_damage: float = 0.0
    is_top_damage: bool = False


class BudProxyTests(unittest.TestCase):
    def test_empty_party(self) -> None:
        out = estimate_bud_proxy(())
        self.assertEqual(out.total, 0.0)

    def test_debuffer_raises_proxy(self) -> None:
        carry = _H(1, "Azaka", 9, ("dps",), (), highest_damage=1e12, is_top_damage=True)
        tank = _H(2, "Bruenor", 1, ("tank", "support"), ("buffer",))
        before = estimate_bud_proxy((carry, tank))
        after = estimate_bud_proxy(
            (
                carry,
                tank,
                _H(3, "Spurt", 3, ("support",), ("debuffer", "bud")),
            )
        )
        self.assertGreater(bud_proxy_ratio(before, after), 1.5)

    def test_adjacent_buffer_beats_far_buffer(self) -> None:
        carry = _H(1, "Azaka", 9, ("dps",), (), highest_damage=1e12, is_top_damage=True)
        # Seat 6 is adjacent to 9; seat 1 is not.
        adj_buffer = _H(2, "Near", 6, ("support",), ("buffer",))
        far_buffer = _H(3, "Far", 1, ("support",), ("buffer",))
        near = estimate_bud_proxy((carry, adj_buffer))
        far = estimate_bud_proxy((carry, far_buffer))
        self.assertGreater(near.total, far.total)

    def test_format_and_boost(self) -> None:
        self.assertIn("×", format_bud_ratio(1.4))
        self.assertEqual(format_bud_ratio(1.0), "geen winst")
        self.assertGreater(score_boost_from_ratio(2.0), 0)
        self.assertLess(score_boost_from_ratio(0.5), 0)

    def test_higher_ilvl_buffer_does_not_inflate_proxy(self) -> None:
        """Support ilvl must not invent large BUD gains (Omin/Nayeli lesson)."""
        carry = _H(1, "Azaka", 9, ("dps",), (), highest_damage=1e12, is_top_damage=True)
        weak = _H(2, "Omin", 3, ("support", "healer"), ("gold", "buffer"), ilvl=7, gear_score=7)
        strong = _H(3, "Nayeli", 3, ("tank", "support"), ("buffer",), ilvl=1462, gear_score=1462)
        before = estimate_bud_proxy((carry, weak))
        after = estimate_bud_proxy((carry, strong))
        ratio = bud_proxy_ratio(before, after)
        # Tank presence may nudge slightly; must not look like a ×3 upgrade.
        self.assertLess(ratio, 1.25)

    def test_live_instrument_gear_score_ignored_for_ilvl(self) -> None:
        """Inflated formation gear_score must not drive support weighting."""
        carry = _H(1, "Azaka", 9, ("dps",), (), highest_damage=1e261, is_top_damage=True)
        halsin = _H(
            156,
            "Halsin",
            3,
            ("support", "healer"),
            ("speed", "buffer"),
            ilvl=9,
            gear_score=1e40,
        )
        nayeli = _H(
            3,
            "Nayeli",
            3,
            ("tank", "support"),
            ("buffer",),
            ilvl=1462,
            gear_score=1462,
        )
        before = estimate_bud_proxy((carry, halsin))
        after = estimate_bud_proxy((carry, nayeli))
        # Same buffer presence → roughly flat (tank nudge only).
        self.assertLess(bud_proxy_ratio(before, after), 1.25)





if __name__ == "__main__":
    unittest.main()
