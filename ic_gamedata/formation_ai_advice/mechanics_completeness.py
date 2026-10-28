"""Generic mechanic completeness for ADVICE_REQUEST vs BASE_SNAPSHOT.

Walks selected-party abilities, specialization options, feat changes, and
recursive upgrade dependencies. Re-resolves from live definitions when the
snapshot body is missing usable effect prose. Does not invent mechanics.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

from ic_gamedata.formation_ai_advice.clipboard_export import (
    _HINT_ABILITY_MISSING,
    _HINT_SPEC_MISSING,
    _mechanic_entry,
    _prune_empty,
)
from ic_gamedata.formation_ai_advice.export import (
    _mechanic_fields_from_upgrade,
    _upgrade_row_map,
)

CatalogKind = Literal["ability", "specialization_option", "feat"]
Completeness = Literal[
    "known",
    "partial",
    "missing",
    "parameter_missing",
    "description_truncated",
    "magnitude_not_computed",
    "live_state_unknown",
]
DescriptionStatus = Literal["full", "truncated", "source_incomplete", "missing"]
ParameterStatus = Literal["resolved", "unresolved", "n/a"]

_ATTACK_ID_NOISE = ("sets attack id to", "adds monster hit effect")
# Fingerprint of the former clipboard preview cut (effect[:260].rstrip() + "…").
_LEGACY_PREVIEW_CUT = 260


def _has_usable_effect(body: dict[str, Any] | None) -> bool:
    if not isinstance(body, dict):
        return False
    effect = body.get("effect")
    if isinstance(effect, str) and effect.strip():
        low = effect.strip().casefold()
        if any(low.startswith(p) for p in _ATTACK_ID_NOISE):
            return False
        return True
    return False


def delta_row_is_essential_for_request(row: dict[str, Any] | None) -> bool:
    """True when this delta must keep its effect — BASE does not already cover it.

    Budget shrinkage must not strip or drop these rows while claiming
    ``delta_omitted_use_BASE_SNAPSHOT``.
    """
    if not isinstance(row, dict):
        return False
    if row.get("role") == "supplement":
        return True
    if row.get("snapshot_had_effect") is False:
        return True
    return False


def assess_snapshot_mechanics_export_coverage(
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Measure whether a BASE_SNAPSHOT actually exported usable mechanic prose.

    Existence of champion rows / option refs / hashes is not enough — consumers
    need ``shared.abilities`` / ``shared.specialization_options`` bodies with
    ``effect`` text (or resolvable refs to those bodies).
    """
    if not isinstance(snapshot, dict):
        return {
            "export_complete": False,
            "usable_for_qualitative_advice": False,
            "reason": "no_snapshot",
            "ability_bodies": 0,
            "ability_with_effect": 0,
            "option_bodies": 0,
            "option_with_effect": 0,
            "option_missing_effect": 0,
            "champions_with_ability_refs": 0,
            "champion_count": 0,
        }

    shared = snapshot.get("shared") if isinstance(snapshot.get("shared"), dict) else {}
    abilities = (
        shared.get("abilities") if isinstance(shared.get("abilities"), dict) else {}
    )
    options = (
        shared.get("specialization_options")
        if isinstance(shared.get("specialization_options"), dict)
        else {}
    )
    champions = [
        c for c in (snapshot.get("champions") or []) if isinstance(c, dict)
    ]

    ab_with = sum(
        1 for body in abilities.values() if _has_usable_effect(body if isinstance(body, dict) else None)
    )
    opt_with = sum(
        1
        for body in options.values()
        if _has_usable_effect(body if isinstance(body, dict) else None)
    )
    opt_missing = sum(
        1
        for body in options.values()
        if isinstance(body, dict) and not _has_usable_effect(body)
    )
    champs_with_ab = sum(
        1
        for c in champions
        if isinstance(c.get("abilities"), list) and c.get("abilities")
    )

    # Usable when we exported a real ability catalog and most options have prose.
    # Empty ability catalog with many champions = export failure, not "no kit".
    ability_ok = ab_with > 0 and (
        champs_with_ab > 0 or len(champions) == 0
    )
    option_ok = True
    if options:
        # Allow a small fraction of truly missing source effects.
        option_ok = opt_with >= max(1, int(0.5 * len(options)))
    export_complete = bool(ability_ok and option_ok and ab_with > 0)
    # Qualitative party advice needs at least some ability prose in the export.
    usable = bool(ab_with > 0 and (opt_with > 0 or not options))

    reason = None
    if not abilities and champions:
        reason = "shared_abilities_catalog_empty"
    elif ab_with == 0 and champions:
        reason = "no_usable_ability_effects"
    elif options and opt_with == 0:
        reason = "no_usable_specialization_effects"
    elif options and not option_ok:
        reason = "majority_specialization_effects_missing"
    elif champs_with_ab == 0 and champions and abilities:
        reason = "champions_missing_ability_refs"
    elif not export_complete:
        reason = "partial_mechanics_export"

    return {
        "export_complete": export_complete,
        "usable_for_qualitative_advice": usable,
        "reason": reason,
        "ability_bodies": len(abilities),
        "ability_with_effect": ab_with,
        "option_bodies": len(options),
        "option_with_effect": opt_with,
        "option_missing_effect": opt_missing,
        "champions_with_ability_refs": champs_with_ab,
        "champion_count": len(champions),
        "note": (
            "mechanics_hash covers projected shared catalogs as serialized; "
            "it does not prove prior exports had usable effect prose. "
            "Use this coverage block before omitting ADVICE_REQUEST deltas."
            if not export_complete
            else None
        ),
    }


