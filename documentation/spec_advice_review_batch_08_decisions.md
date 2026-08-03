# Spec advice review — batch 08 decisions

### Wyll (hero_id=142)
- safe_default: Pact of the Blade
- push_default: Pact of the Blade
- farm_default: null
- conditionals:
  - when: situational Pact of the Chain → Pact of the Chain
  - when: situational Pact of the Tome → Pact of the Tome
- csv_label_maps_to: null
- notes: Pact of the Blade is the stable default; Chain/Tome are situational pact choices.
- review_needed: true

### Karlach (hero_id=143)
- safe_default: Berserker
- push_default: Berserker
- farm_default: null
- conditionals:
  - when: situational Wildheart route → Wildheart
  - when: situational Wild Magic route → Wild Magic
- csv_label_maps_to: null
- notes: Berserker is the stable default; Wildheart/Wild Magic are situational routes.
- review_needed: true

### Presto (hero_id=144)
- safe_default: Humble Heroes
- push_default: Humble Heroes
- farm_default: null
- conditionals:
  - when: situational Junior Juggernauts → Junior Juggernauts
  - when: situational Magical Mastery → Magical Mastery
- csv_label_maps_to: null
- notes: Humble Heroes is the stable default; Juggernauts/Magical Mastery are situational.
- review_needed: true

### Dynaheir (hero_id=145)
- safe_default: Circle Magic
- push_default: Circle Magic
- farm_default: null
- conditionals:
  - when: situational Iron Lord's Justice support/DPS → Iron Lord's Justice
  - when: situational Loyal Bodyguard support/DPS → Loyal Bodyguard
- csv_label_maps_to: null
- notes: Circle Magic is the stable default; Justice/Bodyguard are situational support/DPS variants.
- review_needed: true

### Dark Urge (hero_id=146)
- safe_default: Divine Soul
- push_default: Divine Soul
- farm_default: null
- conditionals:
  - when: tier0 Storm Sorcery alternative → Storm Sorcery
  - when: tier0 Draconic Bloodline alternative → Draconic Bloodline
  - when: tier1 Embrace the Urge → Embrace the Urge
  - when: tier1 Resist the Urge → Resist the Urge
- csv_label_maps_to: null
- notes: Divine Soul is the stable tier0 default; Urge picks stay split on tier1.
- review_needed: true

### Gale (hero_id=147)
- safe_default: Ceremorphosis
- push_default: Ceremorphosis
- farm_default: null
- conditionals:
  - when: tier0 Evocation contextual → Evocation
  - when: tier0 Abjuration contextual → Abjuration
  - when: tier0 Enchantment contextual → Enchantment
  - when: tier0 Illusion contextual → Illusion
  - when: tier1 Mystical Mentor contextual → Mystical Mentor
  - when: tier1 Finite Fellowship contextual → Finite Fellowship
- csv_label_maps_to: Mystical Mentor
- notes: Ceremorphosis is safe; CSV maps Support→Mystical Mentor; schools stay contextual.
- review_needed: true

### Diana (hero_id=148)
- safe_default: Ensemble Cast
- push_default: Ensemble Cast
- farm_default: null
- conditionals:
  - when: tier0 Inspire: Acrobatic Assault → Inspire: Acrobatic Assault
  - when: tier0 Inspire: Modest Might → Inspire: Modest Might
  - when: tier0 Inspire: Fledgling Fury → Inspire: Fledgling Fury
  - when: tier1 Spotlight Episode situational → Spotlight Episode
- csv_label_maps_to: null
- notes: Ensemble Cast is the stable default; all inspire options and Spotlight are situational.
- review_needed: true

### Aeon (hero_id=150)
- safe_default: Play the Long Game
- push_default: Play the Long Game
- farm_default: null
- conditionals:
  - when: run plan needs Immediate Infiltration → Immediate Infiltration
  - when: tier1 Artificer's Arsenal by run plan → Artificer's Arsenal
  - when: tier1 Spy Network by run plan → Spy Network
  - when: tier1 Powerful Patronage by run plan → Powerful Patronage
- csv_label_maps_to: null
- notes: Play the Long Game is the stable default; Infiltration/tier1 picks by run plan.
- review_needed: true

### Umberto (hero_id=151)
- safe_default: Family of Orphans
- push_default: Family of Orphans
- farm_default: null
- conditionals:
  - when: tier0 Law's Alliance → Law's Alliance
  - when: tier0 Call of the Wardens → Call of the Wardens
  - when: clear offensive alternative → More Damage
  - when: tier1 More Bees situational → More Bees
  - when: tier1 More Clues situational → More Clues
- csv_label_maps_to: null
- notes: Family of Orphans is the stable default; More Damage is the clear offensive alt.
- review_needed: true

### Bobby (hero_id=152)
- safe_default: Group Charge
- push_default: Group Charge
- farm_default: null
- conditionals:
  - when: tier0 Stunning Strength → Stunning Strength
  - when: tier1 Not So Low by progression needs → Not So Low
  - when: tier1 Still Growing Up by progression needs → Still Growing Up
  - when: tier1 Strong Armed by progression needs → Strong Armed
