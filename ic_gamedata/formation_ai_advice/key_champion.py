"""Adventure ``key_champion`` rules: required presence vs NPC overlay slots.

Idle Champions ``game_changes`` type ``key_champion`` (e.g. Tanking Expectations)
unlocks a matching champion into the formation. Observed API/live contract:

- A champion matching ``by_tags`` / ``by_seat`` / ``hero_ids`` **cannot be
  removed** (replacement lock / must remain). That is independent of where
  they currently stand on the formation grid.
- ``force_slot`` + ``slot_id`` reserve a **technical formation index** for the
  adventure overlay NPC (often named ``Shadow`` with a ``graphic``). That seat
  is blocked for champion placement. It is **not** automatic proof that the
  real key champion is position-locked onto that NPC seat.
- Live runs can show the real champion on one ``position_id`` and the Shadow
  NPC on another (e.g. Havilar on 10, Shadow on 3). Do not overwrite the party
  position or invent ``locked_position_id`` from the NPC binding alone.
- Other champions matching the complementary ban (e.g. ``only_allow !tanking``)
  stay disallowed — only the seated key champion is the roster exception.

A true champion ``position_locked`` / ``locked_position_id`` requires separate
source evidence beyond ``force_slot``/``slot_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ic_gamedata.parsing import parse_int as _parse_int

_KEY_CHAMPION_SOURCE = "defines.adventure_defines.game_changes.key_champion"


@dataclass(frozen=True)
class KeyChampionRule:
    """One ``key_champion`` game_change, optionally with a resolved slot."""

    required_tags: frozenset[str] = frozenset()
    banned_tags: frozenset[str] = frozenset()  # unused for match; reserved
    required_seat_ids: frozenset[int] = frozenset()
    hero_ids: frozenset[int] = frozenset()
    force_slot: bool = False
    slot_index: int | None = None
    position_id: int | None = None
    name: str | None = None
    graphic_id: int | None = None
    raw_by_tags: str | None = None
    source: str = _KEY_CHAMPION_SOURCE

    @property
    def has_matcher(self) -> bool:
        return bool(self.required_tags or self.required_seat_ids or self.hero_ids)


@dataclass(frozen=True)
class KeyChampionBinding:
    """Party champion bound to a key_champion rule."""

    champion_id: int
    rule: KeyChampionRule
    replacement_locked: bool = True
    must_remain_in_party: bool = True
    position_locked: bool = False
    locked_position_id: int | None = None

    def as_export_fields(self) -> dict[str, Any]:
        """Machine-readable lock fields for ADVICE_REQUEST party rows.

        Provenance stays compact for the 17k clipboard budget: kind + matcher
        + overlay ``force_slot``/``slot_id`` (NPC reservation — not champion
        ``locked_position_id``).
        """
        prov: dict[str, Any] = {"kind": "adventure_key_champion"}
        if self.rule.raw_by_tags:
            prov["by_tags"] = self.rule.raw_by_tags
        elif self.rule.required_tags:
            prov["by_tags"] = ",".join(sorted(self.rule.required_tags))
        if self.rule.required_seat_ids:
            prov["by_seat"] = sorted(self.rule.required_seat_ids)
        if self.rule.hero_ids:
            prov["hero_ids"] = sorted(self.rule.hero_ids)
        # Overlay reservation only — consumers must not treat these as
        # party[].locked_position_id without separate position_locked evidence.
        if self.rule.force_slot:
            prov["force_slot"] = True
        if self.rule.slot_index is not None:
            prov["slot_id"] = self.rule.slot_index
        out: dict[str, Any] = {
            "locked": True,
            "lock_reason": "adventure_key_champion",
            "replacement_locked": True,
            "must_remain_in_party": True,
            "position_locked": bool(self.position_locked),
            "lock_provenance": prov,
        }
        if self.position_locked and isinstance(self.locked_position_id, int):
            out["locked_position_id"] = self.locked_position_id
        return out


def _parse_tag_list(raw: str | None) -> tuple[frozenset[str], frozenset[str]]:
    """Split ``by_tags.tags`` into required vs banned (!prefix) tags."""
    required: set[str] = set()
    banned: set[str] = set()
    if not isinstance(raw, str) or not raw.strip():
        return frozenset(), frozenset()
    for part in raw.replace(";", ",").split(","):
        token = part.strip()
        if not token:
            continue
        if token.startswith("!"):
            tag = token[1:].strip().casefold()
            if tag:
                banned.add(tag)
        else:
            required.add(token.casefold())
    return frozenset(required), frozenset(banned)


def _hero_tags(hero_id: int) -> frozenset[str]:
    try:
        from ic_gamedata.specialization_data import (
            hero_tags_map_from_cached_definitions,
        )

        tags = hero_tags_map_from_cached_definitions().get(int(hero_id)) or ()
    except Exception:
        tags = ()
    return frozenset(str(t).casefold() for t in tags if t)


def _hero_seat(hero_id: int) -> int | None:
    try:
        from ic_gamedata.specialization_data import (
            hero_seat_id_map_from_cached_definitions,
        )

        seat = hero_seat_id_map_from_cached_definitions().get(int(hero_id))
    except Exception:
        return None
    if isinstance(seat, int) and 1 <= seat <= 12:
        return seat
    return None


def hero_matches_key_champion_rule(hero_id: int, rule: KeyChampionRule) -> bool:
    """True when ``hero_id`` satisfies the key_champion matcher."""
    if not rule.has_matcher:
        return False
    if rule.hero_ids and int(hero_id) in rule.hero_ids:
        return True
    checks: list[bool] = []
    if rule.required_tags:
        checks.append(rule.required_tags.issubset(_hero_tags(hero_id)))
    if rule.required_seat_ids:
        seat = _hero_seat(hero_id)
        checks.append(seat is not None and seat in rule.required_seat_ids)
    if not checks:
        # Only hero_ids was configured and this hero was not listed.
        return False
    return all(checks)


def collect_key_champion_changes(
    adventure_define: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(adventure_define, Mapping):
        return []
    out: list[dict[str, Any]] = []
    for change in adventure_define.get("game_changes") or []:
        if not isinstance(change, Mapping):
            continue
        if str(change.get("type") or "").strip().casefold() != "key_champion":
            continue
        out.append(dict(change))
    return out


def parse_key_champion_rules(
    adventure_define: Mapping[str, Any] | None,
    *,
    index_to_position: Mapping[int, int] | None = None,
) -> list[KeyChampionRule]:
    """Parse ``key_champion`` changes; resolve ``slot_id`` when map provided."""
    rules: list[KeyChampionRule] = []
    for change in collect_key_champion_changes(adventure_define):
        required_tags, banned_tags = frozenset(), frozenset()
        raw_by_tags = None
        by_tags = change.get("by_tags")
        if isinstance(by_tags, dict):
            raw_by_tags = by_tags.get("tags")
            if isinstance(raw_by_tags, str):
                required_tags, banned_tags = _parse_tag_list(raw_by_tags)

        seat_ids: set[int] = set()
        by_seat = change.get("by_seat")
        if isinstance(by_seat, dict):
            seats = by_seat.get("seats")
            if isinstance(seats, list):
                for raw in seats:
                    sid = _parse_int(raw)
                    if sid is not None and 1 <= sid <= 12:
                        seat_ids.add(sid)

        hero_ids: set[int] = set()
        for raw in change.get("hero_ids") or []:
            hid = _parse_int(raw)
            if hid is not None and hid > 0:
                hero_ids.add(hid)

        force_slot = bool(change.get("force_slot"))
        slot_index = _parse_int(change.get("slot_id"))
        position_id = None
        if (
            force_slot
            and slot_index is not None
            and isinstance(index_to_position, Mapping)
        ):
            mapped = index_to_position.get(slot_index)
            if isinstance(mapped, int):
                position_id = int(mapped)

        name = change.get("name")
        name_s = str(name).strip() if name not in (None, "") else None
        graphic_id = _parse_int(change.get("graphic"))

        rule = KeyChampionRule(
            required_tags=required_tags,
            banned_tags=banned_tags,
            required_seat_ids=frozenset(seat_ids),
            hero_ids=frozenset(hero_ids),
            force_slot=force_slot,
            slot_index=slot_index,
            position_id=position_id,
            name=name_s,
            graphic_id=graphic_id,
            raw_by_tags=str(raw_by_tags) if isinstance(raw_by_tags, str) else None,
        )
        if rule.has_matcher or force_slot or slot_index is not None:
            rules.append(rule)
    return rules


def resolve_key_champion_seat_meta(
    payload: Mapping[str, Any],
    adventure_id: int | None,
) -> tuple[frozenset[int], dict[int, dict[str, Any]], tuple[str, ...]]:
    """Forced key_champion slots → technical position_ids + blocker meta.

    Returns ``(position_ids, meta_by_position, warnings)``. Meta uses
    ``type=npc`` when the define supplies a name/graphic overlay (Shadow), else
    ``type=key_champion``. Unresolved ``slot_id`` values are omitted from
    position_ids and reported in warnings — never treated as free.
    """
    from ic_gamedata.adventure_restrictions import _adventure_define
    from ic_gamedata.formation_position_resolve import (
        current_formation_index_map,
        resolve_formation_indices,
    )

    warnings: list[str] = []
    if adventure_id is None:
        return frozenset(), {}, ("no_adventure_id",)

    adv = _adventure_define(dict(payload), adventure_id)
    if adv is None:
        return frozenset(), {}, ("adventure_define_missing",)

    changes = collect_key_champion_changes(adv)
    if not changes:
        return frozenset(), {}, ()

    force_indices: list[int] = []
    meta_by_index: dict[int, dict[str, Any]] = {}
    for change in changes:
        if not bool(change.get("force_slot")):
            continue
        idx = _parse_int(change.get("slot_id"))
        if idx is None:
            warnings.append("key_champion_force_slot_missing_slot_id")
            continue
        force_indices.append(idx)
        blocker: dict[str, Any] = {"type": "npc"}
        name = change.get("name")
        if name not in (None, ""):
            blocker["name"] = str(name)
            blocker["type"] = "npc"
        else:
            blocker["type"] = "key_champion"
        graphic = _parse_int(change.get("graphic"))
        if graphic is not None:
            blocker["graphic_id"] = graphic
        blocker["source"] = _KEY_CHAMPION_SOURCE
        meta_by_index[idx] = blocker

    if not force_indices:
        return frozenset(), {}, tuple(warnings)

    index_map, node_count, layout_warnings = current_formation_index_map(
        payload, adventure_id
    )
    warnings.extend(layout_warnings)
    if not index_map:
        warnings.append("key_champion_no_formation_layout")
        return frozenset(), {}, tuple(dict.fromkeys(warnings))

    mapped = resolve_formation_indices(
        force_indices,
        index_to_position=index_map,
        layout_node_count=node_count,
    )
    warnings.extend(mapped.warnings)
    for idx in mapped.unresolved_indices:
        warnings.append(f"key_champion_slot_unresolved:{idx}")

    meta_by_position: dict[int, dict[str, Any]] = {}
    for idx, pos in mapped.index_to_position.items():
        meta_by_position[int(pos)] = dict(meta_by_index.get(idx) or {"type": "npc"})

    return mapped.position_ids, meta_by_position, tuple(dict.fromkeys(warnings))


def bind_party_key_champions(
    *,
    party_ids: Iterable[int],
    position_by_hero: Mapping[int, int] | None,
    rules: Iterable[KeyChampionRule],
) -> dict[int, KeyChampionBinding]:
    """Bind seated party heroes to key_champion rules (replacement locks).

    ``force_slot`` / resolved NPC ``position_id`` are **not** applied as champion
    ``position_locked`` here — the overlay seat is handled via reserved slot
    states. Preference when multiple party heroes match: first matching party id
    (live ``position_by_hero`` is not overridden).
    """
    party = [int(h) for h in party_ids if isinstance(h, int) or str(h).isdigit()]
    _ = position_by_hero  # kept for call-site compatibility / future evidence
    bindings: dict[int, KeyChampionBinding] = {}

    for rule in rules:
        if not rule.has_matcher:
            continue
        matches = [hid for hid in party if hero_matches_key_champion_rule(hid, rule)]
        if not matches:
            continue
        chosen = matches[0]
        # Never derive champion position_lock from force_slot/NPC overlay alone.
        bindings[chosen] = KeyChampionBinding(
            champion_id=chosen,
            rule=rule,
            replacement_locked=True,
            must_remain_in_party=True,
            position_locked=False,
            locked_position_id=None,
        )
    return bindings


def load_key_champion_bindings_for_party(
    payload: Mapping[str, Any],
    adventure_id: int | None,
    *,
    party_ids: Iterable[int],
    position_by_hero: Mapping[int, int] | None = None,
) -> dict[int, KeyChampionBinding]:
    """End-to-end: define → rules (with slot resolve) → party bindings."""
    from ic_gamedata.adventure_restrictions import _adventure_define
    from ic_gamedata.formation_position_resolve import current_formation_index_map

    if adventure_id is None:
        return {}
    adv = _adventure_define(dict(payload), adventure_id)
    if adv is None:
        return {}
    index_map, _n, _w = current_formation_index_map(payload, adventure_id)
    rules = parse_key_champion_rules(adv, index_to_position=index_map)
    return bind_party_key_champions(
        party_ids=party_ids,
        position_by_hero=position_by_hero,
        rules=rules,
    )
