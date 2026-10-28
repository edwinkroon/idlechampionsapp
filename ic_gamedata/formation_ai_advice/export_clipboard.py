"""Clipboard text builders for export mode (BASE / REQUEST / DETAILS).

Preview, counters, and clipboard output must use the exact same string
returned by these builders — never re-format after counting.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from ic_gamedata.formation_ai_advice.export_budget import (
    DEFAULT_CHAR_BUDGET,
    MAX_EXPORT_BYTES,
    budget_status,
    count_chars,
    count_utf8_bytes,
    section_sizes,
)
from ic_gamedata.formation_ai_advice.labels import (
    POSITION_DISPLAY_AI_INSTRUCTION,
)
from ic_gamedata.formation_ai_advice.reply_contract import (
    reply_format_pointer_nl,
)
from ic_gamedata.formation_ai_advice.snapshot_export import minify_json

InstructionMode = Literal["project", "standalone"]

# Short pointer; full importer rules live in request JSON ``answer_contract``.
ADVICE_TABLE_FORMAT = reply_format_pointer_nl()

# Lead-in: execute advice now (not acknowledge / re-ask).
EXECUTION_ORDER_CLIPBOARD = (
    "Voer onderstaande ADVICE_REQUEST nu uit en geef een concreet formatie- "
    "en swapadvies volgens de verplichte antwoordvorm. Dit is een "
    "uitvoerverzoek, geen verzoek om alleen de aanvraag te controleren of "
    "de ontvangst van gegevens te bevestigen. Gebruik de vaste "
    "advieswerkwijze van dit project."
)

# Find BASE by filename then metadata; continue in the same answer.
BASE_LOOKUP_AND_CONTINUE = (
    "Lees eerst de basissnapshot uit de beschikbare projectbestanden. "
    "Zoek eerst op de opgegeven bestandsnaam. Als die niet wordt gevonden, "
    "bekijk dan de beschikbare JSON-bestanden en controleer hun metadata. "
    "De interne meta.snapshot_id bepaalt of het de bedoelde snapshot is; "
    "controleer ook de opgegeven mechanics_hash en account_state_hash. "
    "Een afwijkende bestandsnaam is op zichzelf geen reden om te stoppen. "
    "Een niet-overeenkomende snapshot_id of hash mag niet stilzwijgend "
    "worden genegeerd.\n"
    "\n"
    "Wanneer de juiste basissnapshot is gevonden en gelezen: ga in "
    "hetzelfde antwoord door met de inhoudelijke beoordeling. Lever het "
    "advies, de Swapafweging en het JSON-object volgens answer_contract. "
    "Stop niet na alleen een bevestiging dat het bestand is gevonden en "
    "vraag niet opnieuw of je de analyse moet uitvoeren.\n"
    "\n"
    "Alleen als de vereiste basissnapshot na controle echt ontbreekt, "
    "onleesbaar is of niet overeenkomt: meld de concrete blokkade en vraag "
    "gericht om de ontbrekende of juiste bron. Verzin geen mechanics of "
    "importschema en lever geen onveilig importeerbaar voorstel."
)

MISSING_COMPARISON_CONTINUE = (
    "Ontbrekende livewaarden, stacks of equipmentdetails beperken alleen "
    "de betreffende vergelijking. Ze zijn geen algemene stopreden zolang "
    "de benodigde mechanics, plaatsbaarheid en eligibility voldoende zijn "
    "vastgesteld. Gebruik waar verantwoord de classificatie "
    "‘waarschijnlijk sterker’ of ‘testvoorstel’, met concrete onzekerheid. "
    "Vraag niet opnieuw om toestemming om de gevraagde analyse uit te voeren."
)


class AdviceRequestBudgetError(ValueError):
    """Raised when a finished ADVICE_REQUEST clipboard export exceeds the limit."""

    def __init__(
        self,
        *,
        chars: int,
        max_chars: int,
        cause: str,
        utf8_bytes: int | None = None,
    ) -> None:
        self.chars = chars
        self.max_chars = max_chars
        self.utf8_bytes = utf8_bytes if utf8_bytes is not None else chars
        self.cause = cause
        super().__init__(
            f"ADVICE_REQUEST te groot: {self.utf8_bytes} UTF-8-bytes "
            f"(max {max_chars}). {cause}"
        )

# Swap-search workflow. Full text → project instructions; compact → clipboard (17k).
SWAP_SCOPE_TOKEN = "owned_roster_up_to_3_swap_search"

SWAP_ADVICE_WORKFLOW = f"""## Swapzoekopdracht ({SWAP_SCOPE_TOKEN})

Verplicht bij deze scope (research_mode=provided_data_only: geen webresearch; mechanics uit BASE_SNAPSHOT, niet herhalen):

1. Eerst: BASE_SNAPSHOT, actuele restricties, geometry, NPC/slot_states, champion-locks (must_remain/replacement/position), eligibility/beschikbaarheid.
2. Vergelijk twee routes: A) beste onderbouwde plaatsing met huidige champions; B) onderbouwd alternatief met ≤ max_swaps_per_proposal.
3. Beoordeel alle swap.included_candidate_ids op relevante doelbijdrage. Geen verborgen tierlist of willekeurige top-N. Filter alleen op expliciete beperkingen of inhoudelijk beschreven incompatibiliteit.
4. Onderzoek naast losse vervangingen ook samenhangende combinaties ≤3 swaps waar mechanics dat toelaten (andere DPS kan andere supports vragen). Claim geen uitputtende combinatoriek zonder die te hebben uitgevoerd.
5. Houd rekening met: permanente seats/seatconflicten; verplichte champions en locks; other_party_ids (owned ≠ beschikbaar); buffbereik op de voorgestelde actuele geometry; traits/rollen/plaatsingsafhankelijke deltas; specs en toegestane feats; overleving/opbouwtijd/doel; unknown live-state en companionposities.
6. Ontbrekende bufftotalen/stacks/equipment ≠ automatische swap-afwijzing. Kwalitatief vergelijken op betrouwbare mechanicbeschrijvingen; verzin geen multipliers of gegarandeerde winst. {MISSING_COMPARISON_CONTINUE}
7. Classificeer: onderbouwde verbetering (wat aantoonbaar verbetert) | waarschijnlijk sterker (bepalende onzekerheid) | testvoorstel (benodigde waarneming). Betere deelbijdrage ≠ bewezen hogere totale BUD.
8. Adviseer geen swap alleen om deze werkwijze te vervullen. Bij behoud van de huidige champions: noem kort welke relevante alternatieven/combinaties zijn vergeleken en waarom die niet overtuigen.
9. Bij blokkerende bronconflicten: alleen daarvan afhankelijke conclusies blokkeren; omzeil geen eligibility, locks of NPC-blokkades; geen importeerbaar voorstel dat veiligheidsvoorwaarden schendt.

Na de formatietabel: compacte sectie «Swapafweging» — Advies: 0/1/2/3 swaps; bij swaps wie eruit/erin + waarom; belangrijkste onderzochte alternatieven of combinaties; waarom dit de voorkeur heeft boven alleen herschikken; ontbrekende gegevens die de keuze nog kunnen veranderen. Geen fictieve kandidaten. «Geen bewezen optimum» vervangt de swapvergelijking niet.

