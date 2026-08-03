# Soft review batch — 10 high-value `review_needed` cases

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
- unmapped labels: null tenzij exacte option name

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

### Strongheart (hero_id=126)
- Current safe_default: Honorary Member
- Current push_default: Honorary Member
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: safe_default Honorary Member vs csv_label_maps_to Valor's Call; dynamic handler present
- Explanation: Safe Honorary Member; CSV maps Support→Valor's Call; Righteous Event situational.
- csv_default_label: Support route
- csv_label_maps_to: Valor's Call
- csv_advice_text: A Righteous Event situational; pick support that best fits progress/quest goals.
- Current conditionals:
  - when: situational A Righteous Event for progress/quest goals → A Righteous Event
  - when: setup prefers Valor's Call instead → Valor's Call
- Available options:
  - tier 0: Valor's Call [19733]; Honorary Member [19734]; A Righteous Event [19738]

### Gale (hero_id=147)
- Current safe_default: Ceremorphosis
- Current push_default: Ceremorphosis
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: safe_default Ceremorphosis vs csv_label_maps_to Mystical Mentor; dynamic handler; multi-tier
- Explanation: Safe Ceremorphosis; CSV maps Support→Mystical Mentor; schools contextual.
- csv_default_label: Support route
- csv_label_maps_to: Mystical Mentor
- csv_advice_text: Schools and Finite Fellowship are contextual; CSV maps Support→Mystical Mentor.
- Current conditionals:
  - when: tier0 Evocation contextual → Evocation
  - when: tier0 Abjuration contextual → Abjuration
  - when: tier0 Enchantment contextual → Enchantment
  - when: tier0 Illusion contextual → Illusion
  - when: tier1 Mystical Mentor contextual → Mystical Mentor
  - when: tier1 Finite Fellowship contextual → Finite Fellowship
- Available options:
  - tier 0: Evocation [14574]; Abjuration [14575]; Enchantment [14576]; Illusion [14577]
  - tier 1: Ceremorphosis [14578]; Mystical Mentor [14579]; Finite Fellowship [14580]

### Thellora (hero_id=139)
- Current safe_default: Callessa's Blessed
- Current push_default: Callessa's Blessed
- Current farm_default: Callessa's Blessed
- Dynamic handler: no
- Review reasons: safe_default Callessa's Blessed vs csv_label_maps_to Vanguard of the Quick
- Explanation: Safe Callessa's Blessed; CSV maps Speed→Vanguard; Defender for survival.
- csv_default_label: Speed route
- csv_label_maps_to: Vanguard of the Quick
- csv_advice_text: Defender of the Meek only when survivability is the main need.
- Current conditionals:
  - when: survivability is the main need → Defender of the Meek
  - when: setup prefers Vanguard of the Quick instead → Vanguard of the Quick
- Available options:
  - tier 0: Defender of the Meek [12982]; Vanguard of the Quick [12983]; Callessa's Blessed [12984]

### Astarion (hero_id=129)
- Current safe_default: Arcane Trickster
- Current push_default: Arcane Trickster
- Current farm_default: null
- Dynamic handler: no
- Review reasons: safe_default Arcane Trickster vs csv_label_maps_to Outflank (Top); multi-tier situational
- Explanation: Safe Arcane Trickster; CSV maps Damage→Outflank Top; other tiers situational.
- csv_default_label: Damage route
- csv_label_maps_to: Outflank (Top)
- csv_advice_text: Tier0 Top/Bottom and tier1 Thief/Assassin are situational.
- Current conditionals:
  - when: tier0 Outflank (Top) → Outflank (Top)
  - when: tier0 Outflank (Bottom) → Outflank (Bottom)
  - when: tier1 Thief → Thief
  - when: tier1 Assassin → Assassin
- Available options:
  - tier 0: Outflank (Top) [12493]; Outflank (Bottom) [12494]
  - tier 1: Thief [12495]; Arcane Trickster [12496]; Assassin [12497]

### Selise (hero_id=81)
- Current safe_default: Mithral Skin
- Current push_default: Mithral Skin
- Current farm_default: null
- Dynamic handler: no
- Review reasons: safe_default Mithral Skin vs csv_label_maps_to Reflective Shield; tier1 duplicates option names across upgrade ids
- Explanation: Safe Mithral Skin; Reflective Shield/Avenger by tank vs utility; CSV maps Shield.
- csv_default_label: Tank route
- csv_label_maps_to: Reflective Shield
- csv_advice_text: Reflective Shield/Relentless Avenger split by tanking vs utility needs.
- Current conditionals:
  - when: tier0 tanking needs Reflective Shield → Reflective Shield
  - when: tier0 utility needs Relentless Avenger → Relentless Avenger
  - when: tier1 Tyr's Eyes needed → Tyr's Eyes
