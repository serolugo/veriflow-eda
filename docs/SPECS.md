# VeriFlow V1 — System Specification

## 1. Overview

VeriFlow V1 is a lightweight RTL verification framework for multi-project ASIC chip design. It automates the interface/connectivity check, simulation, and synthesis flow, and generates structured documentation for every run.

VeriFlow has two operating modes:

- **Database Mode** (`veriflow db ...`) — a tile database with indexed run history, generated documentation, and version tracking. Most of this specification describes Database Mode.
- **Project Mode** (`veriflow project run`) — verifies a local project directory described by a single `veriflow.yaml` file. See [PROJECT_CONFIG.md](PROJECT_CONFIG.md) for its configuration schema.

The system is composed of three internal components orchestrated through a single CLI:

- **VeriTile** — RTL verification engine (connectivity check, simulation, synthesis)
- **AutoDoc** — documentation engine (run records, structured files, CSV indexes)
- **VeriFlow** — CLI orchestrator that coordinates both

---

## 2. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| External dependencies | PyYAML, Rich |
| Persistence | CSV + YAML + JSON (no database server) |
| Simulator | Icarus Verilog (`iverilog`, `vvp`) |
| Synthesizer | Yosys |
| Waveform viewer | Surfer (optional) |
| Tool distribution | OSS CAD Suite (optional — any PATH install of iverilog/yosys works) |
| Compatibility | Windows, Linux, macOS |
| CI/CD | GitHub Actions compatible |

---

## 3. Project Structure

```
veriflow/
├── cli.py                   # CLI entry point (db / project namespaces)
├── api.py                   # Internal Python integration surface (run_tile)
├── commands/                # Per-command implementation
│   ├── init_db.py
│   ├── create_tile.py
│   ├── run.py
│   ├── run_project.py       # Project Mode runner
│   ├── db_read.py           # list-tiles / list-runs / show-run
│   ├── waves.py
│   ├── bump_version.py
│   └── bump_revision.py
├── core/                    # Reusable core logic
│   ├── __init__.py          # VeriFlowError
│   ├── tile_id.py
│   ├── run_id.py
│   ├── csv_store.py
│   ├── copier.py
│   ├── pipeline.py          # PipelineStage / PipelineRunner
│   ├── pipeline_builder.py  # build_default_pipeline
│   ├── stages/              # connectivity, simulation, synthesis stages
│   ├── backends/            # icarus / yosys backends + registry
│   ├── sim_runner.py
│   ├── synth_runner.py
│   ├── log_parser.py
│   └── validator.py
├── framework/               # Stage framework (Design, Flow, Stage, StageInput, …)
├── generators/              # Documentation file generators
│   ├── readme.py
│   ├── notes.py
│   ├── manifest.py
│   ├── summary.py
│   └── results.py           # results.json writer
├── models/                  # Configuration dataclasses
│   ├── project_config.py    # Database Mode project_config.yaml
│   ├── tile_config.py       # merged tile + run fields
│   ├── interface_profile.py # interface profile registry (semicolab)
│   ├── execution_profile.py
│   ├── technology_profile.py
│   ├── profile_loader.py
│   ├── run_context.py
│   ├── stage_context.py
│   └── stage_result.py
├── workflows/               # Mode orchestration
│   ├── database.py          # DatabaseWorkflow
│   ├── project.py           # ProjectWorkflow
│   └── project_config.py    # veriflow.yaml parsing
├── template/                # Testbench scaffold templates
│   ├── tb_semicolab_template.v
│   └── tb_universal_template.v
├── ui/                      # Terminal UI and styled output
│   ├── banner.py            # SEMICOLAB banner (pyfiglet + TerminalTextEffects)
│   ├── output.py            # Styled output helpers (Rich)
│   ├── theme.py             # Central color palette and Rich theme
│   ├── themes.py            # 16 Textual-compatible color palettes
│   └── tui.py               # Redirect stub to tilebench TUI
└── tests/
    ├── runner.py
    └── test_*.py
```

---

## 4. Database Structure

```
database/
├── project_config.yaml       # Global project configuration
├── tile_index.csv            # Index of all tiles
├── records.csv               # Full run history
├── config/
│   └── tile_XXXX/            # User-editable tile configuration
│       └── tile_config.yaml     # tile + run fields
│       └── src/
│           ├── rtl/          # User RTL sources
│           └── tb/           # User testbench (self-contained)
└── tiles/
    └── <tile_id>/            # Generated artifacts per tile
        ├── README.md
        ├── works/            # Latest verified sources
        │   ├── rtl/
        │   └── tb/
        └── runs/
            └── run-NNN/
                ├── manifest.yaml
                ├── results.json
                ├── notes.md
                ├── summary.md
                ├── src/
                │   ├── rtl/
                │   └── tb/
                └── out/
                    ├── connectivity/logs/
                    ├── sim/logs/ + waves/
                    └── synth/logs/
```

---

## 5. CLI Interface

