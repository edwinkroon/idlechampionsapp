"""Build seat-centric advisor report."""

from __future__ import annotations

from typing import Any

from ic_gamedata.adventure_restrictions import AdventureRosterFilter, is_hero_allowed
from ic_gamedata.patron_roster import patron_restriction_note
from ic_gamedata.formation_advisor.models import FormationInsight
from ic_gamedata.formation_advisor.topology import load_formation_topology
from ic_gamedata.party_advisor import ContextMode, FormationHero, GoalMode, _loot_ilvl_by_hero, _owned_heroes, _resolve_bud_hero, _resolve_speed_hero
from ic_gamedata.party_advisor_specializations import (
    SpecializationInsight,
    _formation_context_from_payload,
    current_spec_labels_for_hero,
    recommended_spec_for_goal,
    resolve_spec_display_status,
)
from ic_gamedata.specializations import _merge_known_options, load_specialization_rules
from ic_gamedata.seat_advisor.bench_ranker import better_bench_for_role, rank_bench_alternatives
from ic_gamedata.seat_advisor.formation_visual import build_visual_nodes, load_formation_graph
from ic_gamedata.seat_advisor.html_grid import generate_formation_html
from ic_gamedata.seat_advisor.models import SeatAdvisorReport, SeatInsightLine, SeatReport, SeatRole, VisualSeatNode
from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.speed_utility_roles import (
    recommended_feats_for_speed_utility,
    speed_utility_relevance_reason,
    speed_utility_role,
)
from ic_gamedata.feat_status import build_feat_recommendations
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.seat_advisor.role_inference import infer_seat_role, role_fits_champion, role_label
from ic_gamedata.seat_advisor.role_prefs import get_chosen_role, load_role_preferences


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
    for status in ("open_tier", "mismatch", "ok", "match", "bench_suggestion"):
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

    for hero in formation:
        if hero.seat is None:
            continue
        seat = hero.seat
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
        utility = speed_utility_role(hero, goal)
        allowed = is_hero_allowed(hero.hero_id, roster_filter, formation_hero_ids=formation_ids)
        lines = _lines_for_seat(seat, hero.hero_id, formation_insights, specialization_insights)
        if not allowed:
            patron_id = roster_filter.patron_id if roster_filter else None
            patron_note = (
                patron_restriction_note(hero.hero_id, patron_id, payload)
                if patron_id
                else None
            )
            detail = patron_note or "Deze champion voldoet niet aan de adventure-beperkingen."
            lines = (
                SeatInsightLine(
                    source="restrictie",
                    headline="Niet toegestaan — vervang",
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
            relevance = "Niet toegestaan op adventure/patron"
            priority = 0
        elif better and not lines:
            lines = (
                SeatInsightLine(
                    source="bench",
                    headline=f"Alternatief voor rol {role_label(effective)}",
                    detail=f"Overweeg {better.hero_name} ({better.reason}) i.p.v. {hero.name}.",
                    priority=4,
                ),
            )

        if lines:
            relevance = lines[0].headline
            priority = lines[0].priority
        elif not allowed:
            pass
        elif better:
            relevance = f"Betere {role_label(effective)} beschikbaar op bench"
            priority = 5
        elif not role_fits_champion(hero, effective):
            relevance = f"{hero.name} past niet ideaal bij rol {role_label(effective)}"
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
        if current_best is None and goal in {"speed", "gold"}:
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

    return SeatAdvisorReport(
        bud_hero_id=bud_id,
        bud_hero_name=bud_name,
        speed_hero_id=speed_id,
        speed_hero_name=speed_name,
        seats=tuple(seat_reports),
        visual_nodes=visual_nodes,
        formation_name=formation_name,
        html_grid=html_grid,
    )
