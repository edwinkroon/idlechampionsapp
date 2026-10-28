"""Explicit user eligibility confirmations for a scoped adventure context.

Presence in the live formation is never enough. A correction only applies when
the user confirmed the same champion for the same party/adventure/patron
scope, and remains distinct from API-proven overrides.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ic_gamedata.paths import _CONFIG_BASE

CORRECTIONS_PATH = _CONFIG_BASE / "config" / "eligibility_corrections.json"
CORRECTIONS_SCHEMA = 1
SOURCE_USER_CONFIRMATION = "user_confirmation"
RESOLUTION_USER_CONFIRMATION = "user_confirmation"


@dataclass(frozen=True)
class EligibilityCorrection:
    champion_id: int
    party_id: int | None
    adventure_id: int | None
    patron_id: int | None
    base_status: str
    base_reason: str | None
    decision: str  # allowed
    source: str
    confirmed_at: str
    note: str | None = None

    def matches_scope(
        self,
        *,
        champion_id: int,
        party_id: int | None,
        adventure_id: int | None,
        patron_id: int | None,
    ) -> bool:
        if int(self.champion_id) != int(champion_id):
            return False
        if self.decision != "allowed":
            return False
        if self.source != SOURCE_USER_CONFIRMATION:
            return False
        return (
            _same_optional_int(self.party_id, party_id)
            and _same_optional_int(self.adventure_id, adventure_id)
            and _same_optional_int(self.patron_id, patron_id)
        )

    def as_export(self) -> dict[str, Any]:
        return {
            "champion_id": self.champion_id,
            "party_id": self.party_id,
            "adventure_id": self.adventure_id,
            "patron_id": self.patron_id,
            "base_status": self.base_status,
            "base_reason": self.base_reason,
            "decision": self.decision,
            "effective_status": "allowed",
            "source": self.source,
            "confirmed_at": self.confirmed_at,
            "note": self.note,
        }


def _same_optional_int(left: int | None, right: int | None) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return int(left) == int(right)


def _parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def load_corrections(path: Path | None = None) -> list[EligibilityCorrection]:
    target = path or CORRECTIONS_PATH
    if not target.is_file():
        return []
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw.get("corrections") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[EligibilityCorrection] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hid = _parse_int(row.get("champion_id"))
        if hid is None:
            continue
        decision = str(row.get("decision") or "").strip().casefold()
        source = str(row.get("source") or "").strip()
        if decision != "allowed" or source != SOURCE_USER_CONFIRMATION:
            continue
        out.append(
            EligibilityCorrection(
                champion_id=hid,
                party_id=_parse_int(row.get("party_id")),
                adventure_id=_parse_int(row.get("adventure_id")),
                patron_id=_parse_int(row.get("patron_id")),
                base_status=str(row.get("base_status") or "denied"),
                base_reason=(
                    str(row["base_reason"])
                    if row.get("base_reason") is not None
                    else None
                ),
                decision="allowed",
                source=SOURCE_USER_CONFIRMATION,
                confirmed_at=str(row.get("confirmed_at") or ""),
                note=(
                    str(row["note"]).strip() or None
                    if row.get("note") is not None
                    else None
                ),
            )
        )
    return out


def save_corrections(
    corrections: Iterable[EligibilityCorrection],
    *,
    path: Path | None = None,
) -> None:
    target = path or CORRECTIONS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CORRECTIONS_SCHEMA,
        "corrections": [asdict(c) for c in corrections],
    }
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def find_correction(
    corrections: Iterable[EligibilityCorrection],
    *,
    champion_id: int,
    party_id: int | None,
    adventure_id: int | None,
    patron_id: int | None,
) -> EligibilityCorrection | None:
    for row in corrections:
        if row.matches_scope(
            champion_id=champion_id,
            party_id=party_id,
            adventure_id=adventure_id,
            patron_id=patron_id,
        ):
            return row
    return None


def upsert_correction(
    correction: EligibilityCorrection,
    *,
    path: Path | None = None,
) -> list[EligibilityCorrection]:
    existing = [
        row
        for row in load_corrections(path)
        if not row.matches_scope(
            champion_id=correction.champion_id,
            party_id=correction.party_id,
            adventure_id=correction.adventure_id,
            patron_id=correction.patron_id,
        )
    ]
    existing.append(correction)
    save_corrections(existing, path=path)
    return existing


def revoke_correction(
    *,
    champion_id: int,
    party_id: int | None,
    adventure_id: int | None,
    patron_id: int | None,
    path: Path | None = None,
) -> list[EligibilityCorrection]:
    remaining = [
        row
        for row in load_corrections(path)
        if not row.matches_scope(
            champion_id=champion_id,
            party_id=party_id,
            adventure_id=adventure_id,
            patron_id=patron_id,
        )
    ]
    save_corrections(remaining, path=path)
    return remaining


def make_user_confirmation(
    *,
    champion_id: int,
    party_id: int | None,
    adventure_id: int | None,
    patron_id: int | None,
    base_status: str,
    base_reason: str | None,
    note: str | None = None,
    confirmed_at: str | None = None,
) -> EligibilityCorrection:
    return EligibilityCorrection(
        champion_id=int(champion_id),
        party_id=party_id,
        adventure_id=adventure_id,
        patron_id=patron_id,
        base_status=str(base_status or "denied"),
        base_reason=base_reason,
        decision="allowed",
        source=SOURCE_USER_CONFIRMATION,
        confirmed_at=confirmed_at or _now_iso(),
        note=(note.strip() if isinstance(note, str) and note.strip() else None),
    )
