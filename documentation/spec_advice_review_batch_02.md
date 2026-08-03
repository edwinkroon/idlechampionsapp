# Idle Champions specialization advice review (risk sample)

This batch is a stratified sample (handlers, farm/gold, formation/adventure,
multi-tier, unmapped labels, recent champs) — not sequential IDs.

Please review each champion below. For each one, answer:
1. Is there a safe universal default, or should safe_default be null?
2. Split push vs farm vs formation/adventure conditionals if needed.
3. Any wrong option names, unmapped UI labels, or missing situational rules?

## 1. Hitch (hero_id=13)

- **Sample reason:** risk sample primary=unmapped_label; tags=unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Charismatic (391)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** High Cha route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Neem de route die het meeste charisma/synergie in je formatie benut.
- **Available options:**
  - tier 0: More Daggers [386] @L160; Charismatic [391] @L160

## 2. Stoki (hero_id=14)

- **Sample reason:** risk sample primary=unmapped_label; tags=unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** All Out Assault (16056)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Stack route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Neem de lijn die meer support op je dps geeft; stacks alleen als setup dat ondersteunt.
- **Available options:**
  - tier 0: All Out Assault [16056] @L200; Bend It Like Birdsong [16057] @L200; A Little Bit Faster Now [16058] @L200

## 3. Krond (hero_id=15)

- **Sample reason:** risk sample primary=multi_tier; tags=multi_tier
- **Risk tags:** multi_tier
- **Our default advice:** Eldritch Strike (17242)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Damage route / alt: Other route
- **CSV label maps to:** War Magic
- **CSV advice text:** Als deze champion je carry is, kies de pure damage-route.
- **Available options:**
  - tier 0: Survival of the Strongest [17238] @L60; Survival of the Fittest [17239] @L60; Survival of the Smartest [17240] @L60
  - tier 1: Eldritch Strike [17242] @L150; Power Behind the Throne [17243] @L150; War Magic [17244] @L150

## 4. Gromma (hero_id=16)

- **Sample reason:** risk sample primary=multi_tier; tags=multi_tier
- **Risk tags:** multi_tier
- **Our default advice:** Circle of the Arctic (14878)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Arctic / alt: Mountain
- **CSV label maps to:** Circle of the Arctic
- **CSV advice text:** Debuff/tank afhankelijk van encounter; kies de lijn die je push betrouwbaarder maakt.
- **Available options:**
  - tier 0: Circle of the Mountain [14877] @L100; Circle of the Arctic [14878] @L100; Circle of the Swamp [14879] @L100
  - tier 1: Stoneskin [14880] @L300; Entanglement [14881] @L300; Melf's Acid Arrow [14882] @L300

## 5. Dhadius (hero_id=17)

- **Sample reason:** risk sample primary=multi_tier; tags=multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Empowered Empowerment (14559)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Debuff route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Spec kiezen op basis van wat je carry meer geeft; meestal support/debuff voor push.
- **Available options:**
  - tier 0: Together In Magic [14556] @L140; Apart in Magic [14557] @L140
  - tier 1: Empowered Orbs [14558] @L260; Empowered Empowerment [14559] @L260; Use Smaller Words [14560] @L260

## 6. Regis (hero_id=20)

- **Sample reason:** risk sample primary=dynamic_handler; tags=dynamic_handler, multi_tier
- **Risk tags:** dynamic_handler, multi_tier
- **Our default advice:** Ruby Encouragement (Ahead) (11530)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Ahead / alt: Behind
- **CSV label maps to:** Ruby Encouragement (Ahead)
- **CSV advice text:** Kies Ahead/Behind naar de kolom van je DPS; bij Ruby Weakness kies het attack-type van je BUD (melee/ranged/magic).
- **Available options:**
  - tier 0: Ruby Encouragement (Ahead) [11530] @L20; Ruby Encouragement (Behind) [11531] @L20
  - tier 1: Ruby Weakness (Ranged) [11532] @L150; Ruby Weakness (Melee) [11533] @L150; Ruby Weakness (Magic) [11534] @L150

## 7. Zorbu (hero_id=22)

- **Sample reason:** risk sample primary=formation_or_adventure; tags=formation_or_adventure, unmapped_label
- **Risk tags:** formation_or_adventure, unmapped_label
- **Our default advice:** Lead The Pack (12993)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Enemy type route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies de spec die bij de relevante enemy types en je Zorbu-doel past.
- **Available options:**
  - tier 0: Lead The Pack [12993] @L60; Hunting Partners [12994] @L60

## 8. Catti-brie (hero_id=25)

- **Sample reason:** risk sample primary=dynamic_handler; tags=dynamic_handler, unmapped_label
- **Risk tags:** dynamic_handler, unmapped_label
- **Our default advice:** Big Push (11313)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Crit route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Neem de route die je carry sterker bufft; vaak support/crit afhankelijk van comp.
- **Available options:**
  - tier 0: Piercing Arrow [11312] @L220; Big Push [11313] @L220; Critical Family [11314] @L220

## 9. Evelyn (hero_id=26)

- **Sample reason:** risk sample primary=dynamic_handler; tags=dynamic_handler
- **Risk tags:** dynamic_handler
- **Our default advice:** Compel Duel (12211)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** Lathander's Allies
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Fighting Style: Protection [12210] @L240; Compel Duel [12211] @L240; Lathander's Allies [12212] @L240

## 10. Deekin (hero_id=28)