def _looks_like_export_preview_truncation(
    snap_effect: str, live_effect: str
) -> bool:
    """Detect our former compact preview slice — not a lone ellipsis heuristic.

    Requires: snap ends with the export ellipsis we appended, the prefix matches
    the live prose, and live continues materially past that cut. A legitimate
    source ellipsis alone is not enough.
    """
    if not snap_effect or not live_effect:
        return False
    if not snap_effect.endswith("…"):
        return False
    prefix = snap_effect[:-1].rstrip()
    if len(prefix) < 40:
        return False
    # Former helper cut near 260 characters.
    if abs(len(prefix) - _LEGACY_PREVIEW_CUT) > 25 and len(prefix) > _LEGACY_PREVIEW_CUT + 40:
        return False
    if live_effect.startswith(prefix) and len(live_effect) > len(prefix) + 10:
        return True
    return False


def _parameter_status_of_body(body: dict[str, Any] | None) -> ParameterStatus:
    if not isinstance(body, dict) or not _has_usable_effect(body):
        return "n/a"
    explicit = body.get("parameter_status")
    if explicit in ("resolved", "unresolved", "n/a"):
        return explicit  # type: ignore[return-value]
    mag = body.get("magnitude")
    # Computed total unknown ≠ unresolved definition placeholders.
    if mag == "basis_of_actueel_niet_berekend":
        return "resolved"
    if body.get("unresolved_parameters"):
        return "unresolved"
    if mag == "parameter_onbekend":
        return "unresolved"
    if "(onbekend)" in str(body.get("effect") or ""):
        return "unresolved"
    return "resolved"


def _description_status_of_body(body: dict[str, Any] | None) -> DescriptionStatus:
    if not isinstance(body, dict):
        return "missing"
    explicit = body.get("description_status")
    if explicit in ("full", "truncated", "source_incomplete", "missing"):
        return explicit  # type: ignore[return-value]
    if body.get("description_truncated") is True or body.get("export_truncated") is True:
        return "truncated"
    if body.get("source_incomplete") is True:
        return "source_incomplete"
    if not _has_usable_effect(body):
        return "missing"
    return "full"


def _completeness_of_body(body: dict[str, Any] | None) -> Completeness:
    """Primary completeness for comparison — description truncates outrank params."""
    if not isinstance(body, dict):
        return "missing"
    desc = _description_status_of_body(body)
    if desc == "truncated":
        return "description_truncated"
    if desc in ("missing", "source_incomplete"):
        return "missing"
    param = _parameter_status_of_body(body)
    if param == "unresolved":
        return "parameter_missing"
    mag = body.get("magnitude")
    if mag == "basis_of_actueel_niet_berekend":
        return "magnitude_not_computed"
    if "(onbekend)" in str(body.get("effect") or ""):
        return "partial"
    return "known"


def _catalog_body(
    shared: dict[str, Any] | None,
    *,
    kind: CatalogKind,
    item_id: int,
) -> dict[str, Any] | None:
    if not isinstance(shared, dict):
        return None
    key = {
        "ability": "abilities",
        "specialization_option": "specialization_options",
        "feat": "feats",
    }[kind]
    cat = shared.get(key)
    if not isinstance(cat, dict):
        return None
    body = cat.get(str(item_id))
    return body if isinstance(body, dict) else None


