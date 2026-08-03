# Soft review batch — next 10 `review_needed` cases

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

### Ulkoria (hero_id=68)
- Current safe_default: Shield Guardian
- Current push_default: Shield Guardian
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Magic route unmapped; confirm Guardian vs Pranks for magic-heavy comps
- Explanation: Safe Shield Guardian; Urchin Pranks only for magic-heavy caster synergy.
- csv_default_label: Magic route
- csv_label_maps_to: None
- csv_advice_text: Urchin Pranks only in magic-heavy formations for caster synergy.
- Current conditionals:
  - when: magic-heavy formation and maximize caster synergy → Urchin Pranks
- Available options:
  - tier 0: Shield Guardian [4349]; Urchin Pranks [4350]

### Penelope (hero_id=71)
- Current safe_default: Everybody Gets To Be Friends
- Current push_default: Everybody Gets To Be Friends
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/Control routes unmapped; tier1 encounter mapping still soft
- Explanation: Safe Everybody Gets To Be Friends; tier1 control picks by encounter pattern.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Tier1 control options by encounter pattern; Support/Control labels unmapped.
- Current conditionals:
  - when: tier0 Keep Your Friends Close needed → Keep Your Friends Close
  - when: tier0 Keep Your Future Friends Closer needed → Keep Your Future Friends Closer
  - when: tier1 encounter/control needs Fury of the Fireflies → Fury of the Fireflies
  - when: tier1 encounter/control needs Splitting The Hive → Splitting The Hive
  - when: tier1 encounter/control needs Dance of the Ladybugs → Dance of the Ladybugs
- Available options:
  - tier 0: Keep Your Friends Close [14703]; Keep Your Future Friends Closer [14704]; Everybody Gets To Be Friends [14705]
  - tier 1: Fury of the Fireflies [14706]; Splitting The Hive [14707]; Dance of the Ladybugs [14708]

### Lucius (hero_id=72)
- Current safe_default: Dichromancy
- Current push_default: Dichromancy
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; confirm when Corrosion/Chill beat Dichromancy
- Explanation: Safe Dichromancy; Corrosion Master/Lingering Chill are situational only.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Corrosion Master/Lingering Chill are situational variants only.
- Current conditionals:
  - when: situational Corrosion Master variant → Corrosion Master
  - when: situational Lingering Chill variant → Lingering Chill
- Available options:
  - tier 0: Dichromancy [19253]; Corrosion Master [19254]; Lingering Chill [19255]

### Baeloth (hero_id=73)
- Current safe_default: Baeloth's Birthday Party
- Current push_default: Baeloth's Birthday Party
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/Djinn routes unmapped; utility vs death-prevention triggers soft
- Explanation: Safe Birthday Party; Over Excited/Show Must Go On for utility/death-prevention.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Over Excited/Show Must Go On only for utility or death-prevention needs.
- Current conditionals:
  - when: specific utility interaction needs Over Excited → Over Excited
  - when: death-prevention interaction needs The Show Must Go On → The Show Must Go On
- Available options:
  - tier 0: Baeloth's Birthday Party [4749]; Over Excited [4750]; The Show Must Go On [4751]

### Talin (hero_id=74)
- Current safe_default: Additional Scatter Tacks
- Current push_default: Additional Scatter Tacks
- Current farm_default: Additional Scatter Tacks
- Dynamic handler: no
- Review reasons: Speed/Control routes unmapped to exact option names
- Explanation: Safe/farm/push Scatter Tacks; Path Finder and Reversal are situational.
- csv_default_label: Speed route
- csv_label_maps_to: None
- csv_advice_text: Path Finder for navigation speed; Reversal for control/debuff zones.
- Current conditionals:
  - when: speed/navigation style needs Path Finder → Path Finder
  - when: control/debuff-heavy scenario needs Reversal of Fortunes → Reversal of Fortunes
- Available options:
  - tier 0: Path Finder [4765]; Additional Scatter Tacks [4766]; Reversal of Fortunes [4767]

