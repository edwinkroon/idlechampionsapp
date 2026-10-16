# Afronding schema 1.8 — relevante exportfragmenten

## 1. available / prerequisites (opdracht)

Interpretatie:
- Kolomrichting en afstandsregel staan bij de geometrie.
- Neutral op de Lawful/Chaotic-as is iets anders dan Neutral op de Good/Evil-as.
- Tel een buff op de hoofd-DPS alleen mee als de targeting onderbouwd is.
- Basiswaarden zijn geen actuele totale buffs na gear, upgrades en stacks (zie bronregels).
- Leid geen damagevermenigvuldigers af uit gemiddelde itemlevels.
- Extra schade op basis van bestaande BUD is niet automatisch hogere BUD.
- available geldt voor de huidige specialisatiekeuzes. Bij wijziging van een eerdere keuze beoordeel je de bereikbaarheid van vervolgopties opnieuw via requires_option_id. available=false is dus niet automatisch een permanent verbod. Respecteer overige prerequisites en beperkingen (required_level, not_unlocked, available=unknown).

## 2. Ontbrekende ability/feat meldingen

```json
{
  "abilities": [
    {
      "id": 15049,
      "name": "Beehive Barrage",
      "advice_hint": "Effect ontbreekt — bijdrage niet volledig te beoordelen."
    },
    {
      "id": 15058,
      "name": "Brown Bear Bash",
      "advice_hint": "Effect ontbreekt — bijdrage niet volledig te beoordelen."
    }
  ],
  "active_feats": [
    {
      "id": 1,
      "name": "Calm Under Pressure",
      "advice_hint": "Effect ontbreekt — bijdrage niet volledig te beoordelen."
    }
  ],
  "more_bees": {
    "id": 15055,
    "name": "More Bees",
    "effect": "Umberto Beehive Barrage buff.",
    "depends_on_upgrade_ids": [
      15049
    ],
    "available": true,
    "depends_on_missing": [
      "Beehive Barrage"
    ],
    "comparison_limit": "De vergelijking van More Bees met de alternatieven is beperkt doordat de basismechanic van Beehive Barrage ontbreekt."
  }
}
```

## 3. In Search of Knowledge

```
Cazrin's attacks and abilities gain additional effects based on the number of Books that she has collected in the current adventure
- 10+ Books: Cazrin fires an additional Magic Missile with her base attack.
 - 40+ Books: Increase the effect of Sunny Disposition by 5% for each Book she has collected in the current adventure, stacking multiplicatively.
 - 80+ Books: Cazrin fires an additional Magic Missile with her base attack. 
 - 120+ Books: When triggered, Mage Armor is now cast on all Champions in the formation instead of just Cazrin.
 - 160+ Books: Increase the effect of Unctuous Uggie by 1% for each Book Cazrin has collected in the current adventure, stacking additively.
 - 200+ Books: Support Champions affected by Mage Armor have a 40% chance to deal an additional 5 seconds of BUD damage with each normal attack hit.
 - 240+ Books: Mage Armor's damage prevention is increased to 50%.
 - 300+ Books: For each Tanking Champion affected by Mage Armor, the effect of Sunny Disposition is increased by 400%, stacking multiplicatively.
```
