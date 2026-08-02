"""Show unmatched guide names and missing champions."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
advice = json.loads((ROOT / "config" / "champion_role_advice.json").read_text(encoding="utf-8"))
champs = json.loads((ROOT / "config" / "champions.json").read_text(encoding="utf-8"))
matched = {int(k) for k in advice["champions"]}
missing = [(int(k), v["name"]) for k, v in champs.items() if int(k) not in matched]
print("matched", len(matched), "missing", len(missing))
for hid, name in missing:
    print(f"  {hid}: {name}")
print("unmatched guides:")
for u in advice.get("unmatched_guides") or []:
    print(" ", u)
index = json.loads((ROOT / "data" / "gaarawarr_guides" / "index.json").read_text(encoding="utf-8"))
for hid, name in missing:
    hits = [r for r in index if name.split()[0].lower() in (r.get("title") or "").lower()]
    if hits:
        print(hid, name, "->", [h.get("title") for h in hits[:3]])
