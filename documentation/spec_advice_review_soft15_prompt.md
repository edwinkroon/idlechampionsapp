# Soft review batch — next 10 `review_needed` cases (soft15)

Copy everything below the line into Perplexity.

---

Je helpt een Idle Champions specialization-advisor verbeteren.

Gebruik ALLEEN option names en upgrade_ids uit "Available options".
Verzin geen specs.

Per champion moet je beslissen:
1. Blijft de huidige safe_default staan, of moet die wijzigen?
2. Moet csv_label_maps_to gelijk aan safe_default, of bewust anders (en waarom)?
3. Zijn de conditionals scherp genoeg, of moeten when-regels concreter?
4. Mag review_needed op false, of moet die true blijven?

Decision rule:
- safe_default = meest stabiele universele keuze
- null alleen als er echt geen universele default is
- alternatives = conditionals
- bij CSV vs config conflict: kies de stabiele universal als safe_default
- csv_label_maps_to bij voorkeur gelijk aan safe_default; alleen afwijken met expliciete reden
- unmapped labels: map naar safe_default als die label de universele route is; anders null tenzij exacte option name

Antwoord ALLEEN in dit formaat, voor elke champion:

### {name} (hero_id={id})
- safe_default: {exact option name} | null
- push_default: {name} | null
- farm_default: {name} | null
- conditionals:
  - when: ... → {option name}
- csv_label_maps_to: {name} | null
- notes: kort (max 1 zin)
- review_needed: true/false
- change_from_current: keep | change
- change_summary: max 1 zin wat er wijzigt t.o.v. current

Champions:

### Vin Ursa (hero_id=127)
- Current safe_default: Friends in High Places
- Current push_default: Friends in High Places
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; multi-tier positional
- Explanation: Safe Friends in High Places; deck/Low/Meh Places are positional conditionals.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Tier0 deck and tier1 Low/Meh Places are positional/context-based.
- Current conditionals:
  - when: tier0 Front Deck positional → Front Deck
  - when: tier0 Rear Deck positional → Rear Deck
  - when: tier1 Friends in Low Places context → Friends in Low Places
  - when: tier1 Friends in Meh Places context → Friends in Meh Places
- Available options:
  - tier 0: Front Deck [12090]; Rear Deck [12091]
  - tier 1: Friends in Low Places [12092]; Friends in Meh Places [12093]; Friends in High Places [12094]

### Lae'zel (hero_id=128)
- Current safe_default: Battle Master
- Current push_default: Battle Master
- Current farm_default: Battle Master
- Dynamic handler: no
- Review reasons: Speed/Support routes unmapped
- Explanation: Safe/farm/push Battle Master; Champion/Eldritch Knight are situational.
- csv_default_label: Speed route
- csv_label_maps_to: None
- csv_advice_text: Champion/Eldritch Knight situational; Battle Master is speed/support default.
- Current conditionals:
  - when: situational Champion → Champion
  - when: situational Eldritch Knight → Eldritch Knight
- Available options:
  - tier 0: Champion [12118]; Battle Master [12119]; Eldritch Knight [12120]

### Certainty (hero_id=138)
- Current safe_default: Best And The Brightest
- Current push_default: Best And The Brightest
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Best And The Brightest; Smooth Negotiators only when preferable.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Smooth Negotiators only when that alternate support route is preferable.
- Current conditionals:
  - when: alternate support route preferable → Smooth Negotiators → Smooth Negotiators
- Available options:
  - tier 0: Best And The Brightest [12510]; Smooth Negotiators [12511]

### Jang Sao (hero_id=140)
- Current safe_default: Moon Collector
- Current push_default: Moon Collector
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; recent multi-tier champ
- Explanation: Safe Moon Collector; other tier0/tier1 picks are situational.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Tier0 and other tier1 picks are tier-based situational choices.
- Current conditionals:
  - when: tier0 Wisdom of the Ages → Wisdom of the Ages
  - when: tier0 Speed of Shooting Stars → Speed of Shooting Stars
  - when: tier1 Star Caller → Star Caller
  - when: tier1 Night Runner → Night Runner
