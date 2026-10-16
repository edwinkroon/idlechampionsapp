"""Human-readable specialization advice explanations."""

from __future__ import annotations

from ic_gamedata.specialization_models import PendingSpecialization

_FORMATION_REASONS: tuple[tuple[str, str], ...] = (
    ("Bruenor is current top damage", "This choice is used because Bruenor is currently dealing the highest damage in the run."),
    ("Bruenor buffs the party", "This choice is used because Bruenor mainly acts as a buffer for the rest of the party here."),
    ("Companions of the Hall", "This choice is used because multiple Companions of the Hall are in the active formation."),
    ("Catti-brie is current top damage", "This choice is used because Catti-brie is currently dealing the highest damage in the run."),
    ("Catti-brie supports push", "This choice is used because Catti-brie mainly supports campaign/push here."),
    ("Widdle covers the strongest ability-score group", "This choice is used because most relevant champions in the active formation lean on STR/DEX."),
    ("Widdle covers the smartest and toughest group", "This choice is used because most relevant champions in the active formation lean on INT/CON."),
    ("Widdle covers the wisest and most charismatic group", "This choice is used because most relevant champions in the active formation lean on WIS/CHA."),
    ("more magic than melee", "This choice is used because the active formation has more magic attackers than melee attackers."),
    ("melee formation", "This choice is used because the active formation mainly relies on melee attackers."),
    ("magic attackers → Pact of the Tome", "This choice is used because the active formation has enough magic attackers; Pact of the Tome scales best with magic champions."),
    ("familiars → Pact of the Chain", "This choice is used because enough familiars are assigned to the active party; Pact of the Chain scales with each familiar."),
    ("melee attackers → Pact of the Blade", "This choice is used because the active formation mainly has melee attackers; Pact of the Blade strengthens Folk Hero on melee champions."),
    ("BUD/top damage is melee", "This choice matches Ruby Weakness on melee because your BUD/top damage attacks with melee — monsters then take 100% more melee damage."),
    ("BUD/top damage is ranged", "This choice matches Ruby Weakness on ranged because your BUD/top damage attacks with ranged — monsters then take 100% more ranged damage."),
    ("BUD/top damage is magic", "This choice matches Ruby Weakness on magic because your BUD/top damage attacks with magic — monsters then take 100% more magic damage."),
    ("melee attackers → Ruby Weakness", "This choice is used because the active formation mainly has melee attackers; Ruby Weakness (Melee) makes enemies take more melee damage."),
    ("ranged attackers → Ruby Weakness", "This choice is used because the active formation mainly has ranged attackers; Ruby Weakness (Ranged) makes enemies take more ranged damage."),
    ("magic attackers → Ruby Weakness", "This choice is used because the active formation mainly has magic attackers; Ruby Weakness (Magic) makes enemies take more magic damage."),
    ("BUD is in front of Regis → Ahead", "This choice buffs the column in front of Regis because your BUD is placed there."),
    ("BUD is behind Regis → Behind", "This choice buffs the column behind Regis because your BUD is placed there."),
    (
        "BUD shares Vlahnya's column → Spy Network",
        "Spy Network is required here: Enthralling Performance only hits columns ahead of Vlahnya unless Spy Network also covers her own column, and your BUD stands with her.",
    ),
    (
        "Vlahnya's column has ≤2 champions → Breaking Out Solo",
        "Breaking Out Solo is used because Vlahnya's column has at most two champions, so the +200% Enthralling Performance bonus applies while she still buffs columns ahead.",
    ),
    (
        "Vlahnya's column is crowded → Spy Network",
        "Spy Network is used because Vlahnya's column has more than two champions, so Breaking Out Solo's +200% bonus would not apply; Spy Network at least extends her buff to that column.",
    ),
    ("BUD is beside Korth → Samurai Training (Beside)", "Samurai Training (Beside) is used because your BUD sits adjacent to Korth."),
    ("BUD is in front of Korth → Samurai Training (In Front)", "Samurai Training (In Front) is used because your BUD stands in a column ahead of Korth."),
    ("BUD is behind Korth → Samurai Training (Behind)", "Samurai Training (Behind) is used because your BUD stands in a column behind Korth."),
    ("BUD shares Ezmerelda's column → Vampire Hunter", "Vampire Hunter is used because your BUD shares Ezmerelda's column."),
    ("BUD not in Ezmerelda's column → We've Trained For This", "We've Trained For This is used because your BUD is not in Ezmerelda's column."),
    ("Turiel is frontline → Voice of Resilience", "Voice of Resilience is used because Turiel is seated on the front line."),
    ("Turiel not frontline → Voice of Authority", "Voice of Authority is used because Turiel is not on the front line."),
    ("Tyril is frontline → Wild Shape", "Wild Shape is used because Tyril is seated as a frontline tank."),
    ("Tyril not frontline → Moonbeam", "Moonbeam is used because Tyril is not on the front line."),
    ("BUD is adjacent to Alyndra → Expansive Vision", "Expansive Vision is used because your BUD sits adjacent to Alyndra."),
    ("BUD not adjacent to Alyndra → Extra Judgy", "Extra Judgy is used because your BUD is not adjacent to Alyndra."),
    ("Vin Ursa frontline → Front Deck", "Front Deck is used because Vin Ursa is seated on the front line."),
    ("Vin Ursa backline → Rear Deck", "Rear Deck is used because Vin Ursa is seated on the back line."),
    ("tank adjacent to Jamilah → Bruiser", "Bruiser is used because at least one tank sits adjacent to Jamilah."),
    ("no adjacent tanks → Indomitable Might", "Indomitable Might is used because no tank sits adjacent to Jamilah."),
    ("Cazrin is current top damage → Signature Smell", "This choice is for DPS Cazrin: Signature Smell sends Uggie's buffs to Cazrin instead of the rest of the party."),
    ("Cazrin as support → Smell Mastery", "This choice is for support Cazrin: Smell Mastery doubles the per-Book bonus from In Search of Knowledge on Sunny Disposition."),
    ("multiplicative →", "This choice follows the qualified champions × percentage rule from the game: each qualified champion multiplies the buff, and the option with the highest total multiplier wins."),
    ("qualified ×", "This choice follows the qualified champions × percentage rule: the specialization with the highest score wins."),
    ("More Damage (quick power)", "This choice is Umberto's quick power spec: More Damage strengthens Detective's Entourage immediately (Gaarawarr)."),
    ("More Bees (tank spec)", "This choice is Umberto's tank spec: More Bees strengthens Beehive Barrage against attacking enemies."),
    ("champions behind KoS → Master of Pawns", "This choice is used because multiple champions stand in the two columns behind King of Shadows; Master of Pawns strengthens Power of the King for them."),
    ("KoS as carry / little party buff → Shadow Unleashed", "This choice is used because King of Shadows mainly carries damage or has few allies behind him; Shadow Unleashed strengthens Phase Three: The Warrior."),
    ("relevant affiliation allies", "This choice is used because multiple Acq Inc, C-Team, or Waffle Crew champions are in the active formation."),
    ("another tank present", "This choice is used because another tank is already in the active formation."),
    ("Evelyn tanks up front", "This choice is used because Evelyn is the frontline tank; Compel Duel strengthens her Divine Prayer when enemies attack her."),
    ("Tatyana present → My Loyal Bodyguard", "This choice is used because Tatyana is in the formation; My Loyal Bodyguard strengthens Faithful Friend by 200%."),
    ("no Tatyana → All Hail the God Brain", "This choice is used because Tatyana is not in the formation; All Hail the God Brain strengthens Tregrum's pre-stack damage without that synergy."),
    ("evil champions", "This choice is used because the active formation contains multiple evil champions."),
    ("evil → The Dark Hunger", "This choice raises the max number of Accursed Specters to the number of evil champions in your formation."),
    ("DEX≥16 → Shadows in the Night", "This choice raises the max number of Accursed Specters to the number of champions with DEX 16+ in your formation."),
    ("CHA highest → Charm of the Fallen", "This choice raises the max number of Accursed Specters to the number of champions with Charisma as their highest ability score."),
    ("no specter data; default The Dark Hunger", "No usable alignment/ability counts available; fallback is the guide default The Dark Hunger."),
    ("variant:", "This choice is used in a variant run because multiple champions benefit from ability-score swaps via Witch's Switch."),
    ("strong ability-score swaps", "This choice is used because the active formation has many large gaps between relevant ability-score pairs."),
    ("debuff/brake synergy", "This choice is used because the active formation already relies heavily on debuffs."),
    ("general debuff/push choice", "This choice is used as a general push choice without specific evil or stat-swap synergy."),
    ("few healers in party", "This choice is used because the active formation has few dedicated healers."),
    ("enough healing available", "This choice is used because the party already has enough healing."),
    ("gold farm → Craft Maker", "This choice is used for gold farming: Craft Maker grants Flint the Gold role and scales Gold Find with enemy max HP."),
    ("Flint is BUD/top damage → Life Taker", "This choice is used because Flint is the BUD/top damage dealer; Life Taker turns him into a DPS scaled by Forged Bonds stacks."),
    ("speed goal → Foe Breaker", "This choice is used for speed runs: Foe Breaker helps clear armored/segmented HP without switching Flint onto a gold specialization."),
    ("push/support → Foe Breaker", "This choice is used for push/support: Foe Breaker lets Forged Bonds targets strip extra armored/segmented/critical HP."),
    ("BUD hit", "This choice stacks Raise Spirits on your BUD/top damage the most times, using Caramon plus recruited allies as extra emanation sources."),
    ("Good allies", "This choice recruits Good champions so Raise Spirits also emanates from them; that typically covers the BUD more often than tank-only Staunch Allies."),
    ("Nayeli buffs back-line champions", "This choice is used because Nayeli mainly acts as a frontline buffer for back-line damage here."),
    ("Baldur's Gate 3 champions", "This choice is used because multiple Baldur's Gate 3 champions are in the active formation."),
    ("companion/affiliation synergy", "This choice is used because the active formation has strong companion or affiliation synergy."),
    ("human champions", "This choice is used because the active formation best matches this specialization's race synergy."),
    ("dwarf/elf champions", "This choice is used because the active formation best matches this specialization's race synergy."),
    ("short-folk champions", "This choice is used because the active formation best matches this specialization's race synergy."),
    ("exotic champions", "This choice is used because the active formation best matches this specialization's race synergy."),
    (
        "no seat data → Scent: Herbs and Spices",
        "Seat positions are missing, so Meat Sauce's distance curve cannot be scored. Herbs and Spices stays the default.",
    ),
    (
        "tanking champions → Scent: Herbs and Spices",
        "Herbs and Spices is used because each tanking champion multiplies Roasted Vegetables by 50%, and that beats changing Meat Sauce's distance curve for the Supports here.",
    ),
    (
        "→ Scent: Roasted Chicken",
        "Roasted Chicken is used because the Support champions sit far enough that Meat Sauce's new distance curve beats the tank multiplier from Herbs and Spices.",
    ),
)


