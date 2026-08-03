#!/usr/bin/env python3
"""Build config/specialization_advisor_models.json from review batches + known fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ic_gamedata.specializations import load_specialization_rules

OUT = ROOT / "config" / "specialization_advisor_models.json"

# Manually curated. Rule: safe_default when a stable universal choice exists;
# null only when truly context-dependent; alternatives are conditional_only.


def _choice(upgrade_id: int | None, name: str | None) -> dict | None:
    if upgrade_id is None or not name:
        return None
    return {"upgrade_id": upgrade_id, "name": name}


RECORDS: dict[int, dict] = {
    # --- batch 01 ---
    1: {
        "advice_model": "safe_default",
        "safe_default": _choice(7, "Battle Master"),
        "push_default": _choice(7, "Battle Master"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "survival/tank coverage needed (Shield Master)",
                "upgrade_id": 6,
                "name": "Shield Master",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Battle Master",
            "csv_label_maps_to": "Battle Master",
            "csv_advice_text": "Shield Master only when survival/tank coverage is required; Gold Find label has no option.",
        },
        "explanation_summary": "Safe/push Battle Master; Shield Master only when tank/survival gap requires it.",
        "review_needed": False,
        "review_reasons": [],
    },
    2: {
        "advice_model": "safe_default",
        "safe_default": _choice(29, "War Domain"),
        "push_default": _choice(29, "War Domain"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "healing/survival coverage or formation gap clearly requires it",
                "upgrade_id": 30,
                "name": "Life Domain",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "War Domain",
            "csv_label_maps_to": "War Domain",
            "csv_advice_text": "Use Life Domain only when healing/survival coverage or formation gap clearly requires it.",
        },
        "explanation_summary": "Safe War Domain; Life Domain only when healing/survival or formation gap requires it.",
        "review_needed": False,
        "review_reasons": [],
    },
    3: {
        "advice_model": "safe_default",
        "safe_default": _choice(44, "Oath of Devotion"),
        "push_default": _choice(44, "Oath of Devotion"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "formation layout rewards alternative",
                "upgrade_id": 43,
                "name": "Oath of Vengeance",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Oath of Devotion",
            "csv_label_maps_to": "Oath of Devotion",
            "csv_advice_text": "Vengeance when formation layout rewards it.",
        },
        "explanation_summary": "Safe default Oath of Devotion; Vengeance when formation layout rewards it.",
        "review_needed": False,
        "review_reasons": [],
    },
    4: {
        "advice_model": "farm_default",
        "safe_default": _choice(59, "Leader of the Bregan D'aerthe"),
        "push_default": _choice(58, "Secret Lord of Luskan"),
        "farm_default": _choice(59, "Leader of the Bregan D'aerthe"),
        "conditionals": [
            {
                "when": "push/damage run needs Secret Lord of Luskan",
                "upgrade_id": 58,
                "name": "Secret Lord of Luskan",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Piracy",
            "csv_label_maps_to": "Leader of the Bregan D'aerthe",
            "csv_advice_text": "Gold/farm almost always Bregan; Secret Lord only for push/damage setups.",
        },
        "explanation_summary": "Safe/farm Bregan (Piracy→gold); push→Secret Lord of Luskan.",
        "review_needed": False,
        "review_reasons": [],
    },
    5: {
        "advice_model": "safe_default",
        "safe_default": _choice(75, "College of Valor"),
        "push_default": _choice(75, "College of Valor"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "specifically need Lore alternate utility/cooldown behavior",
                "upgrade_id": 76,
                "name": "College of Lore",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "College of Valor",
            "csv_label_maps_to": "College of Valor",
            "csv_advice_text": "Use Lore only when you specifically need the alternate utility/cooldown behavior.",
        },
        "explanation_summary": "Safe Valor; Lore only for alternate utility/cooldown behavior.",
        "review_needed": False,
        "review_reasons": [],
    },
    6: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "formation bond match required (per tier)", "upgrade_id": None, "name": None}
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Bond: Potpourri",
            "csv_label_maps_to": None,
            "csv_advice_text": "Always pick the bond that matches the current formation; no universal default.",
        },
        "explanation_summary": "Formation-only bonds. No universal default.",
        "review_needed": False,
        "review_reasons": [],
    },
    7: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "adventure enemy type Humanoids", "upgrade_id": 108, "name": "Favored Enemy: Humanoids"},
            {"when": "adventure enemy type Beasts", "upgrade_id": 109, "name": "Favored Enemy: Beasts"},
            {"when": "adventure enemy type Undead", "upgrade_id": 110, "name": "Favored Enemy: Undead"},
            {"when": "adventure enemy type Fey", "upgrade_id": 111, "name": "Favored Enemy: Fey"},
            {
                "when": "adventure enemy type Monstrosities",
                "upgrade_id": 112,
                "name": "Favored Enemy: Monstrosities",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": True,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Humanoid/Beast etc.",
            "csv_label_maps_to": None,
            "csv_advice_text": "Always match Favored Enemy to adventure/zone enemy types.",
        },
        "explanation_summary": "Adventure/enemy-type only; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    8: {
        "advice_model": "safe_default",
        "safe_default": _choice(129, "Font of Magic"),
        "push_default": _choice(129, "Font of Magic"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup explicitly needs Tides of Chaos instead of Font",
                "upgrade_id": 130,
                "name": "Tides of Chaos",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Damage route",
            "csv_label_maps_to": "Font of Magic",
            "csv_advice_text": "Font of Magic is the stable damage default; Tides only if setup requires it.",
        },
        "explanation_summary": "Safe/push Font of Magic; Tides only when setup explicitly needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    9: {
        "advice_model": "farm_default",
        "safe_default": _choice(139, "Dark Luck"),
        "push_default": _choice(140, "Dark Blessing"),
        "farm_default": _choice(139, "Dark Luck"),
        "conditionals": [
            {
                "when": "push/support run needs Dark Blessing instead of gold",
                "upgrade_id": 140,
                "name": "Dark Blessing",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Dark Luck",
            "csv_label_maps_to": "Dark Luck",
            "csv_advice_text": "Dark Luck for farm/favor; Dark Blessing only for push/support setups.",
        },
        "explanation_summary": "Safe/farm Dark Luck; push→Dark Blessing when not farming gold.",
        "review_needed": False,
        "review_reasons": [],
    },
    10: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "frontline/tank role", "upgrade_id": 146, "name": "Wild Shape"},
            {"when": "damage/support role", "upgrade_id": 145, "name": "Moonbeam"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Wild Shape",
            "csv_label_maps_to": None,
            "csv_advice_text": "Wild Shape for frontline/tank; Moonbeam for damage/support — role-dependent.",
        },
        "explanation_summary": "Role/formation only: Wild Shape vs Moonbeam; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    # --- batch 02 ---
    13: {
        "advice_model": "safe_default",
        "safe_default": _choice(391, "Charismatic"),
        "push_default": _choice(391, "Charismatic"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup explicitly needs More Daggers instead of CHA synergy",
                "upgrade_id": 386,
                "name": "More Daggers",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "High Cha route",
            "csv_label_maps_to": "Charismatic",
            "csv_advice_text": "More Daggers only when the setup explicitly needs that alternate.",
        },
        "explanation_summary": "Safe Charismatic (High Cha); More Daggers only when setup needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    14: {
        "advice_model": "safe_default",
        "safe_default": _choice(16056, "All Out Assault"),
        "push_default": _choice(16056, "All Out Assault"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "stack route / Birdsong stacking setup",
                "upgrade_id": 16057,
                "name": "Bend It Like Birdsong",
            },
            {
                "when": "speed-named option needed for farm clears",
                "upgrade_id": 16058,
                "name": "A Little Bit Faster Now",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "All Out Assault",
            "csv_advice_text": "Stack or speed options only when the setup explicitly needs them.",
        },
        "explanation_summary": "Safe All Out Assault; Birdsong/speed only when setup requires those routes.",
        "review_needed": False,
        "review_reasons": [],
    },
    15: {
        "advice_model": "safe_default",
        "safe_default": _choice(17242, "Eldritch Strike"),
        "push_default": _choice(17242, "Eldritch Strike"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier1 War Magic needed instead of Eldritch Strike",
                "upgrade_id": 17244,
                "name": "War Magic",
            },
            {
                "when": "tier1 Power Behind the Throne",
                "upgrade_id": 17243,
                "name": "Power Behind the Throne",
            },
            {"when": "tier0 Survival of the Strongest", "upgrade_id": 17238, "name": "Survival of the Strongest"},
            {"when": "tier0 Survival of the Fittest", "upgrade_id": 17239, "name": "Survival of the Fittest"},
            {"when": "tier0 Survival of the Smartest", "upgrade_id": 17240, "name": "Survival of the Smartest"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Damage route",
            "csv_label_maps_to": "Eldritch Strike",
            "csv_advice_text": "Damage route→Eldritch Strike; other tier0/tier1 picks only when setup needs them.",
        },
        "explanation_summary": "Safe Eldritch Strike (Damage route); other tier options are conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    16: {
        "advice_model": "safe_default",
        "safe_default": _choice(14878, "Circle of the Arctic"),
        "push_default": _choice(14878, "Circle of the Arctic"),
        "farm_default": None,
        "conditionals": [
            {"when": "encounter needs Mountain circle", "upgrade_id": 14877, "name": "Circle of the Mountain"},
            {"when": "encounter needs Swamp circle", "upgrade_id": 14879, "name": "Circle of the Swamp"},
            {"when": "tier1 Stoneskin", "upgrade_id": 14880, "name": "Stoneskin"},
            {"when": "tier1 Entanglement", "upgrade_id": 14881, "name": "Entanglement"},
            {"when": "tier1 Melf's Acid Arrow", "upgrade_id": 14882, "name": "Melf's Acid Arrow"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": True,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Circle of the Arctic",
            "csv_label_maps_to": "Circle of the Arctic",
            "csv_advice_text": "Deviate from Arctic only when the encounter clearly needs another circle/tier1.",
        },
        "explanation_summary": "Safe Arctic; other circles/tier1 only when encounter requires them.",
        "review_needed": False,
        "review_reasons": [],
    },
    17: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 Together In Magic", "upgrade_id": 14556, "name": "Together In Magic"},
            {"when": "tier0 Apart in Magic", "upgrade_id": 14557, "name": "Apart in Magic"},
            {"when": "tier1 Empowered Empowerment (config)", "upgrade_id": 14559, "name": "Empowered Empowerment"},
            {"when": "tier1 Empowered Orbs", "upgrade_id": 14558, "name": "Empowered Orbs"},
            {"when": "tier1 Use Smaller Words", "upgrade_id": 14560, "name": "Use Smaller Words"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support/Debuff",
            "csv_label_maps_to": None,
            "csv_advice_text": "Multi-tier formation/support choices; no single universal default.",
        },
        "explanation_summary": "Multi-tier formation/support; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    20: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "tier0: DPS column ahead of Regis", "upgrade_id": 11530, "name": "Ruby Encouragement (Ahead)"},
            {"when": "tier0: DPS column behind Regis", "upgrade_id": 11531, "name": "Ruby Encouragement (Behind)"},
            {"when": "tier1: BUD attack ranged", "upgrade_id": 11532, "name": "Ruby Weakness (Ranged)"},
            {"when": "tier1: BUD attack melee", "upgrade_id": 11533, "name": "Ruby Weakness (Melee)"},
            {"when": "tier1: BUD attack magic", "upgrade_id": 11534, "name": "Ruby Weakness (Magic)"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Ruby Encouragement (Ahead)",
            "csv_label_maps_to": None,
            "csv_advice_text": "Ahead/Behind from DPS column; Ruby Weakness from BUD attack type.",
        },
        "explanation_summary": "Handler: split Ahead/Behind from Ruby Weakness attack-type; no safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    22: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "enemy-type / Zorbu goal path Lead The Pack", "upgrade_id": 12993, "name": "Lead The Pack"},
            {"when": "enemy-type / partners path", "upgrade_id": 12994, "name": "Hunting Partners"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": True,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Enemy type route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Match enemy-type/goal path; no universal default.",
        },
        "explanation_summary": "Adventure/enemy-type dependent; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    25: {
        "advice_model": "safe_default",
        "safe_default": _choice(11313, "Big Push"),
        "push_default": _choice(11313, "Big Push"),
        "farm_default": None,
        "conditionals": [
            {"when": "crit/family path needed", "upgrade_id": 11314, "name": "Critical Family"},
            {"when": "piercing path needed", "upgrade_id": 11312, "name": "Piercing Arrow"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Big Push",
            "csv_advice_text": "Crit/piercing only when the composition explicitly needs those paths.",
        },
        "explanation_summary": "Safe Big Push; Critical Family / Piercing only when setup needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    26: {
        "advice_model": "safe_default",
        "safe_default": _choice(12211, "Compel Duel"),
        "push_default": _choice(12211, "Compel Duel"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "support allies path needed instead of Compel Duel",
                "upgrade_id": 12212,
                "name": "Lathander's Allies",
            },
            {
                "when": "protection fighting style needed",
                "upgrade_id": 12210,
                "name": "Fighting Style: Protection",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Compel Duel",
            "csv_advice_text": "Allies/Protection only when formation role clearly requires them.",
        },
        "explanation_summary": "Safe Compel Duel; Allies/Protection only when formation requires them.",
        "review_needed": False,
        "review_reasons": [],
    },
    28: {
        "advice_model": "farm_default",
        "safe_default": _choice(18862, "Troubadour Troupe"),
        "push_default": None,
        "farm_default": _choice(18862, "Troubadour Troupe"),
        "conditionals": [
            {"when": "alternate stories path needed", "upgrade_id": 18860, "name": "Unorthodox Stories"},
            {"when": "doom from afar path needed", "upgrade_id": 18861, "name": "DOOOOOM From Afar"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Boss Wants Speed",
            "csv_label_maps_to": "Troubadour Troupe",
            "csv_advice_text": "Speed/farm→Troubadour; other options only when setup needs them.",
        },
        "explanation_summary": "Safe/farm Troubadour Troupe (Boss Wants Speed); others conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    34: {
        "advice_model": "farm_default",
        "safe_default": _choice(18659, "Business Partners"),
        "push_default": None,
        "farm_default": _choice(18659, "Business Partners"),
        "conditionals": [
            {"when": "tier0 Not So Straightforward", "upgrade_id": 18657, "name": "Not So Straightforward"},
            {"when": "tier0 Scales and Horns", "upgrade_id": 18658, "name": "Scales and Horns"},
            {"when": "tier1 Command: Cower (config)", "upgrade_id": 18662, "name": "Command: Cower"},
            {"when": "tier1 Command: Hold", "upgrade_id": 18660, "name": "Command: Hold"},
            {"when": "tier1 Command: Duel", "upgrade_id": 18661, "name": "Command: Duel"},
            {"when": "tier1 Command: Droppit", "upgrade_id": 18663, "name": "Command: Droppit"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Business Partners",
            "csv_label_maps_to": "Business Partners",
            "csv_advice_text": "Business Partners for farm; other tier0/tier1 only when setup needs them.",
        },
        "explanation_summary": "Safe/farm Business Partners; other tier0/tier1 commands are conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    36: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {
                "when": "most specter targets: evil count (Dark Hunger)",
                "upgrade_id": 13246,
                "name": "The Dark Hunger",
            },
            {
                "when": "most specter targets: DEX≥16 (Shadows)",
                "upgrade_id": 13247,
                "name": "Shadows in the Night",
            },
            {
                "when": "most specter targets: CHA-highest (Charm)",
                "upgrade_id": 13248,
                "name": "Charm of the Fallen",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Specter-cap by formation counts; no universal safe default.",
        },
        "explanation_summary": "Specter-cap by formation counts; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    39: {
        "advice_model": "safe_default",
        "safe_default": _choice(2038, "Luck of the Vistani"),
        "push_default": None,
        "farm_default": _choice(2038, "Luck of the Vistani"),
        "conditionals": [
            {
                "when": "setup explicitly needs Additional Secrets",
                "upgrade_id": 2039,
                "name": "Additional Secrets",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Luck of the Vistani",
            "csv_advice_text": "Additional Secrets only when the setup explicitly needs that alternate.",
        },
        "explanation_summary": "Safe Luck of the Vistani; Additional Secrets only when setup needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    47: {
        "advice_model": "farm_default",
        "safe_default": _choice(9732, "Criminal Contacts"),
        "push_default": None,
        "farm_default": _choice(9732, "Criminal Contacts"),
        "conditionals": [
            {
                "when": "setup explicitly needs Alchemist's Fire Expertise instead of speed",
                "upgrade_id": 9731,
                "name": "Alchemist's Fire Expertise",
            },
            {
                "when": "setup explicitly needs Known Allies instead of speed",
                "upgrade_id": 9730,
                "name": "Known Allies",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Dash",
            "csv_label_maps_to": "Criminal Contacts",
            "csv_advice_text": "Prefer speed/farm (Criminal Contacts); only deviate if setup explicitly needs Fire/Allies.",
        },
        "explanation_summary": "Safe/farm Criminal Contacts (Dash/speed); Fire/Allies only when setup needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    55: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "tier1 Calm Under Pressure (config id 3336)", "upgrade_id": 3336, "name": "Calm Under Pressure"},
            {"when": "formation-dependent; pick per tier from options", "upgrade_id": None, "name": None},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Multi-tier formation picks; no universal safe default.",
        },
        "explanation_summary": "Multi-tier formation; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    64: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "handler path Epic Equipment", "upgrade_id": 16727, "name": "Epic Equipment"},
            {"when": "Premium Gear", "upgrade_id": 16728, "name": "Premium Gear"},
            {"when": "Shiniest Loot", "upgrade_id": 16729, "name": "Shiniest Loot"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Loot/gear choice needs handler context; no universal default.",
        },
        "explanation_summary": "Dynamic gear/loot handler; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    65: {
        "advice_model": "farm_default",
        "safe_default": _choice(12305, "Favored Friends"),
        "push_default": _choice(12305, "Favored Friends"),
        "farm_default": _choice(12306, "Long Term Investments"),
        "conditionals": [
            {
                "when": "gold/favor farm needs Long Term Investments",
                "upgrade_id": 12306,
                "name": "Long Term Investments",
            },
            {"when": "formation needs Form Ranks", "upgrade_id": 12304, "name": "Form Ranks"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Favored Friends",
            "csv_advice_text": "Long Term Investments for gold/favor farm; Form Ranks when formation needs it.",
        },
        "explanation_summary": "Safe/push Favored Friends; farm→Long Term Investments; Form Ranks conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    82: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "formation needs tankiness → Shield Wall", "upgrade_id": 15961, "name": "Shield Wall"},
            {"when": "formation needs support → Impromptu Allies", "upgrade_id": 15959, "name": "Impromptu Allies"},
            {"when": "For The Greater Good", "upgrade_id": 15960, "name": "For The Greater Good"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Shield Wall",
            "csv_label_maps_to": None,
            "csv_advice_text": "Pick tank vs support from formation gaps; no universal safe default.",
        },
        "explanation_summary": "Formation-gap dependent; no universal safe default.",
        "review_needed": False,
        "review_reasons": [],
    },
    149: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "config Legacy of Ravengard (unverified)", "upgrade_id": 15033, "name": "Legacy of Ravengard"},
            {"when": "Lead The Charge", "upgrade_id": 15031, "name": "Lead The Charge"},
            {"when": "Strength of Baldur's Gate", "upgrade_id": 15032, "name": "Strength of Baldur's Gate"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "No CSV source; keep null until a stable universal default is confirmed.",
        },
        "explanation_summary": "Recent champ; no CSV. Keep safe_default null.",
        "review_needed": False,
        "review_reasons": [],
    },
    153: {
        "advice_model": "conditional_only",
        "safe_default": None,
        "push_default": None,
        "farm_default": None,
        "conditionals": [
            {"when": "config Kas the Betrayer (unverified)", "upgrade_id": 15624, "name": "Kas the Betrayer"},
            {"when": "Kas the Bloody Handed", "upgrade_id": 15623, "name": "Kas the Bloody Handed"},
            {"when": "Kas the Destroyer", "upgrade_id": 15625, "name": "Kas the Destroyer"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "No CSV source; keep null until a stable universal default is confirmed.",
        },
        "explanation_summary": "Recent champ; no CSV. Keep safe_default null.",
        "review_needed": False,
        "review_reasons": [],
    },
}


def _options_by_tier(cfg: dict) -> dict:
    tiers: dict[str, list[dict]] = {}
    for opt in cfg.get("options") or []:
        tier = str(int(opt.get("tier_index") or 0))
        tiers.setdefault(tier, []).append(
            {
                "upgrade_id": int(opt["upgrade_id"]),
                "name": opt.get("name"),
                "required_level": opt.get("required_level"),
            }
        )
    return dict(sorted(tiers.items(), key=lambda kv: int(kv[0])))


def main() -> int:
    rules = load_specialization_rules()
    heroes = rules.get("heroes") or {}
    out_heroes: dict[str, dict] = {}
    for hero_id, model in sorted(RECORDS.items()):
        cfg = heroes.get(str(hero_id))
        if not isinstance(cfg, dict):
            raise SystemExit(f"missing hero {hero_id} in specializations.json")
        name = str(cfg.get("name") or f"Hero {hero_id}")
        out_heroes[str(hero_id)] = {
            "hero_id": hero_id,
            "name": name,
            "has_dynamic_handler": bool(model.get("has_dynamic_handler")),
            **{k: v for k, v in model.items()},
            "options_by_tier": _options_by_tier(cfg),
        }
    from ic_gamedata.specialization_engine import HERO_HANDLERS

    for hid, row in out_heroes.items():
        row["has_dynamic_handler"] = int(hid) in HERO_HANDLERS

    payload = {
        "version": 1,
        "notes": (
            "Advisor-facing specialization model. Separates safe/push/farm defaults "
            "and conditionals. review_needed means do not silently pick one conflict side."
        ),
        "heroes": out_heroes,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(out_heroes)} heroes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
