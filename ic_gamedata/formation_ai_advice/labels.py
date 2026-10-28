"""Human-readable labels for formation positions and specialization groups."""

from __future__ import annotations

from typing import Any

_ZONE_NL = {
    "front": "voor",
    "mid": "midden",
    "back": "achter",
}

# Human-facing place notation: ``display_column``-``display_slot`` (e.g. ``1-1``).
# Technical ``position_id`` / permanent seats stay separate for import JSON.
POSITION_DISPLAY_CONVENTION: dict[str, Any] = {
    "format": "column-slot",
    "column_order": "back_to_front",
    "slot_order": "top_to_bottom",
    "index_base": 1,
    "active_positions_only": True,
    "example": "1-1",
    "technical_id_field": "id",
    "row_direction": "lower_row_is_top",
    "known_column_direction_rules": (
        "lower_column_is_front",
        "lower_column_index_is_front",
    ),
}

_LOWER_COLUMN_IS_FRONT = frozenset(
    {
        "lower_column_is_front",
        "lower_column_index_is_front",
    }
)


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


def specialization_choice_display(
    name: str | None,
    *,
    advised_option_id: int | None = None,
    current_option_id: int | None = None,
    selection_status: str | None = None,
    required_level: int | None = None,
) -> str:
    """One specialization-group fragment for the Specialisatie(s) table column.

    Status labels (Dutch, exact):
    - new advice → ``Naam (advies)``
    - same as current → ``Naam (actief)``
    - current kept, no new advice → ``Naam (behouden)``
    - no current and no advice → ``Nog te kiezen — geen nieuw advies``
    - advised but not unlocked → ``Naam (advies vanaf lvl X)`` or
      ``Naam (advies na ontgrendeling)``
    Unresolvable names become ``Onbekend`` (never invent from champion name).
    """
    label = (name or "").strip() or "Onbekend"
    not_unlocked = str(selection_status or "").strip().casefold() == "not_unlocked"

    if isinstance(advised_option_id, int):
        if not_unlocked:
            if isinstance(required_level, int) and required_level > 0:
                return f"{label} (advies vanaf lvl {required_level})"
            return f"{label} (advies na ontgrendeling)"
        if (
            isinstance(current_option_id, int)
            and current_option_id == advised_option_id
        ):
            return f"{label} (actief)"
        return f"{label} (advies)"

    if isinstance(current_option_id, int):
        return f"{label} (behouden)"

    return "Nog te kiezen — geen nieuw advies"


def format_specializations_table_cell(group_fragments: list[str]) -> str:
    """Join group fragments for the Specialisatie(s) column.

    Single group: fragment as-is. Multiple groups: ``Keuze 1: …; Keuze 2: …``
    in existing group order.
    """
    parts = [str(p).strip() for p in group_fragments if str(p).strip()]
    if not parts:
        return "Nog te kiezen — geen nieuw advies"
    if len(parts) == 1:
        return parts[0]
    return "; ".join(f"Keuze {i}: {part}" for i, part in enumerate(parts, start=1))


def position_caption(
    *,
    position_id: int,
    column: int | None,
    zone: str | None,
    row_order: int | float | None = None,
    display_position: str | None = None,
) -> str:
    """Physical place label — not the champion's permanent F-seat.

    Prefer ``display_position`` (``kolom-plek``, e.g. ``1-1``) when known.
    Technical ``position_id`` remains available for import, not as the
    primary human label.
    """
    zone_txt = zone_label_nl(zone)
    if display_position:
        return f"Plek {display_position} — {zone_txt}"
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


def resolve_column_direction_rule(front_direction: Any) -> str | None:
    """Return a known column-direction rule string, or None if unknown."""
    if isinstance(front_direction, dict):
        raw = front_direction.get("rule") or front_direction.get("id")
    else:
        raw = front_direction
    if raw is None:
        return None
    text = str(raw).strip().casefold().replace("-", "_")
    # Normalise common aliases.
    aliases = {
        "lower_column_is_front": "lower_column_is_front",
        "lower_column_index_is_front": "lower_column_is_front",
        "higher_column_is_front": "higher_column_is_front",
        "higher_column_index_is_front": "higher_column_is_front",
    }
    return aliases.get(text)


