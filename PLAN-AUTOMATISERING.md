# Plan: Automatisering Idle Champions of the Forgotten Realms

## 1. Hoe het spel werkt (technisch)

- **Platform**: Windows (o.a. via Steam), ook beschikbaar op andere platforms.
- **Type**: Desktop-app; ontvangt toetsenbord- en muisinvoer.
- **Besturing**: Het spel reageert op **hotkeys**; er is geen officiële API. Automatisering werkt dus door:
  - het spelvenster te activeren (focus),
  - daarna toetsaanslagen te sturen (bijv. via AutoHotkey of Python met `pyautogui`/`pygetwindow`).

Bestanden in je workspace ontbreken nog; je kunt later een hotkey-overzicht toevoegen (bijv. `hotkeys.txt` of in de README) en het plan daarop laten leunen.

---

## 2. Relevante hotkeys (bron: Fandom Wiki / DefKey)

| Hotkey | Functie |
|--------|---------|
| **G** | Toggle Auto-Progress (aan/uit) |
| **`** (backtick) | Level Click Damage |
| **F1–F12** | Level Champion (F1 = champion 1, … F12 = champion 12) |
| **1–0** | Champion Ultimate gebruiken |
| **Q / W / E** | Formation 1 / 2 / 3 laden |
| **R** | Complete Adventure |
| **Space** | Chests sneller openen |
| **Esc** | Menu sluiten |
| **Left/Right Arrow** | Vorige/volgende area |

Voor jouw wensen zijn vooral belangrijk: **G** (auto progress), **`** (click damage level) en **F1–F12** (champions levelen).

---

## 3. Wat je kunt automatiseren

