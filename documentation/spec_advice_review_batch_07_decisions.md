# Spec advice review — batch 07 decisions

### Virgil (hero_id=115)
- safe_default: Mood: Anxious
- push_default: Mood: Anxious
- farm_default: Mood: Anxious
- conditionals:
  - when: specific speed need makes Mood: Relaxed better → Mood: Relaxed
  - when: specific durability need makes Mood: Determined better → Mood: Determined
- csv_label_maps_to: null
- notes: Mood: Anxious is the stable farm/push default; Relaxed/Determined only for speed/durability needs.
- review_needed: true

### Warduke (hero_id=116)
- safe_default: Chaos Reigns
- push_default: Chaos Reigns
- farm_default: null
- conditionals:
  - when: situational Mercenary for Hire evil/carry variant → Mercenary for Hire
  - when: situational League of Malevolence evil/carry variant → League of Malevolence
- csv_label_maps_to: null
- notes: Chaos Reigns is the stable default; Mercenary/League are situational evil/carry variants.
- review_needed: true

### Imoen (hero_id=117)
- safe_default: Aberration Slaying Arrows
- push_default: Aberration Slaying Arrows
- farm_default: null
- conditionals:
  - when: enemy-type-specific Beast Slaying Arrows → Beast Slaying Arrows
  - when: enemy-type-specific Dragon Slaying Arrows → Dragon Slaying Arrows
  - when: enemy-type-specific Monstrosity Slaying Arrows → Monstrosity Slaying Arrows
- csv_label_maps_to: null
- notes: Aberration arrows are the stable default; other arrow types only for enemy-type value.
- review_needed: true

### Fen (hero_id=118)
- safe_default: Curse of the Dhampir
- push_default: Curse of the Dhampir
- farm_default: null
- conditionals:
  - when: Shadows of the Underdark route explicitly better → Shadows of the Underdark
- csv_label_maps_to: null
- notes: Curse of the Dhampir is the stable default; Shadows only when explicitly better.
- review_needed: true

### Uriah (hero_id=119)
- safe_default: Book of Exalted Deeds
- push_default: Book of Exalted Deeds
- farm_default: null
- conditionals:
  - when: alternate alignment/utility path needs Book of Vile Darkness → Book of Vile Darkness
- csv_label_maps_to: null
- notes: Exalted Deeds is the stable default; Vile Darkness only for the alternate alignment path.
- review_needed: true

### Solaak (hero_id=120)
- safe_default: Confidant
- push_default: Confidant
- farm_default: null
- conditionals:
  - when: situational Unwavering → Unwavering
  - when: situational Emboldened → Emboldened
- csv_label_maps_to: null
- notes: Confidant is the stable default; Unwavering/Emboldened are situational only.
- review_needed: true

### Miria (hero_id=121)
- safe_default: Independent
- push_default: Independent
- farm_default: null
- conditionals:
  - when: situational Methodical utility → Methodical
  - when: situational Intellectual utility → Intellectual
- csv_label_maps_to: null
- notes: Independent is the stable default; Methodical/Intellectual are situational utility variants.
- review_needed: true

### Antrius (hero_id=122)
- safe_default: Bard College
- push_default: Bard College
- farm_default: null
- conditionals:
  - when: situational Truly Awful Stats → Truly Awful Stats
  - when: situational The "A" In Chaotic Is For Antrius → The "A" In Chaotic Is For Antrius
- csv_label_maps_to: null
- notes: Bard College is the stable default; Awful Stats/Chaotic Antrius are situational.
- review_needed: true

### Nixie (hero_id=123)
- safe_default: Anarchy Amplified
- push_default: Anarchy Amplified
- farm_default: null
- conditionals:
  - when: alternate setup clearly better → Infernal Impact
  - when: alternate setup clearly better → Flawed Force
- csv_label_maps_to: null
- notes: Anarchy Amplified is the stable default; Infernal/Flawed only when clearly better.
- review_needed: true

### Evandra (hero_id=124)
- safe_default: Carnival Crew
- push_default: Carnival Crew
- farm_default: null
- conditionals:
  - when: stronger force/support route better for the run → Fighting Force
  - when: setup prefers Powerful Allies instead → Powerful Allies
- csv_label_maps_to: Powerful Allies
- notes: Carnival Crew is safe; CSV maps Support→Powerful Allies; Fighting Force situational.
- review_needed: false

