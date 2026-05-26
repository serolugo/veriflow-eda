# VeriFlow — Architecture Reference

---

## Overview: Full execution flow

```
veriflow (no args)
    └── ui/tui.py → tilebench.tui.selector.run_veriflow()

veriflow --db ./database <command> [flags]
    └── cli.py main()
            └── argparse dispatch
                    ├── init          → commands/init_db.py
                    ├── create-tile   → commands/create_tile.py
                    ├── run           → commands/run.py
                    │       ├── core/validator.py   (validate DB + tools + inputs)
                    │       ├── core/copier.py       (copy RTL/TB to run/src/)
                    │       ├── core/sim_runner.py   (connectivity check + simulation)
                    │       ├── core/synth_runner.py (synthesis)
                    │       ├── generators/          (manifest, notes, summary, README)
                    │       ├── core/csv_store.py    (append records.csv row)
                    │       └── ui/output.py         (styled console output)
                    ├── waves         → commands/waves.py
                    │       └── core/sim_runner.py   (open_surfer / launch_waves)
                    ├── bump-version  → commands/bump_version.py
                    └── bump-revision → commands/bump_revision.py
```

Errors propagate as `VeriFlowError` (defined in `core/__init__.py`) and are caught at the CLI entry point with exit code 1.

---

## Module reference

### `cli.py` — Entry point and routing

Parses arguments with `argparse` and dispatches to command handlers. Two distinct behaviors:

- **No arguments** → calls `ui/tui.py:run_tui()`, which launches the TileBench TUI in VeriFlow mode
- **With `--db` and a subcommand** → dispatches to the matching `commands/` handler

All imports of command modules are deferred (inside the `if` branches) to avoid loading unused code on every invocation.

---

### `commands/init_db.py` — Database initialization

Creates the canonical database layout under `<db>/`:
```
project_config.yaml    (template with comments)
tile_index.csv         (empty — header written on first tile)
records.csv            (empty — header written on first run)
config/                (empty)
tiles/                 (.gitkeep)
```

With `--force`: overwrites an existing database entirely.

---

### `commands/create_tile.py` — Tile scaffolding

1. Reads `id_prefix` from `project_config.yaml`
2. Calls `csv_store.get_next_tile_number()` to get the next 4-digit tile number
3. Generates `tile_id` via `tile_id.generate_tile_id()` with version=01, revision=01, date=today
4. Creates `config/tile_XXXX/tile_config.yaml` (merged template with inline comments)
5. Creates `config/tile_XXXX/src/rtl/` and `src/tb/` with `tb_tile.v` + `tb_tasks.v` (from `template/`)
6. Creates `tiles/<tile_id>/` with `README.md`, `works/rtl/`, `works/tb/`, `runs/`
7. Appends to `tile_index.csv`

---

### `api.py` — Internal Python integration surface

`run_tile(db_path, tile, *, skip_connectivity, skip_sim, skip_synth, only_connectivity, only_sim, only_synth, waves, non_interactive) → dict`

Thin wrapper over `cmd_run()` for callers that want a Python-callable entry point without going through the CLI or subprocess.  Accepts `str | Path` for `db_path`; normalises it via `normalize_path()`.  All flag names mirror the CLI flags.  `VeriFlowError` propagates unchanged.  Raises `VF_NON_INTERACTIVE_VIEWER_DISABLED` if `waves=True` and `non_interactive=True`.

Intended consumers: TUI integration, CI/CD scripts, agent tooling.  This is an internal surface — it is not a REST or RPC API.

---

### `commands/run.py` — Verification pipeline orchestrator

Main entry: `cmd_run(db, tile_number, skip_*, only_*, waves)`.

**Setup phase:**
1. Translates `--only-*` flags into their `skip_*` equivalents
2. Validates the database (`validator.validate_database`)
3. Validates external tools (`validator.validate_tools`) — only if at least one tool stage will run
4. Reads `tile_config.yaml` and `project_config.yaml`
5. In Universal mode (`semicolab: false`): sets `skip_check = True` automatically
6. Validates run inputs (`validator.validate_run_inputs`)
7. Resolves `tile_id` from `tile_index.csv`; syncs `tile_name`/`tile_author` back to the index
8. Determines next `run_id` from `runs_dir`

