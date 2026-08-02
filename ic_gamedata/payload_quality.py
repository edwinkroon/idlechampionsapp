"""Assess completeness of getuserdetails payloads for graceful degradation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ic_gamedata.parsing import parse_int as _parse_int

FormationSource = Literal["grid", "in_seat", "hero_in_seats", "saves", "none"]


@dataclass(frozen=True)
class PayloadQuality:
    """How complete/usable the latest payload is."""

    has_payload: bool
    has_active_instance: bool
    has_formation_grid: bool
    formation_hero_count: int
    formation_source: FormationSource
    warnings: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return self.has_payload and self.has_active_instance

    @property
    def formation_reliable(self) -> bool:
        return self.formation_source == "grid" and self.formation_hero_count > 0


def _formation_ids(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    ids: list[int] = []
    for item in raw:
        hid = _parse_int(item)
        if hid is not None and hid > 0:
            ids.append(hid)
    return ids


def assess_payload_quality(payload: dict[str, Any] | None) -> PayloadQuality:
    if not isinstance(payload, dict):
        return PayloadQuality(
            has_payload=False,
            has_active_instance=False,
            has_formation_grid=False,
            formation_hero_count=0,
            formation_source="none",
            warnings=("Geen API-payload — laatste bekende data wordt gebruikt indien beschikbaar.",),
        )

    details = payload.get("details")
    if not isinstance(details, dict):
        return PayloadQuality(
            has_payload=True,
            has_active_instance=False,
            has_formation_grid=False,
            formation_hero_count=0,
            formation_source="none",
            warnings=("Payload zonder details-blok.",),
        )

    active_id = _parse_int(details.get("active_game_instance_id"))
    instance = None
    for inst in details.get("game_instances") or []:
        if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:
            instance = inst
            break
    if instance is None:
        instances = details.get("game_instances")
        if isinstance(instances, list) and instances and isinstance(instances[0], dict):
            instance = instances[0]

    warnings: list[str] = []
    if instance is None:
        warnings.append("Geen actieve party-instance in payload.")
        return PayloadQuality(
            has_payload=True,
            has_active_instance=False,
            has_formation_grid=False,
            formation_hero_count=0,
            formation_source="none",
            warnings=tuple(warnings),
        )

    grid_ids = _formation_ids(instance.get("formation"))
    if not grid_ids:
        grid_ids = _formation_ids(details.get("formation"))

    if grid_ids:
        source: FormationSource = "grid"
        count = len(grid_ids)
    else:
        # Fallbacks are less reliable (may include benched seat holders).
        in_seat_count = 0
        for hero in details.get("heroes") or []:
            if not isinstance(hero, dict):
                continue
            if hero.get("in_seat") in (1, "1", True):
                in_seat_count += 1
        seats = instance.get("hero_in_seats")
        seat_holders = 0
        if isinstance(seats, dict):
            for raw in seats.values():
                hid = _parse_int(raw)
                if hid is not None and hid > 0:
                    seat_holders += 1

        if in_seat_count >= 2:
            source = "in_seat"
            count = in_seat_count
            warnings.append(
                "Live formation-grid ontbreekt — party afgeleid uit in_seat (kan achterlopen)."
            )
        elif seat_holders >= 1:
            source = "hero_in_seats"
            count = seat_holders
            warnings.append(
                "Live formation-grid ontbreekt — hero_in_seats kan gebenchte champions bevatten."
            )
        else:
            saves = instance.get("formation_saves_v2")
            if not isinstance(saves, list):
                saves = details.get("formation_saves_v2")
            save_count = 0
            if isinstance(saves, list):
                for save in saves:
                    if isinstance(save, dict):
                        save_count = max(save_count, len(_formation_ids(save.get("formation"))))
            if save_count:
                source = "saves"
                count = save_count
                warnings.append("Geen live formatie — fallback op opgeslagen formation save.")
            else:
                source = "none"
                count = 0
                warnings.append("Geen formatie-data in payload.")

    return PayloadQuality(
        has_payload=True,
        has_active_instance=True,
        has_formation_grid=bool(grid_ids),
        formation_hero_count=count,
        formation_source=source,
        warnings=tuple(warnings),
    )