- **Sample reason:** risk sample primary=farm_gold; tags=farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Troubadour Troupe (18862)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Boss Wants Speed / alt: Confidence in the Boss
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Speed is standaard voor farming en snelle clears.
- **Available options:**
  - tier 0: Unorthodox Stories [18860] @L130; DOOOOOM From Afar [18861] @L130; Troubadour Troupe [18862] @L130

## 11. Donaar (hero_id=34)

- **Sample reason:** risk sample primary=farm_gold; tags=multi_tier, farm_gold
- **Risk tags:** multi_tier, farm_gold
- **Our default advice:** Business Partners (18659), Command: Cower (18662)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Ohhh Yeah / alt: Blessing focus
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gold voor farm/favor; utility/support voor push.
- **Available options:**
  - tier 0: Not So Straightforward [18657] @L150; Scales and Horns [18658] @L150; Business Partners [18659] @L150
  - tier 1: Command: Hold [18660] @L250; Command: Duel [18661] @L250; Command: Cower [18662] @L250; Command: Droppit [18663] @L250

## 12. Warden (hero_id=36)

- **Sample reason:** risk sample primary=dynamic_handler; tags=dynamic_handler, unmapped_label
- **Risk tags:** dynamic_handler, unmapped_label
- **Our default advice:** The Dark Hunger (13246)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Highest specter-cap route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies de specter-cap met de meeste doelen in je formatie: Evil (Dark Hunger), DEX≥16 (Shadows), of CHA-hoogst (Charm).
- **Available options:**
  - tier 0: The Dark Hunger [13246] @L80; Shadows in the Night [13247] @L80; Charm of the Fallen [13248] @L80

## 13. Paultin (hero_id=39)

- **Sample reason:** risk sample primary=farm_gold; tags=farm_gold, unmapped_label
- **Risk tags:** farm_gold, unmapped_label
- **Our default advice:** Luck of the Vistani (2038)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Luck of the Vistani [2038] @L280; Additional Secrets [2039] @L280

## 14. Shandie (hero_id=47)

- **Sample reason:** risk sample primary=farm_gold; tags=farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Alchemist's Fire Expertise (9731)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Dash / alt: Other route
- **CSV label maps to:** Criminal Contacts
- **CSV advice text:** Speed is de standaardkeuze voor farming.
- **Available options:**
  - tier 0: Known Allies [9730] @L230; Alchemist's Fire Expertise [9731] @L230; Criminal Contacts [9732] @L230

## 15. Morgaen (hero_id=55)

- **Sample reason:** risk sample primary=formation_or_adventure; tags=multi_tier, formation_or_adventure, unmapped_label
- **Risk tags:** multi_tier, formation_or_adventure, unmapped_label
- **Our default advice:** Calm Under Pressure (3336)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Fine As Is [3330] @L240; Keep Your Distance [3331] @L240; Monster Fodder [3332] @L240; Stay Out Of My Way [3333] @L240
  - tier 1: Keep It Simple [3334] @L300; Tight Formation [3335] @L300; Calm Under Pressure [3336] @L300; The Long Game [3337] @L300
  - tier 2: Tight Formation [3340] @L420; Calm Under Pressure [3341] @L420; The Long Game [3342] @L420; Keep It Simple [3343] @L420; Calm Under Pressure [3344] @L420; The Long Game [3345] @L420; Keep It Simple [3346] @L420; Tight Formation [3347] @L420; The Long Game [3348] @L420; Keep It Simple [3349] @L420; Tight Formation [3350] @L420; Calm Under Pressure [3351] @L420

## 16. Beadle (hero_id=64)

- **Sample reason:** risk sample primary=dynamic_handler; tags=dynamic_handler
- **Risk tags:** dynamic_handler
- **Our default advice:** Epic Equipment (16727)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Epic Equipment [16727] @L160; Premium Gear [16728] @L160; Shiniest Loot [16729] @L160

## 17. Omin (hero_id=65)

- **Sample reason:** risk sample primary=fill:dynamic_handler; tags=dynamic_handler, farm_gold, unmapped_label
- **Risk tags:** dynamic_handler, farm_gold, unmapped_label
- **Our default advice:** Favored Friends (12305)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Gold route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gold voor favor/gold teams; support voor standaard push.
- **Available options:**
  - tier 0: Form Ranks [12304] @L180; Favored Friends [12305] @L180; Long Term Investments [12306] @L180

## 18. Sgt. Knox (hero_id=82)

- **Sample reason:** risk sample primary=formation_or_adventure; tags=formation_or_adventure
- **Risk tags:** formation_or_adventure
- **Our default advice:** Shield Wall (15961)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Support route
- **CSV label maps to:** Shield Wall
- **CSV advice text:** Meestal wat je formation mist: tankiness of extra support.
- **Available options:**
  - tier 0: Impromptu Allies [15959] @L160; For The Greater Good [15960] @L160; Shield Wall [15961] @L160

## 19. Ravengard (hero_id=149)

- **Sample reason:** risk sample primary=recent; tags=recent
- **Risk tags:** recent
- **Our default advice:** Legacy of Ravengard (15033)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Lead The Charge [15031] @L200; Strength of Baldur's Gate [15032] @L200; Legacy of Ravengard [15033] @L200

## 20. Kas (hero_id=153)

- **Sample reason:** risk sample primary=recent; tags=recent
- **Risk tags:** recent
- **Our default advice:** Kas the Betrayer (15624)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Kas the Bloody Handed [15623] @L180; Kas the Betrayer [15624] @L180; Kas the Destroyer [15625] @L180
