"""Central user-facing advice goals for UI, prompts, and JSON exports.

Single source of truth for labels, help text, primary metrics, and priorities
so Formation / Party Advisor / Specializations and clipboard exports cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

UserGoalId = Literal[
    "push",
    "quest_clear",
    "gem_farm",
    "favor_farm",
    "custom_task",
]
LegacyGoalId = Literal["bud", "gold", "speed"]
ScoringLane = Literal["bud", "gold", "speed"]
FavorHorizon = Literal["per_run", "per_time", "unknown"]
PlayMode = Literal["foreground", "background", "offline", "unknown"]
AutoReset = Literal["yes", "no", "unknown"]

USER_GOAL_IDS: tuple[UserGoalId, ...] = (
    "push",
    "quest_clear",
    "gem_farm",
    "favor_farm",
    "custom_task",
)
LEGACY_GOAL_IDS: frozenset[str] = frozenset({"bud", "gold", "speed"})


@dataclass(frozen=True)
class GoalDefinition:
    id: UserGoalId
    label: str
    description: str
    primary_metric: str
    priorities: tuple[str, ...]


@dataclass(frozen=True)
class GoalMigration:
    """Result of reading a stored goal preference."""

    goal_id: UserGoalId | None
    needs_confirm: bool
    legacy_id: str | None
    proposed_id: UserGoalId | None
    message: str | None


GOAL_DEFINITIONS: dict[UserGoalId, GoalDefinition] = {
    "push": GoalDefinition(
        id="push",
        label="Push",
        description="Bereik een zo hoog mogelijk gebied.",
        primary_metric="highest_reachable_area",
        priorities=(
            "Respecteer partyregels en restricties.",
            "Optimaliseer voortgang op hoge gebieden.",
            "Weeg damage/BUD en overleving samen.",
            "Neem relevante opbouwmechanics en fasewissels mee.",
            "Gebruik speed als ondersteunend middel, niet als hoofddoel.",
            "Claim geen exact optimum zonder voldoende gegevens.",
        ),
    ),
    "quest_clear": GoalDefinition(
        id="quest_clear",
        label="Quest / variant voltooien",
        description="Haal het vereiste gebied of voltooi de opdracht.",
        primary_metric="reach_end_condition_then_minimize_time",
        priorities=(
            "Respecteer alle adventure-/variant-/patronvoorwaarden.",
            "Zorg dat de eindvoorwaarde haalbaar is.",
            "Optimaliseer daarna de tijd tot voltooiing.",
            "Damage en overleving hoeven voldoende te zijn voor het doelgebied; "
            "maximale BUD is geen zelfstandig doel.",
            "Houd rekening met veranderende restricties als die bekend zijn.",
            "Optimaliseer niet onnodig voor gebieden voorbij het questdoel.",
        ),
    ),
    "gem_farm": GoalDefinition(
        id="gem_farm",
        label="Gems verzamelen",
        description="Verzamel zoveel mogelijk gems per uur.",
        primary_metric="gems_per_hour",
        priorities=(
            "Respecteer harde partyregels.",
            "Optimaliseer gemopbrengst over de volledige herhaalcyclus.",
            "Weeg snelheid, gemopbrengst, opstarttijd, gebiedsovergangen en resets "
            "mee voor zover de benodigde mechanics bekend zijn.",
            "Damage en overleving moeten voldoende zijn voor de farmroute.",
            "Maximaal gebied en maximale BUD zijn geen zelfstandig doel.",
            "Meer areas per uur is niet automatisch meer gems per uur.",
            "Houd rekening met voorgrond/achtergrond/offline als dat bekend is.",
            "Claim geen exacte gems/uur zonder voldoende gegevens of metingen.",
        ),
    ),
    "favor_farm": GoalDefinition(
        id="favor_farm",
        label="Favor verzamelen",
        description="Vergroot de favor van de gekozen campagne.",
        primary_metric="favor_yield_for_chosen_horizon",
        priorities=(
            "Respecteer harde partyregels.",
            "Beoordeel voortgang en goudverzameling in samenhang.",
            "Verwar hoogste gebied niet met gegarandeerd hoogste favoropbrengst.",
            "Onderscheid eventuele push- en goldfarmopstellingen als de mechanics "
            "dat onderbouwen en de toegestane wijzigingen het toelaten.",
            "Gold find is een middel, geen garantie van optimale favor per uur.",
            "Claim geen exacte favorwinst zonder voldoende gegevens.",
        ),
    ),
    "custom_task": GoalDefinition(
        id="custom_task",
        label="Specifieke taak",
        description="Werk aan een achievement, championstack of andere concrete opdracht.",
        primary_metric="user_task_condition",
        priorities=(
            "Respecteer harde partyregels.",
            "Optimaliseer de concrete taak.",
            "Behoud champions die de taak vereist.",
            "Neem niet automatisch push- of gemfarmprioriteiten over.",
            "Meld ontbrekende beslisvoorwaarden in plaats van ze te verzinnen.",
        ),
    ),
}

GOAL_COMBO_ITEMS: tuple[tuple[str, UserGoalId], ...] = tuple(
    (GOAL_DEFINITIONS[gid].label, gid) for gid in USER_GOAL_IDS
)

_SCORING_LANE: dict[str, ScoringLane] = {
    "push": "bud",
    "quest_clear": "bud",
    "gem_farm": "speed",
    "favor_farm": "gold",
    "custom_task": "bud",
    # Legacy technical lanes (scoring only; not silent user-goal migration).
    "bud": "bud",
    "gold": "gold",
    "speed": "speed",
}


def is_user_goal_id(value: str | None) -> bool:
    return value in USER_GOAL_IDS


def goal_definition(goal_id: str) -> GoalDefinition:
    if goal_id in GOAL_DEFINITIONS:
        return GOAL_DEFINITIONS[goal_id]  # type: ignore[index]
    raise KeyError(f"Onbekend adviesdoel: {goal_id}")


def scoring_lane(goal_id: str | None) -> ScoringLane:
    """Map a user goal (or legacy lane) to the existing optimizer scoring lane.

    This is intentionally *not* a user-facing migration: gold≠favor, speed≠gems.
    """
    if not goal_id:
        return "bud"
    return _SCORING_LANE.get(str(goal_id), "bud")


def migrate_stored_goal(raw: str | None) -> GoalMigration:
    """Map a QSettings value to a user goal without silent incorrect 1:1 mapping."""
    value = str(raw or "").strip()
    if not value:
        return GoalMigration(
            goal_id="push",
            needs_confirm=False,
            legacy_id=None,
            proposed_id="push",
            message=None,
        )
    if value in USER_GOAL_IDS:
        return GoalMigration(
            goal_id=value,  # type: ignore[arg-type]
            needs_confirm=False,
            legacy_id=None,
            proposed_id=None,
            message=None,
        )
    if value == "bud":
        return GoalMigration(
            goal_id="push",
            needs_confirm=True,
            legacy_id="bud",
            proposed_id="push",
            message=(
                "Eerder doel was ‘BUD / damage’. Voorgesteld nieuw doel: Push — "
                "bevestig of kies een ander doel."
            ),
        )
    if value == "gold":
        return GoalMigration(
            goal_id=None,
            needs_confirm=True,
            legacy_id="gold",
            proposed_id=None,
            message=(
                "Eerder doel was ‘Gold income’. Kies een nieuw doel "
                "(niet automatisch Favor verzamelen)."
            ),
        )
    if value == "speed":
        return GoalMigration(
            goal_id=None,
            needs_confirm=True,
            legacy_id="speed",
            proposed_id=None,
            message=(
                "Eerder doel was ‘Speed / areas’. Kies een nieuw doel "
                "(niet automatisch Gems verzamelen)."
            ),
        )
    return GoalMigration(
        goal_id=None,
        needs_confirm=True,
        legacy_id=value,
        proposed_id=None,
        message=f"Onbekend opgeslagen doel ‘{value}’. Kies een nieuw doel.",
    )


def legacy_label(legacy_id: str | None) -> str:
    return {
        "bud": "BUD / damage",
        "gold": "Gold income",
        "speed": "Speed / areas",
    }.get(str(legacy_id or ""), str(legacy_id or "onbekend"))


def _parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _unknown_token(value: Any, *, allowed: frozenset[str] | set[str]) -> str:
    text = str(value or "unknown").strip().casefold()
    if text in allowed:
        return text
    return "unknown"


def extract_live_goal_context(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Read lightweight adventure/area context without inventing values."""
    if not isinstance(payload, dict):
        return {
            "current_area": None,
            "adventure_area_goal": None,
            "modron_area_goal": None,
            "campaign_id": None,
            "campaign_name": None,
            "adventure_id": None,
            "adventure_name": None,
        }
    instance = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    # Prefer active game instance when present.
    try:
        from ic_gamedata.party_advisor_formation import _active_game_instance

        active = _active_game_instance(payload) or {}
        if isinstance(active, dict) and active:
            instance = active
    except Exception:
        pass

    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    current_area = _parse_int(instance.get("current_area") or instance.get("area"))
    adventure_id = _parse_int(
        instance.get("current_adventure_id") or details.get("current_adventure_id")
    )
    campaign_id = _parse_int(
        instance.get("current_campaign_id")
        or instance.get("campaign_id")
        or details.get("current_campaign_id")
    )
    campaign_name = None
    adventure_name = None
    adventure_area_goal = None
    try:
        from ic_gamedata.adventure_restrictions import _adventure_define

        adv = _adventure_define(payload, adventure_id) if adventure_id else None
        if isinstance(adv, dict):
            adventure_name = str(adv.get("name") or "") or None
            for key in ("area_goal", "required_area", "goal_area", "end_area"):
                parsed = _parse_int(adv.get(key))
                if parsed is not None and parsed > 0:
                    adventure_area_goal = parsed
                    break
    except Exception:
        pass

    modron_area_goal = None
    try:
        from ic_gamedata.modron_area_goal import resolve_modron_area_goal

        party_index = _parse_int(
            instance.get("current_party_index")
            or details.get("current_party_index")
            or instance.get("party_index")
        )
        modron_area_goal = resolve_modron_area_goal(
            instance if isinstance(instance, dict) else None,
            payload,
            party_index=party_index,
        )
    except Exception:
        pass

    if campaign_id is not None:
        try:
            camps = details.get("campaigns") or payload.get("campaigns")
            if isinstance(camps, list):
                for row in camps:
                    if not isinstance(row, dict):
                        continue
                    if _parse_int(row.get("id") or row.get("campaign_id")) == campaign_id:
                        campaign_name = str(row.get("name") or "") or None
                        break
        except Exception:
            pass

    return {
        "current_area": current_area,
        "adventure_area_goal": adventure_area_goal,
        "modron_area_goal": modron_area_goal,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "adventure_id": adventure_id,
        "adventure_name": adventure_name,
    }


