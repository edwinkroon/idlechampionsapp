"""Compare live account/mechanics state to an exported BASE_SNAPSHOT.

Local hash comparison only — does not verify that any AI chat still has the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ic_gamedata.formation_ai_advice.snapshot_export import build_base_snapshot
from ic_gamedata.formation_ai_advice.snapshot_store import load_snapshot_registry
from ic_gamedata.party_advisor_models import FormationHero


class SnapshotFreshnessStatus(str, Enum):
    NO_SNAPSHOT = "no_snapshot"
    NO_RELEVANT_CHANGES_DETECTED = "no_relevant_changes_detected"
    ACCOUNT_CHANGED = "account_changed"
    MECHANICS_CHANGED = "mechanics_changed"
    ACCOUNT_AND_MECHANICS_CHANGED = "account_and_mechanics_changed"
    ACTUALITY_UNKNOWN = "actuality_unknown"


@dataclass(frozen=True)
class SnapshotFreshnessReport:
    status: SnapshotFreshnessStatus
    exported_snapshot_id: str | None
    live_snapshot_id: str | None
    exported_account_hash: str | None
    live_account_hash: str | None
    exported_mechanics_hash: str | None
    live_mechanics_hash: str | None
    user_declared_shared: bool
    user_declared_shared_snapshot_id: str | None
    local_comparison_only: bool = True
    notes: tuple[str, ...] = ()
    recommend_new_base_export: bool = False
    live_meta: dict[str, Any] | None = None

    @property
    def label_nl(self) -> str:
        mapping = {
            SnapshotFreshnessStatus.NO_SNAPSHOT: "Geen geëxporteerde snapshot",
            SnapshotFreshnessStatus.NO_RELEVANT_CHANGES_DETECTED: (
                "Geen gedetecteerde relevante wijzigingen (lokale vergelijking)"
            ),
            SnapshotFreshnessStatus.ACCOUNT_CHANGED: "Accountgegevens gewijzigd",
            SnapshotFreshnessStatus.MECHANICS_CHANGED: "Mechanics gewijzigd",
            SnapshotFreshnessStatus.ACCOUNT_AND_MECHANICS_CHANGED: (
                "Accountgegevens én mechanics gewijzigd"
            ),
            SnapshotFreshnessStatus.ACTUALITY_UNKNOWN: (
                "Actualiteit niet vast te stellen"
            ),
        }
        return mapping[self.status]


def compute_live_snapshot_meta(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...] | None = None,
    *,
    goal: str = "push",
    context: str = "campaign",
    force_refresh_roster: bool = False,
) -> dict[str, Any]:
    """Build a live snapshot and return its meta (new ID if content changed)."""
    snap = build_base_snapshot(
        payload,
        formation=formation,
        goal=goal,
        context=context,
        force_refresh_roster=force_refresh_roster,
    )
    meta = snap.get("meta") if isinstance(snap.get("meta"), dict) else {}
    return {
        "snapshot": snap,
        "snapshot_id": meta.get("snapshot_id"),
        "mechanics_hash": meta.get("mechanics_hash"),
        "account_state_hash": meta.get("account_state_hash"),
        "created_at": meta.get("created_at"),
        "data_version": meta.get("data_version"),
    }


def assess_snapshot_freshness(
    payload: dict[str, Any],
    formation: tuple[FormationHero, ...] | None = None,
    *,
    goal: str = "push",
    context: str = "campaign",
    registry: dict[str, Any] | None = None,
    force_refresh_roster: bool = False,
) -> SnapshotFreshnessReport:
    """Compare live hashes to the last **exported** snapshot in the registry."""
    reg = registry if isinstance(registry, dict) else load_snapshot_registry()
    exported_id = reg.get("last_exported_snapshot_id") or reg.get("last_snapshot_id")
    exported_account = reg.get("last_account_state_hash")
    exported_mech = reg.get("last_mechanics_hash")
    declared_id = reg.get("user_declared_shared_snapshot_id")
    declared = bool(
        declared_id
        and exported_id
        and str(declared_id) == str(exported_id)
    )

    base_notes = [
        "Vergelijking is alleen lokaal (app vs laatst opgeslagen/geëxporteerde snapshot).",
        "Dit bewijst niet dat een AI-chat of projectopslag het bestand nog heeft.",
        "‘Geen gedetecteerde wijzigingen’ garandeert niet dat game defines actueel zijn "
        "als daar geen aparte betrouwbare bron voor is.",
    ]

    if not exported_id or not exported_account or not exported_mech:
        return SnapshotFreshnessReport(
            status=SnapshotFreshnessStatus.NO_SNAPSHOT,
            exported_snapshot_id=exported_id if isinstance(exported_id, str) else None,
            live_snapshot_id=None,
            exported_account_hash=exported_account if isinstance(exported_account, str) else None,
            live_account_hash=None,
            exported_mechanics_hash=exported_mech if isinstance(exported_mech, str) else None,
            live_mechanics_hash=None,
            user_declared_shared=declared,
            user_declared_shared_snapshot_id=declared_id
            if isinstance(declared_id, str)
            else None,
            notes=tuple(
                base_notes
                + [
                    "Exporteer eerst een basisbestand (opslaan/downloaden) vóór "
                    "compacte adviesvragen."
                ]
            ),
            recommend_new_base_export=True,
        )

    try:
        live = compute_live_snapshot_meta(
            payload,
            formation,
            goal=goal,
            context=context,
            force_refresh_roster=force_refresh_roster,
        )
    except Exception as exc:
        return SnapshotFreshnessReport(
            status=SnapshotFreshnessStatus.ACTUALITY_UNKNOWN,
            exported_snapshot_id=str(exported_id),
            live_snapshot_id=None,
            exported_account_hash=str(exported_account),
            live_account_hash=None,
            exported_mechanics_hash=str(exported_mech),
            live_mechanics_hash=None,
            user_declared_shared=declared,
            user_declared_shared_snapshot_id=str(declared_id)
            if declared_id
            else None,
            notes=tuple(
                base_notes
                + [f"Live hashberekening mislukt: {type(exc).__name__}: {exc}"]
            ),
            recommend_new_base_export=True,
        )

    live_account = live.get("account_state_hash")
    live_mech = live.get("mechanics_hash")
    live_id = live.get("snapshot_id")
    if not isinstance(live_account, str) or not isinstance(live_mech, str):
        return SnapshotFreshnessReport(
            status=SnapshotFreshnessStatus.ACTUALITY_UNKNOWN,
            exported_snapshot_id=str(exported_id),
            live_snapshot_id=str(live_id) if live_id else None,
            exported_account_hash=str(exported_account),
            live_account_hash=live_account if isinstance(live_account, str) else None,
            exported_mechanics_hash=str(exported_mech),
            live_mechanics_hash=live_mech if isinstance(live_mech, str) else None,
            user_declared_shared=declared,
            user_declared_shared_snapshot_id=str(declared_id)
            if declared_id
            else None,
            notes=tuple(base_notes + ["Live hashes ontbreken of zijn ongeldig."]),
            recommend_new_base_export=True,
            live_meta={k: v for k, v in live.items() if k != "snapshot"},
        )

    account_changed = live_account != str(exported_account)
    mech_changed = live_mech != str(exported_mech)
    if account_changed and mech_changed:
        status = SnapshotFreshnessStatus.ACCOUNT_AND_MECHANICS_CHANGED
    elif account_changed:
        status = SnapshotFreshnessStatus.ACCOUNT_CHANGED
    elif mech_changed:
        status = SnapshotFreshnessStatus.MECHANICS_CHANGED
    else:
        status = SnapshotFreshnessStatus.NO_RELEVANT_CHANGES_DETECTED

    notes = list(base_notes)
    if status != SnapshotFreshnessStatus.NO_RELEVANT_CHANGES_DETECTED:
        notes.append(
            "Aanbevolen: nieuw basisbestand exporteren (nieuw snapshot-ID). "
            "Wijzig de oude snapshot niet onder hetzelfde ID."
        )
        if live_id and live_id != exported_id:
            notes.append(
                f"Live inhoud zou snapshot `{live_id}` worden; "
                f"geëxporteerde referentie is nog `{exported_id}`."
            )
        notes.append(
            "Compacte aanvragen blijven naar de geëxporteerde snapshot verwijzen "
            "tot je de nieuwe exporteert — niet stil naar een alleen-lokaal "
            "gebouwde snapshot."
        )
    if declared and status != SnapshotFreshnessStatus.NO_RELEVANT_CHANGES_DETECTED:
        notes.append(
            "Je eerdere verklaring ‘gedeeld’ geldt voor de oude snapshot; "
            "deel de nieuwe na export opnieuw (checkbox is geen technische check)."
        )
    elif not declared:
        notes.append(
            "Gebruikersverklaring ‘Ik heb deze snapshot gedeeld’ ontbreekt of "
            "komt niet overeen — dat is optioneel en geen AI-verificatie."
        )

    return SnapshotFreshnessReport(
        status=status,
        exported_snapshot_id=str(exported_id),
        live_snapshot_id=str(live_id) if live_id else None,
        exported_account_hash=str(exported_account),
        live_account_hash=live_account,
        exported_mechanics_hash=str(exported_mech),
        live_mechanics_hash=live_mech,
        user_declared_shared=declared,
        user_declared_shared_snapshot_id=str(declared_id) if declared_id else None,
        notes=tuple(notes),
        recommend_new_base_export=status
        != SnapshotFreshnessStatus.NO_RELEVANT_CHANGES_DETECTED,
        live_meta={k: v for k, v in live.items() if k != "snapshot"},
    )


USER_HELP_NL = """\
## Wanneer wat doen?

**Basisgegevens delen** — eenmaal na een verse export, of na relevante roster-/feat-/mechanicwijzigingen. Voeg het bestand bewust toe aan je AI-chat of projectbronnen.

**Alleen een adviesvraag kopiëren** — als de geëxporteerde snapshot nog klopt voor account/mechanics (lokale check) en je die al hebt gedeeld. De aanvraag bevat altijd verse adventure/party/eligibility.

**Basisgegevens vernieuwen** — bij “Accountgegevens gewijzigd” of “Mechanics gewijzigd”: bouw en exporteer een **nieuw** basisbestand (nieuw ID). Overschrijf niet stil onder hetzelfde ID.

**AI vindt de snapshot niet** — deel het opgeslagen bestand opnieuw; claim niet dat de app kan zien of de AI het nog heeft. Gebruik daarna opnieuw de checkbox alleen als gebruikersverklaring.
""".strip()
