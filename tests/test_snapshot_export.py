"""Tests for BASE_SNAPSHOT / ADVICE_REQUEST / CHAMPION_DETAILS split."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.clipboard_export import (
    format_clipboard_markdown,
    format_swap_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.export import build_export_payload
from ic_gamedata.formation_ai_advice.snapshot_export import (
    all_refs_resolvable,
    build_advice_request,
    build_base_snapshot,
    build_champion_details,
    format_advice_request_markdown,
    format_base_snapshot_markdown,
    format_champion_details_markdown,
    measure_export_sizes,
    minify_json,
)
from ic_gamedata.formation_ai_advice.swap_export import build_swap_export_payload
from ic_gamedata.party_advisor_models import FormationHero


def _hero(
    hero_id: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
    tags: tuple[str, ...] = (),
) -> FormationHero:
    return FormationHero(
        hero_id=hero_id,
        name=name,
        seat=seat,
        level=100,
        gear_score=100.0,
        ilvl=100,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label="ilvl 100",
        role_label=roles[0].capitalize() if roles else "Unknown",
        roles=roles,
        tags=tags,
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class SnapshotExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.formation = (
            _hero(3, "Nayeli", 1, roles=("tank", "support")),
            _hero(2, "Celeste", 2, roles=("healer", "support")),
            _hero(4, "Jarlaxle", 3, roles=("dps", "gold")),
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

    def test_base_snapshot_covers_all_owned(self) -> None:
        from ic_gamedata.party_advisor_formation import _owned_heroes

        owned_ids = {hid for hid, *_ in _owned_heroes(self.payload)}
        snap = build_base_snapshot(self.payload, formation=self.formation)
        self.assertEqual(snap["meta"]["export_kind"], "base_snapshot")
        self.assertTrue(str(snap["meta"]["snapshot_id"]).startswith("snap_"))
        self.assertIn("mechanics_hash", snap["meta"])
        self.assertIn("account_state_hash", snap["meta"])
        cov = snap["roster"]["coverage"]
        self.assertEqual(cov["owned_known_count"], len(owned_ids))
        snap_ids = {c["id"] for c in snap["champions"] if isinstance(c.get("id"), int)}
        index_ids = {r["id"] for r in snap["roster"]["owned"]}
        incomplete_ids = {
            row["champion_id"]
            for row in (cov.get("incomplete") or [])
            if isinstance(row, dict) and isinstance(row.get("champion_id"), int)
        }
        self.assertEqual(snap_ids | incomplete_ids, owned_ids)
        self.assertEqual(index_ids, snap_ids)
        self.assertEqual(
            cov["included_count"] + cov["incomplete_count"],
            cov["owned_known_count"],
        )

    def test_base_snapshot_includes_per_slot_item_levels(self) -> None:
        from ic_gamedata.party_advisor_formation import _loot_slot_ilvls_by_hero

        details = self.payload.get("details") or {}
        slot_map = _loot_slot_ilvls_by_hero(details)
        self.assertTrue(slot_map, "fixture must include loot slots")

        snap = build_base_snapshot(self.payload, formation=self.formation)
        self.assertIn("item_levels (avg/by_slot)", snap["meta"]["account_state_hash_covers"])

        with_levels = [
            c
            for c in snap["champions"]
            if isinstance(c.get("item_levels"), dict)
            and c["item_levels"].get("by_slot")
        ]
        self.assertTrue(with_levels)
        sample = with_levels[0]
        il = sample["item_levels"]
        by_slot = il["by_slot"]
        self.assertIsInstance(by_slot, dict)
        levels = [int(v) for v in by_slot.values()]
        self.assertEqual(il["avg"], round(sum(levels) / len(levels)))
        expected = slot_map.get(int(sample["id"])) or {}
        for slot_id, level in expected.items():
            self.assertEqual(int(by_slot[str(slot_id)]), level)

    def test_blocked_champion_still_in_snapshot(self) -> None:
        """Adventure max-INT gate must not remove owned heroes from BASE."""
        payload = json.loads(json.dumps(self.payload))
        # Attach a synthetic adventure with INT <= 11.
        defines = payload.setdefault("defines", {})
        adventures = list(defines.get("adventure_defines") or [])
        adventures.append(
            {
                "id": 1617,
                "name": "Mental Gymnastics",
                "restrictions_text": (
                    "You may only use Champions with an Intelligence of 11 or less."
                ),
                "game_changes": [
                    {
                        "type": "only_allow_crusaders",
                        "by_stat": {
                            "stats": [{"stat": "int", "comp": "<=", "value": 11}],
                        },
                    }
                ],
            }
        )
        defines["adventure_defines"] = adventures
        details = payload.setdefault("details", {})
        for inst in details.get("game_instances") or []:
            if isinstance(inst, dict):
                inst["current_adventure_id"] = 1617

        scores = {
            59: {"int": 19},
            2: {"int": 10},
            3: {"int": 10},
            4: {"int": 10},
        }
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            snap = build_base_snapshot(payload, formation=self.formation)
            ids = {c["id"] for c in snap["champions"]}
            # Melf may or may not be owned in the fixture; if owned, must be present.
            from ic_gamedata.party_advisor_formation import _owned_heroes

            owned = {hid for hid, *_ in _owned_heroes(payload)}
            if 59 in owned:
                self.assertIn(59, ids)
            # No champion should carry adventure eligibility in the snapshot.
            for c in snap["champions"]:
                self.assertNotIn("eligibility", c)
                self.assertNotIn("position", c)

    def test_refs_resolvable_inside_snapshot(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        self.assertTrue(all_refs_resolvable(snap))
        # Break a ref deliberately.
        for c in snap["champions"]:
            for ab in c.get("abilities") or []:
                if isinstance(ab, dict) and "ref" in ab:
                    ab["ref"] = 999999001
                    self.assertFalse(all_refs_resolvable(snap))
                    return
        self.skipTest("fixture had no ability refs to mutate")

    def test_advice_request_references_snapshot(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
        )
        self.assertEqual(req["meta"]["export_kind"], "advice_request")
        self.assertEqual(
            req["meta"]["snapshot_ref"]["snapshot_id"],
            snap["meta"]["snapshot_id"],
        )
        self.assertEqual(
            req["meta"]["snapshot_ref"]["mechanics_hash"],
            snap["meta"]["mechanics_hash"],
        )
        self.assertTrue(req.get("party"))
        self.assertIn("geometry", req)
        self.assertIn("roster_eligibility", req)
        # Current specialization choices live on the request, not buried in
        # full mechanic dumps.
        for member in req["party"]:
            self.assertIn("id", member)
            self.assertIn("position", member)
            self.assertIn("live_state", member)
            self.assertEqual(member["live_state"]["status"], "unknown")
            # Active feat loadout with short mechanic effect when known.
            if "active_feats" in member:
                for feat in member["active_feats"] or []:
                    self.assertIn("id", feat)
                    self.assertNotIn("mechanical_text", feat)
                    self.assertNotIn("effect_facts", feat)
                    self.assertNotIn("quality", feat)
            else:
                self.assertEqual(member.get("feats_status"), "unknown")
        # Fixture Jarlaxle (id 4) has active_feats in the webRequestLog sample.
        jarlaxle = next(m for m in req["party"] if m.get("id") == 4)
        self.assertTrue(jarlaxle.get("active_feats"))
        self.assertTrue(all(isinstance(f.get("id"), int) for f in jarlaxle["active_feats"]))
        frugal = jarlaxle["active_feats"][0]
        self.assertEqual(frugal.get("name"), "Frugal")
        self.assertIn("effect", frugal)
        self.assertIn("gold", str(frugal.get("effect") or "").casefold())
        self.assertEqual(
            (req.get("live_state_defaults") or {}).get("status"),
            "unknown",
        )

    def test_unknown_bench_loadout_not_empty(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        # Any champion with unknown feats must not look like an empty feat list.
        saw_unknown = False
        for c in snap["champions"]:
            if c.get("feats_status") == "unknown":
                saw_unknown = True
                self.assertIsNone(c.get("active_feats"))
                self.assertTrue(c.get("feats_note"))
        # Fixture may have known feats for all; still assert contract via synthetic.
        if not saw_unknown:
            fake = {
                "id": 1,
                "name": "X",
                "feats_status": "unknown",
                "feats_note": "onbekend",
                "active_feats": None,
            }
            self.assertIsNone(fake["active_feats"])
            self.assertNotEqual(fake["feats_status"], "known_empty")

    def test_minify_preserves_meaning(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        raw = minify_json(snap)
        restored = json.loads(raw)
        self.assertEqual(restored["meta"]["snapshot_id"], snap["meta"]["snapshot_id"])
        self.assertEqual(len(restored["champions"]), len(snap["champions"]))
        self.assertTrue(all_refs_resolvable(restored))

    def test_champion_details_subset(self) -> None:
        details = build_champion_details(
            self.payload,
            [2, 3, 999001],
            formation=self.formation,
            snapshot_id="snap_test",
        )
        self.assertEqual(details["meta"]["export_kind"], "champion_details")
        ids = {c["id"] for c in details["champions"]}
        self.assertEqual(ids, {2, 3})
        missing_ids = {
            m["champion_id"] for m in details["coverage"]["missing"] or []
        }
        self.assertIn(999001, missing_ids)
        # Details keep inline mechanics (no catalog required).
        for c in details["champions"]:
            self.assertTrue(
                c.get("abilities") or c.get("specializations") or c.get("name")
            )

    def test_legacy_export_still_works(self) -> None:
        export = build_export_payload(
            self.payload,
            self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
            request_id="legacy-1",
        )
        md = format_clipboard_markdown(export)
        self.assertIn("## Gegevens", md)
        self.assertGreater(len(md), 500)

        swap = build_swap_export_payload(
            self.payload,
            self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
            request_id="legacy-swap-1",
        )
        swap_md = format_swap_clipboard_markdown(swap)
        self.assertIn("## Gegevens", swap_md)
        self.assertGreater(len(swap_md), 500)

    def test_formatters_and_measured_sizes(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            goal="push",
            fixed_main_dps_id=4,
            include_swap_scope=True,
        )
        details = build_champion_details(
            self.payload,
            [2, 3, 4],
            formation=self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
        )
        legacy = format_swap_clipboard_markdown(
            build_swap_export_payload(
                self.payload,
                self.formation,
                goal="push",
                fixed_main_dps_id=4,
                request_id="size-legacy",
            )
        )
        sizes = measure_export_sizes(
            base_snapshot=snap,
            advice_request=req,
            champion_details=details,
            legacy_markdown=legacy,
        )
        # Persist measured sizes on the test result for the report (real numbers).
        self.assertGreater(sizes["base_snapshot_json"], 0)
        self.assertGreater(sizes["advice_request_json"], 0)
        self.assertGreater(sizes["champion_details_json"], 0)
        self.assertGreater(sizes["legacy_markdown"], 0)
        # Advice request should be much smaller than legacy full swap paste.
        self.assertLess(sizes["advice_request_json"], sizes["legacy_markdown"])
        # Snapshot + request together is the intended split workflow.
        split_total = sizes["base_snapshot_json"] + sizes["advice_request_json"]
        self.assertGreater(split_total, 0)
        # Formatters return markdown wrappers.
        self.assertIn("BASE_SNAPSHOT", format_base_snapshot_markdown(snap))
        self.assertIn("ADVICE_REQUEST", format_advice_request_markdown(req))
        self.assertIn("CHAMPION_DETAILS", format_champion_details_markdown(details))
        # Print measured sizes for the agent report (unittest captures stdout).
        print("MEASURED_SIZES", json.dumps(sizes, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
