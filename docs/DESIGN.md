# VeriFlow V1 — Detailed Technical Design

## 1. General Architecture

VeriFlow follows a layered architecture:

```
CLI (cli.py)
    └── Commands (commands/)          ← per-command orchestration + presentation
            ├── Workflows (workflows/)   ← DatabaseWorkflow / ProjectWorkflow
            ├── Core (core/)             ← reusable logic, stages, backends, no UI
            ├── Generators (generators/) ← file generation
            └── Models (models/)         ← configuration dataclasses + profiles
```

Communication between layers is unidirectional — commands use workflows, core, and generators, never the reverse. Errors propagate as `VeriFlowError` and are caught at the CLI entry point.

The execution engines live in `workflows/`:

- **`DatabaseWorkflow`** (`workflows/database.py`) — runs the pipeline for a tile in a database, generates all documentation, and updates the CSVs. `commands/run.py` delegates to it and only handles terminal presentation and wave launching.
- **`ProjectWorkflow`** (`workflows/project.py`) — runs the pipeline for a `veriflow.yaml` project (Project Mode). See [PROJECT_CONFIG.md](PROJECT_CONFIG.md) for the config schema.

---

## 2. Module: `cli.py`

**Responsibility:** Entry point. Parses arguments and dispatches to the correct command.

**Implementation:** `argparse` with two nested subcommand namespaces: `db` (Database Mode) and `project` (Project Mode). Catches `VeriFlowError` and prints it as `[ERROR]` with the error's exit code. In `--json` mode, errors are serialized to stdout as `{ "status": "ERROR", "error": VeriFlowError.to_dict() }`.

### Global flags

| Flag | Behavior |
|---|---|
| `--json` | Quiet Rich output (`console.quiet = True`); redirect all `print()` to stderr; emit single JSON object to stdout after command completes |
| `--non-interactive` | Block TUI launch and waveform viewer; error if combined with `--waves` or the `waves` subcommand |

### Entry point
With `pip install -e .`, the `veriflow` command maps to `veriflow.cli:main`. Direct execution with `python veriflow/cli.py` is also supported via a path fix at the top of the file:
```python
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))
```

### Registered subcommands

| Subcommand | Handler |
|---|---|
| `project run` | `commands.run_project.cmd_run_project` |
| `db init` | `commands.init_db.cmd_init` |
| `db create-tile` | `commands.create_tile.cmd_create_tile` |
| `db run` | `commands.run.cmd_run` |
| `db waves` | `commands.waves.cmd_waves` |
| `db bump-version` | `commands.bump_version.cmd_bump_version` |
| `db bump-revision` | `commands.bump_revision.cmd_bump_revision` |
| `db list-tiles` | `commands.db_read.cmd_db_list_tiles` |
| `db list-runs` | `commands.db_read.cmd_db_list_runs` |
| `db show-run` | `commands.db_read.cmd_db_show_run` |

All `db` subcommands take a required `--db PATH` flag. Invoking `veriflow` with no arguments launches the TUI.

---

## 3. Module: `core/__init__.py`

Defines the base exception:

```python
class VeriFlowError(Exception):
    """Hard error — stops execution and displays [ERROR]."""
    code: str        # stable error code string (e.g. "VF_TILE_CONFIG_MISSING")
    details: dict    # optional structured context (e.g. {"path": "..."})
    exit_code: int   # process exit code (default 1)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "details": self.details, "exit_code": self.exit_code}
```

All errors that must stop the pipeline are raised as `VeriFlowError`. The CLI catches them at the top level and either prints `[ERROR] <message>` (human mode) or emits `{ "status": "ERROR", "error": e.to_dict() }` (JSON mode).

---

## 4. Module: `core/tile_id.py`

**Responsibility:** Tile ID generation and parsing.

### `generate_tile_id(id_prefix, tile_number, id_version, id_revision, today)`
Builds the Tile ID in the format:
```
<id_prefix>-<YYMMDD><tile_number:04d><id_version:02d><id_revision:02d>
```

### `parse_tile_id(tile_id) → dict`
Decomposes a Tile ID into its parts. Logic assumes the numeric block after the last `-` is exactly 14 characters: 6 (date) + 4 (tile_number) + 2 (version) + 2 (revision).

Returns: `{id_prefix, yymmdd, tile_number, id_version, id_revision}`

---

## 5. Module: `core/run_id.py`

