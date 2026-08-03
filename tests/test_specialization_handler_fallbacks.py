"""Smoke tests for specialization handler empty-data fallbacks."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import AdventureRosterFilter
from ic_gamedata.specialization_data import hero_ability_scores_map_from_cached_definitions
from ic_gamedata.specialization_engine import (
    FormationContext,
    HERO_HANDLERS,
    _pick_best_qualified_stack,
)


def _is_explicit_fallback_reason(reason: str) -> bool:
    text = reason.casefold()
    markers = (
        "default",
        "geen qualified",
        "geen stack",
        "geen loot",
        "geen good",
        "geen ability",
        "geen data",
        "algemene ",
        "0 melee",
        "0 magic",
        "0 familiars",
        "geen attack-type",
    )
    return any(marker in text for marker in markers)


# Residual self-stacks still score > 0 with empty cached definitions (e.g. Gale
# always counts himself for Ceremorphosis; Volo self-grants Hunter). Those picks
# look like real stack wins — allowlisted so the smoke stays focused on silent
# defaults that pretend to be confident formation advice.
_KNOWN_RESIDUAL_EMPTY_DATA_CHANGES = frozenset({
    147,  # Gale: Ceremorphosis self-stack
    159,  # Volo: Spirits self-hunter count
})


class PickBestQualifiedStackFallbackTests(unittest.TestCase):
    def test_all_zero_counts_return_explicit_default(self) -> None:
        upgrade_id, reason = _pick_best_qualified_stack(
            [
                (1, 0, 100, "A"),
                (2, 0, 100, "B"),
                (3, 0, 7.5, "C"),
            ],
            default_id=2,
            default_label="B",
        )
        self.assertEqual(upgrade_id, 2)
        self.assertTrue(_is_explicit_fallback_reason(reason), reason)
        self.assertIn("default", reason.casefold())


class HandlerEmptyDataFallbackTests(unittest.TestCase):
    def test_empty_cached_data_pick_changes_are_explicit_or_allowlisted(self) -> None:
        scores = hero_ability_scores_map_from_cached_definitions()
        if len(scores) < 10:
            self.skipTest("cached_definitions ability scores unavailable")

        sample = list(scores.keys())[:10]
        owned = frozenset(set(range(1, 200)) | set(sample))
        silent: list[tuple[int, list[int] | None, list[int] | None, str]] = []

        for hero_id, handler in sorted(HERO_HANDLERS.items()):
            form = set(sample) | {hero_id}
            seats = {hid: index + 1 for index, hid in enumerate(sorted(form)[:12])}
            full_ctx = FormationContext(
                active_hero_ids=form,
                owned_hero_ids=owned,
                roster_filter=AdventureRosterFilter(),
                account_stats={"GrandTourBaseAdventuresCompleted": 50},
                event_boon_count=5,
                modron_core_competency_stacks=20,
                seat_by_hero=seats,
                hero_upgrade_ids={},
            )
            full = handler(full_ctx)
            with (
                patch(
                    "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                    return_value={},
                ),
                patch(
                    "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
                    return_value={},
                ),
                patch(
                    "ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions",
                    return_value={},
                ),
            ):
                empty = handler(
                    FormationContext(
                        active_hero_ids=form,
                        owned_hero_ids=owned,
                        roster_filter=AdventureRosterFilter(),
                        account_stats=None,
                        event_boon_count=0,
                        modron_core_competency_stacks=0,
                        seat_by_hero=seats,
                        hero_upgrade_ids={},
                    )
                )
            full_ids = full[0] if full else None
            empty_ids = empty[0] if empty else None
            empty_reason = empty[1] if empty else ""
            if full_ids == empty_ids:
                continue
            if _is_explicit_fallback_reason(empty_reason):
                continue
            if hero_id in _KNOWN_RESIDUAL_EMPTY_DATA_CHANGES:
                continue
            silent.append((hero_id, full_ids, empty_ids, empty_reason))

        self.assertEqual(
            silent,
            [],
            "Handlers changed pick under empty data without an explicit "
            f"default/geen/algemene rationale: {silent}",
        )


if __name__ == "__main__":
    unittest.main()
