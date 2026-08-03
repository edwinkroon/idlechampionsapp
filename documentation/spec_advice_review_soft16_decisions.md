# Soft-16 specialization review decisions

Source: Perplexity soft review against `documentation/spec_advice_review_soft16_prompt.md`.

Pattern:

- Keep existing stable defaults for all ten.
- Map `csv_label_maps_to` to safe_default for Diana, Minthara, Wren.
- Aeon / Bobby / Eric / Volo / Sheila / Vlithryn / Hank: keep CSV unmapped (`null`).
- Tighten `when` text; leave `review_needed: true`.

| Hero | hero_id | Change |
|------|---------|--------|
| Diana | 148 | `csv_label_maps_to` → Ensemble Cast; inspire when-rules |
| Aeon | 150 | keep CSV null; run-plan when-rules |
| Bobby | 152 | keep CSV null; progression when-rules |
| Minthara | 154 | `csv_label_maps_to` → Soul Destroyer |
| Wren | 155 | `csv_label_maps_to` → Glitch Form: Dwarf Monk |
| Eric | 157 | keep CSV null; trait when-rules |
| Volo | 159 | keep CSV null; guide when-rules |
| Sheila | 160 | keep CSV null; strike when-rules |
| Vlithryn | 162 | keep CSV null; rescue/outreach when-rules |
| Hank | 163 | keep CSV null; tier when-rules |

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
