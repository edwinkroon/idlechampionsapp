Je bent een Idle Champions-formatieadviseur.
Dit is een zelfstandige game-adviesaanvraag, geen programmeer- of exportreviewtaak.

Adviseer de plaatsing en specialisaties van uitsluitend de geselecteerde champions voor het hieronder genoemde doel en de gekozen hoofd-DPS.

Doel: push/damage (BUD / damage; hoofd-DPS centraal).
Hoofd-DPS: Jarlaxle (`4`).
Prioriteiten: Respecteer alle harde plaatsings- en partyregels; Houd voldoende overleving als voorwaarde voor bruikbare voortgang; Optimaliseer damage/BUD rondom de gekozen hoofd-DPS; Weeg extra BUD-gebaseerde schade mee voor voortgang, maar tel die niet automatisch als verhoging van BUD; Bij onvoldoende gegevens: kwalitatief voorstel, geen bewezen optimum.

Gebruik uitsluitend de aangeleverde gegevens.
Zoek niet op internet en vul ontbrekende mechanics niet in op basis van abilitynamen, flavor of herinneringen.

Wat jij als adviseur zelf moet doen:
- Plaatsingen vergelijken.
- Afstanden uit de aangeleverde adjacency bepalen waar nodig.
- Targeting op de hoofd-DPS controleren.
- Relevante champions, rollen en andere kwalificaties tellen.
- Synergieën en positionele conflicten afwegen.
- Specialisaties vergelijken.
- Rekenen als waarden en voorwaarden daarvoor voldoende bekend zijn.
- Anders een onderbouwd kwalitatief voorstel geven.

Harde regels:
- Gebruik iedere geselecteerde champion precies eenmaal.
- Gebruik uitsluitend geldige actieve posities.
- Maximaal één champion per permanente seat.
- Position_id is niet hetzelfde als permanente seat.
- Wijzig geen champions, feats of equipment.
- Specialisaties mogen worden geadviseerd binnen hun echte keuzegroepen en prerequisites.
- Beoordeel een alternatief inclusief relevante veranderingen aan alignment, rollen, aanvalstype, tags of andere kenmerken.
- Houd rekening met restricties en geverifieerde uitzonderingen.

Interpretatie:
- Kolomrichting en afstandsregel staan bij de geometrie.
- Neutral op de Lawful/Chaotic-as is iets anders dan Neutral op de Good/Evil-as.
- Tel een buff op de hoofd-DPS alleen mee als de targeting onderbouwd is.
- Basiswaarden zijn geen actuele totale buffs na gear, upgrades en stacks (zie bronregels).
- Leid geen damagevermenigvuldigers af uit gemiddelde itemlevels.
- Extra schade op basis van bestaande BUD is niet automatisch hogere BUD.
- available geldt voor de huidige specialisatiekeuzes. Bij wijziging van een eerdere keuze beoordeel je de bereikbaarheid van vervolgopties opnieuw via requires_option_id. available=false is dus niet automatisch een permanent verbod. Respecteer overige prerequisites en beperkingen (required_level, not_unlocked, available=unknown).

Omgaan met onzekerheid:
- Een onbekend percentage blokkeert bekende targeting niet.
- Een onbekende positionele bron maakt alleen de daarvan afhankelijke targeting voorwaardelijk.
- Geef concrete keuzes als de informatie dat ondersteunt.
- Als een ontbrekend gegeven de keuze kan omdraaien, vermeld de relevante alternatieven en de beslisfactor kort.
- Claim geen bewezen optimum zonder voldoende bewijs.
- Bij restrictieconflict of onbekende toelating: geef uitsluitend een voorwaardelijk voorstel en claim geen geldig speelbare party.

Antwoord uitsluitend met deze Markdown-tabel, niets ervoor of erna:

| Positie (ID + kolom/rij) | Champion | Seat | Specialisaties | Reden / onzekerheid |
| --- | --- | --- | --- | --- |

Sorteer achterste kolom naar voorste kolom, binnen de kolom boven naar beneden.
Gebruik de aangeleverde positie-ID's en labels.
Vermeld onzekerheden kort bij de betreffende champion.
Gebruik A → B alleen als de actuele keuze A daadwerkelijk bekend is.
Toon wijzigingen van bekende specialisaties vet.
Maak onderscheid tussen behouden, nieuw kiezen en huidige keuze onbekend.

Als een andere opstelling nodig is om stacks of een fase op te bouwen, vermeld de noodzakelijke tijdelijke plaatsing kort in de relevante rij.
De tabel beschrijft de aanbevolen hoofdopstelling.

