"""Integration: live adventure 909 disallow+by_stat through real advice export.

Proven API shape (getuserdetails 2026-10-17, adventure_id 909):
  type=disallow_crusaders
  by_stat.stats=[{stat:dex, comp:<, value:12}]
  restrictions_text=Only Champions with a DEX score of 12 or higher can be used

Historical bug: _filter_from_by_stat copied the same comparator into allow_exprs,
so export claimed predicate_kind=allow for GetStat(dex)<12 and denied high-DEX parties.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    build_adventure_roster_filter,
    evaluate_heroes_against_filter,
    is_hero_allowed,
    structured_stat_gates,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.party_advisor_models import FormationHero

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "adventure_909_live_define.json"
_PARTY = (21, 43, 106, 113, 164, 166, 170, 171, 172, 180)


def _load_live_define() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


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


def _payload_with_live_909(*, formation_ids: tuple[int, ...] = _PARTY) -> dict:
    adv = _load_live_define()
    return {
        "defines": {"adventure_defines": [adv]},
        "details": {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 909,
                    "current_area": 706,
                    "formation": list(formation_ids),
                }
            ],
            "heroes": [
                {
                    "hero_id": hid,
                    "owned": "1",
                    "name": f"Hero{hid}",
                    "seat_id": (i % 12) + 1,
                }
                for i, hid in enumerate(formation_ids)
            ],
        },
    }


def _scores_for_party() -> dict[int, dict[str, int]]:
    # Live character_sheet basis (high DEX party from advice export).
    return {
        21: {"dex": 18},
        43: {"dex": 15},
        106: {"dex": 14},
        113: {"dex": 14},
        164: {"dex": 17},
        166: {"dex": 13},
        170: {"dex": 13},
        171: {"dex": 14},
        172: {"dex": 16},
        180: {"dex": 18},
        # Boundary heroes for gate tests
        9011: {"dex": 11},
        9012: {"dex": 12},
        9013: {"dex": 13},
    }


class DisallowByStat909SemanticsTests(unittest.TestCase):
    def test_live_fixture_shape(self) -> None:
        adv = _load_live_define()
        self.assertEqual(adv["id"], 909)
        change = adv["game_changes"][0]
        self.assertEqual(change["type"], "disallow_crusaders")
        stat = change["by_stat"]["stats"][0]
        self.assertEqual(stat, {"stat": "dex", "comp": "<", "value": 12})
        self.assertIn("12 or higher", adv["restrictions_text"])

    def test_filter_deny_when_true_not_allow_expr(self) -> None:
        payload = _payload_with_live_909()
        scores = _scores_for_party()
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 909)
            self.assertIn("GetStat(`dex`) < 12", filt.deny_exprs)
            self.assertNotIn("GetStat(`dex`) < 12", filt.allow_exprs)
            self.assertTrue(
                any(s == "dex" and o == ">=" and v == 12 for s, o, v in filt.ability_score_gates)
            )
            interp = filt.expr_interpretations[0]
            self.assertEqual(interp.get("change_type"), "disallow_crusaders")
            self.assertEqual(interp.get("source"), "by_stat")
            self.assertEqual(interp.get("predicate_kind"), "deny")
            self.assertEqual(interp.get("true_means"), "denied")

            self.assertFalse(is_hero_allowed(9011, filt))
            self.assertTrue(is_hero_allowed(9012, filt))
            self.assertTrue(is_hero_allowed(9013, filt))

            gates = structured_stat_gates(filt)
            self.assertFalse(
                any(
                    g.get("operator") == "<" and g.get("predicate_kind") == "allow"
                    for g in gates
                )
            )
            hard = [
                g
                for g in gates
                if g.get("stat") == "dex"
                and g.get("operator") == ">="
                and g.get("value") == 12
            ]
            self.assertTrue(hard)
            raw_pred = hard[0].get("raw_predicate") or {}
            self.assertEqual(raw_pred.get("raw_expr"), "GetStat(`dex`) < 12")
            self.assertEqual(raw_pred.get("predicate_kind"), "deny")


class DisallowByStat909AdviceExportIntegrationTests(unittest.TestCase):
    """Drive the real build_advice_request / snapshot export path."""

    def test_advice_request_export_normalizes_disallow_by_stat(self) -> None:
        payload = _payload_with_live_909()
        scores = _scores_for_party()
        formation = tuple(
            _hero(hid, f"Hero{hid}", (idx % 12) + 1) for idx, hid in enumerate(_PARTY)
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ), patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value={},
        ):
            snap = build_base_snapshot(payload, formation=formation)
            req = build_advice_request(
                payload,
                formation,
                snapshot_id=str(snap["meta"]["snapshot_id"]),
                snapshot_meta=snap["meta"],
                goal="push",
                include_swap_scope=False,
                request_id="862f8222-test-replay",
            )

        goal = req.get("goal") or {}
        structured = goal.get("structured_restrictions") or {}
        self.assertEqual(goal.get("adventure_id"), 909)
        self.assertIn(
            "Only Champions with a DEX score of 12 or higher can be used",
            structured.get("raw_restrictions_text") or "",
        )
        self.assertIn("GetStat(`dex`) < 12", structured.get("deny_exprs") or [])
        self.assertNotIn("GetStat(`dex`) < 12", structured.get("allow_exprs") or [])

        gates = structured.get("stat_gates") or []
        self.assertFalse(
            any(
                g.get("operator") == "<" and g.get("predicate_kind") == "allow"
                for g in gates
                if isinstance(g, dict)
            )
        )
        hard = [
            g
            for g in gates
            if isinstance(g, dict)
            and g.get("stat") == "dex"
            and g.get("operator") == ">="
            and g.get("value") == 12
        ]
        self.assertTrue(hard, msg=f"missing normalized gate in {gates!r}")
        self.assertEqual(hard[0].get("predicate_kind"), "allow")
        self.assertEqual(
            (hard[0].get("raw_predicate") or {}).get("predicate_kind"), "deny"
        )
        self.assertEqual(
            (hard[0].get("raw_predicate") or {}).get("change_type"),
            "disallow_crusaders",
        )

        # Boundary checks via the same filter the export used.
        filt = build_adventure_roster_filter(payload, 909)
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            rows = {
                r["champion_id"]: r
                for r in evaluate_heroes_against_filter([9011, 9012, 9013], filt)
            }
        self.assertEqual(rows[9011]["status"], "denied")
        self.assertEqual(rows[9012]["status"], "allowed")
        self.assertEqual(rows[9013]["status"], "allowed")

        # Selected high-DEX party must not be denied by this rule.
        for member in req.get("party") or []:
            self.assertEqual(
                member.get("eligibility"),
                "allowed",
                msg=f"party member {member.get('id')} still denied: {member}",
            )
        self.assertNotEqual(goal.get("party_restriction_status"), "conflict")

        # Prove the fixed serializer path is what the request carries.
        fragment = {
            "request_id": (req.get("meta") or {}).get("request_id"),
            "adventure_id": goal.get("adventure_id"),
            "party_restriction_status": goal.get("party_restriction_status"),
            "deny_exprs": structured.get("deny_exprs"),
            "allow_exprs": structured.get("allow_exprs"),
            "stat_gates": structured.get("stat_gates"),
            "expr_interpretations": structured.get("expr_interpretations"),
        }
        print("EXPORT_FRAGMENT_909", json.dumps(fragment, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    unittest.main()
