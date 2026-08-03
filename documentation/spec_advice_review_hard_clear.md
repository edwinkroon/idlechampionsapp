# Soft review hard-clear

After soft-10…17 Perplexity passes, `review_needed` was cleared for all soft-reviewed champions whose defaults/CSV maps are settled.

## Cleared

74 champions from soft-10…17 → `review_needed: false`, `review_reasons: []`.

## Still `review_needed: true` (structural)

| hero_id | name | reason |
|--------:|------|--------|
| 81 | Selise | tier1 duplicates option names across many upgrade ids |
| 165 | Baldric | tier1 duplicates option names across many upgrade ids |

## Intentional null `safe_default` (unchanged)

12 champions remain context-only (Asharra, Minsc, Tyril, …) — not part of this clear.

## Result

`documentation/spec_advice_review_needed.md`: **2** review_needed, **12** intentional null.
