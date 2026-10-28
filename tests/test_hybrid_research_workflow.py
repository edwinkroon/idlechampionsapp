"""Hybrid research mode + by_attack_types + research_gaps regressions."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
    build_adventure_roster_filter,
    evaluate_heroes_against_filter,
    is_hero_allowed,
)
from ic_gamedata.formation_ai_advice.clipboard_export import (
    format_clipboard_markdown,
    format_swap_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.export import (
    _attach_research_gaps,
    _readiness_issues,
    build_export_payload,
)
from ic_gamedata.formation_ai_advice.research_mode import (
    RESEARCH_MODE_HYBRID,
    RESEARCH_MODE_PROVIDED_ONLY,
    allows_targeted_public_research,
    normalize_research_mode,
    research_gaps_from_unevaluable_rules,
    research_mode_instruction_lines,
)


def _meta(hid: int, *, attack_types: frozenset[str], int_score: int = 14):
    return type(
        "M",
        (),
        {
            "hero_id": hid,
            "roles": frozenset(),
            "tags": frozenset(),
            "stats": {
                "str": 10,
                "dex": 10,
                "con": 10,
                "int": int_score,
                "wis": 10,
                "cha": 10,
            },
            "attack_types": attack_types,
            "age": None,
            "all_tags": frozenset(),
        },
    )()


class ResearchModeTests(unittest.TestCase):
    def test_provided_data_only_forbids_external_research_instructions(self) -> None:
        """1) provided_data_only stays research-free."""
        lines = research_mode_instruction_lines(RESEARCH_MODE_PROVIDED_ONLY)
        self.assertEqual(lines, [])
        self.assertFalse(allows_targeted_public_research(RESEARCH_MODE_PROVIDED_ONLY))
        export = {
            "meta": {
                "schema_version": "1.9",
                "request_id": "r1",
                "research_mode": RESEARCH_MODE_PROVIDED_ONLY,
            },
            "goal": {
                "id": "push",
                "label": "Push",
                "description": "d",
                "priorities": ["p"],
                "primary_metric": "m",
            },
            "formation": {"positions": []},
            "champions": [],
        }
        # Minimal clipboard path via instruction helper only.
        joined = "\n".join(
            [
                "Gebruik BASE_SNAPSHOT",
                *research_mode_instruction_lines(RESEARCH_MODE_PROVIDED_ONLY),
            ]
        )
        self.assertNotIn("Hybride researchmodus", joined)
        self.assertNotIn("webonderzoek", joined.casefold())

    def test_hybrid_mode_emits_targeted_research_instructions(self) -> None:
        """2) Hybrid mode gives targeted research instructions."""
        lines = research_mode_instruction_lines(RESEARCH_MODE_HYBRID)
        blob = "\n".join(lines)
        self.assertIn("Hybride researchmodus", blob)
        self.assertIn("research_gaps", blob)
        self.assertIn("niet automatisch als allowed", blob)
        self.assertTrue(allows_targeted_public_research(RESEARCH_MODE_HYBRID))
        self.assertEqual(
            normalize_research_mode("provided_data_plus_targeted_research"),
            RESEARCH_MODE_HYBRID,
        )


class ByAttackTypesTests(unittest.TestCase):
    def test_adventure_211_disallow_magic_evaluates_locally(self) -> None:
        """by_attack_types is evaluated from base attack damage types."""
        payload = {
            "defines": {
                "adventure_defines": [
                    {
                        "id": 211,
                        "name": "We're not in Faerûn Anymore",
                        "restrictions_text": (
                            "Only Champions with melee or ranged base attacks "
                            "can be used."
                        ),
                        "game_changes": [
                            {
                                "type": "disallow_crusaders",
                                "by_attack_types": {
                                    "attack_types": ["magic"],
                                    "blocked_portrait": 6341,
                                },
                            }
                        ],
                    }
                ]
            },
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 211,
                        "current_patron_id": 0,
                        "formation": [],
                    }
                ],
                "heroes": [
                    {"hero_id": 20, "owned": "1"},
                    {"hero_id": 57, "owned": "1"},
                ],
            },
        }
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(
                hid,
                attack_types=frozenset({"melee"} if hid == 20 else {"magic"}),
            ),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            filt = build_adventure_roster_filter(payload, 211)
            self.assertEqual(filt.banned_attack_types, {"magic"})
            self.assertFalse(filt.has_unevaluable_roster_rules)
            self.assertTrue(is_hero_allowed(20, filt))
            self.assertFalse(is_hero_allowed(57, filt))
            self.assertEqual(
                evaluate_heroes_against_filter([57], filt)[0]["status"], "denied"
            )

    def test_unhandled_predicate_exports_raw_params_once(self) -> None:
        """3+4+8) Unevaluable predicate keeps raw params; not invented; one row."""
        payload = {
            "defines": {
                "adventure_defines": [
                    {
                        "id": 9002,
                        "game_changes": [
                            {
                                "type": "only_allow_crusaders",
                                "by_popularity": {"min": 3},
                            }
                        ],
                    }
                ]
            },
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 9002,
                        "current_patron_id": 0,
                        "formation": [],
                    }
                ],
                "heroes": [{"hero_id": 3, "owned": "1"}],
            },
        }
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, attack_types=frozenset({"melee"})),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            filt = build_adventure_roster_filter(payload, 9002)
            self.assertEqual(len(filt.unevaluable_rules), 1)
            rule = filt.unevaluable_rules[0]
            self.assertEqual(rule["predicate"], "by_popularity")
            self.assertEqual(rule["raw"], {"min": 3})
            self.assertNotIn("fabricated", str(rule).casefold())
            # Missing keys are absent, not invented.
            self.assertNotIn("max", rule.get("raw") or {})

    def test_unknown_essential_rule_stays_unknown(self) -> None:
        """5) Unknown essential rule → unknown, not allowed."""
        filt = AdventureRosterFilter(
            has_unknown_rules=True,
            has_unevaluable_roster_rules=True,
            unevaluable_rules=[
                {
                    "id": "urule_1",
                    "predicate": "by_foo",
                    "change_type": "disallow_crusaders",
                    "raw": {"x": 1},
                }
            ],
        )
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, attack_types=frozenset({"melee"})),
        ):
            self.assertFalse(is_hero_allowed(3, filt))
            self.assertEqual(
                evaluate_heroes_against_filter([3], filt)[0]["status"], "unknown"
            )

    def test_proven_denied_not_promoted_to_allowed(self) -> None:
        """6) Denied by attack type stays denied."""
        filt = AdventureRosterFilter(banned_attack_types={"magic"})
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, attack_types=frozenset({"magic"})),
        ):
            self.assertFalse(is_hero_allowed(57, filt))

    def test_force_allow_exception_within_scope(self) -> None:
        """7) Force-allow still bypasses attack-type ban."""
        filt = AdventureRosterFilter(
            banned_attack_types={"magic"},
            exempt_hero_ids={102},
        )
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, attack_types=frozenset({"magic"})),
        ):
            self.assertTrue(is_hero_allowed(102, filt))
            self.assertFalse(is_hero_allowed(57, filt))


class ResearchGapsAndReadinessTests(unittest.TestCase):
    def test_research_gaps_dedupe_rules_not_per_candidate(self) -> None:
        """8) One gap per rule; candidate count is summary only."""
        gaps = research_gaps_from_unevaluable_rules(
            [
                {
                    "id": "urule_1",
                    "predicate": "by_foo",
                    "change_type": "disallow_crusaders",
                    "raw": {"a": 1},
                    "why_local_unknown": "not implemented",
                }
            ],
            adventure_id=211,
            unknown_candidate_count=50,
            unknown_candidate_sample_ids=list(range(1, 60)),
        )
        assert gaps is not None
        self.assertEqual(len(gaps["gaps"]), 1)
        self.assertEqual(gaps["gaps"][0]["unknown_candidate_count"], 50)
        self.assertEqual(len(gaps["gaps"][0]["unknown_candidate_sample_ids"]), 8)

    def test_readiness_separates_party_placement_from_incomplete_swap(self) -> None:
        """9) Party placement usable while local swap coverage incomplete."""
        export = {
            "meta": {
                "research_mode": RESEARCH_MODE_PROVIDED_ONLY,
                "scope": "owned_roster_one_swap_search",
            },
            "goal": {
                "restrictions_checked_by_app": True,
                "restrictions_fully_known": False,
                "party_restriction_status": "ok",
                "structured_restrictions": {
                    "has_unevaluable_roster_rules": True,
                    "unevaluable_rules": [
                        {
                            "id": "urule_1",
                            "predicate": "by_foo",
                            "raw": {"x": 1},
                        }
                    ],
                },
            },
            "formation": {
                "positions": [1, 2],
                "active_positions": [1, 2],
                "valid_position_ids": [1, 2],
                "adjacency": {1: [2], 2: [1]},
                "geometry_issues": [],
            },
            "champions": [
                {
                    "champion_id": 3,
                    "name": "Nayeli",
                    "current_position": 1,
                    "permanent_seat": 1,
                    "eligibility": {"effective_eligibility": "allowed"},
                }
            ],
            "candidates": [
                {
                    "champion_id": 57,
                    "eligibility": {"effective_eligibility": "unknown"},
                }
            ],
            "research_gaps": {"gaps": [{"id": "urule_1"}]},
        }
        status, issues, dimensions = _readiness_issues(export)
        self.assertEqual(status, "ready_with_warnings")
        self.assertEqual(dimensions.get("local_swap_coverage"), "incomplete_unknown_rules")
        self.assertEqual(dimensions.get("public_research"), "needed_but_mode_forbids")
        codes = {i.get("code") for i in issues}
        self.assertIn("local_swap_coverage_incomplete", codes)

    def test_external_findings_do_not_auto_change_local_eligibility(self) -> None:
        """10) research_gaps note forbids silent local promotion."""
        export: dict = {
            "goal": {
                "adventure_id": 1,
                "structured_restrictions": {
                    "unevaluable_rules": [
                        {
                            "id": "urule_1",
                            "predicate": "by_foo",
                            "raw": {"x": 1},
                        }
                    ]
                },
            },
            "champions": [],
            "candidates": [],
        }
        _attach_research_gaps(export, research_mode=RESEARCH_MODE_HYBRID)
        note = (export.get("research_gaps") or {}).get("local_eligibility_note") or ""
        self.assertIn("niet automatisch", note.casefold())
        self.assertTrue((export.get("research_gaps") or {}).get("public_research_allowed"))

    def test_context_switch_rebuilds_gaps_without_stale_cache(self) -> None:
        """11) No public-rules knowledge cache yet — gaps rebuild from filter."""
        # Documented: optional cache is a follow-up; ensure builder is pure.
        a = research_gaps_from_unevaluable_rules(
            [{"id": "urule_1", "predicate": "by_foo", "raw": {"a": 1}}],
            adventure_id=211,
        )
        b = research_gaps_from_unevaluable_rules(
            [{"id": "urule_1", "predicate": "by_bar", "raw": {"b": 2}}],
            adventure_id=805,
        )
        assert a is not None and b is not None
        self.assertEqual(a["gaps"][0]["predicate"], "by_foo")
        self.assertEqual(b["gaps"][0]["predicate"], "by_bar")
        self.assertNotEqual(
            a["gaps"][0]["needed_context"].get("adventure_id"),
            b["gaps"][0]["needed_context"].get("adventure_id"),
        )


if __name__ == "__main__":
    unittest.main()