def _blob(item: PendingSpecialization) -> str:
    return f"{item.reason} {item.rationale}".casefold()


def _insufficient_data_message(item: PendingSpecialization) -> str:
    text = _blob(item)
    if "alignment" in text or "str data" in text:
        return (
            "Not enough champion data (alignment and STR) to score this specialization. "
            "No recommendation is made until that information is available."
        )
    if "no seat" in text or "seat data" in text:
        if item.desired_option_index is not None:
            return (
                "Seat positions are missing, so Raise Spirits geometry cannot be scored. "
                "The Allies pick is based only on who qualifies in the party."
            )
        return (
            "Seat positions are missing, so this specialization cannot be scored. "
            "No recommendation is made from option order."
        )
    if "no formation signal" in text:
        return (
            "There is not enough formation information to choose a specialization. "
            "No guess is made from the first listed option."
        )
    return (
        "There is not enough information to choose a specialization. "
        "No recommendation is made."
    )


def human_specialization_reason(item: PendingSpecialization, context: dict[str, str | int | None]) -> str:
    if "insufficient data" in _blob(item):
        return _insufficient_data_message(item)
    if item.desired_option_index is None:
        if item.reason == "rule does not apply to this tier":
            return "A specialization rule already exists for this champion, but not for this open tier."
        return "No usable specialization rule has been found for this champion yet."

    rationale = item.rationale
    adventure_name = context.get("adventure_name")
    campaign_name = context.get("campaign_name")

    if "adventure rule" in rationale:
        if isinstance(adventure_name, str) and adventure_name:
            return f"This choice is configured specifically for the current adventure: {adventure_name}."
        return "This choice is configured specifically for the current adventure."
    if "campaign rule" in rationale:
        if isinstance(campaign_name, str) and campaign_name:
            return f"This choice is configured specifically for the current campaign: {campaign_name}."
        return "This choice is configured specifically for the current campaign."
    if "location rule" in rationale:
        return "This choice is tied to the current location within the campaign."
    if "context rule" in rationale:
        return "This choice comes from the active context rule for this automation mode."
    if "formation rule" in rationale:
        chosen_name = ""
        if item.desired_option_index is not None and item.desired_option_index < len(
            item.options
        ):
            chosen_name = item.options[item.desired_option_index].name

        # Multi-tier handlers (e.g. Cazrin) embed several reasons in one string.
        # Prefer the needle that names the open tier's chosen option.
        if chosen_name:
            for needle, message in _FORMATION_REASONS:
                if needle in rationale and chosen_name in needle:
                    return message

        for needle, message in _FORMATION_REASONS:
            if needle not in rationale:
                continue
            if needle == "good champions" and "Raistlin" in item.hero_name:
                continue
            # Skip option-specific needles that belong to a different choice.
            if chosen_name and "→" in needle:
                tail = needle.split("→", 1)[-1].strip()
                if (
                    tail
                    and tail.casefold() != chosen_name.casefold()
                    and tail in rationale
                ):
                    continue
            return message
        return "This choice was made based on the active formation, champion profile, and known specialization synergy."
    if "csv rule" in rationale or "csv-exception" in rationale:
        quality = ""
        if item.rule_source_type == "heuristic":
            quality = " This is a generic placeholder rule; manual review is recommended."
        elif item.rule_source_type == "authored":
            quality = " This advice follows a hand-authored champion rule."
        dataset = item.data_source_version or item.advice_source or "documentation"
        if item.condition_used:
            return (
                f"This choice comes from the CSV ruleset ({dataset}): "
                f"{item.rationale.split(': ', 1)[-1]}.{quality}"
            )
        return f"This choice comes from the CSV ruleset in documentation/ ({dataset}).{quality}"
    if "meta rule" in rationale:
        return "This choice follows a generally recommended community/wiki default for this champion."
    if "default rule" in rationale:
        if isinstance(campaign_name, str) and campaign_name:
            return f"No more specific rule exists for {campaign_name}, so the default choice is used. This is usually the best general pick."
        return "No more specific rule was found, so the default choice is used. This is usually the best general pick."
    if "baseline rule" in rationale:
        if "speed profile" in rationale:
            return "No hand-authored rule exists for this champion yet, so a baseline choice was made that best fits a speed profile."
        if "gold profile" in rationale:
            return "No hand-authored rule exists for this champion yet, so a baseline choice was made that best fits a gold profile."
        if "tank" in rationale:
            return "No hand-authored rule exists for this champion yet, so a baseline choice was made that best fits a tank/support profile."
        if "dps" in rationale:
            return "No hand-authored rule exists for this champion yet, so a baseline choice was made that best fits a damage profile."
        return "No hand-authored rule exists for this champion yet, so a cautious baseline choice was made from role, tags, and option names."
    return rationale
