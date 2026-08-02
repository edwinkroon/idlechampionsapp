"""Specialization insights for Party Advisor (v2_full CSV + formation context)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from ic_gamedata.adventure_restrictions import AdventureRosterFilter, is_hero_allowed
from ic_gamedata.familiar_seats import familiar_party_count
from ic_gamedata.party_advisor import AdvisorTip, FormationHero, GoalMode, ContextMode
from ic_gamedata.speed_utility_roles import (
    recommended_spec_for_speed_utility,
    speed_utility_role,
)
from ic_gamedata.specialization_engine import FormationContext
from ic_gamedata.specialization_models import SpecializationOption
from ic_gamedata.specialization_rules.context_builder import build_evaluation_context, champion_names_match
from ic_gamedata.specialization_rules.evaluator import evaluate_specialization
from ic_gamedata.specialization_rules.loader import cached_documentation_rules
from ic_gamedata.specialization_rules.models import AdviceResult, Rule
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.specializations import (
    _current_choices,
    _merge_known_options,
    load_specialization_rules,
    merged_hero_record_for_specializations,
    pending_specializations,
    resolve_hero_record,
)

InsightStatus = Literal[
    "open_tier",
    "matches",
    "mismatch",
    "formation_synergy",
    "bench_suggestion",
]

SpecDisplayStatus = Literal["match", "pending", "mismatch"]

FORMATION_SYNERGY_TAGS = frozenset({"formation-dependent", "alignment", "adventure-specific"})
MAX_INSIGHTS = 5
MISMATCH_MIN_CONFIDENCE = 4
_BENCH_LIMIT = 2

_ROUTE_FAMILY_WORDS = frozenset(
    {
        "outflank",
        "oath",
        "pact",
        "bond",
        "route",
        "domain",
        "shape",
        "enemy",
        "speed",
        "gold",
        "support",
        "tank",
        "heal",
        "healing",
    }
)


@dataclass(frozen=True)
class SpecializationInsight:
    hero_id: int
    hero_name: str
    seat: int | None
    recommended_label: str
    current_labels: tuple[str, ...]
    status: InsightStatus
    rule_source_type: str
    data_source_version: str
    confidence: int
    headline: str
    detail: str
    priority: int


def advisor_run_goal(goal: GoalMode, context: ContextMode) -> str:
    if goal == "gold":
        return "gold_farm"
    if goal == "speed":
        return "speed_farm"
    if context == "modron":
        return "speed_farm"
    if context == "push":
        return "push"
    return "generic_progression"


def recommended_spec_for_goal(
    payload: dict[str, Any],
    hero_id: int,
    hero_name: str,
    seat: int | None,
    options: list[SpecializationOption],
    *,
    goal: GoalMode,
    context: ContextMode,
    formation_ctx: FormationContext,
    hero: FormationHero | None = None,
    formation: tuple[FormationHero, ...] = (),
) -> str | None:
    """CSV-backed specialization labels for speed/gold goals (all tiers)."""
    from ic_gamedata.speed_utility_roles import recommended_spec_for_speed_utility, speed_utility_role

    if hero is not None:
        utility = speed_utility_role(hero, goal)
        if utility is not None:
            return recommended_spec_for_speed_utility(hero, formation, utility=utility)

    from ic_gamedata.specializations import _csv_choice_advice

    run_goal = advisor_run_goal(goal, context)
    if run_goal not in {"speed_farm", "gold_farm"}:
        return None
    if not options:
        return None

    chosen_ids, _, _ = _csv_choice_advice(
        hero_id,
        hero_name,
        seat=seat,
        run_goal=run_goal,
        active_hero_ids=set(formation_ctx.active_hero_ids),
        highest_damage_hero_id=formation_ctx.highest_damage_hero_id,
        familiar_count=formation_ctx.familiar_count,
        seat_by_hero=dict(formation_ctx.seat_by_hero),
        known_options=options,
        payload=payload,
    )
    labels = _labels_for_choices(tuple(chosen_ids), options)
    return " / ".join(labels) if labels else None


def _recommended_label_parts(recommended: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in recommended.split(" / ") if part.strip())
    return parts if parts else (recommended.strip(),)


def _active_party_id(payload: dict[str, Any]) -> int | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    return _parse_int(details.get("active_game_instance_id"))


def _hero_record(payload: dict[str, Any], hero_id: int) -> dict[str, Any] | None:
    return merged_hero_record_for_specializations(payload, hero_id) or resolve_hero_record(
        payload, hero_id
    )


def _labels_for_choices(
    choice_ids: tuple[int, ...],
    options: list[SpecializationOption],
) -> tuple[str, ...]:
    by_id = {opt.upgrade_id: opt.name for opt in options}
    return tuple(by_id[uid] for uid in choice_ids if uid in by_id)


def _same_route_family(current: str, recommended: str) -> bool:
    current_cf = current.casefold()
    recommended_cf = recommended.casefold()
    if current_cf == recommended_cf:
        return True
    if current_cf in recommended_cf or recommended_cf in current_cf:
        return True
    words_current = {w for w in re.findall(r"[a-z0-9]+", current_cf) if len(w) > 3}
    words_recommended = {w for w in re.findall(r"[a-z0-9]+", recommended_cf) if len(w) > 3}
    shared = words_current & words_recommended
    return bool(shared & _ROUTE_FAMILY_WORDS)


def _is_meaningful_mismatch(
    current_labels: tuple[str, ...],
    recommended_label: str,
    *,
    rule_source_type: str,
    confidence: int,
) -> bool:
    if rule_source_type != "authored" or confidence < MISMATCH_MIN_CONFIDENCE:
        return False
    if not current_labels or not recommended_label.strip():
        return False
    recommended_cf = recommended_label.casefold()
    for current in current_labels:
        if current.casefold() == recommended_cf:
            return False
        if _same_route_family(current, recommended_label):
            return False
    return True


def _rule_for_champion(champion_name: str) -> Rule | None:
    dataset = cached_documentation_rules()
    for rule in dataset.rules:
        if champion_names_match(rule.champion, champion_name):
            return rule
    return None


def _has_formation_synergy_tag(rule: Rule | None) -> bool:
    if rule is None:
        return False
    tag_set = {tag.casefold() for tag in rule.tags}
    return bool(tag_set & FORMATION_SYNERGY_TAGS)


def _formation_context_from_payload(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
) -> FormationContext:
    highest_damage_hero_id = None
    seat_by_hero: dict[int, int] = {}
    details = payload.get("details")
    if isinstance(details, dict):
        party_id = _active_party_id(payload)
        for inst in details.get("game_instances") or []:
            if not isinstance(inst, dict):
                continue
            if _parse_int(inst.get("game_instance_id")) != party_id:
                continue
            stats = inst.get("stats")
            if isinstance(stats, dict):
                highest_damage_hero_id = _parse_int(
                    stats.get("this_reset_highest_damage_dealt_hero_id")
                )
            hero_in_seats = inst.get("hero_in_seats")
            if isinstance(hero_in_seats, dict):
                for seat_raw, hero_raw in hero_in_seats.items():
                    seat = _parse_int(seat_raw)
                    hero_id = _parse_int(hero_raw)
                    if seat is not None and hero_id is not None:
                        seat_by_hero[hero_id] = seat
            break
    for hero in formation:
        if hero.seat is not None:
            seat_by_hero.setdefault(hero.hero_id, hero.seat)
    return FormationContext(
        active_hero_ids=frozenset(h.hero_id for h in formation),
        highest_damage_hero_id=highest_damage_hero_id,
        familiar_count=familiar_party_count(payload),
        seat_by_hero=seat_by_hero,
    )


def _evaluate_hero_advice(
    *,
    payload: dict[str, Any],
    hero_id: int,
    hero_name: str,
    seat: int | None,
    options: list[SpecializationOption],
    run_goal: str,
    formation_ctx: FormationContext,
) -> AdviceResult | None:
    if not options:
        return None
    eval_ctx = build_evaluation_context(
        hero_id=hero_id,
        hero_name=hero_name,
        seat=seat,
        run_goal=run_goal,
        formation=formation_ctx,
        payload=payload,
    )
    return evaluate_specialization(eval_ctx, options)


def _insight_from_advice(
    *,
    hero_id: int,
    hero_name: str,
    seat: int | None,
    advice: AdviceResult,
    current_labels: tuple[str, ...],
    status: InsightStatus,
    priority: int,
    headline: str,
    detail: str,
) -> SpecializationInsight:
    return SpecializationInsight(
        hero_id=hero_id,
        hero_name=hero_name,
        seat=seat,
        recommended_label=advice.chosen_label or advice.specialization_key,
        current_labels=current_labels,
        status=status,
        rule_source_type=advice.rule_source_type,
        data_source_version=advice.data_source_version,
        confidence=advice.confidence,
        headline=headline,
        detail=detail,
        priority=priority,
    )


def _sorted_open_pending(open_pending: list) -> list:
    return sorted(
        open_pending,
        key=lambda item: (
            item.options[0].tier_index if item.options else 99,
            item.seat is None,
            item.seat or 99,
            item.hero_id,
        ),
    )


def _open_tier_insight(
    pending_item,
    *,
    run_goal: str,
) -> SpecializationInsight | None:
    tier_index = pending_item.options[0].tier_index if pending_item.options else 0
    tier_label = tier_index + 1
    options_text = " / ".join(option.name for option in pending_item.options)
    is_heuristic = pending_item.rule_source_type == "heuristic"
    priority = 4 if is_heuristic else 1
    quality = " (generieke placeholder)" if is_heuristic else ""

    if pending_item.desired_option_index is None:
        return SpecializationInsight(
            hero_id=pending_item.hero_id,
            hero_name=pending_item.hero_name,
            seat=pending_item.seat,
            recommended_label="(nog geen vaste keuze)",
            current_labels=(),
            status="open_tier",
            rule_source_type=pending_item.rule_source_type or "heuristic",
            data_source_version=pending_item.data_source_version or "v2_full",
            confidence=pending_item.confidence or 2,
            headline=f"Open specialization: {pending_item.hero_name}",
            detail=(
                f"Tier {tier_label} wacht op een keuze ({run_goal.replace('_', ' ')}). "
                f"Open opties: {options_text}. Er is nog geen vaste regel voor deze tier."
            ),
            priority=5,
        )

    chosen = pending_item.options[pending_item.desired_option_index].name
    return SpecializationInsight(
        hero_id=pending_item.hero_id,
        hero_name=pending_item.hero_name,
        seat=pending_item.seat,
        recommended_label=chosen,
        current_labels=(),
        status="open_tier",
        rule_source_type=pending_item.rule_source_type or "authored",
        data_source_version=pending_item.data_source_version or "v2_full",
        confidence=pending_item.confidence or 3,
        headline=f"Open specialization: {pending_item.hero_name}",
        detail=(
            f"Kies {chosen} voor tier {tier_label} "
            f"({run_goal.replace('_', ' ')}){quality}."
        ),
        priority=priority,
    )


def _utility_spec_mismatch_insight(
    *,
    payload: dict[str, Any],
    hero: FormationHero,
    formation: tuple[FormationHero, ...],
    utility: str,
    options: list[SpecializationOption],
    open_pending: list,
) -> SpecializationInsight | None:
    if open_pending:
        return None

    hero_record = _hero_record(payload, hero.hero_id)
    if hero_record is None:
        return None

    recommended = recommended_spec_for_speed_utility(
        hero,
        formation,
        utility=utility,  # type: ignore[arg-type]
    )
    if not recommended:
        return None

    current_ids = _current_choices(hero_record, options)
    current_labels = _labels_for_choices(current_ids, options)
    recommended_cf = recommended.casefold()
    if any(label.casefold() == recommended_cf for label in current_labels):
        return None
    if any(_same_route_family(label, recommended) for label in current_labels):
        return None

    task = "gem-farming" if utility == "gold" else "modron scavenging"
    return SpecializationInsight(
        hero_id=hero.hero_id,
        hero_name=hero.name,
        seat=hero.seat,
        recommended_label=recommended,
        current_labels=current_labels,
        status="mismatch",
        rule_source_type="authored",
        data_source_version="utility",
        confidence=5,
        headline=f"{hero.name}: utility-spec voor speed-team",
        detail=(
            f"Huidige keuze: {' / '.join(current_labels) or '—'}. "
            f"Aanbevolen voor {task} in speed-team: {recommended}."
        ),
        priority=2,
    )


def _insight_for_formation_hero(
    *,
    payload: dict[str, Any],
    hero: FormationHero,
    options: list[SpecializationOption],
    run_goal: str,
    formation_ctx: FormationContext,
    open_pending: list,
) -> SpecializationInsight | None:
    hero_open = [item for item in open_pending if item.hero_id == hero.hero_id]
    for pending_item in _sorted_open_pending(hero_open):
        insight = _open_tier_insight(pending_item, run_goal=run_goal)
        if insight is not None:
            return insight

    hero_record = _hero_record(payload, hero.hero_id)
    if hero_record is None:
        return None

    current_ids = _current_choices(hero_record, options)
    current_labels = _labels_for_choices(current_ids, options)
    advice = _evaluate_hero_advice(
        payload=payload,
        hero_id=hero.hero_id,
        hero_name=hero.name,
        seat=hero.seat,
        options=options,
        run_goal=run_goal,
        formation_ctx=formation_ctx,
    )
    if advice is None or advice.upgrade_id is None:
        return None

    recommended = advice.chosen_label or advice.specialization_key

    # Choice already made (and matches recommendation) → no advice to show.
    if advice.upgrade_id in current_ids:
        return None
    if current_labels and (
        any(label.casefold() == recommended.casefold() for label in current_labels)
        or any(_same_route_family(label, recommended) for label in current_labels)
    ):
        return None

    if _is_meaningful_mismatch(
        current_labels,
        recommended,
        rule_source_type=advice.rule_source_type,
        confidence=advice.confidence,
    ):
        return _insight_from_advice(
            hero_id=hero.hero_id,
            hero_name=hero.name,
            seat=hero.seat,
            advice=advice,
            current_labels=current_labels,
            status="mismatch",
            priority=2,
            headline=f"{hero.name}: overweeg andere spec",
            detail=(
                f"Huidige keuze: {' / '.join(current_labels)}. "
                f"Aanbevolen voor deze party: {recommended}. {advice.rationale}"
            ).strip(),
        )

    # No open dialog and no clear mismatch — stay quiet (don't keep "matches" tips).
    return None


def _bench_specialization_insights(
    *,
    payload: dict[str, Any],
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    in_party: set[int],
    known_by_hero: dict[int, list[SpecializationOption]],
    run_goal: str,
    goal: GoalMode,
    context: ContextMode,
    formation_ctx: FormationContext,
    roster_filter: AdventureRosterFilter | None = None,
) -> list[SpecializationInsight]:
    want_tags: set[str] = set()
    if context == "modron" or run_goal == "speed_farm" or goal == "speed":
        want_tags.add("speed")
    if goal == "gold" or run_goal == "gold_farm":
        want_tags.update({"gold", "favor"})
    if context == "push" and goal == "bud":
        want_tags.add("support")

    if not want_tags:
        return []

    insights: list[SpecializationInsight] = []
    for hero_id, name, _roles, _tags in owned:
        if hero_id in in_party:
            continue
        if not is_hero_allowed(hero_id, roster_filter):
            continue
        options = known_by_hero.get(hero_id, [])
        if not options:
            continue
        rule = _rule_for_champion(name)
        if rule is None:
            continue
        rule_tags = {tag.casefold() for tag in rule.tags}
        if not (rule_tags & want_tags):
            continue
        advice = _evaluate_hero_advice(
            payload=payload,
            hero_id=hero_id,
            hero_name=name,
            seat=None,
            options=options,
            run_goal=run_goal,
            formation_ctx=formation_ctx,
        )
        if advice is None or advice.rule_source_type != "authored":
            continue
        recommended = advice.chosen_label or advice.specialization_key
        insights.append(
            SpecializationInsight(
                hero_id=hero_id,
                hero_name=name,
                seat=None,
                recommended_label=recommended,
                current_labels=(),
                status="bench_suggestion",
                rule_source_type=advice.rule_source_type,
                data_source_version=advice.data_source_version,
                confidence=advice.confidence,
                headline=f"Op bench: {name}",
                detail=(
                    f"Overweeg {name} met {recommended} — past bij "
                    f"{goal}/{context} en vult een formatie-gap."
                ),
                priority=3,
            )
        )
        if len(insights) >= _BENCH_LIMIT:
            break
    return insights


def _party_has_speed_spec(formation: tuple[FormationHero, ...]) -> bool:
    for hero in formation:
        rule = _rule_for_champion(hero.name)
        if rule and "speed" in {tag.casefold() for tag in rule.tags}:
            return True
    return False


def _party_has_gold_spec(formation: tuple[FormationHero, ...]) -> bool:
    for hero in formation:
        rule = _rule_for_champion(hero.name)
        if rule and {"gold", "favor"} & {tag.casefold() for tag in rule.tags}:
            return True
    return False


def _party_specialization_composition_tips(
    formation: tuple[FormationHero, ...],
    insights: tuple[SpecializationInsight, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    run_goal: str,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
) -> list[AdvisorTip]:
    if len(formation) < 2:
        return []

    tips: list[AdvisorTip] = []
    insight_names = {ins.hero_name.casefold() for ins in insights}

    if (context == "modron" or goal == "speed") and not _party_has_speed_spec(formation):
        bench_speed = [
            ins
            for ins in insights
            if ins.status == "bench_suggestion"
            and "speed" in ins.recommended_label.casefold()
        ]
        detail = "Speed-specs (Briv, Widdle, Deekin) zijn belangrijk voor areas/uur."
        if bench_speed:
            detail += f" Op bench: {bench_speed[0].hero_name} → {bench_speed[0].recommended_label}."
        title = "Speed-specs voor Modron" if context == "modron" else "Geen speed-spec champion in party"
        tips.append(
            AdvisorTip(
                priority=2,
                title=title,
                detail=detail,
            )
        )

    if goal == "gold" and not _party_has_gold_spec(formation):
        detail = "Gold/favor-specs (Jarlaxle, Omin, Freely) versterken economy runs."
        gold_bench = [ins for ins in insights if ins.status == "bench_suggestion"]
        if gold_bench:
            detail += f" Op bench: {gold_bench[0].hero_name} → {gold_bench[0].recommended_label}."
        tips.append(
            AdvisorTip(
                priority=2,
                title="Geen gold-spec champion in party",
                detail=detail,
            )
        )

    asharra = next((h for h in formation if h.name.casefold() == "asharra"), None)
    if asharra and "asharra" not in insight_names:
        rule = _rule_for_champion("Asharra")
        if rule and "formation-dependent" in {t.casefold() for t in rule.tags}:
            tips.append(
                AdvisorTip(
                    priority=3,
                    title="Asharra: bond-spec afhankelijk van party",
                    detail="Kies de bond/spec die past bij dwarf/elf (of andere species) in je huidige formation.",
                )
            )

    return tips


def build_specialization_insights(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    roster_filter: AdventureRosterFilter | None = None,
) -> tuple[SpecializationInsight, ...]:
    if not formation:
        return ()

    rules = load_specialization_rules()
    known_by_hero = _merge_known_options(payload, rules)
    run_goal = advisor_run_goal(goal, context)
    formation_ctx = _formation_context_from_payload(payload, formation)
    all_pending = pending_specializations(payload, rules, context=context, run_goal=run_goal)

    insights: list[SpecializationInsight] = []
    for hero in formation:
        options = known_by_hero.get(hero.hero_id, [])
        if not options:
            continue
        hero_open = [p for p in all_pending if p.hero_id == hero.hero_id]
        utility = speed_utility_role(hero, goal)
        hero_run_goal = run_goal
        if utility == "gold":
            hero_run_goal = "gold_farm"
        elif utility == "modron":
            hero_run_goal = "generic_progression"
        insight = _insight_for_formation_hero(
            payload=payload,
            hero=hero,
            options=options,
            run_goal=hero_run_goal,
            formation_ctx=formation_ctx,
            open_pending=hero_open,
        )
        if insight is None and utility is not None:
            insight = _utility_spec_mismatch_insight(
                payload=payload,
                hero=hero,
                formation=formation,
                utility=utility,
                options=options,
                open_pending=hero_open,
            )
        if insight is not None:
            insights.append(insight)

    in_party = {h.hero_id for h in formation}
    owned = _owned_from_payload(payload)
    insights.extend(
        _bench_specialization_insights(
            payload=payload,
            owned=owned,
            in_party=in_party,
            known_by_hero=known_by_hero,
            run_goal=run_goal,
            goal=goal,
            context=context,
            formation_ctx=formation_ctx,
            roster_filter=roster_filter,
        )
    )

    insights.sort(key=lambda item: (item.priority, item.hero_name))
    return tuple(insights[:MAX_INSIGHTS])


def _owned_from_payload(payload: dict[str, Any]) -> list[tuple[int, str, tuple[str, ...], tuple[str, ...]]]:
    from ic_gamedata.party_advisor import _owned_heroes

    return _owned_heroes(payload)


def party_specialization_composition_tips(
    formation: tuple[FormationHero, ...],
    insights: tuple[SpecializationInsight, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
) -> list[AdvisorTip]:
    return _party_specialization_composition_tips(
        formation,
        insights,
        goal=goal,
        context=context,
        run_goal=advisor_run_goal(goal, context),
        owned=owned,
    )


def spec_summary_for_hero(
    hero_id: int,
    insights: tuple[SpecializationInsight, ...],
) -> str | None:
    for insight in insights:
        if insight.hero_id != hero_id or insight.status == "bench_suggestion":
            continue
        if insight.status == "open_tier":
            return f"Spec: kies {insight.recommended_label} ({insight.rule_source_type})"
        if insight.status == "mismatch":
            return f"Spec: overweeg {insight.recommended_label} (nu: {' / '.join(insight.current_labels)})"
    return None


def current_spec_labels_for_hero(
    payload: dict[str, Any],
    hero_id: int,
    insights: tuple[SpecializationInsight, ...],
) -> tuple[str, ...]:
    for insight in insights:
        if insight.hero_id == hero_id and insight.current_labels:
            return insight.current_labels

    rules = load_specialization_rules()
    known_by_hero = _merge_known_options(payload, rules)
    options = known_by_hero.get(hero_id, [])
    hero_record = _hero_record(payload, hero_id)
    if hero_record is None or not options:
        return ()

    from ic_gamedata.specializations import _current_choices

    return _labels_for_choices(_current_choices(hero_record, options), options)


def resolve_spec_display_status(
    hero_id: int,
    insights: tuple[SpecializationInsight, ...],
    *,
    recommended: str | None,
    current_labels: tuple[str, ...],
) -> SpecDisplayStatus | None:
    """Classify specialization advice for UI coloring."""
    if not recommended:
        return None

    for insight in insights:
        if insight.hero_id != hero_id or insight.status == "bench_suggestion":
            continue
        if insight.status == "open_tier":
            return "pending"

    if not current_labels:
        return "pending"

    recommended_cf = recommended.casefold()
    recommended_parts = _recommended_label_parts(recommended)
    if recommended_parts and all(
        any(part.casefold() == label.casefold() for label in current_labels)
        for part in recommended_parts
    ):
        return "match"
    if any(label.casefold() == recommended_cf for label in current_labels):
        return "match"
    if any(_same_route_family(label, recommended) for label in current_labels):
        return "match"

    return "mismatch"


def spec_summary_line(
    hero_name: str,
    *,
    recommended: str,
    current_labels: tuple[str, ...],
    status: SpecDisplayStatus,
    is_bud: bool = False,
) -> str:
    label = f"{hero_name} (BUD)" if is_bud else hero_name
    current = " / ".join(current_labels)
    if status == "match":
        return f"{label}: {recommended}"
    if status == "mismatch" and current:
        return f"{label}: {current} → {recommended}"
    return f"{label}: {recommended}"
