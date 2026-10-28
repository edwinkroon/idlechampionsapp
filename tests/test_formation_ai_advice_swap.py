"""Tests for automatic owned-roster champion-swap chat advice export."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.formation_ai_advice.clipboard_export import (
    build_advice_payload,
    build_swap_advice_payload,
    format_clipboard_markdown,
    format_swap_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.export import build_export_payload
from ic_gamedata.formation_ai_advice.swap_export import (
    SWAP_SCOPE,
    _seat_conflict_for_candidate,
    build_swap_export_payload,
)
from ic_gamedata.party_advisor_formation import resolve_live_formation
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


class FormationAiAdviceSwapTests(unittest.TestCase):
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

    def test_resolve_live_formation_prefers_payload_over_stale_fallback(self) -> None:
        live = resolve_live_formation(self.payload)
        if not live:
            self.skipTest("fixture has no live formation board")
        stale = (_hero(99999, "STALE", 1),)
        resolved = resolve_live_formation(self.payload, fallback=stale)
        self.assertTrue(resolved)
        self.assertNotIn(99999, {h.hero_id for h in resolved})
        self.assertEqual(
            {h.hero_id for h in resolved},
            {h.hero_id for h in live},
        )

    def _standard_export(self):
        return build_export_payload(
            self.payload,
            self._formation(),
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
            request_id="req-standard-1",
        )

    def _swap_export(
        self,
        *,
        locked=(),
        goal="push",
        fixed_main_dps_id=4,
        goal_parameters=None,
    ):
        return build_swap_export_payload(
            self.payload,
            self._formation(),
            locked_champion_ids=list(locked) if locked else None,
            goal=goal,
            context="campaign",
            fixed_main_dps_id=fixed_main_dps_id,
            goal_parameters=goal_parameters,
            request_id="req-swap-auto-1",
        )

    # --- Stap 1: automatic roster coverage ---

    def test_standard_mode_unchanged_no_replace(self) -> None:
        export = self._standard_export()
        self.assertEqual(
            export["meta"]["scope"],
            "optimize_placement_and_specializations_selected_only",
        )
        self.assertFalse(export["constraints"]["may_replace_champions"])
        self.assertNotIn("candidates", export)
        md = format_clipboard_markdown(export)
        self.assertIn("uitsluitend de geselecteerde champions", md)

    def test_all_owned_classified_accounts_reconcile(self) -> None:
        export = self._swap_export()
        cov = export["swap"]["coverage"]
        self.assertTrue(cov["accounts_reconciled"])
        self.assertEqual(
            cov["party_count"] + cov["external_owned_count"],
            cov["owned_known_count"],
        )
        self.assertEqual(
            cov["included_count"] + cov["excluded_count"] + cov["incomplete_count"],
            cov["external_owned_count"],
        )
        class_ids = {row["champion_id"] for row in export["swap"]["classification"]}
        party = set(export["swap"]["current_party_ids"])
        owned_external = set()
        from ic_gamedata.party_advisor_formation import _owned_heroes

        for hid, *_ in _owned_heroes(self.payload):
            if hid not in party:
                owned_external.add(hid)
        self.assertEqual(class_ids, owned_external)

    def test_no_hidden_ranking_or_manual_required(self) -> None:
        export = self._swap_export()
        self.assertEqual(export["meta"]["scope"], SWAP_SCOPE)
        self.assertEqual(export["constraints"]["max_swaps_per_proposal"], 3)
        self.assertEqual(export["swap"]["max_swaps_per_proposal"], 3)
        self.assertEqual(
            export["swap"]["candidate_selection"], "automatic_owned_external"
        )
        self.assertTrue(export["constraints"]["no_hidden_tier_list_or_top_n"])
        self.assertTrue(export["constraints"]["ai_selects_among_exported_externals"])
        self.assertNotEqual(export["swap"]["candidate_selection"], "manual")

    def test_party_baseline_preserved(self) -> None:
        export = self._swap_export(fixed_main_dps_id=4)
        party_ids = {c["champion_id"] for c in export["champions"]}
        self.assertEqual(party_ids, {2, 3, 4})
        for c in export["champions"]:
            if c["champion_id"] == 4:
                self.assertTrue(c.get("locked"))
                self.assertEqual(c.get("lock_reason"), "fixed_main_dps")

    def test_no_fixed_dps_means_no_auto_lock(self) -> None:
        export = self._swap_export(fixed_main_dps_id=None, locked=())
        self.assertIsNone(export["goal"].get("fixed_main_dps_id"))
        self.assertIsNone(export["goal"].get("damage_focus"))
        self.assertEqual(export["goal"].get("fixed_champion_ids") or [], [])
        self.assertFalse(export["constraints"]["main_dps_locked"])
        for c in export["champions"]:
            self.assertFalse(c.get("locked"))

    def test_included_have_mechanics_or_explicit_gap(self) -> None:
        export = self._swap_export()
        self.assertTrue(export["candidates"])
        for cand in export["candidates"]:
            self.assertIn(cand.get("inclusion"), (
                "included_allowed",
                "included_conditional",
            ))
            has_mech = bool(cand.get("abilities") or cand.get("specialization_groups"))
            self.assertTrue(
                has_mech or cand.get("has_relevant_data_gaps"),
                msg=f"candidate {cand.get('champion_id')} missing mechanics silently",
            )
            self.assertEqual(cand.get("equipment_status"), "unknown")
            self.assertIn("bench_loadout", cand)

    def test_unknown_eligibility_not_treated_as_denied(self) -> None:
        export = self._swap_export()
        for row in export["swap"]["classification"]:
            if row.get("eligibility") in ("unknown", "conflict"):
                self.assertNotEqual(
                    row["classification"],
                    "excluded",
                    msg="unknown/conflict must not hard-exclude unless seat-lock",
                )

    def test_seat_lock_excludes_hard(self) -> None:
        conflict = _seat_conflict_for_candidate(
            candidate_seat=3,
            party_by_seat={3: {"champion_id": 4, "name": "Jarlaxle"}},
            locked_ids={4},
            main_dps_id=4,
        )
        self.assertEqual(conflict["status"], "blocked_by_lock")
        self.assertFalse(conflict["valid_one_swap"])

        free = _seat_conflict_for_candidate(
            candidate_seat=9,
            party_by_seat={3: {"champion_id": 4, "name": "Jarlaxle"}},
            locked_ids={4},
            main_dps_id=4,
        )
        self.assertEqual(free["status"], "free")
        self.assertTrue(free["valid_one_swap"])

    def test_locked_seat_occupant_excludes_matching_candidates(self) -> None:
        export = self._swap_export(locked=(4, 3))
        # Any external with permanent seat matching locked Nayeli/Jarlaxle
        # must be excluded for one-swap scope.
        locked_seats = {
            c["seat"]
            for c in export["champions"]
            if c.get("locked") and isinstance(c.get("seat"), int)
        }
        for cand in export["candidates"]:
            seat = cand.get("seat")
            if seat in locked_seats:
                self.fail(
                    f"included candidate {cand['champion_id']} on locked seat {seat}"
                )
        for row in export["swap"]["excluded"]:
            if row.get("seat") in locked_seats:
                reason = str(row.get("reason") or "").casefold()
                self.assertTrue(
                    "gelockt" in reason or "vastgezet" in reason or "lock" in reason,
                    msg=reason,
                )

    def test_goal_preserved_not_hardcoded_damage(self) -> None:
        export = self._swap_export(
            goal="gem_farm",
            fixed_main_dps_id=None,
            goal_parameters={"play_mode": "unknown", "auto_reset": "unknown"},
        )
        self.assertEqual(export["goal"]["id"], "gem_farm")
        self.assertEqual(export["goal"]["primary_metric"], "gems_per_hour")
        self.assertEqual(export["swap"]["goal_id"], "gem_farm")

    def test_standard_advice_payload_unaffected(self) -> None:
        a = build_advice_payload(self._standard_export())
        self.assertNotIn("candidates", a)
        self.assertNotIn("swap", a)

    # --- Stap 2: one-click brief / no manual candidates ---

    def test_swap_clipboard_asks_ai_to_search_roster(self) -> None:
        export = self._swap_export()
        md = format_swap_clipboard_markdown(export)
        self.assertIn("Idle Champions-formatieadviseur", md)
        self.assertIn("geen vervanger of kandidaten aangewezen", md.casefold())
        self.assertIn("zoek zelf relevante alternatieven", md.casefold())
        self.assertNotIn("Handmatig geselecteerde kandidaten", md)
        self.assertNotIn("selecteer minimaal", md.casefold())
        self.assertIn("Wissel aanbevolen", md)
        self.assertIn("| Voorstel | Eruit (Plek) | Erin (Plek) |", md)
        self.assertIn(SWAP_SCOPE, md)
        # Real user goal from export, not hardcoded damage-only task.
        self.assertIn("Doel: Push.", md)

    def test_swap_clipboard_gem_farm_goal(self) -> None:
        export = self._swap_export(
            goal="gem_farm",
            fixed_main_dps_id=None,
            goal_parameters={"play_mode": "background", "auto_reset": "yes"},
        )
        md = format_swap_clipboard_markdown(export)
        self.assertIn("gems verzamelen", md.casefold())
        self.assertIn("gems_per_hour", md.casefold())
        self.assertIn("geen vaste hoofd-dps", md.casefold())
        self.assertNotIn("push/damage", md.casefold())

    def test_swap_advice_coverage_in_projection(self) -> None:
        export = self._swap_export()
        advice = build_swap_advice_payload(export)
        cov = (advice.get("swap") or {}).get("coverage") or {}
        self.assertIsNotNone(cov.get("owned_known"))
        self.assertIsNotNone(cov.get("included"))
        self.assertIsNotNone(cov.get("excluded"))
        self.assertIn("coverage_complete", cov)
        self.assertTrue(advice.get("candidates"))
        self.assertEqual(
            (advice.get("swap") or {}).get("candidate_selection"),
            "automatic_owned_external",
        )

    def test_copy_generator_is_format_swap_clipboard_markdown(self) -> None:
        """Regression: UI one-click path must call this formatter."""
        export = self._swap_export()
        md = format_swap_clipboard_markdown(export)
        self.assertGreater(len(md), 1000)
        self.assertIn("## Gegevens", md)


if __name__ == "__main__":
    unittest.main()
