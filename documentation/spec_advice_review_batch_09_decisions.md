# Spec advice review — batch 09 decisions (final remaining)

### Tess (hero_id=164)
- safe_default: The Fallback Plan
- push_default: The Fallback Plan
- farm_default: null
- conditionals:
  - when: situational Eyes on the Horizon → Eyes on the Horizon
  - when: situational Rogues' Gallery → Rogues' Gallery
- csv_label_maps_to: null
- notes: The Fallback Plan is the stable default; Horizon/Rogues' Gallery are situational.
- review_needed: true

### Baldric (hero_id=165)
- safe_default: Bargain With Eldath
- push_default: Bargain With Eldath
- farm_default: null
- conditionals:
  - when: tier0 Bargain With Tyr → Bargain With Tyr
  - when: tier0 Bargain With Moradin → Bargain With Moradin
  - when: tier0 Bargain With Tymora → Bargain With Tymora
  - when: tier0 Bargain With Mystra → Bargain With Mystra
  - when: tier1 Dark Bargain → Dark Bargain
  - when: tier1 other Bargain deity/path → Bargain With Moradin
- csv_label_maps_to: null
- notes: Bargain With Eldath is the only universal default; other Bargains/Dark Bargain stay conditional.
- review_needed: true

### Cazrin (hero_id=166)
- safe_default: Ancestor's Shadow
- push_default: Ancestor's Shadow
- farm_default: null
- conditionals:
  - when: tier0 Self Taught → Self Taught
  - when: situational Lost in the Library → Lost in the Library
  - when: tier1 smell/mastery route intended → Smell Mastery
  - when: tier1 Signature Smell instead → Signature Smell
- csv_label_maps_to: null
- notes: Ancestor's Shadow is the stable default; Smell Mastery only if that route is intended.
- review_needed: true

### Windfall (hero_id=167)
- safe_default: Black Dragon's Corrosion
- push_default: Black Dragon's Corrosion
- farm_default: null
- conditionals:
  - when: situational Red Dragon's Greed → Red Dragon's Greed
  - when: situational Blue Dragon's Spark → Blue Dragon's Spark
  - when: situational Green Dragon's Spite → Green Dragon's Spite
  - when: situational White Dragon's Chill → White Dragon's Chill
- csv_label_maps_to: null
- notes: Black Dragon's Corrosion is the stable default; other dragon colors stay conditional.
- review_needed: false

### King of Shadows (hero_id=168)
- safe_default: Embrace the Shadow Weave
- push_default: Embrace the Shadow Weave
- farm_default: null
- conditionals:
  - when: tier0 Master of Pawns contextual → Master of Pawns
  - when: tier0 Shadow Unleashed contextual → Shadow Unleashed
  - when: tier1 Legacy of Illefarn contextual → Legacy of Illefarn
  - when: tier1 Rites of Survival contextual → Rites of Survival
- csv_label_maps_to: null
- notes: Embrace the Shadow Weave is the stable default; other shadow options are contextual.
- review_needed: true

### Skylla (hero_id=169)
- safe_default: Withering Ward
- push_default: Withering Ward
- farm_default: null
- conditionals:
  - when: situational Witch's Switch → Witch's Switch
  - when: situational League of Malevolence → League of Malevolence
  - when: tier1 Green Fire situational → Green Fire
  - when: tier1 Blue Fire situational → Blue Fire
  - when: tier1 Violet Fire situational → Violet Fire
- csv_label_maps_to: null
- notes: Withering Ward is the stable default; Switch/League/fire options are situational.
- review_needed: true

### Lark (hero_id=170)
- safe_default: Band of Misfits
- push_default: Band of Misfits
- farm_default: null
- conditionals:
  - when: situational Center of Attention → Center of Attention
  - when: situational Path of Nightmares → Path of Nightmares
- csv_label_maps_to: null
- notes: Band of Misfits is the stable default; Attention/Nightmares are situational.
- review_needed: false

### Anson (hero_id=171)
- safe_default: Found Family
- push_default: Found Family
- farm_default: null
- conditionals:
  - when: situational Pure of Heart → Pure of Heart
  - when: situational Never Surrender → Never Surrender
- csv_label_maps_to: null
- notes: Found Family is the stable default; Pure of Heart/Never Surrender are situational.
- review_needed: false

### Kyre (hero_id=172)
- safe_default: Complete Control
- push_default: Complete Control
- farm_default: null
- conditionals:
  - when: situational Faster Than Light → Faster Than Light
  - when: situational Pure of Soul → Pure of Soul
- csv_label_maps_to: null
- notes: Complete Control is the stable default; Faster Than Light/Pure of Soul are situational.
- review_needed: false

### Raistlin (hero_id=173)
- safe_default: Heroic Mage
- push_default: Heroic Mage
- farm_default: null
- conditionals:
  - when: situational Reclusive Mage → Reclusive Mage
  - when: situational War Mage → War Mage
- csv_label_maps_to: null
- notes: Heroic Mage is the stable default; Reclusive/War Mage are situational.
- review_needed: true

### Tasslehoff (hero_id=174)
- safe_default: Fast Friends
- push_default: Fast Friends
- farm_default: null
- conditionals:
  - when: tier0 Map Collector: Pre-Cataclysm → Map Collector: Pre-Cataclysm
  - when: tier0 Map Collector: Time of Darkness → Map Collector: Time of Darkness
  - when: tier0 Map Collector: War of the Lance → Map Collector: War of the Lance
  - when: tier1 Small Friends situational → Small Friends
  - when: tier1 Old Friends situational → Old Friends
- csv_label_maps_to: null
- notes: Fast Friends is the stable default; map collectors and Small/Old Friends are situational.
- review_needed: true

### Laurana (hero_id=175)
- safe_default: Battle Plan: Charge
- push_default: Battle Plan: Charge
- farm_default: null
- conditionals:
  - when: tier0 Battle Plan: Outflank → Battle Plan: Outflank
  - when: tier0 Battle Plan: Fortify → Battle Plan: Fortify
  - when: tier1 Lead the Attack → Lead the Attack
  - when: tier1 Protect the Vulnerable → Protect the Vulnerable
  - when: tier1 Wield the Dragonlance → Wield the Dragonlance
- csv_label_maps_to: null
- notes: Battle Plan: Charge is the stable default; other plans and tier1 picks are situational.
- review_needed: true

### Trixie (hero_id=176)
- safe_default: Faster, Friends
- push_default: Faster, Friends
- farm_default: Faster, Friends
- conditionals:
  - when: situational Ultimate Friends → Ultimate Friends
- csv_label_maps_to: null
- notes: Faster, Friends is the stable default; Ultimate Friends is situational.
- review_needed: false

### Van Richten (hero_id=177)
- safe_default: Endless Hunt
- push_default: Endless Hunt
- farm_default: null
- conditionals:
  - when: contextual Occult Allies → Occult Allies
  - when: contextual Scholar of Dread → Scholar of Dread
  - when: tier1 Occult Aid: Cure Wounds → Occult Aid: Cure Wounds
  - when: tier1 Occult Aid: Dispel Evil → Occult Aid: Dispel Evil
  - when: tier1 Occult Aid: Sanctuary → Occult Aid: Sanctuary
- csv_label_maps_to: null
- notes: Endless Hunt is the stable default; Allies/Scholar and Occult Aid picks are contextual.
- review_needed: true
