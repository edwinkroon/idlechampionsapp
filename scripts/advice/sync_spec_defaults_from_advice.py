"""Sync specializations.json defaults from Gaarawarr role advice when available."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
advice = json.loads((ROOT / "config" / "champion_role_advice.json").read_text(encoding="utf-8"))
specs_path = ROOT / "config" / "specializations.json"
specs = json.loads(specs_path.read_text(encoding="utf-8"))

# Keep dynamic engine heroes untouched in JSON defaults (engine overrides anyway),
# but still update static defaults for consistency.
updated = 0
for hid, entry in (advice.get("champions") or {}).items():
    if entry.get("source") != "Gaarawarr" and not str(entry.get("source") or "").startswith("Psylisa"):
        continue
    roles = entry.get("roles") or {}
    # Prefer support/buffer then any
    block = None
    for key in ("support", "buffer", "tank", "bud", "flex"):
        if key in roles:
            block = roles[key]
            break
    if block is None and roles:
        block = next(iter(roles.values()))
    ids = list((block or {}).get("specialization_ids") or [])
    if not ids:
        continue
    hero = (specs.get("heroes") or {}).get(hid)
    if not isinstance(hero, dict):
        continue
    if hero.get("default") != ids:
        hero["default"] = ids
        updated += 1

specs_path.write_text(json.dumps(specs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"updated defaults for {updated} heroes")
