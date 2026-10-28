"""Split advice data into BASE_SNAPSHOT, ADVICE_REQUEST, and CHAMPION_DETAILS.

Reuses the existing champion/mechanics pipeline (``build_champion_entry``,
clipboard projection helpers, adventure eligibility evaluators). Does not
replace the legacy full clipboard export.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import Any, Iterable, Literal, Mapping

from ic_gamedata.formation_ai_advice.clipboard_export import (
    _HINT_ABILITY_MISSING,
    _project_champion_for_advice,
    _prune_empty,
)
from ic_gamedata.formation_ai_advice.export import (
    _ability_score_and_attack_maps,
    _data_version,
    _permanent_seat,
    _restriction_block,
    _utc_now_iso,
    build_champion_entry,
    build_export_payload,
)
from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION
from ic_gamedata.formation_ai_advice.mechanics_completeness import (
    assess_snapshot_mechanics_export_coverage,
    build_mechanics_completeness,
)
from ic_gamedata.advice_goals import GOAL_DEFINITIONS, USER_GOAL_IDS
from ic_gamedata.formation_ai_advice.labels import position_display_convention_block
from ic_gamedata.formation_ai_advice.reply_contract import (
    build_answer_contract_ref,
    build_static_answer_contract,
)
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_advisor_models import FormationHero

ExportKind = Literal["base_snapshot", "advice_request", "champion_details"]

SNAPSHOT_EXPORT_SCHEMA = "1.4"

_SOURCE_PRIORITY = (
    "BASE_SNAPSHOT levert mechanics, vaste championgegevens (o.a. gender, "
    "alignment, roles, specialization-opties), answer_contract, standaard "
    "geometry-layout en goal_catalog. ADVICE_REQUEST levert de actuele "
    "veranderlijke toestand en overschrijft daarvoor de snapshot: party, "
    "bezetting, geselecteerde specialisaties, actieve feats (compact), "
    "ontgrendelstatus, live stacks/fase, eligibility, en — wanneer de "
    "actuele formatielayout "
    "aantoonbaar afwijkt — de volledige actuele geometry (positions, "
    "adjacency, richtingen, displaymapping) als geheel. Actuele occupied "
    "blijft altijd de bron voor championbezetting. Actuele slot_states "
    "(occupancy/placeability, inclusief NPC/escort-blokkades) horen bij de "
    "veranderlijke adventure-/partystate en moeten altijd in ADVICE_REQUEST "
    "staan — ook wanneer layout_matches_base. geometry.ref en "
    "layout_matches_base hergebruiken alleen de structurele layout; ze "
    "nemen geen oude bezetting of plaatsbaarheid over. Ontbrekende of "
    "unknown actuele slot-state mag niet stilzwijgend worden aangevuld met "
    "oudere snapshotwaarden. available_position_ids bevat uitsluitend "
    "bevestigd lege, plaatsbare posities — niet afleiden uit "
    "len(valid_position_ids) - len(party). valid_position_ids is de "
    "volledige technische layout (inclusief escort/NPC-seats). Een compacte "
    "geometry.ref naar BASE_SNAPSHOT.geometry is alleen geldig wanneer de "
    "exporter de actuele layout structureel gelijk heeft bevonden aan de "
    "basislayout (layout_matches_base); alleen dezelfde valid_position_ids "
    "is onvoldoende. Layoutverschil met de basissnapshot is "
    "expected_state_override, geen material_source_conflict. Een actuele "
    "geselecteerde specialisatie vervangt de oudere selectie én een oudere "
    "status zoals not_unlocked voor dezelfde specialisatiegroep. Mechanics "
    "niet afleiden uit championnamen, herinnering of de geselecteerde optie."
)


def _goal_catalog_for_snapshot() -> dict[str, Any]:
    return {
        gid: {
            "label": GOAL_DEFINITIONS[gid].label,
            "description": GOAL_DEFINITIONS[gid].description,
            "primary_metric": GOAL_DEFINITIONS[gid].primary_metric,
            "priorities": list(GOAL_DEFINITIONS[gid].priorities),
        }
        for gid in USER_GOAL_IDS
    }


def _geometry_from_formation_block(
    formation_block: dict[str, Any],
    *,
    include_occupancy: bool = False,
    include_slot_states: bool = True,
) -> dict[str, Any]:
    """Geometry layout for the adventure formation shape.

    ``valid_position_ids`` is the full technical layout (including escort/NPC
    seats). Placeability lives in ``slot_states`` / derived id lists.
    """
    distance = (
        formation_block.get("distance")
        if isinstance(formation_block.get("distance"), dict)
        else {}
    )
    front_direction = formation_block.get("front_direction") or {
        "rule": "lower_column_is_front",
    }
    convention = formation_block.get("position_display_convention")
    if not isinstance(convention, dict):
        convention = position_display_convention_block(technical_id_field="id")
    else:
        convention = {**convention, "technical_id_field": "id"}
    positions = []
    for row in formation_block.get("positions") or []:
        if not isinstance(row, dict):
            continue
        item = {
            "id": row.get("position_id"),
            "column": row.get("column_index"),
            "row": row.get("row_order"),
            "zone": row.get("zone"),
            "display_column": row.get("display_column"),
            "display_slot": row.get("display_slot"),
            "display_position": row.get("display_position"),
        }
        if include_occupancy:
            item["champion_id"] = row.get("current_champion_id")
        positions.append(_prune_empty(item))
    block: dict[str, Any] = {
        "source": formation_block.get("geometry_source")
        or formation_block.get("formation_id"),
        "column_direction": front_direction,
        "row_direction": (
            front_direction.get("row_direction")
            if isinstance(front_direction, dict)
            else None
        )
        or "lower_row_is_top",
        "position_display_convention": convention,
        "distance_rule": distance.get("rule")
        or (formation_block.get("distance_definition") or {}).get("type")
        or "hops_on_active_adjacency",
        "valid_position_ids": formation_block.get("valid_position_ids")
        or formation_block.get("active_position_ids"),
        "blocked_position_ids": formation_block.get("blocked_position_ids"),
        "available_position_ids": formation_block.get("available_position_ids"),
        "unknown_placeability_position_ids": formation_block.get(
            "unknown_placeability_position_ids"
        ),
        "adjacency": formation_block.get("adjacency_by_position"),
        "positions": positions or None,
        "table_order_note": formation_block.get("table_order_note"),
    }
    if include_slot_states:
        slot_states = formation_block.get("slot_states")
        if isinstance(slot_states, list) and slot_states:
            block["slot_states"] = slot_states
    return _prune_empty(block)


_LAYOUT_POSITION_FIELDS = (
    "id",
    "column",
    "row",
    "zone",
    "display_column",
    "display_slot",
    "display_position",
)

_REQUIRED_LAYOUT_POSITION_FIELDS = (
    "id",
    "column",
    "row",
    "display_column",
    "display_slot",
    "display_position",
)


def _as_int_id(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _occupied_from_geometry(full_geometry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _prune_empty(
            {
                "id": row.get("id"),
                "champion_id": row.get("champion_id"),
            }
        )
        for row in (full_geometry.get("positions") or [])
        if isinstance(row, dict) and row.get("champion_id") is not None
    ]


def _layout_positions(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Active layout rows without occupancy (champions live in occupied)."""
    rows: list[dict[str, Any]] = []
    for row in geometry.get("positions") or []:
        if not isinstance(row, dict):
            continue
        pid = row.get("id")
        if pid is None:
            pid = row.get("position_id")
        item: dict[str, Any] = {"id": pid}
        for key in _LAYOUT_POSITION_FIELDS:
            if key == "id":
                continue
            if row.get(key) is not None:
                item[key] = row[key]
        if item.get("id") is None:
            continue
        rows.append(_prune_empty(item))
    return rows


def _normalize_adjacency(adjacency: Any) -> dict[str, list[int]]:
    if not isinstance(adjacency, dict):
        return {}
    out: dict[str, list[int]] = {}
    for key, neighbors in adjacency.items():
        kid = _as_int_id(key)
        if kid is None:
            continue
        norm: list[int] = []
        if isinstance(neighbors, (list, tuple)):
            for n in neighbors:
                nid = _as_int_id(n)
                if nid is not None:
                    norm.append(nid)
        out[str(kid)] = sorted(set(norm))
    return out