Antwoordvorm blijft: tabel (Plek/Champion/Specialisatie(s)) → korte uitleg/Swapafweging → precies één JSON volgens BASE_SNAPSHOT.answer_contract (één voorstel; technische position_id’s; exacte request_id). Bij geblokkeerd antwoord: bestaand answer_contract volgen."""

SWAP_ADVICE_WORKFLOW_CLIPBOARD = f"""## Swapzoekopdracht ({SWAP_SCOPE_TOKEN})
Verplicht (provided_data_only: geen webresearch; mechanics in BASE, niet herhalen):
1) Eerst BASE, restricties, geometry, NPC/slot_states, locks, eligibility.
2) Vergelijk A huidige party vs B ≤max_swaps_per_proposal.
3) Beoordeel alle included_candidate_ids; geen tierlist/top-N; filter alleen op expliciete beperkingen/beschreven incompatibiliteit.
4) Ook combinaties ≤3 swaps waar passend; geen claim van uitputtende zoekactie.
5) Seats/locks; other_party_ids≠beschikbaar; buffbereik; traits/specs/feats; overleving/doel; unknown live/companions.
6) Ontbrekende stacks/equipment ≠ swap afwijzen; geen verzonnen multipliers/winst. {MISSING_COMPARISON_CONTINUE}
7) Classificeer: onderbouwd | waarschijnlijk sterker (+onzekerheid) | testvoorstel. Deelbijdrage≠hogere BUD.
8) Geen cosmetische swap; bij behoud: noem vergeleken alternatieven + waarom niet.
9) Bronconflicten: geen omzeilen van eligibility/locks/NPC; geen onveilig importeerbaar voorstel.
Na tabel: «Swapafweging» (0–3 swaps; eruit/erin; onderzochte alternatieven; vs herschikken; ontbrekende data; geen fictie). Eén JSON/voorstel per answer_contract."""


PROJECT_INSTRUCTIONS = """# Idle Champions — vaste projectinstructies (formatieadvies)

Gebruik deze regels bij adviesvragen die naar een BASE_SNAPSHOT verwijzen.

- Pas actuele toestand uit ADVICE_REQUEST toe vóór vergelijking en advies.
- BASE_SNAPSHOT = mechanics, vaste championgegevens, answer_contract, standaard geometry-layout, goal_catalog; ADVICE_REQUEST = actuele veranderlijke toestand (party, bezetting, specs, ontgrendelstatus, live stacks/fase, eligibility, slot_states/plaatsbaarheid) en overschrijft die velden. Wijkt de actuele formatielayout af, dan bevat ADVICE_REQUEST.geometry de volledige actuele layout (positions, adjacency, richtingen) die de snapshot-layout als geheel overschrijft; actuele occupied blijft de champion-bezettingsbron.
- geometry.valid_position_ids = volledige technische layout (inclusief escort/NPC-seats). Plaatsbaarheid staat in geometry.slot_states. available_position_ids = alleen bevestigd lege, plaatsbare plekken — niet afleiden uit len(valid_position_ids) − len(party). Ontbrekende slot_states betekent niet dat ongebruikte posities vrij zijn.
- Plaats geen champions op placeability=blocked (npc/escort/object). Bij placeability=unknown: geen nieuwe championplaatsing; status needs_information tenzij de bron expliciet bevestigt.
- NPC/escorts zijn geen party-champions en geen champion-swaps; verzin geen champion_id voor een NPC.
- Actuele slot_states horen altijd in ADVICE_REQUEST (ook bij layout_matches_base). geometry.ref hergebruikt alleen structurele layout — geen oude bezetting of plaatsbaarheid.
- Een compacte geometry.ref naar BASE_SNAPSHOT.geometry is alleen geldig wanneer de exporter layout_matches_base heeft vastgesteld (structurele layoutgelijkheid; alleen dezelfde valid_position_ids is onvoldoende).
- Verschillen met oudere snapshotselecties, ontgrendelstatus of formatielayout zijn normale overrides (expected_state_override), geen conflicten — meld ze niet als waarschuwing.
- Meld alleen materiële, onopgeloste tegenstrijdigheden (material_source_conflict).
- Meld ontbrekende vergelijkingsgegevens (missing_comparison_data) apart en beperk die onzekerheid tot de betreffende vergelijking; overig advies dat door beschikbare gegevens gedragen wordt blijft staan.
- Ontbrekende/unknown actuele waarden niet stilzwijgend invullen met oude snapshotwaarden.
- Huidige selectie bekend ≠ beste keuze aantoonbaar bepaald; geen bewezen optimale ranking zonder de benodigde gegevens.
- Maximaal één champion per permanente seat.
- Voorstellen met championwissels zijn onderling onafhankelijk (ieder start vanaf dezelfde baseline-party), tenzij de aanvraag anders zegt.
- Geen automatische hoofd-DPS-lock: alleen een expliciet vastgezette hoofd-DPS is locked.
- Vergelijk kandidaten met een goed herplaatste baseline (niet alleen “nieuwe champion erin”).
- Feat-verbetervoorstellen mogen (constraints.may_change_feats=true); wijzig geen equipment tenzij de aanvraag dat expliciet toestaat.
- party[].active_feat_ids = compacte actieve feat-IDs; party[].active_feats = id/naam/effect. effect mag bij budgetdruk weg (ids blijven). feats_status=unknown ≠ geen feats.
- bud_observation: reset_highest_damage_champion_id ≠ current BUD setter; current_bud/peak unknown zonder meter/poll-loop.
- main_dps_buffs: cat+ref = BASE_SNAPSHOT catalogus (upgrade/option/feat-id); effect_def_id = effect_defines. reach≠activation; computed in_range ≠ runtime active. Budget: pri A/B (hoofdbuffs/conds) vóór D/E.
- live_diagnostics: bekende livewaarde mét bron, of unknown+reason_code; mechanic-ref ≠ gemeten stack/waarde.
- roster_eligibility.presence_conflicts: static deny vs formatie-aanwezigheid (aanwezigheid ≠ toelating); required/force_allow ≠ position lock. party must_remain/replacement_locked ≠ automatisch position_locked; force_slot/slot_id = NPC-overlay tenzij apart bewezen.
- Verzin geen schadewinst of damage-multipliers; itemlevels zijn geen vermenigvuldigers.
- Lever complete eindformaties met geldige specialisaties (echte keuzegroepen/prerequisites).
- Benoem expliciete onzekerheid en dekkingsbeperkingen; claim geen bewezen optimum zonder bewijs.
- Leid ontbrekende mechanics of gender niet af uit championnamen, flavor of herinnering.
- Permanent seat ≠ fysieke positie.
- research_mode=provided_data_only: geen externe research. provided_data_plus_targeted_research: alleen ontbrekende openbare rules/mechanics uit research_gaps; citeer bronnen; scheid feiten/aanvullingen/aannames; unknown≠allowed; actuele account/geometry/slot_states/spelblokkades blijven leidend.
- Bij meta.scope=""" + SWAP_SCOPE_TOKEN + """ of aanwezig swap-blok: volg de swapzoekopdracht hieronder — niet standaard alleen herschikken.
- """ + POSITION_DISPLAY_AI_INSTRUCTION + """

""" + ADVICE_TABLE_FORMAT + """

