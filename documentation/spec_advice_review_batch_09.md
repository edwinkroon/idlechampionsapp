# Idle Champions specialization advice review (remaining batch 9, heroes 1-14 of 14)

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

## 1. Tess (hero_id=164)

- **Sample reason:** dynamic_handler, recent
- **Risk tags:** dynamic_handler, recent
- **Our default advice:** The Fallback Plan (17321)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: The Fallback Plan [17321] @L150; Eyes on the Horizon [17322] @L150; Rogues' Gallery [17323] @L150

## 2. Baldric (hero_id=165)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Bargain With Eldath (17495)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Bargain With Tyr [17491] @L70; Bargain With Moradin [17492] @L70; Bargain With Tymora [17493] @L70; Bargain With Mystra [17494] @L70; Bargain With Eldath [17495] @L70
  - tier 1: Dark Bargain [17496] @L150; Bargain With Moradin [17497] @L150; Bargain With Tymora [17498] @L150; Bargain With Mystra [17499] @L150; Bargain With Eldath [17500] @L150; Bargain With Tyr [17501] @L150; Dark Bargain [17502] @L150; Bargain With Tymora [17503] @L150; Bargain With Mystra [17504] @L150; Bargain With Eldath [17505] @L150; Bargain With Tyr [17506] @L150; Bargain With Moradin [17507] @L150; Dark Bargain [17508] @L150; Bargain With Mystra [17509] @L150; Bargain With Eldath [17510] @L150; Bargain With Tyr [17511] @L150; Bargain With Moradin [17512] @L150; Bargain With Tymora [17513] @L150; Dark Bargain [17514] @L150; Bargain With Eldath [17515] @L150; Bargain With Tyr [17516] @L150; Bargain With Moradin [17517] @L150; Bargain With Tymora [17518] @L150; Bargain With Mystra [17519] @L150; Dark Bargain [17520] @L150

## 3. Cazrin (hero_id=166)

- **Sample reason:** dynamic_handler, multi_tier, recent
- **Risk tags:** dynamic_handler, multi_tier, recent
- **Our default advice:** Ancestor's Shadow (17679), Smell Mastery (17682)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Self Taught [17678] @L180; Ancestor's Shadow [17679] @L180; Lost in the Library [17680] @L180
  - tier 1: Signature Smell [17681] @L240; Smell Mastery [17682] @L240

## 4. Windfall (hero_id=167)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Black Dragon's Corrosion (17059)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Red Dragon's Greed [17056] @L100; Blue Dragon's Spark [17057] @L100; Green Dragon's Spite [17058] @L100; Black Dragon's Corrosion [17059] @L100; White Dragon's Chill [17060] @L100

## 5. King of Shadows (hero_id=168)

- **Sample reason:** dynamic_handler, multi_tier, recent
- **Risk tags:** dynamic_handler, multi_tier, recent
- **Our default advice:** Embrace the Shadow Weave (17765)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Master of Pawns [17762] @L210; Shadow Unleashed [17763] @L210
  - tier 1: Legacy of Illefarn [17764] @L280; Embrace the Shadow Weave [17765] @L280; Rites of Survival [17766] @L280

## 6. Skylla (hero_id=169)

- **Sample reason:** dynamic_handler, multi_tier, recent
- **Risk tags:** dynamic_handler, multi_tier, recent
- **Our default advice:** Withering Ward (17850)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Witch's Switch [17848] @L110; League of Malevolence [17849] @L110; Withering Ward [17850] @L110
  - tier 1: Green Fire [17851] @L200; Blue Fire [17852] @L200; Violet Fire [17853] @L200

## 7. Lark (hero_id=170)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Band of Misfits (18055)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Band of Misfits [18055] @L170; Center of Attention [18056] @L170; Path of Nightmares [18057] @L170

## 8. Anson (hero_id=171)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Found Family (18475)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Pure of Heart [18474] @L230; Found Family [18475] @L230; Never Surrender [18476] @L230

## 9. Kyre (hero_id=172)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Complete Control (18671)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Complete Control [18671] @L170; Faster Than Light [18672] @L170; Pure of Soul [18673] @L170

## 10. Raistlin (hero_id=173)

- **Sample reason:** dynamic_handler, recent
- **Risk tags:** dynamic_handler, recent
- **Our default advice:** Heroic Mage (18934)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Heroic Mage [18934] @L130; Reclusive Mage [18935] @L130; War Mage [18936] @L130

## 11. Tasslehoff (hero_id=174)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Fast Friends (19238)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Map Collector: Pre-Cataclysm [19240] @L20; Map Collector: Time of Darkness [19241] @L20; Map Collector: War of the Lance [19242] @L20
  - tier 1: Small Friends [19237] @L150; Fast Friends [19238] @L150; Old Friends [19239] @L150

## 12. Laurana (hero_id=175)

- **Sample reason:** multi_tier, recent
- **Risk tags:** multi_tier, recent
- **Our default advice:** Battle Plan: Charge (19354)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Battle Plan: Charge [19354] @L30; Battle Plan: Outflank [19355] @L30; Battle Plan: Fortify [19356] @L30
  - tier 1: Lead the Attack [19357] @L120; Protect the Vulnerable [19358] @L120; Wield the Dragonlance [19359] @L120

## 13. Trixie (hero_id=176)

- **Sample reason:** recent
- **Risk tags:** recent
- **Our default advice:** Faster, Friends (19692)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Faster, Friends [19692] @L160; Ultimate Friends [19693] @L160

## 14. Van Richten (hero_id=177)

- **Sample reason:** dynamic_handler, multi_tier, recent
- **Risk tags:** dynamic_handler, multi_tier, recent
- **Our default advice:** Endless Hunt (19702), Occult Aid: Dispel Evil (19704)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** yes
- **Available options:**
  - tier 0: Occult Allies [19700] @L120; Scholar of Dread [19701] @L120; Endless Hunt [19702] @L120
  - tier 1: Occult Aid: Cure Wounds [19703] @L220; Occult Aid: Dispel Evil [19704] @L220; Occult Aid: Sanctuary [19705] @L220
