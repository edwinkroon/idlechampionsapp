"""Tests for Briv stack merge across resets."""

from __future__ import annotations

import unittest

from ic_gamedata.dashboard_enrich import _merge_optional_briv_stacks


class BrivStackMergeTests(unittest.TestCase):
    def test_keeps_higher_during_run(self) -> None:
        self.assertEqual(
            _merge_optional_briv_stacks(100, 500, tracked_area=200, api_area=210),
            500,
        )

    def test_resets_on_area_drop(self) -> None:
        self.assertEqual(
            _merge_optional_briv_stacks(48, 5_000_000, tracked_area=300, api_area=12),
            48,
        )


if __name__ == "__main__":
    unittest.main()
