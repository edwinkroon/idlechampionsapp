# Idle Champions specialization advice review (remaining batch 4, heroes 1-20 of 114)

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

## 1. Qillek (hero_id=44)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Empowered Blessing (8772)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Empowered Blessing / alt: Other route
- **CSV label maps to:** Empowered Blessing
- **CSV advice text:** Gebruik meestal healing/support; alternatief alleen als offense belangrijker is.
- **Available options:**
  - tier 0: Expanded Blessing [8771] @L250; Empowered Blessing [8772] @L250; Seized Assets [8773] @L250

## 2. Korth (hero_id=45)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Samurai Training (Behind) (13041)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Rapid Training / alt: Group Tactics
- **CSV label maps to:** Samurai Training (Behind)
- **CSV advice text:** Pak de spec die je carry het beste bufft; vaak afhankelijk van adjacency/attack cadence.
- **Available options:**
  - tier 0: Samurai Training (Behind) [13041] @L200; Samurai Training (In Front) [13042] @L200; Samurai Training (Beside) [13043] @L200

## 3. Walnut (hero_id=46)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Ah, Screw It (19714)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Extended Warranty [19712] @L180; Sign and Date [19713] @L180; Ah, Screw It [19714] @L180
  - tier 1: Co-Signers [19715] @L310; Temporary Alliance [19716] @L310

## 4. Jim (hero_id=48)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Darkmagic Cheer Squad (12132)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Magic magic magic / alt: Other route
- **CSV label maps to:** Magic {magic}#CCC {magic}#888 {magic}#444
- **CSV advice text:** Kies utility/damage afhankelijk van gebruik; vaak niche en setup-afhankelijk.
- **Available options:**
  - tier 0: Darkmagic Cheer Squad [12132] @L160; Magic {magic}#CCC {magic}#888 {magic}#444 [12133] @L160; Unpaid Extras [12134] @L160

## 5. Turiel (hero_id=49)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Voice of Authority (10664)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Frontline / alt: Control
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Tank/spec voor survivability; control als enemies positioning relevant is.
- **Available options:**
  - tier 0: Voice of Resilience [10663] @L300; Voice of Authority [10664] @L300

## 6. Pwent (hero_id=50)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Recruiting Drive (11496)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: DPS route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Vrijwel altijd support tenzij je een vreemde niche comp draait.
- **Available options:**
  - tier 0: Recruiting Drive [11496] @L200; Scents of Mithral Hall [11497] @L200; Critical Wound [11498] @L200

## 7. Avren (hero_id=51)

- **Sample reason:** multi_tier
- **Risk tags:** multi_tier
- **Our default advice:** Empowered Mirrors (3099)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Good/Sturdy mirror path / alt: Other mirror path
- **CSV label maps to:** Mirror Focus (Good)
- **CSV advice text:** Kies de mirror/spec die op jouw dps en alignment setup de beste mirrors geeft.
- **Available options:**
  - tier 0: Mirror Focus (Good) [3095] @L100; Mirror Focus (Neutral) [3096] @L100; Mirror Focus (Evil) [3097] @L100
  - tier 1: Sturdy Mirrors [3098] @L200; Empowered Mirrors [3099] @L200

## 8. Sentry (hero_id=52)

- **Sample reason:** farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Nature's Wrath (8866)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Tank route
- **CSV label maps to:** Nature's Wrath
- **CSV advice text:** Speed voor farming; tank/survival voor moeilijke content.
- **Available options:**
  - tier 0: Dedicated Guardian [8763] @L225; Nature's Wrath [8866] @L225; Sentry's Homeland [8867] @L225

## 9. Krull (hero_id=53)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Plague Focus: {Pain}#F00 (3215)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Pain / alt: Traitor
- **CSV label maps to:** Plague Focus: {Pain}#F00
- **CSV advice text:** Meestal de debuff/spec die het meeste BUD/push oplevert in je setup.
- **Available options:**
  - tier 0: Plague Focus: {Pilfer}#0F0 [3214] @L180; Plague Focus: {Pain}#F00 [3215] @L180; Plague Focus: {Traitor}#F0F [3216] @L180

## 10. Artemis (hero_id=54)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Observance: Foe (3270)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Observe / alt: Other scaling
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies altijd de spec die zijn observe/scaling maximaliseert binnen je setup.
- **Available options:**
  - tier 0: Observance: Friend [3269] @L400; Observance: Foe [3270] @L400

## 11. Havilar (hero_id=56)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Dembo (18043)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Imp route / alt: Tank route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies op basis van utility vs survivability.
- **Available options:**
  - tier 0: Dembo [18043] @L150; Olla [18044] @L150; Bosh [18045] @L150

