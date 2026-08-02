"""Tests for multiply-stack specialization audit."""

from __future__ import annotations

import unittest

from ic_gamedata.specialization_stack_audit import audit_qualified_stack_specs


class SpecializationStackAuditTests(unittest.TestCase):
    def test_audit_marks_umberto_handled_when_handler_registered(self) -> None:
        handled = {151, 164, 159}
        tiers = audit_qualified_stack_specs(handled_hero_ids=handled)
        umberto = [
            tier
            for tier in tiers
            if tier.hero_id == 151 and tier.required_level == 200
        ]
        self.assertEqual(len(umberto), 1)
        self.assertEqual(umberto[0].status, "handled")
        self.assertEqual(len(umberto[0].options), 3)

    def test_audit_marks_umberto_generic_without_custom_handler(self) -> None:
        tiers = audit_qualified_stack_specs(handled_hero_ids=set())
        umberto = [
            tier
            for tier in tiers
            if tier.hero_id == 151 and tier.required_level == 200
        ]
        self.assertEqual(len(umberto), 1)
        self.assertEqual(umberto[0].status, "handled")
        self.assertIn("generic", umberto[0].notes)

    def test_audit_marks_vlithryn_custom_for_per_unique_race(self) -> None:
        tiers = audit_qualified_stack_specs(handled_hero_ids=set())
        vlithryn = [
            tier
            for tier in tiers
            if tier.hero_id == 162 and tier.required_level == 80
        ]
        self.assertEqual(len(vlithryn), 1)
        self.assertEqual(vlithryn[0].status, "custom")

    def test_audit_marks_beadle_handled_when_handler_registered(self) -> None:
        from ic_gamedata.specialization_engine import HERO_HANDLERS

        tiers = audit_qualified_stack_specs(handled_hero_ids=set(HERO_HANDLERS))
        beadle = [tier for tier in tiers if tier.hero_id == 64 and tier.required_level == 160]
        self.assertEqual(len(beadle), 1)
        self.assertEqual(beadle[0].status, "handled")
        self.assertEqual(len(beadle[0].options), 3)


if __name__ == "__main__":
    unittest.main()
