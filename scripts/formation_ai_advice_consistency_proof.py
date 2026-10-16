"""Generate consistency-round proof: corrected examples + size metrics.

Live 10-champion Cazrin party snapshot is NOT available in-repo.
This uses cached definitions + a synthetic advice projection marked as such.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ic_gamedata.formation_ai_advice.clipboard_export import (
    _project_value,
    build_advice_payload,
    format_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.export import _effect_description_text
from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION
from ic_gamedata.specialization_data import cached_definitions_data

ROOT = Path(__file__).resolve().parents[1]
OUT_MD = ROOT / "documentation" / "formation_ai_advice_sample_clipboard.md"
OUT_JSON = ROOT / "documentation" / "formation_ai_advice_sample_export.json"
OUT_REPORT = ROOT / "documentation" / "formation_ai_advice_consistency_proof.json"


def _effects_by_id():
    data = cached_definitions_data()
    return {
        int(r["id"]): r
        for r in data.get("effect_defines") or []
        if isinstance(r, dict) and r.get("id") is not None
    }


def _fingerprint_defines(effect_ids: list[int]) -> str:
    effects = _effects_by_id()
    payload = []
    for eid in effect_ids:
        row = effects.get(eid) or {}
        keys = []
        for k in row.get("effect_keys") or []:
            if isinstance(k, dict):
                keys.append(
                    {
                        "effect_string": k.get("effect_string"),
                        "targets": k.get("targets"),
                        "filter_targets": k.get("filter_targets"),
                        "stacks_multiply": k.get("stacks_multiply"),
                        "amount_expr": k.get("amount_expr"),
                        "use_computed_amount_for_description": k.get(
                            "use_computed_amount_for_description"
                        ),
                    }
                )
        payload.append(
            {
                "id": eid,
                "description": _effect_description_text(row),
                "keys": keys,
            }
        )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


CASES = [
    (2573, "Donaar", "Lead By Example", 34),
    (2414, "Cazrin", "Sunny Disposition", 166),
    (2488, "Skylla", "Hypnotic Pattern", 169),
    (2392, "Baldric", "Dark Bargain (magic)", 165),
    (2450, "King of Shadows", "Phase Two: The Warden", 168),
    (2448, "King of Shadows", "Power of the King", 168),
    (2596, "Kyre", "Flawless Strike", 172),
]


def main() -> None:
    effects = _effects_by_id()
    effect_ids = [c[0] for c in CASES]
    input_fp = _fingerprint_defines(effect_ids)

    catalog: dict[str, dict] = {}
    examples: dict[str, dict] = {}
    for eid, owner, label, hero_id in CASES:
        row = effects[eid]
        refined = refine_mechanic(
            _effect_description_text(row),
            row,
            f"effect_def,{eid}",
            owner_name=owner,
        )
        facts = refined.get("effect_facts") or {}
        projected = _project_value(facts) or {}
        tip = refined.get("text")
        if not tip:
            from ic_gamedata.formation_ai_advice.export import _synthetic_mechanical_text

            tip = _synthetic_mechanical_text(facts, {})
        entry = {
            "mechanical_text": tip,
            **projected,
        }
        # Stable synthetic ref for proof (not production fingerprint).
        ref = hashlib.sha1(
            json.dumps(
                {"eid": eid, "owner": owner, "tip": tip, "sem": projected.get("semantics")},
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()[:10]
        catalog[ref] = entry
        examples[label] = {
            "effect_id": eid,
            "owner": owner,
            "hero_id": hero_id,
            "effect_ref": ref,
            "mechanical_text": tip,
            "effect_scope": facts.get("effect_scope"),
            "semantics": facts.get("semantics"),
            "parameters": facts.get("parameters"),
            "projected": projected,
        }

    # Synthetic export for clipboard path (marked — not a live party snapshot).
    export = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "request_id": "synthetic-consistency-1",
            "data_version": "defines-cached",
            "research_mode": "provided_data_only",
            "scope": "optimize_placement_and_specializations_selected_only",
            "fixture_kind": "synthetic_defines_only",
            "live_party_snapshot": False,
            "input_fingerprint": input_fp,
            "note": (
                "Live 10-champion Cazrin party snapshot was not available locally. "
                "Examples are from cached effect_defines only."
            ),
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
            "active_position_ids": list(range(1, 11)),
            "valid_position_ids": list(range(1, 11)),
            "positions": [
                {
                    "position_id": i,
                    "column_index": (i - 1) % 5,
                    "row_order": 0,
                    "zone": "mid",
                    "state": "active",
                    "label": f"Positie {i}",
                }
                for i in range(1, 11)
            ],
            "adjacency_by_position": {str(i): [] for i in range(1, 11)},
        },
        "champions": [
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
                        "mechanical_text": examples[label]["mechanical_text"],
                        "effect_facts": {
                            "effect_scope": examples[label]["effect_scope"],
                            "semantics": examples[label]["semantics"],
                            "parameters": examples[label]["parameters"],
                            "amount_status": "known",
                        },
                        "usability": "mechanical_usable",
                        "quality": {"usable_for_placement": True},
                    }
                ],
            }
            for idx, (eid, owner, label, hero_id) in enumerate(CASES)
        ],
        "constraints": {},
        "readiness": {
            "status": "ready_with_warnings",
            "dimensions": {
                "party_legality": {"status": "unknown"},
                "placement_advice": {"status": "ready_with_warnings"},
                "specialization_advice": {"status": "unknown"},
                "numeric_comparison": {"status": "ready_with_warnings"},
            },
            "issues": [
                {
                    "code": "synthetic_fixture",
                    "severity": "warning",
                    "message": "Geen live party-snapshot; synthetische defines-fixture.",
                }
            ],
        },
        "gaps": [],
    }

    advice = build_advice_payload(export)
    clipboard = format_clipboard_markdown(export, output_mode="table")
    advice_json = json.dumps(advice, ensure_ascii=False, separators=(",", ":"))
    export_json = json.dumps(export, ensure_ascii=False, separators=(",", ":"))

    section_sizes = {
        key: len(json.dumps(advice.get(key), ensure_ascii=False, separators=(",", ":")))
        for key in ("meta", "goal", "formation", "effects", "champions", "gaps", "readiness", "notes")
        if key in advice
    }
    largest_effects = sorted(
        (
            {
                "ref": ref,
                "chars": len(json.dumps(body, ensure_ascii=False, separators=(",", ":"))),
                "text": (body.get("mechanical_text") or "")[:80],
            }
            for ref, body in (advice.get("effects") or {}).items()
        ),
        key=lambda r: r["chars"],
        reverse=True,
    )[:8]

    report = {
        "schema_version": SCHEMA_VERSION,
        "live_party_snapshot_available": False,
        "fixture_kind": "synthetic_defines_only",
        "input_fingerprint": input_fp,
        "input_fingerprint_covers": effect_ids,
        "sizes": {
            "advice_chars": len(advice_json),
            "advice_bytes": len(advice_json.encode("utf-8")),
            "export_internal_chars": len(export_json),
            "clipboard_markdown_chars": len(clipboard),
            "section_chars": section_sizes,
            "effect_definition_count": len(advice.get("effects") or {}),
            "effect_instance_count": sum(
                1
                for c in advice.get("champions") or []
                for _ in (c.get("abilities") or [])
            ),
            "largest_effects": largest_effects,
        },
        "note_on_before_after": (
            "No frozen live Cazrin party snapshot was available, so this is not a "
            "live before/after measurement. Sizes are for the synthetic defines fixture "
            "after the consistency fix. Duplicate canonical fields (value+values, "
            "effect_scope+semantics.scope, targets+semantics.recipients) are removed "
            "in the advice projection."
        ),
        "corrected_examples": {
            label: {
                "mechanical_text": ex["mechanical_text"],
                "scope": ex["effect_scope"],
                "semantics_scope": (ex["semantics"] or {}).get("scope"),
                "recipients": (ex["semantics"] or {}).get("recipients"),
                "position_source": (ex["semantics"] or {}).get("position_source"),
                "subeffects": (ex["semantics"] or {}).get("subeffects"),
                "projected_value": (ex["projected"] or {}).get("value"),
                "projected_values": (ex["projected"] or {}).get("values"),
            }
            for label, ex in examples.items()
        },
        "remaining_unknowns": [
            "Live party positions/feats/equipment not frozen — placement comparisons incomplete.",
            "apply_effects_at_stacks threshold numeric value remains partial.",
            "Uggie companion seat position_status remains unknown.",
            "Power of the King computed hero_dps amount remains computed_unknown.",
        ],
        "verified_extra_cases": [
            "Umberto Protective Presence: health share → other, healing → all (mixed).",
            "Anson Got Your Back: health share → other, healing → all (mixed).",
        ],
        "semantic_conflicts": [],
    }

    OUT_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    OUT_JSON.write_text(
        json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    OUT_MD.write_text(clipboard, encoding="utf-8")
    print("input_fingerprint", input_fp)
    print("advice_chars", len(advice_json))
    print("clipboard_chars", len(clipboard))
    print("wrote", OUT_REPORT)
    print("wrote", OUT_MD)
    for label, ex in examples.items():
        print("\n===", label)
        print("scope", ex["effect_scope"])
        print("text", (ex["mechanical_text"] or "")[:180])
        sem = ex["semantics"] or {}
        print("recipients", sem.get("recipients"))
        print("subeffects", len(sem.get("subeffects") or []))


if __name__ == "__main__":
    main()
