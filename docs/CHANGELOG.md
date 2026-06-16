# Changelog

All notable changes to VeriFlow are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] - 2026-06-15

First public release. VeriFlow is a lightweight RTL verification and documentation
framework for multi-project ASIC chip design, built on open-source EDA tooling
(Icarus Verilog + Yosys — no oss-cad-suite required).

### Highlights

**Two operating modes**

- **Database Mode** (`veriflow db ...`) — tile database with indexed run history,
  per-run artifacts, and auto-generated documentation. Supports `bump-version` /
  `bump-revision` for version tracking.
- **Project Mode** (`veriflow project run`) — verify a single project directory
  described by a `veriflow.yaml` file; no database needed.

**Configurable interface profiles**

Connectivity checking is driven by named interface profiles (`interface_name:
"semicolab"` in `project_config.yaml`, or an `interface:` section in
`veriflow.yaml`). Setting `interface_name: null` / omitting the section runs no
connectivity check. The built-in `semicolab` profile enforces the nine-port
Semicolab port contract.

**`veriflow wrap` — interface wrapper generator**

Three commands scaffold a Verilog adapter that maps existing RTL port names to
a named interface profile:

- `wrap init` — reads RTL sources, extracts ports, scaffolds `wrapper_config.yaml`
- `wrap generate` — validates the mapping and generates `wrapper.v`; runs the
  connectivity check on the result
- `wrap wizard` — interactive guided session combining both steps

**`veriflow doctor` — EDA tool availability check**

Verifies that iverilog, vvp, and yosys are installed and in PATH. Reports results
by backend category. Supports `--json` output. Exit code 0 = all tools available,
1 = any tool missing.

**Self-contained testbenches**

Testbenches are complete Verilog modules compiled together with the RTL. The
testbench top module is selected explicitly (`tb_top_module` in Database Mode,
`simulation.tb_top` in Project Mode). `db create-tile` generates a ready-to-edit
scaffold for Semicolab or generic projects.

**Automation / CI support**

- `--json` global flag — suppresses Rich output and emits a single JSON object to
  stdout on completion (success or error with stable `code` values)
- `--non-interactive` global flag — disables TUI and waveform viewer; safe for CI
  pipelines and agent workflows
- `results.json` — machine-readable run result written on every `db run`, regardless
  of flags. Schema version `"1.2"`.

**Open-source toolchain**

Requires only `iverilog` + `vvp` + `yosys`, installable independently on Linux
(apt), macOS (brew), and Windows (winget + MSYS2). See `docs/INSTALL.md`.

---

## Development History (pre-1.0.0 internal milestones)

The following entries document the internal development history between the initial
codebase and the public 1.0.0 release. They are preserved for reference but are not
part of the public changelog.

---

### [Unreleased → 1.0.0] internal changes

#### Changed

- **`results.json` schema 1.2** — the boolean `semicolab` field was replaced by `interface_name`: the selected interface profile name (e.g. `"semicolab"`), or `null` when no interface is configured.
- **`interface_name` replaces the `semicolab` boolean** — `project_config.yaml` now declares `interface_name: "semicolab"` or `interface_name: null` instead of `semicolab: true/false`. The connectivity check is driven by interface profile selection; a missing key fails with `VF_PROJECT_INTERFACE_REQUIRED` and the deprecated `semicolab` key fails with `VF_PROJECT_INTERFACE_CONFIG_LEGACY`.
- **CSV headers** — `tile_index.csv` now has an `interface_name` column and `records.csv` an `Interface` column (replacing the former `Semicolab` column); both hold the interface profile name, empty for generic projects.
- **Self-contained testbenches** — testbenches are complete Verilog modules compiled together with the RTL; the testbench top is selected explicitly (`tb_top_module` in Database Mode, `simulation.tb_top` in Project Mode). The runtime marker-extraction/DUT-injection flow (`// USER TEST ... //`, `/* MODULE_INSTANTIATION */`) and automatic `$dumpfile` insertion were removed; `create-tile` now generates a self-contained scaffold from `tb_semicolab_template.v` or `tb_universal_template.v`. Documentation updated accordingly.

