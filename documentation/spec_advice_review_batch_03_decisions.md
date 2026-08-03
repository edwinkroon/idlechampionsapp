# Spec advice review — batch 03 decisions

Resolved under the safe_default / null / conditional_only rule.
Celeste/Calliope/Evelyn/Shandie/Krond/Makos/Tyril were already resolved earlier (not in this batch).

### Jamilah (hero_id=11)
- safe_default: Bruiser
- push_default: Bruiser
- farm_default: null
- conditionals:
  - when: setup explicitly needs Indomitable Might instead of damage → Indomitable Might
- csv_label_maps_to: Bruiser
- notes: Damage default when used; Indomitable Might only as explicit alternate.
- review_needed: false

### Arkhan (hero_id=12)
- safe_default: Usurped Power
- push_default: Usurped Power
- farm_default: null
- conditionals:
  - when: formation needs Bulk Up survivability instead of usurp DPS → Bulk Up
- csv_label_maps_to: Usurped Power
- notes: CSV Usurp wins over config Bulk Up as the stable universal usurp path.
- review_needed: false

### Drizzt (hero_id=18)
- safe_default: Drow Stalker
- push_default: Drow Stalker
- farm_default: null
- conditionals:
  - when: not using Drizzt as carry / need Companions support → Leader of the Companions
- csv_label_maps_to: Drow Stalker
- notes: DPS route maps to Drow Stalker when he is the carry.
- review_needed: false

### Barrowin (hero_id=19)
- safe_default: Booming Voice
- push_default: Booming Voice
- farm_default: null
- conditionals:
  - when: healing/sustain coverage clearly required → Greater Blessing
  - when: setup explicitly needs Hammer of the Law → Hammer of the Law
- csv_label_maps_to: null
- notes: Healing/Support route labels have no exact option names; keep Booming Voice as stable default.
- review_needed: false

### Birdsong (hero_id=21)
- safe_default: Concertino
- push_default: Concertino
- farm_default: null
- conditionals:
  - when: tier1 support role instead of carry DPS → Unison
  - when: tier1 Soprano path needed → Soprano
  - when: tier0 Theme of Valor → Theme of Valor
  - when: tier0 Theme of Consideration → Theme of Consideration
  - when: tier0 Theme of Deception → Theme of Deception
- csv_label_maps_to: null
- notes: Multi-tier; Concertino is the stable tier1 DPS default; themes/support stay conditional.
- review_needed: false

### Strix (hero_id=23)
- safe_default: Smelly Lunch
- push_default: Smelly Lunch
- farm_default: null
- conditionals:
  - when: stacking Power of Friendship → Olfactory Fatigue
  - when: many Tieflings in formation → Scent of Brimstone
- csv_label_maps_to: Smelly Lunch
- notes: Smelly Lunch is the universal default; Fatigue/Brimstone are situational.
- review_needed: false

### Nrakk (hero_id=24)
- safe_default: Githzerai Focus
- push_default: Githzerai Focus
- farm_default: null
- conditionals:
  - when: race/agility support interactions needed instead of Focus → Githzerai Agility
- csv_label_maps_to: null
- notes: Buff/Race labels unmapped; Focus remains the stable config default.
- review_needed: false

### Binwin (hero_id=27)
- safe_default: Tallest in Faerûn
- push_default: Tallest in Faerûn
- farm_default: null
- conditionals:
  - when: setup explicitly needs Overkill damage → Overkill
  - when: setup explicitly needs Dwarven Encouragement → Dwarven Encouragement
- csv_label_maps_to: null
- notes: Support route unmapped; Tallest in Faerûn is the stable utility default.
- review_needed: false

### Xander (hero_id=29)
- safe_default: Follow Closely
- push_default: Follow Closely
- farm_default: null
- conditionals:
  - when: setup explicitly needs Trying Extra Hard → Trying Extra Hard
- csv_label_maps_to: null
- notes: Support route unmapped; Follow Closely stays the stable default.
- review_needed: false

### Azaka (hero_id=30)
- safe_default: Resist the Curse
- push_default: Resist the Curse
- farm_default: null
- conditionals:
  - when: setup explicitly needs Lycanthrope Forever → Lycanthrope Forever
