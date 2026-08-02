# Plan: Gem Farm Intelligence (initiatieven #5, #2, #1)

**Doel:** drie onderling verbonden features bouwen voor gem farm / Modron-spelers:

| # | Initiatief | Kort |
|---|------------|------|
| 5 | **Farm Health Monitor** | Detecteer degradatie en toon in-app alerts |
| 2 | **Briv & Gem Farm Intelligence** | Stack-zone / reset-advies op basis van live Briv-gear + history |
| 1 | **Modron / Gem Farm Co-Pilot** | Observeer fases, adviseer, optioneel Q/W/E/G sturen |

**Waarom deze volgorde:** #5 valideert data en levert direct nut; #2 geeft oorzaken en parameters; #1 handelt pas als observe + advise betrouwbaar zijn.

---

## Jouw keuzes (vastgelegd)

| Vraag | Keuze |
|-------|--------|
| Co-Pilot eindbeeld korte termijn | **Eerst adviseren, daarna optioneel Q/W/E/G** (per actie instelbaar) |
| IC Script Hub / IdleCombos | **Co-Pilot = adviseur**; Script Hub mag naast de app draaien voor keys/automation (zie § Script Hub) |
| Farm Health alerts v1 | **Alleen in-app** (dashboard badge + log; geen tray/toast) |

### Antwoorden scope-vragen (2026-08-02)

| # | Onderwerp | Antwoord |
|---|-----------|----------|
| 1 | Primair doel | **Gem farm only** — health/copilot alleen in Modron-reset / gem-farm context |
| 2 | Briv testdata | **Test-fixtures** — geen live payload; handmatig testen in app |
| 3 | Zone-heuristiek | **Conservatief** (betrouwbaarder, langzamere zones) |
| 4 | Formation Q/W/E | **Script Hub-standaard:** Q=progress, W=stack, E=Briv-swap |
| 5 | Key-bevestiging | **Lange tijd alleen adviseren** — Q/W/E/G pas veel later |
| 6 | Modron reset (R) | **Ooit volledig automatisch R** bij pre_reset (lage prio) |
| 7 | Baseline reset | **Vragen bij grote wijziging:** “Baseline resetten?” |
| 8 | Parties monitoren | **Alleen actieve party** (badge op die tile) |
| 9 | Script Hub + Co-Pilot | **A — Co-Pilot blijft adviseur**; Script Hub (indien gebruikt) doet het spelen; app = health + Briv intelligence + tekstadvies |

---

## Uitgangspunten

1. **Domainlogica blijft in `ic_gamedata/`** — geen business rules in Qt-widgets.
2. **Bestaande data bronnen hergebruiken** — API payload, memory reader, `StatsTracker`, `goal_run_history.json`.
3. **Geen Byteglow/Emmotes clone** — rekenkern MVP is heuristisch; externe links voor verificatie blijven OK.
4. **Co-Pilot stuurt nooit blind** — elke key-actie heeft guards (hover-gate, focus, caps lock, helper-focus) zoals `ic_automation/worker.py`.
5. **Script Hub = speler, Co-Pilot = adviseur** — Co-Pilot stuurt in MVP geen keys. Als Script Hub actief is (best-effort detectie), blijft dat zo; Co-Pilot levert health, Briv-advies en tekst (“wissel naar W”).

---

## Gedeelde architectuur

### Nieuwe modules (voorstel)

```
ic_gamedata/
  gem_farm/
    __init__.py
    models.py          # dataclasses: FarmProfile, BrivGear, HealthStatus, CopilotPhase, …
    config_store.py    # load/save config/gem_farm.json via ConfigManager-extensie
    baselines.py       # rolling mediane run-duur / gem-u per party
    health_rules.py    # anomaly rules (#5)
    briv_calculator.py # stack-zone / stack-target heuristieken (#2)
    phase_detector.py  # Co-Pilot fase uit live signals (#1)
    copilot_advisor.py # tekstadvies + suggested actions (#1)
    event_log.py       # append-only health/copilot events voor Analytics

ic_ui/
  tabs/
    gem_farm_tab.py    # Briv Intelligence + Co-Pilot instellingen + health log (één tab)
  widgets/
    farm_health_badge.py  # 🟢/🟡/🔴 pill voor dashboard tiles
```

### Config: `config/gem_farm.json`

```json
{
  "profiles": {
    "1": {
      "enabled": true,
      "stack_zone": 310,
      "reset_zone": 295,
      "stack_target_stacks": null,
      "briv_gear_override": null,
      "copilot": {
        "advise_only": true,
        "allow_formation_q": false,
        "allow_formation_w": false,
        "allow_formation_e": false,
        "allow_auto_progress_g": false
      }
    }
  },
  "health": {
    "enabled": true,
    "run_slowdown_pct": 115,
    "gem_drop_pct": 85,
    "area_stall_sec": 180
  }
}
```