```bash
veriflow [--json] [--non-interactive] db <command> --db <path> [options]
veriflow [--json] [--non-interactive] project run [--config veriflow.yaml]

# Also available as:
python -m veriflow.cli db <command> --db <path> [options]
```

### Global flags

| Flag | Description |
|---|---|
| `--json` | Suppress Rich output; emit single JSON object to stdout |
| `--non-interactive` | Disable TUI and waveform viewer; safe for CI/agent use |

### `db` subcommands

All take `--db <path>`.

| Command | Description |
|---|---|
| `db init [--force]` | Initialize the database |
| `db create-tile [--top-module NAME]` | Create a new tile (`--top-module` required for Semicolab projects) |
| `db run --tile XXXX [flags]` | Execute the verification pipeline |
| `db waves --tile XXXX [--run run-NNN]` | Open waveform viewer (Surfer) |
| `db bump-version --tile XXXX` | Increment tile version |
| `db bump-revision --tile XXXX` | Increment tile revision |
| `db list-tiles` | List all registered tiles |
| `db list-runs --tile XXXX` | List runs for a tile |
| `db show-run --tile XXXX --run run-NNN` | Show details of a specific run |

### `project` subcommands

| Command | Description |
|---|---|
| `project run [--config PATH]` | Run the Project Mode workflow (default config: `veriflow.yaml`) |

### `db run` command flags

| Flag | Description |
|---|---|
| `--skip-check` | Skip connectivity check |
| `--skip-sim` | Skip simulation |
| `--skip-synth` | Skip synthesis |
| `--only-check` | Run connectivity check only (error if no interface profile is configured) |
| `--only-sim` | Run simulation only |
| `--only-synth` | Run synthesis only |
| `--waves` | Launch waveform viewer when done (not allowed with `--non-interactive`) |

---

## 6. Tile ID Format

```
<id_prefix>-<YYMMDD><tile_number><id_version><id_revision>
```

Example: `MST130-01-26032500010102`

| Field | Example | Description |
|---|---|---|
| `id_prefix` | `MST130-01` | Defined in `project_config.yaml` |
| `YYMMDD` | `260325` | System date at bump time |
| `tile_number` | `0001` | Unique tile number (4 hex digits) |
| `id_version` | `01` | Internal version (designer iteration) |
| `id_revision` | `02` | Official revision (advisor authorization) |

---

## 7. Version Hierarchy

- **version** — internal increment. The designer uses this to mark development iterations.
- **revision** — major increment. Represents a formal authorization by the advisor.

### Bump behavior

| Command | version | revision | Previous dir | New dir |
|---|---|---|---|---|
| `bump-version` | +1 | unchanged | preserved | created clean |
| `bump-revision` | reset to 01 | +1 | preserved | created clean |

The new directory inherits `works/` from the previous one and starts with an empty `runs/`.

---

## 8. Configuration Files

### `project_config.yaml`
```yaml
id_prefix: ""
project_name: ""
repo: ""
interface_name: "semicolab"   # or null for a generic project
description: |
```

`interface_name` must be declared explicitly:

- `"semicolab"` — the built-in Semicolab interface profile (nine-port structural contract); enables the connectivity check.
- `null` — generic project: no interface contract, no connectivity check.

Semicolab is an interface profile, not a boolean mode. Unknown names fail with `VF_INTERFACE_UNKNOWN`; a missing key fails with `VF_PROJECT_INTERFACE_REQUIRED`.

### `tile_config.yaml`
Contains both tile information (permanent) and run information (updated each run). This is the only per-tile config file — all run fields live here:
```yaml
tile_name: ""
tile_author: ""
top_module: ""        # must match the RTL module name exactly
tb_top_module: "tb"   # testbench top module name
description: |
ports: |
usage_guide: |
tb_description: |

run_author: ""
objective: ""
tags: ""
main_change: |
notes: |
```

In code, the file is represented by the `TileConfig` dataclass (`veriflow/models/tile_config.py`).

---

## 9. CSV Files

### `tile_index.csv`
```
tile_number, tile_id, tile_name, tile_author, version, revision, interface_name
```
- One row per tile
- Updated on every bump
- `interface_name` records the interface profile the tile was created under (empty for generic projects)
- Source of truth for resolving tile_number → current tile_id

### `records.csv`
```
Tile_ID, Run_ID, Date, Author, Objective, Status,
Version, Revision, Connectivity, Simulation, Synthesis,
Tool_Version, Main_Change, Run_Path, Tags, Interface
```
- One row appended per run
- `Run_Path` relative to `tiles/`
- `Interface` is the interface profile name active for the run (e.g. `semicolab`), empty for generic projects
- Queryable by an LLM for historical analysis

---

## 10. Verification Pipeline

```
[Connectivity Check] → FAIL → document and stop
        ↓ PASS (or SKIPPED for generic projects)
[Simulation]         → FAILED → document, continue
        ↓
[Synthesis]          → FAIL → document, complete run
        ↓
[Documentation]      → manifest, results.json, notes, summary, README, records
```

