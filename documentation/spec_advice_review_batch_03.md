# Idle Champions specialization advice review (remaining batch 3, heroes 1-20 of 134)

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

## 1. Jamilah (hero_id=11)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Bruiser (239)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Bruiser / alt: Other route
- **CSV label maps to:** Bruiser
- **CSV advice text:** Kies damage als je haar gebruikt; anders meestal geen prioriteit.
- **Available options:**
  - tier 0: Bruiser [239] @L60; Indomitable Might [240] @L60

## 2. Arkhan (hero_id=12)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Bulk Up (243)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Usurp / alt: Bulk Up
- **CSV label maps to:** Usurped Power
- **CSV advice text:** Kies de spec die exact past bij je Arkhan-formatie; vaak pure usurp-logica.
- **Available options:**
  - tier 0: Bulk Up [243] @L65; Usurped Power [244] @L65

## 3. Drizzt (hero_id=18)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Drow Stalker (11517)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** DPS route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Als je Drizzt gebruikt als carry, kies pure damage.
- **Available options:**
  - tier 0: Leader of the Companions [11516] @L180; Drow Stalker [11517] @L180

## 4. Barrowin (hero_id=19)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Booming Voice (10690)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Healing route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Healing wanneer sustain telt; support als fight al veilig is.
- **Available options:**
  - tier 0: Greater Blessing [10689] @L130; Booming Voice [10690] @L130; Hammer of the Law [10691] @L130

## 5. Birdsong (hero_id=21)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Concertino (10783)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** DPS route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies op basis van rol: carry = damage, anders support.
- **Available options:**
  - tier 0: Theme of Valor [10778] @L60; Theme of Consideration [10779] @L60; Theme of Deception [10780] @L60
  - tier 1: Unison [10781] @L130; Soprano [10782] @L130; Concertino [10783] @L130

## 6. Strix (hero_id=23)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Smelly Lunch (12292)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Smelly Lunch / alt: Olfactory Fatigue
- **CSV label maps to:** Smelly Lunch
- **CSV advice text:** Meestal Smelly Lunch (Poor Hygiene ×5). Olfactory Fatigue alleen als je Power of Friendship wilt stacken; Scent of Brimstone bij veel Tieflings.
- **Available options:**
  - tier 0: Olfactory Fatigue [12290] @L190; Scent of Brimstone [12291] @L190; Smelly Lunch [12292] @L190

## 7. Nrakk (hero_id=24)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Githzerai Focus (13005)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Buff route / alt: Race route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies de route die je belangrijkste support-interacties activeert.
- **Available options:**
  - tier 0: Githzerai Focus [13005] @L200; Githzerai Agility [13006] @L200

## 8. Binwin (hero_id=27)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Tallest in Faerûn (18465)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Overkill [18463] @L120; Dwarven Encouragement [18464] @L120; Tallest in Faerûn [18465] @L120

## 9. Xander (hero_id=29)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Follow Closely (1196)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Trying Extra Hard [1195] @L175; Follow Closely [1196] @L175

## 10. Azaka (hero_id=30)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Resist the Curse (1237)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Resist the Curse [1237] @L100; Lycanthrope Forever [1238] @L100

## 11. Ishi (hero_id=31)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Friend to the Familiar (16532)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Friend to the Familiar [16532] @L90; Friend to the Feared [16533] @L90; Friend to the Exceptional [16534] @L90

## 12. Wulfgar (hero_id=32)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Flag Bearer (11509)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Heavy Blows [11508] @L140; Flag Bearer [11509] @L140; Moradin's Will [11510] @L140

## 13. Farideh (hero_id=33)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Daughters of Mehen (17839)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Daughters of Mehen [17839] @L140; Fury of Asmodeus [17840] @L140; Pact with Lorcan [17841] @L140

## 14. Vlahnya (hero_id=35)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Breaking Out Solo (1659)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Spy Network [1658] @L200; Breaking Out Solo [1659] @L200

## 15. Nerys (hero_id=37)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Kelemvor's Foe (9747)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Kelemvor's Heal [9745] @L80; Kelemvor's Will [9746] @L80; Kelemvor's Foe [9747] @L80

## 16. K'thriss (hero_id=38)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Velvet Touch (17328)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Efficient Bookkeeping / alt: Pain
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Meestal support/debuff voor push; kies de alternatieve scaling alleen als je formatie daar expliciet op leunt.
- **Available options:**
  - tier 0: Velvet Touch [17328] @L130; Ligotti's Minions [17329] @L130; The Unknowable Ur [17330] @L130

## 17. Black Viper (hero_id=40)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Collector (2112)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Assassinate [2111] @L215; Collector [2112] @L215

## 18. Rosie (hero_id=41)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Busy Beestinger (15613)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Damage route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Als deze champion je carry is, kies de pure damage-route.
- **Available options:**
  - tier 0: Matriarch [15609] @L170; Familiar Friends [15610] @L170; Grandmother Night [15611] @L170
  - tier 1: Grandma-Bod [15612] @L280; Busy Beestinger [15613] @L280; Slower Decay [15614] @L280

## 19. Aila (hero_id=42)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Stormbreaker (8785)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Debuff route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Debuff/tank kiezen afhankelijk van push en survivability.
- **Available options:**
  - tier 0: Stormcaller [8784] @L225; Stormbreaker [8785] @L225

## 20. Spurt (hero_id=43)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Adopted Family (10683)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Pack Tactics / alt: Kobold Family
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Neem meestal de sterkste support-optie; niche keuzes alleen voor specifieke synergie.
- **Available options:**
  - tier 0: Kobold Family [10681] @L250; Centi-pult [10682] @L250; Adopted Family [10683] @L250
