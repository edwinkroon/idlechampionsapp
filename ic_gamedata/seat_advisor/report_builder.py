"""Build seat-centric advisor report."""

from __future__ import annotations

from typing import Any

from ic_gamedata.adventure_restrictions import AdventureRosterFilter, is_hero_allowed
from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.feat_status import build_feat_recommendations
from ic_gamedata.formation_advisor.models import FormationInsight
from ic_gamedata.formation_advisor.topology import load_formation_topology
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_advisor import (
    ContextMode,
    FormationHero,
    GoalMode,
    _loot_ilvl_by_hero,
    _owned_heroes,
    _resolve_bud_hero,
    _resolve_speed_hero,
)
from ic_gamedata.party_advisor_specializations import (
    SpecializationInsight,
    _formation_context_from_payload,
    current_spec_labels_for_hero,
    recommended_spec_for_goal,
    resolve_spec_display_status,
)
from ic_gamedata.patron_roster import patron_restriction_note
from ic_gamedata.seat_advisor.bench_ranker import better_bench_for_role, rank_bench_alternatives
from ic_gamedata.seat_advisor.formation_visual import build_visual_nodes, load_formation_graph
from ic_gamedata.seat_advisor.html_grid import generate_formation_html
from ic_gamedata.seat_advisor.models import (
    SeatAdvisorReport,
    SeatInsightLine,
    SeatReport,
    SeatRole,
    VisualSeatNode,
)
from ic_gamedata.seat_advisor.role_inference import infer_seat_role, role_fits_champion, role_label
from ic_gamedata.seat_advisor.role_prefs import get_chosen_role, load_role_preferences
from ic_gamedata.specializations import _merge_known_options, load_specialization_rules
from ic_gamedata.speed_utility_roles import (
    recommended_feats_for_speed_utility,
    speed_utility_for_effective_role,
    speed_utility_relevance_reason,
)


def _active_instance(payload: dict[str, Any]) -> dict[str, Any] | None:
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    active_id = _parse_int(details.get("active_game_instance_id"))
    for inst in details.get("game_instances") or []:
        if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:
            return inst
    instances = details.get("game_instances")
    if isinstance(instances, list) and instances and isinstance(instances[0], dict):
        return instances[0]
    return None


def _insight_priority(insight: FormationInsight) -> int:
    base = insight.priority
    if insight.insight_type == "swap":
        return base
    if insight.insight_type == "placement":
        return base + 5
    return base + 10


def _lines_for_seat(
    seat: int,
    hero_id: int,
    formation_insights: tuple[FormationInsight, ...],
    spec_insights: tuple[SpecializationInsight, ...],
) -> tuple[SeatInsightLine, ...]:
    lines: list[SeatInsightLine] = []
    for ins in formation_insights:
        if ins.seat == seat or ins.hero_id == hero_id:
            lines.append(
                SeatInsightLine(
                    source="formatie",
                    headline=ins.headline,
                    detail=ins.detail,
                    priority=_insight_priority(ins),
                )
            )
    for ins in spec_insights:
        if ins.hero_id == hero_id and ins.status in {"open_tier", "mismatch"}:
            lines.append(
                SeatInsightLine(
                    source="specialization",
                    headline=ins.headline,
                    detail=ins.detail,
                    priority=ins.priority,
                )
            )
    lines.sort(key=lambda line: line.priority)
    return tuple(lines)


def _spec_labels(spec_insights: tuple[SpecializationInsight, ...], hero_id: int) -> tuple[str, ...]:
    for ins in spec_insights:
        if ins.hero_id == hero_id and ins.current_labels:
            return ins.current_labels
    return ()


def _best_spec(spec_insights: tuple[SpecializationInsight, ...], hero_id: int) -> str | None:
    # Prefer actionable mismatch/open picks, else any formation-aware recommendation.
    for status in ("open_tier", "mismatch", "ok", "match", "matches", "bench_suggestion"):
        for ins in spec_insights:
            if ins.hero_id == hero_id and ins.recommended_label and ins.status == status:
                return ins.recommended_label
    for ins in spec_insights:
        if ins.hero_id == hero_id and ins.recommended_label:
            return ins.recommended_label
    return None


def _role_advice_fields(
    hero_id: int,
    role: SeatRole,
    current_best_spec: str | None,
    *,
    utility_feats: tuple[str, ...] | None = None,
) -> tuple[str | None, tuple[str, ...], str, str, str, str | None, str]:
    advice = get_role_advice(hero_id, role)
    if advice is None:
        feats = utility_feats or ()
        return current_best_spec, feats, "", "", "", None, ""
    guide_default = " / ".join(advice.specialization_names) if advice.specialization_names else None
    best = current_best_spec or guide_default
    source = advice.source
    if advice.source_date:
        source = f"{advice.source} ({advice.source_date})"
    feats = utility_feats if utility_feats is not None else advice.feats
    return (
        best,
        feats,
        advice.formation,
        source,
        advice.source_url,
        guide_default,
        advice.wiki_url,
    )


