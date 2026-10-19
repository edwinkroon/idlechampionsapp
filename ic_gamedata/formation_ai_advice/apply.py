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
    permanent_seat_by_hero: dict[int, int] | None = None,
    position_geometry: dict[int, tuple[float, float, str]] | None = None,
) -> tuple[VisualSeatNode, ...]:
    """Preview placement: ``seat_by_hero`` maps champion_id → position_id.

    Live visual nodes are keyed by the current occupant’s permanent F-seat, which
    in this app coincides with the formation ``position_id`` while occupied.
    Proposal cards must keep geometry at ``position_id`` but label ``seat`` with
    the champion’s permanent F-seat (follows the champion, not the place).

    ``position_geometry`` supplies (x, y, zone) for empty slots that have no live
    card yet (e.g. Flint → empty position 1). Without it, missing slots fall back
    to an overflow strip — which stretches the board and looks wrong.
    """
    names = dict(hero_name_by_id or {})
    for n in nodes:
        if n.hero_id is not None and n.hero_name:
            names.setdefault(int(n.hero_id), str(n.hero_name))

    perm = dict(permanent_seat_by_hero or {})
    for n in nodes:
        if n.hero_id is not None:
            perm.setdefault(int(n.hero_id), int(n.seat))

    # Roles follow the champion, not the place they move into.
    live_by_hero = {
        int(n.hero_id): n for n in nodes if n.hero_id is not None
    }

    # Live geometry: position_id → node (include empties when present).
    geom_by_position = {int(n.seat): n for n in nodes}
    hero_at_position = {
        int(position_id): int(hid) for hid, position_id in seat_by_hero.items()
    }
    pos_geom = {
        int(pid): (float(xy[0]), float(xy[1]), str(xy[2]))
        for pid, xy in (position_geometry or {}).items()
    }

    gap_x, gap_y = 110.0, 72.0
    if geom_by_position:
        max_x = max(n.x for n in geom_by_position.values())
        min_y = min(n.y for n in geom_by_position.values())
    elif nodes:
        max_x = max(n.x for n in nodes)
        min_y = min(n.y for n in nodes)
    else:
        max_x, min_y = 0.0, 0.0

    out: list[VisualSeatNode] = []
    missing_offset = 0
    for position_id in sorted(hero_at_position):
        hid = hero_at_position[position_id]
        label_seat = int(perm.get(hid) or position_id)
        name = names.get(hid) or f"Champion {hid}"
        src = live_by_hero.get(hid)
        role_kwargs = dict(
            effective_role=src.effective_role if src is not None else None,
            inferred_role=src.inferred_role if src is not None else None,
            chosen_role=src.chosen_role if src is not None else None,
            is_bud=bool(src.is_bud) if src is not None else False,
        )
        geom = geom_by_position.get(position_id)
        if geom is not None:
            out.append(
                replace(
                    geom,
                    seat=label_seat,
                    hero_id=hid,
                    hero_name=name,
                    has_issue=False,
                    is_active=True,
                    **role_kwargs,
                )
            )
        elif position_id in pos_geom:
            x, y, zone = pos_geom[position_id]
            out.append(
                VisualSeatNode(
                    seat=label_seat,
                    x=x,
                    y=y,
                    zone=zone,
                    hero_id=hid,
                    hero_name=name,
                    has_issue=False,
                    is_active=True,
                    **role_kwargs,
                )
            )
        else:
            zone = next(iter(geom_by_position.values())).zone if geom_by_position else "mid"
            out.append(
                VisualSeatNode(
                    seat=label_seat,
                    x=max_x + gap_x + (missing_offset % 3) * gap_x,
                    y=min_y + (missing_offset // 3) * gap_y,
                    zone=zone,
                    hero_id=hid,
                    hero_name=name,
                    has_issue=True,
                    is_active=True,
                    **role_kwargs,
                )
            )
            missing_offset += 1
    return tuple(out)


def changed_seats(
    before: dict[int, int],
    after: dict[int, int],
) -> set[int]:
    """Return champion_ids whose position_id changed (or who are new).

    ``before`` / ``after`` are champion_id → position_id maps.
    """
    ids = set(before) | set(after)
    return {hid for hid in ids if before.get(hid) != after.get(hid)}


def mark_changed_nodes(
    nodes: tuple[VisualSeatNode, ...],
    changed: set[int],
) -> tuple[VisualSeatNode, ...]:
    """Mark nodes whose ``hero_id`` is in ``changed`` (champion ids)."""
    return tuple(
        replace(n, has_issue=True)
        if n.hero_id is not None and n.hero_id in changed
        else n
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
