# Changelog

## Phase 6 — Domain cleanup + legacy

- Split `stats.py` into `stats_rates.py`, `stats_run_history.py`, and facade `stats.py`
- Split `party_advisor.py` into `party_advisor_formation.py`, `party_advisor_scoring.py`, and facade
- Added `ConfigManager` for unified JSON config access
- Added version label in window title and Help → About dialog
- Fixed `idle_champions_gamedata.py` compatibility shim (`GameSnapshot` import)
- Goal run history store reads types directly from `stats_models`

## Phase 5 — Models + legacy archive

- Extracted `stats_models.py` and `party_advisor_models.py`
- Archived tkinter GUI to `legacy/`; root entrypoint redirects to `app_launcher.py`
- Expanded Ruff coverage to `ic_gamedata`

## Phase 4 — CI & tooling

- GitHub Actions CI (pytest + ruff)
- `pyproject.toml`, `requirements-dev.txt`
- Shared advisor goal context bar

## Phase 3 — Analytics

- Analytics tab with PyQtGraph Modron run charts and CSV export

## Phase 2 — Dashboard UX

- `GameStateService`, Modron progress bar, status pills, throttled refresh

## Phase 1 — UI structure

- Extracted tabs/workers from monolithic `pyside_app.py`

## Phase 0 — Foundation

- Git baseline, `ic_gamedata/parsing.py`, `ic_ui/theme.py`
