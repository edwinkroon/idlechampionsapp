"""Measure compact advice export size and regenerate sample clipboard."""

from __future__ import annotations

import json
from pathlib import Path

from ic_gamedata.formation_ai_advice.clipboard_export import (
    build_advice_payload,
    format_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION
from tests.test_formation_ai_advice import FormationAiAdviceTests

ROOT = Path(__file__).resolve().parents[1]
OUT_MD = ROOT / "documentation" / "formation_ai_advice_sample_clipboard.md"
OUT_PROOF = ROOT / "documentation" / "formation_ai_advice_compact_proof.json"

# Baseline measured immediately before this compact rewrite (schema 1.6 advice).
BASELINE_FIXTURE = {
    "label": "tests._export() 3-champion Beast Mode fixture",
    "advice_chars_before": 24682,
    "clipboard_chars_before": 26249,
    "export_internal_chars": 48812,
}


def _section_sizes(advice: dict) -> dict[str, int]:
    out = {}
    for key in (
        "meta",
        "bronregels",
        "context",
        "geometry",
        "champions",
        "onzekerheden",
        "readiness",
    ):
        if key in advice:
            out[key] = len(
                json.dumps(advice[key], ensure_ascii=False, separators=(",", ":"))
            )
    return out


def main() -> None:
    suite = FormationAiAdviceTests()
    suite.setUpClass()
    export = suite._export()
    advice = build_advice_payload(export)
    md = format_clipboard_markdown(export)
    advice_json = json.dumps(advice, ensure_ascii=False, separators=(",", ":"))

    # Also measure richer synthetic defines fixture (same as consistency cases).
    from scripts.formation_ai_advice_consistency_proof import CASES, _effects_by_id
    from ic_gamedata.formation_ai_advice.export import _effect_description_text
    from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic

    effects = _effects_by_id()
    rich_champs = []
    for idx, (eid, owner, label, hero_id) in enumerate(CASES):
        row = effects[eid]
        refined = refine_mechanic(
            _effect_description_text(row),
            row,
            f"effect_def,{eid}",
            owner_name=owner,
        )
        rich_champs.append(
            {
                "champion_id": hero_id,
                "name": owner,
                "seat": idx + 1,
                "current_position": idx + 1,
                "affiliations": [],
                "affiliations_status": "known",
                "abilities": [
                    {
                        "ability_id": eid,
                        "name": label,
                        "mechanical_text": refined.get("text"),
                        "effect_facts": refined.get("effect_facts"),
                        "usability": "mechanical_usable",
                        "quality": {"usable_for_placement": True},
                    }
                ],
            }
        )
    rich_export = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "request_id": "synthetic-compact-1",
            "data_version": "defines-cached",
            "research_mode": "provided_data_only",
        },
        "goal": {
            "main_dps_id": 166,
            "objective": "push_damage",
            "priorities": [
                "Respecteer alle harde plaatsings- en partyregels.",
                "Optimaliseer damage/BUD rondom de gekozen hoofd-DPS.",
            ],
            "adventure_name": "synthetic",
            "campaign_name": "synthetic",
            "party_restriction_status": "unknown",
        },
        "formation": {
            "geometry_source": "synthetic",
            "front_direction": "lower_column_index_is_front",
            "active_position_ids": list(range(1, 11)),
            "valid_position_ids": list(range(1, 11)),
            "adjacency_by_position": {str(i): [i - 1, i + 1] for i in range(1, 11)},
            "positions": [
                {
                    "position_id": i,
                    "column_index": (i - 1) % 5,
                    "row_order": 0,
                    "zone": "mid",
                    "state": "active",
                    "label": f"Positie {i}",
                    "current_champion_id": None,
                }
                for i in range(1, 11)
            ],
        },
        "champions": rich_champs,
        "readiness": {
            "status": "ready_with_warnings",
            "dimensions": {
                "party_legality": {"status": "unknown"},
                "placement_advice": {"status": "ready_with_warnings"},
                "specialization_advice": {"status": "unknown"},
            },
            "issues": [
                {
                    "code": "synthetic_fixture",
                    "severity": "warning",
                    "message": "Geen live party-snapshot.",
                }
            ],
        },
    }
    rich_advice = build_advice_payload(rich_export)
    rich_md = format_clipboard_markdown(rich_export)
    rich_json = json.dumps(rich_advice, ensure_ascii=False, separators=(",", ":"))

    # Consistency proof previous clipboard size (~16.7k after 1.6 rewrite).
    rich_before = 16697

    report = {
        "schema_version": SCHEMA_VERSION,
        "fixture": BASELINE_FIXTURE,
        "after": {
            "advice_chars": len(advice_json),
            "clipboard_chars": len(md),
            "section_chars": _section_sizes(advice),
            "reduction_vs_advice_before_pct": round(
                100
                * (1 - len(advice_json) / BASELINE_FIXTURE["advice_chars_before"]),
                1,
            ),
            "reduction_vs_clipboard_before_pct": round(
                100
                * (1 - len(md) / BASELINE_FIXTURE["clipboard_chars_before"]),
                1,
            ),
        },
        "rich_synthetic_defines": {
            "clipboard_chars_before_approx": rich_before,
            "clipboard_chars_after": len(rich_md),
            "advice_chars_after": len(rich_json),
            "section_chars": _section_sizes(rich_advice),
            "reduction_pct": round(100 * (1 - len(rich_md) / rich_before), 1),
        },
        "removed_from_advice_projection": [
            "Hash effect_ref catalog + duplicated semantics/subeffects/parameters",
            "Full distance matrix (adjacency retained)",
            "quality/usability/effect_key_index/parser traces",
            "Long notes block (replaced by short bronregels)",
            "Repeated readiness dimension objects",
        ],
        "kept_for_advice": [
            "Self-contained Dutch task brief with goal + main DPS",
            "Geometry: positions, column direction, adjacency",
            "Champion identity, effective traits, affiliations status",
            "Complete mechanical effect text inline",
            "Specialization options, prerequisites, availability, state_changes",
            "Active feat effects",
            "Bundled onzekerheden that can flip a choice",
        ],
        "agent_test_status": (
            "Automatic presence/structure tests only — no live agent trial run."
        ),
        "remaining_decision_gaps": [
            "Live party snapshot not frozen (equipment/feats/stacks often unknown).",
            "Uggie companion seat unknown → Uggie-dependent targeting conditional.",
            "Specialization selection_status often unknown in log fixtures → no A→B.",
        ],
    }
    OUT_PROOF.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Sample clipboard uses the standard test fixture (stable, complete).
    OUT_MD.write_text(md, encoding="utf-8")
    print(json.dumps(report["after"], indent=2))
    print("rich clipboard", len(rich_md), "was", rich_before)
    print("wrote", OUT_MD)
    print("wrote", OUT_PROOF)


if __name__ == "__main__":
    main()
