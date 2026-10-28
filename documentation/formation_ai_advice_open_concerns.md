# Formatie-AI-adviesexport — open zorgen en problemen

Stand van zaken na de compacte export + inhoudelijke correcties (schema 1.2).
Dit is geen takenlijst voor “alles fixen”; het scheidt wat **opgelost** is van wat **nog risico’s** of **ontbrekende brongegevens** zijn.

---

## 1. Omvang vs. volledigheid

- De compacte adviesexport is kleiner dan de oude prose+JSON-dump en dan de debugexport, maar **niet** systematisch 50%/25% kleiner dan elke tussenstap.
- Rijkere mechanics (feats, effectieve kenmerken, typed parameters, eligibility-overrides) **vergroten** de export terecht. Lengtedoelen mogen geen mechanics wegknippen.
- Een live party van ~7 champions (bijv. Artemis/Tyril/Briv/…) zit niet als fixture in de repo; gemeten cijfers op de 3-champ testfixture zijn **niet** representatief voor jouw grootste exports (~70k tekens).

**Actie bij twijfel:** meet altijd op dezelfde live export (Kopieer voor chat) vóór/na een wijziging.

---

## 2. Ontbrekende of onzekere game-bronnen

| Onderwerp | Risico |
|---|---|
| Equipment-effecten | Staan als `equipment_status: unknown`. Geen multipliers uit gemiddelde itemlevels — maar de AI ziet ook geen echte gear-buffs. |
| Actuele totale buff na gear/feats/stacks | Parameters zijn vaak `definition_base` of `computed_unknown`, niet “huidige in-game eindwaarde”. |
| Escorts / blocked als hop | `escorts_count_as_adjacent: unknown`; hops lopen in de export **niet** door blocked. Of elk ability dat zo speelt, is niet vastgesteld. |
| NPC/escort-identiteit | `slot_states` markeert `slot_escort`-seats als `occupancy=escort` / `placeability=blocked`, maar API levert geen NPC-id/naam op die seats — `blocker.id`/`name` blijven weg. Andere blokkadetypes dan `slot_escort` zijn niet gescand. Zonder adventure-define: lege seats → `placeability=unknown` (niet “vrij”). |
| Voorste kolom = aangevallen slots | `front_column_is_attacked_slots: unknown`. Lage `column_index` = front in onze topologie; dat die ook de aangevallen plekken zijn, is niet bewezen. |
| Affiliaties | `affiliations_status: unknown` mag **niet** als “Unaffiliated” gelezen worden. Force-allow-by-tag kan daardoor op `unknown` blijven. |
| Spec-keuze niet uitgelezen | `selection_status: unknown` als `specialization_choices` ontbreekt in de payload — AI mag dan geen A→B alsof A bekend was. |

---

## 3. Restricties en uitzonderingen

**Opgelost in principe**

- Unconditional kit-override (Dark Inheritance-achtig: `do_nothing` + eligibility-beschrijving).
- Campaign-scoped override (Volo-achtig) met check op `campaign_id` / `campaign_name`.
- Force-allow-by-tag alleen bij geverifieerde tag.

**Blijvende zorgen**

- Dark Inheritance / Volo’s Guide gebruiken effectueel `do_nothing`; de override hangt af van **beschrijvingstekst + effect_string**. Dat is geen volledig machine-effect, wel met harde eis dat `do_nothing` aanwezig is (geen pure keyword-guess zonder effect).
- Als campagnegegevens ontbreken → `effective_eligibility: unknown` (goed), maar party-`readiness` kan nog “ok/unconfirmed/conflict” mixen; UI moet die status serieus nemen.
- Stat-gates (DEX e.d.) + override: eindstatus moet uit `eligibility.effective_*` komen, niet alleen uit de ruwe partycheck-regel.
- Handmatige restrictietekst bovenop API-rules blijft een **conflict**, geen stille override.

---

## 4. Feats en dubbeltelling

**Opgelost in principe**

- Actieve feats exporteren mechanical_text + effect_facts, niet alleen flavor.
- Tag/rol-wijzigingen gaan naar `effective_*` met `already_applied_in_export`.

**Blijvende zorgen**

- Numerieke feat-multipliers (bijv. % per Ceremorphosis-stack) zijn **niet** vooraf in andere magnitudes verwerkt. De AI mag ze niet “nog eens” op een al-buffed getal plakken — maar moet ze wél meewegen in kwalitatief advies.
- Feat-defines die alleen listeners / lege descriptions hebben, blijven mager; debugexport behoudt meer ruwe velden.

---

## 5. Effectieve kenmerken vs. specialisatie-alternatieven

**Opgelost in principe**

- `base_alignment` / `effective_alignment`, idem roles/tags.
- Spec-opties kunnen `state_changes` hebben; evaluatie-alternatief = base + kandidaat, niet stapelen op huidige spec.

**Blijvende zorgen**