#### Removed

- **Flat database CLI aliases** — `veriflow --db <path> <command>` forms were removed; all Database Mode commands live under the `veriflow db <command> --db <path>` namespace.
- **Unused legacy files** — the `RunConfig` model (`models/run_config.py`; run fields live in `tile_config.yaml` / `TileConfig`) and the `ip_tile.v` RTL template were removed.

#### Added

- **`results.json` artifact** — every `run` command writes a machine-readable JSON file to `tiles/<tile_id>/runs/run-NNN/results.json` alongside `manifest.yaml`. Contains schema version, tile/run identifiers, overall status, per-stage results, source file paths, and artifact paths. All paths are relative to the database root (Windows/Linux portable).
- **`--json` CLI flag** — suppresses Rich terminal output and emits a single JSON object to stdout on command completion. On success: `{ "status": "SUCCESS", "command": "...", "run_result": {...} }`. On error: `{ "status": "ERROR", "error": { "code": "...", "message": "...", "details": {...}, "exit_code": N } }`.
- **`--non-interactive` CLI flag** — disables the TUI and waveform viewer; safe for use in CI pipelines, shell scripts, and agent workflows. Combining with `--waves` or the `waves` subcommand is an error.
- **Structured `VeriFlowError` metadata** — `VeriFlowError` now carries `code` (stable string), `details` (dict), and `exit_code` (int) fields. `VeriFlowError.to_dict()` serializes all fields for JSON error output.

---

### [Internal milestone 2026-03-25]

#### Added
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

### [Post-milestone additions]

#### ui/ module — styled output and palette library
- **`ui/output.py`** — styled output helpers for all commands: `print_status`, `print_section`, `print_run_header`, `print_done`, `print_fail_detail`, `print_wave_url`, `print_ports_table`
- **`ui/theme.py`** — central Rich color palette and theme; all UI modules import from here
- **`ui/themes.py`** — 16 Textual-compatible palettes (Tokyo Night, Dracula, Nord, Catppuccin, Gruvbox, One Dark/Light, Monokai, Solarized, Oxocarbon, High Contrast, Colorblind Safe); `~/.veriflow_theme` persists the selection (migrates from `~/.semicolab_theme`); shared palette library for `tilebench`
- **`cli.py`** updated — no-argument invocation shows `--help` (removed dead TUI redirect; `ui/banner.py` and `ui/tui.py` deleted as dead code)

#### waves command
- Standalone `veriflow --db ... waves --tile XXXX [--run run-NNN]` command to open waveforms without re-running the pipeline
- Resolves to latest run when `--run` is omitted

#### Waveform viewer priority chain
- **Docker** (`VERIFLOW_DOCKER` env var; `SEMICOLAB_DOCKER` accepted as deprecated alias) → Surfer WASM at `http://localhost:7681` with `?load_url=` VCD preload (`open_surfer()`)
- **Local — Surfer native** → if `surfer` found in PATH, opened with `subprocess.Popen`
- If Surfer is not found locally, VeriFlow prints the Surfer install hint.

#### sim_runner.py improvements
- `_read_user_test` now reads from `tb_tile.v` directly (same file as wrapper) instead of separate files
- `_prepare_universal_tb` handles Universal mode testbenches
- ~~`run_simulation` accepts `semicolab` flag and branches accordingly~~ — *superseded 2026-06-14: flag removed; `run_simulation` is now profile-agnostic; see interface_name migration above*
- Removed legacy waveform launch paths (X11/VNC stack dropped from TileBench)

#### run.py improvements
- All console output now uses `ui/output` Rich helpers
- `_finalize_run` extracted as a separate function to handle early-exit (connectivity FAIL) and normal completion paths uniformly
- `tile_index` kept in sync with `tile_config` on every run (`tile_name`, `tile_author`)
- ~~`records.csv` row now includes `Semicolab` column~~ — *superseded 2026-06-14: column renamed to `Interface`; see above*

#### ProjectConfig
- ~~Added `semicolab` boolean field (default `true`)~~ — *superseded 2026-06-14: field removed; replaced by `interface_name` string; see above*
