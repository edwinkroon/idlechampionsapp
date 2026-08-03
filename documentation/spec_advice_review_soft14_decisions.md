# Soft-14 specialization review decisions

Source: Perplexity soft review against `documentation/spec_advice_review_soft14_prompt.md`.

Pattern applied across all ten:

- Keep existing stable `safe_default` / `push_default` / `farm_default`.
- Align `csv_label_maps_to` to that safe default where a CSV label exists.
- Uriah: keep `csv_label_maps_to` null (no CSV source).
- Tighten `when` text on conditionals; leave `review_needed: true` as soft follow-ups.

| Hero | hero_id | Change |
|------|---------|--------|
| Kent | 114 | `csv_label_maps_to` → Potent Poison |
| Virgil | 115 | `csv_label_maps_to` → Mood: Anxious; speed/durability when-rules |
| Warduke | 116 | `csv_label_maps_to` → Chaos Reigns |
| Imoen | 117 | `csv_label_maps_to` → Aberration Slaying Arrows; enemy-type when-rules |
| Fen | 118 | `csv_label_maps_to` → Curse of the Dhampir |
| Uriah | 119 | keep `csv_label_maps_to` null; tighten Vile Darkness when-rule |
| Solaak | 120 | `csv_label_maps_to` → Confidant |
| Miria | 121 | `csv_label_maps_to` → Independent |
| Antrius | 122 | `csv_label_maps_to` → Bard College |
| Nixie | 123 | `csv_label_maps_to` → Anarchy Amplified |

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
