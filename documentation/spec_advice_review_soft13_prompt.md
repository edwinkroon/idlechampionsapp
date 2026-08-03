# Soft review batch — next 10 `review_needed` cases (soft13)

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

### Vi (hero_id=95)
- Current safe_default: A Nudge In The Right Direction
- Current push_default: A Nudge In The Right Direction
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe A Nudge In The Right Direction; Bless/Positive are situational only.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Bless Their Hearts / Positive Reinforcement are situational only.
- Current conditionals:
  - when: situational Bless Their Hearts → Bless Their Hearts
  - when: situational Positive Reinforcement → Positive Reinforcement
- Available options:
  - tier 0: Bless Their Hearts [12316]; Positive Reinforcement [12317]; A Nudge In The Right Direction [12318]

### Tatyana (hero_id=97)
- Current safe_default: Best Friend Forever
- Current push_default: Best Friend Forever
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Tank/Utility routes unmapped
- Explanation: Safe Best Friend Forever; Friends/By My Side are situational.
- csv_default_label: Tank route
- csv_label_maps_to: None
- csv_advice_text: Your Friends / By My Side are situational tank/utility variants.
- Current conditionals:
  - when: situational Your Friends are My Friends → Your Friends are My Friends
  - when: situational By My Side → By My Side
- Available options:
  - tier 0: Your Friends are My Friends [7387]; By My Side [7388]; Best Friend Forever [7389]

### Gazrick (hero_id=98)
- Current safe_default: Aim Around Armor
- Current push_default: null
- Current farm_default: Aim Around Armor
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe/farm Aim Around Armor; Gold/Frost variants are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Genius with Gold / Finesse with Frost are situational support/utility.
- Current conditionals:
  - when: situational Genius with Gold support/utility → Genius with Gold
  - when: situational Finesse with Frost support/utility → Finesse with Frost
- Available options:
  - tier 0: Genius with Gold [7538]; Aim Around Armor [7539]; Finesse with Frost [7540]

### Dungeon Master (hero_id=99)
- Current safe_default: Fear Not, Champions!
- Current push_default: Fear Not, Champions!
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Utility route unmapped
- Explanation: Safe Fear Not, Champions!; other utility options are situational.
- csv_default_label: Utility route
- csv_label_maps_to: None
- csv_advice_text: Where Did He Go / Special Guest Stars are situational utility choices.
- Current conditionals:
  - when: situational Where Did He Go This Time? → Where Did He Go This Time?
  - when: situational Special Guest Stars → Special Guest Stars
- Available options:
  - tier 0: Where Did He Go This Time? [7849]; Fear Not, Champions! [7850]; Special Guest Stars [16144]

### Merilwen (hero_id=101)
- Current safe_default: Meow-il-wen
- Current push_default: null
- Current farm_default: Meow-il-wen
- Dynamic handler: no
- Review reasons: Gold/Support routes unmapped
- Explanation: Safe/farm Meow-il-wen; Skunk/Friends are situational.
- csv_default_label: Gold route
- csv_label_maps_to: None
- csv_advice_text: Stink Like Skunk / Treasures Her Friends are situational.
- Current conditionals:
  - when: situational Stink Like Skunk → Stink Like Skunk
  - when: situational Treasures Her Friends → Treasures Her Friends
- Available options:
  - tier 0: Stink Like Skunk [7997]; Treasures Her Friends [7998]; Meow-il-wen [7999]

### Nahara (hero_id=102)
- Current safe_default: A Barovian Bond
- Current push_default: A Barovian Bond
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped
- Explanation: Safe A Barovian Bond; Grave Experience/Lyre are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Grave Experience / Skilled Lyre are situational.
- Current conditionals:
  - when: situational A Grave Experience → A Grave Experience
  - when: situational A Skilled Lyre → A Skilled Lyre
- Available options:
  - tier 0: A Grave Experience [19723]; A Barovian Bond [19724]; A Skilled Lyre [19725]

### Voronika (hero_id=104)
- Current safe_default: Embrace Evil
- Current push_default: Embrace Evil
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support routing unmapped; multi-tier situational
- Explanation: Safe Embrace Evil; other tier0/tier1 picks are situational conditionals.
- csv_default_label: Support routing
- csv_label_maps_to: None
- csv_advice_text: Tier0/tier1 alternates are situational and must stay split by tier.
- Current conditionals:
  - when: tier0 Hunt The Favored → Hunt The Favored
  - when: tier0 Weaken The Fools → Weaken The Fools
  - when: tier1 Battle Magic → Battle Magic
  - when: tier1 Powerful Focus → Powerful Focus
  - when: tier1 Strike First, Strike Hard → Strike First, Strike Hard
- Available options:
  - tier 0: Embrace Evil [15635]; Hunt The Favored [15636]; Weaken The Fools [15637]
  - tier 1: Battle Magic [15638]; Powerful Focus [15639]; Strike First, Strike Hard [15640]

### Dob (hero_id=105)
- Current safe_default: Befriend Everybody!
- Current push_default: Befriend Everybody!
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: Support route unmapped; dynamic handler present
- Explanation: Safe Befriend Everybody!; Magical/Friendly/Quick are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Magical/Friendly/Quick are situational; Everybody is the stable default.
- Current conditionals:
  - when: situational Befriend the Magical → Befriend the Magical
  - when: situational Befriend the Friendly → Befriend the Friendly
  - when: situational Befriend the Quick → Befriend the Quick
- Available options:
  - tier 0: Befriend the Magical [8742]; Befriend the Friendly [8743]; Befriend the Quick [8744]; Befriend Everybody! [8745]

### Blooshi (hero_id=106)
- Current safe_default: Charred Souls
- Current push_default: Charred Souls
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Tank/Damage routes unmapped; multi-tier situational
- Explanation: Safe Charred Souls; other souls/spirits by survival vs offense needs.
- csv_default_label: Tank route
- csv_label_maps_to: None
- csv_advice_text: Sliced/Skewered and Spirit picks by survival vs offense needs.
- Current conditionals:
  - when: offense needs Sliced Souls → Sliced Souls
  - when: offense needs Skewered Souls → Skewered Souls
  - when: tier1 survival needs Resilient Spirit → Resilient Spirit
  - when: tier1 offense needs Wild Spirit → Wild Spirit
- Available options:
  - tier 0: Sliced Souls [7523]; Skewered Souls [7524]; Charred Souls [7525]
  - tier 1: Resilient Spirit [7526]; Wild Spirit [7527]

### Egbert (hero_id=113)
- Current safe_default: Atonement Begins with an Apology
- Current push_default: Atonement Begins with an Apology
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/Control routes unmapped; multi-tier situational
- Explanation: Safe Atonement Apology; other tier0/tier1 picks are situational.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Chaos/Bombs/Health/Capitalism are situational tier-based choices.
- Current conditionals:
  - when: tier0 Team Chaos Team → Team Chaos Team
  - when: tier1 Smoky Bombs → Smoky Bombs
  - when: tier1 Health Kick → Health Kick
  - when: tier1 Oxventure Capitalism → Oxventure Capitalism
- Available options:
  - tier 0: Atonement Begins with an Apology [8877]; Team Chaos Team [8878]
  - tier 1: Smoky Bombs [8879]; Health Kick [8880]; Oxventure Capitalism [8881]