**Execution phase:**
9. Creates the run directory tree: `src/rtl/`, `src/tb/`, `out/connectivity/logs/`, `out/sim/logs/`, `out/sim/waves/`, `out/synth/logs/`, `out/synth/reports/`
10. Copies RTL from `config/tile_XXXX/src/rtl/` → `run/src/rtl/` (flat, `.v` files)
11. Copies TB from `config/tile_XXXX/src/tb/` → `run/src/tb/`; sets `skip_sim = True` if no TB files found
12. Runs connectivity check (SemiCoLab only) → FAIL stops the pipeline and calls `_finalize_run` immediately
13. Runs simulation → `(result, {sim_time, seed})`
14. Runs synthesis → `(result, {cells, warnings, errors, has_latches})`

**Finalization (`_finalize_run`):**
15. Generates `manifest.yaml` (custom serializer, not `yaml.dump`)
16. Generates `notes.md`
17. Regenerates tile `README.md`
18. Updates `works/rtl/` and `works/tb/` with the current run's sources
19. Appends a row to `records.csv` (includes `Semicolab` column)
20. Generates `summary.md` and prints summary table to console

If `--waves` was passed and `waves.vcd` exists, calls `launch_waves()` after finalization.

**Status derivation** (`_derive_status`):

| Condition | Status |
|---|---|
| `conn == "FAIL"` | `FAIL` |
| Any stage `SKIPPED` | `PARTIAL` |
| All stages PASS/COMPLETED | `PASS` |

---

### `core/pipeline_builder.py` — Default pipeline construction

`build_default_pipeline(*, rtl_files, tb_files, tb_base_path, tb_tasks_path, top_module, has_tb, profile=None) → PipelineRunner`

Centralises construction of the fixed three-stage pipeline (connectivity → simulation → synthesis).  Returns a `PipelineRunner` whose `.stages` list holds the three stage instances in order.

Accepts an optional `profile: ExecutionProfile` (defaults to `default_execution_profile()`) and threads it through to each stage so that `StageResult.tool` labels reflect the profile's declared tool strings.

`commands/run.py` calls this once after sources are copied and tb paths are resolved, then unpacks the returned stages and runs each individually via single-stage `PipelineRunner` calls so that the connectivity-FAIL early-exit logic is preserved.

In `build_default_pipeline`, backend instances are obtained from the backend registry using the IDs stored in `ExecutionProfile`.  Stage constructors still accept an explicit `backend` parameter, so tests can inject mocks directly without touching the registry.

This is an internal construction helper.  The pipeline order and stage set are fixed; there is no plugin registry, YAML config, or dynamic dispatch.

---

### `core/backends/registry.py` — Internal backend registry

A static, read-only mapping from backend name strings to concrete backend classes.  Three lookup functions are exposed:

```python
get_connectivity_backend(name: str) -> ConnectivityBackend
get_simulation_backend(name: str)   -> SimulationBackend
get_synthesis_backend(name: str)    -> SynthesisBackend
```

Supported names: `"icarus"` (connectivity, simulation) and `"yosys"` (synthesis).  An unrecognised name raises `VeriFlowError` with one of the following codes:

| Code | Trigger |
|---|---|
| `VF_BACKEND_CONNECTIVITY_UNKNOWN` | unknown connectivity backend name |
| `VF_BACKEND_SIMULATION_UNKNOWN`   | unknown simulation backend name |
| `VF_BACKEND_SYNTHESIS_UNKNOWN`    | unknown synthesis backend name |

The registry uses a plain Python dictionary and no dynamic imports.  It is an **internal helper** — users have no mechanism to select backends today; that surface is intentionally deferred.  No plugins, YAML selection, or alternate backends are wired in at this stage.

---

### `models/technology_profile.py` — Technology target metadata

> **Backend vs technology profile distinction:**
> A *backend* is a tool that executes work (e.g. `yosys`, `iverilog`).
> A *technology profile* is a synthesis target / PDK context (e.g. `sky130`, `gf180`, `ihp130`).
> These are orthogonal: the same backend can synthesise for different technology targets, and the same target can in principle be served by different backends.

