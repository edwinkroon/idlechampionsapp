"""Shared formation-index → technical position_id resolution.

Idle Champions ``slot_escort`` values (``slot_ids`` / ``slot_id``) are
**0-based indices into the adventure formation graph**, not UI seat numbers,
not display labels (``2-1``), and not permanent champion F-keys.

One resolver feeds export, preview overlays, capacity math, and import
validation — callers must not re-interpret escort indices ad hoc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ic_gamedata.parsing import parse_int as _parse_int

_SLOT_ESCORT_SOURCE = "defines.adventure_defines.game_changes.slot_escort"


@dataclass(frozen=True)
class FormationIndexResolution:
    """Result of mapping one or more formation-graph indices."""

    position_ids: frozenset[int] = frozenset()
    """Successfully resolved technical position_ids."""

    unresolved_indices: tuple[int, ...] = ()
    """Raw indices that could not be mapped (out of range / no layout)."""

    index_to_position: Mapping[int, int] = field(default_factory=dict)
    """Subset of the full index→position map for the requested indices."""

    layout_node_count: int | None = None
    """Number of nodes in the layout used for resolution, if any."""

    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EscortSeatResolution:
    """Resolved ``slot_escort`` seats for the current adventure layout."""

    position_ids: frozenset[int] = frozenset()
    unresolved_indices: tuple[int, ...] = ()
    """Escort source indices that did not resolve to a position_id."""

    meta_by_position: Mapping[int, Mapping[str, Any]] = field(default_factory=dict)
    """Optional blocker metadata (name/graphic) keyed by position_id."""

    raw_indices: tuple[int, ...] = ()
    """All escort indices collected from the adventure define."""

    define_found: bool = False
    escort_changes_present: bool = False
    warnings: tuple[str, ...] = ()
    source: str = _SLOT_ESCORT_SOURCE

    @property
    def mapping_reliable(self) -> bool:
        """True when escort indices were fully resolved (or none present)."""
        if not self.escort_changes_present:
            return True
        return not self.unresolved_indices and not any(
            w.startswith("no_formation_layout") for w in self.warnings
        )


def current_formation_index_map(
    payload: Mapping[str, Any],
    adventure_id: int | None,
) -> tuple[dict[int, int], int | None, tuple[str, ...]]:
    """Build index→position_id for the **current** adventure layout.

    Uses adventure (else campaign) formation graph nodes plus the live
    formation grid / ``hero_in_seats``. Does not read BASE_SNAPSHOT geometry.
    """
    warnings: list[str] = []
    if adventure_id is None:
        return {}, None, ("no_adventure_id",)

    from ic_gamedata.formation_advisor.topology import (
        _active_instance,
        _formation_grid_hero_ids,
        _seat_by_hero,
        formation_index_to_position_id,
    )
    from ic_gamedata.seat_advisor.formation_visual import load_formation_graph

    _name, nodes = load_formation_graph(dict(payload), adventure_id)
    if not nodes:
        warnings.append("no_formation_layout")
        return {}, None, tuple(warnings)

    instance = _active_instance(dict(payload)) or {}
    formation_ids = _formation_grid_hero_ids(instance, dict(payload))
    seat_by_hero = _seat_by_hero(instance)
    index_map = formation_index_to_position_id(nodes, formation_ids, seat_by_hero)
    return index_map, len(nodes), tuple(warnings)


def resolve_formation_indices(
    indices: Iterable[int],
    *,
    index_to_position: Mapping[int, int],
    layout_node_count: int | None = None,
) -> FormationIndexResolution:
    """Resolve confirmed 0-based formation indices to technical position_ids.

    Does not treat values as seats, display positions, or 1-based indexes.
    Out-of-range or unmapped indices become ``unresolved_indices``.
    """
    resolved: set[int] = set()
    unresolved: list[int] = []
    subset: dict[int, int] = {}
    warnings: list[str] = []

    for raw in indices:
        idx = int(raw)
        if layout_node_count is not None and (
            idx < 0 or idx >= layout_node_count
        ):
            unresolved.append(idx)
            warnings.append(f"formation_index_out_of_range:{idx}")
            continue
        pos = index_to_position.get(idx)
        if pos is None:
            unresolved.append(idx)
            warnings.append(f"formation_index_unmapped:{idx}")
            continue
        resolved.add(int(pos))
        subset[idx] = int(pos)

    return FormationIndexResolution(
        position_ids=frozenset(resolved),
        unresolved_indices=tuple(unresolved),
        index_to_position=subset,
        layout_node_count=layout_node_count,
        warnings=tuple(warnings),
    )


def _collect_slot_escort_entries(
    adv: Mapping[str, Any],
) -> list[tuple[list[int], list[Any], list[Any]]]:
    """Return (indices, names, graphics) per ``slot_escort`` game_change."""
    entries: list[tuple[list[int], list[Any], list[Any]]] = []
    for change in adv.get("game_changes") or []:
        if not isinstance(change, Mapping):
            continue
        if str(change.get("type") or "").strip().lower() != "slot_escort":
            continue
        indices: list[int] = []
        slot_ids = change.get("slot_ids")
        if isinstance(slot_ids, list):
            for raw in slot_ids:
                parsed = _parse_int(raw)
                if parsed is not None:
                    indices.append(parsed)
        else:
            single = _parse_int(change.get("slot_id"))
            if single is not None:
                indices.append(single)
        if not indices:
            continue
        names = change.get("names") if isinstance(change.get("names"), list) else []
        if not names and change.get("name") is not None:
            names = [change.get("name")]
        graphics = (
            change.get("graphics")
            if isinstance(change.get("graphics"), list)
            else []
        )
        if not graphics and change.get("graphic") is not None:
            graphics = [change.get("graphic")]
        entries.append((indices, list(names), list(graphics)))
    return entries


def resolve_slot_escort_seats(
    payload: Mapping[str, Any],
    adventure_id: int | None,
) -> EscortSeatResolution:
    """Resolve adventure ``slot_escort`` indices to technical position_ids."""
    from ic_gamedata.adventure_restrictions import _adventure_define

    adv = _adventure_define(dict(payload), adventure_id)
    if adv is None:
        return EscortSeatResolution(
            define_found=False,
            warnings=("adventure_define_missing",),
        )

    entries = _collect_slot_escort_entries(adv)
    if not entries:
        return EscortSeatResolution(define_found=True, escort_changes_present=False)

    raw_indices: list[int] = []
    # Parallel metadata aligned with flattened index order.
    name_by_index: dict[int, str] = {}
    graphic_by_index: dict[int, Any] = {}
    for indices, names, graphics in entries:
        for i, idx in enumerate(indices):
            raw_indices.append(idx)
            if i < len(names) and names[i] not in (None, ""):
                name_by_index[idx] = str(names[i])
            if i < len(graphics) and graphics[i] not in (None, "", -1):
                graphic_by_index[idx] = graphics[i]

    index_map, node_count, layout_warnings = current_formation_index_map(
        payload, adventure_id
    )
    warnings = list(layout_warnings)

    if not index_map:
        return EscortSeatResolution(
            position_ids=frozenset(),
            unresolved_indices=tuple(raw_indices),
            raw_indices=tuple(raw_indices),
            define_found=True,
            escort_changes_present=True,
            warnings=tuple(warnings)
            if warnings
            else ("no_formation_layout",),
        )

    mapped = resolve_formation_indices(
        raw_indices,
        index_to_position=index_map,
        layout_node_count=node_count,
    )
    warnings.extend(mapped.warnings)

    meta: dict[int, dict[str, Any]] = {}
    for idx, pos in mapped.index_to_position.items():
        blocker: dict[str, Any] = {"type": "escort"}
        name = name_by_index.get(idx)
        if name:
            blocker["name"] = name
        graphic = graphic_by_index.get(idx)
        if graphic is not None:
            gid = _parse_int(graphic)
            if gid is not None:
                blocker["graphic_id"] = gid
        meta[pos] = blocker

    return EscortSeatResolution(
        position_ids=mapped.position_ids,
        unresolved_indices=mapped.unresolved_indices,
        meta_by_position=meta,
        raw_indices=tuple(raw_indices),
        define_found=True,
        escort_changes_present=True,
        warnings=tuple(dict.fromkeys(warnings)),
        source=_SLOT_ESCORT_SOURCE,
    )