def _position_column_value(row: dict[str, Any]) -> int | None:
    for key in ("column_index", "column"):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value == int(value):
            return int(value)
    return None


def _position_row_value(row: dict[str, Any]) -> float:
    for key in ("row_order", "row"):
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return 0.0


def _position_tech_id(row: dict[str, Any]) -> int:
    for key in ("position_id", "id"):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _is_active_position(row: dict[str, Any]) -> bool:
    state = row.get("state")
    if state is None:
        return True
    return str(state).casefold() == "active"


def formation_display_sort_key(
    *,
    column_index: int | None,
    row_order: int | float | None = None,
    position_id: int = 0,
    column_direction_rule: str | None = "lower_column_is_front",
) -> tuple[int, float, int]:
    """Table/board reading order: back column → front, top → bottom within column.

    With ``lower_column_is_front``, higher ``column_index`` is farther back
    (sorted first). ``row_order`` / y: lower = higher on screen (top first).
    """
    col = int(column_index) if column_index is not None else 0
    row = float(row_order) if row_order is not None else 0.0
    rule = resolve_column_direction_rule(column_direction_rule) or "lower_column_is_front"
    if rule == "higher_column_is_front":
        col_key = col
    else:
        # lower_column_is_front: back = highest column index
        col_key = -col
    return (col_key, row, int(position_id))


def sort_positions_for_display(
    positions: list[dict[str, Any]],
    *,
    column_direction_rule: str | None = "lower_column_is_front",
) -> list[dict[str, Any]]:
    """Sort export ``formation.positions`` rows for tables and clipboard."""
    return sorted(
        (p for p in positions if isinstance(p, dict)),
        key=lambda p: formation_display_sort_key(
            column_index=_position_column_value(p),
            row_order=_position_row_value(p),
            position_id=_position_tech_id(p),
            column_direction_rule=column_direction_rule,
        ),
    )


