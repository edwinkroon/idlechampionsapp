# Soft review batch — next 10 `review_needed` cases (soft12)

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

### Prudence (hero_id=84)
- Current safe_default: Eldritch Torrent
- Current push_default: Eldritch Torrent
- Current farm_default: null
- Dynamic handler: no
- Review reasons: DPS/Utility routes unmapped to exact option names
- Explanation: Safe Eldritch Torrent; She Hungers only for alternate scaling setups.
- csv_default_label: DPS route
- csv_label_maps_to: None
- csv_advice_text: She Hungers only when the setup benefits from that alternate scaling.
- Current conditionals:
  - when: setup benefits from alternate She Hungers scaling → She Hungers
- Available options:
  - tier 0: Eldritch Torrent [6072]; She Hungers [6073]

### Corazon (hero_id=85)
- Current safe_default: Distant Crewmates
- Current push_default: Distant Crewmates
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Distant Crewmates; Mage Hand only for alternate utility needs.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Mage Hand only when that alternate utility behavior is specifically needed.
- Current conditionals:
  - when: specifically need Mage Hand alternate utility → Mage Hand
- Available options:
  - tier 0: Distant Crewmates [6133]; Mage Hand [6134]

### Reya (hero_id=86)
- Current safe_default: Champions of Good
- Current push_default: Champions of Good
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Tank/Support routes unmapped
- Explanation: Safe Champions of Good; Law only when formation/roster alignment prefers it.
- csv_default_label: Tank route
- csv_label_maps_to: None
- csv_advice_text: Champions of Law only when formation/roster alignment prefers it.
- Current conditionals:
  - when: formation/roster alignment prefers Champions of Law → Champions of Law
- Available options:
  - tier 0: Champions of Good [5459]; Champions of Law [5460]

### NERDS (hero_id=87)
- Current safe_default: Green Leader, Standing By
- Current push_default: Green Leader, Standing By
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; color-to-profile mapping soft
- Explanation: Safe Green Leader; other colors by needed support profile.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Other colors are situational by needed support profile.
- Current conditionals:
  - when: support profile needs Orange Leader → Orange Leader, Standing By
  - when: support profile needs Red Leader → Red Leader, Standing By
  - when: support profile needs Yellow Leader → Yellow Leader, Standing By
  - when: support profile needs Pink Leader → Pink Leader, Standing By
  - when: support profile needs Purple Leader → Purple Leader, Standing By
- Available options:
  - tier 0: Orange Leader, Standing By [6146]; Red Leader, Standing By [6147]; Green Leader, Standing By [6148]; Yellow Leader, Standing By [6149]; Pink Leader, Standing By [6150]; Purple Leader, Standing By [6151]

### Xerophon (hero_id=88)
- Current safe_default: High Charisma
- Current push_default: High Charisma
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Multi-tier stat picks; Support route unmapped
- Explanation: Safe High Charisma (tier5); all earlier stat tiers are separate conditionals.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Each earlier stat tier is a separate conditional choice rule.
- Current conditionals:
  - when: tier0 High Strength → High Strength
  - when: tier0 Low Strength → Low Strength
  - when: tier1 High Dexterity → High Dexterity
  - when: tier1 Low Dexterity → Low Dexterity
  - when: tier2 High Constitution → High Constitution
  - when: tier2 Low Constitution → Low Constitution
  - when: tier3 High Intelligence → High Intelligence
  - when: tier3 Low Intelligence → Low Intelligence
  - when: tier4 High Wisdom → High Wisdom
  - when: tier4 Low Wisdom → Low Wisdom
  - when: tier5 Low Charisma → Low Charisma
- Available options:
  - tier 0: High Strength [6838]; Low Strength [6839]
  - tier 1: High Dexterity [6840]; Low Dexterity [6841]
  - tier 2: High Constitution [6978]; Low Constitution [6979]
  - tier 3: High Intelligence [6976]; Low Intelligence [6977]
  - tier 4: High Wisdom [6980]; Low Wisdom [6981]
  - tier 5: High Charisma [6842]; Low Charisma [6843]

### D'hani (hero_id=89)
- Current safe_default: Ochre Jelly Yellow
- Current push_default: Ochre Jelly Yellow
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Debuff/Paint focus labels unmapped
- Explanation: Safe Ochre Jelly Yellow; Green/Blue paints are situational scaling choices.
- csv_default_label: Debuff focus
- csv_label_maps_to: None
- csv_advice_text: Green/Blue paints are situational paint/scaling choices only.
- Current conditionals:
  - when: situational Twig Blight Green paint/scaling → Twig Blight Green
  - when: situational Frost Giant Blue paint/scaling → Frost Giant Blue
- Available options:
  - tier 0: Ochre Jelly Yellow [13717]; Twig Blight Green [13718]; Frost Giant Blue [13719]

### Brig (hero_id=90)
- Current safe_default: "Back"-Up Singer
- Current push_default: "Back"-Up Singer
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Back-Up Singer; Cream of the Crop only for clearer utility route.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Cream of the Crop only when that utility route is clearly better.
- Current conditionals:
  - when: alternate utility route clearly better → Cream of the Crop
- Available options:
  - tier 0: "Back"-Up Singer [6355]; Cream of the Crop [6356]

### Widdle (hero_id=91)
- Current safe_default: Mind and Body
- Current push_default: Mind and Body
- Current farm_default: Mind and Body
- Dynamic handler: yes
- Review reasons: Fast Friends label unmapped; dynamic handler present
- Explanation: Safe/farm/push Mind and Body; Strong/Steady and Wisdom are situational.
- csv_default_label: Fast Friends
- csv_label_maps_to: None
- csv_advice_text: Strong and Steady / Wisdom and Confidence are situational only.
- Current conditionals:
  - when: situational Strong and Steady needed → Strong and Steady
  - when: situational Wisdom and Confidence needed → Wisdom and Confidence
- Available options:
  - tier 0: Strong and Steady [6909]; Mind and Body [6910]; Wisdom and Confidence [6911]

### Yorven (hero_id=92)
- Current safe_default: Eldritch Claw Tattoo
- Current push_default: Eldritch Claw Tattoo
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Eldritch Claw Tattoo; other tattoos/paths are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Hunger/Rabbit/Infectious Fury are situational alternatives only.
- Current conditionals:
  - when: situational Hunger For Blood → Hunger For Blood
  - when: situational Follow The Mad Rabbit → Follow The Mad Rabbit
  - when: situational Infectious Fury → Infectious Fury
- Available options:
  - tier 0: Hunger For Blood [17070]; Eldritch Claw Tattoo [17071]; Follow The Mad Rabbit [17072]; Infectious Fury [17073]

### Viconia (hero_id=93)
- Current safe_default: Begrudging Respect
- Current push_default: Begrudging Respect
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/Undead routes unmapped
- Explanation: Safe Begrudging Respect; Turn Undead only for real undead value.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Turn Undead only when undead-focused value is real; Holy Power situational.
- Current conditionals:
  - when: situational Holy Power → Holy Power
  - when: undead-focused value is real → Turn Undead → Turn Undead
- Available options:
  - tier 0: Holy Power [9784]; Begrudging Respect [9785]; Turn Undead [9786]
