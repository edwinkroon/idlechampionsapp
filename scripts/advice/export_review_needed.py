#!/usr/bin/env python3
"""Write a markdown checklist of review_needed advisor models."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ic_gamedata.specialization_advisor_model import (
    clear_specialization_advisor_models_cache,
    load_specialization_advisor_models,
)

OUT = ROOT / "documentation" / "spec_advice_review_needed.md"


def main() -> int:
    clear_specialization_advisor_models_cache()
    models = load_specialization_advisor_models()
    rows = [m for m in sorted(models.values(), key=lambda x: x.hero_id) if m.review_needed]
    null_safe = [
        m
        for m in sorted(models.values(), key=lambda x: x.hero_id)
        if m.safe_default is None and not m.review_needed
    ]
    lines = [
        "# Specialization advice — review needed",
        "",
        f"{len(rows)} champions marked `review_needed` in advisor models.",
        "",
        "Per champion: kies één kant van het conflict, of houd `safe_default` op null.",
        "",
        "| hero_id | name | model | safe | push | farm | first reason |",
        "|---:|---|---|---|---|---|---|",
    ]
    for m in rows:
        reason = (m.review_reasons[0] if m.review_reasons else "").replace("|", "/")
        safe = m.safe_default.name if m.safe_default else "null"
        push = m.push_default.name if m.push_default else "null"
        farm = m.farm_default.name if m.farm_default else "null"
        lines.append(
            f"| {m.hero_id} | {m.name} | {m.advice_model} | {safe} | {push} | {farm} | {reason} |"
        )
    lines.extend(
        [
            "",
            "## Intentional null `safe_default` (context-dependent)",
            "",
            "| hero_id | name | summary |",
            "|---:|---|---|",
        ]
    )
    for m in null_safe:
        summary = (m.explanation_summary or "").replace("|", "/")
        lines.append(f"| {m.hero_id} | {m.name} | {summary} |")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(rows)} review_needed, {len(null_safe)} intentional null)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
