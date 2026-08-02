"""One-off: rank epic gear slots for Marvelous Support Pigment (pigment id 3)."""

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
from ic_gamedata.snapshot_fetch import fetch_merged_snapshot

SUPPORT_PIGMENT_ID = 3
RARITY_LABEL = {
    1: "common",
    2: "uncommon",
    3: "rare",
    4: "epic",
    5: "legendary",
    6: "shiny legendary",
}


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
    owned = {h["hero_id"]: h for h in heroes if h.get("owned")}

    from ic_gamedata.party_advisor import _formation_heroes

    active_formation = _formation_heroes(payload)
    active_ids = {h.hero_id for h in active_formation}

    saved_ids: set[int] = set()
    for save in details.get("formation_saves_v2", []):
        if not isinstance(save, dict):
            continue
        name = (save.get("name") or "").lower()
        if save.get("favorite") or "push" in name or "speed" in name or "bud" in name:
            for hero_raw in save.get("formation", []):
                hid = _parse_int(hero_raw)
                if hid is not None:
                    saved_ids.add(hid)

    defs = json.loads((install.downloaded_files_dir / "cached_definitions.json").read_text(encoding="utf-8"))
    loot_names: dict[tuple[int, int], str] = {}
    for loot_def in defs.get("loot_defines", []):
        key = (loot_def.get("hero_id"), loot_def.get("slot_id"))
        loot_names[key] = loot_def.get("name", f"Slot {loot_def.get('slot_id')}")

    def champ_info(hid: int) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        entry = champs.get(str(hid), {})
        return (
            entry.get("name", f"Hero {hid}"),
            tuple(entry.get("roles", [])),
            tuple(entry.get("tags", [])),
        )

    def support_score(hid: int) -> tuple[int, str, tuple[str, ...], tuple[str, ...]]:
        name, roles, tags = champ_info(hid)
        score = 0
        if "healer" in roles:
            score += 100
        if "support" in roles:
            score += 80
        if "buffer" in tags:
            score += 40
        if "tank" in roles:
            score += 15
        if hid in active_ids:
            score += 100
        elif hid in saved_ids:
            score += 60
        if owned.get(hid, {}).get("level", 0) >= 400:
            score += 10
        return score, name, roles, tags

    candidates: list[dict] = []
    for (hid, slot), item in best.items():
        rarity = _parse_int(item.get("rarity")) or 0
        pigment = _parse_int(item.get("pigment")) or 0
        if rarity < RARITY_EPIC or pigment > 0:
            continue
        base, name, roles, tags = support_score(hid)
        if base < 40:
            continue
        enchant = _parse_int(item.get("enchant")) or 0
        gild = _parse_int(item.get("gild")) or 0
        gear_name = loot_names.get((hid, slot), f"Slot {slot}")
        candidates.append(
            {
                "hero_id": hid,
                "name": name,
                "slot": slot,
                "gear": gear_name,
                "rarity": RARITY_LABEL.get(rarity, str(rarity)),
                "enchant": enchant,
                "gild": gild,
                "in_active": hid in active_ids,
                "in_saved": hid in saved_ids,
                "roles": roles,
                "tags": tags,
                "score": base + enchant / 10 + (5 if gild >= 1 else 0),
            }
        )

    candidates.sort(key=lambda row: (-row["score"], -row["enchant"]))

    print(f"Snapshot: {detail}")
    print("\n=== Support/buffer in active formation ===")
    for hero in sorted(active_formation, key=lambda h: h.seat):
        if "support" in hero.roles or "healer" in hero.roles:
            print(f"  seat {hero.seat}: {hero.name} ({hero.hero_id}) ilvl={hero.ilvl}")

    print("\n=== Al Support Pigment (id 3) ===")
    for (hid, slot), item in sorted(best.items()):
        pigment = _parse_int(item.get("pigment")) or 0
        if pigment != SUPPORT_PIGMENT_ID:
            continue
        base, name, roles, tags = support_score(hid)
        if base < 40:
            continue
        gear = loot_names.get((hid, slot), f"Slot {slot}")
        print(f"  {name} slot {slot} ({gear})")

    # One best slot per champion for diversity.
    seen: set[int] = set()
    top: list[dict] = []
    for row in candidates:
        if row["hero_id"] in seen:
            continue
        seen.add(row["hero_id"])
        top.append(row)
        if len(top) >= 5:
            break

    print("\n=== Top 5 aanbevelingen ===")
    for index, row in enumerate(top, 1):
        if row["in_active"]:
            usage = "actieve formation"
        elif row["in_saved"]:
            usage = "opgeslagen push/speed team"
        else:
            usage = "bench"
        print(
            f"{index}. {row['name']} — {row['gear']} "
            f"(slot {row['slot']}, {row['rarity']}, +{row['enchant']}, {usage})"
        )

    print("\n=== Actieve/speed team — epic zonder pigment ===")
    focus_ids = [58, 75, 83, 47, 28, 59, 148, 52, 3, 126, 172, 166, 170, 151, 498, 624, 21, 2, 19]
    for hid in focus_ids:
        best_epic: tuple[int, int, str] | None = None
        for (hero_id, slot), item in best.items():
            if hero_id != hid:
                continue
            rarity = _parse_int(item.get("rarity")) or 0
            pigment = _parse_int(item.get("pigment")) or 0
            enchant = _parse_int(item.get("enchant")) or 0
            if rarity >= RARITY_EPIC and pigment == 0:
                gear = loot_names.get((hero_id, slot), f"Slot {slot}")
                if best_epic is None or enchant > best_epic[0]:
                    best_epic = (enchant, slot, gear)
        name, _, _ = champ_info(hid)
        if best_epic:
            print(f"  {name}: slot {best_epic[1]} — {best_epic[2]} (+{best_epic[0]})")
        else:
            print(f"  {name}: geen epic zonder pigment")


if __name__ == "__main__":
    main()
