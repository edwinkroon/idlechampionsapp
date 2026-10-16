from __future__ import annotations

import json
from pathlib import Path

from ic_gamedata.formation_ai_advice.clipboard_export import (
    build_advice_payload,
    format_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.export import _effect_description_text
from ic_gamedata.formation_ai_advice.mechanics import refine_mechanic
from ic_gamedata.specialization_data import cached_definitions_data
from tests.test_formation_ai_advice import FormationAiAdviceTests

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    t = FormationAiAdviceTests()
    t.setUpClass()
    export = t._export()
    md = format_clipboard_markdown(export)
    advice = build_advice_payload(export)
    advice_chars = len(json.dumps(advice, ensure_ascii=False, separators=(",", ":")))

    effects = {
        int(r["id"]): r
        for r in cached_definitions_data().get("effect_defines") or []
        if isinstance(r, dict) and r.get("id") is not None
    }
    isok = refine_mechanic(
        _effect_description_text(effects[2417]),
        effects[2417],
        "effect_def,2417",
        owner_name="Cazrin",
    )
    cazrin = build_advice_payload(
        {
            "meta": {"schema_version": "1.8", "request_id": "cazrin"},
            "goal": {
                "objective": "push_damage",
                "main_dps_id": 166,
                "priorities": ["Optimaliseer damage/BUD rondom de gekozen hoofd-DPS."],
            },
            "formation": {
                "positions": [],
                "adjacency_by_position": {},
                "valid_position_ids": [1],
            },
            "champions": [
                {
                    "champion_id": 166,
                    "name": "Cazrin",
                    "abilities": [
                        {
                            "ability_id": 17677,
                            "name": "In Search of Knowledge",
                            "mechanical_text": isok.get("text"),
                            "mechanical_source": "effect_defines[2417].description",
                            "usability": "mechanical_usable",
                            "effect_facts": isok.get("effect_facts"),
                        }
                    ],
                }
            ],
            "readiness": {"status": "ready", "dimensions": {}},
        }
    )
    umberto = build_advice_payload(
        {
            "meta": {"request_id": "u"},
            "goal": {"objective": "push_damage", "main_dps_id": 151},
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
                            "group_id": "t1",
                            "selection_mode": "exactly_one",
                            "selection_status": "unselected",
                            "options": [
                                {
                                    "option_id": 15055,
                                    "name": "More Bees",
                                    "mechanical_text": "Umberto Beehive Barrage buff.",
                                    "usability": "mechanical_usable",
                                    "effect_facts": {
                                        "referenced_upgrade_ids": [15049]
                                    },
                                    "available_in_current_state": True,
                                }
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

    available_block = next(
        (
            block
            for block in md.split("\n\n")
            if "available geldt" in block.casefold()
        ),
        "",
    )
    snippets = "\n".join(
        [
            "# Afronding schema 1.8 — relevante exportfragmenten",
            "",
            "## 1. available / prerequisites (opdracht)",
            "",
            available_block,
            "",
            "## 2. Ontbrekende ability/feat meldingen",
            "",
            "```json",
            json.dumps(
                {
                    "abilities": umberto["champions"][0]["abilities"],
                    "active_feats": umberto["champions"][0]["active_feats"],
                    "more_bees": umberto["champions"][0]["specializations"][0][
                        "options"
                    ][0],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "## 3. In Search of Knowledge",
            "",
            "```",
            cazrin["champions"][0]["abilities"][0]["effect"],
            "```",
            "",
        ]
    )
    (ROOT / "documentation" / "formation_ai_advice_finish_snippets.md").write_text(
        snippets, encoding="utf-8"
    )
    (ROOT / "documentation" / "formation_ai_advice_sample_clipboard.md").write_text(
        md, encoding="utf-8"
    )
    proof = {
        "schema_version": "1.8",
        "before_1_7_same_fixture": {"advice_chars": 8279, "clipboard_chars": 11887},
        "after_1_8_same_fixture": {
            "advice_chars": advice_chars,
            "clipboard_chars": len(md),
        },
        "delta_clipboard_chars": len(md) - 11887,
        "isok_effect_chars": len(cazrin["champions"][0]["abilities"][0]["effect"]),
        "supplemented": [
            "Cazrin In Search of Knowledge Book thresholds 10/40/80/120/160/200/240/300 from effect_defines post.conditions",
            "Resolved placeholders: 5% per Book, 1% Unctuous Uggie, 40% chance, 50% Mage Armor, 400% tank Sunny",
        ],
        "still_missing_source_prose": [
            "Umberto Beehive Barrage: no effect_defines description (custom handlers only)",
            "Umberto Brown Bear Bash: only set_ultimate_attack",
            "Live Book/Toughness stack counts: current state, not definitions",
        ],
    }
    (ROOT / "documentation" / "formation_ai_advice_finish_proof.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
