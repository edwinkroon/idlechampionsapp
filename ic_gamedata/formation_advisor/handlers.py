"""Champion-specific formation placement handlers."""

from __future__ import annotations

from collections.abc import Callable

from ic_gamedata.formation_advisor.models import FormationInsight, FormationLayoutContext

_KOS_ID = 168
_RAISTLIN_ID = 173

PlacementHandler = Callable[[FormationLayoutContext], FormationInsight | None]


def _formation_column(ctx: FormationLayoutContext, seat: int) -> int:
    return ctx.topology.seat_column.get(seat, ((seat - 1) % 4) + 1)


def _handle_king_of_shadows(ctx: FormationLayoutContext) -> FormationInsight | None:
    if _KOS_ID not in ctx.active_hero_ids:
        return None
    kos_seat = ctx.seat_of(_KOS_ID)
    if kos_seat is None:
        return None
    zone = ctx.zone_of_seat(kos_seat)
    if zone == "front":
        beneficiaries = 0
        kos_col = _formation_column(ctx, kos_seat)
        for hid in ctx.active_hero_ids:
            if hid == _KOS_ID:
                continue
            seat = ctx.seat_of(hid)
            if seat is None:
                continue
            col = _formation_column(ctx, seat)
            if kos_col < col <= kos_col + 2:
                beneficiaries += 1
        if beneficiaries >= 2:
            return None
        return FormationInsight(
            insight_type="placement",
            hero_id=_KOS_ID,
            hero_name=ctx.name(_KOS_ID),
            seat=kos_seat,
            related_hero_id=None,
            related_hero_name=None,
            related_seat=None,
            priority=2,
            headline=f"{ctx.name(_KOS_ID)}: zet carries achter KoS",
            detail=(
                f"King of Shadows staat goed vooraan (slot {kos_seat}). "
                f"Schuif DPS/support naar de kolommen achter hem voor Power of the King."
            ),
            rule_source_type="handler",
            data_source_version="handler",
            confidence=4,
            rule_id="handler_kos_placement",
        )
    return FormationInsight(
        insight_type="placement",
        hero_id=_KOS_ID,
        hero_name=ctx.name(_KOS_ID),
        seat=kos_seat,
        related_hero_id=None,
        related_hero_name=None,
        related_seat=None,
        priority=2,
        headline=f"{ctx.name(_KOS_ID)}: naar voren",
        detail=(
            f"KoS staat op slot {kos_seat} ({zone}) — zet hem in de frontlinie "
            "zodat party-buffs achter hem landen."
        ),
        rule_source_type="handler",
        data_source_version="handler",
        confidence=4,
        rule_id="handler_kos_front",
    )


def _handle_raistlin(ctx: FormationLayoutContext) -> FormationInsight | None:
    if _RAISTLIN_ID not in ctx.active_hero_ids:
        return None
    seat = ctx.seat_of(_RAISTLIN_ID)
    if seat is None:
        return None
    neighbor_count = 0
    for neighbor_seat in ctx.adjacent_seats(seat):
        if ctx.hero_at_seat(neighbor_seat) is not None:
            neighbor_count += 1
    if neighbor_count <= 1:
        return None
    return FormationInsight(
        insight_type="placement",
        hero_id=_RAISTLIN_ID,
        hero_name=ctx.name(_RAISTLIN_ID),
        seat=seat,
        related_hero_id=None,
        related_hero_name=None,
        related_seat=None,
        priority=2,
        headline=f"{ctx.name(_RAISTLIN_ID)}: isoleer voor damage",
        detail=(
            f"Raistlin op slot {seat} heeft {neighbor_count} buren — "
            "meer damage wanneer hij naast minder champions staat. "
            "Overweeg een isolerder slot."
        ),
        rule_source_type="handler",
        data_source_version="handler",
        confidence=4,
        rule_id="handler_raistlin_isolate",
    )


def _bench_buffer_suggestion(ctx: FormationLayoutContext) -> FormationInsight | None:
    if ctx.carry_hero_id is None or ctx.goal != "bud":
        return None
    if _carry_has_adjacent_buffer(ctx):
        return None
    for bench_id in sorted(ctx.allowed_bench_ids):
        if "buffer" in ctx.tags(bench_id) or (
            "support" in ctx.roles(bench_id) and "buffer" in ctx.tags(bench_id)
        ):
            replace_id = _weakest_non_carry(ctx)
            if replace_id is None:
                continue
            return FormationInsight(
                insight_type="bench",
                hero_id=bench_id,
                hero_name=ctx.name(bench_id),
                seat=None,
                related_hero_id=replace_id,
                related_hero_name=ctx.name(replace_id),
                related_seat=ctx.seat_of(replace_id),
                priority=2,
                headline=f"Bench: {ctx.name(bench_id)} i.p.v. {ctx.name(replace_id)}",
                detail=(
                    f"{ctx.name(bench_id)} op bench kan {ctx.name(ctx.carry_hero_id)} "
                    f"beter buffen dan {ctx.name(replace_id)} (slot {ctx.seat_of(replace_id)})."
                ),
                rule_source_type="heuristic",
                data_source_version="formation_rules_v1",
                confidence=3,
                rule_id="heuristic_bench_buffer",
            )
    return None


def _carry_has_adjacent_buffer(ctx: FormationLayoutContext) -> bool:
    carry_id = ctx.carry_hero_id
    if carry_id is None:
        return False
    carry_seat = ctx.seat_of(carry_id)
    if carry_seat is None:
        return False
    for neighbor_seat in ctx.adjacent_seats(carry_seat):
        neighbor_id = ctx.hero_at_seat(neighbor_seat)
        if neighbor_id is None:
            continue
        if "buffer" in ctx.tags(neighbor_id):
            return True
    return False


def _weakest_non_carry(ctx: FormationLayoutContext) -> int | None:
    carry = ctx.carry_hero_id
    candidates = [
        hid
        for hid in ctx.active_hero_ids
        if hid != carry and "tank" not in ctx.roles(hid) and "buffer" not in ctx.tags(hid)
    ]
    if not candidates:
        return None
    return candidates[-1]


PLACEMENT_HANDLERS: list[PlacementHandler] = [
    _handle_king_of_shadows,
    _handle_raistlin,
    _bench_buffer_suggestion,
]


def evaluate_placement_handlers(ctx: FormationLayoutContext) -> list[FormationInsight]:
    insights: list[FormationInsight] = []
    for handler in PLACEMENT_HANDLERS:
        insight = handler(ctx)
        if insight is not None:
            insights.append(insight)
    return insights
