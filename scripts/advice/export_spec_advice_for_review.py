#!/usr/bin/env python3
"""Export first N champions' specialization advice for external review (e.g. Perplexity)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ic_gamedata.specialization_engine import HERO_HANDLERS
from ic_gamedata.specialization_models import SpecializationOption
from ic_gamedata.specialization_rules.loader import cached_documentation_rules
from ic_gamedata.specialization_rules.route_mapper import (
    clear_route_override_cache,
    map_label_to_upgrade_id,
)
from ic_gamedata.specializations import load_specialization_rules


def _gaarawarr_entry(role_advice: dict, hero_id: int) -> tuple[list[str], list[int], str]:
    entry = role_advice.get(str(hero_id)) or {}
    roles = entry.get("roles") or {}
    url = str(entry.get("source_url") or "")
    for role_key in ("support", "buffer", "dps", "tank", "healer", "flex"):
        role = roles.get(role_key)
        if isinstance(role, dict) and role.get("specializations"):
            specs = [str(x) for x in role.get("specializations") or []]
            ids = [int(x) for x in role.get("specialization_ids") or []]
            return specs, ids, url
    for role in roles.values():
        if isinstance(role, dict) and role.get("specializations"):
            specs = [str(x) for x in role.get("specializations") or []]
            ids = [int(x) for x in role.get("specialization_ids") or []]
            return specs, ids, url
    return [], [], url


def _option_names(cfg: dict) -> list[str]:
    return [str(o.get("name") or "") for o in (cfg.get("options") or [])]


def _tier_count(cfg: dict) -> int:
    tiers = {
        int(o.get("tier_index") or 0)
        for o in (cfg.get("options") or [])
        if isinstance(o, dict)
    }
    return len(tiers)


def _classify_risk(
    hero_id: int,
    cfg: dict,
    *,
    csv_label: str,
    csv_advice: str,
    mapped_name: str | None,
) -> list[str]:
    """Return risk tags used for stratified sampling."""
    tags: list[str] = []
    names = " | ".join(_option_names(cfg)).casefold()
    advice = (csv_advice or "").casefold()
    label = (csv_label or "").casefold()
    if hero_id in HERO_HANDLERS:
        tags.append("dynamic_handler")
    if _tier_count(cfg) >= 2:
        tags.append("multi_tier")
    if any(k in names for k in ("gold", "rich", "fortune", "piracy", "favor", "luck", "business")) or any(
        k in advice for k in ("gold", "farm", "favor")
    ):
        tags.append("farm_gold")
    if any(k in names for k in ("bond:", "favored enemy", "species", "formation")) or any(
        k in advice for k in ("formation", "bond", "enemy-type", "enemy type", "zone")
    ):
        tags.append("formation_or_adventure")
    if mapped_name is None and label and any(k in label for k in ("route", "etc", "/", "piracy")):
        tags.append("unmapped_label")
    if hero_id >= 140:
        tags.append("recent")
    if not tags:
        tags.append("baseline")
    return tags


def _pack_hero(
    hero_id: int,
    cfg: dict,
    *,
    role_advice: dict,
    rules_by_champ: dict,
    sample_reason: str | None = None,
) -> dict:
    name = str(cfg.get("name") or f"Hero {hero_id}")
    options_raw = cfg.get("options") or []
    id_to_name = {int(o["upgrade_id"]): str(o.get("name") or "") for o in options_raw}
    defaults = [int(x) for x in (cfg.get("default") or [])]
    tiers: dict[str, list[dict]] = {}
    for opt in options_raw:
        tier = str(int(opt.get("tier_index") or 0))
        tiers.setdefault(tier, []).append(
            {
                "upgrade_id": int(opt["upgrade_id"]),
                "name": opt.get("name"),
                "required_level": opt.get("required_level"),
            }
        )
    ga_specs, ga_ids, ga_url = _gaarawarr_entry(role_advice, hero_id)
    csv_rule = rules_by_champ.get(name.casefold())
    csv_label = ""
    csv_alt = ""
    csv_advice = ""
    mapped_name = None
    if csv_rule:
        csv_label = csv_rule.default_label or csv_rule.machine_default or ""
        csv_alt = csv_rule.alternative_label or csv_rule.machine_alternative or ""
        csv_advice = csv_rule.advice_pattern or ""
        opts = [
            SpecializationOption(
                int(o["upgrade_id"]),
                str(o.get("name") or ""),
                int(o.get("required_level") or 0),
                int(o.get("tier_index") or 0),
            )
            for o in options_raw
        ]
        mapped = (
            map_label_to_upgrade_id(str(csv_label), opts, champion_name=name)
            if csv_label
            else None
        )
        mapped_name = id_to_name.get(mapped) if mapped else None

    our_advice = [f"{id_to_name.get(d, '?')} ({d})" for d in defaults]
    risk_tags = _classify_risk(
        hero_id,
        cfg,
        csv_label=csv_label,
        csv_advice=csv_advice,
        mapped_name=mapped_name,
    )
    item = {
        "hero_id": hero_id,
        "name": name,
        "has_dynamic_handler": hero_id in HERO_HANDLERS,
        "sample_reason": sample_reason or ", ".join(risk_tags),
        "risk_tags": risk_tags,
        "our_default_advice": our_advice,
        "gaarawarr_specializations": ga_specs,
        "gaarawarr_ids": ga_ids,
        "gaarawarr_url": ga_url,
        "csv_default_label": csv_label,
        "csv_alternative_label": csv_alt,
        "csv_advice_text": csv_advice,
        "csv_label_maps_to": mapped_name,
        "options_by_tier": dict(sorted(tiers.items(), key=lambda kv: int(kv[0]))),
    }
    return item


def build_pack(limit: int = 10, offset: int = 0) -> list[dict]:
    rules = load_specialization_rules()
    role_advice = json.loads(
        (ROOT / "config" / "champion_role_advice.json").read_text(encoding="utf-8")
    ).get("heroes", {})
    clear_route_override_cache()
    dataset = cached_documentation_rules()
    rules_by_champ = {r.champion.casefold(): r for r in dataset.rules}

    heroes = sorted(
        ((int(hid), cfg) for hid, cfg in (rules.get("heroes") or {}).items() if str(hid).isdigit()),
        key=lambda item: item[0],
    )
    selected = heroes[offset : offset + limit]
    return [
        _pack_hero(hero_id, cfg, role_advice=role_advice, rules_by_champ=rules_by_champ)
        for hero_id, cfg in selected
    ]


def build_risk_sample(
    limit: int = 20,
    *,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """Stratified sample across risk tags; deterministic pick order within each bucket."""
    exclude_ids = exclude_ids or set()
    rules = load_specialization_rules()
    role_advice = json.loads(
        (ROOT / "config" / "champion_role_advice.json").read_text(encoding="utf-8")
    ).get("heroes", {})
    clear_route_override_cache()
    dataset = cached_documentation_rules()
    rules_by_champ = {r.champion.casefold(): r for r in dataset.rules}

    buckets: dict[str, list[tuple[int, dict, list[str]]]] = {
        "dynamic_handler": [],
        "farm_gold": [],
        "formation_or_adventure": [],
        "multi_tier": [],
        "unmapped_label": [],
        "recent": [],
        "baseline": [],
    }
    for hid, cfg in (rules.get("heroes") or {}).items():
        if not str(hid).isdigit():
            continue
        hero_id = int(hid)
        if hero_id in exclude_ids:
            continue
        name = str(cfg.get("name") or "")
        csv_rule = rules_by_champ.get(name.casefold())
        csv_label = ""
        csv_advice = ""
        mapped_name = None
        if csv_rule:
            csv_label = csv_rule.default_label or csv_rule.machine_default or ""
            csv_advice = csv_rule.advice_pattern or ""
            options_raw = cfg.get("options") or []
            id_to_name = {int(o["upgrade_id"]): str(o.get("name") or "") for o in options_raw}
            opts = [
                SpecializationOption(
                    int(o["upgrade_id"]),
                    str(o.get("name") or ""),
                    int(o.get("required_level") or 0),
                    int(o.get("tier_index") or 0),
                )
                for o in options_raw
            ]
            mapped = (
                map_label_to_upgrade_id(str(csv_label), opts, champion_name=name)
                if csv_label
                else None
            )
            mapped_name = id_to_name.get(mapped) if mapped else None
        tags = _classify_risk(
            hero_id,
            cfg,
            csv_label=csv_label,
            csv_advice=csv_advice,
            mapped_name=mapped_name,
        )
        # Primary bucket = first matching priority tag
        primary = next((t for t in buckets if t in tags), "baseline")
        buckets[primary].append((hero_id, cfg, tags))

    for key in buckets:
        buckets[key].sort(key=lambda item: item[0])

    # Target mix for 20: handlers, farm, formation/adventure, multi-tier, unmapped, recent fillers
    quotas = {
        "dynamic_handler": 5,
        "farm_gold": 4,
        "formation_or_adventure": 4,
        "multi_tier": 3,
        "unmapped_label": 2,
        "recent": 2,
        "baseline": 0,
    }
    picked: list[tuple[int, dict, list[str], str]] = []
    seen: set[int] = set()

    def _take(bucket: str, n: int) -> None:
        for hero_id, cfg, tags in buckets.get(bucket, []):
            if len([p for p in picked if p[3] == bucket]) >= n:
                break
            if hero_id in seen:
                continue
            seen.add(hero_id)
            picked.append((hero_id, cfg, tags, bucket))

    for bucket, n in quotas.items():
        _take(bucket, n)

    # Fill remaining from leftover high-value buckets then any
    fill_order = [
        "dynamic_handler",
        "formation_or_adventure",
        "farm_gold",
        "multi_tier",
        "unmapped_label",
        "recent",
        "baseline",
    ]
    while len(picked) < limit:
        progressed = False
        for bucket in fill_order:
            for hero_id, cfg, tags in buckets.get(bucket, []):
                if hero_id in seen:
                    continue
                seen.add(hero_id)
                picked.append((hero_id, cfg, tags, f"fill:{bucket}"))
                progressed = True
                break
            if len(picked) >= limit:
                break
        if not progressed:
            break

    picked = picked[:limit]
    picked.sort(key=lambda item: item[0])
    return [
        _pack_hero(
            hero_id,
            cfg,
            role_advice=role_advice,
            rules_by_champ=rules_by_champ,
            sample_reason=f"risk sample primary={primary}; tags={', '.join(tags)}",
        )
        for hero_id, cfg, tags, primary in picked
    ]

def to_perplexity_markdown(pack: list[dict]) -> str:
    lines = [
        "# Idle Champions specialization advice review (risk sample)",
        "",
        "This batch is a stratified sample (handlers, farm/gold, formation/adventure,",
        "multi-tier, unmapped labels, recent champs) — not sequential IDs.",
        "",
        "Please review each champion below. For each one, answer:",
        "1. Is there a safe universal default, or should safe_default be null?",
        "2. Split push vs farm vs formation/adventure conditionals if needed.",
        "3. Any wrong option names, unmapped UI labels, or missing situational rules?",
        "",
    ]
    for i, item in enumerate(pack, start=1):
        lines.append(f"## {i}. {item['name']} (hero_id={item['hero_id']})")
        lines.append("")
        if item.get("sample_reason"):
            lines.append(f"- **Sample reason:** {item['sample_reason']}")
        if item.get("risk_tags"):
            lines.append(f"- **Risk tags:** {', '.join(item['risk_tags'])}")
        lines.append(f"- **Our default advice:** {', '.join(item['our_default_advice']) or '(none)'}")
        lines.append(
            f"- **Gaarawarr guide specs:** {', '.join(item['gaarawarr_specializations']) or '(none)'}"
        )
        if item["gaarawarr_url"]:
            lines.append(f"- **Guide URL:** {item['gaarawarr_url']}")
        lines.append(f"- **Dynamic formation handler:** {'yes' if item['has_dynamic_handler'] else 'no'}")
        if item["csv_default_label"]:
            lines.append(
                f"- **CSV rule label:** {item['csv_default_label']}"
                + (f" / alt: {item['csv_alternative_label']}" if item["csv_alternative_label"] else "")
            )
            lines.append(f"- **CSV label maps to:** {item['csv_label_maps_to'] or '(unmapped)'}")
            if item["csv_advice_text"]:
                lines.append(f"- **CSV advice text:** {item['csv_advice_text']}")
        lines.append("- **Available options:**")
        for tier, opts in item["options_by_tier"].items():
            joined = "; ".join(f"{o['name']} [{o['upgrade_id']}] @L{o['required_level']}" for o in opts)
            lines.append(f"  - tier {tier}: {joined}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--mode",
        choices=("sequential", "risk"),
        default="sequential",
        help="sequential=offset/limit by hero_id; risk=stratified sample",
    )
    parser.add_argument(
        "--exclude-batch1",
        action="store_true",
        help="With --mode risk, exclude hero_id 1-10 from batch 01",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "documentation" / "spec_advice_review_batch_01.md",
    )
    args = parser.parse_args()
    if args.mode == "risk":
        exclude = set(range(1, 11)) if args.exclude_batch1 else set()
        pack = build_risk_sample(limit=args.limit, exclude_ids=exclude)
    else:
        pack = build_pack(limit=args.limit, offset=args.offset)
    md = to_perplexity_markdown(pack)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    json_path = args.out.with_suffix(".json")
    json_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    # Compact roster to stderr for quick scan
    print("Sample roster:", file=sys.stderr)
    for item in pack:
        print(
            f"  {item['hero_id']:3} {item['name']:<22} {item.get('sample_reason', '')}",
            file=sys.stderr,
        )
    # Avoid Windows console encoding issues on option names.
    try:
        print(md)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(md.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    print(f"\nWrote {args.out}", file=sys.stderr)
    print(f"Wrote {json_path}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