`TechnologyProfile` is a plain dataclass describing a named technology target:

```python
@dataclass
class TechnologyProfile:
    name: str = "generic"
    pdk: str | None = None
    cell_library: str | None = None
    liberty: str | None = None
    constraints: str | None = None
    notes: str | None = None
```

`default_technology_profile() → TechnologyProfile` returns the bare `generic` instance with all optional fields `None`.

`get_technology_profile(name: str) → TechnologyProfile` looks up a named profile from the internal registry.  Supported names: `"generic"`, `"sky130"`, `"gf180"`, `"ihp130"`.  An unknown name raises `VeriFlowError` with code `VF_TECHNOLOGY_UNKNOWN`.

The `sky130`, `gf180`, and `ihp130` entries are **metadata placeholders only**.  They record PDK and cell-library names but do not point to local PDK file paths and are not wired into `YosysSynthesisBackend`.  Yosys invocation is unchanged by this module.  PDK-aware synthesis target configuration is explicitly deferred to a future milestone.

`ExecutionProfile` carries a `technology_name: str = "generic"` field that names the intended target.  It is not consumed by any stage yet; it exists so the profile dataclass can evolve toward technology-aware synthesis without a breaking schema change.

---

### `models/execution_profile.py` — Toolchain description

`ExecutionProfile` is a plain dataclass that records which external tools and internal backend IDs the current fixed pipeline uses.  It is **not** a configuration surface — users cannot select profiles or swap backends yet.

```python
@dataclass
class ExecutionProfile:
    name: str = "default"
    connectivity_tool: str = "iverilog"
    simulation_tool: str = "iverilog/vvp"
    synthesis_tool: str = "yosys"
    doc_profile: str = "default"
    # Internal backend IDs — not user-configurable yet
    connectivity_backend: str = "icarus"
    simulation_backend: str = "icarus"
    synthesis_backend: str = "yosys"
```

The `*_tool` fields determine the `StageResult.tool` label written to `results.json`; they are unchanged.  The `*_backend` fields are internal IDs passed to the backend registry by `build_default_pipeline`; they match the currently fixed toolchain and are not exposed as user configuration.

`default_execution_profile() → ExecutionProfile` returns the canonical instance.  Its `*_tool` field values are identical to the string literals previously hardcoded in the stage implementations, so `StageResult.tool` and `results.json` content are unchanged.

**Future work (not implemented):** YAML-driven profile loading, user-selectable backend names, alternate backend implementations, and plugins are intentionally deferred.  `ExecutionProfile` and the registry exist now only as internal infrastructure for the current fixed toolchain.

---

### `commands/waves.py` — Waveform viewer

`cmd_waves(db, tile_number, run_id)`:

1. Validates the database
2. Resolves `tile_id` from `tile_index.csv`
3. If `--run` is given: opens that specific run directory; raises `VeriFlowError` if not found
4. If `--run` is omitted: scans `runs/` for directories matching `run-NNN`, picks the highest
5. Verifies `out/sim/waves/waves.vcd` exists
6. Calls `launch_waves()`, which uses Surfer WASM in Docker and native Surfer locally

---

### `commands/bump_version.py` / `commands/bump_revision.py` — Version management

Both commands:
1. Resolve the current `tile_id` from `tile_index.csv`
2. Increment the appropriate counter (version +1; or revision +1 + version reset to 01)
3. Generate a new `tile_id` with today's date
4. Create the new `tiles/<new_tile_id>/` directory with `works/` copied from the previous one and a clean `runs/`
5. Update `tile_index.csv` to point to the new `tile_id`

The previous directory is preserved as read-only history.

---

### `core/sim_runner.py` — Testbench injection, simulation, wave viewer

**Testbench injection (SemiCoLab):**

