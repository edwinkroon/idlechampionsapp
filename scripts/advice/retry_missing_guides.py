"""Retry Arctic Shift fetches for remaining missing Gaarawarr guides (slow)."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "gaarawarr_guides"
UA = {"User-Agent": "IdleChampionsAdvisor/1.0"}
BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"
IDS = "https://arctic-shift.photon-reddit.com/api/posts/ids"

advice = json.loads((ROOT / "config" / "champion_role_advice.json").read_text(encoding="utf-8"))
champs = json.loads((ROOT / "config" / "champions.json").read_text(encoding="utf-8"))
missing = [
    v["name"]
    for k, v in champs.items()
    if (advice.get("champions") or {}).get(k, {}).get("source") != "Gaarawarr"
]
print("retry missing", len(missing))


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
seen = {row["id"] for row in index}
added = 0
for name in missing:
    token = name.replace("'", " ").split()[0]
    if len(token) < 3:
        token = name
    q = urllib.parse.urlencode(
        {
            "author": "Gaarawarr",
            "subreddit": "idlechampions",
            "title": token,
            "limit": 25,
        }
    )
    for attempt in range(4):
        try:
            rows = get(f"{BASE}?{q}").get("data") or []
            break
        except Exception as exc:  # noqa: BLE001
            wait = 2 + attempt * 3
            print(f"retry {name} after {exc} sleep {wait}s")
            time.sleep(wait)
            rows = []
    hits = [
        p
        for p in rows
        if "champion guide" in str(p.get("title") or "").lower()
        and token.lower() in str(p.get("title") or "").lower()
    ]
    print(name, "->", len(hits))
    for post in hits:
        pid = str(post.get("id"))
        if pid in seen:
            continue
        try:
            full = get(f"{IDS}?ids={pid}").get("data") or [post]
        except Exception:
            full = [post]
        post = full[0] if full else post
        (OUT / f"{pid}.json").write_text(json.dumps(post, ensure_ascii=False), encoding="utf-8")
        index.append(
            {
                "id": pid,
                "title": post.get("title"),
                "created_utc": post.get("created_utc"),
                "url": f"https://www.reddit.com{post.get('permalink')}" if post.get("permalink") else None,
                "body_len": len(post.get("selftext") or ""),
            }
        )
        seen.add(pid)
        added += 1
        time.sleep(0.8)
    time.sleep(1.2)

(OUT / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
print("added", added)
