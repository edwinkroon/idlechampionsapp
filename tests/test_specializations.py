"""Tests for specialization rules and pending-choice detection."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.specializations import (
    SpecializationOption,
    _current_choices,
    format_specialization_advice,
    load_specialization_rules,
    pending_specializations,
)
from ic_gamedata.specialization_models import PendingSpecialization


class SpecializationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base = Path(__file__).resolve().parent.parent
        cls.payload = json.loads((base / "webRequestLog_example.json").read_text(encoding="utf-8"))
        cls.rules = load_specialization_rules()

    def test_rules_file_loads(self) -> None:
        self.assertIn("heroes", self.rules)
        self.assertIn("147", self.rules["heroes"])

    def test_example_payload_has_no_pending_specializations(self) -> None:
        pending = pending_specializations(self.payload, self.rules)
        self.assertEqual(pending, [])

    def test_current_choices_merges_upgrades_and_specialization_choices(self) -> None:
        options = [
            SpecializationOption(14576, "Tier 0 A", 100, 0),
            SpecializationOption(14580, "Tier 1 A", 200, 1),
        ]
        hero = {"specialization_choices": [14576], "upgrades": [14580, 99999]}
        self.assertEqual(_current_choices(hero, options), (14576, 14580))

    def test_current_choices_accepts_string_and_dict_ids(self) -> None:
        options = [SpecializationOption(14576, "Tier 0 A", 100, 0)]
        hero = {
            "specialization_choices": ["14576"],
            "upgrades": [{"upgrade_id": 99999}],
        }
        self.assertEqual(_current_choices(hero, options), (14576,))

    def test_pending_clears_tier_when_choice_not_in_known_options_filter(self) -> None:
        """Raw upgrade ids must still complete a tier even if _current_choices filters strictly."""
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 147}
        gale = next(h for h in details["heroes"] if int(h["hero_id"]) == 147)
        gale["game_instance_id"] = 0
        gale["in_seat"] = 1
        gale["level"] = 300
        gale["specialization_choices"] = ["14576"]
        gale["upgrades"] = []

        pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].options[0].tier_index, 1)

    def test_pending_clears_all_tiers_after_full_choice(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 147}
        gale = next(h for h in details["heroes"] if int(h["hero_id"]) == 147)
        gale["game_instance_id"] = 0
        gale["in_seat"] = 1
        gale["level"] = 300
        gale["specialization_choices"] = [14576, 14580]
        gale["upgrades"] = []

        pending = pending_specializations(payload, self.rules)
        self.assertEqual(pending, [])

    def test_pending_clears_tier_when_choice_only_in_upgrades(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 147}
        gale = next(h for h in details["heroes"] if int(h["hero_id"]) == 147)
        gale["game_instance_id"] = 1
        gale["in_seat"] = 1
        gale["level"] = 300
        gale["specialization_choices"] = []
        gale["upgrades"] = [14576]

        pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].options[0].tier_index, 1)

    def test_format_advice_hides_items_without_actionable_choice(self) -> None:
        pending = [
            PendingSpecialization(
                hero_id=1,
                hero_name="Test",
                seat=1,
                game_instance_id=1,
                current_choices=(),
                options=(SpecializationOption(1001, "A", 50, 0),),
                desired_upgrade_id=None,
                desired_option_index=None,
                reason="geen regel",
                rationale="Geen regel",
            )
        ]
        text = format_specialization_advice({}, pending)
        self.assertEqual(text, "Geen specialization-advies nodig.")

    def test_detects_pending_tier_when_level_is_high_enough(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 147}
        gale = next(
            h
            for h in details["heroes"]
            if int(h["hero_id"]) == 147 and int(h["game_instance_id"]) == 1
        )
        gale["game_instance_id"] = 1
        gale["in_seat"] = 1
        gale["level"] = 300
        gale["specialization_choices"] = [14576]

        pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        item = pending[0]
        self.assertEqual(item.hero_id, 147)
        self.assertEqual(item.desired_upgrade_id, 14580)
        self.assertEqual(item.desired_option_index, 2)
        self.assertEqual([opt.upgrade_id for opt in item.options], [14578, 14579, 14580])

    def test_missing_rule_uses_baseline_choice_when_options_exist(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 99999}

        rules = json.loads(json.dumps(self.rules))
        rules["heroes"]["99999"] = {
            "name": "Placeholder Hero",
            "options": [
                {"upgrade_id": 1001, "name": "A", "required_level": 50, "tier_index": 0},
                {"upgrade_id": 1002, "name": "B", "required_level": 50, "tier_index": 0},
            ]
        }
        details["heroes"] = [
            {
                "hero_id": 99999,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 999,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        pending = pending_specializations(payload, rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 1001)
        self.assertIn("basis-regel", pending[0].rationale)

    def test_cached_definitions_fallback_detects_pending_specialization(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 26}
        details["heroes"].append(
            {
                "hero_id": 26,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        )
        payload["defines"]["upgrade_defines"] = []

        fallback = {
            26: [
                SpecializationOption(12210, "Fighting Style: Protection", 240, 0),
                SpecializationOption(12211, "Compel Duel", 240, 0),
                SpecializationOption(12212, "Lathander's Allies", 240, 0),
            ]
        }
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].hero_name, "Evelyn")
        self.assertEqual(
            [opt.name for opt in pending[0].options],
            ["Fighting Style: Protection", "Compel Duel", "Lathander's Allies"],
        )

    def test_pending_uses_real_seat_number_from_hero_in_seats(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"6": 62}
        payload["details"]["heroes"] = [
            {
                "hero_id": 62,
                "game_instance_id": 1,
                "in_seat": 0,
                "level": 400,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            62: [
                SpecializationOption(8753, "New Recruits", 300, 0),
                SpecializationOption(8754, "Tight Knit", 300, 0),
            ]
        }
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].seat, 6)

    def test_evelyn_prefers_protection_when_another_tank_is_present(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 26, "2": 19}
        payload["details"]["heroes"] = [
            {
                "hero_id": 26,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            },
            {
                "hero_id": 19,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            },
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            26: [
                SpecializationOption(12210, "Fighting Style: Protection", 240, 0),
                SpecializationOption(12211, "Compel Duel", 240, 0),
                SpecializationOption(12212, "Lathander's Allies", 240, 0),
            ]
        }
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        evelyn = next(item for item in pending if item.hero_id == 26)
        self.assertEqual(evelyn.desired_upgrade_id, 12210)

    def test_evelyn_prefers_lathanders_allies_with_affiliation_team(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 26, "2": 41, "3": 500}
        payload["details"]["heroes"] = [
            {
                "hero_id": 26,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            26: [
                SpecializationOption(12210, "Fighting Style: Protection", 240, 0),
                SpecializationOption(12211, "Compel Duel", 240, 0),
                SpecializationOption(12212, "Lathander's Allies", 240, 0),
            ]
        }
        fake_tags = {
            26: ("acqinc", "wafflecrew"),
            41: ("cteam",),
            500: ("wafflecrew",),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
        ):
            pending = pending_specializations(payload, self.rules)
        evelyn = next(item for item in pending if item.hero_id == 26)
        self.assertEqual(evelyn.desired_upgrade_id, 12212)

    def test_bruenor_prefers_csv_authored_default_over_engine_handler(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 1}
        inst["stats"] = {"this_reset_highest_damage_dealt_hero_id": 1}
        payload["details"]["heroes"] = [
            {
                "hero_id": 1,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 7)
        self.assertEqual(pending[0].data_source_version, "v2_full")
        self.assertEqual(pending[0].rule_source_type, "authored")
        self.assertIn("csv-regel", pending[0].rationale)

    def test_wyll_prefers_tome_for_magic_heavy_party(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 142, "2": 168, "3": 999}
        payload["details"]["heroes"] = [
            {
                "hero_id": 142,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            142: [
                SpecializationOption(13433, "Pact of the Blade", 110, 0),
                SpecializationOption(13434, "Pact of the Chain", 110, 0),
                SpecializationOption(13435, "Pact of the Tome", 110, 0),
            ]
        }
        fake_types = {
            142: frozenset({"melee", "magic"}),
            168: frozenset({"melee", "magic"}),
            999: frozenset({"magic"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 13435)

    def test_wyll_prefers_blade_for_melee_heavy_party(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 142, "2": 1, "3": 3, "4": 25}
        payload["details"]["heroes"] = [
            {
                "hero_id": 142,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            142: [
                SpecializationOption(13433, "Pact of the Blade", 110, 0),
                SpecializationOption(13434, "Pact of the Chain", 110, 0),
                SpecializationOption(13435, "Pact of the Tome", 110, 0),
            ]
        }
        fake_types = {
            142: frozenset({"melee", "magic"}),
            1: frozenset({"melee"}),
            3: frozenset({"melee"}),
            25: frozenset({"melee"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 13433)

    def test_wyll_prefers_chain_with_many_familiars(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 142, "2": 999}
        payload["details"]["heroes"] = [
            {
                "hero_id": 142,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["details"]["familiars"] = [
            {"familiar_id": str(i), "assignment": {"Clicks": 0, "game_instance_id": 1}}
            for i in range(6)
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            142: [
                SpecializationOption(13433, "Pact of the Blade", 110, 0),
                SpecializationOption(13434, "Pact of the Chain", 110, 0),
                SpecializationOption(13435, "Pact of the Tome", 110, 0),
            ]
        }
        fake_types = {
            142: frozenset({"melee", "magic"}),
            999: frozenset({"magic"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 13434)

    def test_tess_prefers_ranged_when_highest_qualified_score(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 164, "2": 901, "3": 902, "4": 903}
        payload["details"]["heroes"] = [
            {
                "hero_id": 164,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            164: [
                SpecializationOption(17321, "The Fallback Plan", 150, 0),
                SpecializationOption(17322, "Eyes on the Horizon", 150, 0),
                SpecializationOption(17323, "Rogues' Gallery", 150, 0),
            ]
        }
        fake_tags = {
            164: ("fallbacks", "rogue"),
            901: ("unaffiliated",),
            902: ("unaffiliated",),
            903: ("rogue",),
        }
        fake_types = {
            164: frozenset({"ranged"}),
            901: frozenset({"ranged"}),
            902: frozenset({"ranged"}),
            903: frozenset({"melee"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        # fallback: (2.5)^3, ranged: (3.0)^3, rogue: (3.5)^2
        self.assertEqual(pending[0].desired_upgrade_id, 17322)

    def test_tess_prefers_fallback_plan_with_many_unaffiliated(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 164, **{str(seat): 900 + seat for seat in range(2, 11)}}
        payload["details"]["heroes"] = [
            {
                "hero_id": 164,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            164: [
                SpecializationOption(17321, "The Fallback Plan", 150, 0),
                SpecializationOption(17322, "Eyes on the Horizon", 150, 0),
                SpecializationOption(17323, "Rogues' Gallery", 150, 0),
            ]
        }
        fake_tags = {
            164: ("fallbacks", "rogue"),
            910: ("companion",),
        }
        fake_types = {
            164: frozenset({"ranged"}),
            903: frozenset({"ranged"}),
        }
        for seat in range(2, 10):
            hero_id = 900 + seat
            fake_tags[hero_id] = ("unaffiliated",)
            fake_types.setdefault(hero_id, frozenset({"melee"}))
        fake_tags[902] = ("unaffiliated", "rogue")
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_champion_config", return_value={}),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        # fallback: 9, ranged: 2, rogue: 2 → Fallback Plan (matches in-game qualified counts)
        self.assertEqual(pending[0].desired_upgrade_id, 17321)

    def test_umberto_prefers_family_of_orphans_with_many_unaffiliated(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {
            "1": 151,
            "2": 902,
            "3": 903,
            "4": 904,
            "5": 905,
            "6": 906,
            "7": 907,
            "8": 908,
            "9": 909,
            "10": 910,
        }
        payload["details"]["heroes"] = [
            {
                "hero_id": 151,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 250,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            151: [
                SpecializationOption(15052, "Law's Alliance", 200, 0),
                SpecializationOption(15053, "Family of Orphans", 200, 0),
                SpecializationOption(15054, "Call of the Wardens", 200, 0),
            ]
        }
        fake_tags = {
            151: ("druid", "lawful"),
            902: ("ranger",),
            909: ("lawful",),
            910: ("lawful",),
        }
        for hero_id in range(903, 909):
            fake_tags[hero_id] = ("unaffiliated",)
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_champion_config", return_value={}),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        # lawful: 3, unaffiliated: 6, ranger/druid: 2 → Family of Orphans
        self.assertEqual(pending[0].desired_upgrade_id, 15053)

    def test_cazrin_prefers_ancestors_shadow_with_good_and_fallback_party(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 166, **{str(i): 900 + i for i in range(2, 11)}}
        payload["details"]["heroes"] = [
            {
                "hero_id": 166,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 250,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            166: [
                SpecializationOption(17678, "Self Taught", 180, 0),
                SpecializationOption(17679, "Ancestor's Shadow", 180, 0),
                SpecializationOption(17680, "Lost in the Library", 180, 0),
            ]
        }
        fake_tags = {166: ("fallbacks",)}
        fake_types = {166: frozenset({"magic"})}
        for hero_id in range(902, 907):
            fake_tags[hero_id] = ("good", "fallbacks")
            fake_types[hero_id] = frozenset({"melee"})
        for hero_id in range(907, 911):
            fake_tags[hero_id] = ("good",)
            fake_types[hero_id] = frozenset({"magic"})
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
            patch("ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.adventure_restrictions.hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules, run_goal="bud")
        cazrin = [
            item
            for item in pending
            if item.hero_id == 166 and item.options and item.options[0].tier_index == 0
        ]
        self.assertEqual(len(cazrin), 1)
        # Self Taught: 6 qualified, Ancestor's Shadow: 10 qualified → Ancestor's Shadow
        self.assertEqual(cazrin[0].desired_upgrade_id, 17679)
        self.assertIn("Ancestor's Shadow", cazrin[0].rationale)

    def test_beadle_prefers_premium_gear_with_high_ilvl_formation(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 64, "2": 901, "3": 902}
        payload["details"]["heroes"] = [
            {
                "hero_id": 64,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 200,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        payload["details"]["loot"] = [
            {"hero_id": hero_id, "slot_id": slot, "rarity": 4, "gild": 0, "enchant": 400}
            for hero_id in (64, 901, 902)
            for slot in range(1, 7)
        ]
        beadle_opts = {
            64: [
                SpecializationOption(16727, "Epic Equipment", 160, 0),
                SpecializationOption(16728, "Premium Gear", 160, 0),
                SpecializationOption(16729, "Shiniest Loot", 160, 0),
            ]
        }
        with patch(
            "ic_gamedata.specializations._choices_from_cached_definitions",
            return_value=beadle_opts,
        ):
            pending = pending_specializations(payload, self.rules)
        beadle = [item for item in pending if item.hero_id == 64]
        self.assertEqual(len(beadle), 1)
        self.assertEqual(beadle[0].desired_upgrade_id, 16728)

    def test_beadle_prefers_shiniest_loot_with_many_shiny_pieces(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 64, **{str(i): 900 + i for i in range(2, 11)}}
        payload["details"]["heroes"] = [
            {
                "hero_id": 64,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 200,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        payload["details"]["loot"] = [
            {"hero_id": hero_id, "slot_id": 1, "rarity": 4, "gild": 1, "enchant": 0}
            for hero_id in [64, *range(901, 910)]
        ]
        beadle_opts = {
            64: [
                SpecializationOption(16727, "Epic Equipment", 160, 0),
                SpecializationOption(16728, "Premium Gear", 160, 0),
                SpecializationOption(16729, "Shiniest Loot", 160, 0),
            ]
        }
        with patch(
            "ic_gamedata.specializations._choices_from_cached_definitions",
            return_value=beadle_opts,
        ):
            pending = pending_specializations(payload, self.rules)
        beadle = [item for item in pending if item.hero_id == 64]
        self.assertEqual(len(beadle), 1)
        self.assertEqual(beadle[0].desired_upgrade_id, 16729)

    def test_tess_prefers_rogues_gallery_with_many_rogues(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 164, "2": 910, "3": 911, "4": 912}
        payload["details"]["heroes"] = [
            {
                "hero_id": 164,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            164: [
                SpecializationOption(17321, "The Fallback Plan", 150, 0),
                SpecializationOption(17322, "Eyes on the Horizon", 150, 0),
                SpecializationOption(17323, "Rogues' Gallery", 150, 0),
            ]
        }
        fake_tags = {
            164: ("fallbacks", "rogue"),
            910: ("rogue",),
            911: ("rogue",),
            912: ("rogue",),
        }
        fake_types = {
            164: frozenset({"ranged"}),
            910: frozenset({"melee"}),
            911: frozenset({"melee"}),
            912: frozenset({"melee"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        # fallback: (2.5)^1, ranged: (3.0)^1, rogue: (3.5)^4
        self.assertEqual(pending[0].desired_upgrade_id, 17323)

    def test_kos_prefers_master_of_pawns_with_allies_behind(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 168, "2": 901, "3": 902, "6": 903}
        payload["details"]["heroes"] = [
            {
                "hero_id": 168,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 400,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            168: [
                SpecializationOption(17762, "Master of Pawns", 210, 0),
                SpecializationOption(17763, "Shadow Unleashed", 210, 0),
                SpecializationOption(17764, "Legacy of Illefarn", 280, 1),
                SpecializationOption(17765, "Embrace the Shadow Weave", 280, 1),
                SpecializationOption(17766, "Rites of Survival", 280, 1),
            ]
        }
        fake_tags = {
            168: ("evil", "human"),
            901: ("evil",),
            902: ("evil",),
            903: ("evil",),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
        ):
            pending = pending_specializations(payload, self.rules)
        tier0 = next(item for item in pending if item.hero_id == 168 and item.options[0].tier_index == 0)
        tier1 = next(item for item in pending if item.hero_id == 168 and item.options[0].tier_index == 1)
        # seats 2,3 are cols 2/3 behind KoS at seat 1 -> 3 beneficiaries -> Master of Pawns
        self.assertEqual(tier0.desired_upgrade_id, 17762)
        # 4 evil * 200 = 800 beats legacy/healing
        self.assertEqual(tier1.desired_upgrade_id, 17765)

    def test_kos_prefers_shadow_unleashed_when_he_carries(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 168, "5": 901}
        inst["stats"] = {"this_reset_highest_damage_dealt_hero_id": 168}
        payload["details"]["heroes"] = [
            {
                "hero_id": 168,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 400,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            168: [
                SpecializationOption(17762, "Master of Pawns", 210, 0),
                SpecializationOption(17763, "Shadow Unleashed", 210, 0),
            ]
        }
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        tier0 = next(item for item in pending if item.hero_id == 168)
        # 0 beneficiaries behind, KoS is top damage -> Shadow Unleashed
        self.assertEqual(tier0.desired_upgrade_id, 17763)

    def test_catti_prefers_critical_family_with_companions(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 25, "2": 1, "3": 900}
        payload["details"]["heroes"] = [
            {
                "hero_id": 25,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            25: [
                SpecializationOption(11312, "Piercing Arrow", 220, 0),
                SpecializationOption(11313, "Big Push", 220, 0),
                SpecializationOption(11314, "Critical Family", 220, 0),
            ]
        }
        fake_tags = {
            25: ("companion",),
            1: ("companion",),
            900: ("companion",),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 11314)

    def test_nova_defaults_to_tight_knit(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 62}
        payload["details"]["heroes"] = [
            {
                "hero_id": 62,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 400,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            62: [
                SpecializationOption(8753, "New Recruits", 300, 0),
                SpecializationOption(8754, "Tight Knit", 300, 0),
            ]
        }
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 8754)

    def test_widdle_prefers_best_ability_score_bucket(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 91, "2": 142, "3": 162}
        inst["stats"] = {"this_reset_highest_damage_dealt_hero_id": 142}
        payload["details"]["heroes"] = [
            {
                "hero_id": 91,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 400,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            91: [
                SpecializationOption(6909, "Strong and Steady", 310, 0),
                SpecializationOption(6910, "Mind and Body", 310, 0),
                SpecializationOption(6911, "Wisdom and Confidence", 310, 0),
            ]
        }
        fake_scores = {
            91: {"str": 18, "dex": 15, "con": 13, "int": 17, "wis": 12, "cha": 11},
            142: {"str": 8, "dex": 14, "con": 10, "int": 18, "wis": 12, "cha": 14},
            162: {"str": 10, "dex": 10, "con": 14, "int": 12, "wis": 16, "cha": 12},
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions", return_value=fake_scores),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 6910)

    def test_astarion_defaults_cover_both_specialization_tiers(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"10": 129}
        payload["details"]["heroes"] = [
            {
                "hero_id": 129,
                "game_instance_id": 1,
                "in_seat": 10,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            129: [
                SpecializationOption(12493, "Outflank (Top)", 10, 0),
                SpecializationOption(12494, "Outflank (Bottom)", 10, 0),
                SpecializationOption(12495, "Thief", 200, 1),
                SpecializationOption(12496, "Arcane Trickster", 200, 1),
                SpecializationOption(12497, "Assassin", 200, 1),
            ]
        }
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 2)
        self.assertEqual([item.desired_upgrade_id for item in pending], [12493, 12495])
        self.assertEqual(pending[0].data_source_version, "v2_full")
        self.assertEqual(pending[0].rule_source_type, "authored")

    def test_missing_config_uses_baseline_choice_from_hero_profile(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"4": 4}
        payload["details"]["heroes"] = [
            {
                "hero_id": 4,
                "game_instance_id": 1,
                "in_seat": 4,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            4: [
                SpecializationOption(4001, "Battle Training", 20, 0),
                SpecializationOption(4002, "Get Rich Quick", 20, 0),
            ]
        }
        rules = json.loads(json.dumps(self.rules))
        rules["heroes"].pop("4", None)
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 4002)
        self.assertIn("basis-regel", pending[0].rationale)

    def test_skylla_prefers_league_with_multiple_evil_champions(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"4": 169, "8": 128, "10": 173, "11": 2000}
        payload["details"]["heroes"] = [
            {
                "hero_id": 169,
                "game_instance_id": 1,
                "in_seat": 4,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            169: [
                SpecializationOption(17848, "Witch's Switch", 110, 0),
                SpecializationOption(17849, "League of Malevolence", 110, 0),
                SpecializationOption(17850, "Withering Ward", 110, 0),
                SpecializationOption(17851, "Green Fire", 200, 1),
                SpecializationOption(17852, "Blue Fire", 200, 1),
                SpecializationOption(17853, "Violet Fire", 200, 1),
            ]
        }
        fake_tags = {
            169: ("evil", "debuff"),
            128: ("evil",),
            173: ("evil",),
            2000: ("good",),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
        ):
            pending = pending_specializations(payload, self.rules)
        skylla = next(item for item in pending if item.hero_id == 169 and item.options[0].tier_index == 0)
        skylla_fire = next(item for item in pending if item.hero_id == 169 and item.options[0].tier_index == 1)
        self.assertEqual(skylla.desired_upgrade_id, 17849)
        self.assertEqual(skylla_fire.desired_upgrade_id, 17851)

    def test_skylla_prefers_withering_ward_over_witch_switch_in_campaign(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"4": 169, "8": 69, "10": 50, "11": 176}
        payload["details"]["heroes"] = [
            {
                "hero_id": 169,
                "game_instance_id": 1,
                "in_seat": 4,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            169: [
                SpecializationOption(17848, "Witch's Switch", 110, 0),
                SpecializationOption(17849, "League of Malevolence", 110, 0),
                SpecializationOption(17850, "Withering Ward", 110, 0),
                SpecializationOption(17851, "Green Fire", 200, 1),
            ]
        }
        fake_scores = {
            169: {"str": 9, "dex": 11, "con": 14, "int": 12, "wis": 15, "cha": 17},
            69: {"str": 8, "dex": 10, "con": 16, "int": 18, "wis": 9, "cha": 17},
            50: {"str": 7, "dex": 9, "con": 15, "int": 17, "wis": 8, "cha": 16},
            176: {"str": 6, "dex": 8, "con": 14, "int": 16, "wis": 7, "cha": 15},
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value=fake_scores,
            ),
        ):
            pending = pending_specializations(payload, self.rules, context="campaign")
        skylla = next(item for item in pending if item.hero_id == 169 and item.options[0].tier_index == 0)
        self.assertEqual(skylla.desired_upgrade_id, 17850)

    def test_skylla_prefers_witch_switch_in_variant_with_strong_swaps(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"4": 169, "8": 69, "10": 50, "11": 176}
        payload["details"]["heroes"] = [
            {
                "hero_id": 169,
                "game_instance_id": 1,
                "in_seat": 4,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            169: [
                SpecializationOption(17848, "Witch's Switch", 110, 0),
                SpecializationOption(17849, "League of Malevolence", 110, 0),
                SpecializationOption(17850, "Withering Ward", 110, 0),
                SpecializationOption(17851, "Green Fire", 200, 1),
            ]
        }
        fake_scores = {
            169: {"str": 9, "dex": 11, "con": 14, "int": 12, "wis": 15, "cha": 17},
            69: {"str": 8, "dex": 10, "con": 16, "int": 18, "wis": 9, "cha": 17},
            50: {"str": 7, "dex": 9, "con": 15, "int": 17, "wis": 8, "cha": 16},
            176: {"str": 6, "dex": 8, "con": 14, "int": 16, "wis": 7, "cha": 15},
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value=fake_scores,
            ),
        ):
            pending = pending_specializations(payload, self.rules, context="variant")
        skylla = next(item for item in pending if item.hero_id == 169 and item.options[0].tier_index == 0)
        self.assertEqual(skylla.desired_upgrade_id, 17848)

    def test_vlithryn_prefers_spreading_when_species_score_wins(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        # 4 unique species, only 2 with INT <= 12 → Spreading 4*300=1200 vs Who Else 2*200=400
        inst["hero_in_seats"] = {"1": 162, "2": 901, "3": 902, "4": 903}
        payload["details"]["heroes"] = [
            {
                "hero_id": 162,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 200,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            162: [
                SpecializationOption(17048, "Who Else Would Save Them?", 80, 0),
                SpecializationOption(17049, "Help the Unfortunate", 80, 0),
                SpecializationOption(17050, "Spreading the Word", 80, 0),
            ]
        }
        fake_tags = {
            162: ("triton",),
            901: ("human",),
            902: ("dwarf",),
            903: ("tiefling",),
        }
        fake_scores = {
            # High totals so Help the Unfortunate does not win on accident.
            162: {"str": 16, "dex": 14, "con": 16, "int": 15, "wis": 16, "cha": 14},  # 91
            901: {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},  # 60, INT<=12
            902: {"str": 16, "dex": 14, "con": 16, "int": 8, "wis": 14, "cha": 14},  # 82, INT<=12
            903: {"str": 14, "dex": 16, "con": 14, "int": 14, "wis": 14, "cha": 16},  # 88
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions", return_value=fake_scores),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 17050)

    def test_vlithryn_prefers_who_else_when_low_int_score_wins(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        # Same species twice + Vlithryn: 2 unique species (2*300=600) vs 4 low-INT (4*200=800)
        inst["hero_in_seats"] = {"1": 162, "2": 901, "3": 902, "4": 903}
        payload["details"]["heroes"] = [
            {
                "hero_id": 162,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 200,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            162: [
                SpecializationOption(17048, "Who Else Would Save Them?", 80, 0),
                SpecializationOption(17049, "Help the Unfortunate", 80, 0),
                SpecializationOption(17050, "Spreading the Word", 80, 0),
            ]
        }
        fake_tags = {
            162: ("human",),
            901: ("human",),
            902: ("human",),
            903: ("dwarf",),
        }
        fake_scores = {
            # All INT <= 12, but totals above 78 so Help does not dominate.
            162: {"str": 16, "dex": 14, "con": 16, "int": 10, "wis": 14, "cha": 14},  # 84
            901: {"str": 16, "dex": 14, "con": 16, "int": 8, "wis": 14, "cha": 14},  # 82
            902: {"str": 16, "dex": 14, "con": 16, "int": 9, "wis": 14, "cha": 14},  # 83
            903: {"str": 16, "dex": 14, "con": 16, "int": 11, "wis": 14, "cha": 14},  # 85
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions", return_value=fake_scores),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 17048)

    def test_volo_prefers_magical_when_magic_count_wins(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        # 1 hunter (+Volo after Spirits = 2) vs 4 magic → Magical wins
        inst["hero_in_seats"] = {"1": 159, "2": 901, "3": 902, "4": 903}
        payload["details"]["heroes"] = [
            {
                "hero_id": 159,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 200,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            159: [
                SpecializationOption(16554, "Volo's Guide to Spirits and Specters", 150, 0),
                SpecializationOption(16555, "Volo's Guide to Brain-Eating Tadpoles", 150, 0),
                SpecializationOption(16556, "Volo's Guide to All Things Magical", 150, 0),
            ]
        }
        fake_tags = {
            159: ("human", "support"),
            901: ("hunter",),
            902: ("support",),
            903: ("support",),
        }
        fake_types = {
            159: frozenset({"magic"}),
            901: frozenset({"melee"}),
            902: frozenset({"magic"}),
            903: frozenset({"magic"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_champion_config", return_value={}),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 16556)

    def test_volo_prefers_spirits_when_hunter_count_wins(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        # 3 hunters + Volo becoming hunter = 4 vs 1 magic → Spirits wins
        inst["hero_in_seats"] = {"1": 159, "2": 901, "3": 902, "4": 903}
        payload["details"]["heroes"] = [
            {
                "hero_id": 159,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 200,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        fallback = {
            159: [
                SpecializationOption(16554, "Volo's Guide to Spirits and Specters", 150, 0),
                SpecializationOption(16555, "Volo's Guide to Brain-Eating Tadpoles", 150, 0),
                SpecializationOption(16556, "Volo's Guide to All Things Magical", 150, 0),
            ]
        }
        fake_tags = {
            159: ("human", "support"),
            901: ("hunter",),
            902: ("hunter",),
            903: ("hunter",),
        }
        fake_types = {
            159: frozenset({"magic"}),
            901: frozenset({"melee"}),
            902: frozenset({"ranged"}),
            903: frozenset({"melee"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_champion_config", return_value={}),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].desired_upgrade_id, 16554)

    def test_merged_hero_record_uses_roster_row_specialization_choices(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 147}
        party_gale = next(
            h for h in details["heroes"] if int(h["hero_id"]) == 147 and int(h["game_instance_id"]) == 1
        )
        party_gale["level"] = 300
        party_gale["specialization_choices"] = []
        party_gale["upgrades"] = []
        details["heroes"].append(
            {
                "hero_id": 147,
                "game_instance_id": 0,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [14576],
                "upgrades": [],
            }
        )

        pending = pending_specializations(payload, self.rules)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].options[0].tier_index, 1)
        self.assertEqual(pending[0].desired_upgrade_id, 14580)

    def test_duplicate_party_rows_produce_single_pending_entry_per_tier(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 147}
        party_gale = next(
            h for h in details["heroes"] if int(h["hero_id"]) == 147 and int(h["game_instance_id"]) == 1
        )
        party_gale["level"] = 300
        party_gale["specialization_choices"] = []
        details["heroes"].append(
            {
                "hero_id": 147,
                "game_instance_id": 0,
                "in_seat": 1,
                "level": 300,
                "specialization_choices": [],
                "upgrades": [],
            }
        )

        pending = pending_specializations(payload, self.rules)
        tier0 = [item for item in pending if item.hero_id == 147 and item.options[0].tier_index == 0]
        self.assertEqual(len(tier0), 1)

    def test_pending_specializations_follow_active_party(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst1 = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst1["hero_in_seats"] = {"1": 147}

        details["game_instances"].append(
            {
                "game_instance_id": 2,
                "hero_in_seats": {"1": 173},
                "formation": [173, -1, -1, -1, -1, -1, -1, -1, -1],
                "current_adventure_id": 14,
            }
        )
        for hero in details["heroes"]:
            if not isinstance(hero, dict):
                continue
            hid = int(hero["hero_id"])
            if hid == 147:
                hero["level"] = 300
                hero["specialization_choices"] = []
                hero["game_instance_id"] = 1
                hero["in_seat"] = 1
            elif hid == 173:
                hero["level"] = 300
                hero["specialization_choices"] = []
                hero["game_instance_id"] = 2
                hero["in_seat"] = 1
            else:
                hero["in_seat"] = 0

        pending_party1 = pending_specializations(payload, self.rules)
        details["active_game_instance_id"] = 2
        pending_party2 = pending_specializations(payload, self.rules)

        party1_ids = {item.hero_id for item in pending_party1}
        party2_ids = {item.hero_id for item in pending_party2}
        self.assertIn(147, party1_ids)
        self.assertNotIn(147, party2_ids)
        self.assertIn(173, party2_ids)
        self.assertNotIn(173, party1_ids)

    def _van_richten_options(self) -> list[SpecializationOption]:
        return [
            SpecializationOption(19700, "Occult Allies", 120, 0),
            SpecializationOption(19701, "Scholar of Dread", 120, 0),
            SpecializationOption(19702, "Endless Hunt", 120, 0),
            SpecializationOption(19703, "Occult Aid: Cure Wounds", 220, 1),
            SpecializationOption(19704, "Occult Aid: Dispel Evil", 220, 1),
            SpecializationOption(19705, "Occult Aid: Sanctuary", 220, 1),
        ]

    def _van_richten_pending_payload(
        self,
        *,
        seats: dict[str, int],
        specialization_choices: list[int],
    ) -> dict:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = seats
        hero_ids = {int(seat_id) for seat_id in seats.values()}
        payload["details"]["heroes"] = [
            {
                "hero_id": hero_id,
                "game_instance_id": 1,
                "in_seat": next(int(seat) for seat, hid in seats.items() if int(hid) == hero_id),
                "level": 400,
                "specialization_choices": specialization_choices if hero_id == 177 else [],
                "upgrades": [],
            }
            for hero_id in sorted(hero_ids)
        ]
        payload["defines"]["upgrade_defines"] = []
        return payload

    def test_van_richten_tier1_pending_recommends_dispel_evil(self) -> None:
        payload = self._van_richten_pending_payload(
            seats={"3": 177, "2": 2, "6": 5, "4": 4},
            specialization_choices=[19702],
        )
        fallback = {177: self._van_richten_options()}
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        tier1 = next(item for item in pending if item.hero_id == 177 and item.options[0].tier_index == 1)
        self.assertEqual(tier1.desired_upgrade_id, 19704)
        self.assertIsNotNone(tier1.desired_option_index)

    def test_van_richten_tier1_pending_recommends_cure_wounds_without_healers(self) -> None:
        payload = self._van_richten_pending_payload(
            seats={"1": 177, "2": 4, "3": 6, "4": 7},
            specialization_choices=[19702],
        )
        fallback = {177: self._van_richten_options()}
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        tier1 = next(item for item in pending if item.hero_id == 177 and item.options[0].tier_index == 1)
        self.assertEqual(tier1.desired_upgrade_id, 19703)

    def test_van_richten_tier1_pending_recommends_sanctuary_for_front_non_tanks(self) -> None:
        payload = self._van_richten_pending_payload(
            seats={"1": 3, "5": 177, "9": 4, "2": 2, "6": 5},
            specialization_choices=[19702],
        )
        fallback = {177: self._van_richten_options()}
        with patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value=fallback):
            pending = pending_specializations(payload, self.rules)
        tier1 = next(item for item in pending if item.hero_id == 177 and item.options[0].tier_index == 1)
        self.assertEqual(tier1.desired_upgrade_id, 19705)


if __name__ == "__main__":
    unittest.main()
