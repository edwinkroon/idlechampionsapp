"""Explicit placeability layer for formation geometry.

Distinguishes technical layout positions from champion occupancy and from
confirmed NPC/escort/object blocks. Empty (no champion) is never treated as
placeable unless the adventure define confirms it.

Sources for reserved seats (formation-graph indices → technical position_ids):

- ``slot_escort`` via ``resolve_slot_escort_seats``
- ``key_champion`` with ``force_slot`` via ``resolve_key_champion_seat_meta``
  (empty overlay → occupancy ``npc`` / placeability ``blocked``; never free)
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping

Occupancy = Literal["champion", "npc", "escort", "object", "empty", "unknown"]
Placeability = Literal["placeable", "blocked", "unknown"]

OCCUPANCY_VALUES: frozenset[str] = frozenset(
    ("champion", "npc", "escort", "object", "empty", "unknown")
)
PLACEABILITY_VALUES: frozenset[str] = frozenset(
    ("placeable", "blocked", "unknown")
)

_SLOT_ESCORT_SOURCE = "defines.adventure_defines.game_changes.slot_escort"
_KEY_CHAMPION_SOURCE = "defines.adventure_defines.game_changes.key_champion"
_MISSING_DEFINE_SOURCE = "defines.adventure_defines"
_CHAMPION_SOURCE = "party.position"

_CHAMPION_ESCORT_CONFLICT = (
    "Conflict: observed champion on a seat also resolved from slot_escort; "
    "keeping live champion occupancy. Escort mapping or live state may be wrong."
)
_KEY_CHAMPION_OVERLAY_CONFLICT = (
    "Conflict: observed champion on a key_champion force_slot overlay seat; "
    "keeping live champion occupancy. Overlay/NPC reservation is separate "
    "from the required champion's party position — not a free add seat."
)


def adventure_placeability_known(
    payload: Mapping[str, Any] | None,
    adventure_id: int | None,
) -> bool:
    """True when the adventure define was found and escort mapping is reliable."""
    if not isinstance(payload, Mapping) or adventure_id is None:
        return False
    from ic_gamedata.adventure_restrictions import _adventure_define
    from ic_gamedata.formation_position_resolve import resolve_slot_escort_seats

    if _adventure_define(dict(payload), adventure_id) is None:
        return False
    return resolve_slot_escort_seats(payload, adventure_id).mapping_reliable


def build_slot_states(
    position_ids: Iterable[int],
    *,
    champion_by_position: Mapping[int, int | None] | None = None,
    reserved_seats: Iterable[int] | None = None,
    placeability_known: bool = False,
    display_by_position: Mapping[int, str] | None = None,
    escort_meta_by_position: Mapping[int, Mapping[str, Any]] | None = None,
    escort_mapping_unreliable: bool = False,
) -> list[dict[str, Any]]:
    """Build one slot_state per technical position_id.

    Rules
    -----
    - Champion present → occupancy=champion, placeability=placeable
      (reassignment allowed; not an empty available seat).
    - Champion on a reserved escort seat → keep champion; emit an explicit
      conflict reason (never silently drop the champion or invent an NPC id).
    - Seat in reserved and empty → occupancy=escort, placeability=blocked
      (from slot_escort; name/graphic only when the define supplies them).
    - Empty, placeability known, not reserved → empty + placeable.
    - Empty, placeability unknown / escort mapping unreliable → unknown
      (never infer free).
    """
    champs = dict(champion_by_position or {})
    reserved = {int(s) for s in (reserved_seats or ())}
    display = dict(display_by_position or {})
    escort_meta = {
        int(k): dict(v)
        for k, v in (escort_meta_by_position or {}).items()
        if isinstance(v, Mapping)
    }
    # Unreliable escort detection must not invent free add seats.
    effective_known = bool(placeability_known) and not escort_mapping_unreliable
    states: list[dict[str, Any]] = []
    for raw in sorted({int(p) for p in position_ids}):
        pid = int(raw)
        hid = champs.get(pid)
        if hid is not None:
            row: dict[str, Any] = {
                "position_id": pid,
                "occupancy": "champion",
                "placeability": "placeable",
                "source": _CHAMPION_SOURCE,
            }
            if pid in reserved:
                blocker = dict(escort_meta.get(pid) or {})
                btype = str(blocker.get("type") or "").strip().casefold()
                if btype in ("npc", "key_champion"):
                    # Live champion wins; do not treat overlay reservation as
                    # proof the required champion belongs on this seat.
                    row["reason"] = _KEY_CHAMPION_OVERLAY_CONFLICT
                    row["conflict"] = "champion_vs_key_champion_overlay"
                    row["source"] = str(
                        blocker.get("source") or _KEY_CHAMPION_SOURCE
                    )
                    if blocker:
                        row["blocker"] = blocker
                else:
                    row["reason"] = _CHAMPION_ESCORT_CONFLICT
                    row["conflict"] = "champion_vs_slot_escort"
            states.append(_with_display(row, display.get(pid)))
            continue

        if pid in reserved:
            # Resolved escort / key_champion seats stay blocked even when other
            # indices failed.
            blocker = dict(escort_meta.get(pid) or {"type": "escort"})
            btype = str(blocker.get("type") or "").strip().casefold()
            if btype not in ("escort", "npc", "object", "key_champion"):
                blocker["type"] = "escort"
                btype = "escort"
            if btype in ("npc", "key_champion"):
                occupancy = "npc"
                reason = (
                    "Reserved by adventure key_champion force_slot "
                    "(NPC/overlay seat — not champion-placeable)"
                )
                source = str(blocker.get("source") or _KEY_CHAMPION_SOURCE)
            else:
                occupancy = "escort"
                reason = "Occupied by adventure escort (slot_escort)"
                source = _SLOT_ESCORT_SOURCE
            row = {
                "position_id": pid,
                "occupancy": occupancy,
                "placeability": "blocked",
                "blocker": blocker,
                "reason": reason,
                "source": source,
            }
            states.append(_with_display(row, display.get(pid)))
            continue

        if effective_known:
            row = {
                "position_id": pid,
                "occupancy": "empty",
                "placeability": "placeable",
                "reason": (
                    "Empty seat; not reserved by adventure slot_escort "
                    "or key_champion force_slot"
                ),
                "source": _SLOT_ESCORT_SOURCE,
            }
            states.append(_with_display(row, display.get(pid)))
            continue

        reason = (
            "Escort/placeability mapping unreliable; not treating as free"
            if escort_mapping_unreliable
            else "Placeability not available from source"
        )
        source = (
            _SLOT_ESCORT_SOURCE
            if escort_mapping_unreliable
            else _MISSING_DEFINE_SOURCE
        )
        row = {
            "position_id": pid,
            "occupancy": "unknown",
            "placeability": "unknown",
            "reason": reason,
            "source": source,
        }
        states.append(_with_display(row, display.get(pid)))
    return states


def derive_position_id_lists(
    slot_states: Iterable[Mapping[str, Any]] | None,
) -> dict[str, list[int]]:
    """Derive blocked / available / unknown lists from the same slot_states.

    ``available_position_ids`` contains only confirmed empty, placeable seats
    — never champion-occupied seats and never unknown.
    """
    blocked: list[int] = []
    available: list[int] = []
    unknown: list[int] = []
    for row in slot_states or ():
        if not isinstance(row, Mapping):
            continue
        pid = row.get("position_id")
        if not isinstance(pid, int):
            continue
        placeability = row.get("placeability")
        occupancy = row.get("occupancy")
        if placeability == "blocked":
            blocked.append(pid)
        elif placeability == "unknown":
            unknown.append(pid)
        if occupancy == "empty" and placeability == "placeable":
            available.append(pid)
    return {
        "blocked_position_ids": blocked,
        "available_position_ids": available,
        "unknown_placeability_position_ids": unknown,
    }


def attach_derived_slot_fields(geometry: dict[str, Any]) -> dict[str, Any]:
    """Write derived id lists onto ``geometry`` from its ``slot_states``."""
    derived = derive_position_id_lists(geometry.get("slot_states"))
    geometry["blocked_position_ids"] = derived["blocked_position_ids"] or None
    geometry["available_position_ids"] = derived["available_position_ids"] or None
    geometry["unknown_placeability_position_ids"] = (
        derived["unknown_placeability_position_ids"] or None
    )
    return geometry


def slot_state_by_position(
    slot_states: Iterable[Mapping[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in slot_states or ():
        if not isinstance(row, Mapping):
            continue
        pid = row.get("position_id")
        if isinstance(pid, int):
            out[pid] = dict(row)
    return out


def placeability_for_position(
    slot_states: Iterable[Mapping[str, Any]] | None,
    position_id: int,
) -> Placeability | None:
    """Return placeability for ``position_id``, or None if no slot_state."""
    by_id = slot_state_by_position(slot_states)
    row = by_id.get(int(position_id))
    if row is None:
        return None
    value = row.get("placeability")
    if value in PLACEABILITY_VALUES:
        return value  # type: ignore[return-value]
    return None


def format_position_ref(
    position_id: int,
    *,
    display_position: str | None = None,
    reason: str | None = None,
) -> str:
    """Concrete error label: technical id + optional display plek + reason."""
    parts = [f"technische positie {position_id}"]
    if display_position:
        parts.append(f"displayplek {display_position}")
    text = " / ".join(parts)
    if reason:
        text = f"{text}: {reason}"
    return text


def validate_slot_states(
    slot_states: Iterable[Mapping[str, Any]] | None,
    *,
    valid_position_ids: Iterable[int] | None,
    occupied: Iterable[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Structural checks — returns human-readable error messages."""
    errors: list[str] = []
    valid = {int(p) for p in (valid_position_ids or ())}
    seen: set[int] = set()
    rows: list[Mapping[str, Any]] = [
        row for row in (slot_states or ()) if isinstance(row, Mapping)
    ]

    for row in rows:
        pid = row.get("position_id")
        if not isinstance(pid, int):
            errors.append("slot_state zonder geldige position_id.")
            continue
        if valid and pid not in valid:
            errors.append(
                f"slot_state voor {format_position_ref(pid)} "
                f"staat niet in valid_position_ids."
            )
        if pid in seen:
            errors.append(f"Dubbele slot_state voor positie {pid}.")
        seen.add(pid)

        occupancy = row.get("occupancy")
        placeability = row.get("placeability")
        if occupancy not in OCCUPANCY_VALUES:
            errors.append(
                f"Ongeldige occupancy {occupancy!r} op positie {pid}."
            )
        if placeability not in PLACEABILITY_VALUES:
            errors.append(
                f"Ongeldige placeability {placeability!r} op positie {pid}."
            )

        if occupancy == "champion" and placeability == "blocked":
            errors.append(
                f"Tegenstrijdige slot_state op positie {pid}: "
                "champion met placeability=blocked."
            )
        if occupancy in ("npc", "escort", "object") and placeability == "placeable":
            errors.append(
                f"Tegenstrijdige slot_state op positie {pid}: "
                f"{occupancy} met placeability=placeable."
            )
        if occupancy == "empty" and placeability == "blocked":
            errors.append(
                f"Tegenstrijdige slot_state op positie {pid}: "
                "empty met placeability=blocked (gebruik npc/escort/object)."
            )

    by_id = slot_state_by_position(slot_states)

    # Occupied champions must not also be marked as escort/npc blocks.
    for row in occupied or ():
        if not isinstance(row, Mapping):
            continue
        oid = row.get("id")
        if not isinstance(oid, int):
            continue
        state = by_id.get(oid)
        if state is None:
            continue
        if state.get("occupancy") in ("npc", "escort", "object"):
            errors.append(
                f"Positie {oid} is champion-bezet in occupied maar "
                f"slot_state.occupancy={state.get('occupancy')}."
            )
        if state.get("placeability") == "blocked" and state.get("occupancy") != "champion":
            errors.append(
                f"Positie {oid} is champion-bezet maar placeability=blocked."
            )

    return errors


def _with_display(row: dict[str, Any], display: str | None) -> dict[str, Any]:
    if display:
        row = dict(row)
        row["display_position"] = display
    return row
