"""Research-mode constants and hybrid prompt helpers for advice exports.

The app does not run an external search service. Modes only change clipboard
instructions: what the AI assistant may look up publicly vs what must stay
grounded in the exported account/run state.

Follow-up (not implemented here): an optional local public-rules knowledge
cache could reuse confirmed adventure/mechanic facts across exports. Any such
cache must store source, verification date, adventure/patron/data context, and
must never treat unconfirmed AI assumptions as verified game rules. There is
no automatic feedback loop from chat research into the app today.
"""

from __future__ import annotations

from typing import Any

RESEARCH_MODE_PROVIDED_ONLY = "provided_data_only"
RESEARCH_MODE_HYBRID = "provided_data_plus_targeted_research"
# Legacy alias kept for older callers / snapshots.
RESEARCH_MODE_WEB_ALLOWED = "web_research_allowed"

KNOWN_RESEARCH_MODES = frozenset(
    {
        RESEARCH_MODE_PROVIDED_ONLY,
        RESEARCH_MODE_HYBRID,
        RESEARCH_MODE_WEB_ALLOWED,
    }
)

RESEARCH_MODE_COMBO_ITEMS: tuple[tuple[str, str], ...] = (
    ("Alleen exportgegevens", RESEARCH_MODE_PROVIDED_ONLY),
    ("Export + gerichte research", RESEARCH_MODE_HYBRID),
)


def normalize_research_mode(raw: Any) -> str:
    text = str(raw or "").strip()
    if text in KNOWN_RESEARCH_MODES:
        return text
    return RESEARCH_MODE_PROVIDED_ONLY


def allows_targeted_public_research(mode: str) -> bool:
    return normalize_research_mode(mode) in {
        RESEARCH_MODE_HYBRID,
        RESEARCH_MODE_WEB_ALLOWED,
    }


def research_mode_instruction_lines(mode: str) -> list[str]:
    """Clipboard addendum for the active research mode (may be empty)."""
    normalized = normalize_research_mode(mode)
    if normalized == RESEARCH_MODE_PROVIDED_ONLY:
        return []
    if normalized == RESEARCH_MODE_HYBRID:
        return [
            "",
            "Hybride researchmodus (gerichte publieke aanvulling):",
            "- Gebruik BASE_SNAPSHOT en ADVICE_REQUEST als primaire bronnen.",
            "- Onderzoek alleen ontbrekende openbare mechanics/restricties die "
            "het formatie- of swapadvies kunnen veranderen (zie research_gaps).",
            "- Zoek eerst de exacte adventure-/variant-/patroncontext; geen breed "
            "internetonderzoek zonder beslisrelevantie.",
            "- Beoordeel actualiteit en betrouwbaarheid van bronnen; een oude "
            "communitymelding is niet automatisch bewijs voor de actuele volledige regel.",
            "- Citeer externe aanvullingen; scheid geëxporteerde feiten, extern "
            "bevestigde aanvullingen en onbevestigde aannames.",
            "- Verzin geen live/accountgegevens, geometry, slot_states of "
            "expliciete spelblokkades; die blijven leidend.",
            "- Behandel lokale eligibility=unknown niet automatisch als allowed, "
            "maar onderzoek de ontbrekende beslisregel vóór je vervangingen "
            "definitief uitsluit.",
            "- Lokale denied blijft denied tenzij een bewezen uitzondering binnen "
            "zijn scope van toepassing is.",
            "- Claim niet dat de huidige party optimaal is als kandidaten niet "
            "voldoende konden worden onderzocht.",
            "- Bij een onopgelost conflict: vraag gericht om een controle of screenshot.",
        ]
    # web_research_allowed — broader legacy wording
    return [
        "",
        "Aanvullend webonderzoek is voor deze aanvraag toegestaan; "
        "claims herleidbaar houden; geen verzonnen URL’s. "
        "Actuele account-/runstatus en expliciete spelblokkades blijven leidend; "
        "unknown eligibility niet stilzwijgend als allowed behandelen.",
    ]


def research_gaps_from_unevaluable_rules(
    unevaluable_rules: list[dict[str, Any]] | None,
    *,
    adventure_id: int | None = None,
    adventure_name: str | None = None,
    patron_id: int | None = None,
    patron_name: str | None = None,
    unknown_candidate_count: int | None = None,
    unknown_candidate_sample_ids: list[int] | None = None,
) -> dict[str, Any] | None:
    """Compact action-oriented gaps for hybrid research (one entry per rule)."""
    rules = [r for r in (unevaluable_rules or []) if isinstance(r, dict)]
    if not rules:
        return None
    gaps: list[dict[str, Any]] = []
    for rule in rules:
        rule_id = str(rule.get("id") or f"rule_{len(gaps) + 1}")
        gaps.append(
            {
                "id": rule_id,
                "kind": "unevaluable_roster_predicate",
                "predicate": rule.get("predicate"),
                "change_type": rule.get("change_type"),
                "raw": rule.get("raw"),
                "why_local_unknown": rule.get("why_local_unknown")
                or "Lokale evaluator ondersteunt deze predicate niet (of parameters ontbreken).",
                "public_research_may_help": True,
                "blocks": ["swap_eligibility_comparison", "unconditional_candidate_ranking"],
                "does_not_block": [
                    "geometry_and_slot_states",
                    "proposals_that_exclude_unresolved_replaceable_party_members",
                ],
                "needed_context": {
                    k: v
                    for k, v in {
                        "adventure_id": adventure_id,
                        "adventure_name": adventure_name,
                        "patron_id": patron_id,
                        "patron_name": patron_name,
                        "rule_ref": rule_id,
                    }.items()
                    if v is not None
                },
                "unknown_candidate_count": unknown_candidate_count,
                "unknown_candidate_sample_ids": (
                    list(unknown_candidate_sample_ids[:8])
                    if unknown_candidate_sample_ids
                    else None
                ),
                "champion_data_refs": rule.get("champion_data_refs"),
            }
        )
    return {
        "gaps": gaps,
        "note": (
            "Één gap per niet-geëvalueerde essentiële regel. "
            "Kandidaten blijven lokaal unknown tot de regel is opgelost; "
            "geen stilzwijgende allowed-promotie."
        ),
    }
