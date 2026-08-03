# Selise / Baldric duplicate upgrade_id resolution

## Problem

Tier-1 options reuse the same specialization **name** under many different `upgrade_id`s (branch variants). Name-only lookup is ambiguous.

## Convention

For advice defaults, conditionals, and route overrides: **lowest `upgrade_id` per `(tier, name)`** is canonical.

This matches `_dedupe_options_by_name` in `ic_gamedata/specialization_qualified_rules.py`.

## Canonical pins

### Selise (81)

| Tier | Name | upgrade_id |
|-----:|------|-----------:|
| 0 | Relentless Avenger | 13749 |
| 0 | Reflective Shield | 13750 |
| 0 | Mithral Skin | 13751 (safe_default) |
| 1 | Tyr's Eyes | 13752 |
| 1 | Relentless Avenger | 13753 |
| 1 | Reflective Shield | 13754 |
| 1 | Mithral Skin | 13756 |

Overrides: `config/specialization_route_overrides.json` → `Selise` (`Name` and `Name@1`).

### Baldric (165)

| Tier | Name | upgrade_id |
|-----:|------|-----------:|
| 0 | Bargain With Tyr…Eldath | 17491…17495 (safe=17495 Eldath) |
| 1 | Dark Bargain | 17496 |
| 1 | Bargain With Moradin | 17497 |
| 1 | Bargain With Tymora | 17498 |
| 1 | Bargain With Mystra | 17499 |
| 1 | Bargain With Eldath | 17500 |
| 1 | Bargain With Tyr | 17501 |

Overrides: `Baldric` with `@1` keys for tier-1 names.

## Result

Both champions: `review_needed: false`. Preferred advice still uses explicit upgrade_ids; label mapping uses the pinned overrides.
