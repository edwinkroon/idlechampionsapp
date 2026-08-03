# Soft-10 specialization review decisions

Source: Perplexity soft review pass against `documentation/spec_advice_review_soft10_prompt.md`.

Pattern applied across all ten:

- Keep the existing stable `safe_default` / `push_default` / `farm_default`.
- Align `csv_label_maps_to` to that safe default (no longer point CSV labels at a conditional side).
- Tighten `when` text on conditionals; leave `review_needed: true` as soft follow-ups.

| Hero | hero_id | Change |
|------|---------|--------|
| Strongheart | 126 | `csv_label_maps_to` → Honorary Member; Support override → 19734 |
| Gale | 147 | `csv_label_maps_to` → Ceremorphosis; Support override → 14578; clearer tier0/1 when-rules |
| Thellora | 139 | `csv_label_maps_to` → Callessa's Blessed; Support override → 12984; Vanguard only for explicit speed |
| Astarion | 129 | `csv_label_maps_to` → Arcane Trickster; Damage override → 12496 |
| Selise | 81 | `csv_label_maps_to` → Mithral Skin; Tank override → 13751 |
| Valentine | 103 | `csv_label_maps_to` → My Loyal Bodyguard; God Brain = explicit gold |
| Umberto | 151 | `csv_label_maps_to` → Family of Orphans; split More Damage conditional |
| Tess | 164 | `csv_label_maps_to` → The Fallback Plan; tighten Horizon/Gallery when-rules |
| King of Shadows | 168 | `csv_label_maps_to` → Embrace the Shadow Weave; tier-explicit conditionals |
| Skylla | 169 | `csv_label_maps_to` → Withering Ward; tighten Switch/League/fire when-rules |

Rebuild:

```bash
python scripts/advice/build_advisor_models.py
python scripts/advice/export_review_needed.py
```
