"""Formation placement advisor: seat swaps, placement tips, bench upgrades."""

from ic_gamedata.formation_advisor.advisor import (
    build_formation_insights,
    formation_insights_to_tips,
)
from ic_gamedata.formation_advisor.models import FormationInsight

__all__ = [
    "FormationInsight",
    "build_formation_insights",
    "formation_insights_to_tips",
]
