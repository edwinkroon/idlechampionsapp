"""Human-readable adventure names from getuserdetails payload."""

from __future__ import annotations

from typing import Any


def adventure_display_name(payload: dict[str, Any] | None, adventure_id: int | None) -> str | None:
    """Resolve adventure name for UI captions (handles Free Play variants)."""
    if payload is None or adventure_id is None or adventure_id < 0:
        return None
    defines = payload.get("defines")
    if not isinstance(defines, dict):
        return f"Adventure {adventure_id}"
    adventures = defines.get("adventure_defines")
    if not isinstance(adventures, list):
        return f"Adventure {adventure_id}"

    adventure_by_id: dict[int, dict[str, Any]] = {}
    for adventure in adventures:
        if not isinstance(adventure, dict):
            continue
        try:
            adventure_by_id[int(adventure.get("id"))] = adventure
        except (TypeError, ValueError):
            continue

    location_name_by_id: dict[int, str] = {}
    locations = defines.get("location_defines")
    if isinstance(locations, list):
        for location in locations:
            if not isinstance(location, dict):
                continue
            try:
                location_id = int(location.get("id"))
            except (TypeError, ValueError):
                continue
            name = location.get("name")
            if isinstance(name, str) and name.strip():
                location_name_by_id[location_id] = name.strip()

    for adv in adventures:
        if not isinstance(adv, dict):
            continue
        try:
            if int(adv.get("id")) != adventure_id:
                continue
        except (TypeError, ValueError):
            continue
        name = adv.get("name")
        adventure_name = name.strip() if isinstance(name, str) and name.strip() else ""
        location_name = None
        if adv.get("location_id") is not None:
            try:
                location_name = location_name_by_id.get(int(adv.get("location_id")))
            except (TypeError, ValueError):
                location_name = None
        if location_name and adventure_name:
            if adventure_name.lower().startswith("free play"):
                base_adventure_name = None
                variant_adventure_id = adv.get("variant_adventure_id")
                try:
                    variant_adventure_id = int(variant_adventure_id)
                except (TypeError, ValueError):
                    variant_adventure_id = None
                if variant_adventure_id is not None:
                    base_adventure = adventure_by_id.get(variant_adventure_id)
                    if isinstance(base_adventure, dict):
                        base_name = base_adventure.get("name")
                        if isinstance(base_name, str) and base_name.strip():
                            base_adventure_name = base_name.strip()
                if base_adventure_name:
                    return f"{base_adventure_name} - {adventure_name}"
                return f"{location_name} - {adventure_name}"
            return adventure_name
        if adventure_name:
            return adventure_name
        if location_name:
            return location_name
    return f"Adventure {adventure_id}"
