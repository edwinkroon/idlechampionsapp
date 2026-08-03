# Spec advice review — batch 04 decisions

User-recommended decisions applied under the safe_default / null / conditional_only rule.

### Qillek (hero_id=44)
- safe_default: Empowered Blessing
- push_default: Empowered Blessing
- farm_default: null
- conditionals:
  - when: offense more important than healing/support → Expanded Blessing
  - when: setup explicitly needs Seized Assets → Seized Assets
- csv_label_maps_to: Empowered Blessing
- notes: Healing/support default; Expanded Blessing/Seized Assets only as explicit alternates.
- review_needed: false

### Korth (hero_id=45)
- safe_default: Samurai Training (Behind)
- push_default: Samurai Training (Behind)
- farm_default: null
- conditionals:
  - when: carry adjacency needs In Front → Samurai Training (In Front)
  - when: carry adjacency needs Beside → Samurai Training (Beside)
- csv_label_maps_to: Samurai Training (Behind)
- notes: Behind is the stable default; In Front/Beside depend on adjacency/carry setup.
- review_needed: false

### Walnut (hero_id=46)
- safe_default: Ah, Screw It
- push_default: Ah, Screw It
- farm_default: null
- conditionals:
  - when: tier0 Extended Warranty needed → Extended Warranty
  - when: tier0 Sign and Date needed → Sign and Date
  - when: tier1 Co-Signers support → Co-Signers
  - when: tier1 Temporary Alliance support → Temporary Alliance
- csv_label_maps_to: null
- notes: Tier0 Ah, Screw It is the universal default; tier1 are conditional support variants.
- review_needed: false

### Jim (hero_id=48)
- safe_default: Darkmagic Cheer Squad
- push_default: Darkmagic Cheer Squad
- farm_default: null
- conditionals:
  - when: setup really benefits from the magic-themed option → Magic {magic}#CCC {magic}#888 {magic}#444
  - when: setup explicitly needs Unpaid Extras → Unpaid Extras
- csv_label_maps_to: Darkmagic Cheer Squad
- notes: Darkmagic Cheer Squad is the stable default; magic-themed option only if the setup benefits.
- review_needed: false

### Turiel (hero_id=49)
- safe_default: Voice of Authority
- push_default: Voice of Authority
- farm_default: null
- conditionals:
  - when: frontline/survivability needs Voice of Resilience → Voice of Resilience
- csv_label_maps_to: null
- notes: Authority is the stable default; Resilience only for frontline survivability.
- review_needed: false

### Pwent (hero_id=50)
- safe_default: Recruiting Drive
- push_default: Recruiting Drive
- farm_default: null
- conditionals:
  - when: niche DPS/comp needs Critical Wound → Critical Wound
  - when: setup needs Scents of Mithral Hall → Scents of Mithral Hall
- csv_label_maps_to: null
- notes: Support default Recruiting Drive; alternatives only for niche comps.
- review_needed: false

### Avren (hero_id=51)
- safe_default: Empowered Mirrors
- push_default: Empowered Mirrors
- farm_default: null
- conditionals:
  - when: tier0 Good mirror path → Mirror Focus (Good)
  - when: tier0 Neutral mirror path → Mirror Focus (Neutral)
  - when: tier0 Evil mirror path → Mirror Focus (Evil)
  - when: tier1 Sturdy Mirrors needed instead of Empowered → Sturdy Mirrors
- csv_label_maps_to: Empowered Mirrors
- notes: Tier1 Empowered Mirrors is the stable universal default; tier0 mirrors are contextual.
- review_needed: false

### Sentry (hero_id=52)
- safe_default: Nature's Wrath
- push_default: null
- farm_default: Nature's Wrath
- conditionals:
  - when: tank/survival content needs Dedicated Guardian → Dedicated Guardian
  - when: setup needs Sentry's Homeland → Sentry's Homeland
- csv_label_maps_to: Nature's Wrath
- notes: Speed/farm default Nature's Wrath; Guardian only for hard survival content.
- review_needed: false

### Krull (hero_id=53)
- safe_default: Plague Focus: {Pain}#F00
- push_default: Plague Focus: {Pain}#F00
- farm_default: null
- conditionals:
  - when: setup needs Traitor plague focus → Plague Focus: {Traitor}#F0F
  - when: setup needs Pilfer plague focus → Plague Focus: {Pilfer}#0F0
- csv_label_maps_to: Plague Focus: {Pain}#F00
- notes: Pain is the stable plague focus; Traitor/Pilfer only when the setup needs them.
- review_needed: false

### Artemis (hero_id=54)
- safe_default: Observance: Foe
- push_default: Observance: Foe
- farm_default: null
- conditionals:
  - when: setup maximizes Observance: Friend scaling → Observance: Friend
- csv_label_maps_to: null
- notes: Observance: Foe is the stable default; Observe label has no exact option match.
- review_needed: false

