# Formation BUD-relation coverage

Tracks which champions have executable placement preferences vs BUD/carry.
Config: `config/formation_champion_placement_rules.json`.
Scan helper: `scripts/advice/_scan_formation_prose.py`.

## Status legend

| Status | Meaning |
|--------|---------|
| `hero` | Explicit entry under `heroes` |
| `tag_default` | Covered by `defaults.by_tag` when tagged buffer/debuffer |
| `role_default` | Covered by `defaults.by_role` (e.g. tank → front) |
| `handler` | Hard-coded in `formation_advisor/handlers.py` |
| `needs_authoring` | Prose too vague / kit-specific for a single bud_relation |

## Baseline (automatic)

- **buffer** tag → `adjacent` to BUD  
- **debuffer** tag → `adjacent` to BUD  
- **tank** role → `front` zone  

## Explicit hero overrides

### Batch A

| ID | Name | Relation |
|----|------|----------|
| 1 | Bruenor | `same_column` |
| 2 | Celeste | `prefer_column` 1 |
| 5 | Calliope | `graph_distance_lte` 2 |
| 44 | Qillek | `avoid_adjacent_role` tank |
| 180 | Kitiara | `farthest` + `adjacent_count_lt` 2 |

### Batch B

| ID | Name | Relation |
|----|------|----------|
| 51 | Avren | `adjacent` |
| 70 | Ezmerelda | `same_column` |
| 74 | Talin | `adjacent` |
| 77 | Alyndra | `adjacent` |
| 126 | Strongheart | `adjacent` |
| 128 | Lae'zel | `same_column` |
| 139 | Thellora | `ahead` |
| 170 | Lark | `carry_not_edge` |
| 171 | Anson | `ahead` |
| 172 | Kyre | `adjacent` |

### Batch C (exhaust clear prose)

| ID | Name | Relation |
|----|------|----------|
| 3 | Nayeli | `ahead` |
| 11 | Jamilah | `prefer_adjacent_role` tank |
| 34 | Donaar | `adjacent` |
| 64 | Beadle | `graph_distance_lte` 2 |
| 80 | Mehen | `behind` |
| 84 | Prudence | `adjacent_count_lt` 3 |
| 104 | Voronika | `same_column` |
| 106 | Blooshi | `not_front` |
| 151 | Umberto | `carry_column_distance_lte` 2 |
| 162 | Vlithryn | `behind` |

### Batch D (needs_authoring → tackled)

| ID | Name | Relation | Notes |
|----|------|----------|--------|
| 21 | Birdsong | `graph_distance_lte` 2 | Buff within two slots |
| 38 | K'thriss | `farthest` | Unseen Encouragement on farthest |
| 39 | Paultin | `not_adjacent` | Magical Secrets; Edgy/Lucky still kit-specific |
| 49 | Turiel | `front` | Frontline + columns-behind stacking |
| 118 | Fen | `same_column` | Column buff |
| 138 | Certainty | `behind` | Buffs row/column in front |
| 141 | Shadowheart | `shadowheart_dex_spread` (≥2) | Invoke Duplicity / Find Yourself |
| 147 | Gale | `behind` | Two columns in front (Insight default) |
| 158 | Kalix | `not_adjacent` | Never adjacent to Primary DPS |
| 164 | Tess | `ahead` | Lead The Way → columns behind |
| 166 | Cazrin | `behind` | Column + columns in front (support mode) |
| 174 | Tasslehoff | `not_adjacent` | Never adjacent to DPS |

### Batch E (compound / width-aware)

| ID | Name | Relation | Notes |
|----|------|----------|--------|
| 59 | Melf | `graph_distance_lte` 3 + `not_edge` | Mid seat; buff ≤3 seats |
| 73 | Baeloth | `adjacent_column` | Columns ahead **and** behind |
| 75 | Hew Maan | `hew_teamwork` | X=1 if ≤4 cols else 2 |
| 143 | Karlach | `same_or_one_behind` | Own column + one behind |
| 176 | Trixie | `adjacent_behind` | Adjacent seat in a rear-er column |

## Handlers (do not duplicate)

| ID | Name |
|----|------|
| 168 | King of Shadows |
| 173 | Raistlin |
| 178 | Flint |

## Remaining `needs_authoring` (not tackled)

Still mention formation in role advice, but tip is kit-specific, conditional on spec, affiliation, or needs seat-row / live-spec data we don't want to guess:

| ID | Name | Why skipped |
|----|------|-------------|
| 25 | Catti-brie | DPS knockback-to-spawn; support `behind` only if Push Forward — role-conditional |
| 42 | Aila | Front-line survivability for party, not her seat vs BUD |
| 55 | Morgaen | Spec-conditional adjacent vs front |
| 65 | Omin | Spec/layout/Assassin requirements; has formation spec handler |
| 66 | Lazaapz | Comp/tank inclusion, not BUD geometry |
| 67 | Dragonbait | Multi-tank **spec** advice |
| 71 | Penelope | Maximize adjacent Support/Heal/Gold + Story Time ≤2 — kit-specific |
| 78 | Orkira | Orkira-stacking / heal-farm formation |
| 79 | Shaka | Explicitly non-forcing placement |
| 94 | Rust | Oxventurers affiliation count, not seat |
| 145 | Dynaheir | Front-column Overwhelm for others, not her vs BUD |
| 148 | Diana | Within-column top/middle/bottom — needs seat-row topology |
| 149 | Ravengard | Vague frontline Form Up stub |
| 153 | Kas | Evil-comp / tag adjacency, not BUD seat |
| 157 | Eric | Spec flips 3-behind vs 3-ahead |
| 161 | Grimm | “speed-adjacent” metaphor, not seats |
| 177 | Van Richten | Endless Hunt is tag stacks; seat tip too vague |
| 179 | Caramon | Raise Spirits ally geometry — already has spec handler |

Re-scan after guide updates: `python scripts/advice/_scan_formation_prose.py`.
Prose-backed BUD placement coverage is complete aside from the table above.
