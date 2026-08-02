"""Load and persist gem farm configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ic_gamedata.gem_farm.models import (
    BrivGearOverride,
    CopilotSettings,
    FarmHealthThresholds,
    FarmProfile,
    GemFarmConfig,
)
from ic_gamedata.paths import GEM_FARM_CONFIG_PATH


def _parse_copilot(raw: dict[str, Any] | None) -> CopilotSettings:
    if not isinstance(raw, dict):
        return CopilotSettings()
    return CopilotSettings(
        send_keys_enabled=bool(raw.get("send_keys_enabled", False)),
        advise_only=bool(raw.get("advise_only", True)),
        allow_formation_q=bool(raw.get("allow_formation_q", False)),
        allow_formation_w=bool(raw.get("allow_formation_w", False)),
        allow_formation_e=bool(raw.get("allow_formation_e", False)),
        allow_auto_progress_g=bool(raw.get("allow_auto_progress_g", False)),
    )


def _parse_gear_override(raw: Any) -> BrivGearOverride | None:
    if not isinstance(raw, dict):
        return None
    enchant = raw.get("enchant")
    rarity = raw.get("rarity")
    gild = raw.get("gild")
    if enchant is None and rarity is None and gild is None:
        return None
    return BrivGearOverride(
        enchant=int(enchant) if enchant is not None else None,
        rarity=int(rarity) if rarity is not None else None,
        gild=int(gild) if gild is not None else None,
    )


def _optional_name(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    return name or None


def _parse_profile(raw: dict[str, Any]) -> FarmProfile:
    stack_zone = raw.get("stack_zone")
    reset_zone = raw.get("reset_zone")
    stack_target = raw.get("stack_target_stacks")
    return FarmProfile(
        enabled=bool(raw.get("enabled", True)),
        stack_zone=int(stack_zone) if stack_zone is not None else None,
        reset_zone=int(reset_zone) if reset_zone is not None else None,
        stack_target_stacks=int(stack_target) if stack_target is not None else None,
        briv_gear_override=_parse_gear_override(raw.get("briv_gear_override")),
        formation_q_name=_optional_name(raw.get("formation_q_name")),
        formation_w_name=_optional_name(raw.get("formation_w_name")),
        formation_e_name=_optional_name(raw.get("formation_e_name")),
        copilot=_parse_copilot(raw.get("copilot") if isinstance(raw.get("copilot"), dict) else None),
    )


def _parse_health(raw: dict[str, Any] | None) -> FarmHealthThresholds:
    if not isinstance(raw, dict):
        return FarmHealthThresholds()
    return FarmHealthThresholds(
        enabled=bool(raw.get("enabled", True)),
        run_slowdown_pct=float(raw.get("run_slowdown_pct", 115)),
        gem_drop_pct=float(raw.get("gem_drop_pct", 85)),
        area_stall_sec=float(raw.get("area_stall_sec", 180)),
        gem_drop_min_sec=float(raw.get("gem_drop_min_sec", 600)),
    )


def parse_gem_farm_config(data: dict[str, Any] | None) -> GemFarmConfig:
    if not isinstance(data, dict):
        return GemFarmConfig()
    profiles: dict[int, FarmProfile] = {}
    raw_profiles = data.get("profiles")
    if isinstance(raw_profiles, dict):
        for key, raw in raw_profiles.items():
            if not isinstance(raw, dict):
                continue
            try:
                party_index = int(key)
            except (TypeError, ValueError):
                continue
            profiles[party_index] = _parse_profile(raw)
    return GemFarmConfig(profiles=profiles, health=_parse_health(data.get("health")))


def load_gem_farm_config(path: Path | None = None) -> GemFarmConfig:
    config_path = path or GEM_FARM_CONFIG_PATH
    if not config_path.is_file():
        return GemFarmConfig()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return GemFarmConfig()
    return parse_gem_farm_config(payload if isinstance(payload, dict) else None)


def _profile_to_dict(profile: FarmProfile) -> dict[str, Any]:
    gear_override = None
    if profile.briv_gear_override is not None:
        o = profile.briv_gear_override
        gear_override = {
            "enchant": o.enchant,
            "rarity": o.rarity,
            "gild": o.gild,
        }
    return {
        "enabled": profile.enabled,
        "stack_zone": profile.stack_zone,
        "reset_zone": profile.reset_zone,
        "stack_target_stacks": profile.stack_target_stacks,
        "briv_gear_override": gear_override,
        "formation_q_name": profile.formation_q_name,
        "formation_w_name": profile.formation_w_name,
        "formation_e_name": profile.formation_e_name,
        "copilot": {
            "send_keys_enabled": profile.copilot.send_keys_enabled,
            "advise_only": profile.copilot.advise_only,
            "allow_formation_q": profile.copilot.allow_formation_q,
            "allow_formation_w": profile.copilot.allow_formation_w,
            "allow_formation_e": profile.copilot.allow_formation_e,
            "allow_auto_progress_g": profile.copilot.allow_auto_progress_g,
        },
    }


def _config_to_dict(config: GemFarmConfig) -> dict[str, Any]:
    return {
        "profiles": {str(party): _profile_to_dict(profile) for party, profile in sorted(config.profiles.items())},
        "health": {
            "enabled": config.health.enabled,
            "run_slowdown_pct": config.health.run_slowdown_pct,
            "gem_drop_pct": config.health.gem_drop_pct,
            "area_stall_sec": config.health.area_stall_sec,
            "gem_drop_min_sec": config.health.gem_drop_min_sec,
        },
    }


class GemFarmConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or GEM_FARM_CONFIG_PATH

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> GemFarmConfig:
        return load_gem_farm_config(self._path)

    def save(self, config: GemFarmConfig) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(_config_to_dict(config), indent=2), encoding="utf-8")
