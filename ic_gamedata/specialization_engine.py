"""Formation-aware specialization choice engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ic_gamedata.loot_stats import HeroLootStats, formation_loot_stack_totals
from ic_gamedata.specialization_custom_stacks import (
    acqinc_cteam_count,
    ceremorphosis_stack_count,
    champions_of_tymora_count,
    diana_inspire_match_count,
    diana_inspire_upgrade_id,
    dob_qualified_counts,
    grand_tour_base_adventures_completed,
    high_intelligence_count,
    omin_has_known_associates,
    shadowheart_duplicity_distance,
    unavailable_owned_hero_count,
    unique_species_count,
)
from ic_gamedata.specialization_data import (
    hero_ability_scores_map_from_cached_definitions,
    hero_attack_types_map_from_cached_definitions,
    hero_roles_map_from_champion_config,
    hero_tags_map_from_cached_definitions,
    hero_tags_map_from_champion_config,
    load_meta_static_defaults,
)
from ic_gamedata.specialization_models import SpecializationOption

# Patchable aliases for unit tests.
_hero_roles_map_from_champion_config = hero_roles_map_from_champion_config
_hero_tags_map_from_champion_config = hero_tags_map_from_champion_config
_hero_tags_map_from_cached_definitions = hero_tags_map_from_cached_definitions
_hero_attack_types_map_from_cached_definitions = hero_attack_types_map_from_cached_definitions
_hero_ability_scores_map_from_cached_definitions = hero_ability_scores_map_from_cached_definitions

@dataclass(frozen=True)
class FormationContext:
    active_hero_ids: set[int]
    highest_damage_hero_id: int | None = None
    familiar_count: int = 0
    seat_by_hero: dict[int, int] | None = None
    run_goal: str | None = None
    loot_by_hero: dict[int, HeroLootStats] | None = None
    account_stats: dict[str, Any] | None = None
    event_boon_count: int = 0
    modron_core_competency_stacks: int = 0
    owned_hero_ids: frozenset[int] | None = None
    hero_upgrade_ids: dict[int, frozenset[int]] | None = None


HeroHandler = Callable[[FormationContext], tuple[list[int], str] | None]

_WYLL_BLADE = 13433
_WYLL_CHAIN = 13434
_WYLL_TOME = 13435
_WYLL_FOLK_HERO_COVERAGE = 0.65

_TESS_FALLBACK = 17321
_TESS_RANGED = 17322
_TESS_ROGUE = 17323
# Matches effect_def pre_stack values in cached_definitions (150/200/250).
_TESS_PCT_FALLBACK = 150
_TESS_PCT_RANGED = 200
_TESS_PCT_ROGUE = 250

_KOS_ID = 168
_KOS_PAWNS = 17762
_KOS_UNLEASHED = 17763
_KOS_PAWNS_PCT = 400
_KOS_UNLEASHED_PCT = 1000
_KOS_LEGACY = 17764
_KOS_SHADOW_WEAVE = 17765
_KOS_RITES = 17766
_KOS_PCT_LEGACY = 100
_KOS_PCT_EVIL = 200
_KOS_PCT_HEALING = 300
_KOS_LEGACY_RACE_TAGS = frozenset({"elf", "dwarf", "half-elf", "human"})

_VLITHRYN_WHO_ELSE = 17048
_VLITHRYN_HELP = 17049
_VLITHRYN_SPREADING = 17050
_VLITHRYN_PCT_WHO_ELSE = 200
_VLITHRYN_PCT_HELP = 300
_VLITHRYN_PCT_SPREADING = 300
_VLITHRYN_SPECIES_TAGS = frozenset(
    {
        "aarakocra",
        "aasimar",
        "bullywug",
        "centaur",
        "changeling",
        "dhampir",
        "doppelganger",
        "dragonborn",
        "dwarf",
        "elf",
        "fairy",
        "firbolg",
        "genasi",
        "giff",
        "githyanki",
        "githzerai",
        "gnome",
        "goblin",
        "goliath",
        "half-elf",
        "half-orc",
        "halfling",
        "harengon",
        "human",
        "kalashtar",
        "kender",
        "kobold",
        "lizardfolk",
        "minotaur",
        "modron",
        "plasmoid",
        "satyr",
        "saurial",
        "tabaxi",
        "thri-kreen",
        "tiefling",
        "tortle",
        "triton",
        "warforged",
        "yuan-ti",
    }
)
_VLITHRYN_SPECIES_NORMALIZE = {
    "drow": "elf",
    "wildelf": "elf",
    "halfelf": "half-elf",
    "halforc": "half-orc",
    "yuanti": "yuan-ti",
}

_VOLO_ID = 159
_VOLO_SPIRITS = 16554
_VOLO_TADPOLES = 16555
_VOLO_MAGICAL = 16556
_VOLO_PCT = 100

_SKYLLA_WITCH_SWITCH = 17848
_SKYLLA_LEAGUE = 17849
_SKYLLA_WITHERING = 17850
_SKYLLA_GREEN_FIRE = 17851
_SKYLLA_SWAP_PAIRS = (("str", "cha"), ("dex", "int"), ("con", "wis"))
_VARIANT_RUN_GOALS = frozenset({"variant", "stat_restrictive", "stat_restricted"})


def _is_variant_run_goal(run_goal: str | None) -> bool:
    return (run_goal or "").casefold() in _VARIANT_RUN_GOALS


def _skylla_swap_pair_hits(scores: dict[str, int]) -> int:
    return sum(
        1
        for left, right in _SKYLLA_SWAP_PAIRS
        if abs(scores.get(left, 0) - scores.get(right, 0)) >= 5
    )


def _skylla_swap_metrics(active_hero_ids: set[int]) -> tuple[int, int]:
    """Return (total_swap_hits, champions_with_two_or_more_swap_pairs)."""
    scores_by_hero = _hero_ability_scores_map_from_cached_definitions()
    total_hits = strong_champions = 0
    for hid in active_hero_ids:
        hits = _skylla_swap_pair_hits(scores_by_hero.get(hid, {}))
        total_hits += hits
        if hits >= 2:
            strong_champions += 1
    return total_hits, strong_champions


def _skylla_witch_switch_thresholds(party_size: int) -> tuple[int, int]:
    """Return (min_strong_swap_champions, min_total_swap_hits)."""
    return max(3, party_size // 2), max(18, party_size * 3)


@dataclass(frozen=True)
class FormationMetrics:
    evil_count: int
    good_count: int
    companion_count: int
    debuff_count: int
    speed_count: int
    gold_count: int
    tank_count: int
    healer_count: int
    human_count: int
    dwarf_elf_count: int
    short_folk_count: int
    exotic_count: int
    swap_hits: int
    bg3_count: int
    small_friends_count: int
    fast_friends_count: int


_SMALL_FOLK_TAGS = frozenset(
    {"dwarf", "fairy", "gnome", "goblin", "halfling", "kender", "kobold", "plasmoid"}
)
_DWARF_ELF_TAGS = frozenset({"dwarf", "elf", "halfelf"})
_EXOTIC_TAGS = frozenset(
    {"tiefling", "dragonborn", "tabaxi", "gith", "githyanki", "firbolg", "orc", "plasmoid"}
)
_BG3_HERO_IDS = frozenset({128, 129, 141, 142, 147})
_AFFINITY_TAGS = frozenset({"acqinc", "cteam", "wafflecrew", "absoluteadversaries"})

EMPTY_FORMATION_METRICS = FormationMetrics(
    evil_count=0,
    good_count=0,
    companion_count=0,
    debuff_count=0,
    speed_count=0,
    gold_count=0,
    tank_count=0,
    healer_count=0,
    human_count=0,
    dwarf_elf_count=0,
    short_folk_count=0,
    exotic_count=0,
    swap_hits=0,
    bg3_count=0,
    small_friends_count=0,
    fast_friends_count=0,
)


def formation_metrics(active_hero_ids: set[int]) -> FormationMetrics:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    roles_by_hero = _hero_roles_map_from_champion_config()
    scores_by_hero = _hero_ability_scores_map_from_cached_definitions()

    evil_count = good_count = companion_count = debuff_count = 0
    speed_count = gold_count = tank_count = healer_count = 0
    human_count = dwarf_elf_count = short_folk_count = exotic_count = 0
    swap_hits = small_friends_count = fast_friends_count = 0
    bg3_count = sum(1 for hid in active_hero_ids if hid in _BG3_HERO_IDS)

    for hid in active_hero_ids:
        tags = set(tags_by_hero.get(hid, ()))
        cfg_tags = set(cfg_tags_by_hero.get(hid, ()))
        roles = set(roles_by_hero.get(hid, ()))
        if "evil" in tags:
            evil_count += 1
        if "good" in tags:
            good_count += 1
        if "companion" in tags:
            companion_count += 1
        if "debuff" in tags or "debuffer" in cfg_tags or "bud" in cfg_tags:
            debuff_count += 1
        if "speed" in tags or "speed" in cfg_tags:
            speed_count += 1
        if "gold" in tags or "gold" in roles:
            gold_count += 1
        if "tank" in roles:
            tank_count += 1
        if "healer" in roles:
            healer_count += 1
        if "human" in tags:
            human_count += 1
        if tags.intersection(_DWARF_ELF_TAGS):
            dwarf_elf_count += 1
        if tags.intersection(_SMALL_FOLK_TAGS):
            short_folk_count += 1
            small_friends_count += 1
        if tags.intersection(_EXOTIC_TAGS):
            exotic_count += 1
        scores = scores_by_hero.get(hid, {})
        if scores.get("dex", 0) >= 16 or "speed" in tags or "speed" in cfg_tags:
            fast_friends_count += 1
        swap_hits += sum(
            1
            for left, right in (("str", "cha"), ("dex", "int"), ("con", "wis"))
            if abs(scores.get(left, 0) - scores.get(right, 0)) >= 5
        )

    return FormationMetrics(
        evil_count=evil_count,
        good_count=good_count,
        companion_count=companion_count,
        debuff_count=debuff_count,
        speed_count=speed_count,
        gold_count=gold_count,
        tank_count=tank_count,
        healer_count=healer_count,
        human_count=human_count,
        dwarf_elf_count=dwarf_elf_count,
        short_folk_count=short_folk_count,
        exotic_count=exotic_count,
        swap_hits=swap_hits,
        bg3_count=bg3_count,
        small_friends_count=small_friends_count,
        fast_friends_count=fast_friends_count,
    )


def _score_specialization_option(
    opt: SpecializationOption,
    hero_id: int,
    metrics: FormationMetrics,
    *,
    highest_damage_hero_id: int | None = None,
    static_only: bool = False,
) -> tuple[int, list[str]]:
    name = opt.name.lower()
    roles = set(_hero_roles_map_from_champion_config().get(hero_id, ()))
    tags = set(_hero_tags_map_from_champion_config().get(hero_id, ()))
    cfg_tags = set(_hero_tags_map_from_champion_config().get(hero_id, ()))
    cached_tags = set(_hero_tags_map_from_cached_definitions().get(hero_id, ()))
    all_tags = tags | cached_tags | cfg_tags
    reasons: list[str] = []
    score = 0

    def _add(points: int, reason: str, *, keyword: str | None = None) -> None:
        nonlocal score
        if keyword is None or keyword in name:
            score += points
            if reason not in reasons:
                reasons.append(reason)

    profile_keywords = {
        "gold": ("gold", "rich", "fortune", "business", "riches", "treasure", "coins"),
        "speed": ("phlo", "fast", "speed", "swift", "quick"),
        "tank": ("guard", "bodyguard", "shield", "protection", "devotion", "guardian", "steel"),
        "healer": ("life", "healing", "heal", "mercy", "restoration"),
        "dps": ("assassin", "battle", "war", "critical", "damage", "vengeance", "champion", "fire"),
        "support": ("allies", "friends", "family", "mentor", "charge", "valor", "team", "fellowship"),
    }
    for tag_key, weight in (("gold", 4), ("speed", 4)):
        if tag_key in all_tags:
            for word in profile_keywords[tag_key]:
                if word in name:
                    _add(weight, f"{tag_key}-profiel")
    for role_key, weight in (("tank", 3), ("healer", 3), ("dps", 3), ("support", 3), ("gold", 3)):
        if role_key in roles:
            for word in profile_keywords.get(role_key, ()):
                if word in name:
                    _add(weight, f"{role_key}-profiel")

    if not static_only:
        if metrics.evil_count >= 3 and any(w in name for w in ("evil", "malevolence", "villain")):
            _add(8, f"{metrics.evil_count} evil champions")
        if metrics.companion_count >= 3 and any(
            w in name for w in ("companion", "hall", "family", "allies", "fellowship", "friends", "tight knit")
        ):
            _add(8, f"{metrics.companion_count} companion/affiliatie synergie")
        if metrics.debuff_count >= 3 and any(w in name for w in ("ward", "plague", "withering", "debuff", "curse")):
            _add(6, f"{metrics.debuff_count} debuff champions")
        if metrics.good_count >= 4 and "good" in name:
            _add(6, f"{metrics.good_count} good champions")
        if metrics.speed_count >= 2 and any(w in name for w in ("phlo", "fast", "speed", "swift")):
            _add(5, f"{metrics.speed_count} speed champions")
        if metrics.gold_count >= 2 and any(w in name for w in ("gold", "rich", "fortune", "riches")):
            _add(5, f"{metrics.gold_count} gold champions")
        if metrics.small_friends_count >= 3 and "small friends" in name:
            _add(7, f"{metrics.small_friends_count} small-folk champions")
        if metrics.fast_friends_count >= 3 and "fast friends" in name:
            _add(7, f"{metrics.fast_friends_count} snelle champions")
        if metrics.bg3_count >= 3 and "finite fellowship" in name:
            _add(8, f"{metrics.bg3_count} Baldur's Gate 3 champions")
        if "bond: humans" in name:
            _add(metrics.human_count * 2, f"{metrics.human_count} human champions")
        if "bond: dwarves and elves" in name:
            _add(metrics.dwarf_elf_count * 2, f"{metrics.dwarf_elf_count} dwarf/elf champions")
        if "bond: short-folk" in name or "short folk" in name:
            _add(metrics.short_folk_count * 2, f"{metrics.short_folk_count} short-folk champions")
        if "exotic species" in name:
            _add(metrics.exotic_count * 2, f"{metrics.exotic_count} exotic champions")
        if "witch's switch" in name or "witchs switch" in name:
            if metrics.swap_hits >= 18:
                _add(4, f"{metrics.swap_hits} sterke ability-score swaps")
            else:
                score -= 12
        if "observance: foe" in name and metrics.evil_count >= 2:
            _add(4, "evil-doelwit synergie")
        if "observance: friend" in name and metrics.good_count >= metrics.evil_count:
            _add(4, "good-party synergie")
        if highest_damage_hero_id == hero_id and any(
            w in name for w in ("assassin", "battle", "damage", "piercing", "shield master")
        ):
            _add(4, "champion is huidige top damage")

    meta_ids = load_meta_static_defaults().get(hero_id, [])
    if opt.upgrade_id in meta_ids:
        _add(6, "algemene meta-keuze")

    if score <= 0 and not reasons:
        reasons.append("algemene profiel-match")
    return score, reasons


def smart_defaults_from_options(
    hero_id: int,
    known_options: list[SpecializationOption],
    metrics: FormationMetrics,
    *,
    highest_damage_hero_id: int | None = None,
    static_only: bool = False,
) -> tuple[list[int], str]:
    chosen_ids: list[int] = []
    reason_parts: list[str] = []
    for tier_index in sorted({opt.tier_index for opt in known_options}):
        tier_options = [opt for opt in known_options if opt.tier_index == tier_index]
        ranked: list[tuple[int, int, SpecializationOption, list[str]]] = []
        for order, opt in enumerate(tier_options):
            score, reasons = _score_specialization_option(
                opt,
                hero_id,
                metrics,
                highest_damage_hero_id=highest_damage_hero_id,
                static_only=static_only,
            )
            ranked.append((score, -order, opt, reasons))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best = ranked[0]
        chosen_ids.append(best[2].upgrade_id)
        if best[3]:
            reason_parts.append(best[3][0])
    rule_kind = "basis-regel" if static_only else "formatie-regel"
    detail = reason_parts[0] if reason_parts else "profiel-match"
    return chosen_ids, f"{rule_kind} ({detail})"


def _other_tanks(active_hero_ids: set[int], hero_id: int) -> list[int]:
    roles_by_hero = _hero_roles_map_from_champion_config()
    return [
        hid
        for hid in active_hero_ids
        if hid != hero_id and "tank" in roles_by_hero.get(hid, ())
    ]


def _handle_bruenor(ctx: FormationContext) -> tuple[list[int], str] | None:
    if ctx.highest_damage_hero_id == 1:
        return [6], "formatie-regel (Bruenor is huidige top damage)"
    return [7], "formatie-regel (Bruenor bufft de party)"


def _handle_celeste(ctx: FormationContext) -> tuple[list[int], str] | None:
    metrics = formation_metrics(ctx.active_hero_ids)
    if metrics.healer_count <= 1:
        return [30], "formatie-regel (weinig healers in party)"
    return [29], "formatie-regel (voldoende healing beschikbaar)"


def _handle_nayeli(ctx: FormationContext) -> tuple[list[int], str] | None:
    if _other_tanks(ctx.active_hero_ids, 3):
        return [44], "formatie-regel (andere tank aanwezig)"
    return [43], "formatie-regel (Nayeli bufft achterliggende champions)"


def _handle_catti(ctx: FormationContext) -> tuple[list[int], str] | None:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    companion_count = sum(
        1 for hid in ctx.active_hero_ids if "companion" in tags_by_hero.get(hid, ())
    )
    if companion_count >= 3:
        return [11314], f"formatie-regel ({companion_count} Companions of the Hall)"
    if ctx.highest_damage_hero_id == 25:
        return [11312], "formatie-regel (Catti-brie is huidige top damage)"
    return [11313], "formatie-regel (Catti-brie ondersteunt push)"


def _handle_evelyn(ctx: FormationContext) -> tuple[list[int], str] | None:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    affiliate_count = sum(
        1
        for hid in ctx.active_hero_ids
        if _AFFINITY_TAGS.intersection(tags_by_hero.get(hid, ()))
    )
    if affiliate_count >= 3:
        return [12212], f"formatie-regel ({affiliate_count} relevante affiliatiegenoten)"
    if _other_tanks(ctx.active_hero_ids, 26):
        return [12210], "formatie-regel (andere tank aanwezig)"
    return [12211], "formatie-regel (Evelyn tankt vooraan)"


def _handle_widdle(ctx: FormationContext) -> tuple[list[int], str] | None:
    scores_by_hero = _hero_ability_scores_map_from_cached_definitions()

    def _qualifies(hid: int, group: str) -> bool:
        scores = scores_by_hero.get(hid, {})
        if group == "strong":
            return (scores.get("str", 0) >= 12) or (scores.get("dex", 0) >= 12)
        if group == "mind":
            return (scores.get("int", 0) >= 12) or (scores.get("con", 0) >= 12)
        return (scores.get("wis", 0) >= 12) or (scores.get("cha", 0) >= 12)

    counts = {
        "strong": sum(1 for hid in ctx.active_hero_ids if _qualifies(hid, "strong")),
        "mind": sum(1 for hid in ctx.active_hero_ids if _qualifies(hid, "mind")),
        "wisdom": sum(1 for hid in ctx.active_hero_ids if _qualifies(hid, "wisdom")),
    }
    best = max(counts.values(), default=0)
    tied = [key for key, value in counts.items() if value == best]
    if ctx.highest_damage_hero_id is not None:
        for key in tied:
            if _qualifies(ctx.highest_damage_hero_id, key):
                if key == "strong":
                    return [6909], "formatie-regel (Widdle dekt de sterkste ability-score groep)"
                if key == "mind":
                    return [6910], "formatie-regel (Widdle dekt de slimste en taaiste groep)"
                return [6911], "formatie-regel (Widdle dekt de wijsste en meest charismatische groep)"
    choice = tied[0] if tied else "strong"
    if choice == "mind":
        return [6910], "formatie-regel (Widdle dekt de slimste en taaiste groep)"
    if choice == "wisdom":
        return [6911], "formatie-regel (Widdle dekt de wijsste en meest charismatische groep)"
    return [6909], "formatie-regel (Widdle dekt de sterkste ability-score groep)"


def _wyll_attack_counts(active_hero_ids: set[int]) -> tuple[int, int]:
    attack_types_by_hero = _hero_attack_types_map_from_cached_definitions()
    melee_count = magic_count = 0
    for hid in active_hero_ids:
        types = attack_types_by_hero.get(hid, frozenset())
        if "melee" in types:
            melee_count += 1
        if "magic" in types:
            magic_count += 1
    return melee_count, magic_count


def _handle_wyll(ctx: FormationContext) -> tuple[list[int], str] | None:
    party_size = max(len(ctx.active_hero_ids), 1)
    melee_count, magic_count = _wyll_attack_counts(ctx.active_hero_ids)
    familiar_count = ctx.familiar_count

    tome_mult = (1.25**magic_count) if magic_count else 0.0
    chain_mult = (1.10**familiar_count) if familiar_count else 0.0
    blade_mult = (
        1.0 + 2.0 * (melee_count / party_size) * _WYLL_FOLK_HERO_COVERAGE
        if melee_count
        else 0.0
    )

    scores = {
        _WYLL_BLADE: blade_mult,
        _WYLL_CHAIN: chain_mult,
        _WYLL_TOME: tome_mult,
    }

    if ctx.highest_damage_hero_id is not None:
        top_types = _hero_attack_types_map_from_cached_definitions().get(
            ctx.highest_damage_hero_id, frozenset()
        )
        if "magic" in top_types and "melee" not in top_types:
            scores[_WYLL_TOME] *= 1.08
        elif "melee" in top_types and "magic" not in top_types:
            scores[_WYLL_BLADE] *= 1.08

    best_id = max(scores, key=scores.__getitem__)
    if best_id == _WYLL_TOME:
        return [best_id], f"formatie-regel ({magic_count} magic-aanvallers → Pact of the Tome)"
    if best_id == _WYLL_CHAIN:
        return [best_id], f"formatie-regel ({familiar_count} familiars → Pact of the Chain)"
    return [best_id], f"formatie-regel ({melee_count} melee-aanvallers → Pact of the Blade)"


def _handle_gale(ctx: FormationContext) -> tuple[list[int], str] | None:
    metrics = formation_metrics(ctx.active_hero_ids)
    tier0 = 14576
    if metrics.bg3_count >= 3:
        tier0_reason = f"{metrics.bg3_count} Baldur's Gate 3 champions"
    else:
        tier0_reason = "algemene Gale-keuze"

    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    scores_by_hero = _hero_ability_scores_map_from_cached_definitions()
    ceremorphosis = ceremorphosis_stack_count(
        ctx.active_hero_ids,
        tags_by_hero,
        cfg_tags_by_hero,
    )
    high_int = high_intelligence_count(ctx.active_hero_ids, scores_by_hero)
    unavailable = unavailable_owned_hero_count(ctx.active_hero_ids, ctx.owned_hero_ids)
    _tier1_id, tier1_reason = _pick_best_qualified_stack(
        [
            (14578, ceremorphosis, 100, "Ceremorphosis"),
            (14579, high_int, 100, "Mystical Mentor"),
            (14580, unavailable, 7.5, "Finite Fellowship"),
        ],
        default_id=14580,
        default_label="Finite Fellowship",
    )
    return [tier0, _tier1_id], (
        f"formatie-regel ({tier0_reason}; "
        f"{tier1_reason.removeprefix('formatie-regel (').rstrip(')')})"
    )


def _handle_skylla(ctx: FormationContext) -> tuple[list[int], str] | None:
    metrics = formation_metrics(ctx.active_hero_ids)
    party_size = len(ctx.active_hero_ids)
    if metrics.evil_count >= 3:
        return [_SKYLLA_LEAGUE, _SKYLLA_GREEN_FIRE], f"formatie-regel ({metrics.evil_count} evil champions)"
    if _is_variant_run_goal(ctx.run_goal):
        swap_hits, strong_swaps = _skylla_swap_metrics(ctx.active_hero_ids)
        min_strong, min_hits = _skylla_witch_switch_thresholds(party_size)
        if strong_swaps >= min_strong or swap_hits >= min_hits:
            return (
                [_SKYLLA_WITCH_SWITCH, _SKYLLA_GREEN_FIRE],
                f"formatie-regel (variant: {swap_hits} ability-score swaps, {strong_swaps} champions met 2+ paren)",
            )
    if metrics.debuff_count >= 3:
        return [_SKYLLA_WITHERING, _SKYLLA_GREEN_FIRE], f"formatie-regel ({metrics.debuff_count} debuff/brake synergie)"
    return [_SKYLLA_WITHERING, _SKYLLA_GREEN_FIRE], "formatie-regel (algemene debuff/push-keuze)"


def _handle_raistlin(ctx: FormationContext) -> tuple[list[int], str] | None:
    metrics = formation_metrics(ctx.active_hero_ids)
    if metrics.good_count >= 4:
        return [18934], f"formatie-regel ({metrics.good_count} good champions)"
    return [18935], "formatie-regel (algemene push-keuze)"


def _qualified_multiplicative_score(count: int, pct: int | float) -> float:
    if count <= 0:
        return 0.0
    return (1.0 + pct / 100.0) ** count


def _pick_best_qualified_stack(
    options: list[tuple[int, int, int | float, str]],
    *,
    default_id: int,
    default_label: str,
) -> tuple[int, str]:
    scored = [
        (upgrade_id, count, pct, name, _qualified_multiplicative_score(count, pct))
        for upgrade_id, count, pct, name in options
    ]
    best_id, best_count, best_pct, best_name, best_score = max(
        scored,
        key=lambda item: (item[4], item[1], item[2], -item[0]),
    )
    if best_score <= 0:
        return default_id, f"formatie-regel (geen qualified champions; default {default_label})"
    pct_label = int(best_pct) if best_pct == int(best_pct) else best_pct
    return (
        best_id,
        f"formatie-regel ({best_count} qualified × {pct_label}% multiplicatief → {best_name})",
    )


def _tess_qualified_counts(active_hero_ids: set[int]) -> tuple[int, int, int]:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    attack_types_by_hero = _hero_attack_types_map_from_cached_definitions()
    fallback_count = ranged_count = rogue_count = 0
    for hid in active_hero_ids:
        tags = set(tags_by_hero.get(hid, ())) | set(cfg_tags_by_hero.get(hid, ()))
        if "unaffiliated" in tags or "fallbacks" in tags:
            fallback_count += 1
        if "ranged" in attack_types_by_hero.get(hid, frozenset()):
            ranged_count += 1
        if "rogue" in tags:
            rogue_count += 1
    return fallback_count, ranged_count, rogue_count


def _handle_tess(ctx: FormationContext) -> tuple[list[int], str] | None:
    fallback_count, ranged_count, rogue_count = _tess_qualified_counts(ctx.active_hero_ids)
    best_id, reason = _pick_best_qualified_stack(
        [
            (_TESS_FALLBACK, fallback_count, _TESS_PCT_FALLBACK, "The Fallback Plan"),
            (_TESS_RANGED, ranged_count, _TESS_PCT_RANGED, "Eyes on the Horizon"),
            (_TESS_ROGUE, rogue_count, _TESS_PCT_ROGUE, "Rogues' Gallery"),
        ],
        default_id=_TESS_FALLBACK,
        default_label="The Fallback Plan",
    )
    return [best_id], reason


_UMBERTO_LAWS_ALLIANCE = 15052
_UMBERTO_FAMILY_OF_ORPHANS = 15053
_UMBERTO_CALL_OF_WARDENS = 15054
_UMBERTO_MORE_BEES = 15055
_UMBERTO_MORE_CLUES = 15056
_UMBERTO_MORE_DAMAGE = 15057
_UMBERTO_PCT_LAWFUL = 125
_UMBERTO_PCT_UNAFFILIATED = 100
_UMBERTO_PCT_RANGER_DRUID = 300


def _umberto_qualified_counts(active_hero_ids: set[int]) -> tuple[int, int, int]:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    lawful_count = unaffiliated_count = ranger_druid_count = 0
    for hid in active_hero_ids:
        tags = set(tags_by_hero.get(hid, ())) | set(cfg_tags_by_hero.get(hid, ()))
        if "lawful" in tags:
            lawful_count += 1
        if "unaffiliated" in tags:
            unaffiliated_count += 1
        if "ranger" in tags or "druid" in tags:
            ranger_druid_count += 1
    return lawful_count, unaffiliated_count, ranger_druid_count


def _umberto_tier1_choice(ctx: FormationContext) -> tuple[int, str]:
    """Second specialization (lvl 400): Gaarawarr quick-power vs tank bees."""
    roles = set(_hero_roles_map_from_champion_config().get(151, ()))
    seat = ctx.seat_by_hero.get(151) if ctx.seat_by_hero else None
    frontline = seat is not None and _formation_column(seat) == 1
    solo_tank = "tank" in roles and frontline and not _other_tanks(ctx.active_hero_ids, 151)
    if solo_tank:
        return _UMBERTO_MORE_BEES, "More Bees (tank-spec)"
    return _UMBERTO_MORE_DAMAGE, "More Damage (snel power)"


_CAZRIN_ID = 166
_CAZRIN_SELF_TAUGHT = 17678
_CAZRIN_ANCESTOR = 17679
_CAZRIN_PCT = 100
_CAZRIN_SELF_TAUGHT_EXPR = (
    "HasTag(`fallbacks`) || has_base_attack_dmg_type_melee || has_base_attack_dmg_type_ranged"
)
_CAZRIN_ANCESTOR_EXPR = "HasTag(`fallbacks`) || HasTag(`good`)"
_BUD_RUN_GOALS = frozenset({"bud", "generic_progression", "push", "campaign"})


def _cazrin_qualified_counts(active_hero_ids: set[int]) -> tuple[int, int]:
    from ic_gamedata.adventure_restrictions import hero_matches_specialization_expr

    self_taught = ancestor = 0
    for hid in active_hero_ids:
        if hero_matches_specialization_expr(hid, _CAZRIN_SELF_TAUGHT_EXPR) is True:
            self_taught += 1
        if hero_matches_specialization_expr(hid, _CAZRIN_ANCESTOR_EXPR) is True:
            ancestor += 1
    return self_taught, ancestor


def _cazrin_fallback_allies(active_hero_ids: set[int]) -> int:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    count = 0
    for hid in active_hero_ids:
        if hid == _CAZRIN_ID:
            continue
        tags = set(tags_by_hero.get(hid, ())) | set(cfg_tags_by_hero.get(hid, ()))
        if "fallbacks" in tags:
            count += 1
    return count


def _handle_cazrin(ctx: FormationContext) -> tuple[list[int], str] | None:
    self_taught_count, ancestor_count = _cazrin_qualified_counts(ctx.active_hero_ids)
    best_id, reason = _pick_best_qualified_stack(
        [
            (_CAZRIN_SELF_TAUGHT, self_taught_count, _CAZRIN_PCT, "Self Taught"),
            (_CAZRIN_ANCESTOR, ancestor_count, _CAZRIN_PCT, "Ancestor's Shadow"),
        ],
        default_id=_CAZRIN_ANCESTOR,
        default_label="Ancestor's Shadow",
    )
    if (
        self_taught_count == ancestor_count
        and ancestor_count > 0
        and best_id == _CAZRIN_SELF_TAUGHT
    ):
        run_goal = (ctx.run_goal or "").casefold()
        fallback_allies = _cazrin_fallback_allies(ctx.active_hero_ids)
        if run_goal in _BUD_RUN_GOALS or not run_goal or fallback_allies >= 1:
            ally_note = (
                f"; {fallback_allies} fallback-allies → Ancestor's Shadow"
                if fallback_allies >= 1
                else "; BUD/push → Ancestor's Shadow"
            )
            return (
                [_CAZRIN_ANCESTOR],
                reason.replace("Self Taught", "Ancestor's Shadow").replace(")", f"{ally_note})"),
            )
    return [best_id], reason


def _handle_omin(ctx: FormationContext) -> tuple[list[int], str] | None:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    form_ranks = champions_of_tymora_count(
        ctx.active_hero_ids,
        ctx.seat_by_hero,
        tags_by_hero,
        known_associates_unlocked=omin_has_known_associates(ctx.hero_upgrade_ids),
    )
    favored = acqinc_cteam_count(ctx.active_hero_ids, tags_by_hero)
    best_id, reason = _pick_best_qualified_stack(
        [
            (12304, form_ranks, 50, "Form Ranks"),
            (12305, favored, 100, "Favored Friends"),
        ],
        default_id=12305,
        default_label="Favored Friends",
    )
    return [best_id], reason


def _handle_nordom(ctx: FormationContext) -> tuple[list[int], str] | None:
    adventures = grand_tour_base_adventures_completed(ctx.account_stats)
    competency = ctx.modron_core_competency_stacks
    scored = [
        (18166, adventures, 33, "BASIC Functionality", _qualified_multiplicative_score(adventures, 33)),
        (
            18168,
            competency,
            25,
            "Core Competency",
            _qualified_multiplicative_score(competency, 25),
        ),
    ]
    best_id, best_count, best_pct, best_name, best_score = max(
        scored,
        key=lambda item: (item[4], item[1], item[2], -item[0]),
    )
    if best_score <= 0:
        return [18167], "formatie-regel (geen stack-data; default Modron Core Toolbox)"
    pct_label = int(best_pct) if best_pct == int(best_pct) else best_pct
    return (
        [best_id],
        f"formatie-regel ({best_count} stacks × {pct_label}% multiplicatief → {best_name})",
    )


def _handle_dob(ctx: FormationContext) -> tuple[list[int], str] | None:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    attack_types_by_hero = _hero_attack_types_map_from_cached_definitions()
    scores_by_hero = _hero_ability_scores_map_from_cached_definitions()
    magical, friendly, quick, species = dob_qualified_counts(
        ctx.active_hero_ids,
        tags_by_hero,
        attack_types_by_hero,
        scores_by_hero,
    )
    best_id, reason = _pick_best_qualified_stack(
        [
            (8742, magical, 100, "Befriend the Magical"),
            (8743, friendly, 100, "Befriend the Friendly"),
            (8744, quick, 100, "Befriend the Quick"),
            (8745, species, 100, "Befriend Everybody!"),
        ],
        default_id=8745,
        default_label="Befriend Everybody!",
    )
    return [best_id], reason


def _handle_strongheart(ctx: FormationContext) -> tuple[list[int], str] | None:
    metrics = formation_metrics(ctx.active_hero_ids)
    best_id, reason = _pick_best_qualified_stack(
        [
            (19733, metrics.good_count, 100, "Valor's Call"),
            (19738, ctx.event_boon_count, 20, "A Righteous Event"),
        ],
        default_id=19734,
        default_label="Honorary Member",
    )
    if metrics.good_count == ctx.event_boon_count == 0:
        return [19734], "formatie-regel (geen good/boon stacks; default Honorary Member)"
    return [best_id], reason


def _handle_shadowheart(ctx: FormationContext) -> tuple[list[int], str] | None:
    scores_by_hero = _hero_ability_scores_map_from_cached_definitions()
    distance = shadowheart_duplicity_distance(
        ctx.active_hero_ids,
        ctx.seat_by_hero,
        scores_by_hero,
    )
    run_goal = (ctx.run_goal or "").casefold()
    if distance >= 2:
        return [13281], f"formatie-regel ({distance} slots duplicate-afstand → Find Yourself)"
    if run_goal in _BUD_RUN_GOALS:
        return [13279], "formatie-regel (BUD-run → Guidance)"
    if distance > 0:
        return [13281], f"formatie-regel ({distance} slot duplicate-afstand → Find Yourself)"
    return [13281], "formatie-regel (default Find Yourself)"


def _handle_karlach(ctx: FormationContext) -> tuple[list[int], str] | None:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    ceremorphosis = ceremorphosis_stack_count(
        ctx.active_hero_ids,
        tags_by_hero,
        cfg_tags_by_hero,
    )
    if ceremorphosis >= 3:
        return [13728], f"formatie-regel ({ceremorphosis} ceremorphosis stacks → Wild Magic)"
    return [13726], "formatie-regel (default Berserker; rage stacks niet in payload)"


def _handle_diana(ctx: FormationContext) -> tuple[list[int], str] | None:
    inspire_id = diana_inspire_upgrade_id(ctx.hero_upgrade_ids) or 14792
    matched = diana_inspire_match_count(ctx.active_hero_ids, inspire_id)
    unmatched = max(0, len(ctx.active_hero_ids) - matched)
    best_id, reason = _pick_best_qualified_stack(
        [
            (14796, matched, 100, "Ensemble Cast"),
            (14797, unmatched, 140, "Spotlight Episode"),
        ],
        default_id=14796,
        default_label="Ensemble Cast",
    )
    return [best_id], reason


_BEADLE_EPIC = 16727
_BEADLE_PREMIUM = 16728
_BEADLE_SHINY = 16729
_BEADLE_PCT_EPIC = 20
_BEADLE_PCT_PREMIUM = 0.075
_BEADLE_PCT_SHINY = 30


def _handle_beadle(ctx: FormationContext) -> tuple[list[int], str] | None:
    epic_count, ilvl_count, shiny_count = formation_loot_stack_totals(
        ctx.active_hero_ids,
        ctx.loot_by_hero,
    )
    if ctx.loot_by_hero is None:
        return [_BEADLE_EPIC], "formatie-regel (geen loot-data; default Epic Equipment)"
    best_id, reason = _pick_best_qualified_stack(
        [
            (_BEADLE_EPIC, epic_count, _BEADLE_PCT_EPIC, "Epic Equipment"),
            (_BEADLE_PREMIUM, ilvl_count, _BEADLE_PCT_PREMIUM, "Premium Gear"),
            (_BEADLE_SHINY, shiny_count, _BEADLE_PCT_SHINY, "Shiniest Loot"),
        ],
        default_id=_BEADLE_EPIC,
        default_label="Epic Equipment",
    )
    return [best_id], reason


def _handle_umberto(ctx: FormationContext) -> tuple[list[int], str] | None:
    lawful_count, unaffiliated_count, ranger_druid_count = _umberto_qualified_counts(
        ctx.active_hero_ids
    )
    tier0_id, tier0_reason = _pick_best_qualified_stack(
        [
            (_UMBERTO_LAWS_ALLIANCE, lawful_count, _UMBERTO_PCT_LAWFUL, "Law's Alliance"),
            (
                _UMBERTO_FAMILY_OF_ORPHANS,
                unaffiliated_count,
                _UMBERTO_PCT_UNAFFILIATED,
                "Family of Orphans",
            ),
            (
                _UMBERTO_CALL_OF_WARDENS,
                ranger_druid_count,
                _UMBERTO_PCT_RANGER_DRUID,
                "Call of the Wardens",
            ),
        ],
        default_id=_UMBERTO_FAMILY_OF_ORPHANS,
        default_label="Family of Orphans",
    )
    tier1_id, tier1_label = _umberto_tier1_choice(ctx)
    tier0_detail = tier0_reason.removeprefix("formatie-regel (").rstrip(")")
    return (
        [tier0_id, tier1_id],
        f"formatie-regel ({tier0_detail}; {tier1_label})",
    )


_VR_ID = 177
_VR_OCCULT_ALLIES = 19700
_VR_SCHOLAR = 19701
_VR_ENDLESS = 19702
_VR_CURE = 19703
_VR_DISPEL = 19704
_VR_SANCTUARY = 19705


def _van_richten_endless_hunt_stacks(active_hero_ids: set[int]) -> int:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    total = 0
    for hero_id in active_hero_ids:
        tags = set(tags_by_hero.get(hero_id, ())) | set(cfg_tags_by_hero.get(hero_id, ()))
        if "hunter" in tags:
            total += 1
        if "debuff" in tags or "debuffer" in cfg_tags_by_hero.get(hero_id, ()):
            total += 1
    return total


def _front_column_non_tank_count(ctx: FormationContext) -> int:
    if not ctx.seat_by_hero:
        return 0
    roles_by_hero = _hero_roles_map_from_champion_config()
    count = 0
    for hero_id in ctx.active_hero_ids:
        seat = ctx.seat_by_hero.get(hero_id)
        if seat is None or _formation_column(seat) != 1:
            continue
        if "tank" not in roles_by_hero.get(hero_id, ()):
            count += 1
    return count


def _van_richten_tier0_choice(ctx: FormationContext) -> tuple[int, str]:
    from ic_gamedata.specialization_qualified_counts import count_qualified_heroes
    from ic_gamedata.specialization_qualified_rules import tier_rule_for_hero_level

    tier = tier_rule_for_hero_level(_VR_ID, 120)
    occult_count = scholar_count = 0
    partial = False
    if tier is not None:
        for opt in tier.supported_options:
            count, is_partial = count_qualified_heroes(ctx.active_hero_ids, opt)
            if opt.upgrade_id == _VR_OCCULT_ALLIES:
                occult_count = count
            elif opt.upgrade_id == _VR_SCHOLAR:
                scholar_count = count
            partial = partial or is_partial
    endless_count = _van_richten_endless_hunt_stacks(ctx.active_hero_ids)
    best_id, reason = _pick_best_qualified_stack(
        [
            (_VR_OCCULT_ALLIES, occult_count, 100, "Occult Allies"),
            (_VR_SCHOLAR, scholar_count, 100, "Scholar of Dread"),
            (_VR_ENDLESS, endless_count, 100, "Endless Hunt"),
        ],
        default_id=_VR_ENDLESS,
        default_label="Endless Hunt",
    )
    if partial and "deels ingeschat" not in reason:
        reason = reason[:-1] + "; deels ingeschat)"
    return best_id, reason


def _van_richten_tier1_choice(ctx: FormationContext) -> tuple[int, str]:
    metrics = formation_metrics(ctx.active_hero_ids)
    front_non_tanks = _front_column_non_tank_count(ctx)
    if metrics.healer_count <= 1:
        return _VR_CURE, "weinig healers → Occult Aid: Cure Wounds"
    if front_non_tanks >= 2 and metrics.tank_count >= 1:
        return _VR_SANCTUARY, f"{front_non_tanks} front non-tanks → Occult Aid: Sanctuary"
    return _VR_DISPEL, "push/progressie → Occult Aid: Dispel Evil"


def _handle_van_richten(ctx: FormationContext) -> tuple[list[int], str] | None:
    tier0_id, tier0_reason = _van_richten_tier0_choice(ctx)
    tier1_id, tier1_reason = _van_richten_tier1_choice(ctx)
    return (
        [tier0_id, tier1_id],
        f"formatie-regel ({tier0_reason.removeprefix('formatie-regel (').rstrip(')')}; {tier1_reason})",
    )


def _merge_tier_default_ids(
    known_options: list[SpecializationOption],
    primary_ids: list[int],
    fallback_ids: list[int],
) -> list[int]:
    chosen_by_tier: dict[int, int] = {}
    for tier_index in sorted({opt.tier_index for opt in known_options}):
        tier_options = [opt for opt in known_options if opt.tier_index == tier_index]
        tier_ids = {opt.upgrade_id for opt in tier_options}
        pick = next((upgrade_id for upgrade_id in primary_ids if upgrade_id in tier_ids), None)
        if pick is None:
            pick = next((upgrade_id for upgrade_id in fallback_ids if upgrade_id in tier_ids), None)
        if pick is None and tier_options:
            pick = tier_options[0].upgrade_id
        if pick is not None:
            chosen_by_tier[tier_index] = pick
    return [chosen_by_tier[index] for index in sorted(chosen_by_tier)]


def _combined_dynamic_reason(
    multiply_result: tuple[list[int], str] | None,
    smart_result: tuple[list[int], str] | None,
    known_options: list[SpecializationOption],
    merged_ids: list[int],
) -> str:
    parts: list[str] = []
    if multiply_result is not None and multiply_result[0]:
        parts.append(multiply_result[1].removeprefix("formatie-regel (").rstrip(")"))
    if smart_result is not None:
        multiply_ids = set(multiply_result[0]) if multiply_result else set()
        for tier_index in sorted({opt.tier_index for opt in known_options}):
            tier_options = [opt for opt in known_options if opt.tier_index == tier_index]
            tier_ids = {opt.upgrade_id for opt in tier_options}
            if multiply_ids & tier_ids:
                continue
            pick = next((upgrade_id for upgrade_id in merged_ids if upgrade_id in tier_ids), None)
            if pick is None:
                continue
            name = next(opt.name for opt in tier_options if opt.upgrade_id == pick)
            parts.append(f"{name} (profiel-match)")
    if not parts and smart_result is not None:
        return smart_result[1]
    if not parts:
        return "formatie-regel (basiskeuze)"
    return f"formatie-regel ({'; '.join(parts)})"


def _pick_generic_qualified_stack_choices(
    hero_id: int,
    active_hero_ids: set[int],
    known_options: list[SpecializationOption] | None,
) -> tuple[list[int], str] | None:
    from ic_gamedata.specialization_qualified_counts import count_qualified_heroes
    from ic_gamedata.specialization_qualified_rules import (
        qualified_stack_tiers_by_hero,
        tiers_for_known_options,
    )

    if known_options:
        tier_rules = tiers_for_known_options(hero_id, known_options)
    else:
        tiers = qualified_stack_tiers_by_hero().get(hero_id, {})
        if not tiers:
            return None
        tier_rules = [tiers[min(tiers)]]

    if not tier_rules:
        return None

    chosen_ids: list[int] = []
    reason_parts: list[str] = []
    for tier in tier_rules:
        scored_options: list[tuple[int, int, int | float, str]] = []
        partial = False
        options = tier.supported_options if tier.supported_options else tier.options
        for opt in options:
            count, is_partial = count_qualified_heroes(active_hero_ids, opt)
            partial = partial or is_partial
            scored_options.append((opt.upgrade_id, count, opt.pct, opt.name))
        default = options[0]
        best_id, reason = _pick_best_qualified_stack(
            scored_options,
            default_id=default.upgrade_id,
            default_label=default.name,
        )
        if partial and "deels ingeschat" not in reason:
            reason = reason[:-1] + "; deels ingeschat)"
        chosen_ids.append(best_id)
        reason_parts.append(reason.removeprefix("formatie-regel (").rstrip(")"))

    if not chosen_ids:
        return None
    return chosen_ids, f"formatie-regel ({'; '.join(reason_parts)})"


def _vlithryn_unique_species_count(active_hero_ids: set[int]) -> int:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    return unique_species_count(active_hero_ids, tags_by_hero)


def _vlithryn_qualified_counts(active_hero_ids: set[int]) -> tuple[int, int, int]:
    scores_by_hero = _hero_ability_scores_map_from_cached_definitions()
    low_int = low_total = 0
    for hid in active_hero_ids:
        scores = scores_by_hero.get(hid, {})
        intel = scores.get("int")
        if intel is not None and intel <= 12:
            low_int += 1
        if len(scores) >= 6:
            total = sum(scores.get(stat, 0) for stat in ("str", "dex", "con", "int", "wis", "cha"))
            if total <= 78:
                low_total += 1
    return low_int, low_total, _vlithryn_unique_species_count(active_hero_ids)


def _handle_vlithryn(ctx: FormationContext) -> tuple[list[int], str] | None:
    low_int, low_total, species_count = _vlithryn_qualified_counts(ctx.active_hero_ids)
    best_id, reason = _pick_best_qualified_stack(
        [
            (_VLITHRYN_WHO_ELSE, low_int, _VLITHRYN_PCT_WHO_ELSE, "Who Else Would Save Them?"),
            (_VLITHRYN_HELP, low_total, _VLITHRYN_PCT_HELP, "Help the Unfortunate"),
            (_VLITHRYN_SPREADING, species_count, _VLITHRYN_PCT_SPREADING, "Spreading the Word"),
        ],
        default_id=_VLITHRYN_WHO_ELSE,
        default_label="Who Else Would Save Them?",
    )
    return [best_id], reason


def _volo_qualified_counts(active_hero_ids: set[int]) -> tuple[int, int, int]:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    cfg_tags_by_hero = _hero_tags_map_from_champion_config()
    attack_types_by_hero = _hero_attack_types_map_from_cached_definitions()

    hunter_count = 0
    for hid in active_hero_ids:
        tags = set(tags_by_hero.get(hid, ())) | set(cfg_tags_by_hero.get(hid, ()))
        if "hunter" in tags:
            hunter_count += 1
    # Spirits and Specters grants Volo the Hunter role, so he counts after picking it.
    volo_tags = set(tags_by_hero.get(_VOLO_ID, ())) | set(cfg_tags_by_hero.get(_VOLO_ID, ()))
    if _VOLO_ID in active_hero_ids and "hunter" not in volo_tags:
        hunter_count += 1

    # Absolute Adversaries: formation gains one Ceremorphosis stack per AA champion.
    tadpole_count = sum(
        1
        for hid in active_hero_ids
        if "absoluteadversaries" in set(tags_by_hero.get(hid, ())) | set(cfg_tags_by_hero.get(hid, ()))
    )

    magical_count = sum(
        1 for hid in active_hero_ids if "magic" in attack_types_by_hero.get(hid, frozenset())
    )
    return hunter_count, tadpole_count, magical_count


def _handle_volo(ctx: FormationContext) -> tuple[list[int], str] | None:
    hunter_count, tadpole_count, magical_count = _volo_qualified_counts(ctx.active_hero_ids)
    best_id, reason = _pick_best_qualified_stack(
        [
            (_VOLO_SPIRITS, hunter_count, _VOLO_PCT, "Volo's Guide to Spirits and Specters"),
            (_VOLO_TADPOLES, tadpole_count, _VOLO_PCT, "Volo's Guide to Brain-Eating Tadpoles"),
            (_VOLO_MAGICAL, magical_count, _VOLO_PCT, "Volo's Guide to All Things Magical"),
        ],
        default_id=_VOLO_MAGICAL,
        default_label="Volo's Guide to All Things Magical",
    )
    return [best_id], reason


def _formation_column(seat: int) -> int:
    return ((seat - 1) % 4) + 1


def _kos_potk_beneficiaries(active_hero_ids: set[int], seat_by_hero: dict[int, int] | None) -> int:
    """Champions in the two columns behind King of Shadows (Power of the King targets)."""
    if not seat_by_hero:
        return max(0, len(active_hero_ids) - 1)
    kos_seat = seat_by_hero.get(_KOS_ID)
    if kos_seat is None:
        return max(0, len(active_hero_ids) - 1)
    kos_col = _formation_column(kos_seat)
    count = 0
    for hid in active_hero_ids:
        if hid == _KOS_ID:
            continue
        seat = seat_by_hero.get(hid)
        if seat is None:
            continue
        col = _formation_column(seat)
        if kos_col < col <= kos_col + 2:
            count += 1
    return count


def _kos_tier1_qualified_counts(active_hero_ids: set[int]) -> tuple[int, int, int]:
    tags_by_hero = _hero_tags_map_from_cached_definitions()
    legacy_count = evil_count = healing_count = 0
    for hid in active_hero_ids:
        tags = set(tags_by_hero.get(hid, ()))
        if tags.intersection(_KOS_LEGACY_RACE_TAGS):
            legacy_count += 1
        if "evil" in tags:
            evil_count += 1
        if "healing" in tags:
            healing_count += 1
    return legacy_count, evil_count, healing_count


def _handle_king_of_shadows(ctx: FormationContext) -> tuple[list[int], str] | None:
    beneficiaries = _kos_potk_beneficiaries(ctx.active_hero_ids, ctx.seat_by_hero)
    pawns_score = beneficiaries * _KOS_PAWNS_PCT
    if ctx.highest_damage_hero_id == _KOS_ID:
        unleashed_score = _KOS_UNLEASHED_PCT
    else:
        unleashed_score = max(0, (2 - beneficiaries)) * (_KOS_UNLEASHED_PCT // 2)

    tier0_id = _KOS_PAWNS if pawns_score >= unleashed_score else _KOS_UNLEASHED
    tier0_name = "Master of Pawns" if tier0_id == _KOS_PAWNS else "Shadow Unleashed"

    legacy_count, evil_count, healing_count = _kos_tier1_qualified_counts(ctx.active_hero_ids)
    tier1_id, tier1_reason = _pick_best_qualified_stack(
        [
            (_KOS_LEGACY, legacy_count, _KOS_PCT_LEGACY, "Legacy of Illefarn"),
            (_KOS_SHADOW_WEAVE, evil_count, _KOS_PCT_EVIL, "Embrace the Shadow Weave"),
            (_KOS_RITES, healing_count, _KOS_PCT_HEALING, "Rites of Survival"),
        ],
        default_id=_KOS_SHADOW_WEAVE,
        default_label="Embrace the Shadow Weave",
    )

    if tier0_id == _KOS_PAWNS:
        tier0_reason = f"{beneficiaries} champions achter KoS → Master of Pawns"
    else:
        tier0_reason = "KoS als carry / weinig party-buff → Shadow Unleashed"

    return (
        [tier0_id, tier1_id],
        f"formatie-regel ({tier0_reason}; {tier1_reason.removeprefix('formatie-regel (').rstrip(')')})",
    )


HERO_HANDLERS: dict[int, HeroHandler] = {
    1: _handle_bruenor,
    2: _handle_celeste,
    3: _handle_nayeli,
    25: _handle_catti,
    26: _handle_evelyn,
    64: _handle_beadle,
    65: _handle_omin,
    91: _handle_widdle,
    100: _handle_nordom,
    105: _handle_dob,
    126: _handle_strongheart,
    141: _handle_shadowheart,
    142: _handle_wyll,
    143: _handle_karlach,
    147: _handle_gale,
    148: _handle_diana,
    159: _handle_volo,
    162: _handle_vlithryn,
    164: _handle_tess,
    168: _handle_king_of_shadows,
    169: _handle_skylla,
    173: _handle_raistlin,
    151: _handle_umberto,
    166: _handle_cazrin,
    177: _handle_van_richten,
}


def dynamic_default_ids(
    hero_id: int,
    active_hero_ids: set[int],
    *,
    highest_damage_hero_id: int | None = None,
    familiar_count: int = 0,
    seat_by_hero: dict[int, int] | None = None,
    known_options: list[SpecializationOption] | None = None,
    run_goal: str | None = None,
    loot_by_hero: dict[int, HeroLootStats] | None = None,
    account_stats: dict[str, Any] | None = None,
    event_boon_count: int = 0,
    modron_core_competency_stacks: int = 0,
    owned_hero_ids: frozenset[int] | None = None,
    hero_upgrade_ids: dict[int, frozenset[int]] | None = None,
) -> tuple[list[int], str] | None:
    ctx = FormationContext(
        active_hero_ids=active_hero_ids,
        highest_damage_hero_id=highest_damage_hero_id,
        familiar_count=familiar_count,
        seat_by_hero=seat_by_hero,
        run_goal=run_goal,
        loot_by_hero=loot_by_hero,
        account_stats=account_stats,
        event_boon_count=event_boon_count,
        modron_core_competency_stacks=modron_core_competency_stacks,
        owned_hero_ids=owned_hero_ids,
        hero_upgrade_ids=hero_upgrade_ids,
    )
    handler = HERO_HANDLERS.get(hero_id)
    if handler is not None:
        return handler(ctx)

    multiply_result = _pick_generic_qualified_stack_choices(
        hero_id,
        active_hero_ids,
        known_options,
    )
    if known_options:
        metrics = formation_metrics(active_hero_ids)
        smart_result = smart_defaults_from_options(
            hero_id,
            known_options,
            metrics,
            highest_damage_hero_id=highest_damage_hero_id,
        )
        merged_ids = _merge_tier_default_ids(
            known_options,
            multiply_result[0] if multiply_result else [],
            smart_result[0],
        )
        if merged_ids:
            return (
                merged_ids,
                _combined_dynamic_reason(multiply_result, smart_result, known_options, merged_ids),
            )

    if multiply_result is not None:
        return multiply_result
    if known_options:
        metrics = formation_metrics(active_hero_ids)
        return smart_defaults_from_options(
            hero_id,
            known_options,
            metrics,
            highest_damage_hero_id=highest_damage_hero_id,
        )
    return None


def baseline_default_ids(
    hero_id: int,
    known_options: list[SpecializationOption],
) -> tuple[list[int], str] | None:
    if not known_options:
        return None
    meta = load_meta_static_defaults().get(hero_id)
    if meta:
        valid = [item for item in meta if any(opt.upgrade_id == item for opt in known_options)]
        if valid:
            return valid, "meta-regel (community/wiki default)"
    return smart_defaults_from_options(
        hero_id,
        known_options,
        EMPTY_FORMATION_METRICS,
        static_only=True,
    )
