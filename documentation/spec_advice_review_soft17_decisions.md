# Soft-17 specialization review decisions (final remaining)

Source: Perplexity soft review against `documentation/spec_advice_review_soft17_prompt.md`.

Pattern:

- Keep existing stable defaults for all six.
- Keep `csv_label_maps_to` null (no CSV sources).
- Tighten `when` text; leave `review_needed: true`.
- Baldric: replace vague duplicate-name conditional with explicit per-deity tier1 variants (first upgrade_id per unique name).

| Hero | hero_id | Change |
|------|---------|--------|
| Baldric | 165 | explicit tier0/tier1 bargain when-rules; drop vague duplicate conditional |
| Cazrin | 166 | split smell vs mastery tier1 when-rules |
| Raistlin | 173 | tighten reclusive/war mage when-rules |
| Tasslehoff | 174 | explicit map-collector / friends when-rules |
| Laurana | 175 | explicit outflank/fortify/attack/protect/dragonlance when-rules |
| Van Richten | 177 | explicit occult allies/scholar/aid when-rules |

All soft-10…17 cases are now through Perplexity. Next: hard-clear `review_needed` where appropriate, then commit.

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
