"""Scrape ic_spoilers patron roster into config/patron_roster.json."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

HTML_URL = "https://emmotes.github.io/ic_spoilers/patron_roster.html"
PATRON_IDS = ("mirt", "vajra", "strahd", "zariel", "elminster")
OUT_PATH = Path(__file__).resolve().parent.parent / "config" / "patron_roster.json"


def _availability(code: int) -> str:
    if code == 0:
        return "unavailable"
    if code == 331:
        return "feat"
    if code == 333:
        return "available"
    if code == 334:
        return "always"
    return "timed"


def scrape() -> dict[str, object]:
    html = urllib.request.urlopen(HTML_URL).read().decode("utf-8", "replace")
    items = re.findall(
        r'class="patronRosterItem(?: [^"]*)?" data-sort="([^"]+)"[^>]*>(.*?)</span>',
        html,
        re.S,
    )
    rows: list[dict[str, object]] = []
    index = 0
    while index + 10 < len(items):
        sort_raw, id_text = items[index + 1]
        _, name_text = items[index + 3]
        _, seat_text = items[index + 5]
        hero_id = int(re.sub(r"\D", "", id_text) or "0")
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", name_text)).strip()
        seat = int(re.sub(r"\D", "", seat_text) or "0")
        if hero_id <= 0 or not name or not name[0].isalpha():
            index += 1
            continue
        parts = [int(part) for part in sort_raw.split(",")]
        if len(parts) < 8:
            index += 1
            continue
        patrons = {
            patron: _availability(parts[3 + offset])
            for offset, patron in enumerate(PATRON_IDS)
        }
        rows.append({"hero_id": hero_id, "name": name, "seat": seat, "patrons": patrons})
        index += 10

    deduped: dict[int, dict[str, object]] = {}
    for row in rows:
        deduped[int(row["hero_id"])] = row
    return {
        "source": HTML_URL,
        "patron_ids": {"1": "mirt", "2": "vajra", "3": "strahd", "4": "zariel", "5": "elminster"},
        "heroes": [deduped[key] for key in sorted(deduped)],
    }


def main() -> None:
    data = scrape()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['heroes'])} heroes to {OUT_PATH}")
    bruenor = next(item for item in data["heroes"] if item["hero_id"] == 1)
    print("Bruenor:", bruenor["patrons"])


if __name__ == "__main__":
    main()
