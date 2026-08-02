"""One-off helper: split party_advisor.py into formation + scoring modules."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "ic_gamedata" / "party_advisor.py"
lines = SOURCE.read_text(encoding="utf-8").splitlines(keepends=True)

FORMATION_START = next(i for i, line in enumerate(lines) if line.startswith("def _champions_path_candidates"))
SCORING_START = next(i for i, line in enumerate(lines) if line.startswith("def _disallowed_replacement_detail"))
ANALYZE_START = next(i for i, line in enumerate(lines) if line.startswith("def analyze_party"))

FORMATION_HEADER = '''"""Formation parsing, champion metadata, and role helpers for party advisor."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from ic_gamedata.parsing import parse_int as _parse_int
from ic_gamedata.parsing import parse_number as _parse_number
from ic_gamedata.party_advisor_models import FormationHero

_RELATIVE_GEAR_WEAK_PCT = 12.0

'''

SCORING_HEADER = '''"""Composition scoring, tips, and improvement suggestions for party advisor."""

from __future__ import annotations

import re
from typing import Any

from ic_gamedata.party_advisor_models import AdvisorTip, ContextMode, FormationHero, GoalMode, HeroImprovement
from ic_gamedata.party_advisor_formation import (
    _RELATIVE_GEAR_WEAK_PCT,
    _bench_suggestions,
    _human_buff_note,
    _ilvl_below_avg_action,
    _ilvl_label,
    _is_actionable_adventure_rule,
    _is_buffer,
    _is_debuffer,
    _is_dps,
    _is_speed,
    _is_tank,
    _is_useful_adventure_note,
    _known_buffers,
    _known_debuffers,
    _resolve_bud_hero,
    _resolve_speed_hero,
    _seat_zone_guess,
)

'''

FACADE_HEADER = '''"""Party advisor: formation and gear analysis from getuserdetails payload."""

from __future__ import annotations

from typing import Any

from ic_gamedata.party_advisor_formation import (
    _active_game_instance,
    _adventure_modifiers,
    _adventure_name,
    _formation_heroes,
    _human_buff_note,
    _is_actionable_adventure_rule,
    _is_useful_adventure_note,
    _loot_ilvl_by_hero,
    _owned_heroes,
    _resolve_bud_hero,
    _resolve_speed_hero,
)
from ic_gamedata.party_advisor_models import (
    AdvisorReport,
    AdvisorTip,
    ContextMode,
    FormationHero,
    GoalMode,
    HeroImprovement,
    goal_label,
)
from ic_gamedata.party_advisor_scoring import (
    _build_improvements,
    _composition_advice,
    _coverage_from_formation_insights,
    _filter_relevant_formation_tips,
    _formation_tips,
    _tip,
)

'''

formation_body = "".join(lines[FORMATION_START:SCORING_START])
scoring_body = "".join(lines[SCORING_START:ANALYZE_START])
facade_body = "".join(lines[ANALYZE_START:])

(ROOT / "ic_gamedata" / "party_advisor_formation.py").write_text(
    FORMATION_HEADER + formation_body, encoding="utf-8"
)
(ROOT / "ic_gamedata" / "party_advisor_scoring.py").write_text(
    SCORING_HEADER + scoring_body, encoding="utf-8"
)

REEXPORTS = '''
# Re-exports for backward-compatible imports from ic_gamedata.party_advisor
from ic_gamedata.party_advisor_formation import (  # noqa: F401
    _active_game_instance,
    _adventure_modifiers,
    _adventure_name,
    _bench_suggestions,
    _formation_heroes,
    _is_actionable_adventure_rule,
    _is_buffer,
    _is_debuffer,
    _is_dps,
    _is_speed,
    _is_tank,
    _is_useful_adventure_note,
    _loot_ilvl_by_hero,
    _owned_heroes,
    _resolve_bud_hero,
    _resolve_speed_hero,
    _seat_zone_guess,
)
from ic_gamedata.party_advisor_scoring import (  # noqa: F401
    _composition_advice,
    _coverage_from_formation_insights,
    _formation_tips,
)

__all__ = [
    "AdvisorReport",
    "AdvisorTip",
    "ContextMode",
    "FormationHero",
    "GoalMode",
    "HeroImprovement",
    "analyze_party",
    "format_report",
    "goal_label",
]
'''

(ROOT / "ic_gamedata" / "party_advisor.py").write_text(
    FACADE_HEADER + facade_body + REEXPORTS, encoding="utf-8"
)
print("Split complete.")
