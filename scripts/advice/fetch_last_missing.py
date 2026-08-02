"""Fetch the last few missing Gaarawarr champion guides with broader queries."""

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

TARGETS = {
    "Lazaapz": ["Lazaapz", "Champion Guide Lazaapz"],
    "Sgt. Knox": ["Knox", "Sgt. Knox", "Sergeant Knox"],
    "Corazon": ["Corazon"],
    "Rust": ["Rust,", "Champion Guide: Rust", "Champion Guide - Rust"],
    "Merilwen": ["Merilwen"],
    "Voronika": ["Voronika"],
    "Ravengard": ["Ravengard", "Ulder"],
    "Volo": ["Champion Guide: Volo", "Champion Guide - Volo", "Evergreen Champion Guide: Volo"],
    "Tasslehoff": ["Tasslehoff", "Tass "],
}


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


index = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
seen = {row["id"] for row in index}
added = 0
for name, queries in TARGETS.items():
    for title in queries:
        q = urllib.parse.urlencode(
            {
                "author": "Gaarawarr",
                "subreddit": "idlechampions",
                "title": title,
                "limit": 30,
            }
        )
        try:
            rows = get(f"{BASE}?{q}").get("data") or []
        except Exception as exc:  # noqa: BLE001
            print(name, title, "FAIL", exc)
            time.sleep(3)
            continue
        hits = [p for p in rows if "champion guide" in str(p.get("title") or "").lower()]
        print(name, title, "->", [(p.get("id"), p.get("title")) for p in hits[:3]])
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
            time.sleep(0.7)
        time.sleep(1.5)

(OUT / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
print("added", added)
