# Soft-13 specialization review decisions

Source: Perplexity soft review against `documentation/spec_advice_review_soft13_prompt.md`.

Pattern applied across all ten:

- Keep existing stable `safe_default` / `push_default` / `farm_default`.
- Align `csv_label_maps_to` to that safe default (fill previously null maps).
- Tighten `when` text on conditionals; leave `review_needed: true` as soft follow-ups.
- Route overrides now map CSV route labels to the safe default option ids.

| Hero | hero_id | Change |
|------|---------|--------|
| Vi | 95 | `csv_label_maps_to` → A Nudge In The Right Direction |
| Tatyana | 97 | `csv_label_maps_to` → Best Friend Forever; role-specific when-rules |
| Gazrick | 98 | `csv_label_maps_to` → Aim Around Armor |
| Dungeon Master | 99 | `csv_label_maps_to` → Fear Not, Champions! |
| Merilwen | 101 | `csv_label_maps_to` → Meow-il-wen; gold vs support when-rules |
| Nahara | 102 | `csv_label_maps_to` → A Barovian Bond |
| Voronika | 104 | `csv_label_maps_to` → Embrace Evil; tier-explicit conditionals |
| Dob | 105 | `csv_label_maps_to` → Befriend Everybody!; profile when-rules |
| Blooshi | 106 | `csv_label_maps_to` → Charred Souls; offense vs survival when-rules |
| Egbert | 113 | `csv_label_maps_to` → Atonement Begins with an Apology; tier when-rules |

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
