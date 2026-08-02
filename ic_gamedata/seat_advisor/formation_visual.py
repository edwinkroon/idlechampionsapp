"""Formation node positions for visual grid."""

from __future__ import annotations

from typing import Any

from ic_gamedata.formation_advisor.topology import load_formation_topology
from ic_gamedata.formation_seats import active_formation_seats
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.seat_advisor.models import VisualSeatNode


def _parse_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


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


def _seat_by_hero(instance: dict[str, Any]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    seats = instance.get("hero_in_seats")
    if not isinstance(seats, dict):
        return mapping
    for seat_raw, hero_raw in seats.items():
        seat = _parse_int(seat_raw)
        hero_id = _parse_int(hero_raw)
        if seat is not None and hero_id is not None and hero_id > 0 and 1 <= seat <= 12:
            mapping[hero_id] = seat
    return mapping


def _formation_grid_hero_ids(instance: dict[str, Any], payload: dict[str, Any]) -> list[int]:
    """Hero IDs per formation grid index — prefer the densest live/save/details grid."""

    def _ids(raw: Any) -> list[int]:
        if not isinstance(raw, list):
            return []
        result: list[int] = []
        for item in raw:
            hero_id = _parse_int(item)
            result.append(hero_id if hero_id is not None else -1)
        return result

    def _filled(grid: list[int]) -> int:
        return sum(1 for hero_id in grid if hero_id > 0)

    candidates: list[list[int]] = []
    live = _ids(instance.get("formation"))
    if live:
        candidates.append(live)

    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    details_live = _ids(details.get("formation"))
    if details_live:
        candidates.append(details_live)

    saves = instance.get("formation_saves_v2")
    if not isinstance(saves, list) or not saves:
        saves = details.get("formation_saves_v2")
    if isinstance(saves, list):
        for save in saves:
            if not isinstance(save, dict):
                continue
            grid = _ids(save.get("formation"))
            if grid:
                candidates.append(grid)

    if not candidates:
        return []
    return max(candidates, key=_filled)


def _make_visual_node(
    *,
    seat: int,
    x: float,
    y: float,
    zone: str,
    hero_id: int | None,
    hero_name_by_id: dict[int, str],
    seat_meta: dict[int, dict[str, Any]],
    active_seats: frozenset[int],
) -> VisualSeatNode:
    meta = seat_meta.get(seat, {})
    return VisualSeatNode(
        seat=seat,
        x=x,
        y=y,
        zone=zone,
        hero_id=hero_id,
        hero_name=hero_name_by_id.get(hero_id) if hero_id else None,
        effective_role=meta.get("effective_role"),
        inferred_role=meta.get("inferred_role"),
        chosen_role=meta.get("chosen_role"),
        is_bud=bool(meta.get("is_bud")),
        has_issue=bool(meta.get("has_issue")),
        is_active=seat in active_seats,
    )


def _formation_nodes_from_changes(changes: list[Any]) -> tuple[str, list[dict[str, Any]]] | None:
    for change in changes:
        if not isinstance(change, dict):
            continue
        if str(change.get("type") or "").strip().lower() != "formation":
            continue
        formation = change.get("formation")
        if isinstance(formation, list) and formation:
            nodes = [node for node in formation if isinstance(node, dict)]
            if nodes:
                name = str(change.get("name") or "Formation")
                return name, nodes
    return None


def _adventure_define(payload: dict[str, Any], adventure_id: int | None) -> dict[str, Any] | None:
    if adventure_id is None:
        return None
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return None
    for adv in defines.get("adventure_defines") or []:
        if isinstance(adv, dict) and _parse_int(adv.get("id")) == adventure_id:
            return adv
    return None


def _campaign_id_for_adventure(payload: dict[str, Any], adventure_id: int | None) -> int | None:
    adv = _adventure_define(payload, adventure_id)
    if adv is None:
        return None
    return _parse_int(adv.get("campaign_id"))


def load_formation_graph(
    payload: dict[str, Any],
    adventure_id: int | None,
) -> tuple[str, list[dict[str, Any]]]:
    defines = payload.get("defines")
    if isinstance(defines, dict):
        adv = _adventure_define(payload, adventure_id)
        if adv is not None:
            found = _formation_nodes_from_changes(adv.get("game_changes") or [])
            if found:
                return found
        campaign_id = _campaign_id_for_adventure(payload, adventure_id)
        if campaign_id is not None:
            for campaign in defines.get("campaign_defines") or []:
                if not isinstance(campaign, dict):
                    continue
                if _parse_int(campaign.get("id")) != campaign_id:
                    continue
                found = _formation_nodes_from_changes(campaign.get("game_changes") or [])
                if found:
                    return found
    return "Diamond Formation", []


# Game formation graphs use a compact coord system (~0–80). Scale up so 96×56
# seat cards don't sit on top of each other.
_GRAPH_SCALE_X = 5.0
_GRAPH_SCALE_Y = 3.5
_CARD_GAP_X = 110.0
_CARD_GAP_Y = 72.0


def _node_xy(node: dict[str, Any], index: int) -> tuple[float, float]:
    x = _parse_float(node.get("x"))
    y = _parse_float(node.get("y"))
    if x is None:
        x = float(index % 3) * 20.0
    if y is None:
        y = float(index // 3) * 20.0
    return x * _GRAPH_SCALE_X, y * _GRAPH_SCALE_Y


def _unique_grid_xy(index: int) -> tuple[float, float]:
    col = index % 4
    row = index // 4
    return float(col) * _CARD_GAP_X, float(row) * _CARD_GAP_Y


def build_visual_nodes(
    payload: dict[str, Any],
    adventure_id: int | None,
    *,
    hero_name_by_id: dict[int, str],
    seat_meta: dict[int, dict[str, Any]],
    formation_seats: dict[int, int] | None = None,
) -> tuple[VisualSeatNode, ...]:
    """
    Build visual seat nodes.

    formation_seats: optional hero_id → seat from Party Advisor formation
    (used when instance.hero_in_seats is missing/empty on live API).
    """
    formation_name, nodes = load_formation_graph(payload, adventure_id)
    _ = formation_name
    instance = _active_instance(payload) or {}
    seat_by_hero = _seat_by_hero(instance)
    if formation_seats:
        for hero_id, seat in formation_seats.items():
            if hero_id > 0 and 1 <= seat <= 12:
                seat_by_hero.setdefault(hero_id, seat)
    hero_by_seat = {seat: hid for hid, seat in seat_by_hero.items()}
    formation_ids = _formation_grid_hero_ids(instance, payload)
    _active_id, active_seats = active_formation_seats(payload)
    if not active_seats and hero_by_seat:
        active_seats = frozenset(hero_by_seat)
    topo = load_formation_topology(payload, adventure_id)

    index_to_seat: dict[int, int] = {}
    for index, hero_id in enumerate(formation_ids):
        if hero_id <= 0:
            continue
        seat = seat_by_hero.get(hero_id)
        if seat is not None and seat not in index_to_seat.values():
            index_to_seat[index] = seat

    occupied_seats = sorted(hero_by_seat)
    if not occupied_seats:
        return ()

    nodes_out: list[VisualSeatNode] = []
    placed_seats: set[int] = set()

    if nodes:
        # 1) Place seats known from the live/save formation grid onto graph nodes.
        for index, node in enumerate(nodes):
            seat = index_to_seat.get(index)
            if seat is None or seat in placed_seats:
                continue
            x, y = _node_xy(node, index)
            nodes_out.append(
                _make_visual_node(
                    seat=seat,
                    x=x,
                    y=y,
                    zone=topo.seat_zone.get(seat, "mid"),
                    hero_id=hero_by_seat.get(seat),
                    hero_name_by_id=hero_name_by_id,
                    seat_meta=seat_meta,
                    active_seats=active_seats,
                )
            )
            placed_seats.add(seat)

        # 2) Remaining occupied seats → unused graph slots (keeps Witchlight shape).
        unused_indices = [i for i in range(len(nodes)) if i not in index_to_seat]
        remaining = [seat for seat in occupied_seats if seat not in placed_seats]
        for seat, index in zip(remaining, unused_indices):
            x, y = _node_xy(nodes[index], index)
            nodes_out.append(
                _make_visual_node(
                    seat=seat,
                    x=x,
                    y=y,
                    zone=topo.seat_zone.get(seat, "mid"),
                    hero_id=hero_by_seat.get(seat),
                    hero_name_by_id=hero_name_by_id,
                    seat_meta=seat_meta,
                    active_seats=active_seats,
                )
            )
            placed_seats.add(seat)

        # 3) Still more champions than formation slots → unique overflow grid to the right.
        overflow = [seat for seat in occupied_seats if seat not in placed_seats]
        if overflow:
            max_x = max((n.x for n in nodes_out), default=0.0)
            for offset, seat in enumerate(overflow):
                x, y = _unique_grid_xy(offset)
                nodes_out.append(
                    _make_visual_node(
                        seat=seat,
                        x=max_x + _CARD_GAP_X + x,
                        y=y,
                        zone=topo.seat_zone.get(seat, "mid"),
                        hero_id=hero_by_seat.get(seat),
                        hero_name_by_id=hero_name_by_id,
                        seat_meta=seat_meta,
                        active_seats=active_seats,
                    )
                )
                placed_seats.add(seat)
    else:
        # No graph: unique grid so seats never share coordinates.
        for index, seat in enumerate(occupied_seats):
            x, y = _unique_grid_xy(index)
            nodes_out.append(
                _make_visual_node(
                    seat=seat,
                    x=x,
                    y=y,
                    zone=topo.seat_zone.get(seat, "mid"),
                    hero_id=hero_by_seat.get(seat),
                    hero_name_by_id=hero_name_by_id,
                    seat_meta=seat_meta,
                    active_seats=active_seats,
                )
            )

    return tuple(nodes_out)