- `_build_dut_inst(top_module)` — generates the DUT instantiation string with the 9 fixed ports
- `_read_user_test(tb_files)` — extracts code between `// USER TEST STARTS HERE //` and `// USER TEST ENDS HERE //` from `tb_tile.v`; strips module wrappers if markers are absent
- `_inject_tb(tb_base_path, top_module, tb_files)` — reads `tb_tile.v`, replaces `/* MODULE_INSTANTIATION */` and `/* USER_TEST */`, writes to a `tempfile.NamedTemporaryFile`, returns the path

**Universal mode:**

- `_ensure_dumpfile(content)` — injects `$dumpfile`/`$dumpvars` after the module declaration if not already present
- `_prepare_universal_tb(tb_files)` — applies `_ensure_dumpfile` and writes to a temp file

**Pipeline functions:**

- `run_connectivity_check(...)` — compiles with `iverilog -o NUL/dev/null` using `_inject_tb` with no user TB files; returns `"PASS"` or `"FAIL"`
- `run_simulation(...)` — compiles into `tempfile.mkdtemp()` (avoids Windows path-with-spaces issues), runs `vvp` from `wave_path.parent` so `$dumpfile("waves.vcd")` lands in the correct directory; returns `("COMPLETED"|"FAILED", {sim_time, seed})`

**Waveform viewer:**

- `open_surfer(wave_path)` — Docker mode only; constructs `http://localhost:7681/?load_url=<vcd>` URL and prints it; calls `webbrowser.open()` as best-effort
- `launch_waves(wave_path)` — priority: (1) `SEMICOLAB_DOCKER` → `open_surfer`; (2) `surfer` in PATH → native Surfer; (3) prints Surfer install hint

---

### `core/synth_runner.py` — Synthesis

`run_synthesis(rtl_files, top_module, synth_log_path)`:

Builds and runs an inline Yosys script:
```
read_verilog <files...>
hierarchy -check -top <top_module>
synth
check
stat
```

Returns `("PASS"|"FAIL", {cells, warnings, errors, has_latches})`.
FAIL if return code != 0 or `"Latch inferred"` detected in the log.

---

### `core/validator.py` — Pre-run validation

| Function | What it checks |
|---|---|
| `validate_database(db)` | `project_config.yaml`, `tile_index.csv`, `records.csv`, `tiles/` exist |
| `validate_tools()` | `iverilog` and `yosys` in PATH (`shutil.which`) |
| `validate_run_inputs(db, tile_number, tile_config)` | `config/tile_XXXX/` exists; `src/rtl/` has `.v` files; `top_module` set and has matching `.v` file |
| `validate_project_config(project_config)` | `id_prefix` is not empty |
| `detect_iverilog_version()` | Runs `iverilog -V`, parses with `log_parser.parse_iverilog_version` |

---

### `core/csv_store.py` — CSV persistence

Manages two CSV files:

**`tile_index.csv`** — one row per tile, current `tile_id` for each `tile_number`:
```
tile_number, tile_id, tile_name, tile_author, version, revision
```

**`records.csv`** — one row appended per run:
```
Tile_ID, Run_ID, Date, Author, Objective, Status,
Version, Revision, Connectivity, Simulation, Synthesis,
Tool_Version, Main_Change, Run_Path, Tags, Semicolab
```

Both files: if empty, the header is written before the first append. If non-empty, the header is validated before any read/write. `get_tile_row` raises `VeriFlowError` if the tile is not found.

---

### `core/copier.py` — Flat file copy

`copy_flat(src_dir, dst_dir, extension=".v") → list[Path]`

Copies all files matching `extension` from `src_dir` to `dst_dir` without preserving subdirectory structure. Name collisions are resolved by appending `_1`, `_2`, etc. Returns the list of destination paths.

---

### `core/log_parser.py` — Output parsing

| Function | Input | Output |
|---|---|---|
| `parse_sim_log(log_text)` | `vvp` stdout | `{sim_time: "335 ns", seed: ""}` — parses `$finish called at N (unit)`, converts to ns |
| `parse_synth_log(log_text)` | `yosys` stdout | `{cells: "253", warnings: "0", errors: "0", has_latches: False}` — takes last `stat` block |
| `parse_iverilog_version(version_output)` | `iverilog -V` stdout | `"Icarus Verilog 13.0"` |

---

### `core/run_id.py` — Run ID generation

