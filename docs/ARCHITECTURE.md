# VeriFlow — Architecture Reference

---

## Overview: Full execution flow

```
veriflow (no args)
    └── ui/tui.py → tilebench.tui.selector.run_veriflow()

veriflow project run [--config veriflow.yaml]
    └── cli.py main()
            └── commands/run_project.py
                    └── workflows/project.py (ProjectWorkflow)
                            ├── workflows/project_config.py  (veriflow.yaml parsing)
                            ├── framework/                   (Design, Flow, RunRequest)
                            └── core/stages/ + core/backends/

veriflow db <command> --db ./database [flags]
    └── cli.py main()
            └── argparse dispatch
                    ├── db init          → commands/init_db.py
                    ├── db create-tile   → commands/create_tile.py
                    ├── db run           → commands/run.py
                    │       └── workflows/database.py (DatabaseWorkflow)
                    │               ├── core/validator.py    (validate DB + tools + inputs)
                    │               ├── core/copier.py       (copy RTL/TB to run/src/)
                    │               ├── core/pipeline_builder.py (build stages)
                    │               ├── core/stages/         (connectivity, simulation, synthesis)
                    │               ├── generators/          (manifest, results.json, notes, summary, README)
                    │               └── core/csv_store.py    (append records.csv row)
                    ├── db waves         → commands/waves.py
                    │       └── core/sim_runner.py   (open_surfer / launch_waves)
                    ├── db bump-version  → commands/bump_version.py
                    ├── db bump-revision → commands/bump_revision.py
                    └── db list-tiles / list-runs / show-run → commands/db_read.py
```

Errors propagate as `VeriFlowError` (defined in `core/__init__.py`) and are caught at the CLI entry point with the error's exit code.

---

## Module reference

### `cli.py` — Entry point and routing

Parses arguments with `argparse` and dispatches to command handlers. Subcommands are grouped into two namespaces: `db` (Database Mode, all subcommands take `--db PATH`) and `project` (Project Mode). Two additional behaviors:

- **No arguments** → calls `ui/tui.py:run_tui()`, which launches the TileBench TUI in VeriFlow mode
- **`--json` / `--non-interactive`** → global flags placed before the subcommand

All imports of command modules are deferred (inside the `if` branches) to avoid loading unused code on every invocation.

---

### `workflows/database.py` — DatabaseWorkflow

