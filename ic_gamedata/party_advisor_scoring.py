"""Composition scoring, tips, and improvement suggestions for party advisor."""

from __future__ import annotations

from typing import Any

from ic_gamedata.party_advisor_formation import (
    _RELATIVE_GEAR_WEAK_PCT,
    _bench_suggestions,
    _ilvl_below_avg_action,
    _is_actionable_adventure_rule,
    _is_buffer,
    _is_debuffer,
    _is_dps,
    _is_speed,
    _is_tank,
    _resolve_bud_hero,
    _resolve_speed_hero,
    _seat_zone_guess,
)
from ic_gamedata.party_advisor_models import (
    AdvisorTip,
    ContextMode,
    FormationHero,
    GoalMode,
    HeroImprovement,
)


def _seat_text(seat: int | None) -> str:
    return f"seat {seat}" if seat is not None else "bench"


def _disallowed_replacement_detail(
    formation: tuple[FormationHero, ...],
    disallowed_heroes: list[FormationHero],
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    roster_filter: Any,
    *,
    goal: GoalMode,
    context: ContextMode,
    ilvl_by_hero: dict[int, int] | None = None,
    limit_per_hero: int = 2,
) -> str | None:
    if not disallowed_heroes or roster_filter is None:
        return None

    from ic_gamedata.seat_advisor.bench_ranker import rank_bench_alternatives
    from ic_gamedata.seat_advisor.role_inference import infer_seat_role

    in_party = {hero.hero_id for hero in formation}
    bud = _resolve_bud_hero(formation)
    bud_id = bud.hero_id if bud else None
    ilvl_map = ilvl_by_hero or {}
    parts: list[str] = []

    for hero in disallowed_heroes:
        seat = hero.seat or 1
        role = infer_seat_role(
            hero,
            zone=_seat_zone_guess(seat),
            bud_hero_id=bud_id,
            goal=goal,
            context=context,
        )
        alternatives = rank_bench_alternatives(
            role=role,
            current_hero=hero,
            owned=owned,
            in_party=in_party,
            roster_filter=roster_filter,
            ilvl_by_hero=ilvl_map,
            limit=limit_per_hero,
        )
        seat_txt = f" (slot {hero.seat})" if hero.seat is not None else ""
        if alternatives:
            names = ", ".join(alt.hero_name for alt in alternatives)
            parts.append(f"{hero.name}{seat_txt} → {names}")
            continue

        fallback = _bench_suggestions(
            owned,
            in_party,
            roster_filter=roster_filter,
            limit=limit_per_hero,
        )
        if fallback:
            parts.append(f"{hero.name}{seat_txt} → {', '.join(fallback)} (bench)")
        else:
            parts.append(f"{hero.name}: geen toegestane vervanger op bench")

    if not parts:
        return None
    return "Alternatieven: " + " · ".join(parts)


