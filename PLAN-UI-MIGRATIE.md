# Migratieplan: UI-stabiliteit & polish (Idle Champions App)

**Doel:** scrollen en UI soepel houden terwijl automatisering draait, en de app er minder “slordig” uit laten zien — zonder de domainlogica (`ic_gamedata`, `ic_reader`) of SendInput-automation te verliezen.

**Kernprobleem:** één tkinter-eventloop doet tegelijk UI (scroll, advisor-render) én automation (`root.after` voor auto-click ~10/s, levelen, abilities, …). Dat is structureel.

**Aanbevolen eindbeeld:**

```
┌─────────────────────────────┐     signals / queue      ┌──────────────────────────┐
│  UI process (PySide6)       │ ◄──────────────────────► │  Automation worker        │
│  - tabs, scroll areas       │                          │  - timers, SendInput      │
│  - advisor, dashboard       │                          │  - geen UI-widgets        │
│  - settings                 │                          │  - status events naar UI  │
└─────────────────────────────┘                          └──────────────────────────┘
              │                                                      │
              └────────── shared: ic_gamedata / ic_reader / config ──┘
```

PyInstaller-exe mag blijven; de toolkit en thread-grens veranderen.

---

## Uitgangspunten (niet onderhandelen)

1. **Domaincode blijft Python** — geen port van specialization/seat advisor naar C#/JS in fase 1–3.
2. **Automation blijft Win32 SendInput/scancodes** — browser/Electron stuurt geen betrouwbare game-input.
3. **UI-thread mag geen key-bursts of klikloops doen** — alleen status tonen en settings wijzigen.
4. **Gefaseerd leveren** — elke fase is alleen shippable als acceptance criteria groen zijn.
5. **Geen “big bang rewrite”** van `idle_champions_app.py` in één PR.

---

## Fase 0 — Baseline & meetlat (½–1 dag)

### Doel
Weten wat “beter” is, en regressies kunnen vangen.

### Acties
- [ ] Noteer huidige pijnpunten in een korte checklist (scroll Instellingen, scroll Advisor, auto-click aan, tab-wissel).
- [ ] Voeg een debug-toggle of logregel toe: aantal actieve `after`-timers + laatste UI-frame tijd (optioneel; mag tijdelijk).
- [ ] Lijst alle timers in `IdleChampionsApp`: level, grave, abilities, specializations, auto_click, dash_poll.
- [ ] Bevries gedrag: bestaande tests (`test_seat_advisor`, `test_specializations`, party/formation) moeten blijven groen na elke fase.

### Acceptance
- Documenteerde “repro”-stappen voor scroll-bug (automation aan → Advisor/Instellingen scrollen).
- Timer-inventaris klaar.

### Risico
Laag. Geen productiewijziging verplicht.

---

## Fase 1 — Automation van de UI-thread af (1–2 dagen)  ← **DONE 2026-07-29**

### Doel
Scrollproblemen grotendeels oplossen **zonder** toolkit te wisselen.

### Opgeleverd
- Package `ic_automation/` (`settings`, `win_input`, `worker`, `controller`)
- Level / grave / abilities / auto-progress / auto-click draaien in daemon-thread
- Specialization blijft tijdelijk op UI `after` (API + labels)
- Live settings via immutable `AutomationSettings` snapshot
- Status via queue → UI poll 250ms
- Formatie F-key sync elke 5s op UI-thread, daarna settings push
- Tests: `tests/test_automation_worker.py`

### Architectuur
Nieuw module-voorstel: `ic_automation/` (of `idle_champions_automation_core.py`):

| Component | Verantwoordelijkheid |
|-----------|----------------------|
| `AutomationController` | start/stop, settings snapshot, welke features aan staan |
| `AutomationWorker` (thread) | eigen sleep/timers; stuurt keys/clicks |
| `UiBridge` | `queue.Queue` of callbacks via `root.after(0, …)` alleen voor statuslabels |

UI (`IdleChampionsApp`) doet alleen:
- Start/Stop → controller
- Settings wijzigen → immutable settings-object naar worker
- Status ontvangen → labels updaten (throttle: max 4×/s)

### Concreet uit `idle_champions_app.py` verplaatsen
- `schedule_level`, `schedule_grave`, `schedule_abilities`, `schedule_specializations`, `schedule_auto_click`
- SendInput-helpers die nu tijdens `after` draaien
- **Niet** verplaatsen: advisor-render, dashboard-poll UI (die eerst alleen throttlen)