### Havilar (hero_id=56)
- safe_default: Dembo
- push_default: Dembo
- farm_default: null
- conditionals:
  - when: specific comp needs Olla → Olla
  - when: specific comp needs Bosh → Bosh
- csv_label_maps_to: null
- notes: Dembo is the stable imp default; Olla/Bosh only for specific comps.
- review_needed: false

### Sisaspia (hero_id=57)
- safe_default: Fungal Body
- push_default: Fungal Body
- farm_default: null
- conditionals:
  - when: healing/sustain coverage required → Spreading Spores
  - when: setup needs Simple Infection → Simple Infection
- csv_label_maps_to: Fungal Body
- notes: Fungal Body wins as stable default; Spores/Infection when healing/sustain is needed.
- review_needed: false

### Briv (hero_id=58)
- safe_default: Go With The Phlo
- push_default: null
- farm_default: Go With The Phlo
- conditionals:
  - when: tank survivability needed → Tempered Steel
  - when: setup needs Metalborn → Metalborn
- csv_label_maps_to: Go With The Phlo
- notes: Speed route is the stable farm default; tank options only when survival is required.
- review_needed: false

### Melf (hero_id=59)
- safe_default: Melf's Speedy Spawns
- push_default: Melf's Abundant Allies
- farm_default: Melf's Speedy Spawns
- conditionals:
  - when: tier0 Frequent Foes needed → Melf's Frequent Foes
  - when: tier0 Doubled Drops needed → Melf's Doubled Drops
  - when: tier1 Adaptive Attacks needed → Melf's Adaptive Attacks
  - when: tier1 Ranked Roles needed → Melf's Ranked Roles
  - when: tier1 Amorphous Alignment needed → Melf's Amorphous Alignment
- csv_label_maps_to: Melf's Speedy Spawns
- notes: Speedy Spawns for farm; Abundant Allies for push; other tier0/tier1 are conditional.
- review_needed: false

### Krydle (hero_id=60)
- safe_default: Keep Your Friends Close
- push_default: Keep Your Friends Close
- farm_default: null
- conditionals:
  - when: setup explicitly needs Keep Your Enemies Closer → Keep Your Enemies Closer
- csv_label_maps_to: null
- notes: Friends Close is the stable default; no extra split needed.
- review_needed: false

### Jaheira (hero_id=61)
- safe_default: Class Act - Spellslingers
- push_default: Class Act - Spellslingers
- farm_default: null
- conditionals:
  - when: tier0 Class Act - Bruisers → Class Act - Bruisers
  - when: tier0 Class Act - Hybrids → Class Act - Hybrids
  - when: tier0 Class Act - Baldur's Gate → Class Act - Baldur's Gate
  - when: tier1 Hunter - Nature → Hunter - Nature
  - when: tier1 Hunter - Twisted Creatures → Hunter - Twisted Creatures
  - when: tier1 Hunter - Civilization → Hunter - Civilization
  - when: tier1 Hunter - Soulless → Hunter - Soulless
- csv_label_maps_to: null
- notes: Spellslingers is the stable tier0 default; hunter/nature picks are tier1 conditionals.
- review_needed: false

### Nova (hero_id=62)
- safe_default: Tight Knit
- push_default: Tight Knit
- farm_default: null
- conditionals:
  - when: tankier route needed → New Recruits
- csv_label_maps_to: null
- notes: Tight Knit is the stable support default; Support/Tankier labels stay unmapped.
- review_needed: false

### Freely (hero_id=63)
- safe_default: Always Expect Chaos
- push_default: null
- farm_default: Always Expect Chaos
- conditionals:
  - when: alignment setup needs Trust in Law → Trust in Law
  - when: alignment setup needs Value Neutrality → Value Neutrality
- csv_label_maps_to: null
- notes: Chaos is the stable universal default; Law/Neutral only when alignment coverage requires them.
- review_needed: false

### Lazaapz (hero_id=66)
- safe_default: Fury of the Brawl
- push_default: Fury of the Brawl
- farm_default: null
- conditionals:
  - when: tier0 Fury of the Cabal needed → Fury of the Cabal
  - when: tier0 Fury of the Stall needed → Fury of the Stall
  - when: tier1 Guardian path → Guardian
  - when: tier1 Infiltrator path → Infiltrator
- csv_label_maps_to: null
- notes: Fury of the Brawl is the stable tier0 default; Guardian vs Infiltrator are tier1 conditionals.
- review_needed: false

### Dragonbait (hero_id=67)
- safe_default: Scent: Herbs and Spices
- push_default: Scent: Herbs and Spices
- farm_default: null
- conditionals:
  - when: survivability/tank pressure requires Roasted Chicken → Scent: Roasted Chicken
- csv_label_maps_to: null
- notes: Herbs and Spices is the support default; Roasted Chicken only when survivability is the problem.
- review_needed: false
