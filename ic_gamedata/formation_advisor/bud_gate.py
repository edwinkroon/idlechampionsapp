"""BUD-proxy gating for formation placement swaps and bench tips."""

from __future__ import annotations

from dataclasses import replace as dc_replace

from ic_gamedata.bud_proxy import (
    bud_proxy_ratio,
    estimate_bud_proxy,
    format_bud_ratio,
    meaningful_bud_ratio,
)
from ic_gamedata.formation_advisor.models import FormationLayoutContext
from ic_gamedata.party_advisor_models import FormationHero


def _adjacency(ctx: FormationLayoutContext) -> dict[int, frozenset[int]]:
    """Prefer live topology; fill gaps with the standard diamond used by bud_proxy."""
    from ic_gamedata.bud_proxy import _DEFAULT_ADJACENCY

    merged = dict(_DEFAULT_ADJACENCY)
    for seat, neighbors in ctx.topology.seat_adjacency.items():
        if neighbors:
            merged[seat] = neighbors
    return merged


def _apply_seat_swap(
    formation: tuple[FormationHero, ...],
    *,
    mover_id: int,
    mover_new_seat: int,
    partner_id: int | None,
    partner_new_seat: int | None,
) -> tuple[FormationHero, ...]:
    out: list[FormationHero] = []
    for hero in formation:
        if hero.hero_id == mover_id:
            out.append(dc_replace(hero, seat=mover_new_seat))
        elif partner_id is not None and hero.hero_id == partner_id and partner_new_seat is not None:
            out.append(dc_replace(hero, seat=partner_new_seat))
        else:
            out.append(hero)
    return tuple(out)


def _bench_as_hero(
    ctx: FormationLayoutContext,
    bench_id: int,
    seat: int | None,
) -> FormationHero:
    return FormationHero(
        hero_id=bench_id,
        name=ctx.name(bench_id),
        seat=seat,
        level=0,
        gear_score=1.0,
        ilvl=0,
        ilvl_pct_vs_avg=0.0,
        gear_rank=0,
        gear_rank_total=0,
        gear_pct_of_best=0.0,
        gear_label="",
        role_label="",
        roles=tuple(ctx.hero_roles_by_id.get(bench_id, ())),
        tags=tuple(ctx.hero_tags_by_id.get(bench_id, ())),
        highest_damage=0.0,
        active_feats=0,
        is_top_damage=False,
    )


def score_seat_swap(
    ctx: FormationLayoutContext,
    *,
    mover_id: int,
    target_seat: int,
    partner_id: int | None,
) -> float | None:
    """Return after/before BUD proxy ratio for a seat move/swap, or None if unscored."""
    formation = ctx.formation
    if not formation:
        return None
    mover = next((h for h in formation if h.hero_id == mover_id), None)
    if mover is None or mover.seat is None:
        return None
    partner_new_seat = mover.seat if partner_id is not None else None
    after = _apply_seat_swap(
        formation,
        mover_id=mover_id,
        mover_new_seat=target_seat,
        partner_id=partner_id,
        partner_new_seat=partner_new_seat,
    )
    before = estimate_bud_proxy(
        formation,
        adjacency=_adjacency(ctx),
        carry_hero_id=ctx.carry_hero_id,
    )
    after_proxy = estimate_bud_proxy(
        after,
        adjacency=_adjacency(ctx),
        carry_hero_id=ctx.carry_hero_id,
    )
    return bud_proxy_ratio(before, after_proxy)


def best_swap_to_carry(
    ctx: FormationLayoutContext,
    hero_id: int,
) -> tuple[int | None, int | None, float] | None:
    """Best seat next to carry for ``hero_id`` by BUD proxy ratio.

    Returns ``(partner_id, partner_seat, ratio)`` where ``partner_id`` is None
    for an empty seat. Returns None when no candidate improves or matches proxy.
    """
    carry_id = ctx.carry_hero_id
    if carry_id is None or hero_id == carry_id:
        return None
    carry_seat = ctx.seat_of(carry_id)
    hero_seat = ctx.seat_of(hero_id)
    if carry_seat is None or hero_seat is None:
        return None
    if ctx.is_adjacent(hero_id, carry_id):
        return None

    best: tuple[int | None, int | None, float] | None = None
    for neighbor_seat in ctx.adjacent_seats(carry_seat):
        if neighbor_seat == hero_seat:
            continue
        partner_id = ctx.hero_at_seat(neighbor_seat)
        if partner_id == carry_id:
            continue
        if partner_id is not None and "tank" in ctx.roles(partner_id):
            continue
        ratio = score_seat_swap(
            ctx,
            mover_id=hero_id,
            target_seat=neighbor_seat,
            partner_id=partner_id,
        )
        if ratio is None or ratio < 1.0:
            continue
        if best is None or ratio > best[2]:
            best = (partner_id, neighbor_seat, ratio)
    return best


def score_bench_replace(
    ctx: FormationLayoutContext,
    *,
    bench_id: int,
    replace_id: int,
) -> float | None:
    formation = ctx.formation
    if not formation:
        return None
    replace = next((h for h in formation if h.hero_id == replace_id), None)
    if replace is None:
        return None
    incoming = _bench_as_hero(ctx, bench_id, replace.seat)
    after = tuple(
        incoming if hero.hero_id == replace_id else hero for hero in formation
    )
    before = estimate_bud_proxy(
        formation,
        adjacency=_adjacency(ctx),
        carry_hero_id=ctx.carry_hero_id,
    )
    after_proxy = estimate_bud_proxy(
        after,
        adjacency=_adjacency(ctx),
        carry_hero_id=ctx.carry_hero_id,
    )
    return bud_proxy_ratio(before, after_proxy)


def append_proxy_ratio(detail: str, ratio: float | None) -> str:
    if ratio is None or not meaningful_bud_ratio(ratio):
        return detail
    return f"{detail} BUD proxy: {format_bud_ratio(ratio)} vs current party."
