"""Broader Arctic Shift search for the 7 missing champions (any author)."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "alt_guides"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "IdleChampionsAdvisor/1.0"}
BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"
IDS = "https://arctic-shift.photon-reddit.com/api/posts/ids"

TARGETS = {
    "Corazon": ["Corazon", "Coraz"],
    "Rust": ["Champion Guide Rust", "Year 5 Rust", "Rust, the"],
    "Merilwen": ["Merilwen"],
    "Voronika": ["Voronika"],
    "Ravengard": ["Ravengard", "Duke Ravengard", "Ulder"],
    "Volo": ["Champion Guide Volo", "Evergreen Champion Guide: Volo", "Year 8 Champion Guide: Volo", "Guide: Volo,"],
    "Tasslehoff": ["Tasslehoff", "Tass,", "Burrfoot"],
}


def get(url: str):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            wait = 2 + attempt * 3
            print("fail", exc, "sleep", wait)
            time.sleep(wait)
    return {"data": []}


found: dict[str, list[dict]] = {k: [] for k in TARGETS}
for name, queries in TARGETS.items():
    for title in queries:
        q = urllib.parse.urlencode(
            {
                "subreddit": "idlechampions",
                "title": title,
                "limit": 50,
            }
        )
        rows = get(f"{BASE}?{q}").get("data") or []
        useful = []
        for p in rows:
            t = str(p.get("title") or "")
            low = t.lower()
            if "champion guide" in low or ("guide" in low and name.split()[0].lower() in low):
                useful.append(p)
            elif name.split()[0].lower() in low and any(
                k in low for k in ("spotlight", "guide", "formation", "specialization")
            ):
                useful.append(p)
        print(name, title, "->", len(useful), [((p.get("author"), p.get("id"), p.get("title")[:70])) for p in useful[:4]])
        for p in useful:
            found[name].append(p)
        time.sleep(1.2)

# Dedup and save full posts
index = []
for name, posts in found.items():
    seen = set()
    uniq = []
    for p in posts:
        pid = str(p.get("id"))
        if pid in seen:
            continue
        seen.add(pid)
        uniq.append(p)
    # Prefer champion guides, then newest
    uniq.sort(
        key=lambda p: (
            0 if "champion guide" in str(p.get("title") or "").lower() else 1,
            -(int(p.get("created_utc") or 0)),
        )
    )
    print("FINAL", name, len(uniq))
    for p in uniq[:3]:
        pid = str(p.get("id"))
        full = get(f"{IDS}?ids={pid}").get("data") or [p]
        post = full[0] if full else p
        (OUT / f"{pid}.json").write_text(json.dumps(post, ensure_ascii=False), encoding="utf-8")
        index.append(
            {
                "champion": name,
                "id": pid,
                "title": post.get("title"),
                "author": post.get("author"),
                "created_utc": post.get("created_utc"),
                "body_len": len(post.get("selftext") or ""),
                "url": f"https://www.reddit.com{post.get('permalink')}" if post.get("permalink") else None,
            }
        )
        time.sleep(0.8)

(OUT / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
print("saved", len(index), "posts")
