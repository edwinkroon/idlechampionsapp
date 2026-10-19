"""Generic mechanic completeness for ADVICE_REQUEST (+ Baeloth/Ulkoria regression)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.compact_clipboard import (
    build_advice_request_clipboard_text,
)
from ic_gamedata.formation_ai_advice.export import (
    _effect_description_text,
    _effect_defines_by_id,
    _mechanic_fields_from_upgrade,
    _upgrade_row_map,
)
from ic_gamedata.formation_ai_advice.export_budget import DEFAULT_CHAR_BUDGET, count_chars
from ic_gamedata.formation_ai_advice.mechanics_completeness import (
    _looks_like_export_preview_truncation,
    build_mechanics_completeness,
    compact_mechanics_for_clipboard,
    omit_oversized_effects_for_budget,
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
        role_label="Support",
        roles=("support",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class EffectDescriptionShapeTests(unittest.TestCase):
    def test_top_level_conditions_extracted(self) -> None:
        row = {
            "description": {
                "conditions": [
                    {
                        "condition": "upgrade_purchased 4749",
                        "desc": "Gated variant with +4 stacks.^More text",
                    },
                    {
                        "desc": "Base: columns front/behind get damage per stack.^Cap note",
                    },
                ]
            }
        }
        text = _effect_description_text(row)
        self.assertIsNotNone(text)
        assert text is not None
        # Prefer unconditional base when present.
        self.assertIn("Base: columns front/behind", text)
        self.assertNotIn("Gated variant", text)
        self.assertIn("\n", text)

    def test_baeloth_4747_resolves_from_conditions(self) -> None:
        upgrades = _upgrade_row_map()
        row = upgrades.get(4747)
        if row is None:
            self.skipTest("Baeloth upgrade 4747 missing from definitions")
        fields = _mechanic_fields_from_upgrade(row)
        text = fields.get("mechanical_text") or ""
        self.assertTrue(text.strip(), msg="Morbid Excitement still has no prose")
        self.assertIn("Morbid Excitement", text)
        self.assertIn("column", text.casefold())
        # Missing numeric placeholders ≠ missing mechanic.
        self.assertNotEqual(fields.get("usability"), "missing")

    def test_ulkoria_4350_uses_spec_description_not_attack_id(self) -> None:
        upgrades = _upgrade_row_map()
        row = upgrades.get(4350)
        if row is None:
            self.skipTest("Ulkoria option 4350 missing from definitions")
        fields = _mechanic_fields_from_upgrade(row)
        text = (fields.get("mechanical_text") or "").casefold()
        self.assertFalse(text.startswith("sets attack id to"))
        self.assertIn("urchin", text)
        self.assertIn("ultimate", text)


class MechanicsCompletenessUnitTests(unittest.TestCase):
    def test_option_without_effect_reports_gap(self) -> None:
        entries = {
            1: {
                "champion_id": 1,
                "specialization_groups": [
                    {
                        "group_id": "tier_0",
                        "options": [
                            {"option_id": 900001, "name": "Empty Opt"},
                            {"option_id": 900002, "name": "Other Opt"},
                        ],
                    }
                ],
            }
        }
        # Snapshot has neither option body.
        snap = {"shared": {"specialization_options": {}}, "champions": [{"id": 1}]}
        with patch(
            "ic_gamedata.formation_ai_advice.mechanics_completeness._live_projected",
            side_effect=lambda uid, kind, owner_name=None: {
                "id": uid,
                "name": f"Opt {uid}",
                "advice_hint": "Keuze open — effect ontbreekt.",
            },
        ):
            block = build_mechanics_completeness(
                party_ids=[1],
                entries_by_id=entries,
                base_snapshot=snap,
            )
        gaps = block.get("mechanic_gaps") or []
        ids = {g["id"] for g in gaps}
        self.assertIn(900001, ids)
        self.assertIn(900002, ids)

    def test_shared_missing_dependency_limits_comparison(self) -> None:
        entries = {
            73: {
                "champion_id": 73,
                "name": "Baeloth",
                "specialization_groups": [
                    {
                        "group_id": "tier_0",
                        "options": [
                            {"option_id": 4749, "name": "Birthday Party"},
                            {"option_id": 4750, "name": "Over Excited"},
                        ],
                    }
                ],
                "abilities": [{"ability_id": 4747, "name": "Morbid Excitement"}],
            }
        }
        # Snapshot: options present, ability missing effect (old bug shape).
        snap = {
            "shared": {
                "abilities": {
                    "4747": {
                        "name": "Morbid Excitement",
                        "advice_hint": "Effect ontbreekt — bijdrage niet volledig te beoordelen.",
                    }
                },
                "specialization_options": {
                    "4749": {
                        "name": "Birthday Party",
                        "effect": "buffs Morbid Excitement",
                        "depends_on_upgrade_ids": [4747],
                    },
                    "4750": {
                        "name": "Over Excited",
                        "effect": "more stacks",
                        "depends_on_upgrade_ids": [4747],
                    },
                },
            },
            "champions": [{"id": 73}],
        }
        block = build_mechanics_completeness(
            party_ids=[73],
            entries_by_id=entries,
            base_snapshot=snap,
        )
        delta = block.get("mechanics_delta") or []
        # Live re-resolve should supplement 4747 when definitions available.
        if _upgrade_row_map().get(4747) is not None:
            self.assertTrue(
                any(r.get("id") == 4747 and r.get("role") == "supplement" for r in delta),
                msg=f"expected 4747 supplement, got {delta!r}",
            )
            # Full prose restored → no missing/truncated gap; params may still gap.
            gaps_4747 = [
                g for g in (block.get("mechanic_gaps") or []) if g.get("id") == 4747
            ]
            self.assertFalse(
                any(
                    g.get("completeness") in ("missing", "description_truncated")
                    for g in gaps_4747
                ),
                msg=f"unexpected structural gap for 4747: {gaps_4747!r}",
            )
        else:
            gaps = block.get("mechanic_gaps") or []
            morbid = next(g for g in gaps if g["id"] == 4747)
            self.assertIn(4749, morbid.get("dependent_option_ids") or [])
            self.assertIn(4750, morbid.get("dependent_option_ids") or [])
            self.assertIn("Birthday Party", morbid.get("note") or "")

    def test_cyclic_dependency_does_not_loop(self) -> None:
        entries = {
            1: {
                "champion_id": 1,
                "specialization_groups": [
                    {
                        "group_id": "t0",
                        "options": [{"option_id": 10, "name": "A"}],
                    }
                ],
            }
        }
        snap = {
            "shared": {
                "specialization_options": {
                    "10": {
                        "name": "A",
                        "effect": "ref B",
                        "depends_on_upgrade_ids": [11],
                    }
                },
                "abilities": {
                    "11": {
                        "name": "B",
                        "effect": "ref A",
                        "depends_on_upgrade_ids": [10],
                    }
                },
            },
            "champions": [{"id": 1}],
        }

        def _live(uid, kind, owner_name=None):
            if uid == 10:
                return {
                    "id": 10,
                    "name": "A",
                    "effect": "ref B",
                    "depends_on_upgrade_ids": [11],
                }
            if uid == 11:
                return {
                    "id": 11,
                    "name": "B",
                    "effect": "ref A",
                    "depends_on_upgrade_ids": [10],
                }
            return None

        with patch(
            "ic_gamedata.formation_ai_advice.mechanics_completeness._live_projected",
            side_effect=_live,
        ):
            block = build_mechanics_completeness(
                party_ids=[1],
                entries_by_id=entries,
                base_snapshot=snap,
            )
        self.assertEqual(block["counts"]["checked"], 2)
        self.assertEqual(block.get("mechanic_gaps"), None)

    def test_known_mechanic_unknown_magnitude_not_missing(self) -> None:
        entries = {
            1: {
                "champion_id": 1,
                "abilities": [{"ability_id": 5}],
            }
        }
        snap = {
            "shared": {
                "abilities": {
                    "5": {
                        "name": "Buff",
                        "effect": "Does X with (onbekend)%",
                        "magnitude": "basis_of_actueel_niet_berekend",
                    }
                }
            },
            "champions": [{"id": 1}],
        }
        with patch(
            "ic_gamedata.formation_ai_advice.mechanics_completeness._live_projected",
            return_value={
                "id": 5,
                "name": "Buff",
                "effect": "Does X with (onbekend)%",
                "magnitude": "basis_of_actueel_niet_berekend",
                "description_status": "full",
                "parameter_status": "resolved",
            },
        ):
            block = build_mechanics_completeness(
                party_ids=[1],
                entries_by_id=entries,
                base_snapshot=snap,
            )
        self.assertFalse(block.get("mechanic_gaps"))

    def test_beehive_barrage_15049_full_prose_not_preview_slice(self) -> None:
        row = _upgrade_row_map().get(15049)
        if row is None:
            self.skipTest("ability 15049 missing from definitions")
        fields = _mechanic_fields_from_upgrade(row)
        full = fields.get("mechanical_text") or ""
        self.assertGreater(len(full), 280)
        self.assertTrue(full.rstrip().endswith("formation."))
        self.assertNotIn("When an enemy wi…", full)

        # Snapshot holds the old clipboard preview cut.
        preview = full[:260].rstrip() + "…"
        self.assertTrue(_looks_like_export_preview_truncation(preview, full))
        self.assertFalse(
            _looks_like_export_preview_truncation(
                "Wait for it… then strike.",
                "Wait for it… then strike. Extra live text that continues.",
            ),
            msg="legitimate ellipsis in full source must not fingerprint as preview cut",
        )

        entries = {
            151: {
                "champion_id": 151,
                "name": "Umberto",
                "abilities": [{"ability_id": 15049, "name": "Beehive Barrage"}],
                "specialization_groups": [
                    {
                        "group_id": "tier_0",
                        "options": [
                            {"option_id": 15050, "name": "More Bees"},
                            {"option_id": 15051, "name": "Other Spec"},
                        ],
                    }
                ],
            }
        }
        snap = {
            "shared": {
                "abilities": {
                    "15049": {
                        "name": "Beehive Barrage",
                        "effect": preview,
                        "magnitude": "parameter_onbekend",
                    }
                },
                "specialization_options": {},
            },
            "champions": [{"id": 151, "abilities": [{"ref": 15049}]}],
        }
        block = build_mechanics_completeness(
            party_ids=[151],
            entries_by_id=entries,
            base_snapshot=snap,
        )
        delta = block.get("mechanics_delta") or []
        bee = next(r for r in delta if r.get("id") == 15049)
        self.assertEqual(bee.get("effect"), full)
        self.assertEqual(bee.get("description_status"), "full")
        self.assertNotIn("…", (bee.get("effect") or "")[-5:])

        compact = compact_mechanics_for_clipboard(block)
        assert compact is not None
        c_bee = next(
            r for r in (compact.get("mechanics_delta") or []) if r.get("id") == 15049
        )
        self.assertEqual(c_bee.get("effect"), full)
        self.assertGreater(len(c_bee.get("effect") or ""), 280)

        gaps = [g for g in (block.get("mechanic_gaps") or []) if g.get("id") == 15049]
        self.assertTrue(
            any(g.get("completeness") == "parameter_missing" for g in gaps),
            msg=f"expected parameter_missing for unresolved bees params, got {gaps!r}",
        )
        self.assertFalse(
            any(g.get("completeness") == "description_truncated" for g in gaps),
            msg="full restored prose must not be flagged description_truncated",
        )

    def test_ui_preview_helper_must_not_become_canonical_export(self) -> None:
        """Long prose shortened by a UI helper must not be the exported effect."""

        def ui_preview(text: str, max_len: int = 80) -> str:
            if len(text) <= max_len:
                return text
            return text[: max_len - 1].rstrip() + "…"

        full = (
            "A very long mechanical description that the UI list preview shortens "
            "for display, but the ADVICE_REQUEST export must keep verbatim."
        )
        preview = ui_preview(full)
        self.assertTrue(preview.endswith("…"))
        self.assertLess(len(preview), len(full))

        block = {
            "mechanics_delta": [
                {
                    "catalog": "ability",
                    "id": 1,
                    "role": "supplement",
                    "name": "Long Buff",
                    "effect": full,
                    "description_status": "full",
                    "parameter_status": "resolved",
                }
            ]
        }
        # Mistakenly compacting with the UI preview must not happen.
        self.assertNotEqual(
            compact_mechanics_for_clipboard(block)["mechanics_delta"][0]["effect"],
            preview,
        )
        self.assertEqual(
            compact_mechanics_for_clipboard(block)["mechanics_delta"][0]["effect"],
            full,
        )

    def test_full_text_with_unresolved_params_not_truncated(self) -> None:
        entries = {
            1: {"champion_id": 1, "abilities": [{"ability_id": 9}]}
        }
        full = (
            "Buff deals $(amount) (onbekend) damage and stacks to $max___1 (onbekend). "
            "This sentence continues so the description is clearly complete."
        )
        snap = {
            "shared": {"abilities": {}, "specialization_options": {}},
            "champions": [{"id": 1}],
        }
        with patch(
            "ic_gamedata.formation_ai_advice.mechanics_completeness._live_projected",
            return_value={
                "id": 9,
                "name": "Param Buff",
                "effect": full,
                "magnitude": "parameter_onbekend",
                "description_status": "full",
                "parameter_status": "unresolved",
                "unresolved_parameters": ["$(amount)", "$max___1"],
            },
        ):
            block = build_mechanics_completeness(
                party_ids=[1], entries_by_id=entries, base_snapshot=snap
            )
        row = next(r for r in block["mechanics_delta"] if r["id"] == 9)
        self.assertEqual(row["effect"], full)
        self.assertEqual(row["description_status"], "full")
        gaps = block.get("mechanic_gaps") or []
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["completeness"], "parameter_missing")
        self.assertEqual(gaps[0]["description_status"], "full")

    def test_truncated_with_and_without_ellipsis_via_metadata(self) -> None:
        entries = {
            1: {"champion_id": 1, "abilities": [{"ability_id": 11}]}
        }
        # Truncated mid-sentence WITHOUT ellipsis — explicit metadata only.
        snap = {
            "shared": {
                "abilities": {
                    "11": {
                        "name": "Cut Mid",
                        "effect": "When an enemy wi",
                        "description_truncated": True,
                        "export_truncated": True,
                        "truncation_cause": "export_preview",
                    }
                }
            },
            "champions": [{"id": 1}],
        }
        with patch(
            "ic_gamedata.formation_ai_advice.mechanics_completeness._live_projected",
            return_value={
                "id": 11,
                "name": "Cut Mid",
                "advice_hint": "Effect ontbreekt",
                "description_status": "missing",
            },
        ):
            block = build_mechanics_completeness(
                party_ids=[1], entries_by_id=entries, base_snapshot=snap
            )
        # Snapshot has usable (truncated) effect text → effective_ok via snap.
        gaps = block.get("mechanic_gaps") or []
        trunc = [g for g in gaps if g.get("completeness") == "description_truncated"]
        self.assertTrue(trunc, msg=f"expected description_truncated gap, got {gaps!r}")
        self.assertEqual(trunc[0].get("description_status"), "truncated")

    def test_legitimate_ellipsis_in_full_source_not_truncated(self) -> None:
        entries = {
            1: {"champion_id": 1, "abilities": [{"ability_id": 12}]}
        }
        full = "The bees pause… then sting for 100% BUD. Full stop."
        snap = {
            "shared": {
                "abilities": {
                    "12": {
                        "name": "Pause",
                        "effect": full,
                        "description_status": "full",
                    }
                }
            },
            "champions": [{"id": 1}],
        }
        with patch(
            "ic_gamedata.formation_ai_advice.mechanics_completeness._live_projected",
            return_value={
                "id": 12,
                "name": "Pause",
                "effect": full,
                "description_status": "full",
                "parameter_status": "resolved",
            },
        ):
            block = build_mechanics_completeness(
                party_ids=[1], entries_by_id=entries, base_snapshot=snap
            )
        self.assertFalse(block.get("mechanic_gaps"))
        self.assertFalse(block.get("mechanics_delta"))

    def test_missing_and_source_incomplete(self) -> None:
        entries = {
            1: {"champion_id": 1, "abilities": [{"ability_id": 13}]}
        }
        snap = {
            "shared": {"abilities": {}, "specialization_options": {}},
            "champions": [{"id": 1}],
        }
        with patch(
            "ic_gamedata.formation_ai_advice.mechanics_completeness._live_projected",
            return_value={
                "id": 13,
                "name": "Gone",
                "advice_hint": "Effect ontbreekt",
                "description_status": "missing",
                "parameter_status": "n/a",
            },
        ):
            block = build_mechanics_completeness(
                party_ids=[1], entries_by_id=entries, base_snapshot=snap
            )
        gaps = block.get("mechanic_gaps") or []
        self.assertEqual(gaps[0]["completeness"], "missing")
        self.assertEqual(gaps[0]["description_status"], "missing")

    def test_budget_omit_does_not_half_cut_effect(self) -> None:
        full = "X" * 400
        block = {
            "mechanics_delta": [
                {
                    "catalog": "ability",
                    "id": 99,
                    "name": "Huge",
                    "effect": full,
                    "description_status": "full",
                    "parameter_status": "resolved",
                }
            ],
            "mechanic_gaps": [],
        }
        out = omit_oversized_effects_for_budget(block, max_effect_chars=100)
        assert out is not None
        row = out["mechanics_delta"][0]
        self.assertNotIn("effect", row)
        self.assertTrue(row.get("effect_omitted_for_budget"))
        gaps = out.get("mechanic_gaps") or []
        self.assertTrue(
            any(
                g.get("completeness") == "description_truncated"
                and g.get("cause") == "export_budget"
                for g in gaps
            )
        )
        # compact path still never mid-cuts.
        kept = compact_mechanics_for_clipboard(
            {
                "mechanics_delta": [
                    {
                        "catalog": "ability",
                        "id": 99,
                        "effect": full,
                        "description_status": "full",
                    }
                ]
            }
        )
        self.assertEqual(kept["mechanics_delta"][0]["effect"], full)


class MechanicsCompletenessExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        # Prefer Baeloth/Ulkoria when owned; fall back to fixture heroes.
        owned = {
            int(h["hero_id"])
            for h in self.payload["details"]["heroes"]
            if h.get("owned") in ("1", 1, True)
        }
        picks: list[tuple[int, str, int]] = []
        for hid, name in ((73, "Baeloth"), (68, "Ulkoria"), (3, "Nayeli"), (2, "Celeste"), (4, "Jarlaxle")):
            if hid in owned or hid in (3, 2, 4):
                picks.append((hid, name, len(picks) + 1))
            if len(picks) >= 5:
                break
        self.formation = tuple(_hero(h, n, s) for h, n, s in picks)
        self._tmpdir = tempfile.TemporaryDirectory()
        cache_path = Path(self._tmpdir.name) / "owned_roster_cache.json"
        self._cache_patch = patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
            cache_path,
        )
        self._cache_patch.start()

    def tearDown(self) -> None:
        self._cache_patch.stop()
        self._tmpdir.cleanup()

    def test_request_includes_mechanics_completeness_and_stays_in_budget(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        # Simulate an outdated snapshot missing effect prose for known ids.
        shared = snap.setdefault("shared", {})
        abilities = shared.setdefault("abilities", {})
        options = shared.setdefault("specialization_options", {})
        if "4747" in abilities or _upgrade_row_map().get(4747):
            abilities["4747"] = {
                "name": "Morbid Excitement",
                "advice_hint": "Effect ontbreekt — bijdrage niet volledig te beoordelen.",
            }
        if "4350" in options or _upgrade_row_map().get(4350):
            options["4350"] = {
                "name": "Urchin Pranks",
                "advice_hint": "Keuze open — effect ontbreekt.",
            }
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
            include_swap_scope=False,
        )
        self.assertIn("mechanics_completeness", req)
        block = req["mechanics_completeness"]
        self.assertIn("priority", block)
        text = build_advice_request_clipboard_text(req, mode="project")
        chars = count_chars(text)
        self.assertLessEqual(chars, DEFAULT_CHAR_BUDGET, msg=f"chars={chars}")
        # Clipboard exposes flattened delta/gaps.
        if block.get("mechanics_delta"):
            self.assertIn("mechanics_delta", text)
        # Regression: if definitions present, supplements restore Baeloth/Ulkoria.
        delta_ids = {r["id"] for r in (block.get("mechanics_delta") or [])}
        if _upgrade_row_map().get(4747) and 73 in {h.hero_id for h in self.formation}:
            self.assertIn(4747, delta_ids)
        if _upgrade_row_map().get(4350) and 68 in {h.hero_id for h in self.formation}:
            self.assertIn(4350, delta_ids)

    def test_effect_defines_1362_has_conditions_shape(self) -> None:
        er = _effect_defines_by_id().get(1362)
        if er is None:
            self.skipTest("effect 1362 missing")
        desc = er.get("description")
        self.assertIsInstance(desc, dict)
        assert isinstance(desc, dict)
        self.assertIn("conditions", desc)
        text = _effect_description_text(er)
        self.assertTrue(text)

    def test_umberto_beehive_clipboard_keeps_full_effect_in_budget(self) -> None:
        row = _upgrade_row_map().get(15049)
        if row is None:
            self.skipTest("ability 15049 missing")
        full = _mechanic_fields_from_upgrade(row).get("mechanical_text") or ""
        self.assertGreater(len(full), 280)
        preview = full[:260].rstrip() + "…"
        formation = (
            _hero(151, "Umberto", 1),
            _hero(3, "Nayeli", 2),
            _hero(2, "Celeste", 3),
            _hero(4, "Jarlaxle", 4),
            _hero(1, "Bruenor", 5),
        )
        snap = build_base_snapshot(self.payload, formation=formation)
        shared = snap.setdefault("shared", {})
        abilities = shared.setdefault("abilities", {})
        abilities["15049"] = {
            "name": "Beehive Barrage",
            "effect": preview,
            "magnitude": "parameter_onbekend",
        }
        block = build_mechanics_completeness(
            party_ids=[151, 3, 2, 4, 1],
            entries_by_id={
                151: {
                    "champion_id": 151,
                    "name": "Umberto",
                    "abilities": [{"ability_id": 15049, "name": "Beehive Barrage"}],
                },
                3: {"champion_id": 3},
                2: {"champion_id": 2},
                4: {"champion_id": 4},
                1: {"champion_id": 1},
            },
            base_snapshot=snap,
        )
        req = build_advice_request(
            self.payload,
            formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
            include_swap_scope=False,
        )
        req["mechanics_completeness"] = block
        text = build_advice_request_clipboard_text(req, mode="project")
        chars = count_chars(text)
        self.assertLessEqual(chars, DEFAULT_CHAR_BUDGET, msg=f"chars={chars}")
        self.assertIn(full, text)
        self.assertNotIn("When an enemy wi…", text)
        self.assertIn("answer_contract", text)
        self.assertIn("removed from the formation.", text)


if __name__ == "__main__":
    unittest.main()
