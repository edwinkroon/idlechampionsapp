"""Download Gaarawarr champion guides via Arctic Shift (no API key)."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "IdleChampionsAdvisor/1.0 (local research)"}
BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"
IDS_BASE = "https://arctic-shift.photon-reddit.com/api/posts/ids"
OUT = Path(__file__).resolve().parents[1] / "data" / "gaarawarr_guides"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search(**params) -> list[dict]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = _get(f"{BASE}?{query}")
    items = data.get("data") or []
    return items if isinstance(items, list) else []


def _is_guide(title: str) -> bool:
    return bool(re.search(r"champion\s+guide", title or "", re.I))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seen: dict[str, dict] = {}

    title_queries = [
        "Champion Guide",
        "Core Champion",
        "Evergreen Champion",
        "Time Gate Y",
    ]
    for title in title_queries:
        rows = _search(
            author="Gaarawarr",
            subreddit="idlechampions",
            title=title,
            limit=100,
        )
        print(f"title={title!r} -> {len(rows)}")
        for post in rows:
            pid = post.get("id")
            if pid and _is_guide(str(post.get("title") or "")):
                seen[str(pid)] = post
        time.sleep(0.35)

    # Paginate older pages.
    if seen:
        oldest = min(int(p.get("created_utc") or 0) for p in seen.values())
        for page in range(12):
            rows = _search(
                author="Gaarawarr",
                subreddit="idlechampions",
                title="Champion Guide",
                limit=100,
                before=oldest,
            )
            print(f"page={page} before={oldest} -> {len(rows)}")
            if not rows:
                break
            added = 0
            for post in rows:
                created = int(post.get("created_utc") or 0)
                if created:
                    oldest = min(oldest, created)
                pid = post.get("id")
                title = str(post.get("title") or "")
                if pid and _is_guide(title) and str(pid) not in seen:
                    seen[str(pid)] = post
                    added += 1
            time.sleep(0.35)
            if added == 0 and len(rows) < 100:
                break

    # Refresh full bodies via ids endpoint (ensures complete selftext).
    ids = list(seen.keys())
    for i in range(0, len(ids), 20):
        chunk = ids[i : i + 20]
        url = f"{IDS_BASE}?ids={','.join(chunk)}"
        try:
            data = _get(url).get("data") or []
        except Exception as exc:  # noqa: BLE001
            print(f"ids refresh failed for chunk {i}: {exc}")
            data = []
        for post in data:
            pid = post.get("id")
            if pid:
                seen[str(pid)] = post
        time.sleep(0.25)

    index: list[dict] = []
    for post in sorted(seen.values(), key=lambda p: int(p.get("created_utc") or 0), reverse=True):
        pid = str(post.get("id"))
        (OUT / f"{pid}.json").write_text(json.dumps(post, ensure_ascii=False), encoding="utf-8")
        permalink = post.get("permalink")
        index.append(
            {
                "id": pid,
                "title": post.get("title"),
                "created_utc": post.get("created_utc"),
                "url": f"https://www.reddit.com{permalink}" if permalink else None,
                "body_len": len(post.get("selftext") or ""),
            }
        )

    (OUT / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved {len(index)} guides to {OUT}")
    for row in index[:10]:
        print(row["id"], (row["title"] or "")[:90])


if __name__ == "__main__":
    main()
