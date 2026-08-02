# Idle Champions of the Forgotten Realms – Automatisering

Automatisch levelen en auto progress weer aanzetten voor Idle Champions op Windows.

## Wat het doet

- **Auto levelen**: periodiek toetsen sturen voor click damage (backtick, optioneel) en champions (F11→F1, dan F12).
- **Auto progress**: na een ingestelde tijd toets **G** sturen (toggle).

---

## Aanbevolen: Windows-app (geen AutoHotkey)

Eigen programma met duidelijke stappen en een **Test**-knop.

### Starten

1. **Met Python** (aanbevolen): dubbelklik op `Start Idle Champions App.bat` of voer in een terminal uit:
   ```bash
   pip install -r requirements.txt
   python app_launcher.py
   ```
   Ontwikkelaars: `pip install -r requirements-dev.txt` en daarna `python -m pytest tests` / `python -m ruff check ic_core ic_ui ic_gamedata`.
2. **Zonder Python**: maak eerst een .exe met `build_exe.bat`, daarna kun je `dist\IdleChampionsApp.exe` dubbelklikken.

### Gebruik in de app

1. Start **Idle Champions** en laat het venster open (niet minimaliseren).
2. Vul de **venstertitel** in (deel van de titel is genoeg, bijv. `Idle Champions`).
3. Klik op **Test (vind venster + stuur 1× F1)** – als het venster wordt gevonden en je ziet in het spel dat er geleveld wordt, werkt het.
4. Klik op **Start** om automatisch te levelen. **Stop** om te stoppen.

De app gebruikt **pywin32** (indien geïnstalleerd) voor betere venster-activatie. Installeer met: `pip install -r requirements.txt`.

---

## Optie 2: AutoHotkey

### Vereisten

- [AutoHotkey v2](https://www.autohotkey.com/download/) geïnstalleerd.

### Gebruik

1. Start **Idle Champions** (bijv. via Steam).
2. Dubbelklik op `IdleChampionsAutomation.ahk` of rechtsklik → *Run Script*.
3. Druk op **Ctrl+Alt+A** om automatisering te **starten**; nogmaals **Ctrl+Alt+A** om te **stoppen**.
4. **Test** (als het niet levelt): druk **Ctrl+Alt+T** of **Ctrl+Shift+T** – er verschijnt een **pop-upvenster** in het midden van het scherm met het resultaat (venster gevonden of niet) en de exacte venstertitel; er wordt één keer F12 gestuurd. Kijk in het spel of er geleveld wordt.

### Instellingen aanpassen

Open `IdleChampionsAutomation.ahk` in een teksteditor. Bovenin staan o.a.:

| Variabele | Betekenis | Standaard |
|-----------|-----------|-----------|
| `WindowTitle` | Deel van de venstertitel van het spel | `Idle Champions` |
| `LevelIntervalSeconds` | Elke hoeveel seconden levelen | `20` |
| `AutoProgressIntervalMinutes` | Elke hoeveel minuten toets G | `5` |
| `LevelClickDamage` | Ook backtick (click damage) sturen? `1`=ja, `0`=nee | `1` |
| `LevelChampions` | Welke F-toetsen en in welke volgorde; standaard `12,11,…,1` (F12 eerst) | bv. `12,11,10,9,8,7,6` |

Na wijziging het script opnieuw starten (of herladen).

### .exe maken (optioneel)

- Rechtsklik op het `.ahk`-bestand → *Compile Script* (als je de AHK-compiler hebt geïnstalleerd). Je krijgt een losse `.exe` die je zonder AutoHotkey kunt draaien.

---

## Oude Python-GUI (legacy)

De tkinter-app staat in `legacy/idle_champions_automation_tk.py`. Het rootbestand `idle_champions_automation.py` stuurt door naar **`app_launcher.py`**. `idle_champions_gamedata.py` is een compatibiliteitsshim — gebruik **`app_launcher.py`** / de PySide6-app.

---

## Let op: Auto progress (toets G)

**G** is een **toggle**: één keer G = aan → uit of uit → aan. Het script “weet” niet of auto progress aan of uit staat.

- Gebruik een **ruime interval** (bijv. 5–15 min) zodat je in de praktijk meestal “uit → aan” doet.
- Als het script langer draait dan twee keer die interval, kan het na de tweede keer G weer uit gaan. Zet dan handmatig weer aan of stop het script even.

---

## Bestanden

| Bestand | Beschrijving |
|---------|--------------|
| **`app_launcher.py`** | Start de PySide6-app (dashboard, analytics, party advisor, automatisering). |
| **`ic_ui/pyside_app.py`** | Hoofdvenster: tab-wiring en gecentraliseerde API-poll. |
| **`ic_ui/tabs/`** | UI-tabs (dashboard, analytics, advisor, specializations, automation, sources). |
| **`ic_core/game_state.py`** | Gedeelde live speldata (GameStateService). |
| **`Start Idle Champions App.bat`** | Start de app (installeert dependencies indien nodig). |
| **`build_exe.bat`** | Maakt `IdleChampionsApp.exe` (geen Python nodig om te draaien). |
| `ic_gamedata/` | Spelpad-detectie, stats, party advisor domain. |
| `requirements.txt` | Runtime-dependencies (PySide6, pyqtgraph, pyautogui, …). |
| `requirements-dev.txt` | pytest + ruff voor ontwikkeling/CI. |
| `.github/workflows/ci.yml` | GitHub Actions: tests + lint op `ic_core` / `ic_ui`. |
| `PLAN-AUTOMATISERING.md` | Uitgebreid plan en achtergrond. |

---

## Hoe weet ik of het goed runt?

- **AutoHotkey**: Na **Ctrl+Alt+A** zie je een melding "Automatisering GESTART". De **eerste level-ronde** gebeurt meteen, daarna elke X seconden (standaard **20**). Het spelvenster moet zichtbaar zijn (niet geminimaliseerd); je ziet dan de F12→F1-toetsen (en eventueel backtick) in het spel.
- **Python**: Klik op **Start** → status wordt "Status: actief". De eerste level-ronde loopt kort na start, daarna elke X seconden (standaard **20**).

**Om de hoeveel tijd levelt het?** Standaard **elke 20 seconden**. Je kunt dat aanpassen:
- **AHK**: in het script `LevelIntervalSeconds := 20` (of bijvoorbeeld `10`) wijzigen.
- **Python**: in de GUI het veld "Level-interval (seconden)" (bijv. `10` of `15`).

Tip: zet het interval tijdelijk op **5** seconden om te controleren of de toetsen in het spel aankomen.

---

## Problemen

- **Venster wordt niet gevonden**: gebruik **Ctrl+Alt+T** (AHK) om te zien welke titel het script zoekt. Controleer de venstertitel (taakbalk of Alt+Tab). Pas `WindowTitle` (AHK) of “Venstertitel” (Python) aan zodat het een deel van die titel is (bijv. `Idle Champions of the Forgotten Realms`).
- **Toetsen komen niet aan (script draait wel)**: (1) Zorg dat het spelvenster **niet geminimaliseerd** is. (2) Als het spel **als administrator** draait, start dan ook AutoHotkey als administrator (rechtsklik het .ahk-bestand → *Als administrator uitvoeren*). (3) Sluit overlays (Discord, Steam) of zet het spel in **venstermodus** i.p.v. fullscreen.
- **Python: “pygetwindow” of “pyautogui” niet gevonden**: voer uit: `pip install -r requirements.txt`