- Available options:
  - tier 0: Relentless Avenger [13749]; Reflective Shield [13750]; Mithral Skin [13751]
  - tier 1: Tyr's Eyes [13752]; Relentless Avenger [13753]; Reflective Shield [13754]; Relentless Avenger [13755]; Mithral Skin [13756]; Reflective Shield [13757]; Mithral Skin [13758]

### Valentine (hero_id=103)
- Current safe_default: My Loyal Bodyguard
- Current push_default: null
- Current farm_default: My Loyal Bodyguard
- Dynamic handler: no
- Review reasons: Socialite gold / Support labels unmapped
- Explanation: Safe/farm My Loyal Bodyguard; God Brain/Family Business situational.
- csv_default_label: Socialite gold
- csv_label_maps_to: null
- csv_advice_text: God Brain / Family Business are situational.
- Current conditionals:
  - when: situational All Hail the God Brain → All Hail the God Brain
  - when: situational Family Business → Family Business
- Available options:
  - tier 0: All Hail the God Brain [8149]; My Loyal Bodyguard [8150]; Family Business [8151]

### Umberto (hero_id=151)
- Current safe_default: Family of Orphans
- Current push_default: Family of Orphans
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler; multi-tier
- Explanation: Safe Family of Orphans; More Damage offensive alt; Bees/Clues situational.
- csv_default_label: null
- csv_label_maps_to: null
- csv_advice_text: More Damage is the clear offensive alt; Bees/Clues are situational tier1.
- Current conditionals:
  - when: tier0 Law's Alliance → Law's Alliance
  - when: tier0 Call of the Wardens → Call of the Wardens
  - when: clear offensive alternative → More Damage
  - when: tier1 More Bees situational → More Bees
  - when: tier1 More Clues situational → More Clues
- Available options:
  - tier 0: Law's Alliance [15052]; Family of Orphans [15053]; Call of the Wardens [15054]
  - tier 1: More Bees [15055]; More Clues [15056]; More Damage [15057]

### Tess (hero_id=164)
- Current safe_default: The Fallback Plan
- Current push_default: The Fallback Plan
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler present
- Explanation: Safe The Fallback Plan; Horizon/Rogues' Gallery are situational.
- csv_default_label: null
- csv_label_maps_to: null
- csv_advice_text: Eyes on the Horizon / Rogues' Gallery are situational alternatives.
- Current conditionals:
  - when: situational Eyes on the Horizon → Eyes on the Horizon
  - when: situational Rogues' Gallery → Rogues' Gallery
- Available options:
  - tier 0: The Fallback Plan [17321]; Eyes on the Horizon [17322]; Rogues' Gallery [17323]

### King of Shadows (hero_id=168)
- Current safe_default: Embrace the Shadow Weave
- Current push_default: Embrace the Shadow Weave
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler; multi-tier contextual
- Explanation: Safe Embrace the Shadow Weave; other shadow options are contextual.
- csv_default_label: null
- csv_label_maps_to: null
- csv_advice_text: Pawns/Unleashed/Illefarn/Rites are contextual alternatives.
- Current conditionals:
  - when: tier0 Master of Pawns contextual → Master of Pawns
  - when: tier0 Shadow Unleashed contextual → Shadow Unleashed
  - when: tier1 Legacy of Illefarn contextual → Legacy of Illefarn
  - when: tier1 Rites of Survival contextual → Rites of Survival
- Available options:
  - tier 0: Master of Pawns [17762]; Shadow Unleashed [17763]
  - tier 1: Legacy of Illefarn [17764]; Embrace the Shadow Weave [17765]; Rites of Survival [17766]

### Skylla (hero_id=169)
- Current safe_default: Withering Ward
- Current push_default: Withering Ward
- Current farm_default: null
- Dynamic handler: yes
- Review reasons: No CSV; dynamic handler; multi-tier fire soft
- Explanation: Safe Withering Ward; Switch/League/fire options are situational.
- csv_default_label: null
- csv_label_maps_to: null
- csv_advice_text: Witch's Switch, League of Malevolence, and fire options are situational.
- Current conditionals:
  - when: situational Witch's Switch → Witch's Switch
  - when: situational League of Malevolence → League of Malevolence
  - when: tier1 Green Fire situational → Green Fire
  - when: tier1 Blue Fire situational → Blue Fire
  - when: tier1 Violet Fire situational → Violet Fire
- Available options:
  - tier 0: Witch's Switch [17848]; League of Malevolence [17849]; Withering Ward [17850]
  - tier 1: Green Fire [17851]; Blue Fire [17852]; Violet Fire [17853]