- **Levelen**
  - Periodiek **F1–F12** (en eventueel **`** voor click damage) sturen zodat champions en click damage blijven levelen.
- **Auto progress weer aanzetten**
  - Na een ingestelde tijd **G** sturen zodat auto progress weer aan staat (als het uit stond).
- **Formation wisselen**
  - **Q / W / E** op vaste tijden of condities.
- **Adventure afronden**
  - **R** sturen (bijv. bij Modron-reset of na een bepaalde tijd).
- **Chests**
  - **Space** herhaaldelijk om chests sneller te openen.
- **Menu’s sluiten**
  - **Esc** om per ongeluk geopende dialogen te sluiten.

Andere opties (minder prioriteit): mute toggle (**U**), UI toggle (**T**), scientific notation (**Y**).

---

## 4. Jouw prioriteiten vertaald naar gedrag

1. **Levelen automatisch**
   - Op een timer (bijv. elke X seconden) een vaste reeks toetsen sturen:
     - **`** (click damage) en **F1** t/m **F12** (of een subset, afhankelijk van je formation).
   - Eventueel alleen de champions die je in de formation hebt (bijv. F1–F6).

2. **Auto progress na een tijd weer aan**
   - Als auto progress uit staat, na een bepaalde tijd weer **G** sturen.
   - **Let op**: **G** is een *toggle*. Eén keer **G** = van uit naar aan (of omgekeerd). Zonder te “weten” of auto progress aan of uit staat, zou je na twee keer dezelfde interval het weer uit kunnen zetten. Daarom:
   - **Optie A (simpel)**: Alleen **G** sturen op een vaste interval (bijv. elke 5 min). Gebruik: “Ik zet auto progress uit; na 5 min zet het script het weer aan.” Nadeel: als je het script langer laat lopen, wordt het na 10 min weer uit gezet.
   - **Optie B (beter)**: Eén keer **G** sturen bij start (om zeker aan te zetten), daarna alleen **G** sturen als we “denken” dat het uit staat (bijv. door pixel/beeldherkenning van de auto-progress-knop). Dat vergt extra implementatie (screenshot + vergelijken).
   - **Praktisch advies**: Begin met Optie A en een ruime interval (bijv. 5–15 min), zodat je in de praktijk meestal “uit → aan” doet. Later kan Optie B toegevoegd worden.

---

## 5. Keuze: Windows-applicatie

Je wilt een **Windows-applicatie**. Twee realistische opties:

### Optie A: AutoHotkey (AHK) – aanbevolen voor alleen toetsen

- **Voordelen**: Lichtgewicht, veel gebruikt voor game-automatisering, weinig dependencies, draait als `.exe` of script.
- **Werking**: Script dat:
  - het Idle Champions-venster zoekt (bijv. op venstertitel),
  - met `WinActivate` focus geeft,
  - met `Send` of `ControlSend` de hotkeys stuurt,
  - timers gebruikt voor levelen en voor “na X minuten G sturen”.
- **Bestaande projecten**: Er bestaan al AHK-scripts voor Idle Champions (bijv. idlecombos, idleChampions-ahk, IdleChampionsSimpleScript); je kunt die als voorbeeld of basis gebruiken.

### Optie B: Python + GUI (bijv. Tkinter/PyQt) als “Windows-app”

- **Voordelen**: Eén executable (met PyInstaller), makkelijk een simpele GUI (knoppen, instellingen, start/stop).
- **Werking**: 
  - `pygetwindow` om het spelvenster te vinden en te activeren,
  - `pyautogui` om toetsen te sturen.
- **Nadeel**: In sommige (fullscreen/directX) games werkt `pyautogui` minder betrouwbaar; voor een venster dat focus krijgt en gewone toetsen ontvangt, werkt het vaak wel.

**Aanbeveling**: Start met **AutoHotkey** voor de kern (levelen + G na X min). Als je later een duidelijke “app” met knoppen en instellingen wilt, kun je:
- een klein AHK-script aanroepen vanuit een Python-GUI, of
- alles in Python doen en testen of toetsen goed aankomen in het spel.

---

## 6. Concreet implementatieplan

### Fase 1: Basis (AHK of Python)

1. **Venster vinden en activeren**
   - Zoek venster op titel (bijv. "Idle Champions" of "Idle Champions of the Forgotten Realms").
   - Voor elke actie: venster activeren, korte `Sleep`, dan toetsen sturen.

2. **Level-automatisering**
   - Timer (bijv. elke 10–30 seconden):
     - Stuur achtereenvolgens: **`** (click damage), **F1**, **F2**, … **F12** (of een configureerbare subset).
   - Optioneel: kleine wachttijd tussen toetsen (bijv. 50–100 ms) zodat het spel niet overspoeld wordt.

3. **Auto progress na X minuten**
   - Startoptie: “Na hoeveel minuten moet G worden gestuurd?” (bijv. 5).
   - Eén timer: elke X minuten **G** sturen (met venster activeren + Sleep + Send G).
   - Documenteer dat G een toggle is (zie sectie 4).

### Fase 2: Uitbreiding

4. **Instelbare opties**
   - Interval levelen (seconden).
   - Interval “G sturen” (minuten).
   - Welke F-toetsen (F1–F12 of subset).
   - Venstertitel of part van titel voor vensterdetectie.

5. **Start/stop**
   - Hotkey of GUI-knop om automatisering te starten en te stoppen (zodat je het spel nog handmatig kunt spelen).

6. **Optioneel: state van auto progress**
   - Screenshot van het gebied van de auto-progress-knop en een eenvoudige check (kleur/pixel) om alleen **G** te sturen als we “uit” detecteren. Dan kun je veilig op een vaste interval alleen “aanzetten”.

### Fase 3: Als “echte” Windows-app

7. **GUI (als je Python kiest)**
   - Checkboxen: “Auto levelen”, “Auto progress na X min”.
   - Velden: interval levelen, interval G, eventueel venstertitel.
   - Start/Stop-knop, minimaliseren naar systray optioneel.

8. **Build**
   - AHK: script als `.ahk` of compileren naar `.exe`.
   - Python: `pyinstaller` voor één `.exe`; AHK kan daarnaast als losse `.exe` blijven.

---

## 7. Samenvatting

| Onderdeel | Aanpak |
|-----------|--------|
| **Hoe het werkt** | Spel reageert op hotkeys; automatisering = venster activeren + toetsen sturen. |
| **Levelen** | Timer: periodiek **`** + **F1**…**F12** (of subset) sturen. |
| **Auto progress weer aan** | Timer: elke X minuten **G** sturen; bewust van toggle-gedrag (of later pixel-check). |
| **Technologie** | Aanbevolen: **AutoHotkey** voor snel resultaat; **Python + pyautogui/pygetwindow** als je een GUI-app wilt. |
| **Volgende stap** | AHK-script of Python-script dat venster vindt, level-timer en “G-na-X-min”-timer implementeert, met instelbare intervallen. |

Als je wilt, kan ik in een volgende stap een concreet **voorbeeldscript** (AHK of Python) voor je projectmap uitschrijven op basis van dit plan.
