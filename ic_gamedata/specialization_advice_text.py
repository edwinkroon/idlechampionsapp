"""Human-readable specialization advice explanations."""

from __future__ import annotations

from ic_gamedata.specialization_models import PendingSpecialization

_FORMATION_REASONS: tuple[tuple[str, str], ...] = (
    ("Bruenor is huidige top damage", "Deze keuze wordt gebruikt omdat Bruenor op dit moment zelf de hoogste damage in de run doet."),
    ("Bruenor bufft de party", "Deze keuze wordt gebruikt omdat Bruenor hier vooral als buffer voor de rest van de party speelt."),
    ("Companions of the Hall", "Deze keuze wordt gebruikt omdat meerdere Companions of the Hall in de actieve formatie staan."),
    ("Catti-brie is huidige top damage", "Deze keuze wordt gebruikt omdat Catti-brie op dit moment zelf de hoogste damage in de run doet."),
    ("Catti-brie ondersteunt push", "Deze keuze wordt gebruikt omdat Catti-brie hier vooral als campaign/push-ondersteuning speelt."),
    ("Widdle dekt de sterkste ability-score groep", "Deze keuze wordt gebruikt omdat de meeste relevante champions in de actieve formatie vooral op STR/DEX leunen."),
    ("Widdle dekt de slimste en taaiste groep", "Deze keuze wordt gebruikt omdat de meeste relevante champions in de actieve formatie vooral op INT/CON leunen."),
    ("Widdle dekt de wijsste en meest charismatische groep", "Deze keuze wordt gebruikt omdat de meeste relevante champions in de actieve formatie vooral op WIS/CHA leunen."),
    ("meer magic dan melee", "Deze keuze wordt gebruikt omdat de actieve formatie meer magic-aanvallers dan melee-aanvallers heeft."),
    ("melee formatie", "Deze keuze wordt gebruikt omdat de actieve formatie vooral op melee-aanvallers leunt."),
    ("magic-aanvallers → Pact of the Tome", "Deze keuze wordt gebruikt omdat de actieve formatie genoeg magic-aanvallers heeft; Pact of the Tome schaalt het sterkst met magic champions."),
    ("familiars → Pact of the Chain", "Deze keuze wordt gebruikt omdat er genoeg familiars aan de actieve party zijn toegewezen; Pact of the Chain schaalt met elke familiar."),
    ("melee-aanvallers → Pact of the Blade", "Deze keuze wordt gebruikt omdat de actieve formatie vooral melee-aanvallers heeft; Pact of the Blade versterkt Folk Hero op melee champions."),
    ("multiplicatief →", "Deze keuze volgt de qualified champions × percentage-regel uit het spel: elke qualified champion vermenigvuldigt de buff, en de optie met de hoogste totale multiplier wint."),
    ("qualified ×", "Deze keuze volgt de qualified champions × percentage-regel: de specialization met de hoogste score wint."),
    ("champions achter KoS → Master of Pawns", "Deze keuze wordt gebruikt omdat meerdere champions in de twee kolommen achter King of Shadows staan; Master of Pawns versterkt Power of the King voor hen."),
    ("KoS als carry / weinig party-buff → Shadow Unleashed", "Deze keuze wordt gebruikt omdat King of Shadows vooral zelf damage draait of weinig allies achter hem heeft; Shadow Unleashed versterkt Phase Three: The Warrior."),
    ("relevante affiliatiegenoten", "Deze keuze wordt gebruikt omdat meerdere Acq Inc-, C-Team- of Waffle Crew-champions in de actieve formatie staan."),
    ("andere tank aanwezig", "Deze keuze wordt gebruikt omdat er al een andere tank in de actieve formatie staat."),
    ("Evelyn tankt vooraan", "Deze keuze wordt gebruikt omdat Evelyn zelf de frontline tank is; Compel Duel versterkt haar Divine Prayer als enemies haar aanvallen."),
    ("evil champions", "Deze keuze wordt gebruikt omdat de actieve formatie meerdere evil champions bevat."),
    ("variant:", "Deze keuze wordt gebruikt in een variant-run omdat meerdere champions profiteren van ability-score swaps via Witch's Switch."),
    ("sterke ability-score swaps", "Deze keuze wordt gebruikt omdat de actieve formatie veel grote verschillen tussen relevante ability-score paren heeft."),
    ("debuff/brake synergie", "Deze keuze wordt gebruikt omdat de actieve formatie al sterk leunt op debuffs."),
    ("algemene debuff/push-keuze", "Deze keuze wordt gebruikt als algemene push-keuze zonder specifieke evil- of stat-swap-synergie."),
    ("weinig healers in party", "Deze keuze wordt gebruikt omdat de actieve formatie weinig dedicated healers heeft."),
    ("voldoende healing beschikbaar", "Deze keuze wordt gebruikt omdat er al voldoende healing in de party zit."),
    ("Nayeli bufft achterliggende champions", "Deze keuze wordt gebruikt omdat Nayeli hier vooral als frontline-buffer voor achterliggende damage speelt."),
    ("Baldur's Gate 3 champions", "Deze keuze wordt gebruikt omdat meerdere Baldur's Gate 3-champions in de actieve formatie staan."),
    ("companion/affiliatie synergie", "Deze keuze wordt gebruikt omdat de actieve formatie veel companion- of affiliatie-synergie heeft."),
    ("human champions", "Deze keuze wordt gebruikt omdat de actieve formatie het best matcht met de ras-synergie van deze specialization."),
    ("dwarf/elf champions", "Deze keuze wordt gebruikt omdat de actieve formatie het best matcht met de ras-synergie van deze specialization."),
    ("short-folk champions", "Deze keuze wordt gebruikt omdat de actieve formatie het best matcht met de ras-synergie van deze specialization."),
    ("exotic champions", "Deze keuze wordt gebruikt omdat de actieve formatie het best matcht met de ras-synergie van deze specialization."),
)


