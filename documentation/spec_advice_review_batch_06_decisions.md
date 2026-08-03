# Spec advice review — batch 06 decisions

### D'hani (hero_id=89)
- safe_default: Ochre Jelly Yellow
- push_default: Ochre Jelly Yellow
- farm_default: null
- conditionals:
  - when: situational Twig Blight Green paint/scaling → Twig Blight Green
  - when: situational Frost Giant Blue paint/scaling → Frost Giant Blue
- csv_label_maps_to: null
- notes: Ochre Jelly Yellow is the stable default; Green/Blue paints are situational scaling.
- review_needed: true

### Brig (hero_id=90)
- safe_default: "Back"-Up Singer
- push_default: "Back"-Up Singer
- farm_default: null
- conditionals:
  - when: alternate utility route clearly better → Cream of the Crop
- csv_label_maps_to: null
- notes: Back-Up Singer is the stable default; Cream of the Crop only for clearer utility.
- review_needed: true

### Widdle (hero_id=91)
- safe_default: Mind and Body
- push_default: Mind and Body
- farm_default: Mind and Body
- conditionals:
  - when: situational Strong and Steady needed → Strong and Steady
  - when: situational Wisdom and Confidence needed → Wisdom and Confidence
- csv_label_maps_to: null
- notes: Mind and Body is the stable farm/push default; Strong/Wisdom are situational.
- review_needed: true

### Yorven (hero_id=92)
- safe_default: Eldritch Claw Tattoo
- push_default: Eldritch Claw Tattoo
- farm_default: null
- conditionals:
  - when: situational Hunger For Blood → Hunger For Blood
  - when: situational Follow The Mad Rabbit → Follow The Mad Rabbit
  - when: situational Infectious Fury → Infectious Fury
- csv_label_maps_to: null
- notes: Eldritch Claw Tattoo is the stable default; other paths are situational.
- review_needed: true

### Viconia (hero_id=93)
- safe_default: Begrudging Respect
- push_default: Begrudging Respect
- farm_default: null
- conditionals:
  - when: situational Holy Power → Holy Power
  - when: undead-focused value is real → Turn Undead
- csv_label_maps_to: null
- notes: Begrudging Respect is the stable default; Turn Undead only for real undead value.
- review_needed: true

### Rust (hero_id=94)
- safe_default: Even More Riches
- push_default: Even More Riches
- farm_default: Even More Riches
- conditionals:
  - when: niche route explicitly desired → Rust's Fever Dream
  - when: setup prefers Get Rich Quick instead → Get Rich Quick
- csv_label_maps_to: Get Rich Quick
- notes: Even More Riches is safe; CSV still maps Gold→Get Rich Quick; Fever Dream niche only.
- review_needed: false

### Vi (hero_id=95)
- safe_default: A Nudge In The Right Direction
- push_default: A Nudge In The Right Direction
- farm_default: null
- conditionals:
  - when: situational Bless Their Hearts → Bless Their Hearts
  - when: situational Positive Reinforcement → Positive Reinforcement
- csv_label_maps_to: null
- notes: Nudge is the stable default; Bless/Positive are situational only.
- review_needed: true

### Desmond (hero_id=96)
- safe_default: Embrace the Beast
- push_default: Embrace the Beast
- farm_default: null
- conditionals:
  - when: defeated/dead synergy or party composition demands Double Time → Double Time
  - when: defeated/dead synergy or party composition demands Strength in Numbers → Strength in Numbers
- csv_label_maps_to: Embrace the Beast
- notes: Embrace the Beast is the stable default; Double Time/Numbers only for defeated synergy.
- review_needed: false

### Tatyana (hero_id=97)
- safe_default: Best Friend Forever
- push_default: Best Friend Forever
- farm_default: null
- conditionals:
  - when: situational Your Friends are My Friends → Your Friends are My Friends
  - when: situational By My Side → By My Side
- csv_label_maps_to: null
- notes: Best Friend Forever is the stable default; Friends/By My Side are situational.
- review_needed: true

### Gazrick (hero_id=98)
- safe_default: Aim Around Armor
- push_default: null
- farm_default: Aim Around Armor
- conditionals:
  - when: situational Genius with Gold support/utility → Genius with Gold
  - when: situational Finesse with Frost support/utility → Finesse with Frost
- csv_label_maps_to: null
- notes: Aim Around Armor is the stable farm default; Gold/Frost are situational.
- review_needed: true