- csv_label_maps_to: null
- notes: Support route unmapped; Resist the Curse is the stable default.
- review_needed: false

### Ishi (hero_id=31)
- safe_default: Friend to the Familiar
- push_default: Friend to the Familiar
- farm_default: null
- conditionals:
  - when: formation needs Friend to the Feared → Friend to the Feared
  - when: formation needs Friend to the Exceptional → Friend to the Exceptional
- csv_label_maps_to: null
- notes: Support route unmapped; Familiar is the stable default unless formation needs another friend path.
- review_needed: false

### Wulfgar (hero_id=32)
- safe_default: Flag Bearer
- push_default: Flag Bearer
- farm_default: null
- conditionals:
  - when: setup needs Heavy Blows damage → Heavy Blows
  - when: setup needs Moradin's Will → Moradin's Will
- csv_label_maps_to: null
- notes: Support route unmapped; Flag Bearer is the stable default.
- review_needed: false

### Farideh (hero_id=33)
- safe_default: Daughters of Mehen
- push_default: Daughters of Mehen
- farm_default: null
- conditionals:
  - when: setup needs Fury of Asmodeus → Fury of Asmodeus
  - when: setup needs Pact with Lorcan → Pact with Lorcan
- csv_label_maps_to: null
- notes: No CSV source; keep config Daughters of Mehen as stable default.
- review_needed: false

### Vlahnya (hero_id=35)
- safe_default: Breaking Out Solo
- push_default: Breaking Out Solo
- farm_default: null
- conditionals:
  - when: setup explicitly needs Spy Network → Spy Network
- csv_label_maps_to: null
- notes: Support route unmapped; Breaking Out Solo is the stable default.
- review_needed: false

### Nerys (hero_id=37)
- safe_default: Kelemvor's Foe
- push_default: Kelemvor's Foe
- farm_default: null
- conditionals:
  - when: healing/sustain coverage required → Kelemvor's Heal
  - when: setup needs Kelemvor's Will → Kelemvor's Will
- csv_label_maps_to: null
- notes: No CSV source; Foe is the stable config default.
- review_needed: false

### K'thriss (hero_id=38)
- safe_default: Velvet Touch
- push_default: Velvet Touch
- farm_default: null
- conditionals:
  - when: formation leans on Ligotti's Minions scaling → Ligotti's Minions
  - when: formation leans on The Unknowable Ur → The Unknowable Ur
- csv_label_maps_to: null
- notes: Efficient Bookkeeping/Pain labels have no exact options; Velvet Touch stays safe default.
- review_needed: false

### Black Viper (hero_id=40)
- safe_default: Collector
- push_default: Collector
- farm_default: null
- conditionals:
  - when: setup explicitly needs Assassinate → Assassinate
- csv_label_maps_to: null
- notes: Support route unmapped; Collector is the stable default.
- review_needed: false

### Rosie (hero_id=41)
- safe_default: Busy Beestinger
- push_default: Busy Beestinger
- farm_default: null
- conditionals:
  - when: tier1 Grandma-Bod path needed → Grandma-Bod
  - when: tier1 Slower Decay path needed → Slower Decay
  - when: tier0 Matriarch → Matriarch
  - when: tier0 Familiar Friends → Familiar Friends
  - when: tier0 Grandmother Night → Grandmother Night
- csv_label_maps_to: null
- notes: Multi-tier; Busy Beestinger is the stable tier1 damage default.
- review_needed: false

### Aila (hero_id=42)
- safe_default: Stormbreaker
- push_default: Stormbreaker
- farm_default: null
- conditionals:
  - when: debuff path needed instead of tank Stormbreaker → Stormcaller
- csv_label_maps_to: null
- notes: Tank/Debuff labels unmapped; Stormbreaker is the stable tank default.
- review_needed: false

### Spurt (hero_id=43)
- safe_default: Adopted Family
- push_default: Adopted Family
- farm_default: null
- conditionals:
  - when: Kobold Family synergy required → Kobold Family
  - when: Centi-pult niche synergy required → Centi-pult
- csv_label_maps_to: null
- notes: Pack Tactics is not an option name; Adopted Family stays the strongest support default.
- review_needed: false
