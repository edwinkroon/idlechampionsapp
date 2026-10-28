"""Regression: presence ≠ eligibility; export fields stay mutually consistent.

Covers the Volo/Vajra-style conflict class without hardcoding that adventure:
a seated champion who fails static restrictions must not be exported as
unconditional allowed, and validation/readiness must not claim party_ok.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
    evaluate_heroes_against_filter,
    is_hero_allowed,
)
from ic_gamedata.formation_ai_advice.export_validation import (
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.mechanics import evaluate_restriction_overrides
from ic_gamedata.formation_ai_advice.snapshot_export import (
    _compact_eligibility_table,
    _eligibility_presence_conflicts,
    build_advice_request,
    build_base_snapshot,
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
        role_label="Support",
        roles=("support",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


def _denied_ids(elig: dict) -> set[int]:
    out: set[int] = set()
    for row in elig.get("denied") or []:
        if isinstance(row, dict) and isinstance(row.get("id"), int):
            out.add(int(row["id"]))
    for group in elig.get("denied_groups") or []:
        if isinstance(group, dict):
            out.update(int(i) for i in (group.get("ids") or []) if isinstance(i, int))
    return out


def _unknown_ids(elig: dict) -> set[int]:
    out: set[int] = set()
    for row in elig.get("unknown") or []:
        if isinstance(row, dict) and isinstance(row.get("id"), int):
            out.add(int(row["id"]))
    for group in elig.get("unknown_groups") or []:
        if isinstance(group, dict):
            out.update(int(i) for i in (group.get("ids") or []) if isinstance(i, int))
    return out


def _clean_con_filter() -> AdventureRosterFilter:
    """Isolated CON>=14 + patron block for 159 (no live patron side-effects)."""
    return AdventureRosterFilter(
        ability_score_gates=[("con", ">=", 14)],
        deny_exprs=["GetStat(`con`) < 14"],
        patron_blocked_hero_ids={159},
        active_notes=["Test CON>=14", "Test patron block 159"],
    )


class EligibilityPresenceConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        cache_path = Path(self._tmpdir.name) / "owned_roster_cache.json"
        self._cache_patch = patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
            cache_path,
        )
        self._cache_patch.start()
        self.payload = json.loads(json.dumps(self.base_payload))
        defines = self.payload.setdefault("defines", {})
        adventures = list(defines.get("adventure_defines") or [])
        adventures.append(
            {
                "id": 9001,
                "name": "Critical Level",
                "restrictions_text": (
                    "Only Champions with a CON score of 14 or higher can be used"
                ),
                "game_changes": [
                    {
                        "type": "disallow_crusaders",
                        "by_stat": {
                            "stats": [{"stat": "con", "comp": "<", "value": 14}],
                        },
                    }
                ],
            }
        )
        defines["adventure_defines"] = adventures
        for inst in self.payload.get("details", {}).get("game_instances") or []:
            if isinstance(inst, dict):
                inst["current_adventure_id"] = 9001
                # No live patron — inject patron_blocked only via filter stub.
                inst.pop("current_patron_id", None)
                inst["formation"] = [2, 3, 4, 0, 0, 0, 0, 0, 159]
        heroes = self.payload.setdefault("details", {}).setdefault("heroes", [])
        if not any(int(h.get("hero_id") or 0) == 159 for h in heroes if isinstance(h, dict)):
            heroes.append({"hero_id": 159, "owned": "1", "name": "Volo", "seat_id": 9})
        self.formation = (
            _hero(2, "Celeste", 1),
            _hero(3, "Nayeli", 2),
            _hero(4, "Jarlaxle", 3),
            _hero(159, "Volo", 9),
        )
        self.scores = {
            2: {"con": 14, "dex": 14, "int": 14},
            3: {"con": 16, "dex": 12, "int": 12},
            4: {"con": 14, "dex": 18, "int": 12},
            159: {"con": 10, "dex": 12, "int": 14},  # BASE CON below gate
            1: {"con": 15, "dex": 12, "int": 14},
            12: {"con": 16, "dex": 14, "int": 14},
        }

    def tearDown(self) -> None:
        self._cache_patch.stop()
        self._tmpdir.cleanup()

    def _request(self, **kwargs):
        snap = build_base_snapshot(self.payload, formation=self.formation)
        filt = _clean_con_filter()
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=self.scores,
        ), patch(
            "ic_gamedata.adventure_restrictions.build_adventure_roster_filter",
            return_value=filt,
        ):
            req = build_advice_request(
                self.payload,
                self.formation,
                snapshot_id=snap["meta"]["snapshot_id"],
                snapshot_meta=snap["meta"],
                base_snapshot=snap,
                **kwargs,
            )
        # Structured export keeps raw patron_blocked from the filter stub.
        structured = (req.get("goal") or {}).get("structured_restrictions")
        if isinstance(structured, dict):
            structured["patron_blocked_hero_ids"] = sorted(filt.patron_blocked_hero_ids)
        return req, snap

    def test_1_seated_but_effectively_blocked(self) -> None:
        """Champion in party but blocked → presence kept, not auto-allowed.

        Volo may resolve to denied (hard patron/CON) or unknown when a real
        campaign-scoped kit override lacks verified campaign context — never
        unconditional allowed solely because he is seated.
        """
        req, _snap = self._request(include_swap_scope=False)
        party_by_id = {m["id"]: m for m in req["party"]}
        self.assertIn(159, party_by_id)
        self.assertEqual(party_by_id[159].get("position"), 9)
        self.assertNotEqual(party_by_id[159].get("eligibility"), "allowed")
        elig = req["roster_eligibility"]
        self.assertNotIn(159, set(elig.get("allowed_ids") or []))
        denied = _denied_ids(elig)
        unknown = _unknown_ids(elig)
        self.assertTrue(
            159 in denied or 159 in unknown,
            msg=f"159 must be denied or unknown; denied={denied} unknown={unknown}",
        )
        structured = (req.get("goal") or {}).get("structured_restrictions") or {}
        self.assertIn(159, structured.get("patron_blocked_hero_ids") or [])
        conflicts = {
            c["champion_id"]: c
            for c in (elig.get("presence_conflicts") or [])
            if isinstance(c, dict)
        }
        self.assertIn(159, conflicts)
        self.assertEqual(conflicts[159]["status"], "unresolved")
        self.assertEqual(conflicts[159]["conflict"], "static_denied_formation_present")
        self.assertIs(conflicts[159].get("replacement_locked"), False)

    def test_2_seated_and_provably_allowed(self) -> None:
        """Party member who meets gates → consistent allowed."""
        req, _ = self._request(include_swap_scope=False)
        party_by_id = {m["id"]: m for m in req["party"]}
        elig = req["roster_eligibility"]
        allowed = set(elig.get("allowed_ids") or [])
        denied = _denied_ids(elig)
        for hid in (2, 3, 4):
            self.assertEqual(party_by_id[hid].get("eligibility"), "allowed")
            self.assertIn(hid, allowed)
            self.assertNotIn(hid, denied)

    def test_3_static_block_lifted_by_explicit_exception(self) -> None:
        """Documented kit/campaign exceptions → effective allowed + resolved conflict."""
        # force_allow via exempt_hero_ids (API exception list).
        conflicts = _eligibility_presence_conflicts(
            {
                "overrides_applied": [
                    {
                        "champion_id": 159,
                        "base": "denied",
                        "effective": "allowed",
                        "reason": "force_allow via tag human",
                    }
                ]
            },
            exempt_hero_ids={159},
        )
        self.assertIsNotNone(conflicts)
        row = next(c for c in conflicts if c["champion_id"] == 159)
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolution"], "force_allow_hero")

        # Campaign-scoped kit allow (Volo-class) without exempt list.
        campaign_conflicts = _eligibility_presence_conflicts(
            {
                "overrides_applied": [
                    {
                        "champion_id": 159,
                        "base": "denied",
                        "effective": "allowed",
                        "reason": (
                            "Campaign scope matched "
                            "(A Grand Tour of the Sword Coast)"
                        ),
                        "overrides": [
                            {"kind": "campaign_scoped_eligibility"}
                        ],
                    }
                ]
            },
            exempt_hero_ids=set(),
        )
        crow = next(c for c in campaign_conflicts if c["champion_id"] == 159)
        self.assertEqual(crow["status"], "resolved")
        self.assertEqual(crow["resolution"], "campaign_scoped_eligibility")
        self.assertIs(crow.get("replacement_locked"), False)

        record = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="patron_blocked",
            overrides=[
                {
                    "kind": "force_allow_hero_by_tag",
                    "required_tag": "human",
                    "source_ability_id": 1,
                    "condition": "target_has_tag",
                }
            ],
            champion_tags=["human"],
            tags_known=True,
            campaign_id=None,
            campaign_name=None,
        )
        self.assertEqual(record["effective_eligibility"], "allowed")
        self.assertIn("force_allow", str(record.get("effective_reason") or ""))
        self.assertEqual(record["base_eligibility"], "denied")

    def test_4_insufficient_exception_data_is_unknown(self) -> None:
        """Possible override without verified tags → unknown, not silent allowed."""
        record = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="patron_blocked",
            overrides=[
                {
                    "kind": "force_allow_hero_by_tag",
                    "required_tag": "human",
                    "source_ability_id": 1,
                    "condition": "target_has_tag",
                }
            ],
            champion_tags=[],
            tags_known=False,
            campaign_id=None,
            campaign_name=None,
        )
        self.assertEqual(record["effective_eligibility"], "unknown")
        self.assertNotEqual(record["effective_eligibility"], "allowed")

    def test_5_stat_gate_uses_effective_sheet_scores(self) -> None:
        """CON gate judged on provided sheet scores (no invented modifiers)."""
        filt = AdventureRosterFilter(ability_score_gates=[("con", ">=", 14)])
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=self.scores,
        ):
            rows = {
                r["champion_id"]: r
                for r in evaluate_heroes_against_filter([159, 3], filt)
            }
        self.assertEqual(rows[159]["status"], "denied")
        self.assertEqual(rows[3]["status"], "allowed")
        self.assertEqual(rows[159]["ability_scores"].get("con"), 10)
        self.assertEqual(rows[3]["ability_scores"].get("con"), 16)

    def test_6_allowed_ids_vs_denied_invariant(self) -> None:
        """Validation flags allowed_ids ∩ denied overlap."""
        request = {
            "meta": {"snapshot_ref": {"snapshot_id": "snap_x"}},
            "goal": {"id": "g", "party_restriction_status": "ok"},
            "geometry": {"valid_position_ids": [1, 9], "occupied": [9]},
            "party": [
                {"id": 159, "eligibility": "allowed", "live_state": {"status": "known"}}
            ],
            "roster_eligibility": {
                "allowed_ids": [159],
                "denied_groups": [
                    {
                        "reason": "Champion geblokkeerd door adventure/patron/trials.",
                        "ids": [159],
                    }
                ],
                "presence_conflicts": [
                    {
                        "champion_id": 159,
                        "conflict": "static_denied_formation_present",
                        "status": "unresolved",
                        "replacement_locked": False,
                    }
                ],
            },
            "readiness": {
                "status": "ready",
                "dimensions": {"party_legality": "allowed"},
            },
        }
        result = validate_advice_request_export(
            payload=self.payload,
            request=request,
            snapshot_id="snap_x",
            exported_snapshot_id="snap_x",
        )
        codes = {i.code for i in result.issues}
        self.assertIn("allowed_ids_contradict_denied", codes)
        self.assertIn("party_eligibility_contradicts_denied", codes)
        self.assertFalse(result.party_restriction_ok)
        self.assertFalse(result.advice_ready)

    def test_7_unresolved_replaceable_does_not_block_structure(self) -> None:
        """Replaceable contested member: conflict visible; structure still ok."""
        req, snap = self._request(include_swap_scope=True)
        elig = req["roster_eligibility"]
        conflicts = {
            c["champion_id"]: c
            for c in (elig.get("presence_conflicts") or [])
            if isinstance(c, dict)
        }
        self.assertEqual(conflicts[159]["status"], "unresolved")
        self.assertIs(conflicts[159].get("replacement_locked"), False)
        dims = (req.get("readiness") or {}).get("dimensions") or {}
        self.assertEqual(dims.get("party_legality"), "conflict")
        self.assertIn(dims.get("placement_advice"), ("partial", "insufficient"))
        validation = validate_advice_request_export(
            payload=self.payload,
            request=req,
            snapshot_id=snap["meta"]["snapshot_id"],
            exported_snapshot_id=snap["meta"]["snapshot_id"],
        )
        self.assertTrue(validation.structural_ok)
        self.assertFalse(validation.party_restriction_ok)
        self.assertFalse(validation.advice_ready)
        allowed = set(elig.get("allowed_ids") or [])
        self.assertTrue({2, 3, 4} <= allowed)

    def test_8_replacement_locked_unresolved_blocks_keep_advice(self) -> None:
        """Locked contested champion blocks keep/move advice path."""
        request = {
            "meta": {"snapshot_ref": {"snapshot_id": "snap_y"}},
            "goal": {"id": "g", "party_restriction_status": "conflict"},
            "geometry": {"valid_position_ids": [1, 9], "occupied": [9]},
            "party": [
                {
                    "id": 159,
                    "eligibility": "denied",
                    "live_state": {"status": "known"},
                    "replacement_locked": True,
                    "must_remain_in_party": True,
                }
            ],
            "roster_eligibility": {
                "allowed_ids": [],
                "denied_groups": [{"reason": "patron", "ids": [159]}],
                "presence_conflicts": [
                    {
                        "champion_id": 159,
                        "conflict": "static_denied_formation_present",
                        "status": "unresolved",
                        "replacement_locked": True,
                        "must_remain_in_party": True,
                    }
                ],
            },
            "readiness": {
                "status": "ready_with_warnings",
                "dimensions": {
                    "party_legality": "conflict",
                    "placement_advice": "insufficient",
                },
            },
        }
        result = validate_advice_request_export(
            payload=self.payload,
            request=request,
            snapshot_id="snap_y",
            exported_snapshot_id="snap_y",
        )
        codes = {i.code for i in result.issues}
        self.assertIn("replacement_locked_presence_conflict", codes)
        self.assertFalse(result.party_restriction_ok)
        self.assertFalse(result.advice_ready)

    def test_9_eligible_but_other_party_not_auto_placeable(self) -> None:
        """Eligibility ≠ availability when practical_availability is other_party."""
        filt = AdventureRosterFilter(ability_score_gates=[("con", ">=", 14)])
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=self.scores,
        ), patch(
            "ic_gamedata.adventure_restrictions.build_adventure_roster_filter",
            return_value=filt,
        ), patch(
            "ic_gamedata.formation_ai_advice.swap_export._other_party_instance",
            return_value={
                "status": "other_party",
                "game_instance_id": 2,
            },
        ):
            elig = _compact_eligibility_table(
                [12],
                self.payload,
                adventure_id=9001,
                campaign_id=None,
                campaign_name=None,
                entries_by_id={
                    12: {
                        "champion_id": 12,
                        "tags": ["human"],
                        "affiliations_status": "known",
                        "raw_tags": ["human"],
                    }
                },
                include_external_availability=True,
            )
        self.assertIn(12, set(elig.get("allowed_ids") or []))
        avail = elig.get("practical_availability") or []
        self.assertTrue(
            any(
                isinstance(row, dict)
                and row.get("id") == 12
                and row.get("status") == "other_party"
                for row in avail
            )
        )
        note = str(elig.get("availability_note") or "")
        self.assertIn("plaatsbaar", note.casefold())

    def test_10_npc_escort_placeability_unchanged_by_eligibility_fix(self) -> None:
        """Eligibility repair must not invent free seats on NPC/escort slots."""
        req, _ = self._request(include_swap_scope=False)
        geo = req.get("geometry") or {}
        for slot in geo.get("slot_states") or []:
            if not isinstance(slot, dict):
                continue
            if slot.get("occupant_kind") in ("npc", "escort") or slot.get(
                "placeability"
            ) == "blocked":
                self.assertNotEqual(slot.get("placeability"), "placeable")
        if not geo.get("slot_states"):
            self.assertNotIn("assumed_free_positions", geo)

    def test_11_export_consistency_across_fields(self) -> None:
        """allowed/denied/party/conflicts/validation/readiness stay coherent."""
        req, snap = self._request(include_swap_scope=False)
        elig = req["roster_eligibility"]
        allowed = set(elig.get("allowed_ids") or [])
        denied = _denied_ids(elig)
        unknown = _unknown_ids(elig)
        self.assertFalse(allowed & denied)
        self.assertFalse(allowed & unknown)
        party_by_id = {m["id"]: m for m in req["party"]}
        for hid, member in party_by_id.items():
            status = member.get("eligibility")
            if status == "allowed":
                self.assertIn(hid, allowed)
                self.assertNotIn(hid, denied)
            elif status == "denied":
                self.assertIn(hid, denied)
                self.assertNotIn(hid, allowed)
            elif status == "unknown":
                self.assertIn(hid, unknown)
                self.assertNotIn(hid, allowed)
        self.assertIn(159, party_by_id)
        conflicts = {
            c["champion_id"]: c
            for c in (elig.get("presence_conflicts") or [])
            if isinstance(c, dict)
        }
        self.assertEqual(conflicts[159]["status"], "unresolved")
        dims = (req.get("readiness") or {}).get("dimensions") or {}
        self.assertEqual(dims.get("party_legality"), "conflict")
        self.assertNotEqual(dims.get("party_legality"), "allowed")
        validation = validate_advice_request_export(
            payload=self.payload,
            request=req,
            snapshot_id=snap["meta"]["snapshot_id"],
            exported_snapshot_id=snap["meta"]["snapshot_id"],
        )
        self.assertFalse(validation.party_restriction_ok)
        self.assertFalse(validation.advice_ready)
        self.assertTrue(validation.structural_ok)
        self.assertTrue(
            any(
                i.code
                in {
                    "party_denied_by_restrictions",
                    "unresolved_presence_conflict",
                    "restriction_conflict_blocks_advice",
                }
                for i in validation.errors
            )
        )


class FormationPresenceNotPermissionUnitTests(unittest.TestCase):
    def test_is_hero_allowed_ignores_presence_arg(self) -> None:
        filt = AdventureRosterFilter(patron_blocked_hero_ids={159})
        self.assertFalse(is_hero_allowed(159, filt))
        self.assertFalse(is_hero_allowed(159, filt, formation_hero_ids=frozenset({159})))

    def test_evaluate_ignores_presence_arg(self) -> None:
        filt = AdventureRosterFilter(patron_blocked_hero_ids={159})
        rows = evaluate_heroes_against_filter(
            [159], filt, formation_hero_ids=frozenset({159})
        )
        self.assertEqual(rows[0]["status"], "denied")


if __name__ == "__main__":
    unittest.main()
