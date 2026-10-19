"""Clipboard text builders for compact export (BASE / REQUEST / DETAILS).

Preview, counters, and clipboard output must use the exact same string
returned by these builders — never re-format after counting.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Literal

from ic_gamedata.formation_ai_advice.export_budget import (
    DEFAULT_CHAR_BUDGET,
    budget_status,
    count_chars,
    section_sizes,
)
from ic_gamedata.formation_ai_advice.labels import (
    POSITION_DISPLAY_AI_INSTRUCTION,
)
from ic_gamedata.formation_ai_advice.reply_contract import (
    reply_format_pointer_nl,
    snapshot_expected_filename,
)
from ic_gamedata.formation_ai_advice.snapshot_export import minify_json

InstructionMode = Literal["project", "standalone"]

# Short pointer; full importer rules live in request JSON ``answer_contract``.
ADVICE_TABLE_FORMAT = reply_format_pointer_nl()


class AdviceRequestBudgetError(ValueError):
    """Raised when a finished ADVICE_REQUEST clipboard export exceeds the limit."""

    def __init__(self, *, chars: int, max_chars: int, cause: str) -> None:
        self.chars = chars
        self.max_chars = max_chars
        self.cause = cause
        super().__init__(
            f"ADVICE_REQUEST te groot: {chars} tekens (max {max_chars}). {cause}"
        )

PROJECT_INSTRUCTIONS = """# Idle Champions — vaste projectinstructies (formatieadvies)

Gebruik deze regels bij adviesvragen die naar een BASE_SNAPSHOT verwijzen.

- Pas actuele toestand uit ADVICE_REQUEST toe vóór vergelijking en advies.
- BASE_SNAPSHOT = mechanics + vaste championgegevens; ADVICE_REQUEST = actuele veranderlijke toestand (party, posities, specs, ontgrendelstatus, live stacks/fase, eligibility) en overschrijft die velden.
- Verschillen met oudere snapshotselecties of ontgrendelstatus zijn normale overrides (expected_state_override), geen conflicten — meld ze niet als waarschuwing.
- Meld alleen materiële, onopgeloste tegenstrijdigheden (material_source_conflict).
- Meld ontbrekende vergelijkingsgegevens (missing_comparison_data) apart en beperk die onzekerheid tot de betreffende vergelijking; overig advies dat door beschikbare gegevens gedragen wordt blijft staan.
- Ontbrekende/unknown actuele waarden niet stilzwijgend invullen met oude snapshotwaarden.
- Huidige selectie bekend ≠ beste keuze aantoonbaar bepaald; geen bewezen optimale ranking zonder de benodigde gegevens.
- Maximaal één champion per permanente seat.
- Voorstellen met championwissels zijn onderling onafhankelijk (ieder start vanaf dezelfde baseline-party), tenzij de aanvraag anders zegt.
- Geen automatische hoofd-DPS-lock: alleen een expliciet vastgezette hoofd-DPS is locked.
- Vergelijk kandidaten met een goed herplaatste baseline (niet alleen “nieuwe champion erin”).
- Wijzig geen feats of equipment tenzij de aanvraag dat expliciet toestaat.
- Verzin geen schadewinst of damage-multipliers; itemlevels zijn geen vermenigvuldigers.
- Lever complete eindformaties met geldige specialisaties (echte keuzegroepen/prerequisites).
- Benoem expliciete onzekerheid en dekkingsbeperkingen; claim geen bewezen optimum zonder bewijs.
- Leid ontbrekende mechanics of gender niet af uit championnamen, flavor of herinnering.
- Permanent seat ≠ fysieke positie.
- """ + POSITION_DISPLAY_AI_INSTRUCTION + """