### `get_next_run_id(runs_dir) → str`
Scans `runs_dir` for folders matching `run-NNN`. Returns the next ID with 3-digit zero padding. Returns `"run-001"` if no runs exist.

---

## 6. Module: `core/csv_store.py`

**Responsibility:** Read and write `tile_index.csv` and `records.csv`.

### Expected headers
```python
TILE_INDEX_HEADER = ["tile_number", "tile_id", "tile_name", "tile_author", "version", "revision", "interface_name"]
RECORDS_HEADER    = ["Tile_ID", "Run_ID", "Date", "Author", "Objective", "Status",
                     "Version", "Revision", "Connectivity", "Simulation", "Synthesis",
                     "Tool_Version", "Main_Change", "Run_Path", "Tags", "Interface"]
```

### Main functions

| Function | Description |
|---|---|
| `read_tile_index(path)` | Reads CSV, validates header |
| `append_tile_index(path, row)` | Appends with auto-header if empty |
| `update_tile_index(path, tile_number, row)` | Replaces the row for the given tile |
| `get_tile_row(path, tile_number)` | Returns row or raises `VeriFlowError` |
| `get_next_tile_number(path)` | Returns the next available number |
| `append_record(path, row)` | Appends to records.csv with auto-header |

### Empty file rule
If a CSV exists but is empty, the header is written before the first append. This allows `init` to create empty files without content.

---

## 7. Module: `core/copier.py`

### `copy_flat(src_dir, dst_dir, extension=".v") → list[Path]`
Copies all files with the given extension from `src_dir` to `dst_dir` in a flat manner (no subdirectory preservation). Resolves name collisions by appending `_1`, `_2`, etc. suffixes.

---

## 8. Module: `core/validator.py`

**Responsibility:** All system validations.

### `validate_database(db)`
Verifies that `project_config.yaml`, `tile_index.csv`, `records.csv`, and `tiles/` exist.

### `validate_tools()`
Verifies that `iverilog` and `yosys` are in PATH using `shutil.which`. Only called when at least one external tool stage will run.

### `validate_run_inputs(db, tile_number_str, tile_config)`
Verifies:
- `config/tile_XXXX/` exists
- `src/rtl/` has `.v` files
- `top_module` is not empty
- A `.v` file whose stem matches `top_module` exists

### `validate_project_config(project_config)`
Verifies that `id_prefix` is not empty.

### `detect_iverilog_version() → str`
Runs `iverilog -V` and parses the version using `log_parser.parse_iverilog_version`.

---

## 9. Module: `core/sim_runner.py`

**Responsibility:** Interface/connectivity check, simulation, and waveform viewer launching. Testbenches are self-contained — there is no injection or marker extraction.

