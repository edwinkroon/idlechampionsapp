# Soft-11 specialization review decisions

Source: Perplexity soft review against `documentation/spec_advice_review_soft11_prompt.md`.

Pattern applied across all ten:

- Keep existing stable `safe_default` / `push_default` / `farm_default`.
- Align `csv_label_maps_to` to that safe default (fill previously null maps).
- Tighten `when` text on conditionals; leave `review_needed: true` as soft follow-ups.
- Route overrides now map CSV route labels to the safe default option ids.

| Hero | hero_id | Change |
|------|---------|--------|
| Ulkoria | 68 | `csv_label_maps_to` → Shield Guardian; Magic route override → 4349 |
| Penelope | 71 | `csv_label_maps_to` → Everybody Gets To Be Friends; Support override → 14705 |
| Lucius | 72 | `csv_label_maps_to` → Dichromancy; Support override → 19253 |
| Baeloth | 73 | `csv_label_maps_to` → Birthday Party; Support override → 4749 |
| Talin | 74 | `csv_label_maps_to` → Additional Scatter Tacks; Speed override → 4766 |
| Orisha | 76 | `csv_label_maps_to` → Blazing Soul; Support override → 4909 |
| Alyndra | 77 | `csv_label_maps_to` → Expansive Vision; Support override → 17749 |
| Orkira | 78 | `csv_label_maps_to` → Tailfeather of the Phoenix; Healing/Support → 5577 |
| Shaka | 79 | `csv_label_maps_to` → Blinding Wall of Light; Support override → 13424 |
| Mehen | 80 | `csv_label_maps_to` → Found Family; Fiend route override → 16152 |

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