""" + ADVICE_TABLE_FORMAT


def safety_instruction(snapshot_id: str) -> str:
    sid = snapshot_id.strip() or "?"
    fname = snapshot_expected_filename(sid)
    return (
        f"snapshot_ref wijst naar basissnapshot `{sid}` "
        f"(verwacht bestand `{fname}`); dit verzoek bevat die inhoud niet. "
        "Lees eerst die basissnapshot vóór mechanic-afhankelijk advies. "
        "Ontbreekt of onleesbaar: meld dat en verzin geen mechanics. "
        "ADVICE_REQUEST overschrijft veranderlijke snapshottoestand. "
        "Expected overrides ≠ bronconflicten. "
        "Leid ontbrekende mechanics/gender niet af uit namen of herinnering."
    )


def instruction_mode_assumption(mode: InstructionMode) -> str:
    if mode == "project":
        return (
            "Modus: Voor mijn project — korte instructies. "
            "Gaat ervan uit dat de vaste advieswerkwijze in het project staat. "
            "Basis-snapshotreferentie en veiligheidsvoorwaarden blijven aanwezig."
        )
    return (
        "Modus: Zelfstandig — algemene adviesinstructies zijn bijgevoegd. "
        "Het genoemde basisbestand blijft nodig voor mechanics "
        "(niet volledig zelfstandig zonder bijlagen)."
    )


def _standalone_advice_rules(*, swap: bool) -> list[str]:
    lines = [
        "Je bent een Idle Champions-formatieadviseur.",
        "Dit is een game-adviesaanvraag, geen programmeer- of exportreviewtaak.",
        "",
    ]
    if swap:
        lines.extend(
            [
                "Zoek relevante één-wisselvoorstellen binnen de aangeleverde "
                "eligibility/classificatie en BASE_SNAPSHOT-mechanics.",
                "Maximaal één wissel per voorstel; voorstellen zijn onafhankelijk.",
                "Geen verborgen top-N of tierlijst.",
            ]
        )
    else:
        lines.extend(
            [
                "Adviseer plaatsing en specialisaties van de huidige party "
                "voor het genoemde doel.",
                "Vervang geen champions tenzij de aanvraag swap-scope heeft.",
            ]
        )
    lines.extend(
        [
            "",
            "Harde regels:",
            "- Maximaal één champion per permanente seat.",
            "- Permanent seat ≠ fysieke positie.",
            "- Geen automatische hoofd-DPS-lock.",
            "- Wijzig geen feats/equipment tenzij expliciet toegestaan.",
            "- Geen verzonnen schadewinst.",
            "- Complete eindformaties en geldige specialisaties.",
            "- Expliciete onzekerheid en dekkingsbeperkingen.",
        ]
    )
    return lines


def compact_request_for_clipboard(request: dict[str, Any]) -> dict[str, Any]:
    """Semantic-preserving shrink of an ADVICE_REQUEST for clipboard paste.

    Never drops answer_contract, snapshot_ref identity/hashes, geometry,
    party/specs, hard constraints, or material uncertainties.
    """
    payload = copy.deepcopy(request)

    # Legacy alias → canonical name.
    if "answer_contract" not in payload and isinstance(
        payload.get("reply_contract"), dict
    ):
        payload["answer_contract"] = payload.pop("reply_contract")
    else:
        payload.pop("reply_contract", None)

    # bronregels + live_state note duplicate safety/project instructions.
    payload.pop("bronregels", None)
    defaults = payload.get("live_state_defaults")
    if isinstance(defaults, dict):
        defaults.pop("note", None)
        if not defaults:
            payload.pop("live_state_defaults", None)

    meta = payload.get("meta")
    if isinstance(meta, dict):
        validation = meta.get("validation")
        if isinstance(validation, dict):
            validation.pop("field_meanings", None)

    geometry = payload.get("geometry")
    if isinstance(geometry, dict):
        convention = geometry.get("position_display_convention")
        if isinstance(convention, dict):
            convention.pop("known_column_direction_rules", None)
            convention.pop("row_direction", None)
        column_direction = geometry.get("column_direction")
        if isinstance(column_direction, dict):
            column_direction.pop("ui_note", None)
            column_direction.pop("source", None)

    goal = payload.get("goal")
    if isinstance(goal, dict):
        structured = goal.get("structured_restrictions")
        if isinstance(structured, dict):
            structured.pop("checked_means", None)
            structured.pop("raw_restrictions_text", None)
            # Full raw adventure sentence is already in goal.restriction_text /
            # adventure context when present — drop duplicate blob.
            structured.pop("raw_restriction_texts", None)
            for gate in structured.get("stat_gates") or []:
                if not isinstance(gate, dict):
                    continue
                for key in (
                    "raw_predicate",
                    "conversion",
                    "true_means",
                    "predicate_kind",
                    "stats_basis",
                    "evidence",  # verbose; label+source+operator remain
                ):
                    gate.pop(key, None)
            # expr_interpretations duplicate normalized gates — keep a thin
            # deny/allow hint only (saves hundreds of chars under 15k budget).
            exprs = structured.get("expr_interpretations")
            if isinstance(exprs, list):
                thin: list[dict[str, Any]] = []
                for ex in exprs:
                    if not isinstance(ex, dict):
                        continue
                    thin.append(
                        {
                            k: ex[k]
                            for k in (
                                "raw_expr",
                                "true_means",
                                "action",
                            )
                            if k in ex and ex[k] is not None
                        }
                    )
                if thin:
                    structured["expr_interpretations"] = thin
                else:
                    structured.pop("expr_interpretations", None)
            notes = structured.get("active_notes")
            rtxt = goal.get("restriction_text")
            if (
                isinstance(notes, list)
                and rtxt
                and all(n == rtxt or (isinstance(n, str) and rtxt in n) for n in notes)
            ):
                structured.pop("active_notes", None)

    elig = payload.get("roster_eligibility")
    if isinstance(elig, dict):
        elig.pop("scope_note", None)

    deviations = payload.get("snapshot_deviations")
    if isinstance(deviations, dict):
        for key in (
            "hash_note",
            "advice_note",
            "source_priority",
            "hash_covers_note",
        ):
            deviations.pop(key, None)
        # Expected overrides are normal — keep count, drop verbose rows.
        overrides = deviations.get("expected_state_overrides")
        if isinstance(overrides, list) and overrides:
            deviations["expected_state_overrides_count"] = len(overrides)
            deviations.pop("expected_state_overrides", None)
        available = deviations.get("comparison_data_available")
        if isinstance(available, list) and available:
            deviations["comparison_data_available_count"] = len(available)
            deviations.pop("comparison_data_available", None)

    readiness = payload.get("readiness")
    if isinstance(readiness, dict):
        compact_issues = []
        for issue in readiness.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            compact_issues.append(
                {
                    k: issue[k]
                    for k in ("code", "severity", "affected_champion_ids")
                    if k in issue and issue[k] is not None
                }
            )
        if compact_issues:
            readiness["issues"] = compact_issues

    # uncertainty already consolidates classes; drop verbose per-item notes.
    uncertainty = payload.get("uncertainty")
    if isinstance(uncertainty, dict):
        items = []
        for row in uncertainty.get("items") or []:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    k: row[k]
                    for k in ("class", "blocks_advice", "blocks_only", "count")
                    if k in row and row[k] is not None
                }
            )
        if items:
            uncertainty["items"] = items

    swap = payload.get("swap")
    if isinstance(swap, dict):
        for row in swap.get("classification") or []:
            if isinstance(row, dict):
                row.pop("name", None)
                row.pop("reason", None)
                # eligibility already in roster_eligibility for owned set.
                row.pop("eligibility", None)
        excluded = swap.get("excluded")
        if isinstance(excluded, list) and excluded:
            swap["excluded_count"] = len(excluded)
            swap.pop("excluded", None)
        incomplete = swap.get("incomplete")
        if isinstance(incomplete, list) and incomplete:
            swap["incomplete_count"] = len(incomplete)
            swap.pop("incomplete", None)
        cov = swap.get("coverage")
        if isinstance(cov, dict):
            swap["coverage"] = {
                k: v for k, v in cov.items() if isinstance(v, (int, float, bool))
            }

    # answer_contract: drop display table block duplicated by markdown pointer.
    contract = payload.get("answer_contract")
    if isinstance(contract, dict):
        contract.pop("display_vs_import", None)

    # Flatten mechanics_completeness → compact top-level mechanics_delta / gaps.
    from ic_gamedata.formation_ai_advice.mechanics_completeness import (
        compact_mechanics_for_clipboard,
    )

    mech = compact_mechanics_for_clipboard(payload.get("mechanics_completeness"))
    payload.pop("mechanics_completeness", None)
    if isinstance(mech, dict):
        if mech.get("mechanics_delta"):
            payload["mechanics_delta"] = mech["mechanics_delta"]
            # Short priority flag instead of long prose.
            payload["mechanics_delta_priority"] = "delta>snapshot_shared; not_state_override"
        if mech.get("mechanic_gaps"):
            payload["mechanic_gaps"] = mech["mechanic_gaps"]

    # Shrink structure_example placements for budget (rules remain in contract).
    contract = payload.get("answer_contract")
    if isinstance(contract, dict):
        example = contract.get("structure_example")
        if isinstance(example, dict) and isinstance(example.get("json"), dict):
            body = example["json"]
            places = body.get("placements")
            if isinstance(places, list) and len(places) > 2:
                body["placements"] = places[:2]
            specs = body.get("specializations")
            if isinstance(specs, list) and len(specs) > 2:
                body["specializations"] = specs[:2]
        # full_after_normalize types are recoverable from schema_version.
        full = contract.get("full_after_normalize")
        if isinstance(full, dict):
            full.pop("assignments_item_types", None)
            full.pop("specialization_choice_types", None)

    return payload


def build_advice_request_clipboard_text(
    request: dict[str, Any],
    *,
    mode: InstructionMode = "project",
    loss_free_compact: bool = True,
    max_chars: int | None = DEFAULT_CHAR_BUDGET,
    raise_on_over_budget: bool = False,
) -> str:
    """Exact clipboard string for an advice request (count this string).

    When ``raise_on_over_budget`` is true and ``max_chars`` is set, raises
    ``AdviceRequestBudgetError`` instead of silently returning oversized text.
    Callers that only preview should leave raise_on_over_budget false and use
    ``evaluate_clipboard_budget``.
    """
    meta = request.get("meta") if isinstance(request.get("meta"), dict) else {}
    snap_ref = meta.get("snapshot_ref") if isinstance(meta.get("snapshot_ref"), dict) else {}
    snapshot_id = str(snap_ref.get("snapshot_id") or "?")
    payload = (
        compact_request_for_clipboard(request) if loss_free_compact else request
    )
    body = minify_json(payload)
    lines: list[str] = [
        "# Idle Champions — ADVICE_REQUEST",
        "",
        instruction_mode_assumption(mode),
        "",
        safety_instruction(snapshot_id),
        "",
    ]
    if mode == "standalone":
        swap = isinstance(payload.get("swap"), dict)
        lines.extend(_standalone_advice_rules(swap=swap))
        lines.append("")
    lines.extend([ADVICE_TABLE_FORMAT, ""])
    fname = snap_ref.get("expected_filename") or snapshot_expected_filename(snapshot_id)
    lines.extend(
        [
            f"snapshot_ref: `{snapshot_id}` · bestand `{fname}`",
            "",
            "```json",
            body,
            "```",
            "",
        ]
    )
    text = "\n".join(lines)
    if raise_on_over_budget and max_chars is not None:
        status = budget_status(text, int(max_chars))
        if not status.within_budget:
            sections = {
                "json_gegevens": body,
                "antwoordformaat_tabel": ADVICE_TABLE_FORMAT,
                "modus_en_veiligheid": "\n".join(
                    [instruction_mode_assumption(mode), safety_instruction(snapshot_id)]
                ),
            }
            top = section_sizes(sections)[:3]
            cause = "Grootste onderdelen: " + "; ".join(
                f"{s['name']}={s['chars']}" for s in top
            )
            raise AdviceRequestBudgetError(
                chars=status.chars,
                max_chars=status.max_chars,
                cause=cause,
            )
    return text


def build_base_snapshot_clipboard_text(snapshot: dict[str, Any]) -> str:
    """Markdown pack for optional copy; primary UX is save-to-file."""
    from ic_gamedata.formation_ai_advice.snapshot_export import (
        format_base_snapshot_markdown,
    )

    text = format_base_snapshot_markdown(snapshot)
    # Append explicit one-time note (not claiming AI receipt).
    extra = (
        "\nVoeg dit bestand eenmalig toe aan je AI-chat of projectbronnen. "
        "De app kan niet controleren of de AI het bestand heeft ontvangen "
        "of nog beschikbaar heeft.\n"
    )
    return text.rstrip() + "\n" + extra


def build_project_instructions_clipboard_text() -> str:
    return PROJECT_INSTRUCTIONS + "\n"


def advice_request_section_breakdown(request: dict[str, Any], *, mode: InstructionMode) -> list[dict[str, Any]]:
    """Size contributors for UI when over budget."""
    meta = request.get("meta") if isinstance(request.get("meta"), dict) else {}
    snap_ref = meta.get("snapshot_ref") if isinstance(meta.get("snapshot_ref"), dict) else {}
    snapshot_id = str(snap_ref.get("snapshot_id") or "?")
    body = minify_json(compact_request_for_clipboard(request))
    sections = {
        "modus_en_veiligheid": "\n".join(
            [
                instruction_mode_assumption(mode),
                safety_instruction(snapshot_id),
            ]
        ),
        "antwoordformaat_tabel": ADVICE_TABLE_FORMAT,
        "json_gegevens": body,
    }
    if mode == "standalone":
        sections["algemene_instructies"] = "\n".join(
            _standalone_advice_rules(swap=isinstance(request.get("swap"), dict))
        )
    return section_sizes(sections)


def build_champion_details_clipboard_text(
    details: dict[str, Any],
    *,
    part_index: int | None = None,
    part_total: int | None = None,
) -> str:
    meta = details.get("meta") if isinstance(details.get("meta"), dict) else {}
    snap_ref = meta.get("snapshot_ref") if isinstance(meta.get("snapshot_ref"), dict) else {}
    export_ref = (
        snap_ref.get("snapshot_id")
        or meta.get("request_id")
        or meta.get("created_at")
        or "champion_details"
    )
    coverage = details.get("coverage") if isinstance(details.get("coverage"), dict) else {}
    header = [
        "# Idle Champions — CHAMPION_DETAILS",
        "",
        f"export_ref: `{export_ref}`",
    ]
    if part_index is not None and part_total is not None:
        header.append(f"deel: {part_index}/{part_total}")
    header.extend(
        [
            f"gevraagd: {coverage.get('requested_count', '?')}",
            f"opgenomen: {coverage.get('included_count', '?')}",
            "",
            "```json",
            minify_json(details),
            "```",
            "",
        ]
    )
    return "\n".join(header)


def split_champion_details_for_budget(
    details: dict[str, Any],
    *,
    max_chars: int,
) -> list[str]:
    """Split into clipboard parts at champion boundaries only.

    Never cuts mid-JSON / mid-champion / mid-mechanic. Each part is a complete
    CHAMPION_DETAILS document with the same export_ref and part numbering.
    """
    champions = [
        c for c in (details.get("champions") or []) if isinstance(c, dict)
    ]
    if not champions:
        text = build_champion_details_clipboard_text(details)
        return [text]

    # Probe single-champion part size to know if even one champion overflows.
    parts_champs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    def _pack(chs: list[dict[str, Any]], *, index: int, total: int) -> str:
        chunk = copy.deepcopy(details)
        chunk["champions"] = chs
        cov = dict(chunk.get("coverage") or {})
        cov["included_count"] = len(chs)
        cov["requested_count"] = len(chs)
        cov["part_index"] = index
        cov["part_total"] = total
        chunk["coverage"] = cov
        meta = dict(chunk.get("meta") or {})
        meta["part_index"] = index
        meta["part_total"] = total
        chunk["meta"] = meta
        return build_champion_details_clipboard_text(
            chunk, part_index=index, part_total=total
        )

    # First assign champions to provisional groups using a conservative
    # estimate; then renumber once total is known.
    provisional: list[list[dict[str, Any]]] = []
    bucket: list[dict[str, Any]] = []
    for champ in champions:
        trial = bucket + [champ]
        # Temporary total=99 so header length is stable-ish; refined below.
        trial_text = _pack(trial, index=1, total=99)
        if count_chars(trial_text) <= max_chars or not bucket:
            bucket = trial
            # If a single champion alone exceeds budget, still emit as its own
            # part (caller must block or raise budget — we never slice JSON).
            if len(bucket) == 1 and count_chars(trial_text) > max_chars:
                provisional.append(bucket)
                bucket = []
        else:
            provisional.append(bucket)
            bucket = [champ]
    if bucket:
        provisional.append(bucket)

    total = len(provisional)
    return [
        _pack(group, index=i + 1, total=total)
        for i, group in enumerate(provisional)
    ]


def evaluate_clipboard_budget(
    text: str,
    *,
    max_chars: int,
    sections: dict[str, str] | None = None,
) -> dict[str, Any]:
    status = budget_status(text, max_chars)
    return {
        "chars": status.chars,
        "utf8_bytes": status.utf8_bytes,
        "max_chars": status.max_chars,
        "within_budget": status.within_budget,
        "over_by": status.over_by,
        "label": status.label,
        "sections": section_sizes(sections) if sections else None,
    }


def try_loss_free_shrink(text: str) -> str:
    """Apply only lossless whitespace/minify tweaks to an already-built string.

    Does not truncate, drop champions, or rewrite mechanics.
    """
    # Normalize newlines; strip trailing spaces on lines; keep content.
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    # Collapse runs of >2 blank lines to a single blank line.
    out: list[str] = []
    blank = 0
    for line in lines:
        if line.strip() == "":
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(line)
    return "\n".join(out).rstrip() + "\n"