def geometry_layout_canonical(geometry: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic layout view — occupancy and key order do not matter."""
    if not isinstance(geometry, dict):
        return {}
    valid_raw = geometry.get("valid_position_ids") or []
    valid = sorted(
        {
            vid
            for vid in (_as_int_id(x) for x in valid_raw)
            if vid is not None
        }
    )
    positions: list[dict[str, Any]] = []
    for row in _layout_positions(geometry):
        pid = _as_int_id(row.get("id"))
        if pid is None:
            continue
        positions.append(
            {
                "id": pid,
                "column": row.get("column"),
                "row": row.get("row"),
                "zone": row.get("zone"),
                "display_column": row.get("display_column"),
                "display_slot": row.get("display_slot"),
                "display_position": row.get("display_position"),
            }
        )
    positions.sort(key=lambda r: int(r["id"]))
    col_dir = geometry.get("column_direction")
    if isinstance(col_dir, dict):
        col_rule = col_dir.get("rule")
    else:
        col_rule = col_dir
    return {
        "valid_position_ids": valid,
        "positions": positions,
        "adjacency": _normalize_adjacency(geometry.get("adjacency")),
        "column_direction_rule": col_rule,
        "row_direction": geometry.get("row_direction"),
        "distance_rule": geometry.get("distance_rule"),
    }


def geometry_layouts_equal(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> bool:
    """True when layouts match structurally (ignores occupancy / key order)."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    left_c = geometry_layout_canonical(left)
    right_c = geometry_layout_canonical(right)
    if not left_c.get("valid_position_ids") or not right_c.get("valid_position_ids"):
        return False
    return left_c == right_c


def geometry_layout_fingerprint(geometry: dict[str, Any] | None) -> str:
    """Stable hash of layout only (not occupancy)."""
    return _stable_content_hash(geometry_layout_canonical(geometry))


def geometry_layout_gaps(geometry: dict[str, Any] | None) -> list[str]:
    """Missing essential layout fields for placement advice — never invent."""
    if not isinstance(geometry, dict):
        return ["geometry"]
    gaps: list[str] = []
    valid_raw = geometry.get("valid_position_ids") or []
    valid = [
        vid
        for vid in (_as_int_id(x) for x in valid_raw)
        if vid is not None
    ]
    if not valid:
        gaps.append("valid_position_ids")
        return gaps

    # Display numbering is for champion-capable seats; escort/NPC blocks stay
    # in the technical layout without contiguous display_position slots.
    blocked = {
        vid
        for vid in (
            _as_int_id(x) for x in (geometry.get("blocked_position_ids") or [])
        )
        if vid is not None
    }
    for row in geometry.get("slot_states") or []:
        if not isinstance(row, dict):
            continue
        pid = _as_int_id(row.get("position_id"))
        if pid is None:
            continue
        if row.get("placeability") == "blocked":
            blocked.add(pid)

    pos_by_id: dict[int, dict[str, Any]] = {}
    for row in _layout_positions(geometry):
        pid = _as_int_id(row.get("id"))
        if pid is None:
            continue
        pos_by_id[pid] = row

    for pid in valid:
        row = pos_by_id.get(pid)
        if row is None:
            gaps.append(f"positions[{pid}]")
            continue
        required = _REQUIRED_LAYOUT_POSITION_FIELDS
        if pid in blocked:
            # Column/row needed for adjacency geometry; display_* optional.
            required = ("id", "column", "row")
        for field in required:
            if field == "id":
                continue
            if row.get(field) is None:
                gaps.append(f"positions[{pid}].{field}")

    adj = geometry.get("adjacency")
    if not isinstance(adj, dict):
        gaps.append("adjacency")
    else:
        adj_norm = _normalize_adjacency(adj)
        for pid in valid:
            if str(pid) not in adj_norm:
                gaps.append(f"adjacency[{pid}]")
        # Edges must only reference technical valid positions (incl. escorts).
        valid_set = set(valid)
        for key, neighbors in adj_norm.items():
            kid = _as_int_id(key)
            if kid is not None and kid not in valid_set:
                gaps.append(f"adjacency_inactive_key[{kid}]")
            for nid in neighbors:
                if nid not in valid_set:
                    gaps.append(f"adjacency_edge_to_inactive[{key}->{nid}]")

    col_dir = geometry.get("column_direction")
    if isinstance(col_dir, dict):
        if not col_dir.get("rule"):
            gaps.append("column_direction.rule")
    elif not col_dir:
        gaps.append("column_direction")

    if not geometry.get("row_direction"):
        gaps.append("row_direction")

    return gaps


def _live_placeability_fields(full_geometry: dict[str, Any]) -> dict[str, Any]:
    """Current occupancy + slot_states — never inherited from BASE_SNAPSHOT."""
    occupied = _occupied_from_geometry(full_geometry)
    return {
        "occupied": occupied or None,
        "slot_states": full_geometry.get("slot_states") or None,
        "blocked_position_ids": full_geometry.get("blocked_position_ids"),
        "available_position_ids": full_geometry.get("available_position_ids"),
        "unknown_placeability_position_ids": full_geometry.get(
            "unknown_placeability_position_ids"
        ),
    }


def _thin_geometry_for_request(full_geometry: dict[str, Any]) -> dict[str, Any]:
    """Live occupancy/placeability + verified base layout ref.

    Caller must confirm layout match. Slot_states are always current — never
    taken from BASE_SNAPSHOT.
    """
    live = _live_placeability_fields(full_geometry)
    return _prune_empty(
        {
            "ref": "BASE_SNAPSHOT.geometry",
            "layout_matches_base": True,
            "source": full_geometry.get("source"),
            "valid_position_ids": full_geometry.get("valid_position_ids"),
            **live,
        }
    )


def _full_current_geometry_for_request(
    full_geometry: dict[str, Any],
    *,
    incomplete: bool = False,
    gaps: list[str] | None = None,
) -> dict[str, Any]:
    """Full actuele layout — replaces BASE_SNAPSHOT.geometry as a whole."""
    live = _live_placeability_fields(full_geometry)
    block: dict[str, Any] = {
        "overrides_base_snapshot_geometry": True,
        "override_kind": "expected_state_override",
        "source": full_geometry.get("source"),
        "valid_position_ids": full_geometry.get("valid_position_ids"),
        **live,
        "positions": _layout_positions(full_geometry) or None,
        "adjacency": full_geometry.get("adjacency"),
        "column_direction": full_geometry.get("column_direction"),
        "row_direction": full_geometry.get("row_direction"),
        "position_display_convention": full_geometry.get(
            "position_display_convention"
        ),
        "distance_rule": full_geometry.get("distance_rule"),
        "table_order_note": full_geometry.get("table_order_note"),
    }
    if incomplete:
        block["layout_incomplete"] = True
        block["missing_layout_fields"] = list(gaps or []) or None
        # Never point consumers at BASE layout when current layout differs.
        block.pop("ref", None)
    return _prune_empty(block)


def geometry_for_advice_request(
    full_geometry: dict[str, Any],
    base_geometry: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Choose thin ref vs full current geometry for ADVICE_REQUEST.

    Returns ``(geometry_block, meta)`` where meta includes ``mode``:
    ``thin`` | ``full`` | ``incomplete``.
    """
    layouts_match = geometry_layouts_equal(full_geometry, base_geometry)
    if layouts_match:
        return (
            _thin_geometry_for_request(full_geometry),
            {
                "mode": "thin",
                "layouts_equal": True,
                "layout_fingerprint": geometry_layout_fingerprint(full_geometry),
            },
        )

    gaps = geometry_layout_gaps(full_geometry)
    if gaps:
        return (
            _full_current_geometry_for_request(
                full_geometry, incomplete=True, gaps=gaps
            ),
            {
                "mode": "incomplete",
                "layouts_equal": False,
                "gaps": gaps,
                "layout_fingerprint": geometry_layout_fingerprint(full_geometry),
            },
        )

    return (
        _full_current_geometry_for_request(full_geometry),
        {
            "mode": "full",
            "layouts_equal": False,
            "layout_fingerprint": geometry_layout_fingerprint(full_geometry),
        },
    )

_BRONREGELS = (
    _SOURCE_PRIORITY
    + " "
    "Gebruik complete, betrouwbare mechanicbeschrijvingen (effect) voor "
    "kwalitatieve interpretatie. effect_kind=bron is bronproza; "
    "effect_kind=gegenereerd is afgeleid. Ondersteunende ontbrekende "
    "parservelden zijn geen reden om duidelijke broninformatie te negeren. "
    "Verschillen tussen oudere snapshotselecties/ontgrendelstatus en de "
    "actuele aanvraag zijn expected_state_override (normaal), geen conflict. "
    "Meld alleen material_source_conflict (onopgeloste tegenstrijdigheid na "
    "bronprioriteit). Meld missing_comparison_data apart en beperk die "
    "onzekerheid tot de betreffende vergelijking. "
    "Bekende basiswaarden (definition_base) zijn geen actuele totale buffs "
    "na gear, upgrades en stacks — magnitude=basis_of_actueel_niet_berekend "
    "betekent dat de actuele totaalwaarde niet is berekend, niet dat de "
    "mechanic ontbreekt. magnitude=parameter_onbekend: een relevante "
    "parameter ontbreekt echt. "
    "Trait-wijzigingen van actieve feats met traits_already_in_effective=true "
    "zitten al in alignment/roles/tags — niet dubbel toepassen. "
    "Equipment-itemlevels zijn geen damagevermenigvuldigers. "
    "Permanent seat ≠ fysieke positie. "
    "Gender ≠ alignment ≠ roles ≠ tags (gendertag alleen via hero_defines). "
    "unknown ≠ leeg ≠ false ≠ niet van toepassing."
)

_REQUEST_BRONREGELS = (
    "Pas actuele toestand uit ADVICE_REQUEST toe vóór vergelijking en advies. "
    + _SOURCE_PRIORITY
    + " "
    "Verschillen met oudere snapshotselecties of ontgrendelstatus zijn "
    "normale overrides (expected_state_override), geen conflicten — meld ze "
    "niet als waarschuwing. Meld alleen materiële, onopgeloste "
    "tegenstrijdigheden (material_source_conflict). Meld ontbrekende "
    "vergelijkingsgegevens (missing_comparison_data) apart en beperk die "
    "onzekerheid tot de betreffende vergelijking; geef wel overig advies dat "
    "door beschikbare gegevens gedragen wordt. Geen bewezen optimale ranking "
    "wanneer noodzakelijke gegevens ontbreken. Huidige selectie bekend ≠ "
    "beste keuze aantoonbaar bepaald. Permanent seat ≠ positie. "
    "Geen verborgen top-N of tierlijst."
)

_GENDER_COMPARE_TAGS = frozenset({"female", "male", "non-binary", "nonbinary"})


def _stable_content_hash(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def minify_json(value: Any) -> str:
    """Machine-oriented JSON without whitespace."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def _ilvl_map(payload: dict[str, Any]) -> dict[int, int]:
    try:
        from ic_gamedata.party_advisor_formation import _loot_ilvl_by_hero
    except Exception:
        return {}
    details = payload.get("details")
    if not isinstance(details, dict):
        return {}
    return _loot_ilvl_by_hero(details)


def _slot_ilvl_map(payload: dict[str, Any]) -> dict[int, dict[int, int]]:
    try:
        from ic_gamedata.party_advisor_formation import _loot_slot_ilvls_by_hero
    except Exception:
        return {}
    details = payload.get("details")
    if not isinstance(details, dict):
        return {}
    return _loot_slot_ilvls_by_hero(details)


def _owned_rows(
    payload: dict[str, Any],
) -> list[tuple[int, str, tuple[str, ...], tuple[str, ...]]]:
    from ic_gamedata.party_advisor_formation import _owned_heroes

    return _owned_heroes(payload)


def _empty_formation() -> tuple[FormationHero, ...]:
    return ()


def _build_layout_context(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...] | None,
    *,
    goal: str = "push",
    context: str = "campaign",
):
    form = formation if formation is not None else _empty_formation()
    try:
        from ic_gamedata.adventure_restrictions import build_adventure_roster_filter

        adventure_id = None
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        active_id = _parse_int(details.get("active_game_instance_id"))
        for inst in details.get("game_instances") or []:
            if not isinstance(inst, dict):
                continue
            if active_id is None or _parse_int(inst.get("game_instance_id")) == active_id:
                adventure_id = _parse_int(inst.get("current_adventure_id"))
                break
        roster_filter = build_adventure_roster_filter(payload, adventure_id)
    except Exception:
        roster_filter = None
    return build_formation_layout_context(
        payload,
        form,
        goal=goal,  # type: ignore[arg-type]
        context=context,  # type: ignore[arg-type]
        roster_filter=roster_filter,
    )


def collect_owned_champion_entries(
    payload: dict[str, Any],
    *,
    formation: tuple[FormationHero, ...] | None = None,
    force_refresh_roster: bool = False,
    goal: str = "push",
    context: str = "campaign",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build full champion entries for every owned hero via the shared pipeline."""
    from ic_gamedata.formation_ai_advice.owned_roster_cache import (
        entries_for_save,
        load_owned_roster_cache,
        loadout_fingerprint,
        resolve_champion_entry,
        save_owned_roster_cache,
    )
    from ic_gamedata.formation_ai_advice.swap_export import _candidate_loadout_notes

    owned = _owned_rows(payload)
    owned_ids = [hid for hid, *_ in owned]
    ctx = _build_layout_context(payload, formation, goal=goal, context=context)
    scores_map, attack_map = _ability_score_and_attack_maps()
    ilvl_map = _ilvl_map(payload)
    slot_map = _slot_ilvl_map(payload)
    data_version = _data_version(payload)
    roster_cache = load_owned_roster_cache()
    cache_dirty = False
    entries: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    party_ids = {h.hero_id for h in (formation or ())}

    for hid, name, _roles, _tags in owned:
        fingerprint = loadout_fingerprint(
            payload,
            hid,
            ilvl=ilvl_map.get(hid),
            slot_ilvls=slot_map.get(hid),
            data_version=data_version,
        )

        def _builder(_hid: int = hid) -> dict[str, Any]:
            return build_champion_entry(
                payload,
                ctx,
                _hid,
                current_position=None,
                ilvl=ilvl_map.get(_hid),
                slot_ilvls=slot_map.get(_hid),
                scores_map=scores_map,
                attack_map=attack_map,
            )

        try:
            entry, source = resolve_champion_entry(
                cache=roster_cache,
                hero_id=hid,
                fingerprint=fingerprint,
                builder=_builder,
                force_refresh=force_refresh_roster,
            )
            if source == "built":
                cache_dirty = True
            entry = copy.deepcopy(entry)
            entry["owned"] = True
            entry["in_party"] = hid in party_ids
            entry["current_position"] = None
            entry["bench_loadout"] = _candidate_loadout_notes(entry)
            entries.append(entry)
        except Exception as exc:
            incomplete.append(
                {
                    "champion_id": hid,
                    "name": name,
                    "reason": f"Exportfout: {exc}",
                }
            )

    if cache_dirty:
        try:
            import time

            prior = roster_cache.get("cached_at")
            try:
                cached_at = float(prior) if prior else 0.0
            except (TypeError, ValueError):
                cached_at = 0.0
            if cached_at <= 0:
                cached_at = time.time()
            save_owned_roster_cache(entries_for_save(roster_cache), cached_at=cached_at)
        except OSError:
            pass

    coverage = {
        "owned_known_count": len(owned_ids),
        "included_count": len(entries),
        "incomplete_count": len(incomplete),
        "incomplete": incomplete or None,
        "note": (
            "Alle betrouwbaar owned champions horen in de basissnapshot, "
            "ongeacht huidige adventure-eligibility. Ontbrekende entries "
            "staan expliciet onder incomplete."
        ),
    }
    return entries, coverage


def _strip_transient_for_snapshot(projected: dict[str, Any]) -> dict[str, Any]:
    """Remove adventure/request-specific fields from a champion projection."""
    out = dict(projected)
    for key in (
        "position",
        "eligibility",
        "locked",
        "lock_reason",
        "live_state",
        "permanent_seat_vs_party",
        "inclusion",
        "inclusion_reason",
        "practical_availability",
        "in_party",
    ):
        out.pop(key, None)
    # Snapshot loadout: keep selected specs/feats as account state, but make
    # unknown bench loadout explicit (never imply empty).
    return _prune_empty(out)


def _catalog_shared_mechanics(
    champions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Deduplicate identical ability/feat/option bodies into shared catalogs."""
    ability_cat: dict[str, dict[str, Any]] = {}
    feat_cat: dict[str, dict[str, Any]] = {}
    option_cat: dict[str, dict[str, Any]] = {}
    out_champs: list[dict[str, Any]] = []

    def _body(row: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in row.items() if k != "id"}

    for champ in champions:
        c = dict(champ)
        abs_out: list[dict[str, Any]] = []
        for ab in c.get("abilities") or []:
            if not isinstance(ab, dict):
                continue
            aid = ab.get("id")
            if not isinstance(aid, int):
                abs_out.append(ab)
                continue
            key = str(aid)
            body = _body(ab)
            existing = ability_cat.get(key)
            if existing is None:
                ability_cat[key] = body
                abs_out.append({"ref": aid})
            elif existing == body:
                abs_out.append({"ref": aid})
            else:
                # Conflicting bodies for same id — keep inline to avoid lying.
                abs_out.append(ab)
        if abs_out:
            c["abilities"] = abs_out
        else:
            c.pop("abilities", None)

        feats_out: list[dict[str, Any]] = []
        for feat in c.get("active_feats") or []:
            if not isinstance(feat, dict):
                continue
            fid = feat.get("id")
            if not isinstance(fid, int):
                feats_out.append(feat)
                continue
            key = str(fid)
            body = _body(feat)
            existing = feat_cat.get(key)
            if existing is None:
                feat_cat[key] = body
                feats_out.append({"ref": fid})
            elif existing == body:
                feats_out.append({"ref": fid})
            else:
                feats_out.append(feat)
        if feats_out:
            c["active_feats"] = feats_out
        elif c.get("feats_status") == "unknown":
            c["active_feats"] = None
        else:
            c.pop("active_feats", None)

        specs_out: list[dict[str, Any]] = []
        for group in c.get("specializations") or []:
            if not isinstance(group, dict):
                continue
            g = dict(group)
            opts_out: list[dict[str, Any]] = []
            for opt in g.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                oid = opt.get("id")
                if not isinstance(oid, int):
                    opts_out.append(opt)
                    continue
                # selected/available are loadout/state — keep on the champion row.
                state_keys = {
                    "selected",
                    "available",
                    "unavailable_reason",
                }
                body = {k: v for k, v in opt.items() if k not in state_keys and k != "id"}
                key = str(oid)
                existing = option_cat.get(key)
                row: dict[str, Any] = {"ref": oid}
                for sk in state_keys:
                    if sk in opt:
                        row[sk] = opt[sk]
                if existing is None:
                    option_cat[key] = body
                    opts_out.append(_prune_empty(row))
                elif existing == body:
                    opts_out.append(_prune_empty(row))
                else:
                    opts_out.append(opt)
            g["options"] = opts_out or None
            specs_out.append(_prune_empty(g))
        if specs_out:
            c["specializations"] = specs_out
        else:
            c.pop("specializations", None)
        out_champs.append(_prune_empty(c))

    shared = _prune_empty(
        {
            "abilities": ability_cat or None,
            "feats": feat_cat or None,
            "specialization_options": option_cat or None,
            "hints": {
                "ability_missing": _HINT_ABILITY_MISSING,
            },
        }
    )
    return shared, out_champs


def _resolve_refs_in_champion(
    champ: dict[str, Any],
    shared: dict[str, Any],
) -> dict[str, Any]:
    """Expand catalog refs for tests / CHAMPION_DETAILS consumers."""
    out = copy.deepcopy(champ)
    abilities = shared.get("abilities") if isinstance(shared.get("abilities"), dict) else {}
    feats = shared.get("feats") if isinstance(shared.get("feats"), dict) else {}
    options = (
        shared.get("specialization_options")
        if isinstance(shared.get("specialization_options"), dict)
        else {}
    )

    resolved_abs: list[dict[str, Any]] = []
    for ab in out.get("abilities") or []:
        if isinstance(ab, dict) and "ref" in ab and str(ab["ref"]) in abilities:
            row = {"id": ab["ref"], **abilities[str(ab["ref"])]}
            resolved_abs.append(row)
        elif isinstance(ab, dict):
            resolved_abs.append(ab)
    if resolved_abs:
        out["abilities"] = resolved_abs

    resolved_feats: list[dict[str, Any]] = []
    for feat in out.get("active_feats") or []:
        if isinstance(feat, dict) and "ref" in feat and str(feat["ref"]) in feats:
            resolved_feats.append({"id": feat["ref"], **feats[str(feat["ref"])]})
        elif isinstance(feat, dict):
            resolved_feats.append(feat)
    if resolved_feats:
        out["active_feats"] = resolved_feats

    specs_out: list[dict[str, Any]] = []
    for group in out.get("specializations") or []:
        if not isinstance(group, dict):
            continue
        g = dict(group)
        opts: list[dict[str, Any]] = []
        for opt in g.get("options") or []:
            if isinstance(opt, dict) and "ref" in opt and str(opt["ref"]) in options:
                row = {"id": opt["ref"], **options[str(opt["ref"])]}
                for sk in ("selected", "available", "unavailable_reason"):
                    if sk in opt:
                        row[sk] = opt[sk]
                opts.append(row)
            elif isinstance(opt, dict):
                opts.append(opt)
        g["options"] = opts or None
        specs_out.append(g)
    if specs_out:
        out["specializations"] = specs_out
    return out


def all_refs_resolvable(snapshot: dict[str, Any]) -> bool:
    """True when every mechanic ref resolves inside the same snapshot."""
    shared = snapshot.get("shared") if isinstance(snapshot.get("shared"), dict) else {}
    abilities = shared.get("abilities") if isinstance(shared.get("abilities"), dict) else {}
    feats = shared.get("feats") if isinstance(shared.get("feats"), dict) else {}
    options = (
        shared.get("specialization_options")
        if isinstance(shared.get("specialization_options"), dict)
        else {}
    )
    for champ in snapshot.get("champions") or []:
        if not isinstance(champ, dict):
            return False
        for ab in champ.get("abilities") or []:
            if isinstance(ab, dict) and "ref" in ab and str(ab["ref"]) not in abilities:
                return False
        for feat in champ.get("active_feats") or []:
            if isinstance(feat, dict) and "ref" in feat and str(feat["ref"]) not in feats:
                return False
        for group in champ.get("specializations") or []:
            if not isinstance(group, dict):
                continue
            for opt in group.get("options") or []:
                if (
                    isinstance(opt, dict)
                    and "ref" in opt
                    and str(opt["ref"]) not in options
                ):
                    return False
    return True


def build_base_snapshot(
    payload: dict[str, Any],
    *,
    formation: tuple[FormationHero, ...] | None = None,
    force_refresh_roster: bool = False,
    request_id: str | None = None,
    goal: str = "push",
    context: str = "campaign",
) -> dict[str, Any]:
    """Account-level mechanics snapshot for all owned champions."""
    entries, coverage = collect_owned_champion_entries(
        payload,
        formation=formation,
        force_refresh_roster=force_refresh_roster,
        goal=goal,
        context=context,
    )
    projected: list[dict[str, Any]] = []
    for entry in entries:
        row = _project_champion_for_advice(entry, include_bench_notes=True)
        if row is None:
            coverage["incomplete_count"] = int(coverage.get("incomplete_count") or 0) + 1
            incomplete = list(coverage.get("incomplete") or [])
            incomplete.append(
                {
                    "champion_id": entry.get("champion_id"),
                    "name": entry.get("name"),
                    "reason": "Projectie leverde geen bruikbare rij.",
                }
            )
            coverage["incomplete"] = incomplete
            coverage["included_count"] = max(
                0, int(coverage.get("included_count") or 0) - 1
            )
            continue
        projected.append(_strip_transient_for_snapshot(row))

    shared, champions = _catalog_shared_mechanics(projected)
    index = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "seat": c.get("seat"),
        }
        for c in champions
        if isinstance(c.get("id"), int)
    ]
    mechanics_material = {
        "shared": shared,
        "champions": champions,
    }
    account_material = {
        "owned_ids": sorted(i["id"] for i in index if isinstance(i.get("id"), int)),
        "loadouts": [
            {
                "id": c.get("id"),
                "selected": [
                    (g.get("selected") or {}).get("id")
                    for g in (c.get("specializations") or [])
                    if isinstance(g, dict) and (g.get("selected") or {}).get("id") is not None
                ],
                "feat_refs": [
                    f.get("ref") if isinstance(f, dict) else None
                    for f in (c.get("active_feats") or [])
                ],
                "equipment": c.get("equipment"),
                "item_levels": c.get("item_levels"),
                "feats_status": c.get("feats_status"),
                "specialization_status": c.get("specialization_status"),
            }
            for c in champions
        ],
    }
    mechanics_hash = _stable_content_hash(mechanics_material)[:24]
    account_state_hash = _stable_content_hash(account_material)[:24]
    snapshot_id = f"snap_{_stable_content_hash({'m': mechanics_hash, 'a': account_state_hash})[:20]}"
    data_version = _data_version(payload)

    # Static reply/geometry/goal prose — ADVICE_REQUEST only keeps refs + live.
    geometry_block = None
    if formation:
        try:
            export = build_export_payload(
                payload,
                formation,
                goal=goal,
                context=context,
            )
            formation_block = (
                export.get("formation")
                if isinstance(export.get("formation"), dict)
                else {}
            )
            geometry_block = _geometry_from_formation_block(
                formation_block,
                include_occupancy=False,
            )
        except Exception:
            geometry_block = None

    # Provisional snapshot for coverage assessment (same serialized catalogs).
    provisional = {
        "shared": shared,
        "champions": champions,
    }
    mechanics_export_coverage = assess_snapshot_mechanics_export_coverage(
        provisional
    )

    return {
        "meta": {
            "export_kind": "base_snapshot",
            "export_schema_version": SNAPSHOT_EXPORT_SCHEMA,
            "advice_schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "created_at": _utc_now_iso(),
            "request_id": request_id or str(uuid.uuid4()),
            "mechanics_hash": mechanics_hash,
            "mechanics_hash_covers": (
                "shared ability/feat/option catalogs + per-champion projected "
                "mechanics (not adventure eligibility or live stacks). "
                "Hash ≠ proof that effect prose is present — see "
                "mechanics_export_coverage."
            ),
            "account_state_hash": account_state_hash,
            "account_state_hash_covers": (
                "owned champion ids + snapshot loadout selections/feats/"
                "equipment status fields + item_levels (avg/by_slot)"
            ),
            "mechanics_export_coverage": mechanics_export_coverage,
            "data_version": data_version,
            "research_mode": "provided_data_only",
        },
        "bronregels": _BRONREGELS,
        "answer_contract": build_static_answer_contract(),
        "goal_catalog": _goal_catalog_for_snapshot(),
        "geometry": geometry_block,
        "shared": shared,
        "roster": {
            "owned": index,
            "coverage": coverage,
        },
        "champions": champions,
        "onzekerheden": _prune_empty(
            {
                "equipment_effects": "unknown"
                if any(c.get("equipment") == "unknown" for c in champions)
                else None,
                "mechanics_export_incomplete": (
                    True
                    if not mechanics_export_coverage.get("export_complete")
                    else None
                ),
                "mechanics_export_reason": mechanics_export_coverage.get("reason"),
                "note": (
                    "Adventure-eligibility, live bezetting en slot_states/"
                    "plaatsbaarheid horen in ADVICE_REQUEST. Geometry-layout "
                    "hier is de standaard-formatievorm bij snapshot-export. "
                    "Wijkt de actuele layout af, dan exporteert ADVICE_REQUEST "
                    "een volledige actuele geometry die de snapshot-layout als "
                    "geheel overschrijft; actuele occupied en slot_states "
                    "blijven de bron voor bezetting/plaatsbaarheid (ook bij "
                    "geometry.ref). Een geometry.ref is alleen geldig bij "
                    "aantoonbaar gelijke layout (layout_matches_base). "
                    + (
                        "Mechanics-export is incompleet — exporteer opnieuw "
                        "met geladen definitions of gebruik ADVICE_REQUEST "
                        "mechanics_delta; claim geen advice_ready op basis "
                        "van snapshot-ID alleen."
                        if not mechanics_export_coverage.get("export_complete")
                        else ""
                    )
                ),
            }
        ),
    }