def _composition_advice(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    roster_filter: Any | None = None,
    covered: frozenset[str] = frozenset(),
    player_capacity: int | None = None,
) -> list[AdvisorTip]:
    """Formatie-/samenstellingsadvies — alleen als er iets nuttigs te verbeteren valt."""
    if len(formation) < 2:
        return []

    tips: list[AdvisorTip] = []
    main = _resolve_bud_hero(formation) or formation[0]
    in_party = {h.hero_id for h in formation}
    tanks = [h for h in formation if _is_tank(h)]
    dps = [h for h in formation if _is_dps(h)]
    supports = [h for h in formation if "support" in h.roles]
    speed = [h for h in formation if _is_speed(h)]
    buffers = [h for h in formation if _is_buffer(h)]

    # Te weinig champions in formation (formation advisor covers this when enabled)
    if player_capacity is not None:
        is_underfilled = len(formation) < player_capacity
        capacity_label = player_capacity
    else:
        is_underfilled = len(formation) <= 7
        capacity_label = None

    if is_underfilled and "formation_not_full" not in covered:
        if capacity_label is not None:
            detail = (
                f"Je hebt {len(formation)} van {capacity_label} beschikbare champion-slots gevuld "
                "(NPC-slots tellen niet mee). "
                "Vul lege slots met supports/buffers — dat levert meestal meer op dan een extra DPS."
            )
        else:
            detail = (
                f"Je hebt {len(formation)} champions in formation. "
                "Vul lege slots met supports/buffers — dat levert meestal meer op dan een extra DPS."
            )
        tips.append(_tip(2, "Formatie niet vol", detail))

    # Geen tank waar overleving telt
    if not tanks and context in ("push", "campaign"):
        suggestions = _bench_suggestions(
            owned, in_party, want_roles={"tank"}, roster_filter=roster_filter
        )
        detail = "Zet een tank vooraan (bijv. Nayeli, Briv, Torogar) om langer te overleven."
        if suggestions:
            detail += f" Op de bank: {', '.join(suggestions)}."
        tips.append(_tip(2, "Geen tank in formation", detail))

    # Te veel DPS, te weinig support — alleen bij BUD
    if goal == "bud" and len(dps) >= 3 and len(buffers) <= 1:
        dps_names = ", ".join(h.name for h in dps[:4])
        tips.append(
            _tip(
                2,
                "Te veel DPS t.o.v. support",
                f"DPS in party: {dps_names}. Focus buffs op één carry ({main.name}) "
                "of wissel een DPS om voor een buffer/support.",
            )
        )

    # Carry heeft geen DPS-rol
    if goal == "bud" and not _is_dps(main) and dps:
        tips.append(
            _tip(
                2,
                f"Carry-focus: {main.name} is geen DPS",
                f"{main.name} heeft de sterkste instrument-score, maar {dps[0].name} "
                "heeft wel een DPS-rol. Overweeg buffs/debuffers op die DPS te richten.",
            )
        )

    # Speed / Modron zonder speed champion
    if (goal == "speed" or context == "modron") and not speed and "modron_no_speed" not in covered:
        suggestions = _bench_suggestions(
            owned, in_party, want_tags={"speed"}, roster_filter=roster_filter
        )
        detail = "Voor areas/uur helpt een speed champion (Briv, Hank, Widdle, Deekin)."
        if suggestions:
            detail += f" Beschikbaar: {', '.join(suggestions)}."
        priority = 1 if goal == "speed" else 2
        tips.append(_tip(priority, "Geen speed champion", detail))

    # Push zonder debuffer + zonder tank is already covered separately;
    # Push met veel healers/tanks maar weinig DPS
    if context == "push" and goal == "bud" and len(dps) == 0:
        tips.append(
            _tip(
                1,
                "Geen DPS in push-formation",
                "Aan je wall wil je minstens één dedicated single-target DPS als carry.",
            )
        )

    # Support-arme party — skip when formation advisor already flagged buffer placement
    if (
        goal == "bud"
        and len(supports) <= 1
        and len(formation) >= 8
        and "buffer_placement" not in covered
        and not any(t.title.startswith("Te veel DPS") for t in tips)
    ):
        tips.append(
            _tip(
                3,
                "Weinig support in formation",
                f"Met bijna alleen DPS/tank mist je positional buffs. "
                f"Voeg een buffer toe naast BUD {main.name} ({_seat_text(main.seat)}).",
            )
        )

    return tips


