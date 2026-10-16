"""Detect which ultimate hotkeys (1-9, 0) are ready from getuserdetails."""



from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int

# Seat 1..10 → hotkeys "1".."9","0". Seats 11-12 have no number hotkey.

_SEAT_TO_KEY = {

    1: "1",

    2: "2",

    3: "3",

    4: "4",

    5: "5",

    6: "6",

    7: "7",

    8: "8",

    9: "9",

    10: "0",

}



# Seed: core / common champions (datamined ultimate attack ids).

_SEED_ULTIMATES: dict[int, list[int]] = {

    1: [2],

    2: [4],

    3: [6],

    4: [8],

    5: [10],

    6: [12],

    7: [14],

    8: [16],

    9: [18],

    10: [20],

    11: [24],

    12: [28],

    43: [279],  # Spurt

    58: [605],  # Briv

    147: [745],  # Gale

    173: [941],  # Raistlin

}





def _config_path() -> Path:

    if getattr(sys, "frozen", False):

        return Path(sys.executable).resolve().parent / "config" / "ultimate_attacks.json"

    return Path(__file__).resolve().parent.parent / "config" / "ultimate_attacks.json"





def _load_saved_ultimates() -> dict[int, list[int]]:

    path = _config_path()

    try:

        raw = json.loads(path.read_text(encoding="utf-8"))

    except (OSError, json.JSONDecodeError, TypeError):

        return {}

    if not isinstance(raw, dict):

        return {}

    out: dict[int, list[int]] = {}

    for key, value in raw.items():

        hero_id = _parse_int(key)

        if hero_id is None:

            continue

        ids: list[int] = []

        if isinstance(value, list):

            for item in value:

                attack_id = _parse_int(item)

                if attack_id is not None and attack_id > 0:

                    ids.append(attack_id)

        else:

            attack_id = _parse_int(value)

            if attack_id is not None and attack_id > 0:

                ids.append(attack_id)

        if ids:

            out[hero_id] = ids

    return out





def _ultimates_from_events(payload: dict[str, Any]) -> dict[int, list[int]]:

    details = payload.get("details")

    if not isinstance(details, dict):

        return {}

    out: dict[int, list[int]] = {}

    events = details.get("events_details")

    if isinstance(events, dict):

        for entry in events.get("champion_details") or []:

            if not isinstance(entry, dict):

                continue

            hero_id = _parse_int(entry.get("hero_id"))

            props = entry.get("event_properties")

            if hero_id is None or not isinstance(props, dict):

                continue

            ids: list[int] = []

            for raw in props.get("ultimate_attack_ids") or []:

                attack_id = _parse_int(raw)

                if attack_id is not None and attack_id > 0:

                    ids.append(attack_id)

            if ids:

                out[hero_id] = ids

    return out





def _ultimates_from_defines(payload: dict[str, Any]) -> dict[int, list[int]]:

    """Parse set_ultimate_attack,<id> from upgrade_defines when present."""

    defines = payload.get("defines")

    if not isinstance(defines, dict):

        return {}

    upgrades = defines.get("upgrade_defines")

    if not isinstance(upgrades, list):

        return {}

    out: dict[int, list[int]] = {}

    for entry in upgrades:

        if not isinstance(entry, dict):

            continue

        if entry.get("upgrade_type") != "unlock_ultimate":

            continue

        hero_id = _parse_int(entry.get("hero_id"))

        if hero_id is None:

            continue

        effect = str(entry.get("effect") or "")

        if not effect.startswith("set_ultimate_attack,"):

            continue

        attack_id = _parse_int(effect.split(",", 1)[1])

        if attack_id is None or attack_id <= 0:

            continue

        out.setdefault(hero_id, []).append(attack_id)

    return out





def _ultimates_from_payload(payload: dict[str, Any]) -> dict[int, list[int]]:

    return _merge_ultimate_maps(

        _ultimates_from_events(payload),

        _ultimates_from_defines(payload),

    )