def _apply_roster_suggestion(
    formation: tuple[FormationHero, ...],
    suggestion: Any,
    *,
    occupied_seats: set[int],
) -> tuple[FormationHero, ...]:
    try:
        from ic_gamedata.roster_upgrade_advisor import _OwnedChamp, _hypothetical_formation
    except ImportError:
        return formation

    candidate_seat = getattr(suggestion, "candidate_seat", None)
    candidate_hero_id = getattr(suggestion, "candidate_hero_id", None)
    candidate_name = getattr(suggestion, "candidate_name", None)
    if not isinstance(candidate_hero_id, int) or not isinstance(candidate_name, str):
        return formation

    if candidate_seat is not None and candidate_seat in occupied_seats and not bool(
        getattr(suggestion, "same_seat_swap", False)
    ):
        return formation

    replace_hero = next(
        (
            hero
            for hero in formation
            if hero.hero_id == getattr(suggestion, "replace_hero_id", None)
        ),
        None,
    )
    candidate = _OwnedChamp(
        hero_id=candidate_hero_id,
        name=candidate_name,
        roles=(),
        tags=(),
        ilvl=0,
        seat_id=candidate_seat,
    )
    updated = _hypothetical_formation(
        formation,
        candidate=candidate,
        replace=replace_hero,
        same_seat_swap=bool(getattr(suggestion, "same_seat_swap", False)),
    )
    occupied_seats.clear()
    occupied_seats.update(hero.seat for hero in updated if hero.seat is not None)
    return updated


