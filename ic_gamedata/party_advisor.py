"""Party advisor: formation and gear analysis from getuserdetails payload."""

from __future__ import annotations

from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.parsing import parse_number as _parse_number
from ic_gamedata.party_advisor_formation import (
    _active_game_instance,
    _adventure_modifiers,
    _adventure_name,
    _bench_suggestions,
    _coverage_from_formation_insights,
    _formation_heroes,
    _human_buff_note,
    _is_actionable_adventure_rule,
    _is_buffer,
    _is_debuffer,
    _is_dps,
    _is_speed,
    _is_tank,
    _is_useful_adventure_note,
    _loot_ilvl_by_hero,
    _owned_heroes,
    _resolve_bud_hero,
    _resolve_speed_hero,
    _seat_zone_guess,
)
from ic_gamedata.party_advisor_models import (
    AdvisorReport,
    AdvisorTip,
    ContextMode,
    FormationHero,
    GoalMode,
    HeroImprovement,
    goal_label,
)
from ic_gamedata.party_advisor_scoring import (
    _build_improvements,
    _composition_advice,
    _filter_relevant_formation_tips,
    _formation_tips,
)


def analyze_party(
    payload: dict[str, Any],
    *,
    goal: GoalMode,
    context: ContextMode,
    include_specializations: bool = True,
    include_formation: bool = True,
) -> AdvisorReport:
    """Build advisor report from raw getuserdetails JSON."""
    instance = _active_game_instance(payload) or {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}

    adventure_id = _parse_int(instance.get("current_adventure_id") or details.get("current_adventure_id"))
    adventure_name = _adventure_name(payload, adventure_id)
    modifiers = _adventure_modifiers(payload, adventure_id)

    from ic_gamedata.adventure_restrictions import (
        build_adventure_roster_filter,
        player_formation_capacity,
        restriction_summary,
    )

    roster_filter = build_adventure_roster_filter(payload, adventure_id)
    restrictions_note = restriction_summary(roster_filter)
    player_capacity = player_formation_capacity(payload, adventure_id)

    adventure_data = instance.get("adventure_data")
    if not isinstance(adventure_data, dict):
        adventure_data = details.get("adventure_data") if isinstance(details.get("adventure_data"), dict) else {}
    gold_growth = _parse_number(adventure_data.get("gold_growth_rate"))

    stats = instance.get("stats") if isinstance(instance.get("stats"), dict) else {}
    global_mult = _parse_number(stats.get("global_dps_multiplier"))

    formation = _formation_heroes(payload)
    owned = _owned_heroes(payload)
    adventure_buff_note = _human_buff_note(global_mult)
    improvements = _build_improvements(
        formation,
        goal=goal,
        context=context,
        owned=owned,
        modifiers=modifiers,
    )

    formation_insights: tuple[Any, ...] = ()
    if include_formation and formation:
        from ic_gamedata.formation_advisor import build_formation_insights

        formation_insights = build_formation_insights(
            payload,
            formation,
            goal=goal,
            context=context,
            roster_filter=roster_filter,
        )

    covered = _coverage_from_formation_insights(formation_insights)

    ilvl_by_hero = _loot_ilvl_by_hero(details) if isinstance(details, dict) else {}

    tips = _formation_tips(
        formation,
        goal=goal,
        context=context,
        owned=owned,
        modifiers=modifiers,
        adventure_buff_note=adventure_buff_note,
        gold_growth_rate=gold_growth,
        roster_filter=roster_filter,
        covered=covered,
        ilvl_by_hero=ilvl_by_hero,
        player_capacity=player_capacity,
    )

    specialization_insights: tuple[Any, ...] = ()
    if include_specializations and formation:
        from ic_gamedata.party_advisor_specializations import (
            build_specialization_insights,
            party_specialization_composition_tips,
        )

        specialization_insights = build_specialization_insights(
            payload,
            formation,
            goal=goal,
            context=context,
            roster_filter=roster_filter,
        )
        spec_tips = party_specialization_composition_tips(
            formation,
            specialization_insights,
            goal=goal,
            context=context,
            owned=owned,
        )
        if spec_tips:
            combined = list(tips) + spec_tips
            combined.sort(key=lambda item: item.priority)
            tips = tuple(
                AdvisorTip(priority=index, title=tip.title, detail=tip.detail)
                for index, tip in enumerate(combined, start=1)
            )

    seat_report = None
    if formation:
        from ic_gamedata.seat_advisor import build_seat_advisor_report

        seat_report = build_seat_advisor_report(
            payload,
            formation,
            goal=goal,
            context=context,
            formation_insights=formation_insights,
            specialization_insights=specialization_insights,
            roster_filter=roster_filter,
        )

    tips = _filter_relevant_formation_tips(
        tips,
        has_seat_report=seat_report is not None and bool(seat_report.seats),
    )

    main_name = (_resolve_bud_hero(formation) or formation[0]).name if formation else None
    if goal == "bud":
        summary = (
            f"BUD-advies — {adventure_name}: focus op {main_name}."
            if main_name
            else f"BUD-advies — {adventure_name}."
        )
    elif goal == "speed":
        speed_name = (_resolve_speed_hero(formation) or (formation[0] if formation else None))
        speed_label = speed_name.name if speed_name is not None else None
        summary = (
            f"Speed-advies — {adventure_name}: focus op {speed_label}."
            if speed_label
            else f"Speed-advies — {adventure_name}."
        )
    else:
        summary = f"Gold-advies — {adventure_name}."

    return AdvisorReport(
        goal=goal,
        context=context,
        adventure_name=adventure_name,
        adventure_id=adventure_id,
        gold_growth_rate=gold_growth,
        adventure_buff_note=adventure_buff_note,
        main_dps_name=main_name,
        formation_heroes=formation,
        improvements=tuple(improvements),
        tips=tuple(tips),
        summary=summary,
        specialization_insights=specialization_insights,
        adventure_restrictions_note=restrictions_note,
        formation_insights=formation_insights,
        seat_report=seat_report,
    )


