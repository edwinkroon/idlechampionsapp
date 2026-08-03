# Idle Champions specialization advice review (remaining batch 7, heroes 1-20 of 54)

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

## 1. Virgil (hero_id=115)

- **Sample reason:** farm_gold, unmapped_label
- **Risk tags:** farm_gold, unmapped_label
- **Our default advice:** Mood: Anxious (9608)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Speed voor farm; support voor push.
- **Available options:**
  - tier 0: Mood: Relaxed [9607] @L150; Mood: Anxious [9608] @L150; Mood: Determined [9609] @L150

## 2. Warduke (hero_id=116)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Chaos Reigns (9619)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** DPS route / alt: Evil route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies wat zijn eigen carry-potentie of evil-synergie het best ondersteunt.
- **Available options:**
  - tier 0: Chaos Reigns [9619] @L250; Mercenary for Hire [9620] @L250; League of Malevolence [9621] @L250

## 3. Imoen (hero_id=117)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Aberration Slaying Arrows (9646)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Beast Slaying Arrows [9643] @L40; Dragon Slaying Arrows [9644] @L40; Monstrosity Slaying Arrows [9645] @L40; Aberration Slaying Arrows [9646] @L40

## 4. Fen (hero_id=118)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Curse of the Dhampir (9762)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Shadows of the Underdark [9761] @L140; Curse of the Dhampir [9762] @L140

## 5. Uriah (hero_id=119)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Book of Exalted Deeds (19680)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Book of Exalted Deeds [19680] @L120; Book of Vile Darkness [19681] @L120

## 6. Solaak (hero_id=120)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Confidant (10617)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Unwavering [10615] @L280; Emboldened [10616] @L280; Confidant [10617] @L280

## 7. Miria (hero_id=121)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Independent (10672)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Utility route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Tank als survivability telt; utility bij specifieke varianten.
- **Available options:**
  - tier 0: Methodical [10670] @L80; Intellectual [10671] @L80; Independent [10672] @L80

## 8. Antrius (hero_id=122)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Bard College (10798)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Bard College [10798] @L300; Truly Awful Stats [10799] @L300; The "A" In Chaotic Is For Antrius [10800] @L300

## 9. Nixie (hero_id=123)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Anarchy Amplified (10892)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Infernal Impact [10890] @L130; Flawed Force [10891] @L130; Anarchy Amplified [10892] @L130

## 10. Evandra (hero_id=124)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Carnival Crew (11301)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** Powerful Allies
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Powerful Allies [11299] @L200; Fighting Force [11300] @L200; Carnival Crew [11301] @L200

## 11. BBEG (hero_id=125)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Min-Maxing (11545)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Control route / alt: Support route
- **CSV label maps to:** Min-Maxing
- **CSV advice text:** Meestal control/debuff voor utility; support als het beter schaalt met je comp.
- **Available options:**
  - tier 0: Powergaming [11544] @L150; Min-Maxing [11545] @L150; Rules Lawyering [11546] @L150

## 12. Strongheart (hero_id=126)

- **Sample reason:** dynamic_handler
- **Risk tags:** dynamic_handler
- **Our default advice:** Honorary Member (19734)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** Valor's Call
- **CSV advice text:** Gebruik de support-optie die quest/progressie of push het best dient.
- **Available options:**
  - tier 0: Valor's Call [19733] @L80; Honorary Member [19734] @L80; A Righteous Event [19738] @L80

## 13. Vin Ursa (hero_id=127)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Friends in High Places (12094)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Front Deck [12090] @L30; Rear Deck [12091] @L30
  - tier 1: Friends in Low Places [12092] @L250; Friends in Meh Places [12093] @L250; Friends in High Places [12094] @L250

## 14. Lae'zel (hero_id=128)

- **Sample reason:** farm_gold, unmapped_label
- **Risk tags:** farm_gold, unmapped_label
- **Our default advice:** Battle Master (12119)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik speed voor farming en snelle clears; wijk af als survival of specifieke utility belangrijker is.
- **Available options:**
  - tier 0: Champion [12118] @L230; Battle Master [12119] @L230; Eldritch Knight [12120] @L230

## 15. Astarion (hero_id=129)

- **Sample reason:** multi_tier
- **Risk tags:** multi_tier
- **Our default advice:** Arcane Trickster (12496)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Damage route / alt: Support route
- **CSV label maps to:** Outflank (Top)
- **CSV advice text:** Carry = damage; anders support als je hem daarvoor inzet.
- **Available options:**
  - tier 0: Outflank (Top) [12493] @L10; Outflank (Bottom) [12494] @L10
  - tier 1: Thief [12495] @L200; Arcane Trickster [12496] @L200; Assassin [12497] @L200

## 16. Krux (hero_id=136)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Foe of Xaryxis (11660)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Nautical Knockback [11658] @L250; Take the Helm [11659] @L250; Foe of Xaryxis [11660] @L250

## 17. Certainty (hero_id=138)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Best And The Brightest (12510)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Best And The Brightest [12510] @L200; Smooth Negotiators [12511] @L200

## 18. Thellora (hero_id=139)

- **Sample reason:** farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Callessa's Blessed (12984)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Support route
- **CSV label maps to:** Vanguard of the Quick
- **CSV advice text:** Gebruik speed voor farming en snelle clears; wijk af als survival of specifieke utility belangrijker is.
- **Available options:**
  - tier 0: Defender of the Meek [12982] @L150; Vanguard of the Quick [12983] @L150; Callessa's Blessed [12984] @L150

## 19. Jang Sao (hero_id=140)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Moon Collector (13263)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Wisdom of the Ages [13261] @L100; Speed of Shooting Stars [13262] @L100
  - tier 1: Moon Collector [13263] @L170; Star Caller [13264] @L170; Night Runner [13265] @L170

## 20. Shadowheart (hero_id=141)

- **Sample reason:** dynamic_handler, unmapped_label, recent
- **Risk tags:** dynamic_handler, unmapped_label, recent
- **Our default advice:** Find Yourself (13281)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **CSV rule label:** Healing route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Healing/survival wanneer sustain nodig is; anders support.
- **Available options:**
  - tier 0: Guidance [13279] @L180; Sister of Darkness [13280] @L180; Find Yourself [13281] @L180