def _build_recommended_visual_nodes(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    adventure_id: int | None,
    seat_meta: dict[int, dict[str, Any]],
    roster_filter: AdventureRosterFilter | None,
) -> tuple[tuple[VisualSeatNode, ...], str | None]:
    # Unknown/unevaluable restriction expressions: hide rather than guess illegal swaps.
    # Known patron/variant/trials rules are fine — suggest_roster_upgrades and the
    # is_hero_allowed gate below already filter candidates to the allowed roster.
    if roster_filter is not None and roster_filter.has_unknown_rules:
        return (), (
            "Owned formation not shown: this scenario's restrictions cannot be fully "
            "evaluated."
        )
    try:
        from ic_gamedata.roster_upgrade_advisor import suggest_roster_upgrades
    except ImportError:
        return (), None

    suggestions = suggest_roster_upgrades(payload, goal=goal, context=context, limit=4)
    if not suggestions:
        return (), None

    projected = formation
    occupied_seats = {hero.seat for hero in formation if hero.seat is not None}
    touched_heroes = {hero.hero_id for hero in formation}
    changed = False
    for suggestion in suggestions:
        candidate_id = getattr(suggestion, "candidate_hero_id", None)
        replace_id = getattr(suggestion, "replace_hero_id", None)
        if not isinstance(candidate_id, int):
            continue
        if roster_filter is not None and not is_hero_allowed(candidate_id, roster_filter):
            continue
        if candidate_id in touched_heroes:
            continue
        if replace_id is not None and replace_id not in touched_heroes:
            continue
        updated = _apply_roster_suggestion(
            projected,
            suggestion,
            occupied_seats=occupied_seats,
        )
        if updated == projected:
            continue
        projected = updated
        touched_heroes.add(candidate_id)
        if isinstance(replace_id, int):
            touched_heroes.discard(replace_id)
        changed = True

    if not changed:
        return (), None

    hero_name_by_id = {hero.hero_id: hero.name for hero in projected}
    formation_seats = {hero.hero_id: hero.seat for hero in projected if hero.seat is not None}
    visual_nodes = build_visual_nodes(
        payload,
        adventure_id,
        hero_name_by_id=hero_name_by_id,
        seat_meta=seat_meta,
        formation_seats=formation_seats,
    )
    if any(node.hero_id is not None for node in visual_nodes):
        return visual_nodes, None
    topo = load_formation_topology(payload, adventure_id)
    return (
        tuple(
            VisualSeatNode(
                seat=seat,
                x=float(index % 4) * 110.0,
                y=float(index // 4) * 72.0,
                zone=topo.seat_zone.get(seat, "mid"),
                hero_id=hero_id,
                hero_name=hero_name_by_id.get(hero_id),
                effective_role=(seat_meta.get(seat) or {}).get("effective_role"),
                inferred_role=(seat_meta.get(seat) or {}).get("inferred_role"),
                chosen_role=(seat_meta.get(seat) or {}).get("chosen_role"),
                is_bud=bool((seat_meta.get(seat) or {}).get("is_bud")),
                has_issue=bool((seat_meta.get(seat) or {}).get("has_issue")),
                is_active=True,
            )
            for index, (hero_id, seat) in enumerate(
                sorted(formation_seats.items(), key=lambda item: item[1])
            )
        ),
        None,
    )


def build_seat_advisor_report(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode,
    context: ContextMode,
    formation_insights: tuple[FormationInsight, ...] = (),
    specialization_insights: tuple[SpecializationInsight, ...] = (),
    roster_filter: AdventureRosterFilter | None = None,
    role_prefs: dict[int, dict[str, str]] | None = None,
) -> SeatAdvisorReport | None:
    if not formation:
        return None

    instance = _active_instance(payload) or {}
    adventure_id = _parse_int(instance.get("current_adventure_id"))
    topo = load_formation_topology(payload, adventure_id)
    bud = _resolve_bud_hero(formation) if goal == "bud" else None
    bud_id = bud.hero_id if bud else None
    bud_name = bud.name if bud else None
    speed = _resolve_speed_hero(formation) if goal == "speed" else None
    speed_id = speed.hero_id if speed else None
    speed_name = speed.name if speed else None
    focus_id = bud_id if goal == "bud" else speed_id

    prefs = role_prefs if role_prefs is not None else load_role_preferences()
    owned = _owned_heroes(payload)
    in_party = {h.hero_id for h in formation}
    formation_ids = frozenset(in_party)
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    ilvl_by_hero = _loot_ilvl_by_hero(details)
    spec_rules = load_specialization_rules()
    known_by_hero = _merge_known_options(payload, spec_rules)
    formation_ctx = _formation_context_from_payload(payload, formation)

    seat_reports: list[SeatReport] = []
    seat_meta: dict[int, dict[str, Any]] = {}
    try:
        from ic_gamedata.specialization_data import hero_seat_id_map_from_cached_definitions

        def_seats = hero_seat_id_map_from_cached_definitions()
    except ImportError:
        def_seats = {}

    for hero in formation:
        seat = hero.seat
        if seat is None:
            # Grid heroes can arrive before hero_in_seats catches up — permanent
            # F-key seat_id still lets the Party Advisor champ overview refresh.
            resolved = def_seats.get(hero.hero_id)
            if resolved is not None and 1 <= resolved <= 12:
                seat = resolved
            else:
                continue
        zone = topo.seat_zone.get(seat, "mid")
        inferred: SeatRole = infer_seat_role(
            hero,
            zone=zone,
            bud_hero_id=focus_id if goal == "bud" else None,
            goal=goal,
            context=context,
        )
        chosen_raw = get_chosen_role(hero.hero_id, goal, prefs)
        chosen: SeatRole | None = chosen_raw
        effective: SeatRole = chosen or inferred
        utility = speed_utility_for_effective_role(hero, goal, effective)
        allowed = is_hero_allowed(hero.hero_id, roster_filter, formation_hero_ids=formation_ids)
        lines = _lines_for_seat(seat, hero.hero_id, formation_insights, specialization_insights)
        if not allowed:
            patron_id = roster_filter.patron_id if roster_filter else None
            patron_note = (
                patron_restriction_note(hero.hero_id, patron_id, payload)
                if patron_id
                else None
            )
            detail = patron_note or "This champion does not meet the adventure restrictions."
            lines = (
                SeatInsightLine(
                    source="restrictie",
                    headline="Not allowed — replace",
                    detail=detail,
                    priority=0,
                ),
            )
        alternatives = rank_bench_alternatives(
            role=effective,
            current_hero=hero,
            owned=owned,
            in_party=in_party,
            roster_filter=roster_filter,
            ilvl_by_hero=ilvl_by_hero,
            limit=3,
        )
        better = better_bench_for_role(hero, effective, alternatives)
        if not allowed:
            relevance = "Not allowed on adventure/patron"
            priority = 0
        elif better and not lines:
            lines = (
                SeatInsightLine(
                    source="bench",
                    headline=f"Alternative for {role_label(effective)} role",
                    detail=f"Consider {better.hero_name} ({better.reason}) instead of {hero.name}.",
                    priority=4,
                ),
            )

        if lines:
            relevance = lines[0].headline
            priority = lines[0].priority
        elif not allowed:
            pass
        elif better:
            relevance = f"Better {role_label(effective)} available on bench"
            priority = 5
        elif not role_fits_champion(hero, effective):
            relevance = f"{hero.name} is not ideal for {role_label(effective)} role"
            priority = 6
        elif utility is not None:
            relevance = speed_utility_relevance_reason(utility)
            priority = 45
        else:
            relevance = "OK"
            priority = 50

        role_mismatch = not role_fits_champion(hero, effective)
        is_bud = goal == "bud" and bud_id == hero.hero_id
        is_speed_focus = goal == "speed" and speed_id == hero.hero_id
        current_best = _best_spec(specialization_insights, hero.hero_id)
        if current_best is None:
            # Always resolve a display recommendation — match insights are omitted
            # on purpose, which previously left BUD/campaign seats without best_spec
            # unless role-guide specialization_names happened to exist.
            current_best = recommended_spec_for_goal(
                payload,
                hero.hero_id,
                hero.name,
                hero.seat,
                known_by_hero.get(hero.hero_id, []),
                goal=goal,
                context=context,
                formation_ctx=formation_ctx,
                hero=hero,
                formation=formation,
            )
        utility_feats = (
            recommended_feats_for_speed_utility(hero.hero_id, utility) if utility else None
        )
        best_spec, feats, formation_advice, advice_source, advice_url, guide_default, wiki_url = (
            _role_advice_fields(
                hero.hero_id,
                effective,
                current_best,
                utility_feats=utility_feats,
            )
        )
        current_specs = current_spec_labels_for_hero(payload, hero.hero_id, specialization_insights)
        spec_status = resolve_spec_display_status(
            hero.hero_id,
            specialization_insights,
            recommended=best_spec,
            current_labels=current_specs,
        )
        feat_recommendations = build_feat_recommendations(hero.hero_id, feats, payload)

        report = SeatReport(
            seat=seat,
            zone=zone,
            hero_id=hero.hero_id,
            hero_name=hero.name,
            gear_label=hero.gear_label,
            inferred_role=inferred,
            chosen_role=chosen,
            effective_role=effective,
            role_mismatch=role_mismatch,
            priority=priority,
            relevance_reason=relevance,
            insights=lines,
            bench_alternatives=alternatives if (better or role_mismatch or not allowed) else (),
            best_spec=best_spec,
            current_specs=current_specs,
            spec_status=spec_status,
            recommended_feats=feat_recommendations,
            formation_advice=formation_advice,
            advice_source=advice_source,
            advice_source_url=advice_url,
            advice_wiki_url=wiki_url,
            guide_default_spec=guide_default,
            is_bud=is_bud,
            is_speed_focus=is_speed_focus,
        )
        seat_reports.append(report)
        seat_meta[seat] = {
            "effective_role": effective,
            "inferred_role": inferred,
            "chosen_role": chosen,
            "is_bud": is_bud,
            "is_speed_focus": is_speed_focus,
            "has_issue": priority < 20,
        }

    seat_reports.sort(key=lambda item: (item.priority, item.seat))

    hero_name_by_id = {h.hero_id: h.name for h in formation}
    formation_seats = {h.hero_id: h.seat for h in formation if h.seat is not None}
    for item in seat_reports:
        formation_seats.setdefault(item.hero_id, item.seat)
    formation_name, _nodes = load_formation_graph(payload, adventure_id)
    visual_nodes = build_visual_nodes(
        payload,
        adventure_id,
        hero_name_by_id=hero_name_by_id,
        seat_meta=seat_meta,
        formation_seats=formation_seats,
    )
    # Ultimate fallback: seat cards know the party even if API formation fields are empty.
    if not any(n.hero_id is not None for n in visual_nodes) and formation_seats:
        topo = load_formation_topology(payload, adventure_id)
        visual_nodes = tuple(
            VisualSeatNode(
                seat=seat,
                x=float(index % 4) * 110.0,
                y=float(index // 4) * 72.0,
                zone=topo.seat_zone.get(seat, "mid"),
                hero_id=hero_id,
                hero_name=hero_name_by_id.get(hero_id),
                effective_role=(seat_meta.get(seat) or {}).get("effective_role"),
                inferred_role=(seat_meta.get(seat) or {}).get("inferred_role"),
                chosen_role=(seat_meta.get(seat) or {}).get("chosen_role"),
                is_bud=bool((seat_meta.get(seat) or {}).get("is_bud")),
                has_issue=bool((seat_meta.get(seat) or {}).get("has_issue")),
                is_active=True,
            )
            for index, (hero_id, seat) in enumerate(
                sorted(formation_seats.items(), key=lambda item: item[1])
            )
        )
    html_grid = generate_formation_html(visual_nodes, formation_name=formation_name)
    recommended_visual_nodes, recommended_hidden_reason = _build_recommended_visual_nodes(
        payload,
        formation,
        goal=goal,
        context=context,
        adventure_id=adventure_id,
        seat_meta=seat_meta,
        roster_filter=roster_filter,
    )

    return SeatAdvisorReport(
        bud_hero_id=bud_id,
        bud_hero_name=bud_name,
        speed_hero_id=speed_id,
        speed_hero_name=speed_name,
        seats=tuple(seat_reports),
        visual_nodes=visual_nodes,
        formation_name=formation_name,
        html_grid=html_grid,
        recommended_visual_nodes=recommended_visual_nodes,
        recommended_hidden_reason=recommended_hidden_reason,
    )