def _build_improvements(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    modifiers: list[str],
) -> list[HeroImprovement]:
    if not formation:
        return [
            HeroImprovement(
                priority=1,
                hero_name=None,
                seat=None,
                headline="Geen actieve formation gevonden",
                action="Start een adventure in Idle Champions en klik opnieuw op Analyseer party.",
            )
        ]

    items: list[HeroImprovement] = []
    main = _resolve_bud_hero(formation) or formation[0]
    top_damage = next((h for h in formation if h.is_top_damage), None)
    party_avg_ilvl = sum(hero.ilvl for hero in formation) / len(formation)

    if goal == "bud":
        if (
            top_damage is not None
            and top_damage.hero_id != main.hero_id
            and not main.is_top_damage
        ):
            items.append(
                HeroImprovement(
                    priority=2,
                    hero_name=top_damage.name,
                    seat=top_damage.seat,
                    headline="Hardste hit deze run",
                    action=(
                        f"De game registreerde de zwaarste hit op {top_damage.name} "
                        f"({_seat_text(top_damage.seat)}), niet op BUD-focus {main.name}. "
                        "Overweeg buffs te verschuiven als dit consistent blijft."
                    ),
                )
            )

        for hero in formation:
            if hero.hero_id == main.hero_id:
                continue
            if hero.ilvl_pct_vs_avg < -_RELATIVE_GEAR_WEAK_PCT:
                items.append(
                    HeroImprovement(
                        priority=2,
                        hero_name=hero.name,
                        seat=hero.seat,
                        headline="Gear onder party-gemiddelde",
                        action=_ilvl_below_avg_action(hero.ilvl, hero.ilvl_pct_vs_avg, party_avg_ilvl),
                    )
                )

        for hero in formation:
            if hero.active_feats == 0 and hero.role_label in ("DPS", "Onbekend"):
                items.append(
                    HeroImprovement(
                        priority=3,
                        hero_name=hero.name,
                        seat=hero.seat,
                        headline="Geen actief feat",
                        action="Zet een damage- of speed-feat aan als je die unlocked hebt.",
                    )
                )

        if context == "push" or context == "modron":
            pass

    elif goal == "speed":
        speed_main = _resolve_speed_hero(formation)
        if speed_main is None:
            suggestions = _bench_suggestions(
                owned, {h.hero_id for h in formation}, want_tags={"speed"}, roster_filter=None
            )
            action = "Zet een speed champion in party voor kortere runs (Briv, Widdle, Deekin, Hank)."
            if suggestions:
                action += f" Op bench: {', '.join(suggestions)}."
            items.append(
                HeroImprovement(
                    priority=1,
                    hero_name=None,
                    seat=None,
                    headline="Geen speed champion in formation",
                    action=action,
                )
            )
        else:
            if speed_main.active_feats == 0:
                items.append(
                    HeroImprovement(
                        priority=2,
                        hero_name=speed_main.name,
                        seat=speed_main.seat,
                        headline="Geen actief feat",
                        action="Zet een speed- of utility-feat aan op je speed carry.",
                    )
                )
            for hero in formation:
                if hero.hero_id == speed_main.hero_id:
                    continue
                if hero.ilvl_pct_vs_avg < -_RELATIVE_GEAR_WEAK_PCT:
                    items.append(
                        HeroImprovement(
                            priority=3,
                            hero_name=hero.name,
                            seat=hero.seat,
                            headline="Gear onder party-gemiddelde",
                            action=_ilvl_below_avg_action(
                                hero.ilvl, hero.ilvl_pct_vs_avg, party_avg_ilvl
                            ),
                        )
                    )

    elif goal == "gold":
        for hero in formation:
            if hero.ilvl_pct_vs_avg < -_RELATIVE_GEAR_WEAK_PCT and hero.hero_id != main.hero_id:
                items.append(
                    HeroImprovement(
                        priority=2,
                        hero_name=hero.name,
                        seat=hero.seat,
                        headline="Gear onder party-gemiddelde",
                        action=_ilvl_below_avg_action(hero.ilvl, hero.ilvl_pct_vs_avg, party_avg_ilvl),
                    )
                )

    items.sort(key=lambda item: item.priority)
    return items


