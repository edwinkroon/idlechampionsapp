"""Tests for party gear / ilvl investment priority."""

from __future__ import annotations

import unittest

from ic_gamedata.gear_investment import recommend_gear_investment
from ic_gamedata.party_advisor_models import FormationHero


def _hero(
    hid: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
    tags: tuple[str, ...] = (),
    ilvl: int = 1000,
    ilvl_pct_vs_avg: float = 0.0,
    is_top_damage: bool = False,
    highest_damage: float = 0.0,
) -> FormationHero:
    return FormationHero(
        hero_id=hid,
        name=name,
        seat=seat,
        level=100,
        gear_score=float(ilvl),
        ilvl=ilvl,
        ilvl_pct_vs_avg=ilvl_pct_vs_avg,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label=f"ilvl {ilvl}",
        role_label=roles[0].capitalize() if roles else "Unknown",
        roles=roles,
        tags=tags,
        highest_damage=highest_damage,
        active_feats=1,
        is_top_damage=is_top_damage,
    )


class GearInvestmentTests(unittest.TestCase):
    def test_prefers_bud_carry(self) -> None:
        formation = (
            _hero(1, "Carry", 1, roles=("dps",), ilvl=1200, is_top_damage=True, highest_damage=1e20),
            _hero(2, "Tank", 2, roles=("tank",), ilvl=900, ilvl_pct_vs_avg=-20.0),
            _hero(3, "Support", 3, roles=("support",), tags=("buffer",), ilvl=1100),
        )
        advice = recommend_gear_investment(formation, goal="bud")
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertEqual(advice.hero_name, "Carry")
        self.assertIn("BUD / top-damage", advice.reason)
        self.assertIn("ilvl 1200", advice.reason)

    def test_catch_up_important_support_when_far_behind(self) -> None:
        # Carry already fat; debuffer critically behind → catch-up wins.
        formation = (
            _hero(
                1,
                "Carry",
                1,
                roles=("dps",),
                ilvl=2000,
                ilvl_pct_vs_avg=40.0,
                is_top_damage=True,
                highest_damage=1e20,
            ),
            _hero(
                2,
                "Krull",
                2,
                roles=("support",),
                tags=("debuffer",),
                ilvl=400,
                ilvl_pct_vs_avg=-60.0,
            ),
            _hero(3, "Tank", 3, roles=("tank",), ilvl=1500, ilvl_pct_vs_avg=10.0),
        )
        advice = recommend_gear_investment(formation, goal="bud")
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertEqual(advice.hero_name, "Krull")

    def test_speed_goal_prefers_speed_champ(self) -> None:
        formation = (
            _hero(1, "Dps", 1, roles=("dps",), ilvl=1500, is_top_damage=True, highest_damage=1e20),
            _hero(2, "Briv", 2, roles=("support",), tags=("speed",), ilvl=800, ilvl_pct_vs_avg=-20.0),
        )
        advice = recommend_gear_investment(formation, goal="speed")
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertEqual(advice.hero_name, "Briv")

    def test_empty_formation(self) -> None:
        self.assertIsNone(recommend_gear_investment((), goal="bud"))


if __name__ == "__main__":
    unittest.main()
