"""Sync speed role feats in champion_role_advice.json with runtime resolution."""

from __future__ import annotations

import json
from pathlib import Path

from ic_gamedata.champion_role_advice import clear_role_advice_cache, get_role_advice

ROOT = Path(__file__).resolve().parents[2]
ADVICE_PATH = ROOT / "config" / "champion_role_advice.json"


def main() -> None:
    payload = json.loads(ADVICE_PATH.read_text(encoding="utf-8"))
    champions = payload.get("champions")
    if not isinstance(champions, dict):
        raise SystemExit("champion_role_advice.json missing champions map")

    clear_role_advice_cache()
    updated = 0
    for hid_str, entry in champions.items():
        if not isinstance(entry, dict):
            continue
        roles = entry.get("roles")
        if not isinstance(roles, dict) or "speed" not in roles:
            continue
        speed = roles.get("speed")
        if not isinstance(speed, dict):
            continue
        try:
            hero_id = int(hid_str)
        except (TypeError, ValueError):
            continue
        advice = get_role_advice(hero_id, "speed")
        resolved = list(advice.feats) if advice else []
        if list(speed.get("feats") or []) == resolved:
            continue
        speed["feats"] = resolved
        updated += 1

    ADVICE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Updated speed feats for {updated} champions in {ADVICE_PATH}")


if __name__ == "__main__":
    main()
