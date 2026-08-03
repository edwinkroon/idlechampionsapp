# Soft review batch — final remaining `review_needed` cases (soft17)

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

### Baldric (hero_id=165)
- Current safe_default: Bargain With Eldath
- Current push_default: Bargain With Eldath
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; tier1 duplicates option names across many upgrade ids
- Explanation: Safe Bargain With Eldath; other Bargains/Dark Bargain stay conditional.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Other Bargain options and Dark Bargain are conditional; only Eldath is universal.
- Current conditionals:
  - when: tier0 Bargain With Tyr → Bargain With Tyr
  - when: tier0 Bargain With Moradin → Bargain With Moradin
  - when: tier0 Bargain With Tymora → Bargain With Tymora
  - when: tier0 Bargain With Mystra → Bargain With Mystra
  - when: tier1 Dark Bargain → Dark Bargain
  - when: tier1 other Bargain deity/path (duplicate names across ids) → Bargain With Moradin
- Available options:
  - tier 0: Bargain With Tyr [17491]; Bargain With Moradin [17492]; Bargain With Tymora [17493]; Bargain With Mystra [17494]; Bargain With Eldath [17495]
  - tier 1: Dark Bargain [17496]; Bargain With Moradin [17497]; Bargain With Tymora [17498]; Bargain With Mystra [17499]; Bargain With Eldath [17500]; Bargain With Tyr [17501]; Dark Bargain [17502]; Bargain With Tymora [17503]; Bargain With Mystra [17504]; Bargain With Eldath [17505]; Bargain With Tyr [17506]; Bargain With Moradin [17507]; Dark Bargain [17508]; Bargain With Mystra [17509]; Bargain With Eldath [17510]; Bargain With Tyr [17511]; Bargain With Moradin [17512]; Bargain With Tymora [17513]; Dark Bargain [17514]; Bargain With Eldath [17515]; Bargain With Tyr [17516]; Bargain With Moradin [17517]; Bargain With Tymora [17518]; Bargain With Mystra [17519]; Dark Bargain [17520]

### Cazrin (hero_id=166)
- Current safe_default: Ancestor's Shadow
- Current push_default: Ancestor's Shadow
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler; multi-tier smell route soft
- Explanation: Safe Ancestor's Shadow; Library situational; Smell Mastery only if intended.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Lost in the Library situational; Smell Mastery only for intended smell route.
- Current conditionals:
  - when: tier0 Self Taught → Self Taught
  - when: situational Lost in the Library → Lost in the Library
  - when: tier1 smell/mastery route intended → Smell Mastery → Smell Mastery
  - when: tier1 Signature Smell instead → Signature Smell
- Available options:
  - tier 0: Self Taught [17678]; Ancestor's Shadow [17679]; Lost in the Library [17680]
  - tier 1: Signature Smell [17681]; Smell Mastery [17682]

### Raistlin (hero_id=173)
- Current safe_default: Heroic Mage
- Current push_default: Heroic Mage
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler present
- Explanation: Safe Heroic Mage; Reclusive/War Mage are situational.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Reclusive Mage / War Mage are situational.
- Current conditionals:
  - when: situational Reclusive Mage → Reclusive Mage
  - when: situational War Mage → War Mage
- Available options:
  - tier 0: Heroic Mage [18934]; Reclusive Mage [18935]; War Mage [18936]

### Tasslehoff (hero_id=174)
- Current safe_default: Fast Friends
- Current push_default: Fast Friends
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier map/friends soft
- Explanation: Safe Fast Friends; map collectors and Small/Old Friends are situational.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Map collector tier0 and Small/Old Friends are situational.
- Current conditionals:
  - when: tier0 Map Collector: Pre-Cataclysm → Map Collector: Pre-Cataclysm
  - when: tier0 Map Collector: Time of Darkness → Map Collector: Time of Darkness
  - when: tier0 Map Collector: War of the Lance → Map Collector: War of the Lance
  - when: tier1 Small Friends situational → Small Friends
  - when: tier1 Old Friends situational → Old Friends
- Available options:
  - tier 0: Map Collector: Pre-Cataclysm [19240]; Map Collector: Time of Darkness [19241]; Map Collector: War of the Lance [19242]
  - tier 1: Small Friends [19237]; Fast Friends [19238]; Old Friends [19239]

### Laurana (hero_id=175)
- Current safe_default: Battle Plan: Charge
- Current push_default: Battle Plan: Charge
- Current farm_default: null
- Dynamic handler: no
- Review reasons: No CSV; multi-tier battle-plan soft
- Explanation: Safe Battle Plan: Charge; other plans and tier1 picks are situational.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Outflank/Fortify and tier1 attack/protect/Dragonlance are situational.
- Current conditionals:
  - when: tier0 Battle Plan: Outflank → Battle Plan: Outflank
  - when: tier0 Battle Plan: Fortify → Battle Plan: Fortify
  - when: tier1 Lead the Attack → Lead the Attack
  - when: tier1 Protect the Vulnerable → Protect the Vulnerable
  - when: tier1 Wield the Dragonlance → Wield the Dragonlance
- Available options:
  - tier 0: Battle Plan: Charge [19354]; Battle Plan: Outflank [19355]; Battle Plan: Fortify [19356]
  - tier 1: Lead the Attack [19357]; Protect the Vulnerable [19358]; Wield the Dragonlance [19359]

### Van Richten (hero_id=177)
- Current safe_default: Endless Hunt
- Current push_default: Endless Hunt
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler; multi-tier occult soft
- Explanation: Safe Endless Hunt; Allies/Scholar and Occult Aid picks are contextual.
- csv_default_label: None
- csv_label_maps_to: None
- csv_advice_text: Occult Allies/Scholar and Occult Aid tier1 options are contextual.
- Current conditionals:
  - when: contextual Occult Allies → Occult Allies
  - when: contextual Scholar of Dread → Scholar of Dread
  - when: tier1 Occult Aid: Cure Wounds → Occult Aid: Cure Wounds
  - when: tier1 Occult Aid: Dispel Evil → Occult Aid: Dispel Evil
  - when: tier1 Occult Aid: Sanctuary → Occult Aid: Sanctuary
- Available options:
  - tier 0: Occult Allies [19700]; Scholar of Dread [19701]; Endless Hunt [19702]
  - tier 1: Occult Aid: Cure Wounds [19703]; Occult Aid: Dispel Evil [19704]; Occult Aid: Sanctuary [19705]
