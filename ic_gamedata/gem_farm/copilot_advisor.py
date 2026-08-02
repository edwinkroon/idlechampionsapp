"""Natural-language Co-Pilot advice (advise-only; Script Hub plays)."""

from __future__ import annotations

from ic_gamedata.gem_farm.models import CopilotAdvice, CopilotPhase
from ic_gamedata.gem_farm.phase_detector import PhaseDetection


def build_copilot_advice(
    phase: PhaseDetection | None,
    *,
    send_keys_enabled: bool = False,
) -> CopilotAdvice | None:
    if phase is None:
        return None

    mapping: dict[CopilotPhase, tuple[str, str, str | None]] = {
        "idle": (
            "Co-Pilot idle",
            "Wacht op actieve gem farm (Modron-doel + Briv in formation).",
            None,
        ),
        "progress": (
            "Progressie-fase",
            "Focus op snelle areas — Q-formation laden.",
            "Q",
        ),
        "stacking": (
            "Stack-fase",
            "Briv stacks opbouwen — W-formation + auto-progress uit (G).",
            "W",
        ),
        "swap_ready": (
            "Stacks klaar",
            "Briv swap — E-formation; auto-progress weer aan (G) indien nodig.",
            "E",
        ),
        "pre_reset": (
            "Reset-zone",
            "Modron reset — voltooi handmatig of via Script Hub (geen R via Co-Pilot).",
            None,
        ),
        "stuck": (
            "Mogelijk vastgelopen",
            "Check auto-progress, dash en formation — zie Farm health alerts.",
            None,
        ),
    }
    headline, detail, formation = mapping.get(
        phase.phase,
        ("Onbekende fase", "—", None),
    )
    if phase.reasons:
        detail = f"{detail} ({'; '.join(phase.reasons)})"
    if formation:
        detail = f"{detail} Toets: {formation}."
    if send_keys_enabled:
        detail = f"{detail} Co-Pilot stuurt Q/W/E/G bij fase-wissel (debounce actief)."
    else:
        detail = f"{detail} Co-Pilot adviseert alleen — zet 'toetsen sturen' aan om hotkeys te versturen."
    return CopilotAdvice(
        phase=phase.phase,
        headline=headline,
        detail=detail,
        formation_hint=formation,
    )
