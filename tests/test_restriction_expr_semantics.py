"""Regression: by_expr allow/deny semantics vs restrictions_text."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    _gates_are_equivalent,
    _gates_are_negations,
    _invert_comparator,
    build_adventure_roster_filter,
    evaluate_heroes_against_filter,
    is_hero_allowed,
    structured_stat_gates,
)


def _mock_adventure(adventure_id: int, **kwargs):
    adv = {"id": adventure_id, "name": f"Adv {adventure_id}", **kwargs}
    return {
        "defines": {"adventure_defines": [adv]},
        "details": {
            "active_game_instance_id": 1,
            "game_instances": [{"game_instance_id": 1, "current_adventure_id": adventure_id}],
        },
    }


class ComparatorNegationTests(unittest.TestCase):
    def test_invert_inclusive_exclusive(self) -> None:
        self.assertEqual(_invert_comparator("<"), ">=")
        self.assertEqual(_invert_comparator("<="), ">")
        self.assertEqual(_invert_comparator(">"), "<=")
        self.assertEqual(_invert_comparator(">="), "<")

    def test_integer_negation_dex_lt_12_vs_gte_12(self) -> None:
        self.assertTrue(
            _gates_are_negations(("dex", "<", 12), ("dex", ">=", 12))
        )
        self.assertTrue(
            _gates_are_negations(("dex", ">=", 12), ("dex", "<", 12))
        )
        self.assertTrue(
            _gates_are_negations(("dex", "<=", 11), ("dex", ">=", 12))
        )

    def test_equivalent_not_negation(self) -> None:
        self.assertTrue(_gates_are_equivalent(("dex", "<", 12), ("dex", "<=", 11)))
        self.assertFalse(_gates_are_negations(("dex", "<", 12), ("dex", "<=", 11)))


class DenyExprReconciliationTests(unittest.TestCase):
    def test_deny_dex_lt_12_reconciled_to_allow_gte_12(self) -> None:
        """Case: text DEX>=12, by_expr GetStat(dex)<12 under only_allow."""
        payload = _mock_adventure(
            909,
            restrictions_text=(
                "Only Champions with a DEX score of 12 or higher can be used"
            ),
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {"expr": "GetStat(`dex`) < 12"},
                }
            ],
        )
        scores = {1: {"dex": 11}, 2: {"dex": 12}, 3: {"dex": 13}, 4: {"dex": 10}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 909)
            self.assertFalse(filt.has_restriction_semantics_conflict)
            self.assertIn("GetStat(`dex`) < 12", filt.deny_exprs)
            self.assertNotIn("GetStat(`dex`) < 12", filt.allow_exprs)
            hard = [(s, o, v) for s, o, v in filt.ability_score_gates if s == "dex"]
            self.assertTrue(any(o == ">=" and v == 12 for _, o, v in hard))

            self.assertFalse(is_hero_allowed(1, filt))  # 11
            self.assertTrue(is_hero_allowed(2, filt))  # 12
            self.assertTrue(is_hero_allowed(3, filt))  # 13

            rows = {
                r["champion_id"]: r
                for r in evaluate_heroes_against_filter([1, 2, 3, 4], filt)
            }
            self.assertEqual(rows[1]["status"], "denied")
            self.assertEqual(rows[2]["status"], "allowed")
            self.assertEqual(rows[3]["status"], "allowed")
            self.assertEqual(rows[4]["status"], "denied")

            gates = structured_stat_gates(filt)
            hard = [g for g in gates if g.get("operator") == ">=" and g.get("value") == 12]
            self.assertTrue(hard)
            self.assertEqual(hard[0].get("label"), "Min. DEX 12")
            self.assertEqual(hard[0].get("predicate_kind"), "allow")
            self.assertEqual(hard[0].get("true_means"), "allowed")
            raw_pred = hard[0].get("raw_predicate") or {}
            self.assertEqual(raw_pred.get("raw_expr"), "GetStat(`dex`) < 12")
            self.assertEqual(raw_pred.get("predicate_kind"), "deny")
            self.assertEqual(raw_pred.get("true_means"), "denied")
            # Must never label the raw deny expression itself as allow.
            self.assertNotIn("raw_expr", hard[0])
            self.assertFalse(
                any(
                    g.get("operator") == "<" and g.get("predicate_kind") == "allow"
                    for g in gates
                )
            )

    def test_or_lower_text_confirms_allow_max(self) -> None:
        """CNE often writes 'or lower'; that must confirm allow-when-true max."""
        payload = _mock_adventure(
            1442,
            restrictions_text=(
                "You may only use Champions with a Wisdom of 12 or lower."
            ),
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {"expr": "GetStat(`wis`) <= 12"},
                }
            ],
        )
        scores = {1: {"wis": 12}, 2: {"wis": 13}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 1442)
            self.assertIn("GetStat(`wis`) <= 12", filt.allow_exprs)
            self.assertEqual(
                filt.expr_interpretations[0].get("predicate_kind"), "allow"
            )
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(2, filt))

    def test_genuine_allow_dex_lt_12_not_inverted(self) -> None:
        """Allow DEX < 12 with matching text must stay a max gate."""
        payload = _mock_adventure(
            9010,
            restrictions_text=(
                "Only Champions with a Dexterity of 12 or less can be used"
            ),
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {"expr": "GetStat(`dex`) < 12"},
                }
            ],
        )
        # Text parses to <= 12; expr is < 12 — not exact negation of <=12.
        # < 12 vs <= 12 are not negations; they are related but different.
        # If text is "12 or less" → <= 12; expr < 12 is stricter allow, same direction.
        scores = {1: {"dex": 11}, 2: {"dex": 12}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 9010)
            # Same-direction: keep as allow_expr (expr < 12).
            # Text also adds hard <= 12 only when no API roster rules — but API
            # rules exist, so text is not merged as hard gate.
            self.assertIn("GetStat(`dex`) < 12", filt.allow_exprs)
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(2, filt))

    def test_matching_allow_dex_gte_12(self) -> None:
        payload = _mock_adventure(
            9011,
            restrictions_text=(
                "Only Champions with a DEX score of 12 or higher can be used"
            ),
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {"expr": "GetStat(`dex`) >= 12"},
                }
            ],
        )
        scores = {1: {"dex": 11}, 2: {"dex": 12}, 3: {"dex": 13}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 9011)
            self.assertIn("GetStat(`dex`) >= 12", filt.allow_exprs)
            self.assertFalse(filt.deny_exprs)
            self.assertFalse(is_hero_allowed(1, filt))
            self.assertTrue(is_hero_allowed(2, filt))
            self.assertTrue(is_hero_allowed(3, filt))

    def test_int_lte_11_regression_untouched(self) -> None:
        payload = _mock_adventure(
            1617,
            restrictions_text=(
                "You may only use Champions with an Intelligence of 11 or less."
            ),
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "<=", "value": 11}],
                    },
                }
            ],
        )
        scores = {1: {"int": 10}, 2: {"int": 11}, 3: {"int": 12}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 1617)
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertTrue(is_hero_allowed(2, filt))
            self.assertFalse(is_hero_allowed(3, filt))

    def test_missing_stat_unknown_not_allowed(self) -> None:
        payload = _mock_adventure(
            9012,
            restrictions_text="Only Champions with a DEX score of 12 or higher can be used",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {"expr": "GetStat(`dex`) < 12"},
                }
            ],
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value={1: {}},
        ):
            filt = build_adventure_roster_filter(payload, 9012)
            rows = evaluate_heroes_against_filter([1], filt)
            self.assertEqual(rows[0]["status"], "unknown")

    def test_upper_bound_without_text_is_unknown_not_proven_allow(self) -> None:
        """predicate_kind=allow is a default, not proven for sole < without text."""
        payload = _mock_adventure(
            9013,
            restrictions_text="[filled in automatically]",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {"expr": "GetStat(`dex`) < 12"},
                }
            ],
        )
        scores = {1: {"dex": 11}, 2: {"dex": 12}, 3: {"dex": 13}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 9013)
            self.assertTrue(filt.has_restriction_semantics_conflict)
            self.assertNotIn("GetStat(`dex`) < 12", filt.allow_exprs)
            self.assertNotIn("GetStat(`dex`) < 12", filt.deny_exprs)
            interp = filt.expr_interpretations[0]
            self.assertEqual(interp.get("predicate_kind"), "unknown")
            self.assertEqual(interp.get("action"), "mark_unconfirmed_semantics")
            gates = structured_stat_gates(filt)
            self.assertTrue(
                any(g.get("predicate_kind") == "unknown" for g in gates)
            )
            # Fail closed / unconfirmed: none treated as proven allowed.
            rows = {
                r["champion_id"]: r
                for r in evaluate_heroes_against_filter([1, 2, 3], filt)
            }
            for hid in (1, 2, 3):
                self.assertIn(rows[hid]["status"], ("denied", "unknown"))
                self.assertNotEqual(rows[hid]["status"], "allowed")
            self.assertFalse(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(2, filt))
            self.assertFalse(is_hero_allowed(3, filt))


class OriginalApiPayload909Tests(unittest.TestCase):
    """Regression on the live advice-export API shape for adventure 909.

    Source evidence (advice/advice_export.txt 2026-10-17):
    - change_type: only_allow_crusaders
    - by_expr.expr: GetStat(`dex`) < 12
    - restrictions_text: Only Champions with a DEX score of 12 or higher can be used
    Consumer: _filter_from_by_expr under only_allow → historically defaulted to
    allow-when-true (predicate_kind=allow) without confirming this comparator.
    """

    def test_original_api_payload_dex_min_12(self) -> None:
        payload = {
            "defines": {
                "adventure_defines": [
                    {
                        "id": 909,
                        "name": "Mountain - Unannounced Visit",
                        "restrictions_text": (
                            "Only Champions with a DEX score of 12 or higher "
                            "can be used"
                        ),
                        "game_changes": [
                            {
                                "type": "only_allow_crusaders",
                                "by_expr": {
                                    "expr": "GetStat(`dex`) < 12",
                                    "blocked_portrait": 13093,
                                },
                            }
                        ],
                    }
                ]
            },
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {"game_instance_id": 1, "current_adventure_id": 909}
                ],
            },
        }
        scores = {11: {"dex": 11}, 12: {"dex": 12}, 13: {"dex": 13}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, 909)
            self.assertEqual(
                filt.expr_interpretations[0].get("predicate_kind"), "deny"
            )
            self.assertEqual(
                filt.expr_interpretations[0].get("change_type"),
                "only_allow_crusaders",
            )
            self.assertIn("GetStat(`dex`) < 12", filt.deny_exprs)
            self.assertNotIn("GetStat(`dex`) < 12", filt.allow_exprs)

            rows = {
                r["champion_id"]: r
                for r in evaluate_heroes_against_filter([11, 12, 13], filt)
            }
            self.assertEqual(rows[11]["status"], "denied")
            self.assertEqual(rows[12]["status"], "allowed")
            self.assertEqual(rows[13]["status"], "allowed")

            gates = structured_stat_gates(filt)
            hard = [
                g
                for g in gates
                if g.get("stat") == "dex"
                and g.get("operator") == ">="
                and g.get("value") == 12
            ]
            self.assertTrue(hard)
            self.assertEqual(
                (hard[0].get("raw_predicate") or {}).get("predicate_kind"),
                "deny",
            )


if __name__ == "__main__":
    unittest.main()
