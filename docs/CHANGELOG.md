# Changelog

All notable changes to VeriFlow are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.0.0] — 2026-03-25

### Added
- **Connectivity check** — compiles RTL + testbench with Icarus Verilog to verify port wiring (SemiCoLab mode only)
- **Simulation** — runs user testbenches via `iverilog`/`vvp`, captures VCD waveforms
- **Synthesis** — validates RTL with Yosys; reports cell count, detects inferred latches
- **Two operating modes** — SemiCoLab (fixed port convention, injection-based TB) and Universal (any RTL module, full TB)
- **Auto-documentation** — generates `manifest.yaml`, `notes.md`, `summary.md`, and `README.md` per run
- **Run history** — `records.csv` with one row per run, queryable per tile and run
- **Tile indexing** — `tile_index.csv` tracks the current Tile ID for each tile number
- **Version tracking** — `bump-version` (designer iteration) and `bump-revision` (advisor authorization)
- **Waveform viewer** — `waves` command and `--waves` flag open the viewer from the CLI
- **Testbench injection** (SemiCoLab) — VeriFlow injects DUT instantiation and user test code at runtime via `/* MODULE_INSTANTIATION */` and `/* USER_TEST */` placeholders
- **Auto `$dumpfile` injection** (Universal) — ensures VCD is always captured regardless of testbench content
- **CSV store** — `tile_index.csv` and `records.csv` with header validation and auto-init
- **Flat copy with collision resolution** — `copier.copy_flat` appends `_1`, `_2` suffixes on name collisions
- **Test suite** — 26 integration tests at `tests/runner.py`, no pytest required
- **Windows compatibility** — posix paths for subprocess calls, `NUL` for discard, `CREATE_NO_WINDOW` for GUI launchers

---

## Recent additions (post v1.0.0)

### ui/ module — TUI and styled output
- **`ui/banner.py`** — SEMICOLAB ASCII banner with `pyfiglet` + `TerminalTextEffects` MiddleOut animation; orange accent for VeriFlow, green for TileWizard; Mifral link shown once
- **`ui/output.py`** — styled output helpers for all commands: `print_status`, `print_section`, `print_run_header`, `print_done`, `print_fail_detail`, `print_wave_url`, `print_ports_table`
- **`ui/theme.py`** — central Rich color palette and theme; all UI modules import from here
- **`ui/themes.py`** — 16 Textual-compatible palettes (Tokyo Night, Dracula, Nord, Catppuccin, Gruvbox, One Dark/Light, Monokai, Solarized, Oxocarbon, High Contrast, Colorblind Safe); `~/.semicolab_theme` persists the selection
- **`ui/tui.py`** — redirect stub to `tilebench.tui.selector.run_veriflow`; invoked when `veriflow` is called with no arguments
- **`cli.py`** updated — no-argument invocation launches the TUI instead of printing help

### waves command
- Standalone `veriflow --db ... waves --tile XXXX [--run run-NNN]` command to open waveforms without re-running the pipeline
- Resolves to latest run when `--run` is omitted

### Waveform viewer priority chain
- **Docker** (`SEMICOLAB_DOCKER` env var) → Surfer WASM at `http://localhost:7681` with `?load_url=` VCD preload (`open_surfer()`)
- **Local — Surfer native** → if `surfer` found in PATH, opened with `subprocess.Popen`
- If Surfer is not found locally, VeriFlow prints the Surfer install hint.

### sim_runner.py improvements
- `_read_user_test` now reads from `tb_tile.v` directly (same file as wrapper) instead of separate files
- `_prepare_universal_tb` handles Universal mode testbenches
- `run_simulation` accepts `semicolab` flag and branches accordingly
- Removed legacy waveform launch paths (X11/VNC stack dropped from TileBench)

### run.py improvements
- All console output now uses `ui/output` Rich helpers
- `_finalize_run` extracted as a separate function to handle early-exit (connectivity FAIL) and normal completion paths uniformly
- `tile_index` kept in sync with `tile_config` on every run (`tile_name`, `tile_author`)
- `records.csv` row now includes `Semicolab` column

### ProjectConfig
- Added `semicolab` boolean field (default `true`); parsed from YAML with string normalization (`"false"`, `"0"`, `"no"` → `False`)
