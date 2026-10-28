"""Tests for owned-roster disk cache (swap advice)."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.owned_roster_cache import (
    _entry_looks_mechanics_complete,
    entries_for_save,
    get_cached_champion_entry,
    load_owned_roster_cache,
    loadout_fingerprint,
    put_cached_champion_entry,
    resolve_champion_entry,
    save_owned_roster_cache,
)


class OwnedRosterCacheTests(unittest.TestCase):
    def test_fingerprint_changes_with_feats(self) -> None:
        payload_a = {
            "details": {
                "heroes": [
                    {
                        "hero_id": 10,
                        "active_feats": [1, 2],
                        "specialization_choices": [5],
                    }
                ]
            }
        }
        payload_b = {
            "details": {
                "heroes": [
                    {
                        "hero_id": 10,
                        "active_feats": [1, 3],
                        "specialization_choices": [5],
                    }
                ]
            }
        }
        a = loadout_fingerprint(payload_a, 10, ilvl=100, data_version="1")
        b = loadout_fingerprint(payload_b, 10, ilvl=100, data_version="1")
        self.assertNotEqual(a, b)

    def test_roundtrip_hit_and_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owned_roster_cache.json"
            cache = load_owned_roster_cache(path)
            self.assertEqual(cache["entries"], {})

            put_cached_champion_entry(
                cache,
                42,
                "fp-1",
                {"champion_id": 42, "name": "Test", "inclusion": "should_strip"},
            )
            save_owned_roster_cache(
                entries_for_save(cache),
                path=path,
                cached_at=time.time(),
            )

            loaded = load_owned_roster_cache(path)
            hit = get_cached_champion_entry(loaded, 42, "fp-1")
            self.assertIsNotNone(hit)
            assert hit is not None
            self.assertEqual(hit["champion_id"], 42)
            self.assertNotIn("inclusion", hit)

            miss = get_cached_champion_entry(loaded, 42, "fp-other")
            self.assertIsNone(miss)

    def test_ttl_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owned_roster_cache.json"
            save_owned_roster_cache(
                {
                    1: {
                        "fingerprint": "x",
                        "entry": {"champion_id": 1},
                    }
                },
                path=path,
                cached_at=time.time() - 100_000,
                ttl_seconds=86_400,
            )
            loaded = load_owned_roster_cache(path, ttl_seconds=86_400)
            self.assertEqual(loaded["entries"], {})

    def test_resolve_builds_once_then_hits(self) -> None:
        cache: dict = {"entries": {}}
        builds = {"n": 0}

        def builder():
            builds["n"] += 1
            return {"champion_id": 7, "name": "Built", "seat": 7}

        # Avoid live hero_defines seat checks for this synthetic hero id.
        with patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache._definition_seat_for_hero",
            return_value=7,
        ), patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache._entry_looks_mechanics_complete",
            return_value=True,
        ):
            first, src1 = resolve_champion_entry(
                cache=cache,
                hero_id=7,
                fingerprint="fp",
                builder=builder,
            )
            second, src2 = resolve_champion_entry(
                cache=cache,
                hero_id=7,
                fingerprint="fp",
                builder=builder,
            )
            self.assertEqual(src1, "built")
            self.assertEqual(src2, "cache")
            self.assertEqual(builds["n"], 1)
            self.assertEqual(first["name"], "Built")
            self.assertEqual(second["name"], "Built")

            _, src3 = resolve_champion_entry(
                cache=cache,
                hero_id=7,
                fingerprint="fp",
                builder=builder,
                force_refresh=True,
            )
            self.assertEqual(src3, "built")
            self.assertEqual(builds["n"], 2)

    def test_put_sanitizes_seat_from_definitions(self) -> None:
        cache: dict = {"entries": {}}
        with patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache._definition_seat_for_hero",
            return_value=8,
        ):
            put_cached_champion_entry(
                cache,
                149,
                "fp-rav",
                {"champion_id": 149, "name": "Ravengard", "seat": 1},
            )
            stored = cache["entries"]["149"]["entry"]
            self.assertEqual(stored["seat"], 8)
            hit = get_cached_champion_entry(cache, 149, "fp-rav")
            assert hit is not None
            self.assertEqual(hit["seat"], 8)

    def test_poisoned_seat_forces_rebuild(self) -> None:
        """Stale seat=1 for Ravengard must not be trusted — rebuild from builder."""
        cache: dict = {
            "entries": {
                "149": {
                    "fingerprint": "fp-poison",
                    "entry": {
                        "champion_id": 149,
                        "name": "Ravengard",
                        "seat": 1,
                        # Look mechanics-complete so only the seat guard rejects.
                        "abilities": [
                            {"name": "Aura", "effect": "Buff allies."},
                        ],
                    },
                }
            }
        }
        builds = {"n": 0}

        def builder():
            builds["n"] += 1
            return {
                "champion_id": 149,
                "name": "Ravengard",
                "seat": 8,
                "abilities": [{"name": "Aura", "effect": "Buff allies."}],
            }

        with patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache._definition_seat_for_hero",
            return_value=8,
        ):
            self.assertFalse(
                _entry_looks_mechanics_complete(
                    cache["entries"]["149"]["entry"], 149
                )
            )
            entry, source = resolve_champion_entry(
                cache=cache,
                hero_id=149,
                fingerprint="fp-poison",
                builder=builder,
            )
        self.assertEqual(source, "built")
        self.assertEqual(builds["n"], 1)
        self.assertEqual(entry["seat"], 8)
        self.assertEqual(cache["entries"]["149"]["entry"]["seat"], 8)

    def test_deekin_ravengard_party_seats_not_duplicate(self) -> None:
        """Party seats come from defines — Ravengard must not collide with Deekin."""
        from ic_gamedata.formation_ai_advice.export import _permanent_seat
        from ic_gamedata.formation_ai_advice.export_validation import (
            ValidationIssue,
        )

        deekin_seat = _permanent_seat(28)
        ravengard_seat = _permanent_seat(149)
        self.assertEqual(deekin_seat, 1)
        self.assertEqual(ravengard_seat, 8)

        # Mirror build_advice_request party.seat assignment.
        party = [
            {"id": 28, "name": "Deekin", "seat": deekin_seat, "position": 1},
            {"id": 149, "name": "Ravengard", "seat": ravengard_seat, "position": 2},
        ]
        seats: dict[int, list[int]] = {}
        for row in party:
            hid = row["id"]
            seat = row["seat"]
            if isinstance(hid, int) and isinstance(seat, int):
                seats.setdefault(seat, []).append(hid)
        dup_issues = [
            ValidationIssue(
                "duplicate_permanent_seat",
                f"Meer dan één champion op permanente seat {seat}: {hids}.",
            )
            for seat, hids in seats.items()
            if len(hids) > 1
        ]
        self.assertEqual(dup_issues, [])


class SwapExportUsesRosterCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_second_swap_export_hits_cache(self) -> None:
        from ic_gamedata.formation_ai_advice.swap_export import build_swap_export_payload
        from ic_gamedata.party_advisor_models import FormationHero

        def hero(hero_id, name, seat, roles=("dps",)):
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
                role_label=roles[0].capitalize(),
                roles=roles,
                tags=(),
                highest_damage=0.0,
                active_feats=1,
                is_top_damage=False,
            )

        formation = (
            hero(3, "Nayeli", 1, roles=("tank", "support")),
            hero(2, "Celeste", 2, roles=("healer", "support")),
            hero(4, "Jarlaxle", 3, roles=("dps", "gold")),
        )

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "owned_roster_cache.json"
            with patch(
                "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
                cache_path,
            ), patch(
                "ic_gamedata.paths.OWNED_ROSTER_CACHE_PATH",
                cache_path,
            ):
                first = build_swap_export_payload(
                    self.payload,
                    formation,
                    goal="push",
                    context="campaign",
                    fixed_main_dps_id=4,
                    request_id="cache-1",
                    force_refresh_roster=True,
                )
                cov1 = first["swap"]["coverage"]["roster_cache"]
                self.assertGreater(cov1["built"], 0)
                self.assertEqual(cov1["hits"], 0)
                self.assertTrue(cache_path.is_file())

                second = build_swap_export_payload(
                    self.payload,
                    formation,
                    goal="push",
                    context="campaign",
                    fixed_main_dps_id=4,
                    request_id="cache-2",
                )
                cov2 = second["swap"]["coverage"]["roster_cache"]
                self.assertGreater(cov2["hits"], 0)
                self.assertEqual(cov2["built"], 0)


if __name__ == "__main__":
    unittest.main()
