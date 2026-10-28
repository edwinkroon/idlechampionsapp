"""Budget + validation regressions for the concrete DEX conflict export case."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export_clipboard import (
    build_advice_request_clipboard_text,
    evaluate_clipboard_budget,
)
from ic_gamedata.formation_ai_advice.export_budget import (
    DEFAULT_CHAR_BUDGET,
    count_chars,
    count_utf8_bytes,
)
from ic_gamedata.formation_ai_advice.export_validation import (
    mark_request_unvalidated,
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
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
        role_label="Dps",
        roles=("dps",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class AdviceRequestBudgetFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.payload = json.loads(json.dumps(self.base_payload))
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

        # Inject live adventure 909 shape (disallow_crusaders + by_stat dex < 12).
        defines = self.payload.setdefault("defines", {})
        adventures = list(defines.get("adventure_defines") or [])
        adventures.append(
            {
                "id": 909,
                "name": "Mountain - Unannounced Visit",
                "restrictions_text": (
                    "Only Champions with a DEX score of 12 or higher can be used"
                ),
                "game_changes": [
                    {
                        "type": "disallow_crusaders",
                        "by_stat": {
                            "stats": [{"stat": "dex", "comp": "<", "value": 12}],
                            "blocked_portrait": 11036,
                        },
                    }
                ],
            }
        )
        defines["adventure_defines"] = adventures
        for inst in self.payload.get("details", {}).get("game_instances") or []:
            if isinstance(inst, dict):
                inst["current_adventure_id"] = 909

    def tearDown(self) -> None:
        self._cache_patch.stop()
        self._tmpdir.cleanup()

    def test_conflict_diagnostic_request_within_16k(self) -> None:
        """Large party under DEX adventure still fits budget (incl. denials)."""
        owned = [
            int(h["hero_id"])
            for h in self.payload["details"]["heroes"]
            if h.get("owned") in ("1", 1, True)
        ]
        scores = {hid: {"dex": 10} for hid in owned}
        for hid in (1, 2, 6, 9, 27):
            scores[hid] = {"dex": 14}
        # Larger party (closer to live 10-man) to stress validation grouping.
        big_formation = (
            _hero(21, "Birdsong", 9),
            _hero(43, "Spurt", 3),
            _hero(106, "Blooshi", 2),
            _hero(113, "Egbert", 7),
            _hero(164, "Tess", 8),
            _hero(166, "Cazrin", 10),
            _hero(170, "Lark", 6),
            _hero(171, "Anson", 1),
            _hero(172, "Kyre", 5),
            _hero(180, "Kitiara", 4),
        )
        snap = build_base_snapshot(self.payload, formation=big_formation)
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            for include_swap in (False, True):
                req = build_advice_request(
                    self.payload,
                    big_formation,
                    snapshot_id=snap["meta"]["snapshot_id"],
                    snapshot_meta=snap["meta"],
                    base_snapshot=snap,
                    goal="push",
                    fixed_main_dps_id=166,
                    include_swap_scope=include_swap,
                )
                validation = validate_advice_request_export(
                    payload=self.payload,
                    request=req,
                    snapshot_id=snap["meta"]["snapshot_id"],
                    exported_snapshot_id=snap["meta"]["snapshot_id"],
                )
                labeled = mark_request_unvalidated(req, validation)
                text = build_advice_request_clipboard_text(labeled, mode="project")
                chars = count_chars(text)
                utf8 = count_utf8_bytes(text)
                self.assertLessEqual(
                    utf8,
                    DEFAULT_CHAR_BUDGET,
                    msg=(
                        f"swap={include_swap} utf8={utf8} chars={chars} "
                        f"budget={DEFAULT_CHAR_BUDGET}"
                    ),
                )
                issues = (labeled.get("meta") or {}).get("validation", {}).get(
                    "issues"
                ) or []
                # Per-code grouping: no repeated party_denied rows.
                denied_rows = [
                    i for i in issues if i.get("code") == "party_denied_by_restrictions"
                ]
                self.assertLessEqual(len(denied_rows), 1)

    def test_selected_only_request_within_16k_after_fix(self) -> None:
        scores = {
            2: {"dex": 14},
            3: {"dex": 13},
            4: {"dex": 16},
            1: {"dex": 10},
        }
        # Give many owned heroes high DEX so pre-fix would deny most.
        owned = [
            int(h["hero_id"])
            for h in self.payload["details"]["heroes"]
            if h.get("owned") in ("1", 1, True)
        ]
        for hid in owned:
            scores.setdefault(hid, {"dex": 14})

        snap = build_base_snapshot(self.payload, formation=self.formation)
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            req = build_advice_request(
                self.payload,
                self.formation,
                snapshot_id=snap["meta"]["snapshot_id"],
                snapshot_meta=snap["meta"],
                goal="push",
                fixed_main_dps_id=4,
                include_swap_scope=False,
            )

        # Restrictiesemantiek hersteld: party met DEX>=12 is allowed.
        for member in req["party"]:
            self.assertEqual(member.get("eligibility"), "allowed")

        structured = (req.get("goal") or {}).get("structured_restrictions") or {}
        self.assertIn("GetStat(`dex`) < 12", structured.get("deny_exprs") or [])
        self.assertNotIn("GetStat(`dex`) < 12", structured.get("allow_exprs") or [])

        elig = req.get("roster_eligibility") or {}
        self.assertEqual(elig.get("scope"), "selected_party_only")
        self.assertIsNone(elig.get("denied"))
        # No bulky flat denied list for the whole roster.
        self.assertTrue(
            elig.get("denied_groups") is None or len(elig.get("denied_groups") or []) == 0
        )

        text = build_advice_request_clipboard_text(req, mode="project")
        chars = count_chars(text)
        utf8 = count_utf8_bytes(text)
        print(
            "FIXED_REQUEST_SIZE",
            json.dumps(
                {
                    "chars": chars,
                    "utf8_bytes": utf8,
                    "budget": DEFAULT_CHAR_BUDGET,
                    "within_16k": utf8 <= DEFAULT_CHAR_BUDGET,
                    "before_case_chars": 22661,
                }
            ),
        )
        self.assertLessEqual(utf8, DEFAULT_CHAR_BUDGET)
        info = evaluate_clipboard_budget(text, max_chars=DEFAULT_CHAR_BUDGET)
        self.assertTrue(info["within_budget"])

        # Exact boundary / one-over still not truncated (UTF-8 byte gate).
        exact = evaluate_clipboard_budget(text, max_chars=utf8)
        self.assertTrue(exact["within_budget"])
        over = evaluate_clipboard_budget(text, max_chars=utf8 - 1)
        self.assertFalse(over["within_budget"])
        self.assertEqual(count_chars(text), chars)
        self.assertEqual(count_utf8_bytes(text), utf8)

        validation = validate_advice_request_export(
            payload=self.payload,
            request=req,
            snapshot_id=snap["meta"]["snapshot_id"],
            exported_snapshot_id=snap["meta"]["snapshot_id"],
        )
        self.assertTrue(validation.advice_ready, validation.summary_nl())
        self.assertTrue(validation.structural_ok)
        self.assertTrue(validation.party_restriction_ok)

    def test_seated_party_not_auto_allowed_when_static_dex_denies(self) -> None:
        """Presence is observation only — low DEX seated champs stay denied."""
        defines = self.payload["defines"]
        for adv in defines["adventure_defines"]:
            if adv.get("id") == 909:
                adv["restrictions_text"] = (
                    "Only Champions with a DEX score of 12 or higher can be used"
                )
                adv["game_changes"] = [
                    {
                        "type": "disallow_crusaders",
                        "by_stat": {
                            "stats": [{"stat": "dex", "comp": "<", "value": 12}],
                        },
                    }
                ]
        scores = {2: {"dex": 10}, 3: {"dex": 11}, 4: {"dex": 9}, 1: {"dex": 8}}
        snap = build_base_snapshot(self.payload, formation=self.formation)
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            req = build_advice_request(
                self.payload,
                self.formation,
                snapshot_id=snap["meta"]["snapshot_id"],
                snapshot_meta=snap["meta"],
                include_swap_scope=False,
            )
        structured = (req.get("goal") or {}).get("structured_restrictions") or {}
        self.assertIn("GetStat(`dex`) < 12", structured.get("deny_exprs") or [])
        self.assertNotIn("GetStat(`dex`) < 12", structured.get("allow_exprs") or [])
        party_ids = {int(m["id"]) for m in (req.get("party") or []) if m.get("id")}
        for member in req.get("party") or []:
            self.assertNotEqual(
                member.get("eligibility"),
                "allowed",
                msg=f"seated {member.get('id')} must not be auto-allowed",
            )
        elig = req.get("roster_eligibility") or {}
        denied_ids = {
            int(row["id"])
            for row in (elig.get("denied") or [])
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        }
        for group in elig.get("denied_groups") or []:
            if isinstance(group, dict):
                denied_ids.update(
                    int(i) for i in (group.get("ids") or []) if isinstance(i, int)
                )
        self.assertTrue(party_ids & denied_ids)
        self.assertFalse(set(elig.get("allowed_ids") or []) & denied_ids)
        conflicts = {
            int(c["champion_id"]): c
            for c in (elig.get("presence_conflicts") or [])
            if isinstance(c, dict) and isinstance(c.get("champion_id"), int)
        }
        for hid in party_ids:
            self.assertIn(hid, conflicts)
            self.assertEqual(conflicts[hid].get("status"), "unresolved")
            self.assertIs(conflicts[hid].get("replacement_locked"), False)
        dims = (req.get("readiness") or {}).get("dimensions") or {}
        self.assertEqual(dims.get("party_legality"), "conflict")
        validation = validate_advice_request_export(
            payload=self.payload,
            request=req,
            snapshot_id=snap["meta"]["snapshot_id"],
            exported_snapshot_id=snap["meta"]["snapshot_id"],
        )
        self.assertFalse(validation.party_restriction_ok, validation.summary_nl())
        self.assertFalse(validation.advice_ready, validation.summary_nl())
        self.assertTrue(validation.structural_ok, validation.summary_nl())
        self.assertTrue(
            any(i.code == "party_denied_by_restrictions" for i in validation.errors)
        )

    def test_not_unlocked_spec_without_id_is_not_structural_error(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        scores = {2: {"dex": 14}, 3: {"dex": 14}, 4: {"dex": 14}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            req = build_advice_request(
                self.payload,
                self.formation,
                snapshot_id=snap["meta"]["snapshot_id"],
                snapshot_meta=snap["meta"],
                include_swap_scope=False,
            )
        # Inject not_unlocked choice.
        req["party"][0]["specialization_choices"] = [
            {"group_id": "tier_1", "selection_status": "not_unlocked"}
        ]
        result = validate_advice_request_export(
            payload=self.payload,
            request=req,
            snapshot_id=snap["meta"]["snapshot_id"],
            exported_snapshot_id=snap["meta"]["snapshot_id"],
        )
        codes = {i.code for i in result.errors}
        self.assertNotIn("spec_choice_missing_id", codes)
        self.assertNotIn("selected_spec_missing_option_id", codes)


if __name__ == "__main__":
    unittest.main()