### BBEG (hero_id=125)
- safe_default: Min-Maxing
- push_default: Min-Maxing
- farm_default: null
- conditionals:
  - when: situational Powergaming control/support → Powergaming
  - when: situational Rules Lawyering control/support → Rules Lawyering
- csv_label_maps_to: Min-Maxing
- notes: Min-Maxing is the stable control default; Powergaming/Rules Lawyering are situational.
- review_needed: false

### Strongheart (hero_id=126)
- safe_default: Honorary Member
- push_default: Honorary Member
- farm_default: null
- conditionals:
  - when: situational A Righteous Event for progress/quest goals → A Righteous Event
  - when: setup prefers Valor's Call instead → Valor's Call
- csv_label_maps_to: Valor's Call
- notes: Honorary Member is safe; CSV maps Support→Valor's Call; Righteous Event situational.
- review_needed: true

### Vin Ursa (hero_id=127)
- safe_default: Friends in High Places
- push_default: Friends in High Places
- farm_default: null
- conditionals:
  - when: tier0 Front Deck positional → Front Deck
  - when: tier0 Rear Deck positional → Rear Deck
  - when: tier1 Friends in Low Places context → Friends in Low Places
  - when: tier1 Friends in Meh Places context → Friends in Meh Places
- csv_label_maps_to: null
- notes: Friends in High Places is the stable default; deck/Low/Meh Places are positional.
- review_needed: true

### Lae'zel (hero_id=128)
- safe_default: Battle Master
- push_default: Battle Master
- farm_default: Battle Master
- conditionals:
  - when: situational Champion → Champion
  - when: situational Eldritch Knight → Eldritch Knight
- csv_label_maps_to: null
- notes: Battle Master is the stable speed/support default; Champion/Eldritch Knight situational.
- review_needed: true

### Astarion (hero_id=129)
- safe_default: Arcane Trickster
- push_default: Arcane Trickster
- farm_default: null
- conditionals:
  - when: tier0 Outflank (Top) → Outflank (Top)
  - when: tier0 Outflank (Bottom) → Outflank (Bottom)
  - when: tier1 Thief → Thief
  - when: tier1 Assassin → Assassin
- csv_label_maps_to: Outflank (Top)
- notes: Arcane Trickster is safe; CSV maps Damage→Outflank Top; other tiers situational.
- review_needed: true

### Krux (hero_id=136)
- safe_default: Foe of Xaryxis
- push_default: Foe of Xaryxis
- farm_default: null
- conditionals:
  - when: situational Nautical Knockback → Nautical Knockback
  - when: situational Take the Helm → Take the Helm
- csv_label_maps_to: null
- notes: Foe of Xaryxis is the stable default; Knockback/Helm are situational.
- review_needed: false

### Certainty (hero_id=138)
- safe_default: Best And The Brightest
- push_default: Best And The Brightest
- farm_default: null
- conditionals:
  - when: alternate support route preferable → Smooth Negotiators
- csv_label_maps_to: null
- notes: Best And The Brightest is the stable default; Smooth Negotiators only when preferable.
- review_needed: true

### Thellora (hero_id=139)
- safe_default: Callessa's Blessed
- push_default: Callessa's Blessed
- farm_default: Callessa's Blessed
- conditionals:
  - when: survivability is the main need → Defender of the Meek
  - when: setup prefers Vanguard of the Quick instead → Vanguard of the Quick
- csv_label_maps_to: Vanguard of the Quick
- notes: Callessa's Blessed is safe; CSV maps Speed→Vanguard; Defender for survival.
- review_needed: true

### Jang Sao (hero_id=140)
- safe_default: Moon Collector
- push_default: Moon Collector
- farm_default: null
- conditionals:
  - when: tier0 Wisdom of the Ages → Wisdom of the Ages
  - when: tier0 Speed of Shooting Stars → Speed of Shooting Stars
  - when: tier1 Star Caller → Star Caller
  - when: tier1 Night Runner → Night Runner
- csv_label_maps_to: null
- notes: Moon Collector is the stable tier1 default; other tier0/tier1 picks are situational.
- review_needed: true

### Shadowheart (hero_id=141)
- safe_default: Find Yourself
- push_default: Find Yourself
- farm_default: null
- conditionals:
  - when: situational Guidance → Guidance
  - when: situational Sister of Darkness → Sister of Darkness
- csv_label_maps_to: null
- notes: Find Yourself is the stable default; Guidance/Sister situational; handler context-sensitive.
- review_needed: true