Party-index als key sluit aan op `party_modron_goals` in `gamedata.json`.

### Dataflow

```
API poll + memory read (dashboard)
        │
        ▼
  GameStateService / StatsTracker
        │
        ├──► baselines.update(party)     ──► health_rules.evaluate() ──► dashboard badge + event_log
        │
        ├──► briv_calculator.advise()  ──► gem_farm_tab (aanbevelingen)
        │
        └──► phase_detector + copilot_advisor ──► gem_farm_tab + (optioneel) automation bridge
```

### Integratiepunten bestaande code

| Bestand | Rol |
|---------|-----|
| `ic_core/game_state.py` | Signal `farm_health_changed` / `copilot_phase_changed` toevoegen |
| `ic_gamedata/stats_rates.py` | `gems_per_period`, rolling window — input voor health + Briv tab |
| `ic_gamedata/goal_run_history_store.py` | Run-duur baseline voor health rules |
| `ic_gamedata/log_parser.py` | `briv_sprint_stacks`, `briv_in_formation` |
| `ic_gamedata/config_manager.py` | Extensie of delegatie naar `gem_farm/config_store.py` |
| `ic_ui/tabs/dashboard_tab.py` | Health badge op actieve party tile |
| `ic_ui/tabs/analytics_tab.py` | Sectie “Farm events” (tabel uit `event_log`) |
| `ic_automation/worker.py` | **Fase 3:** `CopilotActionQueue` — optionele Q/W/E/G na expliciete user enable |

---

## Initiatief #5 — Farm Health Monitor

### Probleem
Gem farms degraderen stilletjes. Dashboard toont rates, maar niemand **alarm slaat** als gem/u of run-duur structureel daalt.

### MVP scope

**Baseline (per party, achtergrond):**
- Mediaan run-duur: laatste N plausibele records uit `goal_run_history` (`is_plausible_goal_run_record`).
- Mediaan gem/u: rolling rate uit `PartySessionStats` (zelfde window als dashboard, min. 3 min).

**Regels v1:**

| ID | Conditie | Severity | Bericht (NL) |
|----|----------|----------|--------------|
| `run_slowdown` | Laatste 3 runs > `run_slowdown_pct`% van mediaan | warning | Runs trager dan normaal — check dash, Briv, formation |
| `gem_drop` | Huidige gem/u < `gem_drop_pct`% baseline ≥ 10 min | warning | Gem-rate onder baseline |
| `area_stall` | Actieve farm, area ongewijzigd ≥ `area_stall_sec` | critical | Area stagneert — mogelijk stuck |
| `unreliable_run` | Laatste record `duration_unreliable` | info | Timer onbetrouwbaar — baseline niet bijgewerkt |

**Alleen evalueren wanneer:**
- Party actief is (`PartySessionStats.is_active`).
- Modron-doel bekend (`memory_modron_goal` of `party_modron_goals`).
- Optioneel: `briv_in_formation` — anders rules dimmen (campaign runs).

**UI v1:**
- Badge op dashboard party tile: 🟢 OK / 🟡 let op / 🔴 kritiek (hoogste severity actieve alert).
- Tooltip met actieve regels + timestamp.
- Analytics-tab: scrollbare tabel laatste 50 events (party, rule, message, waarden).

**Persistente log:** `config/farm_health_events.json` (max 200 entries, rotate).

### Fase 5.1 — Tests
- `tests/test_farm_health_rules.py`: synthetic baselines + triggers.
- Geen UI-tests verplicht in v1.

### Acceptance #5
- [x] Badge verschijnt op actieve party bij gesimuleerde gem-drop (unit test + handmatige check).
- [x] Geen false critical bij adventure-wissel (stall rule disabled als `is_active` false).
- [x] Events zichtbaar in Analytics-tab.
- [x] Bestaande pytest + ruff groen.

**Status:** Fase A + B geïmplementeerd (2026-08-02).

