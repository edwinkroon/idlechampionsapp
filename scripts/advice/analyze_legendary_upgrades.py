"""Rank epic gear worth upgrading to legendary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ic_gamedata.adventure_restrictions import _parse_int
from ic_gamedata.credentials import extract_credentials_from_log
from ic_gamedata.loot_stats import RARITY_EPIC, _best_loot_by_hero_slot
from ic_gamedata.paths import find_game_install
from ic_gamedata.party_advisor import _formation_heroes
from ic_gamedata.snapshot_fetch import fetch_merged_snapshot

RARITY_LEGENDARY = 5
RARITY_LABEL = {4: "epic", 5: "legendary", 6: "shiny legendary"}


def main() -> None:
    champs = json.loads((ROOT / "config/champions.json").read_text(encoding="utf-8"))
    install = find_game_install()
    log = install.web_request_log
    creds = extract_credentials_from_log(log)
    _, payload, _, _, _, detail = fetch_merged_snapshot(creds, log, None)
    if payload is None:
        print("Geen payload beschikbaar")
        return

    details = payload["details"]
    best = _best_loot_by_hero_slot(details.get("loot", []))
    heroes = details.get("heroes", [])
    owned = {int(h["hero_id"]): h for h in heroes if h.get("owned")}

    active_formation = _formation_heroes(payload)
    active_ids = {h.hero_id for h in active_formation}
    active_by_id = {h.hero_id: h for h in active_formation}

    saved_ids: set[int] = set()
    push_ids: set[int] = set()
    speed_ids: set[int] = set()
    for save in details.get("formation_saves_v2", []):
        if not isinstance(save, dict):
            continue
        name = (save.get("name") or "").lower()
        save_heroes: set[int] = set()
        for hero_raw in save.get("formation", []):
            hid = _parse_int(hero_raw)
            if hid is not None:
                save_heroes.add(hid)
        if save.get("favorite") or "push" in name or "speed" in name or "bud" in name:
            saved_ids |= save_heroes
        if "push" in name:
            push_ids |= save_heroes
        if "speed" in name:
            speed_ids |= save_heroes

    defs = json.loads((install.downloaded_files_dir / "cached_definitions.json").read_text(encoding="utf-8"))
    loot_names: dict[tuple[int, int], str] = {}
    for loot_def in defs.get("loot_defines", []):
        key = (loot_def.get("hero_id"), loot_def.get("slot_id"))
        loot_names[key] = loot_def.get("name", f"Slot {loot_def.get('slot_id')}")

    def champ_meta(hid: int) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        entry = champs.get(str(hid), {})
        return (
            entry.get("name", f"Hero {hid}"),
            tuple(entry.get("roles", [])),
            tuple(entry.get("tags", [])),
        )

    def hero_priority(hid: int) -> tuple[int, str]:
        name, roles, tags = champ_meta(hid)
        score = 0
        reasons: list[str] = []

        if hid in active_ids:
            score += 200
            reasons.append("actieve formation")
        if hid in speed_ids:
            score += 120
            reasons.append("speed-team")
        if hid in push_ids:
            score += 120
            reasons.append("push-team")
        elif hid in saved_ids:
            score += 70
            reasons.append("opgeslagen team")

        if "buffer" in tags:
            score += 50
        if "support" in roles:
            score += 40
        if "healer" in roles:
            score += 35
        if "dps" in roles:
            score += 30
        if "speed" in tags:
            score += 25
        if "bud" in tags or "debuffer" in tags:
            score += 20
        if "gold" in tags:
            score += 10

        level = _parse_int(owned.get(hid, {}).get("level")) or 0
        if level >= 400:
            score += 15
        elif level >= 200:
            score += 5

        if hid in active_by_id and active_by_id[hid].ilvl >= 300:
            score += 20

        return score, ", ".join(reasons) if reasons else "bench"

    candidates: list[dict] = []
    for (hid, slot), item in best.items():
        rarity = _parse_int(item.get("rarity")) or 0
        if rarity != RARITY_EPIC:
            continue

        enchant = _parse_int(item.get("enchant")) or 0
        gild = _parse_int(item.get("gild")) or 0
        pigment = _parse_int(item.get("pigment")) or 0
        hero_score, usage = hero_priority(hid)
        name, roles, tags = champ_meta(hid)
        gear_name = loot_names.get((hid, slot), f"Slot {slot}")

        # High enchant = already invested; pigment = planned long-term piece.
        item_score = hero_score + enchant / 5 + (15 if pigment else 0) + (10 if gild >= 1 else 0)

        candidates.append(
            {
                "hero_id": hid,
                "name": name,
                "slot": slot,
                "gear": gear_name,
                "enchant": enchant,
                "gild": gild,
                "pigment": pigment,
                "usage": usage,
                "score": item_score,
            }
        )

    candidates.sort(key=lambda row: (-row["score"], -row["enchant"]))

    print(f"Snapshot: {detail}")
    epic_count = len(candidates)
    leg_count = sum(
        1
        for item in best.values()
        if (_parse_int(item.get("rarity")) or 0) >= RARITY_LEGENDARY
    )
    print(f"Epic slots (upgradebaar): {epic_count} | Al legendary+: {leg_count}")

    # Max 2 slots per champion for a useful top 10 spread.
    per_hero: dict[int, int] = {}
    top: list[dict] = []
    for row in candidates:
        count = per_hero.get(row["hero_id"], 0)
        if count >= 2:
            continue
        per_hero[row["hero_id"]] = count + 1
        top.append(row)
        if len(top) >= 10:
            break

    print("\n=== Top 10 legendary upgrades (epic -> legendary) ===")
    for index, row in enumerate(top, 1):
        notes: list[str] = []
        if row["gild"] >= 1:
            notes.append("shiny")
        if row["pigment"]:
            notes.append(f"pigment={row['pigment']}")
        note_text = f", {', '.join(notes)}" if notes else ""
        print(
            f"{index}. {row['name']} — {row['gear']} "
            f"(slot {row['slot']}, epic +{row['enchant']}{note_text}) "
            f"[{row['usage']}]"
        )


if __name__ == "__main__":
    main()