- csv_label_maps_to: null
- notes: Group Charge is the stable default; tier1 picks by progression needs.
- review_needed: true

### Minthara (hero_id=154)
- safe_default: Soul Destroyer
- push_default: Soul Destroyer
- farm_default: null
- conditionals:
  - when: situational House Matron → House Matron
  - when: situational True Soul → True Soul
- csv_label_maps_to: null
- notes: Soul Destroyer is the stable default; House Matron/True Soul are situational.
- review_needed: true

### Wren (hero_id=155)
- safe_default: Glitch Form: Dwarf Monk
- push_default: Glitch Form: Dwarf Monk
- farm_default: null
- conditionals:
  - when: situational Glitch Form: Tabaxi Barbarian → Glitch Form: Tabaxi Barbarian
  - when: situational Glitch Form: Warforged Sorcerer → Glitch Form: Warforged Sorcerer
- csv_label_maps_to: null
- notes: Dwarf Monk is the stable glitch form; Tabaxi/Warforged are situational forms.
- review_needed: true

### Halsin (hero_id=156)
- safe_default: Harbinger of the Wilds
- push_default: Harbinger of the Wilds
- farm_default: null
- conditionals:
  - when: situational Sage of the Transformed → Sage of the Transformed
  - when: situational Protector of the Grove → Protector of the Grove
- csv_label_maps_to: null
- notes: Harbinger of the Wilds is the stable default; Sage/Protector are situational.
- review_needed: false

### Eric (hero_id=157)
- safe_default: Trait: Brave
- push_default: Trait: Brave
- farm_default: null
- conditionals:
  - when: tier0 Trait: Cautious contextual → Trait: Cautious
  - when: tier0 Trait: Sarcastic contextual → Trait: Sarcastic
  - when: tier1 Unassuming Force contextual → Unassuming Force
  - when: tier1 Youthful Valor contextual → Youthful Valor
  - when: tier1 Treasure Hunters contextual → Treasure Hunters
- csv_label_maps_to: null
- notes: Trait: Brave is the stable default; other traits and tier1 picks are contextual.
- review_needed: true

### Kalix (hero_id=158)
- safe_default: Creative Camouflage
- push_default: Creative Camouflage
- farm_default: null
- conditionals:
  - when: situational Strength in Numbers → Strength in Numbers
  - when: situational One For You, One For Me → One For You, One For Me
- csv_label_maps_to: null
- notes: Creative Camouflage is the stable default; Numbers/One For You are situational.
- review_needed: false

### Volo (hero_id=159)
- safe_default: Volo's Guide to All Things Magical
- push_default: Volo's Guide to All Things Magical
- farm_default: null
- conditionals:
  - when: contextual Volo's Guide to Spirits and Specters → Volo's Guide to Spirits and Specters
  - when: contextual Volo's Guide to Brain-Eating Tadpoles → Volo's Guide to Brain-Eating Tadpoles
- csv_label_maps_to: null
- notes: All Things Magical is the stable default; the other two guides stay conditional.
- review_needed: true

### Sheila (hero_id=160)
- safe_default: A Rosy Outlook
- push_default: A Rosy Outlook
- farm_default: null
- conditionals:
  - when: tier0 Meekly Meeting → Meekly Meeting
  - when: tier0 Youthful Allies → Youthful Allies
  - when: tier1 Frightening Strike situational → Frightening Strike
  - when: tier1 Enraging Strike situational → Enraging Strike
  - when: tier1 Confusing Strike situational → Confusing Strike
- csv_label_maps_to: null
- notes: A Rosy Outlook is the stable default; tier1 strike options are situational.
- review_needed: true

### Grimm (hero_id=161)
- safe_default: Giant Hunter
- push_default: Giant Hunter
- farm_default: null
- conditionals:
  - when: situational Giant Taunter → Giant Taunter
  - when: situational Giant Profits → Giant Profits
- csv_label_maps_to: null
- notes: Giant Hunter is the stable default; Taunter/Profits are situational variants.
- review_needed: false

### Vlithryn (hero_id=162)
- safe_default: Help the Unfortunate
- push_default: Help the Unfortunate
- farm_default: null
- conditionals:
  - when: contextual Who Else Would Save Them? → Who Else Would Save Them?
  - when: contextual Spreading the Word → Spreading the Word
- csv_label_maps_to: null
- notes: Help the Unfortunate is the stable default; the other options are contextual.
- review_needed: true

### Hank (hero_id=163)
- safe_default: Tactical Advantage
- push_default: Tactical Advantage
- farm_default: null
- conditionals:
  - when: tier0 Heart of Heroes → Heart of Heroes
  - when: tier0 Arrow Alliance → Arrow Alliance
  - when: tier0 Unyielding Unity → Unyielding Unity
  - when: tier1 Dragon Slayer → Dragon Slayer
- csv_label_maps_to: null
- notes: Tactical Advantage is the stable tier1 default; other tier picks are situational.
- review_needed: true