def _group_ids_by_reason(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse identical reasons into {reason, ids} groups (sorted ids)."""
    buckets: dict[str, list[int]] = {}
    order: list[str] = []
    for row in rows:
        hid = row.get("id")
        if not isinstance(hid, int):
            continue
        reason = str(row.get("reason") or "unspecified")
        if reason not in buckets:
            buckets[reason] = []
            order.append(reason)
        buckets[reason].append(hid)
    return [
        {"reason": reason, "ids": sorted(buckets[reason])}
        for reason in order
    ]


def _compact_eligibility_table(
    hero_ids: Iterable[int],
    payload: dict[str, Any],
    *,
    adventure_id: int | None,
    campaign_id: int | None,
    campaign_name: str | None,
    entries_by_id: dict[int, dict[str, Any]] | None = None,
    focus_ids: Iterable[int] | None = None,
    include_external_availability: bool = True,
    formation_hero_ids: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Build eligibility summary.

    When ``focus_ids`` is set (selected-only / no-swap scope), only those
    champions are listed in detail. Full owned evaluation still runs so party
    vs roster conflicts stay visible via counts, but bulky per-id denied lists
    and other_party notes for the rest of the roster are omitted.

    ``formation_hero_ids`` is accepted for call-site compatibility only.
    Live presence is **not** treated as eligibility proof; evaluate against
    the roster filter and known explicit overrides instead.
    """
    from ic_gamedata.adventure_restrictions import (
        build_adventure_roster_filter,
        evaluate_heroes_against_filter,
    )
    from ic_gamedata.formation_ai_advice.swap_export import (
        _effective_eligibility_record,
        _other_party_instance,
    )

    del formation_hero_ids  # presence ≠ permission; see presence_conflicts
    ids = sorted({int(h) for h in hero_ids})
    focus: set[int] | None = None
    if focus_ids is not None:
        focus = {int(h) for h in focus_ids if isinstance(h, int) or str(h).isdigit()}
    try:
        filt = build_adventure_roster_filter(payload, adventure_id)
    except Exception:
        filt = None
    base_rows = evaluate_heroes_against_filter(ids, filt)
    allowed: list[int] = []
    denied_rows: list[dict[str, Any]] = []
    unknown_rows: list[dict[str, Any]] = []
    overrides_applied: list[dict[str, Any]] = []
    availability: list[dict[str, Any]] = []
    try:
        from ic_gamedata.advice_fingerprint import party_id_from_payload
        from ic_gamedata.formation_ai_advice.eligibility_corrections import (
            find_correction,
            load_corrections,
        )

        scope_party_id = party_id_from_payload(payload)
        scope_patron_id = None
        try:
            from ic_gamedata.party_advisor_formation import _active_game_instance

            inst = _active_game_instance(payload) or {}
            if isinstance(inst, dict):
                scope_patron_id = _parse_int(inst.get("current_patron_id"))
        except Exception:
            scope_patron_id = None
        user_corrections = load_corrections()
    except Exception:
        scope_party_id = None
        scope_patron_id = None
        user_corrections = []
        find_correction = None  # type: ignore[assignment]

    for row in base_rows:
        hid = row.get("champion_id")
        if not isinstance(hid, int):
            continue
        entry = (entries_by_id or {}).get(hid)
        if entry is not None:
            eff = _effective_eligibility_record(
                entry,
                base_status=str(row.get("status") or "unknown"),
                base_reason=row.get("reason"),
                campaign_id=campaign_id,
                campaign_name=campaign_name,
            )
            status = str(eff.get("effective_eligibility") or "unknown")
            reason = eff.get("effective_reason") or row.get("reason")
            if eff.get("override_source") or (
                eff.get("base_eligibility") == "denied"
                and status == "allowed"
            ):
                if focus is None or hid in focus:
                    overrides_applied.append(
                        _prune_empty(
                            {
                                "champion_id": hid,
                                "base": eff.get("base_eligibility"),
                                "effective": status,
                                "reason": reason,
                                "overrides": eff.get("overrides_considered"),
                            }
                        )
                    )
        else:
            status = str(row.get("status") or "unknown")
            reason = row.get("reason")

        # Scoped user confirmation (never bare presence).
        if status == "denied" and find_correction is not None:
            hit = find_correction(
                user_corrections,
                champion_id=hid,
                party_id=scope_party_id,
                adventure_id=adventure_id,
                patron_id=scope_patron_id,
            )
            if hit is not None:
                if focus is None or hid in focus:
                    overrides_applied.append(
                        {
                            "champion_id": hid,
                            "base": "denied",
                            "effective": "allowed",
                            "reason": hit.base_reason or reason,
                            "source": "user_confirmation",
                            "confirmed_at": hit.confirmed_at,
                            "note": hit.note,
                        }
                    )
                status = "allowed"
                reason = (
                    f"user_confirmation: {hit.base_reason or reason or 'denied'}"
                )

        in_focus = focus is None or hid in focus
        if status == "allowed":
            if in_focus:
                allowed.append(hid)
            elif focus is not None:
                # Still count for totals below via separate tallies.
                pass
        elif status == "denied":
            if in_focus:
                denied_rows.append({"id": hid, "reason": reason})
        else:
            if in_focus:
                unknown_rows.append({"id": hid, "reason": reason})

        if include_external_availability and in_focus:
            avail = _other_party_instance(payload, hid)
            if isinstance(avail, dict) and avail.get("status") not in (
                None,
                "active_party_or_bench_slot",
                "bench_or_unassigned",
            ):
                availability.append(
                    _prune_empty(
                        {
                            "id": hid,
                            "status": avail.get("status"),
                            "game_instance_id": avail.get("game_instance_id"),
                            # Shared note omitted per row; see availability_note.
                        }
                    )
                )

    # Accurate counts over the full evaluated set.
    all_allowed = 0
    all_denied = 0
    all_unknown = 0
    for row in base_rows:
        hid = row.get("champion_id")
        if not isinstance(hid, int):
            continue
        entry = (entries_by_id or {}).get(hid)
        if entry is not None:
            eff = _effective_eligibility_record(
                entry,
                base_status=str(row.get("status") or "unknown"),
                base_reason=row.get("reason"),
                campaign_id=campaign_id,
                campaign_name=campaign_name,
            )
            status = str(eff.get("effective_eligibility") or "unknown")
        else:
            status = str(row.get("status") or "unknown")
        if status == "allowed":
            all_allowed += 1
        elif status == "denied":
            all_denied += 1
        else:
            all_unknown += 1

    if focus is not None:
        # In focus mode, allowed_ids is the focused subset that is allowed.
        out = _prune_empty(
            {
                "scope": "selected_party_only",
                "scope_note": (
                    "Geen championwissels gevraagd: eligibility/details beperkt tot "
                    "de huidige party. Volledige owned-tellingen staan in counts; "
                    "externe kandidaten zijn bewust weggelaten."
                ),
                "allowed_ids": allowed or None,
                "denied_groups": _group_ids_by_reason(denied_rows) or None,
                "unknown_groups": _group_ids_by_reason(unknown_rows) or None,
                "overrides_applied": overrides_applied or None,
                "practical_availability": availability or None,
                "availability_note": (
                    "other_party: staat in een andere party-instance; owned ≠ "
                    "automatisch plaatsbaar."
                    if availability
                    else None
                ),
                "counts": {
                    "focus_allowed": len(allowed),
                    "focus_denied": len(denied_rows),
                    "focus_unknown": len(unknown_rows),
                    "owned_allowed": all_allowed,
                    "owned_denied": all_denied,
                    "owned_unknown": all_unknown,
                },
            }
        )
        return out

    return _prune_empty(
        {
            "scope": "full_owned_roster",
            "allowed_ids": allowed or None,
            "denied_groups": _group_ids_by_reason(denied_rows) or None,
            "unknown_groups": _group_ids_by_reason(unknown_rows) or None,
            # Keep legacy flat lists empty/omitted — groups are canonical.
            "overrides_applied": overrides_applied or None,
            "practical_availability": availability or None,
            "availability_note": (
                "other_party: staat in een andere party-instance; owned ≠ "
                "automatisch plaatsbaar."
                if availability
                else None
            ),
            "counts": {
                "allowed": all_allowed,
                "denied": all_denied,
                "unknown": all_unknown,
            },
        }
    )


def _current_spec_choices(entry: dict[str, Any]) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    for group in entry.get("specialization_groups") or []:
        if not isinstance(group, dict):
            continue
        sid = group.get("selected_option_id")
        if sid is None:
            for opt in group.get("options") or []:
                if isinstance(opt, dict) and opt.get("selected"):
                    sid = opt.get("option_id")
                    break
        choices.append(
            _prune_empty(
                {
                    "group_id": group.get("group_id"),
                    "selected_option_id": sid,
                    "selection_status": group.get("selection_status"),
                }
            )
        )
    return choices


def _current_active_feats(entry: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Active feat loadout for ADVICE_REQUEST: id, name, and mechanic ``effect``.

    Includes ``mechanical_text`` as ``effect`` (typically short). No flavor,
    quality blobs, or effect_facts — those stay in BASE_SNAPSHOT. Under the
    15k clipboard budget, ``effect`` may later be omitted as a whole (never
    mid-cut). ``None`` means unknown (do not read as empty).
    """
    feats_block = entry.get("feats") if isinstance(entry.get("feats"), dict) else {}
    note = str(feats_block.get("note") or "")
    rows = feats_block.get("active_feats")
    if rows is None and isinstance(entry.get("active_feats"), list):
        rows = entry.get("active_feats")
    if note == "unknown" or (rows is None and not feats_block):
        return None
    if not isinstance(rows, list):
        return None
    out: list[dict[str, Any]] = []
    for feat in rows:
        if not isinstance(feat, dict):
            continue
        fid = feat.get("feat_id")
        if fid is None:
            fid = feat.get("id")
        if not isinstance(fid, int):
            parsed = _parse_int(fid)
            fid = parsed if parsed is not None else None
        name = feat.get("name")
        if isinstance(name, str):
            name = name.strip() or None
        if fid is None and not name:
            continue
        effect = feat.get("mechanical_text") or feat.get("effect") or feat.get("text")
        if isinstance(effect, str):
            effect = effect.strip() or None
        else:
            effect = None
        # Skip flavor-only noise that is not usable as a mechanic.
        if effect and effect.casefold().startswith("sets attack id to"):
            effect = None
        out.append(_prune_empty({"id": fid, "name": name, "effect": effect}))
    return out


def _spec_groups_from_snapshot_champ(
    champ: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Map group_id → {selected_option_id, selection_status, option_ids}."""
    out: dict[str, dict[str, Any]] = {}
    for group in champ.get("specializations") or []:
        if not isinstance(group, dict):
            continue
        gid = group.get("group_id")
        if not isinstance(gid, str) or not gid:
            continue
        selected = group.get("selected")
        sid = None
        if isinstance(selected, dict):
            sid = selected.get("id")
        if sid is None:
            sid = group.get("selected_option_id")
        option_ids: list[int] = []
        for opt in group.get("options") or []:
            if not isinstance(opt, dict):
                continue
            oid = opt.get("id") if opt.get("id") is not None else opt.get("ref")
            if isinstance(oid, int):
                option_ids.append(oid)
            elif isinstance(oid, str) and oid.isdigit():
                option_ids.append(int(oid))
        out[gid] = {
            "selected_option_id": sid if isinstance(sid, int) else None,
            "selection_status": group.get("status") or group.get("selection_status"),
            "option_ids": option_ids,
        }
    return out


def _option_ids_for_group_from_entry(entry: dict[str, Any], group_id: str) -> list[int]:
    for group in entry.get("specialization_groups") or []:
        if not isinstance(group, dict) or group.get("group_id") != group_id:
            continue
        ids: list[int] = []
        for opt in group.get("options") or []:
            if not isinstance(opt, dict):
                continue
            oid = opt.get("option_id")
            if isinstance(oid, int):
                ids.append(oid)
        return ids
    return []


def _gender_tag_needs_from_facts(facts: dict[str, Any] | None) -> list[str]:
    if not isinstance(facts, dict):
        return []
    needed: list[str] = []
    for tag in facts.get("target_tags") or []:
        if str(tag).casefold() in _GENDER_COMPARE_TAGS:
            needed.append(str(tag))
    sem = facts.get("semantics") if isinstance(facts.get("semantics"), dict) else {}
    recipients = sem.get("recipients") if isinstance(sem.get("recipients"), dict) else {}
    for tag in recipients.get("tags") or []:
        if str(tag).casefold() in _GENDER_COMPARE_TAGS:
            needed.append(str(tag))
    scaling = (
        sem.get("scaling_population")
        if isinstance(sem.get("scaling_population"), dict)
        else {}
    )
    for tag in scaling.get("tags") or []:
        if str(tag).casefold() in _GENDER_COMPARE_TAGS:
            needed.append(str(tag))
    unique: list[str] = []
    seen: set[str] = set()
    for tag in needed:
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(tag)
    return unique


def _resolve_option_body(
    option_id: int,
    *,
    entry: dict[str, Any] | None,
    shared_options: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(shared_options, dict):
        body = shared_options.get(str(option_id))
        if isinstance(body, dict):
            return body
    if not isinstance(entry, dict):
        return None
    for group in entry.get("specialization_groups") or []:
        if not isinstance(group, dict):
            continue
        for opt in group.get("options") or []:
            if isinstance(opt, dict) and opt.get("option_id") == option_id:
                return opt
    return None


def _party_gender_lookup(
    party_ids: list[int],
    *,
    entries_by_id: dict[int, dict[str, Any]],
    snapshot_by_id: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for hid in party_ids:
        gender = None
        snap = snapshot_by_id.get(hid)
        if isinstance(snap, dict) and isinstance(snap.get("gender"), dict):
            gender = snap["gender"]
        entry = entries_by_id.get(hid)
        if gender is None and isinstance(entry, dict) and isinstance(entry.get("gender"), dict):
            gender = entry["gender"]
        if gender is None:
            from ic_gamedata.formation_ai_advice.export import gender_from_raw_tags

            gender = gender_from_raw_tags(None)
        out[hid] = gender
    return out


def _count_gender_tag_in_party(
    party_ids: list[int],
    gender_by_id: dict[int, dict[str, Any]],
    required_tag: str,
) -> tuple[int | None, list[int]]:
    """Return (count or None if incomplete, ids with unknown/conflict gender)."""
    want = required_tag.casefold()
    if want == "nonbinary":
        want = "non-binary"
    unknown: list[int] = []
    count = 0
    for hid in party_ids:
        gender = gender_by_id.get(hid) or {}
        status = gender.get("status")
        tag = str(gender.get("tag") or gender.get("value") or "").casefold()
        if tag == "nonbinary":
            tag = "non-binary"
        if status != "known" or not tag:
            unknown.append(hid)
            continue
        if tag == want:
            count += 1
    if unknown:
        return None, unknown
    return count, []


def reconcile_snapshot_vs_request(
    *,
    party_state: list[dict[str, Any]],
    entries_by_id: dict[int, dict[str, Any]],
    base_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify expected overrides, material conflicts, and missing comparison data.

    Expected overrides are provenance/debug only — not advice warnings.
    """
    expected: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    snap_champs = (
        {
            int(c["id"]): c
            for c in (base_snapshot.get("champions") or [])
            if isinstance(c, dict) and isinstance(c.get("id"), int)
        }
        if isinstance(base_snapshot, dict)
        else {}
    )
    shared = (
        base_snapshot.get("shared")
        if isinstance(base_snapshot, dict) and isinstance(base_snapshot.get("shared"), dict)
        else {}
    )
    shared_options = (
        shared.get("specialization_options")
        if isinstance(shared.get("specialization_options"), dict)
        else {}
    )

    party_ids = [
        int(row["id"])
        for row in party_state
        if isinstance(row, dict) and isinstance(row.get("id"), int)
    ]
    gender_by_id = _party_gender_lookup(
        party_ids,
        entries_by_id=entries_by_id,
        snapshot_by_id=snap_champs,
    )

    for row in party_state:
        if not isinstance(row, dict):
            continue
        hid = row.get("id")
        if not isinstance(hid, int):
            continue
        name = row.get("name")
        entry = entries_by_id.get(hid)
        snap_groups = _spec_groups_from_snapshot_champ(snap_champs.get(hid) or {})

        for choice in row.get("specialization_choices") or []:
            if not isinstance(choice, dict):
                continue
            gid = choice.get("group_id")
            if not isinstance(gid, str):
                continue
            curr_sid = choice.get("selected_option_id")
            curr_status = choice.get("selection_status")
            snap = snap_groups.get(gid) or {}
            snap_sid = snap.get("selected_option_id")
            snap_status = snap.get("selection_status")
            option_ids = list(snap.get("option_ids") or [])
            if not option_ids and isinstance(entry, dict):
                option_ids = _option_ids_for_group_from_entry(entry, gid)

            # Unknown/missing current state must not be filled from snapshot.
            # Only record when the snapshot has a concrete value that could tempt a fill.
            curr_unknown = curr_status == "unknown" or (
                curr_sid is None
                and curr_status
                not in (None, "unselected", "not_unlocked", "selected")
            )
            snap_has_concrete = isinstance(snap_sid, int) or snap_status == "selected"
            if curr_unknown and snap_has_concrete:
                expected.append(
                    {
                        "kind": "expected_state_override",
                        "code": "unknown_current_not_filled_from_snapshot",
                        "champion_id": hid,
                        "champion_name": name,
                        "group_id": gid,
                        "request": {
                            "selected_option_id": curr_sid,
                            "selection_status": curr_status,
                        },
                        "snapshot": {
                            "selected_option_id": snap_sid,
                            "selection_status": snap_status,
                        },
                        "note": (
                            "Actuele toestand is unknown/ontbrekend — snapshot-"
                            "selectie niet stilzwijgend overnemen."
                        ),
                    }
                )

            if isinstance(curr_sid, int) and option_ids and curr_sid not in option_ids:
                conflicts.append(
                    {
                        "kind": "material_source_conflict",
                        "code": "option_not_in_champion_group",
                        "champion_id": hid,
                        "champion_name": name,
                        "group_id": gid,
                        "selected_option_id": curr_sid,
                        "valid_option_ids": option_ids,
                        "note": (
                            "Geselecteerde optie hoort niet bij deze champion/"
                            "groep volgens de mechanicsbron."
                        ),
                    }
                )

            if not snap_groups:
                continue

            if (
                isinstance(curr_sid, int)
                and isinstance(snap_sid, int)
                and curr_sid != snap_sid
            ):
                expected.append(
                    {
                        "kind": "expected_state_override",
                        "code": "selection_changed",
                        "champion_id": hid,
                        "champion_name": name,
                        "group_id": gid,
                        "snapshot_selected_option_id": snap_sid,
                        "request_selected_option_id": curr_sid,
                        "note": (
                            "Actuele specialisatiekeuze wijkt af van de "
                            "basissnapshot — aanvraag is leidend."
                        ),
                    }
                )
            elif (
                isinstance(curr_sid, int)
                and snap_status == "not_unlocked"
                and curr_status == "selected"
            ):
                expected.append(
                    {
                        "kind": "expected_state_override",
                        "code": "unlocked_since_snapshot",
                        "champion_id": hid,
                        "champion_name": name,
                        "group_id": gid,
                        "snapshot_selection_status": snap_status,
                        "request_selected_option_id": curr_sid,
                        "note": (
                            "Snapshot had not_unlocked; actuele aanvraag heeft "
                            "een selectie — behandel de groep als ontgrendeld "
                            "voor deze aanvraag."
                        ),
                    }
                )
            elif (
                curr_sid is None
                and curr_status == "not_unlocked"
                and isinstance(snap_sid, int)
            ):
                # Current explicitly locked; do not revive snapshot selection.
                expected.append(
                    {
                        "kind": "expected_state_override",
                        "code": "current_not_unlocked_keeps_authority",
                        "champion_id": hid,
                        "champion_name": name,
                        "group_id": gid,
                        "snapshot_selected_option_id": snap_sid,
                        "request_selection_status": curr_status,
                        "note": (
                            "Actuele status not_unlocked blijft leidend; "
                            "oudere snapshotselectie niet terugzetten."
                        ),
                    }
                )

        # Gender-gated specialization comparisons (e.g. Soprano / female count).
        if not isinstance(entry, dict):
            continue
        for group in entry.get("specialization_groups") or []:
            if not isinstance(group, dict):
                continue
            for opt in group.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                oid = opt.get("option_id")
                # Prefer live entry (keeps effect_facts); shared catalog may be tip-only.
                body = opt
                if isinstance(oid, int) and not isinstance(opt.get("effect_facts"), dict):
                    resolved = _resolve_option_body(
                        oid, entry=entry, shared_options=shared_options
                    )
                    if isinstance(resolved, dict):
                        body = resolved
                facts = body.get("effect_facts") if isinstance(body, dict) else None
                needed_tags = _gender_tag_needs_from_facts(
                    facts if isinstance(facts, dict) else None
                )
                if not needed_tags:
                    continue
                opt_name = body.get("name") or opt.get("name") or oid
                for tag in needed_tags:
                    count, unknown_ids = _count_gender_tag_in_party(
                        party_ids, gender_by_id, tag
                    )
                    if unknown_ids:
                        missing.append(
                            {
                                "kind": "missing_comparison_data",
                                "code": "gender_tag_incomplete",
                                "champion_id": hid,
                                "champion_name": name,
                                "option_id": oid,
                                "option_name": opt_name,
                                "required_tag": tag,
                                "property": "gender",
                                "unknown_champion_ids": unknown_ids,
                                "current_selection_known": any(
                                    isinstance(c, dict)
                                    and c.get("selected_option_id") == oid
                                    for c in (row.get("specialization_choices") or [])
                                ),
                                "blocks_proven_ranking": True,
                                "blocks_other_formation_advice": False,
                                "note": (
                                    f"Betrouwbare vergelijking met {opt_name} is "
                                    f"niet mogelijk: gendergegevens ontbreken voor "
                                    f"champion(s) {unknown_ids} (tag `{tag}`). "
                                    "Leid gender niet af uit namen. Overig "
                                    "formatieadvies blijft mogelijk; claim geen "
                                    "bewezen optimale ranking voor deze keuze."
                                ),
                            }
                        )
                    else:
                        # Provenance: count is evaluable from structured gender.
                        expected.append(
                            {
                                "kind": "comparison_data_available",
                                "code": "gender_tag_count",
                                "champion_id": hid,
                                "champion_name": name,
                                "option_id": oid,
                                "option_name": opt_name,
                                "required_tag": tag,
                                "party_matching_count": count,
                                "source": "champions[].gender.tag ← hero_defines.tags",
                                "note": (
                                    f"Telling voor {opt_name}: {count} party-"
                                    f"champion(s) met gender.tag={tag}."
                                ),
                            }
                        )

    return _prune_empty(
        {
            "source_priority": _SOURCE_PRIORITY,
            "expected_state_overrides": expected
            and [
                row
                for row in expected
                if row.get("kind") == "expected_state_override"
            ]
            or None,
            "comparison_data_available": expected
            and [
                row
                for row in expected
                if row.get("kind") == "comparison_data_available"
            ]
            or None,
            "material_source_conflicts": conflicts or None,
            "missing_comparison_data": missing or None,
            "advice_note": (
                "expected_state_overrides zijn informatieve provenance, geen "
                "advieswaarschuwingen. Alleen material_source_conflicts en "
                "missing_comparison_data beperken het advies (het laatste "
                "alleen voor de genoemde vergelijking)."
            ),
        }
    )


def _load_matching_base_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    """Load the exported BASE_SNAPSHOT when it matches ``snapshot_id``."""
    try:
        from ic_gamedata.formation_ai_advice.snapshot_store import (
            load_snapshot_from_registry_path,
        )

        loaded = load_snapshot_from_registry_path()
    except Exception:
        return None
    if not isinstance(loaded, dict):
        return None
    meta = loaded.get("meta") if isinstance(loaded.get("meta"), dict) else {}
    if str(meta.get("snapshot_id") or "") != str(snapshot_id):
        return None
    return loaded


_LIVE_STATE_UNKNOWN_NOTE = (
    "Actuele stacks/fase niet betrouwbaar bekend in deze export."
)

_TRAIT_PLACEMENT_NOTE = (
    "effective_*=huidige specs/feats op de huidige opstelling; "
    "plaatsingsafhankelijke buffs/targets opnieuw berekenen bij een "
    "voorgestelde formatie. traits_already_in_effective niet dubbel toepassen."
)


def _live_state_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Compact live observation for one champion.

    Distinguishes known values (incl. known zero) from unknown and N/A.
    Does not invent stacks from names or mechanics prose.
    """
    known_fields: dict[str, Any] = {}
    for key in (
        "phase",
        "current_phase",
        "toughness_stacks",
        "brutality_stacks",
        "stacks",
    ):
        if entry.get(key) is None:
            continue
        val = entry.get(key)
        # Collapse phase aliases.
        out_key = "phase" if key in ("phase", "current_phase") else key
        if out_key in known_fields:
            continue
        if val == 0 or val == "0":
            known_fields[out_key] = {"value": 0, "value_kind": "known_zero"}
        else:
            known_fields[out_key] = {"value": val, "value_kind": "known"}

    if known_fields:
        return _prune_empty(
            {
                "status": "known",
                "observation": "current_only",
                "fields": known_fields,
                "note": (
                    "Actuele waarneming; geen garantie na verplaatsing of "
                    "gebiedswissel."
                ),
            }
        )
    return {
        "status": "unknown",
        "value_kind": "unknown",
    }


def _hero_levels_by_id(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
) -> dict[int, int]:
    """Current champion levels from payload heroes, with formation fallback."""
    levels: dict[int, int] = {}
    for hero in formation:
        if isinstance(hero.hero_id, int) and isinstance(hero.level, int):
            levels[int(hero.hero_id)] = int(hero.level)
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    for hero in details.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hid = _parse_int(hero.get("hero_id"))
        level = _parse_int(hero.get("level"))
        if hid is None or level is None:
            continue
        levels[hid] = level
    return levels


def _active_feat_ids_from_rows(
    active_feats: list[dict[str, Any]] | None,
    *,
    champ: dict[str, Any] | None = None,
) -> list[int] | None:
    """Compact active feat id list; None = unknown (not empty)."""
    if active_feats is None:
        feats_block = (
            champ.get("feats") if isinstance(champ, dict) and isinstance(champ.get("feats"), dict) else {}
        )
        raw_ids = feats_block.get("active_feat_ids") if isinstance(feats_block, dict) else None
        if isinstance(raw_ids, list):
            out = [
                x
                for x in (_parse_int(v) for v in raw_ids)
                if isinstance(x, int)
            ]
            return out
        return None
    out: list[int] = []
    for feat in active_feats:
        if not isinstance(feat, dict):
            continue
        fid = feat.get("id")
        if fid is None:
            fid = feat.get("feat_id")
        parsed = fid if isinstance(fid, int) else _parse_int(fid)
        if parsed is not None:
            out.append(parsed)
    return out


def _party_lock_fields(
    champion_id: int,
    *,
    fixed_main_dps_id: int | None,
    locked_champion_ids: set[int],
    existing_locked: Any = None,
    existing_reason: Any = None,
) -> tuple[bool | None, str | None]:
    """Stamp locks for REQUEST party rows (same reasons as swap_export).

    Required adventure champions are *not* position-locked here.
    """
    if existing_locked is True and isinstance(existing_reason, str) and existing_reason:
        return True, existing_reason
    if isinstance(fixed_main_dps_id, int) and champion_id == fixed_main_dps_id:
        return True, "fixed_main_dps"
    if champion_id in locked_champion_ids:
        return True, "user_lock"
    return None, None


def _build_bud_observation(
    payload: dict[str, Any],
    *,
    observed_at: str,
) -> dict[str, Any]:
    """Compact BUD-related observation from instance stats only.

    ``this_reset_highest_damage_dealt_hero_id`` is historical reset damage, not
    proof of who currently set the BUD meter. Current BUD / setter / peak stay
    unknown without a live meter or poll loop.
    """
    from ic_gamedata.formation_ai_advice.export import _active_instance

    instance = _active_instance(payload) or {}
    stats = instance.get("stats") if isinstance(instance.get("stats"), dict) else {}
    if not stats:
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        maybe = details.get("stats")
        if isinstance(maybe, dict):
            stats = maybe

    source_key = "this_reset_highest_damage_dealt_hero_id"
    reset_top = _parse_int(stats.get(source_key)) if stats else None
    if reset_top is not None and reset_top <= 0:
        reset_top = None
    reset_status = "known" if reset_top is not None else "unknown"
    return _prune_empty(
        {
            "reset_highest_damage_champion_id": reset_top,
            "reset_highest_damage_status": reset_status,
            "observation_source": f"instance.stats.{source_key}",
            "observed_at": observed_at,
            "current_bud": {
                "status": "unknown",
                "value_kind": "unknown",
                "reason_code": "no_live_bud_meter",
            },
            "current_bud_setter_id": None,
            "current_bud_setter_status": "unknown",
            "current_bud_setter_reason_code": "no_live_bud_meter",
            "peak": {
                "status": "unknown",
                "value_kind": "unknown",
                "reason_code": "no_bud_poll_loop",
            },
            "note": (
                "reset_highest_damage_champion_id is this_reset highest damage; "
                "not current BUD setter without a live meter."
            ),
        }
    )


def _snapshot_catalog_keys(
    base_snapshot: dict[str, Any] | None,
) -> dict[str, set[int]]:
    """Upgrade/feat/option ids present in BASE_SNAPSHOT shared catalogs."""
    out: dict[str, set[int]] = {
        "ability": set(),
        "feat": set(),
        "spec": set(),
    }
    if not isinstance(base_snapshot, dict):
        return out
    shared = base_snapshot.get("shared")
    if not isinstance(shared, dict):
        return out
    for key, cat in (
        ("abilities", "ability"),
        ("feats", "feat"),
        ("specialization_options", "spec"),
    ):
        block = shared.get(key)
        if not isinstance(block, dict):
            continue
        for raw in block:
            parsed = _parse_int(raw)
            if parsed is not None:
                out[cat].add(parsed)
    return out


def _effect_unique_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Canonical unique effect key: src + catalog + canonical ref."""
    cat = row.get("cat") or row.get("effect_catalog") or "ability"
    ref = row.get("ref")
    if ref is None:
        ref = row.get("unresolved_ref")
    if ref is None:
        ref = row.get("catalog_ref")
    return (row.get("src") or row.get("owner_id"), cat, ref)


def _thin_buff_row(
    row: dict[str, Any],
    *,
    reach: str,
    catalog_keys: dict[str, set[int]],
    main_dps_id: int,
    bucket: str,
) -> dict[str, Any]:
    """REQUEST buff row: catalog ref ≠ effect_defines id; reach ≠ activation.

    ``bucket`` is the collect bucket: incoming | own | uncertain.
    Relevance (pri):
    - A head: other-champion buff that may hit main DPS (incoming/uncertain)
    - B condition: has unresolved activation deps
    - C own: main-DPS own mechanic in range
    - E support: low-priority uncertain noise
    """
    if reach == "yes":
        reach_status = "in_range"
        reach_reason = "computed_in_range"
    elif reach == "no":
        reach_status = "out_of_range"
        reach_reason = "computed_out_of_range"
    else:
        reach_status = "unknown"
        reach_reason = "targeting_uncertain"

    deps = row.get("dependencies") if isinstance(row.get("dependencies"), list) else None
    if deps:
        reach_reason = str(row.get("reason") or reach_reason)
        if "activatie" in reach_reason.casefold() or "unresolved" in reach_reason.casefold():
            reach_reason = "unresolved_activation_dependency"

    catalog = row.get("effect_catalog") or row.get("kind") or "ability"
    if catalog == "specialization":
        catalog = "spec"
    elif catalog not in ("ability", "feat", "spec"):
        catalog = "ability"

    catalog_ref = row.get("catalog_ref")
    if catalog_ref is not None and not isinstance(catalog_ref, int):
        catalog_ref = _parse_int(catalog_ref)

    effect_def_id = row.get("effect_def_id")
    if effect_def_id is not None and not isinstance(effect_def_id, int):
        effect_def_id = _parse_int(effect_def_id)

    ref_ok = (
        isinstance(catalog_ref, int)
        and catalog_ref in catalog_keys.get(catalog, set())
    )
    catalog_empty = not any(catalog_keys.values())
    unresolved_ref = None
    unresolved_reason = None
    if catalog_ref is None:
        reason_code = "unresolved_catalog_reference"
        unresolved_reason = "runtime_to_catalog_mapping_unresolved"
        export_ref = None
    elif catalog_empty:
        reason_code = reach_reason
        export_ref = catalog_ref
    elif not ref_ok:
        reason_code = "unresolved_catalog_reference"
        unresolved_reason = "catalog_entry_missing"
        export_ref = None
        unresolved_ref = catalog_ref
    else:
        # Entry exists — check mechanic body if snapshot shared body available.
        reason_code = reach_reason
        export_ref = catalog_ref
        shared = None  # filled by caller via catalog_keys only; body check below

    owner_id = row.get("owner_id")
    kind = str(row.get("kind") or catalog)
    # Relevance priority for budget protection (A before D/E under pressure).
    # Feats are modifiers (D) even when owned by supports — never outrank heads.
    # Confirmed incoming = hard A (in_range). Uncertain ability/spec = soft A
    # (may affect DPS; clipboard drops soft before hard under budget pressure).
    if deps:
        pri = "B"
        relevance = "condition"
    elif kind == "feat":
        pri = "D"
        relevance = "modifier"
    elif bucket == "incoming":
        pri = "A"
        relevance = "head"
    elif bucket == "uncertain" and kind in (
        "ability",
        "specialization",
        "spec",
    ):
        pri = "A"
        relevance = "head"
    elif bucket == "own" and reach_status == "in_range":
        pri = "C"
        relevance = "own"
    else:
        pri = "E"
        relevance = "support"

    # Protect head buffs (known OR unknown) and their conditions — not random
    # support uncertainty alone.
    protected = pri in ("A", "B") or (pri == "C" and reach_status == "in_range")

    thin_deps = None
    if deps:
        thin_deps = [
            _prune_empty(
                {
                    "kind": d.get("kind"),
                    "key": d.get("key"),
                    "upgrade_id": d.get("upgrade_id"),
                    "status": d.get("status"),
                    "reason_code": d.get("reason_code"),
                }
            )
            for d in deps
            if isinstance(d, dict)
        ] or None

    return _prune_empty(
        {
            "src": owner_id,
            "cat": catalog,
            "ref": export_ref,
            "unresolved_ref": unresolved_ref,
            "unresolved_reason": unresolved_reason,
            "effect_def_id": effect_def_id,
            "effect_def_ns": "effect_defines" if effect_def_id is not None else None,
            "reach": reach_status,
            "activation": "unknown",
            "magnitude_status": "unknown",
            "reason": reason_code,
            "deps": thin_deps,
            "pri": pri,
            "relevance": relevance,
            "protected": True if protected else None,
            "name": row.get("name"),  # dropped in clipboard shrink; useful pre-budget
        }
    )


def _build_main_dps_buffs(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    main_dps_id: int,
    goal: str,
    context: str,
    observed_at: str,
    base_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compact computed incoming-buff diagnostics for fixed main DPS."""
    from ic_gamedata.formation_ai_advice.incoming_buffs import collect_incoming_buffs

    report = collect_incoming_buffs(
        payload,
        formation,
        main_dps_id=main_dps_id,
        goal=goal,
        context=context,
    )
    catalog_keys = _snapshot_catalog_keys(base_snapshot)
    # Mechanic body presence for catalog entries (shared catalog values).
    shared_bodies: dict[str, dict[str, Any]] = {}
    if isinstance(base_snapshot, dict):
        shared = base_snapshot.get("shared")
        if isinstance(shared, dict):
            for key, cat in (
                ("abilities", "ability"),
                ("feats", "feat"),
                ("specialization_options", "spec"),
            ):
                block = shared.get(key)
                if isinstance(block, dict):
                    shared_bodies[cat] = block

    empty_completeness = {
        "counting": (
            "unique_key=src+cat+ref; examined=before_budget; "
            "exported/omitted=after_budget"
        ),
        "raw_rows_examined": 0,
        "unique_effects_examined": 0,
        "records_exported": 0,
        "effect_refs_exported": 0,
        "unique_effects_omitted": 0,
        "unresolved_catalog_refs": 0,
        "unknown_reach_count": 0,
        "unknown_activation_count": 0,
        "unknown_magnitude_count": 0,
        "omit_reason": "main_dps_not_in_formation",
    }
    if not report.get("ok"):
        return _prune_empty(
            {
                "fixed_main_dps_id": main_dps_id,
                "observed_at": observed_at,
                "reach_basis_default": "computed",
                "activation_basis_default": "unknown",
                "magnitude_status_default": "unknown",
                "defaults_mean": (
                    "Missing per-row reach_basis/activation_basis/magnitude "
                    "inherits these defaults; never read missing as runtime "
                    "active or numeric 0."
                ),
                "observation_source": "formation_reach_compute",
                "effects": None,
                "completeness": empty_completeness,
            }
        )

    raw_rows: list[dict[str, Any]] = []
    for row in report.get("incoming") or []:
        if isinstance(row, dict):
            raw_rows.append(
                _thin_buff_row(
                    row,
                    reach="yes",
                    catalog_keys=catalog_keys,
                    main_dps_id=main_dps_id,
                    bucket="incoming",
                )
            )
    for row in report.get("own") or []:
        if isinstance(row, dict):
            raw_rows.append(
                _thin_buff_row(
                    row,
                    reach="yes",
                    catalog_keys=catalog_keys,
                    main_dps_id=main_dps_id,
                    bucket="own",
                )
            )
    for row in report.get("uncertain") or []:
        if isinstance(row, dict):
            raw_rows.append(
                _thin_buff_row(
                    row,
                    reach="unknown",
                    catalog_keys=catalog_keys,
                    main_dps_id=main_dps_id,
                    bucket="uncertain",
                )
            )

    # Deduplicate by unique key (keep highest priority / richest row).
    pri_rank = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in raw_rows:
        key = _effect_unique_key(row)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = row
            continue
        if pri_rank.get(str(row.get("pri")), 9) < pri_rank.get(
            str(existing.get("pri")), 9
        ):
            by_key[key] = row
    effects = list(by_key.values())
    # Stable order: priority then src then ref.
    effects.sort(
        key=lambda r: (
            pri_rank.get(str(r.get("pri")), 9),
            int(r.get("src") or 0),
            int(r.get("ref") or r.get("unresolved_ref") or 0),
        )
    )

    # Enrich unresolved reasons when catalog entry exists but body lacks effect.
    unresolved_list: list[dict[str, Any]] = []
    for row in effects:
        uref = row.get("unresolved_ref")
        cat = row.get("cat")
        if row.get("unresolved_reason") == "catalog_entry_missing" and isinstance(
            uref, int
        ):
            unresolved_list.append(
                _prune_empty(
                    {
                        "src": row.get("src"),
                        "cat": cat,
                        "ref": uref,
                        "reason": "catalog_entry_missing",
                    }
                )
            )
        elif row.get("ref") is None and row.get("unresolved_reason"):
            unresolved_list.append(
                _prune_empty(
                    {
                        "src": row.get("src"),
                        "cat": cat,
                        "ref": row.get("unresolved_ref"),
                        "effect_def_id": row.get("effect_def_id"),
                        "reason": row.get("unresolved_reason"),
                    }
                )
            )
        elif isinstance(row.get("ref"), int) and isinstance(cat, str):
            body = (shared_bodies.get(cat) or {}).get(str(row["ref"]))
            if isinstance(body, dict):
                has_effect = bool(
                    body.get("effect")
                    or body.get("mechanical_text")
                    or body.get("text")
                )
                if not has_effect:
                    # Distinct from missing entry.
                    unresolved_list.append(
                        {
                            "src": row.get("src"),
                            "cat": cat,
                            "ref": row["ref"],
                            "reason": "mechanic_body_missing",
                        }
                    )

    unique_n = len(effects)
    unknown_reach = sum(1 for e in effects if e.get("reach") == "unknown")
    return _prune_empty(
        {
            "fixed_main_dps_id": main_dps_id,
            "observed_at": observed_at,
            "reach_basis_default": "computed",
            "activation_basis_default": "unknown",
            "magnitude_status_default": "unknown",
            "defaults_mean": (
                "Missing per-row reach_basis/activation_basis/magnitude "
                "inherits these defaults; never read missing as runtime "
                "active or numeric 0."
            ),
            "observation_source": "formation_reach_compute",
            "priority_order": ["A_head", "B_condition", "C_own", "D_modifier", "E_support"],
            "effects": effects or None,
            "unresolved_catalog": unresolved_list or None,
            "completeness": {
                "counting": (
                    "unique_key=src+cat+ref; examined=before_budget; "
                    "exported/omitted=after_budget; "
                    "unknown_* over unique examined"
                ),
                "raw_rows_examined": len(raw_rows),
                "unique_effects_examined": unique_n,
                "records_exported": unique_n,
                "effect_refs_exported": unique_n,
                "unique_effects_omitted": 0,
                "unresolved_catalog_refs": len(unresolved_list),
                "unknown_reach_count": unknown_reach,
                "unknown_activation_count": unique_n,
                "unknown_magnitude_count": unique_n,
                "omit_reason": None,
            },
        }
    )


def _build_live_diagnostics(
    *,
    party_ids: list[int],
    entries_by_id: dict[int, dict[str, Any]],
    main_dps_id: int | None,
    observed_at: str,
) -> dict[str, Any]:
    """Compact live-state questions; unknown when runtime source is absent.

    Does not invent stacks/values from mechanic prose. Selected specialization
    ids are loadout facts (already on party), not measured buff magnitudes.
    """
    # Champions that commonly need live stacks for DPS diagnosis. Generic
    # scaffolding — values stay unknown unless a future runtime source exists.
    focus_ids = {
        104: "Voronika",
        127: "Vin Ursa",
        153: "Kas",
        154: "Minthara",
        180: "Kitiara",
        106: "Blooshi",
        121: "Miria",
    }
    fields_by_champ: dict[int, list[str]] = {
        104: [
            "puppet_champion_id",
            "crown_completed",
            "crown_remaining_goals",
            "ultimate_power_stacks",
            "calculating_guidance_value",
        ],
        153: [
            "mortal_pawns_stacks",
            "born_into_evil_value",
            "vampire_spawn_ids",
            "undead_ids",
        ],
        180: [
            "merciless_resolve_runtime_target_ids",
            "merciless_resolve_computed_target_ids",
            "power_stacks",
            "merciless_resolve_value",
            "farthest_distance_rule",
        ],
        127: [
            "selected_deck_specialization_id",
            "deck_buff_reaches_main_dps",
        ],
        154: ["strife_stacks", "soul_branding_max_stacks"],
        106: ["soul_stacks", "spirit_status"],
        121: ["soul_cage_stacks", "clone_buildup"],
    }
    champs_out: list[dict[str, Any]] = []
    for hid in party_ids:
        if hid not in focus_ids:
            continue
        entry = entries_by_id.get(hid) or {}
        field_rows: list[dict[str, Any]] = []
        for key in fields_by_champ.get(hid, ()):
            # Special-case: selected deck spec is loadout, not a live stack.
            if key == "selected_deck_specialization_id":
                selected = None
                for group in entry.get("specialization_groups") or []:
                    if not isinstance(group, dict):
                        continue
                    for opt in group.get("options") or []:
                        if (
                            isinstance(opt, dict)
                            and opt.get("selected")
                            and isinstance(opt.get("option_id"), int)
                        ):
                            # Only deck-tier names if present; else first selected.
                            name = str(opt.get("name") or "").casefold()
                            if "deck" in name or "friends in" in name or selected is None:
                                selected = opt.get("option_id")
                if isinstance(selected, int):
                    field_rows.append(
                        {
                            "key": key,
                            "status": "known",
                            "value": selected,
                            "value_kind": "specialization_option_id",
                            "source": "party_specialization_choices",
                        }
                    )
                else:
                    field_rows.append(
                        {
                            "key": key,
                            "status": "unknown",
                            "reason_code": "not_observed",
                        }
                    )
                continue
            if key == "deck_buff_reaches_main_dps":
                field_rows.append(
                    {
                        "key": key,
                        "status": "unknown",
                        "reason_code": "unsupported_semantics",
                        "note": "blocked_column_semantics_unverified",
                    }
                )
                continue
            if key == "farthest_distance_rule":
                field_rows.append(
                    {
                        "key": key,
                        "status": "unknown",
                        "reason_code": "unsupported_semantics",
                        "note": "farthest≠proven_adjacency_hops",
                    }
                )
                continue
            if key == "merciless_resolve_computed_target_ids":
                field_rows.append(
                    {
                        "key": key,
                        "status": "unknown",
                        "reason_code": "unsupported_semantics",
                        "note": "distance_rule_unverified",
                    }
                )
                continue
            field_rows.append(
                {
                    "key": key,
                    "status": "unknown",
                    "reason_code": "source_not_exposed",
                }
            )
        champs_out.append(
            _prune_empty(
                {
                    "id": hid,
                    "name": focus_ids.get(hid),
                    "fields": field_rows,
                }
            )
        )
    return _prune_empty(
        {
            "observed_at": observed_at,
            "fixed_main_dps_id": main_dps_id,
            "note": (
                "Live values require runtime sources; mechanic refs ≠ measured "
                "stacks. unknown reason_codes are factual."
            ),
            "champions": champs_out or None,
        }
    )


def _proven_eligibility_override_resolution(
    override_row: dict[str, Any],
) -> str | None:
    """Return a resolution code when effective allow has a proven exception source.

    Recognizes kit overrides already evaluated into ``overrides_applied``
    (campaign scope match, unconditional ability, force_allow-by-tag). Does not
    invent new exceptions — only classifies documented outcomes.
    """
    reason = str(override_row.get("reason") or "").casefold()
    kinds: list[str] = []
    for item in override_row.get("overrides") or []:
        if isinstance(item, dict) and item.get("kind"):
            kinds.append(str(item.get("kind")))
    if (
        "campaign_scoped_eligibility" in kinds
        or reason.startswith("campaign scope matched")
    ):
        return "campaign_scoped_eligibility"
    if (
        "unconditional_adventure_eligibility" in kinds
        or reason.startswith("unconditional eligibility")
    ):
        return "unconditional_adventure_eligibility"
    if (
        "force_allow_hero_by_tag" in kinds
        or reason.startswith("force_allow via tag")
    ):
        return "force_allow_hero_by_tag"
    return None


def _eligibility_presence_conflicts(
    eligibility: dict[str, Any] | None,
    *,
    exempt_hero_ids: set[int] | None = None,
    payload: dict[str, Any] | None = None,
    adventure_id: int | None = None,
    party_ids: Iterable[int] | None = None,
    position_by_hero: Mapping[int, int] | None = None,
    party_id: int | None = None,
    patron_id: int | None = None,
    user_corrections: Iterable[Any] | None = None,
) -> list[dict[str, Any]] | None:
    """Surface seated presence vs static/effective eligibility.

    Presence in the current party is observation only. A seated champion who
    is statically denied yields an unresolved conflict unless a proven
    exemption applies: ``key_champion``, ``force_allow_hero`` /
    ``force_allow_hero_by_tag``, ``campaign_scoped_eligibility``,
    ``unconditional_adventure_eligibility``, or an explicit scoped
    ``user_confirmation``. Bare presence is never enough.
    """
    exempt = set(exempt_hero_ids or ())
    by_id: dict[int, dict[str, Any]] = {}
    corrections_list: list[Any]
    if user_corrections is None:
        try:
            from ic_gamedata.formation_ai_advice.eligibility_corrections import (
                load_corrections,
            )

            corrections_list = list(load_corrections())
        except Exception:
            corrections_list = []
    else:
        corrections_list = list(user_corrections)

    def _put(row: dict[str, Any]) -> None:
        hid = row.get("champion_id")
        if isinstance(hid, int) and hid not in by_id:
            by_id[hid] = row

    party = [
        int(h)
        for h in (party_ids or ())
        if isinstance(h, int) or (isinstance(h, str) and str(h).isdigit())
    ]
    key_bindings: dict[int, Any] = {}
    if payload is not None and party:
        try:
            from ic_gamedata.formation_ai_advice.key_champion import (
                load_key_champion_bindings_for_party,
            )

            key_bindings = load_key_champion_bindings_for_party(
                payload,
                adventure_id if isinstance(adventure_id, int) else None,
                party_ids=party,
                position_by_hero=position_by_hero
                if isinstance(position_by_hero, Mapping)
                else None,
            )
        except Exception:
            key_bindings = {}

    if isinstance(eligibility, dict):
        for ov in eligibility.get("overrides_applied") or []:
            if not isinstance(ov, dict):
                continue
            if ov.get("base") != "denied" or ov.get("effective") != "allowed":
                continue
            hid = ov.get("champion_id")
            if not isinstance(hid, int):
                continue
            binding = key_bindings.get(hid)
            proven = _proven_eligibility_override_resolution(ov)
            if binding is not None:
                _put(
                    {
                        "champion_id": hid,
                        "conflict": "base_denied_effective_allowed",
                        "status": "resolved",
                        "resolution": "adventure_key_champion",
                        "effective_reason": ov.get("reason"),
                        "replacement_locked": True,
                        "must_remain_in_party": True,
                        "position_locked": bool(binding.position_locked),
                        "locked_position_id": binding.locked_position_id,
                    }
                )
            elif hid in exempt:
                _put(
                    {
                        "champion_id": hid,
                        "conflict": "base_denied_effective_allowed",
                        "status": "resolved",
                        "resolution": "force_allow_hero",
                        "effective_reason": ov.get("reason"),
                        "position_locked": False,
                        "replacement_locked": False,
                    }
                )
            elif proven is not None:
                # Documented kit/campaign exception already evaluated to allow.
                # Raw patron/static block remains in structured_restrictions.
                _put(
                    {
                        "champion_id": hid,
                        "conflict": "base_denied_effective_allowed",
                        "status": "resolved",
                        "resolution": proven,
                        "effective_reason": ov.get("reason"),
                        "position_locked": False,
                        "replacement_locked": False,
                    }
                )
            else:
                _put(
                    {
                        "champion_id": hid,
                        "conflict": "base_denied_effective_allowed",
                        "status": "unresolved",
                        "base_reason": ov.get("reason"),
                        "note": (
                            "override_without_proven_required_or_force_allow"
                        ),
                        "position_locked": False,
                        "replacement_locked": False,
                    }
                )

    # Static filter vs seated party presence (presence ≠ permission).
    if payload is not None and party:
        try:
            from ic_gamedata.adventure_restrictions import (
                build_adventure_roster_filter,
                evaluate_heroes_against_filter,
            )

            filt = build_adventure_roster_filter(payload, adventure_id)
            static_rows = evaluate_heroes_against_filter(
                party, filt, formation_hero_ids=None
            )
            for row in static_rows:
                if not isinstance(row, dict):
                    continue
                hid = row.get("champion_id")
                if not isinstance(hid, int):
                    continue
                if row.get("status") != "denied":
                    continue
                binding = key_bindings.get(hid)
                if binding is not None:
                    # No prose note — resolution + lock flags are enough for
                    # consumers and keep the clipboard under budget.
                    _put(
                        {
                            "champion_id": hid,
                            "conflict": "static_denied_formation_present",
                            "status": "resolved",
                            "resolution": "adventure_key_champion",
                            "base_reason": row.get("reason"),
                            "replacement_locked": True,
                            "must_remain_in_party": True,
                            "position_locked": bool(binding.position_locked),
                            "locked_position_id": binding.locked_position_id,
                        }
                    )
                elif hid in exempt:
                    _put(
                        {
                            "champion_id": hid,
                            "conflict": "static_denied_formation_present",
                            "status": "resolved",
                            "resolution": "force_allow_hero",
                            "base_reason": row.get("reason"),
                            "position_locked": False,
                            "replacement_locked": False,
                        }
                    )
                else:
                    user_hit = None
                    try:
                        from ic_gamedata.formation_ai_advice.eligibility_corrections import (
                            find_correction,
                        )

                        user_hit = find_correction(
                            corrections_list,
                            champion_id=hid,
                            party_id=party_id,
                            adventure_id=adventure_id,
                            patron_id=patron_id,
                        )
                    except Exception:
                        user_hit = None
                    if user_hit is not None:
                        _put(
                            {
                                "champion_id": hid,
                                "conflict": "static_denied_formation_present",
                                "status": "resolved",
                                "resolution": "user_confirmation",
                                "base_status": user_hit.base_status,
                                "base_reason": user_hit.base_reason
                                or row.get("reason"),
                                "effective_status": "allowed",
                                "source": "user_confirmation",
                                "confirmed_at": user_hit.confirmed_at,
                                "note": user_hit.note
                                or (
                                    "user_confirmed_usable_in_this_scope;"
                                    "not_api_verification"
                                ),
                                "position_locked": False,
                                "replacement_locked": False,
                            }
                        )
                    else:
                        _put(
                            {
                                "champion_id": hid,
                                "conflict": "static_denied_formation_present",
                                "status": "unresolved",
                                "base_reason": row.get("reason"),
                                "note": (
                                    "seated_but_not_eligible_without_proven_"
                                    "required_or_force_allow; presence_is_"
                                    "observation_only; not_position_locked"
                                ),
                                "position_locked": False,
                                "replacement_locked": False,
                            }
                        )
        except Exception:
            pass

    return list(by_id.values()) or None


def _compact_gender_row(gender: dict[str, Any] | None, *, champion_id: int) -> dict[str, Any]:
    g = gender if isinstance(gender, dict) else {}
    status = str(g.get("status") or "unknown")
    tag = g.get("tag") if status == "known" else None
    if status == "known" and tag is None:
        tag = g.get("value")
    return _prune_empty(
        {
            "id": champion_id,
            "status": status,
            "tag": tag,
            "layer": "base",
            "source": g.get("source") or None,
            # Explicit: unknown must not be read as false.
            "false_means": None,
            "note": (
                "unknown≠false; niet afleiden uit naam"
                if status != "known"
                else None
            ),
        }
    )


def _build_comparison_traits(
    *,
    party_ids: list[int],
    gender_by_id: dict[int, dict[str, Any]],
    reconciliation: dict[str, Any],
) -> dict[str, Any] | None:
    """Export only gender rows needed for gated comparisons (e.g. Soprano)."""
    needed_ids: set[int] = set()
    needed_tags: set[str] = set()
    for row in reconciliation.get("missing_comparison_data") or []:
        if not isinstance(row, dict):
            continue
        if row.get("property") != "gender" and row.get("code") != "gender_tag_incomplete":
            continue
        for hid in row.get("unknown_champion_ids") or []:
            if isinstance(hid, int):
                needed_ids.add(hid)
        tag = row.get("required_tag")
        if isinstance(tag, str) and tag:
            needed_tags.add(tag)
        # Also include all party members for that comparison so counts work.
        needed_ids.update(party_ids)
    for row in reconciliation.get("comparison_data_available") or []:
        if not isinstance(row, dict):
            continue
        if row.get("code") != "gender_tag_count":
            continue
        needed_ids.update(party_ids)
        tag = row.get("required_tag")
        if isinstance(tag, str) and tag:
            needed_tags.add(tag)
    if not needed_ids:
        return None
    genders = [
        _compact_gender_row(gender_by_id.get(hid), champion_id=hid)
        for hid in sorted(needed_ids)
    ]
    return _prune_empty(
        {
            "gender": genders or None,
            "required_tags": sorted(needed_tags) or None,
            "layer_note": (
                "layer=base ← hero_defines.tags; geen effectieve "
                "plaatsingsafhankelijke genderwijziging in deze export."
            ),
        }
    )


def _uggie_host_champion_ids() -> set[int]:
    try:
        from ic_gamedata.ability_cooldowns import _call_uggie_name_by_hero

        return set(_call_uggie_name_by_hero().keys())
    except Exception:
        return set()


def _party_has_uggie_mechanics(
    party_ids: list[int],
    entries_by_id: dict[int, dict[str, Any]],
) -> bool:
    """True when a seated champion is an Uggie host or Fallbacks affiliate."""
    hosts = _uggie_host_champion_ids()
    for hid in party_ids:
        if hid in hosts:
            return True
        entry = entries_by_id.get(hid)
        if not isinstance(entry, dict):
            continue
        affiliations = entry.get("affiliations") or []
        if any(str(a).casefold() == "fallbacks" for a in affiliations):
            return True
        # Projected mechanics may already mark Uggie companion geometry.
        blob = json.dumps(entry, ensure_ascii=False).casefold()
        if "uggie" in blob:
            return True
    return False


def _build_uggie_companion_state(
    *,
    party_ids: list[int],
    entries_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    """Live Uggie host/position/targets — unknown when not reliably readable."""
    if not _party_has_uggie_mechanics(party_ids, entries_by_id):
        return None
    # Application cannot currently observe companion tile / buff targets from
    # the webRequest payload; do not invent a position_id or host.
    return {
        "observability": "unknown",
        "host_champion_id": None,
        "companion_position_id": None,
        "buff_targets": None,
        "host_pos_is_not_uggie_pos": True,
        "no_invented_position_id": True,
        "blocks_only": "uggie_buff_coverage",
    }


def _compact_uncertainty_summary(
    *,
    reconciliation: dict[str, Any],
    readiness: dict[str, Any],
    uggie: dict[str, Any] | None,
    mechanic_gaps: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Deduped uncertainty classes — avoids repeating the same warning thrice."""
    rows: list[dict[str, Any]] = []
    if reconciliation.get("material_source_conflicts"):
        rows.append(
            {
                "class": "material_source_conflict",
                "blocks_advice": True,
                "count": len(reconciliation["material_source_conflicts"]),
            }
        )
    if reconciliation.get("expected_state_overrides"):
        rows.append(
            {
                "class": "expected_state_override",
                "blocks_advice": False,
                "count": len(reconciliation["expected_state_overrides"]),
                "note": "normaal; geen conflict",
            }
        )
    if reconciliation.get("missing_comparison_data"):
        rows.append(
            {
                "class": "missing_comparison_data",
                "blocks_advice": False,
                "blocks_only": "genoemde_vergelijking",
                "count": len(reconciliation["missing_comparison_data"]),
            }
        )
    if mechanic_gaps:
        trunc_gaps = [
            g
            for g in mechanic_gaps
            if isinstance(g, dict) and g.get("completeness") == "description_truncated"
        ]
        other_gaps = [
            g
            for g in mechanic_gaps
            if isinstance(g, dict) and g.get("completeness") != "description_truncated"
        ]
        if trunc_gaps:
            rows.append(
                {
                    "class": "description_truncated",
                    "blocks_advice": False,
                    "blocks_only": "afhankelijke_specialisatievergelijking",
                    "count": len(trunc_gaps),
                    "note": (
                        "afgekapte/onvolledige effecttekst ≠ bruikbare volledige "
                        "mechanic; geen volledige spec-ranking claimen"
                    ),
                }
            )
        if other_gaps:
            rows.append(
                {
                    "class": "missing_mechanic",
                    "blocks_advice": False,
                    "blocks_only": "afhankelijke_specialisatievergelijking",
                    "count": len(other_gaps),
                    "note": (
                        "ontbrekende dependency of onopgeloste parameters ≠ "
                        "beste beschreven optie; geen volledige spec-ranking claimen"
                    ),
                }
            )
    live_unknown = True  # default export posture unless proven otherwise
    rows.append(
        {
            "class": "live_state_unknown",
            "blocks_advice": False,
            "note": (
                "geen bewezen numerieke ranking op stacks/fase; "
                "kwalitatief advies ok"
            ),
        }
    )
    rows.append(
        {
            "class": "magnitude_not_computed",
            "blocks_advice": False,
            "note": (
                "basis_of_actueel_niet_berekend ≠ mechanic ontbreekt; "
                "geen bewezen optimale ranking zonder totalen"
            ),
        }
    )
    if isinstance(uggie, dict) and uggie.get("observability") == "unknown":
        rows.append(
            {
                "class": "uggie_state_unknown",
                "blocks_advice": False,
                "blocks_only": "uggie_afhankelijke_buffdekking",
            }
        )
    ready_issues = readiness.get("issues") if isinstance(readiness, dict) else None
    if ready_issues:
        rows.append(
            {
                "class": "readiness_issues",
                "blocks_advice": readiness.get("status") == "blocked",
                "count": len(ready_issues),
            }
        )
    _ = live_unknown  # posture documented above
    return {"items": rows} if rows else None


def build_advice_request(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    snapshot_id: str,
    snapshot_meta: dict[str, Any] | None = None,
    base_snapshot: dict[str, Any] | None = None,
    goal: str = "push",
    context: str = "campaign",
    objective: str | None = None,
    fixed_main_dps_id: int | None = None,
    locked_champion_ids: list[int] | tuple[int, ...] | None = None,
    goal_parameters: dict[str, Any] | None = None,
    manual_restriction_text: str | None = None,
    request_id: str | None = None,
    research_mode: str = "provided_data_only",
    include_swap_scope: bool = False,
    force_refresh_roster: bool = False,
) -> dict[str, Any]:
    """Compact current advice request referencing a BASE_SNAPSHOT."""
    from ic_gamedata.formation_ai_advice.research_mode import normalize_research_mode

    research_mode = normalize_research_mode(research_mode)
    resolved_snapshot = base_snapshot
    if resolved_snapshot is None:
        resolved_snapshot = _load_matching_base_snapshot(snapshot_id)

    # Pre-resolve adventure key_champion locks so swap generation and explicit
    # locks treat required champions as fixed before the legacy export builds.
    from ic_gamedata.formation_ai_advice.key_champion import (
        load_key_champion_bindings_for_party,
    )

    early_adventure_id = None
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    active_id = _parse_int(details.get("active_game_instance_id"))
    for inst in details.get("game_instances") or []:
        if not isinstance(inst, dict):
            continue
        if active_id is None or _parse_int(inst.get("game_instance_id")) == active_id:
            early_adventure_id = _parse_int(inst.get("current_adventure_id"))
            break
    early_party_ids = [
        int(h.hero_id)
        for h in formation
        if getattr(h, "hero_id", None) is not None
    ]
    # FormationHero.seat is the technical formation position in this codebase.
    early_pos = {
        int(h.hero_id): int(h.seat)
        for h in formation
        if getattr(h, "hero_id", None) is not None
        and isinstance(getattr(h, "seat", None), int)
    }
    early_key_bindings = load_key_champion_bindings_for_party(
        payload,
        early_adventure_id,
        party_ids=early_party_ids,
        position_by_hero=early_pos,
    )
    merged_locked: list[int] = []
    seen_locked: set[int] = set()
    for raw in list(locked_champion_ids or ()) + list(early_key_bindings):
        hid = _parse_int(raw)
        if hid is None or hid in seen_locked:
            continue
        seen_locked.add(hid)
        merged_locked.append(hid)
    locked_champion_ids = merged_locked

    # Reuse legacy export for goal/geometry/party champions (same pipeline).
    if include_swap_scope:
        from ic_gamedata.formation_ai_advice.swap_export import build_swap_export_payload

        export = build_swap_export_payload(
            payload,
            formation,
            locked_champion_ids=locked_champion_ids,
            goal=goal,
            context=context,
            objective=objective,
            fixed_main_dps_id=fixed_main_dps_id,
            goal_parameters=goal_parameters,
            manual_restriction_text=manual_restriction_text,
            request_id=request_id,
            research_mode=research_mode,
            force_refresh_roster=force_refresh_roster,
        )
    else:
        export = build_export_payload(
            payload,
            formation,
            goal=goal,
            context=context,
            objective=objective,
            fixed_main_dps_id=fixed_main_dps_id,
            explicit_locked_champion_ids=locked_champion_ids,
            goal_parameters=goal_parameters,
            manual_restriction_text=manual_restriction_text,
            request_id=request_id,
            research_mode=research_mode,
        )

    goal_block = export.get("goal") if isinstance(export.get("goal"), dict) else {}
    formation_block = (
        export.get("formation") if isinstance(export.get("formation"), dict) else {}
    )
    party_ids = [
        int(c["champion_id"])
        for c in (export.get("champions") or [])
        if isinstance(c, dict) and isinstance(c.get("champion_id"), int)
    ]

    # Build entries for eligibility overrides (party + owned).
    entries, _cov = collect_owned_champion_entries(
        payload,
        formation=formation,
        force_refresh_roster=force_refresh_roster,
        goal=goal,
        context=context,
    )
    entries_by_id = {
        int(e["champion_id"]): e
        for e in entries
        if isinstance(e.get("champion_id"), int)
    }

    adventure_id = goal_block.get("adventure_id")
    if not isinstance(adventure_id, int):
        adventure_id = _parse_int(adventure_id)
    campaign_id = goal_block.get("campaign_id")
    if not isinstance(campaign_id, int):
        campaign_id = _parse_int(campaign_id)
    campaign_name = (
        str(goal_block.get("campaign_name"))
        if goal_block.get("campaign_name")
        else None
    )

    owned_ids = [hid for hid, *_ in _owned_rows(payload)]
    # Selected-only (no swap): detail eligibility for the party; omit bulky
    # external roster denied/availability dumps. Swap scope keeps full owned cover.
    eligibility = _compact_eligibility_table(
        owned_ids,
        payload,
        adventure_id=adventure_id,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        entries_by_id=entries_by_id,
        focus_ids=None if include_swap_scope else party_ids,
        include_external_availability=include_swap_scope,
        formation_hero_ids=party_ids,
    )

    locked_ids: set[int] = set()
    for raw in locked_champion_ids or ():
        hid = _parse_int(raw)
        if hid is not None:
            locked_ids.add(hid)
    levels_by_id = _hero_levels_by_id(payload, formation)

    from ic_gamedata.formation_ai_advice.key_champion import (
        load_key_champion_bindings_for_party,
    )

    position_by_hero = {
        int(c["champion_id"]): int(c["current_position"])
        for c in (export.get("champions") or [])
        if isinstance(c, dict)
        and isinstance(c.get("champion_id"), int)
        and isinstance(c.get("current_position"), int)
    }
    key_bindings = load_key_champion_bindings_for_party(
        payload,
        adventure_id if isinstance(adventure_id, int) else None,
        party_ids=party_ids,
        position_by_hero=position_by_hero,
    )

    party_state: list[dict[str, Any]] = []
    for champ in export.get("champions") or []:
        if not isinstance(champ, dict):
            continue
        cid = champ.get("champion_id")
        if not isinstance(cid, int):
            continue
        raw_entry = entries_by_id.get(cid) or champ
        snap_entry = entries_by_id.get(cid)
        current_choices = _current_spec_choices(raw_entry)
        # Prefer live export champion feats (same pipeline as mechanics).
        active_feats = _current_active_feats(champ)
        if active_feats is None:
            active_feats = _current_active_feats(raw_entry)
        feats_status = None
        if active_feats is None:
            feats_status = "unknown"
        active_feat_ids = _active_feat_ids_from_rows(active_feats, champ=champ)
        if active_feat_ids is None and feats_status != "unknown":
            active_feat_ids = []
        locked, lock_reason = _party_lock_fields(
            cid,
            fixed_main_dps_id=fixed_main_dps_id
            if isinstance(fixed_main_dps_id, int)
            else None,
            locked_champion_ids=locked_ids,
            existing_locked=champ.get("locked"),
            existing_reason=champ.get("lock_reason"),
        )
        key_lock = key_bindings.get(cid)
        key_fields: dict[str, Any] = {}
        if key_lock is not None:
            key_fields = key_lock.as_export_fields()
            # Adventure key_champion outranks user/DPS locks for reason text.
            locked = True
            lock_reason = str(key_fields.get("lock_reason") or "adventure_key_champion")
        trait_delta = None
        if snap_entry is not None:
            # Snapshot effective traits come from the same build; expose base vs
            # effective when they differ (current specialization applied).
            if (
                champ.get("base_roles") != champ.get("effective_roles")
                or champ.get("base_tags") != champ.get("effective_tags")
                or champ.get("base_alignment") != champ.get("effective_alignment")
            ):
                trait_delta = _prune_empty(
                    {
                        "base_alignment": champ.get("base_alignment"),
                        "effective_alignment": champ.get("effective_alignment"),
                        "base_roles": champ.get("base_roles"),
                        "effective_roles": champ.get("effective_roles"),
                        "base_tags": champ.get("base_tags"),
                        "effective_tags": champ.get("effective_tags"),
                        "applies_to": "current_formation",
                        "placement_dependent_buffs": "recompute_on_proposed_formation",
                        "note": _TRAIT_PLACEMENT_NOTE,
                    }
                )
        party_row = {
            "id": cid,
            "name": champ.get("name"),
            # Always permanent F-key from defines — never trust a stale
            # export/cache seat (e.g. poisoned seat=1 for Ravengard).
            "seat": _permanent_seat(cid),
            "position": champ.get("current_position"),
            "level": levels_by_id.get(cid),
            # Level alone does not prove upgrades are purchased.
            "upgrade_status": "unknown",
            "upgrade_status_reason": "upgrade_purchase_state_unavailable",
            "locked": locked,
            "lock_reason": lock_reason,
            "specialization_choices": current_choices or None,
            # Compact ids first; active_feats keeps id+name+effect.
            "active_feat_ids": active_feat_ids,
            "active_feats": active_feats,
            "feats_status": feats_status,
            "live_state": _live_state_from_entry(champ),
            "trait_delta_vs_base": trait_delta,
            "eligibility": (
                (champ.get("eligibility") or {}).get("effective_eligibility")
                if isinstance(champ.get("eligibility"), dict)
                else None
            ),
        }
        if key_fields:
            for key in (
                "replacement_locked",
                "must_remain_in_party",
                "position_locked",
                "locked_position_id",
                "lock_provenance",
            ):
                if key in key_fields:
                    party_row[key] = key_fields[key]
        party_state.append(_prune_empty(party_row))

    # Structured restrictions with explicit comparators.
    structured = goal_block.get("structured_restrictions")
    if not isinstance(structured, dict):
        # Fallback: rebuild restriction block fields.
        restrictions = _restriction_block(
            payload,
            manual_restriction_text=manual_restriction_text,
            adventure_id=adventure_id,
            selected_hero_ids=party_ids,
        )
        structured = restrictions.get("structured_restrictions")

    snap_meta = snapshot_meta if isinstance(snapshot_meta, dict) else {}
    if (
        isinstance(resolved_snapshot, dict)
        and isinstance(resolved_snapshot.get("meta"), dict)
    ):
        # Prefer hashes from the loaded snapshot when present.
        snap_meta = {
            **snap_meta,
            **{
                k: resolved_snapshot["meta"].get(k)
                for k in (
                    "account_state_hash",
                    "mechanics_hash",
                    "account_state_hash_covers",
                    "mechanics_hash_covers",
                    "snapshot_id",
                )
                if resolved_snapshot["meta"].get(k) is not None
            },
        }
    reconciliation = reconcile_snapshot_vs_request(
        party_state=party_state,
        entries_by_id=entries_by_id,
        base_snapshot=resolved_snapshot,
    )
    # Gender lookup for comparison_traits (same sources as reconciliation).
    snap_champs_by_id = (
        {
            int(c["id"]): c
            for c in (resolved_snapshot.get("champions") or [])
            if isinstance(c, dict) and isinstance(c.get("id"), int)
        }
        if isinstance(resolved_snapshot, dict)
        else {}
    )
    gender_by_id = _party_gender_lookup(
        party_ids,
        entries_by_id=entries_by_id,
        snapshot_by_id=snap_champs_by_id,
    )
    comparison_traits = _build_comparison_traits(
        party_ids=party_ids,
        gender_by_id=gender_by_id,
        reconciliation=reconciliation,
    )
    uggie_state = _build_uggie_companion_state(
        party_ids=party_ids,
        entries_by_id=entries_by_id,
    )
    current_owned = sorted(owned_ids)
    snap_covers = snap_meta.get("account_state_hash_covers")
    deviations = _prune_empty(
        {
            "source_priority": _SOURCE_PRIORITY,
            "expected_state_overrides": reconciliation.get(
                "expected_state_overrides"
            ),
            "comparison_data_available": reconciliation.get(
                "comparison_data_available"
            ),
            "material_source_conflicts": reconciliation.get(
                "material_source_conflicts"
            ),
            "missing_comparison_data": reconciliation.get(
                "missing_comparison_data"
            ),
            "advice_note": reconciliation.get("advice_note"),
            "snapshot_account_state_hash": snap_meta.get("account_state_hash"),
            "snapshot_mechanics_hash": snap_meta.get("mechanics_hash"),
            "owned_count_now": len(current_owned),
            "hash_covers_note": snap_covers,
            "hash_note": (
                "account_state_hash / mechanics_hash blijven de "
                "integriteitscontrole; normale expected_state_overrides "
                "maskeren echte bronproblemen niet."
            ),
        }
    )

    full_geometry = _geometry_from_formation_block(
        formation_block,
        include_occupancy=True,
    )
    base_geometry = None
    if isinstance(resolved_snapshot, dict):
        snap_geo = resolved_snapshot.get("geometry")
        if isinstance(snap_geo, dict):
            base_geometry = snap_geo
    geometry, geometry_meta = geometry_for_advice_request(
        full_geometry, base_geometry
    )

    constraints = dict(export.get("constraints") or {}) if isinstance(export.get("constraints"), dict) else {}
    # Adventure key_champion replacement locks join fixed_champion_ids so swap
    # generation and global may_replace cannot treat them as free seats.
    if key_bindings:
        fixed = {
            int(x)
            for x in (constraints.get("fixed_champion_ids") or [])
            if isinstance(x, int) or str(x).isdigit()
        }
        fixed.update(int(hid) for hid in key_bindings)
        constraints["fixed_champion_ids"] = sorted(fixed)
        goal_fixed = {
            int(x)
            for x in (goal_block.get("fixed_champion_ids") or [])
            if isinstance(x, int) or str(x).isdigit()
        }
        goal_fixed.update(int(hid) for hid in key_bindings)
        goal_block = dict(goal_block)
        goal_block["fixed_champion_ids"] = sorted(goal_fixed)
    readiness = export.get("readiness") if isinstance(export.get("readiness"), dict) else {}
    readiness = dict(readiness) if isinstance(readiness, dict) else {}
    if geometry_meta.get("mode") in ("full", "incomplete"):
        # Layout change vs BASE is expected_state_override — not a conflict.
        geo_override = {
            "kind": "expected_state_override",
            "code": "geometry_layout_changed",
            "note": (
                "Actuele formatielayout wijkt af van BASE_SNAPSHOT.geometry; "
                "ADVICE_REQUEST.geometry overschrijft de snapshot-layout "
                "als geheel. Actuele occupied blijft leidend voor bezetting."
            ),
            "request_valid_position_ids": full_geometry.get(
                "valid_position_ids"
            ),
            "snapshot_valid_position_ids": (
                base_geometry.get("valid_position_ids")
                if isinstance(base_geometry, dict)
                else None
            ),
            "layout_incomplete": geometry_meta.get("mode") == "incomplete",
        }
        expected_overrides = list(
            (deviations.get("expected_state_overrides") or [])
            if isinstance(deviations, dict)
            else []
        )
        expected_overrides.append(geo_override)
        if isinstance(deviations, dict):
            deviations = dict(deviations)
            deviations["expected_state_overrides"] = expected_overrides
        if isinstance(reconciliation, dict):
            reconciliation = dict(reconciliation)
            reconciliation["expected_state_overrides"] = expected_overrides

    if geometry_meta.get("mode") == "incomplete":
        gaps = list(geometry_meta.get("gaps") or [])
        issues = [
            iss
            for iss in (readiness.get("issues") or [])
            if isinstance(iss, dict)
        ]
        issues.append(
            {
                "code": "geometry_layout_incomplete",
                "severity": "error",
                "dimension": "geometry",
                "message": (
                    "Actuele formatielayout wijkt af van de basissnapshot maar "
                    "essentiële geometry ontbreekt "
                    f"({', '.join(gaps[:12])}{'…' if len(gaps) > 12 else ''}). "
                    "Geen verzonnen coördinaten/adjacency; plaatsingsadvies "
                    "is niet gereed. Roster-eligibility kan apart. "
                    "Maak een nieuwe basissnapshot voor dit avontuur of "
                    "ververs de formatiegeometrie."
                ),
                "missing_layout_fields": gaps,
                "fix": (
                    "Formation-tab verversen of nieuwe BASE_SNAPSHOT maken "
                    "voor de actuele adventure/campagne."
                ),
            }
        )
        readiness["issues"] = issues
        readiness["status"] = "blocked"
        readiness["placement_advice"] = "insufficient"
    req_id = (
        (export.get("meta") or {}).get("request_id")
        or request_id
        or str(uuid.uuid4())
    )
    mechanics_block = build_mechanics_completeness(
        party_ids=party_ids,
        entries_by_id=entries_by_id,
        base_snapshot=resolved_snapshot,
        party_names={
            int(p["id"]): str(p.get("name") or p["id"])
            for p in party_state
            if isinstance(p.get("id"), int)
        },
    )
    base_mech_coverage = assess_snapshot_mechanics_export_coverage(
        resolved_snapshot if isinstance(resolved_snapshot, dict) else None
    )
    if isinstance(mechanics_block, dict):
        mechanics_block = dict(mechanics_block)
        mechanics_block["base_mechanics_export_coverage"] = base_mech_coverage

    essential_delta_count = sum(
        1
        for row in (mechanics_block.get("mechanics_delta") or [])
        if isinstance(row, dict)
        and (
            row.get("role") == "supplement"
            or row.get("snapshot_had_effect") is False
        )
    )
    base_unusable = not base_mech_coverage.get("usable_for_qualitative_advice")
    cov_reason = base_mech_coverage.get("reason")
    if base_unusable or (
        not base_mech_coverage.get("export_complete") and essential_delta_count > 0
    ):
        # Snapshot-ID / roster rows ≠ usable mechanics. Eligibility stays separate.
        issues = [
            iss
            for iss in (readiness.get("issues") or [])
            if isinstance(iss, dict)
        ]
        if cov_reason == "no_snapshot":
            # Local body not loaded — AI may still have the file; do not hard-block.
            issues.append(
                {
                    "code": "base_snapshot_body_unavailable_locally",
                    "severity": "warning",
                    "dimension": "mechanics",
                    "message": (
                        "BASE_SNAPSHOT-inhoud is lokaal niet geladen voor "
                        "mechanicdekkingscontrole. Snapshot-ID alleen bewijst "
                        "geen effectproza. Lees het snapshotbestand of "
                        "exporteer opnieuw."
                    ),
                    "fix": "Zorg dat het basisbestand beschikbaar is.",
                }
            )
            if readiness.get("status") not in ("blocked",):
                readiness["status"] = "ready_with_warnings"
        elif base_unusable and essential_delta_count == 0:
            issues.append(
                {
                    "code": "base_mechanics_export_incomplete",
                    "severity": "error",
                    "dimension": "mechanics",
                    "message": (
                        "Gerefereerde BASE_SNAPSHOT mist bruikbare ability/"
                        "specialisatie-effectproza "
                        f"(reason={cov_reason}; "
                        f"ability_with_effect="
                        f"{base_mech_coverage.get('ability_with_effect')}; "
                        f"option_with_effect="
                        f"{base_mech_coverage.get('option_with_effect')}) "
                        "en er is geen mechanics_delta-supplement. "
                        "Plaatsings-/specialisatieadvies is niet gereed. "
                        "Roster-eligibility blijft apart beoordeelbaar. "
                        "Exporteer een nieuwe basissnapshot met geladen "
                        "definitions."
                    ),
                    "fix": "Basis bijwerken (nieuwe snapshot-ID).",
                }
            )
            readiness["placement_advice"] = "insufficient"
            readiness["specialization_advice"] = "insufficient"
            readiness["status"] = "blocked"
        else:
            issues.append(
                {
                    "code": "base_mechanics_require_delta",
                    "severity": "warning",
                    "dimension": "mechanics",
                    "message": (
                        "BASE_SNAPSHOT-mechanics-export is incompleet "
                        f"(reason={cov_reason}); "
                        f"{essential_delta_count} essential mechanics_delta "
                        "row(s) vullen ontbrekende effectproza aan. "
                        "Niet weglaten voor budget "
                        "(delta_omitted_use_BASE_SNAPSHOT is ongeldig hier). "
                        "Bij voorkeur nieuwe basissnapshot exporteren."
                    ),
                    "fix": (
                        "Behoud mechanics_delta of Basis bijwerken."
                    ),
                }
            )
            if readiness.get("status") not in ("blocked",):
                readiness["status"] = "ready_with_warnings"
        readiness["issues"] = issues

    uncertainty = _compact_uncertainty_summary(
        reconciliation=reconciliation,
        readiness=readiness if isinstance(readiness, dict) else {},
        uggie=uggie_state,
        mechanic_gaps=(
            list(mechanics_block.get("mechanic_gaps") or [])
            if isinstance(mechanics_block, dict)
            else None
        ),
    )

    observed_at = _utc_now_iso()
    bud_observation = _build_bud_observation(payload, observed_at=observed_at)
    main_dps_buffs = None
    if isinstance(fixed_main_dps_id, int):
        main_dps_buffs = _build_main_dps_buffs(
            payload,
            formation,
            main_dps_id=fixed_main_dps_id,
            goal=goal,
            context=context,
            observed_at=observed_at,
            base_snapshot=(
                resolved_snapshot if isinstance(resolved_snapshot, dict) else None
            ),
        )
    live_diagnostics = _build_live_diagnostics(
        party_ids=party_ids,
        entries_by_id=entries_by_id,
        main_dps_id=fixed_main_dps_id if isinstance(fixed_main_dps_id, int) else None,
        observed_at=observed_at,
    )
    exempt_ids: set[int] = set()
    try:
        from ic_gamedata.adventure_restrictions import build_adventure_roster_filter

        filt = build_adventure_roster_filter(payload, adventure_id)
        if filt is not None:
            exempt_ids = set(getattr(filt, "exempt_hero_ids", set()) or ())
    except Exception:
        exempt_ids = set()
    scope_party_id = _parse_int(goal_block.get("party_id"))
    if scope_party_id is None:
        try:
            from ic_gamedata.advice_fingerprint import party_id_from_payload

            scope_party_id = party_id_from_payload(payload)
        except Exception:
            scope_party_id = None
    scope_patron_id = _parse_int(goal_block.get("patron_id"))
    eligibility_conflicts = _eligibility_presence_conflicts(
        eligibility if isinstance(eligibility, dict) else None,
        exempt_hero_ids=exempt_ids,
        payload=payload,
        adventure_id=adventure_id if isinstance(adventure_id, int) else None,
        party_ids=party_ids,
        position_by_hero=position_by_hero,
        party_id=scope_party_id,
        patron_id=scope_patron_id,
    )
    if eligibility_conflicts and isinstance(eligibility, dict):
        eligibility = dict(eligibility)
        eligibility["presence_conflicts"] = eligibility_conflicts
        user_confirmed = [
            c
            for c in eligibility_conflicts
            if isinstance(c, dict)
            and c.get("status") == "resolved"
            and c.get("resolution") == "user_confirmation"
        ]
        if user_confirmed:
            eligibility["user_eligibility_corrections"] = [
                {
                    "champion_id": c.get("champion_id"),
                    "base_status": c.get("base_status") or "denied",
                    "base_reason": c.get("base_reason"),
                    "effective_status": "allowed",
                    "source": "user_confirmation",
                    "confirmed_at": c.get("confirmed_at"),
                    "note": c.get("note"),
                }
                for c in user_confirmed
            ]
            # Move confirmed ids out of denied lists so counters stay consistent.
            confirmed_ids = {
                int(c["champion_id"])
                for c in user_confirmed
                if isinstance(c.get("champion_id"), int)
            }
            if confirmed_ids:
                denied_rows = [
                    row
                    for row in (eligibility.get("denied") or [])
                    if not (
                        isinstance(row, dict)
                        and isinstance(row.get("id"), int)
                        and int(row["id"]) in confirmed_ids
                    )
                ]
                eligibility["denied"] = denied_rows or None
                allowed_ids = list(eligibility.get("allowed_ids") or [])
                for hid in sorted(confirmed_ids):
                    if hid not in allowed_ids:
                        allowed_ids.append(hid)
                eligibility["allowed_ids"] = allowed_ids
                # Drop from denied_groups ids lists when present.
                groups = []
                for group in eligibility.get("denied_groups") or []:
                    if not isinstance(group, dict):
                        continue
                    ids = [
                        i
                        for i in (group.get("ids") or [])
                        if isinstance(i, int) and i not in confirmed_ids
                    ]
                    if ids:
                        groups.append({**group, "ids": ids})
                eligibility["denied_groups"] = groups or None
        # Unresolved presence conflicts must not look fully settled.
        unresolved = [
            c
            for c in eligibility_conflicts
            if isinstance(c, dict) and c.get("status") == "unresolved"
        ]
        unresolved_n = len(unresolved)
        locked_unresolved = [
            c for c in unresolved if c.get("replacement_locked")
        ]
        if unresolved_n and readiness.get("status") not in ("blocked",):
            readiness = dict(readiness) if isinstance(readiness, dict) else {}
            dims = dict(readiness.get("dimensions") or {})
            dims["party_legality"] = "conflict"
            dims["restrictions"] = "conflict"
            if locked_unresolved:
                dims["placement_advice"] = "insufficient"
            elif dims.get("placement_advice") not in (
                "insufficient",
                "blocked",
            ):
                # Replaceable contested members: proposals without them remain
                # possible; keeping/moving them still needs proof.
                dims["placement_advice"] = "partial"
            readiness["dimensions"] = dims
            issues = [
                iss
                for iss in (readiness.get("issues") or [])
                if isinstance(iss, dict)
            ]
            affected = [
                int(c["champion_id"])
                for c in unresolved
                if isinstance(c.get("champion_id"), int)
            ]
            issues.append(
                {
                    "code": "eligibility_presence_conflict",
                    "severity": "warning",
                    "dimension": "eligibility",
                    "affected_champion_ids": affected or None,
                    "message": (
                        f"{unresolved_n} seated champion(s) fail static/"
                        "effective eligibility without proven force_allow/"
                        "required rule; presence is observation only; "
                        "not an unconditional allowed status"
                        + (
                            "; replacement_locked blocks keep/move advice"
                            if locked_unresolved
                            else "; replaceable — end-formation without them "
                            "may still be legal"
                        )
                        + "."
                    ),
                }
            )
            readiness["issues"] = issues
            if readiness.get("status") == "ready":
                readiness["status"] = "ready_with_warnings"

    result: dict[str, Any] = {
        "meta": {
            "export_kind": "advice_request",
            "export_schema_version": SNAPSHOT_EXPORT_SCHEMA,
            "advice_schema_version": SCHEMA_VERSION,
            "request_id": req_id,
            "created_at": observed_at,
            "snapshot_ref": {
                "snapshot_id": snapshot_id,
                # Real on-disk basename when known (e.g. basicdata_*.json).
                # ``None`` for legacy refs — never invent ``{snapshot_id}.json``.
                "expected_filename": (
                    str(snap_meta["expected_filename"]).strip()
                    if isinstance(snap_meta.get("expected_filename"), str)
                    and str(snap_meta.get("expected_filename")).strip()
                    else None
                ),
                "mechanics_hash": snap_meta.get("mechanics_hash"),
                "account_state_hash": snap_meta.get("account_state_hash"),
                "contains_snapshot_body": False,
            },
            "research_mode": research_mode,
            "scope": (export.get("meta") or {}).get("scope"),
            "data_version": (export.get("meta") or {}).get("data_version"),
        },
        "answer_contract": build_answer_contract_ref(
            str(req_id),
            snapshot_id=str(snapshot_id),
        ),
        "bronregels": _REQUEST_BRONREGELS,
        "live_state_defaults": {
            "status": "unknown",
            "value_kind": "unknown",
            "known_zero_distinct": True,
            "not_applicable_distinct": True,
            "note": _LIVE_STATE_UNKNOWN_NOTE,
        },
        # Keep adventure/campaign/patron keys even when null so a request never
        # silently omits current-context fields (live state, not snapshot truth).
        # Goal prose (label/description/priorities) lives in BASE_SNAPSHOT.goal_catalog.
        "goal": {
            **(
                _prune_empty(
                    {
                        "id": goal_block.get("id"),
                        "primary_metric": goal_block.get("primary_metric"),
                        "parameters": goal_block.get("parameters"),
                        "fixed_main_dps_id": goal_block.get("fixed_main_dps_id"),
                        "fixed_champion_ids": goal_block.get("fixed_champion_ids"),
                        "adventure_name": goal_block.get("adventure_name"),
                        "campaign_name": goal_block.get("campaign_name"),
                        "patron_name": goal_block.get("patron_name"),
                        "restriction_text": goal_block.get("restriction_text"),
                        "party_restriction_status": goal_block.get(
                            "party_restriction_status"
                        ),
                        "structured_restrictions": structured,
                        "catalog_ref": "BASE_SNAPSHOT.goal_catalog",
                    }
                )
                or {}
            ),
            "adventure_id": goal_block.get("adventure_id"),
            "campaign_id": goal_block.get("campaign_id"),
            "patron_id": goal_block.get("patron_id"),
        },
        "geometry": geometry,
        "party": party_state,
        "bud_observation": bud_observation,
        "main_dps_buffs": main_dps_buffs,
        "live_diagnostics": live_diagnostics,
        "constraints": _prune_empty(
            {
                "may_replace_champions": constraints.get("may_replace_champions"),
                "max_swaps_per_proposal": constraints.get("max_swaps_per_proposal"),
                "fixed_champion_ids": constraints.get("fixed_champion_ids"),
                "fixed_main_dps_id": constraints.get("fixed_main_dps_id"),
                "main_dps_locked": constraints.get("main_dps_locked"),
                "may_change_feats": constraints.get("may_change_feats"),
                "may_change_equipment": constraints.get("may_change_equipment"),
                "no_hidden_tier_list_or_top_n": constraints.get(
                    "no_hidden_tier_list_or_top_n", True
                ),
            }
        ),
        "roster_eligibility": eligibility,
        "snapshot_deviations": deviations,
        "comparison_traits": comparison_traits,
        "companion_state": _prune_empty({"uggie": uggie_state}) if uggie_state else None,
        "mechanics_completeness": mechanics_block,
        "uncertainty": uncertainty,
        "research_gaps": export.get("research_gaps"),
        "readiness": _prune_empty(
            {
                "status": readiness.get("status"),
                "dimensions": readiness.get("dimensions"),
                # Prefer compact codes+ids; drop repeated fill prose (UI/clipboard).
                "issues": [
                    _prune_empty(
                        {
                            "code": iss.get("code"),
                            "severity": iss.get("severity"),
                            "dimension": iss.get("dimension"),
                            "affected_champion_ids": iss.get("affected_champion_ids"),
                            "message": iss.get("message"),
                        }
                    )
                    for iss in (readiness.get("issues") or [])
                    if isinstance(iss, dict)
                ]
                or None,
            }
        ),
    }
    if include_swap_scope and isinstance(export.get("swap"), dict):
        swap = export["swap"]
        result["swap"] = _prune_empty(
            {
                "mode": swap.get("mode"),
                "candidate_selection": swap.get("candidate_selection"),
                "max_swaps_per_proposal": swap.get("max_swaps_per_proposal"),
                "coverage": swap.get("coverage"),
                "excluded": swap.get("excluded"),
                "incomplete": swap.get("incomplete"),
                # classification ids only — mechanics live in BASE_SNAPSHOT
                "classification": [
                    _prune_empty(
                        {
                            "champion_id": row.get("champion_id"),
                            "name": row.get("name"),
                            "seat": row.get("seat"),
                            "classification": row.get("classification"),
                            "reason": row.get("reason"),
                            "eligibility": row.get("eligibility"),
                        }
                    )
                    for row in (swap.get("classification") or [])
                    if isinstance(row, dict)
                ]
                or None,
            }
        )
    # Keep thin answer_contract/geometry refs intact (empty arrays / false matter).
    answer_contract = result.get("answer_contract")
    geometry_out = result.get("geometry")
    snap_ref_out = (
        (result.get("meta") or {}).get("snapshot_ref")
        if isinstance(result.get("meta"), dict)
        else None
    )
    pruned = _prune_empty(result)
    if isinstance(answer_contract, dict):
        pruned["answer_contract"] = answer_contract
    if isinstance(geometry_out, dict):
        pruned["geometry"] = geometry_out
    # Keep expected_filename even when null (legacy unknown — not invented).
    if isinstance(snap_ref_out, dict) and isinstance(pruned.get("meta"), dict):
        pruned["meta"] = dict(pruned["meta"])
        pruned["meta"]["snapshot_ref"] = dict(snap_ref_out)
    # Re-attach live context keys that must remain explicit even when null.
    goal_out = pruned.get("goal") if isinstance(pruned.get("goal"), dict) else {}
    goal_out = dict(goal_out)
    goal_out["adventure_id"] = goal_block.get("adventure_id")
    goal_out["campaign_id"] = goal_block.get("campaign_id")
    goal_out["patron_id"] = goal_block.get("patron_id")
    pruned["goal"] = goal_out
    return pruned


def build_champion_details(
    payload: dict[str, Any],
    champion_ids: Iterable[int],
    *,
    formation: tuple[FormationHero, ...] | None = None,
    snapshot_id: str | None = None,
    force_refresh_roster: bool = False,
    goal: str = "push",
    context: str = "campaign",
) -> dict[str, Any]:
    """Supplemental full projections for explicitly selected champions."""
    wanted = sorted({int(x) for x in champion_ids if isinstance(x, int) or str(x).isdigit()})
    wanted_set = set(wanted)
    entries, coverage = collect_owned_champion_entries(
        payload,
        formation=formation,
        force_refresh_roster=force_refresh_roster,
        goal=goal,
        context=context,
    )
    selected: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    found: set[int] = set()
    for entry in entries:
        cid = entry.get("champion_id")
        if not isinstance(cid, int) or cid not in wanted_set:
            continue
        found.add(cid)
        projected = _project_champion_for_advice(entry, include_bench_notes=True)
        if projected is None:
            missing.append(
                {"champion_id": cid, "reason": "Projectie mislukt."}
            )
            continue
        selected.append(projected)
    for cid in wanted:
        if cid not in found:
            missing.append(
                {
                    "champion_id": cid,
                    "reason": "Niet in owned roster of niet exporteerbaar.",
                }
            )

    return {
        "meta": {
            "export_kind": "champion_details",
            "export_schema_version": SNAPSHOT_EXPORT_SCHEMA,
            "advice_schema_version": SCHEMA_VERSION,
            "created_at": _utc_now_iso(),
            "snapshot_ref": {"snapshot_id": snapshot_id} if snapshot_id else None,
            "requested_champion_ids": wanted,
        },
        "bronregels": _BRONREGELS,
        "champions": selected,
        "coverage": _prune_empty(
            {
                "requested_count": len(wanted),
                "included_count": len(selected),
                "missing": missing or None,
                "owned_roster_coverage": coverage,
            }
        ),
    }


def format_base_snapshot_markdown(snapshot: dict[str, Any]) -> str:
    body = minify_json(snapshot)
    snap_id = (snapshot.get("meta") or {}).get("snapshot_id") or "?"
    return "\n".join(
        [
            "# Idle Champions — BASE_SNAPSHOT",
            "",
            "Deel dit eenmalig met de AI. Vernieuw bij relevante roster-/feat-/spec-/mechanicwijzigingen.",
            f"snapshot_id: `{snap_id}`",
            "",
            "```json",
            body,
            "```",
            "",
        ]
    )


def format_advice_request_markdown(request: dict[str, Any]) -> str:
    body = minify_json(request)
    snap_ref = ((request.get("meta") or {}).get("snapshot_ref") or {})
    ref = snap_ref.get("snapshot_id") if isinstance(snap_ref, dict) else None
    fname = (
        snap_ref.get("expected_filename") if isinstance(snap_ref, dict) else None
    )
    if fname:
        ref_line = f"snapshot_ref: `{ref or '?'}` · bestand `{fname}`"
    else:
        ref_line = (
            f"snapshot_ref: `{ref or '?'}` · bestand onbekend "
            "(zoek via snapshot_id + hashes)"
        )
    return "\n".join(
        [
            "# Idle Champions — ADVICE_REQUEST",
            "",
            "Compacte actuele aanvraag. Mechanics staan in BASE_SNAPSHOT.",
            ref_line,
            "",
            "```json",
            body,
            "```",
            "",
        ]
    )


def format_champion_details_markdown(details: dict[str, Any]) -> str:
    body = minify_json(details)
    return "\n".join(
        [
            "# Idle Champions — CHAMPION_DETAILS",
            "",
            "Aanvullende championgegevens voor expliciet geselecteerde IDs.",
            "",
            "```json",
            body,
            "```",
            "",
        ]
    )


def measure_export_sizes(
    *,
    base_snapshot: dict[str, Any] | None = None,
    advice_request: dict[str, Any] | None = None,
    champion_details: dict[str, Any] | None = None,
    legacy_markdown: str | None = None,
) -> dict[str, int]:
    """Byte/char lengths of minified payloads (for tests/reporting)."""
    out: dict[str, int] = {}
    if base_snapshot is not None:
        out["base_snapshot_json"] = len(minify_json(base_snapshot))
        out["base_snapshot_markdown"] = len(format_base_snapshot_markdown(base_snapshot))
    if advice_request is not None:
        out["advice_request_json"] = len(minify_json(advice_request))
        out["advice_request_markdown"] = len(
            format_advice_request_markdown(advice_request)
        )
    if champion_details is not None:
        out["champion_details_json"] = len(minify_json(champion_details))
        out["champion_details_markdown"] = len(
            format_champion_details_markdown(champion_details)
        )
    if legacy_markdown is not None:
        out["legacy_markdown"] = len(legacy_markdown)
    return out
