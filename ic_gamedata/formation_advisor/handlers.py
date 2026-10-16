"""Champion-specific formation placement handlers."""

from __future__ import annotations

from collections.abc import Callable

from ic_gamedata.formation_advisor.bud_gate import append_proxy_ratio, score_bench_replace
from ic_gamedata.formation_advisor.models import FormationInsight, FormationLayoutContext
from ic_gamedata.formation_advisor.topology import fallback_seat_column

_KOS_ID = 168
_RAISTLIN_ID = 173
_FLINT_ID = 178

PlacementHandler = Callable[[FormationLayoutContext], FormationInsight | None]


def _formation_column(ctx: FormationLayoutContext, seat: int) -> int:
    return ctx.topology.seat_column.get(seat, fallback_seat_column(seat))


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
            headline=f"{ctx.name(_KOS_ID)}: put carries behind KoS",
            detail=(
                f"King of Shadows is well placed up front (slot {kos_seat}). "
                f"Move DPS/support into the columns behind him for Power of the King."
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
        headline=f"{ctx.name(_KOS_ID)}: move forward",
        detail=(
            f"KoS is on slot {kos_seat} ({zone}) — place him on the front line "
            "so party buffs land behind him."
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
        headline=f"{ctx.name(_RAISTLIN_ID)}: isolate for damage",
        detail=(
            f"Raistlin on slot {seat} has {neighbor_count} neighbors — "
            "more damage when he stands next to fewer champions. "
            "Consider a more isolated slot."
        ),
        rule_source_type="handler",
        data_source_version="handler",
        confidence=4,
        rule_id="handler_raistlin_isolate",
    )


def _handle_flint(ctx: FormationLayoutContext) -> FormationInsight | None:
    if _FLINT_ID not in ctx.active_hero_ids:
        return None
    seat = ctx.seat_of(_FLINT_ID)
    if seat is None:
        return None
    neighbor_count = sum(
        1 for neighbor_seat in ctx.adjacent_seats(seat) if ctx.hero_at_seat(neighbor_seat) is not None
    )
    flint_col = _formation_column(ctx, seat)
    carry_id = ctx.carry_hero_id
    carry_covered = False
    if carry_id is not None and carry_id != _FLINT_ID:
        carry_seat = ctx.seat_of(carry_id)
        if carry_seat is not None:
            carry_col = _formation_column(ctx, carry_seat)
            carry_covered = carry_col in (flint_col, flint_col + 1)

    if neighbor_count <= 1 and len(ctx.active_hero_ids) >= 4:
        return FormationInsight(
            insight_type="placement",
            hero_id=_FLINT_ID,
            hero_name=ctx.name(_FLINT_ID),
            seat=seat,
            related_hero_id=None,
            related_hero_name=None,
            related_seat=None,
            priority=2,
            headline=f"{ctx.name(_FLINT_ID)}: pack neighbors for Forged Bonds",
            detail=(
                f"Flint on slot {seat} has only {neighbor_count} adjacent champion(s). "
                "Forged Bonds stacks from each adjacent ally and buffs his column plus the "
                "column behind him — move him into a denser pocket."
            ),
            rule_source_type="handler",
            data_source_version="handler",
            confidence=4,
            rule_id="handler_flint_neighbors",
        )

    if carry_id is not None and carry_id != _FLINT_ID and not carry_covered:
        return FormationInsight(
            insight_type="placement",
            hero_id=_FLINT_ID,
            hero_name=ctx.name(_FLINT_ID),
            seat=seat,
            related_hero_id=carry_id,
            related_hero_name=ctx.name(carry_id),
            related_seat=ctx.seat_of(carry_id),
            priority=2,
            headline=f"{ctx.name(_FLINT_ID)}: cover {ctx.name(carry_id)} with Forged Bonds",
            detail=(
                f"Keep {ctx.name(carry_id)} in Flint's column or the column directly behind him "
                "so Forged Bonds reaches your Primary DPS."
            ),
            rule_source_type="handler",
            data_source_version="handler",
            confidence=4,
            rule_id="handler_flint_cover_carry",
        )
    return None


def _bench_buffer_suggestion(ctx: FormationLayoutContext) -> FormationInsight | None:
    if ctx.carry_hero_id is None or ctx.goal != "bud":
        return None
    if _carry_has_adjacent_buffer(ctx):
        return None
    best: tuple[int, int, float] | None = None
    for bench_id in sorted(ctx.allowed_bench_ids):
        if "buffer" not in ctx.tags(bench_id):
            continue
        for replace_id in _non_carry_replace_candidates(ctx):
            ratio = score_bench_replace(ctx, bench_id=bench_id, replace_id=replace_id)
            if ratio is None or ratio < 1.0:
                continue
            if best is None or ratio > best[2]:
                best = (bench_id, replace_id, ratio)
    if best is None:
        return None
    bench_id, replace_id, ratio = best
    detail = (
        f"{ctx.name(bench_id)} on bench can buff {ctx.name(ctx.carry_hero_id)} "
        f"better than {ctx.name(replace_id)} (slot {ctx.seat_of(replace_id)})."
    )
    return FormationInsight(
        insight_type="bench",
        hero_id=bench_id,
        hero_name=ctx.name(bench_id),
        seat=None,
        related_hero_id=replace_id,
        related_hero_name=ctx.name(replace_id),
        related_seat=ctx.seat_of(replace_id),
        priority=2,
        headline=f"Bench: {ctx.name(bench_id)} instead of {ctx.name(replace_id)}",
        detail=append_proxy_ratio(detail, ratio),
        rule_source_type="heuristic",
        data_source_version="formation_rules_v1",
        confidence=3,
        rule_id="heuristic_bench_buffer",
        bud_ratio=ratio,
    )


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


def _non_carry_replace_candidates(ctx: FormationLayoutContext) -> list[int]:
    carry = ctx.carry_hero_id
    return [
        hid
        for hid in ctx.active_hero_ids
        if hid != carry and "tank" not in ctx.roles(hid) and "buffer" not in ctx.tags(hid)
    ]


def _weakest_non_carry(ctx: FormationLayoutContext) -> int | None:
    candidates = _non_carry_replace_candidates(ctx)
    if not candidates:
        return None
    return candidates[-1]


PLACEMENT_HANDLERS: list[PlacementHandler] = [
    _handle_king_of_shadows,
    _handle_raistlin,
    _handle_flint,
    _bench_buffer_suggestion,
]


def evaluate_placement_handlers(ctx: FormationLayoutContext) -> list[FormationInsight]:
    insights: list[FormationInsight] = []
    for handler in PLACEMENT_HANDLERS:
        insight = handler(ctx)
        if insight is not None:
            insights.append(insight)
    return insights
