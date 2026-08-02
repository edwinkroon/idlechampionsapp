"""Formation seat topology from API defines or heuristic fallback."""



from __future__ import annotations

from typing import Any

from ic_gamedata.formation_advisor.models import FormationTopology, Zone
from ic_gamedata.parsing import parse_int as _parse_int

_DEFAULT_ADJ: dict[int, frozenset[int]] = {

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



# UI seat zones for standard diamond when API bridge data is unavailable (seats 10–12).

_DIAMOND_FALLBACK_ZONE: dict[int, Zone] = {

    1: "front",

    2: "front",

    3: "front",

    4: "mid",

    5: "mid",

    6: "mid",

    7: "back",

    8: "back",

    9: "front",  # diamond tip — UI seat 9, not formation index 9

    10: "back",

    11: "back",

    12: "back",

}





def _zones_from_columns(seat_column: dict[int, int]) -> dict[int, Zone]:

    """Map column indices to front/mid/back relative to the active formation graph."""

    if not seat_column:

        return {}

    min_col = min(seat_column.values())

    max_col = max(seat_column.values())

    if max_col == min_col:

        front_max = min_col

        mid_max = min_col

    else:

        front_max = min_col + 1

        mid_max = min_col + 2 if max_col - min_col >= 3 else max_col

    zones: dict[int, Zone] = {}

    for seat, col in seat_column.items():

        if col <= front_max:

            zones[seat] = "front"

        elif col <= mid_max:

            zones[seat] = "mid"

        else:

            zones[seat] = "back"

    return zones





def _formation_grid_hero_ids(instance: dict[str, Any], payload: dict[str, Any]) -> list[int]:

    """Hero IDs per formation grid index (live grid, else best formation save)."""

    def _ids(raw: Any) -> list[int]:

        if not isinstance(raw, list):

            return []

        result: list[int] = []

        for item in raw:

            hero_id = _parse_int(item)

            result.append(hero_id if hero_id is not None else -1)

        return result



    live = _ids(instance.get("formation"))

    if sum(1 for hero_id in live if hero_id > 0) >= 2:

        return live



    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}

    saves = instance.get("formation_saves_v2")

    if not isinstance(saves, list) or not saves:

        saves = details.get("formation_saves_v2")

    if isinstance(saves, list):

        for save in saves:

            if not isinstance(save, dict):

                continue

            grid = _ids(save.get("formation"))

            if sum(1 for hero_id in grid if hero_id > 0) >= 2:

                return grid

    return live





def _seat_by_hero(instance: dict[str, Any]) -> dict[int, int]:

    mapping: dict[int, int] = {}

    seats = instance.get("hero_in_seats")

    if not isinstance(seats, dict):

        return mapping

    for seat_raw, hero_raw in seats.items():

        seat = _parse_int(seat_raw)

        hero_id = _parse_int(hero_raw)

        if seat is None or hero_id is None or hero_id <= 0:

            continue

        if 1 <= seat <= 12:

            mapping[hero_id] = seat

    return mapping





def _bridge_seat_layout(

    nodes: list[dict[str, Any]],

    formation_ids: list[int],

    seat_by_hero: dict[int, int],

) -> tuple[dict[int, int], dict[int, frozenset[int]]]:

    """

    Map UI seat numbers (F1–F12) to formation columns via the live formation grid.



    Formation node index != UI seat number (e.g. diamond tip is UI seat 9 at grid index 0).

    """

    index_to_seat: dict[int, int] = {}

    for index, hero_id in enumerate(formation_ids):

        if hero_id <= 0:

            continue

        seat = seat_by_hero.get(hero_id)

        if seat is not None:

            index_to_seat[index] = seat



    seat_column: dict[int, int] = {}

    seat_adjacency: dict[int, set[int]] = {}

    for index, node in enumerate(nodes):

        seat = index_to_seat.get(index)

        if seat is None:

            continue

        col = _parse_int(node.get("col"))

        if col is None:

            col = index

        seat_column[seat] = col

        neighbors: set[int] = set()

        raw_adj = node.get("adj")

        if isinstance(raw_adj, list):

            for adj_index in raw_adj:

                adj_i = _parse_int(adj_index)

                if adj_i is None:

                    continue

                neighbor_seat = index_to_seat.get(adj_i)

                if neighbor_seat is not None:

                    neighbors.add(neighbor_seat)

        seat_adjacency.setdefault(seat, set()).update(neighbors)



    return seat_column, {seat: frozenset(neighbors) for seat, neighbors in seat_adjacency.items()}





