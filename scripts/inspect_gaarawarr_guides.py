"""Inspect a few downloaded Gaarawarr guides for section patterns."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "gaarawarr_guides"
index = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
print("guides", len(index))
print("sample titles:")
for row in index[:5] + index[80:85] + index[-5:]:
    print("-", row["id"], row["title"], "body", row["body_len"])

# Prefer recent + one older with body
picks = []
for row in index:
    if row["body_len"] > 5000:
        picks.append(row["id"])
    if len(picks) >= 4:
        break
# also find Farideh if present
for row in index:
    if "Farideh" in (row["title"] or ""):
        picks.append(row["id"])
        break

for pid in picks:
    path = ROOT / f"{pid}.json"
    if not path.exists():
        print("missing", pid)
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    body = data.get("selftext") or ""
    print("\n====", data.get("title"))
    print("body_len", len(body))
    for m in re.finditer(r"(?m)^#{1,3}\s+(.+)$", body):
        print(" H", m.group(1)[:120])
    for m in re.finditer(r"(?m)^\*\*([^*]{3,90})\*\*", body):
        title = m.group(1).strip()
        low = title.lower()
        if any(k in low for k in ("spec", "feat", "format", "when to", "role", "dps", "tank", "support", "gold", "speed", "build", "equip")):
            print(" B", title[:120])
