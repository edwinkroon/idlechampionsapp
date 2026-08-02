# Idle Champions of the Forgotten Realms – Companion App

Dashboard, analytics, party advisor en automatisering voor Idle Champions op Windows.

## Starten

```bash
pip install -r requirements.txt
python app_launcher.py
```

Of dubbelklik op `Start Idle Champions App.bat`.

- **Zonder Python:** bouw met `build_exe.bat`, start daarna `dist\IdleChampionsApp.exe`.
- **Versie:** Help → Over Idle Champions App… in het menu.
- **Dev:** `pip install -r requirements-dev.txt` → `python -m pytest tests` / `python -m ruff check ic_core ic_ui ic_gamedata`.

## Projectstructuur

```
app_launcher.py          # start PySide6-app
main.py                  # CLI memory reader (area watch)
Start Idle Champions App.bat / build_exe.bat

ic_ui/                   # PySide6 UI (tabs, workers, widgets)
ic_core/                 # live services (game data poll, memory, game state)
ic_gamedata/             # domain: API, advisors, specs, stats, parsing
ic_reader/               # read-only process memory
ic_automation/           # Windows input / auto-level controller

config/                  # runtime + rules JSON (machine-local files gitignored)
documentation/           # CSV rulesets (bundled in the exe)
data/                    # guide dumps used for role advice
tests/                   # pytest (+ fixtures/)
scripts/                 # offline maintenance (advice/, scrapers)
```

## Gebruik (kort)

1. Start **Idle Champions** (venster niet minimaliseren).
2. Open de app → Dashboard haalt partydata op via de game-API / log.
3. **Automatisering**-tab: Test (venster + 1× F1), daarna Start/Stop voor auto-level / auto-progress (G).

**Let op:** toets **G** is een toggle (aan/uit). Gebruik een ruime interval (5–15 min).

## Belangrijke bestanden

| Pad | Rol |
|-----|-----|
| `app_launcher.py` | Officiële start |
| `ic_ui/pyside_app.py` | Hoofdvenster + service-wiring |
| `ic_core/game_data_service.py` | Enige API-poll owner (retry / degraded) |
| `ic_gamedata/` | Domainlogica (advisors, specializations, stats) |
| `requirements.txt` | Runtime deps |
| `.github/workflows/ci.yml` | Tests + lint |

## Problemen

- **Venster niet gevonden:** titel moet `Idle Champions` bevatten.
- **Toetsen komen niet aan:** spel niet geminimaliseerd; bij admin-game ook de app als admin; overlays uit / venstermodus.
- **Python-deps:** `pip install -r requirements.txt`
