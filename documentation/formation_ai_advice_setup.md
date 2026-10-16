# Formatieadvies via chat (clipboard)

Geen betaalde API. De Formation-tab exporteert een compact adviespakket; je plakt dat in Cursor of Perplexity.

## Standaard: compact advies (tabel-antwoord)

1. Open de **Formation**-tab met een gevulde formatie.
2. Kies **hoofd-DPS** en **doel**.
3. Optioneel: restrictietekst.
4. **Kopieer voor chat** (standaard) — korte NL-opdracht + één JSON-gegevensblok.
5. Plak in de chat — de AI moet **alleen** een Markdown-tabel teruggeven.
6. Optioneel via het pijltje:
   - **Kopieer advies + JSON** — zelfde advies, plus plakinstructie voor **Plak**.
   - **Kopieer voor chat — zoek betere champions** — één klik: automatisch
     owned roster + zelfstandige opdracht (max. één wissel per voorstel;
     alleen adviesexport; geen apply; geen kandidatenpopup).
   - **Kopieer debugexport** — volledige brongegevens (niet voor standaard chat).

### Zoek betere champions

1. Kies doel en hoofd-DPS.
2. Via ▾: **Kopieer voor chat — zoek betere champions**.
3. De export bevat de huidige party plus alle betrouwbaar owned externe
   champions (geclassificeerd: opgenomen/voorwaardelijk/uitgesloten).
4. Plak in een chat — de AI zoekt zelf welke één-wissel interessant is.
5. Geen automatische wijziging van party, specs, feats of equipment.

## Readiness-dimensies

`readiness.dimensions` scheidt o.a. geometrie, party, restricties, plaatsings- en specialisatiemechanics.  
Een geldige geometrie betekent niet automatisch dat de party is toegestaan of dat alle specs mechanisch onderbouwd zijn.

`quality` per effect: `usable_for_placement` vs `usable_for_numeric_comparison` (true/false/unknown).

## Tests

```powershell
python -m unittest tests.test_formation_ai_advice -v
```
