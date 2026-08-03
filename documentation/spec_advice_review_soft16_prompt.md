# Soft review batch — next 10 `review_needed` cases (soft16)

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

### Diana (hero_id=148)
- Current safe_default: Ensemble Cast
- Current push_default: Ensemble Cast
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: Support route unmapped; dynamic handler; multi-tier
- Explanation: Safe Ensemble Cast; tier0 inspires and Spotlight Episode are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: All tier0 inspire options and Spotlight Episode are situational.
- Current conditionals:
  - when: tier0 Inspire: Acrobatic Assault → Inspire: Acrobatic Assault
  - when: tier0 Inspire: Modest Might → Inspire: Modest Might
  - when: tier0 Inspire: Fledgling Fury → Inspire: Fledgling Fury
  - when: tier1 Spotlight Episode situational → Spotlight Episode
- Available options:
  - tier 0: Inspire: Acrobatic Assault [14791]; Inspire: Modest Might [14792]; Inspire: Fledgling Fury [14793]
  - tier 1: Ensemble Cast [14796]; Spotlight Episode [14797]

### Aeon (hero_id=150)
- Current safe_default: Play the Long Game
- Current push_default: Play the Long Game
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier run-plan soft
- Explanation: Safe Play the Long Game; Infiltration/tier1 picks by run plan.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Immediate Infiltration and tier1 options are situational by run plan.
- Current conditionals:
  - when: run plan needs Immediate Infiltration → Immediate Infiltration
  - when: tier1 Artificer's Arsenal by run plan → Artificer's Arsenal
  - when: tier1 Spy Network by run plan → Spy Network
  - when: tier1 Powerful Patronage by run plan → Powerful Patronage
- Available options:
  - tier 0: Immediate Infiltration [15199]; Play the Long Game [15200]
  - tier 1: Artificer's Arsenal [15201]; Spy Network [15202]; Powerful Patronage [15203]

### Bobby (hero_id=152)
- Current safe_default: Group Charge
- Current push_default: Group Charge
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier progression soft
- Explanation: Safe Group Charge; tier1 picks by progression needs.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Tier1 options are situational by progression needs.
- Current conditionals:
  - when: tier0 Stunning Strength → Stunning Strength
  - when: tier1 Not So Low by progression needs → Not So Low
  - when: tier1 Still Growing Up by progression needs → Still Growing Up
  - when: tier1 Strong Armed by progression needs → Strong Armed
- Available options:
  - tier 0: Stunning Strength [15447]; Group Charge [15448]
  - tier 1: Not So Low [15449]; Still Growing Up [15450]; Strong Armed [15451]

### Minthara (hero_id=154)
- Current safe_default: Soul Destroyer
- Current push_default: Soul Destroyer
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; recent champ
- Explanation: Safe Soul Destroyer; House Matron/True Soul are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: House Matron and True Soul are situational.
- Current conditionals:
  - when: situational House Matron → House Matron
  - when: situational True Soul → True Soul
- Available options:
  - tier 0: House Matron [15946]; True Soul [15947]; Soul Destroyer [15948]

### Wren (hero_id=155)
- Current safe_default: Glitch Form: Dwarf Monk
- Current push_default: Glitch Form: Dwarf Monk
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; recent champ
- Explanation: Safe Glitch Form: Dwarf Monk; other glitch forms are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Tabaxi Barbarian / Warforged Sorcerer are situational forms.
- Current conditionals:
  - when: situational Glitch Form: Tabaxi Barbarian → Glitch Form: Tabaxi Barbarian
  - when: situational Glitch Form: Warforged Sorcerer → Glitch Form: Warforged Sorcerer
- Available options:
  - tier 0: Glitch Form: Dwarf Monk [15217]; Glitch Form: Tabaxi Barbarian [15218]; Glitch Form: Warforged Sorcerer [15219]

