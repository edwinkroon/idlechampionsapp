# ic_reader — read-only Idle Champions memory reader

Read-only access to game state (starting with **current area** and optionally **gems this reset**) via Windows `ReadProcessMemory`. No writes, no input simulation, no injection.

## How it works

1. **Find process** — `IdleChampions.exe` via `psutil`.
2. **Open read-only handle** — `PROCESS_VM_READ` only.
3. **Resolve module base** — e.g. `GameAssembly.dll` (Unity IL2CPP).
4. **Follow pointer chains** — configured in `config/game_offsets.json` (Cheat Engine style).
5. **Score candidates** — multiple chains can be defined; the best plausible `int32` wins.
6. **Log changes** — CLI prints and logs only when the resolved area changes.

```
GameAssembly.dll + static_offset
  → [+offset₀] dereference
  → [+offset₁] dereference
  → read int32 at final address
```

## Quick start

```bash
pip install psutil
copy config\game_offsets.example.json config\game_offsets.json
# Edit game_offsets.json with offsets you validated in Cheat Engine
python main.py --once
python main.py --watch-area --debug
```

Logs: `logs/area_reader.log`

## Configuration

Copy `config/game_offsets.example.json` to `config/game_offsets.json`.

Each logical value (e.g. `current_area`) has **candidates**:

| Field | Meaning |
|--------|---------|
| `id` | Unique name |
| `status` | `unverified` \| `verify` \| `verified` \| `deprecated` |
| `pointer_chain.module` | e.g. `GameAssembly.dll` |
| `pointer_chain.static_offset` | Hex offset from module base |
| `pointer_chain.offsets` | Hex offsets; each step reads a 64-bit pointer at `address + offset` |
| `value_type` | `int32`, `int64`, `float`, `string` |
| `min_plausible` / `max_plausible` | Reject out-of-range reads |
| `max_delta_per_second` | Reject absurdly fast changes |

**No offsets are shipped as “known good”.** Placeholders use `0x0` and empty `offsets` until you verify them.

### Candidate status workflow

1. `unverified` — template, not used for production reads.
2. `verify` — you're testing; may be selected if plausible.
3. `verified` — preferred in scoring after manual validation.
4. `deprecated` — ignored.

## Validating offsets (Cheat Engine, read-only)

1. Start Idle Champions and note the **area number in the UI**.
2. Open **Cheat Engine**, attach to `IdleChampions.exe`.
3. **Do not** freeze values or write memory — search only.
4. First scan: `4 Bytes`, value = current area.
5. Change area in-game, **Next Scan** until few addresses remain.
6. **Pointer scan** for stable paths; note:
   - Module (usually `GameAssembly.dll`)
   - Base offset
   - Offset list (CE “pointer path”)
7. Paste into `config/game_offsets.json` under `current_area.candidates`.
8. Run: `python main.py --watch-area --debug --ui-hint <area_on_screen>`
9. Advance areas; confirm logs match the UI.
10. Set `status` to `verified` when stable across restart.

Community reference (offsets **change every patch**):

- [mikebaldi/Idle-Champions — MemoryRead](https://github.com/mikebaldi/Idle-Champions/tree/main/SharedFunctions/MemoryRead)

Compare your chain layout to their `SH_StaticMemoryPointer` / `SH_GameObjectStructure.ahk` — do **not** copy numbers without re-validating.

## CLI

| Command | Description |
|---------|-------------|
| `python main.py --once` | Single read |
| `python main.py --watch-area` | Poll every 1s; print/log on change |
| `python main.py --watch-area --interval 2` | Custom interval |
| `python main.py --watch-area --debug` | Pointer steps + rejections |
| `python main.py --once --ui-hint 3` | Score candidates against UI area 3 |

Exit code `2` on `--once` if no candidate resolved.

## Debug mode

With `--debug`, logs include:

- Module base addresses
- Each pointer step (`before`, `offset`, `after`)
- Why candidates were rejected (placeholder, negative area, too fast, etc.)

## Tests

```bash
python -m unittest discover -s tests -v
```

Uses `MockMemoryReader` — no game required.

## Troubleshooting

| Issue | Action |
|--------|--------|
| `OpenProcess` / error 998 | Run reader **as Administrator** if the game is elevated; match privilege level. |
| `Module not found` | Confirm `GameAssembly.dll` in Process Explorer; adjust `process.modules` in config. |
| Always `(unresolved)` | Offsets not filled or wrong for your patch — re-do CE validation. |
| Wrong value | Add another candidate; use `--ui-hint`; check for `int64` vs `int32`. |

## Game updates

**Every patch can break pointer chains.** Keep `game_version_note` in JSON updated. After updates, re-run pointer scans and bump candidate `id` or set old ones to `deprecated`.

## Legal / ToS

Memory reading may conflict with game terms of service. This tool is **read-only** and for personal automation on your own machine. Use at your own risk.
