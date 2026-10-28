"""ADVICE_REQUEST live-state fields: level, feats, BUD, buffs, UTF-8 budget."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export_budget import (
    DEFAULT_CHAR_BUDGET,
    count_chars,
    count_utf8_bytes,
)
from ic_gamedata.formation_ai_advice.export_clipboard import (
    AdviceRequestBudgetError,
    build_advice_request_clipboard_text,
    evaluate_clipboard_budget,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    SNAPSHOT_EXPORT_SCHEMA,
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.party_advisor_models import FormationHero


def _hero(
    hero_id: int,
    name: str,
    seat: int,
    *,
    level: int = 100,
    is_top_damage: bool = False,
) -> FormationHero:
    return FormationHero(
        hero_id=hero_id,
        name=name,
        seat=seat,
        level=level,
        gear_score=100.0,
        ilvl=100,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label="ilvl 100",
        role_label="Dps",
        roles=("dps",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=is_top_damage,
    )


class AdviceRequestLiveStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.payload = json.loads(json.dumps(self.base_payload))
        self.formation = (
            _hero(3, "Nayeli", 1, level=220),
            _hero(2, "Celeste", 2, level=180),
            _hero(4, "Jarlaxle", 3, level=250, is_top_damage=True),
        )
        self._tmpdir = tempfile.TemporaryDirectory()
        cache_path = Path(self._tmpdir.name) / "owned_roster_cache.json"
        self._cache_patch = patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
            cache_path,
        )
        self._cache_patch.start()

    def tearDown(self) -> None:
        self._cache_patch.stop()
        self._tmpdir.cleanup()

    def _request(self, **kwargs):
        snap = build_base_snapshot(self.payload, formation=self.formation)
        defaults = dict(
            payload=self.payload,
            formation=self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
            goal="push",
            fixed_main_dps_id=4,
        )
        defaults.update(kwargs)
        return build_advice_request(**defaults), snap

    def test_export_schema_bumped(self) -> None:
        req, _ = self._request()
        self.assertEqual(req["meta"]["export_schema_version"], SNAPSHOT_EXPORT_SCHEMA)
        self.assertEqual(SNAPSHOT_EXPORT_SCHEMA, "1.4")

    def test_party_level_and_active_feat_ids(self) -> None:
        # Fixture heroes often have level "0"; prefer payload when present,
        # otherwise formation level.
        for hero in self.payload["details"]["heroes"]:
            if not isinstance(hero, dict):
                continue
            if int(hero.get("hero_id") or 0) == 4:
                hero["level"] = "333"
                hero["active_feats"] = [101, 202]
        req, _ = self._request()
        by_id = {p["id"]: p for p in req["party"]}
        self.assertEqual(by_id[4]["level"], 333)
        self.assertIn(3, by_id)
        self.assertIsInstance(by_id[4].get("active_feat_ids"), list)
        self.assertEqual(by_id[4]["active_feat_ids"], [101, 202])

    def test_non_swap_locked_for_fixed_main_dps(self) -> None:
        req, _ = self._request(fixed_main_dps_id=4, locked_champion_ids=[3])
        by_id = {p["id"]: p for p in req["party"]}
        self.assertTrue(by_id[4]["locked"])
        self.assertEqual(by_id[4]["lock_reason"], "fixed_main_dps")
        self.assertTrue(by_id[3]["locked"])
        self.assertEqual(by_id[3]["lock_reason"], "user_lock")
        # Required ≠ position lock: Celeste unlocked without explicit lock.
        self.assertNotEqual(by_id[2].get("locked"), True)

    def test_bud_observation_unknown_when_no_setter(self) -> None:
        req, _ = self._request()
        bud = req["bud_observation"]
        self.assertEqual(bud["reset_highest_damage_status"], "unknown")
        self.assertIsNone(bud.get("reset_highest_damage_champion_id"))
        self.assertEqual(bud["current_bud_setter_status"], "unknown")
        self.assertEqual(bud["peak"]["status"], "unknown")
        self.assertEqual(bud["peak"]["reason_code"], "no_bud_poll_loop")
        self.assertEqual(bud["current_bud"]["status"], "unknown")
        # unknown is not silently 0
        self.assertNotEqual(bud["current_bud"].get("value"), 0)
        self.assertNotEqual(bud["peak"].get("value"), 0)

    def test_bud_observation_known_reset_highest(self) -> None:
        for inst in self.payload["details"]["game_instances"]:
            if not isinstance(inst, dict):
                continue
            stats = inst.setdefault("stats", {})
            stats["this_reset_highest_damage_dealt_hero_id"] = "4"
        req, _ = self._request()
        bud = req["bud_observation"]
        self.assertEqual(bud["reset_highest_damage_status"], "known")
        self.assertEqual(bud["reset_highest_damage_champion_id"], 4)
        self.assertEqual(bud["current_bud_setter_status"], "unknown")
        self.assertIn("this_reset_highest_damage_dealt_hero_id", bud["observation_source"])
        self.assertEqual(bud["peak"]["reason_code"], "no_bud_poll_loop")

    def test_main_dps_buffs_computed_basis(self) -> None:
        req, _ = self._request(fixed_main_dps_id=4)
        buffs = req.get("main_dps_buffs")
        self.assertIsInstance(buffs, dict)
        self.assertEqual(buffs["fixed_main_dps_id"], 4)
        self.assertEqual(buffs.get("reach_basis_default"), "computed")
        self.assertEqual(buffs.get("activation_basis_default"), "unknown")
        completeness = buffs["completeness"]
        self.assertIn("unique_effects_examined", completeness)
        self.assertIn("unknown_magnitude_count", completeness)
        self.assertIn("raw_rows_examined", completeness)
        for row in buffs.get("effects") or []:
            if "refs" in row:
                # Budget-grouped unknown bucket
                continue
            self.assertIn(row.get("reach"), ("in_range", "out_of_range", "unknown"))
            self.assertEqual(row.get("activation"), "unknown")
            self.assertIn("src", row)
            self.assertNotIn("value", row)

    def test_no_main_dps_buffs_without_fixed_dps(self) -> None:
        req, _ = self._request(fixed_main_dps_id=None)
        self.assertIsNone(req.get("main_dps_buffs"))

    def test_clipboard_utf8_budget_and_non_ascii(self) -> None:
        req, _ = self._request()
        text = build_advice_request_clipboard_text(req, mode="project")
        utf8 = count_utf8_bytes(text)
        chars = count_chars(text)
        self.assertLessEqual(utf8, DEFAULT_CHAR_BUDGET)
        self.assertGreaterEqual(utf8, chars)  # Dutch copy has multi-byte chars
        info = evaluate_clipboard_budget(text, max_chars=DEFAULT_CHAR_BUDGET)
        self.assertTrue(info["within_budget"])
        self.assertEqual(info["utf8_bytes"], utf8)
        # Non-ASCII smoke: gate uses bytes, not code points alone.
        padded = text + ("é" * 50)
        smoke = evaluate_clipboard_budget(padded, max_chars=count_utf8_bytes(padded))
        self.assertTrue(smoke["within_budget"])
        self.assertGreater(smoke["utf8_bytes"], smoke["chars"])

    def test_over_budget_reports_utf8_bytes(self) -> None:
        req, _ = self._request()
        text = build_advice_request_clipboard_text(req, mode="project")
        tiny = max(200, count_utf8_bytes(text) // 5)
        with self.assertRaises(AdviceRequestBudgetError) as ctx:
            build_advice_request_clipboard_text(
                req,
                mode="project",
                max_chars=tiny,
                raise_on_over_budget=True,
            )
        err = ctx.exception
        self.assertGreater(err.utf8_bytes, tiny)
        self.assertIn("utf-8", str(err).casefold())

    def test_answer_contract_still_present(self) -> None:
        req, _ = self._request()
        self.assertIn("answer_contract", req)
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn("answer_contract", text)
        self.assertIn('"export_kind":"advice_request"', text.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