### Eric (hero_id=157)
- Current safe_default: Trait: Brave
- Current push_default: Trait: Brave
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier trait/context soft
- Explanation: Safe Trait: Brave; other traits and tier1 picks are contextual.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Trait and tier1 options are contextual; Brave is the stable default.
- Current conditionals:
  - when: tier0 Trait: Cautious contextual → Trait: Cautious
  - when: tier0 Trait: Sarcastic contextual → Trait: Sarcastic
  - when: tier1 Unassuming Force contextual → Unassuming Force
  - when: tier1 Youthful Valor contextual → Youthful Valor
  - when: tier1 Treasure Hunters contextual → Treasure Hunters
- Available options:
  - tier 0: Trait: Cautious [16134]; Trait: Brave [16135]; Trait: Sarcastic [16136]
  - tier 1: Unassuming Force [16137]; Youthful Valor [16138]; Treasure Hunters [16139]

### Volo (hero_id=159)
- Current safe_default: Volo's Guide to All Things Magical
- Current push_default: Volo's Guide to All Things Magical
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler; guide context soft
- Explanation: Safe Volo's Guide to All Things Magical; other guides stay conditional.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: The other two guides are contextual and stay conditional.
- Current conditionals:
  - when: contextual Volo's Guide to Spirits and Specters → Volo's Guide to Spirits and Specters
  - when: contextual Volo's Guide to Brain-Eating Tadpoles → Volo's Guide to Brain-Eating Tadpoles
- Available options:
  - tier 0: Volo's Guide to Spirits and Specters [16554]; Volo's Guide to Brain-Eating Tadpoles [16555]; Volo's Guide to All Things Magical [16556]

### Sheila (hero_id=160)
- Current safe_default: A Rosy Outlook
- Current push_default: A Rosy Outlook
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier strike soft
- Explanation: Safe A Rosy Outlook; tier0 alts and tier1 strikes are situational.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Tier1 strike options are situational; tier0 alts stay conditional too.
- Current conditionals:
  - when: tier0 Meekly Meeting → Meekly Meeting
  - when: tier0 Youthful Allies → Youthful Allies
  - when: tier1 Frightening Strike situational → Frightening Strike
  - when: tier1 Enraging Strike situational → Enraging Strike
  - when: tier1 Confusing Strike situational → Confusing Strike
- Available options:
  - tier 0: Meekly Meeting [16541]; Youthful Allies [16542]; A Rosy Outlook [16543]
  - tier 1: Frightening Strike [16544]; Enraging Strike [16545]; Confusing Strike [16546]

### Vlithryn (hero_id=162)
- Current safe_default: Help the Unfortunate
- Current push_default: Help the Unfortunate
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler; context soft
- Explanation: Safe Help the Unfortunate; other options are contextual.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Who Else Would Save Them? / Spreading the Word are contextual.
- Current conditionals:
  - when: contextual Who Else Would Save Them? → Who Else Would Save Them?
  - when: contextual Spreading the Word → Spreading the Word
- Available options:
  - tier 0: Who Else Would Save Them? [17048]; Help the Unfortunate [17049]; Spreading the Word [17050]

### Hank (hero_id=163)
- Current safe_default: Tactical Advantage
- Current push_default: Tactical Advantage
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier situational
- Explanation: Safe Tactical Advantage; other tier0/tier1 picks are situational.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Heart/Arrow/Unity and Dragon Slayer are tier-based situational picks.
- Current conditionals:
  - when: tier0 Heart of Heroes → Heart of Heroes
  - when: tier0 Arrow Alliance → Arrow Alliance
  - when: tier0 Unyielding Unity → Unyielding Unity
  - when: tier1 Dragon Slayer → Dragon Slayer
- Available options:
  - tier 0: Heart of Heroes [17083]; Arrow Alliance [17084]; Unyielding Unity [17085]
  - tier 1: Tactical Advantage [17086]; Dragon Slayer [17087]
