"""Scrape ic_spoilers patron roster into config/patron_roster.json.

Cell labels are authoritative. ``data-sort`` codes are a fallback for empty
cells (checkmark with no caption). Current emmotes codes (Oct 2026):

- 0 → unavailable
- 339 → available (empty checkmark)
- 340 → always
- 337 → feat (``w/ Feats``)
- 338 → ability (partner/ability unlock)
- 336 → ability_feat (``Ability w/ Fts``)
- 1 → sometimes
- other positive codes with ``Until …`` labels → timed
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

HTML_URL = "https://emmotes.github.io/ic_spoilers/patron_roster.html"
PATRON_IDS = ("mirt", "vajra", "strahd", "zariel", "elminster")
OUT_PATH = Path(__file__).resolve().parent.parent / "config" / "patron_roster.json"

# Empty-cell fallbacks when the page shows only a checkmark / blank.
_CODE_AVAILABILITY: dict[int, str] = {
    0: "unavailable",
    1: "sometimes",
    336: "ability_feat",
    337: "feat",
    338: "ability",
    339: "available",
    340: "always",
}

_SPAN_RE = re.compile(
    r'<span class="patronRosterItem([^"]*)" data-sort="([^"]+)"[^>]*>(.*?)</span>',
    re.S,
)


def _clean_cell(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def availability_from_label(label: str, code: int) -> str:
    """Map visible patron cell text (+ code fallback) to a roster status."""
    cleaned = label.strip()
    if cleaned:
        lower = cleaned.casefold()
        if lower.startswith("until "):
            return "timed"
        if lower in {"w/ feats", "with feats", "feats"}:
            return "feat"
        if lower in {"always"}:
            return "always"
        if lower in {"ability"}:
            return "ability"
        if lower in {"ability w/ fts", "ability w/ feats", "ability with feats"}:
            return "ability_feat"
        if lower in {"sometimes"}:
            return "sometimes"
        # Unknown caption — keep as timed-like allow only if code says available-ish.
        if code in _CODE_AVAILABILITY:
            return _CODE_AVAILABILITY[code]
        return "timed"
    if code in _CODE_AVAILABILITY:
        return _CODE_AVAILABILITY[code]
    # Nonzero unknown empty code: historically "timed" window without caption.
    if code > 0:
        return "timed"
    return "unavailable"


def _availability(code: int) -> str:
    """Backward-compatible code-only helper (tests / callers without a label)."""
    return availability_from_label("", code)


def _iter_hero_groups(
    items: list[tuple[str, str, str]],
) -> list[list[tuple[str, str, str]]]:
    """Group consecutive spans that share the same data-sort (17 cells/hero)."""
    groups: list[list[tuple[str, str, str]]] = []
    index = 0
    while index < len(items):
        sort = items[index][1]
        group = [items[index]]
        index += 1
        while index < len(items) and items[index][1] == sort:
            group.append(items[index])
            index += 1
        if len(group) == 17:
            groups.append(group)
    return groups


def scrape(html: str | None = None) -> dict[str, object]:
    if html is None:
        html = urllib.request.urlopen(HTML_URL, timeout=60).read().decode(
            "utf-8", "replace"
        )
    items = _SPAN_RE.findall(html)
    rows: list[dict[str, object]] = []
    for group in _iter_hero_groups(items):
        sort_raw = group[0][1]
        parts = [int(part) for part in sort_raw.split(",") if part.strip()]
        if len(parts) < 8:
            continue
        texts = [_clean_cell(text) for _cls, _sort, text in group]
        hero_id = int(re.sub(r"\D", "", texts[1]) or "0")
        name = texts[3]
        seat = int(re.sub(r"\D", "", texts[5]) or "0")
        if hero_id <= 0 or not name or not name[0].isalpha():
            continue
        patron_labels = [texts[7], texts[9], texts[11], texts[13], texts[15]]
        patron_codes = parts[3:8]
        patrons = {
            patron: availability_from_label(label, code)
            for patron, label, code in zip(
                PATRON_IDS, patron_labels, patron_codes, strict=True
            )
        }
        rows.append(
            {
                "hero_id": hero_id,
                "name": name,
                "seat": seat,
                "patrons": patrons,
            }
        )

    deduped: dict[int, dict[str, object]] = {}
    for row in rows:
        deduped[int(row["hero_id"])] = row
    return {
        "source": HTML_URL,
        "scraped_note": (
            "Statuses from visible patron cells; data-sort codes fill empty checkmarks."
        ),
        "patron_ids": {
            "1": "mirt",
            "2": "vajra",
            "3": "strahd",
            "4": "zariel",
            "5": "elminster",
        },
        "heroes": [deduped[key] for key in sorted(deduped)],
    }


def main() -> None:
    data = scrape()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(data['heroes'])} heroes to {OUT_PATH}")
    for hero_id in (1, 48, 161):
        row = next(item for item in data["heroes"] if item["hero_id"] == hero_id)
        print(f"{row['name']}:", row["patrons"])


if __name__ == "__main__":
    main()
