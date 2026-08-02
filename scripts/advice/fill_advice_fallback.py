"""Fill champions missing Gaarawarr data using specializations.json defaults."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
advice_path = ROOT / "config" / "champion_role_advice.json"
champs = json.loads((ROOT / "config" / "champions.json").read_text(encoding="utf-8"))
specs = json.loads((ROOT / "config" / "specializations.json").read_text(encoding="utf-8"))
advice = json.loads(advice_path.read_text(encoding="utf-8"))
heroes = advice.setdefault("champions", {})

added = 0
for hid, cfg in champs.items():
    if hid in heroes:
        continue
    spec = (specs.get("heroes") or {}).get(hid) or {}
    options = list(spec.get("options") or [])
    defaults = list(spec.get("default") or [])
    names = []
    for uid in defaults:
        for opt in options:
            if int(opt.get("upgrade_id") or -1) == int(uid):
                names.append(str(opt.get("name") or uid))
                break
        else:
            names.append(str(uid))
    role_block = {
        "specializations": names,
        "specialization_ids": [int(x) for x in defaults],
        "formation": "",
        "feats": [],
    }
    roles = {r: dict(role_block) for r in ("support", "buffer", "tank", "healer", "debuffer", "bud", "flex", "gold", "speed")}
    # Prefer champion configured roles first
    for r in cfg.get("roles") or []:
        roles.setdefault(str(r), dict(role_block))
    heroes[hid] = {
        "name": cfg.get("name"),
        "source": "specializations.json fallback",
        "source_url": "",
        "source_date": None,
        "guide_id": None,
        "guide_title": None,
        "roles": roles,
    }
    added += 1

advice["coverage"] = {
    "guides_indexed": advice.get("coverage", {}).get("guides_indexed"),
    "champions_matched": sum(
        1
        for v in heroes.values()
        if "fallback" not in str(v.get("source") or "").lower()
        or "stub" in str(v.get("source") or "").lower()
    ),
    "champions_fallback": sum(
        1
        for v in heroes.values()
        if str(v.get("source") or "") == "specializations.json fallback"
    ),
    "champions_total": len(champs),
}
advice["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
advice_path.write_text(json.dumps(advice, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"added fallback for {added}; total entries {len(heroes)}/{len(champs)}")
