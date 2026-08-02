"""Tests for Briv gear parser, zone calculator, and Co-Pilot phases."""

from __future__ import annotations

import unittest

from ic_gamedata.gem_farm.briv_calculator import BrivHeuristics, advise_briv_zones
from ic_gamedata.gem_farm.briv_gear import parse_briv_slot4_from_payload
from ic_gamedata.gem_farm.copilot_advisor import build_copilot_advice
from ic_gamedata.gem_farm.models import BrivGear, FarmHealthStatus, FarmProfile
from ic_gamedata.gem_farm.phase_detector import detect_copilot_phase


class BrivGearParserTests(unittest.TestCase):
    def test_parse_slot4_from_loot(self) -> None:
        payload = {
            "details": {
                "loot": [
                    {
                        "hero_id": 58,
                        "slot_id": 4,
                        "rarity": 4,
                        "gild": 1,
                        "enchant": 499,
                    }
                ]
            }
        }
        gear = parse_briv_slot4_from_payload(payload)
        self.assertIsNotNone(gear)
        assert gear is not None
        self.assertEqual(gear.enchant, 499)
        self.assertEqual(gear.item_level, 500)
        self.assertEqual(gear.rarity, 4)
        self.assertEqual(gear.gild, 1)
        self.assertEqual(gear.source, "api")


class BrivCalculatorTests(unittest.TestCase):
    def test_advise_zones_conservative(self) -> None:
        gear = BrivGear(
            hero_id=58,
            slot_id=4,
            enchant=499,
            item_level=500,
            item_level_label="500",
            rarity=4,
            rarity_label="Epic",
            gild=1,
            gild_label="Shiny",
            source="test",
        )
        advice = advise_briv_zones(
            modron_goal=300,
            gear=gear,
            heuristics=BrivHeuristics(
                reset_buffer=15,
                stack_above_reset_min=14,
                stack_above_reset_max=24,
                conservative_margin=8,
                enchant_buckets=((999999999, 3500000000),),
            ),
        )
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertLess(advice.reset_zone, 300)
        self.assertLess(advice.stack_zone_recommended, advice.reset_zone)
        self.assertLessEqual(advice.stack_zone_min, advice.stack_zone_recommended)
        self.assertLessEqual(advice.stack_zone_recommended, advice.stack_zone_max)


class CopilotPhaseTests(unittest.TestCase):
    def test_progress_phase(self) -> None:
        from ic_gamedata.gem_farm.briv_calculator import advise_briv_zones

        advice = advise_briv_zones(modron_goal=300, gear=None)
        assert advice is not None
        phase = detect_copilot_phase(
            is_active=True,
            modron_goal=300,
            briv_in_formation=True,
            current_area=200,
            briv_stacks=1_000_000,
            zone_advice=advice,
            profile=FarmProfile(stack_zone=280, reset_zone=285),
            health=FarmHealthStatus(1, "ok", True, ()),
        )
        self.assertIsNotNone(phase)
        assert phase is not None
        self.assertEqual(phase.phase, "progress")
        advice_text = build_copilot_advice(phase)
        self.assertIsNotNone(advice_text)
        assert advice_text is not None
        self.assertIn("Q", advice_text.detail)
        self.assertIn("adviseert alleen", advice_text.detail)

    def test_phase_timeline_sends_w_then_e(self) -> None:
        from ic_gamedata.gem_farm.copilot_keys import should_send_on_phase_change

        advice = advise_briv_zones(
            modron_goal=300,
            gear=None,
            heuristics=BrivHeuristics(
                reset_buffer=15,
                stack_above_reset_min=14,
                stack_above_reset_max=24,
                conservative_margin=8,
                phase_margin=5,
                jump_buffer=5,
            ),
        )
        assert advice is not None
        self.assertLess(advice.stack_zone_recommended, advice.reset_zone)

        prev = None
        keys: list[str] = []
        for area in range(100, advice.modron_goal + 1, 5):
            phase = detect_copilot_phase(
                is_active=True,
                modron_goal=300,
                briv_in_formation=True,
                current_area=area,
                briv_stacks=48,
                zone_advice=advice,
                profile=None,
                health=None,
            )
            assert phase is not None
            key = should_send_on_phase_change(
                previous_phase=prev,
                new_phase=phase.phase,
                send_keys_enabled=True,
            )
            if key:
                keys.append(key)
            prev = phase.phase
        self.assertEqual(keys, ["Q", "W", "E"])


if __name__ == "__main__":
    unittest.main()