def validate_goal_parameters(
    goal_id: str,
    parameters: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Return (ok, error_message). Only custom_task has a hard requirement."""
    params = parameters if isinstance(parameters, dict) else {}
    if goal_id == "custom_task":
        task = str(params.get("task_description") or "").strip()
        if not task:
            return False, "Specifieke taak vereist een taakomschrijving."
    return True, None


def build_goal_parameters(
    goal_id: str,
    *,
    user_parameters: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Merge user inputs with live context. Unknown stays unknown (not 0/false)."""
    user = dict(user_parameters or {})
    live = extract_live_goal_context(payload)
    missing: list[str] = []
    params: dict[str, Any] = {}

    if goal_id == "push":
        params["current_area"] = live.get("current_area")
        params["highest_area_hint"] = live.get("current_area")
        if live.get("current_area") is None:
            missing.append("current_area")
    elif goal_id == "quest_clear":
        user_area = _parse_int(user.get("required_area"))
        user_end = str(user.get("end_condition") or "").strip() or None
        auto_area = live.get("adventure_area_goal")
        if user_area is not None and user_area > 0:
            params["required_area"] = user_area
            params["required_area_source"] = "user"
        elif isinstance(auto_area, int) and auto_area > 0:
            params["required_area"] = auto_area
            params["required_area_source"] = "adventure_data"
        else:
            params["required_area"] = None
            params["required_area_source"] = "unknown"
            missing.append("required_area")
        if user_end:
            params["end_condition"] = user_end
            params["end_condition_source"] = "user"
        elif params.get("required_area") is not None:
            params["end_condition"] = f"Bereik gebied {params['required_area']}."
            params["end_condition_source"] = params["required_area_source"]
        else:
            params["end_condition"] = None
            params["end_condition_source"] = "unknown"
            missing.append("end_condition")
        params["current_area"] = live.get("current_area")
    elif goal_id == "gem_farm":
        play = _unknown_token(
            user.get("play_mode"),
            allowed=frozenset({"foreground", "background", "offline", "unknown"}),
        )
        auto = _unknown_token(
            user.get("auto_reset"),
            allowed=frozenset({"yes", "no", "unknown"}),
        )
        reset_area = _parse_int(user.get("reset_area"))
        if reset_area is None:
            # Prefer modron goal when auto_reset is yes/unknown and value exists.
            modron = live.get("modron_area_goal")
            if isinstance(modron, int) and modron > 0:
                reset_area = modron
                params["reset_area_source"] = "modron_data"
            else:
                params["reset_area_source"] = "unknown"
                missing.append("reset_area")
        else:
            if reset_area <= 0:
                reset_area = None
                params["reset_area_source"] = "unknown"
                missing.append("reset_area")
            else:
                params["reset_area_source"] = "user"
        params["play_mode"] = play
        params["auto_reset"] = auto
        params["reset_area"] = reset_area  # None when unknown — never 0
        if play == "unknown":
            missing.append("play_mode")
        if auto == "unknown":
            missing.append("auto_reset")
        # Familiar / clickdamage / automation: only if already known elsewhere.
        for key in ("familiar_info", "click_damage_info", "automation_info"):
            if key in user:
                params[key] = user.get(key)
            else:
                params[key] = None
                missing.append(key)
    elif goal_id == "favor_farm":
        camp_id = _parse_int(user.get("campaign_id"))
        camp_name = str(user.get("campaign_name") or "").strip() or None
        source = "user"
        if camp_id is None and live.get("campaign_id") is not None:
            camp_id = live.get("campaign_id")
            camp_name = camp_name or live.get("campaign_name")
            source = "live_campaign"
        if camp_id is None:
            source = "unknown"
            missing.append("campaign_id")
        horizon = _unknown_token(
            user.get("time_horizon"),
            allowed=frozenset({"per_run", "per_time", "unknown"}),
        )
        params["campaign_id"] = camp_id
        params["campaign_name"] = camp_name
        params["campaign_source"] = source
        params["time_horizon"] = horizon
        if horizon == "unknown":
            missing.append("time_horizon")
    elif goal_id == "custom_task":
        task = str(user.get("task_description") or "").strip()
        params["task_description"] = task or None
        params["task_champion_id"] = _parse_int(user.get("task_champion_id"))
        params["target_value"] = user.get("target_value")
        params["time_limit"] = user.get("time_limit")
        if not task:
            missing.append("task_description")
    else:
        missing.append("goal_id")

    note = str(user.get("note") or user.get("goal_note") or "").strip()
    if note:
        params["note"] = note

    # Deduplicate missing while preserving order.
    seen: set[str] = set()
    ordered_missing: list[str] = []
    for item in missing:
        if item not in seen:
            seen.add(item)
            ordered_missing.append(item)
    return params, ordered_missing


def build_damage_focus_block(
    *,
    fixed_main_dps_id: int | None,
    name_by_id: dict[int, str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(fixed_main_dps_id, int):
        return None
    names = name_by_id or {}
    return {
        "champion_id": fixed_main_dps_id,
        "name": names.get(fixed_main_dps_id),
        "kind": "fixed",
        "lock_reason": "fixed_main_dps",
    }


def build_fixed_champion_entries(
    *,
    fixed_main_dps_id: int | None,
    explicit_locked_ids: list[int] | tuple[int, ...] | None = None,
    name_by_id: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Only explicit locks + optional fixed main DPS. Never invent auto-locks."""
    names = name_by_id or {}
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    if isinstance(fixed_main_dps_id, int):
        out.append(
            {
                "champion_id": fixed_main_dps_id,
                "name": names.get(fixed_main_dps_id),
                "reason": "fixed_main_dps",
            }
        )
        seen.add(fixed_main_dps_id)
    for raw in explicit_locked_ids or ():
        hid = _parse_int(raw)
        if hid is None or hid in seen:
            continue
        out.append(
            {
                "champion_id": hid,
                "name": names.get(hid),
                "reason": "user_lock",
            }
        )
        seen.add(hid)
    return out


def build_goal_export_object(
    goal_id: str,
    *,
    user_parameters: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    app_context: str | None = None,
    fixed_main_dps_id: int | None = None,
    explicit_locked_ids: list[int] | tuple[int, ...] | None = None,
    name_by_id: dict[int, str] | None = None,
    restriction_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the unambiguous goal object for export JSON and prompt projection."""
    if goal_id not in GOAL_DEFINITIONS:
        # Refuse to silently treat legacy technical goals as user goals.
        raise ValueError(
            f"Export vereist een gebruikersdoel "
            f"({', '.join(USER_GOAL_IDS)}); kreeg {goal_id!r}."
        )
    definition = GOAL_DEFINITIONS[goal_id]  # type: ignore[index]
    parameters, missing = build_goal_parameters(
        goal_id,
        user_parameters=user_parameters,
        payload=payload,
    )
    damage_focus = build_damage_focus_block(
        fixed_main_dps_id=fixed_main_dps_id,
        name_by_id=name_by_id,
    )
    fixed_entries = build_fixed_champion_entries(
        fixed_main_dps_id=fixed_main_dps_id,
        explicit_locked_ids=explicit_locked_ids,
        name_by_id=name_by_id,
    )
    goal: dict[str, Any] = {
        "id": definition.id,
        "label": definition.label,
        "description": definition.description,
        "primary_metric": definition.primary_metric,
        "priorities": list(definition.priorities),
        "priority_source": f"app_default_for_{definition.id}",
        "parameters": parameters,
        "missing_context": missing or None,
        "app_context": app_context,
        # Explicitly no legacy technical objective field.
        "damage_focus": damage_focus,
        "fixed_champions": fixed_entries or None,
        # Convenience mirrors for consumers that only need ids.
        "fixed_champion_ids": [e["champion_id"] for e in fixed_entries],
        "fixed_main_dps_id": fixed_main_dps_id
        if isinstance(fixed_main_dps_id, int)
        else None,
    }
    if restriction_fields:
        for key, value in restriction_fields.items():
            if key in goal and key not in (
                "id",
                "label",
                "description",
                "primary_metric",
                "priorities",
            ):
                # Prefer restriction block keys that don't collide with goal contract.
                if key.startswith("party_") or key in {
                    "adventure_id",
                    "adventure_name",
                    "campaign_id",
                    "campaign_name",
                    "patron_id",
                    "patron_name",
                    "variant_id",
                    "variant_name",
                    "restriction_text",
                    "restrictions_checked_by_app",
                    "structured_restrictions",
                    "local_evidence",
                    "party_restriction_status",
                    "party_restriction_checks",
                    "current_area",
                    "tier",
                }:
                    goal[key] = value
            elif key not in goal:
                goal[key] = value
    return goal


def goal_label(goal_id: str | None) -> str:
    if goal_id in GOAL_DEFINITIONS:
        return GOAL_DEFINITIONS[goal_id].label  # type: ignore[index]
    return legacy_label(goal_id) if goal_id in LEGACY_GOAL_IDS else str(goal_id or "")
