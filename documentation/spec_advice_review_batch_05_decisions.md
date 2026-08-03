# Spec advice review — batch 05 decisions

User-recommended decisions applied. 16 champions remain `review_needed: true` for soft mappings.

### Ulkoria (hero_id=68)
- safe_default: Shield Guardian
- push_default: Shield Guardian
- farm_default: null
- conditionals:
  - when: magic-heavy formation and maximize caster synergy → Urchin Pranks
- csv_label_maps_to: null
- notes: Shield Guardian is the stable default; Urchin Pranks only for magic-heavy caster synergy.
- review_needed: true

### Torogar (hero_id=69)
- safe_default: Tiamat's Rage
- push_default: Tiamat's Rage
- farm_default: null
- conditionals:
  - when: setup prefers alternative support/DPS interaction → Tiamat's Word
- csv_label_maps_to: null
- notes: Tiamat's Rage is the stable push default; Word only for alternate support/DPS setups.
- review_needed: false

### Ezmerelda (hero_id=70)
- safe_default: We've Trained For This
- push_default: We've Trained For This
- farm_default: null
- conditionals:
  - when: formation/target mix clearly prefers Vampire Hunter → Vampire Hunter
  - when: formation/target mix clearly prefers The Devil You Know → The Devil You Know
- csv_label_maps_to: We've Trained For This
- notes: Support default We've Trained For This; Hunter/Devil only when formation/targets prefer them.
- review_needed: false

### Penelope (hero_id=71)
- safe_default: Everybody Gets To Be Friends
- push_default: Everybody Gets To Be Friends
- farm_default: null
- conditionals:
  - when: tier0 Keep Your Friends Close needed → Keep Your Friends Close
  - when: tier0 Keep Your Future Friends Closer needed → Keep Your Future Friends Closer
  - when: tier1 encounter/control needs Fury of the Fireflies → Fury of the Fireflies
  - when: tier1 encounter/control needs Splitting The Hive → Splitting The Hive
  - when: tier1 encounter/control needs Dance of the Ladybugs → Dance of the Ladybugs
- csv_label_maps_to: null
- notes: Tier0 Friends is the stable default; tier1 control picks by encounter pattern.
- review_needed: true

### Lucius (hero_id=72)
- safe_default: Dichromancy
- push_default: Dichromancy
- farm_default: null
- conditionals:
  - when: situational Corrosion Master variant → Corrosion Master
  - when: situational Lingering Chill variant → Lingering Chill
- csv_label_maps_to: null
- notes: Dichromancy is the stable default; Corrosion/Chill are situational variants only.
- review_needed: true

### Baeloth (hero_id=73)
- safe_default: Baeloth's Birthday Party
- push_default: Baeloth's Birthday Party
- farm_default: null
- conditionals:
  - when: specific utility interaction needs Over Excited → Over Excited
  - when: death-prevention interaction needs The Show Must Go On → The Show Must Go On
- csv_label_maps_to: null
- notes: Birthday Party is the stable default; Over Excited/Show Must Go On for utility/death-prevention.
- review_needed: true

### Talin (hero_id=74)
- safe_default: Additional Scatter Tacks
- push_default: Additional Scatter Tacks
- farm_default: Additional Scatter Tacks
- conditionals:
  - when: speed/navigation style needs Path Finder → Path Finder
  - when: control/debuff-heavy scenario needs Reversal of Fortunes → Reversal of Fortunes
- csv_label_maps_to: null
- notes: Scatter Tacks is the stable default; Path Finder and Reversal are situational.
- review_needed: true

### Hew Maan (hero_id=75)
- safe_default: Did We Say Humans? We Meant...
- push_default: null
- farm_default: Did We Say Humans? We Meant...
- conditionals:
  - when: formation specifically benefits from Law Maan → Law Maan
  - when: formation specifically benefits from Hello, Fellow Mercenaries! → Hello, Fellow Mercenaries!
- csv_label_maps_to: Did We Say Humans? We Meant...
- notes: Speed/farm default Did We Say Humans; Law/Mercenaries only for specific formations.
- review_needed: false

### Orisha (hero_id=76)
- safe_default: Blazing Soul
- push_default: Blazing Soul
- farm_default: null
- conditionals:
  - when: tier0 Long Burn needed → Long Burn
  - when: tier1 push/run goal needs Sirens' Connection → Sirens' Connection
  - when: tier1 push/run goal needs Fierce Connection → Fierce Connection
- csv_label_maps_to: null
- notes: Blazing Soul is the stable tier0 default; tier1 connections split by run goal.
- review_needed: true

