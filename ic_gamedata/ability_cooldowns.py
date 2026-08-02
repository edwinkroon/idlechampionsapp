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





def _formation_seats(instance: dict[str, Any]) -> dict[int, int]:

    """seat -> hero_id for champions currently selected in the active party."""

    seats: dict[int, int] = {}

    raw = instance.get("hero_in_seats")

    if not isinstance(raw, dict):

        return seats

    for seat_raw, hero_raw in raw.items():

        seat = _parse_int(seat_raw)

        hero_id = _parse_int(hero_raw)

        if seat is None or hero_id is None or hero_id <= 0:

            continue

        if 1 <= seat <= 10:

            seats[seat] = hero_id

    return seats





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

    """Hotkeys for seats 1-10 on the active party (no cooldown filter)."""

    instance = _active_instance(payload)

    if instance is None:

        return []

    seats = _formation_seats(instance)

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

        return [], "geen actieve party"



    cooldowns = _cooldown_map(payload)

    if not cooldowns:

        keys = formation_ability_keys(payload)

        if not keys:

            return [], "geen champions op toetsen 1-0"

        return keys, "klaar (geen cooldown-data): " + ",".join(keys)



    ultimates = _merged_ultimates(payload)

    seats = _formation_seats(instance)

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

            parts.append(f"{key}: onbekend")

            continue

        if remaining > 0:

            parts.append(f"{key}: {remaining}s")

        else:

            ready.append(key)

            parts.append(f"{key}: klaar")



    if not parts:

        return [], "geen champions op toetsen 1-0"

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

