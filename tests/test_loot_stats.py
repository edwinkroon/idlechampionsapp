"""Tests for loot-derived formation equipment stats."""

from __future__ import annotations

import unittest

from ic_gamedata.loot_stats import (
    HeroLootStats,
    formation_loot_stack_totals,
    hero_loot_stats_from_items,
    loot_stats_by_hero,
)


class LootStatsTests(unittest.TestCase):
    def test_hero_loot_stats_caps_ilvl_per_hero(self) -> None:
        items = {
            (1, slot): {"hero_id": 1, "slot_id": slot, "rarity": 4, "gild": 0, "enchant": 400}
            for slot in range(1, 7)
        }
        items[(1, 2)] = {"hero_id": 1, "slot_id": 2, "rarity": 3, "gild": 1, "enchant": 50}
        stats = hero_loot_stats_from_items(items, 1)
        self.assertEqual(stats.epic_gear_count, 5)
        self.assertEqual(stats.shiny_gear_count, 1)
        self.assertEqual(stats.total_ilvl, 1800)

    def test_loot_stats_by_hero_picks_best_item_per_slot(self) -> None:
        details = {
            "loot": [
                {"hero_id": 1, "slot_id": 1, "rarity": 3, "gild": 0, "enchant": 10},
                {"hero_id": 1, "slot_id": 1, "rarity": 4, "gild": 0, "enchant": 10},
                {"hero_id": 1, "slot_id": 2, "rarity": 2, "gild": 1, "enchant": 5},
            ]
        }
        stats = loot_stats_by_hero(details)[1]
        self.assertEqual(stats.epic_gear_count, 1)
        self.assertEqual(stats.shiny_gear_count, 1)
        self.assertEqual(stats.total_ilvl, 17)

    def test_formation_totals_sum_active_heroes(self) -> None:
        loot = {
            1: HeroLootStats(epic_gear_count=2, shiny_gear_count=1, total_ilvl=100),
            2: HeroLootStats(epic_gear_count=3, shiny_gear_count=0, total_ilvl=200),
        }
        epic, ilvl, shiny = formation_loot_stack_totals({1, 2, 99}, loot)
        self.assertEqual((epic, ilvl, shiny), (5, 300, 1))


if __name__ == "__main__":
    unittest.main()
