#!/usr/bin/env python3
"""Report specialization tiers that need dynamic multiply-stack handlers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ic_gamedata.specialization_stack_audit import audit_qualified_stack_specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        choices=("all", "missing", "handled", "custom"),
        default="all",
        help="Filter tiers by handler status (default: all)",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Shortcut for --status missing",
    )
    args = parser.parse_args()
    status_filter = "missing" if args.missing_only else args.status

    tiers = audit_qualified_stack_specs()
    if status_filter != "all":
        tiers = [tier for tier in tiers if tier.status == status_filter]

    if not tiers:
        print("No matching multiply-stack specialization tiers found.")
        return 0

    counts = {"handled": 0, "missing": 0, "custom": 0}
    for tier in audit_qualified_stack_specs():
        counts[tier.status] = counts.get(tier.status, 0) + 1

    print(
        "Summary: "
        f"{counts.get('handled', 0)} handled, "
        f"{counts.get('missing', 0)} missing, "
        f"{counts.get('custom', 0)} custom"
    )
    print()

    for tier in tiers:
        print(
            f"[{tier.status.upper()}] {tier.hero_name} (id={tier.hero_id}, "
            f"level={tier.required_level}) — {tier.notes}"
        )
        for opt in tier.options:
            pct = f"{opt.pct:g}%" if opt.pct is not None else "?"
            print(
                f"  {opt.upgrade_id:5} {opt.name[:42]:42} "
                f"pct={pct} stack={opt.stack_func or '-'}"
            )
            if opt.filter_summary:
                print(f"         filter: {opt.filter_summary[:90]}")
        print()

    return 1 if status_filter in {"all", "missing"} and counts.get("missing", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
