# Idle Champions specialization advice review (remaining batch 5, heroes 1-20 of 94)

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

## 1. Ulkoria (hero_id=68)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Shield Guardian (4349)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Magic route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Alleen goed wanneer je magic-heavy formatie draait; kies de spec die dat maximaliseert.
- **Available options:**
  - tier 0: Shield Guardian [4349] @L435; Urchin Pranks [4350] @L435

## 2. Torogar (hero_id=69)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Tiamat's Rage (4493)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Tiamat's Word [4492] @L250; Tiamat's Rage [4493] @L250

## 3. Ezmerelda (hero_id=70)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** We've Trained For This (15041)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** We've Trained For This
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: We've Trained For This [15041] @L200; Vampire Hunter [15042] @L200; The Devil You Know [15043] @L200

## 4. Penelope (hero_id=71)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Everybody Gets To Be Friends (14705)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Control route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Support als default; control bij lastig encounter-patroon.
- **Available options:**
  - tier 0: Keep Your Friends Close [14703] @L130; Keep Your Future Friends Closer [14704] @L130; Everybody Gets To Be Friends [14705] @L130
  - tier 1: Fury of the Fireflies [14706] @L300; Splitting The Hive [14707] @L300; Dance of the Ladybugs [14708] @L300

## 5. Lucius (hero_id=72)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Dichromancy (19253)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Dichromancy [19253] @L120; Corrosion Master [19254] @L120; Lingering Chill [19255] @L120

## 6. Baeloth (hero_id=73)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Baeloth's Birthday Party (4749)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Djinn route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Meestal support; utility-keuze als je death-prevention of specifieke interacties nodig hebt.
- **Available options:**
  - tier 0: Baeloth's Birthday Party [4749] @L220; Over Excited [4750] @L220; The Show Must Go On [4751] @L220

## 7. Talin (hero_id=74)

- **Sample reason:** farm_gold, formation_or_adventure, unmapped_label
- **Risk tags:** farm_gold, formation_or_adventure, unmapped_label
- **Our default advice:** Additional Scatter Tacks (4766)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Control route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Speed voor farms; control/debuff voor lastige zones.
- **Available options:**
  - tier 0: Path Finder [4765] @L300; Additional Scatter Tacks [4766] @L300; Reversal of Fortunes [4767] @L300

## 8. Hew Maan (hero_id=75)

- **Sample reason:** farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Did We Say Humans? We Meant... (10653)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Support route
- **CSV label maps to:** Did We Say Humans? We Meant...
- **CSV advice text:** Gebruik speed voor farming en snelle clears; wijk af als survival of specifieke utility belangrijker is.
- **Available options:**
  - tier 0: Did We Say Humans? We Meant... [10653] @L240; Law Maan [10654] @L240; Hello, Fellow Mercenaries! [10655] @L240

## 9. Orisha (hero_id=76)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Blazing Soul (4909)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Blazing Soul [4909] @L100; Long Burn [4910] @L100
  - tier 1: Sirens' Connection [4911] @L200; Fierce Connection [4912] @L200

## 10. Alyndra (hero_id=77)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Expansive Vision (17749)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Positional route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Neem meestal support; alternatief als adjacency exact gunstig uitpakt.
- **Available options:**
  - tier 0: Expansive Vision [17749] @L150; Extra Judgy [17750] @L150; Heroes of the Planes [17751] @L150

## 11. Orkira (hero_id=78)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Tailfeather of the Phoenix (5577)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Healing route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Healing/survival wanneer sustain nodig is; anders support.
- **Available options:**
  - tier 0: Breath of the Phoenix [5576] @L200; Tailfeather of the Phoenix [5577] @L200

## 12. Shaka (hero_id=79)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Blinding Wall of Light (13424)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Puzzle route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik de route die je puzzle/formatie het beste laat landen.
- **Available options:**
  - tier 0: Blinding Wall of Light [13424] @L90; Disintegrating Wall of Light [13425] @L90
  - tier 1: Child's Play [13420] @L150; Pen and Paper [13421] @L150; Sunday Edition [13422] @L150; Brain Break [13423] @L150

## 13. Mehen (hero_id=80)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Found Family (16152)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Fiend route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Alleen echt sterk als je roster bij zijn synergie past; kies dus roster-afhankelijk.
- **Available options:**
  - tier 0: Fighting Force [16150] @L250; Father Figure [16151] @L250; Found Family [16152] @L250

## 14. Selise (hero_id=81)

- **Sample reason:** multi_tier
- **Risk tags:** multi_tier
- **Our default advice:** Mithral Skin (13751)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Support route
- **CSV label maps to:** Reflective Shield
- **CSV advice text:** Kies tank/survival wanneer je frontlinie onder druk staat; anders de support-optie.
- **Available options:**
  - tier 0: Relentless Avenger [13749] @L120; Reflective Shield [13750] @L120; Mithral Skin [13751] @L120
  - tier 1: Tyr's Eyes [13752] @L350; Relentless Avenger [13753] @L350; Reflective Shield [13754] @L350; Relentless Avenger [13755] @L350; Mithral Skin [13756] @L350; Reflective Shield [13757] @L350; Mithral Skin [13758] @L350

## 15. Ellywick (hero_id=83)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** All That Sparkles (15233)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** Faster Tempo
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: For The Fans [15231] @L200; Faster Tempo [15232] @L200; All That Sparkles [15233] @L200

## 16. Prudence (hero_id=84)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Eldritch Torrent (6072)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** DPS route / alt: Utility route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Als ze carry is, kies pure damage/scaling; anders meestal niet prioriteit.
- **Available options:**
  - tier 0: Eldritch Torrent [6072] @L600; She Hungers [6073] @L600

## 17. Corazon (hero_id=85)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Distant Crewmates (6133)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Distant Crewmates [6133] @L220; Mage Hand [6134] @L220

## 18. Reya (hero_id=86)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Champions of Good (5459)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Tank/spec in survivability-content; support als frontline al sterk genoeg is.
- **Available options:**
  - tier 0: Champions of Good [5459] @L160; Champions of Law [5460] @L160

## 19. NERDS (hero_id=87)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Green Leader, Standing By (6148)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Orange Leader, Standing By [6146] @L270; Red Leader, Standing By [6147] @L270; Green Leader, Standing By [6148] @L270; Yellow Leader, Standing By [6149] @L270; Pink Leader, Standing By [6150] @L270; Purple Leader, Standing By [6151] @L270

## 20. Xerophon (hero_id=88)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** High Charisma (6842)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: High Strength [6838] @L20; Low Strength [6839] @L20
  - tier 1: High Dexterity [6840] @L50; Low Dexterity [6841] @L50
  - tier 2: High Constitution [6978] @L90; Low Constitution [6979] @L90
  - tier 3: High Intelligence [6976] @L130; Low Intelligence [6977] @L130
  - tier 4: High Wisdom [6980] @L170; Low Wisdom [6981] @L170
  - tier 5: High Charisma [6842] @L210; Low Charisma [6843] @L210