def _status_fields_from_upgrade_fields(
    fields: dict[str, Any],
    projected: dict[str, Any],
) -> dict[str, Any]:
    """Separate full prose availability from unresolved parameter tokens.

    ``text_complete`` in the resolver means placeholders resolved — that is
    *not* the same as a truncated description. Export uses full mechanical
    prose whenever present; unresolved params are reported separately.
    """
    unresolved_raw = list(fields.get("unresolved_fields") or [])
    ph_tokens = [
        str(u).split(":", 1)[-1]
        for u in unresolved_raw
        if str(u).startswith("unresolved_placeholder")
    ]
    usability = fields.get("usability")
    if _has_usable_effect(projected):
        description_status: DescriptionStatus = "full"
    elif usability in ("flavor_only",) or any(
        str(u).startswith("effect_keys_only")
        or str(u) in ("effect_def_no_description", "effect_only_no_prose")
        for u in unresolved_raw
    ):
        description_status = "source_incomplete"
    else:
        description_status = "missing"

    if description_status != "full":
        parameter_status: ParameterStatus = "n/a"
    elif (
        ph_tokens
        or projected.get("magnitude") == "parameter_onbekend"
        or "(onbekend)" in str(projected.get("effect") or "")
    ):
        parameter_status = "unresolved"
    else:
        parameter_status = "resolved"

    return _prune_empty(
        {
            "description_status": description_status,
            "parameter_status": parameter_status,
            "unresolved_parameters": ph_tokens[:8] or None,
            # Never mark live re-resolve as export-truncated: we keep full prose.
            "description_truncated": False,
            "export_truncated": False,
        }
    )


def _live_projected(
    upgrade_id: int,
    *,
    kind: CatalogKind,
    owner_name: str | None = None,
) -> dict[str, Any] | None:
    row = _upgrade_row_map().get(int(upgrade_id))
    if not isinstance(row, dict):
        return None
    fields = _mechanic_fields_from_upgrade(row, owner_name=owner_name)
    name = (
        row.get("name")
        or row.get("specialization_name")
        or fields.get("name")
    )
    item = {
        "ability_id": upgrade_id,
        "option_id": upgrade_id,
        "feat_id": upgrade_id,
        "name": name,
        **fields,
    }
    entry_kind = (
        "specialization"
        if kind == "specialization_option"
        else ("feat" if kind == "feat" else "ability")
    )
    projected = _mechanic_entry(item, kind=entry_kind)
    if projected is None and name:
        projected = _prune_empty(
            {
                "id": upgrade_id,
                "name": name,
                "advice_hint": (
                    _HINT_SPEC_MISSING
                    if kind == "specialization_option"
                    else _HINT_ABILITY_MISSING
                ),
                "description_status": "missing",
                "parameter_status": "n/a",
            }
        )
    elif isinstance(projected, dict):
        projected = {**projected, **_status_fields_from_upgrade_fields(fields, projected)}
    return projected


def _deps_from_body(body: dict[str, Any] | None) -> list[int]:
    if not isinstance(body, dict):
        return []
    refs = body.get("depends_on_upgrade_ids") or []
    return [int(x) for x in refs if isinstance(x, int) or str(x).isdigit()]