def _formation_tips(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    owned: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]],
    modifiers: list[str],
    adventure_buff_note: str | None,
    gold_growth_rate: float | None,
    roster_filter: Any | None = None,
    covered: frozenset[str] = frozenset(),
    ilvl_by_hero: dict[int, int] | None = None,
    player_capacity: int | None = None,
) -> list[AdvisorTip]:
    """Tactische formation-tips met uitleg (zoals debuffer-advies)."""
    if not formation:
        return [
            _tip(
                1,
                "Geen formation gevonden",
                "Start een adventure in Idle Champions en klik opnieuw op Analyseer party.",
            )
        ]

    tips: list[AdvisorTip] = []
    main = _resolve_bud_hero(formation) or formation[0]
    debuffers = [h for h in formation if _is_debuffer(h)]
    buffers = [h for h in formation if _is_buffer(h)]

    if goal == "bud":
        if main.is_top_damage:
            tips.append(
                _tip(
                    1,
                    f"BUD deze run: {main.name}",
                    (
                        f"De game registreerde de hardste hit op {main.name} "
                        f"({_seat_text(main.seat)}, {main.gear_label}). "
                        "Richt buffers, debuffers en positional buffs op deze champion."
                    ),
                )
            )
        else:
            tips.append(
                _tip(
                    1,
                    f"BUD-focus: {main.name}",
                    (
                        f"Verwachte carry voor BUD-stacking: {main.name} "
                        f"({_seat_text(main.seat)}, {main.gear_label}). "
                        "Nog geen harde hit geregistreerd deze reset — stack buffs hier naarmate damage opbouwt."
                    ),
                )
            )

        if not debuffers and "carry_no_debuffer" not in covered:
            tips.append(
                _tip(
                    2,
                    f"Geen debuffer voor {main.name}",
                    (
                        f"Debuffers verhogen BUD op {main.name} via zware debuff-hits. "
                        "Overweeg Krull, Aila, Gromma, Spurt, Warden of Sisaspia in party."
                    ),
                )
            )

        if len(buffers) == 0 and "buffer_placement" not in covered:
            tips.append(
                _tip(
                    3,
                    f"Weinig buffers voor {main.name}",
                    (
                        f"Champions als Avren, Celeste, Birdsong en Gale verhogen single-target hits. "
                        f"Zet een buffer naast BUD {main.name} ({_seat_text(main.seat)})."
                    ),
                )
            )

        if context == "push":
            tips.append(
                _tip(
                    2,
                    "Push-modus",
                    f"Focus op één single-target DPS ({main.name}) plus debuffers. "
                    "AoE-champions zijn minder efficiënt aan je wall.",
                )
            )
        elif context == "modron":
            tips.append(
                _tip(
                    3,
                    "Modron-modus",
                    "BUD is hier minder belangrijk dan areas/uur. "
                    "Kies speed/support (Briv, Hank) boven pure BUD-stacking.",
                )
            )
        elif context == "events":
            tips.append(
                _tip(
                    3,
                    "Events-modus",
                    f"Check event-boons en variant-restrictions. "
                    f"Debuffer-stacking blijft sterk voor BUD {main.name}.",
                )
            )

        if adventure_buff_note:
            tips.append(
                _tip(
                    3,
                    "Adventure damage-buff",
                    adventure_buff_note,
                )
            )

    elif goal == "speed":
        speed_main = _resolve_speed_hero(formation)
        speed = [h for h in formation if _is_speed(h)]
        in_party = {h.hero_id for h in formation}
        from ic_gamedata.adventure_restrictions import is_hero_allowed

        if speed_main is not None:
            tips.append(
                _tip(
                    1,
                    f"Speed focus: {speed_main.name}",
                    (
                        f"Areas/uur draait om snelle clears — focus specs/feats op "
                        f"{speed_main.name} ({_seat_text(speed_main.seat)}, {speed_main.gear_label}). "
                        "Combineer met genoeg DPS/support om areas vlot te resetten."
                    ),
                )
            )
        else:
            bench_speed = [
                name
                for hid, name, roles, tags in owned
                if "speed" in tags
                and hid not in in_party
                and is_hero_allowed(hid, roster_filter)
            ]
            detail = "Zonder speed champion mis je areas/uur. Briv, Widdle, Deekin en Hank zijn gangbare keuzes."
            if bench_speed:
                detail += " Op bench: " + ", ".join(bench_speed[:4]) + "."
            tips.append(_tip(1, "Geen speed champion in formation", detail))

        if len(speed) > 1:
            names = ", ".join(h.name for h in speed)
            tips.append(
                _tip(
                    3,
                    f"Meerdere speed champions: {names}",
                    "Meestal volstaat één primary speed carry; extra slots zijn beter voor DPS/support.",
                )
            )

        dps = [h for h in formation if _is_dps(h)]
        if len(dps) == 0:
            tips.append(
                _tip(
                    2,
                    "Weinig DPS voor speed runs",
                    "Speed stacking helpt pas als je areas snel genoeg cleart — voeg minstens één carry toe.",
                )
            )

        if context == "modron":
            tips.append(
                _tip(
                    2,
                    "Modron farming",
                    "Korte resets en hoge areas/uur zijn het doel — prioriteer speed-specs en snelle kills.",
                )
            )
        elif context == "campaign":
            tips.append(
                _tip(
                    3,
                    "Campaign speed",
                    "Farm favor/gold sneller door areas kort te houden met speed + burst DPS.",
                )
            )

    elif goal == "gold":
        if gold_growth_rate is not None:
            tips.append(
                _tip(
                    1,
                    f"Gold growth rate: {gold_growth_rate:.2f}×",
                    "Hogere waarde = meer gold per kill op dit adventure.",
                )
            )

        gold_in_party = [h for h in formation if "gold" in h.tags or "gold" in h.roles]
        in_party = {h.hero_id for h in formation}
        from ic_gamedata.adventure_restrictions import is_hero_allowed

        bench_gold = [
            name
            for hid, name, roles, tags in owned
            if ("gold" in tags or "gold" in roles)
            and hid not in in_party
            and is_hero_allowed(hid, roster_filter)
        ]

        if gold_in_party:
            names = ", ".join(h.name for h in gold_in_party)
            tips.append(
                _tip(
                    1,
                    f"Gold champion(s) in formation: {names}",
                    "Houd gold-champions in party voor campaign/event farming.",
                )
            )
        elif bench_gold and "gold_no_gold_role" not in covered:
            tips.append(
                _tip(
                    1,
                    "Geen gold champion in formation",
                    "Overweeg: "
                    + ", ".join(bench_gold[:4])
                    + ". Jarlaxle, Pisl, Freely en Ellywick zijn gangbare keuzes.",
                )
            )
        else:
            tips.append(
                _tip(
                    2,
                    "Geen gold specialist gevonden",
                    "Unlock Jarlaxle (gold) of Pisl voor dedicated gold income.",
                )
            )

        tips.append(
            _tip(
                2,
                "Kill speed = gold speed",
                f"Sterkste gear: {main.name}. Sneller areas clearen levert meer gold op, "
                "vooral zonder dedicated gold champion.",
            )
        )

        if context == "campaign":
            tips.append(
                _tip(
                    2,
                    "Campaign farming",
                    "Combineer gold champion met voldoende DPS om areas snel te clearen. "
                    "Patron currency is apart — kies de juiste patron per adventure.",
                )
            )
        elif context == "events":
            tips.append(
                _tip(
                    2,
                    "Event farming",
                    "Prioriteit: event tokens (Strongheart e.a.) boven raw gold. "
                    "Check event-boons in game voor bonuses.",
                )
            )
        elif context == "push":
            tips.append(
                _tip(
                    3,
                    "Push / wall",
                    "Gold income is hier niet de bottleneck — focus op DPS om verder te push.",
                )
            )
        elif context == "modron":
            tips.append(
                _tip(
                    2,
                    "Modron farming",
                    "Areas/uur telt meer dan gold/uur. Gebruik speed champions (Briv) en korte resets.",
                )
            )

    for note in modifiers[:2]:
        if _is_actionable_adventure_rule(note):
            tips.append(_tip(3, "Adventure-regel", note))

    if roster_filter is not None and formation:
        from ic_gamedata.adventure_restrictions import is_hero_allowed, restriction_summary

        formation_ids = frozenset(hero.hero_id for hero in formation)
        disallowed_heroes = [
            hero
            for hero in formation
            if not is_hero_allowed(hero.hero_id, roster_filter, formation_hero_ids=formation_ids)
        ]
        if disallowed_heroes:
            summary = restriction_summary(roster_filter)
            detail = (
                f"{', '.join(hero.name for hero in disallowed_heroes)} voldoen niet aan de adventure-beperkingen"
                + (f" ({summary})." if summary else ".")
            )
            replacement = _disallowed_replacement_detail(
                formation,
                disallowed_heroes,
                owned,
                roster_filter,
                goal=goal,
                context=context,
                ilvl_by_hero=ilvl_by_hero,
            )
            if replacement:
                detail = f"{detail} {replacement}"
            tips.append(_tip(1, "Champions niet toegestaan op dit adventure", detail))

    tips.extend(
        _composition_advice(
            formation,
            goal=goal,
            context=context,
            owned=owned,
            roster_filter=roster_filter,
            covered=covered,
            player_capacity=player_capacity,
        )
    )

    tips.sort(key=lambda t: t.priority)
    return [
        AdvisorTip(priority=index, title=tip.title, detail=tip.detail)
        for index, tip in enumerate(tips, start=1)
    ]


