# Soft review batch — next 10 `review_needed` cases (soft14)

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

### Kent (hero_id=114)
- Current safe_default: Potent Poison
- Current push_default: Potent Poison
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/Ranged routes unmapped
- Explanation: Safe Potent Poison; Robust Rivals only for preferred ranged setups.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Robust Rivals only when ranged-specific setup actually prefers it.
- Current conditionals:
  - when: ranged-specific setup prefers Robust Rivals → Robust Rivals
- Available options:
  - tier 0: Robust Rivals [9355]; Potent Poison [9356]

### Virgil (hero_id=115)
- Current safe_default: Mood: Anxious
- Current push_default: Mood: Anxious
- Current farm_default: Mood: Anxious
- Dynamic handler: no
- Review reasons: Speed/Support routes unmapped to exact mood option names
- Explanation: Safe/farm/push Mood: Anxious; Relaxed/Determined only for speed/durability needs.
- csv_default_label: Speed route
- csv_label_maps_to: None
- csv_advice_text: Relaxed/Determined only for specific speed or durability needs.
- Current conditionals:
  - when: specific speed need makes Mood: Relaxed better → Mood: Relaxed
  - when: specific durability need makes Mood: Determined better → Mood: Determined
- Available options:
  - tier 0: Mood: Relaxed [9607]; Mood: Anxious [9608]; Mood: Determined [9609]

### Warduke (hero_id=116)
- Current safe_default: Chaos Reigns
- Current push_default: Chaos Reigns
- Current farm_default: null
- Dynamic handler: no
- Review reasons: DPS/Evil routes unmapped
- Explanation: Safe Chaos Reigns; Mercenary/League are situational evil/carry variants.
- csv_default_label: DPS route
- csv_label_maps_to: None
- csv_advice_text: Mercenary / League of Malevolence are situational evil/carry variants.
- Current conditionals:
  - when: situational Mercenary for Hire evil/carry variant → Mercenary for Hire
  - when: situational League of Malevolence evil/carry variant → League of Malevolence
- Available options:
  - tier 0: Chaos Reigns [9619]; Mercenary for Hire [9620]; League of Malevolence [9621]

### Imoen (hero_id=117)
- Current safe_default: Aberration Slaying Arrows
- Current push_default: Aberration Slaying Arrows
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; enemy-type arrow choice soft
- Explanation: Safe Aberration Slaying Arrows; other arrow types only for enemy-type value.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Beast/Dragon/Monstrosity arrows only for enemy-type-specific value.
- Current conditionals:
  - when: enemy-type-specific Beast Slaying Arrows → Beast Slaying Arrows
  - when: enemy-type-specific Dragon Slaying Arrows → Dragon Slaying Arrows
  - when: enemy-type-specific Monstrosity Slaying Arrows → Monstrosity Slaying Arrows
- Available options:
  - tier 0: Beast Slaying Arrows [9643]; Dragon Slaying Arrows [9644]; Monstrosity Slaying Arrows [9645]; Aberration Slaying Arrows [9646]

### Fen (hero_id=118)
- Current safe_default: Curse of the Dhampir
- Current push_default: Curse of the Dhampir
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Curse of the Dhampir; Shadows only when explicitly better.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Shadows of the Underdark only when that route is explicitly better.
- Current conditionals:
  - when: Shadows of the Underdark route explicitly better → Shadows of the Underdark
- Available options:
  - tier 0: Shadows of the Underdark [9761]; Curse of the Dhampir [9762]

### Uriah (hero_id=119)
- Current safe_default: Book of Exalted Deeds
- Current push_default: Book of Exalted Deeds
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV source; confirm when Vile Darkness beats Exalted
- Explanation: Safe Book of Exalted Deeds; Vile Darkness only for alternate alignment path.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Book of Vile Darkness only when that alignment/utility path is right.
- Current conditionals:
  - when: alternate alignment/utility path needs Book of Vile Darkness → Book of Vile Darkness
- Available options:
  - tier 0: Book of Exalted Deeds [19680]; Book of Vile Darkness [19681]

### Solaak (hero_id=120)
- Current safe_default: Confidant
- Current push_default: Confidant
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Confidant; Unwavering/Emboldened are situational only.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Unwavering and Emboldened are situational only.
- Current conditionals:
  - when: situational Unwavering → Unwavering
  - when: situational Emboldened → Emboldened
- Available options:
  - tier 0: Unwavering [10615]; Emboldened [10616]; Confidant [10617]

### Miria (hero_id=121)
- Current safe_default: Independent
- Current push_default: Independent
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Tank/Utility routes unmapped
- Explanation: Safe Independent; Methodical/Intellectual are situational utility variants.
- csv_default_label: Tank route
- csv_label_maps_to: None
- csv_advice_text: Methodical and Intellectual are situational utility variants.
- Current conditionals:
  - when: situational Methodical utility → Methodical
  - when: situational Intellectual utility → Intellectual
- Available options:
  - tier 0: Methodical [10670]; Intellectual [10671]; Independent [10672]

### Antrius (hero_id=122)
- Current safe_default: Bard College
- Current push_default: Bard College
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Bard College; Awful Stats/Chaotic Antrius are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Truly Awful Stats / Chaotic Antrius are situational variants.
- Current conditionals:
  - when: situational Truly Awful Stats → Truly Awful Stats
  - when: situational The "A" In Chaotic Is For Antrius → The "A" In Chaotic Is For Antrius
- Available options:
  - tier 0: Bard College [10798]; Truly Awful Stats [10799]; The "A" In Chaotic Is For Antrius [10800]

### Nixie (hero_id=123)
- Current safe_default: Anarchy Amplified
- Current push_default: Anarchy Amplified
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe Anarchy Amplified; Infernal/Flawed only when clearly better.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Infernal Impact / Flawed Force only when the alternate setup is clearly better.
- Current conditionals:
  - when: alternate setup clearly better → Infernal Impact → Infernal Impact
  - when: alternate setup clearly better → Flawed Force → Flawed Force
- Available options:
  - tier 0: Infernal Impact [10890]; Flawed Force [10891]; Anarchy Amplified [10892]
