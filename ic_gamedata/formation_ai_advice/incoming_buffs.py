"""Incoming formation buffs toward a selected main DPS (clipboard summary)."""

from __future__ import annotations

from typing import Any, Literal, Mapping

from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.formation_advisor.models import FormationLayoutContext
from ic_gamedata.formation_advisor.topology import fallback_seat_column
from ic_gamedata.formation_ai_advice.export import build_export_payload
from ic_gamedata.formation_ai_advice.mechanics import positional_recipient_applies
from ic_gamedata.party_advisor_models import FormationHero

Reach = Literal["yes", "no", "unknown"]


def _column(ctx: FormationLayoutContext, seat: int | None) -> int | None:
    if seat is None:
        return None
    return ctx.topology.seat_column.get(seat, fallback_seat_column(seat))


def _ability_rows(champ: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Abilities + selected specialization options with mechanic text/facts.

    Catalog identity for BASE_SNAPSHOT is the upgrade/option/feat id
    (``catalog_ref``). ``effect_def_id`` is the separate effect_defines id and
    must never be used as a snapshot ability catalog key.
    """
    rows: list[dict[str, Any]] = []
    seen_spec_ids: set[int] = set()
    for ab in champ.get("abilities") or []:
        if isinstance(ab, dict) and (ab.get("name") or ab.get("mechanical_text")):
            row = dict(ab)
            row.setdefault("kind", "ability")
            catalog_ref = row.get("ability_id")
            if catalog_ref is None:
                catalog_ref = row.get("id")
            row["catalog_ref"] = catalog_ref
            # Keep effect_defines id under a distinct key only.
            if "effect_def_id" not in row and row.get("effect_id") is not None:
                # effect_id on ability rows is effect_defines id — do not alias
                # it onto catalog_ref.
                row["effect_def_id"] = row.get("effect_id")
            row["effect_catalog"] = "ability"
            rows.append(row)
    for group in champ.get("specialization_groups") or []:
        if not isinstance(group, dict):
            continue
        for opt in group.get("options") or []:
            if not isinstance(opt, dict) or not opt.get("selected"):
                continue
            oid = opt.get("option_id")
            if oid is None:
                oid = opt.get("id")
            if isinstance(oid, int):
                seen_spec_ids.add(oid)
            rows.append(
                {
                    "name": opt.get("name"),
                    "mechanical_text": opt.get("mechanical_text") or opt.get("text"),
                    "effect_facts": opt.get("effect_facts"),
                    "usability": opt.get("usability"),
                    "kind": "specialization",
                    "catalog_ref": oid,
                    "effect_def_id": opt.get("effect_id"),
                    "effect_catalog": "specialization",
                }
            )
    # Drop kit/dependency ability rows that duplicate a selected specialization
    # upgrade id (avoid double-counting the same mechanic).
    if seen_spec_ids:
        rows = [
            r
            for r in rows
            if not (
                r.get("kind") == "ability"
                and isinstance(r.get("catalog_ref"), int)
                and r["catalog_ref"] in seen_spec_ids
            )
        ]
    for feat in (champ.get("feats") or {}).get("active_feats") or []:
        if not isinstance(feat, dict):
            continue
        fid = feat.get("feat_id")
        if fid is None:
            fid = feat.get("id")
        rows.append(
            {
                "name": feat.get("name"),
                "mechanical_text": feat.get("mechanical_text"),
                "effect_facts": feat.get("effect_facts"),
                "usability": feat.get("usability"),
                "kind": "feat",
                "catalog_ref": fid,
                "effect_def_id": None,
                "effect_catalog": "feat",
            }
        )
    return rows


def _facts(row: Mapping[str, Any]) -> dict[str, Any]:
    facts = row.get("effect_facts")
    return dict(facts) if isinstance(facts, dict) else {}


def _semantics(facts: Mapping[str, Any]) -> dict[str, Any]:
    sem = facts.get("semantics")
    return dict(sem) if isinstance(sem, dict) else {}


def _target_tokens(facts: Mapping[str, Any], sem: Mapping[str, Any]) -> list[str]:
    tokens = facts.get("targets")
    if not isinstance(tokens, list) or not tokens:
        recipients = sem.get("recipients") if isinstance(sem.get("recipients"), dict) else {}
        tokens = recipients.get("targets") if isinstance(recipients, dict) else None
    if not isinstance(tokens, list):
        return []
    return [str(t).strip().casefold() for t in tokens if t is not None and str(t).strip()]


def _recipient_tags(facts: Mapping[str, Any], sem: Mapping[str, Any]) -> list[str]:
    tags = facts.get("target_tags")
    if not isinstance(tags, list) or not tags:
        recipients = sem.get("recipients") if isinstance(sem.get("recipients"), dict) else {}
        tags = recipients.get("tags") if isinstance(recipients, dict) else None
    if not isinstance(tags, list):
        return []
    return [str(t).strip().casefold() for t in tags if t is not None and str(t).strip()]


def _dps_tag_set(ctx: FormationLayoutContext, dps_id: int) -> set[str]:
    roles = {str(r).casefold() for r in ctx.hero_roles_by_id.get(dps_id, ())}
    tags = {str(t).casefold() for t in ctx.hero_tags_by_id.get(dps_id, ())}
    return roles | tags


def _token_reaches_dps(
    token: str,
    *,
    ctx: FormationLayoutContext,
    owner_id: int,
    dps_id: int,
) -> Reach:
    owner_seat = ctx.seat_of(owner_id)
    dps_seat = ctx.seat_of(dps_id)
    owner_col = _column(ctx, owner_seat)
    dps_col = _column(ctx, dps_seat)
    if owner_seat is None or dps_seat is None or owner_col is None or dps_col is None:
        return "unknown"

    t = token.casefold()
    if t in {"adj", "adjacent"}:
        return "yes" if ctx.is_adjacent(owner_id, dps_id) else "no"
    if t in {"non_adj", "non-adjacent", "non_adjacent"}:
        if owner_id == dps_id:
            return "no"
        return "yes" if not ctx.is_adjacent(owner_id, dps_id) else "no"

    applies = positional_recipient_applies(
        t,
        owner_column=int(owner_col),
        candidate_column=int(dps_col),
        candidate_is_owner=(owner_id == dps_id),
    )
    if applies is True:
        return "yes"
    if applies is False:
        return "no"
    return "unknown"


def _tags_match_dps(required: list[str], dps_tags: set[str]) -> Reach:
    if not required:
        return "yes"
    # OR semantics for alternate tags (common in filter_targets).
    if any(tag in dps_tags for tag in required):
        return "yes"
    # Soft aliases
    aliases = {
        "tanking": "tank",
        "dps": "dps",
        "support": "support",
        "healer": "healer",
    }
    for tag in required:
        alt = aliases.get(tag)
        if alt and alt in dps_tags:
            return "yes"
    return "no"


def _unresolved_activation_deps(
    facts: Mapping[str, Any], sem: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Compact unresolved activation/predicate dependencies (no invented state)."""
    import re

    deps: list[dict[str, Any]] = []
    predicate = sem.get("predicate") if isinstance(sem.get("predicate"), dict) else None
    if predicate is None and isinstance(facts.get("targeting"), dict):
        predicate = facts.get("targeting")
    if isinstance(predicate, dict):
        for clause in predicate.get("base_clauses") or []:
            if not isinstance(clause, str):
                continue
            for m in re.finditer(r"HasEffect\(`([^`]+)`\)", clause):
                deps.append(
                    {
                        "kind": "has_effect",
                        "key": m.group(1),
                        "status": "unknown",
                        "reason_code": "effect_presence_unobserved",
                    }
                )
            for m in re.finditer(r"GetUpgradeUnlocked\((\d+)\)", clause):
                deps.append(
                    {
                        "kind": "upgrade_unlocked",
                        "upgrade_id": int(m.group(1)),
                        "status": "unknown",
                        "reason_code": "upgrade_unlock_unobserved",
                    }
                )
        for ext in predicate.get("extensions") or []:
            if not isinstance(ext, dict):
                continue
            active = ext.get("active_in_current_state")
            if active is True:
                continue
            for uid in ext.get("requires_any_upgrade_id") or []:
                if isinstance(uid, int):
                    deps.append(
                        {
                            "kind": "upgrade_unlocked",
                            "upgrade_id": uid,
                            "status": "unknown" if active == "unknown" else "inactive",
                            "reason_code": (
                                "upgrade_unlock_unobserved"
                                if active == "unknown"
                                else "upgrade_not_selected"
                            ),
                        }
                    )
    activation = sem.get("activation_conditions") or facts.get("activation_conditions")
    if isinstance(activation, dict) and activation:
        deps.append(
            {
                "kind": "activation_condition",
                "key": activation.get("kind") or "condition",
                "status": str(activation.get("status") or "unknown"),
                "reason_code": "activation_condition_unverified",
            }
        )
    # Dedup by kind+key/upgrade_id
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for dep in deps:
        sig = (dep.get("kind"), dep.get("key"), dep.get("upgrade_id"))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(dep)
    return out


def mechanic_reaches_main_dps(
    row: Mapping[str, Any],
    *,
    ctx: FormationLayoutContext,
    owner_id: int,
    dps_id: int,
) -> tuple[Reach, str]:
    """Return (reach, short reason) for one ability/spec/feat row.

    Reach is geometry/filter eligibility only. Unresolved activation predicates
    (e.g. HasEffect(`merciless_resolve`)) do **not** make ``all`` targeting an
    unconditional yes — callers must treat activation separately.
    """
    facts = _facts(row)
    sem = _semantics(facts)
    scope = str(facts.get("effect_scope") or sem.get("scope") or "unknown").casefold()
    dps_tags = _dps_tag_set(ctx, dps_id)
    unresolved = _unresolved_activation_deps(facts, sem)

    if owner_id == dps_id:
        if scope in {"owner", "unknown"} and not _target_tokens(facts, sem):
            if unresolved:
                return "unknown", "eigen mechanic; activatievoorwaarde onopgelost"
            return "yes", "eigen mechanic (hoofd-DPS)"
        # Fall through: positional self-buffs still evaluated.

    if scope == "owner":
        return ("yes", "eigen scope") if owner_id == dps_id else ("no", "alleen eigenaar")

    tokens = _target_tokens(facts, sem)
    tags = _recipient_tags(facts, sem)

    if tags:
        tag_reach = _tags_match_dps(tags, dps_tags)
        if tag_reach == "no":
            return "no", f"filter-tags {tags} matchen hoofd-DPS niet"

    # Filtered ``all`` with HasEffect / upgrade gates is not unconditional global.
    if unresolved and (scope == "filtered" or tokens == ["all"] or tokens == ["formation"]):
        return "unknown", "filtered_all_with_unresolved_activation"

    if scope == "global" and not unresolved:
        return "yes", "globale formation-buff"

    if not tokens:
        if scope == "filtered" and tags:
            reach = _tags_match_dps(tags, dps_tags)
            if reach == "yes" and unresolved:
                return "unknown", "tag-filter; activatievoorwaarde onopgelost"
            return reach, "tag-filter"
        if scope in {"positional", "filtered", "mixed"}:
            return "unknown", "targeting niet eenduidig"
        if scope == "unknown":
            return "unknown", "scope/targeting onbekend"
        return "unknown", "geen recipient-tokens"

    reaches = [_token_reaches_dps(tok, ctx=ctx, owner_id=owner_id, dps_id=dps_id) for tok in tokens]
    if any(r == "yes" for r in reaches):
        if unresolved:
            return "unknown", f"targeting {tokens}; activatievoorwaarde onopgelost"
        return "yes", f"targeting {tokens}"
    if all(r == "no" for r in reaches):
        return "no", f"targeting {tokens} raakt hoofd-DPS niet"
    return "unknown", f"targeting {tokens} deels onbekend"


def collect_incoming_buffs(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...],
    *,
    main_dps_id: int,
    goal: str = "push",
    context: str = "campaign",
) -> dict[str, Any]:
    """Build structured incoming-buff summary for ``main_dps_id``."""
    if not any(h.hero_id == main_dps_id for h in formation):
        return {
            "ok": False,
            "error": (
                f"Hoofd-DPS id {main_dps_id} staat niet in de huidige formatie."
            ),
        }

    ctx = build_formation_layout_context(
        payload,
        formation,
        goal=goal,
        context=context,
    )
    export = build_export_payload(
        payload,
        formation,
        goal=goal,
        context=context,
        fixed_main_dps_id=main_dps_id,
    )
    champs = [
        c
        for c in (export.get("champions") or [])
        if isinstance(c, dict) and isinstance(c.get("champion_id"), int)
    ]
    dps_name = ctx.hero_name_by_id.get(main_dps_id) or str(main_dps_id)
    dps_seat = ctx.seat_of(main_dps_id)
    dps_col = _column(ctx, dps_seat)

    incoming: list[dict[str, Any]] = []
    own: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []

    for champ in champs:
        owner_id = int(champ["champion_id"])
        owner_name = str(champ.get("name") or owner_id)
        owner_seat = champ.get("current_position") or ctx.seat_of(owner_id)
        for row in _ability_rows(champ):
            reach, reason = mechanic_reaches_main_dps(
                row, ctx=ctx, owner_id=owner_id, dps_id=main_dps_id
            )
            tip = row.get("mechanical_text") or row.get("text")
            if isinstance(tip, str):
                tip = tip.strip() or None
            kind = str(row.get("kind") or "ability")
            catalog_ref = row.get("catalog_ref")
            if catalog_ref is None:
                catalog_ref = row.get("ability_id") or row.get("feat_id") or row.get("option_id")
            effect_def_id = row.get("effect_def_id")
            # Never fall back to effect_defines id as catalog_ref.
            if effect_def_id is None and kind == "ability":
                # Ability rows store effect_defines under effect_id.
                maybe_def = row.get("effect_id")
                maybe_ab = row.get("ability_id")
                if (
                    isinstance(maybe_def, int)
                    and isinstance(maybe_ab, int)
                    and maybe_def != maybe_ab
                ):
                    effect_def_id = maybe_def
            catalog = row.get("effect_catalog")
            if not isinstance(catalog, str) or not catalog:
                catalog = (
                    "feat"
                    if kind == "feat"
                    else ("specialization" if kind == "specialization" else "ability")
                )
            facts = _facts(row)
            sem = _semantics(facts)
            deps = _unresolved_activation_deps(facts, sem)
            entry = {
                "owner_id": owner_id,
                "owner_name": owner_name,
                "owner_seat": owner_seat,
                "kind": kind,
                "name": row.get("name") or "?",
                "effect": tip,
                "catalog_ref": catalog_ref,
                "effect_def_id": effect_def_id,
                "effect_catalog": catalog,
                "reach": reach,
                "reason": reason,
                "dependencies": deps or None,
            }
            if owner_id == main_dps_id:
                if reach == "yes":
                    own.append(entry)
                elif reach == "unknown":
                    uncertain.append(entry)
                continue
            if reach == "yes":
                incoming.append(entry)
            elif reach == "unknown":
                uncertain.append(entry)

    return {
        "ok": True,
        "main_dps_id": main_dps_id,
        "main_dps_name": dps_name,
        "main_dps_seat": dps_seat,
        "main_dps_column": dps_col,
        "incoming": incoming,
        "own": own,
        "uncertain": uncertain,
    }


