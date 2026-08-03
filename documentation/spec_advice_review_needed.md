# Specialization advice — review needed

0 champions marked `review_needed` in advisor models.

Per champion: kies één kant van het conflict, of houd `safe_default` op null.

| hero_id | name | model | safe | push | farm | first reason |
|---:|---|---|---|---|---|---|

## Intentional null `safe_default` (context-dependent)

Confirmed **keep_null** after soft review pass; see `documentation/spec_advice_intentional_nulls.md`.

| hero_id | name | summary |
|---:|---|---|
| 6 | Asharra | Formation-only bonds. No universal default. |
| 7 | Minsc | Adventure/enemy-type only; no universal safe default. |
| 10 | Tyril | Role/formation only: Wild Shape vs Moonbeam; no universal safe default. |
| 17 | Dhadius | Multi-tier formation/support; no universal safe default. |
| 20 | Regis | Handler: split Ahead/Behind from Ruby Weakness attack-type; no safe default. |
| 22 | Zorbu | Adventure/enemy-type dependent; no universal safe default. |
| 36 | Warden | Specter-cap by formation counts; no universal safe default. |
| 55 | Morgaen | Multi-tier formation; no universal safe default. |
| 64 | Beadle | Dynamic gear/loot handler; no universal safe default. |
| 82 | Sgt. Knox | Formation-gap dependent; no universal safe default. |
| 149 | Ravengard | Recent champ; no CSV. Keep safe_default null. |
| 153 | Kas | Recent champ; no CSV. Keep safe_default null. |
