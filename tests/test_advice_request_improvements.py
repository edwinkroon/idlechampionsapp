"""Acceptance tests for ADVICE_REQUEST export mode."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export_clipboard import (
    AdviceRequestBudgetError,
    build_advice_request_clipboard_text,
    request_for_export,
)
from ic_gamedata.formation_ai_advice.export import gender_from_raw_tags
from ic_gamedata.formation_ai_advice.export_budget import DEFAULT_CHAR_BUDGET, count_chars
from ic_gamedata.formation_ai_advice.export_validation import (
    mark_request_unvalidated,
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION
from ic_gamedata.formation_ai_advice.reply_contract import (
    build_answer_contract,
)
from ic_gamedata.formation_ai_advice.schema import FORMATION_ADVICE_JSON_SCHEMA
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
    reconcile_snapshot_vs_request,
)
from ic_gamedata.formation_ai_advice.validate import parse_proposal_json
from ic_gamedata.party_advisor_models import FormationHero


def _hero(hero_id: int, name: str, seat: int) -> FormationHero:
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
        role_label="Dps",
        roles=("dps",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class ReplyContractTests(unittest.TestCase):
    def test_contract_matches_importer_schema(self) -> None:
        contract = build_answer_contract("req-abc")
        self.assertEqual(contract["schema_version"], SCHEMA_VERSION)
        self.assertEqual(contract["request_id_exact"], "req-abc")
        self.assertEqual(
            set(FORMATION_ADVICE_JSON_SCHEMA["required"]),
            set(contract["full_after_normalize"]["required_top_level"]),
        )
        self.assertEqual(
            list(FORMATION_ADVICE_JSON_SCHEMA["properties"]["status"]["enum"]),
            contract["full_after_normalize"]["status_enum"],
        )
        self.assertEqual(
            contract["semantics"]["completeness"],
            "volledige_party_geen_changes_only",
        )
        self.assertIn("structure_example", contract)
        self.assertIn("compact", contract)

    def test_min_example_validates_against_importer(self) -> None:
        contract = build_answer_contract(
            "req-import",
            party=[
                {"id": 3, "position": 1, "specialization_choices": []},
                {"id": 2, "position": 2, "specialization_choices": []},
            ],
            valid_position_ids=[1, 2],
        )
        example = dict(contract["structure_example"]["json"])
        proposal, errors = parse_proposal_json(
            json.dumps(example),
            expected_request_id="req-import",
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(proposal)
        assert proposal is not None
        self.assertEqual(proposal.request_id, "req-import")
        self.assertEqual(proposal.schema_version, SCHEMA_VERSION)


class AdviceRequestExportImprovementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.payload = json.loads(json.dumps(self.base_payload))
        self.formation = (
            _hero(21, "Birdsong", 9),
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(165, "Baldric", 4),
            _hero(172, "Kyre", 5),
            _hero(166, "Cazrin", 10),
            _hero(106, "Blooshi", 6),
            _hero(4, "Jarlaxle", 3),
            _hero(43, "Spurt", 7),
            _hero(113, "Egbert", 8),
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

    def _build(self, *, swap: bool = False, dex: int = 14) -> dict:
        owned = [
            int(h["hero_id"])
            for h in self.payload["details"]["heroes"]
            if h.get("owned") in ("1", 1, True)
        ]
        scores = {hid: {"dex": dex} for hid in owned}
        snap = build_base_snapshot(self.payload, formation=self.formation)
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            return build_advice_request(
                self.payload,
                self.formation,
                snapshot_id=snap["meta"]["snapshot_id"],
                snapshot_meta=snap["meta"],
                goal="push",
                fixed_main_dps_id=166,
                include_swap_scope=swap,
                base_snapshot=snap,
            ), snap

    def test_full_export_within_16k_with_warnings_and_full_party(self) -> None:
        # Inject adventure that denies low DEX → many warnings when dex low.
        defines = self.payload.setdefault("defines", {})
        adventures = list(defines.get("adventure_defines") or [])
        adventures.append(
            {
                "id": 909,
                "name": "Mountain",
                "restrictions_text": (
                    "Only Champions with a DEX score of 12 or higher can be used"
                ),
                "game_changes": [
                    {
                        "type": "disallow_crusaders",
                        "by_stat": {
                            "stats": [{"stat": "dex", "comp": "<", "value": 12}],
                        },
                    }
                ],
            }
        )
        defines["adventure_defines"] = adventures
        for inst in self.payload.get("details", {}).get("game_instances") or []:
            if isinstance(inst, dict):
                inst["current_adventure_id"] = 909

        for swap in (False, True):
            req, snap = self._build(swap=swap, dex=10)
            validation = validate_advice_request_export(
                payload=self.payload,
                request=req,
                snapshot_id=snap["meta"]["snapshot_id"],
                exported_snapshot_id=snap["meta"]["snapshot_id"],
            )
            labeled = mark_request_unvalidated(req, validation)
            text = build_advice_request_clipboard_text(labeled, mode="project")
            chars = count_chars(text)
            utf8 = len(text.encode("utf-8"))
            self.assertLessEqual(
                utf8,
                DEFAULT_CHAR_BUDGET,
                msg=f"swap={swap} utf8={utf8} chars={chars}",
            )
            self.assertIn("answer_contract", text)
            self.assertIn("snapshot_ref", text)

    def test_over_budget_raises_explicit_error_no_truncation(self) -> None:
        req, snap = self._build(swap=False)
        text = build_advice_request_clipboard_text(req, mode="project")
        tiny = max(100, count_chars(text) // 4)
        with self.assertRaises(AdviceRequestBudgetError) as ctx:
            build_advice_request_clipboard_text(
                req,
                mode="project",
                max_chars=tiny,
                raise_on_over_budget=True,
            )
        err = ctx.exception
        self.assertGreater(err.chars, tiny)
        self.assertEqual(err.max_chars, tiny)
        self.assertIn("te groot", str(err).casefold())
        # Original builder without raise still returns full intact JSON.
        again = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn("```json", again)
        # Last fenced block is the request body (earlier text must not use ```).
        start = again.rindex("```json") + len("```json")
        end = again.index("```", start)
        parsed = json.loads(again[start:end].strip())
        self.assertEqual(parsed.get("meta", {}).get("export_kind"), "advice_request")

    def test_snapshot_ref_filename_and_no_body(self) -> None:
        req, snap = self._build()
        ref = req["meta"]["snapshot_ref"]
        sid = snap["meta"]["snapshot_id"]
        self.assertEqual(ref["snapshot_id"], sid)
        # No registry save in this helper → filename unknown (not invented from id).
        self.assertIsNone(ref["expected_filename"])
        self.assertFalse(ref["contains_snapshot_body"])
        self.assertIn("mechanics_hash", ref)
        self.assertIn("account_state_hash", ref)
        safety = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn("bestand onbekend", safety.casefold())
        self.assertIn("bevat die inhoud niet", safety.casefold())
        self.assertNotIn(f"{sid}.json", safety)

    def test_display_position_not_confused_with_position_id(self) -> None:
        req, snap = self._build()
        self.assertEqual(
            snap["answer_contract"]["semantics"]["position_id"],
            "technisch_formatie_id_niet_display_niet_seat",
        )
        self.assertEqual(req["answer_contract"].get("ref"), "BASE_SNAPSHOT.answer_contract")
        self.assertEqual(req["geometry"].get("ref"), "BASE_SNAPSHOT.geometry")
        for pos in snap["geometry"]["positions"]:
            self.assertIn("id", pos)
            self.assertIn("display_position", pos)
            self.assertNotEqual(pos.get("display_position"), pos.get("id"))
        for occ in req["geometry"].get("occupied") or []:
            self.assertIn("id", occ)
            self.assertIn("champion_id", occ)
            self.assertNotIn("display_position", occ)
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn("display_position", text.casefold())
        self.assertIn("technische position_id", text.casefold())

    def test_missing_female_is_unknown_not_false(self) -> None:
        g = gender_from_raw_tags(["support", "bard"])
        self.assertEqual(g["status"], "unknown")
        self.assertIsNone(g["value"])
        self.assertIsNone(g["tag"])
        # Reconciliation: force unknown gender on a party id.
        party_state = [
            {
                "id": 172,
                "name": "Kyre",
                "specialization_choices": [],
            },
            {
                "id": 21,
                "name": "Birdsong",
                "specialization_choices": [
                    {"group_id": "tier_0", "selected_option_id": 1}
                ],
            },
        ]
        entries = {
            21: {
                "champion_id": 21,
                "gender": gender_from_raw_tags(["female", "bard"]),
                "specialization_groups": [
                    {
                        "group_id": "tier_0",
                        "options": [
                            {
                                "option_id": 1,
                                "name": "Soprano",
                                "effect_facts": {
                                    "semantics": {
                                        "scaling_population": {"tags": ["female"]}
                                    }
                                },
                            }
                        ],
                    }
                ],
            },
            172: {
                "champion_id": 172,
                "gender": gender_from_raw_tags(["support"]),
            },
        }
        result = reconcile_snapshot_vs_request(
            party_state=party_state,
            entries_by_id=entries,
            base_snapshot=None,
        )
        missing = result.get("missing_comparison_data") or []
        self.assertTrue(missing)
        self.assertIn(172, missing[0]["unknown_champion_ids"])
        self.assertFalse(missing[0]["blocks_other_formation_advice"])
        # Build request comparison_traits path with forced gender.
        req, snap = self._build()
        # Inject comparison_traits manually via rebuild helpers is heavy; assert
        # compact gender row semantics on the helper output shape.
        from ic_gamedata.formation_ai_advice.snapshot_export import (
            _build_comparison_traits,
            _compact_gender_row,
        )

        row = _compact_gender_row(gender_from_raw_tags(["support"]), champion_id=172)
        self.assertEqual(row["status"], "unknown")
        self.assertIsNone(row.get("tag"))
        self.assertNotEqual(row.get("tag"), False)
        traits = _build_comparison_traits(
            party_ids=[21, 172],
            gender_by_id={
                21: gender_from_raw_tags(["female"]),
                172: gender_from_raw_tags(["support"]),
            },
            reconciliation=result,
        )
        assert traits is not None
        by_id = {r["id"]: r for r in traits["gender"]}
        self.assertEqual(by_id[172]["status"], "unknown")
        self.assertIsNone(by_id[172].get("tag"))
        self.assertEqual(by_id[21]["status"], "known")
        self.assertEqual(by_id[21]["tag"], "female")

    def test_uggie_unknown_only_blocks_dependent_conclusions(self) -> None:
        req, _ = self._build()
        uggie = (req.get("companion_state") or {}).get("uggie")
        self.assertIsInstance(uggie, dict)
        self.assertEqual(uggie["observability"], "unknown")
        self.assertEqual(uggie.get("blocks_only"), "uggie_buff_coverage")
        uncertainty = req.get("uncertainty") or {}
        classes = {i["class"] for i in uncertainty.get("items") or []}
        self.assertIn("uggie_state_unknown", classes)
        # Must not mark whole advice blocked solely for Uggie.
        uggie_row = next(
            i for i in uncertainty["items"] if i["class"] == "uggie_state_unknown"
        )
        self.assertFalse(uggie_row["blocks_advice"])

    def test_expected_overrides_not_reported_as_conflicts(self) -> None:
        req, snap = self._build()
        # Force selection change vs snapshot.
        if not req["party"]:
            self.skipTest("empty party")
        party0 = req["party"][0]
        choices = list(party0.get("specialization_choices") or [])
        if not choices:
            choices = [{"group_id": "tier_0", "selected_option_id": 999001}]
        else:
            choices[0] = {
                **choices[0],
                "selected_option_id": 999001,
                "selection_status": "selected",
            }
        party0["specialization_choices"] = choices
        # Rebuild reconciliation directly.
        entries = {
            int(p["id"]): {
                "champion_id": int(p["id"]),
                "specialization_groups": [
                    {
                        "group_id": "tier_0",
                        "options": [{"option_id": 999001}, {"option_id": 1}],
                    }
                ],
            }
            for p in req["party"]
        }
        # Put old selection in snapshot.
        base = {
            "champions": [
                {
                    "id": int(party0["id"]),
                    "specializations": [
                        {
                            "group_id": "tier_0",
                            "selected_option_id": 1,
                            "selection_status": "selected",
                            "options": [{"option_id": 1}, {"option_id": 999001}],
                        }
                    ],
                }
            ]
        }
        result = reconcile_snapshot_vs_request(
            party_state=req["party"],
            entries_by_id=entries,
            base_snapshot=base,
        )
        overrides = result.get("expected_state_overrides") or []
        self.assertTrue(
            any(o.get("code") == "selection_changed" for o in overrides)
            or overrides,
        )
        for conflict in result.get("material_source_conflicts") or []:
            self.assertNotEqual(conflict.get("kind"), "expected_state_override")

    def test_optional_live_state_unknown_does_not_block_all_advice(self) -> None:
        req, _ = self._build()
        for member in req["party"]:
            live = member.get("live_state") or {}
            self.assertIn(live.get("status"), ("unknown", "known"))
        uncertainty = req.get("uncertainty") or {}
        live_row = next(
            i for i in uncertainty["items"] if i["class"] == "live_state_unknown"
        )
        self.assertFalse(live_row["blocks_advice"])

    def test_placement_dependent_traits_marked(self) -> None:
        req, _ = self._build()
        # When trait_delta present, must mark recompute.
        for member in req["party"]:
            delta = member.get("trait_delta_vs_base")
            if not delta:
                continue
            self.assertEqual(
                delta.get("placement_dependent_buffs"),
                "recompute_on_proposed_formation",
            )
            self.assertEqual(delta.get("applies_to"), "current_formation")

    def test_clipboard_keeps_required_fields(self) -> None:
        req, _ = self._build()
        compact = request_for_export(req)
        self.assertIn("answer_contract", compact)
        self.assertNotIn("reply_contract", compact)
        self.assertIn("geometry", compact)
        self.assertIn("party", compact)
        self.assertIn("constraints", compact)
        ref = compact["meta"]["snapshot_ref"]
        self.assertIn("snapshot_id", ref)
        self.assertIn("mechanics_hash", ref)
        self.assertIn("account_state_hash", ref)
        self.assertIn("expected_filename", ref)


if __name__ == "__main__":
    unittest.main()