### Regels worker-thread
- Geen tkinter-calls vanuit de worker.
- Geen `update_idletasks()` in de hot path.
- Auto-click: sleep op basis van CPS in de worker, niet `after(100)` op de root.
- Capslock / hover-guards: periodiek in worker evalueren (win32), resultaat als flag.

### Acceptance
- [ ] Met auto-click 10/s + levelen aan: Instellingen- én Advisor-scroll voelen normaal (handmatige check).
- [ ] Start/Stop en checkbox-wijzigingen werken live zoals nu.
- [ ] Geen tkinter calls vanuit worker (code review / grep).
- [ ] Bestaande unit tests groen; handmatige Test-knop (F1) werkt nog.

### Risico’s & mitigatie
| Risico | Mitigatie |
|--------|-----------|
| Race op settings | settings als immutable dataclass + lock of “replace snapshot” |
| Dubbele timers bij herstart | expliciete stop-join van worker voor start |
| Specialization-check heeft UI-state nodig | worker vraagt alleen “moet ik checken?”; resultaat via queue; of specialization blijft tijdelijk op UI-thread tot fase 2 |

### Wat je níet doet in fase 1
- Geen PySide, geen restyling, geen tabs herschrijven.

---

## Fase 2 — UI-render ontkoppelen & advisor lichter maken (1–2 dagen)

### Doel
Minder jank bij Party Advisor / Dashboard terwijl automation draait.

### Acties
- [ ] Advisor: volledige rebuild alleen bij analyse-resultaat of role-change — niet bij elke dash-poll.
- [ ] Dashboard-poll: UI-update max 1×/s; data ophalen mag in thread + queue.
- [ ] Scroll: `bind_all("<MouseWheel>")` vervangen door bind op de scrollable containers alleen (minder conflicten).
- [ ] `update_idletasks()` audit: verwijderen uit automation-paden (zou al weg moeten na fase 1); elders minimaliseren.
- [ ] Optioneel: virtuele/lazy seat-cards (alleen zichtbare seats) — alleen als Advisor nog zwaar voelt.

### Acceptance
- [ ] Analyse-klik < ~1s voor typische party (subjectief ok); UI blijft responsive.
- [ ] Geen volledige advisor-wipe bij dashboard-tick.
- [ ] Scroll zonder global bind_all werkt op beide tabs.

### Risico
Advisor-state (open feats-panels) verliezen bij re-render — bewaar expand-state per hero_id.

---

## Fase 3 — Toolkit-migratie naar PySide6 (3–6 dagen)

### Doel
Native scroll areas, modernere look, langetermijn onderhoud.

### Waarom PySide6 (niet Electron / niet alleen CustomTkinter)
- Echte `QScrollArea` (geen Canvas-hack).
- Signals/slots passen bij worker uit fase 1.
- Blijft één Python-stack + PyInstaller.
- CustomTkinter lost thread/scroll fundamenteel niet op.

### Migratievolgorde (tabs één voor één)

| Stap | Tab / oppervlak | Aanpak |
|------|-----------------|--------|
| 3.0 | Shell | `QMainWindow` + `QTabWidget`; start app naast of i.p.v. tk root via feature-flag `IC_UI=pyside` |
| 3.1 | Automatisering | settings form + Start/Stop; praat met bestaande `AutomationController` |
| 3.2 | Dashboard | labels + timers; zelfde gamedata-API |
| 3.3 | Bronnen | simpele form |
| 3.4 | Party Advisor | seat cards in `QScrollArea`; feats als `QToolBox`/`QTreeWidget`; bron-knoppen `QDesktopServices.openUrl` |
| 3.5 | Formatie-visual | `QGraphicsView` of behoud HTML via `QWebEngine`/`QTextBrowser` alleen als nodig |
| 3.6 | Verwijder tkinter UI | `idle_champions_app.py` wordt dunne launcher of verdwijnt |

### Designrichting (licht, geen redesign-project)
- Consistente margins (8/12/16), één font-stack (Segoe UI Variable / Segoe UI).
- Cards = `QFrame` + stylesheet, geen 5 lagen nested LabelFrames.
- Statusbalk onderaan voor automation-state (running / caps / hover-blocked).

### Packaging
- [ ] `requirements.txt`: `PySide6` toevoegen; tkinterweb alleen houden tot 3.5 klaar is.
- [ ] `IdleChampionsApp.spec` / hiddenimports voor PySide6 plugins (platforms, styles).
- [ ] Smoke-test: exe start op schone Windows-VM.

### Acceptance
- [ ] Alle vier tabs functioneel gelijkwaardig aan huidige app.
- [ ] Scroll Instellingen + Advisor soepel met automation aan.
- [ ] Feature-flag of default: PySide is de normale UI.
- [ ] Tests voor domain ongewijzigd groen; UI smoke-test (start window, click analyze) gedocumenteerd.