### Later (niet MVP)
- Tray notificaties.
- “Snooze alert 1 uur”.
- Correlatie met Briv stack peak (koppeling #2).

---

## Initiatief #2 — Briv & Gem Farm Intelligence

### Probleem
Stack-zone en reset-zone zijn trial-and-error. Community-tools (Byteglow Speed, Emmotes routes) zijn los van live session data.

### MVP scope

**Auto-input uit payload:**
- Briv in formation? (`PartySnapshot.briv_in_formation`)
- Huidige sprint stacks (`briv_sprint_stacks`)
- Briv slot-4: item level, rarity, gilding — parser in `briv_calculator.py` (hero loot uit getuserdetails; zelfde bron als party advisor gear).

**Handmatige override** in tab (als API parse faalt): item level, rarity (common→epic), gilding (none/shiny/golden).

**Output v1 (heuristisch, geen volledige route-sim):**
- Aanbevolen **stack-zone** (range min–max).
- Aanbevolen **reset-zone** (Modron-doel − buffer).
- **Stack target** (rough steelbone/sprint stacks voor volgende run).
- **Toelichting** in 2–3 zinnen (NL).
- Links: “Verifieer op Byteglow Speed” / “Emmotes routes” (QDesktopServices).

**Historische koppeling (light):**
- Als gebruiker `stack_zone` in profile wijzigt → log event.
- Tab toont: “Sinds wijziging op {datum}: gem/u {delta}% vs. vorige 10 runs” (via health baselines + goal history).

**Geen MVP:**
- Volledige Emmotes route simulator (RNG WR, Metalborn, feat swap).
- Offline efficiency model.

### Briv rekenkern v1 (documenteer aannames in code)

Start met **configureerbare tabellen** in `config/briv_heuristics.json` (niet hardcoded magic):

- Input: slot-4 item level bucket (0–1j, 1–2j, …), rarity multiplier, gilding.
- Output: suggested stack zone, buffer vóór reset, min stacks.

Community-formules itereren in JSON; unit tests tegen bekende voorbeelden (1–2 fixtures uit Emmotes/Byteglow docs).

### UI: tab “Gem Farm”

Secties:
1. **Briv gear** (auto + override)
2. **Zones** (huidig profile vs. aanbevolen)
3. **Live** (stacks, gem/u, laatste run-duur)
4. **Health** (samenvatting actieve alerts — link naar Analytics)
5. **Co-Pilot** (instellingen — zie #1)

### Acceptance #2
- [x] Briv gear auto-fill werkt voor ten minste één test-fixture payload.
- [x] Aanbevolen zones verschijnen met override fallback.
- [x] Profile opslaan in `gem_farm.json` per party.
- [x] Unit tests voor calculator + parser.

**Status:** Fase C geïmplementeerd (2026-08-02).

### Open vragen (#2) — zie § Open vragen

---

## Initiatief #1 — Modron / Gem Farm Co-Pilot

### Probleem
Automatisering is timer-based; gem farm vereist fase-awareness (progress → stack → swap → reset).

### Jouw keuze: advise → optional keys

**Fase 1 (observe + advise only):** geen keys; alleen UI + event log.  
**Fase 2 (optional keys):** per actie checkbox in profile; bridge naar automation worker.

### Fase-detectie v1

| Fase | Detectie (prioriteit memory > API area) |
|------|----------------------------------------|
| `progress` | area < stack_zone − margin |
| `stacking` | stack_zone − margin ≤ area < reset_zone − buffer |
| `swap_ready` | briv_stacks ≥ target OR area ≥ pre-reset threshold |
| `pre_reset` | area ≥ reset_zone − jump_buffer |
| `idle` | party inactive of geen modron goal |

`phase_detector.py` retourneert `CopilotPhase` + confidence + redenen (voor debug).

### Advies v1 (`copilot_advisor.py`)

Per fase NL-tekst + suggested action enum:

| Fase | Advies | Suggested action (optioneel key) |
|------|--------|----------------------------------|
| progress | “Progressie — Q formation” | `FORMATION_Q` |
| stacking | “Stack-zone — W formation” | `FORMATION_W` |
| swap_ready | “Stacks klaar — E formation (Briv swap)” | `FORMATION_E` |
| pre_reset | “Reset-zone bereikt — Modron reset” | `MODRON_RESET` (v1: alleen tekst; geen R-key zonder expliciete opt-in) |
| stuck | Health rule `area_stall` actief | `AUTO_PROGRESS_G` (alleen als user `allow_auto_progress_g`) |

**Modron reset:** MVP adviseert alleen; **geen** R-key in v1 (te destructief). Later aparte opt-in.

### Fase E — Automation bridge ✅

**Gebruikerskeuze:** checkbox **Co-Pilot toetsen sturen** op Gem Farm-tab; **standaard uit**. Bevestigingsdialoog bij inschakelen.

Implementatie:
- `ic_automation/copilot_controller.py` + `copilot_worker.py` + `copilot_settings.py`
- `ic_gamedata/gem_farm/copilot_keys.py` — fase → Q/W/E/G (geen R bij pre_reset)
- Snapshot via `GameStateService.update_gem_farm()` → `notify_snapshot()`
- Zelfde guards als automation worker (focus, hover gate, UI pause)
- Debounce: zelfde fase-key niet binnen ~60s herhalen
- Events gelogd in `farm_health_events.json`

| Fase | Key (als ingeschakeld) |
|------|------------------------|
| progress | Q |
| stacking | W |
| swap_ready | E |
| stuck | G |
| pre_reset | — (alleen advies) |

### Script Hub (vastgelegd: optie A)

| Scenario | Gedrag Co-Pilot |
|----------|-----------------|
| Geen Script Hub | Standaard alleen advies; keys via checkbox opt-in |
| Script Hub actief | Tooltip: zet checkbox uit als Hub Q/W/E stuurt |
| Co-Pilot keys aan | Alleen bij fase-wissel; debounce ~60s |

Detectie is **best-effort**; geen harde dependency.

### Acceptance #1
- [x] Fase wisselt correct in unit tests (synthetic area/stack timelines).
- [x] Adviestekst zichtbaar op Gem Farm-tab.
- [x] Keys **standaard uit**; checkbox op Gem Farm-tab met bevestiging bij inschakelen.
- [x] Fase → hotkey mapping getest (`tests/test_copilot_keys.py`).
- [ ] Co-Pilot phase-change events in Analytics *(alleen health/profile events nu)*.

### Later
- Auto-execute keys na countdown.
- Integratie Modron reset (R) met dubbele bevestiging.
- Shandie dash-wait signal (moeilijk zonder OCR — lage prio).

---

## Gezamenlijke roadmap

| Fase | Werk | Duur (indicatie) |
|------|------|------------------|
| **A** | Shared: `models`, `config_store`, `event_log`, Gem Farm tab shell | 1–2 d |
| **B** | #5 Farm Health: rules + badge + analytics events | 2–3 d |
| **C** | #2 Briv calculator + gear parser + profile UI | 3–4 d |
| **D** | #1 Co-Pilot observe/advise + phase UI | 2–3 d |
| **E** | #1 optional keys + copilot worker *(checkbox, default uit)* | ✅ |
| **F** | Polish, docs, `briv_heuristics.json` tunen | 1–2 d |

**Totaal indicatie MVP (A–D + F):** ~1,5–2 weken part-time. Fase E pas na expliciete go/no-go.

### Cross-feature voorbeeldflow

1. Health detecteert `gem_drop` → badge 🟡.
2. Briv-tab toont: “Aanbevolen stack-zone 312; jouw profile 305 — overweeg +2”.
3. User past profile aan → Co-Pilot fase `stacking` met advies “W formation”.
4. User klikt [Uitvoeren] → worker stuurt W (als enabled).
5. Na reset: goal run opgeslagen; health baseline herberekend; badge 🟢.

---

## Open vragen

### Beantwoord ✓

Zie tabel **Antwoorden scope-vragen** bovenaan.

### Beantwoord ✓ (vraag 9)

**Script Hub + Co-Pilot:** optie **A** — Co-Pilot blijft adviseur; Script Hub doet het spelen. Keys via Co-Pilot zijn uitgesteld (fase E); als ooit keys komen, blijven ze **standaard uit** zolang Script Hub actief is (best-effort detectie + banner).

---

## Risico's

| Risico | Mitigatie |
|--------|-----------|
| Memory area onbetrouwbaar | Sanity checks (bestaand patroon `GOAL_PEAK_SANITY_MARGIN`); fallback API area |
| Briv heuristiek wrong | JSON tunable + externe verify links; geen “auto apply zone” zonder user |
| Co-Pilot + Script Hub dubbel Q/W/E | Hub-detectie + default keys uit |
| False health alerts | Strikte `enabled` context; stall rule alleen active farm |
| Scope creep (Emmotes parity) | MVP heuristiek; route sim expliciet out of scope |

---

## Niet in scope (expliciet)

- Promo codes / chest automation (IdleCombos-terrein).
- Volledige champion database (Byteglow).
- IC Script Hub vervanging in één release.
- OCR voor in-game UI state (auto-progress aan/uit).

---

## Volgende stap

1. **Handmatig testen** — gem farm draaien, Gem Farm-tab + dashboard badge controleren (zie hieronder).
2. **Optioneel tunen** — `config/briv_heuristics.json` aanpassen aan jouw farm.
3. **Later (fase E)** — Co-Pilot keys alleen als je Script Hub niet gebruikt.
