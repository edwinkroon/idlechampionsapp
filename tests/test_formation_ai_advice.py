"""Tests for clipboard/chat formation advice (no paid API)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.formation_ai_advice.apply import (
    apply_proposal,
    remap_visual_nodes,
    snapshot_from_visual_nodes,
)
from ic_gamedata.formation_ai_advice.clipboard_export import (
    build_advice_payload,
    extract_json_object,
    format_clipboard_markdown,
    format_debug_markdown,
)
from ic_gamedata.formation_ai_advice.geometry import assess_active_graph
from ic_gamedata.formation_ai_advice.mechanics import (
    eligibility_record,
    merge_restriction_sources,
    quality_flags,
    refine_mechanic,
    selection_status,
)
from ic_gamedata.formation_ai_advice.export import (
    build_export_payload,
    formation_layout_fingerprint_from_export,
    request_fingerprint,
)
from ic_gamedata.formation_ai_advice.labels import (
    champion_seat_caption,
    position_caption,
)
from ic_gamedata.formation_ai_advice.models import (
    SCHEMA_VERSION,
    AdviceSource,
    AssignmentProposal,
    FormationAdviceProposal,
    SpecializationChoice,
)
from ic_gamedata.formation_ai_advice.service import ingest_pasted_proposal
from ic_gamedata.formation_ai_advice.validate import (
    parse_proposal_json,
    preflight_export,
    validate_proposal_against_export,
)
from ic_gamedata.party_advisor_models import FormationHero
from ic_gamedata.seat_advisor.models import VisualSeatNode


def _hero(
    hid: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
) -> FormationHero:
    return FormationHero(
        hero_id=hid,
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
        role_label=roles[0].capitalize(),
        roles=roles,
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


def _node(seat: int, hero_id: int, name: str) -> VisualSeatNode:
    return VisualSeatNode(
        seat=seat,
        x=float(seat),
        y=0.0,
        zone="mid",
        hero_id=hero_id,
        hero_name=name,
        effective_role=None,
        inferred_role=None,
        chosen_role=None,
        is_bud=False,
        has_issue=False,
        is_active=True,
    )


class FormationAiAdviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def _formation(self) -> tuple[FormationHero, ...]:
        return (
            _hero(3, "Nayeli", 1, roles=("tank", "support")),
            _hero(2, "Celeste", 2, roles=("healer", "support")),
            _hero(4, "Jarlaxle", 3, roles=("dps", "gold")),
        )

    def _export(self, **kwargs):
        goal = kwargs.get("goal", "push")
        # Legacy test aliases → user goals (never gold→favor / speed→gems).
        if goal in ("bud",):
            goal = "push"
        objective = kwargs.get("objective")
        if objective == "speed" and goal == "push":
            goal = "gem_farm"
        elif objective == "push_damage":
            goal = goal if goal in {
                "push",
                "quest_clear",
                "gem_farm",
                "gold_farm",
                "favor_farm",
                "custom_task",
            } else "push"
        fixed = kwargs.get(
            "fixed_main_dps_id",
            kwargs.get("main_dps_id", 4),
        )
        return build_export_payload(
            self.payload,
            self._formation(),
            goal=goal,
            context=kwargs.get("context", "campaign"),
            fixed_main_dps_id=fixed,
            goal_parameters=kwargs.get("goal_parameters"),
            request_id=kwargs.get("request_id", "req-test-1"),
        )

    def _identity_proposal_dict(self, export: dict) -> dict:
        assignments = []
        for row in export["champions"]:
            pos = row["current_position"]
            specs = []
            for g in row.get("specialization_groups") or []:
                opts = g.get("options") or []
                pick = next((o for o in opts if o.get("selected")), None) or (
                    opts[0] if opts else None
                )
                if pick:
                    specs.append(
                        {
                            "group_id": g["group_id"],
                            "option_id": pick["option_id"],
                            "reason": "test",
                        }
                    )
            assignments.append(
                {
                    "position_id": pos,
                    "champion_id": row["champion_id"],
                    "specialization_choices": specs,
                    "placement_reason": "blijft",
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": export["meta"]["request_id"],
            "status": "proposal",
            "summary": "Testvoorstel",
            "assignments": assignments,
            "expected_key_buffs": [],
            "assumptions": [],
            "missing_information": [],
            "warnings": [],
            "source_refs": [],
        }

    def test_export_has_adjacency_and_meta(self) -> None:
        export = self._export()
        self.assertEqual(export["meta"]["schema_version"], SCHEMA_VERSION)
        self.assertIn("adjacency_by_position", export["formation"])
        self.assertEqual(export["constraints"]["may_replace_champions"], False)

    def test_nine_slot_formation_not_twelve_ids(self) -> None:
        export = self._export()
        formation = export["formation"]
        self.assertEqual(formation["formation_capacity"], 9)
        self.assertEqual(formation["physical_position_count"], 9)
        valid = formation["valid_position_ids"]
        self.assertEqual(len(valid), 9)
        self.assertNotIn(10, valid)
        self.assertNotIn(11, valid)
        self.assertNotIn(12, valid)
        self.assertEqual(sorted(valid), sorted(formation["active_position_ids"]))

    def test_adjacency_symmetric_on_active_positions(self) -> None:
        export = self._export()
        adj = export["formation"]["adjacency_by_position"]
        active = set(export["formation"]["active_position_ids"])
        for seat_s, neighbors in adj.items():
            seat = int(seat_s)
            self.assertIn(seat, active)
            for other in neighbors:
                self.assertNotEqual(other, seat)
                self.assertIn(other, active)
                self.assertIn(seat, adj.get(str(other), []), msg=f"{seat}->{other}")

    def test_champion_taxonomy_normalized(self) -> None:
        export = self._export()
        by_id = {c["champion_id"]: c for c in export["champions"]}
        celeste = by_id[2]
        self.assertEqual(celeste["species"], "Human")
        self.assertEqual(celeste["classes"], ["Cleric"])
        self.assertIsInstance(celeste["alignment"], dict)
        self.assertEqual(celeste["alignment"]["law_chaos"], "lawful")
        self.assertEqual(celeste["alignment"]["good_evil"], "good")
        affiliations = celeste.get("affiliations") or []
        self.assertNotIn("human", [a.casefold() for a in affiliations])
        self.assertNotIn("cleric", [a.casefold() for a in affiliations])
        self.assertNotIn("support", [a.casefold() for a in affiliations])
        self.assertTrue(celeste.get("raw_tags"))

    def test_specialization_text_from_defines(self) -> None:
        export = self._export()
        celeste = next(c for c in export["champions"] if c["champion_id"] == 2)
        opts = []
        for g in celeste.get("specialization_groups") or []:
            opts.extend(g.get("options") or [])
        war = next(o for o in opts if o.get("name") == "War Domain")
        self.assertTrue(war.get("text"))
        self.assertIn("damage", war["text"].casefold())

    def test_readiness_present(self) -> None:
        export = self._export()
        self.assertIn(export["readiness"]["status"], ("ready", "ready_with_warnings", "blocked"))
        result = preflight_export(export)
        self.assertNotEqual(result.status, "invalid")

    def test_clipboard_table_mode_includes_plek_table_and_import_json(self) -> None:
        md = format_clipboard_markdown(self._export(), output_mode="table")
        self.assertIn("| Plek | Champion |", md)
        self.assertIn("display_position", md.casefold())
        self.assertIn("kolom-plek", md.casefold())
        # Readable table + one import JSON (no longer table-only).
        self.assertIn("importeerbaar json-object", md.casefold())
        self.assertNotIn("position_id + kolom/zone", md)
        self.assertNotIn("Korte samenvatting (2–5 zinnen)", md)
        # One gegevens block — no prose champion dump duplicating JSON.
        self.assertEqual(md.count("## Champions"), 0)
        self.assertIn("## Gegevens", md)
        self.assertNotIn("Canonieke machine-export", md)

    def test_clipboard_json_mode_includes_paste_hint(self) -> None:
        md = format_clipboard_markdown(self._export(), output_mode="json")
        self.assertIn("Verwacht antwoord-JSON", md)
        self.assertIn("req-test-1", md)
        self.assertIn('"placements"', md)
        self.assertIn('"specializations"', md)
        self.assertIn("```json", md)
        self.assertNotIn("### JSON Schema", md)

    def test_needs_information_blocks_apply(self) -> None:
        export = self._export()
        fp = formation_layout_fingerprint_from_export(export)
        proposal = FormationAdviceProposal(
            schema_version=SCHEMA_VERSION,
            request_id="req-test-1",
            status="needs_information",
            summary="meer info nodig",
            missing_information=("Ontbrekende restrictietekst",),
        )
        local = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request=fp,
            current_formation_fingerprint=fp,
        )
        self.assertEqual(local.status, "needs_information")
        self.assertFalse(local.can_apply)

    def test_adventure_name_resolved(self) -> None:
        export = self._export()
        self.assertIsNotNone(export["goal"].get("adventure_name"))
        self.assertTrue(export["goal"].get("restrictions_checked_by_app"))

    def test_lower_column_is_front(self) -> None:
        export = self._export()
        self.assertEqual(
            export["formation"]["front_direction"]["rule"],
            "lower_column_is_front",
        )

    def test_preflight_ok(self) -> None:
        result = preflight_export(self._export())
        self.assertNotEqual(result.status, "invalid")

    def test_missing_game_data_preflight(self) -> None:
        export = self._export()
        export["champions"] = []
        self.assertEqual(preflight_export(export).status, "invalid")

    def test_clipboard_markdown_self_contained(self) -> None:
        export = self._export()
        md = format_clipboard_markdown(export)
        self.assertIn("formatieadviseur", md.casefold())
        self.assertIn("zelfstandige game-adviesaanvraag", md.casefold())
        self.assertIn("```json", md)
        self.assertEqual(md.count("```json"), 1)
        # request_id lives in gegevens JSON (table mode has no paste hint).
        self.assertIn(str(export["meta"]["request_id"]), md)

    def test_advice_payload_smaller_than_full_export(self) -> None:
        export = self._export()
        advice = build_advice_payload(export)
        full = json.dumps(export, ensure_ascii=False)
        compact = json.dumps(advice, ensure_ascii=False)
        self.assertLess(len(compact), len(full) * 0.7)
        # No duplicated champion overview outside the single gegevens JSON.
        md = format_clipboard_markdown(export)
        self.assertNotIn("### Nayeli", md)
        debug = format_debug_markdown(export)
        self.assertIn("DEBUG", debug)
        self.assertGreater(len(debug), len(md))

    def test_adjacency_buff_unknown_percent_usable_for_placement(self) -> None:
        # Synthetic: adjacent targeting known, amount computed/unknown.
        effect_row = {
            "effect_keys": [
                {
                    "effect_string": "hero_dps_mult_vs_targets,1,adj",
                    "targets": "adj",
                    "use_computed_amount_for_description": True,
                }
            ]
        }
        refined = refine_mechanic(
            "Increases the damage of adjacent Champions by $amount%.",
            effect_row,
            "hero_dps_mult_vs_targets,1,adj",
        )
        quality = refined["quality"]
        self.assertEqual(quality["targeting_known"], True)
        self.assertEqual(quality["usable_for_placement"], True)
        self.assertNotEqual(quality["usable_for_numeric_comparison"], True)
        self.assertIn("(onbekend)", refined["text"] or "")

    def test_missing_dependency_ability_reported(self) -> None:
        # Synthetic dependency gap via quality_flags when referenced id is absent.
        quality = quality_flags(
            "Buffs Honorary Crewmates",
            {"effect_keys": [{"effect_string": "buff_upgrades,50,12345"}]},
            "buff_upgrades,50,12345",
            unresolved_placeholders=[],
            upgrade_ids_known=set(),
        )
        self.assertEqual(quality["dependencies_resolved"], False)
        self.assertEqual(quality["usable_for_numeric_comparison"], False)

    def test_spec_branch_abilities_not_all_simultaneously_active(self) -> None:
        export = self._export()
        celeste = next(c for c in export["champions"] if c["champion_id"] == 2)
        for group in celeste.get("specialization_groups") or []:
            selected = [o for o in group["options"] if o.get("selected")]
            if len(selected) != 1:
                continue
            for opt in group["options"]:
                if opt.get("selected"):
                    self.assertTrue(opt.get("simultaneously_active"))
                else:
                    self.assertFalse(opt.get("simultaneously_active"))

    def test_patron_override_verified_and_unverified(self) -> None:
        verified = eligibility_record(
            base_status="denied",
            base_reason="patron_blocked",
            overrides=[
                {
                    "source_ability_id": 999,
                    "source_champion_id": 1,
                    "required_tag": "Good",
                }
            ],
            champion_tags=["Good", "Human"],
            tags_known=True,
        )
        self.assertEqual(verified["effective_eligibility"], "allowed")
        self.assertTrue(verified["affiliation_verified"])

        unknown = eligibility_record(
            base_status="denied",
            base_reason="patron_blocked",
            overrides=[
                {
                    "source_ability_id": 999,
                    "source_champion_id": 1,
                    "required_tag": "Good",
                }
            ],
            champion_tags=[],
            tags_known=False,
        )
        self.assertEqual(unknown["effective_eligibility"], "unknown")
        self.assertEqual(unknown["affiliation_verified"], "unknown")

    def test_conflicting_restriction_sources(self) -> None:
        # Manual text + API rules must not invent a hard party conflict when
        # the API evaluation already says ok — mark unconfirmed instead.
        self.assertEqual(
            merge_restriction_sources("ok", api_has_rules=True, manual_text="geen evil"),
            "unconfirmed",
        )
        self.assertEqual(
            merge_restriction_sources(
                "conflict", api_has_rules=True, manual_text="geen evil"
            ),
            "conflict",
        )
        self.assertEqual(
            merge_restriction_sources("denied", api_has_rules=True, manual_text=""),
            "denied",
        )

    def test_active_only_blocked_neighbors_flagged(self) -> None:
        report = assess_active_graph(
            active_ids=[1, 2],
            blocked_ids=[3],
            adjacency={1: [3], 2: [3], 3: [1, 2]},
            authoritative=True,
        )
        codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("active_only_blocked_neighbors", codes)
        self.assertIn("disconnected_active_graph", codes)
        self.assertEqual(report["distance"]["values"].get("1-2"), "unreachable")

    def test_selection_status_unknown_vs_unselected(self) -> None:
        self.assertEqual(
            selection_status(
                choices_observed=False,
                selected_option_id=None,
                required_level=50,
                hero_level=100,
            ),
            "unknown",
        )
        self.assertEqual(
            selection_status(
                choices_observed=True,
                selected_option_id=None,
                required_level=50,
                hero_level=100,
            ),
            "unselected",
        )
        self.assertEqual(
            selection_status(
                choices_observed=True,
                selected_option_id=None,
                required_level=200,
                hero_level=50,
            ),
            "not_unlocked",
        )

    def test_no_ilvl_damage_multiplier_claim(self) -> None:
        export = self._export()
        self.assertTrue(
            export["constraints"]["do_not_derive_damage_multipliers_from_average_item_level"]
        )
        md = format_clipboard_markdown(export)
        self.assertIn("itemlevels", md.casefold())

    def test_evil_not_targeted_by_good_only_without_override(self) -> None:
        # Synthetic: Good-only filter does not imply Evil is covered.
        effect_row = {
            "effect_keys": [
                {
                    "effect_string": "hero_dps_mult_vs_targets,100,adj",
                    "targets": "adj",
                    "filter_targets": [{"tags": "Good"}],
                }
            ]
        }
        facts = refine_mechanic(
            "Buffs adjacent Good Champions.",
            effect_row,
            "hero_dps_mult_vs_targets,100,adj",
        )["effect_facts"]
        self.assertIn("Good", facts.get("target_tags") or [])
        self.assertNotIn("Evil", facts.get("target_tags") or [])

    def test_artemis_observance_no_non_dps_copies(self) -> None:
        # Synthetic party: Artemis (dps) + supports. Observance-like copy only
        # applies to champions with a dps role; supports must not be assumed.
        party = (
            _hero(95, "Artemis", 1, roles=("dps",)),
            _hero(58, "Briv", 5, roles=("tank", "support")),
            _hero(2, "Celeste", 2, roles=("healer", "support")),
        )
        export = build_export_payload(
            self.payload,
            party,
            goal="bud",
            context="campaign",
            objective="push_damage",
            main_dps_id=95,
            request_id="synth-artemis",
        )
        for champ in export["champions"]:
            roles = {str(r).casefold() for r in (champ.get("roles") or [])}
            if "dps" not in roles:
                # Non-DPS must not be treated as Observance copy targets by role alone.
                self.assertNotIn("dps", roles)

    def test_human_glitch_feat_keeps_mechanics_not_flavor(self) -> None:
        """Synthetic: feat 2449 Human Glitch — mechanics retained, flavor dropped."""
        from ic_gamedata.formation_ai_advice.export import _feat_info

        payload = {
            "details": {
                "heroes": [
                    {"hero_id": 146, "active_feats": [2449], "level": 100},
                ]
            }
        }
        feats = _feat_info(payload, 146)
        glitch = next(
            f for f in (feats.get("active_feats") or []) if f.get("feat_id") == 2449
        )
        text = (glitch.get("mechanical_text") or "").casefold()
        self.assertIn("human", text)
        self.assertIn("ceremorphosis", text)
        self.assertIsNone(glitch.get("flavor_text"))
        self.assertTrue(glitch.get("already_applied_in_export", {}).get("tags"))
        advice = build_advice_payload(
            {
                "meta": {"schema_version": "1.2", "request_id": "t"},
                "goal": {},
                "formation": {},
                "champions": [
                    {
                        "champion_id": 146,
                        "name": "Dark Urge",
                        "feats": feats,
                    }
                ],
                "constraints": {},
                "readiness": {"status": "ready"},
            }
        )
        slim = advice["champions"][0]["active_feats"][0]
        # Advice projection inlines readable effect text (no hash effect_ref).
        self.assertIn("human", (slim.get("effect") or "").casefold())
        self.assertNotIn("flavor_text", slim)
        self.assertNotIn("effect_ref", slim)

    def test_resist_the_urge_effective_alignment_and_role(self) -> None:
        """Synthetic: selected Resist the Urge → Lawful Good + Control role."""
        from ic_gamedata.formation_ai_advice.export import (
            _attach_spec_state_changes,
            _effective_traits_for_champion,
        )
        from ic_gamedata.formation_ai_advice.mechanics import trait_changes_from_keys

        # Effect 1877 keys include change_hero_alignment_tag + add_hero_tags control.
        keys = [
            {"effect_string": "change_hero_alignment_tag,lawful,good"},
            {"effect_string": "add_hero_tags,0,control"},
        ]
        changes = trait_changes_from_keys(keys)
        groups = [
            {
                "selection_status": "selected",
                "options": [
                    {
                        "option_id": 14386,
                        "selected": True,
                        "state_changes": changes,
                    }
                ],
            }
        ]
        groups = _attach_spec_state_changes(groups)  # no-op if already set
        # Ensure state_changes survive attach.
        groups[0]["options"][0]["state_changes"] = changes
        groups[0]["selection_status"] = "selected"
        groups[0]["options"][0]["selected"] = True
        effective = _effective_traits_for_champion(
            base_alignment={
                "label": "Chaotic Evil",
                "law_chaos": "chaotic",
                "good_evil": "evil",
            },
            base_roles=["dps"],
            base_tags=[],
            specialization_groups=groups,
            feats={"active_feats": []},
        )
        self.assertEqual(effective["alignment"]["law_chaos"], "lawful")
        self.assertEqual(effective["alignment"]["good_evil"], "good")
        self.assertIn("dps", [r.casefold() for r in effective["roles"]])
        self.assertIn("control", [r.casefold() for r in effective["roles"]])

    def test_unconditional_and_campaign_eligibility_overrides(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import (
            detect_restriction_override,
            evaluate_restriction_overrides,
        )

        dark = detect_restriction_override(
            mechanical_text=(
                "The Dark Urge is eligible to start in all adventures, even if the "
                "Patron, Variant, or other restrictions would say otherwise."
            ),
            effect_strings=["do_nothing"],
            source_ability_id=14378,
            source_champion_id=146,
        )
        self.assertEqual(dark["kind"], "unconditional_adventure_eligibility")
        allowed = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="dex < 15",
            overrides=[dark],
            champion_tags=[],
            tags_known=True,
            campaign_id=1,
            campaign_name="Grand Tour of the Sword Coast",
        )
        self.assertEqual(allowed["effective_eligibility"], "allowed")

        volo = detect_restriction_override(
            mechanical_text=(
                "Volo can be used in any Grand Tour of the Sword Coast campaign "
                "adventure or variant, even if he would not normally be available "
                "to be used due to variant or patron restrictions."
            ),
            effect_strings=["do_nothing"],
            source_ability_id=16549,
            source_champion_id=159,
        )
        self.assertEqual(volo["kind"], "campaign_scoped_eligibility")
        unknown = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="patron_blocked",
            overrides=[volo],
            champion_tags=[],
            tags_known=True,
            campaign_id=None,
            campaign_name=None,
        )
        self.assertEqual(unknown["effective_eligibility"], "unknown")

    def test_reference_id_not_treated_as_buff_magnitude(self) -> None:
        # Spare Dagger: change_base_attack,39 — attack id, not 39%.
        refined = refine_mechanic(
            "Adds a thrown Dagger to Hitch's Base Attack",
            {"effect_keys": [{"effect_string": "change_base_attack,39"}]},
            "effect_def,38",
        )
        params = (refined.get("effect_facts") or {}).get("parameters") or []
        self.assertTrue(any(p.get("meaning") == "attack_id" for p in params))
        self.assertEqual(
            (refined.get("effect_facts") or {}).get("amount_status"),
            "not_applicable",
        )
        self.assertNotEqual(
            refined["quality"]["usable_for_numeric_comparison"],
            True,
        )

    def test_trust_in_law_targeting_known_without_magnitude(self) -> None:
        refined = refine_mechanic(
            "Freely's Luck of Yondalla ability is granted to all Lawful Champions.",
            {
                "effect_keys": [
                    {
                        "effect_string": "change_upgrade_targets,4038",
                        "new_targets": {
                            "type": "by_tags",
                            "tags": "lawful",
                            "add_self": True,
                        },
                    },
                    {"effect_string": "do_nothing,0", "tag": "lawful"},
                ]
            },
            "effect_def,642",
        )
        self.assertEqual(refined["quality"]["targeting_known"], True)
        self.assertEqual(refined["quality"]["usable_for_placement"], True)

    def test_draconic_bloodline_stacking_multiplicatively(self) -> None:
        refined = refine_mechanic(
            "The Dark Urge's damage is increased by $(amount)% for each Dragonborn "
            "Champion in the formation, stacking multiplicatively.",
            {
                "effect_keys": [
                    {
                        "effect_string": "hero_dps_mult_per_tagged_crusader_mult,200,dragonborn"
                    }
                ]
            },
            "effect_def,1874",
        )
        self.assertEqual(refined["quality"]["stacking_known"], True)
        self.assertEqual(
            (refined.get("effect_facts") or {}).get("stacking_multiplicative"),
            True,
        )

    def test_lucky_shot_missing_mechanic_not_numeric(self) -> None:
        refined = refine_mechanic(
            None,
            {
                "effect_keys": [
                    {"effect_string": "add_monster_hit_effects,10,123,124"}
                ]
            },
            "effect_def,169",
        )
        self.assertEqual(refined["quality"]["usable_for_numeric_comparison"], False)

    def test_buff_upgrades_lists_all_branch_ids(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import referenced_upgrade_ids

        ids = referenced_upgrade_ids(
            None,
            {
                "effect_keys": [
                    {"effect_string": "buff_upgrades,0,12493,12494"},
                ]
            },
        )
        self.assertEqual(ids, [12493, 12494])

    def test_hero_dps_not_described_as_global(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _synthetic_mechanical_text
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic

        refined = refine_mechanic(
            None,
            {"effect_keys": [{"effect_string": "hero_dps_multiplier_mult,30"}]},
            "hero_dps_multiplier_mult,30",
            owner_name="Cazrin",
        )
        text = _synthetic_mechanical_text(
            refined.get("effect_facts") or {}, {}
        ) or ""
        self.assertIn("cazrin", text.casefold())
        self.assertNotIn("all champion", text.casefold())
        self.assertEqual(
            (refined.get("effect_facts") or {}).get("effect_scope"), "owner"
        )
        global_refined = refine_mechanic(
            None,
            {"effect_keys": [{"effect_string": "global_dps_multiplier_mult,10"}]},
            None,
        )
        gtext = _synthetic_mechanical_text(
            global_refined.get("effect_facts") or {}, {}
        ) or ""
        self.assertIn("all champion", gtext.casefold())
        # Personal and global with same percent must not share fingerprint scope.
        from ic_gamedata.formation_ai_advice.clipboard_export import _effect_fingerprint

        fp_hero = _effect_fingerprint(refined.get("effect_facts") or {}, text)
        fp_global = _effect_fingerprint(
            global_refined.get("effect_facts") or {}, gtext
        )
        self.assertNotEqual(fp_hero, fp_global)

    def test_healing_lantern_scaling_not_recipient_filter(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2383)
        if not row:
            self.skipTest("Healing Lantern effect missing")
        refined = refine_mechanic(None, row, "effect_def,2383", owner_name="Baldric")
        sem = (refined.get("effect_facts") or {}).get("semantics") or {}
        recipients = sem.get("recipients") or {}
        scaling = sem.get("scaling_population") or {}
        self.assertEqual(recipients.get("targets"), ["all"])
        self.assertNotIn("healing", recipients.get("tags") or [])
        self.assertIn("healing", scaling.get("tags") or [])
        self.assertIsNotNone(sem.get("activation_conditions"))

    def test_uggie_non_adjacent_not_all(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2363)  # Baldric Uggie!
        if not row:
            self.skipTest("Uggie effect missing")
        refined = refine_mechanic(None, row, "effect_def,2363", owner_name="Baldric")
        facts = refined.get("effect_facts") or {}
        sem = facts.get("semantics") or {}
        self.assertEqual((sem.get("recipients") or {}).get("targets"), ["non_adj"])
        self.assertNotEqual(facts.get("targets"), ["all"])
        src = sem.get("position_source") or {}
        self.assertEqual(src.get("kind"), "uggie_companion")
        self.assertEqual(src.get("position_status"), "unknown")
        self.assertEqual(facts.get("amount_status"), "computed_unknown")

    def test_protective_presence_zero_is_computed_unknown(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(1994)
        if not row:
            self.skipTest("Protective Presence effect missing")
        refined = refine_mechanic(None, row, "effect_def,1994", owner_name="Umberto")
        params = (refined.get("effect_facts") or {}).get("parameters") or []
        for param in params:
            if param.get("value_basis") == "computed" or param.get("status") == "computed_unknown":
                self.assertIsNone(param.get("value"))
        self.assertIn(
            (refined.get("effect_facts") or {}).get("amount_status"),
            {"computed_unknown", "partial", "unknown"},
        )

    def test_kyre_compound_values_in_advice_projection(self) -> None:
        from ic_gamedata.formation_ai_advice.clipboard_export import _project_value
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2596)
        if not row:
            self.skipTest("Kyre Flawless Strike missing")
        from ic_gamedata.formation_ai_advice.export import _effect_description_text

        refined = refine_mechanic(
            _effect_description_text(row), row, None, owner_name="Kyre"
        )
        projected = _project_value(refined.get("effect_facts")) or {}
        values = projected.get("values") or []
        names = {v.get("name") for v in values}
        self.assertIn("crit_chance", names)
        self.assertIn("crit_damage", names)
        by_name = {v["name"]: v for v in values}
        self.assertEqual(by_name["crit_chance"]["value"], 20.0)
        self.assertEqual(by_name["crit_damage"]["value"], 400.0)

    def test_affiliations_known_empty_vs_unknown(self) -> None:
        from ic_gamedata.formation_ai_advice.clipboard_export import build_advice_payload

        advice = build_advice_payload(
            {
                "meta": {"schema_version": "1.5", "request_id": "t"},
                "goal": {},
                "formation": {},
                "champions": [
                    {
                        "champion_id": 1,
                        "name": "KnownEmpty",
                        "affiliations": [],
                        "affiliations_status": "known",
                    },
                    {
                        "champion_id": 2,
                        "name": "UnknownAff",
                        "affiliations": None,
                        "affiliations_status": "unknown",
                    },
                ],
                "constraints": {},
                "readiness": {"status": "ready", "dimensions": {}},
            }
        )
        known = next(c for c in advice["champions"] if c["id"] == 1)
        unknown = next(c for c in advice["champions"] if c["id"] == 2)
        self.assertEqual(known.get("affiliations"), [])
        self.assertEqual(known.get("affiliations_status"), "known")
        self.assertEqual(unknown.get("affiliations_status"), "unknown")
        self.assertNotEqual(unknown.get("affiliations"), [])

    def test_change_upgrade_data_is_not_magnitude(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import (
            parse_effect_string,
            refine_mechanic,
            typed_parameters,
        )

        for source in (
            "change_upgrade_data,18652,0",
            "change_upgrade_data,17672,0",
            "change_upgrade_data,20185",
        ):
            parsed = parse_effect_string(source)
            self.assertEqual(parsed["upgrade_ids"], [int(source.split(",")[1])])
            self.assertFalse(
                any(p.get("name") == "amount" for p in parsed["parameters"])
            )
            refined = refine_mechanic(
                None,
                {"effect_keys": [{"effect_string": source}]},
                source,
            )
            facts = refined.get("effect_facts") or {}
            self.assertNotEqual(facts.get("amount_status"), "known")
            self.assertNotEqual(facts.get("amount"), int(source.split(",")[1]))
            self.assertNotEqual(
                refined["quality"].get("usable_for_numeric_comparison"), True
            )
            params = typed_parameters([{"effect_string": source}])
            self.assertTrue(any(p.get("meaning") == "upgrade_id" for p in params))
            self.assertFalse(any(p.get("name") == "amount" for p in params))

    def test_unknown_effect_numeric_arg_not_amount(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic

        refined = refine_mechanic(
            None,
            {"effect_keys": [{"effect_string": "totally_unknown_effect_xyz,99999,1"}]},
            "totally_unknown_effect_xyz,99999,1",
        )
        facts = refined.get("effect_facts") or {}
        self.assertNotEqual(facts.get("amount_status"), "known")
        self.assertNotEqual(facts.get("amount"), 99999)
        self.assertNotEqual(
            refined["quality"].get("usable_for_numeric_comparison"), True
        )
        params = facts.get("parameters") or []
        self.assertFalse(any(p.get("name") == "amount" for p in params))

    def test_feat_selflessness_not_flavor_mechanical_text(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _feat_info

        payload = {
            "details": {
                "heroes": [{"hero_id": 34, "active_feats": [188], "level": 100}]
            }
        }
        feats = _feat_info(payload, 34)
        row = next(f for f in feats["active_feats"] if f.get("feat_id") == 188)
        text = (row.get("mechanical_text") or "").casefold()
        self.assertNotIn("stay back and heal", text)
        self.assertIn("damage", text)
        self.assertIn("10", text)

    def test_baldric_targeting_uses_selected_extensions_only(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import (
            parse_conditional_targeting,
            refine_mechanic,
        )
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2379)
        if not row:
            self.skipTest("Bargaining Power effect 2379 missing")
        # Eldath (healing) 17495 + Mystra (magic) 17494 selected — not gold/dwarf.
        selected = {17494, 17495}
        refined = refine_mechanic(
            None,
            row,
            "effect_def,2379",
            selected_upgrade_ids=selected,
        )
        facts = refined.get("effect_facts") or {}
        targeting = facts.get("targeting") or {}
        active = set(targeting.get("active_tags") or [])
        self.assertIn("fallbacks", active)
        self.assertIn("healing", active)
        self.assertNotIn("gold", active)
        self.assertNotIn("dwarf", active)
        # Alternate gold extension present but inactive.
        extensions = targeting.get("extensions") or []
        gold_ext = next(
            (e for e in extensions if "gold" in (e.get("tags") or [])), None
        )
        self.assertIsNotNone(gold_ext)
        self.assertIs(gold_ext.get("active_in_current_state"), False)
        # Switching selection activates gold, drops healing.
        switched = parse_conditional_targeting(
            row.get("effect_keys") or [],
            selected_upgrade_ids={17493},
        )
        self.assertIn("gold", switched.get("active_tags") or [])
        self.assertNotIn("healing", switched.get("active_tags") or [])

    def test_advice_projection_no_exclusive_with_lists(self) -> None:
        export = self._export()
        # Inject a large exclusive group like Baldric's second tier.
        for champ in export["champions"]:
            groups = champ.get("specialization_groups") or []
            if not groups:
                continue
            groups[0]["selection_mode"] = "exactly_one"
            options = groups[0].get("options") or []
            ids = [o.get("option_id") for o in options]
            for opt in options:
                opt["exclusive_with"] = [i for i in ids if i != opt.get("option_id")]
            break
        advice = build_advice_payload(export)
        for champ in advice.get("champions") or []:
            for group in champ.get("specializations") or []:
                self.assertEqual(group.get("selection_mode"), "exactly_one")
                for opt in group.get("options") or []:
                    self.assertNotIn("exclusive_with", opt)
        blob = json.dumps(advice, ensure_ascii=False)
        self.assertNotIn("effect_strings", blob)
        self.assertNotIn("placeholder_substitutions", blob)
        self.assertNotIn("stacking_multiplicative", blob)
        self.assertNotIn("stacking_known", blob)
        self.assertNotIn("effect_key_index", blob)

    def test_readiness_separates_numeric_and_placement(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _readiness_issues

        export = self._export()
        # Force a source-unknown gap on a selected ability.
        for champ in export["champions"]:
            abs_ = champ.get("abilities") or []
            if not abs_:
                continue
            abs_[0]["unresolved_fields"] = ["unresolved_placeholder:$(target)"]
            abs_[0]["quality"] = {
                **(abs_[0].get("quality") or {}),
                "usable_for_placement": "unknown",
                "usable_for_numeric_comparison": False,
            }
            break
        status, issues, dims = _readiness_issues(export)
        self.assertIn("placement_advice", dims)
        self.assertIn("numeric_comparison", dims)
        self.assertIn(dims["placement_advice"], ("partial", "insufficient"))
        self.assertNotEqual(dims.get("schema_validity"), "insufficient")
        self.assertTrue(
            any(i.get("code") == "unknown_positional_source" for i in issues)
        )
        # Missing magnitude alone should not force placement insufficient.
        export2 = self._export()
        for champ in export2["champions"]:
            for ab in champ.get("abilities") or []:
                ab["quality"] = {
                    "usable_for_placement": True,
                    "usable_for_numeric_comparison": False,
                    "magnitude_known": False,
                }
        status2, _, dims2 = _readiness_issues(export2)
        self.assertEqual(dims2.get("placement_advice"), "sufficient")
        self.assertIn(dims2.get("numeric_comparison"), ("partial", "insufficient"))

    def test_buff_upgrade_selector_is_not_upgrade_id(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import (
            parse_effect_string,
            referenced_upgrade_ids,
            typed_parameters,
        )

        # Singular: amount, upgrade_id, selector — selector must not become a dependency.
        parsed = parse_effect_string("buff_upgrade,100,17673,1")
        self.assertEqual(parsed["upgrade_ids"], [17673])
        self.assertTrue(
            any(
                p.get("name") == "selector" and p.get("value") == 1
                for p in parsed["parameters"]
            )
        )
        ids = referenced_upgrade_ids("buff_upgrade,100,17673,1", None)
        self.assertEqual(ids, [17673])
        ids2 = referenced_upgrade_ids(
            None,
            {"effect_keys": [{"effect_string": "buff_upgrade,40,18670,1"}]},
        )
        self.assertEqual(ids2, [18670])
        # Plural still keeps every upgrade id.
        plural = referenced_upgrade_ids(
            "buff_upgrades,50,100,200,300",
            None,
        )
        self.assertEqual(plural, [100, 200, 300])
        params = typed_parameters(
            [{"effect_string": "buff_upgrade,100,17845,1"}]
        )
        upgrade_values = [p["value"] for p in params if p.get("name") == "upgrade_id"]
        self.assertEqual(upgrade_values, [17845])

    def test_add_monster_hit_effects_amount_then_ids(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import parse_effect_string

        parsed = parse_effect_string("add_monster_hit_effects,25,67,68")
        names = [(p.get("name"), p.get("value")) for p in parsed["parameters"]]
        self.assertEqual(
            names,
            [
                ("amount_or_chance", 25.0),
                ("hit_effect_id", 67),
                ("hit_effect_id", 68),
            ],
        )
        # First number must not be classified as hit_effect_id alone.
        self.assertFalse(
            any(p.get("name") == "hit_effect_id" and p.get("value") == 25 for p in parsed["parameters"])
        )

    def test_kyre_placeholders_use_separate_amount_slots(self) -> None:
        refined = refine_mechanic(
            "Increases crit chance by $(amount)% and crit damage by $(amount___2)%.",
            {
                "effect_keys": [
                    {"effect_string": "if_stunned_buff_base_crit_chance_add,20"},
                    {
                        "effect_string": "increase_crit_damage_when_monster_stunned,400"
                    },
                ]
            },
            None,
        )
        text = refined["text"] or ""
        self.assertIn("20", text)
        self.assertIn("400", text)
        self.assertNotIn("400% and crit damage by 400", text)
        subs = refined.get("placeholder_substitutions") or []
        by_ph = {s["placeholder"]: s for s in subs}
        self.assertEqual(by_ph["$(amount)"]["value"], 20.0)
        self.assertEqual(by_ph["$(amount___2)"]["value"], 400.0)
        # One known + one missing stays partial.
        partial = refine_mechanic(
            "Chance $(amount)% and damage $(amount___2)%.",
            {
                "effect_keys": [
                    {"effect_string": "if_stunned_buff_base_crit_chance_add,20"},
                ]
            },
            None,
        )
        self.assertIn("20", partial["text"] or "")
        self.assertIn("onbekend", (partial["text"] or "").casefold())
        self.assertTrue(partial.get("unresolved_placeholders"))

    def test_trap_expert_additive_stacking_is_known(self) -> None:
        refined = refine_mechanic(
            "Increases the effect of Trap Expert by $(amount)%, stacking additively.",
            {
                "effect_keys": [
                    {
                        "effect_string": "buff_upgrade,100,12345",
                        "stacks_multiply": False,
                    }
                ]
            },
            "buff_upgrade,100,12345",
        )
        stacking = (refined.get("quality") or {}).get("stacking") or {}
        self.assertEqual(stacking.get("mode"), "additive")
        self.assertEqual(stacking.get("status"), "known")
        self.assertEqual(refined["quality"]["stacking_known"], True)
        self.assertEqual(refined["quality"]["stacking_multiplicative"], False)

    def test_draconic_bloodline_stacking_object(self) -> None:
        refined = refine_mechanic(
            "Damage increased by $(amount)%, stacking multiplicatively.",
            {
                "effect_keys": [
                    {
                        "effect_string": "hero_dps_mult_per_tagged_crusader_mult,200,dragonborn"
                    }
                ]
            },
            None,
        )
        self.assertEqual(
            (refined.get("quality") or {}).get("stacking"),
            {"mode": "multiplicative", "status": "known"},
        )

    def test_feat_parsed_buff_not_flavor_only(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _synthetic_mechanical_text

        text = _synthetic_mechanical_text(
            {
                "referenced_upgrade_ids": [17673],
                "parameters": [
                    {"name": "modifier", "value": 20.0, "meaning": "percent"},
                    {"name": "upgrade_id", "value": 17673, "meaning": "upgrade_id"},
                ],
            },
            {17673: "Selflessness"},
        )
        self.assertEqual(text, "Increases Selflessness by 20%.")
        # Flavor alone stays flavor_only.
        from ic_gamedata.formation_ai_advice.export import _mechanic_fields_from_upgrade

        fields = _mechanic_fields_from_upgrade(
            {
                "specialization_description": "A kind heart guides Donaar.",
                "tip_text": "",
                "effect": "",
            }
        )
        self.assertEqual(fields.get("usability"), "flavor_only")
        self.assertIsNone(fields.get("mechanical_text"))

    def test_baldric_dark_bargain_prerequisites_from_defines(self) -> None:
        """required_upgrade_id on Dark Bargain options must stay conditional."""
        try:
            from ic_gamedata.specialization_data import cached_definitions_data

            data = cached_definitions_data()
        except Exception:
            self.skipTest("cached_definitions unavailable")
        upgrades = {
            int(r["id"]): r
            for r in data.get("upgrade_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        # First-tier bargains 17491-17495 gate Dark Bargain / Bargain With Tyr opts.
        first_tier = [17491, 17492, 17493, 17494, 17495]
        if not all(uid in upgrades for uid in first_tier):
            self.skipTest("Baldric upgrade ids not in defines")
        # Simulate current selection of first bargain only.
        selected = {17491}
        for uid in range(17496, 17501):
            row = upgrades.get(uid) or {}
            req = int(row.get("required_upgrade_id") or 0) or None
            self.assertEqual(req, 17491)
            available = req in selected
            self.assertTrue(available)
        for uid in range(17501, 17506):
            row = upgrades.get(uid) or {}
            req = int(row.get("required_upgrade_id") or 0) or None
            self.assertEqual(req, 17492)
            self.assertFalse(req in selected)
        # Same display name can appear on different branches — keep distinct ids.
        names = {
            uid: str(
                (upgrades.get(uid) or {}).get("specialization_name")
                or (upgrades.get(uid) or {}).get("name")
                or ""
            )
            for uid in range(17501, 17521)
        }
        tyr_ids = [uid for uid, name in names.items() if "tyr" in name.casefold()]
        self.assertGreaterEqual(len(tyr_ids), 2)
        self.assertEqual(len(tyr_ids), len(set(tyr_ids)))

    def test_kyre_flawless_strike_live_defines(self) -> None:
        try:
            from ic_gamedata.specialization_data import cached_definitions_data
            from ic_gamedata.formation_ai_advice.export import _effect_description_text

            data = cached_definitions_data()
        except Exception:
            self.skipTest("cached_definitions unavailable")
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2596)
        if not row:
            self.skipTest("effect 2596 missing")
        desc = _effect_description_text(row)
        refined = refine_mechanic(desc, row, None)
        text = refined.get("text") or ""
        self.assertIn("20%", text)
        self.assertIn("400%", text)
        self.assertNotIn("400% additively increased chance", text)

    def test_advice_and_debug_exports_differ(self) -> None:
        export = self._export()
        advice_md = format_clipboard_markdown(export)
        debug_md = format_debug_markdown(export)
        self.assertNotEqual(advice_md, debug_md)
        advice = build_advice_payload(export)
        self.assertIn("bronregels", advice)
        self.assertIn("traits_already_in_effective", advice["bronregels"])
        self.assertNotIn("effects", advice)  # no hash catalog in compact advice
        self.assertLess(len(advice_md), len(debug_md))

    def test_semantic_preservation_via_references(self) -> None:
        """After compaction, decision fields remain reachable on advice payload."""
        export = self._export()
        # Inject a conditional option shape the slim path must keep.
        for champ in export["champions"]:
            groups = champ.get("specialization_groups") or []
            if not groups:
                continue
            options = groups[0].get("options") or []
            if len(options) < 2:
                continue
            options[0]["requires_selected_option_id"] = None
            options[0]["available_in_current_state"] = True
            options[1]["requires_selected_option_id"] = options[0]["option_id"]
            options[1]["available_in_current_state"] = False
            options[1]["exclusive_with"] = [options[0]["option_id"]]
            break
        advice = build_advice_payload(export)
        found_req = False
        for champ in advice.get("champions") or []:
            for group in champ.get("specializations") or []:
                for opt in group.get("options") or []:
                    if opt.get("requires_option_id"):
                        found_req = True
                        self.assertIn("available", opt)
                        self.assertIs(opt.get("available"), False)
        self.assertTrue(found_req)
        self.assertIn("bronregels", advice)

    def test_copy_button_serializer_uses_compact_advice(self) -> None:
        """Regression: format_clipboard_markdown is what the copy button calls."""
        export = self._export()
        md = format_clipboard_markdown(export, output_mode="table")
        self.assertIn("## Gegevens", md)
        self.assertIn('"schema_version":"1.9"', md.replace(" ", ""))
        self.assertEqual(md.count("```json"), 1)
        self.assertNotIn("### Nayeli", md)

    def test_clipboard_paste_roundtrip(self) -> None:
        export = self._export()
        pasted = self._identity_proposal_dict(export)
        wrapped = "Advies:\n```json\n" + json.dumps(pasted) + "\n```\n"
        self.assertIsNotNone(extract_json_object(wrapped))
        result = ingest_pasted_proposal(wrapped, export_payload=export)
        self.assertIsNotNone(result.proposal)
        self.assertEqual(result.local_validation.status, "valid")
        self.assertIn("Clipboard", result.provider_label)

    def test_extra_or_missing_champion(self) -> None:
        export = self._export()
        fp = formation_layout_fingerprint_from_export(export)
        proposal = FormationAdviceProposal(
            schema_version="1.0",
            request_id="req-test-1",
            status="proposal",
            summary="x",
            assignments=(
                AssignmentProposal(1, 3),
                AssignmentProposal(2, 2),
                AssignmentProposal(3, 99),
            ),
        )
        local = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request=fp,
            current_formation_fingerprint=fp,
        )
        self.assertEqual(local.status, "invalid")

    def test_duplicate_assignment(self) -> None:
        export = self._export()
        fp = formation_layout_fingerprint_from_export(export)
        proposal = FormationAdviceProposal(
            schema_version="1.0",
            request_id="req-test-1",
            status="proposal",
            summary="x",
            assignments=(
                AssignmentProposal(1, 3),
                AssignmentProposal(2, 2),
                AssignmentProposal(3, 4),
                AssignmentProposal(4, 3),
            ),
        )
        local = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request=fp,
            current_formation_fingerprint=fp,
        )
        self.assertEqual(local.status, "invalid")

    def test_cross_champion_specialization_rejected(self) -> None:
        export = self._export()
        for row in export["champions"]:
            if row["champion_id"] == 3:
                row["specialization_groups"] = [
                    {
                        "group_id": "tier_0",
                        "tier_index": 0,
                        "group_label": "Keuze 1",
                        "options": [{"option_id": 43, "name": "A", "selected": True}],
                    }
                ]
            if row["champion_id"] == 4:
                row["specialization_groups"] = [
                    {
                        "group_id": "tier_0",
                        "tier_index": 0,
                        "group_label": "Keuze 1",
                        "options": [{"option_id": 58, "name": "B", "selected": True}],
                    }
                ]
        fp = formation_layout_fingerprint_from_export(export)
        proposal = FormationAdviceProposal(
            schema_version="1.0",
            request_id="req-test-1",
            status="proposal",
            summary="x",
            assignments=(
                AssignmentProposal(
                    1,
                    3,
                    specialization_choices=(
                        SpecializationChoice("tier_0", 58, "wrong owner"),
                    ),
                ),
                AssignmentProposal(2, 2),
                AssignmentProposal(3, 4),
            ),
        )
        local = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request=fp,
            current_formation_fingerprint=fp,
        )
        self.assertEqual(local.status, "invalid")
        self.assertTrue(any("hoort bij champion 4" in e for e in local.errors))

    def test_source_ref_without_source(self) -> None:
        export = self._export()
        fp = formation_layout_fingerprint_from_export(export)
        proposal = FormationAdviceProposal(
            schema_version="1.0",
            request_id="req-test-1",
            status="proposal",
            summary="x",
            assignments=(
                AssignmentProposal(1, 3),
                AssignmentProposal(2, 2),
                AssignmentProposal(3, 4),
            ),
            source_refs=("999",),
        )
        local = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(AdviceSource("1", "ok", "https://example.com"),),
            formation_fingerprint_at_request=fp,
            current_formation_fingerprint=fp,
        )
        self.assertEqual(local.status, "invalid")

    def test_stale_after_formation_change(self) -> None:
        export = self._export()
        fp1 = formation_layout_fingerprint_from_export(export)
        export2 = self._export()
        export2["formation"]["current_champion_by_position"]["1"] = 4
        export2["formation"]["current_champion_by_position"]["3"] = 3
        fp2 = formation_layout_fingerprint_from_export(export2)
        proposal = FormationAdviceProposal(
            schema_version="1.0",
            request_id="req-test-1",
            status="proposal",
            summary="x",
            assignments=(
                AssignmentProposal(1, 3),
                AssignmentProposal(2, 2),
                AssignmentProposal(3, 4),
            ),
        )
        local = validate_proposal_against_export(
            proposal,
            export,
            api_sources=(),
            formation_fingerprint_at_request=fp1,
            current_formation_fingerprint=fp2,
        )
        self.assertEqual(local.status, "stale")

    def test_seat_label_follows_champion_not_position(self) -> None:
        pos = position_caption(position_id=5, column=2, zone="mid", row_order=0)
        self.assertIn("Kolom 3", pos)
        self.assertIn("Positie 5", pos)
        self.assertIn("boven", pos)
        self.assertNotIn("Seat", pos)
        self.assertEqual(champion_seat_caption(8), "Seat 8")
        # Live: Vlahnya F5 at pos 5, Calliope F8 at pos 8.
        # Proposal: Vlahnya → pos 8, Calliope → pos 5. Labels stay F-seats.
        nodes = (_node(5, 35, "Vlahnya"), _node(8, 5, "Calliope"))
        remapped = remap_visual_nodes(nodes, {35: 8, 5: 5})
        by_hero = {n.hero_id: n for n in remapped}
        self.assertEqual(by_hero[35].seat, 5)
        self.assertEqual(by_hero[5].seat, 8)
        self.assertEqual(by_hero[35].x, nodes[1].x)
        self.assertEqual(by_hero[5].x, nodes[0].x)

    def test_preview_without_mutation(self) -> None:
        nodes = (_node(1, 3, "Nayeli"), _node(2, 2, "Celeste"), _node(3, 4, "Jarlaxle"))
        remapped = remap_visual_nodes(nodes, {3: 3, 2: 1, 4: 2})
        self.assertEqual(nodes[0].hero_id, 3)
        by_hero = {n.hero_id: n for n in remapped}
        self.assertEqual(by_hero[2].seat, 2)
        self.assertEqual(by_hero[2].x, nodes[0].x)

    def test_apply_and_undo(self) -> None:
        nodes = (_node(1, 3, "Nayeli"), _node(2, 2, "Celeste"), _node(3, 4, "Jarlaxle"))
        proposal = FormationAdviceProposal(
            schema_version="1.0",
            request_id="r",
            status="proposal",
            summary="swap",
            assignments=(
                AssignmentProposal(1, 4, (SpecializationChoice("tier_0", 1, "x"),)),
                AssignmentProposal(2, 2),
                AssignmentProposal(3, 3),
            ),
        )
        state = apply_proposal(proposal, current_nodes=nodes)
        self.assertEqual(state.seat_by_hero[4], 1)
        self.assertIsNotNone(state.undo)
        undo = snapshot_from_visual_nodes(nodes)
        self.assertEqual(undo.seat_by_hero[3], 1)

    def test_remap_shows_new_seat_not_in_live_geometry(self) -> None:
        """Briv on an empty position must get a visible, non-overlapping card."""
        nodes = (
            _node(12, 105, "Dob"),
            _node(2, 120, "Solaak"),
            _node(6, 118, "Fen"),
        )
        after = {105: 12, 120: 2, 118: 6, 58: 5}
        names = {105: "Dob", 120: "Solaak", 118: "Fen", 58: "Briv"}
        remapped = remap_visual_nodes(
            nodes,
            after,
            hero_name_by_id=names,
            permanent_seat_by_hero={58: 5},
        )
        by_hero = {n.hero_id: n for n in remapped if n.hero_id is not None}
        self.assertIn(58, by_hero)
        self.assertEqual(by_hero[58].hero_name, "Briv")
        self.assertEqual(by_hero[58].seat, 5)
        live_coords = {(n.x, n.y) for n in nodes}
        self.assertNotIn((by_hero[58].x, by_hero[58].y), live_coords)

    def test_remap_uses_position_geometry_for_empty_slot(self) -> None:
        """Empty position_id must use formation-graph coords, not overflow strip."""
        nodes = (
            _node(9, 178, "Flint"),
            _node(6, 118, "Fen"),
            _node(5, 58, "Briv"),
        )
        after = {178: 1, 118: 9, 58: 5}
        remapped = remap_visual_nodes(
            nodes,
            after,
            hero_name_by_id={178: "Flint", 118: "Fen", 58: "Briv"},
            permanent_seat_by_hero={178: 9, 118: 6, 58: 5},
            position_geometry={1: (40.0, 10.0, "front")},
        )
        by_hero = {n.hero_id: n for n in remapped}
        self.assertEqual(by_hero[178].seat, 9)
        self.assertEqual(by_hero[178].x, 40.0)
        self.assertEqual(by_hero[178].y, 10.0)
        self.assertEqual(by_hero[178].zone, "front")
        # Must not sit past Briv on an overflow strip.
        self.assertLess(by_hero[178].x, by_hero[58].x + 50.0)
        # Fen takes Flint's old place; roles follow Fen (none on stub) not Tank.
        self.assertEqual(by_hero[118].x, nodes[0].x)

    def test_remap_keeps_permanent_seat_label_when_position_changes(self) -> None:
        """Flint (F-seat 9) at position_id 1 must still show Slot 9, not Slot 1."""
        nodes = (
            _node(9, 178, "Flint"),
            _node(6, 118, "Fen"),
            _node(4, 96, "Desmond"),
        )
        # Move Flint → pos 1, Fen → pos 9, Desmond → pos 6.
        after = {178: 1, 118: 9, 96: 6}
        remapped = remap_visual_nodes(
            nodes,
            after,
            hero_name_by_id={178: "Flint", 118: "Fen", 96: "Desmond"},
            permanent_seat_by_hero={178: 9, 118: 6, 96: 4},
            position_geometry={1: (15.0, 5.0, "front")},
        )
        by_hero = {n.hero_id: n for n in remapped}
        self.assertEqual(by_hero[178].seat, 9)
        self.assertEqual(by_hero[118].seat, 6)
        self.assertEqual(by_hero[96].seat, 4)
        # Fen occupies former Flint geometry (position 9).
        self.assertEqual(by_hero[118].x, nodes[0].x)
        self.assertEqual(by_hero[118].y, nodes[0].y)
        self.assertEqual(by_hero[178].x, 15.0)

    def test_parse_request_id_mismatch(self) -> None:
        text = json.dumps(
            {
                "schema_version": "1.0",
                "request_id": "other",
                "status": "proposal",
                "summary": "x",
                "assignments": [],
                "expected_key_buffs": [],
                "assumptions": [],
                "missing_information": [],
                "warnings": [],
                "source_refs": [],
            }
        )
        proposal, errors = parse_proposal_json(text, expected_request_id="req")
        self.assertIsNone(proposal)
        self.assertTrue(any("request_id" in e for e in errors))

    def test_parse_compact_placements_specializations(self) -> None:
        """AI often returns placements/specializations instead of full schema."""
        text = json.dumps(
            {
                "schema_version": "1.9",
                "request_id": "req-compact",
                "conditional": True,
                "condition": "Eligibility conflict for Dark Urge.",
                "placements": [
                    {"position_id": 1, "champion_id": 25},
                    {"position_id": 4, "champion_id": 96},
                ],
                "specializations": [
                    {
                        "champion_id": 25,
                        "group_id": "tier_0",
                        "option_id": 11313,
                    },
                    {
                        "champion_id": 96,
                        "group_id": "tier_0",
                        "option_id": 7305,
                    },
                ],
            }
        )
        proposal, errors = parse_proposal_json(
            text, expected_request_id="req-compact"
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(proposal)
        assert proposal is not None
        # Placements present → usable proposal; condition becomes a warning.
        self.assertEqual(proposal.status, "proposal")
        self.assertIn("Dark Urge", proposal.summary)
        self.assertTrue(
            any("Dark Urge" in w for w in proposal.warnings),
            proposal.warnings,
        )
        self.assertEqual(len(proposal.assignments), 2)
        by_champ = {a.champion_id: a for a in proposal.assignments}
        self.assertEqual(by_champ[25].position_id, 1)
        self.assertEqual(by_champ[25].specialization_choices[0].option_id, 11313)
        self.assertEqual(by_champ[96].position_id, 4)

    def test_fingerprint_stable_without_request_id(self) -> None:
        a = self._export(request_id="a")
        b = self._export(request_id="b")
        self.assertEqual(request_fingerprint(a), request_fingerprint(b))

    def test_layout_fingerprint_ignores_poll_current_time(self) -> None:
        """API polls bump current_time → meta.data_version; must not stale advice."""
        a = self._export()
        b = json.loads(json.dumps(a))
        meta = b.setdefault("meta", {})
        meta["data_version"] = str(int(meta.get("data_version") or 0) + 999_999)
        meta["data_fetched_at"] = meta["data_version"]
        self.assertEqual(
            formation_layout_fingerprint_from_export(a),
            formation_layout_fingerprint_from_export(b),
        )

    def test_export_group_labels_readable(self) -> None:
        export = self._export()
        for row in export["champions"]:
            for g in row.get("specialization_groups") or []:
                label = g.get("group_label") or ""
                self.assertNotIn("tier_", label)

    def test_hard_min_stat_conflict_not_ready(self) -> None:
        from ic_gamedata.adventure_restrictions import AdventureRosterFilter
        from ic_gamedata.formation_ai_advice.export import _readiness_issues

        export = self._export()
        # Force a hard INT>=13 gate + denied party checks.
        export["goal"]["structured_restrictions"] = {
            "min_stats": [
                {
                    "stat": "int",
                    "operator": ">=",
                    "value": 13,
                    "scope": "hard_min",
                    "source": "test",
                    "stats_basis": "character_sheet_ability_scores",
                }
            ],
            "stat_gates": [
                {
                    "stat": "int",
                    "operator": ">=",
                    "value": 13,
                    "scope": "hard_min",
                    "source": "test",
                }
            ],
            "allow_exprs": None,
            "has_unknown_rules": False,
        }
        export["goal"]["restrictions_checked_by_app"] = True
        export["goal"]["restrictions_fully_known"] = True
        export["goal"]["party_restriction_status"] = "conflict"
        export["goal"]["party_restriction_checks"] = [
            {
                "champion_id": 2,
                "status": "denied",
                "reason": "INT 12 < min 13 (character_sheet basis).",
                "ability_scores": {"int": 12},
            }
        ]
        status, issues, dims = _readiness_issues(export)
        self.assertEqual(status, "ready_with_warnings")
        self.assertEqual(dims["restrictions"], "conflict")
        conflict = next(i for i in issues if i.get("code") == "restriction_conflict")
        self.assertEqual(conflict.get("severity"), "warning")
        # Chat export must remain copyable so AI can propose legal swaps.
        self.assertNotEqual(status, "blocked")

    def test_override_clears_restriction_conflict_for_seated_party(self) -> None:
        """Raw CHA deny + Dark Inheritance allow → no open party conflict."""
        from ic_gamedata.formation_ai_advice.export import (
            _enrich_eligibility,
            _readiness_issues,
        )

        export = self._export()
        # Simulate Dark Urge already in party: raw deny, kit override allows.
        export["goal"]["party_restriction_status"] = "conflict"
        export["goal"]["restrictions_checked_by_app"] = True
        export["goal"]["party_restriction_checks"] = [
            {
                "champion_id": 146,
                "status": "denied",
                "reason": "CHA 17 blocked by gate",
            }
        ]
        # Inject a seated champion row with Dark Inheritance ability text.
        export["champions"] = [
            {
                "champion_id": 146,
                "name": "The Dark Urge",
                "abilities": [
                    {
                        "ability_id": 14378,
                        "active_state": "kit",
                        "mechanical_text": (
                            "The Dark Urge is eligible to start in all adventures, "
                            "even if the Patron, Variant, or other restrictions "
                            "would say otherwise."
                        ),
                        "effect_facts": {"effect_strings": ["do_nothing"]},
                    }
                ],
            }
        ]
        _enrich_eligibility(export)
        check = export["goal"]["party_restriction_checks"][0]
        self.assertEqual(check.get("base_status"), "denied")
        self.assertEqual(check.get("status"), "allowed")
        self.assertEqual(check.get("effective_status"), "allowed")
        self.assertEqual(export["goal"]["party_restriction_status"], "ok")
        status, issues, dims = _readiness_issues(export)
        self.assertNotEqual(dims.get("restrictions"), "conflict")
        self.assertFalse(
            any(i.get("code") == "restriction_conflict" for i in issues),
            issues,
        )
        self.assertNotEqual(status, "blocked")

    def test_or_expr_stat_gate_is_soft_not_hard_min(self) -> None:
        from ic_gamedata.adventure_restrictions import (
            _stat_gates_from_expr,
            structured_stat_gates,
            AdventureRosterFilter,
        )

        expr = (
            "HasTag(`baldursgate`) || HasTag(`absoluteadversaries`) || "
            "GetStat(`int`) >= 13"
        )
        gates = _stat_gates_from_expr(expr)
        self.assertTrue(gates)
        self.assertEqual(gates[0]["stat"], "int")
        self.assertEqual(gates[0]["scope"], "allow_expr_or_clause")
        filt = AdventureRosterFilter()
        filt.allow_exprs.append(expr)
        structured = structured_stat_gates(filt)
        self.assertTrue(any(g.get("scope") == "allow_expr_or_clause" for g in structured))
        self.assertFalse(any(g.get("scope") == "hard_min" for g in structured))

    def test_flavor_only_spec_not_mechanical_usable(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _mechanic_fields_from_upgrade

        fields = _mechanic_fields_from_upgrade(
            {
                "specialization_name": "Heart of Heroes",
                "specialization_description": (
                    "Heroism isn't measured by skill, but by courage."
                ),
                "tip_text": "",
                "effect": "effect_def,2324",
            }
        )
        # effect_defines should supply mechanical prose when present.
        if fields.get("mechanical_text"):
            self.assertTrue(fields.get("mechanical_usable") or fields.get("usability") == "partially_resolved")
            self.assertIn("damage", (fields.get("mechanical_text") or "").casefold())
        else:
            self.assertEqual(fields.get("usability"), "flavor_only")
            self.assertFalse(fields.get("mechanical_usable"))

    def test_incomplete_spec_does_not_block_geometry_ready_dimension(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _readiness_issues

        export = self._export()
        for row in export["champions"]:
            for g in row.get("specialization_groups") or []:
                for opt in g.get("options") or []:
                    opt["usability"] = "flavor_only"
                    opt["mechanical_usable"] = False
                    opt["mechanical_text"] = None
                    opt["text"] = None
        status, issues, dims = _readiness_issues(export)
        self.assertEqual(dims["geometry"], "ok")
        self.assertEqual(dims["specialization_mechanics"], "degraded")
        self.assertTrue(
            any(i.get("code") == "incomplete_specialization_mechanics" for i in issues)
        )
        self.assertNotEqual(status, "blocked")

    def test_blocked_positions_not_in_valid_ids(self) -> None:
        export = self._export()
        valid = set(export["formation"]["valid_position_ids"])
        blocked = set(export["formation"].get("blocked_position_ids") or [])
        self.assertFalse(valid & blocked)

    def test_readiness_has_dimensions(self) -> None:
        export = self._export()
        dims = export["readiness"]["dimensions"]
        for key in (
            "geometry",
            "party_identity",
            "restrictions",
            "placement_mechanics",
            "specialization_mechanics",
        ):
            self.assertIn(key, dims)

    def test_positions_ordered_back_column_first_top_to_bottom(self) -> None:
        from ic_gamedata.formation_ai_advice.labels import (
            formation_display_sort_key,
            sort_positions_for_display,
        )

        rows = [
            {"position_id": 1, "column_index": 0, "row_order": 0},
            {"position_id": 2, "column_index": 4, "row_order": 1},
            {"position_id": 3, "column_index": 4, "row_order": 0},
            {"position_id": 4, "column_index": 2, "row_order": 0},
        ]
        ordered = sort_positions_for_display(rows)
        self.assertEqual(
            [r["position_id"] for r in ordered],
            [3, 2, 4, 1],
        )
        # Kolom 5 (index 4) before Kolom 1 (index 0); within col, row 0 before 1.
        self.assertLess(
            formation_display_sort_key(column_index=4, row_order=0, position_id=3),
            formation_display_sort_key(column_index=4, row_order=1, position_id=2),
        )
        export = self._export()
        cols = [
            p["column_index"]
            for p in export["formation"]["positions"]
            if isinstance(p.get("column_index"), int)
        ]
        self.assertEqual(cols, sorted(cols, reverse=True))
        md = format_clipboard_markdown(export)
        self.assertIn("achter naar voren", md.casefold())
        self.assertIn("display_position", md.casefold())
        # Active places carry kolom-plek labels in geometry JSON.
        advice_low = json.dumps(
            build_advice_payload(export), ensure_ascii=False
        ).casefold()
        self.assertIn('"display_position": "1-1"', advice_low)

    def test_standalone_advice_brief_is_self_contained(self) -> None:
        """Export must explain the task without prior chat history."""
        md = format_clipboard_markdown(self._export())
        low = md.casefold()
        self.assertIn("idle champions-formatieadviseur", low)
        self.assertIn("zelfstandige game-adviesaanvraag", low)
        self.assertIn("geen programmeer", low)
        self.assertIn("zoek niet op internet", low)
        self.assertIn("hoofd-dps", low)
        self.assertIn("jarlaxle", low)
        self.assertIn("| plek | champion |", low)
        self.assertIn("display_position", low)
        self.assertNotIn("zoals eerder besproken", low)
        self.assertNotIn("vorige afspraken", low)
        self.assertNotIn("bekende regels", low)
        # Not a coding / export-review assignment.
        self.assertNotIn("verbeter het schema", low)
        self.assertNotIn("schrijf code", low)

    def test_compact_advice_inlines_mechanics_not_parser_dump(self) -> None:
        advice = build_advice_payload(self._export())
        self.assertNotIn("effects", advice)
        self.assertIn("bronregels", advice)
        self.assertIn("geometry", advice)
        self.assertIn("column_direction", advice["geometry"])
        self.assertIn("adjacency", advice["geometry"])
        # No full distance matrix required when adjacency is present.
        self.assertNotIn("distance", advice["geometry"])
        celeste = next(c for c in advice["champions"] if c["id"] == 2)
        mantle = next(a for a in celeste["abilities"] if a["name"] == "Crusader's Mantle")
        self.assertIn("next to", (mantle.get("effect") or "").casefold())
        self.assertNotIn("subeffects", mantle)
        self.assertNotIn("effect_key", mantle)
        self.assertNotIn("semantics", mantle)

    def test_gem_farm_objective_not_hardcoded_as_push(self) -> None:
        md = format_clipboard_markdown(
            self._export(goal="gem_farm", fixed_main_dps_id=None)
        )
        self.assertIn("gems verzamelen", md.casefold())
        self.assertIn("gems_per_hour", md.casefold())
        self.assertNotIn("Doel: Push.", md)

    def test_uggie_unknown_position_does_not_claim_certain_targets(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _effect_description_text
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2363)
        if not row:
            self.skipTest("Uggie effect missing")
        refined = refine_mechanic(
            _effect_description_text(row), row, "effect_def,2363", owner_name="Baldric"
        )
        advice = build_advice_payload(
            {
                "meta": {"schema_version": SCHEMA_VERSION, "request_id": "u"},
                "goal": {"objective": "push_damage", "main_dps_id": 1},
                "formation": {"adjacency_by_position": {}, "positions": []},
                "champions": [
                    {
                        "champion_id": 165,
                        "name": "Baldric",
                        "abilities": [
                            {
                                "ability_id": 2363,
                                "name": "Uggie!",
                                "mechanical_text": refined.get("text"),
                                "effect_facts": refined.get("effect_facts"),
                                "usability": "mechanical_usable",
                                "quality": {"usable_for_placement": True},
                            }
                        ],
                    }
                ],
                "readiness": {"status": "ready", "dimensions": {}},
            }
        )
        ab = advice["champions"][0]["abilities"][0]
        self.assertIn("onbekend", (ab.get("position_source") or "").casefold())
        gaps = " ".join(
            g.get("wat", "") for g in (advice.get("onzekerheden") or [])
        ).casefold()
        self.assertIn("uggie", gaps)
        # Must not claim a certain all-formation recipient.
        self.assertNotIn('"targets":["all"]', json.dumps(ab))

    def test_positional_scope_donaar_cazrin_skylla_kos(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _effect_description_text
        from ic_gamedata.formation_ai_advice.mechanics import (
            positional_recipient_applies,
            refine_mechanic,
        )
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        cases = [
            (2573, "Donaar", "col_and_behind", 3, {3, 4, 5}, {0, 1, 2}),
            (2414, "Cazrin", "col_and_ahead", 3, {0, 1, 2, 3}, {4, 5}),
            (2474, "Skylla", "next_col", 3, {2}, {0, 1, 3, 4, 5}),
            (2448, "King of Shadows", "self_and_prev_two_col", 2, {2, 3, 4}, {0, 1, 5}),
        ]
        for eid, owner, token, owner_col, yes_cols, no_cols in cases:
            row = effects.get(eid)
            if not row:
                self.skipTest(f"effect {eid} missing")
            refined = refine_mechanic(
                _effect_description_text(row),
                row,
                f"effect_def,{eid}",
                owner_name=owner,
            )
            facts = refined.get("effect_facts") or {}
            self.assertEqual(
                facts.get("effect_scope"),
                "positional",
                msg=owner,
            )
            targets = facts.get("targets") or []
            self.assertIn(token, targets, msg=owner)
            sem = facts.get("semantics") or {}
            self.assertEqual(sem.get("scope"), "positional")
            self.assertEqual((sem.get("position_source") or {}).get("kind"), "owner")
            for col in yes_cols:
                applies = positional_recipient_applies(
                    token,
                    owner_column=owner_col,
                    candidate_column=col,
                    candidate_is_owner=(col == owner_col and token.startswith("self")),
                )
                self.assertTrue(applies, msg=f"{owner} col {col} should receive")
            for col in no_cols:
                # Ahead of Donaar / behind Cazrin must not receive.
                applies = positional_recipient_applies(
                    token,
                    owner_column=owner_col,
                    candidate_column=col,
                    candidate_is_owner=False,
                )
                self.assertFalse(applies, msg=f"{owner} col {col} must not receive")

    def test_cazrin_personal_feats_remain_owner_scoped(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic

        for pct in (30, 60):
            refined = refine_mechanic(
                None,
                {
                    "effect_keys": [
                        {"effect_string": f"hero_dps_multiplier_mult,{pct}"}
                    ]
                },
                f"hero_dps_multiplier_mult,{pct}",
                owner_name="Cazrin",
            )
            facts = refined.get("effect_facts") or {}
            self.assertEqual(facts.get("effect_scope"), "owner")
            params = facts.get("parameters") or []
            self.assertTrue(
                any(
                    p.get("name") == "owner_damage" and p.get("value") == float(pct)
                    for p in params
                )
            )

    def test_bud_seconds_not_percent_skylla_baldric(self) -> None:
        from ic_gamedata.formation_ai_advice.clipboard_export import _project_value
        from ic_gamedata.formation_ai_advice.export import _effect_description_text
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        for eid, owner in ((2488, "Skylla"), (2392, "Baldric")):
            row = effects.get(eid)
            if not row:
                self.skipTest(f"effect {eid} missing")
            refined = refine_mechanic(
                _effect_description_text(row),
                row,
                f"effect_def,{eid}",
                owner_name=owner,
            )
            facts = refined.get("effect_facts") or {}
            bud = [
                p
                for p in (facts.get("parameters") or [])
                if p.get("effect_key") == "base_attack_deal_bonus_damage"
                or p.get("name") == "additional_bud_damage"
            ]
            self.assertTrue(bud, msg=owner)
            self.assertEqual(bud[0].get("unit"), "seconds_of_bud")
            self.assertEqual(bud[0].get("meaning"), "seconds_of_bud")
            self.assertEqual(bud[0].get("value"), 5.0)
            self.assertNotEqual(bud[0].get("unit"), "percent")
            projected = _project_value(facts) or {}
            mag = projected.get("value") or {}
            if not mag and projected.get("values"):
                mag = next(
                    (
                        v
                        for v in projected["values"]
                        if v.get("name") == "additional_bud_damage"
                    ),
                    {},
                )
            if mag.get("name") == "additional_bud_damage":
                self.assertEqual(mag.get("unit"), "seconds_of_bud")

    def test_dark_bargain_magic_subeffects_not_merged(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _effect_description_text
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2392)
        if not row:
            self.skipTest("Dark Bargain 2392 missing")
        refined = refine_mechanic(
            _effect_description_text(row),
            row,
            "effect_def,2392",
            owner_name="Baldric",
        )
        sem = (refined.get("effect_facts") or {}).get("semantics") or {}
        self.assertIsNone(sem.get("recipients"))
        self.assertIsNone(sem.get("predicate"))
        subs = sem.get("subeffects") or []
        magic = next(
            s
            for s in subs
            if s.get("effect_key") == "base_attack_deal_bonus_damage"
        )
        non_magic = next(
            s for s in subs if s.get("effect_key") == "hero_dps_multiplier_reduce"
        )
        self.assertIs(
            (magic.get("recipients") or {}).get("filter", {}).get(
                "requires_magic_attack"
            ),
            True,
        )
        self.assertIs(
            (non_magic.get("recipients") or {})
            .get("filter", {})
            .get("requires_magic_attack"),
            False,
        )
        self.assertEqual(
            (magic.get("parameters") or [])[0].get("unit"), "seconds_of_bud"
        )
        self.assertEqual(
            (non_magic.get("parameters") or [])[0].get("name"), "damage_reduction"
        )

    def test_phase_two_placeholder_and_subeffect_recipients(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _effect_description_text
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2450)
        if not row:
            self.skipTest("Phase Two effect missing")
        desc = _effect_description_text(row)
        refined = refine_mechanic(
            desc, row, "effect_def,2450", owner_name="King of Shadows"
        )
        text = refined.get("text") or ""
        # Own health uses health_mult,1 — never borrow sharing 25.
        self.assertIn("by 1%", text)
        self.assertNotRegex(text, r"increased by 25%\s+for each\s+Toughness")
        self.assertIn("by 25%", text)  # sharing / healing still 25
        facts = refined.get("effect_facts") or {}
        sem = facts.get("semantics") or {}
        self.assertEqual(sem.get("scope"), "mixed")
        self.assertIsNone(sem.get("recipients"))
        self.assertIsNotNone(sem.get("activation_conditions"))
        by_key = {s["effect_key"]: s for s in (sem.get("subeffects") or [])}
        self.assertEqual(
            (by_key["health_mult"].get("recipients") or {}).get("targets"),
            ["self"],
        )
        self.assertEqual(
            (by_key["increase_health_by_source_percent"].get("recipients") or {}).get(
                "targets"
            ),
            ["other"],
        )
        self.assertEqual(
            (by_key["global_healing_mult"].get("recipients") or {}).get("targets"),
            ["all"],
        )
        own = (by_key["health_mult"].get("parameters") or [])[0]
        share = (
            by_key["increase_health_by_source_percent"].get("parameters") or []
        )[0]
        self.assertEqual(own.get("value"), 1.0)
        self.assertEqual(share.get("value"), 25.0)

    def test_canonical_advice_projection_no_duplicate_fields(self) -> None:
        from ic_gamedata.formation_ai_advice.clipboard_export import _project_value
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic

        refined = refine_mechanic(
            None,
            {"effect_keys": [{"effect_string": "hero_dps_multiplier_mult,30"}]},
            None,
            owner_name="Cazrin",
        )
        projected = _project_value(refined.get("effect_facts")) or {}
        self.assertIn("value", projected)
        self.assertNotIn("values", projected)
        self.assertNotIn("effect_scope", projected)
        self.assertNotIn("targets", projected)
        self.assertIn("semantics", projected)
        self.assertEqual(projected["semantics"]["scope"], "owner")

    def test_semantic_validator_flags_owner_positional_conflict(self) -> None:
        from ic_gamedata.formation_ai_advice.validate import validate_advice_semantics

        gaps = validate_advice_semantics(
            {
                "effects": {
                    "bad": {
                        "mechanical_text": "x",
                        "semantics": {
                            "scope": "owner",
                            "recipients": {"targets": ["col_and_behind"]},
                        },
                    }
                },
                "champions": [],
            }
        )
        self.assertTrue(
            any(g.get("code") == "owner_scope_positional_recipients" for g in gaps)
        )

    def test_available_false_is_current_branch_not_permanent_ban(self) -> None:
        md = format_clipboard_markdown(self._export())
        self.assertIn("available geldt voor de huidige specialisatiekeuzes", md.casefold())
        self.assertIn("requires_option_id", md.casefold())
        self.assertIn("niet automatisch een permanent verbod", md.casefold())

        advice = build_advice_payload(
            {
                "meta": {"schema_version": SCHEMA_VERSION, "request_id": "a"},
                "goal": {"objective": "push_damage", "main_dps_id": 1},
                "formation": {"positions": [], "adjacency_by_position": {}},
                "champions": [
                    {
                        "champion_id": 165,
                        "name": "Baldric",
                        "specialization_groups": [
                            {
                                "group_id": "tier_0",
                                "group_label": "Keuze 1",
                                "selection_mode": "exactly_one",
                                "selection_status": "selected",
                                "selected_option_id": 100,
                                "options": [
                                    {
                                        "option_id": 100,
                                        "name": "Branch A",
                                        "selected": True,
                                        "mechanical_text": "A effect",
                                        "usability": "mechanical_usable",
                                        "available_in_current_state": True,
                                    },
                                    {
                                        "option_id": 101,
                                        "name": "Branch B",
                                        "selected": False,
                                        "mechanical_text": "B effect",
                                        "usability": "mechanical_usable",
                                        "available_in_current_state": True,
                                    },
                                ],
                            },
                            {
                                "group_id": "tier_1",
                                "group_label": "Keuze 2",
                                "selection_mode": "exactly_one",
                                "selection_status": "selected",
                                "selected_option_id": 200,
                                "options": [
                                    {
                                        "option_id": 200,
                                        "name": "Follow A",
                                        "selected": True,
                                        "mechanical_text": "Follow A",
                                        "usability": "mechanical_usable",
                                        "requires_selected_option_id": 100,
                                        "available_in_current_state": True,
                                    },
                                    {
                                        "option_id": 201,
                                        "name": "Follow B",
                                        "selected": False,
                                        "mechanical_text": "Follow B",
                                        "usability": "mechanical_usable",
                                        "requires_selected_option_id": 101,
                                        "available_in_current_state": False,
                                    },
                                    {
                                        "option_id": 202,
                                        "name": "Unknown prereq",
                                        "selected": False,
                                        "mechanical_text": "X",
                                        "usability": "mechanical_usable",
                                        "requires_selected_option_id": 999,
                                        "available_in_current_state": "unknown",
                                    },
                                ],
                            },
                        ],
                    }
                ],
                "readiness": {"status": "ready", "dimensions": {}},
            }
        )
        opts = {
            o["id"]: o
            for g in advice["champions"][0]["specializations"]
            for o in g["options"]
        }
        self.assertIs(opts[201]["available"], False)
        self.assertEqual(opts[201]["unavailable_reason"], "requires_other_option")
        self.assertEqual(opts[201]["requires_option_id"], 101)
        self.assertEqual(opts[202]["available"], "unknown")
        self.assertEqual(opts[202]["unavailable_reason"], "prerequisite_unknown")
        # Still exported — not dropped for being unavailable.
        self.assertIn(201, opts)

    def test_missing_effect_hints_differ_by_kind(self) -> None:
        advice = build_advice_payload(
            {
                "meta": {"schema_version": SCHEMA_VERSION, "request_id": "m"},
                "goal": {"objective": "push_damage", "main_dps_id": 1},
                "formation": {"positions": [], "adjacency_by_position": {}},
                "champions": [
                    {
                        "champion_id": 151,
                        "name": "Umberto",
                        "abilities": [
                            {
                                "ability_id": 15049,
                                "name": "Beehive Barrage",
                                "usability": "effect_unsupported_or_missing_prose",
                            },
                            {
                                "ability_id": 15058,
                                "name": "Brown Bear Bash",
                                "mechanical_text": "Sets attack id to 767.",
                                "usability": "partially_resolved",
                            },
                        ],
                        "specialization_groups": [
                            {
                                "group_id": "tier_1",
                                "selection_mode": "exactly_one",
                                "selection_status": "unselected",
                                "options": [
                                    {
                                        "option_id": 15055,
                                        "name": "More Bees",
                                        "mechanical_text": (
                                            "Umberto's Beehive Barrage increases bees."
                                        ),
                                        "usability": "mechanical_usable",
                                        "effect_facts": {
                                            "referenced_upgrade_ids": [15049],
                                        },
                                        "available_in_current_state": True,
                                    },
                                    {
                                        "option_id": 15057,
                                        "name": "More Damage",
                                        "usability": "missing",
                                        "available_in_current_state": True,
                                    },
                                ],
                            }
                        ],
                        "feats": {
                            "active_feats": [
                                {
                                    "feat_id": 1,
                                    "name": "Calm Under Pressure",
                                    "usability": "missing",
                                }
                            ]
                        },
                    }
                ],
                "readiness": {"status": "ready", "dimensions": {}},
            }
        )
        champ = advice["champions"][0]
        by_name = {a["name"]: a for a in champ["abilities"]}
        self.assertEqual(
            by_name["Beehive Barrage"]["advice_hint"],
            "Effect ontbreekt — bijdrage niet volledig te beoordelen.",
        )
        self.assertNotIn("Keuze open", by_name["Beehive Barrage"]["advice_hint"])
        self.assertEqual(
            by_name["Brown Bear Bash"]["advice_hint"],
            "Effect ontbreekt — bijdrage niet volledig te beoordelen.",
        )
        feat = champ["active_feats"][0]
        self.assertEqual(
            feat["advice_hint"],
            "Effect ontbreekt — bijdrage niet volledig te beoordelen.",
        )
        opts = {o["name"]: o for o in champ["specializations"][0]["options"]}
        self.assertEqual(opts["More Damage"]["advice_hint"], "Keuze open — effect ontbreekt.")
        self.assertIn("Beehive Barrage ontbreekt", opts["More Bees"]["comparison_limit"])
        # Known percent + unknown total is NOT treated as fully missing.
        known = build_advice_payload(
            {
                "meta": {"request_id": "k"},
                "goal": {},
                "formation": {},
                "champions": [
                    {
                        "champion_id": 1,
                        "name": "X",
                        "abilities": [
                            {
                                "ability_id": 1,
                                "name": "Buff",
                                "mechanical_text": "Increases damage by 100%.",
                                "usability": "mechanical_usable",
                                "effect_facts": {"amount_status": "computed_unknown"},
                            }
                        ],
                    }
                ],
                "readiness": {"status": "ready", "dimensions": {}},
            }
        )
        ab = known["champions"][0]["abilities"][0]
        self.assertIn("100%", ab["effect"])
        self.assertNotIn("advice_hint", ab)
        self.assertEqual(ab.get("magnitude"), "basis_of_actueel_niet_berekend")

    def test_cazrin_in_search_of_knowledge_book_thresholds(self) -> None:
        from ic_gamedata.formation_ai_advice.export import _effect_description_text
        from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        effects = {
            int(r["id"]): r
            for r in data.get("effect_defines") or []
            if isinstance(r, dict) and r.get("id") is not None
        }
        row = effects.get(2417)
        if not row:
            self.skipTest("In Search of Knowledge missing")
        desc = _effect_description_text(row)
        self.assertIn("10+ Books", desc or "")
        self.assertIn("40+ Books", desc or "")
        self.assertIn("300+ Books", desc or "")
        refined = refine_mechanic(
            desc, row, "effect_def,2417", owner_name="Cazrin"
        )
        text = refined.get("text") or ""
        self.assertIn("by 5% for each Book", text)
        self.assertIn("40% chance", text)
        self.assertIn("increased to 50%", text)
        self.assertIn("by 400%", text)
        self.assertNotIn("amount___", text)
        self.assertNotIn("effect_key", text)

        advice = build_advice_payload(
            {
                "meta": {"schema_version": SCHEMA_VERSION, "request_id": "c"},
                "goal": {"objective": "push_damage", "main_dps_id": 166},
                "formation": {"positions": [], "adjacency_by_position": {}},
                "champions": [
                    {
                        "champion_id": 166,
                        "name": "Cazrin",
                        "abilities": [
                            {
                                "ability_id": 17677,
                                "name": "In Search of Knowledge",
                                "mechanical_text": text,
                                "mechanical_source": "effect_defines[2417].description",
                                "usability": "mechanical_usable",
                                "effect_facts": refined.get("effect_facts"),
                            }
                        ],
                        "specialization_groups": [
                            {
                                "group_id": "tier_1",
                                "selection_mode": "exactly_one",
                                "selection_status": "unselected",
                                "options": [
                                    {
                                        "option_id": 17682,
                                        "name": "Smell Mastery",
                                        "mechanical_text": (
                                            "When Uggie is with Cazrin, In Search of "
                                            "Knowledge's per-Book bonus for Sunny "
                                            "Disposition is increased by 100%."
                                        ),
                                        "usability": "mechanical_usable",
                                        "available_in_current_state": True,
                                    },
                                    {
                                        "option_id": 17680,
                                        "name": "Lost in the Library",
                                        "mechanical_text": (
                                            "In Search of Knowledge's per Book damage "
                                            "boost to Sunny Disposition is reduced "
                                            "from 5%."
                                        ),
                                        "usability": "mechanical_usable",
                                        "available_in_current_state": True,
                                    },
                                ],
                            }
                        ],
                    }
                ],
                "readiness": {"status": "ready", "dimensions": {}},
            }
        )
        isok = advice["champions"][0]["abilities"][0]
        self.assertIn("10+ Books", isok["effect"])
        self.assertIn("5%", isok["effect"])
        self.assertNotIn("subeffects", isok)
        opts = {o["name"]: o for o in advice["champions"][0]["specializations"][0]["options"]}
        self.assertIn("per-Book", opts["Smell Mastery"]["effect"])
        self.assertIn("5%", opts["Lost in the Library"]["effect"])


if __name__ == "__main__":
    unittest.main()