def _tip(priority: int, title: str, detail: str) -> AdvisorTip:
    return AdvisorTip(priority=priority, title=title, detail=detail)


_GENERIC_FORMATION_TIP_TITLES = frozenset(
    {
        "adventure damage-buff",
        "adventure-regel",
        "push-modus",
        "modron-modus",
        "events-modus",
        "campaign farming",
        "event farming",
        "push / wall",
        "modron farming",
        "kill speed = gold speed",
    }
)


def _is_relevant_formation_tip(tip: AdvisorTip, *, has_seat_report: bool) -> bool:
    """Drop open-deur tips that duplicate seat cards or state the obvious."""
    title = tip.title.casefold().strip()
    if has_seat_report and (
        title.startswith("bud deze run:")
        or title.startswith("bud-focus:")
        or title.startswith("speed focus:")
    ):
        return False
    if title in _GENERIC_FORMATION_TIP_TITLES:
        return False
    if title.startswith("gold growth rate:"):
        return False
    if title.startswith("gold champion(s) in formation:"):
        return False
    return True


def _filter_relevant_formation_tips(
    tips: list[AdvisorTip] | tuple[AdvisorTip, ...],
    *,
    has_seat_report: bool,
) -> tuple[AdvisorTip, ...]:
    filtered = [
        tip for tip in tips if _is_relevant_formation_tip(tip, has_seat_report=has_seat_report)
    ]
    return tuple(
        AdvisorTip(priority=index, title=tip.title, detail=tip.detail)
        for index, tip in enumerate(filtered, start=1)
    )