def format_incoming_buffs_clipboard(report: Mapping[str, Any]) -> str:
    """Plain-text clipboard body (Dutch)."""
    if not report.get("ok"):
        return str(report.get("error") or "Kon inkomende buffs niet bepalen.")

    name = report.get("main_dps_name") or "?"
    seat = report.get("main_dps_seat")
    col = report.get("main_dps_column")
    lines = [
        f"Inkomende buffs → {name} (hoofd-DPS)",
        f"Seat {seat} · kolom {col}",
        "",
    ]

    incoming = list(report.get("incoming") or [])
    if not incoming:
        lines.append("Geen bevestigde inkomende buffs gevonden.")
    else:
        lines.append(f"Bevestigd inkomend ({len(incoming)}):")
        by_owner: dict[str, list[dict[str, Any]]] = {}
        for row in incoming:
            key = f"{row.get('owner_name')} (seat {row.get('owner_seat')})"
            by_owner.setdefault(key, []).append(row)
        for owner_key, rows in by_owner.items():
            lines.append(f"- Van {owner_key}:")
            for row in rows:
                kind = row.get("kind") or "ability"
                tip = row.get("effect") or "(geen mechanictekst)"
                lines.append(f"  · [{kind}] {row.get('name')}: {tip}")
                lines.append(f"    ({row.get('reason')})")

    own = list(report.get("own") or [])
    if own:
        lines.extend(["", f"Eigen buffs van {name} ({len(own)}):"])
        for row in own:
            tip = row.get("effect") or "(geen mechanictekst)"
            lines.append(f"- [{row.get('kind')}] {row.get('name')}: {tip}")

    uncertain = list(report.get("uncertain") or [])
    if uncertain:
        lines.extend(
            [
                "",
                f"Onzeker / niet bevestigd ({len(uncertain)}):",
                "(targeting of scope niet hard genoeg om ja/nee te zeggen)",
            ]
        )
        for row in uncertain:
            tip = row.get("effect") or "(geen mechanictekst)"
            lines.append(
                f"- {row.get('owner_name')}: [{row.get('kind')}] "
                f"{row.get('name')}: {tip}"
            )
            lines.append(f"  ({row.get('reason')})")

    lines.extend(
        [
            "",
            "Bron: actuele formatie + mechanic-export. "
            "Geen verzonnen percentages; onbekende targeting blijft onzeker.",
        ]
    )
    return "\n".join(lines)
