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
from typing import Any, Iterable, Literal

from ic_gamedata.formation_ai_advice.clipboard_export import (
    _HINT_ABILITY_MISSING,
    _project_champion_for_advice,
    _prune_empty,
)
from ic_gamedata.formation_ai_advice.export import (
    _ability_score_and_attack_maps,
    _data_version,
    _restriction_block,
    _utc_now_iso,
    build_champion_entry,
    build_export_payload,
)
from ic_gamedata.formation_ai_advice.models import SCHEMA_VERSION
from ic_gamedata.formation_ai_advice.mechanics_completeness import (
    build_mechanics_completeness,
)
from ic_gamedata.formation_ai_advice.reply_contract import (
    build_answer_contract,
    snapshot_expected_filename,
)
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.party_advisor_models import FormationHero

ExportKind = Literal["base_snapshot", "advice_request", "champion_details"]

SNAPSHOT_EXPORT_SCHEMA = "1.0"

_SOURCE_PRIORITY = (
    "BASE_SNAPSHOT levert mechanics en vaste championgegevens (o.a. gender, "
    "alignment, roles, specialization-opties). ADVICE_REQUEST levert de "
    "actuele veranderlijke toestand en overschrijft daarvoor de snapshot: "
    "party, posities, geselecteerde specialisaties, ontgrendelstatus, live "
    "stacks/fase en eligibility, voor zover expliciet aangeleverd. Een "
    "actuele geselecteerde specialisatie vervangt de oudere selectie én een "
    "oudere status zoals not_unlocked voor dezelfde specialisatiegroep. "
    "Ontbrekende of unknown actuele waarden mogen niet stilzwijgend worden "
    "ingevuld met oude snapshotwaarden. Mechanics niet afleiden uit "
    "championnamen, herinnering of de geselecteerde optie."
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
            data_version=data_version,
        )

        def _builder(_hid: int = hid) -> dict[str, Any]:
            return build_champion_entry(
                payload,
                ctx,
                _hid,
                current_position=None,
                ilvl=ilvl_map.get(_hid),
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
                "mechanics (not adventure eligibility, geometry, or live stacks)"
            ),
            "account_state_hash": account_state_hash,
            "account_state_hash_covers": (
                "owned champion ids + snapshot loadout selections/feats/"
                "equipment status fields"
            ),
            "data_version": data_version,
            "research_mode": "provided_data_only",
        },
        "bronregels": _BRONREGELS,
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
                "note": (
                    "Adventure-eligibility hoort niet in dit basisbestand; "
                    "die staat in ADVICE_REQUEST."
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
) -> dict[str, Any]:
    """Build eligibility summary.

    When ``focus_ids`` is set (selected-only / no-swap scope), only those
    champions are listed in detail. Full owned evaluation still runs so party
    vs roster conflicts stay visible via counts, but bulky per-id denied lists
    and other_party notes for the rest of the roster are omitted.
    """
    from ic_gamedata.adventure_restrictions import (
        build_adventure_roster_filter,
        evaluate_heroes_against_filter,
    )
    from ic_gamedata.formation_ai_advice.swap_export import (
        _effective_eligibility_record,
        _other_party_instance,
    )

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
    resolved_snapshot = base_snapshot
    if resolved_snapshot is None:
        resolved_snapshot = _load_matching_base_snapshot(snapshot_id)
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
        party_state.append(
            _prune_empty(
                {
                    "id": cid,
                    "name": champ.get("name"),
                    "seat": champ.get("seat"),
                    "position": champ.get("current_position"),
                    "locked": champ.get("locked") or None,
                    "lock_reason": champ.get("lock_reason"),
                    "specialization_choices": current_choices or None,
                    "live_state": _live_state_from_entry(champ),
                    "trait_delta_vs_base": trait_delta,
                    "eligibility": (
                        (champ.get("eligibility") or {}).get("effective_eligibility")
                        if isinstance(champ.get("eligibility"), dict)
                        else None
                    ),
                }
            )
        )

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

    distance = (
        formation_block.get("distance")
        if isinstance(formation_block.get("distance"), dict)
        else {}
    )
    from ic_gamedata.formation_ai_advice.labels import position_display_convention_block

    front_direction = formation_block.get("front_direction") or {
        "rule": "lower_column_is_front",
    }
    convention = formation_block.get("position_display_convention")
    if not isinstance(convention, dict):
        convention = position_display_convention_block(technical_id_field="id")
    else:
        convention = {**convention, "technical_id_field": "id"}
    geometry = _prune_empty(
        {
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
            "adjacency": formation_block.get("adjacency_by_position"),
            "positions": [
                _prune_empty(
                    {
                        "id": row.get("position_id"),
                        "column": row.get("column_index"),
                        "row": row.get("row_order"),
                        "zone": row.get("zone"),
                        "champion_id": row.get("current_champion_id"),
                        "display_column": row.get("display_column"),
                        "display_slot": row.get("display_slot"),
                        "display_position": row.get("display_position"),
                    }
                )
                for row in (formation_block.get("positions") or [])
                if isinstance(row, dict)
            ]
            or None,
            "table_order_note": formation_block.get("table_order_note"),
        }
    )

    constraints = export.get("constraints") if isinstance(export.get("constraints"), dict) else {}
    readiness = export.get("readiness") if isinstance(export.get("readiness"), dict) else {}
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

    result: dict[str, Any] = {
        "meta": {
            "export_kind": "advice_request",
            "export_schema_version": SNAPSHOT_EXPORT_SCHEMA,
            "advice_schema_version": SCHEMA_VERSION,
            "request_id": req_id,
            "created_at": _utc_now_iso(),
            "snapshot_ref": {
                "snapshot_id": snapshot_id,
                "expected_filename": snapshot_expected_filename(str(snapshot_id)),
                "mechanics_hash": snap_meta.get("mechanics_hash"),
                "account_state_hash": snap_meta.get("account_state_hash"),
                "contains_snapshot_body": False,
            },
            "research_mode": research_mode,
            "scope": (export.get("meta") or {}).get("scope"),
            "data_version": (export.get("meta") or {}).get("data_version"),
        },
        "answer_contract": build_answer_contract(
            str(req_id),
            party=party_state,
            valid_position_ids=(
                list(geometry.get("valid_position_ids") or [])
                if isinstance(geometry, dict)
                else None
            ),
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
        "goal": {
            **(
                _prune_empty(
                    {
                        "id": goal_block.get("id"),
                        "label": goal_block.get("label"),
                        "description": goal_block.get("description"),
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
        "readiness": _prune_empty(
            {
                "status": readiness.get("status"),
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
    # Keep answer_contract intact (empty specializations[] / false flags matter).
    answer_contract = result.get("answer_contract")
    pruned = _prune_empty(result)
    if isinstance(answer_contract, dict):
        pruned["answer_contract"] = answer_contract
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
    ref = ((request.get("meta") or {}).get("snapshot_ref") or {}).get("snapshot_id")
    return "\n".join(
        [
            "# Idle Champions — ADVICE_REQUEST",
            "",
            "Compacte actuele aanvraag. Mechanics staan in BASE_SNAPSHOT.",
            f"snapshot_ref: `{ref or '?'}`",
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
