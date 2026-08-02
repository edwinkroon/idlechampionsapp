"""Download specific known guide posts for the 7 missing champions."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "gaarawarr_guides"
ALT = ROOT / "data" / "alt_guides"
ALT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "IdleChampionsAdvisor/1.0"}
IDS = "https://arctic-shift.photon-reddit.com/api/posts/ids"

# Known post ids from Arctic search + targeted lookups
POSTS = {
    "Corazon": ["plrgke", "16eln1w"],  # Psylisa guide, Bring the Heat
    "Rust": ["10flh9u", "1eifaa3", "rygdhd"],
    "Merilwen": ["v7z0np"],
    "Voronika": ["wl8oc4", "1g0pt0h"],
    "Ravengard": ["1d9123g"],
    "Volo": [],
    "Tasslehoff": ["1s59zpp"],
}

# Extra searches for Volo / Tasslehoff / Corazon via ids discovered later
EXTRA_QUERIES = [
    ("author=Gaarawarr&subreddit=idlechampions&title=Year%208%20Champion&limit=50"),
    ("author=Gaarawarr&subreddit=idlechampions&title=Year%209%20Champion&limit=50"),
    ("author=Gaarawarr&subreddit=idlechampions&title=Fleetswake&limit=30"),
    ("author=Gaarawarr&subreddit=idlechampions&title=Volo&limit=30"),
    ("author=Gaarawarr&subreddit=idlechampions&title=Tass&limit=30"),
    ("author=Gaarawarr&subreddit=idlechampions&title=Coraz&limit=30"),
    ("subreddit=idlechampions&title=Psylisa%27s%20Guide&limit=50"),
    ("subreddit=idlechampions&title=Champion%3A%20Volo&limit=20"),
    ("subreddit=idlechampions&title=Champion%3A%20Tass&limit=20"),
    ("subreddit=idlechampions&title=Duke%20Ravengard&limit=20"),
]


def get(url: str):
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            wait = 2 + attempt * 4
            print("fail", exc, "sleep", wait)
            time.sleep(wait)
    return {"data": []}


# Discover more ids
discovered: dict[str, list[str]] = {k: list(v) for k, v in POSTS.items()}
for q in EXTRA_QUERIES:
    data = get(f"https://arctic-shift.photon-reddit.com/api/posts/search?{q}").get("data") or []
    print("query", q[:60], "n", len(data))
    for p in data:
        title = str(p.get("title") or "")
        low = title.lower()
        pid = str(p.get("id"))
        mapping = [
            ("Corazon", ("coraz",)),
            ("Rust", ("rust",)),
            ("Merilwen", ("merilwen",)),
            ("Voronika", ("voronika",)),
            ("Ravengard", ("ravengard", "ulder")),
            ("Volo", ("volo",)),
            ("Tasslehoff", ("tasslehoff", "tass,", "burrfoot")),
        ]
        for champ, keys in mapping:
            if any(k in low for k in keys) and (
                "champion" in low or "guide" in low or "spotlight" in low or "psylisa" in low
            ):
                if pid not in discovered[champ]:
                    discovered[champ].append(pid)
                    print("  +", champ, pid, title[:80], p.get("author"))
    time.sleep(1.5)

index = []
main_index_path = OUT / "index.json"
main_index = json.loads(main_index_path.read_text(encoding="utf-8")) if main_index_path.exists() else []
seen_main = {row["id"] for row in main_index}

for champ, ids in discovered.items():
    print("SAVE", champ, ids)
    for pid in ids:
        full = get(f"{IDS}?ids={pid}").get("data") or []
        if not full:
            print("  missing body", pid)
            continue
        post = full[0]
        # Save into gaarawarr_guides so parser can pick it up (any author)
        (OUT / f"{pid}.json").write_text(json.dumps(post, ensure_ascii=False), encoding="utf-8")
        (ALT / f"{pid}.json").write_text(json.dumps(post, ensure_ascii=False), encoding="utf-8")
        row = {
            "id": pid,
            "title": post.get("title"),
            "created_utc": post.get("created_utc"),
            "url": f"https://www.reddit.com{post.get('permalink')}" if post.get("permalink") else None,
            "body_len": len(post.get("selftext") or ""),
            "author": post.get("author"),
            "champion_hint": champ,
        }
        index.append(row)
        if pid not in seen_main:
            main_index.append({k: row[k] for k in ("id", "title", "created_utc", "url", "body_len")})
            seen_main.add(pid)
        time.sleep(0.7)

(ALT / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
main_index_path.write_text(json.dumps(main_index, indent=2, ensure_ascii=False), encoding="utf-8")
print("alt saved", len(index), "main index", len(main_index))