- Available options:
  - tier 0: Wisdom of the Ages [13261]; Speed of Shooting Stars [13262]
  - tier 1: Moon Collector [13263]; Star Caller [13264]; Night Runner [13265]

### Shadowheart (hero_id=141)
- Current safe_default: Find Yourself
- Current push_default: Find Yourself
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: Healing/Support unmapped; dynamic handler present
- Explanation: Safe Find Yourself; Guidance/Sister situational; handler context-sensitive.
- csv_default_label: Healing route
- csv_label_maps_to: None
- csv_advice_text: Guidance/Sister of Darkness situational; dynamic handler stays context-sensitive.
- Current conditionals:
  - when: situational Guidance → Guidance
  - when: situational Sister of Darkness → Sister of Darkness
- Available options:
  - tier 0: Guidance [13279]; Sister of Darkness [13280]; Find Yourself [13281]

### Wyll (hero_id=142)
- Current safe_default: Pact of the Blade
- Current push_default: Pact of the Blade
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: Support route unmapped; dynamic handler present
- Explanation: Safe Pact of the Blade; Chain/Tome are situational pact choices.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Pact of the Chain / Pact of the Tome are situational pact choices.
- Current conditionals:
  - when: situational Pact of the Chain → Pact of the Chain
  - when: situational Pact of the Tome → Pact of the Tome
- Available options:
  - tier 0: Pact of the Blade [13433]; Pact of the Chain [13434]; Pact of the Tome [13435]

### Karlach (hero_id=143)
- Current safe_default: Berserker
- Current push_default: Berserker
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: Support route unmapped; dynamic handler present
- Explanation: Safe Berserker; Wildheart/Wild Magic are situational routes.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Wildheart and Wild Magic are situational route choices.
- Current conditionals:
  - when: situational Wildheart route → Wildheart
  - when: situational Wild Magic route → Wild Magic
- Available options:
  - tier 0: Berserker [13726]; Wildheart [13727]; Wild Magic [13728]

### Presto (hero_id=144)
- Current safe_default: Humble Heroes
- Current push_default: Humble Heroes
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; recent champ
- Explanation: Safe Humble Heroes; Juggernauts/Magical Mastery are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Junior Juggernauts / Magical Mastery are situational alternatives.
- Current conditionals:
  - when: situational Junior Juggernauts → Junior Juggernauts
  - when: situational Magical Mastery → Magical Mastery
- Available options:
  - tier 0: Humble Heroes [13765]; Junior Juggernauts [13766]; Magical Mastery [13767]

### Dynaheir (hero_id=145)
- Current safe_default: Circle Magic
- Current push_default: Circle Magic
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/DPS routes unmapped
- Explanation: Safe Circle Magic; Justice/Bodyguard are situational support/DPS variants.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Iron Lord's Justice / Loyal Bodyguard are situational support/DPS variants.
- Current conditionals:
  - when: situational Iron Lord's Justice support/DPS → Iron Lord's Justice
  - when: situational Loyal Bodyguard support/DPS → Loyal Bodyguard
- Available options:
  - tier 0: Circle Magic [13879]; Iron Lord's Justice [13880]; Loyal Bodyguard [13881]

### Dark Urge (hero_id=146)
- Current safe_default: Divine Soul
- Current push_default: Divine Soul
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier Urge choice soft
- Explanation: Safe Divine Soul; tier0 Storm/Draconic and tier1 Urge picks are conditional.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Tier0 Storm/Draconic alternatives; tier1 Embrace vs Resist the Urge.
- Current conditionals:
  - when: tier0 Storm Sorcery alternative → Storm Sorcery
  - when: tier0 Draconic Bloodline alternative → Draconic Bloodline
  - when: tier1 Embrace the Urge → Embrace the Urge
  - when: tier1 Resist the Urge → Resist the Urge
- Available options:
  - tier 0: Storm Sorcery [14382]; Draconic Bloodline [14383]; Divine Soul [14384]
  - tier 1: Embrace the Urge [14385]; Resist the Urge [14386]