### Alyndra (hero_id=77)
- safe_default: Expansive Vision
- push_default: Expansive Vision
- farm_default: null
- conditionals:
  - when: adjacency/team composition prefers Extra Judgy → Extra Judgy
  - when: adjacency/team composition prefers Heroes of the Planes → Heroes of the Planes
- csv_label_maps_to: null
- notes: Expansive Vision is the stable default; Judgy/Planes only for adjacency/comp fits.
- review_needed: true

### Orkira (hero_id=78)
- safe_default: Tailfeather of the Phoenix
- push_default: Tailfeather of the Phoenix
- farm_default: null
- conditionals:
  - when: healing/survival is the main problem → Breath of the Phoenix
- csv_label_maps_to: null
- notes: Tailfeather is the stable support default; Breath only when healing/survival is the problem.
- review_needed: true

### Shaka (hero_id=79)
- safe_default: Blinding Wall of Light
- push_default: Blinding Wall of Light
- farm_default: null
- conditionals:
  - when: tier0 Disintegrating Wall of Light needed → Disintegrating Wall of Light
  - when: tier1 puzzle/formation Child's Play → Child's Play
  - when: tier1 puzzle/formation Pen and Paper → Pen and Paper
  - when: tier1 puzzle/formation Sunday Edition → Sunday Edition
  - when: tier1 puzzle/formation Brain Break → Brain Break
- csv_label_maps_to: null
- notes: Blinding Wall is the stable default; tier1 puzzle/formation picks are context-based.
- review_needed: true

### Mehen (hero_id=80)
- safe_default: Found Family
- push_default: Found Family
- farm_default: null
- conditionals:
  - when: roster synergy clearly prefers Fighting Force → Fighting Force
  - when: roster synergy clearly prefers Father Figure → Father Figure
- csv_label_maps_to: null
- notes: Found Family is the stable default; Force/Father Figure only for clear roster synergy.
- review_needed: true

### Selise (hero_id=81)
- safe_default: Mithral Skin
- push_default: Mithral Skin
- farm_default: null
- conditionals:
  - when: tier0 tanking needs Reflective Shield → Reflective Shield
  - when: tier0 utility needs Relentless Avenger → Relentless Avenger
  - when: tier1 Tyr's Eyes needed → Tyr's Eyes
- csv_label_maps_to: Reflective Shield
- notes: Mithral Skin is safe; CSV still maps Tank→Reflective Shield; tier1 has duplicate names.
- review_needed: true

### Ellywick (hero_id=83)
- safe_default: All That Sparkles
- push_default: All That Sparkles
- farm_default: Faster Tempo
- conditionals:
  - when: run goal explicitly prefers For The Fans → For The Fans
- csv_label_maps_to: Faster Tempo
- notes: Sparkles is the stable default; Faster Tempo for farm/speed; Fans only for explicit run goals.
- review_needed: false

### Prudence (hero_id=84)
- safe_default: Eldritch Torrent
- push_default: Eldritch Torrent
- farm_default: null
- conditionals:
  - when: setup benefits from alternate She Hungers scaling → She Hungers
- csv_label_maps_to: null
- notes: Eldritch Torrent is the stable DPS default; She Hungers only for alternate scaling.
- review_needed: true

### Corazon (hero_id=85)
- safe_default: Distant Crewmates
- push_default: Distant Crewmates
- farm_default: null
- conditionals:
  - when: specifically need Mage Hand alternate utility → Mage Hand
- csv_label_maps_to: null
- notes: Distant Crewmates is the stable default; Mage Hand only for alternate utility.
- review_needed: true

### Reya (hero_id=86)
- safe_default: Champions of Good
- push_default: Champions of Good
- farm_default: null
- conditionals:
  - when: formation/roster alignment prefers Champions of Law → Champions of Law
- csv_label_maps_to: null
- notes: Champions of Good is the stable default; Law only when alignment prefers it.
- review_needed: true

### NERDS (hero_id=87)
- safe_default: Green Leader, Standing By
- push_default: Green Leader, Standing By
- farm_default: null
- conditionals:
  - when: support profile needs Orange Leader → Orange Leader, Standing By
  - when: support profile needs Red Leader → Red Leader, Standing By
  - when: support profile needs Yellow Leader → Yellow Leader, Standing By
  - when: support profile needs Pink Leader → Pink Leader, Standing By
  - when: support profile needs Purple Leader → Purple Leader, Standing By
- csv_label_maps_to: null
- notes: Green Leader is the stable default; other colors by needed support profile.
- review_needed: true

### Xerophon (hero_id=88)
- safe_default: High Charisma
- push_default: High Charisma
- farm_default: null
- conditionals:
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
- csv_label_maps_to: null
- notes: High Charisma is the stable tier5 default; each earlier stat tier is a separate rule.
- review_needed: true
