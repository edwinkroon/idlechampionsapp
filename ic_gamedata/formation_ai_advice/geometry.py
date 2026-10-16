"""Distance on the active-position graph.

Blocked and reserved seats stay in the physical adjacency list, but hops used
for this export do not travel through them. That is an export rule, not a
claim that every in-game ability ignores escorts.
"""

from __future__ import annotations

from collections import deque
from typing import Any


def assess_active_graph(
    active_ids: list[int],
    blocked_ids: list[int],
    adjacency: dict[int, list[int]],
    *,
    authoritative: bool,
) -> dict[str, Any]:
    active = set(active_ids)
    blocked = set(blocked_ids)
    graph: dict[int, list[int]] = {}
    only_blocked: list[int] = []
    for seat in sorted(active):
        neighbors = [n for n in adjacency.get(seat, []) if n != seat]
        active_neighbors = [n for n in neighbors if n in active]
        blocked_neighbors = [n for n in neighbors if n in blocked]
        graph[seat] = active_neighbors
        if neighbors and not active_neighbors and blocked_neighbors:
            only_blocked.append(seat)

    components = _components(graph)
    matrix: dict[str, int | str] = {}
    for left in sorted(active):
        distances = _bfs(left, graph)
        for right in sorted(active):
            if right <= left:
                continue
            hop = distances.get(right)
            matrix[f"{left}-{right}"] = hop if hop is not None else "unreachable"

    issues: list[dict[str, Any]] = []
    if only_blocked:
        issues.append(
            {
                "code": "active_only_blocked_neighbors",
                "severity": "warning",
                "position_ids": only_blocked,
                "message": (
                    "Actieve positie(s) hebben alleen blocked/reserved buren. "
                    "Op de actieve graaf zijn dat geïsoleerde componenten."
                ),
                "fix": "Afstand niet als bereikbaar behandelen; mechanic per effect controleren.",
            }
        )
    if len(components) > 1:
        issues.append(
            {
                "code": "disconnected_active_graph",
                "severity": "warning",
                "position_ids": [seat for group in components for seat in group],
                "message": (
                    f"Actieve graaf heeft {len(components)} componenten. "
                    "Hops lopen niet door blocked posities."
                ),
                "fix": "Onbereikbare paren staan als 'unreachable' in de matrix.",
            }
        )
    return {
        "issues": issues,
        "components": components,
        "distance": {
            "rule": "hops_on_active_adjacency",
            "paths_through_blocked": "excluded",
            "escorts_count_as_adjacent": "unknown",
            "front_column_is_attacked_slots": "unknown",
            "authoritative": authoritative,
            "note": (
                "Matrix = hops tussen geldige posities via fysieke adjacency, "
                "zonder paden door blocked/reserved. Of een ability escorts meetelt "
                "staat niet vast en blijft per effect onbekend tenzij dat effect "
                "zelf include_escorts zet. De voorste kolom is de lage column_index; "
                "dat die kolom ook de aangevallen slots zijn is niet vastgesteld."
                if authoritative
                else
                "Topologie is een heuristiek. De matrix is de exportregel, geen gamewaarheid."
            ),
            "values": matrix,
        },
    }


def _components(graph: dict[int, list[int]]) -> list[list[int]]:
    seen: set[int] = set()
    groups: list[list[int]] = []
    for start in sorted(graph):
        if start in seen:
            continue
        group: list[int] = []
        queue = deque([start])
        seen.add(start)
        while queue:
            seat = queue.popleft()
            group.append(seat)
            for other in graph.get(seat, []):
                if other not in seen:
                    seen.add(other)
                    queue.append(other)
        groups.append(sorted(group))
    return groups


def _bfs(start: int, graph: dict[int, list[int]]) -> dict[int, int]:
    dist = {start: 0}
    queue = deque([start])
    while queue:
        seat = queue.popleft()
        for other in graph.get(seat, []):
            if other not in dist:
                dist[other] = dist[seat] + 1
                queue.append(other)
    return dist
