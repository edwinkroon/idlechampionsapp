"""Orchestrate health, Briv zones, and Co-Pilot for the active party."""

from __future__ import annotations

from ic_gamedata.gem_farm.briv_calculator import advise_briv_zones, load_briv_heuristics
from ic_gamedata.gem_farm.briv_gear import parse_briv_slot4_from_payload
from ic_gamedata.gem_farm.config_store import GemFarmConfigStore
from ic_gamedata.gem_farm.copilot_advisor import build_copilot_advice
from ic_gamedata.gem_farm.formation_hotkeys import resolve_formation_hotkeys
from ic_gamedata.gem_farm.models import (
    FarmHealthStatus,
    FarmProfile,
    GemFarmConfig,
    GemFarmSnapshot,
)
from ic_gamedata.gem_farm.monitor import FarmHealthMonitor
from ic_gamedata.gem_farm.phase_detector import detect_copilot_phase
from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.stats_models import GoalRunRecord, PartySessionStats


class GemFarmAdvisor:
    """Evaluate full gem-farm snapshot for dashboard + Gem Farm tab."""

    def __init__(
        self,
        *,
        health_monitor: FarmHealthMonitor | None = None,
        config_store: GemFarmConfigStore | None = None,
    ) -> None:
        self._health = health_monitor or FarmHealthMonitor(config_store=config_store)
        self._config_store = config_store or GemFarmConfigStore()
        self._last_snapshot: GemFarmSnapshot | None = None

    @property
    def health_monitor(self) -> FarmHealthMonitor:
        return self._health

    @property
    def last_snapshot(self) -> GemFarmSnapshot | None:
        return self._last_snapshot

    def profile_for_party(self, config: GemFarmConfig, party_index: int) -> FarmProfile:
        return config.profiles.get(party_index, FarmProfile())

    def evaluate(
        self,
        *,
        party: PartySnapshot,
        ps: PartySessionStats | None,
        is_active: bool,
        payload: dict | None,
        memory_modron_goal: int | None,
        goal_run_history: tuple[GoalRunRecord, ...],
        config: GemFarmConfig | None = None,
        now: float | None = None,
    ) -> GemFarmSnapshot:
        if config is None:
            config = self._config_store.load()

        health = self._health.evaluate_active_party(
            party=party,
            ps=ps,
            is_active=is_active,
            memory_modron_goal=memory_modron_goal,
            goal_run_history=goal_run_history,
            config=config,
            now=now,
        )

        modron_goal = memory_modron_goal
        if modron_goal is None and ps is not None and ps.modron_area_goal:
            modron_goal = ps.modron_area_goal
        if modron_goal is None and party.modron_area_goal:
            modron_goal = party.modron_area_goal

        profile = self.profile_for_party(config, party.party_index)
        gear = parse_briv_slot4_from_payload(payload, override=profile.briv_gear_override)
        zone_advice = advise_briv_zones(
            modron_goal=modron_goal,
            gear=gear,
            profile=profile,
            heuristics=load_briv_heuristics(),
        )

        phase = detect_copilot_phase(
            is_active=is_active,
            modron_goal=modron_goal,
            briv_in_formation=party.briv_in_formation,
            current_area=party.current_area,
            briv_stacks=party.briv_sprint_stacks,
            zone_advice=zone_advice,
            profile=profile,
            health=health,
        )
        copilot = build_copilot_advice(
            phase,
            send_keys_enabled=profile.copilot.send_keys_enabled,
        )
        formation_hotkeys = resolve_formation_hotkeys(
            payload,
            party_index=party.party_index,
            profile_names=(
                profile.formation_q_name,
                profile.formation_w_name,
                profile.formation_e_name,
            ),
        )

        snapshot = GemFarmSnapshot(
            party_index=party.party_index,
            monitoring=health.monitoring,
            health=health,
            briv_gear=gear,
            zone_advice=zone_advice,
            copilot=copilot,
            formation_hotkeys=formation_hotkeys,
            briv_stacks=party.briv_sprint_stacks,
            briv_steelbones_stacks=party.briv_steelbones_stacks,
            gems_per_quarter=ps.gems_per_quarter if ps is not None else None,
            current_area=party.current_area,
        )
        self._last_snapshot = snapshot
        return snapshot

    def evaluate_idle(self, party_index: int) -> GemFarmSnapshot:
        health = FarmHealthStatus(
            party_index=party_index,
            level="ok",
            monitoring=False,
            alerts=(),
        )
        snapshot = GemFarmSnapshot(
            party_index=party_index,
            monitoring=False,
            health=health,
            briv_gear=None,
            zone_advice=None,
            copilot=build_copilot_advice(
                detect_copilot_phase(
                    is_active=False,
                    modron_goal=None,
                    briv_in_formation=False,
                    current_area=None,
                    briv_stacks=None,
                    zone_advice=None,
                    profile=None,
                    health=health,
                ),
                send_keys_enabled=False,
            ),
        )
        self._last_snapshot = snapshot
        return snapshot
