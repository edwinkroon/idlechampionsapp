# Soft review hard-clear

After soft-10…17 Perplexity passes, `review_needed` was cleared for all soft-reviewed champions whose defaults/CSV maps are settled.

## Cleared

74 champions from soft-10…17 → `review_needed: false`, `review_reasons: []`.

## Still `review_needed: true` (structural)

None after the Selise/Baldric duplicate-id resolution (see `spec_advice_duplicate_upgrade_ids.md`).

Previously held:

| hero_id | name | resolution |
|--------:|------|------------|
| 81 | Selise | Pin lowest upgrade_id per name; `@1` overrides |
| 165 | Baldric | Pin lowest upgrade_id per name; `@1` overrides |

## Intentional null `safe_default` (unchanged)

12 champions remain context-only (Asharra, Minsc, Tyril, …) — not part of this clear.

## Result

`documentation/spec_advice_review_needed.md`: **0** review_needed (after Selise/Baldric resolution), **12** intentional null.
