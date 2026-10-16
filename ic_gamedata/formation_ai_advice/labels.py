"""Human-readable labels for formation positions and specialization groups."""

from __future__ import annotations

from typing import Any

_ZONE_NL = {
    "front": "voor",
    "mid": "midden",
    "back": "achter",
}


def zone_label_nl(zone: str | None) -> str:
    if not zone:
        return "?"
    return _ZONE_NL.get(str(zone).lower(), str(zone))


def specialization_group_label(
    *,
    group_id: str,
    tier_index: int | None = None,
    required_level: int | None = None,
    choice_order: int | None = None,
) -> str:
    """Readable group name; keep group_id stable for machine validation."""
    order = choice_order
    if order is None and tier_index is not None:
        order = int(tier_index) + 1
    if order is None and group_id.startswith("tier_"):
        try:
            order = int(group_id.split("_", 1)[1]) + 1
        except ValueError:
            order = None
    if order is None:
        base = "Specialisatiekeuze"
    else:
        base = f"Keuze {order}"
    if required_level is not None and required_level > 0:
        return f"{base} (lvl {required_level})"
    return base


def group_label_from_export_group(group: dict[str, Any]) -> str:
    if not isinstance(group, dict):
        return "Specialisatiekeuze"
    explicit = group.get("group_label")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    opts = group.get("options") or []
    levels = [
        int(o["required_level"])
        for o in opts
        if isinstance(o, dict) and isinstance(o.get("required_level"), int)
    ]
    min_level = min(levels) if levels else None
    return specialization_group_label(
        group_id=str(group.get("group_id") or ""),
        tier_index=group.get("tier_index") if isinstance(group.get("tier_index"), int) else None,
        required_level=min_level,
        choice_order=group.get("choice_order")
        if isinstance(group.get("choice_order"), int)
        else None,
    )


def position_caption(
    *,
    position_id: int,
    column: int | None,
    zone: str | None,
    row_order: int | float | None = None,
) -> str:
    """Physical place label — not the champion's permanent F-seat.

    Always includes ``position_id`` so columns with multiple seats stay unique.
    """
    zone_txt = zone_label_nl(zone)
    if column is None:
        base = f"Positie {position_id} — {zone_txt}"
    else:
        base = f"Positie {position_id} · Kolom {column + 1} — {zone_txt}"
    if row_order is None:
        return base
    # 0 = top of column in our export convention.
    row = int(row_order)
    if row <= 0:
        vert = "boven"
    elif row == 1:
        vert = "midden"
    else:
        vert = "onder"
    return f"{base} ({vert})"


def champion_seat_caption(permanent_seat: int | None) -> str:
    if permanent_seat is None:
        return "Seat ?"
    return f"Seat {permanent_seat}"


def formation_display_sort_key(
    *,
    column_index: int | None,
    row_order: int | float | None = None,
    position_id: int = 0,
) -> tuple[int, float, int]:
    """Table/board reading order: back column → front, top → bottom within column.

    ``column_index`` is 0-based (0 = front / Kolom 1). Higher index = farther back
    (Kolom 5 before Kolom 1). ``row_order`` / y: lower = higher on screen.
    """
    col = int(column_index) if column_index is not None else 0
    row = float(row_order) if row_order is not None else 0.0
    return (-col, row, int(position_id))


def sort_positions_for_display(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort export ``formation.positions`` rows for tables and clipboard."""
    return sorted(
        (p for p in positions if isinstance(p, dict)),
        key=lambda p: formation_display_sort_key(
            column_index=p.get("column_index")
            if isinstance(p.get("column_index"), int)
            else None,
            row_order=p.get("row_order"),
            position_id=int(p["position_id"])
            if isinstance(p.get("position_id"), int)
            else 0,
        ),
    )