def _walk_party_mechanic_ids(
    *,
    party_ids: list[int],
    entries_by_id: dict[int, dict[str, Any]],
    base_snapshot: dict[str, Any] | None,
) -> tuple[dict[int, CatalogKind], dict[int, set[int]]]:
    """Return (id→kind, id→champion_ids that need it)."""
    kinds: dict[int, CatalogKind] = {}
    needed_by: dict[int, set[int]] = {}
    snap_champs = {
        int(c["id"]): c
        for c in ((base_snapshot or {}).get("champions") or [])
        if isinstance(c, dict) and isinstance(c.get("id"), int)
    }
    shared = (
        (base_snapshot or {}).get("shared")
        if isinstance((base_snapshot or {}).get("shared"), dict)
        else {}
    )

    def _need(uid: int, kind: CatalogKind, champ_id: int) -> None:
        kinds.setdefault(uid, kind)
        needed_by.setdefault(uid, set()).add(champ_id)

    for hid in party_ids:
        entry = entries_by_id.get(hid) or {}
        snap = snap_champs.get(hid) or {}
        # Abilities from snapshot refs + live entry.
        for ab in snap.get("abilities") or entry.get("abilities") or []:
            if not isinstance(ab, dict):
                continue
            aid = ab.get("ref") if "ref" in ab else ab.get("id") or ab.get("ability_id")
            if isinstance(aid, int):
                _need(aid, "ability", hid)
        # Spec options from live specialization groups (all options).
        for group in entry.get("specialization_groups") or []:
            if not isinstance(group, dict):
                continue
            for opt in group.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                oid = opt.get("option_id")
                if isinstance(oid, int):
                    _need(oid, "specialization_option", hid)
        # Snapshot specialization refs.
        for group in snap.get("specializations") or []:
            if not isinstance(group, dict):
                continue
            for opt in group.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                oid = opt.get("ref") if "ref" in opt else opt.get("id")
                if isinstance(oid, int):
                    _need(oid, "specialization_option", hid)
        # Active feats.
        feats = entry.get("feats") if isinstance(entry.get("feats"), dict) else {}
        for feat in feats.get("active_feats") or []:
            if not isinstance(feat, dict):
                continue
            fid = feat.get("feat_id") or feat.get("id")
            if isinstance(fid, int):
                _need(fid, "feat", hid)

    # Recursive dependency closure with cycle detection.
    pending = list(kinds.keys())
    seen_edge: set[tuple[int, int]] = set()
    while pending:
        uid = pending.pop()
        kind = kinds.get(uid, "ability")
        body = _catalog_body(shared, kind=kind, item_id=uid) or _live_projected(
            uid, kind=kind
        )
        for dep in _deps_from_body(body):
            edge = (uid, dep)
            if edge in seen_edge:
                continue
            seen_edge.add(edge)
            if dep not in kinds:
                kinds[dep] = "ability"
                pending.append(dep)
            # Dependents inherit champion need-set.
            needed_by.setdefault(dep, set()).update(needed_by.get(uid) or ())

    return kinds, needed_by


def _delta_record(
    *,
    kind: CatalogKind,
    item_id: int,
    live: dict[str, Any],
    snap_body: dict[str, Any] | None,
    role: Literal["supplement", "correction"],
) -> dict[str, Any]:
    return _prune_empty(
        {
            "catalog": kind,
            "id": item_id,
            "role": role,
            "name": live.get("name"),
            # Canonical full effect — never a UI/clipboard preview slice.
            "effect": live.get("effect"),
            "effect_kind": live.get("effect_kind"),
            "magnitude": live.get("magnitude"),
            "depends_on_upgrade_ids": live.get("depends_on_upgrade_ids"),
            "advice_hint": live.get("advice_hint"),
            "description_status": _description_status_of_body(live),
            "parameter_status": _parameter_status_of_body(live),
            "unresolved_parameters": live.get("unresolved_parameters"),
            "source": "live_definitions_re_resolve",
            "overrides_snapshot": role == "correction",
            "snapshot_had_effect": _has_usable_effect(snap_body),
        }
    )


def _gap_record(
    *,
    kind: CatalogKind,
    item_id: int,
    name: str | None,
    champ_ids: Iterable[int],
    completeness: Completeness,
    dependent_option_ids: list[int],
    dependent_names: list[str],
    description_status: DescriptionStatus | None = None,
    parameter_status: ParameterStatus | None = None,
    cause: str | None = None,
) -> dict[str, Any]:
    limits = "specialization_comparison" if dependent_option_ids else "placement_qualitative"
    note = None
    if dependent_names:
        opts = " / ".join(dependent_names[:4])
        base = name or str(item_id)
        if completeness == "description_truncated":
            note = (
                f"Vergelijking van {opts} beperkt: beschrijving van {base} "
                f"is tekstueel onvolledig/afgekapt."
            )
        elif completeness == "parameter_missing":
            note = (
                f"Vergelijking van {opts} beperkt: parameters van {base} "
                f"zijn onopgelost (beschrijving kan wél volledig zijn)."
            )
        else:
            note = (
                f"Vergelijking van {opts} beperkt doordat {base} ontbreekt "
                f"of onvolledig is."
            )
    return _prune_empty(
        {
            "kind": "missing_mechanic",
            "catalog": kind,
            "id": item_id,
            "name": name,
            "completeness": completeness,
            "description_status": description_status,
            "parameter_status": parameter_status,
            "cause": cause,
            "champion_ids": sorted({int(c) for c in champ_ids}),
            "dependent_option_ids": dependent_option_ids or None,
            "limits": limits,
            "blocks_other_formation_advice": False,
            "blocks_proven_ranking_for": (
                "dependent_specialization_options"
                if dependent_option_ids
                else None
            ),
            "note": note,
        }
    )


