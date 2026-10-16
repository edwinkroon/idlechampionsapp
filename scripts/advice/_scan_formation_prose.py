"""Scan champion_role_advice formation prose for placement patterns.

Prints matches not yet in formation_champion_placement_rules.json heroes
or known handlers.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
advice = json.loads((ROOT / "config" / "champion_role_advice.json").read_text(encoding="utf-8"))[
    "champions"
]
placement = json.loads(
    (ROOT / "config" / "formation_champion_placement_rules.json").read_text(encoding="utf-8")
)
covered = {int(k) for k in (placement.get("heroes") or {})}
# Handlers already executable elsewhere.
covered |= {168, 173, 178}

patterns: dict[str, re.Pattern[str]] = {
    "same_column": re.compile(
        r"same column|column as (your |the )?(primary )?dps|column as (your )?bud",
        re.I,
    ),
    "adjacent_bud": re.compile(
        r"adjacent to (your |the )?(primary )?(dps|bud|carry)|"
        r"next to (your |the )?(primary )?(dps|bud|carry)|"
        r"beside (your |the )?(primary )?(dps|bud|carry)|"
        r"next to your dps",
        re.I,
    ),
    "ahead": re.compile(
        r"in front of (your |the )?(primary )?(dps|bud|carry)|"
        r"ahead of (your |the )?(primary )?(dps|bud)|"
        r"column ahead|stand in front of",
        re.I,
    ),
    "behind": re.compile(
        r"behind (your |the )?(primary )?(dps|bud|carry)|"
        r"buffs behind|columns behind|"
        r"in the column(s)? behind",
        re.I,
    ),
    "farthest": re.compile(
        r"farthest|furthest|as far as possible|"
        r"far(?:thest)? (away )?from.*(dps|bud|carry|primary)|"
        r"keep (your )?(primary )?dps (as )?far",
        re.I,
    ),
    "front": re.compile(
        r"place (him|her|them|this champion) (on |in )?(the )?front|"
        r"belongs? (up )?front|put (him|her|them) (up )?front|"
        r"on the front line of the formation",
        re.I,
    ),
    "back": re.compile(
        r"place (him|her|them) (on |in )?(the )?back|"
        r"toward the back|back of (your |the )?formation|"
        r"in the back (line|column)",
        re.I,
    ),
    "second_column": re.compile(r"2nd column|second column", re.I),
    "avoid_tank": re.compile(
        r"not (place|sit)?.*adjacent to.*tank|avoid.*tank|"
        r"far from the tanks|not adjacent to them",
        re.I,
    ),
    "distance": re.compile(r"\d[ -]?slot|does not jump|slots away|seat distance", re.I),
    "carry_not_edge": re.compile(
        r"can't be in the front or back|not in the front or back|"
        r"dps can't be in the front|primary dps can't be",
        re.I,
    ),
    "many_adjacents": re.compile(
        r"as many adjacent|many adjacents|surrounded|"
        r"maximize adjacent|adjacent champions?",
        re.I,
    ),
}

hits: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
ambiguous: list[tuple[int, str, str]] = []

for hid_s, entry in advice.items():
    hid = int(hid_s)
    if hid in covered:
        continue
    name = str(entry.get("name") or hid)
    formations: set[str] = set()
    for block in (entry.get("roles") or {}).values():
        if isinstance(block, dict):
            f = (block.get("formation") or "").strip()
            if f:
                formations.add(f)
    text = " | ".join(sorted(formations))
    if not text:
        continue
    matched = False
    for label, rx in patterns.items():
        if rx.search(text):
            hits[label].append((hid, name, text[:240].replace("\n", " ")))
            matched = True
    if not matched and any(
        w in text.casefold()
        for w in ("column", "adjacent", "front", "behind", "dps", "formation")
    ):
        ambiguous.append((hid, name, text[:240].replace("\n", " ")))

total = 0
for label in patterns:
    items = hits.get(label, [])
    total += len(items)
    print(f"=== {label} ({len(items)}) ===")
    for hid, name, snippet in sorted(items):
        print(f"  {hid:4} {name}: {snippet}")
    print()

print(f"=== ambiguous positional prose ({len(ambiguous)}) ===")
for hid, name, snippet in sorted(ambiguous)[:40]:
    print(f"  {hid:4} {name}: {snippet}")
print()
print(f"TOTAL clear pattern hits (may overlap heroes): {total}")
print(f"UNIQUE heroes with clear hits: {len({h for items in hits.values() for h, _, _ in items})}")
