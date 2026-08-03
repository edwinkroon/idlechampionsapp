"""Relative BUD proxy for comparing hypothetical party swaps.

MVP: multiplicative model anchored on live carry damage (or gear when damage
is unknown), plus role coverage, adjacency to the carry, and affiliation
overlap. Not a combat sim — only ranks relative BUD impact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

# Standard diamond adjacency (matches formation_advisor.topology._DEFAULT_ADJ).
_DEFAULT_ADJACENCY: dict[int, frozenset[int]] = {
    1: frozenset({2, 3}),
    2: frozenset({1, 3, 4, 5}),
    3: frozenset({1, 2, 5, 6}),
    4: frozenset({2, 5, 7}),
    5: frozenset({2, 3, 4, 6, 7, 8}),
    6: frozenset({3, 5, 8, 9}),
    7: frozenset({4, 5, 8, 10}),
    8: frozenset({5, 6, 7, 9, 10, 11}),
    9: frozenset({6, 8, 11, 12}),
    10: frozenset({7, 8, 11}),
    11: frozenset({8, 9, 10, 12}),
    12: frozenset({9, 11}),
}

_AFFILIATION_TAGS = frozenset(
    {
        "companion",
        "acqinc",
        "cteam",
        "wafflecrew",
        "heroeslance",
        "awfulones",
        "emeraldenclave",
        "morndinsamman",
        "majestics",
        "rivals",
    }
)


class _HeroLike(Protocol):
    hero_id: int
    name: str
    seat: int | None
    roles: tuple[str, ...]
    tags: tuple[str, ...]
    gear_score: float
    ilvl: int
    highest_damage: float
    is_top_damage: bool


@dataclass(frozen=True)
class BudProxyBreakdown:
    total: float
    carry_power: float
    support_factor: float
    position_factor: float
    affiliation_factor: float
    carry_hero_id: int | None
    carry_name: str | None
    notes: tuple[str, ...]


def _is_dps(hero: _HeroLike) -> bool:
    return "dps" in hero.roles


def _is_tank(hero: _HeroLike) -> bool:
    return "tank" in hero.roles


def _is_buffer(hero: _HeroLike) -> bool:
    return "buffer" in hero.tags


def _is_debuffer(hero: _HeroLike) -> bool:
    return "debuffer" in hero.tags or "bud" in hero.tags


def _is_support(hero: _HeroLike) -> bool:
    return "support" in hero.roles


def resolve_carry(heroes: Sequence[_HeroLike]) -> _HeroLike | None:
    """Mirror party_advisor_formation._resolve_bud_hero for proxy scoring."""
    if not heroes:
        return None
    top_damage = next((h for h in heroes if h.is_top_damage), None)
    dps_heroes = [h for h in heroes if _is_dps(h)]

    if top_damage is not None and _is_dps(top_damage):
        return top_damage

    if dps_heroes:
        best_dps = max(dps_heroes, key=lambda h: (h.highest_damage, h.gear_score, h.ilvl))
        if top_damage is not None and (
            _is_buffer(top_damage)
            or (_is_tank(top_damage) and not _is_dps(top_damage))
            or (_is_support(top_damage) and not _is_dps(top_damage))
        ):
            return best_dps
        if top_damage is not None:
            return top_damage
        return best_dps

    if top_damage is not None:
        return top_damage
    return max(heroes, key=lambda h: (h.highest_damage, h.gear_score, h.ilvl))


def _carry_power(carry: _HeroLike) -> float:
    if carry.highest_damage > 0:
        return float(carry.highest_damage)
    # Bench / no live stats: soft gear proxy so DPS swaps still compare.
    return max(float(carry.gear_score), float(carry.ilvl), 1.0)


def _gear_strength(hero: _HeroLike) -> float:
    """Prefer ilvl for support weighting.

    Formation heroes often carry enormous instrument ``gear_score`` values
    (dps × d_mult). Using those made ilvl-7 Halsin beat ilvl-1400 Nayeli in
    the proxy while candidates only have ilvl-scale scores.
    """
    if hero.ilvl > 0:
        return float(hero.ilvl)
    gs = float(hero.gear_score)
    if gs <= 0:
        return 1.0
    # Reject non-ilvl instrument scores.
    if gs > 50_000:
        return 1.0
    return gs



def _gear_mult(hero: _HeroLike) -> float:
    """Soft log gear weight: ~1.2 at ilvl 7, ~3.2 at ilvl 1500."""
    return math.log10(_gear_strength(hero) + 9.0)


def _adjacent_to(
    hero: _HeroLike,
    carry: _HeroLike,
    adjacency: dict[int, frozenset[int]],
) -> bool:
    if hero.seat is None or carry.seat is None:
        return False
    return carry.seat in adjacency.get(hero.seat, frozenset())


def _affiliation_factor(heroes: Sequence[_HeroLike]) -> tuple[float, list[str]]:
    tag_counts: dict[str, int] = {}
    for hero in heroes:
        for tag in set(hero.tags) & _AFFILIATION_TAGS:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    shared = [(tag, n) for tag, n in tag_counts.items() if n >= 2]
    if not shared:
        return 1.0, []
    # Each shared affiliation with n heroes ≈ (n-1) soft stacks.
    bonus = sum((n - 1) for _tag, n in shared)
    factor = 1.0 + 0.12 * bonus
    notes = [f"affiliatie {tag}×{n}" for tag, n in sorted(shared)]
    return factor, notes


def estimate_bud_proxy(
    heroes: Sequence[_HeroLike],
    *,
    adjacency: dict[int, frozenset[int]] | None = None,
    carry_hero_id: int | None = None,
) -> BudProxyBreakdown:
    """Estimate a relative BUD score for a formation snapshot."""
    if not heroes:
        return BudProxyBreakdown(
            total=0.0,
            carry_power=0.0,
            support_factor=1.0,
            position_factor=1.0,
            affiliation_factor=1.0,
            carry_hero_id=None,
            carry_name=None,
            notes=("lege party",),
        )

    adj = adjacency if adjacency is not None else _DEFAULT_ADJACENCY
    if carry_hero_id is not None:
        carry = next((h for h in heroes if h.hero_id == carry_hero_id), None)
        if carry is None:
            carry = resolve_carry(heroes)
    else:
        carry = resolve_carry(heroes)
    assert carry is not None

    power = _carry_power(carry)
    notes: list[str] = [f"carry {carry.name}"]

    debuffers = [h for h in heroes if _is_debuffer(h)]
    buffers = [h for h in heroes if _is_buffer(h)]
    tanks = [h for h in heroes if _is_tank(h)]

    # Presence-based support factors — NOT ilvl. Live tests (Halsin/Omin ilvl ~7 vs
    # Nayeli 1400+) show support kits dominate gear; ilvl-weighted buffers falsely
    # predicted ×3 BUD gains that dropped e219→e214 in-game.
    support = 1.0
    if debuffers:
        support *= 2.25
        notes.append(f"{len(debuffers)} debuffer(s)")
        for _ in range(min(len(debuffers) - 1, 2)):
            support *= 1.4
    if buffers:
        support *= 1.0 + 0.55 * len(buffers)
        notes.append(f"{len(buffers)} buffer(s)")
    if tanks:
        support *= 1.0 + 0.12 * min(len(tanks), 2)
        notes.append("tank aanwezig")

    position = 1.0
    adj_buffers = 0
    adj_debuffers = 0
    for hero in buffers:
        if hero.hero_id == carry.hero_id or not _adjacent_to(hero, carry, adj):
            continue
        adj_buffers += 1
        position *= 1.55
    for hero in debuffers:
        if hero.hero_id == carry.hero_id or not _adjacent_to(hero, carry, adj):
            continue
        adj_debuffers += 1
        position *= 1.4
    for hero in heroes:
        if hero.hero_id == carry.hero_id:
            continue
        if not (_is_support(hero) and not _is_buffer(hero) and not _is_debuffer(hero)):
            continue
        if not _adjacent_to(hero, carry, adj):
            continue
        position *= 1.12
    if adj_buffers:
        notes.append(f"{adj_buffers} buffer(s) adjacent")
    if adj_debuffers:
        notes.append(f"{adj_debuffers} debuffer(s) adjacent")

    affiliation, aff_notes = _affiliation_factor(heroes)
    notes.extend(aff_notes)

    total = power * support * position * affiliation
    return BudProxyBreakdown(
        total=total,
        carry_power=power,
        support_factor=support,
        position_factor=position,
        affiliation_factor=affiliation,
        carry_hero_id=carry.hero_id,
        carry_name=carry.name,
        notes=tuple(notes),
    )


def bud_proxy_ratio(before: BudProxyBreakdown, after: BudProxyBreakdown) -> float:
    if before.total <= 0:
        return 1.0 if after.total <= 0 else float("inf")
    return after.total / before.total


def format_bud_ratio(ratio: float) -> str:
    if not math.isfinite(ratio) or ratio <= 0:
        return "onbekend"
    if abs(ratio - 1.0) < 0.03:
        return "geen winst"
    if ratio >= 1.0:
        return f"~×{ratio:.2f}"
    return f"~×{ratio:.2f} (lager)"


def meaningful_bud_ratio(ratio: float | None, *, threshold: float = 0.03) -> bool:
    """True when ratio is worth showing as a BUD change."""
    if ratio is None or not math.isfinite(ratio) or ratio <= 0:
        return False
    return abs(ratio - 1.0) >= threshold


def score_boost_from_ratio(ratio: float) -> float:
    """Additive score boost for roster-upgrade ranking (log2 scale)."""
    if not math.isfinite(ratio) or ratio <= 0:
        return 0.0
    return math.log2(ratio) * 400.0
