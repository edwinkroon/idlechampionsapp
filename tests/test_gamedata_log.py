"""Tests for webRequestLog parsing."""

from __future__ import annotations

import unittest

from ic_gamedata.log_parser import parse_web_request_log, snapshot_from_payload


SAMPLE_BLOCK = """
https://pslt3.idlechampions.com/~idledragons/post.php?call=getuserdetails&user_id=1
{"success":true,"details":{"current_area":485,"gold":"1.5e20","stats":{"gold_gained":"2.5e25","this_reset_gems_earned":"187","this_reset_monster_kills":"1200","boss_kills":"40"}}}
"""


class LogParserTests(unittest.TestCase):
    def test_snapshot_from_payload(self) -> None:
        snap = snapshot_from_payload(
            {
                "details": {
                    "current_area": 10,
                    "gold": "100",
                    "stats": {"this_reset_gems_earned": "5", "gold_gained": "500"},
                }
            },
            api_call="getuserdetails",
        )
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.current_area, 10)
        self.assertEqual(snap.gems_this_reset, 5)
        self.assertEqual(snap.gold_gained, 500.0)

    def test_parse_web_request_log_block(self) -> None:
        snapshots = parse_web_request_log("*" * 50 + SAMPLE_BLOCK)
        self.assertEqual(len(snapshots), 1)
        snap = snapshots[0]
        self.assertEqual(snap.api_call, "getuserdetails")
        self.assertEqual(snap.current_area, 485)
        self.assertEqual(snap.gems_this_reset, 187)
        self.assertAlmostEqual(snap.gold or 0, 1.5e20)


if __name__ == "__main__":
    unittest.main()
