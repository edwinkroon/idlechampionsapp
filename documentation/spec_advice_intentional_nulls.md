# Intentional null `safe_default` — confirmed keep

Reviewed after soft-10…17 + hard-clear. **All 12 stay `safe_default: null`.**

Do not promote `specializations.json` UI defaults into advisor `safe_default` for these champions.

| hero_id | name | why null |
|--------:|------|----------|
| 6 | Asharra | Formation-only bonds; must match party composition |
| 7 | Minsc | Favored Enemy is adventure/enemy-type only |
| 10 | Tyril | Wild Shape vs Moonbeam is role/formation only |
| 17 | Dhadius | Multi-tier formation/support; no universal pick |
| 20 | Regis | Handler: Ahead/Behind vs Ruby Weakness attack-type |
| 22 | Zorbu | Lead The Pack vs Hunting Partners is adventure/goal |
| 36 | Warden | Specter-cap depends on formation counts (handler) |
| 55 | Morgaen | Multi-tier formation positioning |
| 64 | Beadle | Dynamic gear/loot handler |
| 82 | Sgt. Knox | Formation-gap / tank vs support context |
| 149 | Ravengard | Recent; no CSV; options unverified as universal |
| 153 | Kas | Recent; no CSV; options unverified as universal |

## Decision rule (reminder)

- `null` only when there is truly no universal default
- Alternatives stay in `conditionals` / handlers
- UI defaults in `specializations.json` are not advisor universals

## Status

Confirmed **keep_null** for all twelve. No model changes required.