## Gegevens
```json
{"meta":{"schema_version":"1.8","request_id":"req-test-1","data_version":"1773041353","research_mode":"provided_data_only"},"bronregels":"Gebruik complete, betrouwbare mechanicbeschrijvingen (effect) voor kwalitatieve interpretatie. effect_kind=bron is bronproza; effect_kind=gegenereerd is afgeleid. Ondersteunende ontbrekende parservelden zijn geen reden om duidelijke broninformatie te negeren. Bij een echte tegenspraak die de aanbeveling beïnvloedt: meld het conflict; raad niet welke waarde klopt. Bekende basiswaarden (definition_base) zijn geen actuele totale buffs na gear, upgrades en stacks — magnitude=basis_of_actueel_niet_berekend betekent dat de actuele totaalwaarde niet is berekend, niet dat de mechanic ontbreekt. magnitude=parameter_onbekend: een relevante parameter ontbreekt echt. Trait-wijzigingen van actieve feats met traits_already_in_effective=true zitten al in alignment/roles/tags — niet dubbel toepassen. available geldt voor de huidige specialisatiekeuzes. Bij wijziging van een eerdere keuze beoordeel je de bereikbaarheid van vervolgopties opnieuw via requires_option_id. available=false met unavailable_reason=requires_other_option is dus geen permanent verbod. Levelblokkades staan op required_level / group status not_unlocked; available=unknown betekent dat de prerequisite-status niet vaststaat.","context":{"objective":"push_damage","objective_label":"push/damage (BUD / damage; hoofd-DPS centraal)","main_dps":{"id":4,"name":"Jarlaxle"},"priorities":["Respecteer alle harde plaatsings- en partyregels.","Houd voldoende overleving als voorwaarde voor bruikbare voortgang.","Optimaliseer damage/BUD rondom de gekozen hoofd-DPS.","Weeg extra BUD-gebaseerde schade mee voor voortgang, maar tel die niet automatisch als verhoging van BUD.","Bij onvoldoende gegevens: kwalitatief voorstel, geen bewezen optimum."],"adventure":"Beast Mode","campaign":"A Grand Tour of the Sword Coast","party_restriction_status":"ok","restriction_checks":[{"champion_id":2,"name":"Celeste","status":"allowed","reason":"Geen blokkerende restrictie voor deze champion."},{"champion_id":3,"name":"Nayeli","status":"allowed","reason":"Geen blokkerende restrictie voor deze champion."},{"champion_id":4,"name":"Jarlaxle","status":"allowed","reason":"Geen blokkerende restrictie voor deze champion."}]},"geometry":{"source":"api_campaign","column_direction":{"rule":"lower_column_is_front","ui_note":"Enemies → right (front = toward the right / lower column_index).","source":"api_campaign"},"distance_rule":"hops_on_active_adjacency","escorts_in_adjacency":"unknown","valid_position_ids":[1,2,3,4,5,6,7,8,9],"adjacency":{"1":[3,6,8],"2":[5,6,7],"3":[1,4,5,6],"4":[3,5],"5":[2,3,4,6],"6":[1,2,3,5,7,8],"7":[2,6,8,9],"8":[1,6,7,9],"9":[7,8]},"positions":[{"id":4,"column":4,"row":0,"zone":"back","state":"active","label":"Positie 4 · Kolom 5 — achter (boven)"},{"id":3,"column":3,"row":0,"zone":"back","state":"active","label":"Positie 3 · Kolom 4 — achter (boven)","champion_id":4},{"id":5,"column":3,"row":1,"zone":"back","state":"active","label":"Positie 5 · Kolom 4 — achter (midden)"},{"id":1,"column":2,"row":0,"zone":"mid","state":"active","label":"Positie 1 · Kolom 3 — midden (boven)","champion_id":3},{"id":6,"column":2,"row":1,"zone":"mid","state":"active","label":"Positie 6 · Kolom 3 — midden (midden)"},{"id":2,"column":2,"row":2,"zone":"mid","state":"active","label":"Positie 2 · Kolom 3 — midden (onder)","champion_id":2},{"id":8,"column":1,"row":0,"zone":"front","state":"active","label":"Positie 8 · Kolom 2 — voor (boven)"},{"id":7,"column":1,"row":1,"zone":"front","state":"active","label":"Positie 7 · Kolom 2 — voor (midden)"},{"id":9,"column":0,"row":0,"zone":"front","state":"active","label":"Positie 9 · Kolom 1 — voor (boven)"}]},"champions":[{"id":2,"name":"Celeste","seat":2,"position":2,"species":"Human","classes":["Cleric"],"alignment":{"label":"Lawful Good","law_chaos":"lawful","good_evil":"good","source":"character_sheet_details.alignment"},"roles":["healer","support"],"affiliations":[],"affiliations_status":"known","attack":"magic","stats":{"str":14,"dex":8,"con":13,"int":12,"wis":15,"cha":10},"eligibility":{"status":"allowed","reason":"Geen blokkerende restrictie voor deze champion.","affiliation_verified":true},"abilities":[{"id":24,"name":"Crusader's Mantle","effect":"Increases the damage of Champions next to Celeste by 100%","effect_kind":"bron","stacking":"multiplicatief"},{"id":26,"name":"Mass Cure Wounds","effect":"Heals Champions in the column in front of Celeste for 6 every second","effect_kind":"bron"}],"specializations":[{"group_id":"tier_0","label":"Keuze 1 (lvl 100)","selection_mode":"exactly_one","status":"unknown","options":[{"id":29,"name":"War Domain","effect":"Celeste focuses her concentration on increasing the damage of those around her.","effect_kind":"bron","depends_on_upgrade_ids":[24],"available":true,"required_level":100},{"id":30,"name":"Life Domain","effect":"Increases the range of Mass Cure Wounds by 1 (affects all Champions in both of the 2 columns ahead of Celeste)","effect_kind":"bron","depends_on_upgrade_ids":[26],"available":true,"required_level":100}]}],"equipment":"unknown"},{"id":3,"name":"Nayeli","seat":3,"position":1,"species":"Human","classes":["Paladin"],"alignment":{"label":"Lawful Good","law_chaos":"lawful","good_evil":"good","source":"character_sheet_details.alignment"},"roles":["tank","support"],"affiliations":[],"affiliations_status":"known","attack":"melee","stats":{"str":16,"dex":12,"con":16,"int":8,"wis":10,"cha":14},"eligibility":{"status":"allowed","reason":"Geen blokkerende restrictie voor deze champion.","affiliation_verified":true},"abilities":[{"id":38,"name":"Aura of Courage","effect":"Increases the damage of Champions in the column behind Nayeli by 100%","effect_kind":"bron","stacking":"multiplicatief"},{"id":40,"name":"Aura of Protection","effect":"Increases the damage of all Champions by 50% for each enemy attacking Nayeli and/or each enemy enrage stack.","effect_kind":"bron"},{"id":782,"name":"Aura of Heroism","effect":"Increases the Health of all other Champions by 25% of Nayeli's Max Health","effect_kind":"bron"}],"specializations":[{"group_id":"tier_0","label":"Keuze 1 (lvl 100)","selection_mode":"exactly_one","status":"unknown","options":[{"id":43,"name":"Oath of Vengeance","effect":"Nayeli focuses on rallying her fellow Champions and further increasing the damage of anyone in the column behind her.","effect_kind":"bron","depends_on_upgrade_ids":[38],"available":true,"required_level":100},{"id":44,"name":"Oath of Devotion","effect":"Increases health by 70%.","effect_kind":"bron","available":true,"required_level":100}]}],"equipment":"unknown"},{"id":4,"name":"Jarlaxle","seat":4,"position":3,"species":"Elf (Drow)","classes":["Rogue"],"alignment":{"label":"Neutral Evil","law_chaos":"neutral","good_evil":"evil","source":"character_sheet_details.alignment"},"roles":["gold","dps"],"affiliations":[],"affiliations_status":"known","attack":"melee","stats":{"str":10,"dex":18,"con":13,"int":16,"wis":11,"cha":14},"eligibility":{"status":"allowed","reason":"Geen blokkerende restrictie voor deze champion.","affiliation_verified":true},"abilities":[{"id":52,"name":"Master of Disguise","effect":"Increases the damage of Jarlaxle by 100% for each Good or Neutral champion next to them","effect_kind":"bron","stacking":"multiplicatief"},{"id":55,"name":"Master Attuner","effect":"Increases the damage of Jarlaxle by 25% for each $(describe_rarity rarity) (onbekend) item equipped by other Champions in the formation","effect_kind":"bron"},{"id":2188,"name":"Master of Piracy","effect":"Increases gold find by 25% for each Drow or Rogue Champion in the formation","effect_kind":"bron"},{"id":11520,"name":"Critical Hit","effect":"Increases critical hit chance by 20%.","effect_kind":"bron"}],"specializations":[{"group_id":"tier_0","label":"Keuze 1 (lvl 150)","selection_mode":"exactly_one","status":"not_unlocked","options":[{"id":58,"name":"Secret Lord of Luskan","effect":"Increases Master of Disguise by 100%.","effect_kind":"bron","depends_on_upgrade_ids":[52],"available":true,"required_level":150},{"id":59,"name":"Leader of the Bregan D'aerthe","effect":"Jarlaxle leads a crew of shady pirates, further increasing the gold find of Master of Piracy.","effect_kind":"bron","depends_on_upgrade_ids":[2188],"available":true,"required_level":150}]}],"active_feats":[{"id":22,"name":"Frugal","effect":"Increases party gold find by 10%.","stacking":"multiplicatief"}],"equipment":"unknown"}],"onzekerheden":[{"wat":"Celeste: specialisatiegroep Keuze 1 (lvl 100) onbekend","gevolg":"Gebruik geen A → B; huidige keuze is niet vastgesteld."},{"wat":"Nayeli: specialisatiegroep Keuze 1 (lvl 100) onbekend","gevolg":"Gebruik geen A → B; huidige keuze is niet vastgesteld."},{"wat":"Equipment-effecten onbekend","gevolg":"Geen gear-buffs meewegen tenzij elders expliciet gegeven."}],"readiness":{"status":"ready","party_legality":"allowed","placement_advice":"sufficient","specialization_advice":"sufficient"}}
```