## 12. Sisaspia (hero_id=57)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Fungal Body (13255)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Spores / alt: Healing
- **CSV label maps to:** Spreading Spores
- **CSV advice text:** Healing/spec voor veilige progressie; support als overleven al stabiel is.
- **Available options:**
  - tier 0: Simple Infection [13253] @L220; Spreading Spores [13254] @L220; Fungal Body [13255] @L220

## 13. Briv (hero_id=58)

- **Sample reason:** farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Go With The Phlo (3457)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Tank route
- **CSV label maps to:** Go With The Phlo
- **CSV advice text:** Speed/jump voor gem farm en snelle clears; tank als je hem echt nodig hebt om te overleven.
- **Available options:**
  - tier 0: Metalborn [3455] @L170; Tempered Steel [3456] @L170; Go With The Phlo [3457] @L170

## 14. Melf (hero_id=59)

- **Sample reason:** multi_tier, farm_gold
- **Risk tags:** multi_tier, farm_gold
- **Our default advice:** Melf's Speedy Spawns (19340), Melf's Abundant Allies (19342)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Speed route / alt: Push route
- **CSV label maps to:** Melf's Speedy Spawns
- **CSV advice text:** Speed bij farm; push-support bij diepere runs.
- **Available options:**
  - tier 0: Melf's Frequent Foes [19339] @L110; Melf's Speedy Spawns [19340] @L110; Melf's Doubled Drops [19341] @L110
  - tier 1: Melf's Abundant Allies [19342] @L140; Melf's Adaptive Attacks [19343] @L140; Melf's Ranked Roles [19344] @L140; Melf's Amorphous Alignment [19345] @L140

## 15. Krydle (hero_id=60)

- **Sample reason:** baseline
- **Risk tags:** baseline
- **Our default advice:** Keep Your Friends Close (9634)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **Available options:**
  - tier 0: Keep Your Friends Close [9634] @L400; Keep Your Enemies Closer [9635] @L400

## 16. Jaheira (hero_id=61)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Class Act - Spellslingers (9714), Hunter - Nature (9718)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Class Act - Spellslingers [9714] @L30; Class Act - Bruisers [9715] @L30; Class Act - Hybrids [9716] @L30; Class Act - Baldur's Gate [9717] @L30
  - tier 1: Hunter - Nature [9718] @L180; Hunter - Twisted Creatures [9719] @L180; Hunter - Civilization [9720] @L180; Hunter - Soulless [9721] @L180

## 17. Nova (hero_id=62)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Tight Knit (8754)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Tankier route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Meestal support/scaling voor push; tankier alternatief als nodig.
- **Available options:**
  - tier 0: New Recruits [8753] @L300; Tight Knit [8754] @L300

## 18. Freely (hero_id=63)

- **Sample reason:** farm_gold
- **Risk tags:** farm_gold
- **Our default advice:** Always Expect Chaos (4043)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Law/Chaos etc. / alt: Alignment route
- **CSV label maps to:** Trust in Law
- **CSV advice text:** Kies de alignment/spec die je team het beste dekt; vaak voor favor/gold setups.
- **Available options:**
  - tier 0: Trust in Law [4041] @L100; Value Neutrality [4042] @L100; Always Expect Chaos [4043] @L100

## 19. Lazaapz (hero_id=66)

- **Sample reason:** multi_tier, unmapped_label
- **Risk tags:** multi_tier, unmapped_label
- **Our default advice:** Fury of the Brawl (17484), Guardian (17487)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Support route / alt: Other route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Gebruik meestal de support- of utility-keuze als veilige default; wijk alleen af als de formatie, run-doel of champion-rol daar duidelijk om vraagt.
- **Available options:**
  - tier 0: Fury of the Brawl [17484] @L90; Fury of the Cabal [17485] @L90; Fury of the Stall [17486] @L90
  - tier 1: Guardian [17487] @L160; Infiltrator [17488] @L160

## 20. Dragonbait (hero_id=67)

- **Sample reason:** unmapped_label
- **Risk tags:** unmapped_label
- **Our default advice:** Scent: Herbs and Spices (3278)
- **Gaarawarr guide specs:** (none)
- **Dynamic formation handler:** no
- **CSV rule label:** Tank route / alt: Support route
- **CSV label maps to:** (unmapped)
- **CSV advice text:** Kies tank/survival wanneer je frontlinie onder druk staat; anders de support-optie.
- **Available options:**
  - tier 0: Scent: Roasted Chicken [3277] @L120; Scent: Herbs and Spices [3278] @L120
