# Idle Champions specialization advice review (remaining batch 8, heroes 1-20 of 34)

Please review each champion below. For each one, answer:
1. Is there a safe universal default, or should safe_default be null?
2. Split push vs farm vs formation/adventure conditionals if needed.
3. Any wrong option names, unmapped UI labels, or missing situational rules?

Decision rule:
- If CSV and config conflict, keep the most stable universal default as safe_default.
- Use null only when no safe universal default exists.
- Use conditional_only for situational alternatives.
- Keep csv_label_maps_to aligned with the chosen safe_default.
- Keep csv_advice_text specific to when the alternative should be chosen.

## 1. Wyll (hero_id=142)

- **Sample reason:** dynamic_handler, unmapped_label, recent
- **Risk tags:** dynamic_handler, unmapped_label, recent
- **Our default advice:** Pact of the Blade (13433)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Pact of the Blade [13433] @L110; Pact of the Chain [13434] @L110; Pact of the Tome [13435] @L110

## 2. Karlach (hero_id=143)

- **Sample reason:** dynamic_handler, unmapped_label, recent
- **Risk tags:** dynamic_handler, unmapped_label, recent
- **Our default advice:** Berserker (13726)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Berserker [13726] @L130; Wildheart [13727] @L130; Wild Magic [13728] @L130

## 3. Presto (hero_id=144)

- **Sample reason:** unmapped_label, recent
- **Risk tags:** unmapped_label, recent
- **Our default advice:** Humble Heroes (13765)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Humble Heroes [13765] @L200; Junior Juggernauts [13766] @L200; Magical Mastery [13767] @L200

## 4. Dynaheir (hero_id=145)

- **Sample reason:** unmapped_label, recent
- **Risk tags:** unmapped_label, recent
- **Our default advice:** Circle Magic (13879)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: DPS route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Support als default; damage alleen wanneer ze je carry is.
- **Available options:**
  - tier 0: Circle Magic [13879] @L250; Iron Lord's Justice [13880] @L250; Loyal Bodyguard [13881] @L250

## 5. Dark Urge (hero_id=146)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Divine Soul (14384)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Storm Sorcery [14382] @L130; Draconic Bloodline [14383] @L130; Divine Soul [14384] @L130
  - tier 1: Embrace the Urge [14385] @L180; Resist the Urge [14386] @L180

## 6. Gale (hero_id=147)

- **Sample reason:** dynamic_handler, multi_tier, recent
- **Risk tags:** dynamic_handler, multi_tier, recent
- **Our default advice:** Ceremorphosis (14578)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** Mystical Mentor
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Evocation [14574] @L140; Abjuration [14575] @L140; Enchantment [14576] @L140; Illusion [14577] @L140
  - tier 1: Ceremorphosis [14578] @L250; Mystical Mentor [14579] @L250; Finite Fellowship [14580] @L250

## 7. Diana (hero_id=148)

- **Sample reason:** dynamic_handler, multi_tier, unmapped_label, recent
- **Risk tags:** dynamic_handler, multi_tier, unmapped_label, recent
- **Our default advice:** Ensemble Cast (14796)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Inspire: Acrobatic Assault [14791] @L60; Inspire: Modest Might [14792] @L60; Inspire: Fledgling Fury [14793] @L60
  - tier 1: Ensemble Cast [14796] @L130; Spotlight Episode [14797] @L130

## 8. Aeon (hero_id=150)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Play the Long Game (15200)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Immediate Infiltration [15199] @L150; Play the Long Game [15200] @L150
  - tier 1: Artificer's Arsenal [15201] @L250; Spy Network [15202] @L250; Powerful Patronage [15203] @L250

## 9. Umberto (hero_id=151)

- **Sample reason:** dynamic_handler, multi_tier, recent
- **Risk tags:** dynamic_handler, multi_tier, recent
- **Our default advice:** Family of Orphans (15053), More Damage (15057)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Law's Alliance [15052] @L200; Family of Orphans [15053] @L200; Call of the Wardens [15054] @L200
  - tier 1: More Bees [15055] @L400; More Clues [15056] @L400; More Damage [15057] @L400

## 10. Bobby (hero_id=152)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Group Charge (15448)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Stunning Strength [15447] @L110; Group Charge [15448] @L110
  - tier 1: Not So Low [15449] @L250; Still Growing Up [15450] @L250; Strong Armed [15451] @L250

## 11. Minthara (hero_id=154)

- **Sample reason:** unmapped_label, recent
- **Risk tags:** unmapped_label, recent
- **Our default advice:** Soul Destroyer (15948)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: House Matron [15946] @L250; True Soul [15947] @L250; Soul Destroyer [15948] @L250

## 12. Wren (hero_id=155)

- **Sample reason:** unmapped_label, recent
- **Risk tags:** unmapped_label, recent
- **Our default advice:** Glitch Form: Dwarf Monk (15217)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Glitch Form: Dwarf Monk [15217] @L80; Glitch Form: Tabaxi Barbarian [15218] @L80; Glitch Form: Warforged Sorcerer [15219] @L80

## 13. Halsin (hero_id=156)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Harbinger of the Wilds (15966)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Harbinger of the Wilds [15966] @L240; Sage of the Transformed [15967] @L240; Protector of the Grove [15968] @L240

## 14. Eric (hero_id=157)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Trait: Brave (16135)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Trait: Cautious [16134] @L30; Trait: Brave [16135] @L30; Trait: Sarcastic [16136] @L30
  - tier 1: Unassuming Force [16137] @L470; Youthful Valor [16138] @L470; Treasure Hunters [16139] @L470

## 15. Kalix (hero_id=158)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Creative Camouflage (16522)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Strength in Numbers [16521] @L240; Creative Camouflage [16522] @L240; One For You, One For Me [16523] @L240

## 16. Volo (hero_id=159)

- **Sample reason:** dynamic_handler, recent
- **Risk tags:** dynamic_handler, recent
- **Our default advice:** Volo's Guide to All Things Magical (16556)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Volo's Guide to Spirits and Specters [16554] @L150; Volo's Guide to Brain-Eating Tadpoles [16555] @L150; Volo's Guide to All Things Magical [16556] @L150

## 17. Sheila (hero_id=160)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** A Rosy Outlook (16543)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Meekly Meeting [16541] @L90; Youthful Allies [16542] @L90; A Rosy Outlook [16543] @L90
  - tier 1: Frightening Strike [16544] @L200; Enraging Strike [16545] @L200; Confusing Strike [16546] @L200

## 18. Grimm (hero_id=161)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Giant Hunter (16890)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Giant Hunter [16890] @L200; Giant Taunter [16891] @L200; Giant Profits [16892] @L200

## 19. Vlithryn (hero_id=162)

- **Sample reason:** dynamic_handler, recent
- **Risk tags:** dynamic_handler, recent
- **Our default advice:** Help the Unfortunate (17049)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Who Else Would Save Them? [17048] @L80; Help the Unfortunate [17049] @L80; Spreading the Word [17050] @L80

## 20. Hank (hero_id=163)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Tactical Advantage (17086)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Heart of Heroes [17083] @L110; Arrow Alliance [17084] @L110; Unyielding Unity [17085] @L110
  - tier 1: Tactical Advantage [17086] @L230; Dragon Slayer [17087] @L230