""" + SWAP_ADVICE_WORKFLOW


def _filename_clause(expected_filename: str | None) -> str:
    """Readable filename hint; never invent ``{snapshot_id}.json``."""
    name = (expected_filename or "").strip()
    if name:
        return f"zoekhulp-bestand `{name}`"
    return (
        "bestandsnaam onbekend (legacy) — zoek via snapshot_id en hashes "
        "in JSON-metadata"
    )


def safety_instruction(
    snapshot_id: str,
    *,
    expected_filename: str | None = None,
) -> str:
    sid = snapshot_id.strip() or "?"
    file_bit = _filename_clause(expected_filename)
    return (
        f"snapshot_ref wijst naar basissnapshot `{sid}` ({file_bit}); "
        "dit verzoek bevat die inhoud niet. "
        f"{BASE_LOOKUP_AND_CONTINUE} "
        "ADVICE_REQUEST overschrijft veranderlijke snapshottoestand; een "
        "volledige actuele geometry overschrijft de snapshot-layout als geheel. "
        "Actuele slot_states (NPC/escort-blokkades, placeability) altijd uit "
        "ADVICE_REQUEST gebruiken — ook bij geometry.ref/layout_matches_base. "
        "geometry.ref alleen gebruiken bij layout_matches_base. "
        "available_position_ids = bevestigd vrij; ontbrekende slot_states ≠ vrij. "
        "Expected overrides ≠ bronconflicten. "
        "Leid ontbrekende mechanics/gender niet af uit namen of herinnering."
    )


# Compact project-mode pointer (once per ADVICE_REQUEST). Full workflow stays
# in PROJECT_INSTRUCTIONS / the Cursor project — do not re-embed it here.
TEST_FOCUSED_ADVICE_POINTER = (
    "Volg de vaste projectinstructies voor testgericht advies. "
    "Bij een bekend knelpunt: kies een concrete, onderbouwde eerste test; "
    "adviseer niet automatisch behoud vanwege ontbrekende livewaarden. "
    "Onzekerheid is geen bewijs van winst. Respecteer altijd eligibility, "
    "seatconflicten, locks en NPC-/escortblokkades."
)


def instruction_mode_assumption(mode: InstructionMode) -> str:
    if mode == "project":
        # Keep lean: TEST_FOCUSED_ADVICE_POINTER carries the project-workflow cue.
        return (
            "Modus: Voor mijn project — korte instructies. "
            "Basis-snapshotreferentie en veiligheidsvoorwaarden blijven aanwezig."
        )
    return (
        "Modus: Zelfstandig — algemene adviesinstructies zijn bijgevoegd. "
        "Het genoemde basisbestand blijft nodig voor mechanics "
        "(niet volledig zelfstandig zonder bijlagen)."
    )


def _request_has_swap_scope(payload: dict[str, Any] | None) -> bool:
    """True when the request asks for owned-roster swap search."""
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("swap"), dict):
        return True
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    scope = str(meta.get("scope") or "").strip().casefold()
    if SWAP_SCOPE_TOKEN.casefold() in scope or "swap_search" in scope:
        return True
    # Budget shrink may drop the swap object; keep workflow if scope/max_swaps remain.
    constraints = (
        payload.get("constraints")
        if isinstance(payload.get("constraints"), dict)
        else {}
    )
    return bool(
        constraints.get("may_replace_champions")
        and constraints.get("max_swaps_per_proposal") is not None
        and "swap" in scope
    )


def _standalone_advice_rules(*, swap: bool) -> list[str]:
    lines = [
        "Je bent een Idle Champions-formatieadviseur.",
        "Dit is een game-adviesaanvraag, geen programmeer- of exportreviewtaak.",
        "",
    ]
    if swap:
        lines.append(SWAP_ADVICE_WORKFLOW_CLIPBOARD)
        lines.append("")
        lines.extend(
            [
                "Voorstellen met wissels zijn onderling onafhankelijk "
                "(ieder vanaf dezelfde baseline-party).",
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
            "- Feat-verbetervoorstellen mogen; wijzig geen equipment tenzij "
            "expliciet toegestaan.",
            "- Geen verzonnen schadewinst.",
            "- Complete eindformaties en geldige specialisaties.",
            "- Expliciete onzekerheid en dekkingsbeperkingen.",
            "- research_mode=provided_data_only: geen webresearch.",
        ]
    )
    return lines


def _group_flat_eligibility_rows(
    rows: list[Any],
) -> list[dict[str, Any]]:
    """Collapse ``[{id, reason}, ...]`` into ``[{reason, ids}, ...]``."""
    buckets: dict[str, list[int]] = {}
    order: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hid = row.get("id")
        if not isinstance(hid, int):
            continue
        reason = str(row.get("reason") or "unspecified")
        if reason not in buckets:
            buckets[reason] = []
            order.append(reason)
        buckets[reason].append(hid)
    return [
        {"reason": reason, "ids": sorted(set(buckets[reason]))}
        for reason in order
    ]


def _shrink_eligibility_for_export(elig: dict[str, Any]) -> None:
    """Drop bulky flat denied/unknown/availability forms (budget-critical)."""
    for flat_key, group_key in (
        ("denied", "denied_groups"),
        ("unknown", "unknown_groups"),
    ):
        flat = elig.get(flat_key)
        if not isinstance(flat, list) or not flat:
            elig.pop(flat_key, None)
            continue
        grouped = _group_flat_eligibility_rows(flat)
        existing = elig.get(group_key)
        if isinstance(existing, list) and existing:
            # Prefer already-grouped form; drop legacy flat duplicate.
            elig.pop(flat_key, None)
            continue
        if grouped:
            elig[group_key] = grouped
        elig.pop(flat_key, None)

    avail = elig.get("practical_availability")
    if isinstance(avail, list) and avail:
        # Notes are repetitive prose; keep ids + status (+ instance).
        thin: list[dict[str, Any]] = []
        for row in avail:
            if not isinstance(row, dict):
                continue
            item = {
                k: row[k]
                for k in ("id", "status", "game_instance_id")
                if k in row and row[k] is not None
            }
            if item.get("id") is not None:
                thin.append(item)
        if thin:
            elig["practical_availability"] = thin
        else:
            elig.pop("practical_availability", None)

    overrides = elig.get("overrides_applied")
    if isinstance(overrides, list) and overrides:
        thin_ov: list[dict[str, Any]] = []
        for row in overrides:
            if not isinstance(row, dict):
                continue
            thin_ov.append(
                {
                    k: row[k]
                    for k in ("champion_id", "base", "effective", "reason")
                    if k in row and row[k] is not None
                }
            )
        if thin_ov:
            elig["overrides_applied"] = thin_ov
        else:
            elig.pop("overrides_applied", None)


def _compact_slot_states_for_export(geometry: dict[str, Any]) -> None:
    """Shrink slot_states in place for clipboard budget (enums stay authoritative)."""
    states = geometry.get("slot_states")
    if not isinstance(states, list) or not states:
        return
    thin: list[dict[str, Any]] = []
    for row in states:
        if not isinstance(row, dict):
            continue
        out: dict[str, Any] = {
            k: row[k]
            for k in (
                "position_id",
                "display_position",
                "occupancy",
                "placeability",
            )
            if k in row and row[k] is not None
        }
        blocker = row.get("blocker")
        if isinstance(blocker, dict):
            thin_blocker = {
                k: blocker[k]
                for k in ("type", "name", "graphic_id")
                if k in blocker and blocker[k] is not None
            }
            if thin_blocker:
                out["blocker"] = thin_blocker
        # Keep reason only when placeability/occupancy alone is ambiguous.
        occ = str(out.get("occupancy") or "")
        place = str(out.get("placeability") or "")
        if place == "unknown" or occ == "unknown" or row.get("conflict"):
            if row.get("reason"):
                out["reason"] = row["reason"]
            if row.get("conflict"):
                out["conflict"] = row["conflict"]
        thin.append(out)
    geometry["slot_states"] = thin


def request_for_export(request: dict[str, Any]) -> dict[str, Any]:
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

    # bronregels + live_state_defaults duplicate safety/project instructions
    # and per-champion live_state posture already present on party rows.
    payload.pop("bronregels", None)
    payload.pop("live_state_defaults", None)

    meta = payload.get("meta")
    if isinstance(meta, dict):
        validation = meta.get("validation")
        if isinstance(validation, dict):
            validation.pop("field_meanings", None)
            # Codes + ids suffice on clipboard; long Dutch messages/notes bloat.
            validation.pop("note", None)
            for key in ("issues", "warnings"):
                rows = validation.get(key)
                if not isinstance(rows, list):
                    continue
                thin_rows: list[dict[str, Any]] = []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    thin_rows.append(
                        {
                            k: row[k]
                            for k in (
                                "code",
                                "severity",
                                "ids",
                                "affected_champion_ids",
                            )
                            if k in row and row[k] is not None
                        }
                    )
                if thin_rows:
                    validation[key] = thin_rows
                else:
                    validation.pop(key, None)

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
        # Slot states: keep machine enums + thin blocker; drop long reason/source
        # when occupancy/placeability already encode the block.
        _compact_slot_states_for_export(geometry)

    goal = payload.get("goal")
    if isinstance(goal, dict):
        # Observed Modron is advisory context — keep ids/sources, drop note prose.
        observed = goal.get("observed_modron")
        if isinstance(observed, dict):
            observed.pop("note", None)
            if observed.get("reset_area") is None:
                goal.pop("observed_modron", None)
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
            # expr_interpretations: keep thin deny/allow hints, but preserve
            # unevaluable predicate audit (rule_ref/raw/source) for research_gaps.
            exprs = structured.get("expr_interpretations")
            if isinstance(exprs, list):
                thin: list[dict[str, Any]] = []
                for ex in exprs:
                    if not isinstance(ex, dict):
                        continue
                    if ex.get("source") in {
                        "unhandled_predicate",
                        "by_attack_types",
                        "by_seat",
                    } or ex.get("rule_ref") or ex.get("raw") is not None:
                        thin.append(
                            {
                                k: ex[k]
                                for k in (
                                    "source",
                                    "change_type",
                                    "source_field",
                                    "rule_ref",
                                    "action",
                                    "raw",
                                    "attack_types",
                                    "seats",
                                    "evidence",
                                )
                                if k in ex and ex[k] is not None
                            }
                        )
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
            # unevaluable_rules stays: compact, one row per predicate (do not invent).
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
        _shrink_eligibility_for_export(elig)
        # Presence conflicts: codes + lock flags; drop prose notes.
        conflicts = elig.get("presence_conflicts")
        if isinstance(conflicts, list) and conflicts:
            elig["presence_conflicts"] = [
                {
                    k: c[k]
                    for k in (
                        "champion_id",
                        "conflict",
                        "status",
                        "resolution",
                        "replacement_locked",
                        "must_remain_in_party",
                        "position_locked",
                        "locked_position_id",
                        "base_reason",
                    )
                    if isinstance(c, dict) and k in c and c[k] is not None
                }
                for c in conflicts
                if isinstance(c, dict)
            ]

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

    # Party: keep short names (readability); drop redundant live/trait prose.
    # Gender and champion identity live on BASE_SNAPSHOT.champions / roster.
    for member in payload.get("party") or []:
        if not isinstance(member, dict):
            continue
        live = member.get("live_state")
        if isinstance(live, dict):
            live.pop("note", None)
        # Compact key_champion provenance (booleans + locked_position_id remain).
        prov = member.get("lock_provenance")
        if isinstance(prov, dict):
            member["lock_provenance"] = {
                k: prov[k]
                for k in (
                    "kind",
                    "by_tags",
                    "by_seat",
                    "hero_ids",
                    "force_slot",
                    "slot_id",
                )
                if k in prov and prov[k] is not None
            } or None
        delta = member.get("trait_delta_vs_base")
        if isinstance(delta, dict):
            delta.pop("note", None)
            # Drop unchanged base/effective pairs (delta only needs diffs).
            for base_k, eff_k in (
                ("base_alignment", "effective_alignment"),
                ("base_roles", "effective_roles"),
                ("base_tags", "effective_tags"),
            ):
                if (
                    base_k in delta
                    and eff_k in delta
                    and delta[base_k] == delta[eff_k]
                ):
                    delta.pop(base_k, None)
                    delta.pop(eff_k, None)
            # Placement flags alone are useless without a remaining trait diff.
            if not any(k.startswith(("base_", "effective_")) for k in delta):
                member.pop("trait_delta_vs_base", None)

    # BUD / buff diagnostics: drop explanatory prose; keep statuses + ids.
    bud = payload.get("bud_observation")
    if isinstance(bud, dict):
        bud.pop("note", None)
    buffs = payload.get("main_dps_buffs")
    if isinstance(buffs, dict):
        buffs.pop("note", None)
        # Keep short defaults_mean; drop long priority_order labels under export.
        buffs.pop("priority_order", None)
        # Unresolved catalog: compact unique (cat, ref, reason) only.
        urefs = buffs.get("unresolved_catalog")
        if isinstance(urefs, list) and urefs:
            seen: set[tuple[Any, ...]] = set()
            compact_u: list[dict[str, Any]] = []
            for r in urefs:
                if not isinstance(r, dict):
                    continue
                key = (r.get("cat"), r.get("ref"), r.get("reason"))
                if key in seen:
                    continue
                seen.add(key)
                compact_u.append(
                    {
                        k: r[k]
                        for k in ("cat", "ref", "reason")
                        if k in r and r[k] is not None
                    }
                )
            buffs["unresolved_catalog"] = compact_u or None
        # Drop bulky counting prose from completeness (codes remain).
        completeness = buffs.get("completeness")
        if isinstance(completeness, dict):
            completeness.pop("counting", None)

    live = payload.get("live_diagnostics")
    if isinstance(live, dict):
        live.pop("note", None)
        champs = []
        for row in live.get("champions") or []:
            if not isinstance(row, dict):
                continue
            fields = []
            for f in row.get("fields") or []:
                if not isinstance(f, dict):
                    continue
                fields.append(
                    {
                        k: f[k]
                        for k in (
                            "key",
                            "status",
                            "value",
                            "value_kind",
                            "source",
                            "reason_code",
                        )
                        if k in f and f[k] is not None
                    }
                )
            thin_champ = {
                k: v
                for k, v in {
                    "id": row.get("id"),
                    "fields": fields or None,
                }.items()
                if v is not None
            }
            if thin_champ:
                champs.append(thin_champ)
        live["champions"] = champs or None

    # Prefer compact feat ids on clipboard when both are present.
    for member in payload.get("party") or []:
        if not isinstance(member, dict):
            continue
        ids = member.get("active_feat_ids")
        feats = member.get("active_feats")
        if isinstance(ids, list) and isinstance(feats, list) and feats:
            member.pop("active_feats", None)

    # comparison_traits.gender duplicates BASE_SNAPSHOT.champions[].gender.
    comparison = payload.get("comparison_traits")
    if isinstance(comparison, dict):
        comparison.pop("gender", None)
        comparison.pop("layer_note", None)
        # Keep required_tags only when non-empty; else drop the block.
        tags = comparison.get("required_tags")
        if isinstance(tags, list) and tags:
            payload["comparison_traits"] = {"required_tags": tags}
        else:
            payload.pop("comparison_traits", None)

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

    # answer_contract on the request is already a thin BASE_SNAPSHOT ref.
    # Flatten mechanics_completeness → compact top-level mechanics_delta / gaps.
    from ic_gamedata.formation_ai_advice.mechanics_completeness import (
        compact_mechanics_for_clipboard,
    )

    raw_mech = payload.get("mechanics_completeness")
    base_cov = None
    if isinstance(raw_mech, dict):
        base_cov = raw_mech.get("base_mechanics_export_coverage")
    mech = compact_mechanics_for_clipboard(raw_mech)
    payload.pop("mechanics_completeness", None)
    if isinstance(mech, dict):
        if mech.get("mechanics_delta"):
            payload["mechanics_delta"] = mech["mechanics_delta"]
            # Short priority flag instead of long prose.
            payload["mechanics_delta_priority"] = "delta>snapshot_shared; not_state_override"
        if mech.get("mechanic_gaps"):
            payload["mechanic_gaps"] = mech["mechanic_gaps"]
        if mech.get("mechanic_gap_ids"):
            payload["mechanic_gap_ids"] = mech["mechanic_gap_ids"]
        if mech.get("mechanic_gaps_note"):
            payload["mechanic_gaps_note"] = mech["mechanic_gaps_note"]
    # Compact coverage proof — needed so budget omission cannot claim BASE
    # has mechanics when the export was empty.
    if isinstance(base_cov, dict):
        payload["base_mechanics_export_coverage"] = {
            k: base_cov[k]
            for k in (
                "export_complete",
                "usable_for_qualitative_advice",
                "reason",
                "ability_with_effect",
                "option_with_effect",
                "option_missing_effect",
                "champion_count",
            )
            if k in base_cov and base_cov[k] is not None
        }

    return payload


def _render_advice_request_clipboard(
    payload: dict[str, Any],
    *,
    mode: InstructionMode,
    snapshot_id: str,
    expected_filename: str | None,
) -> str:
    body = minify_json(payload)
    swap = _request_has_swap_scope(payload)
    lines: list[str] = [
        "# Idle Champions — ADVICE_REQUEST",
        "",
        EXECUTION_ORDER_CLIPBOARD,
        "",
        instruction_mode_assumption(mode),
        "",
    ]
    if mode == "project":
        # Exactly once: short pointer — not the full PROJECT_INSTRUCTIONS body.
        lines.extend([TEST_FOCUSED_ADVICE_POINTER, ""])
    lines.extend(
        [
            safety_instruction(snapshot_id, expected_filename=expected_filename),
            "",
        ]
    )
    if mode == "standalone":
        lines.extend(_standalone_advice_rules(swap=swap))
        lines.append("")
    elif swap:
        # Project mode assumes fixed rules exist, but still embed the compact
        # swap workflow so partijsetup-copy cannot silently skip swap search.
        lines.extend(
            [
                SWAP_ADVICE_WORKFLOW_CLIPBOARD,
                "",
            ]
        )
    lines.extend([ADVICE_TABLE_FORMAT, ""])
    fname = (expected_filename or "").strip()
    if fname:
        ref_line = f"snapshot_ref: `{snapshot_id}` · bestand `{fname}`"
    else:
        ref_line = (
            f"snapshot_ref: `{snapshot_id}` · bestand onbekend "
            "(zoek via snapshot_id + mechanics_hash/account_state_hash)"
        )
    lines.extend(
        [
            ref_line,
            "",
            "```json",
            body,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _clipboard_utf8_bytes(
    payload: dict[str, Any],
    *,
    mode: InstructionMode,
    snapshot_id: str,
    expected_filename: str | None,
) -> int:
    return count_utf8_bytes(
        _render_advice_request_clipboard(
            payload,
            mode=mode,
            snapshot_id=snapshot_id,
            expected_filename=expected_filename,
        )
    )


def _clipboard_chars(
    payload: dict[str, Any],
    *,
    mode: InstructionMode,
    snapshot_id: str,
    expected_filename: str | None,
) -> int:
    """Code-point count (diagnostics); budget gate uses ``_clipboard_utf8_bytes``."""
    return count_chars(
        _render_advice_request_clipboard(
            payload,
            mode=mode,
            snapshot_id=snapshot_id,
            expected_filename=expected_filename,
        )
    )


def _thin_mechanics_delta_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """Thin only deltas BASE already covers — never strip essential supplements."""
    from ic_gamedata.formation_ai_advice.mechanics_completeness import (
        delta_row_is_essential_for_request,
    )

    thin_delta: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if delta_row_is_essential_for_request(row):
            # Keep full effect — BASE lacks usable prose for this id.
            thin_delta.append(dict(row))
            continue
        thin = {
            k: row[k]
            for k in ("catalog", "id", "role", "snapshot_had_effect")
            if k in row and row[k] is not None
        }
        thin["effect_omitted_for_budget"] = True
        thin_delta.append(thin)
    return thin_delta


def _fits(
    payload: dict[str, Any],
    *,
    mode: InstructionMode,
    snapshot_id: str,
    expected_filename: str | None,
    max_chars: int,
) -> bool:
    """True when the full clipboard UTF-8 byte size is within ``max_chars``."""
    return (
        _clipboard_utf8_bytes(
            payload,
            mode=mode,
            snapshot_id=snapshot_id,
            expected_filename=expected_filename,
        )
        <= max_chars
    )


def _fit_payload_to_budget(
    payload: dict[str, Any],
    *,
    mode: InstructionMode,
    snapshot_id: str,
    expected_filename: str | None,
    max_chars: int,
) -> dict[str, Any]:
    """Shrink request payload until clipboard fits (never mid-cut effect prose)."""
    working = dict(payload)
    kw = {
        "mode": mode,
        "snapshot_id": snapshot_id,
        "expected_filename": expected_filename,
        "max_chars": max_chars,
    }
    if _fits(working, **kw):
        return working

    from ic_gamedata.formation_ai_advice.mechanics_completeness import (
        delta_row_is_essential_for_request,
    )

    # 1) Strip mechanic effect prose only where BASE already has usable effect.
    if working.get("mechanics_delta"):
        trial = dict(working)
        trial["mechanics_delta"] = _thin_mechanics_delta_rows(
            list(working.get("mechanics_delta") or [])
        ) or None
        trial["mechanics_delta_priority"] = (
            trial.get("mechanics_delta_priority")
            or "delta>snapshot_shared; not_state_override"
        )
        trial.pop("mechanic_gaps", None)
        working = trial
        if _fits(working, **kw):
            return working

    # 2) Collapse practical_availability to id list.
    elig = working.get("roster_eligibility")
    if isinstance(elig, dict) and isinstance(elig.get("practical_availability"), list):
        ids = [
            int(row["id"])
            for row in elig["practical_availability"]
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        ]
        trial = dict(working)
        trial_elig = dict(elig)
        trial_elig.pop("practical_availability", None)
        if ids:
            trial_elig["other_party_ids"] = sorted(set(ids))
        trial["roster_eligibility"] = trial_elig
        working = trial
        if _fits(working, **kw):
            return working

    # 3) Drop only non-essential mechanics_delta rows (BASE already covers them).
    #    Essential supplements/corrections stay — never claim BASE has them.
    if working.get("mechanics_delta") or working.get("mechanic_gap_ids"):
        rows = [
            r for r in (working.get("mechanics_delta") or []) if isinstance(r, dict)
        ]
        essential = [r for r in rows if delta_row_is_essential_for_request(r)]
        redundant = [r for r in rows if not delta_row_is_essential_for_request(r)]
        trial = dict(working)
        if essential:
            trial["mechanics_delta"] = essential
            trial["mechanics_delta_priority"] = (
                "delta>snapshot_shared; essential_supplements_kept"
            )
            if redundant:
                trial["mechanics_delta_redundant_omitted_for_budget"] = True
                trial["mechanics_delta_redundant_omitted_count"] = len(redundant)
            trial.pop("mechanic_gaps", None)
            trial.pop("mechanic_gaps_note", None)
            trial.pop("mechanic_gap_ids", None)
            # Do not set mechanics_delta_omitted_for_budget — essential remain.
        else:
            n = len(rows)
            trial.pop("mechanics_delta", None)
            trial.pop("mechanic_gaps", None)
            trial.pop("mechanic_gaps_note", None)
            trial.pop("mechanic_gap_ids", None)
            trial["mechanics_delta_omitted_for_budget"] = True
            trial["mechanics_delta_omitted_count"] = n or None
            trial["mechanics_delta_priority"] = (
                "delta_omitted_use_BASE_SNAPSHOT; refresh_base_if_stale"
            )
        working = trial
        if _fits(working, **kw):
            return working

    # 4) Swap: keep only includable candidate ids (drop per-row prose).
    swap = working.get("swap")
    if isinstance(swap, dict) and isinstance(swap.get("classification"), list):
        trial = dict(working)
        trial_swap = dict(swap)
        included = [
            int(row["champion_id"])
            for row in (swap.get("classification") or [])
            if isinstance(row, dict)
            and isinstance(row.get("champion_id"), int)
            and str(row.get("classification") or "").startswith("included")
        ]
        trial_swap.pop("classification", None)
        trial_swap["included_candidate_ids"] = sorted(set(included)) or None
        trial["swap"] = trial_swap
        working = trial
        if _fits(working, **kw):
            return working

    # 5) Eligibility: ids only (no reason strings).
    elig = working.get("roster_eligibility")
    if isinstance(elig, dict):
        trial = dict(working)
        trial_elig = dict(elig)
        for group_key, ids_key in (
            ("denied_groups", "denied_ids"),
            ("unknown_groups", "unknown_ids"),
        ):
            groups = trial_elig.get(group_key)
            if not isinstance(groups, list) or not groups:
                continue
            ids = []
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for hid in group.get("ids") or []:
                    if isinstance(hid, int):
                        ids.append(hid)
            trial_elig.pop(group_key, None)
            if ids:
                trial_elig[ids_key] = sorted(set(ids))
        # Keep presence_conflicts (required/banned vs seated); drop bulky overrides.
        conflicts = trial_elig.get("presence_conflicts")
        trial_elig.pop("overrides_applied", None)
        trial_elig.pop("availability_note", None)
        if isinstance(conflicts, list) and conflicts:
            trial_elig["presence_conflicts"] = [
                {
                    k: c[k]
                    for k in (
                        "champion_id",
                        "conflict",
                        "status",
                        "resolution",
                        "replacement_locked",
                        "must_remain_in_party",
                        "position_locked",
                        "locked_position_id",
                        "base_reason",
                    )
                    if isinstance(c, dict) and k in c and c[k] is not None
                }
                for c in conflicts
                if isinstance(c, dict)
            ]
        trial["roster_eligibility"] = trial_elig
        working = trial
        if _fits(working, **kw):
            return working

    # 6) Drop non-essential request chrome (still over by a few hundred).
    # Keep live_diagnostics + presence_conflicts (protected diagnostics).
    trial = dict(working)
    trial.pop("uncertainty", None)
    trial.pop("snapshot_deviations", None)
    trial.pop("companion_state", None)
    trial.pop("comparison_traits", None)
    trial.pop("live_state_defaults", None)
    readiness = trial.get("readiness")
    if isinstance(readiness, dict):
        # Keep compact eligibility conflict issue codes when present.
        thin_issues = []
        for iss in readiness.get("issues") or []:
            if not isinstance(iss, dict):
                continue
            if iss.get("code") == "eligibility_presence_conflict":
                thin_issues.append(
                    {
                        k: iss[k]
                        for k in ("code", "severity", "dimension")
                        if k in iss and iss[k] is not None
                    }
                )
        thin_ready: dict[str, Any] = {
            k: readiness[k]
            for k in ("status",)
            if k in readiness and readiness[k] is not None
        }
        if thin_issues:
            thin_ready["issues"] = thin_issues
        trial["readiness"] = thin_ready or None
    working = trial
    if _fits(working, **kw):
        return working

    # 6b) Party feats: drop effect prose as wholes (keep id+name). Never mid-cut.
    if isinstance(working.get("party"), list):
        omitted = 0
        trial = dict(working)
        thin_party = []
        for member in working.get("party") or []:
            if not isinstance(member, dict):
                continue
            row = dict(member)
            feats = row.get("active_feats")
            if isinstance(feats, list) and feats:
                thin_feats = []
                for feat in feats:
                    if not isinstance(feat, dict):
                        continue
                    if feat.get("effect"):
                        omitted += 1
                    thin_feats.append(
                        {
                            k: feat[k]
                            for k in ("id", "name")
                            if k in feat and feat[k] is not None
                        }
                    )
                row["active_feats"] = thin_feats
            thin_party.append(row)
        if omitted:
            trial["party"] = thin_party
            trial["active_feat_effects_omitted_for_budget"] = True
            trial["active_feat_effects_omitted_count"] = omitted
            working = trial
            if _fits(working, **kw):
                return working

    # 6c) main_dps_buffs — relevance order (never drop A/B head before E noise).
    # A head, B condition, C own → protect; D modifier / E support → shrink first.
    buffs = working.get("main_dps_buffs")
    if isinstance(buffs, dict) and isinstance(buffs.get("effects"), list):
        head_keys = (
            "src",
            "cat",
            "ref",
            "unresolved_ref",
            "reach",
            "activation",
            "magnitude_status",
            "reason",
            "deps",
            "pri",
            "relevance",
            "protected",
        )

        def _pri(row: dict[str, Any]) -> str:
            return str(row.get("pri") or "E")

        def _is_hard_head(row: dict[str, Any]) -> bool:
            """Confirmed heads + conditions — last to drop under budget."""
            p = _pri(row)
            if p == "B":
                return True
            if p == "C" and row.get("reach") == "in_range":
                return True
            if p == "A" and row.get("reach") == "in_range":
                return True
            return False

        def _is_soft_head(row: dict[str, Any]) -> bool:
            """Potential heads with unknown reach — protect over D/E, not over hard."""
            return _pri(row) == "A" and row.get("reach") != "in_range"

        def _is_head(row: dict[str, Any]) -> bool:
            return _is_hard_head(row) or _is_soft_head(row)

        def _effect_ref_count(rows: list[Any]) -> int:
            n = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if isinstance(row.get("refs"), list):
                    n += len(row["refs"])
                elif isinstance(row.get("u"), list):
                    n += len(row["u"])
                else:
                    n += 1
            return n

        def _update_completeness(
            trial_buffs: dict[str, Any],
            *,
            exported_rows: list[Any],
            omitted_unique: int,
            omit_reason: str,
        ) -> None:
            completeness = trial_buffs.get("completeness")
            if not isinstance(completeness, dict):
                return
            completeness = dict(completeness)
            examined = int(completeness.get("unique_effects_examined") or 0)
            refs_exported = _effect_ref_count(exported_rows)
            completeness["records_exported"] = len(exported_rows)
            completeness["effect_refs_exported"] = refs_exported
            completeness["unique_effects_omitted"] = omitted_unique
            # Partition: omitted = examined - represented refs (approx).
            if examined and refs_exported <= examined:
                completeness["unique_effects_omitted"] = max(
                    omitted_unique, examined - refs_exported
                )
            completeness["omit_reason"] = omit_reason
            trial_buffs["completeness"] = completeness

        # Always strip display names before fit trials.
        trial = dict(working)
        trial_buffs = dict(buffs)
        stripped = []
        for row in buffs.get("effects") or []:
            if not isinstance(row, dict):
                continue
            stripped.append(
                {k: row[k] for k in head_keys if k in row and row[k] is not None}
            )
        # Keep compact unresolved identities (cat+ref+reason); never invent mappings.
        unresolved = trial_buffs.get("unresolved_catalog")
        if isinstance(unresolved, list) and unresolved:
            trial_buffs["unresolved_catalog"] = [
                {
                    k: r[k]
                    for k in ("cat", "ref", "reason")
                    if isinstance(r, dict) and k in r and r[k] is not None
                }
                for r in unresolved
            ]
        trial_buffs["effects"] = stripped or None
        trial["main_dps_buffs"] = trial_buffs
        working = trial
        if _fits(working, **kw):
            return working

        # 6c-i) Drop E/F support noise first (never A/B/C head).
        trial = dict(working)
        trial_buffs = dict(trial.get("main_dps_buffs") or {})
        kept: list[dict[str, Any]] = []
        omitted = 0
        for row in trial_buffs.get("effects") or []:
            if not isinstance(row, dict):
                continue
            if _is_head(row) or _pri(row) == "D":
                kept.append(row)
            else:
                omitted += 1
        trial_buffs["effects"] = kept or None
        _update_completeness(
            trial_buffs,
            exported_rows=kept,
            omitted_unique=omitted,
            omit_reason="budget_drop_low_relevance_support",
        )
        trial["main_dps_buffs"] = trial_buffs
        working = trial
        if _fits(working, **kw):
            return working

        # 6c-ii) Drop D modifiers next (keep A/B/C head).
        trial = dict(working)
        trial_buffs = dict(trial.get("main_dps_buffs") or {})
        kept = []
        omitted = 0
        for row in trial_buffs.get("effects") or []:
            if not isinstance(row, dict):
                continue
            if _is_head(row):
                kept.append(row)
            else:
                omitted += 1
        trial_buffs["effects"] = kept or None
        _update_completeness(
            trial_buffs,
            exported_rows=kept,
            omitted_unique=omitted,
            omit_reason="budget_drop_modifiers_keep_heads",
        )
        trial["main_dps_buffs"] = trial_buffs
        working = trial
        if _fits(working, **kw):
            return working

        # 6c-iii) Drop soft heads (unknown reach) before confirmed in_range heads.
        trial = dict(working)
        trial_buffs = dict(trial.get("main_dps_buffs") or {})
        kept = []
        omitted = 0
        for row in trial_buffs.get("effects") or []:
            if not isinstance(row, dict):
                continue
            if _is_hard_head(row):
                kept.append(row)
            else:
                omitted += 1
        trial_buffs["effects"] = kept or None
        _update_completeness(
            trial_buffs,
            exported_rows=kept,
            omitted_unique=omitted,
            omit_reason="budget_drop_soft_unknown_heads",
        )
        trial["main_dps_buffs"] = trial_buffs
        working = trial
        if _fits(working, **kw):
            return working

        # 6d) Compact head rows (drop effect_def / pri labels).
        trial = dict(working)
        trial_buffs = dict(trial.get("main_dps_buffs") or {})
        compact: list[dict[str, Any]] = []
        for row in trial_buffs.get("effects") or []:
            if not isinstance(row, dict):
                continue
            compact.append(
                {
                    k: row[k]
                    for k in (
                        "src",
                        "cat",
                        "ref",
                        "unresolved_ref",
                        "reach",
                        "activation",
                        "reason",
                        "deps",
                        "relevance",
                    )
                    if k in row and row[k] is not None
                }
            )
        trial_buffs["effects"] = compact or None
        trial["main_dps_buffs"] = trial_buffs
        working = trial
        if _fits(working, **kw):
            return working

        # 6e) Group hard heads by (src, cat, reach) into refs[] (decodeable).
        trial = dict(working)
        trial_buffs = dict(trial.get("main_dps_buffs") or {})
        groups: dict[tuple[Any, ...], dict[str, Any]] = {}
        group_order: list[tuple[Any, ...]] = []
        for row in trial_buffs.get("effects") or []:
            if not isinstance(row, dict):
                continue
            ref = row.get("ref") or row.get("unresolved_ref")
            key = (row.get("src"), row.get("cat"), row.get("reach"), row.get("activation"))
            if key not in groups:
                groups[key] = {
                    "src": row.get("src"),
                    "cat": row.get("cat"),
                    "reach": row.get("reach"),
                    "activation": row.get("activation"),
                    "refs": [],
                    "relevance": row.get("relevance") or "head",
                }
                if row.get("deps"):
                    groups[key]["deps"] = row.get("deps")
                if row.get("reason") and row.get("reason") not in (
                    "computed_in_range",
                    "computed_out_of_range",
                ):
                    groups[key]["reason"] = row.get("reason")
                group_order.append(key)
            if isinstance(ref, int):
                groups[key]["refs"].append(ref)
        grouped = []
        for key in group_order:
            g = groups[key]
            refs = g.get("refs") or []
            if len(refs) == 1:
                g = dict(g)
                g["ref"] = refs[0]
                g.pop("refs", None)
            elif not refs:
                g = {k: v for k, v in g.items() if k != "refs" and v is not None}
            grouped.append({k: v for k, v in g.items() if v is not None})
        trial_buffs["effects"] = grouped or None
        _update_completeness(
            trial_buffs,
            exported_rows=grouped,
            omitted_unique=int(
                (trial_buffs.get("completeness") or {}).get("unique_effects_omitted")
                or 0
            ),
            omit_reason="budget_group_heads_by_src",
        )
        urefs = trial_buffs.get("unresolved_catalog")
        if isinstance(urefs, list) and urefs:
            trial_buffs["unresolved_catalog"] = [
                {
                    k: r[k]
                    for k in ("cat", "ref", "reason")
                    if isinstance(r, dict) and k in r and r[k] is not None
                }
                for r in urefs
            ]
        trial["main_dps_buffs"] = trial_buffs
        working = trial
        if _fits(working, **kw):
            return working

        # 6f) Ultrathin single rows (deps keys only).
        trial = dict(working)
        trial_buffs = dict(trial.get("main_dps_buffs") or {})
        ultra: list[dict[str, Any]] = []
        for row in trial_buffs.get("effects") or []:
            if not isinstance(row, dict):
                continue
            deps = row.get("deps")
            thin_deps = None
            if isinstance(deps, list):
                thin_deps = [
                    {
                        k: d[k]
                        for k in ("kind", "key", "upgrade_id", "status")
                        if isinstance(d, dict) and k in d and d[k] is not None
                    }
                    for d in deps
                    if isinstance(d, dict)
                ] or None
            item: dict[str, Any] = {
                k: v
                for k, v in {
                    "src": row.get("src"),
                    "cat": row.get("cat"),
                    "ref": row.get("ref") or row.get("unresolved_ref"),
                    "refs": row.get("refs"),
                    "reach": row.get("reach"),
                    "activation": row.get("activation"),
                    "deps": thin_deps,
                }.items()
                if v is not None
            }
            ultra.append(item)
        trial_buffs["effects"] = ultra or None
        _update_completeness(
            trial_buffs,
            exported_rows=ultra,
            omitted_unique=int(
                (trial_buffs.get("completeness") or {}).get("unique_effects_omitted")
                or 0
            ),
            omit_reason="budget_ultrathin_heads",
        )
        trial["main_dps_buffs"] = trial_buffs
        working = trial
        if _fits(working, **kw):
            return working

        # 6g) Drop unresolved_catalog rows (uncertain noise) before hard heads.
        # Keep count + flag so the model knows the catalog was truncated.
        trial = dict(working)
        trial_buffs = dict(trial.get("main_dps_buffs") or {})
        urefs = trial_buffs.get("unresolved_catalog")
        if isinstance(urefs, list) and urefs:
            trial_buffs = dict(trial_buffs)
            trial_buffs.pop("unresolved_catalog", None)
            trial_buffs["unresolved_catalog_omitted_for_budget"] = True
            trial_buffs["unresolved_catalog_omitted_count"] = len(urefs)
            completeness = trial_buffs.get("completeness")
            if isinstance(completeness, dict):
                completeness = dict(completeness)
                completeness["omit_reason"] = "budget_drop_unresolved_catalog"
                trial_buffs["completeness"] = completeness
            trial["main_dps_buffs"] = trial_buffs
            working = trial
            if _fits(working, **kw):
                return working

    # 6d) Drop lock_provenance under pressure — boolean locks + locked_position_id
    # remain authoritative for validation/apply.
    if isinstance(working.get("party"), list):
        trial = dict(working)
        thin_party = []
        dropped_prov = False
        for member in working.get("party") or []:
            if not isinstance(member, dict):
                continue
            row = dict(member)
            if "lock_provenance" in row:
                row.pop("lock_provenance", None)
                dropped_prov = True
            thin_party.append(row)
        if dropped_prov:
            trial["party"] = thin_party
            working = trial
            if _fits(working, **kw):
                return working

    # 7) Party: drop names + unknown live_state (ids/level/locks/specs/feats remain).
    if isinstance(working.get("party"), list):
        trial = dict(working)
        thin_party: list[dict[str, Any]] = []
        for member in working.get("party") or []:
            if not isinstance(member, dict):
                continue
            row = {
                k: member[k]
                for k in (
                    "id",
                    "seat",
                    "position",
                    "level",
                    "upgrade_status",
                    "locked",
                    "lock_reason",
                    "replacement_locked",
                    "must_remain_in_party",
                    "position_locked",
                    "locked_position_id",
                    "specialization_choices",
                    "active_feat_ids",
                    "active_feats",
                    "feats_status",
                    "eligibility",
                )
                if k in member and member[k] is not None
            }
            # Prefer compact ids when both present under pressure.
            if row.get("active_feat_ids") is not None and row.get("active_feats"):
                row.pop("active_feats", None)
            # Keep empty active_feats (known empty) via explicit [].
            if "active_feats" in member and member["active_feats"] == []:
                row["active_feats"] = []
            if "active_feat_ids" in member and member["active_feat_ids"] == []:
                row["active_feat_ids"] = []
            thin_party.append(row)
        trial["party"] = thin_party
        working = trial
        if _fits(working, **kw):
            return working

        # 7b) Specs → selected ids only; drop upgrade_status when unknown.
        trial = dict(working)
        thinner: list[dict[str, Any]] = []
        for member in trial.get("party") or []:
            if not isinstance(member, dict):
                continue
            row = dict(member)
            if row.get("upgrade_status") == "unknown":
                row.pop("upgrade_status", None)
            choices = row.get("specialization_choices")
            if isinstance(choices, list) and choices:
                thin_choices = []
                for ch in choices:
                    if not isinstance(ch, dict):
                        continue
                    sid = ch.get("selected_option_id")
                    if sid is not None:
                        thin_choices.append({"id": sid})
                    elif ch.get("group_id") is not None:
                        thin_choices.append(
                            {
                                k: ch[k]
                                for k in ("group_id", "selection_status")
                                if k in ch and ch[k] is not None
                            }
                        )
                row["specialization_choices"] = thin_choices or None
            thinner.append({k: v for k, v in row.items() if v is not None})
        trial["party"] = thinner
        working = trial
        if _fits(working, **kw):
            return working

    # 8) Goal: keep ids/status; drop display names / long restriction text.
    goal = working.get("goal")
    if isinstance(goal, dict):
        trial = dict(working)
        trial_goal = dict(goal)
        for key in (
            "adventure_name",
            "campaign_name",
            "patron_name",
            "restriction_text",
            "description",
            "label",
        ):
            trial_goal.pop(key, None)
        observed = trial_goal.get("observed_modron")
        if isinstance(observed, dict):
            observed = dict(observed)
            observed.pop("note", None)
            if observed.get("reset_area") is None:
                trial_goal.pop("observed_modron", None)
            else:
                trial_goal["observed_modron"] = observed
        structured = trial_goal.get("structured_restrictions")
        if isinstance(structured, dict):
            structured = dict(structured)
            structured.pop("expr_interpretations", None)
            structured.pop("active_notes", None)
            structured.pop("raw_restriction_texts", None)
            structured.pop("checked_means", None)
            # Keep unevaluable_rules (compact raw params) — research_gaps refs them.
            trial_goal["structured_restrictions"] = structured
        trial["goal"] = trial_goal
        working = trial
        if _fits(working, **kw):
            return working

    # 9) BUD note / optional chrome already mostly gone — drop bud peak/current
    # detail objects to short reason codes if still over.
    bud = working.get("bud_observation")
    if isinstance(bud, dict):
        trial = dict(working)
        trial["bud_observation"] = {
            k: bud[k]
            for k in (
                "reset_highest_damage_champion_id",
                "reset_highest_damage_status",
                "observation_source",
                "observed_at",
                "current_bud_setter_status",
            )
            if k in bud and bud[k] is not None
        }
        trial["bud_observation"]["current_bud"] = "unknown"
        trial["bud_observation"]["peak"] = "unknown"
        working = trial
        if _fits(working, **kw):
            return working

    # 10) Last resort: collapse live_diagnostics to counts (protected codes stay
    # on readiness / presence_conflicts).
    live = working.get("live_diagnostics")
    if isinstance(live, dict):
        trial = dict(working)
        thin_live: dict[str, Any] = {}
        for key in ("unknown_count", "known_count", "status"):
            if key in live and live[key] is not None:
                thin_live[key] = live[key]
        rows = live.get("rows") or live.get("values")
        if isinstance(rows, list):
            thin_live["rows_omitted_for_budget"] = len(rows)
        trial["live_diagnostics"] = thin_live or {"omitted_for_budget": True}
        working = trial
        if _fits(working, **kw):
            return working

    return working


def build_advice_request_clipboard_text(
    request: dict[str, Any],
    *,
    mode: InstructionMode = "project",
    shrink_for_export: bool = True,
    max_chars: int | None = MAX_EXPORT_BYTES,
    raise_on_over_budget: bool = False,
) -> str:
    """Exact clipboard string for an advice request (count this string).

    When ``max_chars`` is set, applies loss-free then budget-aware shrinking
    (omit oversized effects; never mid-cut prose). Hard gate is UTF-8 bytes
    (``MAX_EXPORT_BYTES``). When ``raise_on_over_budget`` is true and the
    result is still over, raises ``AdviceRequestBudgetError``.
    """
    meta = request.get("meta") if isinstance(request.get("meta"), dict) else {}
    snap_ref = meta.get("snapshot_ref") if isinstance(meta.get("snapshot_ref"), dict) else {}
    snapshot_id = str(snap_ref.get("snapshot_id") or "?")
    expected_filename = snap_ref.get("expected_filename")
    payload = request_for_export(request) if shrink_for_export else copy.deepcopy(request)
    if max_chars is not None:
        payload = _fit_payload_to_budget(
            payload,
            mode=mode,
            snapshot_id=snapshot_id,
            expected_filename=(
                str(expected_filename) if expected_filename else None
            ),
            max_chars=int(max_chars),
        )
    text = _render_advice_request_clipboard(
        payload,
        mode=mode,
        snapshot_id=snapshot_id,
        expected_filename=(
            str(expected_filename) if expected_filename else None
        ),
    )
    if raise_on_over_budget and max_chars is not None:
        status = budget_status(text, int(max_chars))
        if not status.within_budget:
            body = minify_json(payload)
            sections = {
                "json_gegevens": body,
                "antwoordformaat_tabel": ADVICE_TABLE_FORMAT,
                "modus_en_veiligheid": "\n".join(
                    [
                        instruction_mode_assumption(mode),
                        safety_instruction(
                            snapshot_id,
                            expected_filename=(
                                str(expected_filename) if expected_filename else None
                            ),
                        ),
                    ]
                ),
            }
            top = section_sizes(sections)[:3]
            cause = "Grootste onderdelen: " + "; ".join(
                f"{s['name']}={s['utf8_bytes']}B" for s in top
            )
            raise AdviceRequestBudgetError(
                chars=status.chars,
                max_chars=status.max_chars,
                utf8_bytes=status.utf8_bytes,
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


def advice_request_section_breakdown(
    request: dict[str, Any],
    *,
    mode: InstructionMode,
    max_chars: int | None = DEFAULT_CHAR_BUDGET,
) -> list[dict[str, Any]]:
    """Size contributors for UI when over budget (after the same fit as copy)."""
    meta = request.get("meta") if isinstance(request.get("meta"), dict) else {}
    snap_ref = meta.get("snapshot_ref") if isinstance(meta.get("snapshot_ref"), dict) else {}
    snapshot_id = str(snap_ref.get("snapshot_id") or "?")
    expected = snap_ref.get("expected_filename")
    payload = request_for_export(request)
    if max_chars is not None:
        payload = _fit_payload_to_budget(
            payload,
            mode=mode,
            snapshot_id=snapshot_id,
            expected_filename=str(expected) if expected else None,
            max_chars=int(max_chars),
        )
    body = minify_json(payload)
    swap = _request_has_swap_scope(payload) or _request_has_swap_scope(request)
    sections = {
        "modus_en_veiligheid": "\n".join(
            [
                instruction_mode_assumption(mode),
                safety_instruction(
                    snapshot_id,
                    expected_filename=str(expected) if expected else None,
                ),
            ]
        ),
        "antwoordformaat_tabel": ADVICE_TABLE_FORMAT,
        "json_gegevens": body,
    }
    if mode == "standalone":
        sections["algemene_instructies"] = "\n".join(
            _standalone_advice_rules(swap=swap)
        )
    elif swap:
        sections["swap_werkwijze"] = SWAP_ADVICE_WORKFLOW_CLIPBOARD
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
