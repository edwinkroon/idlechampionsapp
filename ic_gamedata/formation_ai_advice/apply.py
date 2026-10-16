"""In-app apply/undo helpers for formation advice overlays (no game automation)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ic_gamedata.formation_ai_advice.models import (
    AppliedFormationSnapshot,
    FormationAdviceProposal,
    SpecializationChoice,
)
from ic_gamedata.seat_advisor.models import VisualSeatNode


@dataclass(frozen=True)
class AppliedAdviceState:
    seat_by_hero: dict[int, int]
    specialization_advice: dict[int, tuple[SpecializationChoice, ...]]
    undo: AppliedFormationSnapshot | None = None
    note: str = (
        "Specialisaties zijn alleen als advies opgeslagen; "
        "de app kan ze niet in de game instellen."
    )


def snapshot_from_visual_nodes(
    nodes: tuple[VisualSeatNode, ...] | list[VisualSeatNode],
    *,
    specialization_advice: dict[int, tuple[SpecializationChoice, ...]] | None = None,
    label: str = "vóór AI-voorstel",
) -> AppliedFormationSnapshot:
    seat_by_hero = {
        int(n.hero_id): int(n.seat)
        for n in nodes
        if n.hero_id is not None
    }
    return AppliedFormationSnapshot(
        seat_by_hero=seat_by_hero,
        specialization_advice=dict(specialization_advice or {}),
        label=label,
    )


def apply_proposal(
    proposal: FormationAdviceProposal,
    *,
    current_nodes: tuple[VisualSeatNode, ...] | list[VisualSeatNode],
    previous_spec_advice: dict[int, tuple[SpecializationChoice, ...]] | None = None,
) -> AppliedAdviceState:
    """Atomically build new overlay + undo snapshot from a validated proposal."""
    undo = snapshot_from_visual_nodes(
        current_nodes,
        specialization_advice=previous_spec_advice,
    )
    seat_by_hero = {a.champion_id: a.position_id for a in proposal.assignments}
    specs = {
        a.champion_id: a.specialization_choices
        for a in proposal.assignments
        if a.specialization_choices
    }
    return AppliedAdviceState(
        seat_by_hero=seat_by_hero,
        specialization_advice=specs,
        undo=undo,
    )


def remap_visual_nodes(
    nodes: tuple[VisualSeatNode, ...] | list[VisualSeatNode],
    seat_by_hero: dict[int, int],
    *,
    hero_name_by_id: dict[int, str] | None = None,
) -> tuple[VisualSeatNode, ...]:
    """Preview/apply placement without mutating geometry source nodes in place."""
    names = hero_name_by_id or {
        int(n.hero_id): str(n.hero_name)
        for n in nodes
        if n.hero_id is not None and n.hero_name
    }
    hero_by_seat = {seat: hid for hid, seat in seat_by_hero.items()}
    # Keep geometry of existing seat cards; reassign heroes.
    by_seat = {n.seat: n for n in nodes}
    out: list[VisualSeatNode] = []
    for seat, node in by_seat.items():
        hid = hero_by_seat.get(seat)
        out.append(
            replace(
                node,
                hero_id=hid,
                hero_name=names.get(hid) if hid is not None else None,
                is_active=hid is not None,
            )
        )
    # Seats in proposal missing from geometry: append with copied coords of first node.
    missing = [s for s in hero_by_seat if s not in by_seat]
    if missing and nodes:
        template = nodes[0]
        for seat in missing:
            hid = hero_by_seat[seat]
            out.append(
                VisualSeatNode(
                    seat=seat,
                    x=template.x,
                    y=template.y + 0.15 * len(out),
                    zone=template.zone,
                    hero_id=hid,
                    hero_name=names.get(hid),
                    effective_role=None,
                    inferred_role=None,
                    chosen_role=None,
                    is_bud=False,
                    has_issue=True,
                    is_active=True,
                )
            )
    return tuple(out)


def changed_seats(
    before: dict[int, int],
    after: dict[int, int],
) -> set[int]:
    """Seats whose champion differs between two overlays."""
    before_by_seat = {seat: hid for hid, seat in before.items()}
    after_by_seat = {seat: hid for hid, seat in after.items()}
    seats = set(before_by_seat) | set(after_by_seat)
    return {s for s in seats if before_by_seat.get(s) != after_by_seat.get(s)}


def mark_changed_nodes(
    nodes: tuple[VisualSeatNode, ...],
    changed: set[int],
) -> tuple[VisualSeatNode, ...]:
    return tuple(
        replace(n, has_issue=True) if n.seat in changed else n
        for n in nodes
    )


def restriction_recheck(
    payload: dict[str, Any],
    champion_ids: list[int] | tuple[int, ...],
) -> tuple[list[str], list[str]]:
    """Return (hard_errors, unchecked_notes). Inability to check is not a hard fail."""
    try:
        from ic_gamedata.adventure_restrictions import (
            build_adventure_roster_filter,
            is_hero_allowed,
        )

        from ic_gamedata.parsing import parse_int as _parse_int

        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        active_id = _parse_int(details.get("active_game_instance_id"))
        adventure_id = None
        for inst in details.get("game_instances") or []:
            if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:
                adventure_id = _parse_int(inst.get("current_adventure_id"))
                break
        filt = build_adventure_roster_filter(payload, adventure_id)
    except Exception:
        return [], ["Adventure-restricties konden niet opnieuw worden gecontroleerd."]
    errors: list[str] = []
    for hid in champion_ids:
        if not is_hero_allowed(hid, filt):
            errors.append(f"Champion {hid} is niet toegestaan onder adventure-restricties.")
    return errors, []