The Database Mode execution engine. `commands/run.py` delegates here; the workflow performs no Rich output or wave launching (that is the caller's responsibility).

**`DatabaseWorkflow(database_path)`** main APIs:

| Method | Description |
|---|---|
| `run_tile(tile_number, options: DatabaseRunOptions) → DatabaseRunResult` | Execute the full pipeline for one tile |
| `list_tiles() → list[DatabaseTileInfo]` | One entry per registered tile (includes `interface_name`) |
| `list_runs(tile_id=…, tile_number=…) → list[DatabaseRunInfo]` | All runs for a tile, from persisted files |
| `load_run_result(tile_id=…, tile_number=…, run_id=…) → DatabaseRunResult` | Reload a persisted `results.json` without re-running tools |

`DatabaseRunOptions` carries `skip_connectivity`, `skip_sim`, `skip_synth`, `only_connectivity`, `only_sim`, `only_synth`.

`DatabaseRunResult` carries `tile_id`, `run_id`, `run_dir`, `status`, `interface_name`, `stages` (dict of `StageResult`), `sources`, `artifacts`, and `data` (the full `results.json` dict).

**`run_tile` flow:**
1. Resolves `--only-*` flags into `skip_*` combinations
2. Validates the database; validates tools only if at least one tool stage will run
3. Reads `tile_config.yaml` and `project_config.yaml`; resolves the interface profile from `interface_name`
4. No interface profile → `skip_check = True` automatically; `--only-check` with no profile → `VF_INTERFACE_CHECK_NO_PROFILE`
5. Validates run inputs; resolves `tile_id` from `tile_index.csv`; syncs `tile_name`/`tile_author` back to the index
6. Determines the next `run_id`; builds a `RunContext` (carries `interface_name` and the skip flags)
7. Creates the run directory tree and copies RTL/TB sources (no TB sources → `skip_sim = True`)
8. Builds the pipeline via `build_default_pipeline(...)` and runs the stages; connectivity FAIL stops the pipeline and finalizes immediately
9. `_finalize_run` generates `manifest.yaml`, `notes.md`, tile `README.md`, `summary.md`, and `results.json` (schema 1.2, includes `interface_name`), refreshes `works/`, and appends the `records.csv` row (includes the `Interface` column)

**Status derivation** (`_derive_status`):

| Condition | Status |
|---|---|
| `conn == "FAIL"` | `FAIL` |
| Any stage `SKIPPED` | `PARTIAL` |
| All executed stages PASS/COMPLETED | `PASS` |
| Simulation `FAILED` or synthesis `FAIL` | `FAIL` |

---

### `workflows/project.py` — ProjectWorkflow

Project Mode execution engine. `ProjectWorkflow.from_file(path)` loads a `ProjectWorkflowConfig` from `veriflow.yaml`; `run()` builds a `Design` + `Flow` and executes it into `<runs_dir>/run-NNN/`.

`build_project_flow(config)` assembles the stage list conditionally:
- `InterfaceStage` only if an `interface` section is configured
- `SimulationStage` only if `tb_sources` are present
- `SynthesisStage` always

See [PROJECT_CONFIG.md](PROJECT_CONFIG.md) for the `veriflow.yaml` schema and validation error codes.

---

### `commands/init_db.py` — Database initialization

Creates the canonical database layout under `<db>/`:
```
project_config.yaml    (template — id_prefix, project_name, repo, interface_name, description)
tile_index.csv         (empty — header written on first tile)
records.csv            (empty — header written on first run)
config/                (empty)
tiles/                 (.gitkeep)
```

With `--force`: overwrites an existing database entirely.

---

### `commands/create_tile.py` — Tile scaffolding

`cmd_create_tile(db, *, top_module="")`:

1. Reads and validates `project_config.yaml`; resolves the interface profile from `interface_name`
2. For Semicolab projects, `--top-module` is required and must be a valid Verilog identifier (`VF_TILE_TOP_MODULE_REQUIRED` / `VF_TILE_TOP_MODULE_INVALID`)
3. Calls `csv_store.get_next_tile_number()`; generates `tile_id` via `tile_id.generate_tile_id()` with version=01, revision=01, date=today
4. Creates `config/tile_XXXX/tile_config.yaml` (merged template with inline comments; `top_module` substituted when provided)
5. Creates `config/tile_XXXX/src/rtl/` and `src/tb/`; generates the self-contained testbench scaffold `src/tb/tb_tile.v` (Semicolab: from `template/tb_semicolab_template.v` with the DUT instantiation filled in; generic: from `template/tb_universal_template.v`)
6. Creates `tiles/<tile_id>/` with `README.md`, `works/rtl/`, `works/tb/`, `runs/`
7. Appends to `tile_index.csv` (row includes the `interface_name` column)

---

### `api.py` — Internal Python integration surface

`run_tile(db_path, tile, *, skip_connectivity, skip_sim, skip_synth, only_connectivity, only_sim, only_synth, waves, non_interactive) → dict`

Thin wrapper over `cmd_run()` for callers that want a Python-callable entry point without going through the CLI or subprocess.  Accepts `str | Path` for `db_path`; normalises it via `normalize_path()`.  All flag names mirror the CLI flags.  `VeriFlowError` propagates unchanged.  Raises `VF_NON_INTERACTIVE_VIEWER_DISABLED` if `waves=True` and `non_interactive=True`.

Intended consumers: TUI integration, CI/CD scripts, agent tooling.  This is an internal surface — it is not a REST or RPC API.

---

### `commands/run.py` — Run command presentation

Main entry: `cmd_run(db, tile_number, skip_*, only_*, waves)`.

Builds `DatabaseRunOptions`, calls `DatabaseWorkflow(db).run_tile(...)`, then handles presentation only: prints the run header, per-stage results, and completion line via `ui/output`, and launches the waveform viewer if `--waves` was passed and `waves.vcd` exists. Returns the `run_result` dict (same shape as `results.json`).

All pipeline logic lives in `DatabaseWorkflow` (see above).

---

### `commands/db_read.py` — Read-only database queries

| Function | Description |
|---|---|
| `cmd_db_list_tiles(db)` | Lists tiles from `tile_index.csv`; prints a Rich table; returns `list[DatabaseTileInfo]` |
| `cmd_db_list_runs(db, tile)` | Lists runs for a tile from persisted run directories |
| `cmd_db_show_run(db, run_id, tile)` | Loads one persisted `results.json` via `DatabaseWorkflow.load_run_result()` |

In `--json` mode the CLI serializes these results into the output payload.

---

### `core/pipeline_builder.py` — Default pipeline construction

`build_default_pipeline(*, rtl_files, tb_files, tb_top, top_module, profile=None, interface_profile=None) → PipelineRunner`

Centralises construction of the fixed three-stage pipeline (connectivity → simulation → synthesis).  Builds a `Design` from the sources and returns a `PipelineRunner` whose `.stages` list holds the three stage instances in order.

- `interface_profile` is forwarded to `InterfaceStage`; when the context's `skip_connectivity` is set the stage reports `SKIPPED`.
- `tb_top` selects the testbench top module for `SimulationStage` and must be non-empty (`VF_SIM_TB_TOP_REQUIRED`).
- `profile: ExecutionProfile` (defaults to `default_execution_profile()`) supplies tool labels and backend IDs; backend instances are obtained from the backend registry. Stage constructors still accept an explicit `backend` parameter, so tests can inject mocks directly.

`DatabaseWorkflow` calls this once after sources are copied, then runs each stage individually via single-stage `PipelineRunner` calls so that the connectivity-FAIL early-exit logic is preserved.

This is an internal construction helper.  The pipeline order and stage set are fixed; there is no plugin registry or dynamic dispatch.

---

### `core/stages/` — Pipeline stages

All stages implement `run(input: StageInput) → StageResult`, where `StageInput` carries the `Design` and the run context.

| Stage | Module | Behavior |
|---|---|---|
| `InterfaceStage` (name `"connectivity"`) | `stages/connectivity.py` | Skips if `ctx.skip_connectivity`; otherwise requires an `InterfaceProfile` and runs the backend's connectivity check against the RTL |
| `SimulationStage` | `stages/simulation.py` | Skips if `ctx.skip_sim` or no TB sources; otherwise compiles RTL+TB with the explicit `tb_top` and runs the simulation |
| `SynthesisStage` | `stages/synthesis.py` | Skips if `ctx.skip_synth`; otherwise runs Yosys synthesis |

`InterfaceStage` writes its artifacts under the historical `out/connectivity/` path.

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

The registry uses a plain Python dictionary and no dynamic imports.  Project Mode's `execution` section may name backends explicitly; today the only registered names are the defaults.  No plugins or alternate backends are wired in at this stage.

---

### `models/interface_profile.py` — Interface profiles

`InterfaceProfile` is a frozen dataclass (`name`, `description`, tuple of `InterfacePort(name, direction, width)`). The built-in `semicolab` profile defines the nine-port structural contract required by the Semicolab harness.

Registry APIs (used by frontends such as TileWizard/TileBench to enumerate profiles):

```python
get_interface_profile(name)          # None for name=None (generic project); VF_INTERFACE_UNKNOWN otherwise
list_interface_profile_names()
list_interface_profiles()
has_interface_profile(name)
default_interface_profile()          # always None — interfaces are opt-in
```

VeriFlow has no default interface: projects must opt in explicitly via `interface_name` (Database Mode) or `interface.name` (Project Mode). An omitted or null value means a generic project with no interface checking. Custom YAML-defined interfaces are future work.

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

### `models/profile_loader.py` — Profile file loading (internal foundation)

`load_execution_profile(path: str | Path) → ExecutionProfile`

Reads a YAML file and returns a populated `ExecutionProfile`.  This is an **internal foundation only** — it is not exposed through the CLI and does not affect default behavior when no profile file is provided.

**Supported YAML keys:**

| Key | Type | Default |
|---|---|---|
| `name` | str | `"default"` |
| `connectivity_backend` | str | `"icarus"` |
| `simulation_backend` | str | `"icarus"` |
| `synthesis_backend` | str | `"yosys"` |
| `connectivity_tool` | str | `"iverilog"` |
| `simulation_tool` | str | `"iverilog/vvp"` |
| `synthesis_tool` | str | `"yosys"` |
| `technology_name` | str | `"generic"` |
| `doc_profile` | str | `"default"` |

All keys are optional; missing keys take their `ExecutionProfile` defaults.  Keys not in the table above raise `VeriFlowError` with code `VF_PROFILE_UNKNOWN_KEY`.

Backend names are validated via the backend registry; an unrecognised name propagates the registry's `VeriFlowError` (`VF_BACKEND_CONNECTIVITY_UNKNOWN`, `VF_BACKEND_SIMULATION_UNKNOWN`, or `VF_BACKEND_SYNTHESIS_UNKNOWN`).  `technology_name` is validated via `get_technology_profile()`; an unrecognised name propagates `VF_TECHNOLOGY_UNKNOWN`.

**Current status:**
- Not wired into any CLI flag or command.
- Default behavior (no profile file) is completely unchanged.
- Intended as the foundation for a future `--profile` flag once implementation-stage profiles are designed.

**Future direction (not implemented):** Flow profiles may later support implementation stages such as LibreLane/OpenLane synthesis flows.  The loader, error codes, and validation contracts defined here are intended to remain stable as that surface is added.

---

### `models/execution_profile.py` — Toolchain description

`ExecutionProfile` is a plain dataclass that records which external tools and internal backend IDs the current fixed pipeline uses.

```python
@dataclass
class ExecutionProfile:
    name: str = "default"
    connectivity_tool: str = "iverilog"
    simulation_tool: str = "iverilog/vvp"
    synthesis_tool: str = "yosys"
    doc_profile: str = "default"
    # Internal backend IDs
    connectivity_backend: str = "icarus"
    simulation_backend: str = "icarus"
    synthesis_backend: str = "yosys"
```

The `*_tool` fields determine the `StageResult.tool` label written to `results.json`.  The `*_backend` fields are IDs passed to the backend registry by `build_default_pipeline` (and by Project Mode's `execution` section).

`default_execution_profile() → ExecutionProfile` returns the canonical instance.

**Future work (not implemented):** alternate backend implementations and plugins are intentionally deferred.

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

### `core/sim_runner.py` — Connectivity check, simulation, wave viewer

Testbenches are self-contained — there is no injection, marker extraction, or temp TB rewriting.

**Connectivity / interface check:**

- `_build_interface_check_wrapper(top_module, interface_profile)` — generates a minimal Verilog elaboration wrapper from the profile: one signal per declared port plus a named-port DUT instantiation. No clock, reset, tasks, or stimulus.
- `run_connectivity_check(rtl_files, interface_profile, top_module, log_path)` — compiles the RTL sources plus the generated wrapper with `iverilog -o NUL//dev/null`; does not read user testbench files; returns `"PASS"` or `"FAIL"`

**Simulation:**

- `run_simulation(rtl_files, tb_files, tb_top, sim_log_path, wave_path)` — compiles all RTL and TB files together with `iverilog -s <tb_top>` into `tempfile.mkdtemp()` (avoids Windows path-with-spaces issues), runs `vvp` from `wave_path.parent` so `$dumpfile("waves.vcd")` lands in the correct directory; returns `("COMPLETED"|"FAILED", {sim_time, seed})`. `$dumpfile`/`$dumpvars` must be present in the testbench itself.

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
tile_number, tile_id, tile_name, tile_author, version, revision, interface_name
```

**`records.csv`** — one row appended per run:
```
Tile_ID, Run_ID, Date, Author, Objective, Status,
Version, Revision, Connectivity, Simulation, Synthesis,
Tool_Version, Main_Change, Run_Path, Tags, Interface
```

`interface_name` / `Interface` hold the interface profile name (e.g. `semicolab`), empty for generic projects.

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
| `results.py` | `generate_results_json(data, output_path)` | `results.json` — machine-readable run result (schema 1.2) |
| `notes.py` | `generate_notes(tile_id, tile_config, output_path)` | `notes.md` — designer notes from `tile_config.notes` |
| `readme.py` | `generate_readme(tile_id, tile_config, output_path)` | `README.md` in `tiles/<tile_id>/` — regenerated on every run |
| `summary.py` | `generate_summary(...)` | `summary.md` — results table; also printed to console |

---

### `models/` — Configuration dataclasses

**`ProjectConfig`** (Database Mode `project_config.yaml`)
```python
@dataclass
class ProjectConfig:
    id_prefix: str
    project_name: str
    repo: str
    description: str
    interface_name: str | None = None   # None → generic project
```
`from_dict` requires the `interface_name` key (`VF_PROJECT_INTERFACE_REQUIRED` if missing) and rejects the deprecated `semicolab` key (`VF_PROJECT_INTERFACE_CONFIG_LEGACY`).

**`TileConfig`** — merged tile + run fields (single `tile_config.yaml`):
```python
@dataclass
class TileConfig:
    # Tile fields (fill once at create-tile time)
    tile_name: str
    tile_author: str
    top_module: str
    tb_top_module: str   # testbench top module, defaults to "tb"
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

**`RunContext`** — per-run execution context handed to stages: `tile_id`, `run_id`, `tile_dir`, `run_dir`, `interface_name`, `skip_connectivity`, `skip_sim`, `skip_synth`, `db_path`; plus derived path properties and `log_rel()`.

**`StageResult`** — uniform per-stage result (`name`, `status`, `tool`, `log_paths`, `artifacts`, `metrics`, `error`); `to_dict()` produces the stage dictionaries persisted in `results.json`.

---

### `template/*.v` — Testbench scaffold templates

Used only at `create-tile` time to generate the initial `src/tb/tb_tile.v`. After scaffolding, the file belongs entirely to the user; nothing is injected at run time.

| File | Role |
|---|---|
| `tb_semicolab_template.v` | Self-contained Semicolab testbench scaffold: nine-port signals, clock/reset, `$dumpfile`/`$dumpvars`, helper tasks, `/* DUT_MODULE */` placeholder replaced with `--top-module`, marked user-stimulus block |
| `tb_universal_template.v` | Minimal generic scaffold: empty `module tb` with waveform dump; user declares signals and instantiates the DUT |

---

### `ui/` — Terminal UI and styled output

| Module | Role |
|---|---|
| `ui/theme.py` | Central Rich color palette and `VERIFLOW_THEME`; all UI modules import from here |
| `ui/output.py` | Styled output helpers used by all commands: `print_status`, `print_section`, `print_run_header`, `print_done`, `print_fail_detail`, `print_wave_url`, `print_ports_table` |
| `ui/banner.py` | SEMICOLAB ASCII banner; `pyfiglet` for figlet rendering + `TerminalTextEffects` MiddleOut animation (both optional, falls back gracefully); orange accent for VeriFlow, green for TileWizard; Mifral link shown once (`~/.semicolab_seen`) |
| `ui/themes.py` | 16 Textual-compatible color palettes; `Palette` dataclass with semantic keys (`bg`, `accent`, `green`, `red`, …); `~/.semicolab_theme` persists the selection; provides `build_css()` and `palette_to_vars()` for Textual CSS injection |
| `ui/tui.py` | Redirect stub: delegates to `tilebench.tui.selector.run_veriflow(workspace=None)` (requires `tilebench` installed) |