- Alleen wijzigingen die als `change_hero_alignment_tag` / `add_hero_tags` (e.d.) in effect_keys staan, worden structureel toegepast. Prose-only “becomes Lawful Good” zonder die keys wordt **niet** als trait-change geïnjecteerd.
- Alignment-afhankelijke targeting voor **hypothetische** specs vereist dat de AI `state_changes` van die optie gebruikt; dat staat in de data, maar is makkelijk te missen in een korte tabel.

---

## 6. Quality-flags en numerieke bruikbaarheid

**Opgelost in principe**

- Referentie-ID’s (`change_base_attack`, hit-effect-ids) ≠ buffsterkte.
- Targeting via tags (`by_tags` / lawful) kan `targeting_known` zijn zonder magnitude.
- Multiplicatieve stacking via `_mult` / “stacking multiplicatively”.
- Ontbrekende mechanic + los getal → geen `usable_for_numeric_comparison: true`.

**Blijvende zorgen**

- `usable_for_numeric_comparison: true` betekent: lokale definitie lijkt vergelijkbaar — **niet** “actuele in-game DPS is uitgerekend”.
- `dependencies_resolved` vs `dependencies_present` vs `dependencies_found`: makkelijk te verwarren. Alleen “resolved” is genoeg voor formule-vergelijking.
- Tekstparsers blijven ondersteunend; onbekende effectstructuren blijven onbekend. Geen regex als enige waarheid.

---

## 7. Ability-afhankelijkheden en vertakkingen (o.a. Astarion Outflank)

**Opgelost in principe**

- `buff_upgrades,…,id1,id2` levert **beide** upgrade-ids.
- Exclusieve specs zijn niet allemaal `simultaneously_active`.

**Blijvende zorgen**

- Gedeelde buffs die Top én Bottom noemen, betekenen “de geselecteerde tak”, niet “Top is actief”. De export claimt Top niet hard, maar een AI kan dat nog steeds verkeerd lezen.
- Ontbrekende onderliggende ability → `missing_dependency` / gap; targeting die daarvan afhangt blijft onvolledig tot de define er is.

---

## 8. Geometrie en tabelrijen

**Opgelost in principe**

- Labels: `Positie N · Kolom K — zone (boven|midden|onder)`.
- Actieve posities met alleen blocked buren → geometry warning + `unreachable` in hop-matrix.

**Blijvende zorgen**

- Rij “boven/midden/onder” is een **exportconventie** (row_order), geen gegarandeerde game-UI-term.
- Heuristische topologie (`geometry_source` niet API) mag niet als harde gamewaarheid worden gelezen (`authoritative: false`).

---

## 9. Instructie aan de AI / kopieerflow

- Standaardknop: **Kopieer voor chat** → compact advies (korte NL-opdracht + één JSON-blok).
- Pijltje: advies+JSON (Plak) of **debugexport** (volledig).
- Bij `party_restriction_status` conflict/unconfirmed: alleen voorwaardelijk voorstel; geen claim “geldig speelbaar”.
- Geen bewezen optimum zonder voldoende bewijs; geen damage uit gemiddelde itemlevels.

**Zorgen**

- Als iemand per ongeluk de debugexport naar chat plakt, is de prompt te groot en te technisch.
- Schema 1.2: oude consumers die 1.1 verwachten moeten major-compat of migratie krijgen (validate checkt major).

---

## 10. Tests en fixtures

- 54 tests in `tests.test_formation_ai_advice` (synthetisch gemarkeerd waar nodig).
- **Geen** regressiefixture voor de zeven-championparty (Artemis, Tyril, Briv, Alyndra, Corazon, Solaak, Laurana). Gedrag daarop is niet CI-gedekt.
- Human Glitch / Resist the Urge / Volo / Dark Inheritance: deels synthetisch + defines; hangt af van lokale `cached_definitions.json`.

---

## 11. Wat de AI (en jij) wél / niet mag aannemen

**Wel**

- Placement op basis van bekende targeting/voorwaarden, ook als % onbekend is (kwalitatief).
- Effectieve kenmerken na geselecteerde specs/feats.
- Eligibility-eindstatus na geverifieerde overrides.

**Niet**

- Flavor of ability-namen als bewijs van het effect.
- Referentie-ID’s als percentages.
- Basisdefine-waarden als huidige totale buff.
- Onbekende affiliatie als “geen affiliatie”.
- Spec A→B als huidige keuze `unknown` is.
- Geldige party claimen bij conflict/unconfirmed restricties.

---

## 12. Korte prioriteitenlijst (als je verder wilt)

1. Live 7-champ export als anonieme fixture in `tests/fixtures/` (geen secrets) voor regressie + size-meting.
2. Equipment-effecten uit betrouwbare bron, of expliciet “geen equipment in advies”.
3. Per-ability bewijs of escorts/blocked meetellen (niet globaal gokken).
4. Consumers/UI tonen `effective_eligibility` prominenter dan alleen de ruwe partycheck.
5. Optioneel: gedeelde Outflank-buff als één logisch effect + “geldt voor geselecteerde tak”.

---

*Bestand bedoeld om te kopiëren naar chat/issues. Geen hardcoded “game truths” buiten wat de exporter uit defines/API haalt.*