def build_mechanics_completeness(
    *,
    party_ids: list[int],
    entries_by_id: dict[int, dict[str, Any]],
    base_snapshot: dict[str, Any] | None,
    party_names: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Build ``mechanics_delta`` + ``mechanic_gaps`` for an ADVICE_REQUEST."""
    shared = (
        (base_snapshot or {}).get("shared")
        if isinstance((base_snapshot or {}).get("shared"), dict)
        else {}
    )
    priority = (
        "mechanics_delta overrides BASE_SNAPSHOT shared catalogs for the "
        "same catalog+id when role=correction; supplements fill missing "
        "bodies. Dit is géén expected_state_override."
    )
    # Without a loaded snapshot catalog we cannot know what is missing vs
    # merely unloaded — do not dump the whole party kit into the request.
    if not isinstance(base_snapshot, dict) or not shared:
        return _prune_empty(
            {
                "priority": priority,
                "mechanic_gaps": [
                    {
                        "kind": "snapshot_mechanics_unavailable",
                        "completeness": "missing",
                        "limits": "specialization_comparison",
                        "blocks_other_formation_advice": False,
                        "note": (
                            "BASE_SNAPSHOT/shared mechanics niet beschikbaar "
                            "voor aanvulling; lees het snapshotbestand of "
                            "exporteer een nieuw basisbestand."
                        ),
                    }
                ],
                "counts": {"checked": 0, "delta": 0, "gaps": 1},
            }
        )

    kinds, needed_by = _walk_party_mechanic_ids(
        party_ids=party_ids,
        entries_by_id=entries_by_id,
        base_snapshot=base_snapshot,
    )

    # Map ability id → option ids that depend on it (for gap notes).
    dependents: dict[int, list[tuple[int, str]]] = {}
    for uid, kind in kinds.items():
        if kind != "specialization_option":
            continue
        live = _live_projected(uid, kind=kind)
        name = (live or {}).get("name") or str(uid)
        for dep in _deps_from_body(live) or _deps_from_body(
            _catalog_body(shared, kind=kind, item_id=uid)
        ):
            dependents.setdefault(dep, []).append((uid, str(name)))

    delta: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for uid in sorted(kinds.keys()):
        kind = kinds[uid]
        snap_body = _catalog_body(shared, kind=kind, item_id=uid)
        live = _live_projected(uid, kind=kind)
        snap_ok = _has_usable_effect(snap_body)
        live_ok = _has_usable_effect(live)
        snap_c = _completeness_of_body(snap_body)
        live_c = _completeness_of_body(live)

        live_eff = str((live or {}).get("effect") or "")
        snap_eff = str((snap_body or {}).get("effect") or "")
        preview_trunc = bool(
            live_ok
            and snap_ok
            and _looks_like_export_preview_truncation(snap_eff, live_eff)
        )

        if live_ok and not snap_ok:
            delta.append(
                _delta_record(
                    kind=kind,
                    item_id=uid,
                    live=live or {},
                    snap_body=snap_body,
                    role="supplement",
                )
            )
        elif live_ok and snap_ok and (
            live_eff != snap_eff or preview_trunc
        ):
            # Correct when live restores truncated/missing prose, or is longer.
            if preview_trunc:
                delta.append(
                    _delta_record(
                        kind=kind,
                        item_id=uid,
                        live=live or {},
                        snap_body=snap_body,
                        role="correction",
                    )
                )
            elif live_c in (
                "known",
                "partial",
                "parameter_missing",
                "magnitude_not_computed",
            ) and snap_c in ("missing", "description_truncated"):
                delta.append(
                    _delta_record(
                        kind=kind,
                        item_id=uid,
                        live=live or {},
                        snap_body=snap_body,
                        role="correction",
                    )
                )
            elif len(live_eff) > len(snap_eff) + 40:
                delta.append(
                    _delta_record(
                        kind=kind,
                        item_id=uid,
                        live=live or {},
                        snap_body=snap_body,
                        role="correction",
                    )
                )

        # Effective body for gap classification: prefer live (full re-resolve).
        effective = (live if live_ok else None) or (snap_body if snap_ok else None)
        effective_ok = _has_usable_effect(effective)
        deps = dependents.get(uid) or []
        dep_ids = [d[0] for d in deps]
        dep_names = [d[1] for d in deps]
        name = (live or snap_body or {}).get("name")
        champ_ids = needed_by.get(uid) or ()

        if not effective_ok:
            gaps.append(
                _gap_record(
                    kind=kind,
                    item_id=uid,
                    name=name,
                    champ_ids=champ_ids,
                    completeness="missing",
                    dependent_option_ids=dep_ids,
                    dependent_names=dep_names,
                    description_status="missing",
                    parameter_status="n/a",
                    cause="effect_missing",
                )
            )
        else:
            # Prefer live description status; treat unresolved legacy preview
            # as truncated only when we could not restore full live prose.
            desc_status = _description_status_of_body(effective)
            if (
                not live_ok
                and snap_ok
                and (
                    (snap_body or {}).get("description_truncated") is True
                    or (snap_body or {}).get("export_truncated") is True
                )
            ):
                desc_status = "truncated"
            param_status = _parameter_status_of_body(effective)

            # Truncation and unresolved parameters are independent signals.
            if desc_status == "truncated":
                gaps.append(
                    _gap_record(
                        kind=kind,
                        item_id=uid,
                        name=name,
                        champ_ids=champ_ids,
                        completeness="description_truncated",
                        dependent_option_ids=dep_ids,
                        dependent_names=dep_names,
                        description_status="truncated",
                        parameter_status=param_status,
                        cause=(
                            str((effective or {}).get("truncation_cause"))
                            if isinstance(effective, dict)
                            and (effective or {}).get("truncation_cause")
                            else "description_truncated"
                        ),
                    )
                )
            elif desc_status == "source_incomplete":
                gaps.append(
                    _gap_record(
                        kind=kind,
                        item_id=uid,
                        name=name,
                        champ_ids=champ_ids,
                        completeness="missing",
                        dependent_option_ids=dep_ids,
                        dependent_names=dep_names,
                        description_status="source_incomplete",
                        parameter_status=param_status,
                        cause="source_incomplete",
                    )
                )

            if param_status == "unresolved":
                gaps.append(
                    _gap_record(
                        kind=kind,
                        item_id=uid,
                        name=name,
                        champ_ids=champ_ids,
                        completeness="parameter_missing",
                        dependent_option_ids=dep_ids,
                        dependent_names=dep_names,
                        description_status=desc_status,
                        parameter_status="unresolved",
                        cause="unresolved_placeholders",
                    )
                )

    # Compact: drop magnitude_not_computed-only noise from gaps (still known mechanic).
    gaps = [g for g in gaps if g.get("completeness") != "magnitude_not_computed"]

    return _prune_empty(
        {
            "priority": priority,
            "mechanics_delta": delta or None,
            "mechanic_gaps": gaps or None,
            "counts": {
                "checked": len(kinds),
                "delta": len(delta),
                "gaps": len(gaps),
            },
        }
    )


def omit_oversized_effects_for_budget(
    block: dict[str, Any] | None,
    *,
    max_effect_chars: int,
) -> dict[str, Any] | None:
    """If an effect cannot fit the budget, omit it — never export a half string.

    Replaces oversized ``effect`` with an explicit gap
    (``description_truncated`` / ``export_budget``). Callers should prefer
    shrinking non-essential sections before invoking this.
    """
    if not isinstance(block, dict) or max_effect_chars <= 0:
        return block
    out = dict(block)
    delta: list[dict[str, Any]] = []
    gaps = list(out.get("mechanic_gaps") or [])
    for row in out.get("mechanics_delta") or []:
        if not isinstance(row, dict):
            continue
        effect = row.get("effect")
        if isinstance(effect, str) and len(effect) > max_effect_chars:
            omitted = dict(row)
            omitted.pop("effect", None)
            omitted["description_status"] = "truncated"
            omitted["description_truncated"] = True
            omitted["export_truncated"] = True
            omitted["truncation_cause"] = "export_budget"
            omitted["effect_omitted_for_budget"] = True
            delta.append(_prune_empty(omitted))
            cat = row.get("catalog")
            kind: CatalogKind = (
                cat
                if cat in ("ability", "specialization_option", "feat")
                else "ability"
            )
            gaps.append(
                _gap_record(
                    kind=kind,
                    item_id=int(row.get("id") or 0),
                    name=row.get("name"),
                    champ_ids=(),
                    completeness="description_truncated",
                    dependent_option_ids=list(row.get("dependent_option_ids") or []),
                    dependent_names=[],
                    description_status="truncated",
                    parameter_status=_parameter_status_of_body(row),
                    cause="export_budget",
                )
            )
        else:
            delta.append(row)
    out["mechanics_delta"] = delta or None
    out["mechanic_gaps"] = gaps or None
    return _prune_empty(out)


def compact_mechanics_for_clipboard(block: dict[str, Any] | None) -> dict[str, Any] | None:
    """Shrink mechanics block for the clipboard UTF-8 byte budget.

    Keeps full canonical ``effect`` prose. Never mid-sentence truncates into a
    preview ellipsis — that previously poisoned Beehive Barrage (15049).
    """
    if not isinstance(block, dict):
        return None
    out = dict(block)
    delta = []
    for row in out.get("mechanics_delta") or []:
        if not isinstance(row, dict):
            continue
        effect = row.get("effect")
        # Do not slice effect text. Budget pressure must omit+gap, not half-cut.
        delta.append(
            _prune_empty(
                {
                    "catalog": row.get("catalog"),
                    "id": row.get("id"),
                    "role": row.get("role"),
                    "name": row.get("name"),
                    "effect": effect,
                    "effect_kind": row.get("effect_kind"),
                    "magnitude": row.get("magnitude"),
                    "depends_on_upgrade_ids": row.get("depends_on_upgrade_ids"),
                    "description_status": row.get("description_status"),
                    "parameter_status": row.get("parameter_status"),
                    "unresolved_parameters": row.get("unresolved_parameters"),
                    "source": row.get("source"),
                    "overrides_snapshot": row.get("overrides_snapshot"),
                    "snapshot_had_effect": row.get("snapshot_had_effect"),
                    "effect_omitted_for_budget": row.get("effect_omitted_for_budget"),
                    "truncation_cause": row.get("truncation_cause"),
                }
            )
        )
    # Clipboard budget: keep detail only where it changes advice limits.
    # Bulk parameter_missing (no spec deps) → id lists (~5k → hundreds).
    detail: list[dict[str, Any]] = []
    bulk_ids: dict[str, list[int]] = {}
    for row in out.get("mechanic_gaps") or []:
        if not isinstance(row, dict):
            continue
        completeness = str(row.get("completeness") or "missing")
        deps = row.get("dependent_option_ids") or []
        has_deps = bool(deps)
        structural = completeness in ("missing", "description_truncated") or has_deps
        item_id = row.get("id")
        if (
            not structural
            and completeness == "parameter_missing"
            and (isinstance(item_id, int) or str(item_id).isdigit())
        ):
            bulk_ids.setdefault("parameter_missing", []).append(int(item_id))
            continue

        desc_status = row.get("description_status")
        param_status = row.get("parameter_status")
        cause = row.get("cause")
        if completeness == "parameter_missing" and desc_status == "full":
            desc_status = None
        if completeness == "parameter_missing" and param_status == "unresolved":
            param_status = None
        if completeness == "description_truncated" and desc_status == "truncated":
            desc_status = None
        if completeness == "missing" and desc_status == "missing":
            desc_status = None
        if completeness == "parameter_missing" and cause == "unresolved_placeholders":
            cause = None
        if completeness == "missing" and cause == "effect_missing":
            cause = None
        detail.append(
            _prune_empty(
                {
                    "catalog": row.get("catalog"),
                    "id": item_id,
                    "name": row.get("name"),
                    "completeness": completeness,
                    "description_status": desc_status,
                    "parameter_status": param_status,
                    "cause": cause,
                    "dependent_option_ids": deps or None,
                    "limits": row.get("limits"),
                    "note": row.get("note"),
                }
            )
        )

    for key, ids in list(bulk_ids.items()):
        bulk_ids[key] = sorted(set(ids))

    out["mechanics_delta"] = delta or None
    out["mechanic_gaps"] = detail or None
    out["mechanic_gap_ids"] = bulk_ids or None
    if bulk_ids:
        out["mechanic_gaps_note"] = (
            "mechanic_gap_ids.parameter_missing: effectproza beschikbaar "
            "(snapshot/delta); alleen placeholders onopgelost. "
            "Spec-vergelijking alleen beperkt waar mechanic_gaps "
            "dependent_option_ids heeft."
        )
    return _prune_empty(out)
