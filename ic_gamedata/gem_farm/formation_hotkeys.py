"""Resolve Q/W/E formation save names from getuserdetails payload."""

from __future__ import annotations

from typing import Any

from ic_gamedata.gem_farm.models import FormationHotkeySlot, FormationHotkeys
from ic_gamedata.party_display import BRIV_HERO_ID, instance_for_party
from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.specialization_data import hero_name_map_from_champion_config

HOTKEY_LABELS = ("Q", "W", "E")
SLOT_KEYS = ("1", "2", "3")


def _saves_by_id(instance: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    saves = instance.get("formation_saves_v2")
    if not isinstance(saves, list):
        return out
    for save in saves:
        if not isinstance(save, dict):
            continue
        save_id = _parse_int(save.get("formation_save_id"))
        if save_id is not None and save_id > 0:
            out[save_id] = save
    return out


def _all_saves_by_id(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    details = payload.get("details")
    if not isinstance(details, dict):
        return merged
    instances = details.get("game_instances")
    if not isinstance(instances, list):
        return merged
    for inst in instances:
        if isinstance(inst, dict):
            merged.update(_saves_by_id(inst))
    return merged


def _merge_saves_for_party(payload: dict[str, Any], party_index: int) -> dict[int, dict[str, Any]]:
    """Collect formation saves for one party, including sibling instances on the same campaign."""
    instance = instance_for_party(payload, party_index)
    if instance is None:
        return {}
    campaign_id = _campaign_id(instance)
    merged: dict[int, dict[str, Any]] = {}

    details = payload.get("details")
    if isinstance(details, dict):
        instances = details.get("game_instances")
        if isinstance(instances, list):
            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                gid = _parse_int(inst.get("game_instance_id"))
                if gid is None:
                    continue
                if gid != party_index and _campaign_id(inst) != campaign_id:
                    continue
                merged.update(_saves_by_id(inst))

    # Prefer the active party's copy when duplicate save ids exist.
    merged.update(_saves_by_id(instance))
    return merged


def _names_from_saves(saves: dict[int, dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for save in saves.values():
        raw = save.get("name")
        if not isinstance(raw, str):
            continue
        name = raw.strip()
        if not name or name == "___AUTO___SAVE___":
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return sorted(names, key=str.casefold)


def formation_save_names_for_party(
    payload: dict[str, Any] | None,
    party_index: int | None = None,
) -> list[str]:
    """Return saved formation names for dropdowns.

    Prefer the party's campaign saves; if empty or party unknown, fall back to
    every formation save in the payload so the UI is never blank when API data exists.
    """
    if not isinstance(payload, dict):
        return []
    if party_index is not None:
        names = _names_from_saves(_merge_saves_for_party(payload, party_index))
        if names:
            return names
    return _names_from_saves(_all_saves_by_id(payload))


def _campaign_id(instance: dict[str, Any]) -> int | None:
    return _parse_int(instance.get("formation_saves_v2_campaign_id"))


def _modron_saves_map(payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("details")
    if not isinstance(details, dict):
        return {}
    raw = details.get("modron_saves")
    return raw if isinstance(raw, dict) else {}



def _resolve_modron_formation_saves(
    payload: dict[str, Any],
    *,
    party_index: int,
    campaign_id: int | None,
) -> tuple[dict[str, Any], str]:
    """
    Resolve Q/W/E slots from modron_saves.

    API quirk: key \"1\" is often campaign 1 (TOT), not party 1. When party index
    equals campaign id (party 1 on campaign 1100022), prefer the party-key entry.
    """
    modron_map = _modron_saves_map(payload)
    merged: dict[str, Any] = {}
    source = "none"

    party_entry = modron_map.get(str(party_index))
    if isinstance(party_entry, dict):
        fs = party_entry.get("formation_saves")
        if isinstance(fs, dict):
            for slot_key in SLOT_KEYS:
                if slot_key in fs:
                    merged[slot_key] = fs[slot_key]
            if any(slot_key in fs for slot_key in SLOT_KEYS):
                source = "modron_saves"

    if campaign_id is not None and str(campaign_id) != str(party_index):
        campaign_entry = modron_map.get(str(campaign_id))
        if isinstance(campaign_entry, dict):
            fs = campaign_entry.get("formation_saves")
            if isinstance(fs, dict):
                for slot_key in SLOT_KEYS:
                    if slot_key in fs and slot_key not in merged:
                        merged[slot_key] = fs[slot_key]
                if merged and source == "none":
                    source = f"campaign_{campaign_id}"

    if campaign_id is not None:
        details = payload.get("details")
        instances = details.get("game_instances") if isinstance(details, dict) else None
        if isinstance(instances, list):
            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                gid = _parse_int(inst.get("game_instance_id"))
                if gid is None or gid == party_index:
                    continue
                if _campaign_id(inst) != campaign_id:
                    continue
                entry = modron_map.get(str(gid))
                if not isinstance(entry, dict):
                    continue
                fs = entry.get("formation_saves")
                if not isinstance(fs, dict):
                    continue
                for slot_key in SLOT_KEYS:
                    if slot_key in fs and slot_key not in merged:
                        merged[slot_key] = fs[slot_key]
                if merged and source == "none":
                    source = f"fallback_party_{gid}"

    return merged, source


def _hero_ids_from_save(save: dict[str, Any]) -> list[int]:
    formation = save.get("formation")
    if not isinstance(formation, list):
        return []
    ids: list[int] = []
    for raw in formation:
        hero_id = _parse_int(raw)
        if hero_id is not None and hero_id > 0:
            ids.append(hero_id)
    return ids


def _champion_names(hero_ids: list[int], name_map: dict[int, str]) -> tuple[str, ...]:
    names: list[str] = []
    for hero_id in hero_ids:
        names.append(name_map.get(hero_id, f"#{hero_id}"))
    return tuple(names)


def _save_by_name(saves_by_id: dict[int, dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    target = name.casefold()
    for save in saves_by_id.values():
        raw_name = save.get("name")
        if isinstance(raw_name, str) and raw_name.strip().casefold() == target:
            return save
    return None


def _slot_from_save(
    hotkey: str,
    save: dict[str, Any] | None,
    *,
    save_id: int | None,
    name_map: dict[int, str],
) -> FormationHotkeySlot:
    if not isinstance(save, dict):
        return FormationHotkeySlot(hotkey=hotkey, save_id=save_id)

    resolved_id = _parse_int(save.get("formation_save_id")) or save_id
    save_name = str(save.get("name")).strip() if save.get("name") else None
    if save_name == "___AUTO___SAVE___":
        save_name = "(auto-save)"
    hero_ids = _hero_ids_from_save(save)
    return FormationHotkeySlot(
        hotkey=hotkey,
        save_id=resolved_id,
        save_name=save_name,
        champion_names=_champion_names(hero_ids, name_map),
        briv_in_save=BRIV_HERO_ID in hero_ids,
    )


def resolve_formation_hotkeys(
    payload: dict[str, Any] | None,
    *,
    party_index: int,
    profile_names: tuple[str | None, str | None, str | None] | None = None,
) -> FormationHotkeys | None:
    """
    Map game hotkeys Q/W/E to saved formation names for one party.

    Uses modron_saves.formation_saves slots 1/2/3 (Formation 1/2/3). When the
    active party has no modron entry, reuses bindings from another instance on
    the same campaign.
    """
    if not isinstance(payload, dict):
        return None
    instance = instance_for_party(payload, party_index)
    if instance is None:
        return None

    saves_by_id = _merge_saves_for_party(payload, party_index)
    saves_by_id.update(_all_saves_by_id(payload))
    campaign_id = _campaign_id(instance)
    formation_saves, source = _resolve_modron_formation_saves(
        payload,
        party_index=party_index,
        campaign_id=campaign_id,
    )

    name_map = hero_name_map_from_champion_config()
    slots: list[FormationHotkeySlot] = []
    profile_by_hotkey = (
        dict(zip(HOTKEY_LABELS, profile_names, strict=True)) if profile_names else {}
    )

    for hotkey, slot_key in zip(HOTKEY_LABELS, SLOT_KEYS, strict=True):
        save_id: int | None = None
        save: dict[str, Any] | None = None
        profile_name = profile_by_hotkey.get(hotkey)
        if profile_name:
            save = _save_by_name(saves_by_id, profile_name)
        if save is None and formation_saves:
            save_id = _parse_int(formation_saves.get(slot_key))
            save = saves_by_id.get(save_id) if save_id is not None else None
        slots.append(_slot_from_save(hotkey, save, save_id=save_id, name_map=name_map))

    resolved_source = source
    if any(profile_by_hotkey.values()):
        resolved_source = "profile" if source == "none" else f"{source}+profile"

    return FormationHotkeys(party_index=party_index, slots=tuple(slots), source=resolved_source)


# Preferred Idle Champions gem-farm save titles (exact match, case-insensitive).
PREFERRED_FORMATION_NAMES: dict[str, tuple[str, ...]] = {
    "Q": ("speed 2.0", "speed2.0", "speedgemchest2"),
    "W": ("speedgemnight2-bbeg", "speedgemnight2", "speedgem night"),
    "E": ("speed zonder briv", "hank speed zonder briv"),
}


def suggest_formation_names(
    names: list[str],
    *,
    known: tuple[str | None, str | None, str | None] = (None, None, None),
) -> tuple[str | None, str | None, str | None]:
    """Fill missing Q/W/E names from saved-formation titles when API slots are incomplete."""
    q_name, w_name, e_name = known
    available = [n for n in names if n]
    by_lower = {n.casefold(): n for n in available}

    def _preferred(hotkey: str, *, exclude: set[str]) -> str | None:
        for candidate in PREFERRED_FORMATION_NAMES.get(hotkey, ()):
            match = by_lower.get(candidate.casefold())
            if match and match not in exclude:
                return match
        return None

    def _best(tokens: tuple[str, ...], *, exclude: set[str], require: tuple[str, ...] = ()) -> str | None:
        best_name: str | None = None
        best_score = -1
        for name in available:
            if name in exclude:
                continue
            lower = name.casefold()
            if require and not all(token in lower for token in require):
                continue
            score = sum(1 for token in tokens if token in lower)
            if score > best_score:
                best_score = score
                best_name = name
        return best_name if best_score > 0 else None

    used: set[str] = {n for n in (q_name, w_name, e_name) if n}
    if not q_name:
        q_name = _preferred("Q", exclude=used) or _best(("speed", "2.0"), exclude=used)
        if q_name and "zonder" in q_name.casefold():
            alt = _preferred("Q", exclude=used | {q_name}) or _best(("speed",), exclude=used | {q_name})
            if alt and "zonder" not in alt.casefold():
                q_name = alt
        if q_name:
            used.add(q_name)
    if not w_name:
        w_name = _preferred("W", exclude=used) or _best(("bbeg", "stack", "widdle", "night"), exclude=used)
        if w_name:
            used.add(w_name)
    if not e_name:
        e_name = _preferred("E", exclude=used) or _best(
            ("zonder", "briv"),
            exclude=used,
            require=("zonder",),
        )
        if e_name is None:
            e_name = _best(("zonder", "swap", "dash"), exclude=used)
    return q_name, w_name, e_name


def format_hotkey_line(slot: FormationHotkeySlot, *, max_names: int = 4) -> str:
    if slot.save_name:
        label = slot.save_name
    elif slot.save_id is not None:
        label = f"onbekend (save #{slot.save_id})"
    else:
        label = "niet gekoppeld"

    if slot.champion_names:
        shown = ", ".join(slot.champion_names[:max_names])
        extra = len(slot.champion_names) - max_names
        if extra > 0:
            shown = f"{shown} +{extra}"
        return f"{slot.hotkey}: {label} ({shown})"
    return f"{slot.hotkey}: {label}"


def format_hotkeys_summary(hotkeys: FormationHotkeys | None) -> str | None:
    if hotkeys is None:
        return None
    lines = [format_hotkey_line(slot) for slot in hotkeys.slots]
    if hotkeys.source.startswith("fallback_party_"):
        lines.append(f"(bindings via party {hotkeys.source.removeprefix('fallback_party_')})")
    elif hotkeys.source.startswith("campaign_"):
        lines.append(f"(bindings via campaign {hotkeys.source.removeprefix('campaign_')})")
    elif "+profile" in hotkeys.source:
        lines.append("(deels uit profile)")
    elif hotkeys.source == "profile":
        lines.append("(uit profile)")
    elif hotkeys.source == "none":
        lines.append("(Q/W/E niet in API — kies teams hieronder)")
    if any(
        slot.save_id is not None and not slot.save_name
        for slot in hotkeys.slots
    ):
        lines.append("(onbekende save: kies team handmatig in dropdown)")
    return "\n".join(lines)