def assign_display_positions(
    positions: list[dict[str, Any]],
    *,
    column_direction: Any = "lower_column_is_front",
    active_only: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach display_column / display_slot / display_position from geometry.

    Numbering is derived only from column direction + row order among active
    positions — never from position_id, permanent seat, or array order.
    Returns ``(updated_rows, issues)``.
    """
    rule = resolve_column_direction_rule(column_direction)
    issues: list[dict[str, Any]] = []
    if rule is None:
        issues.append(
            {
                "code": "unknown_column_direction",
                "severity": "error",
                "message": (
                    "Kolomrichting ontbreekt of is onbekend — "
                    "display_position wordt niet gegokt."
                ),
                "fix": (
                    "Exporteer opnieuw met een bekende front_direction.rule "
                    "(bijv. lower_column_is_front)."
                ),
            }
        )
        cleaned: list[dict[str, Any]] = []
        for row in positions:
            if not isinstance(row, dict):
                continue
            out = dict(row)
            out.pop("display_column", None)
            out.pop("display_slot", None)
            out.pop("display_position", None)
            cleaned.append(out)
        return cleaned, issues

    # Group active (or all) rows by geometry column.
    by_col: dict[int, list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []
    for row in positions:
        if not isinstance(row, dict):
            continue
        out = dict(row)
        out.pop("display_column", None)
        out.pop("display_slot", None)
        out.pop("display_position", None)
        col = _position_column_value(out)
        if col is None:
            issues.append(
                {
                    "code": "missing_column_for_display",
                    "severity": "warning",
                    "position_id": _position_tech_id(out) or None,
                    "message": (
                        f"Positie {_position_tech_id(out)} heeft geen kolom — "
                        "geen display_position."
                    ),
                }
            )
            passthrough.append(out)
            continue
        if active_only and not _is_active_position(out):
            passthrough.append(out)
            continue
        by_col.setdefault(col, []).append(out)

    if rule in _LOWER_COLUMN_IS_FRONT:
        # Back → front: highest geometry column first → display_column 1.
        ordered_cols = sorted(by_col.keys(), reverse=True)
    else:
        # higher_column_is_front: back = lowest column index.
        ordered_cols = sorted(by_col.keys())

    numbered: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for display_col, geo_col in enumerate(ordered_cols, start=1):
        slots = sorted(
            by_col[geo_col],
            key=lambda r: (_position_row_value(r), _position_tech_id(r)),
        )
        for display_slot, row in enumerate(slots, start=1):
            label = f"{display_col}-{display_slot}"
            if label in seen_labels:
                issues.append(
                    {
                        "code": "duplicate_display_position",
                        "severity": "error",
                        "message": f"Dubbele display_position {label}.",
                    }
                )
            seen_labels.add(label)
            row = dict(row)
            row["display_column"] = display_col
            row["display_slot"] = display_slot
            row["display_position"] = label
            # Refresh human label when present.
            if "label" in row or "position_id" in row:
                row["label"] = position_caption(
                    position_id=_position_tech_id(row),
                    column=_position_column_value(row),
                    zone=str(row["zone"]) if row.get("zone") else None,
                    row_order=_position_row_value(row),
                    display_position=label,
                )
            numbered.append(row)

    # Preserve blocked / incomplete rows after numbered actives, still
    # sorted by geometry reading order for stable output.
    combined = numbered + passthrough
    combined = sort_positions_for_display(
        combined, column_direction_rule=rule
    )
    return combined, issues


def position_display_convention_block(
    *,
    technical_id_field: str = "id",
) -> dict[str, Any]:
    """Machine-readable convention for exports / AI instructions."""
    return {
        **POSITION_DISPLAY_CONVENTION,
        "technical_id_field": technical_id_field,
    }


# Shared AI instruction for every advice-export entry point.
POSITION_DISPLAY_AI_INSTRUCTION = (
    "Gebruik voor de leesbare formatietabel de aangeleverde display_position "
    "in het formaat kolom-plek, bijvoorbeeld 1-1. Het eerste nummer telt de "
    "kolommen van achter naar voren; het tweede nummer telt de plekken binnen "
    "die kolom van boven naar beneden. Gebruik de kolommen ‘Plek’, "
    "‘Champion’ en ‘Specialisatie(s)’ en sorteer op display_column en "
    "vervolgens display_slot. In de kolom Champion: ‘Naam (seat N)’ met de "
    "permanente F-seat uit het veld `seat` (bijv. Hitch (seat 3)). "
    "Plek = display_position; seat = permanente F-toets — die twee niet "
    "verwisselen. Toon geen technische position_id’s in de Plek-kolom. "
    "Gebruik in uitleg over verplaatsingen dezelfde notatie. Behoud in het "
    "import-JSON juist de echte position_id’s; vervang deze nooit door de "
    "weergavenotatie. Vulregels voor Specialisatie(s): "
    "BASE_SNAPSHOT.answer_contract.display_vs_import."
)

ADVICE_REPLY_FORMAT_INSTRUCTION = (
    "Antwoordvorm (verplicht, zelfstandig — geen eerdere chat nodig):\n"
    "1. Een leesbare formatietabel met kolommen ‘Plek’, ‘Champion’ en "
    "‘Specialisatie(s)’, gesorteerd op display_column en daarna "
    "display_slot (bijv. 1-1, 1-2, 2-1, …). Champion-cel: Naam (seat N).\n"
    "2. Eventuele korte uitleg onder de tabel.\n"
    "3. Precies één importeerbaar JSON-object in één afgesloten "
    "Markdown-codeblok met taal json, volgens het bestaande "
    "antwoordschema, met technische position_id’s "
    "(niet de weergavenotatie).\n"
    f"{POSITION_DISPLAY_AI_INSTRUCTION}"
)

ADVICE_TABLE_HEADER_EXAMPLE = (
    "| Plek | Champion | Specialisatie(s) |\n"
    "| --- | --- | --- |\n"
    "| 1-1 | Hitch (seat 3) | Charismatic (actief) |\n"
    "| 2-1 | Celeste (seat 2) | Keuze 1: War Domain (advies); "
    "Keuze 2: Life Domain (behouden) |"
)
