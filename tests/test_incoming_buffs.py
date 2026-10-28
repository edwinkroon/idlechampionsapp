"""Incoming buffs toward a selected main DPS."""

from __future__ import annotations

import unittest

from ic_gamedata.formation_ai_advice.incoming_buffs import (
    format_incoming_buffs_clipboard,
    mechanic_reaches_main_dps,
)
from ic_gamedata.formation_advisor.models import (
    FormationLayoutContext,
    FormationTopology,
)


def _ctx(
    *,
    seats: dict[int, int],
    columns: dict[int, int],
    adjacency: dict[int, frozenset[int]],
    roles: dict[int, tuple[str, ...]] | None = None,
    tags: dict[int, tuple[str, ...]] | None = None,
    names: dict[int, str] | None = None,
) -> FormationLayoutContext:
    topo = FormationTopology(
        seat_adjacency=adjacency,
        seat_column=columns,
        seat_zone={s: "mid" for s in columns},
        source="test",
    )
    return FormationLayoutContext(
        active_hero_ids=frozenset(seats),
        seat_by_hero=seats,
        hero_name_by_id=names or {hid: f"H{hid}" for hid in seats},
        hero_roles_by_id=roles or {hid: ("dps",) if hid == 4 else ("support",) for hid in seats},
        hero_tags_by_id=tags or {hid: () for hid in seats},
        carry_hero_id=4,
        highest_damage_hero_id=4,
        topology=topo,
        run_goal="push",
        context="campaign",
        goal="push",
        party_size=len(seats),
        formation_capacity=len(seats),
        owned_hero_ids=frozenset(seats),
        allowed_bench_ids=frozenset(),
    )


class IncomingBuffReachTests(unittest.TestCase):
    def setUp(self) -> None:
        # Seats: buffer 1 col0, dps 4 col1 adjacent, far support 2 col3
        self.ctx = _ctx(
            seats={10: 1, 4: 2, 20: 5},
            columns={1: 0, 2: 1, 5: 3},
            adjacency={
                1: frozenset({2}),
                2: frozenset({1}),
                # Non-empty so topology does not fall back to default diamond.
                5: frozenset({6}),
            },
            roles={10: ("support",), 4: ("dps",), 20: ("support",)},
            tags={10: ("buffer",), 4: (), 20: ("buffer",)},
            names={10: "Buffer", 4: "Carry", 20: "Far"},
        )

    def test_global_buff_reaches_dps(self) -> None:
        row = {
            "name": "Party damage",
            "effect_facts": {"effect_scope": "global", "targets": ["all"]},
        }
        reach, _ = mechanic_reaches_main_dps(
            row, ctx=self.ctx, owner_id=10, dps_id=4
        )
        self.assertEqual(reach, "yes")

    def test_adjacent_buff_only_when_adjacent(self) -> None:
        row = {
            "name": "Adj",
            "effect_facts": {
                "effect_scope": "positional",
                "targets": ["adj"],
                "semantics": {"scope": "positional", "recipients": {"targets": ["adj"]}},
            },
        }
        yes, _ = mechanic_reaches_main_dps(row, ctx=self.ctx, owner_id=10, dps_id=4)
        no, _ = mechanic_reaches_main_dps(row, ctx=self.ctx, owner_id=20, dps_id=4)
        self.assertEqual(yes, "yes")
        self.assertEqual(no, "no")

    def test_owner_scope_does_not_count_as_incoming(self) -> None:
        row = {
            "name": "Self",
            "effect_facts": {"effect_scope": "owner", "targets": ["self"]},
        }
        reach, _ = mechanic_reaches_main_dps(
            row, ctx=self.ctx, owner_id=10, dps_id=4
        )
        self.assertEqual(reach, "no")

    def test_clipboard_format_lists_incoming(self) -> None:
        report = {
            "ok": True,
            "main_dps_name": "Carry",
            "main_dps_seat": 2,
            "main_dps_column": 1,
            "incoming": [
                {
                    "owner_name": "Buffer",
                    "owner_seat": 1,
                    "kind": "ability",
                    "name": "Rally",
                    "effect": "Buffs adjacent champions.",
                    "reason": "targeting ['adj']",
                }
            ],
            "own": [],
            "uncertain": [],
        }
        text = format_incoming_buffs_clipboard(report)
        self.assertIn("Inkomende buffs → Carry", text)
        self.assertIn("Rally", text)
        self.assertIn("Buffs adjacent champions.", text)


if __name__ == "__main__":
    unittest.main()