def _topology_from_formation_nodes(

    nodes: list[dict[str, Any]],

    *,

    source: str,

    formation_ids: list[int] | None = None,

    seat_by_hero: dict[int, int] | None = None,

) -> FormationTopology | None:

    if len(nodes) < 2:

        return None



    seat_column: dict[int, int] = {}

    seat_adjacency: dict[int, frozenset[int]] = {}



    if formation_ids and seat_by_hero:

        bridged_col, bridged_adj = _bridge_seat_layout(nodes, formation_ids, seat_by_hero)

        seat_column.update(bridged_col)

        seat_adjacency.update(bridged_adj)



    # Legacy index→seat fallback for nodes without a bridged hero (partial grids).

    for index, node in enumerate(nodes):

        seat = index + 1

        if seat in seat_column:

            continue

        col = _parse_int(node.get("col"))

        if col is None:

            col = ((seat - 1) % 4) + 1

        seat_column[seat] = col

        raw_adj = node.get("adj")

        neighbors: set[int] = set()

        if isinstance(raw_adj, list):

            for adj_index in raw_adj:

                adj_i = _parse_int(adj_index)

                if adj_i is not None:

                    neighbors.add(adj_i + 1)

        seat_adjacency[seat] = frozenset(neighbors)



    if not seat_column:

        return None



    seat_zone = _zones_from_columns(seat_column)

    for seat in range(1, 13):

        seat_zone.setdefault(seat, _DIAMOND_FALLBACK_ZONE.get(seat, "mid"))

        seat_column.setdefault(seat, ((seat - 1) % 4) + 1)

        seat_adjacency.setdefault(seat, _DEFAULT_ADJ.get(seat, frozenset()))



    return FormationTopology(

        seat_adjacency=seat_adjacency,

        seat_column=seat_column,

        seat_zone=seat_zone,

        source=source,

    )





def _formation_nodes_from_changes(changes: list[Any]) -> list[dict[str, Any]] | None:

    for change in changes:

        if not isinstance(change, dict):

            continue

        if str(change.get("type") or "").strip().lower() != "formation":

            continue

        formation = change.get("formation")

        if isinstance(formation, list) and formation:

            nodes = [node for node in formation if isinstance(node, dict)]

            if nodes:

                return nodes

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





def load_formation_topology(payload: dict[str, Any], adventure_id: int | None) -> FormationTopology:

    """Resolve seat adjacency from adventure/campaign API defines, else heuristic fallback."""

    instance = _active_instance(payload) or {}

    formation_ids = _formation_grid_hero_ids(instance, payload)

    seat_by_hero = _seat_by_hero(instance)



    defines = payload.get("defines")

    if isinstance(defines, dict):

        adv = _adventure_define(payload, adventure_id)

        if adv is not None:

            nodes = _formation_nodes_from_changes(adv.get("game_changes") or [])

            if nodes:

                topo = _topology_from_formation_nodes(

                    nodes,

                    source="api_adventure",

                    formation_ids=formation_ids,

                    seat_by_hero=seat_by_hero,

                )

                if topo is not None:

                    return topo

        campaign_id = _campaign_id_for_adventure(payload, adventure_id)

        if campaign_id is not None:

            for campaign in defines.get("campaign_defines") or []:

                if not isinstance(campaign, dict):

                    continue

                if _parse_int(campaign.get("id")) != campaign_id:

                    continue

                nodes = _formation_nodes_from_changes(campaign.get("game_changes") or [])

                if nodes:

                    topo = _topology_from_formation_nodes(

                        nodes,

                        source="api_campaign",

                        formation_ids=formation_ids,

                        seat_by_hero=seat_by_hero,

                    )

                    if topo is not None:

                        return topo

    return _heuristic_topology()





def _heuristic_topology() -> FormationTopology:

    seat_column = {

        1: 0,

        2: 1,

        3: 1,

        4: 2,

        5: 2,

        6: 2,

        7: 3,

        8: 3,

        9: 0,

        10: 3,

        11: 4,

        12: 4,

    }

    seat_zone = dict(_DIAMOND_FALLBACK_ZONE)

    return FormationTopology(

        seat_adjacency=dict(_DEFAULT_ADJ),

        seat_column=seat_column,

        seat_zone=seat_zone,

        source="heuristic",

    )