### Orisha (hero_id=76)
- Current safe_default: Blazing Soul
- Current push_default: Blazing Soul
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support route unmapped; tier1 run-goal mapping still soft
- Explanation: Safe Blazing Soul; tier1 connections are run-goal conditionals.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Tier1 Sirens/Fierce Connection split by run goal.
- Current conditionals:
  - when: tier0 Long Burn needed → Long Burn
  - when: tier1 push/run goal needs Sirens' Connection → Sirens' Connection
  - when: tier1 push/run goal needs Fierce Connection → Fierce Connection
- Available options:
  - tier 0: Blazing Soul [4909]; Long Burn [4910]
  - tier 1: Sirens' Connection [4911]; Fierce Connection [4912]

### Alyndra (hero_id=77)
- Current safe_default: Expansive Vision
- Current push_default: Expansive Vision
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/Positional routes unmapped
- Explanation: Safe Expansive Vision; Extra Judgy/Planes only for adjacency/comp fits.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Extra Judgy/Heroes of the Planes only when adjacency/comp prefers them.
- Current conditionals:
  - when: adjacency/team composition prefers Extra Judgy → Extra Judgy
  - when: adjacency/team composition prefers Heroes of the Planes → Heroes of the Planes
- Available options:
  - tier 0: Expansive Vision [17749]; Extra Judgy [17750]; Heroes of the Planes [17751]

### Orkira (hero_id=78)
- Current safe_default: Tailfeather of the Phoenix
- Current push_default: Tailfeather of the Phoenix
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Healing/Support routes unmapped to exact option names
- Explanation: Safe Tailfeather; Breath only when healing/survival is the main problem.
- csv_default_label: Healing route
- csv_label_maps_to: None
- csv_advice_text: Breath of the Phoenix only when healing/survival is the main problem.
- Current conditionals:
  - when: healing/survival is the main problem → Breath of the Phoenix
- Available options:
  - tier 0: Breath of the Phoenix [5576]; Tailfeather of the Phoenix [5577]

### Shaka (hero_id=79)
- Current safe_default: Blinding Wall of Light
- Current push_default: Blinding Wall of Light
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Support/Puzzle routes unmapped; tier1 puzzle mapping soft
- Explanation: Safe Blinding Wall; tier1 puzzle/formation picks are context conditionals.
- csv_default_label: Support route
- csv_label_maps_to: None
- csv_advice_text: Tier1 puzzle/formation route is context-based; Support/Puzzle unmapped.
- Current conditionals:
  - when: tier0 Disintegrating Wall of Light needed → Disintegrating Wall of Light
  - when: tier1 puzzle/formation Child's Play → Child's Play
  - when: tier1 puzzle/formation Pen and Paper → Pen and Paper
  - when: tier1 puzzle/formation Sunday Edition → Sunday Edition
  - when: tier1 puzzle/formation Brain Break → Brain Break
- Available options:
  - tier 0: Blinding Wall of Light [13424]; Disintegrating Wall of Light [13425]
  - tier 1: Child's Play [13420]; Pen and Paper [13421]; Sunday Edition [13422]; Brain Break [13423]

### Mehen (hero_id=80)
- Current safe_default: Found Family
- Current push_default: Found Family
- Current farm_default: null
- Dynamic handler: no
- Review reasons: Fiend route unmapped; roster-synergy triggers soft
- Explanation: Safe Found Family; Fighting Force/Father Figure only for clear roster synergy.
- csv_default_label: Fiend route
- csv_label_maps_to: None
- csv_advice_text: Fighting Force/Father Figure only when roster synergy clearly prefers them.
- Current conditionals:
  - when: roster synergy clearly prefers Fighting Force → Fighting Force
  - when: roster synergy clearly prefers Father Figure → Father Figure
- Available options:
  - tier 0: Fighting Force [16150]; Father Figure [16151]; Found Family [16152]