The connectivity check runs only when an interface profile is configured; generic projects (no interface) skip it automatically.

### Status derivation

Shared between both modes via `veriflow.framework.status.derive_run_status()` (see
dev-docs/TRACEABILITY_AUDIT.md, Findings #4/#4b -- Project Mode and Database Mode used to
implement this independently, and had silently diverged: Project Mode treated an all-SKIPPED
run as `PASS`, a vacuous pass since nothing that ran had actually failed because nothing ran at
all. One shared function now backs both.

| Condition | Status |
|---|---|
| Any stage FAIL | FAIL |
| No FAIL, but any stage SKIPPED (or zero stages ran at all) | PARTIAL |
| All executed stages PASS / COMPLETED, none SKIPPED | PASS |

In Project Mode's `results.json`, a stage can also report `NOT_RUN` instead of `SKIPPED`: that
value is reserved specifically for a stage that *was* part of the configured pipeline but never
got a turn because an earlier stage FAILed first (the run stopped before reaching it) -- as
opposed to `SKIPPED`, which means the stage was never configured to begin with (no
`interface:`/`tb_sources`) or was explicitly bypassed via `--skip-check`/`--skip-sim`/
`--skip-synth`. Both `SKIPPED` and `NOT_RUN` count identically toward the `PARTIAL` status
derivation above -- the distinction is for a human/tool reading `results.json` to understand
*why* a stage didn't run, not a third status-derivation tier.

---

## 11. Testbench Architecture

Testbenches are **self-contained Verilog modules**. The files in `src/tb/` must form a complete, compilable testbench, including the DUT instantiation. There is no marker extraction and no runtime injection.

1. VeriFlow compiles all RTL sources and all TB sources together with iverilog.
2. The testbench top module is selected explicitly with `-s <tb_top>`:
   - Database Mode: `tb_top_module` from `tile_config.yaml` (default `tb`)
   - Project Mode: `simulation.tb_top` from `veriflow.yaml`
3. `vvp` runs the compiled simulation from the waves directory so `$dumpfile("waves.vcd")` lands in `out/sim/waves/`.
4. If no `.v` TB sources are present, the simulation stage is skipped automatically.

`db create-tile` generates a starting scaffold (`src/tb/tb_tile.v`):

- **Semicolab projects** — generated from `template/tb_semicolab_template.v` with the DUT instantiation substituted from `--top-module`; includes the nine-port signals, clock/reset, `$dumpfile`/`$dumpvars`, and helper tasks. The whole file is user-editable.
- **Generic projects** — generated from `template/tb_universal_template.v`; a minimal `module tb` skeleton where the user declares signals and instantiates the DUT.

The connectivity check is independent of testbenches: it compiles the RTL together with a generated elaboration wrapper derived from the interface profile's port list.

---

## 12. Validation Rules

### Hard errors (stop execution)
- `project_config.yaml` not found
- `interface_name` missing from `project_config.yaml` (`VF_PROJECT_INTERFACE_REQUIRED`)
- `interface_name` not a registered profile (`VF_INTERFACE_UNKNOWN`)
- Deprecated `semicolab` key present in `project_config.yaml` (`VF_PROJECT_INTERFACE_CONFIG_LEGACY`)
- `tile_index.csv` or `records.csv` not found
- `tiles/` not found
- `tile_config.yaml` not found
- `src/rtl/` empty or no `.v` files
- `id_prefix` empty in `project_config.yaml`
- `top_module` empty in `tile_config.yaml`
- No `.v` file whose stem matches `top_module`
- `--only-check` with no interface profile configured (`VF_INTERFACE_CHECK_NO_PROFILE`)
- `--top-module` missing on `create-tile` for a Semicolab project (`VF_TILE_TOP_MODULE_REQUIRED`)
- `iverilog` or `yosys` not found in PATH
- Incorrect CSV header in a non-empty file

### Soft errors (continue)
- Empty `tile_index.csv` or `records.csv` → valid, uninitialized
- Optional YAML fields empty → rendered as `""`
- `src/tb/` absent or empty → simulation stage skipped
- Simulation FAILED → document, continue to synthesis
- Synthesis FAIL → document, complete run

---

## 13. Files Generated Per Run

| File | Description |
|---|---|
| `manifest.yaml` | Full run metadata (custom serializer) |
| `results.json` | Machine-readable run result (schema 1.2, includes `interface_name`) |
| `notes.md` | Run notes |
| `summary.md` | Tabular results summary |
| `README.md` | Tile documentation (regenerated on every run) |

---

## 14. Tests

Only relevant for a repo checkout (not needed for a `pip install
veriflow-eda` install). Run the full suite with pytest:

```bash
python -m pytest veriflow/tests -q
```

Coverage includes:
- Tile ID generation and parsing
- Run ID generation
- init, create-tile, run, waves, bump-version, bump-revision commands
- Database and Project workflows, framework stages, interface profiles
- CSV validation (header, empty file)
- Flat copy with collision resolution
- Validation errors
- Manifest serialization