def _merge_ultimate_maps(*maps: dict[int, list[int]]) -> dict[int, list[int]]:

    merged: dict[int, list[int]] = {}

    for mapping in maps:

        for hero_id, ids in mapping.items():

            if ids:

                merged[hero_id] = list(ids)

    return merged





def _merged_ultimates(payload: dict[str, Any]) -> dict[int, list[int]]:

    return _merge_ultimate_maps(

        _SEED_ULTIMATES,

        _load_saved_ultimates(),

        _ultimates_from_payload(payload),

    )





def _active_instance(payload: dict[str, Any]) -> dict[str, Any] | None:

    details = payload.get("details")

    if not isinstance(details, dict):

        return None

    active_id = _parse_int(details.get("active_game_instance_id"))

    instances = details.get("game_instances")

    if not isinstance(instances, list):

        return None

    for inst in instances:

        if isinstance(inst, dict) and _parse_int(inst.get("game_instance_id")) == active_id:

            return inst

    if instances and isinstance(instances[0], dict):

        return instances[0]

    return None





def _seat_by_hero(instance: dict[str, Any]) -> dict[int, int]:
    """hero_id -> seat from ``hero_in_seats`` (includes benched seat holders)."""
    mapping: dict[int, int] = {}
    raw = instance.get("hero_in_seats")
    if not isinstance(raw, dict):
        return mapping
    for seat_raw, hero_raw in raw.items():
        seat = _parse_int(seat_raw)
        hero_id = _parse_int(hero_raw)
        if seat is None or hero_id is None or hero_id <= 0:
            continue
        if 1 <= seat <= 12:
            mapping[hero_id] = seat
    return mapping


def _permanent_seat_by_hero() -> dict[int, int]:
    try:
        from ic_gamedata.specialization_data import hero_seat_id_map_from_cached_definitions
    except ImportError:
        return {}
    return hero_seat_id_map_from_cached_definitions()


def _hotkey_seats_for_heroes(
    hero_ids: list[int],
    seat_by_hero: dict[int, int],
) -> dict[int, int]:
    """seat -> hero_id for formation champions who have a number hotkey (1–0)."""
    defs = _permanent_seat_by_hero()
    seats: dict[int, int] = {}
    for hero_id in hero_ids:
        seat = seat_by_hero.get(hero_id)
        if seat is None:
            seat = defs.get(hero_id)
        if seat is not None and 1 <= seat <= 10:
            seats[seat] = hero_id
    return seats


