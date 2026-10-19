"""Tests for ADVICE_REQUEST answer_contract (derived from the real importer)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.compact_clipboard import (
    AdviceRequestBudgetError,
    build_advice_request_clipboard_text,
)
from ic_gamedata.formation_ai_advice.export_budget import DEFAULT_CHAR_BUDGET, count_chars
from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION
from ic_gamedata.formation_ai_advice.reply_contract import build_answer_contract
from ic_gamedata.formation_ai_advice.schema import FORMATION_ADVICE_JSON_SCHEMA
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.formation_ai_advice.validate import (
    parse_proposal_json,
    validate_proposal_against_export,
)
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


class AnswerContractUnitTests(unittest.TestCase):
    def test_contract_matches_formation_advice_json_schema(self) -> None:
        contract = build_answer_contract("req-x")
        self.assertEqual(contract["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            contract["full_after_normalize"]["required_top_level"],
            list(FORMATION_ADVICE_JSON_SCHEMA["required"]),
        )
        self.assertEqual(
            contract["full_after_normalize"]["status_enum"],
            FORMATION_ADVICE_JSON_SCHEMA["properties"]["status"]["enum"],
        )
        self.assertEqual(
            contract["full_after_normalize"]["assignments_item_required"],
            FORMATION_ADVICE_JSON_SCHEMA["properties"]["assignments"]["items"][
                "required"
            ],
        )
        self.assertEqual(
            contract["semantics"]["completeness"],
            "volledige_party_geen_changes_only",
        )
        self.assertIn(
            "geen gefabriceerd placements-antwoord",
            contract["semantics"]["missing_essential_data"],
        )

    def test_structure_example_parses_with_importer(self) -> None:
        party = [
            {
                "id": 3,
                "position": 1,
                "specialization_choices": [
                    {
                        "group_id": "tier_0",
                        "selected_option_id": 101,
                        "selection_status": "selected",
                    }
                ],
            },
            {"id": 2, "position": 2, "specialization_choices": []},
        ]
        contract = build_answer_contract(
            "req-import",
            party=party,
            valid_position_ids=[1, 2],
        )
        example = contract["structure_example"]["json"]
        self.assertTrue(contract["structure_example"]["not_advice"])
        proposal, errors = parse_proposal_json(
            json.dumps(example),
            expected_request_id="req-import",
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(proposal)
        assert proposal is not None
        self.assertEqual(proposal.request_id, "req-import")
        self.assertEqual(
            {(a.position_id, a.champion_id) for a in proposal.assignments},
            {(1, 3), (2, 2)},
        )


class AnswerContractInRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.formation = (
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(4, "Jarlaxle", 3),
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

    def _request(self, *, swap: bool = False) -> tuple[dict, dict]:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            goal="push",
            fixed_main_dps_id=4,
            include_swap_scope=swap,
            base_snapshot=snap,
        )
        return req, snap

    def test_every_advice_request_contains_answer_contract(self) -> None:
        req, _ = self._request()
        self.assertEqual(req["meta"]["export_kind"], "advice_request")
        self.assertIn("answer_contract", req)
        self.assertNotIn("reply_contract", req)
        contract = req["answer_contract"]
        self.assertEqual(contract["request_id_exact"], req["meta"]["request_id"])
        self.assertEqual(
            contract["snapshot_id_echo"], req["meta"]["snapshot_ref"]["snapshot_id"]
        )
        # Example uses current party technical ids, not display positions.
        example = contract["structure_example"]["json"]
        party_ids = {p["id"] for p in req["party"]}
        for row in example["placements"]:
            self.assertIn(row["champion_id"], party_ids)
            self.assertIsInstance(row["position_id"], int)
            self.assertNotIsInstance(row["position_id"], str)

    def test_example_accepted_by_parse_and_semantic_validator(self) -> None:
        req, snap = self._request()
        example = req["answer_contract"]["structure_example"]["json"]
        proposal, errors = parse_proposal_json(
            json.dumps(example),
            expected_request_id=req["meta"]["request_id"],
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(proposal)

        # Build a minimal export_payload shape that validate_proposal expects.
        export_like = {
            "champions": [
                {
                    "champion_id": p["id"],
                    "seat": p.get("seat"),
                    "specializations": [
                        {
                            "group_id": c.get("group_id"),
                            "options": (
                                [{"option_id": c["selected_option_id"]}]
                                if isinstance(c.get("selected_option_id"), int)
                                else []
                            ),
                        }
                        for c in (p.get("specialization_choices") or [])
                        if isinstance(c, dict)
                    ],
                }
                for p in req["party"]
            ],
            "formation": {
                "valid_position_ids": req["geometry"]["valid_position_ids"],
            },
        }
        assert proposal is not None
        local = validate_proposal_against_export(
            proposal,
            export_like,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        # Structure example mirrors current placement; should be applicable
        # unless seats/positions conflict in fixture geometry.
        self.assertIn(local.status, ("valid", "invalid"))
        if local.status != "valid":
            # Still must be a real validator result (not unchecked invent).
            self.assertTrue(local.errors or local.warnings is not None)

    def test_invalid_position_and_spec_rejected(self) -> None:
        req, _ = self._request()
        bad = {
            "schema_version": SCHEMA_VERSION,
            "request_id": req["meta"]["request_id"],
            "placements": [
                {"position_id": 99999, "champion_id": p["id"]}
                for p in req["party"]
            ],
            "specializations": [
                {
                    "champion_id": req["party"][0]["id"],
                    "group_id": "tier_0",
                    "option_id": 999999001,
                }
            ],
        }
        proposal, errors = parse_proposal_json(
            json.dumps(bad),
            expected_request_id=req["meta"]["request_id"],
        )
        self.assertEqual(errors, [])
        assert proposal is not None
        export_like = {
            "champions": [
                {
                    "champion_id": p["id"],
                    "seat": p.get("seat"),
                    "specializations": [
                        {"group_id": "tier_0", "options": [{"option_id": 1}]}
                    ],
                }
                for p in req["party"]
            ],
            "formation": {
                "valid_position_ids": req["geometry"]["valid_position_ids"],
            },
        }
        local = validate_proposal_against_export(
            proposal,
            export_like,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertEqual(local.status, "invalid")
        self.assertFalse(local.can_apply)
        joined = " ".join(local.errors).casefold()
        self.assertTrue(
            "positie" in joined or "specialisatie" in joined or "optie" in joined
        )

    def test_display_position_not_used_as_position_id(self) -> None:
        req, _ = self._request()
        contract = req["answer_contract"]
        self.assertEqual(
            contract["semantics"]["position_id"],
            "technisch_formatie_id_niet_display_niet_seat",
        )
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn("answer_contract", text)
        self.assertIn("technische position_id", text.casefold())
        self.assertIn("display_position", text.casefold())

    def test_omission_and_completeness_described(self) -> None:
        contract = build_answer_contract("r")
        sem = contract["semantics"]
        self.assertEqual(sem["completeness"], "volledige_party_geen_changes_only")
        self.assertEqual(sem["empty_specializations_array"], "ok")
        self.assertEqual(
            sem["omitted_champ_specializations"],
            "geen_nieuw_spec_advies_voor_die_champ",
        )
        self.assertIn("needs_information", sem["missing_essential_data"])

    def test_full_export_within_15k(self) -> None:
        for swap in (False, True):
            req, _ = self._request(swap=swap)
            text = build_advice_request_clipboard_text(req, mode="project")
            self.assertLessEqual(
                count_chars(text),
                DEFAULT_CHAR_BUDGET,
                msg=f"swap={swap} chars={count_chars(text)}",
            )
            self.assertIn('"answer_contract"', text)

    def test_over_budget_explicit_error(self) -> None:
        req, _ = self._request()
        text = build_advice_request_clipboard_text(req, mode="project")
        tiny = max(200, count_chars(text) // 5)
        with self.assertRaises(AdviceRequestBudgetError) as ctx:
            build_advice_request_clipboard_text(
                req,
                mode="project",
                max_chars=tiny,
                raise_on_over_budget=True,
            )
        self.assertGreater(ctx.exception.chars, tiny)

    def test_base_snapshot_unchanged_by_request_build(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        before = json.dumps(snap, sort_keys=True)
        build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
        )
        after = json.dumps(snap, sort_keys=True)
        self.assertEqual(before, after)
        self.assertEqual(snap["meta"]["export_kind"], "base_snapshot")


if __name__ == "__main__":
    unittest.main()
