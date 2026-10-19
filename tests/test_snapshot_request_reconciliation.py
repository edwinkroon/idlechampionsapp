"""BASE_SNAPSHOT ↔ ADVICE_REQUEST: overrides vs conflicts vs missing comparison data."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.compact_clipboard import (
    PROJECT_INSTRUCTIONS,
    build_advice_request_clipboard_text,
    safety_instruction,
)
from ic_gamedata.formation_ai_advice.export import gender_from_raw_tags
from ic_gamedata.formation_ai_advice.mechanics import effect_facts, _load_effect_row
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
    reconcile_snapshot_vs_request,
)
from ic_gamedata.party_advisor_models import FormationHero


def _hero(
    hero_id: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
    tags: tuple[str, ...] = (),
) -> FormationHero:
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
        role_label=roles[0].capitalize() if roles else "Unknown",
        roles=roles,
        tags=tags,
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class GenderContractTests(unittest.TestCase):
    def test_gender_from_tags_known(self) -> None:
        g = gender_from_raw_tags(["support", "female", "bard"])
        self.assertEqual(g["status"], "known")
        self.assertEqual(g["value"], "female")
        self.assertEqual(g["tag"], "female")
        self.assertEqual(g["source"], "hero_defines.tags")

    def test_gender_unknown_not_inferred_from_empty(self) -> None:
        g = gender_from_raw_tags(["support", "bard"])
        self.assertEqual(g["status"], "unknown")
        self.assertIsNone(g["value"])
        self.assertIn("niet afleiden", (g.get("note") or "").casefold())

    def test_gender_none_source_unknown(self) -> None:
        g = gender_from_raw_tags(None)
        self.assertEqual(g["status"], "unknown")
        self.assertIsNone(g["source"])

    def test_soprano_scaling_uses_female_tag(self) -> None:
        row = _load_effect_row(1460)
        self.assertIsNotNone(row)
        facts = effect_facts(None, row, owner_name="Birdsong")
        sem = facts.get("semantics") or {}
        scaling = sem.get("scaling_population") or {}
        self.assertIn("female", scaling.get("tags") or [])
        # Counter tag is scaling, not a recipient filter.
        recipients = sem.get("recipients") or {}
        self.assertNotIn("female", recipients.get("tags") or [])


class ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.formation = (
            _hero(3, "Nayeli", 1, roles=("tank", "support")),
            _hero(2, "Celeste", 2, roles=("healer", "support")),
            _hero(4, "Jarlaxle", 3, roles=("dps", "gold")),
        )
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

    def test_current_selection_overrides_snapshot_selection(self) -> None:
        snap = {
            "champions": [
                {
                    "id": 21,
                    "name": "Birdsong",
                    "gender": {
                        "status": "known",
                        "value": "female",
                        "tag": "female",
                        "source": "hero_defines.tags",
                    },
                    "specializations": [
                        {
                            "group_id": "tier_1",
                            "status": "selected",
                            "selected": {"id": 10782, "name": "Soprano"},
                            "options": [
                                {"id": 10782, "name": "Soprano"},
                                {"id": 10781, "name": "Unison"},
                            ],
                        }
                    ],
                }
            ],
            "shared": {},
        }
        party = [
            {
                "id": 21,
                "name": "Birdsong",
                "specialization_choices": [
                    {
                        "group_id": "tier_1",
                        "selected_option_id": 10781,
                        "selection_status": "selected",
                    }
                ],
            }
        ]
        result = reconcile_snapshot_vs_request(
            party_state=party,
            entries_by_id={},
            base_snapshot=snap,
        )
        overrides = result.get("expected_state_overrides") or []
        self.assertTrue(
            any(o.get("code") == "selection_changed" for o in overrides),
            overrides,
        )
        self.assertFalse(result.get("material_source_conflicts"))

    def test_selected_overrides_not_unlocked(self) -> None:
        snap = {
            "champions": [
                {
                    "id": 166,
                    "name": "Cazrin",
                    "gender": {
                        "status": "known",
                        "value": "female",
                        "tag": "female",
                        "source": "hero_defines.tags",
                    },
                    "specializations": [
                        {
                            "group_id": "tier_1",
                            "status": "not_unlocked",
                            "selected": None,
                            "options": [
                                {"id": 17680, "name": "Smell Mastery"},
                                {"id": 17681, "name": "Other"},
                            ],
                        }
                    ],
                }
            ],
            "shared": {},
        }
        party = [
            {
                "id": 166,
                "name": "Cazrin",
                "specialization_choices": [
                    {
                        "group_id": "tier_1",
                        "selected_option_id": 17680,
                        "selection_status": "selected",
                    }
                ],
            }
        ]
        result = reconcile_snapshot_vs_request(
            party_state=party,
            entries_by_id={},
            base_snapshot=snap,
        )
        overrides = result.get("expected_state_overrides") or []
        self.assertTrue(
            any(o.get("code") == "unlocked_since_snapshot" for o in overrides),
            overrides,
        )
        self.assertFalse(result.get("material_source_conflicts"))

    def test_unknown_current_not_filled_from_snapshot(self) -> None:
        snap = {
            "champions": [
                {
                    "id": 3,
                    "name": "Nayeli",
                    "gender": {
                        "status": "known",
                        "value": "female",
                        "tag": "female",
                        "source": "hero_defines.tags",
                    },
                    "specializations": [
                        {
                            "group_id": "tier_0",
                            "status": "selected",
                            "selected": {"id": 30},
                            "options": [{"id": 30}, {"id": 29}],
                        }
                    ],
                }
            ],
            "shared": {},
        }
        party = [
            {
                "id": 3,
                "name": "Nayeli",
                "specialization_choices": [
                    {
                        "group_id": "tier_0",
                        "selected_option_id": None,
                        "selection_status": "unknown",
                    }
                ],
            }
        ]
        result = reconcile_snapshot_vs_request(
            party_state=party,
            entries_by_id={},
            base_snapshot=snap,
        )
        overrides = result.get("expected_state_overrides") or []
        self.assertTrue(
            any(
                o.get("code") == "unknown_current_not_filled_from_snapshot"
                for o in overrides
            ),
            overrides,
        )
        # Party row itself must keep unknown — reconciliation never mutates it.
        self.assertIsNone(party[0]["specialization_choices"][0]["selected_option_id"])
        self.assertEqual(
            party[0]["specialization_choices"][0]["selection_status"], "unknown"
        )

    def test_invalid_option_is_material_conflict(self) -> None:
        snap = {
            "champions": [
                {
                    "id": 21,
                    "name": "Birdsong",
                    "gender": {
                        "status": "known",
                        "value": "female",
                        "tag": "female",
                        "source": "hero_defines.tags",
                    },
                    "specializations": [
                        {
                            "group_id": "tier_1",
                            "status": "selected",
                            "selected": {"id": 10782},
                            "options": [
                                {"id": 10782, "name": "Soprano"},
                                {"id": 10781, "name": "Unison"},
                            ],
                        }
                    ],
                }
            ],
            "shared": {},
        }
        party = [
            {
                "id": 21,
                "name": "Birdsong",
                "specialization_choices": [
                    {
                        "group_id": "tier_1",
                        "selected_option_id": 999001,
                        "selection_status": "selected",
                    }
                ],
            }
        ]
        result = reconcile_snapshot_vs_request(
            party_state=party,
            entries_by_id={},
            base_snapshot=snap,
        )
        conflicts = result.get("material_source_conflicts") or []
        self.assertTrue(
            any(c.get("code") == "option_not_in_champion_group" for c in conflicts),
            conflicts,
        )

    def test_missing_gender_limits_soprano_not_whole_advice(self) -> None:
        entries = {
            21: {
                "champion_id": 21,
                "name": "Birdsong",
                "gender": {
                    "status": "known",
                    "value": "female",
                    "tag": "female",
                    "source": "hero_defines.tags",
                },
                "specialization_groups": [
                    {
                        "group_id": "tier_1",
                        "selection_status": "selected",
                        "selected_option_id": 10781,
                        "options": [
                            {
                                "option_id": 10781,
                                "name": "Unison",
                                "selected": True,
                                "effect_facts": {},
                            },
                            {
                                "option_id": 10782,
                                "name": "Soprano",
                                "selected": False,
                                "effect_facts": {
                                    "semantics": {
                                        "scaling_population": {
                                            "tags": ["female"],
                                            "combine": "count_matching",
                                        }
                                    }
                                },
                            },
                        ],
                    }
                ],
            }
        }
        party = [
            {
                "id": 21,
                "name": "Birdsong",
                "specialization_choices": [
                    {
                        "group_id": "tier_1",
                        "selected_option_id": 10781,
                        "selection_status": "selected",
                    }
                ],
            },
            {
                "id": 4,
                "name": "Jarlaxle",
                "specialization_choices": [],
            },
        ]
        # Jarlaxle gender unknown → Soprano count incomplete.
        snap = {
            "champions": [
                {
                    "id": 21,
                    "name": "Birdsong",
                    "gender": entries[21]["gender"],
                    "specializations": [],
                },
                {
                    "id": 4,
                    "name": "Jarlaxle",
                    "gender": {
                        "status": "unknown",
                        "value": None,
                        "tag": None,
                        "source": "hero_defines.tags",
                    },
                    "specializations": [],
                },
            ],
            "shared": {},
        }
        result = reconcile_snapshot_vs_request(
            party_state=party,
            entries_by_id=entries,
            base_snapshot=snap,
        )
        missing = result.get("missing_comparison_data") or []
        self.assertTrue(missing, result)
        row = missing[0]
        self.assertEqual(row["option_name"], "Soprano")
        self.assertTrue(row["blocks_proven_ranking"])
        self.assertFalse(row["blocks_other_formation_advice"])
        self.assertIn(4, row["unknown_champion_ids"])

    def test_known_gender_enables_soprano_count(self) -> None:
        entries = {
            21: {
                "champion_id": 21,
                "name": "Birdsong",
                "gender": {
                    "status": "known",
                    "value": "female",
                    "tag": "female",
                    "source": "hero_defines.tags",
                },
                "specialization_groups": [
                    {
                        "group_id": "tier_1",
                        "options": [
                            {
                                "option_id": 10782,
                                "name": "Soprano",
                                "effect_facts": {
                                    "semantics": {
                                        "scaling_population": {
                                            "tags": ["female"],
                                            "combine": "count_matching",
                                        }
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        }
        party = [
            {"id": 21, "name": "Birdsong", "specialization_choices": []},
            {"id": 3, "name": "Nayeli", "specialization_choices": []},
            {"id": 4, "name": "Jarlaxle", "specialization_choices": []},
        ]
        snap = {
            "champions": [
                {
                    "id": 21,
                    "gender": {
                        "status": "known",
                        "value": "female",
                        "tag": "female",
                        "source": "hero_defines.tags",
                    },
                },
                {
                    "id": 3,
                    "gender": {
                        "status": "known",
                        "value": "female",
                        "tag": "female",
                        "source": "hero_defines.tags",
                    },
                },
                {
                    "id": 4,
                    "gender": {
                        "status": "known",
                        "value": "male",
                        "tag": "male",
                        "source": "hero_defines.tags",
                    },
                },
            ],
            "shared": {},
        }
        result = reconcile_snapshot_vs_request(
            party_state=party,
            entries_by_id=entries,
            base_snapshot=snap,
        )
        self.assertFalse(result.get("missing_comparison_data"))
        available = result.get("comparison_data_available") or []
        self.assertTrue(available)
        self.assertEqual(available[0]["party_matching_count"], 2)

    def test_export_includes_gender_and_instructions_omit_override_warnings(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        # Gender present on snapshot champions when defines have the tag.
        genders = [
            c.get("gender")
            for c in snap["champions"]
            if isinstance(c, dict) and c.get("id") in {2, 3, 4}
        ]
        self.assertTrue(genders)
        for g in genders:
            self.assertIsInstance(g, dict)
            self.assertIn(g.get("status"), {"known", "unknown", "conflict"})
            if g.get("status") == "known":
                self.assertEqual(g.get("source"), "hero_defines.tags")

        # Mutate snapshot party specs to differ from a fresh request.
        for c in snap["champions"]:
            if c.get("id") != 3:
                continue
            for group in c.get("specializations") or []:
                if group.get("group_id") == "tier_0":
                    group["status"] = "selected"
                    group["selected"] = {"id": 29, "name": "War Domain"}
                    break

        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
            goal="push",
            fixed_main_dps_id=4,
        )
        self.assertIn("expected_state_override", req["bronregels"].casefold())
        self.assertIn("material_source_conflict", req["bronregels"].casefold())
        self.assertIn("missing_comparison_data", req["bronregels"].casefold())
        deviations = req.get("snapshot_deviations") or {}
        self.assertIn("source_priority", deviations)
        self.assertIn("hash_note", deviations)
        # Mechanics / account hashes still attached (integrity not masked).
        self.assertEqual(
            deviations.get("snapshot_mechanics_hash"),
            snap["meta"]["mechanics_hash"],
        )
        self.assertEqual(
            deviations.get("snapshot_account_state_hash"),
            snap["meta"]["account_state_hash"],
        )

        text = build_advice_request_clipboard_text(req, mode="project")
        safety = safety_instruction(snap["meta"]["snapshot_id"])
        self.assertIn(safety, text)
        self.assertIn("expected overrides", safety.casefold())
        self.assertIn("conflicten", safety.casefold())
        # Expected overrides must not be framed as warnings in the instruction text.
        self.assertNotIn("relevant bronverschil", text.casefold())
        self.assertIn("expected_state_override", PROJECT_INSTRUCTIONS.casefold())
        # Safety / project text must not tell the model to warn on normal overrides.
        for blob in (safety, PROJECT_INSTRUCTIONS):
            self.assertNotRegex(
                blob.casefold(),
                r"meld.*expected_state_override",
            )


if __name__ == "__main__":
    unittest.main()