### Dungeon Master (hero_id=99)
- safe_default: Fear Not, Champions!
- push_default: Fear Not, Champions!
- farm_default: null
- conditionals:
  - when: situational Where Did He Go This Time? → Where Did He Go This Time?
  - when: situational Special Guest Stars → Special Guest Stars
- csv_label_maps_to: null
- notes: Fear Not, Champions! is the stable default; other utility picks are situational.
- review_needed: true

### Nordom (hero_id=100)
- safe_default: Modron Core Toolbox
- push_default: Modron Core Toolbox
- farm_default: null
- conditionals:
  - when: automation/modron goals need BASIC Functionality → BASIC Functionality
  - when: automation/modron goals need Core Competency → Core Competency
- csv_label_maps_to: Modron Core Toolbox
- notes: Modron Core Toolbox is the stable default; BASIC/Competency by automation goals.
- review_needed: false

### Merilwen (hero_id=101)
- safe_default: Meow-il-wen
- push_default: null
- farm_default: Meow-il-wen
- conditionals:
  - when: situational Stink Like Skunk → Stink Like Skunk
  - when: situational Treasures Her Friends → Treasures Her Friends
- csv_label_maps_to: null
- notes: Meow-il-wen is the stable farm default; Skunk/Friends are situational.
- review_needed: true

### Nahara (hero_id=102)
- safe_default: A Barovian Bond
- push_default: A Barovian Bond
- farm_default: null
- conditionals:
  - when: situational A Grave Experience → A Grave Experience
  - when: situational A Skilled Lyre → A Skilled Lyre
- csv_label_maps_to: null
- notes: A Barovian Bond is the stable default; Grave/Lyre are situational.
- review_needed: true

### Valentine (hero_id=103)
- safe_default: My Loyal Bodyguard
- push_default: null
- farm_default: My Loyal Bodyguard
- conditionals:
  - when: situational All Hail the God Brain → All Hail the God Brain
  - when: situational Family Business → Family Business
- csv_label_maps_to: null
- notes: My Loyal Bodyguard is the stable farm default; God Brain/Family are situational.
- review_needed: true

### Voronika (hero_id=104)
- safe_default: Embrace Evil
- push_default: Embrace Evil
- farm_default: null
- conditionals:
  - when: tier0 Hunt The Favored → Hunt The Favored
  - when: tier0 Weaken The Fools → Weaken The Fools
  - when: tier1 Battle Magic → Battle Magic
  - when: tier1 Powerful Focus → Powerful Focus
  - when: tier1 Strike First, Strike Hard → Strike First, Strike Hard
- csv_label_maps_to: null
- notes: Embrace Evil is the stable tier0 default; other tier0/tier1 picks stay split and situational.
- review_needed: true

### Dob (hero_id=105)
- safe_default: Befriend Everybody!
- push_default: Befriend Everybody!
- farm_default: null
- conditionals:
  - when: situational Befriend the Magical → Befriend the Magical
  - when: situational Befriend the Friendly → Befriend the Friendly
  - when: situational Befriend the Quick → Befriend the Quick
- csv_label_maps_to: null
- notes: Befriend Everybody! is the stable default; Magical/Friendly/Quick are situational.
- review_needed: true

### Blooshi (hero_id=106)
- safe_default: Charred Souls
- push_default: Charred Souls
- farm_default: null
- conditionals:
  - when: offense needs Sliced Souls → Sliced Souls
  - when: offense needs Skewered Souls → Skewered Souls
  - when: tier1 survival needs Resilient Spirit → Resilient Spirit
  - when: tier1 offense needs Wild Spirit → Wild Spirit
- csv_label_maps_to: null
- notes: Charred Souls is the stable default; other souls/spirits by survival vs offense.
- review_needed: true

### Egbert (hero_id=113)
- safe_default: Atonement Begins with an Apology
- push_default: Atonement Begins with an Apology
- farm_default: null
- conditionals:
  - when: tier0 Team Chaos Team → Team Chaos Team
  - when: tier1 Smoky Bombs → Smoky Bombs
  - when: tier1 Health Kick → Health Kick
  - when: tier1 Oxventure Capitalism → Oxventure Capitalism
- csv_label_maps_to: null
- notes: Apology is the stable tier0 default; Chaos/Bombs/Health/Capitalism are situational.
- review_needed: true

### Kent (hero_id=114)
- safe_default: Potent Poison
- push_default: Potent Poison
- farm_default: null
- conditionals:
  - when: ranged-specific setup prefers Robust Rivals → Robust Rivals
- csv_label_maps_to: null
- notes: Potent Poison is the stable default; Robust Rivals only for preferred ranged setups.
- review_needed: true