def _formation_seats(
    instance: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[int, int]:
    """seat -> hero_id for champions on the live formation who can ult via 1–0.

    ``hero_in_seats`` lists one champion per seat even when they are benched.
    A populated formation grid is authoritative; a sparse grid (0–1 heroes) falls
    back to seats 1–10 so a mid-update payload does not blank the hotkeys.
    """
    seat_by_hero = _seat_by_hero(instance)
    live_ids: list[int] = []
    if payload is not None:
        try:
            from ic_gamedata.formation_seats import live_formation_hero_ids
        except ImportError:
            live_ids = []
        else:
            live_ids = [hid for hid in live_formation_hero_ids(payload) if hid > 0]
    if len(live_ids) >= 2:
        return _hotkey_seats_for_heroes(live_ids, seat_by_hero)
    return {
        seat: hero_id
        for hero_id, seat in seat_by_hero.items()
        if 1 <= seat <= 10
    }





def _cooldown_map(payload: dict[str, Any]) -> dict[int, int]:

    details = payload.get("details")

    if not isinstance(details, dict):

        return {}

    out: dict[int, int] = {}

    for entry in details.get("attack_cooldowns") or []:

        if not isinstance(entry, dict):

            continue

        attack_id = _parse_int(entry.get("attack_id"))

        remaining = _parse_int(entry.get("cooldown_remaining"))

        if attack_id is None:

            continue

        out[attack_id] = max(0, remaining or 0)

    return out





def _ultimate_cooldown_remaining(

    attack_ids: list[int],

    cooldowns: dict[int, int],

) -> int | None:

    """

    Remaining cooldown seconds for mapped ultimate attack ids, or None if unknown.



    Unknown when no mapping exists or any mapped attack_id is missing from the

    live cooldown list (we cannot verify readiness conservatively).

    """

    if not attack_ids:

        return None

    remainings: list[int] = []

    for attack_id in attack_ids:

        if attack_id not in cooldowns:

            return None

        remainings.append(cooldowns[attack_id])

    return max(remainings)





def _attack_ready(attack_ids: list[int], cooldowns: dict[int, int]) -> bool:

    remaining = _ultimate_cooldown_remaining(attack_ids, cooldowns)

    return remaining == 0





def formation_ability_keys(payload: dict[str, Any]) -> list[str]:

    """Hotkeys for champions on the live formation who can ult via 1–0."""

    instance = _active_instance(payload)

    if instance is None:

        return []

    seats = _formation_seats(instance, payload)

    keys: list[str] = []

    for seat in sorted(seats):

        key = _SEAT_TO_KEY.get(seat)

        if key is not None:

            keys.append(key)

    return keys





def ability_status(payload: dict[str, Any]) -> tuple[list[str], str]:

    """

    Return (ready_hotkeys, status_text) for seats 1-10.



    Status lists every occupied hotkey with remaining cooldown or 'klaar'.

    Unmapped champions are shown as 'onbekend' and are never treated as ready.

    """

    instance = _active_instance(payload)

    if instance is None:

        return [], "no active party"



    cooldowns = _cooldown_map(payload)

    if not cooldowns:

        keys = formation_ability_keys(payload)

        if not keys:

            return [], "no champions on hotkeys 1-0"

        return keys, "ready (no cooldown data): " + ",".join(keys)



    ultimates = _merged_ultimates(payload)

    seats = _formation_seats(instance, payload)

    ready: list[str] = []

    parts: list[str] = []



    for seat in sorted(seats):

        key = _SEAT_TO_KEY.get(seat)

        if key is None:

            continue

        hero_id = seats[seat]

        attack_ids = ultimates.get(hero_id) or []

        remaining = _ultimate_cooldown_remaining(attack_ids, cooldowns)

        if remaining is None:

            parts.append(f"{key}: unknown")

            continue

        if remaining > 0:

            parts.append(f"{key}: {remaining}s")

        else:

            ready.append(key)

            parts.append(f"{key}: ready")



    if not parts:

        return [], "no champions on hotkeys 1-0"

    return ready, "; ".join(parts)





def ready_ability_keys(payload: dict[str, Any]) -> list[str]:

    """

    Return hotkeys (\"1\"..\"9\",\"0\") whose ultimate is verified ready.



    Unmapped champions or missing cooldown entries are skipped (conservative).

    """

    ready, _status = ability_status(payload)

    return ready





def persist_ultimates_from_payload(payload: dict[str, Any]) -> None:

    """Merge learned ultimate ids into config/ultimate_attacks.json for next runs."""

    learned = _ultimates_from_payload(payload)

    if not learned:

        return

    merged = _merge_ultimate_maps(_SEED_ULTIMATES, _load_saved_ultimates(), learned)

    path = _config_path()

    try:

        path.parent.mkdir(parents=True, exist_ok=True)

        serializable = {str(k): v for k, v in sorted(merged.items())}

        path.write_text(json.dumps(serializable, indent=2) + "\n", encoding="utf-8")

    except OSError:

        return


def _attack_name_by_id() -> dict[int, str]:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data
    except ImportError:
        return {}
    data = cached_definitions_data()
    attacks = data.get("attack_defines")
    if not isinstance(attacks, list):
        return {}
    out: dict[int, str] = {}
    for item in attacks:
        if not isinstance(item, dict):
            continue
        attack_id = _parse_int(item.get("id"))
        name = str(item.get("name") or "").strip()
        if attack_id is None or not name:
            continue
        out[attack_id] = name
    return out


def _hero_ultimate_attack_id() -> dict[int, int]:
    try:
        from ic_gamedata.specialization_data import cached_definitions_data
    except ImportError:
        return {}
    heroes = cached_definitions_data().get("hero_defines")
    if not isinstance(heroes, list):
        return {}
    out: dict[int, int] = {}
    for item in heroes:
        if not isinstance(item, dict):
            continue
        hero_id = _parse_int(item.get("id"))
        attack_id = _parse_int(item.get("ultimate_attack_id"))
        if hero_id is None or attack_id is None or attack_id <= 0:
            continue
        out[hero_id] = attack_id
    return out


def _hero_display_name(hero_id: int) -> str:
    try:
        from ic_gamedata.specialization_data import (
            hero_name_map_from_cached_definitions,
            hero_name_map_from_champion_config,
        )
    except ImportError:
        return f"Hero {hero_id}"
    name = hero_name_map_from_champion_config().get(hero_id)
    if name:
        return name
    name = hero_name_map_from_cached_definitions().get(hero_id)
    if name:
        return name
    return f"Hero {hero_id}"


def _call_uggie_name_by_hero() -> dict[int, str]:
    """Fallbacks ultimates also call Uggie; the hotkey UI shows Call Uggie."""
    try:
        from ic_gamedata.specialization_data import (
            cached_definitions_data,
            hero_name_map_from_cached_definitions,
        )
    except ImportError:
        return {}
    data = cached_definitions_data()
    names = hero_name_map_from_cached_definitions()
    attack_names = _attack_name_by_id()
    out: dict[int, str] = {}

    effect_hero: dict[int, int] = {}
    for upgrade in data.get("upgrade_defines") or []:
        if not isinstance(upgrade, dict):
            continue
        hero_id = _parse_int(upgrade.get("hero_id"))
        effect = str(upgrade.get("effect") or "")
        if hero_id is None or not effect.startswith("effect_def,"):
            continue
        effect_id = _parse_int(effect.split(",", 1)[1])
        if effect_id is not None:
            effect_hero[effect_id] = hero_id

    for effect in data.get("effect_defines") or []:
        if not isinstance(effect, dict):
            continue
        effect_id = _parse_int(effect.get("id"))
        if effect_id is None:
            continue
        hero_id = effect_hero.get(effect_id)
        if hero_id is None:
            continue
        for key in effect.get("effect_keys") or []:
            if not isinstance(key, dict):
                continue
            call_id = _parse_int(key.get("call_uggie_ult_id"))
            if call_id is None:
                continue
            name = attack_names.get(call_id)
            if name:
                out[hero_id] = name

    for attack in data.get("attack_defines") or []:
        if not isinstance(attack, dict):
            continue
        if str(attack.get("name") or "").strip() != "Call Uggie":
            continue
        desc = str(attack.get("description") or "")
        for hero_id, hero_name in names.items():
            if desc.startswith(f"{hero_name} "):
                out.setdefault(hero_id, "Call Uggie")
                break
    return out


def _ultimate_display_name(hero_id: int, payload: dict[str, Any]) -> str:
    # Fallbacks: number key moves Uggie; game/UI treats that as Call Uggie.
    call_uggie = _call_uggie_name_by_hero().get(hero_id)
    if call_uggie:
        return call_uggie
    attack_id = _hero_ultimate_attack_id().get(hero_id)
    if attack_id is None:
        ids = _merged_ultimates(payload).get(hero_id) or []
        attack_id = ids[0] if ids else None
    if attack_id is None:
        return "Ultimate"
    return _attack_name_by_id().get(attack_id) or "Ultimate"


def ability_hotkey_labels(payload: dict[str, Any]) -> dict[str, str]:
    """Return hotkey → \"Champion - Ultimate\" for formation champions on seats 1–10."""
    instance = _active_instance(payload)
    if instance is None:
        return {}
    seats = _formation_seats(instance, payload)
    labels: dict[str, str] = {}
    for seat, hero_id in seats.items():
        key = _SEAT_TO_KEY.get(seat)
        if key is None:
            continue
        hero_name = _hero_display_name(hero_id)
        ultimate = _ultimate_display_name(hero_id, payload)
        labels[key] = f"{hero_name} - {ultimate}"
    return labels

