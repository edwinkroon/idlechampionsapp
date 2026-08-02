"""Print specialization/feat excerpts from sample Gaarawarr guides."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "data" / "gaarawarr_guides"


def section(body: str, names: tuple[str, ...]) -> str:
    pattern = r"(?is)(?:^|\n)(?:#{1,3}\s*)?(?:\*\*)?(" + "|".join(re.escape(n) for n in names) + r")(?:\*\*)?\s*\n(.*?)(?=\n(?:#{1,3}\s|\*\*[A-Z][^*]{2,60}\*\*\s*\n)|$)"
    m = re.search(pattern, body)
    return (m.group(0) if m else "")[:2500]


for pid in ("1ukyeic", "1tys9zz", "1opg14g", "d8wxuk", "1o7mhsf"):
    path = ROOT / f"{pid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    body = data.get("selftext") or ""
    print("=" * 80)
    print(data.get("title"))
    print("--- SPECS ---")
    print(section(body, ("First Specialization Choice", "Second Specialization Choice", "Specializations", "Specialization")))
    print("--- FEATS ---")
    print(section(body, ("Feats", "Feat")))
    print("--- FORMATION ---")
    print(section(body, ("Formation & Mission Information", "Formation Information", "New Player Formation & Specializations")))
