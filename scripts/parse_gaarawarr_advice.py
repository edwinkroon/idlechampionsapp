"""Parse downloaded Gaarawarr guides into role-based champion advice."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "data" / "gaarawarr_guides"
CHAMPIONS = ROOT / "config" / "champions.json"
SPECS = ROOT / "config" / "specializations.json"
OUT = ROOT / "config" / "champion_role_advice.json"

ROLE_ALIASES = {
    "dps": "bud",
    "carry": "bud",
    "bud": "bud",
    "pushing": "support",
    "push": "support",
    "buffer": "buffer",
    "debuffer": "debuffer",
    "tank": "tank",
    "healer": "healer",
    "support": "support",
    "gold": "gold",
    "speed": "speed",
    "farming": "speed",
    "flex": "flex",
}

# Feat recommendation tags -> seat roles that should see them.
FEAT_TAG_TO_ROLES = {
    "dps": ("bud", "flex"),
    "pushing": ("tank", "buffer", "debuffer", "support", "healer", "flex"),
    "gold": ("gold",),
    "speed": ("speed",),
    "farming": ("speed",),
}


def _norm_name(value: str) -> str:
    text = value.lower().strip()
    text = text.replace("’", "'").replace("`", "'")
    # Fold accented characters roughly for names like Môrgæn
    repl = {
        "ô": "o",
        "ö": "o",
        "æ": "ae",
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ý": "y",
        "�": "",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9' +.-]+", "", text)
    return text


def _fuzzy_hero_id(name: str, by_name: dict[str, int]) -> int | None:
    key = _norm_name(name)
    if key in by_name:
        return by_name[key]
    stripped = re.sub(r"^(the|brother|commodore|sir|archdruid|grand duke)\s+", "", key)
    if stripped in by_name:
        return by_name[stripped]
    first = stripped.split()[0] if stripped.split() else ""
    if first and first in by_name:
        return by_name[first]
    compact = re.sub(r"[^a-z0-9]+", "", key)
    for cand, hid in by_name.items():
        if re.sub(r"[^a-z0-9]+", "", cand) == compact:
            return hid
    for cand, hid in by_name.items():
        c = re.sub(r"[^a-z0-9]+", "", cand)
        if compact and c and (compact.startswith(c) or c.startswith(compact)):
            if abs(len(compact) - len(c)) <= 4:
                return hid
    return None


def _champion_name_from_title(title: str) -> str | None:
    text = title or ""
    patterns = (
        r"champion guide\s*[:\-–]\s*(.+)$",
        r"year\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine)\s+"
        r"(?:event\s+)?champion(?:\s+guide)?\s*[:\-–]\s*(.+)$",
        r"evergreen\s+champion(?:\s+guide)?\s*[:\-–]\s*(.+)$",
        r"core\s+champion(?:\s+guide)?\s*[:\-–]\s*(.+)$",
        r"psylisa'?s\s+guide\s+to\s+(.+?)(?:\s*[-–].*)?$",
        r"(?:lolligagers'?|underbuffed'?s?)\s+guide\s+to\s+(.+?)(?:\s*[-–].*)?$",
        r"champion\s+spotlight\s*[:\-–]?\s*(.+)$",
    )
    name = None
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            name = m.group(1).strip()
            break
    if not name:
        return None
    # "Rust on the Harbour, the Tabaxi Rogue" -> keep until comma race/class
    name = re.sub(
        r",\s*(?:the\s+)?[A-Za-z][A-Za-z'/\-]*(?:\s*[A-Za-z/][A-Za-z'/\-]*){0,8}\s*$",
        "",
        name,
    )
    name = re.sub(r"\s+on the Harbour$", "", name, flags=re.I)
    name = re.sub(r"\s+the\s+Pixie$", "", name, flags=re.I)
    name = re.sub(r"\s+Majere$", "", name, flags=re.I)
    name = re.sub(r"\s+Burrfoot$", "", name, flags=re.I)
    # "Duke Ravengard" -> Ravengard via fuzzy first-token / alias
    return name.strip(" -–")


def _load_hero_maps() -> tuple[dict[str, int], dict[int, str], dict[int, list[dict]]]:
    champs = json.loads(CHAMPIONS.read_text(encoding="utf-8"))
    by_name: dict[str, int] = {}
    by_id: dict[int, str] = {}
    for hid, cfg in champs.items():
        hero_id = int(hid)
        name = str(cfg.get("name") or "")
        by_id[hero_id] = name
        by_name[_norm_name(name)] = hero_id
        # aliases
        if name == "Black Viper":
            by_name[_norm_name("The Black Viper")] = hero_id
        if name == "Sgt. Knox":
            by_name[_norm_name("Sgt Knox")] = hero_id
            by_name[_norm_name("Sergeant Knox")] = hero_id
        if name == "King of Shadows":
            by_name[_norm_name("The King of Shadows")] = hero_id
        if name == "Certainty":
            by_name[_norm_name("Certainty Dran")] = hero_id
        if name == "Trixie":
            by_name[_norm_name("Trixie the Pixie")] = hero_id
        if name == "Raistlin":
            by_name[_norm_name("Raistlin Majere")] = hero_id
        if name == "Van Richten":
            by_name[_norm_name("Rudolph Van Richten")] = hero_id
        if name == "Dark Urge":
            by_name[_norm_name("The Dark Urge")] = hero_id
        if name == "Krux":
            by_name[_norm_name("Commodore Krux")] = hero_id
        if name == "Uriah":
            by_name[_norm_name("Brother Uriah")] = hero_id
        if name == "Morgaen":
            by_name["morgn"] = hero_id
            by_name["mrgn"] = hero_id
            by_name[_norm_name("Morgaen")] = hero_id
        if name == "Warden":
            by_name[_norm_name("The Warden")] = hero_id
        if name == "Beadle":
            by_name[_norm_name("Beadle & Grimm")] = hero_id
            by_name[_norm_name("Beadle and Grimm")] = hero_id
        if name == "Dungeon Master":
            by_name[_norm_name("The Dungeon Master")] = hero_id
        if name == "Catti-brie":
            by_name[_norm_name("Catti brie")] = hero_id
        if name == "Donaar":
            by_name[_norm_name("Donaar Blit'zen")] = hero_id
        if name == "Deekin":
            by_name[_norm_name("Deekin Scalesinger")] = hero_id
        if name == "Jarlaxle":
            by_name[_norm_name("Jarlaxle Baenre")] = hero_id
        if name == "Jim":
            by_name[_norm_name("Jim Darkmagic")] = hero_id
        if name == "Walnut":
            by_name[_norm_name("Walnut Dankgrass")] = hero_id
        if name == "Rosie":
            by_name[_norm_name("Rosie Beestinger")] = hero_id
        if name == "Omin":
            by_name[_norm_name("Omin Dran")] = hero_id
        if name == "Pwent":
            by_name[_norm_name("Thibbledorf Pwent")] = hero_id
        if name == "Artemis":
            by_name[_norm_name("Artemis Entreri")] = hero_id
        if name == "Volo":
            by_name[_norm_name("Volothamp Geddarm")] = hero_id
            by_name[_norm_name("Volothamp")] = hero_id
        if name == "Kas":
            by_name[_norm_name("Kas the Bloody-Handed")] = hero_id
            by_name[_norm_name("Kas the Bloody Handed")] = hero_id
        if name == "Corazon":
            by_name[_norm_name("Corazón")] = hero_id
            by_name[_norm_name("Corazon de Ballestero")] = hero_id
            by_name[_norm_name("Coraz")] = hero_id
        if name == "Rust":
            by_name[_norm_name("Rust on the Harbour")] = hero_id
        if name == "Ravengard":
            by_name[_norm_name("Duke Ravengard")] = hero_id
            by_name[_norm_name("Ulder Ravengard")] = hero_id
        if name == "Tasslehoff":
            by_name[_norm_name("Tasslehoff Burrfoot")] = hero_id
            by_name[_norm_name("Tass")] = hero_id
        if name == "Ezmerelda":
            by_name[_norm_name("Ezmerelda d'Avenir")] = hero_id
        if name == "Binwin":
            by_name[_norm_name("Binwin Bronzebottom")] = hero_id
        if name == "Bruenor":
            by_name[_norm_name("Bruenor Battlehammer")] = hero_id
        if name == "Viconia":
            by_name[_norm_name("Viconia DeVir")] = hero_id
        if name == "Astarion":
            by_name[_norm_name("Astarion Ancunin")] = hero_id
        if name == "Karlach":
            by_name[_norm_name("Karlach Cliffgate")] = hero_id
        if name == "Wyll":
            by_name[_norm_name("Wyll Ravengard")] = hero_id
        if name == "Gale":
            by_name[_norm_name("Gale of Waterdeep")] = hero_id
        if name == "Minthara":
            by_name[_norm_name("Minthara Baenre")] = hero_id
        if name == "Lae'zel":
            by_name[_norm_name("Laezel")] = hero_id
        if name == "BBEG":
            by_name[_norm_name("The BBEG")] = hero_id
        if name == "NERDS":
            by_name[_norm_name("The NERDS")] = hero_id
        if name == "Strongheart":
            by_name[_norm_name("Sir Strongheart")] = hero_id
        if name == "Eric":
            by_name[_norm_name("Eric the Cavalier")] = hero_id
        if name == "Hank":
            by_name[_norm_name("Hank the Ranger")] = hero_id
        if name == "Diana":
            by_name[_norm_name("Diana the Acrobat")] = hero_id
        if name == "Presto":
            by_name[_norm_name("Presto the Magician")] = hero_id
        if name == "Bobby":
            by_name[_norm_name("Bobby the Barbarian")] = hero_id
        if name == "Sheila":
            by_name[_norm_name("Sheila the Thief")] = hero_id
        if name == "K'thriss":
            by_name[_norm_name("Kthriss")] = hero_id
        if name == "Hew Maan":
            by_name[_norm_name("Hew Maan")] = hero_id
            by_name[_norm_name("Hewmaan")] = hero_id
        if name == "D'hani":
            by_name[_norm_name("Dhani")] = hero_id
        if name == "Sgt. Knox":
            by_name[_norm_name("Sergeant Knox")] = hero_id
            by_name[_norm_name("Sgt Knox")] = hero_id
        if name == "Black Viper":
            by_name[_norm_name("The Black Viper")] = hero_id
        if name == "King of Shadows":
            by_name[_norm_name("The King of Shadows")] = hero_id
        if name == "Certainty":
            by_name[_norm_name("Certainty Dran")] = hero_id
        if name == "Trixie":
            by_name[_norm_name("Trixie the Pixie")] = hero_id
        if name == "Raistlin":
            by_name[_norm_name("Raistlin Majere")] = hero_id
        if name == "Van Richten":
            by_name[_norm_name("Rudolph Van Richten")] = hero_id
        if name == "Fen":
            by_name[_norm_name("Fen the Dhampir")] = hero_id
        if name == "Vi":
            by_name[_norm_name("Vi the Tabaxi")] = hero_id

    specs_root = json.loads(SPECS.read_text(encoding="utf-8"))
    options_by_hero: dict[int, list[dict]] = {}
    for hid, cfg in (specs_root.get("heroes") or {}).items():
        hero_id = int(hid)
        options_by_hero[hero_id] = list(cfg.get("options") or [])
    return by_name, by_id, options_by_hero


def _extract_section(body: str, headings: tuple[str, ...]) -> str:
    parts: list[str] = []
    for heading in headings:
        pattern = (
            rf"(?is)(?:^|\n)(?:\#{{1,3}}\s*)?(?:\*\*)?{re.escape(heading)}(?:\*\*)?\s*\n"
            rf"(.*?)(?=\n(?:\#{{1,3}}\s+|\*\*[A-Z][^*]{{2,80}}\*\*\s*\n)|$)"
        )
        for match in re.finditer(pattern, body):
            parts.append(match.group(0))
    return "\n".join(parts)


def _preferred_spec_names(spec_section: str, option_names: list[str], body: str = "") -> list[str]:
    if not option_names:
        return []
    preferred: list[str] = []
    haystacks = [spec_section, body]

    # Explicit "Personally, I think 'X' is the way to go"
    for text in haystacks:
        for match in re.finditer(
            r"(?i)(?:personally,? i think|i think|go with|pick|choose|this tends to be|default to)\s+['\"]([^'\"]+)['\"]",
            text,
        ):
            name = match.group(1).strip()
            for opt in option_names:
                if _norm_name(name) in _norm_name(opt) or _norm_name(opt) in _norm_name(name):
                    if opt not in preferred:
                        preferred.append(opt)

    # Gaar notes near option blocks
    scored: list[tuple[int, str]] = []
    for text in haystacks:
        blocks = re.split(r"(?m)^\*\*", text)
        for block in blocks:
            header = block.split(":**", 1)[0].split("**", 1)[0].strip()
            if not header or len(header) > 90:
                continue
            matched = None
            for opt in option_names:
                if _norm_name(header) == _norm_name(opt) or _norm_name(header) in _norm_name(opt):
                    matched = opt
                    break
            if matched is None:
                continue
            note = ""
            mnote = re.search(r"(?is)Gaar'?s Note:(.*?)(?:\n\n|$)", block)
            if mnote:
                note = mnote.group(1).lower()
            score = 1  # mentioned at all
            if any(
                p in note
                for p in (
                    "way to go",
                    "tends to be",
                    "default",
                    "most situations",
                    "best choice",
                    "should be the",
                    "this is the spec",
                )
            ):
                score += 5
            if "unfortunately" in note or "lower buff" in note or "situational" in note:
                score -= 3
            scored.append((score, matched))
    scored.sort(key=lambda item: (-item[0], item[1]))
    # Keep only strongly preferred notes; otherwise first mentioned option.
    strong = [name for score, name in scored if score >= 5]
    if strong:
        for name in strong:
            if name not in preferred:
                preferred.append(name)
    elif scored and not preferred:
        preferred.append(scored[0][1])

    # Any option name mentioned near specialization wording
    if not preferred:
        for opt in option_names:
            if re.search(rf"\*\*{re.escape(opt)}\s*:", body, re.I) or re.search(
                rf"\*\*{re.escape(opt)}\s*:", spec_section, re.I
            ):
                preferred.append(opt)
                break
    return preferred[:3]


def _parse_feat_rows(feat_section: str) -> list[dict]:
    rows: list[dict] = []
    # Modern table rows: | Obtained | Recommended | Name | Effect |
    for line in feat_section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        if len(cols) < 4:
            continue
        obtained, recommended, name, effect = cols[0], cols[1], cols[2], cols[3]
        if name.lower() in {"name", ":------------:", ":-:"} or "---" in name:
            continue
        if not name or name.lower() == "obtained":
            continue
        tags = []
        for token in re.split(r"[/,; ]+", recommended):
            token = token.strip().lower()
            if token and token not in {"-", ""}:
                tags.append(token)
        rows.append(
            {
                "name": name,
                "effect": effect,
                "obtained": obtained,
                "recommended_tags": tags,
            }
        )

    # Older style: **Chest:** Elementalist - Increases...
    if not rows:
        for match in re.finditer(
            r"(?m)^\*\*(?:Default|Chest|12,500 Gems|50,000 Gems\*?)(?:[^:]*):\*\*\s*(.+?)\s*[-–—]\s*(.+)$",
            feat_section,
        ):
            rows.append(
                {
                    "name": match.group(1).strip(),
                    "effect": match.group(2).strip(),
                    "obtained": "",
                    "recommended_tags": [],
                }
            )

    # Psylisa / short style: **Cautionary Tale:** 40% Pirate's Code
    if not rows:
        prefer_40 = bool(re.search(r"(?i)pick the two\s+40%\s+feats", feat_section))
        for match in re.finditer(
            r"(?m)^\*\*([^*]+):\*\*\s*([^\n]+)$",
            feat_section,
        ):
            name = match.group(1).strip()
            effect = match.group(2).strip()
            if name.lower() in {"selflessness", "worldliness"} and "10%" in effect:
                tags: list[str] = []
            else:
                tags = []
            if prefer_40 and "40%" in effect:
                tags = ["pushing", "dps"]
            rows.append(
                {
                    "name": name,
                    "effect": effect,
                    "obtained": "",
                    "recommended_tags": tags,
                }
            )
        if prefer_40:
            rows = [r for r in rows if "40%" in r["effect"]] or rows
    return rows


def _feats_for_roles(feat_rows: list[dict]) -> dict[str, list[str]]:
    by_role: dict[str, list[str]] = defaultdict(list)
    pushing_names = [r["name"] for r in feat_rows if "pushing" in r["recommended_tags"]]
    dps_names = [r["name"] for r in feat_rows if "dps" in r["recommended_tags"]]
    gold_names = [r["name"] for r in feat_rows if "gold" in r["recommended_tags"]]
    speed_names = [
        r["name"]
        for r in feat_rows
        if "speed" in r["recommended_tags"] or "farming" in r["recommended_tags"]
    ]

    # If no explicit tags, pick strongest-looking damage/global feats as support defaults.
    if not any((pushing_names, dps_names, gold_names, speed_names)):
        fallback = [r["name"] for r in feat_rows[:4]]
        for role in ("support", "buffer", "tank", "healer", "debuffer", "flex", "bud"):
            by_role[role] = fallback
        return dict(by_role)

    for role in ("support", "buffer", "tank", "healer", "debuffer", "flex"):
        by_role[role] = pushing_names or [r["name"] for r in feat_rows if r["recommended_tags"]][:4]
    by_role["bud"] = dps_names or pushing_names
    by_role["gold"] = gold_names or pushing_names
    by_role["speed"] = speed_names
    return {role: names[:6] for role, names in by_role.items() if names}


def _formation_blurb(body: str) -> str:
    section = _extract_section(
        body,
        (
            "Formation & Mission Information",
            "Formation Information",
            "New Player Formation & Specializations",
        ),
    )
    # Keep first Gaar note or first meaningful paragraph.
    note = re.search(r"(?is)Gaar'?s Note:\s*(.+?)(?:\n\n|&nbsp;|$)", section)
    if note:
        text = re.sub(r"\s+", " ", note.group(1)).strip()
        return text[:280]
    # Placement cues from interesting abilities
    interesting = _extract_section(body, ("Interesting Abilities", "Basic Abilities"))
    for match in re.finditer(r"(?is)Gaar'?s Note:\s*(.+?)(?:\n\n|&nbsp;|$)", interesting):
        text = re.sub(r"\s+", " ", match.group(1)).strip()
        if any(k in text.lower() for k in ("column", "front", "back", "adjacent", "tank", "place")):
            return text[:280]
    # Psylisa placement cue
    swap = re.search(
        r"(?i)when you want to add (?:him|her|them) to your formation you can swap (?:him|her|them) with ([^.]+)\.",
        body,
    )
    if swap:
        return f"Swap with {swap.group(1).strip()}."[:280]
    return ""


def _resolve_spec_ids(preferred_names: list[str], options: list[dict]) -> list[int]:
    ids: list[int] = []
    by_tier: dict[int, list[dict]] = defaultdict(list)
    for opt in options:
        by_tier[int(opt.get("tier_index") or 0)].append(opt)

    used_tiers: set[int] = set()
    for name in preferred_names:
        for opt in options:
            opt_name = str(opt.get("name") or "")
            if _norm_name(name) == _norm_name(opt_name) or _norm_name(name) in _norm_name(opt_name):
                tier = int(opt.get("tier_index") or 0)
                if tier in used_tiers:
                    continue
                ids.append(int(opt["upgrade_id"]))
                used_tiers.add(tier)
                break

    # Fill missing tiers with first option (stable) only if we found at least one preferred.
    if ids:
        for tier, opts in sorted(by_tier.items()):
            if tier in used_tiers:
                continue
            # leave unfilled; role advice shouldn't invent tiers
            pass
    return ids


def _guide_quality_score(parsed: dict, post: dict) -> tuple:
    """Prefer real champion guides over spotlights / stubs; then newer date."""
    title = (parsed.get("guide_title") or post.get("title") or "").lower()
    body = post.get("selftext") or ""
    author = str(post.get("author") or "").lower()
    score = 0
    if "champion guide" in title or re.search(r"year\s+.+\s+champion", title):
        score += 50
    if "psylisa" in title or "guide to" in title:
        score += 40
    if "spotlight" in title or title.startswith("new champion") or "introducing" in title:
        score -= 30
    if "rework" in title:
        score += 10
    if "gaar" in author:
        score += 15
    if "psylisa" in author:
        score += 12
    # Real guide bodies are long; stubs like Volo's joke post score poorly.
    blen = len(body)
    if blen >= 8000:
        score += 25
    elif blen >= 3000:
        score += 15
    elif blen >= 800:
        score += 8
    elif blen < 200:
        score -= 40
    if "gaar's note" in body.lower() or "gaars note" in body.lower():
        score += 20
    roles = parsed.get("roles") or {}
    has_specs = any((r.get("specializations") or []) for r in roles.values())
    has_feats = any((r.get("feats") or []) for r in roles.values())
    if has_specs:
        score += 10
    if has_feats:
        score += 8
    date = parsed.get("source_date") or ""
    return (score, date)


def parse_guide(post: dict, by_name: dict[str, int], options_by_hero: dict[int, list[dict]]) -> dict | None:
    title = str(post.get("title") or "")
    champ_name = _champion_name_from_title(title)
    if not champ_name:
        return None
    hero_id = _fuzzy_hero_id(champ_name, by_name)
    if hero_id is None:
        return {"unmatched": champ_name, "title": title, "id": post.get("id")}

    body = post.get("selftext") or ""
    options = options_by_hero.get(hero_id, [])
    option_names = [str(o.get("name") or "") for o in options]
    spec_section = _extract_section(
        body,
        (
            "First Specialization Choice",
            "Second Specialization Choice",
            "Third Specialization Choice",
            "Specializations",
            "Specialization",
        ),
    )
    feat_section = _extract_section(body, ("Feats", "Feat"))
    preferred = _preferred_spec_names(spec_section, option_names, body=body)
    spec_ids = _resolve_spec_ids(preferred, options)
    feat_rows = _parse_feat_rows(feat_section)
    feats_by_role = _feats_for_roles(feat_rows)
    formation = _formation_blurb(body)
    created = int(post.get("created_utc") or 0)
    source_date = (
        datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat() if created else None
    )
    author = str(post.get("author") or "") or "community"
    if author.lower() in {"[deleted]", "none"}:
        source_name = "community"
    elif "gaar" in author.lower():
        source_name = "Gaarawarr"
    elif "psylisa" in author.lower():
        source_name = "Psylisa"
    else:
        source_name = author

    roles: dict[str, dict] = {}
    # Specs: one best set; apply to all roles unless DPS-named options exist.
    base_role_entry = {
        "specializations": preferred,
        "specialization_ids": spec_ids,
        "formation": formation,
        "feats": [],
    }
    for role, feats in feats_by_role.items():
        entry = dict(base_role_entry)
        entry["feats"] = feats
        roles[role] = entry
    if not roles:
        roles["support"] = {
            **base_role_entry,
            "feats": [r["name"] for r in feat_rows[:4]],
        }

    return {
        "hero_id": hero_id,
        "name": champ_name,
        "source": source_name,
        "source_url": f"https://www.reddit.com{(post.get('permalink') or '')}",
        "source_date": source_date,
        "guide_id": post.get("id"),
        "guide_title": title,
        "roles": roles,
        "all_feats": feat_rows,
        "_post": post,
        "_body_len": len(body),
        "_is_stub": len(body) < 200 or "actual guide coming soon" in body.lower(),
    }


def main() -> None:
    by_name, by_id, options_by_hero = _load_hero_maps()
    index = json.loads((GUIDES / "index.json").read_text(encoding="utf-8"))

    # Keep best guide per champion (quality first, then newest).
    newest_by_hero: dict[int, dict] = {}
    unmatched: list[dict] = []
    for row in index:
        path = GUIDES / f"{row['id']}.json"
        if not path.exists():
            continue
        post = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_guide(post, by_name, options_by_hero)
        if parsed is None:
            continue
        if "unmatched" in parsed:
            unmatched.append(parsed)
            continue
        hero_id = int(parsed["hero_id"])
        parsed["name"] = by_id.get(hero_id, parsed.get("name"))
        prev = newest_by_hero.get(hero_id)
        if prev is None or _guide_quality_score(parsed, post) > _guide_quality_score(
            prev, prev.get("_post") or {}
        ):
            newest_by_hero[hero_id] = parsed

    champions_out: dict[str, dict] = {}
    specs_root = json.loads(SPECS.read_text(encoding="utf-8"))
    for hero_id, parsed in sorted(newest_by_hero.items()):
        parsed.pop("_post", None)
        is_stub = bool(parsed.pop("_is_stub", False))
        parsed.pop("_body_len", None)
        roles = parsed["roles"]
        # Fill empty specialization lists from specializations.json defaults.
        hero_spec = (specs_root.get("heroes") or {}).get(str(hero_id)) or {}
        default_ids = [int(x) for x in (hero_spec.get("default") or [])]
        default_names = []
        for uid in default_ids:
            for opt in hero_spec.get("options") or []:
                if int(opt.get("upgrade_id") or -1) == uid:
                    default_names.append(str(opt.get("name") or uid))
                    break
        for role_key, block in list(roles.items()):
            if not block.get("specialization_ids") and default_ids:
                block["specialization_ids"] = default_ids
                block["specializations"] = default_names
            roles[role_key] = block
        source = parsed["source"]
        if is_stub:
            # Keep the Reddit link for reference, but make clear advice came from defaults.
            source = f"{source} stub + specializations.json"
        champions_out[str(hero_id)] = {
            "name": by_id.get(hero_id, parsed.get("name")),
            "source": source,
            "source_url": parsed["source_url"],
            "source_date": parsed["source_date"],
            "guide_id": parsed["guide_id"],
            "guide_title": parsed["guide_title"],
            "roles": roles,
        }

    payload = {
        "version": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": "Arctic Shift + community r/idlechampions guides",
        "champions": champions_out,
        "unmatched_guides": unmatched,
        "coverage": {
            "guides_indexed": len(index),
            "champions_matched": len(champions_out),
            "champions_total": len(by_id),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"wrote {OUT} matched={len(champions_out)}/{len(by_id)} unmatched={len(unmatched)}"
    )
    for item in unmatched[:20]:
        print(" unmatched:", item.get("unmatched"), "|", item.get("title"))


if __name__ == "__main__":
    main()