### Risico’s
| Risico | Mitigatie |
|--------|-----------|
| Spec/binary groter | acceptabel; strip unused Qt modules in spec indien nodig |
| Parallel tk + Qt verwarring | korte overlap met env-flag; daarna tk verwijderen |
| Styling tijdrovend | eerst functioneel, stylesheet in tweede PR |

---

## Fase 4 — Polish & opschonen (1–2 dagen)

### Acties
- [ ] Verwijder dode tk-scroll helpers (`_on_global_mousewheel`, canvas-settings hacks) als tk weg is.
- [ ] Split UI in packages: `ic_ui/automation_tab.py`, `dashboard_tab.py`, `advisor_tab.py`.
- [ ] Update README: stack = Python + PySide6 + automation worker; AHK blijft optioneel fallback.
- [ ] Archiveer of markeer `idle_champions_automation.py` (oude GUI) als legacy.

### Acceptance
- [ ] README klopt met echte startpaden.
- [ ] Geen dubbele entrypoints die gebruikers verwarren (één aanbevolen).

---

## Wat we bewust níet doen (nu)

| Idee | Waarom niet (nu) |
|------|------------------|
| Electron / Tauri frontend | Extra runtime; automation moet tóch native sidecar blijven |
| Volledige C# rewrite | Domain + tests herschrijven; te groot voor het probleem |
| Alleen CustomTkinter/ttkbootstrap | Cosmetisch; lost main-thread automation niet op |
| Automation in AHK + UI in Python zonder gedeelde controller | Twee bronnen van waarheid voor settings/timers |
| Big-bang “herscrijf heel `idle_champions_app.py`” | Hoog regressierisico; moeilijk te reviewen |

---

## Suggestie: PR-splitsing

1. **PR1 — Automation worker** (fase 1) — gedrag gelijk, scroll beter.
2. **PR2 — Advisor/dashboard render throttle** (fase 2).
3. **PR3 — PySide shell + Automatisering-tab** (fase 3.0–3.1).
4. **PR4 — Dashboard + Bronnen** (3.2–3.3).
5. **PR5 — Party Advisor + cleanup tk** (3.4–3.6 + fase 4).

Elke PR mergebaar en testbaar zonder de volgende.

---

## Effort-inschatting (één developer, bekend met de codebase)

| Fase | Effort | Gebruikerswaarde |
|------|--------|------------------|
| 0 Baseline | 0.5 d | meten |
| 1 Worker-thread | 1–2 d | **groot** (scroll + soepelheid) |
| 2 Lichtere UI-updates | 1–2 d | merkbaar |
| 3 PySide6 | 3–6 d | look + onderhoudige scroll |
| 4 Cleanup | 1–2 d | onderhoud |
| **Totaal** | **~7–12 dagen** | |

Als je maar één ding doet: **fase 1**. Dat adresseert jouw concrete klacht (“scrollen stuk bij automation”) het meest direct.

---

## Beslispunten voor jou (vóór start fase 3)

1. **Default UI na migratie:** meteen PySide, of tijdelijk flag?
2. **Exe-grootte:** PySide ~+50–100MB acceptabel?
3. **Look:** “functioneel netjes” (fase 3) vs. latere design-pass?
4. **AHK:** behouden als noodoptie in README, of deprioriteren?

---

## Definition of Done (eindprogramma)

- [ ] Automation draait niet op de UI-thread.
- [ ] Scrollen op Instellingen en Party Advisor blijft bruikbaar bij auto-click + levelen.
- [ ] UI gebruikt native scroll (PySide `QScrollArea`), geen Canvas-yscroll hack als primary path.
- [ ] `ic_gamedata` / specialization / seat advisor ongewijzigd in verantwoordelijkheid (hoogstens dunne adapters).
- [ ] Eén duidelijke startroute (bat/exe) in README.
- [ ] Domain-tests groen; handmatige smoke-checklist gedocumenteerd.

---

## Eerste implementatiestap (zodra je “go” geeft op fase 1)

1. Maak `ic_automation/controller.py` + `worker.py` met settings-dataclass.
2. Verplaats auto-click + grave als eerste (hoogste timer-frequentie).
3. Houd level/abilities/specialization tijdelijk op `after` óf verplaats meteen mee als de bridge stabiel is.
4. Meet handmatig: automation aan → scroll Advisor 20 seconden — moet vloeiend blijven.

Dit plan is de leidraad; fase 1 kan zonder UI-rewrite morgen al waarde leveren.
