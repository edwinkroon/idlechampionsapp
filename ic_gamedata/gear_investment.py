"""Which formation champion should receive item levels first."""

from __future__ import annotations

from dataclasses import dataclass

from ic_gamedata.party_advisor_formation import (
    _is_buffer,
    _is_debuffer,
    _is_dps,
    _is_speed,
    _is_tank,
    _resolve_bud_hero,
    _resolve_speed_hero,
)
from ic_gamedata.party_advisor_models import FormationHero, GoalMode


@dataclass(frozen=True)
class GearInvestmentAdvice:
    hero_id: int
    hero_name: str
    seat: int | None
    ilvl: int
    party_avg_ilvl: float
    ilvl_pct_vs_avg: float
    reason: str
    score: float


def _role_weight(hero: FormationHero, *, goal: GoalMode, focus: FormationHero | None) -> float:
    is_focus = focus is not None and hero.hero_id == focus.hero_id
    if goal == "bud":
        if is_focus or hero.is_top_damage:
            return 5.0
        if _is_dps(hero):
            return 3.5
        if _is_debuffer(hero):
            return 3.0
        if _is_buffer(hero) or "support" in hero.roles:
            return 2.5
        if _is_tank(hero):
            return 1.5
        return 1.0
    if goal == "speed":
        if is_focus or _is_speed(hero):
            return 5.0
        if _is_dps(hero) or hero.is_top_damage:
            return 2.5
        if _is_buffer(hero) or _is_debuffer(hero):
            return 2.0
        return 1.0
    # gold
    if "gold" in hero.roles or "goldfind" in hero.tags or "gold" in hero.tags:
        return 5.0
    if is_focus or hero.is_top_damage or _is_dps(hero):
        return 3.0
    if _is_buffer(hero) or _is_debuffer(hero):
        return 2.0
    return 1.0


def _focus_hero(formation: tuple[FormationHero, ...], goal: GoalMode) -> FormationHero | None:
    if goal == "speed":
        return _resolve_speed_hero(formation) or _resolve_bud_hero(formation)
    return _resolve_bud_hero(formation)


def _reason_for(
    hero: FormationHero,
    *,
    goal: GoalMode,
    focus: FormationHero | None,
    party_avg: float,
    weight: float,
    catch_up: bool,
) -> str:
    is_focus = focus is not None and hero.hero_id == focus.hero_id
    if goal == "bud" and (is_focus or hero.is_top_damage):
        role_why = (
            f"{hero.name} is your BUD / top-damage dealer, so item levels here "
            "usually give the largest damage return."
        )
    elif goal == "speed" and (is_focus or _is_speed(hero)):
        role_why = (
            f"{hero.name} is your speed focus, so gear here usually shortens runs most."
        )
    elif goal == "gold" and weight >= 5.0:
        role_why = (
            f"{hero.name} covers the gold role, so gear here usually improves gold find most."
        )
    elif catch_up and _is_debuffer(hero):
        role_why = (
            f"{hero.name} is an important debuffer far behind the party average; "
            "catching them up is worth more right now than stacking an already-geared carry."
        )
    elif catch_up and (_is_buffer(hero) or "support" in hero.roles):
        role_why = (
            f"{hero.name} is a key support far behind the party average; "
            "buff strength often scales with item level, so catch-up has high ROI."
        )
    elif _is_debuffer(hero):
        role_why = (
            f"{hero.name} is a debuffer — many debuffs scale with item level."
        )
    elif _is_buffer(hero) or "support" in hero.roles:
        role_why = (
            f"{hero.name} is a support — buff strength often scales with item level."
        )
    elif _is_dps(hero):
        role_why = f"{hero.name} is DPS — personal damage scales with gear."
    else:
        role_why = f"{hero.name} currently has the best gear ROI among this party."

    if hero.ilvl_pct_vs_avg < -5:
        ilvl_why = (
            f"Current ilvl {hero.ilvl} is {abs(hero.ilvl_pct_vs_avg):.0f}% below "
            f"the party average ({party_avg:.0f})."
        )
    elif hero.ilvl_pct_vs_avg > 5:
        ilvl_why = (
            f"Current ilvl {hero.ilvl} is already {hero.ilvl_pct_vs_avg:.0f}% above "
            f"the party average ({party_avg:.0f}), but their role still wins on ROI."
        )
    else:
        ilvl_why = f"Current ilvl {hero.ilvl}, roughly at the party average ({party_avg:.0f})."

    return f"{role_why} {ilvl_why}"


def recommend_gear_investment(
    formation: tuple[FormationHero, ...],
    *,
    goal: GoalMode = "bud",
) -> GearInvestmentAdvice | None:
    """Pick the formation champion where the next ilvls are most worthwhile."""
    if not formation:
        return None

    party_avg = sum(hero.ilvl for hero in formation) / len(formation)
    focus = _focus_hero(formation, goal)

    best: tuple[float, FormationHero, float, bool] | None = None
    for hero in formation:
        weight = _role_weight(hero, goal=goal, focus=focus)
        deficit = max(0.0, party_avg - float(hero.ilvl))
        # Role first; catching up someone important behind the curve is high ROI.
        score = weight * 1000.0 + deficit * weight
        catch_up = (
            focus is not None
            and hero.hero_id != focus.hero_id
            and deficit > 0
            and hero.ilvl_pct_vs_avg <= -20.0
            and weight >= 2.5
        )
        # Soften stacking on already-fat supports when a focus exists.
        if (
            focus is not None
            and hero.hero_id != focus.hero_id
            and hero.ilvl_pct_vs_avg > 25.0
        ):
            score *= 0.55
        if best is None or score > best[0] or (
            abs(score - best[0]) < 1e-6 and hero.ilvl < best[1].ilvl
        ):
            best = (score, hero, weight, catch_up)

    if best is None:
        return None
    score, hero, weight, catch_up = best
    return GearInvestmentAdvice(
        hero_id=hero.hero_id,
        hero_name=hero.name,
        seat=hero.seat,
        ilvl=hero.ilvl,
        party_avg_ilvl=party_avg,
        ilvl_pct_vs_avg=hero.ilvl_pct_vs_avg,
        reason=_reason_for(
            hero,
            goal=goal,
            focus=focus,
            party_avg=party_avg,
            weight=weight,
            catch_up=catch_up,
        ),
        score=score,
    )
