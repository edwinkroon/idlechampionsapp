# Soft-15 specialization review decisions

Source: Perplexity soft review against `documentation/spec_advice_review_soft15_prompt.md`.

Pattern:

- Keep existing stable defaults for all ten.
- Map `csv_label_maps_to` to safe_default only for Vin Ursa, Lae'zel, Certainty.
- Jang Sao / Shadowheart / Wyll / Karlach / Presto / Dynaheir / Dark Urge: keep CSV unmapped (`null`) as decided.
- Tighten `when` text; leave `review_needed: true`.

| Hero | hero_id | Change |
|------|---------|--------|
| Vin Ursa | 127 | `csv_label_maps_to` → Friends in High Places; tier when-rules |
| Lae'zel | 128 | `csv_label_maps_to` → Battle Master; Champion/EK when-rules |
| Certainty | 138 | `csv_label_maps_to` → Best And The Brightest |
| Jang Sao | 140 | keep CSV null; tier when-rules |
| Shadowheart | 141 | keep CSV null; healing/darkness when-rules |
| Wyll | 142 | keep CSV null; pact when-rules |
| Karlach | 143 | keep CSV null; wildheart/magic when-rules |
| Presto | 144 | keep CSV null; juggernauts/mastery when-rules |
| Dynaheir | 145 | keep CSV null; justice/bodyguard when-rules |
| Dark Urge | 146 | keep CSV null; tier Urge when-rules |

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