`get_next_run_id(runs_dir) → str`

Scans `runs_dir` for directories matching `run-NNN`. Returns `"run-001"` if none exist, otherwise the next zero-padded 3-digit ID.

---

### `core/tile_id.py` — Tile ID generation and parsing

**Format:** `<id_prefix>-<YYMMDD><tile_number:04d><version:02d><revision:02d>`

Example: `MST130-01-26032500010102`

- `generate_tile_id(id_prefix, tile_number, id_version, id_revision, today)` — builds the ID
- `parse_tile_id(tile_id) → dict` — decomposes into `{id_prefix, yymmdd, tile_number, id_version, id_revision}`; assumes the numeric block after the last `-` is exactly 14 characters

---

### `generators/` — Per-run documentation

| Module | Function | Output |
|---|---|---|
| `manifest.py` | `generate_manifest(data, output_path)` | `manifest.yaml` — custom serializer with blank-line sections; no `yaml.dump` |
| `notes.py` | `generate_notes(tile_id, tile_config, run_config, output_path)` | `notes.md` — designer notes from `run_config.notes` |
| `readme.py` | `generate_readme(tile_id, tile_config, output_path)` | `README.md` in `tiles/<tile_id>/` — regenerated on every run |
| `summary.py` | `generate_summary(...)` | `summary.md` — results table; also printed to console |

---

### `models/` — Configuration dataclasses

All models implement `from_dict(data)` using `.get()` with `""` defaults; `None` values normalized to `""`.

**`ProjectConfig`**
```python
@dataclass
class ProjectConfig:
    id_prefix: str
    project_name: str
    repo: str
    description: str
    semicolab: bool = True   # false → Universal mode, skip connectivity check
```
The `semicolab` field accepts YAML booleans and strings (`"false"`, `"0"`, `"no"` → `False`).

**`TileConfig`** — merged tile + run fields (single `tile_config.yaml`):
```python
@dataclass
class TileConfig:
    # Tile fields (fill once at create-tile time)
    tile_name: str
    tile_author: str
    top_module: str
    description: str
    ports: str
    usage_guide: str
    tb_description: str
    # Run fields (update before each run)
    run_author: str
    objective: str
    tags: str
    main_change: str
    notes: str
```

---

### `template/*.v` — Verilog templates (SemiCoLab mode)

| File | Role |
|---|---|
| `ip_tile.v` | Base RTL template with the 9 fixed ports; user implements logic between `// USER LOGIC STARTS HERE //` markers |
| `tb_base.v` | Internal testbench wrapper; contains `/* MODULE_INSTANTIATION */` and `/* USER_TEST */` placeholders; never edited by users |
| `tb_tasks.v` | Task library (`write_data_reg_a`, `write_data_reg_b`, `write_csr_in`, `reset_csr_in`, `read_csr_out`); included via `` `include `` in the wrapper |

On `create-tile`, `tb_base.v` is copied to `config/tile_XXXX/src/tb/tb_tile.v` — this is the file the user edits to write tests.

---

### `ui/` — Terminal UI and styled output

| Module | Role |
|---|---|
| `ui/theme.py` | Central Rich color palette and `VERIFLOW_THEME`; all UI modules import from here |
| `ui/output.py` | Styled output helpers used by all commands: `print_status`, `print_section`, `print_run_header`, `print_done`, `print_fail_detail`, `print_wave_url`, `print_ports_table`, `print_file_tree` |
| `ui/banner.py` | SEMICOLAB ASCII banner; `pyfiglet` for figlet rendering + `TerminalTextEffects` MiddleOut animation (both optional, falls back gracefully); orange accent for VeriFlow, green for TileWizard; Mifral link shown once (`~/.semicolab_seen`) |
| `ui/themes.py` | 16 Textual-compatible color palettes; `Palette` dataclass with semantic keys (`bg`, `accent`, `green`, `red`, …); `~/.semicolab_theme` persists the selection; provides `build_css()` and `palette_to_vars()` for Textual CSS injection |
| `ui/tui.py` | Redirect stub: delegates to `tilebench.tui.selector.run_veriflow(workspace=None)` (requires `tilebench` installed) |
