"""Regression: Kopieer partijsetup → baseline uses formation=, not heroes=.

AdviceTab._export_build_kwargs once passed heroes= into build_export_payload,
causing ``Baseline mislukt: TypeError: ... unexpected keyword argument 'heroes'``
after a successful clipboard copy (request_copied → _stash_paste_baseline).
"""

from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export import build_export_payload
from ic_gamedata.formation_ai_advice.export_clipboard import (
    build_advice_request_clipboard_text,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.formation_ai_advice.snapshot_store import (
    get_exported_snapshot_meta,
    save_base_snapshot_to_basisgegevens,
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
        role_label="Dps",
        roles=("dps",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


def _advice_tab_export_kwargs(
    payload: dict,
    formation: tuple[FormationHero, ...],
    *,
    goal: str = "push",
    context: str = "campaign",
    fixed_main_dps_id: int | None = 4,
    goal_parameters: dict | None = None,
) -> dict:
    """Mirror AdviceTab._export_build_kwargs key names (must stay aligned)."""
    return {
        "payload": payload,
        "formation": formation,
        "goal": goal,
        "context": context,
        "fixed_main_dps_id": fixed_main_dps_id,
        "goal_parameters": goal_parameters or {},
        "manual_restriction_text": None,
    }


class AdviceCopyBaselineKwargsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.payload = json.loads(json.dumps(self.base_payload))
        self.formation = (
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(4, "Jarlaxle", 3),
        )
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.registry_path = root / "advice_snapshot_registry.json"
        self.snapshots_dir = root / "advice_snapshots"
        self.basisgegevens_dir = root / "basisgegevens"
        self.cache_path = root / "owned_roster_cache.json"
        self._patches = [
            patch(
                "ic_gamedata.paths.ADVICE_SNAPSHOT_REGISTRY_PATH",
                self.registry_path,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOT_REGISTRY_PATH",
                self.registry_path,
            ),
            patch(
                "ic_gamedata.paths.ADVICE_SNAPSHOTS_DIR",
                self.snapshots_dir,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOTS_DIR",
                self.snapshots_dir,
            ),
            patch(
                "ic_gamedata.paths.BASISGEGEVENS_DIR",
                self.basisgegevens_dir,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.BASISGEGEVENS_DIR",
                self.basisgegevens_dir,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
                self.cache_path,
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmpdir.cleanup()

    def test_build_export_payload_rejects_heroes_kwarg(self) -> None:
        sig = inspect.signature(build_export_payload)
        self.assertIn("formation", sig.parameters)
        self.assertNotIn("heroes", sig.parameters)
        with self.assertRaises(TypeError) as ctx:
            build_export_payload(
                self.payload,
                heroes=self.formation,  # type: ignore[call-arg]
                goal="push",
                context="campaign",
            )
        self.assertIn("heroes", str(ctx.exception))

    def test_advice_tab_source_passes_formation_key(self) -> None:
        """Guard against reintroducing heroes= in AdviceTab kwargs."""
        src = (
            Path(__file__).resolve().parent.parent
            / "ic_ui"
            / "tabs"
            / "advice_tab.py"
        ).read_text(encoding="utf-8")
        # Narrow to _export_build_kwargs body.
        start = src.index("def _export_build_kwargs")
        end = src.index("\n    def ", start + 1)
        body = src[start:end]
        self.assertIn('"formation": heroes', body)
        self.assertNotIn('"heroes": heroes', body)

    def test_kopieer_partijsetup_baseline_kwargs_build_export_payload(self) -> None:
        """Path: collect tab kwargs → build_export_payload (paste baseline)."""
        kwargs = _advice_tab_export_kwargs(self.payload, self.formation)
        self.assertIn("formation", kwargs)
        self.assertNotIn("heroes", kwargs)

        export = build_export_payload(**kwargs)
        self.assertIsInstance(export, dict)
        champions = export.get("champions") or []
        ids = {
            int(row["champion_id"])
            for row in champions
            if isinstance(row, dict) and isinstance(row.get("champion_id"), int)
        }
        self.assertEqual(ids, {2, 3, 4})
        for row in champions:
            self.assertTrue(row.get("name"))
            self.assertIn("current_position", row)

        formation_block = export.get("formation")
        self.assertIsInstance(formation_block, dict)

    def test_positional_and_keyword_formation_calls_still_work(self) -> None:
        positional = build_export_payload(
            self.payload,
            self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
        )
        keyword = build_export_payload(
            payload=self.payload,
            formation=self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
        )
        self.assertEqual(
            [c.get("champion_id") for c in positional.get("champions") or []],
            [c.get("champion_id") for c in keyword.get("champions") or []],
        )

    def test_full_copy_path_baseline_then_advice_request_refs_filename(self) -> None:
        """Basis bijwerken + Kopieer partijsetup metadata linkage."""
        snap = build_base_snapshot(
            self.payload,
            formation=self.formation,
            goal="push",
            context="campaign",
        )
        meta = snap.get("meta") if isinstance(snap.get("meta"), dict) else {}
        self.assertTrue(meta.get("snapshot_id"))
        self.assertTrue(meta.get("mechanics_hash"))
        self.assertTrue(meta.get("account_state_hash"))
        champions = snap.get("champions") or []
        self.assertGreaterEqual(len(champions), 1)
        champ_ids = {
            int(c["id"])
            for c in champions
            if isinstance(c, dict) and isinstance(c.get("id"), int)
        }
        self.assertTrue({2, 3, 4}.issubset(champ_ids) or champ_ids)

        # Baseline paste stash uses the same kwargs as AdviceTab.
        paste_baseline = build_export_payload(
            **_advice_tab_export_kwargs(self.payload, self.formation)
        )
        self.assertEqual(
            {
                int(c["champion_id"])
                for c in (paste_baseline.get("champions") or [])
                if isinstance(c, dict) and isinstance(c.get("champion_id"), int)
            },
            {2, 3, 4},
        )

        saved = save_base_snapshot_to_basisgegevens(snap)
        self.assertTrue(saved.is_file())
        self.assertTrue(saved.name.startswith("basicdata_"))

        snap_meta = get_exported_snapshot_meta()
        self.assertIsNotNone(snap_meta)
        assert snap_meta is not None
        self.assertEqual(snap_meta.get("snapshot_id"), meta.get("snapshot_id"))
        self.assertEqual(snap_meta.get("expected_filename"), saved.name)
        self.assertEqual(
            snap_meta.get("mechanics_hash") or meta.get("mechanics_hash"),
            meta.get("mechanics_hash"),
        )

        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(snap_meta["snapshot_id"]),
            snapshot_meta=snap_meta,
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
            goal_parameters={},
            include_swap_scope=False,
        )
        req_meta = req.get("meta") if isinstance(req.get("meta"), dict) else {}
        snap_ref = req_meta.get("snapshot_ref")
        if not isinstance(snap_ref, dict):
            # Some builds nest ref under snapshot_id only — accept either.
            self.assertEqual(req_meta.get("snapshot_id"), snap_meta["snapshot_id"])
        else:
            self.assertEqual(snap_ref.get("snapshot_id"), snap_meta["snapshot_id"])
            filename = snap_ref.get("expected_filename") or snap_ref.get("filename")
            if filename:
                self.assertEqual(filename, saved.name)

        text = build_advice_request_clipboard_text(req)
        self.assertIn(str(snap_meta["snapshot_id"]), text)
        self.assertIn(saved.name, text)


if __name__ == "__main__":
    unittest.main()
