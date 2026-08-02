"""Datamodel for formation placement advisor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

InsightType = Literal["placement", "swap", "bench", "warning"]
RuleSourceType = Literal["authored", "heuristic", "handler"]
DataSourceVersion = Literal["formation_rules_v1", "handler"]
Zone = Literal["front", "mid", "back"]


@dataclass(frozen=True)
class FormationTopology:
    """Seat layout: adjacency, column, zone per seat (1–12)."""

    seat_adjacency: dict[int, frozenset[int]]
    seat_column: dict[int, int]
    seat_zone: dict[int, Zone]
    source: str = "heuristic"


@dataclass(frozen=True)
class FormationLayoutContext:
    """Shared context for placement rules and handlers."""

    active_hero_ids: frozenset[int]
    seat_by_hero: dict[int, int]
    hero_name_by_id: dict[int, str]
    hero_roles_by_id: dict[int, tuple[str, ...]]
    hero_tags_by_id: dict[int, tuple[str, ...]]
    carry_hero_id: int | None
    highest_damage_hero_id: int | None
    topology: FormationTopology
    run_goal: str
    context: str
    goal: str
    party_size: int
    owned_hero_ids: frozenset[int]
    allowed_bench_ids: frozenset[int]

    def seat_of(self, hero_id: int) -> int | None:
        return self.seat_by_hero.get(hero_id)

    def hero_at_seat(self, seat: int) -> int | None:
        for hero_id, hero_seat in self.seat_by_hero.items():
            if hero_seat == seat:
                return hero_id
        return None

    def zone_of_seat(self, seat: int) -> Zone:
        return self.topology.seat_zone.get(seat, "mid")

    def zone_of_hero(self, hero_id: int) -> Zone | None:
        seat = self.seat_of(hero_id)
        if seat is None:
            return None
        return self.zone_of_seat(seat)

    def adjacent_seats(self, seat: int) -> frozenset[int]:
        return self.topology.seat_adjacency.get(seat, frozenset())

    def is_adjacent(self, hero_a: int, hero_b: int) -> bool:
        seat_a = self.seat_of(hero_a)
        seat_b = self.seat_of(hero_b)
        if seat_a is None or seat_b is None:
            return False
        return seat_b in self.adjacent_seats(seat_a)

    def name(self, hero_id: int) -> str:
        return self.hero_name_by_id.get(hero_id, f"Champion {hero_id}")

    def roles(self, hero_id: int) -> frozenset[str]:
        return frozenset(self.hero_roles_by_id.get(hero_id, ()))

    def tags(self, hero_id: int) -> frozenset[str]:
        return frozenset(self.hero_tags_by_id.get(hero_id, ()))


@dataclass(frozen=True)
class PlacementRule:
    rule_id: str
    champion: str
    role: str
    tag: str
    run_goal: str
    context: str
    condition_field: str
    condition_operator: str
    condition_value: str
    tip_type: InsightType
    headline: str
    detail: str
    priority: int
    rule_source_type: RuleSourceType


@dataclass(frozen=True)
class RuleDataset:
    rules: tuple[PlacementRule, ...]
    data_source_version: DataSourceVersion = "formation_rules_v1"


@dataclass(frozen=True)
class FormationInsight:
    insight_type: InsightType
    hero_id: int | None
    hero_name: str
    seat: int | None
    related_hero_id: int | None
    related_hero_name: str | None
    related_seat: int | None
    priority: int
    headline: str
    detail: str
    rule_source_type: RuleSourceType
    data_source_version: DataSourceVersion
    confidence: int
    rule_id: str = ""
