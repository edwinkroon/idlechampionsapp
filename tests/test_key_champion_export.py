"""Adventure key_champion: required Havilar + NPC/force_slot placeability."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.key_champion import (
    KeyChampionRule,
    bind_party_key_champions,
    hero_matches_key_champion_rule,
    parse_key_champion_rules,
    resolve_key_champion_seat_meta,
)
from ic_gamedata.formation_ai_advice.models import (
    SCHEMA_VERSION,
    AssignmentProposal,
    FormationAdviceProposal,
)
from ic_gamedata.formation_ai_advice.slot_states import (
    build_slot_states,
    derive_position_id_lists,
)
from ic_gamedata.formation_ai_advice.validate import validate_proposal_against_export
from ic_gamedata.adventure_restrictions import reserved_formation_seats


def _adv_416_define() -> dict[str, Any]:
    return {
        "id": 416,
        "name": "Tanking Expectations",
        "game_changes": [
            {"type": "has_save_data"},
            {
                "type": "key_champion",
                "by_tags": {"tags": "tanking"},
                "force_slot": True,
                "slot_id": 0,
                "hp": 1,
                "graphic": 1216,
                "name": "Shadow",
            },
            {
                "type": "only_allow_crusaders",
                "by_tags": {
                    "tags": "!tanking",
                    "blocked_portrait": 6280,
                },
            },
        ],
    }


def _payload(adventure_id: int = 416) -> dict[str, Any]:
    return {
        "details": {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": adventure_id,
                    "formation": [56, 3, 4, 5, 6, 7, 8, 0, 0, 0],
                    "hero_in_seats": {"10": 56, "1": 3, "2": 4},
                }
            ],
            "heroes": [{"hero_id": 56, "level": 100}],
        }
    }


class KeyChampionParseTests(unittest.TestCase):
    def test_parse_416_rule(self) -> None:
        rules = parse_key_champion_rules(
            _adv_416_define(),
            index_to_position={0: 3, 1: 1, 2: 2},
        )
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule.required_tags, frozenset({"tanking"}))
        self.assertTrue(rule.force_slot)
        self.assertEqual(rule.slot_index, 0)
        self.assertEqual(rule.position_id, 3)
        self.assertEqual(rule.name, "Shadow")

    def test_havilar_matches_tanking_tag(self) -> None:
        rule = KeyChampionRule(required_tags=frozenset({"tanking"}))
        with patch(
            "ic_gamedata.formation_ai_advice.key_champion._hero_tags",
            side_effect=lambda hid: (
                frozenset({"tanking", "support"})
                if hid == 56
                else frozenset({"dps"})
            ),
        ):
            self.assertTrue(hero_matches_key_champion_rule(56, rule))
            self.assertFalse(hero_matches_key_champion_rule(3, rule))


class KeyChampionLockTests(unittest.TestCase):
    """A — verplichte Havilar: replacement lock vs position lock."""

    def test_binding_replacement_not_position_from_force_slot(self) -> None:
        """force_slot/slot_id describe the NPC overlay — not champion position_lock."""
        rule = KeyChampionRule(
            required_tags=frozenset({"tanking"}),
            force_slot=True,
            slot_index=0,
            position_id=3,
            name="Shadow",
        )
        with patch(
            "ic_gamedata.formation_ai_advice.key_champion._hero_tags",
            return_value=frozenset({"tanking"}),
        ):
            # Havilar live on 10; NPC overlay resolves to technical 3.
            bindings = bind_party_key_champions(
                party_ids=[56, 3, 4],
                position_by_hero={56: 10, 3: 1, 4: 2},
                rules=[rule],
            )
        self.assertIn(56, bindings)
        b = bindings[56]
        self.assertTrue(b.replacement_locked)
        self.assertTrue(b.must_remain_in_party)
        self.assertFalse(b.position_locked)
        self.assertIsNone(b.locked_position_id)
        fields = b.as_export_fields()
        self.assertTrue(fields["locked"])
        self.assertEqual(fields["lock_reason"], "adventure_key_champion")
        self.assertTrue(fields["replacement_locked"])
        self.assertFalse(fields["position_locked"])
        self.assertNotIn("locked_position_id", fields)
        # Provenance may still record overlay force_slot/slot_id without locking.
        prov = fields["lock_provenance"]
        self.assertEqual(prov.get("kind"), "adventure_key_champion")
        self.assertNotIn("source", prov)
        self.assertNotIn("define_graphic_id", prov)
        self.assertNotIn("required_tags", prov)
        self.assertTrue(prov.get("force_slot"))
        self.assertEqual(prov.get("slot_id"), 0)

    def test_proposal_keeping_havilar_ok_moving_without_position_lock(self) -> None:
        export = {
            "meta": {"schema_version": SCHEMA_VERSION, "request_id": "r1"},
            "constraints": {"may_replace_champions": True},
            "party": [
                {
                    "id": 56,
                    "seat": 10,
                    "position": 1,
                    "replacement_locked": True,
                    "must_remain_in_party": True,
                    "position_locked": False,
                },
                {"id": 3, "seat": 1, "position": 2},
            ],
            "champions": [
                {"champion_id": 56, "seat": 10, "current_position": 1},
                {"champion_id": 3, "seat": 1, "current_position": 2},
            ],
            "formation": {
                "valid_position_ids": [1, 2, 4],
                "active_position_ids": [1, 2, 4],
                "slot_states": [
                    {
                        "position_id": 1,
                        "occupancy": "champion",
                        "placeability": "placeable",
                    },
                    {
                        "position_id": 2,
                        "occupancy": "champion",
                        "placeability": "placeable",
                    },
                    {
                        "position_id": 4,
                        "occupancy": "empty",
                        "placeability": "placeable",
                    },
                ],
                "current_champion_by_position": {"1": 56, "2": 3},
            },
        }
        # Move Havilar 1 → 4 (allowed: no position lock).
        proposal = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="r1",
            status="proposal",
            summary="keep havilar move",
            assignments=(
                AssignmentProposal(position_id=4, champion_id=56),
                AssignmentProposal(position_id=2, champion_id=3),
            ),
        )
        result = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request="a",
            current_formation_fingerprint="a",
        )
        lock_errors = [
            e
            for e in result.errors
            if "replacement" in e.casefold()
            or "position-locked" in e.casefold()
            or "verplichte" in e.casefold()
        ]
        self.assertEqual(lock_errors, [], result.errors)
        self.assertTrue(result.can_apply, result.errors)

    def test_proposal_dropping_havilar_fails(self) -> None:
        export = {
            "meta": {"schema_version": SCHEMA_VERSION, "request_id": "r1"},
            "constraints": {"may_replace_champions": True},
            "party": [
                {
                    "id": 56,
                    "seat": 10,
                    "position": 3,
                    "replacement_locked": True,
                    "must_remain_in_party": True,
                    "position_locked": True,
                    "locked_position_id": 3,
                },
                {"id": 3, "seat": 1, "position": 1},
            ],
            "formation": {
                "valid_position_ids": [1, 3, 4],
                "slot_states": [
                    {
                        "position_id": 1,
                        "occupancy": "champion",
                        "placeability": "placeable",
                    },
                    {
                        "position_id": 3,
                        "occupancy": "champion",
                        "placeability": "placeable",
                    },
                    {
                        "position_id": 4,
                        "occupancy": "empty",
                        "placeability": "placeable",
                    },
                ],
            },
        }
        # Replace Havilar (56) with seat-10 peer (99) — must fail.
        proposal = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="r1",
            status="proposal",
            summary="drop havilar",
            assignments=(
                AssignmentProposal(position_id=3, champion_id=99),
                AssignmentProposal(position_id=1, champion_id=3),
            ),
        )
        result = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request="a",
            current_formation_fingerprint="a",
        )
        self.assertFalse(result.can_apply)
        self.assertTrue(
            any("56" in e and "replacement" in e.casefold() for e in result.errors)
            or any("56" in e for e in result.errors),
            result.errors,
        )

    def test_proposal_moving_havilar_off_locked_position_fails(self) -> None:
        export = {
            "meta": {"schema_version": SCHEMA_VERSION, "request_id": "r1"},
            "constraints": {"may_replace_champions": True},
            "party": [
                {
                    "id": 56,
                    "seat": 10,
                    "position": 3,
                    "replacement_locked": True,
                    "must_remain_in_party": True,
                    "position_locked": True,
                    "locked_position_id": 3,
                },
            ],
            "formation": {
                "valid_position_ids": [3, 4],
                "slot_states": [
                    {
                        "position_id": 3,
                        "occupancy": "champion",
                        "placeability": "placeable",
                    },
                    {
                        "position_id": 4,
                        "occupancy": "empty",
                        "placeability": "placeable",
                    },
                ],
                "current_champion_by_position": {"3": 56},
            },
        }
        proposal = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="r1",
            status="proposal",
            summary="move locked",
            assignments=(AssignmentProposal(position_id=4, champion_id=56),),
        )
        result = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request="a",
            current_formation_fingerprint="a",
        )
        self.assertFalse(result.can_apply)
        self.assertTrue(
            any("position-locked" in e.casefold() or "locked" in e.casefold() for e in result.errors),
            result.errors,
        )


class KeyChampionNpcSlotTests(unittest.TestCase):
    """B — NPC/key_champion force_slot on position_id 3 / display 5-1."""

    def test_empty_force_slot_is_npc_blocked_not_available(self) -> None:
        states = build_slot_states(
            [1, 2, 3, 4],
            champion_by_position={1: 3},
            reserved_seats=[3],
            placeability_known=True,
            display_by_position={3: "5-1"},
            escort_meta_by_position={
                3: {
                    "type": "npc",
                    "name": "Shadow",
                    "graphic_id": 1216,
                    "source": "defines.adventure_defines.game_changes.key_champion",
                }
            },
        )
        by_id = {s["position_id"]: s for s in states}
        row = by_id[3]
        self.assertEqual(row["occupancy"], "npc")
        self.assertEqual(row["placeability"], "blocked")
        self.assertEqual(row.get("display_position"), "5-1")
        self.assertEqual((row.get("blocker") or {}).get("name"), "Shadow")
        derived = derive_position_id_lists(states)
        self.assertNotIn(3, derived["available_position_ids"])
        self.assertIn(3, derived["blocked_position_ids"])
        self.assertIn(2, derived["available_position_ids"])  # empty confirmed

    def test_placement_on_npc_slot_fails(self) -> None:
        states = build_slot_states(
            [3, 4],
            champion_by_position={},
            reserved_seats=[3],
            placeability_known=True,
            display_by_position={3: "5-1"},
            escort_meta_by_position={3: {"type": "npc", "name": "Shadow"}},
        )
        derived = derive_position_id_lists(states)
        export = {
            "meta": {"schema_version": SCHEMA_VERSION, "request_id": "r1"},
            "constraints": {"may_replace_champions": True},
            "party": [{"id": 56, "seat": 10, "position": 4}],
            "formation": {
                "valid_position_ids": [3, 4],
                "blocked_position_ids": derived["blocked_position_ids"],
                "available_position_ids": derived["available_position_ids"],
                "slot_states": states,
            },
        }
        proposal = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="r1",
            status="proposal",
            summary="place on npc",
            assignments=(AssignmentProposal(position_id=3, champion_id=56),),
        )
        result = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request="a",
            current_formation_fingerprint="a",
        )
        self.assertFalse(result.can_apply)
        self.assertTrue(
            any("3" in e or "geblokkeerd" in e.casefold() or "npc" in e.casefold() for e in result.errors),
            result.errors,
        )

    def test_required_champion_cannot_claim_npc_overlay_without_position_lock(self) -> None:
        """Replacement-locked Havilar still may not sit on the Shadow NPC seat."""
        states = build_slot_states(
            [3, 4, 10],
            champion_by_position={10: 56},
            reserved_seats=[3],
            placeability_known=True,
            display_by_position={3: "5-1", 10: "3-1"},
            escort_meta_by_position={
                3: {
                    "type": "npc",
                    "name": "Shadow",
                    "graphic_id": 1216,
                    "source": "defines.adventure_defines.game_changes.key_champion",
                }
            },
        )
        derived = derive_position_id_lists(states)
        export = {
            "meta": {"schema_version": SCHEMA_VERSION, "request_id": "r1"},
            "constraints": {"may_replace_champions": True, "fixed_champion_ids": [56]},
            "party": [
                {
                    "id": 56,
                    "seat": 10,
                    "position": 10,
                    "replacement_locked": True,
                    "must_remain_in_party": True,
                    "position_locked": False,
                    "lock_reason": "adventure_key_champion",
                    "lock_provenance": {
                        "kind": "adventure_key_champion",
                        "by_tags": "tanking",
                        "force_slot": True,
                        "slot_id": 0,
                    },
                }
            ],
            "formation": {
                "valid_position_ids": [3, 4, 10],
                "blocked_position_ids": derived["blocked_position_ids"],
                "available_position_ids": derived["available_position_ids"],
                "slot_states": states,
                "current_champion_by_position": {"10": 56},
            },
        }
        bad = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="r1",
            status="proposal",
            summary="havilar onto npc overlay",
            assignments=(AssignmentProposal(position_id=3, champion_id=56),),
        )
        result = validate_proposal_against_export(
            bad,
            export,
            api_sources=(),
            formation_fingerprint_at_request="a",
            current_formation_fingerprint="a",
        )
        self.assertFalse(result.can_apply)
        self.assertNotIn(3, derived["available_position_ids"])
        self.assertEqual(
            {s["position_id"]: s["occupancy"] for s in states if s["position_id"] in (3, 10)},
            {3: "npc", 10: "champion"},
        )


class DualPositionKeyChampionTests(unittest.TestCase):
    """Required champion and linked NPC occupy different technical positions."""

    def test_havilar_on_10_shadow_npc_on_3_no_false_position_lock(self) -> None:
        rule = KeyChampionRule(
            required_tags=frozenset({"tanking"}),
            force_slot=True,
            slot_index=0,
            position_id=3,
            name="Shadow",
            graphic_id=1216,
            raw_by_tags="tanking",
        )
        with patch(
            "ic_gamedata.formation_ai_advice.key_champion._hero_tags",
            return_value=frozenset({"tanking"}),
        ):
            bindings = bind_party_key_champions(
                party_ids=[56, 3],
                position_by_hero={56: 10, 3: 1},
                rules=[rule],
            )
        fields = bindings[56].as_export_fields()
        self.assertTrue(fields["replacement_locked"])
        self.assertTrue(fields["must_remain_in_party"])
        self.assertFalse(fields["position_locked"])
        self.assertNotIn("locked_position_id", fields)
        self.assertEqual(fields["lock_provenance"].get("force_slot"), True)
        self.assertEqual(fields["lock_provenance"].get("slot_id"), 0)

        states = build_slot_states(
            [1, 3, 4, 10],
            champion_by_position={10: 56, 1: 3},
            reserved_seats=[3],
            placeability_known=True,
            display_by_position={3: "5-1", 10: "3-1"},
            escort_meta_by_position={
                3: {
                    "type": "npc",
                    "name": "Shadow",
                    "graphic_id": 1216,
                }
            },
        )
        by_id = {s["position_id"]: s for s in states}
        self.assertEqual(by_id[3]["occupancy"], "npc")
        self.assertEqual(by_id[3]["placeability"], "blocked")
        self.assertEqual(by_id[3].get("display_position"), "5-1")
        self.assertEqual(by_id[10]["occupancy"], "champion")
        self.assertEqual(by_id[10].get("display_position"), "3-1")
        derived = derive_position_id_lists(states)
        self.assertNotIn(3, derived["available_position_ids"])
        self.assertIn(4, derived["available_position_ids"])

        export = {
            "meta": {"schema_version": SCHEMA_VERSION, "request_id": "r1"},
            "constraints": {"may_replace_champions": True, "fixed_champion_ids": [56]},
            "party": [
                {
                    "id": 56,
                    "seat": 10,
                    "position": 10,
                    **{
                        k: fields[k]
                        for k in (
                            "locked",
                            "lock_reason",
                            "replacement_locked",
                            "must_remain_in_party",
                            "position_locked",
                            "lock_provenance",
                        )
                        if k in fields
                    },
                },
                {"id": 3, "seat": 1, "position": 1},
            ],
            "formation": {
                "valid_position_ids": [1, 3, 4, 10],
                "blocked_position_ids": derived["blocked_position_ids"],
                "available_position_ids": derived["available_position_ids"],
                "slot_states": states,
                "current_champion_by_position": {"10": 56, "1": 3},
            },
        }
        # Move Havilar 10 → 4 (allowed: no position lock); keep NPC 3 blocked.
        ok = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="r1",
            status="proposal",
            summary="move havilar keep shadow npc",
            assignments=(
                AssignmentProposal(position_id=4, champion_id=56),
                AssignmentProposal(position_id=1, champion_id=3),
            ),
        )
        result = validate_proposal_against_export(
            ok,
            export,
            api_sources=(),
            formation_fingerprint_at_request="a",
            current_formation_fingerprint="a",
        )
        self.assertTrue(result.can_apply, result.errors)

        onto_npc = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="r1",
            status="proposal",
            summary="onto shadow",
            assignments=(
                AssignmentProposal(position_id=3, champion_id=56),
                AssignmentProposal(position_id=1, champion_id=3),
            ),
        )
        bad = validate_proposal_against_export(
            onto_npc,
            export,
            api_sources=(),
            formation_fingerprint_at_request="a",
            current_formation_fingerprint="a",
        )
        self.assertFalse(bad.can_apply)


class MissingSlotSourceTests(unittest.TestCase):
    """C — no slot_escort alone ≠ confirmed free when mapping unreliable."""

    def test_unreliable_mapping_stays_unknown(self) -> None:
        states = build_slot_states(
            [1, 2, 3],
            champion_by_position={},
            reserved_seats=[],
            placeability_known=True,
            escort_mapping_unreliable=True,
        )
        derived = derive_position_id_lists(states)
        self.assertEqual(derived["available_position_ids"], [])
        for row in states:
            self.assertEqual(row["placeability"], "unknown")
            self.assertEqual(row["occupancy"], "unknown")


class SnapshotPriorityTests(unittest.TestCase):
    """D — live key_champion block wins over empty snapshot occupancy."""

    def test_live_placeability_fields_include_blocked_from_slot_states(self) -> None:
        from ic_gamedata.formation_ai_advice.snapshot_export import (
            _live_placeability_fields,
        )

        full = {
            "slot_states": [
                {
                    "position_id": 3,
                    "occupancy": "npc",
                    "placeability": "blocked",
                    "display_position": "5-1",
                },
                {
                    "position_id": 4,
                    "occupancy": "empty",
                    "placeability": "placeable",
                },
            ],
            "available_position_ids": [4],
            "blocked_position_ids": [3],
            "occupied": [{"id": 1, "champion_id": 3}],
        }
        live = _live_placeability_fields(full)
        self.assertEqual(live["available_position_ids"], [4])
        self.assertEqual(live["blocked_position_ids"], [3])
        self.assertEqual(live["slot_states"][0]["occupancy"], "npc")


class RegressionTests(unittest.TestCase):
    """E — echte lege plek blijft vrij; gewone champ blijft vervangbaar."""

    def test_confirmed_empty_stays_available(self) -> None:
        states = build_slot_states(
            [1, 2],
            champion_by_position={1: 3},
            reserved_seats=[],
            placeability_known=True,
        )
        derived = derive_position_id_lists(states)
        self.assertEqual(derived["available_position_ids"], [2])

    def test_non_key_champion_not_bound(self) -> None:
        rule = KeyChampionRule(required_tags=frozenset({"tanking"}), force_slot=True, position_id=3)
        with patch(
            "ic_gamedata.formation_ai_advice.key_champion._hero_tags",
            return_value=frozenset({"dps"}),
        ):
            bindings = bind_party_key_champions(
                party_ids=[3],
                position_by_hero={3: 1},
                rules=[rule],
            )
        self.assertEqual(bindings, {})

    def test_reserved_formation_seats_merges_key_champion(self) -> None:
        payload = _payload(416)

        def _fake_define(_payload, adventure_id):
            return _adv_416_define() if adventure_id == 416 else None

        with patch(
            "ic_gamedata.adventure_restrictions._adventure_define",
            side_effect=_fake_define,
        ), patch(
            "ic_gamedata.formation_position_resolve.current_formation_index_map",
            return_value=({0: 3, 1: 1, 2: 2}, 10, ()),
        ), patch(
            "ic_gamedata.formation_position_resolve.resolve_slot_escort_seats",
        ) as escort:
            from ic_gamedata.formation_position_resolve import EscortSeatResolution

            escort.return_value = EscortSeatResolution(
                define_found=True, escort_changes_present=False
            )
            seats = reserved_formation_seats(payload, 416)
        self.assertIn(3, seats)


class KeyChampionResolveMetaTests(unittest.TestCase):
    def test_resolve_meta_for_416(self) -> None:
        payload = _payload(416)

        def _fake_define(_payload, adventure_id):
            return _adv_416_define() if adventure_id == 416 else None

        with patch(
            "ic_gamedata.adventure_restrictions._adventure_define",
            side_effect=_fake_define,
        ), patch(
            "ic_gamedata.formation_position_resolve.current_formation_index_map",
            return_value=({0: 3}, 10, ()),
        ):
            positions, meta, warnings = resolve_key_champion_seat_meta(payload, 416)
        self.assertEqual(positions, frozenset({3}))
        self.assertEqual(meta[3].get("name"), "Shadow")
        self.assertEqual(meta[3].get("type"), "npc")
        self.assertEqual(warnings, ())


if __name__ == "__main__":
    unittest.main()
