# Idle Champions specialization advice review (remaining batch 6, heroes 1-20 of 74)

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

## 1. D'hani (hero_id=89)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Ochre Jelly Yellow (13717)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Debuff focus / alt: Paint focus
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies wat je formatie het meest versterkt; vaak debuff/support tenzij je bewust haar eigen scaling stapelt.
- **Available options:**
  - tier 0: Ochre Jelly Yellow [13717] @L290; Twig Blight Green [13718] @L290; Frost Giant Blue [13719] @L290

## 2. Brig (hero_id=90)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** "Back"-Up Singer (6355)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: "Back"-Up Singer [6355] @L150; Cream of the Crop [6356] @L150

## 3. Widdle (hero_id=91)

- **Sample reason:** dynamic_handler, farm_gold
- **Risk tags:** dynamic_handler, farm_gold
- **Our default advice:** Mind and Body (6910)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Fast Friends / alt: Healing/other
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Speed bijna altijd voor farming; support/heal alleen als stabiliteit belangrijker is.
- **Available options:**
  - tier 0: Strong and Steady [6909] @L310; Mind and Body [6910] @L310; Wisdom and Confidence [6911] @L310

## 4. Yorven (hero_id=92)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Eldritch Claw Tattoo (17071)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Hunger For Blood [17070] @L120; Eldritch Claw Tattoo [17071] @L120; Follow The Mad Rabbit [17072] @L120; Infectious Fury [17073] @L120

## 5. Viconia (hero_id=93)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Begrudging Respect (9785)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Undead route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Neem undead-spec alleen als je team daar echt van profiteert.
- **Available options:**
  - tier 0: Holy Power [9784] @L80; Begrudging Respect [9785] @L80; Turn Undead [9786] @L80

## 6. Rust (hero_id=94)

- **Sample reason:** farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Even More Riches (15363)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Gold route / alt: Support route
- **CSV label maps to:** Get Rich Quick
- **CSV advice text:** Gold in economy teams; support anders.
- **Available options:**
  - tier 0: Get Rich Quick [15362] @L240; Even More Riches [15363] @L240; Rust's Fever Dream [15364] @L240

## 7. Vi (hero_id=95)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** A Nudge In The Right Direction (12318)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Bless Their Hearts [12316] @L200; Positive Reinforcement [12317] @L200; A Nudge In The Right Direction [12318] @L200

## 8. Desmond (hero_id=96)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Embrace the Beast (7305)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Living on the Edge / alt: Other route
- **CSV label maps to:** Embrace the Beast
- **CSV advice text:** Kies de route die het meeste uit defeated/dead synergie haalt; meestal support-georiënteerd.
- **Available options:**
  - tier 0: Double Time [7304] @L200; Embrace the Beast [7305] @L200; Strength in Numbers [7306] @L200

## 9. Tatyana (hero_id=97)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Best Friend Forever (7389)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Utility route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Tank voor survival; utility als haar pull/clear functie belangrijker is.
- **Available options:**
  - tier 0: Your Friends are My Friends [7387] @L140; By My Side [7388] @L140; Best Friend Forever [7389] @L140

## 10. Gazrick (hero_id=98)

- **Sample reason:** farm_gold, unmapped_label
- **Risk tags:** farm_gold, unmapped_label
- **Our default advice:** Aim Around Armor (7539)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Genius with Gold [7538] @L200; Aim Around Armor [7539] @L200; Finesse with Frost [7540] @L200

## 11. Dungeon Master (hero_id=99)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Fear Not, Champions! (7850)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Utility route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies utility afhankelijk van doel; hij is vooral een enablement-slot.
- **Available options:**
  - tier 0: Where Did He Go This Time? [7849] @L100; Fear Not, Champions! [7850] @L100; Special Guest Stars [16144] @L100

## 12. Nordom (hero_id=100)

- **Sample reason:** dynamic_handler
- **Risk tags:** dynamic_handler
- **Our default advice:** Modron Core Toolbox (18167)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Modron route / alt: Other route
- **CSV label maps to:** Modron Core Toolbox
- **CSV advice text:** Gebruik als utility-champion volgens automation/modron-doel.
- **Available options:**
  - tier 0: BASIC Functionality [18166] @L100; Modron Core Toolbox [18167] @L100; Core Competency [18168] @L100

## 13. Merilwen (hero_id=101)

- **Sample reason:** farm_gold, unmapped_label
- **Risk tags:** farm_gold, unmapped_label
- **Our default advice:** Meow-il-wen (7999)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Gold route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gold bij economy runs; support bij diepere pushes.
- **Available options:**
  - tier 0: Stink Like Skunk [7997] @L200; Treasures Her Friends [7998] @L200; Meow-il-wen [7999] @L200

## 14. Nahara (hero_id=102)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** A Barovian Bond (19724)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: A Grave Experience [19723] @L250; A Barovian Bond [19724] @L250; A Skilled Lyre [19725] @L250

## 15. Valentine (hero_id=103)

- **Sample reason:** farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** My Loyal Bodyguard (8150)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Socialite gold / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gold in economy runs; support als ze vooral formatie-buffs levert.
- **Available options:**
  - tier 0: All Hail the God Brain [8149] @L300; My Loyal Bodyguard [8150] @L300; Family Business [8151] @L300

## 16. Voronika (hero_id=104)

- **Sample reason:** multi_tier, farm_gold
- **Risk tags:** multi_tier, farm_gold
- **Our default advice:** Embrace Evil (15635), Battle Magic (15638)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support routing / alt: Other utility
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support-keuze; alleen afwijken bij niche utility-setup.
- **Available options:**
  - tier 0: Embrace Evil [15635] @L190; Hunt The Favored [15636] @L190; Weaken The Fools [15637] @L190
  - tier 1: Battle Magic [15638] @L500; Powerful Focus [15639] @L500; Strike First, Strike Hard [15640] @L500

## 17. Dob (hero_id=105)

- **Sample reason:** dynamic_handler, unmapped_label
- **Risk tags:** dynamic_handler, unmapped_label
- **Our default advice:** Befriend Everybody! (8745)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Befriend the Magical [8742] @L160; Befriend the Friendly [8743] @L160; Befriend the Quick [8744] @L160; Befriend Everybody! [8745] @L160

## 18. Blooshi (hero_id=106)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Charred Souls (7525)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Damage/support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Tank/spec voor progressie en survivability; alternatief bij offensieve opzet.
- **Available options:**
  - tier 0: Sliced Souls [7523] @L100; Skewered Souls [7524] @L100; Charred Souls [7525] @L100
  - tier 1: Resilient Spirit [7526] @L250; Wild Spirit [7527] @L250

## 19. Egbert (hero_id=113)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Atonement Begins with an Apology (8877)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Control route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik support als default; control als encounter-management nodig is.
- **Available options:**
  - tier 0: Atonement Begins with an Apology [8877] @L200; Team Chaos Team [8878] @L200
  - tier 1: Smoky Bombs [8879] @L300; Health Kick [8880] @L300; Oxventure Capitalism [8881] @L300

## 20. Kent (hero_id=114)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Potent Poison (9356)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Ranged route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Support als veilige default; afwijken bij ranged-specifieke setup.
- **Available options:**
  - tier 0: Robust Rivals [9355] @L250; Potent Poison [9356] @L250