def human_specialization_reason(item: PendingSpecialization, context: dict[str, str | int | None]) -> str:
    if item.desired_option_index is None:
        if item.reason == "regel past niet op deze tier":
            return "Er bestaat al een specialization-regel voor deze champion, maar niet voor deze open tier."
        return "Er is nog geen bruikbare specialization-regel gevonden voor deze champion."

    rationale = item.rationale
    adventure_name = context.get("adventure_name")
    campaign_name = context.get("campaign_name")

    if "adventure-regel" in rationale:
        if isinstance(adventure_name, str) and adventure_name:
            return f"Deze keuze is specifiek ingesteld voor de huidige adventure: {adventure_name}."
        return "Deze keuze is specifiek ingesteld voor de huidige adventure."
    if "campaign-regel" in rationale:
        if isinstance(campaign_name, str) and campaign_name:
            return f"Deze keuze is specifiek ingesteld voor de huidige campaign: {campaign_name}."
        return "Deze keuze is specifiek ingesteld voor de huidige campaign."
    if "locatie-regel" in rationale:
        return "Deze keuze is gekoppeld aan de huidige locatie binnen de campaign."
    if "context-regel" in rationale:
        return "Deze keuze komt uit de actieve context-regel voor deze automation-modus."
    if "formatie-regel" in rationale:
        for needle, message in _FORMATION_REASONS:
            if needle in rationale:
                if needle == "good champions" and "Raistlin" in item.hero_name:
                    continue
                return message
        return "Deze keuze is gekozen op basis van de actieve formatie, champion-profiel en bekende specialization-synergie."
    if "csv-regel" in rationale or "csv-exception" in rationale:
        quality = ""
        if item.rule_source_type == "heuristic":
            quality = " Dit is een generieke placeholder-regel; handmatige review wordt aanbevolen."
        elif item.rule_source_type == "authored":
            quality = " Dit advies volgt een handmatig uitgewerkte champion-regel."
        dataset = item.data_source_version or item.advice_source or "documentation"
        if item.condition_used:
            return (
                f"Deze keuze komt uit de CSV ruleset ({dataset}): "
                f"{item.rationale.split(': ', 1)[-1]}.{quality}"
            )
        return f"Deze keuze komt uit de CSV ruleset in documentation/ ({dataset}).{quality}"
    if "meta-regel" in rationale:
        return "Deze keuze volgt een algemeen aanbevolen community/wiki-default voor deze champion."
    if "default-regel" in rationale:
        if isinstance(campaign_name, str) and campaign_name:
            return f"Er is geen specifiekere regel voor {campaign_name}, daarom wordt de standaardkeuze gebruikt. Dit is meestal de beste algemene keuze."
        return "Er is geen specifiekere regel gevonden, daarom wordt de standaardkeuze gebruikt. Dit is meestal de beste algemene keuze."
    if "basis-regel" in rationale:
        if "speed-profiel" in rationale:
            return "Er is nog geen handgemaakte regel voor deze champion, dus er is een basiskeuze gemaakt die het best past bij een speed-profiel."
        if "gold-profiel" in rationale:
            return "Er is nog geen handgemaakte regel voor deze champion, dus er is een basiskeuze gemaakt die het best past bij een gold-profiel."
        if "tank" in rationale:
            return "Er is nog geen handgemaakte regel voor deze champion, dus er is een basiskeuze gemaakt die het best past bij een tank/support-profiel."
        if "dps" in rationale:
            return "Er is nog geen handgemaakte regel voor deze champion, dus er is een basiskeuze gemaakt die het best past bij een damage-profiel."
        return "Er is nog geen handgemaakte regel voor deze champion, dus er is een voorzichtige basiskeuze gemaakt op basis van rol, tags en option-namen."
    return rationale
