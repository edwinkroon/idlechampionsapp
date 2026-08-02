"""Map Co-Pilot phases to game hotkeys."""

from __future__ import annotations

from ic_gamedata.gem_farm.models import CopilotPhase

FORMATION_KEY_BY_PHASE: dict[CopilotPhase, str] = {
    "progress": "Q",
    "stacking": "W",
    "swap_ready": "E",
}

# Area drop larger than this is treated as a Modron/adventure reset.
AREA_RESET_DROP = 40


def hotkey_for_phase(phase: CopilotPhase, *, send_keys_enabled: bool) -> str | None:
    if not send_keys_enabled:
        return None
    if phase == "stuck":
        return "G"
    return FORMATION_KEY_BY_PHASE.get(phase)


def desired_auto_progress(phase: CopilotPhase) -> bool | None:
    """Target auto-progress state for a phase, or None to leave untouched.

    Stacking parks on an area (AP off). Progress / swap / stuck want AP on.
    """
    if phase == "stacking":
        return False
    if phase in ("progress", "swap_ready", "stuck"):
        return True
    return None


def companion_auto_progress_key(
    *,
    phase: CopilotPhase,
    ap_assumed_on: bool | None,
    allow_auto_progress_g: bool,
) -> tuple[str | None, bool | None]:
    """Return optional G toggle and the updated assumed AP state.

    G is a toggle — we only send it when our assumed state differs from the
    desired phase state. Unknown (None) + want-on does not send (assume the
    player already has AP on during progress). Unknown + want-off does send
    (stack park).
    """
    if not allow_auto_progress_g:
        return None, ap_assumed_on
    desired = desired_auto_progress(phase)
    if desired is None:
        return None, ap_assumed_on
    if desired is False:
        if ap_assumed_on is not False:
            return "G", False
        return None, ap_assumed_on
    # desired True
    if ap_assumed_on is False:
        return "G", True
    return None, ap_assumed_on


def keys_on_phase_change(
    *,
    previous_phase: CopilotPhase | None,
    new_phase: CopilotPhase,
    send_keys_enabled: bool,
    ap_assumed_on: bool | None = None,
    allow_auto_progress_g: bool = True,
) -> tuple[tuple[str, ...], bool | None]:
    """Return (keys to send, updated ap_assumed_on)."""
    if not send_keys_enabled:
        return (), ap_assumed_on
    if new_phase in ("idle", "pre_reset"):
        return (), ap_assumed_on
    if previous_phase == new_phase:
        return (), ap_assumed_on

    keys: list[str] = []
    formation = hotkey_for_phase(new_phase, send_keys_enabled=True)
    if formation and formation != "G":
        keys.append(formation)
    elif formation == "G":
        # stuck: prefer AP companion logic below; fall back to plain G
        pass

    g_key, ap_next = companion_auto_progress_key(
        phase=new_phase,
        ap_assumed_on=ap_assumed_on,
        allow_auto_progress_g=allow_auto_progress_g,
    )
    if g_key:
        keys.append(g_key)
    elif (
        new_phase == "stuck"
        and allow_auto_progress_g
        and not keys
        and ap_assumed_on is not True
    ):
        # Unknown or off: nudge G once to try enabling auto-progress.
        keys.append("G")
        ap_next = True

    return tuple(keys), ap_next


def keys_on_area_reset(
    *,
    previous_area: int | None,
    new_area: int | None,
    phase: CopilotPhase,
    send_keys_enabled: bool,
    ap_assumed_on: bool | None = None,
    allow_auto_progress_g: bool = True,
) -> tuple[tuple[str, ...], bool | None]:
    """After Modron reset, re-send formation (+ G if AP was left off)."""
    if not send_keys_enabled:
        return (), ap_assumed_on
    if previous_area is None or new_area is None:
        return (), ap_assumed_on
    if previous_area - new_area < AREA_RESET_DROP:
        return (), ap_assumed_on
    if phase in ("idle", "pre_reset"):
        return (), ap_assumed_on

    keys: list[str] = []
    formation = hotkey_for_phase(phase, send_keys_enabled=True)
    if formation and formation != "G":
        keys.append(formation)
    g_key, ap_next = companion_auto_progress_key(
        phase=phase,
        ap_assumed_on=ap_assumed_on,
        allow_auto_progress_g=allow_auto_progress_g,
    )
    if g_key:
        keys.append(g_key)
    return tuple(keys), ap_next


def should_send_on_phase_change(
    *,
    previous_phase: CopilotPhase | None,
    new_phase: CopilotPhase,
    send_keys_enabled: bool,
) -> str | None:
    """Legacy: first formation/stuck key only (no auto-progress companion)."""
    if not send_keys_enabled:
        return None
    if new_phase in ("idle", "pre_reset") or previous_phase == new_phase:
        return None
    return hotkey_for_phase(new_phase, send_keys_enabled=True)


def should_send_on_area_reset(
    *,
    previous_area: int | None,
    new_area: int | None,
    phase: CopilotPhase,
    send_keys_enabled: bool,
) -> str | None:
    """Legacy: first formation key only after area drop."""
    keys, _ = keys_on_area_reset(
        previous_area=previous_area,
        new_area=new_area,
        phase=phase,
        send_keys_enabled=send_keys_enabled,
        allow_auto_progress_g=False,
    )
    return keys[0] if keys else None
