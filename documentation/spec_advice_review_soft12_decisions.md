# Soft-12 specialization review decisions

Source: Perplexity soft review against `documentation/spec_advice_review_soft12_prompt.md`.

Pattern applied across all ten:

- Keep existing stable `safe_default` / `push_default` / `farm_default`.
- Align `csv_label_maps_to` to that safe default (fill previously null maps).
- Tighten `when` text on conditionals; leave `review_needed: true` as soft follow-ups.
- Route overrides now map CSV route labels to the safe default option ids.

| Hero | hero_id | Change |
|------|---------|--------|
| Prudence | 84 | `csv_label_maps_to` → Eldritch Torrent; DPS route → 6072 |
| Corazon | 85 | `csv_label_maps_to` → Distant Crewmates; Support → 6133 |
| Reya | 86 | `csv_label_maps_to` → Champions of Good; Tank/Support → 5459 |
| NERDS | 87 | `csv_label_maps_to` → Green Leader, Standing By; Support → 6148 |
| Xerophon | 88 | `csv_label_maps_to` → High Charisma; Support → 6842; tier when-rules |
| D'hani | 89 | `csv_label_maps_to` → Ochre Jelly Yellow; Debuff focus → 13717 |
| Brig | 90 | `csv_label_maps_to` → "Back"-Up Singer; Support → 6355 |
| Widdle | 91 | `csv_label_maps_to` → Mind and Body; Fast Friends → 6910 |
| Yorven | 92 | `csv_label_maps_to` → Eldritch Claw Tattoo; Support → 17071 |
| Viconia | 93 | `csv_label_maps_to` → Begrudging Respect; Support → 9785 |

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