def _seat_text(seat: int | None) -> str:
    return f"slot {seat}" if seat is not None else "—"


def _improvements_for_hero(
    improvements: tuple[HeroImprovement, ...] | list[HeroImprovement],
    hero: FormationHero,
) -> list[HeroImprovement]:
    matched: list[HeroImprovement] = []
    for item in improvements:
        if (item.seat is not None and hero.seat is not None and item.seat == hero.seat) or (item.seat is None and item.hero_name == hero.name):
            matched.append(item)
    return matched


def _global_improvements(
    improvements: tuple[HeroImprovement, ...] | list[HeroImprovement],
) -> list[HeroImprovement]:
    return [item for item in improvements if item.hero_name is None]


def _heroes_by_seat(formation: tuple[FormationHero, ...]) -> list[FormationHero]:
    return sorted(formation, key=lambda hero: (hero.seat is None, hero.seat or 0, hero.name))


def format_report(report: AdvisorReport) -> str:
    """Human-readable report: party list with inline improve notes + tips."""
    goal_label_text = goal_label(report.goal)
    context_labels = {
        "campaign": "Campaign",
        "events": "Events",
        "push": "Push",
        "modron": "Modron",
    }

    lines = [
        report.summary,
        "",
        f"Doel: {goal_label_text}   ·   Context: {context_labels.get(report.context, report.context)}",
        f"Adventure: {report.adventure_name}",
    ]
    if report.gold_growth_rate is not None and report.goal == "gold":
        lines.append(f"Gold scaling adventure: {report.gold_growth_rate:.2f}×")
    if report.adventure_restrictions_note:
        lines.append(f"Champion-beperkingen: {report.adventure_restrictions_note}")

    lines.extend(["", "Party", "-" * 40])
    for item in _global_improvements(report.improvements):
        lines.append(f"! {item.headline}")
        lines.append(f"  → {item.action}")
        lines.append("")

    if not report.formation_heroes:
        lines.append("  Geen champions in actieve slots.")
    else:
        main_id = None
        bud = _resolve_bud_hero(report.formation_heroes)
        if bud is not None:
            main_id = bud.hero_id
        for hero in _heroes_by_seat(report.formation_heroes):
            notes: list[str] = []
            if hero.hero_id == main_id:
                notes.append("main focus")
            if hero.is_top_damage:
                notes.append("hardste hit")
            note_text = f" · {' · '.join(notes)}" if notes else ""
            lines.append(
                f"{hero.name} · {_seat_text(hero.seat)} · {hero.role_label} · {hero.gear_label}{note_text}"
            )
            for item in _improvements_for_hero(report.improvements, hero):
                if item.headline.lower() in item.action.lower():
                    lines.append(f"  → {item.action}")
                else:
                    lines.append(f"  → {item.headline}: {item.action}")
            if report.specialization_insights:
                from ic_gamedata.party_advisor_specializations import spec_summary_for_hero

                spec_line = spec_summary_for_hero(hero.hero_id, report.specialization_insights)
                if spec_line:
                    lines.append(f"  → {spec_line}")
            lines.append("")

    if report.specialization_insights:
        lines.extend(["Specialization & formatie", "-" * 40])
        for insight in report.specialization_insights:
            seat = _seat_text(insight.seat)
            lines.append(f"[{insight.priority}] {insight.headline} ({seat})")
            lines.append(f"    {insight.detail}")
            if insight.rule_source_type == "heuristic":
                lines.append("    (generieke placeholder-regel)")
            lines.append("")

    if report.formation_insights:
        lines.extend(["Formatie & posities", "-" * 40])
        for insight in report.formation_insights:
            seat = _seat_text(insight.seat)
            extra = ""
            if insight.related_seat is not None and insight.related_hero_name:
                extra = f" ↔ {insight.related_hero_name} ({_seat_text(insight.related_seat)})"
            elif insight.related_seat is not None:
                extra = f" → slot {insight.related_seat}"
            lines.append(f"[{insight.priority}] {insight.headline} ({seat}{extra})")
            lines.append(f"    {insight.detail}")
            if insight.rule_source_type == "heuristic":
                lines.append("    (heuristiek)")
            lines.append("")

    if report.tips:
        lines.extend(["Formation-tips", "-" * 40])
        for tip in report.tips:
            lines.append(f"[{tip.priority}] {tip.title}")
            lines.append(f"    {tip.detail}")
            lines.append("")

    return "\n".join(lines).rstrip()


__all__ = [
    "AdvisorReport",
    "AdvisorTip",
    "ContextMode",
    "FormationHero",
    "GoalMode",
    "HeroImprovement",
    "analyze_party",
    "format_report",
    "goal_label",
]
