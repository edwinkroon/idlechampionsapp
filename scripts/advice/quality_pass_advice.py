"""One-shot quality pass: role-specific specs, formation cleanup, empty feats."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADVICE = ROOT / "config" / "champion_role_advice.json"
SPECS = ROOT / "config" / "specializations.json"
GUIDES = ROOT / "data" / "gaarawarr_guides"
CHAMPIONS = ROOT / "config" / "champions.json"

def _norm_name(value: str) -> str:
    text = (value or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9' +.-]+", "", text)
    return re.sub(r"\s+", " ", text)


def _match_spec_id(name: str, options: list[dict]) -> int | None:
    key = _norm_name(name)
    for opt in options:
        opt_name = str(opt.get("name") or "")
        on = _norm_name(opt_name)
        if key == on or key in on or on in key:
            return int(opt["upgrade_id"])
    first = key.split()[0] if key.split() else ""
    for opt in options:
        on = _norm_name(str(opt.get("name") or ""))
        if first and first in on.split():
            return int(opt["upgrade_id"])
    return None


def _extract_role_spec_names(body: str) -> dict[str, list[str]]:
    """Parse Gaar 'DPS Spec' / 'Support Spec' / 'Gold Spec' notes."""
    role_names: dict[str, set[str]] = defaultdict(set)
    blocks = re.split(r"(?m)^\*\*", body)
    for block in blocks:
        header = block.split(":**", 1)[0].split("**", 1)[0].strip()
        if not header or len(header) > 90 or header.lower().startswith("last updated"):
            continue
        note = ""
        m = re.search(r"(?is)Gaar'?s Note:(.*?)(?:\n\n|$)", block)
        if m:
            note = m.group(1).lower()
        if any(p in note for p in ("dps spec", "carry spec", "this is his dps", "this is her dps")):
            role_names["bud"].add(header)
        if any(
            p in note
            for p in (
                "support spec",
                "tank spec",
                "multi-tank",
                "this is his support",
                "this is her support",
            )
        ):
            for role in ("support", "buffer", "tank", "healer", "debuffer", "flex"):
                role_names[role].add(header)
        if "gold spec" in note or ("gold find" in note and "spec" in note):
            role_names["gold"].add(header)
    return {role: sorted(names) for role, names in role_names.items() if names}


def _role_map_from_guide_body(body: str, hero_spec: dict) -> dict[str, list[int]] | None:
    role_names = _extract_role_spec_names(body)
    if not role_names:
        return None
    options = hero_spec.get("options") or []
    out: dict[str, list[int]] = {}
    for role, names in role_names.items():
        ids: list[int] = []
        for name in names:
            uid = _match_spec_id(name, options)
            if uid is not None and uid not in ids:
                ids.append(uid)
        if ids:
            out[role] = ids
    return out or None


def _fill_role_map_gaps(mapping: dict[str, list[int]], default_ids: list[int]) -> dict[str, list[int]]:
    filled = dict(mapping)
    fallback = default_ids or next(iter(mapping.values()), [])
    for role in ALL_ROLES:
        if role not in filled:
            filled[role] = list(fallback)
    return filled


ALL_ROLES = (
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


def _spec_names(hero: dict, ids: list[int]) -> list[str]:
    names: list[str] = []
    options = hero.get("options") or []
    for uid in ids:
        for opt in options:
            if int(opt.get("upgrade_id") or -1) == int(uid):
                names.append(str(opt.get("name") or uid))
                break
        else:
            names.append(str(uid))
    return names


def _set_role_specs(entry: dict, role: str, ids: list[int], names: list[str]) -> None:
    roles = entry.setdefault("roles", {})
    block = dict(roles.get(role) or {})
    block["specialization_ids"] = list(ids)
    block["specializations"] = list(names)
    # preserve feats/formation if present
    block.setdefault("feats", [])
    block.setdefault("formation", "")
    roles[role] = block


def _apply_specs_to_roles(
    entry: dict, role_ids: dict[str, list[int]], hero_spec: dict, default_ids: list[int]
) -> None:
    default_names = _spec_names(hero_spec, default_ids)
    roles = entry.setdefault("roles", {})
    # ensure all roles exist
    template = next(iter(roles.values()), None) if roles else None
    for role in ALL_ROLES:
        if role not in roles:
            roles[role] = {
                "specializations": list(default_names),
                "specialization_ids": list(default_ids),
                "formation": (template or {}).get("formation", ""),
                "feats": list((template or {}).get("feats") or []),
            }
    for role, ids in role_ids.items():
        _set_role_specs(entry, role, ids, _spec_names(hero_spec, ids))
    # roles not listed keep existing or default
    for role, block in roles.items():
        if role not in role_ids and not block.get("specialization_ids"):
            block["specialization_ids"] = list(default_ids)
            block["specializations"] = list(default_names)


def _clean_formation(text: str) -> str:
    raw = (text or "").strip().rstrip("*").strip()
    if not raw:
        return ""
    low = raw.lower()
    # Ability essays / non-placement blurbs
    bad_starts = (
        "this ability is huge",
        "this is her primary buff",
        "this is best used when you're doing variants",
        "this means you want to make sure",  # keep if placement? bruenor is placement-ish
    )
    placement_keys = (
        "column",
        "front",
        "back",
        "adjacent",
        "place",
        "swap",
        "behind",
        "slot",
        "formation",
        "dps is placed",
        "next to",
        "row",
    )
    if any(low.startswith(b) for b in ("this ability is huge", "this is her primary buff")):
        return ""
    if "where your dps is placed" in low:
        return "Spec choice depends on where your DPS sits in formation."
    if len(raw) > 220 and not any(k in low for k in placement_keys):
        return ""
    return raw[:280]


def _feats_from_legacy_table(guide_id: str) -> list[str]:
    """Older guides: | Found | Name | Effect | — prefer 40%/ability and Inspiring Leader."""
    path = GUIDES / f"{guide_id}.json"
    if not path.exists():
        return []
    body = str(json.loads(path.read_text(encoding="utf-8")).get("selftext") or "")
    i = body.lower().find("##feats")
    section = body[i : i + 2500] if i >= 0 else body
    scored: list[tuple[int, str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        if len(cols) < 3:
            continue
        name, effect = cols[1], cols[2] if len(cols) >= 3 else ""
        if name.lower() in {"name", "found"} or "---" in name:
            continue
        score = 0
        el = effect.lower()
        if "all champions" in el and ("25%" in el or "40%" in el):
            score += 5
        if "40%" in el:
            score += 4
        if "60%" in el:
            score += 2
        if name.lower() in {"selflessness", "tavern brawler"}:
            score -= 2
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    out: list[str] = []
    for _, name in scored:
        if name not in out:
            out.append(name)
    return out[:4]


def _feats_from_modern_table(guide_id: str) -> list[str]:
    """Score modern | Obtained | Recommended | Name | Effect | tables."""
    path = GUIDES / f"{guide_id}.json"
    if not path.exists():
        return []
    body = str(json.loads(path.read_text(encoding="utf-8")).get("selftext") or "")
    i = body.lower().find("##feats")
    section = body[i : i + 4000] if i >= 0 else body
    scored: list[tuple[int, str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        if len(cols) < 4:
            continue
        _obtained, recommended, name, effect = cols[0], cols[1], cols[2], cols[3]
        if name.lower() in {"name", "obtained", "feat slot"} or "---" in name:
            continue
        tags = recommended.lower()
        el = effect.lower()
        score = 0
        if any(t in tags for t in ("pushing", "dps")):
            score += 6
        if any(t in tags for t in ("survivability", "healing", "gold", "speed")):
            score += 4
        if "inspiring leader" in name.lower():
            score += 5
        if "40%" in el or "80%" in el or "25%" in el:
            score += 2
        if name.lower() in {"selflessness", "tavern brawler", "tough", "medic"}:
            score -= 2
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    out: list[str] = []
    for _, name in scored:
        if name not in out:
            out.append(name)
    return out[:4]


def _feats_from_guide(guide_id: str) -> list[str]:
    path = GUIDES / f"{guide_id}.json"
    if not path.exists():
        return []
    body = str(json.loads(path.read_text(encoding="utf-8")).get("selftext") or "")
    # table: | Obtained | Recommended | Name | Effect |
    pushing: list[str] = []
    for line in body.splitlines():
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        if len(cols) < 4:
            continue
        obtained, recommended, name, _effect = cols[0], cols[1], cols[2], cols[3]
        if name.lower() in {"name", "obtained"} or "---" in name:
            continue
        tags = recommended.lower()
        if any(t in tags for t in ("pushing", "dps", "gold", "speed", "farming")):
            if "pushing" in tags or "dps" in tags:
                pushing.append(name)
    return pushing[:6]


def main() -> None:
    advice = json.loads(ADVICE.read_text(encoding="utf-8"))
    specs_root = json.loads(SPECS.read_text(encoding="utf-8"))
    heroes = advice.setdefault("champions", {})
    spec_heroes = specs_root.get("heroes") or {}

    # --- Role-specific specs for known tank/DPS splits (Gaar + engine handlers) ---
    role_maps: dict[str, dict[str, list[int]]] = {
        # Nayeli: sole tank → Vengeance (buffs behind); support/with other tank → Devotion
        "3": {
            "tank": [43],
            "bud": [43],
            "support": [44],
            "buffer": [44],
            "healer": [44],
            "debuffer": [44],
            "flex": [44],
            "gold": [44],
            "speed": [44],
        },
        # Evelyn: tank → Compel Duel; support/multi → Protection; flex affiliates → Allies as flex default
        "26": {
            "tank": [12211],
            "bud": [12211],
            "support": [12210],
            "buffer": [12210],
            "healer": [12210],
            "debuffer": [12210],
            "flex": [12212],
            "gold": [12210],
            "speed": [12210],
        },
        # Bruenor: BUD/top damage → Shield Master; support → Battle Master
        "1": {
            "tank": [7],
            "support": [7],
            "buffer": [7],
            "healer": [7],
            "debuffer": [7],
            "flex": [7],
            "bud": [6],
            "gold": [7],
            "speed": [7],
        },
        # Celeste: healer Life, bud War
        "2": {
            "healer": [30],
            "support": [30],
            "buffer": [30],
            "tank": [30],
            "debuffer": [30],
            "flex": [30],
            "bud": [29],
            "gold": [30],
            "speed": [30],
        },
        # Catti-brie: bud Piercing Arrow, support Big Push, flex Critical Family
        "25": {
            "bud": [11312],
            "support": [11313],
            "buffer": [11313],
            "tank": [11313],
            "healer": [11313],
            "debuffer": [11313],
            "flex": [11314],
            "gold": [11313],
            "speed": [11313],
        },
        # Donaar: tank Scales+Hold-ish → keep Business Partners + Cower; bud can use Duel
        "34": {
            "tank": [18659, 18662],
            "support": [18659, 18662],
            "buffer": [18659, 18662],
            "healer": [18659, 18662],
            "debuffer": [18659, 18662],
            "flex": [18659, 18662],
            "bud": [18659, 18661],
            "gold": [18659, 18662],
            "speed": [18659, 18662],
        },
        # Volo: static Magical default; dynamic engine overrides from formation stacks
        "159": {
            "support": [16556],
            "buffer": [16556],
            "tank": [16556],
            "healer": [16556],
            "debuffer": [16556],
            "flex": [16556],
            "bud": [16556],
            "gold": [16556],
            "speed": [16556],
        },
        # Gaar DPS/Support splits (guide notes; names may differ from old guides)
        "60": {"bud": [9635], "support": [9634], "buffer": [9634], "tank": [9634], "healer": [9634],
               "debuffer": [9634], "flex": [9634], "gold": [9634], "speed": [9634]},
        "118": {"bud": [9762], "support": [9761], "buffer": [9761], "tank": [9761], "healer": [9761],
                "debuffer": [9761], "flex": [9761], "gold": [9761], "speed": [9761]},
        "168": {"bud": [17763], "support": [17762], "buffer": [17762], "tank": [17762], "healer": [17762],
                "debuffer": [17762], "flex": [17762], "gold": [17762], "speed": [17762]},
        "16": {"bud": [14879], "support": [14878], "buffer": [14878], "tank": [14878], "healer": [14878],
               "debuffer": [14878], "flex": [14878], "gold": [14878], "speed": [14878]},
        "48": {"bud": [12132], "support": [12133], "buffer": [12133], "tank": [12133], "healer": [12133],
               "debuffer": [12133], "flex": [12133], "gold": [12133], "speed": [12133]},
        "128": {"bud": [12118], "support": [12119], "buffer": [12119], "tank": [12119], "healer": [12119],
                "debuffer": [12119], "flex": [12120], "gold": [12119], "speed": [12119]},
        "143": {"bud": [13726], "support": [13728], "buffer": [13728], "tank": [13728], "healer": [13728],
                "debuffer": [13728], "flex": [13728], "gold": [13728], "speed": [13728]},
        "30": {"bud": [1238], "support": [1237], "buffer": [1237], "tank": [1237], "healer": [1237],
               "debuffer": [1237], "flex": [1237], "gold": [1237], "speed": [1237]},
        "18": {"gold": [11516], "support": [11517], "buffer": [11517], "tank": [11517], "healer": [11517],
               "debuffer": [11517], "flex": [11517], "bud": [11517], "speed": [11517]},
        "10": {"support": [145], "buffer": [145], "tank": [145], "healer": [145], "debuffer": [145],
               "flex": [145], "bud": [145], "gold": [145], "speed": [145]},
        "80": {"gold": [15041], "support": [16152], "buffer": [16152], "tank": [16152], "healer": [16152],
               "debuffer": [16152], "flex": [16152], "bud": [16152], "speed": [16152]},
        "39": {"gold": [2038], "support": [2039], "buffer": [2039], "tank": [2039], "healer": [2039],
               "debuffer": [2039], "flex": [2039], "bud": [2039], "speed": [2039]},
        "83": {"gold": [15233], "support": [15232], "buffer": [15232], "tank": [15232], "healer": [15232],
               "debuffer": [15232], "flex": [15232], "bud": [15232], "speed": [15232]},
        "98": {"gold": [7538], "support": [7539], "buffer": [7539], "tank": [7539], "healer": [7539],
               "debuffer": [7539], "flex": [7539], "bud": [7539], "speed": [7539]},
        "166": {"bud": [17679], "support": [17679], "buffer": [17679], "tank": [17679], "healer": [17679],
                "debuffer": [17679], "flex": [17679], "gold": [17679], "speed": [17679]},
        "157": {"support": [16134], "buffer": [16134], "tank": [16134], "healer": [16134], "debuffer": [16134],
                "flex": [16134], "bud": [16135], "gold": [16134], "speed": [16134]},
    }

    manual_hids = set(role_maps)

    for hid, mapping in role_maps.items():
        entry = heroes.get(hid)
        hero_spec = spec_heroes.get(hid) or {}
        if not entry or not hero_spec:
            continue
        default_ids = [int(x) for x in (hero_spec.get("default") or [])]
        full = _fill_role_map_gaps(mapping, default_ids)
        _apply_specs_to_roles(entry, full, hero_spec, default_ids or next(iter(full.values())))

    # Auto-extract role splits from Gaar notes for heroes not manually mapped
    index = json.loads((GUIDES / "index.json").read_text(encoding="utf-8"))
    auto_applied = 0
    for row in index:
        path = GUIDES / f"{row['id']}.json"
        if not path.exists():
            continue
        post = json.loads(path.read_text(encoding="utf-8"))
        body = post.get("selftext") or ""
        if "gaar" not in str(post.get("author") or "").lower() and "gaar" not in body[:200].lower():
            continue
        title = str(post.get("title") or "")
        # resolve hero from advice entries by guide_id
        matched_hid = None
        for hid, entry in heroes.items():
            if str(entry.get("guide_id") or "") == str(row["id"]):
                matched_hid = hid
                break
        if matched_hid is None or matched_hid in manual_hids:
            continue
        hero_spec = spec_heroes.get(matched_hid) or {}
        parsed = _role_map_from_guide_body(body, hero_spec)
        if not parsed:
            continue
        default_ids = [int(x) for x in (hero_spec.get("default") or [])]
        full = _fill_role_map_gaps(parsed, default_ids)
        entry = heroes[matched_hid]
        _apply_specs_to_roles(entry, full, hero_spec, default_ids or next(iter(full.values())))
        auto_applied += 1
        print("auto role-specs", matched_hid, entry.get("name"), list(full.keys()))

    # Formation cleanup + hand fixes for the seven + noisy ones
    formation_overrides = {
        "85": "Swap with Delina (Slot 8).",
        "94": "Gold find support; Oxventurers in formation help recover the shiny gold piece.",
        "101": "Support/druid placement; pair with Oxventurers when possible.",
        "104": "Stack Embrace Evil; place where Battle Magic hits your DPS column.",
        "149": "Melee-crit support; keep him where Form Up / Legacy buffs your frontline.",
        "159": (
            "Dynamic: pick the specialization with the most stacks — "
            "Hunters (Spirits), Ceremorphosis (Tadpoles), or Magic attacks (All Things Magical)."
        ),
        "162": "Place behind the Primary DPS so her positional buffs land.",
        "164": "Dynamic: pick Fallback / Ranged / Rogues' Gallery based on formation tags.",
        "174": "Spec choice depends on where your DPS sits; Map Collector tracks your strongest affinity.",
        "34": "Use Command: Cower for general support; Duel when Donaar is closer to a carry DPS.",
        "3": "Tank alone → Oath of Vengeance (buffs behind). With another tank → Oath of Devotion.",
        "26": "Solo tank → Compel Duel. Multi-tank → Protection. Affiliate-heavy → Lathander's Allies.",
    }
    for hid, text in formation_overrides.items():
        entry = heroes.get(hid)
        if not entry:
            continue
        for role, block in (entry.get("roles") or {}).items():
            block["formation"] = text

    # Generic formation cleanup for everyone else
    cleaned = 0
    for hid, entry in heroes.items():
        if hid in formation_overrides:
            continue
        for block in (entry.get("roles") or {}).values():
            before = block.get("formation") or ""
            after = _clean_formation(before)
            if after != before:
                block["formation"] = after
                cleaned += 1

    # Fill empty feats from guides / wiki
    index = json.loads((GUIDES / "index.json").read_text(encoding="utf-8"))
    for hid, needle in (("60", "krydle"), ("61", "jaheira")):
        hits = [
            r
            for r in index
            if needle in (r.get("title") or "").lower() and "guide" in (r.get("title") or "").lower()
        ]
        feats: list[str] = []
        for hit in hits:
            feats = _feats_from_guide(str(hit["id"]))
            if feats:
                break
        # Older 3-column feat tables (Found | Name | Effect) have no Recommended tags.
        if not feats:
            for hit in hits:
                feats = _feats_from_legacy_table(str(hit["id"]))
                if feats:
                    break
        entry = heroes.get(hid)
        if not entry or not feats:
            print(f"no feats for {hid} {needle}: {feats}")
            continue
        for role, block in (entry.get("roles") or {}).items():
            if not block.get("feats"):
                block["feats"] = list(feats)
        print(f"filled feats {hid}: {feats}")

    # Hand picks for Year-3 guides (strongest ability / global feats)
    manual_feats = {
        "60": {
            "support": ["Inspiring Leader", "Harrowing History"],
            "buffer": ["Inspiring Leader", "Harrowing History"],
            "bud": ["Grappler", "Shadow Dealing"],
            "flex": ["Inspiring Leader", "Harrowing History"],
            "tank": ["Inspiring Leader", "Harrowing History"],
            "healer": ["Inspiring Leader", "Harrowing History"],
            "debuffer": ["Inspiring Leader", "Harrowing History"],
            "gold": ["Inspiring Leader", "Harrowing History"],
            "speed": ["Inspiring Leader", "Harrowing History"],
        },
        "61": {
            "support": ["Inspiring Leader", "Gate Warden"],
            "buffer": ["Inspiring Leader", "Gate Warden"],
            "bud": ["Grappler", "Gate Warden"],
            "flex": ["Inspiring Leader", "Gate Warden"],
            "tank": ["Inspiring Leader", "Gate Warden"],
            "healer": ["Inspiring Leader", "Gate Warden"],
            "debuffer": ["Inspiring Leader", "Gate Warden"],
            "gold": ["Inspiring Leader", "Gate Warden"],
            "speed": ["Inspiring Leader", "Gate Warden"],
        },
    }
    for hid, by_role in manual_feats.items():
        entry = heroes.get(hid)
        if not entry:
            continue
        for role, block in (entry.get("roles") or {}).items():
            block["feats"] = list(by_role.get(role) or by_role["support"])

    # Volo feats from wiki (no Gaar feat table)
    volo_feats = {
        "support": ["Inspiring Leader", "Volo's Boundless Brilliance"],
        "buffer": ["Inspiring Leader", "Volo's Boundless Brilliance"],
        "tank": ["Inspiring Leader", "Volo's Boundless Brilliance"],
        "healer": ["Inspiring Leader", "Volo's Boundless Brilliance"],
        "debuffer": ["Inspiring Leader", "Volo's Boundless Brilliance"],
        "flex": ["Inspiring Leader", "Volo's Expanded Expertise"],
        "bud": ["Inspiring Leader", "Volo's Fantastic Findings"],
        "gold": ["Inspiring Leader", "Volo's Justified Jaunt"],
        "speed": ["Inspiring Leader", "Volo's Justified Jaunt"],
    }
    volo_entry = heroes.get("159")
    if volo_entry:
        for role, block in (volo_entry.get("roles") or {}).items():
            block["feats"] = list(volo_feats.get(role) or volo_feats["support"])
        for role in ("gold", "speed"):
            if role not in volo_entry["roles"]:
                base = next(iter(volo_entry["roles"].values()))
                volo_entry["roles"][role] = {
                    "specializations": list(base.get("specializations") or []),
                    "specialization_ids": list(base.get("specialization_ids") or []),
                    "formation": base.get("formation") or "",
                    "feats": list(volo_feats[role]),
                }

    # Tess: remove bogus "Eyes on the Horizon" feat if it's a spec name
    tess = heroes.get("164")
    if tess:
        for block in (tess.get("roles") or {}).values():
            feats = [f for f in (block.get("feats") or []) if f != "Eyes on the Horizon"]
            block["feats"] = feats

    # Enrich champions with only one feat recommendation
    enriched = 0
    for hid, entry in heroes.items():
        roles = entry.get("roles") or {}
        if not roles:
            continue
        max_feats = max(len(b.get("feats") or []) for b in roles.values())
        if max_feats >= 2:
            continue
        gid = entry.get("guide_id")
        if not gid:
            continue
        extra = (
            _feats_from_guide(str(gid))
            or _feats_from_modern_table(str(gid))
            or _feats_from_legacy_table(str(gid))
        )
        if len(extra) < 2:
            continue
        for block in roles.values():
            merged: list[str] = list(block.get("feats") or [])
            for feat in extra:
                if feat not in merged:
                    merged.append(feat)
                if len(merged) >= 2:
                    break
            block["feats"] = merged
        enriched += 1

    # Last-resort pairs for guides with only one tagged feat in parser output
    manual_second_feats = {
        "29": ["Streetsmart", "Inspiring Leader"],
        "37": ["Demonic Ichor", "Inspiring Leader"],
        "58": ["Pirate Plating", "Inspiring Leader"],
        "66": ["Inspiring Leader", "Arcane Heights"],
        "72": ["Privileged Background", "Sizzling"],
        "124": ["Ringmaster", "Lucky"],
    }
    for hid, feats in manual_second_feats.items():
        entry = heroes.get(hid)
        if not entry:
            continue
        for block in (entry.get("roles") or {}).values():
            block["feats"] = list(feats)

    advice["quality_pass"] = "role-specs+formation+feats-2026-07-29-v2"
    ADVICE.write_text(json.dumps(advice, indent=2, ensure_ascii=False), encoding="utf-8")

    # Count role-differentiated
    diff = 0
    for entry in heroes.values():
        specs = {tuple(b.get("specializations") or []) for b in (entry.get("roles") or {}).values()}
        if len(specs) > 1:
            diff += 1
    empty_feats = sum(
        1
        for e in heroes.values()
        if not any((b.get("feats") or []) for b in (e.get("roles") or {}).values())
    )
    sparse_feats = sum(
        1
        for e in heroes.values()
        if (e.get("roles") or {})
        and max(len(b.get("feats") or []) for b in e["roles"].values()) <= 1
    )
    print(f"auto role-spec guides applied: {auto_applied}")
    print(f"role-differentiated specs: {diff}")
    print(f"empty-feat champions: {empty_feats}")
    print(f"sparse-feat champions (<=1): {sparse_feats}")
    print(f"feat-enriched: {enriched}")
    print(f"formation fields cleaned: {cleaned}")
    print(f"wrote {ADVICE}")


if __name__ == "__main__":
    main()
