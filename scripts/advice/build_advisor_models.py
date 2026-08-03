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
    # --- batch 03 remaining ---
    11: {
        "advice_model": "safe_default",
        "safe_default": _choice(239, "Bruiser"),
        "push_default": _choice(239, "Bruiser"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup explicitly needs Indomitable Might instead of damage",
                "upgrade_id": 240,
                "name": "Indomitable Might",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Bruiser",
            "csv_label_maps_to": "Bruiser",
            "csv_advice_text": "Indomitable Might only as explicit alternate when not using damage.",
        },
        "explanation_summary": "Safe Bruiser; Indomitable Might only when setup needs that alternate.",
        "review_needed": False,
        "review_reasons": [],
    },
    12: {
        "advice_model": "safe_default",
        "safe_default": _choice(244, "Usurped Power"),
        "push_default": _choice(244, "Usurped Power"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "formation needs Bulk Up survivability instead of usurp DPS",
                "upgrade_id": 243,
                "name": "Bulk Up",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Usurp",
            "csv_label_maps_to": "Usurped Power",
            "csv_advice_text": "Bulk Up only when formation needs survivability instead of usurp DPS.",
        },
        "explanation_summary": "Safe Usurped Power (CSV Usurp); Bulk Up when formation needs survivability.",
        "review_needed": False,
        "review_reasons": [],
    },
    18: {
        "advice_model": "safe_default",
        "safe_default": _choice(11517, "Drow Stalker"),
        "push_default": _choice(11517, "Drow Stalker"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "not using Drizzt as carry / need Companions support",
                "upgrade_id": 11516,
                "name": "Leader of the Companions",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "DPS route",
            "csv_label_maps_to": "Drow Stalker",
            "csv_advice_text": "Companions path only when not using Drizzt as carry.",
        },
        "explanation_summary": "Safe Drow Stalker (DPS/carry); Companions when not the carry.",
        "review_needed": False,
        "review_reasons": [],
    },
    19: {
        "advice_model": "safe_default",
        "safe_default": _choice(10690, "Booming Voice"),
        "push_default": _choice(10690, "Booming Voice"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "healing/sustain coverage clearly required",
                "upgrade_id": 10689,
                "name": "Greater Blessing",
            },
            {
                "when": "setup explicitly needs Hammer of the Law",
                "upgrade_id": 10691,
                "name": "Hammer of the Law",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Healing route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Greater Blessing when sustain required; Hammer only if setup needs it.",
        },
        "explanation_summary": "Safe Booming Voice; Greater Blessing for sustain; Healing/Support labels unmapped.",
        "review_needed": False,
        "review_reasons": [],
    },
    21: {
        "advice_model": "safe_default",
        "safe_default": _choice(10783, "Concertino"),
        "push_default": _choice(10783, "Concertino"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier1 support role instead of carry DPS", "upgrade_id": 10781, "name": "Unison"},
            {"when": "tier1 Soprano path needed", "upgrade_id": 10782, "name": "Soprano"},
            {"when": "tier0 Theme of Valor", "upgrade_id": 10778, "name": "Theme of Valor"},
            {"when": "tier0 Theme of Consideration", "upgrade_id": 10779, "name": "Theme of Consideration"},
            {"when": "tier0 Theme of Deception", "upgrade_id": 10780, "name": "Theme of Deception"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "DPS route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Multi-tier: Concertino for carry DPS; themes/support are conditional.",
        },
        "explanation_summary": "Safe Concertino (tier1 DPS); themes and support paths are conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    23: {
        "advice_model": "safe_default",
        "safe_default": _choice(12292, "Smelly Lunch"),
        "push_default": _choice(12292, "Smelly Lunch"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "stacking Power of Friendship",
                "upgrade_id": 12290,
                "name": "Olfactory Fatigue",
            },
            {
                "when": "many Tieflings in formation",
                "upgrade_id": 12291,
                "name": "Scent of Brimstone",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Smelly Lunch",
            "csv_label_maps_to": "Smelly Lunch",
            "csv_advice_text": "Olfactory Fatigue for Power of Friendship; Brimstone with many Tieflings.",
        },
        "explanation_summary": "Safe Smelly Lunch; Fatigue/Brimstone only for Friendship or Tiefling setups.",
        "review_needed": False,
        "review_reasons": [],
    },
    24: {
        "advice_model": "safe_default",
        "safe_default": _choice(13005, "Githzerai Focus"),
        "push_default": _choice(13005, "Githzerai Focus"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "race/agility support interactions needed instead of Focus",
                "upgrade_id": 13006,
                "name": "Githzerai Agility",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Buff route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Agility only when race/agility support interactions are required.",
        },
        "explanation_summary": "Safe Githzerai Focus; Agility only when race interactions require it.",
        "review_needed": False,
        "review_reasons": [],
    },
    27: {
        "advice_model": "safe_default",
        "safe_default": _choice(18465, "Tallest in Faerûn"),
        "push_default": _choice(18465, "Tallest in Faerûn"),
        "farm_default": None,
        "conditionals": [
            {"when": "setup explicitly needs Overkill damage", "upgrade_id": 18463, "name": "Overkill"},
            {
                "when": "setup explicitly needs Dwarven Encouragement",
                "upgrade_id": 18464,
                "name": "Dwarven Encouragement",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Overkill/Encouragement only when formation or role clearly requires them.",
        },
        "explanation_summary": "Safe Tallest in Faerûn; Overkill/Encouragement only when setup needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    29: {
        "advice_model": "safe_default",
        "safe_default": _choice(1196, "Follow Closely"),
        "push_default": _choice(1196, "Follow Closely"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup explicitly needs Trying Extra Hard",
                "upgrade_id": 1195,
                "name": "Trying Extra Hard",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Trying Extra Hard only when setup explicitly needs that alternate.",
        },
        "explanation_summary": "Safe Follow Closely; Trying Extra Hard only when setup needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    30: {
        "advice_model": "safe_default",
        "safe_default": _choice(1237, "Resist the Curse"),
        "push_default": _choice(1237, "Resist the Curse"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup explicitly needs Lycanthrope Forever",
                "upgrade_id": 1238,
                "name": "Lycanthrope Forever",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Lycanthrope Forever only when setup explicitly needs that alternate.",
        },
        "explanation_summary": "Safe Resist the Curse; Lycanthrope Forever only when setup needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    31: {
        "advice_model": "safe_default",
        "safe_default": _choice(16532, "Friend to the Familiar"),
        "push_default": _choice(16532, "Friend to the Familiar"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "formation needs Friend to the Feared",
                "upgrade_id": 16533,
                "name": "Friend to the Feared",
            },
            {
                "when": "formation needs Friend to the Exceptional",
                "upgrade_id": 16534,
                "name": "Friend to the Exceptional",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Feared/Exceptional only when formation composition requires them.",
        },
        "explanation_summary": "Safe Friend to the Familiar; other friend paths when formation needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    32: {
        "advice_model": "safe_default",
        "safe_default": _choice(11509, "Flag Bearer"),
        "push_default": _choice(11509, "Flag Bearer"),
        "farm_default": None,
        "conditionals": [
            {"when": "setup needs Heavy Blows damage", "upgrade_id": 11508, "name": "Heavy Blows"},
            {"when": "setup needs Moradin's Will", "upgrade_id": 11510, "name": "Moradin's Will"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Heavy Blows/Moradin's Will only when setup clearly requires them.",
        },
        "explanation_summary": "Safe Flag Bearer; Heavy Blows/Moradin's Will only when setup needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    33: {
        "advice_model": "safe_default",
        "safe_default": _choice(17839, "Daughters of Mehen"),
        "push_default": _choice(17839, "Daughters of Mehen"),
        "farm_default": None,
        "conditionals": [
            {"when": "setup needs Fury of Asmodeus", "upgrade_id": 17840, "name": "Fury of Asmodeus"},
            {"when": "setup needs Pact with Lorcan", "upgrade_id": 17841, "name": "Pact with Lorcan"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "No CSV; Asmodeus/Lorcan only when setup explicitly needs them.",
        },
        "explanation_summary": "Safe Daughters of Mehen; other pacts only when setup needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    35: {
        "advice_model": "safe_default",
        "safe_default": _choice(1659, "Breaking Out Solo"),
        "push_default": _choice(1659, "Breaking Out Solo"),
        "farm_default": None,
        "conditionals": [
            {"when": "setup explicitly needs Spy Network", "upgrade_id": 1658, "name": "Spy Network"}
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Spy Network only when setup explicitly needs that alternate.",
        },
        "explanation_summary": "Safe Breaking Out Solo; Spy Network only when setup needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    37: {
        "advice_model": "safe_default",
        "safe_default": _choice(9747, "Kelemvor's Foe"),
        "push_default": _choice(9747, "Kelemvor's Foe"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "healing/sustain coverage required",
                "upgrade_id": 9745,
                "name": "Kelemvor's Heal",
            },
            {"when": "setup needs Kelemvor's Will", "upgrade_id": 9746, "name": "Kelemvor's Will"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Heal/Will only when sustain or that alternate is required.",
        },
        "explanation_summary": "Safe Kelemvor's Foe; Heal/Will only when setup needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    38: {
        "advice_model": "safe_default",
        "safe_default": _choice(17328, "Velvet Touch"),
        "push_default": _choice(17328, "Velvet Touch"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "formation leans on Ligotti's Minions scaling",
                "upgrade_id": 17329,
                "name": "Ligotti's Minions",
            },
            {
                "when": "formation leans on The Unknowable Ur",
                "upgrade_id": 17330,
                "name": "The Unknowable Ur",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Efficient Bookkeeping",
            "csv_label_maps_to": None,
            "csv_advice_text": "Bookkeeping/Pain labels unmapped; alternate scaling only if formation leans on it.",
        },
        "explanation_summary": "Safe Velvet Touch; Minions/Ur only when formation leans on that scaling.",
        "review_needed": False,
        "review_reasons": [],
    },
    40: {
        "advice_model": "safe_default",
        "safe_default": _choice(2112, "Collector"),
        "push_default": _choice(2112, "Collector"),
        "farm_default": None,
        "conditionals": [
            {"when": "setup explicitly needs Assassinate", "upgrade_id": 2111, "name": "Assassinate"}
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Assassinate only when setup explicitly needs that alternate.",
        },
        "explanation_summary": "Safe Collector; Assassinate only when setup needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    41: {
        "advice_model": "safe_default",
        "safe_default": _choice(15613, "Busy Beestinger"),
        "push_default": _choice(15613, "Busy Beestinger"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier1 Grandma-Bod path needed", "upgrade_id": 15612, "name": "Grandma-Bod"},
            {"when": "tier1 Slower Decay path needed", "upgrade_id": 15614, "name": "Slower Decay"},
            {"when": "tier0 Matriarch", "upgrade_id": 15609, "name": "Matriarch"},
            {"when": "tier0 Familiar Friends", "upgrade_id": 15610, "name": "Familiar Friends"},
            {"when": "tier0 Grandmother Night", "upgrade_id": 15611, "name": "Grandmother Night"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Damage route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Multi-tier: Busy Beestinger for damage; other tier0/tier1 only if needed.",
        },
        "explanation_summary": "Safe Busy Beestinger (tier1 damage); other tier options are conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    42: {
        "advice_model": "safe_default",
        "safe_default": _choice(8785, "Stormbreaker"),
        "push_default": _choice(8785, "Stormbreaker"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "debuff path needed instead of tank Stormbreaker",
                "upgrade_id": 8784,
                "name": "Stormcaller",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Tank route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Stormcaller only when the debuff path is clearly required.",
        },
        "explanation_summary": "Safe Stormbreaker (tank); Stormcaller only for the debuff path.",
        "review_needed": False,
        "review_reasons": [],
    },
    43: {
        "advice_model": "safe_default",
        "safe_default": _choice(10683, "Adopted Family"),
        "push_default": _choice(10683, "Adopted Family"),
        "farm_default": None,
        "conditionals": [
            {"when": "Kobold Family synergy required", "upgrade_id": 10681, "name": "Kobold Family"},
            {"when": "Centi-pult niche synergy required", "upgrade_id": 10682, "name": "Centi-pult"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Pack Tactics",
            "csv_label_maps_to": None,
            "csv_advice_text": "Pack Tactics is not an option; Kobold/Centi-pult only for niche synergy.",
        },
        "explanation_summary": "Safe Adopted Family; Kobold Family/Centi-pult only for niche synergy.",
        "review_needed": False,
        "review_reasons": [],
    },
    # --- batch 04 remaining ---
    44: {
        "advice_model": "safe_default",
        "safe_default": _choice(8772, "Empowered Blessing"),
        "push_default": _choice(8772, "Empowered Blessing"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "offense more important than healing/support",
                "upgrade_id": 8771,
                "name": "Expanded Blessing",
            },
            {"when": "setup explicitly needs Seized Assets", "upgrade_id": 8773, "name": "Seized Assets"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Empowered Blessing",
            "csv_label_maps_to": "Empowered Blessing",
            "csv_advice_text": "Expanded Blessing/Seized Assets only when offense or that alternate is needed.",
        },
        "explanation_summary": "Safe Empowered Blessing; Expanded Blessing/Seized Assets only as alternates.",
        "review_needed": False,
        "review_reasons": [],
    },
    45: {
        "advice_model": "safe_default",
        "safe_default": _choice(13041, "Samurai Training (Behind)"),
        "push_default": _choice(13041, "Samurai Training (Behind)"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "carry adjacency needs In Front",
                "upgrade_id": 13042,
                "name": "Samurai Training (In Front)",
            },
            {
                "when": "carry adjacency needs Beside",
                "upgrade_id": 13043,
                "name": "Samurai Training (Beside)",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Rapid Training",
            "csv_label_maps_to": "Samurai Training (Behind)",
            "csv_advice_text": "In Front/Beside only when carry adjacency requires that variant.",
        },
        "explanation_summary": "Safe Samurai Training (Behind); In Front/Beside by adjacency/carry setup.",
        "review_needed": False,
        "review_reasons": [],
    },
    46: {
        "advice_model": "safe_default",
        "safe_default": _choice(19714, "Ah, Screw It"),
        "push_default": _choice(19714, "Ah, Screw It"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 Extended Warranty needed", "upgrade_id": 19712, "name": "Extended Warranty"},
            {"when": "tier0 Sign and Date needed", "upgrade_id": 19713, "name": "Sign and Date"},
            {"when": "tier1 Co-Signers support", "upgrade_id": 19715, "name": "Co-Signers"},
            {"when": "tier1 Temporary Alliance support", "upgrade_id": 19716, "name": "Temporary Alliance"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Tier1 Co-Signers/Temporary Alliance only as conditional support variants.",
        },
        "explanation_summary": "Safe Ah, Screw It (tier0); tier1 support variants are conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    48: {
        "advice_model": "safe_default",
        "safe_default": _choice(12132, "Darkmagic Cheer Squad"),
        "push_default": _choice(12132, "Darkmagic Cheer Squad"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup really benefits from the magic-themed option",
                "upgrade_id": 12133,
                "name": "Magic {magic}#CCC {magic}#888 {magic}#444",
            },
            {"when": "setup explicitly needs Unpaid Extras", "upgrade_id": 12134, "name": "Unpaid Extras"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Magic magic magic",
            "csv_label_maps_to": "Darkmagic Cheer Squad",
            "csv_advice_text": "Magic-themed option only if the setup really benefits from it.",
        },
        "explanation_summary": "Safe Darkmagic Cheer Squad; magic-themed option only when setup benefits.",
        "review_needed": False,
        "review_reasons": [],
    },
    49: {
        "advice_model": "safe_default",
        "safe_default": _choice(10664, "Voice of Authority"),
        "push_default": _choice(10664, "Voice of Authority"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "frontline/survivability needs Voice of Resilience",
                "upgrade_id": 10663,
                "name": "Voice of Resilience",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Frontline",
            "csv_label_maps_to": None,
            "csv_advice_text": "Voice of Resilience only for frontline/survivability needs.",
        },
        "explanation_summary": "Safe Voice of Authority; Resilience only for frontline survivability.",
        "review_needed": False,
        "review_reasons": [],
    },
    50: {
        "advice_model": "safe_default",
        "safe_default": _choice(11496, "Recruiting Drive"),
        "push_default": _choice(11496, "Recruiting Drive"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "niche DPS/comp needs Critical Wound",
                "upgrade_id": 11498,
                "name": "Critical Wound",
            },
            {
                "when": "setup needs Scents of Mithral Hall",
                "upgrade_id": 11497,
                "name": "Scents of Mithral Hall",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Critical Wound/Scents only for niche comps or explicit needs.",
        },
        "explanation_summary": "Safe Recruiting Drive; alternatives only for niche comps.",
        "review_needed": False,
        "review_reasons": [],
    },
    51: {
        "advice_model": "safe_default",
        "safe_default": _choice(3099, "Empowered Mirrors"),
        "push_default": _choice(3099, "Empowered Mirrors"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 Good mirror path", "upgrade_id": 3095, "name": "Mirror Focus (Good)"},
            {"when": "tier0 Neutral mirror path", "upgrade_id": 3096, "name": "Mirror Focus (Neutral)"},
            {"when": "tier0 Evil mirror path", "upgrade_id": 3097, "name": "Mirror Focus (Evil)"},
            {
                "when": "tier1 Sturdy Mirrors needed instead of Empowered",
                "upgrade_id": 3098,
                "name": "Sturdy Mirrors",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Good/Sturdy mirror path",
            "csv_label_maps_to": "Empowered Mirrors",
            "csv_advice_text": "Tier0 Good/Neutral/Evil mirrors are contextual; Sturdy when needed.",
        },
        "explanation_summary": "Safe Empowered Mirrors (tier1); tier0 mirror foci are contextual.",
        "review_needed": False,
        "review_reasons": [],
    },
    52: {
        "advice_model": "farm_default",
        "safe_default": _choice(8866, "Nature's Wrath"),
        "push_default": None,
        "farm_default": _choice(8866, "Nature's Wrath"),
        "conditionals": [
            {
                "when": "tank/survival content needs Dedicated Guardian",
                "upgrade_id": 8763,
                "name": "Dedicated Guardian",
            },
            {"when": "setup needs Sentry's Homeland", "upgrade_id": 8867, "name": "Sentry's Homeland"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Nature's Wrath",
            "csv_advice_text": "Dedicated Guardian only for hard survival content.",
        },
        "explanation_summary": "Safe/farm Nature's Wrath (speed); Guardian only for hard survival.",
        "review_needed": False,
        "review_reasons": [],
    },
    53: {
        "advice_model": "safe_default",
        "safe_default": _choice(3215, "Plague Focus: {Pain}#F00"),
        "push_default": _choice(3215, "Plague Focus: {Pain}#F00"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup needs Traitor plague focus",
                "upgrade_id": 3216,
                "name": "Plague Focus: {Traitor}#F0F",
            },
            {
                "when": "setup needs Pilfer plague focus",
                "upgrade_id": 3214,
                "name": "Plague Focus: {Pilfer}#0F0",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Pain",
            "csv_label_maps_to": "Plague Focus: {Pain}#F00",
            "csv_advice_text": "Traitor/Pilfer only when the setup needs those plague foci.",
        },
        "explanation_summary": "Safe Plague Focus Pain; Traitor/Pilfer only when setup needs them.",
        "review_needed": False,
        "review_reasons": [],
    },
    54: {
        "advice_model": "safe_default",
        "safe_default": _choice(3270, "Observance: Foe"),
        "push_default": _choice(3270, "Observance: Foe"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup maximizes Observance: Friend scaling",
                "upgrade_id": 3269,
                "name": "Observance: Friend",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Observe",
            "csv_label_maps_to": None,
            "csv_advice_text": "Observance: Friend only when that scaling is better for the setup.",
        },
        "explanation_summary": "Safe Observance: Foe; Friend only when that scaling fits the setup.",
        "review_needed": False,
        "review_reasons": [],
    },
    56: {
        "advice_model": "safe_default",
        "safe_default": _choice(18043, "Dembo"),
        "push_default": _choice(18043, "Dembo"),
        "farm_default": None,
        "conditionals": [
            {"when": "specific comp needs Olla", "upgrade_id": 18044, "name": "Olla"},
            {"when": "specific comp needs Bosh", "upgrade_id": 18045, "name": "Bosh"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Imp route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Olla/Bosh only when a specific composition needs them.",
        },
        "explanation_summary": "Safe Dembo; Olla/Bosh only for specific compositions.",
        "review_needed": False,
        "review_reasons": [],
    },
    57: {
        "advice_model": "safe_default",
        "safe_default": _choice(13255, "Fungal Body"),
        "push_default": _choice(13255, "Fungal Body"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "healing/sustain coverage required",
                "upgrade_id": 13254,
                "name": "Spreading Spores",
            },
            {"when": "setup needs Simple Infection", "upgrade_id": 13253, "name": "Simple Infection"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Spores",
            "csv_label_maps_to": "Fungal Body",
            "csv_advice_text": "Spreading Spores/Simple Infection when healing/sustain is required.",
        },
        "explanation_summary": "Safe Fungal Body; Spores/Infection when healing/sustain is needed.",
        "review_needed": False,
        "review_reasons": [],
    },
    58: {
        "advice_model": "farm_default",
        "safe_default": _choice(3457, "Go With The Phlo"),
        "push_default": None,
        "farm_default": _choice(3457, "Go With The Phlo"),
        "conditionals": [
            {"when": "tank survivability needed", "upgrade_id": 3456, "name": "Tempered Steel"},
            {"when": "setup needs Metalborn", "upgrade_id": 3455, "name": "Metalborn"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Go With The Phlo",
            "csv_advice_text": "Tempered Steel/Metalborn only when tank survivability is required.",
        },
        "explanation_summary": "Safe/farm Go With The Phlo (speed); tank options only for survival.",
        "review_needed": False,
        "review_reasons": [],
    },
    59: {
        "advice_model": "farm_default",
        "safe_default": _choice(19340, "Melf's Speedy Spawns"),
        "push_default": _choice(19342, "Melf's Abundant Allies"),
        "farm_default": _choice(19340, "Melf's Speedy Spawns"),
        "conditionals": [
            {"when": "tier0 Frequent Foes needed", "upgrade_id": 19339, "name": "Melf's Frequent Foes"},
            {"when": "tier0 Doubled Drops needed", "upgrade_id": 19341, "name": "Melf's Doubled Drops"},
            {
                "when": "tier1 Adaptive Attacks needed",
                "upgrade_id": 19343,
                "name": "Melf's Adaptive Attacks",
            },
            {"when": "tier1 Ranked Roles needed", "upgrade_id": 19344, "name": "Melf's Ranked Roles"},
            {
                "when": "tier1 Amorphous Alignment needed",
                "upgrade_id": 19345,
                "name": "Melf's Amorphous Alignment",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Melf's Speedy Spawns",
            "csv_advice_text": "Abundant Allies for push; other tier0/tier1 Melf picks are conditional.",
        },
        "explanation_summary": "Safe/farm Speedy Spawns; push Abundant Allies; other Melf picks conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    60: {
        "advice_model": "safe_default",
        "safe_default": _choice(9634, "Keep Your Friends Close"),
        "push_default": _choice(9634, "Keep Your Friends Close"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup explicitly needs Keep Your Enemies Closer",
                "upgrade_id": 9635,
                "name": "Keep Your Enemies Closer",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Enemies Closer only when setup explicitly needs that alternate.",
        },
        "explanation_summary": "Safe Keep Your Friends Close; Enemies Closer only when setup needs it.",
        "review_needed": False,
        "review_reasons": [],
    },
    61: {
        "advice_model": "safe_default",
        "safe_default": _choice(9714, "Class Act - Spellslingers"),
        "push_default": _choice(9714, "Class Act - Spellslingers"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 Class Act - Bruisers", "upgrade_id": 9715, "name": "Class Act - Bruisers"},
            {"when": "tier0 Class Act - Hybrids", "upgrade_id": 9716, "name": "Class Act - Hybrids"},
            {
                "when": "tier0 Class Act - Baldur's Gate",
                "upgrade_id": 9717,
                "name": "Class Act - Baldur's Gate",
            },
            {"when": "tier1 Hunter - Nature", "upgrade_id": 9718, "name": "Hunter - Nature"},
            {
                "when": "tier1 Hunter - Twisted Creatures",
                "upgrade_id": 9719,
                "name": "Hunter - Twisted Creatures",
            },
            {"when": "tier1 Hunter - Civilization", "upgrade_id": 9720, "name": "Hunter - Civilization"},
            {"when": "tier1 Hunter - Soulless", "upgrade_id": 9721, "name": "Hunter - Soulless"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": True,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Other Class Acts and Hunter nature/type picks are tier conditionals.",
        },
        "explanation_summary": "Safe Class Act Spellslingers; other Class Acts and Hunters are conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    62: {
        "advice_model": "safe_default",
        "safe_default": _choice(8754, "Tight Knit"),
        "push_default": _choice(8754, "Tight Knit"),
        "farm_default": None,
        "conditionals": [
            {"when": "tankier route needed", "upgrade_id": 8753, "name": "New Recruits"}
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "New Recruits only when a tankier route is needed.",
        },
        "explanation_summary": "Safe Tight Knit; New Recruits only for the tankier route.",
        "review_needed": False,
        "review_reasons": [],
    },
    63: {
        "advice_model": "farm_default",
        "safe_default": _choice(4043, "Always Expect Chaos"),
        "push_default": None,
        "farm_default": _choice(4043, "Always Expect Chaos"),
        "conditionals": [
            {"when": "alignment setup needs Trust in Law", "upgrade_id": 4041, "name": "Trust in Law"},
            {
                "when": "alignment setup needs Value Neutrality",
                "upgrade_id": 4042,
                "name": "Value Neutrality",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Law/Chaos etc.",
            "csv_label_maps_to": None,
            "csv_advice_text": "Law/Neutral only when alignment coverage requires them.",
        },
        "explanation_summary": "Safe Always Expect Chaos; Law/Neutral only for alignment coverage.",
        "review_needed": False,
        "review_reasons": [],
    },
    66: {
        "advice_model": "safe_default",
        "safe_default": _choice(17484, "Fury of the Brawl"),
        "push_default": _choice(17484, "Fury of the Brawl"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 Fury of the Cabal needed", "upgrade_id": 17485, "name": "Fury of the Cabal"},
            {"when": "tier0 Fury of the Stall needed", "upgrade_id": 17486, "name": "Fury of the Stall"},
            {"when": "tier1 Guardian path", "upgrade_id": 17487, "name": "Guardian"},
            {"when": "tier1 Infiltrator path", "upgrade_id": 17488, "name": "Infiltrator"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Guardian vs Infiltrator are tier1 conditionals; other Furies if needed.",
        },
        "explanation_summary": "Safe Fury of the Brawl; Guardian/Infiltrator are tier1 conditionals.",
        "review_needed": False,
        "review_reasons": [],
    },
    67: {
        "advice_model": "safe_default",
        "safe_default": _choice(3278, "Scent: Herbs and Spices"),
        "push_default": _choice(3278, "Scent: Herbs and Spices"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "survivability/tank pressure requires Roasted Chicken",
                "upgrade_id": 3277,
                "name": "Scent: Roasted Chicken",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Tank route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Roasted Chicken only when survivability is the problem.",
        },
        "explanation_summary": "Safe Herbs and Spices; Roasted Chicken only when survivability is the problem.",
        "review_needed": False,
        "review_reasons": [],
    },
    # --- batch 05 remaining ---
    68: {
        "advice_model": "safe_default",
        "safe_default": _choice(4349, "Shield Guardian"),
        "push_default": _choice(4349, "Shield Guardian"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "magic-heavy formation and caster synergy is the goal",
                "upgrade_id": 4350,
                "name": "Urchin Pranks",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Magic route",
            "csv_label_maps_to": "Shield Guardian",
            "csv_advice_text": "Urchin Pranks only in magic-heavy formations for caster synergy.",
        },
        "explanation_summary": "Safe Shield Guardian; Urchin Pranks only for magic-heavy caster synergy.",
        "review_needed": False,
        "review_reasons": [],
    },
    69: {
        "advice_model": "safe_default",
        "safe_default": _choice(4493, "Tiamat's Rage"),
        "push_default": _choice(4493, "Tiamat's Rage"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "setup prefers alternative support/DPS interaction",
                "upgrade_id": 4492,
                "name": "Tiamat's Word",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Tiamat's Word only if the setup prefers that support/DPS interaction.",
        },
        "explanation_summary": "Safe/push Tiamat's Rage; Tiamat's Word only for alternate support/DPS setups.",
        "review_needed": False,
        "review_reasons": [],
    },
    70: {
        "advice_model": "safe_default",
        "safe_default": _choice(15041, "We've Trained For This"),
        "push_default": _choice(15041, "We've Trained For This"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "formation/target mix clearly prefers Vampire Hunter",
                "upgrade_id": 15042,
                "name": "Vampire Hunter",
            },
            {
                "when": "formation/target mix clearly prefers The Devil You Know",
                "upgrade_id": 15043,
                "name": "The Devil You Know",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "We've Trained For This",
            "csv_advice_text": "Vampire Hunter/Devil You Know only when formation or targets make them better.",
        },
        "explanation_summary": "Safe We've Trained For This; Hunter/Devil only when formation/targets prefer them.",
        "review_needed": False,
        "review_reasons": [],
    },
    71: {
        "advice_model": "safe_default",
        "safe_default": _choice(14705, "Everybody Gets To Be Friends"),
        "push_default": _choice(14705, "Everybody Gets To Be Friends"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 route specifically needed → Keep Your Friends Close",
                "upgrade_id": 14703,
                "name": "Keep Your Friends Close",
            },
            {
                "when": "tier0 route specifically needed → Keep Your Future Friends Closer",
                "upgrade_id": 14704,
                "name": "Keep Your Future Friends Closer",
            },
            {
                "when": "tier1 encounter/control need specifically needs it → Fury of the Fireflies",
                "upgrade_id": 14706,
                "name": "Fury of the Fireflies",
            },
            {
                "when": "tier1 encounter/control need specifically needs it → Splitting The Hive",
                "upgrade_id": 14707,
                "name": "Splitting The Hive",
            },
            {
                "when": "tier1 encounter/control need specifically needs it → Dance of the Ladybugs",
                "upgrade_id": 14708,
                "name": "Dance of the Ladybugs",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": True,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Everybody Gets To Be Friends",
            "csv_advice_text": "Tier0 friends routes and tier1 control picks are encounter-specific.",
        },
        "explanation_summary": "Safe Everybody Gets To Be Friends; tier0/1 alternatives stay encounter-specific.",
        "review_needed": False,
        "review_reasons": [],
    },
    72: {
        "advice_model": "safe_default",
        "safe_default": _choice(19253, "Dichromancy"),
        "push_default": _choice(19253, "Dichromancy"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational corrosion-focused variant is better",
                "upgrade_id": 19254,
                "name": "Corrosion Master",
            },
            {
                "when": "situational chill-focused variant is better",
                "upgrade_id": 19255,
                "name": "Lingering Chill",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Dichromancy",
            "csv_advice_text": "Corrosion Master/Lingering Chill only as situational variants.",
        },
        "explanation_summary": "Safe Dichromancy; Corrosion Master/Lingering Chill are situational only.",
        "review_needed": False,
        "review_reasons": [],
    },
    73: {
        "advice_model": "safe_default",
        "safe_default": _choice(4749, "Baeloth's Birthday Party"),
        "push_default": _choice(4749, "Baeloth's Birthday Party"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "specific utility interaction is needed",
                "upgrade_id": 4750,
                "name": "Over Excited",
            },
            {
                "when": "death-prevention interaction is needed",
                "upgrade_id": 4751,
                "name": "The Show Must Go On",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Baeloth's Birthday Party",
            "csv_advice_text": "Over Excited for utility; Show Must Go On for death-prevention.",
        },
        "explanation_summary": "Safe Birthday Party; Over Excited/Show Must Go On for utility/death-prevention.",
        "review_needed": False,
        "review_reasons": [],
    },
    74: {
        "advice_model": "farm_default",
        "safe_default": _choice(4766, "Additional Scatter Tacks"),
        "push_default": _choice(4766, "Additional Scatter Tacks"),
        "farm_default": _choice(4766, "Additional Scatter Tacks"),
        "conditionals": [
            {
                "when": "navigation speed or pathing is the goal",
                "upgrade_id": 4765,
                "name": "Path Finder",
            },
            {
                "when": "control or debuff-heavy zones are the goal",
                "upgrade_id": 4767,
                "name": "Reversal of Fortunes",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": True,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Additional Scatter Tacks",
            "csv_advice_text": "Path Finder for navigation speed; Reversal for control/debuff zones.",
        },
        "explanation_summary": "Safe/farm/push Scatter Tacks; Path Finder and Reversal are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    75: {
        "advice_model": "farm_default",
        "safe_default": _choice(10653, "Did We Say Humans? We Meant..."),
        "push_default": None,
        "farm_default": _choice(10653, "Did We Say Humans? We Meant..."),
        "conditionals": [
            {
                "when": "formation specifically benefits from Law Maan",
                "upgrade_id": 10654,
                "name": "Law Maan",
            },
            {
                "when": "formation specifically benefits from Hello, Fellow Mercenaries!",
                "upgrade_id": 10655,
                "name": "Hello, Fellow Mercenaries!",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Did We Say Humans? We Meant...",
            "csv_advice_text": "Law Maan/Mercenaries only when the formation specifically benefits.",
        },
        "explanation_summary": "Safe/farm Did We Say Humans; Law/Mercenaries only for specific formations.",
        "review_needed": False,
        "review_reasons": [],
    },
    76: {
        "advice_model": "safe_default",
        "safe_default": _choice(4909, "Blazing Soul"),
        "push_default": _choice(4909, "Blazing Soul"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 burn-focused route is needed", "upgrade_id": 4910, "name": "Long Burn"},
            {
                "when": "tier1 run goal prefers the siren route",
                "upgrade_id": 4911,
                "name": "Sirens' Connection",
            },
            {
                "when": "tier1 run goal prefers the fierce route",
                "upgrade_id": 4912,
                "name": "Fierce Connection",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Blazing Soul",
            "csv_advice_text": "Long Burn is tier0 burn; Sirens/Fierce Connection split by run goal.",
        },
        "explanation_summary": "Safe Blazing Soul; Long Burn and tier1 connections stay contextual.",
        "review_needed": False,
        "review_reasons": [],
    },
    77: {
        "advice_model": "safe_default",
        "safe_default": _choice(17749, "Expansive Vision"),
        "push_default": _choice(17749, "Expansive Vision"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "adjacency or team composition prefers the alternate support route",
                "upgrade_id": 17750,
                "name": "Extra Judgy",
            },
            {
                "when": "adjacency or team composition prefers the other positional route",
                "upgrade_id": 17751,
                "name": "Heroes of the Planes",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Expansive Vision",
            "csv_advice_text": "Extra Judgy/Heroes of the Planes only when adjacency/comp prefers them.",
        },
        "explanation_summary": "Safe Expansive Vision; Extra Judgy/Planes only for adjacency/comp fits.",
        "review_needed": False,
        "review_reasons": [],
    },
    78: {
        "advice_model": "safe_default",
        "safe_default": _choice(5577, "Tailfeather of the Phoenix"),
        "push_default": _choice(5577, "Tailfeather of the Phoenix"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "healing or survival is the main problem",
                "upgrade_id": 5576,
                "name": "Breath of the Phoenix",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Healing route",
            "csv_label_maps_to": "Tailfeather of the Phoenix",
            "csv_advice_text": "Breath of the Phoenix only when healing/survival is the main problem.",
        },
        "explanation_summary": "Safe Tailfeather; Breath only when healing/survival is the main problem.",
        "review_needed": False,
        "review_reasons": [],
    },
    79: {
        "advice_model": "safe_default",
        "safe_default": _choice(13424, "Blinding Wall of Light"),
        "push_default": _choice(13424, "Blinding Wall of Light"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 alternate wall route is explicitly needed",
                "upgrade_id": 13425,
                "name": "Disintegrating Wall of Light",
            },
            {
                "when": "tier1 puzzle or formation route is explicitly needed → Child's Play",
                "upgrade_id": 13420,
                "name": "Child's Play",
            },
            {
                "when": "tier1 puzzle or formation route is explicitly needed → Pen and Paper",
                "upgrade_id": 13421,
                "name": "Pen and Paper",
            },
            {
                "when": "tier1 puzzle or formation route is explicitly needed → Sunday Edition",
                "upgrade_id": 13422,
                "name": "Sunday Edition",
            },
            {
                "when": "tier1 puzzle or formation route is explicitly needed → Brain Break",
                "upgrade_id": 13423,
                "name": "Brain Break",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Blinding Wall of Light",
            "csv_advice_text": "Disintegrating Wall is tier0 alt; puzzle/formation picks are tier1 context.",
        },
        "explanation_summary": "Safe Blinding Wall; Disintegrating Wall and puzzle/formation picks stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    80: {
        "advice_model": "safe_default",
        "safe_default": _choice(16152, "Found Family"),
        "push_default": _choice(16152, "Found Family"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "roster synergy clearly favors the force route",
                "upgrade_id": 16150,
                "name": "Fighting Force",
            },
            {
                "when": "roster synergy clearly favors the father route",
                "upgrade_id": 16151,
                "name": "Father Figure",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Fiend route",
            "csv_label_maps_to": "Found Family",
            "csv_advice_text": "Fighting Force/Father Figure only when roster synergy clearly prefers them.",
        },
        "explanation_summary": "Safe Found Family; Fighting Force/Father Figure only for clear roster synergy.",
        "review_needed": False,
        "review_reasons": [],
    },
    81: {
        "advice_model": "safe_default",
        "safe_default": _choice(13751, "Mithral Skin"),
        "push_default": _choice(13751, "Mithral Skin"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 tanking needs extra shielding",
                "upgrade_id": 13750,
                "name": "Reflective Shield",
            },
            {
                "when": "tier0 utility or carry-protection is better",
                "upgrade_id": 13749,
                "name": "Relentless Avenger",
            },
            {
                "when": "tier1 variant is selected → Tyr's Eyes",
                "upgrade_id": 13752,
                "name": "Tyr's Eyes",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Tank route",
            "csv_label_maps_to": "Mithral Skin",
            "csv_advice_text": "Reflective Shield for extra shielding; Avenger for utility/carry-protection.",
        },
        "explanation_summary": "Safe Mithral Skin; Shield/Avenger by tank vs utility; CSV aligned to Skin.",
        "review_needed": True,
        "review_reasons": ["tier1 duplicates option names across upgrade ids"],
    },
    83: {
        "advice_model": "safe_default",
        "safe_default": _choice(15233, "All That Sparkles"),
        "push_default": _choice(15233, "All That Sparkles"),
        "farm_default": _choice(15232, "Faster Tempo"),
        "conditionals": [
            {
                "when": "run goal explicitly prefers For The Fans",
                "upgrade_id": 15231,
                "name": "For The Fans",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Faster Tempo",
            "csv_advice_text": "For The Fans only when that route is explicitly better for the run goal.",
        },
        "explanation_summary": "Safe All That Sparkles; farm Faster Tempo; Fans only for explicit run goals.",
        "review_needed": False,
        "review_reasons": [],
    },
    84: {
        "advice_model": "safe_default",
        "safe_default": _choice(6072, "Eldritch Torrent"),
        "push_default": _choice(6072, "Eldritch Torrent"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "the setup benefits from alternate scaling",
                "upgrade_id": 6073,
                "name": "She Hungers",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "DPS route",
            "csv_label_maps_to": "Eldritch Torrent",
            "csv_advice_text": "She Hungers only when the setup benefits from that alternate scaling.",
        },
        "explanation_summary": "Safe Eldritch Torrent; She Hungers only for alternate scaling setups.",
        "review_needed": False,
        "review_reasons": [],
    },
    85: {
        "advice_model": "safe_default",
        "safe_default": _choice(6133, "Distant Crewmates"),
        "push_default": _choice(6133, "Distant Crewmates"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "you specifically need the alternate utility behavior",
                "upgrade_id": 6134,
                "name": "Mage Hand",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Distant Crewmates",
            "csv_advice_text": "Mage Hand only when that alternate utility behavior is specifically needed.",
        },
        "explanation_summary": "Safe Distant Crewmates; Mage Hand only for alternate utility needs.",
        "review_needed": False,
        "review_reasons": [],
    },
    86: {
        "advice_model": "safe_default",
        "safe_default": _choice(5459, "Champions of Good"),
        "push_default": _choice(5459, "Champions of Good"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "formation or roster alignment prefers the law route",
                "upgrade_id": 5460,
                "name": "Champions of Law",
            }
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Tank route",
            "csv_label_maps_to": "Champions of Good",
            "csv_advice_text": "Champions of Law only when formation/roster alignment prefers it.",
        },
        "explanation_summary": "Safe Champions of Good; Law only when formation/roster alignment prefers it.",
        "review_needed": False,
        "review_reasons": [],
    },
    87: {
        "advice_model": "safe_default",
        "safe_default": _choice(6148, "Green Leader, Standing By"),
        "push_default": _choice(6148, "Green Leader, Standing By"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "support profile needs Orange Leader",
                "upgrade_id": 6146,
                "name": "Orange Leader, Standing By",
            },
            {
                "when": "support profile needs Red Leader",
                "upgrade_id": 6147,
                "name": "Red Leader, Standing By",
            },
            {
                "when": "support profile needs Yellow Leader",
                "upgrade_id": 6149,
                "name": "Yellow Leader, Standing By",
            },
            {
                "when": "support profile needs Pink Leader",
                "upgrade_id": 6150,
                "name": "Pink Leader, Standing By",
            },
            {
                "when": "support profile needs Purple Leader",
                "upgrade_id": 6151,
                "name": "Purple Leader, Standing By",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Green Leader, Standing By",
            "csv_advice_text": "Other colors are situational by needed support profile.",
        },
        "explanation_summary": "Safe Green Leader; other colors by needed support profile.",
        "review_needed": False,
        "review_reasons": [],
    },
    88: {
        "advice_model": "safe_default",
        "safe_default": _choice(6842, "High Charisma"),
        "push_default": _choice(6842, "High Charisma"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 strength choice is needed → High Strength", "upgrade_id": 6838, "name": "High Strength"},
            {"when": "tier0 strength choice is needed → Low Strength", "upgrade_id": 6839, "name": "Low Strength"},
            {"when": "tier1 dexterity choice is needed → High Dexterity", "upgrade_id": 6840, "name": "High Dexterity"},
            {"when": "tier1 dexterity choice is needed → Low Dexterity", "upgrade_id": 6841, "name": "Low Dexterity"},
            {
                "when": "tier2 constitution choice is needed → High Constitution",
                "upgrade_id": 6978,
                "name": "High Constitution",
            },
            {
                "when": "tier2 constitution choice is needed → Low Constitution",
                "upgrade_id": 6979,
                "name": "Low Constitution",
            },
            {
                "when": "tier3 intelligence choice is needed → High Intelligence",
                "upgrade_id": 6976,
                "name": "High Intelligence",
            },
            {
                "when": "tier3 intelligence choice is needed → Low Intelligence",
                "upgrade_id": 6977,
                "name": "Low Intelligence",
            },
            {"when": "tier4 wisdom choice is needed → High Wisdom", "upgrade_id": 6980, "name": "High Wisdom"},
            {"when": "tier4 wisdom choice is needed → Low Wisdom", "upgrade_id": 6981, "name": "Low Wisdom"},
            {"when": "tier5 charisma choice is needed → Low Charisma", "upgrade_id": 6843, "name": "Low Charisma"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "High Charisma",
            "csv_advice_text": "Each earlier/other stat tier is a separate conditional choice rule.",
        },
        "explanation_summary": "Safe High Charisma (tier5); all earlier/other stat tiers are separate conditionals.",
        "review_needed": False,
        "review_reasons": [],
    },
    # --- batch 06 remaining ---
    89: {
        "advice_model": "safe_default",
        "safe_default": _choice(13717, "Ochre Jelly Yellow"),
        "push_default": _choice(13717, "Ochre Jelly Yellow"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational paint/scaling wants green",
                "upgrade_id": 13718,
                "name": "Twig Blight Green",
            },
            {
                "when": "situational paint/scaling wants blue",
                "upgrade_id": 13719,
                "name": "Frost Giant Blue",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Debuff focus",
            "csv_label_maps_to": "Ochre Jelly Yellow",
            "csv_advice_text": "Green/Blue paints are situational paint/scaling choices only.",
        },
        "explanation_summary": "Safe Ochre Jelly Yellow; Green/Blue paints are situational scaling choices.",
        "review_needed": False,
        "review_reasons": [],
    },
    90: {
        "advice_model": "safe_default",
        "safe_default": _choice(6355, '"Back"-Up Singer'),
        "push_default": _choice(6355, '"Back"-Up Singer'),
        "farm_default": None,
        "conditionals": [
            {
                "when": "the alternate utility route is clearly better",
                "upgrade_id": 6356,
                "name": "Cream of the Crop",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": '"Back"-Up Singer',
            "csv_advice_text": "Cream of the Crop only when that utility route is clearly better.",
        },
        "explanation_summary": "Safe Back-Up Singer; Cream of the Crop only for clearer utility route.",
        "review_needed": False,
        "review_reasons": [],
    },
    91: {
        "advice_model": "farm_default",
        "safe_default": _choice(6910, "Mind and Body"),
        "push_default": _choice(6910, "Mind and Body"),
        "farm_default": _choice(6910, "Mind and Body"),
        "conditionals": [
            {
                "when": "a stronger speed-focused setup specifically needs it",
                "upgrade_id": 6909,
                "name": "Strong and Steady",
            },
            {
                "when": "a wisdom-focused setup specifically needs it",
                "upgrade_id": 6911,
                "name": "Wisdom and Confidence",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Fast Friends",
            "csv_label_maps_to": "Mind and Body",
            "csv_advice_text": "Strong and Steady for speed focus; Wisdom and Confidence for wisdom focus.",
        },
        "explanation_summary": "Safe/farm/push Mind and Body; Strong/Steady and Wisdom are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    92: {
        "advice_model": "safe_default",
        "safe_default": _choice(17071, "Eldritch Claw Tattoo"),
        "push_default": _choice(17071, "Eldritch Claw Tattoo"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "a hunger-based alternate is specifically needed",
                "upgrade_id": 17070,
                "name": "Hunger For Blood",
            },
            {
                "when": "a rabbit-based alternate is specifically needed",
                "upgrade_id": 17072,
                "name": "Follow The Mad Rabbit",
            },
            {
                "when": "a fury-based alternate is specifically needed",
                "upgrade_id": 17073,
                "name": "Infectious Fury",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Eldritch Claw Tattoo",
            "csv_advice_text": "Hunger/Rabbit/Infectious Fury only when those alternates are specifically needed.",
        },
        "explanation_summary": "Safe Eldritch Claw Tattoo; other tattoos/paths are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    93: {
        "advice_model": "safe_default",
        "safe_default": _choice(9785, "Begrudging Respect"),
        "push_default": _choice(9785, "Begrudging Respect"),
        "farm_default": None,
        "conditionals": [
            {"when": "holy-power route is specifically needed", "upgrade_id": 9784, "name": "Holy Power"},
            {
                "when": "undead-focused value is real → Turn Undead",
                "upgrade_id": 9786,
                "name": "Turn Undead",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": True,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Begrudging Respect",
            "csv_advice_text": "Holy Power when specifically needed; Turn Undead when undead value is real.",
        },
        "explanation_summary": "Safe Begrudging Respect; Holy Power situational; Turn Undead for real undead value.",
        "review_needed": False,
        "review_reasons": [],
    },
    94: {
        "advice_model": "farm_default",
        "safe_default": _choice(15363, "Even More Riches"),
        "push_default": _choice(15363, "Even More Riches"),
        "farm_default": _choice(15363, "Even More Riches"),
        "conditionals": [
            {
                "when": "niche route explicitly desired → Rust's Fever Dream",
                "upgrade_id": 15364,
                "name": "Rust's Fever Dream",
            },
            {
                "when": "setup prefers Get Rich Quick instead",
                "upgrade_id": 15362,
                "name": "Get Rich Quick",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Gold route",
            "csv_label_maps_to": "Get Rich Quick",
            "csv_advice_text": "Fever Dream only when the niche route is explicitly desired.",
        },
        "explanation_summary": "Safe Even More Riches; CSV maps Gold→Get Rich Quick; Fever Dream niche only.",
        "review_needed": False,
        "review_reasons": [],
    },
    95: {
        "advice_model": "safe_default",
        "safe_default": _choice(12318, "A Nudge In The Right Direction"),
        "push_default": _choice(12318, "A Nudge In The Right Direction"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational support variant is explicitly better → Bless Their Hearts",
                "upgrade_id": 12316,
                "name": "Bless Their Hearts",
            },
            {
                "when": "situational support variant is explicitly better → Positive Reinforcement",
                "upgrade_id": 12317,
                "name": "Positive Reinforcement",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "A Nudge In The Right Direction",
            "csv_advice_text": "Bless Their Hearts / Positive Reinforcement only as explicit situational variants.",
        },
        "explanation_summary": "Safe A Nudge In The Right Direction; Bless/Positive are situational only.",
        "review_needed": False,
        "review_reasons": [],
    },
    96: {
        "advice_model": "safe_default",
        "safe_default": _choice(7305, "Embrace the Beast"),
        "push_default": _choice(7305, "Embrace the Beast"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "defeated/dead synergy or party composition demands Double Time",
                "upgrade_id": 7304,
                "name": "Double Time",
            },
            {
                "when": "defeated/dead synergy or party composition demands Strength in Numbers",
                "upgrade_id": 7306,
                "name": "Strength in Numbers",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Living on the Edge",
            "csv_label_maps_to": "Embrace the Beast",
            "csv_advice_text": "Double Time / Strength in Numbers only if defeated/dead synergy demands it.",
        },
        "explanation_summary": "Safe Embrace the Beast; Double Time/Numbers only for defeated/dead synergy.",
        "review_needed": False,
        "review_reasons": [],
    },
    97: {
        "advice_model": "safe_default",
        "safe_default": _choice(7389, "Best Friend Forever"),
        "push_default": _choice(7389, "Best Friend Forever"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tank route specifically needs the friend-based option",
                "upgrade_id": 7387,
                "name": "Your Friends are My Friends",
            },
            {
                "when": "utility route specifically needs the side-by-side option",
                "upgrade_id": 7388,
                "name": "By My Side",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Tank route",
            "csv_label_maps_to": "Best Friend Forever",
            "csv_advice_text": "Your Friends for tank friend-based; By My Side for utility side-by-side.",
        },
        "explanation_summary": "Safe Best Friend Forever; Friends/By My Side are role-specific.",
        "review_needed": False,
        "review_reasons": [],
    },
    98: {
        "advice_model": "farm_default",
        "safe_default": _choice(7539, "Aim Around Armor"),
        "push_default": None,
        "farm_default": _choice(7539, "Aim Around Armor"),
        "conditionals": [
            {
                "when": "situational support or utility value from gold scaling is needed",
                "upgrade_id": 7538,
                "name": "Genius with Gold",
            },
            {
                "when": "situational support or utility value from frost scaling is needed",
                "upgrade_id": 7540,
                "name": "Finesse with Frost",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Aim Around Armor",
            "csv_advice_text": "Genius with Gold / Finesse with Frost are situational support/utility.",
        },
        "explanation_summary": "Safe/farm Aim Around Armor; Gold/Frost variants are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    99: {
        "advice_model": "safe_default",
        "safe_default": _choice(7850, "Fear Not, Champions!"),
        "push_default": _choice(7850, "Fear Not, Champions!"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational utility needs the disappearance route",
                "upgrade_id": 7849,
                "name": "Where Did He Go This Time?",
            },
            {
                "when": "situational utility needs the guest-stars route",
                "upgrade_id": 16144,
                "name": "Special Guest Stars",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Utility route",
            "csv_label_maps_to": "Fear Not, Champions!",
            "csv_advice_text": "Where Did He Go / Special Guest Stars are situational utility choices.",
        },
        "explanation_summary": "Safe Fear Not, Champions!; other utility options are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    100: {
        "advice_model": "safe_default",
        "safe_default": _choice(18167, "Modron Core Toolbox"),
        "push_default": _choice(18167, "Modron Core Toolbox"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "automation/modron goals need BASIC Functionality",
                "upgrade_id": 18166,
                "name": "BASIC Functionality",
            },
            {
                "when": "automation/modron goals need Core Competency",
                "upgrade_id": 18168,
                "name": "Core Competency",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Modron route",
            "csv_label_maps_to": "Modron Core Toolbox",
            "csv_advice_text": "BASIC/Core Competency depend on automation/modron goals.",
        },
        "explanation_summary": "Safe Modron Core Toolbox; BASIC/Competency by automation/modron goals.",
        "review_needed": False,
        "review_reasons": [],
    },
    101: {
        "advice_model": "farm_default",
        "safe_default": _choice(7999, "Meow-il-wen"),
        "push_default": None,
        "farm_default": _choice(7999, "Meow-il-wen"),
        "conditionals": [
            {
                "when": "situational gold route is explicitly desired",
                "upgrade_id": 7997,
                "name": "Stink Like Skunk",
            },
            {
                "when": "situational support route is explicitly desired",
                "upgrade_id": 7998,
                "name": "Treasures Her Friends",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Gold route",
            "csv_label_maps_to": "Meow-il-wen",
            "csv_advice_text": "Stink Like Skunk for explicit gold; Treasures Her Friends for explicit support.",
        },
        "explanation_summary": "Safe/farm Meow-il-wen; Skunk/Friends are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    102: {
        "advice_model": "safe_default",
        "safe_default": _choice(19724, "A Barovian Bond"),
        "push_default": _choice(19724, "A Barovian Bond"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational grave-experience route is explicitly desired",
                "upgrade_id": 19723,
                "name": "A Grave Experience",
            },
            {
                "when": "situational lyre route is explicitly desired",
                "upgrade_id": 19725,
                "name": "A Skilled Lyre",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "A Barovian Bond",
            "csv_advice_text": "Grave Experience / Skilled Lyre only when those routes are explicitly desired.",
        },
        "explanation_summary": "Safe A Barovian Bond; Grave Experience/Lyre are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    103: {
        "advice_model": "farm_default",
        "safe_default": _choice(8150, "My Loyal Bodyguard"),
        "push_default": None,
        "farm_default": _choice(8150, "My Loyal Bodyguard"),
        "conditionals": [
            {
                "when": "socialite/gold route is the explicit goal",
                "upgrade_id": 8149,
                "name": "All Hail the God Brain",
            },
            {
                "when": "specific family/support synergies are needed",
                "upgrade_id": 8151,
                "name": "Family Business",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Socialite gold",
            "csv_label_maps_to": "My Loyal Bodyguard",
            "csv_advice_text": "God Brain for explicit gold; Family Business for family/support synergies.",
        },
        "explanation_summary": "Safe/farm My Loyal Bodyguard; God Brain/Family Business situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    104: {
        "advice_model": "safe_default",
        "safe_default": _choice(15635, "Embrace Evil"),
        "push_default": _choice(15635, "Embrace Evil"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 hunt route is selected", "upgrade_id": 15636, "name": "Hunt The Favored"},
            {"when": "tier0 weaken route is selected", "upgrade_id": 15637, "name": "Weaken The Fools"},
            {"when": "tier1 battle route is selected", "upgrade_id": 15638, "name": "Battle Magic"},
            {"when": "tier1 focus route is selected", "upgrade_id": 15639, "name": "Powerful Focus"},
            {
                "when": "tier1 strike route is selected",
                "upgrade_id": 15640,
                "name": "Strike First, Strike Hard",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Support routing",
            "csv_label_maps_to": "Embrace Evil",
            "csv_advice_text": "Tier0 hunt/weaken and tier1 battle/focus/strike stay split by tier.",
        },
        "explanation_summary": "Safe Embrace Evil; other tier0/tier1 picks are situational conditionals.",
        "review_needed": False,
        "review_reasons": [],
    },
    105: {
        "advice_model": "safe_default",
        "safe_default": _choice(8745, "Befriend Everybody!"),
        "push_default": _choice(8745, "Befriend Everybody!"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational magical profile is needed",
                "upgrade_id": 8742,
                "name": "Befriend the Magical",
            },
            {
                "when": "situational friendly profile is needed",
                "upgrade_id": 8743,
                "name": "Befriend the Friendly",
            },
            {
                "when": "situational quick profile is needed",
                "upgrade_id": 8744,
                "name": "Befriend the Quick",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Befriend Everybody!",
            "csv_advice_text": "Magical/Friendly/Quick are profile-based swaps; Everybody is stable default.",
        },
        "explanation_summary": "Safe Befriend Everybody!; Magical/Friendly/Quick are profile-based.",
        "review_needed": False,
        "review_reasons": [],
    },
    106: {
        "advice_model": "safe_default",
        "safe_default": _choice(7525, "Charred Souls"),
        "push_default": _choice(7525, "Charred Souls"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "offense-focused route is explicitly desired → Sliced Souls",
                "upgrade_id": 7523,
                "name": "Sliced Souls",
            },
            {
                "when": "offense-focused route is explicitly desired → Skewered Souls",
                "upgrade_id": 7524,
                "name": "Skewered Souls",
            },
            {
                "when": "tier1 survival is the main need",
                "upgrade_id": 7526,
                "name": "Resilient Spirit",
            },
            {"when": "tier1 offense is the main need", "upgrade_id": 7527, "name": "Wild Spirit"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Tank route",
            "csv_label_maps_to": "Charred Souls",
            "csv_advice_text": "Sliced/Skewered for offense; Resilient vs Wild Spirit by survival vs offense.",
        },
        "explanation_summary": "Safe Charred Souls; other souls/spirits by survival vs offense needs.",
        "review_needed": False,
        "review_reasons": [],
    },
    113: {
        "advice_model": "safe_default",
        "safe_default": _choice(8877, "Atonement Begins with an Apology"),
        "push_default": _choice(8877, "Atonement Begins with an Apology"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 chaos route is selected", "upgrade_id": 8878, "name": "Team Chaos Team"},
            {"when": "tier1 bomb route is selected", "upgrade_id": 8879, "name": "Smoky Bombs"},
            {"when": "tier1 health route is selected", "upgrade_id": 8880, "name": "Health Kick"},
            {
                "when": "tier1 capitalism route is selected",
                "upgrade_id": 8881,
                "name": "Oxventure Capitalism",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Atonement Begins with an Apology",
            "csv_advice_text": "Chaos/Bombs/Health/Capitalism are situational tier-based choices.",
        },
        "explanation_summary": "Safe Atonement Apology; other tier0/tier1 picks are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    114: {
        "advice_model": "safe_default",
        "safe_default": _choice(9356, "Potent Poison"),
        "push_default": _choice(9356, "Potent Poison"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "ranged-specific setup prefers the ranged route",
                "upgrade_id": 9355,
                "name": "Robust Rivals",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Potent Poison",
            "csv_advice_text": "Robust Rivals only when ranged-specific setup actually prefers it.",
        },
        "explanation_summary": "Safe Potent Poison; Robust Rivals only for preferred ranged setups.",
        "review_needed": False,
        "review_reasons": [],
    },
    # --- batch 07 remaining ---
    115: {
        "advice_model": "farm_default",
        "safe_default": _choice(9608, "Mood: Anxious"),
        "push_default": _choice(9608, "Mood: Anxious"),
        "farm_default": _choice(9608, "Mood: Anxious"),
        "conditionals": [
            {
                "when": "specific speed need makes the relaxed route better",
                "upgrade_id": 9607,
                "name": "Mood: Relaxed",
            },
            {
                "when": "specific durability need makes the determined route better",
                "upgrade_id": 9609,
                "name": "Mood: Determined",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Mood: Anxious",
            "csv_advice_text": "Relaxed for speed needs; Determined for durability needs.",
        },
        "explanation_summary": "Safe/farm/push Mood: Anxious; Relaxed/Determined only for speed/durability needs.",
        "review_needed": False,
        "review_reasons": [],
    },
    116: {
        "advice_model": "safe_default",
        "safe_default": _choice(9619, "Chaos Reigns"),
        "push_default": _choice(9619, "Chaos Reigns"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational evil/carry variant is desired → Mercenary for Hire",
                "upgrade_id": 9620,
                "name": "Mercenary for Hire",
            },
            {
                "when": "situational evil/carry variant is desired → League of Malevolence",
                "upgrade_id": 9621,
                "name": "League of Malevolence",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "DPS route",
            "csv_label_maps_to": "Chaos Reigns",
            "csv_advice_text": "Mercenary / League of Malevolence are situational evil/carry variants.",
        },
        "explanation_summary": "Safe Chaos Reigns; Mercenary/League are situational evil/carry variants.",
        "review_needed": False,
        "review_reasons": [],
    },
    117: {
        "advice_model": "safe_default",
        "safe_default": _choice(9646, "Aberration Slaying Arrows"),
        "push_default": _choice(9646, "Aberration Slaying Arrows"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "enemy-type-specific beast value is needed",
                "upgrade_id": 9643,
                "name": "Beast Slaying Arrows",
            },
            {
                "when": "enemy-type-specific dragon value is needed",
                "upgrade_id": 9644,
                "name": "Dragon Slaying Arrows",
            },
            {
                "when": "enemy-type-specific monstrosity value is needed",
                "upgrade_id": 9645,
                "name": "Monstrosity Slaying Arrows",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": True,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Aberration Slaying Arrows",
            "csv_advice_text": "Beast/Dragon/Monstrosity arrows only for enemy-type-specific value.",
        },
        "explanation_summary": "Safe Aberration Slaying Arrows; other arrow types only for enemy-type value.",
        "review_needed": False,
        "review_reasons": [],
    },
    118: {
        "advice_model": "safe_default",
        "safe_default": _choice(9762, "Curse of the Dhampir"),
        "push_default": _choice(9762, "Curse of the Dhampir"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "Shadows of the Underdark route is explicitly better",
                "upgrade_id": 9761,
                "name": "Shadows of the Underdark",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Curse of the Dhampir",
            "csv_advice_text": "Shadows of the Underdark only when that route is explicitly better.",
        },
        "explanation_summary": "Safe Curse of the Dhampir; Shadows only when explicitly better.",
        "review_needed": False,
        "review_reasons": [],
    },
    119: {
        "advice_model": "safe_default",
        "safe_default": _choice(19680, "Book of Exalted Deeds"),
        "push_default": _choice(19680, "Book of Exalted Deeds"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "alternate alignment or utility path is the right fit",
                "upgrade_id": 19681,
                "name": "Book of Vile Darkness",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Book of Vile Darkness only when that alignment/utility path is right.",
        },
        "explanation_summary": "Safe Book of Exalted Deeds; Vile Darkness only for alternate alignment path.",
        "review_needed": False,
        "review_reasons": [],
    },
    120: {
        "advice_model": "safe_default",
        "safe_default": _choice(10617, "Confidant"),
        "push_default": _choice(10617, "Confidant"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational unwavering profile is needed",
                "upgrade_id": 10615,
                "name": "Unwavering",
            },
            {
                "when": "situational emboldened profile is needed",
                "upgrade_id": 10616,
                "name": "Emboldened",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Confidant",
            "csv_advice_text": "Unwavering and Emboldened are situational profile swaps.",
        },
        "explanation_summary": "Safe Confidant; Unwavering/Emboldened are situational only.",
        "review_needed": False,
        "review_reasons": [],
    },
    121: {
        "advice_model": "safe_default",
        "safe_default": _choice(10672, "Independent"),
        "push_default": _choice(10672, "Independent"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational methodical utility is needed",
                "upgrade_id": 10670,
                "name": "Methodical",
            },
            {
                "when": "situational intellectual utility is needed",
                "upgrade_id": 10671,
                "name": "Intellectual",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Tank route",
            "csv_label_maps_to": "Independent",
            "csv_advice_text": "Methodical and Intellectual are situational utility variants.",
        },
        "explanation_summary": "Safe Independent; Methodical/Intellectual are situational utility variants.",
        "review_needed": False,
        "review_reasons": [],
    },
    122: {
        "advice_model": "safe_default",
        "safe_default": _choice(10798, "Bard College"),
        "push_default": _choice(10798, "Bard College"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational awful-stats variant is needed",
                "upgrade_id": 10799,
                "name": "Truly Awful Stats",
            },
            {
                "when": "situational chaotic variant is needed",
                "upgrade_id": 10800,
                "name": 'The "A" In Chaotic Is For Antrius',
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Bard College",
            "csv_advice_text": "Truly Awful Stats / Chaotic Antrius are situational variants.",
        },
        "explanation_summary": "Safe Bard College; Awful Stats/Chaotic Antrius are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    123: {
        "advice_model": "safe_default",
        "safe_default": _choice(10892, "Anarchy Amplified"),
        "push_default": _choice(10892, "Anarchy Amplified"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "the alternate setup is clearly better → Infernal Impact",
                "upgrade_id": 10890,
                "name": "Infernal Impact",
            },
            {
                "when": "the alternate setup is clearly better → Flawed Force",
                "upgrade_id": 10891,
                "name": "Flawed Force",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Anarchy Amplified",
            "csv_advice_text": "Infernal Impact / Flawed Force only when the alternate setup is clearly better.",
        },
        "explanation_summary": "Safe Anarchy Amplified; Infernal/Flawed only when clearly better.",
        "review_needed": False,
        "review_reasons": [],
    },
    124: {
        "advice_model": "safe_default",
        "safe_default": _choice(11301, "Carnival Crew"),
        "push_default": _choice(11301, "Carnival Crew"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "stronger force/support route better for the run → Fighting Force",
                "upgrade_id": 11300,
                "name": "Fighting Force",
            },
            {
                "when": "setup prefers Powerful Allies instead",
                "upgrade_id": 11299,
                "name": "Powerful Allies",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Powerful Allies",
            "csv_advice_text": "Fighting Force only when that stronger force/support route is better.",
        },
        "explanation_summary": "Safe Carnival Crew; CSV maps Support→Powerful Allies; Fighting Force situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    125: {
        "advice_model": "safe_default",
        "safe_default": _choice(11545, "Min-Maxing"),
        "push_default": _choice(11545, "Min-Maxing"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational Powergaming control/support",
                "upgrade_id": 11544,
                "name": "Powergaming",
            },
            {
                "when": "situational Rules Lawyering control/support",
                "upgrade_id": 11546,
                "name": "Rules Lawyering",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Control route",
            "csv_label_maps_to": "Min-Maxing",
            "csv_advice_text": "Powergaming / Rules Lawyering are situational control/support variants.",
        },
        "explanation_summary": "Safe Min-Maxing; Powergaming/Rules Lawyering are situational variants.",
        "review_needed": False,
        "review_reasons": [],
    },
    126: {
        "advice_model": "safe_default",
        "safe_default": _choice(19734, "Honorary Member"),
        "push_default": _choice(19734, "Honorary Member"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "use the support option that best fits quest/progress goals",
                "upgrade_id": 19733,
                "name": "Valor's Call",
            },
            {
                "when": "specific event or progression setup makes it better",
                "upgrade_id": 19738,
                "name": "A Righteous Event",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Honorary Member",
            "csv_advice_text": "Valor's Call for quest/progress fit; Righteous Event for specific progression setups.",
        },
        "explanation_summary": "Safe Honorary Member; Valor's Call/Righteous Event only for quest/progress setups.",
        "review_needed": False,
        "review_reasons": [],
    },
    127: {
        "advice_model": "safe_default",
        "safe_default": _choice(12094, "Friends in High Places"),
        "push_default": _choice(12094, "Friends in High Places"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 front deck positional setup",
                "upgrade_id": 12090,
                "name": "Front Deck",
            },
            {
                "when": "tier0 rear deck positional setup",
                "upgrade_id": 12091,
                "name": "Rear Deck",
            },
            {
                "when": "tier1 low places route is needed",
                "upgrade_id": 12092,
                "name": "Friends in Low Places",
            },
            {
                "when": "tier1 meh places route is needed",
                "upgrade_id": 12093,
                "name": "Friends in Meh Places",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Friends in High Places",
            "csv_advice_text": "Tier0 deck and tier1 Low/Meh Places are positional/context-based.",
        },
        "explanation_summary": "Safe Friends in High Places; deck/Low/Meh Places are positional conditionals.",
        "review_needed": False,
        "review_reasons": [],
    },
    128: {
        "advice_model": "farm_default",
        "safe_default": _choice(12119, "Battle Master"),
        "push_default": _choice(12119, "Battle Master"),
        "farm_default": _choice(12119, "Battle Master"),
        "conditionals": [
            {
                "when": "situational speed-oriented route is needed",
                "upgrade_id": 12118,
                "name": "Champion",
            },
            {
                "when": "situational alternative combat route is needed",
                "upgrade_id": 12120,
                "name": "Eldritch Knight",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Battle Master",
            "csv_advice_text": "Champion for speed-oriented; Eldritch Knight for alternate combat.",
        },
        "explanation_summary": "Safe/farm/push Battle Master; Champion/Eldritch Knight are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    129: {
        "advice_model": "safe_default",
        "safe_default": _choice(12496, "Arcane Trickster"),
        "push_default": _choice(12496, "Arcane Trickster"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "top/bottom tier0 route explicitly chosen → Outflank (Top)",
                "upgrade_id": 12493,
                "name": "Outflank (Top)",
            },
            {
                "when": "top/bottom tier0 route explicitly chosen → Outflank (Bottom)",
                "upgrade_id": 12494,
                "name": "Outflank (Bottom)",
            },
            {"when": "tier1 thief route is needed", "upgrade_id": 12495, "name": "Thief"},
            {"when": "tier1 assassin route is needed", "upgrade_id": 12497, "name": "Assassin"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Damage route",
            "csv_label_maps_to": "Arcane Trickster",
            "csv_advice_text": "Outflank Top/Bottom and Thief/Assassin only when those routes are explicit.",
        },
        "explanation_summary": "Safe Arcane Trickster; Outflank/Thief/Assassin stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    136: {
        "advice_model": "safe_default",
        "safe_default": _choice(11660, "Foe of Xaryxis"),
        "push_default": _choice(11660, "Foe of Xaryxis"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational Nautical Knockback",
                "upgrade_id": 11658,
                "name": "Nautical Knockback",
            },
            {"when": "situational Take the Helm", "upgrade_id": 11659, "name": "Take the Helm"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Nautical Knockback / Take the Helm are situational.",
        },
        "explanation_summary": "Safe Foe of Xaryxis; Knockback/Helm are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    138: {
        "advice_model": "safe_default",
        "safe_default": _choice(12510, "Best And The Brightest"),
        "push_default": _choice(12510, "Best And The Brightest"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "alternate support route is preferable",
                "upgrade_id": 12511,
                "name": "Smooth Negotiators",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Best And The Brightest",
            "csv_advice_text": "Smooth Negotiators only when that alternate support route is preferable.",
        },
        "explanation_summary": "Safe Best And The Brightest; Smooth Negotiators only when preferable.",
        "review_needed": False,
        "review_reasons": [],
    },
    139: {
        "advice_model": "farm_default",
        "safe_default": _choice(12984, "Callessa's Blessed"),
        "push_default": _choice(12984, "Callessa's Blessed"),
        "farm_default": _choice(12984, "Callessa's Blessed"),
        "conditionals": [
            {
                "when": "survivability is the main need → Defender of the Meek",
                "upgrade_id": 12982,
                "name": "Defender of the Meek",
            },
            {
                "when": "speed route is specifically desired → Vanguard of the Quick",
                "upgrade_id": 12983,
                "name": "Vanguard of the Quick",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": "Speed route",
            "csv_label_maps_to": "Callessa's Blessed",
            "csv_advice_text": "Defender for survivability; Vanguard only when speed is specifically desired.",
        },
        "explanation_summary": "Safe Callessa's Blessed; Defender for survival; Vanguard only for explicit speed.",
        "review_needed": False,
        "review_reasons": [],
    },
    140: {
        "advice_model": "safe_default",
        "safe_default": _choice(13263, "Moon Collector"),
        "push_default": _choice(13263, "Moon Collector"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 wisdom route is chosen",
                "upgrade_id": 13261,
                "name": "Wisdom of the Ages",
            },
            {
                "when": "tier0 speed route is chosen",
                "upgrade_id": 13262,
                "name": "Speed of Shooting Stars",
            },
            {"when": "tier1 star route is chosen", "upgrade_id": 13264, "name": "Star Caller"},
            {"when": "tier1 night route is chosen", "upgrade_id": 13265, "name": "Night Runner"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Tier0 wisdom/speed and tier1 star/night picks are situational.",
        },
        "explanation_summary": "Safe Moon Collector; other tier0/tier1 picks are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    141: {
        "advice_model": "safe_default",
        "safe_default": _choice(13281, "Find Yourself"),
        "push_default": _choice(13281, "Find Yourself"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational healing route is needed",
                "upgrade_id": 13279,
                "name": "Guidance",
            },
            {
                "when": "situational darkness route is needed",
                "upgrade_id": 13280,
                "name": "Sister of Darkness",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Healing route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Guidance for healing; Sister of Darkness for darkness; handler context-sensitive.",
        },
        "explanation_summary": "Safe Find Yourself; Guidance/Sister situational; handler context-sensitive.",
        "review_needed": False,
        "review_reasons": [],
    },
    # --- batch 08 remaining ---
    142: {
        "advice_model": "safe_default",
        "safe_default": _choice(13433, "Pact of the Blade"),
        "push_default": _choice(13433, "Pact of the Blade"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational pact of the chain is needed",
                "upgrade_id": 13434,
                "name": "Pact of the Chain",
            },
            {
                "when": "situational pact of the tome is needed",
                "upgrade_id": 13435,
                "name": "Pact of the Tome",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Pact of the Chain / Pact of the Tome are situational pact choices.",
        },
        "explanation_summary": "Safe Pact of the Blade; Chain/Tome are situational pact choices.",
        "review_needed": False,
        "review_reasons": [],
    },
    143: {
        "advice_model": "safe_default",
        "safe_default": _choice(13726, "Berserker"),
        "push_default": _choice(13726, "Berserker"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational wildheart route is needed",
                "upgrade_id": 13727,
                "name": "Wildheart",
            },
            {
                "when": "situational wild magic route is needed",
                "upgrade_id": 13728,
                "name": "Wild Magic",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Wildheart and Wild Magic are situational route choices.",
        },
        "explanation_summary": "Safe Berserker; Wildheart/Wild Magic are situational routes.",
        "review_needed": False,
        "review_reasons": [],
    },
    144: {
        "advice_model": "safe_default",
        "safe_default": _choice(13765, "Humble Heroes"),
        "push_default": _choice(13765, "Humble Heroes"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational junior juggernauts route is needed",
                "upgrade_id": 13766,
                "name": "Junior Juggernauts",
            },
            {
                "when": "situational magical mastery route is needed",
                "upgrade_id": 13767,
                "name": "Magical Mastery",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Junior Juggernauts / Magical Mastery are situational alternatives.",
        },
        "explanation_summary": "Safe Humble Heroes; Juggernauts/Magical Mastery are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    145: {
        "advice_model": "safe_default",
        "safe_default": _choice(13879, "Circle Magic"),
        "push_default": _choice(13879, "Circle Magic"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational iron lord's justice route is needed",
                "upgrade_id": 13880,
                "name": "Iron Lord's Justice",
            },
            {
                "when": "situational loyal bodyguard route is needed",
                "upgrade_id": 13881,
                "name": "Loyal Bodyguard",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": None,
            "csv_advice_text": "Iron Lord's Justice / Loyal Bodyguard are situational support/DPS variants.",
        },
        "explanation_summary": "Safe Circle Magic; Justice/Bodyguard are situational support/DPS variants.",
        "review_needed": False,
        "review_reasons": [],
    },
    146: {
        "advice_model": "safe_default",
        "safe_default": _choice(14384, "Divine Soul"),
        "push_default": _choice(14384, "Divine Soul"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 storm sorcery is the desired alternate",
                "upgrade_id": 14382,
                "name": "Storm Sorcery",
            },
            {
                "when": "tier0 draconic bloodline is the desired alternate",
                "upgrade_id": 14383,
                "name": "Draconic Bloodline",
            },
            {
                "when": "tier1 embrace the urge is chosen",
                "upgrade_id": 14385,
                "name": "Embrace the Urge",
            },
            {
                "when": "tier1 resist the urge is chosen",
                "upgrade_id": 14386,
                "name": "Resist the Urge",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Tier0 Storm/Draconic alternatives; tier1 Embrace vs Resist the Urge.",
        },
        "explanation_summary": "Safe Divine Soul; tier0 Storm/Draconic and tier1 Urge picks are conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    147: {
        "advice_model": "safe_default",
        "safe_default": _choice(14578, "Ceremorphosis"),
        "push_default": _choice(14578, "Ceremorphosis"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 school choice is needed → Evocation", "upgrade_id": 14574, "name": "Evocation"},
            {"when": "tier0 school choice is needed → Abjuration", "upgrade_id": 14575, "name": "Abjuration"},
            {
                "when": "tier0 school choice is needed → Enchantment",
                "upgrade_id": 14576,
                "name": "Enchantment",
            },
            {"when": "tier0 school choice is needed → Illusion", "upgrade_id": 14577, "name": "Illusion"},
            {
                "when": "tier1 support route is preferred → Mystical Mentor",
                "upgrade_id": 14579,
                "name": "Mystical Mentor",
            },
            {
                "when": "tier1 alternate utility route is preferred → Finite Fellowship",
                "upgrade_id": 14580,
                "name": "Finite Fellowship",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Ceremorphosis",
            "csv_advice_text": "Schools are tier0 choices; Mentor/Fellowship are tier1 support/utility routes.",
        },
        "explanation_summary": "Safe Ceremorphosis; schools and Mentor/Fellowship stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    148: {
        "advice_model": "safe_default",
        "safe_default": _choice(14796, "Ensemble Cast"),
        "push_default": _choice(14796, "Ensemble Cast"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 inspire route is explicitly needed → Inspire: Acrobatic Assault",
                "upgrade_id": 14791,
                "name": "Inspire: Acrobatic Assault",
            },
            {
                "when": "tier0 inspire route is explicitly needed → Inspire: Modest Might",
                "upgrade_id": 14792,
                "name": "Inspire: Modest Might",
            },
            {
                "when": "tier0 inspire route is explicitly needed → Inspire: Fledgling Fury",
                "upgrade_id": 14793,
                "name": "Inspire: Fledgling Fury",
            },
            {
                "when": "tier1 alternate route is specifically desired",
                "upgrade_id": 14797,
                "name": "Spotlight Episode",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Ensemble Cast",
            "csv_advice_text": "Tier0 inspire options and Spotlight Episode are situational.",
        },
        "explanation_summary": "Safe Ensemble Cast; tier0 inspires and Spotlight Episode are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    150: {
        "advice_model": "safe_default",
        "safe_default": _choice(15200, "Play the Long Game"),
        "push_default": _choice(15200, "Play the Long Game"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "run plan needs immediate infiltration",
                "upgrade_id": 15199,
                "name": "Immediate Infiltration",
            },
            {
                "when": "tier1 run plan wants the artificer route",
                "upgrade_id": 15201,
                "name": "Artificer's Arsenal",
            },
            {
                "when": "tier1 run plan wants the spy route",
                "upgrade_id": 15202,
                "name": "Spy Network",
            },
            {
                "when": "tier1 run plan wants the patronage route",
                "upgrade_id": 15203,
                "name": "Powerful Patronage",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Immediate Infiltration and tier1 options are situational by run plan.",
        },
        "explanation_summary": "Safe Play the Long Game; Infiltration/tier1 picks by run plan.",
        "review_needed": False,
        "review_reasons": [],
    },
    151: {
        "advice_model": "safe_default",
        "safe_default": _choice(15053, "Family of Orphans"),
        "push_default": _choice(15053, "Family of Orphans"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 law-route is chosen", "upgrade_id": 15052, "name": "Law's Alliance"},
            {
                "when": "tier0 wardens-route is chosen",
                "upgrade_id": 15054,
                "name": "Call of the Wardens",
            },
            {
                "when": "offensive alt is explicitly desired → More Damage",
                "upgrade_id": 15057,
                "name": "More Damage",
            },
            {"when": "tier1 bees route is needed", "upgrade_id": 15055, "name": "More Bees"},
            {"when": "tier1 clues route is needed", "upgrade_id": 15056, "name": "More Clues"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": "Family of Orphans",
            "csv_advice_text": "Law/Wardens are tier0; More Damage offensive alt; Bees/Clues tier1.",
        },
        "explanation_summary": "Safe Family of Orphans; Law/Wardens/Damage/Bees/Clues stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    152: {
        "advice_model": "safe_default",
        "safe_default": _choice(15448, "Group Charge"),
        "push_default": _choice(15448, "Group Charge"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 strength route is explicitly chosen",
                "upgrade_id": 15447,
                "name": "Stunning Strength",
            },
            {
                "when": "tier1 progression route is explicitly chosen → Not So Low",
                "upgrade_id": 15449,
                "name": "Not So Low",
            },
            {
                "when": "tier1 progression route is explicitly chosen → Still Growing Up",
                "upgrade_id": 15450,
                "name": "Still Growing Up",
            },
            {
                "when": "tier1 progression route is explicitly chosen → Strong Armed",
                "upgrade_id": 15451,
                "name": "Strong Armed",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Tier0 strength and tier1 progression options are situational.",
        },
        "explanation_summary": "Safe Group Charge; tier0 strength and tier1 progression picks stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    154: {
        "advice_model": "safe_default",
        "safe_default": _choice(15948, "Soul Destroyer"),
        "push_default": _choice(15948, "Soul Destroyer"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational house route is explicitly desired",
                "upgrade_id": 15946,
                "name": "House Matron",
            },
            {
                "when": "situational true soul route is explicitly desired",
                "upgrade_id": 15947,
                "name": "True Soul",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Soul Destroyer",
            "csv_advice_text": "House Matron and True Soul only when those routes are explicitly desired.",
        },
        "explanation_summary": "Safe Soul Destroyer; House Matron/True Soul are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    155: {
        "advice_model": "safe_default",
        "safe_default": _choice(15217, "Glitch Form: Dwarf Monk"),
        "push_default": _choice(15217, "Glitch Form: Dwarf Monk"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational tabaxi barbarian form is needed",
                "upgrade_id": 15218,
                "name": "Glitch Form: Tabaxi Barbarian",
            },
            {
                "when": "situational warforged sorcerer form is needed",
                "upgrade_id": 15219,
                "name": "Glitch Form: Warforged Sorcerer",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": "Support route",
            "csv_label_maps_to": "Glitch Form: Dwarf Monk",
            "csv_advice_text": "Tabaxi Barbarian / Warforged Sorcerer are situational forms.",
        },
        "explanation_summary": "Safe Glitch Form: Dwarf Monk; other glitch forms are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    156: {
        "advice_model": "safe_default",
        "safe_default": _choice(15966, "Harbinger of the Wilds"),
        "push_default": _choice(15966, "Harbinger of the Wilds"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational Sage of the Transformed",
                "upgrade_id": 15967,
                "name": "Sage of the Transformed",
            },
            {
                "when": "situational Protector of the Grove",
                "upgrade_id": 15968,
                "name": "Protector of the Grove",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Sage of the Transformed / Protector of the Grove are situational.",
        },
        "explanation_summary": "Safe Harbinger of the Wilds; Sage/Protector are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    157: {
        "advice_model": "safe_default",
        "safe_default": _choice(16135, "Trait: Brave"),
        "push_default": _choice(16135, "Trait: Brave"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 cautious trait is contextually better",
                "upgrade_id": 16134,
                "name": "Trait: Cautious",
            },
            {
                "when": "tier0 sarcastic trait is contextually better",
                "upgrade_id": 16136,
                "name": "Trait: Sarcastic",
            },
            {
                "when": "tier1 unassuming force is contextually better",
                "upgrade_id": 16137,
                "name": "Unassuming Force",
            },
            {
                "when": "tier1 youthful valor is contextually better",
                "upgrade_id": 16138,
                "name": "Youthful Valor",
            },
            {
                "when": "tier1 treasure hunters is contextually better",
                "upgrade_id": 16139,
                "name": "Treasure Hunters",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Trait and tier1 options are contextual; Brave is the stable default.",
        },
        "explanation_summary": "Safe Trait: Brave; other traits and tier1 picks are contextual.",
        "review_needed": False,
        "review_reasons": [],
    },
    158: {
        "advice_model": "safe_default",
        "safe_default": _choice(16522, "Creative Camouflage"),
        "push_default": _choice(16522, "Creative Camouflage"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational Strength in Numbers",
                "upgrade_id": 16521,
                "name": "Strength in Numbers",
            },
            {
                "when": "situational One For You, One For Me",
                "upgrade_id": 16523,
                "name": "One For You, One For Me",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Strength in Numbers / One For You, One For Me are situational.",
        },
        "explanation_summary": "Safe Creative Camouflage; Numbers/One For You are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    159: {
        "advice_model": "safe_default",
        "safe_default": _choice(16556, "Volo's Guide to All Things Magical"),
        "push_default": _choice(16556, "Volo's Guide to All Things Magical"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "contextual spirits and specters guide is needed",
                "upgrade_id": 16554,
                "name": "Volo's Guide to Spirits and Specters",
            },
            {
                "when": "contextual brain-eating tadpoles guide is needed",
                "upgrade_id": 16555,
                "name": "Volo's Guide to Brain-Eating Tadpoles",
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
            "csv_advice_text": "The other two guides are contextual and stay conditional.",
        },
        "explanation_summary": "Safe Volo's Guide to All Things Magical; other guides stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    160: {
        "advice_model": "safe_default",
        "safe_default": _choice(16543, "A Rosy Outlook"),
        "push_default": _choice(16543, "A Rosy Outlook"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 meekly meeting route is explicitly chosen",
                "upgrade_id": 16541,
                "name": "Meekly Meeting",
            },
            {
                "when": "tier0 youthful allies route is explicitly chosen",
                "upgrade_id": 16542,
                "name": "Youthful Allies",
            },
            {
                "when": "tier1 striking route is explicitly chosen → Frightening Strike",
                "upgrade_id": 16544,
                "name": "Frightening Strike",
            },
            {
                "when": "tier1 striking route is explicitly chosen → Enraging Strike",
                "upgrade_id": 16545,
                "name": "Enraging Strike",
            },
            {
                "when": "tier1 striking route is explicitly chosen → Confusing Strike",
                "upgrade_id": 16546,
                "name": "Confusing Strike",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Tier0 alts and tier1 strike options are situational.",
        },
        "explanation_summary": "Safe A Rosy Outlook; tier0 alts and tier1 strikes are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    161: {
        "advice_model": "safe_default",
        "safe_default": _choice(16890, "Giant Hunter"),
        "push_default": _choice(16890, "Giant Hunter"),
        "farm_default": None,
        "conditionals": [
            {"when": "situational Giant Taunter", "upgrade_id": 16891, "name": "Giant Taunter"},
            {"when": "situational Giant Profits", "upgrade_id": 16892, "name": "Giant Profits"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Giant Taunter and Giant Profits are situational variants.",
        },
        "explanation_summary": "Safe Giant Hunter; Taunter/Profits are situational variants.",
        "review_needed": False,
        "review_reasons": [],
    },
    162: {
        "advice_model": "safe_default",
        "safe_default": _choice(17049, "Help the Unfortunate"),
        "push_default": _choice(17049, "Help the Unfortunate"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "contextual rescue route is needed",
                "upgrade_id": 17048,
                "name": "Who Else Would Save Them?",
            },
            {
                "when": "contextual outreach route is needed",
                "upgrade_id": 17050,
                "name": "Spreading the Word",
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
            "csv_advice_text": "Who Else Would Save Them? / Spreading the Word are contextual.",
        },
        "explanation_summary": "Safe Help the Unfortunate; other options are contextual.",
        "review_needed": False,
        "review_reasons": [],
    },
    163: {
        "advice_model": "safe_default",
        "safe_default": _choice(17086, "Tactical Advantage"),
        "push_default": _choice(17086, "Tactical Advantage"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 heart route is explicitly needed",
                "upgrade_id": 17083,
                "name": "Heart of Heroes",
            },
            {
                "when": "tier0 arrow route is explicitly needed",
                "upgrade_id": 17084,
                "name": "Arrow Alliance",
            },
            {
                "when": "tier0 unity route is explicitly needed",
                "upgrade_id": 17085,
                "name": "Unyielding Unity",
            },
            {
                "when": "tier1 dragon route is explicitly needed",
                "upgrade_id": 17087,
                "name": "Dragon Slayer",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Heart/Arrow/Unity and Dragon Slayer are tier-based situational picks.",
        },
        "explanation_summary": "Safe Tactical Advantage; other tier0/tier1 picks are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    # --- batch 09 remaining (final) ---
    164: {
        "advice_model": "safe_default",
        "safe_default": _choice(17321, "The Fallback Plan"),
        "push_default": _choice(17321, "The Fallback Plan"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "fallback/utility route is explicitly needed → Eyes on the Horizon",
                "upgrade_id": 17322,
                "name": "Eyes on the Horizon",
            },
            {
                "when": "rogue-focused alternative is explicitly needed → Rogues' Gallery",
                "upgrade_id": 17323,
                "name": "Rogues' Gallery",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": "The Fallback Plan",
            "csv_advice_text": "Horizon/Rogues' Gallery only when those alternatives are explicit.",
        },
        "explanation_summary": "Safe The Fallback Plan; Horizon/Rogues' Gallery stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    165: {
        "advice_model": "safe_default",
        "safe_default": _choice(17495, "Bargain With Eldath"),
        "push_default": _choice(17495, "Bargain With Eldath"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 Bargain With Tyr is selected",
                "upgrade_id": 17491,
                "name": "Bargain With Tyr",
            },
            {
                "when": "tier0 Bargain With Moradin is selected",
                "upgrade_id": 17492,
                "name": "Bargain With Moradin",
            },
            {
                "when": "tier0 Bargain With Tymora is selected",
                "upgrade_id": 17493,
                "name": "Bargain With Tymora",
            },
            {
                "when": "tier0 Bargain With Mystra is selected",
                "upgrade_id": 17494,
                "name": "Bargain With Mystra",
            },
            {
                "when": "tier1 Dark Bargain is selected",
                "upgrade_id": 17496,
                "name": "Dark Bargain",
            },
            {
                "when": "tier1 Bargain With Moradin variant is selected",
                "upgrade_id": 17497,
                "name": "Bargain With Moradin",
            },
            {
                "when": "tier1 Bargain With Tymora variant is selected",
                "upgrade_id": 17498,
                "name": "Bargain With Tymora",
            },
            {
                "when": "tier1 Bargain With Mystra variant is selected",
                "upgrade_id": 17499,
                "name": "Bargain With Mystra",
            },
            {
                "when": "tier1 Bargain With Eldath variant is selected",
                "upgrade_id": 17500,
                "name": "Bargain With Eldath",
            },
            {
                "when": "tier1 Bargain With Tyr variant is selected",
                "upgrade_id": 17501,
                "name": "Bargain With Tyr",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Other Bargain options and Dark Bargain are conditional; only Eldath is universal.",
        },
        "explanation_summary": "Safe Bargain With Eldath; other Bargains/Dark Bargain stay conditional.",
        "review_needed": True,
        "review_reasons": [
            "No CSV; tier1 still has many duplicate option names across upgrade ids",
        ],
    },
    166: {
        "advice_model": "safe_default",
        "safe_default": _choice(17679, "Ancestor's Shadow"),
        "push_default": _choice(17679, "Ancestor's Shadow"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 self-taught route is intended",
                "upgrade_id": 17678,
                "name": "Self Taught",
            },
            {
                "when": "situational library route is wanted",
                "upgrade_id": 17680,
                "name": "Lost in the Library",
            },
            {
                "when": "tier1 smell route is intended",
                "upgrade_id": 17681,
                "name": "Signature Smell",
            },
            {
                "when": "tier1 mastery route is intended",
                "upgrade_id": 17682,
                "name": "Smell Mastery",
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
            "csv_advice_text": "Self Taught/Library and Signature Smell/Smell Mastery stay conditional.",
        },
        "explanation_summary": "Safe Ancestor's Shadow; Self Taught/Library and smell routes stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    167: {
        "advice_model": "safe_default",
        "safe_default": _choice(17059, "Black Dragon's Corrosion"),
        "push_default": _choice(17059, "Black Dragon's Corrosion"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational Red Dragon's Greed",
                "upgrade_id": 17056,
                "name": "Red Dragon's Greed",
            },
            {
                "when": "situational Blue Dragon's Spark",
                "upgrade_id": 17057,
                "name": "Blue Dragon's Spark",
            },
            {
                "when": "situational Green Dragon's Spite",
                "upgrade_id": 17058,
                "name": "Green Dragon's Spite",
            },
            {
                "when": "situational White Dragon's Chill",
                "upgrade_id": 17060,
                "name": "White Dragon's Chill",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Other dragon colors are situational and stay conditional.",
        },
        "explanation_summary": "Safe Black Dragon's Corrosion; other dragon colors stay conditional.",
        "review_needed": False,
        "review_reasons": [],
    },
    168: {
        "advice_model": "safe_default",
        "safe_default": _choice(17765, "Embrace the Shadow Weave"),
        "push_default": _choice(17765, "Embrace the Shadow Weave"),
        "farm_default": None,
        "conditionals": [
            {"when": "tier0 pawn route is selected", "upgrade_id": 17762, "name": "Master of Pawns"},
            {
                "when": "tier0 unleashed route is selected",
                "upgrade_id": 17763,
                "name": "Shadow Unleashed",
            },
            {
                "when": "tier1 legacy route is selected",
                "upgrade_id": 17764,
                "name": "Legacy of Illefarn",
            },
            {
                "when": "tier1 survival route is selected",
                "upgrade_id": 17766,
                "name": "Rites of Survival",
            },
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": "Embrace the Shadow Weave",
            "csv_advice_text": "Pawns/Unleashed are tier0; Illefarn/Rites are tier1 alternatives.",
        },
        "explanation_summary": "Safe Embrace the Shadow Weave; other shadow options are tier-specific.",
        "review_needed": False,
        "review_reasons": [],
    },
    169: {
        "advice_model": "safe_default",
        "safe_default": _choice(17850, "Withering Ward"),
        "push_default": _choice(17850, "Withering Ward"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational switch route is needed",
                "upgrade_id": 17848,
                "name": "Witch's Switch",
            },
            {
                "when": "situational league route is needed",
                "upgrade_id": 17849,
                "name": "League of Malevolence",
            },
            {"when": "tier1 green fire route is needed", "upgrade_id": 17851, "name": "Green Fire"},
            {"when": "tier1 blue fire route is needed", "upgrade_id": 17852, "name": "Blue Fire"},
            {"when": "tier1 violet fire route is needed", "upgrade_id": 17853, "name": "Violet Fire"},
        ],
        "context_flags": {
            "formation_dependent": True,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": "Withering Ward",
            "csv_advice_text": "Switch/League are situational; Green/Blue/Violet Fire are tier1.",
        },
        "explanation_summary": "Safe Withering Ward; Switch/League/fire options stay tactical swaps.",
        "review_needed": False,
        "review_reasons": [],
    },
    170: {
        "advice_model": "safe_default",
        "safe_default": _choice(18055, "Band of Misfits"),
        "push_default": _choice(18055, "Band of Misfits"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational Center of Attention",
                "upgrade_id": 18056,
                "name": "Center of Attention",
            },
            {
                "when": "situational Path of Nightmares",
                "upgrade_id": 18057,
                "name": "Path of Nightmares",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Center of Attention / Path of Nightmares are situational.",
        },
        "explanation_summary": "Safe Band of Misfits; Attention/Nightmares are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    171: {
        "advice_model": "safe_default",
        "safe_default": _choice(18475, "Found Family"),
        "push_default": _choice(18475, "Found Family"),
        "farm_default": None,
        "conditionals": [
            {"when": "situational Pure of Heart", "upgrade_id": 18474, "name": "Pure of Heart"},
            {"when": "situational Never Surrender", "upgrade_id": 18476, "name": "Never Surrender"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Pure of Heart / Never Surrender are situational.",
        },
        "explanation_summary": "Safe Found Family; Pure of Heart/Never Surrender are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    172: {
        "advice_model": "safe_default",
        "safe_default": _choice(18671, "Complete Control"),
        "push_default": _choice(18671, "Complete Control"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational Faster Than Light",
                "upgrade_id": 18672,
                "name": "Faster Than Light",
            },
            {"when": "situational Pure of Soul", "upgrade_id": 18673, "name": "Pure of Soul"},
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Faster Than Light / Pure of Soul are situational.",
        },
        "explanation_summary": "Safe Complete Control; Faster Than Light/Pure of Soul are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    173: {
        "advice_model": "safe_default",
        "safe_default": _choice(18934, "Heroic Mage"),
        "push_default": _choice(18934, "Heroic Mage"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "situational reclusive mage route is needed",
                "upgrade_id": 18935,
                "name": "Reclusive Mage",
            },
            {
                "when": "situational war mage route is needed",
                "upgrade_id": 18936,
                "name": "War Mage",
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
            "csv_advice_text": "Reclusive Mage / War Mage are situational.",
        },
        "explanation_summary": "Safe Heroic Mage; Reclusive/War Mage are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    174: {
        "advice_model": "safe_default",
        "safe_default": _choice(19238, "Fast Friends"),
        "push_default": _choice(19238, "Fast Friends"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 map collector pre-cataclysm route is intended",
                "upgrade_id": 19240,
                "name": "Map Collector: Pre-Cataclysm",
            },
            {
                "when": "tier0 map collector time of darkness route is intended",
                "upgrade_id": 19241,
                "name": "Map Collector: Time of Darkness",
            },
            {
                "when": "tier0 map collector war of the lance route is intended",
                "upgrade_id": 19242,
                "name": "Map Collector: War of the Lance",
            },
            {
                "when": "tier1 small friends route is intended",
                "upgrade_id": 19237,
                "name": "Small Friends",
            },
            {
                "when": "tier1 old friends route is intended",
                "upgrade_id": 19239,
                "name": "Old Friends",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Map collector tier0 and Small/Old Friends are situational.",
        },
        "explanation_summary": "Safe Fast Friends; map collectors and Small/Old Friends are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    175: {
        "advice_model": "safe_default",
        "safe_default": _choice(19354, "Battle Plan: Charge"),
        "push_default": _choice(19354, "Battle Plan: Charge"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "tier0 outflank route is intended",
                "upgrade_id": 19355,
                "name": "Battle Plan: Outflank",
            },
            {
                "when": "tier0 fortify route is intended",
                "upgrade_id": 19356,
                "name": "Battle Plan: Fortify",
            },
            {
                "when": "tier1 attack route is intended",
                "upgrade_id": 19357,
                "name": "Lead the Attack",
            },
            {
                "when": "tier1 protect route is intended",
                "upgrade_id": 19358,
                "name": "Protect the Vulnerable",
            },
            {
                "when": "tier1 dragonlance route is intended",
                "upgrade_id": 19359,
                "name": "Wield the Dragonlance",
            },
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": False,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Outflank/Fortify and tier1 attack/protect/Dragonlance are situational.",
        },
        "explanation_summary": "Safe Battle Plan: Charge; other plans and tier1 picks are situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    176: {
        "advice_model": "safe_default",
        "safe_default": _choice(19692, "Faster, Friends"),
        "push_default": _choice(19692, "Faster, Friends"),
        "farm_default": _choice(19692, "Faster, Friends"),
        "conditionals": [
            {
                "when": "situational Ultimate Friends",
                "upgrade_id": 19693,
                "name": "Ultimate Friends",
            }
        ],
        "context_flags": {
            "formation_dependent": False,
            "adventure_dependent": False,
            "farm_push_split": True,
        },
        "sources": {
            "csv_default_label": None,
            "csv_label_maps_to": None,
            "csv_advice_text": "Ultimate Friends is situational.",
        },
        "explanation_summary": "Safe Faster, Friends; Ultimate Friends is situational.",
        "review_needed": False,
        "review_reasons": [],
    },
    177: {
        "advice_model": "safe_default",
        "safe_default": _choice(19702, "Endless Hunt"),
        "push_default": _choice(19702, "Endless Hunt"),
        "farm_default": None,
        "conditionals": [
            {
                "when": "contextual occult allies route is needed",
                "upgrade_id": 19700,
                "name": "Occult Allies",
            },
            {
                "when": "contextual scholar of dread route is needed",
                "upgrade_id": 19701,
                "name": "Scholar of Dread",
            },
            {
                "when": "tier1 cure wounds route is intended",
                "upgrade_id": 19703,
                "name": "Occult Aid: Cure Wounds",
            },
            {
                "when": "tier1 dispel evil route is intended",
                "upgrade_id": 19704,
                "name": "Occult Aid: Dispel Evil",
            },
            {
                "when": "tier1 sanctuary route is intended",
                "upgrade_id": 19705,
                "name": "Occult Aid: Sanctuary",
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
            "csv_advice_text": "Occult Allies/Scholar and Occult Aid tier1 options are contextual.",
        },
        "explanation_summary": "Safe Endless Hunt; Allies/Scholar and Occult Aid picks are contextual.",
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