### `_build_interface_check_wrapper(top_module, interface_profile) → str`
Generates a minimal Verilog elaboration wrapper from an `InterfaceProfile`: one signal per declared port (using the profile's width and direction), plus a named-port instantiation of `top_module`. The wrapper contains no clock behaviour, reset, tasks, stimulus, or user test content.

Diagnostic limitation: elaboration backends report port-not-found errors when a declared port is absent from the DUT, but do not flag DUT ports missing from the profile — the profile is a declared set of connections, not a complete enumeration of the DUT's interface.

### `run_connectivity_check(rtl_files, interface_profile, top_module, log_path) → str`
Compiles only the RTL sources plus the generated wrapper with iverilog (output discarded to `/dev/null` or `NUL`). Does not read or compile user testbench files. Returns `"PASS"` or `"FAIL"`.

### `run_simulation(rtl_files, tb_files, tb_top, sim_log_path, wave_path) → tuple[str, dict]`
1. Compiles all `rtl_files` and `tb_files` together with `iverilog -s <tb_top>` — the testbench top module is selected explicitly; no temp TB sources, no hidden helpers
2. Compiles into a temp directory without spaces (`tempfile.mkdtemp()`) to avoid Windows path issues
3. Runs `vvp` from `wave_path.parent` so `$dumpfile("waves.vcd")` lands in the correct location
4. Returns `("COMPLETED"|"FAILED", {sim_time, seed})`

VeriFlow does not insert `$dumpfile`/`$dumpvars` — the testbench (or the generated scaffold) must contain them for waveforms to be captured.

**Windows fix:** Uses `.as_posix()` on all paths for subprocess calls.

### `open_surfer(wave_path)`
Docker mode only. Constructs `http://localhost:7681/?load_url=<vcd_url>` where `<vcd_url>` is the VCD resolved relative to `/workspace`. Prints the URL and calls `webbrowser.open()` as best-effort. Handles VCDs outside `/workspace` gracefully (opens Surfer without preloading).

### `launch_waves(wave_path)`
Priority chain (non-blocking `subprocess.Popen`):
1. `VERIFLOW_DOCKER` env var (or deprecated `SEMICOLAB_DOCKER`) → delegates to `open_surfer()`
2. `surfer` found in PATH → Surfer native binary
3. Not found → prints Surfer install hint

---

## 10. Module: `core/synth_runner.py`

### `run_synthesis(rtl_files, top_module, synth_log_path) → tuple[str, dict]`
Builds and executes an inline Yosys script:
```
read_verilog <files>
hierarchy -check -top <top_module>
synth
check
stat
```
Returns `("PASS"|"FAIL", {cells, warnings, errors, has_latches})`.

FAIL if: return code != 0 or `"Latch inferred"` detected in the log.

---

## 11. Module: `core/log_parser.py`

### `parse_sim_log(log_text) → dict`
Searches for the iverilog pattern:
```
$finish called at 335000 (1ps)
```
Converts to nanoseconds according to the reported unit. Returns `{sim_time, seed}`.

### `parse_synth_log(log_text) → dict`
Searches for the Yosys stat pattern:
```
      253 cells
```
Takes the last occurrence (final stat block). Returns `{cells, warnings, errors, has_latches}`.

### `parse_iverilog_version(version_output) → str`
Searches for `"Icarus Verilog version X.Y"` in `iverilog -V` output.

---

## 12. Module: `models/`

Configuration dataclasses with `from_dict` classmethods.

### `ProjectConfig` (Database Mode `project_config.yaml`)
```python
@dataclass
class ProjectConfig:
    id_prefix: str
    project_name: str
    repo: str
    description: str
    interface_name: str | None = None   # None → generic project, no connectivity check
```

`from_dict` requires the `interface_name` key to be present (`VF_PROJECT_INTERFACE_REQUIRED` if missing) and rejects the deprecated `semicolab` key (`VF_PROJECT_INTERFACE_CONFIG_LEGACY`). An empty or whitespace string normalizes to `None`.

### `TileConfig`
Merged model — contains both tile fields (permanent) and run fields (updated each run). This is the only per-tile config model; there is no separate run-config model:
```python
@dataclass
class TileConfig:
    # Tile fields
    tile_name: str
    tile_author: str
    top_module: str
    tb_top_module: str    # testbench top module name, defaults to "tb"
    description: str
    ports: str
    usage_guide: str
    tb_description: str
    # Run fields
    run_author: str
    objective: str
    tags: str
    main_change: str
    notes: str
```

### `InterfaceProfile` / interface registry (`models/interface_profile.py`)
`InterfaceProfile` is a frozen dataclass: `name`, `description`, and a tuple of `InterfacePort(name, direction, width)`. The registry exposes:

| Function | Description |
|---|---|
| `get_interface_profile(name)` | Profile for `name`; `None` for `name=None` (generic); `VF_INTERFACE_UNKNOWN` for unregistered names |
| `list_interface_profile_names()` | Registered names in stable order |
| `list_interface_profiles()` | Fresh profile instances |
| `has_interface_profile(name)` | Membership check |
| `default_interface_profile()` | Always `None` — projects must opt in explicitly |

The built-in profile is `semicolab` — the nine-port structural contract required by the Semicolab harness (see section 19).

### `RunContext` (`models/run_context.py`)
Per-run execution context passed to pipeline stages:
```python
@dataclass
class RunContext:
    tile_id: str
    run_id: str
    tile_dir: Path
    run_dir: Path
    interface_name: str | None
    skip_connectivity: bool
    skip_sim: bool
    skip_synth: bool
    db_path: Path | None = None
```
Provides derived path properties (`src_dir`, `out_dir`, `sim_dir`, `synth_dir`, `impl_dir`, `manifest_path`, `summary_path`, `notes_path`, `results_path`) and `log_rel()` for database-relative log paths.

### `StageResult` (`models/stage_result.py`)
Uniform per-stage result: `name`, `status`, `tool`, `log_paths`, `artifacts`, `metrics`, `error`. `to_dict()` produces the stage dictionaries persisted in `results.json`.

---

## 13. Module: `generators/readme.py`

### `generate_readme(tile_id, tile_config, output_path)`
Generates `README.md` with fields from `tile_config`. Called in `create-tile` (with empty config) and regenerated on every `run` with updated config.

---

## 14. Module: `generators/notes.py`

### `generate_notes(tile_id, tile_config, output_path)`
Generates `notes.md` with the `notes` field from `tile_config`. Generated once per run.

---

## 15. Module: `generators/manifest.py`

### `generate_manifest(data, output_path)`
Wrapper over `_render_manifest`.

### `_render_manifest(data) → str`
Custom serializer — **does not use `yaml.dump`**. Generates YAML manually inserting blank lines between logical sections for readability. All values are wrapped in double quotes. Empty lists render as `[]`, non-empty as items with `- "value"`.

Manifest sections:
1. Identity (tile_id, run_id, date, author)
2. Objective and status
3. Tile info (tile_name, top_module, version, revision)
4. Tools (simulator, synthesizer + versions)
5. Run params (sim_time, seed)
6. Sources (rtl[], tb[])
7. Artifacts (logs[], waves[])
8. Results (connectivity, simulation, synthesis, cells, warnings, errors)

---

## 16. Module: `generators/summary.py`

### `generate_summary(...) → str`
Generates `summary.md` with a results table and also prints it to the console. Returns the string so `cmd_run` can print it.

Table format:
```
| Stage        | Result        | Details          |
|--------------|---------------|------------------|
| Connectivity | PASS          |                  |
| Simulation   | COMPLETED     | 335 ns           |
| Synthesis    | PASS          | 253 cells        |
```

---

## 17. Commands

### `cmd_init(db, force)`
Creates the full database structure. With `--force` overwrites if it already exists. Writes the `project_config.yaml` template (including `interface_name: "semicolab"` as the starting value). Creates `.gitkeep` in `tiles/`.

### `cmd_create_tile(db, *, top_module="")`
1. Reads and validates `project_config.yaml` (including `interface_name`)
2. For Semicolab projects, requires a valid `top_module` (`VF_TILE_TOP_MODULE_REQUIRED` / `VF_TILE_TOP_MODULE_INVALID`)
3. Calculates next `tile_number` and generates `tile_id` with version=01, revision=01
4. Creates `config/tile_XXXX/` with `tile_config.yaml` (merged template with comments; `top_module` substituted when provided)
5. Creates `src/rtl/` and `src/tb/`; generates the self-contained testbench scaffold `tb_tile.v` from the matching template (Semicolab: DUT pre-instantiated; generic: minimal skeleton)
6. Creates `tiles/<tile_id>/` with README, works/, runs/
7. Appends to `tile_index.csv` (including the `interface_name` column)

### `cmd_run(db, tile_number, skip_*, only_*, waves)`
Thin presentation wrapper: builds `DatabaseRunOptions`, delegates execution to `DatabaseWorkflow.run_tile()`, prints the Rich result summary, and launches the waveform viewer if `--waves` was passed and `waves.vcd` exists. Returns the `run_result` dict (same shape as `results.json`).

`DatabaseWorkflow.run_tile()` (in `workflows/database.py`) performs the actual pipeline: validation, config loading, interface profile resolution (no profile → connectivity skipped automatically; `--only-check` without a profile → `VF_INTERFACE_CHECK_NO_PROFILE`), source copying, stage execution via `PipelineRunner`, and finalization (documentation generation + CSV update).

### `cmd_run_project(config_path) → int`
Project Mode entry: loads `veriflow.yaml` via `ProjectWorkflowConfig.from_file()`, runs `ProjectWorkflow`, prints the result, and returns the exit code (0 on overall PASS).

### `cmd_waves(db, tile_number, run_id)`
Resolves run ID (latest if not specified), verifies `waves.vcd` exists, then calls `launch_waves()`.

### `cmd_db_list_tiles(db)` / `cmd_db_list_runs(db, tile)` / `cmd_db_show_run(db, run_id, tile)`
Read-only queries over `tile_index.csv` and persisted `results.json` files, backed by `DatabaseWorkflow.list_tiles()`, `list_runs()`, and `load_run_result()`.

### `cmd_bump_version(db, tile_number)`
- Increments version, revision unchanged
- Preserves previous directory
- Creates new directory with works/ copied and clean runs/

### `cmd_bump_revision(db, tile_number)`
- Increments revision, version **reset to 01**
- Preserves previous directory
- Creates new directory with works/ copied and clean runs/

---

## 18. Verilog Templates

Templates are scaffold-time only: `create-tile` copies/instantiates them once into `src/tb/tb_tile.v`, and from then on the file belongs entirely to the user. Nothing is injected at run time.

### `tb_semicolab_template.v`
Self-contained testbench scaffold for Semicolab projects. Contains the nine-port signal declarations, clock generation, reset sequence, `$dumpfile`/`$dumpvars`, helper tasks (`write_data_reg_a`, `write_data_reg_b`, `write_csr_in`, `reset_csr_in`, `read_csr_out`), a `/* DUT_MODULE */` placeholder replaced with `--top-module` at scaffold time, and a marked user-stimulus block.

### `tb_universal_template.v`
Minimal self-contained scaffold for generic projects: an empty `module tb` with `$dumpfile`/`$dumpvars` and an empty stimulus block. The user declares signals and instantiates the DUT.

---

## 19. Semicolab Interface Profile

Tiles in a Semicolab project (`interface_name: "semicolab"`) implement exactly these ports:

| Port | Direction | Width | Description |
|---|---|---|---|
| `clk` | input | 1 | Clock |
| `arst_n` | input | 1 | Async reset, active low |
| `csr_in` | input | 16 | Control/Status Register input |
| `data_reg_a` | input | 32 | Operand A |
| `data_reg_b` | input | 32 | Operand B |
| `data_reg_c` | output | 32 | Result |
| `csr_out` | output | 16 | Control/Status Register output |
| `csr_in_re` | output | 1 | CSR input read enable |
| `csr_out_we` | output | 1 | CSR output write enable |

This contract is defined as the `semicolab` `InterfaceProfile` in `models/interface_profile.py` and enforced by the connectivity check. Generic projects have no port contract.

---

## 20. Module: `ui/`

**Responsibility:** Terminal presentation layer. All commands import from here — no output formatting logic lives in `commands/` or `core/`.

### `ui/theme.py`
Defines the central Rich color palette (hex constants: `BLUE`, `GREEN`, `ORANGE`, `RED`, `GREY`, `WHITE`) and `VERIFLOW_THEME` (`rich.theme.Theme`). All UI modules import colors and styles from here.

### `ui/output.py`
Styled output helpers using a `rich.console.Console` instance with `VERIFLOW_THEME`. Key functions:

| Function | Output |
|---|---|
| `print_status(label, status, detail)` | Dot-leader line: `  label ·····  STATUS  [detail]` |
| `print_section(title)` | Section header with separator line |
| `print_run_header(db, tile_id, run_id)` | Run metadata block |
| `print_done(message)` | `✓  message` completion line |
| `print_fail_detail(message, log_path)` | Indented failure detail + log path |
| `print_wave_url(url)` | Styled browser link |
| `print_ports_table(ports)` | Rich table of port definitions |

Status rendering: `PASS` → green bold; `FAIL` → red bold; `RUN` → `···` (secondary); others → secondary color.

### `ui/themes.py`
`Palette` frozen dataclass with 15 semantic color keys. `THEMES` dict maps 16 theme names to `Palette` instances. `get_palette(name)` resolves the active theme from `~/.veriflow_theme` (migrates silently from `~/.semicolab_theme`) with fallback to `"tokyo-night"`. `build_css(palette)` generates hardcoded-hex Textual CSS; `palette_to_vars(palette)` returns a `dict[str, str]` for `App.get_css_variables()` (live theming). Shared palette library for `tilebench`; not called directly from VeriFlow CLI.

---

## 21. Windows Compatibility Notes

- All paths use `pathlib.Path`
- Subprocess calls use `.as_posix()` on paths
- Simulation compilation uses `tempfile.mkdtemp()` to avoid paths with spaces
- `vvp` is run with the compiled binary via posix path
- Connectivity check uses `"NUL"` as output on Windows

---

## 22. Module: `models/execution_profile.py` — ExecutionProfile

**Responsibility:** Describe the current fixed toolchain configuration as a typed dataclass.

**Implementation:**

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

def default_execution_profile() -> ExecutionProfile:
    return ExecutionProfile()
```

`build_default_pipeline` accepts an optional `profile` kwarg (defaults to `default_execution_profile()`) and passes it to each stage. Stages read `profile.connectivity_tool` / `simulation_tool` / `synthesis_tool` for the `tool` field in `StageResult`. The `*_backend` IDs select backend instances from the backend registry.

In Database Mode there is one fixed profile. In Project Mode the `execution` section of `veriflow.yaml` may select backend names (today only the defaults are registered). There is no plugin registry or dynamic backend dispatch; alternate backends are future work.
