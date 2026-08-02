"""Audit all speed role blocks in champion_role_advice.json."""
from __future__ import annotations

import json
from pathlib import Path

from ic_gamedata.champion_role_advice import clear_role_advice_cache, get_role_advice

ROOT = Path(__file__).resolve().parents[2]
advice = json.loads((ROOT / "config" / "champion_role_advice.json").read_text(encoding="utf-8"))
champs = json.loads((ROOT / "config" / "champions.json").read_text(encoding="utf-8"))
clear_role_advice_cache()

heroes = advice.get("champions") or {}
rows = []
for hid_str, entry in heroes.items():
    speed = (entry.get("roles") or {}).get("speed")
    if not speed:
        continue
    hid = int(hid_str)
    name = entry.get("name") or champs.get(hid_str, {}).get("name") or hid
    cfg = list(speed.get("feats") or [])
    resolved = list(get_role_advice(hid, "speed").feats) if get_role_advice(hid, "speed") else []
    support = (entry.get("roles") or {}).get("support") or {}
    sup_feats = list(support.get("feats") or [])
    same_as_support = cfg and cfg == sup_feats
    rows.append((hid, name, cfg, resolved, same_as_support, entry.get("guide_id")))

print(f"{'id':>4}  {'name':22}  same_as_support  cfg_feats  resolved")
for hid, name, cfg, resolved, same, gid in sorted(rows, key=lambda r: r[0]):
    if same or (cfg and cfg != resolved) or (cfg and not resolved):
        print(f"{hid:4}  {str(name)[:22]:22}  {str(same):5}  {cfg}  -> {resolved}  ({gid})")

print("total speed blocks", len(rows))
print("same as support", sum(1 for r in rows if r[4]))
print("cfg but empty resolved", sum(1 for r in rows if r[2] and not r[3]))
