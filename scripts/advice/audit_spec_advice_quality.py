#!/usr/bin/env python3
"""Static quality audit for specialization advice (no live payload needed).

Flags:
- keyword substring traps (evil⊂devil, war⊂ward, …)
- CSV/route labels that do not map to an upgrade
- config default vs Gaarawarr specialization mismatch
- missing multiply-stack handlers
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ic_gamedata.specialization_engine import _keyword_in_spec_name
from ic_gamedata.specialization_models import SpecializationOption
from ic_gamedata.specialization_rules.route_mapper import (
    clear_route_override_cache,
    map_label_to_upgrade_id,
)
from ic_gamedata.specialization_stack_audit import audit_qualified_stack_specs
from ic_gamedata.specializations import load_specialization_rules

_SCORE_KEYWORDS = (
    "evil",
    "malevolence",
    "villain",
    "companion",
    "hall",
    "family",
    "allies",
    "fellowship",
    "friends",
    "ward",
    "plague",
    "withering",
    "debuff",
    "curse",
    "good",
    "phlo",
    "fast",
    "speed",
    "swift",
    "gold",
    "rich",
    "fortune",
    "riches",
    "assassin",
    "battle",
    "war",
    "critical",
    "damage",
    "vengeance",
    "champion",
    "fire",
    "heal",
    "healing",
    "life",
    "mercy",
    "guard",
    "shield",
    "protection",
    "devotion",
)


def _load_role_advice() -> dict[str, dict]:
    path = ROOT / "config" / "champion_role_advice.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    heroes = data.get("heroes") if isinstance(data, dict) else None
    return heroes if isinstance(heroes, dict) else {}


def _gaarawarr_spec_ids(entry: dict) -> list[int]:
    roles = entry.get("roles")
    if not isinstance(roles, dict):
        return []
    # Prefer support, else first role with specialization_ids
    preferred = ("support", "buffer", "dps", "tank", "healer", "flex")
    for key in preferred:
        role = roles.get(key)
        if isinstance(role, dict):
            ids = role.get("specialization_ids")
            if isinstance(ids, list) and ids:
                return [int(x) for x in ids if str(x).isdigit() or isinstance(x, int)]
    for role in roles.values():
        if not isinstance(role, dict):
            continue
        ids = role.get("specialization_ids")
        if isinstance(ids, list) and ids:
            return [int(x) for x in ids if str(x).isdigit() or isinstance(x, int)]
    return []


def _option_list(hero_cfg: dict) -> list[SpecializationOption]:
    raw = hero_cfg.get("options")
    if not isinstance(raw, list):
        return []
    out: list[SpecializationOption] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                SpecializationOption(
                    upgrade_id=int(item["upgrade_id"]),
                    name=str(item.get("name") or ""),
                    required_level=int(item.get("required_level") or 0),
                    tier_index=int(item.get("tier_index") or 0),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def audit_keyword_traps(rules: dict) -> list[str]:
    """Find option names where naive substring match differs from word-boundary match."""
    findings: list[str] = []
    heroes = rules.get("heroes") or {}
    for hero_id, cfg in heroes.items():
        if not isinstance(cfg, dict):
            continue
        name = cfg.get("name") or f"Hero {hero_id}"
        for opt in _option_list(cfg):
            opt_cf = opt.name.casefold()
            for kw in _SCORE_KEYWORDS:
                naive = kw in opt_cf
                bounded = _keyword_in_spec_name(opt.name, kw)
                if naive and not bounded:
                    findings.append(
                        f"{name} ({hero_id}): '{opt.name}' naive-matches '{kw}' "
                        f"(would false-positive without word boundaries)"
                    )
    return findings


def audit_route_gaps(rules: dict) -> list[str]:
    """CSV-style support/utility labels that fail to map for a champion."""
    from ic_gamedata.specialization_rules.loader import cached_documentation_rules

    findings: list[str] = []
    clear_route_override_cache()
    dataset = cached_documentation_rules()
    heroes = rules.get("heroes") or {}
    options_by_name: dict[str, list[SpecializationOption]] = {}
    for hero_id, cfg in heroes.items():
        if not isinstance(cfg, dict):
            continue
        champ = str(cfg.get("name") or "")
        options_by_name[champ.casefold()] = _option_list(cfg)

    for rule in dataset.rules:
        champ = rule.champion
        opts = options_by_name.get(champ.casefold())
        if not opts:
            continue
        labels = [
            rule.default_label,
            rule.alternative_label,
            rule.machine_default,
            rule.machine_alternative,
        ]
        for label in labels:
            if not label or not str(label).strip():
                continue
            mapped = map_label_to_upgrade_id(str(label), opts, champion_name=champ)
            if mapped is None and re.search(r"support|utility|route", str(label), re.I):
                findings.append(
                    f"{champ}: label {label!r} does not map to any upgrade "
                    f"(options: {', '.join(o.name for o in opts[:6])})"
                )
    # dedupe
    return sorted(set(findings))


def audit_default_vs_guide(rules: dict) -> list[str]:
    findings: list[str] = []
    advice = _load_role_advice()
    heroes = rules.get("heroes") or {}
    for hero_id, cfg in heroes.items():
        if not isinstance(cfg, dict):
            continue
        defaults = cfg.get("default")
        if not isinstance(defaults, list) or not defaults:
            continue
        entry = advice.get(str(hero_id))
        if not isinstance(entry, dict):
            continue
        guide_ids = _gaarawarr_spec_ids(entry)
        if not guide_ids:
            continue
        default_ids = [int(x) for x in defaults if str(x).isdigit() or isinstance(x, int)]
        # Compare first-tier overlap only where both have values
        if default_ids and guide_ids and default_ids[0] not in guide_ids:
            name = cfg.get("name") or f"Hero {hero_id}"
            opt_names = {o.upgrade_id: o.name for o in _option_list(cfg)}
            findings.append(
                f"{name} ({hero_id}): config default "
                f"{default_ids[0]} ({opt_names.get(default_ids[0], '?')}) "
                f"not in Gaarawarr ids {guide_ids} "
                f"({', '.join(opt_names.get(i, str(i)) for i in guide_ids)})"
            )
    return findings


def audit_missing_handlers() -> list[str]:
    findings: list[str] = []
    for tier in audit_qualified_stack_specs():
        if tier.status == "missing":
            findings.append(
                f"{tier.hero_name} ({tier.hero_id}) level {tier.required_level}: "
                f"missing multiply-stack handler — {tier.notes}"
            )
    return findings


def main() -> int:
    rules = load_specialization_rules()
    sections = {
        "keyword_traps": audit_keyword_traps(rules),
        "route_gaps": audit_route_gaps(rules),
        "default_vs_guide": audit_default_vs_guide(rules),
        "missing_handlers": audit_missing_handlers(),
    }

    total = 0
    for title, items in sections.items():
        print(f"=== {title} ({len(items)}) ===")
        for line in items[:80]:
            print(f"  - {line}")
        if len(items) > 80:
            print(f"  ... +{len(items) - 80} more")
        print()
        total += len(items)

    print(f"TOTAL findings: {total}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
