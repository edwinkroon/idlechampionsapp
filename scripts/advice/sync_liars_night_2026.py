#!/usr/bin/env python3
"""Apply Liar's Night 2026: add Kitiara (180) + Avren/Brig/Dob rebalance IDs."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFS = Path(
    r"F:/Idle champions/IdleChampions/IdleDragons_Data/"
    r"StreamingAssets/downloaded_files/cached_definitions.json"
)

ROLE_KEYS = (
    "support",
    "buffer",
    "tank",
    "healer",
    "debuffer",
    "flex",
    "bud",
    "gold",
    "speed",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _spec_options(defs: dict, hid: int) -> list[dict]:
    by_level: dict[int, list[dict]] = defaultdict(list)
    for u in defs["upgrade_defines"]:
        if int(u.get("hero_id") or 0) != hid:
            continue
        sn = u.get("specialization_name")
        if not sn:
            continue
        lvl = int(u.get("required_level") or 0)
        by_level[lvl].append(
            {
                "upgrade_id": int(u["id"]),
                "name": sn,
                "required_level": lvl,
            }
        )
    out: list[dict] = []
    for tier_index, lvl in enumerate(sorted(by_level)):
        for opt in sorted(by_level[lvl], key=lambda o: o["upgrade_id"]):
            out.append({**opt, "tier_index": tier_index})
    return out


def _options_by_tier(options: list[dict]) -> dict:
    tiers: dict[str, list[dict]] = {}
    for opt in options:
        tiers.setdefault(str(opt["tier_index"]), []).append(
            {
                "upgrade_id": opt["upgrade_id"],
                "name": opt["name"],
                "required_level": opt["required_level"],
            }
        )
    return dict(sorted(tiers.items(), key=lambda kv: int(kv[0])))


def _set_specs(specs: dict, hid: int, name: str, default_ids: list[int], options: list[dict]) -> None:
    specs["heroes"][str(hid)] = {
        "name": name,
        "default": default_ids,
        "options": options,
    }


def main() -> int:
    defs = _load(DEFS)
    champs = _load(ROOT / "config" / "champions.json")
    specs = _load(ROOT / "config" / "specializations.json")
    models = _load(ROOT / "config" / "specialization_advisor_models.json")
    advice = _load(ROOT / "config" / "champion_role_advice.json")
    overrides = _load(ROOT / "config" / "specialization_route_overrides.json")
    ultimates = _load(ROOT / "config" / "ultimate_attacks.json")
    patrons = _load(ROOT / "config" / "patron_roster.json")

    # ----- Avren 51 -----
    avren_opts = _spec_options(defs, 51)
    _set_specs(specs, 51, "Avren", [20700, 20705], avren_opts)
    models["heroes"]["51"] = {
        "hero_id": 51,
        "name": "Avren",
        "has_dynamic_handler": False,
        "advice_model": "safe_default",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {
                "when": "most Good champions (Good/Evil axis)",
                "upgrade_id": 20700,
                "name": "Mirror Focus (Good)",
            },
            {
                "when": "most Neutral champions on Good/Evil axis",
                "upgrade_id": 20701,
                "name": "Mirror Focus (Neutral)",
            },
            {
                "when": "most Evil champions (Good/Evil axis)",
                "upgrade_id": 20702,
                "name": "Mirror Focus (Evil)",
            },
            {
                "when": "most Lawful champions (Law/Chaos axis)",
                "upgrade_id": 20703,
                "name": "Mirror Focus (Lawful)",
            },
            {
                "when": "most Neutral champions on Law/Chaos axis",
                "upgrade_id": 20704,
                "name": "Mirror Focus (Neutral)",
            },
            {
                "when": "most Chaotic champions (Law/Chaos axis)",
                "upgrade_id": 20705,
                "name": "Mirror Focus (Chaotic)",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": (
                "Liar's Night rebalance: both tiers are alignment stack picks "
                "(Good/Evil then Law/Chaos)."
            ),
        },
        "explanation_summary": (
            "Pick Mirror Focus on each axis by the most qualifying champions; "
            "dual-qualified get priority mirrors."
        ),
        "review_needed": False,
        "review_reasons": [],
        "options_by_tier": _options_by_tier(avren_opts),
    }
    avren_formation = (
        "Pick Mirror Focus on the Good/Evil axis and the Law/Chaos axis for the "
        "alignments with the most champions (ideally covering your Primary DPS). "
        "Dual-qualified champions get Mirror Images first. Place Avren next to "
        "your DPS when possible."
    )
    prev_avren = advice["champions"].get("51") or {}
    advice["champions"]["51"] = {
        "name": "Avren",
        "source": "CNE Liar's Night rebalance + prior Gaarawarr",
        "source_url": "http://www.codenameentertainment.com/?page=idle_champions&post_id=1972",
        "source_date": "2026-10-07",
        "guide_id": prev_avren.get("guide_id"),
        "guide_title": "Avren Liar's Night rebalance (alignment Mirror Focus x2)",
        "roles": {
            role: {
                "specializations": ["Mirror Focus (Good)", "Mirror Focus (Chaotic)"],
                "specialization_ids": [20700, 20705],
                "formation": avren_formation,
                "feats": [] if role == "speed" else ["Blinding Reflection", "Two-Headed Coin"],
            }
            for role in ROLE_KEYS
        },
    }
    overrides["champions"]["Avren"] = {
        "Mirror Focus (Good)": 20700,
        "Mirror Focus (Neutral)@1": 20701,
        "Mirror Focus (Evil)": 20702,
        "Mirror Focus (Lawful)": 20703,
        "Mirror Focus (Neutral)@2": 20704,
        "Mirror Focus (Chaotic)": 20705,
        "Good/Evil mirror path": 20700,
        "Law/Chaos mirror path": 20705,
    }

    # ----- Brig 90 -----
    brig_opts = _spec_options(defs, 90)
    _set_specs(specs, 90, "Brig", [20713], brig_opts)
    models["heroes"]["90"] = {
        "hero_id": 90,
        "name": "Brig",
        "has_dynamic_handler": False,
        "advice_model": "safe_default",
        "safe_default": {"upgrade_id": 20713, "name": '"Back"-Up Singer'},
        "push_default": {"upgrade_id": 20713, "name": '"Back"-Up Singer'},
        "farm_default": None,
        "conditionals": [
            {
                "when": "the alternate utility route is clearly better",
                "upgrade_id": 20714,
                "name": "Cream of the Crop",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": '"Back"-Up Singer',
            "csv_advice_text": (
                "Liar's Night rebalance: same specs, new upgrade ids; "
                "Cream of the Crop only when clearer."
            ),
        },
        "explanation_summary": "Safe Back-Up Singer; Cream of the Crop only for clearer utility route.",
        "review_needed": False,
        "review_reasons": [],
        "options_by_tier": _options_by_tier(brig_opts),
    }
    brig = advice["champions"]["90"]
    for block in (brig.get("roles") or {}).values():
        if not isinstance(block, dict):
            continue
        ids = block.get("specialization_ids") or []
        mapped = []
        for i in ids:
            if i in (6355, 20713):
                mapped.append(20713)
            elif i in (6356, 20714):
                mapped.append(20714)
            else:
                mapped.append(i)
        if mapped:
            block["specialization_ids"] = mapped
    brig["source"] = "CNE Liar's Night rebalance + prior Gaarawarr"
    brig["source_url"] = "http://www.codenameentertainment.com/?page=idle_champions&post_id=1972"
    brig["source_date"] = "2026-10-07"
    overrides["champions"]["Brig"] = {
        "Support route": 20713,
        "support_route": 20713,
        '"Back"-Up Singer': 20713,
        "Cream of the Crop": 20714,
    }

    # ----- Dob 105 -----
    dob_opts = _spec_options(defs, 105)
    _set_specs(specs, 105, "Dob", [20926], dob_opts)
    models["heroes"]["105"] = {
        "hero_id": 105,
        "name": "Dob",
        "has_dynamic_handler": True,
        "advice_model": "safe_default",
        "safe_default": {"upgrade_id": 20926, "name": "Befriend the Magical"},
        "push_default": {"upgrade_id": 20926, "name": "Befriend the Magical"},
        "farm_default": None,
        "conditionals": [
            {
                "when": "most Oxventure/magic attack champions",
                "upgrade_id": 20926,
                "name": "Befriend the Magical",
            },
            {
                "when": "most Oxventure/CHA>=17 champions",
                "upgrade_id": 20927,
                "name": "Befriend the Friendly",
            },
            {
                "when": "most Oxventure/DEX>=17 champions",
                "upgrade_id": 20928,
                "name": "Befriend the Quick",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": (
                "Liar's Night rebalance: Befriend Everybody is now base "
                "(I Have Friends Everywhere); pick Magical/Friendly/Quick by stacks."
            ),
        },
        "explanation_summary": (
            "Dynamic Magical/Friendly/Quick by Oxventure-or-filter stacks; "
            "Everybody is now a base ability."
        ),
        "review_needed": False,
        "review_reasons": [],
        "options_by_tier": _options_by_tier(dob_opts),
    }
    dob_formation = (
        "Befriend Everybody is now the base ability I Have Friends Everywhere. "
        "Pick Magical / Friendly / Quick for the Oxventure-or-filter group with "
        "the most champions."
    )
    prev_dob = advice["champions"].get("105") or {}
    advice["champions"]["105"] = {
        "name": "Dob",
        "source": "CNE Liar's Night rebalance + prior Gaarawarr",
        "source_url": "http://www.codenameentertainment.com/?page=idle_champions&post_id=1972",
        "source_date": "2026-10-07",
        "guide_id": prev_dob.get("guide_id"),
        "guide_title": "Dob Liar's Night rebalance (3 Befriend specs)",
        "roles": {
            role: {
                "specializations": ["Befriend the Magical"],
                "specialization_ids": [20926],
                "formation": dob_formation,
                "feats": []
                if role == "speed"
                else list(((prev_dob.get("roles") or {}).get(role) or {}).get("feats") or []),
            }
            for role in ROLE_KEYS
        },
    }
    overrides["champions"]["Dob"] = {
        "Befriend the Magical": 20926,
        "Befriend the Friendly": 20927,
        "Befriend the Quick": 20928,
        "Support route": 20926,
        "support_route": 20926,
    }

    # ----- Kitiara 180 -----
    k_opts = _spec_options(defs, 180)
    _set_specs(specs, 180, "Kitiara", [20603], k_opts)
    champs["180"] = {
        "name": "Kitiara",
        "roles": ["tank", "support"],
        "tags": ["buffer", "control", "breaking"],
    }
    models["heroes"]["180"] = {
        "hero_id": 180,
        "name": "Kitiara",
        "has_dynamic_handler": False,
        "advice_model": "safe_default",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {
                "when": "most Heroes of the Lance champions",
                "upgrade_id": 20602,
                "name": "Loyal to Her Past",
            },
            {
                "when": "most Unaffiliated champions",
                "upgrade_id": 20603,
                "name": "Loyal to Herself",
            },
            {
                "when": "most Evil champions",
                "upgrade_id": 20604,
                "name": "Loyal to Darkness",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": (
                "CNE Spotlight: pick Loyal * by affiliation/alignment stacks; "
                "Herself also spreads Arrogant Charm to adjacents."
            ),
        },
        "explanation_summary": (
            "No universal default — pick Past / Herself / Darkness by Heroes of "
            "the Lance, Unaffiliated, or Evil counts."
        ),
        "review_needed": False,
        "review_reasons": [],
        "options_by_tier": _options_by_tier(k_opts),
    }
    k_formation = (
        "Merciless Resolve buffs Champions furthest from Kitiara, stacking per "
        "adjacent Champion. Park her near the front/mid with many adjacents and "
        "keep your Primary DPS in the farthest column. Pick Loyal to Her Past / "
        "Herself / Darkness by which group (Heroes of the Lance / Unaffiliated / "
        "Evil) is largest; Herself also lets Arrogant Charm trigger from adjacent tanks."
    )
    k_feats_support = [
        "Cold as Ice",
        "One Way or Another",
        "Lonely Heart",
        "Hungry Eyes",
        "Total Eclipse",
        "Inspiring Leader",
    ]
    k_feats_tank = [
        "Resilient",
        "Calm Under Pressure",
        "Defensive Duelist",
        "Tough",
        "Cold as Ice",
        "Lonely Heart",
    ]
    advice["champions"]["180"] = {
        "name": "Kitiara",
        "source": "CNE Spotlight",
        "source_url": "https://codenameentertainment.com/?page=idle_champions&post_id=1970",
        "source_date": "2026-10-07",
        "guide_id": None,
        "guide_title": "Idle Champion Spotlight: Kitiara Uth Matar",
        "roles": {
            role: {
                "specializations": ["Loyal to Herself"],
                "specialization_ids": [20603],
                "formation": (
                    "Kitiara has no gold/speed spec. " + k_formation
                    if role in ("gold", "speed")
                    else k_formation
                ),
                "feats": (
                    []
                    if role == "speed"
                    else (k_feats_tank if role == "tank" else k_feats_support)
                ),
            }
            for role in ROLE_KEYS
        },
    }
    overrides["champions"]["Kitiara"] = {
        "Loyal to Her Past": 20602,
        "Loyal to Herself": 20603,
        "Loyal to Darkness": 20604,
    }
    ultimates["180"] = [1003]

    roster_list = patrons.get("heroes")
    if isinstance(roster_list, list):
        patrons["heroes"] = [r for r in roster_list if int(r.get("hero_id") or 0) != 180]
        patrons["heroes"].append(
            {
                "hero_id": 180,
                "name": "Kitiara",
                "seat": 4,
                "patrons": {
                    "mirt": "available",
                    "vajra": "available",
                    "strahd": "available",
                    "zariel": "available",
                    "elminster": "timed",
                },
            }
        )
        patrons["heroes"].sort(key=lambda row: int(row["hero_id"]))

    advice["coverage"] = {
        "guides_indexed": (advice.get("coverage") or {}).get("guides_indexed", 241),
        "champions_matched": len(advice["champions"]),
        "champions_fallback": 0,
        "champions_total": len(champs),
    }
    advice["quality_pass"] = "liars-night-2026-10-10"

    _dump(ROOT / "config" / "champions.json", champs)
    _dump(ROOT / "config" / "specializations.json", specs)
    _dump(ROOT / "config" / "specialization_advisor_models.json", models)
    _dump(ROOT / "config" / "champion_role_advice.json", advice)
    _dump(ROOT / "config" / "specialization_route_overrides.json", overrides)
    _dump(ROOT / "config" / "ultimate_attacks.json", ultimates)
    _dump(ROOT / "config" / "patron_roster.json", patrons)

    print(
        f"ok champs={len(champs)} specs={len(specs['heroes'])} "
        f"models={len(models['heroes'])} advice={len(advice['champions'])}"
    )
    print("avren", [o["upgrade_id"] for o in specs["heroes"]["51"]["options"]])
    print("brig", [o["upgrade_id"] for o in specs["heroes"]["90"]["options"]])
    print("dob", [o["name"] for o in specs["heroes"]["105"]["options"]])
    print("kitiara", specs["heroes"]["180"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
