# VeriFlow — Project Mode Configuration (`veriflow.yaml`)

Project Mode runs a verification flow against a local project directory described by a single
`veriflow.yaml` file. It does not require a database — Database Mode (`veriflow db ...`) uses a
separate database workflow and `project_config.yaml`, which is **not** the file documented here.

This document is the reference for the `veriflow.yaml` schema, intended for users writing configs
by hand and for frontends (such as TileWizard) that generate them. Parsing is implemented in
`veriflow/workflows/project_config.py` (`ProjectWorkflowConfig`).

---

## Quick start

Generate a commented scaffold, then edit it to match your project:

```bash
# Generate veriflow.yaml with guided comments
veriflow project init

# Open veriflow.yaml and fill in at minimum:
#   design.top_module: "your_module_name"
#   design.rtl_sources:
#     - path/to/your_module.v

# Then run the pipeline
veriflow project run
```

`project init` writes a `veriflow.yaml` in the current directory (use `--config <path>` to
choose a different location, `--force` to overwrite an existing file).

The generated file contains every section as a comment so you can uncomment and fill in only
what you need. Only `design.top_module` and `design.rtl_sources` are required before
`veriflow project run` will accept the config.

Once the file is filled in, run the pipeline:

```bash
# Run with an explicit config path
veriflow project run --config veriflow.yaml

# Or rely on the default (veriflow.yaml in the current directory)
veriflow project run
```

The pipeline executes connectivity check (only if an `interface` is configured), simulation
(only if `tb_sources` are provided), then synthesis. Exit code is `0` when the overall status
is `PASS`, non-zero otherwise.

---

## Canonical example

```yaml
design:
  top_module: shift_mux
  rtl_sources:
    - rtl/shift_mux.v
  tb_sources:
    - tb/tb_shift_mux.v

interface:
  name: semicolab

execution:
  connectivity_backend: icarus
  simulation_backend: icarus
  synthesis_backend: yosys

technology:
  name: generic

simulation:
  tb_top: tb

output:
  runs_dir: runs
```

Only `design` is required. Every other section may be omitted (or set to `null`) to get the
default behavior described below.

---

## Sections

### `design` (required)

| Key | Required | Description |
|---|---|---|
| `top_module` | yes | Name of the RTL top module. |
| `rtl_sources` | yes (non-empty) | List of RTL source files. |
| `tb_sources` | no | List of testbench source files. Only needed if you want simulation. |

All source paths are resolved **relative to the directory containing the config file**, not the
current working directory. Absolute paths also work but make the project non-portable.

If `tb_sources` is omitted or empty, the simulation stage is not run; connectivity (if configured)
and synthesis still run.

### `interface` (optional)

```yaml
interface:
  name: semicolab
```

Selects a registered interface profile and enables the connectivity check stage, which verifies
that `top_module` exposes the profile's port contract.

- Omitting the section, `interface: null`, or `name: null` means a **generic project**: no
  interface contract, no connectivity check.
- `name: semicolab` enables the built-in Semicolab interface profile (the nine-port structural
  contract required by the Semicolab harness).
- Available interface names are discoverable programmatically through the registry APIs in
  `veriflow.models.interface_profile` (`list_interface_profile_names()`,
  `list_interface_profiles()`, `has_interface_profile()`).
- An unknown name fails with `VF_INTERFACE_UNKNOWN`. The only other supported key is
  `definition` (below); anything else is rejected with `VF_INTERFACE_CONFIG_INVALID`.

#### `interface.definition` — external interface profiles

```yaml
interface:
  name: tinytapeout
  definition: ./interfaces/tinytapeout_if.v
```

`definition` points at a Verilog stub (a `module <name> (...); endmodule` port-list
declaration, no body needed) that doesn't have to be one of VeriFlow's built-ins. The path is
resolved relative to the directory containing `veriflow.yaml`. VeriFlow registers the profile
from that file (ports parsed the same way `wrap init` auto-detects RTL ports) before the
connectivity stage runs.

The registered profile's name is the **module name parsed from the file**, not `name:` above —
if they differ, VeriFlow uses the parsed module name and emits a `UserWarning`
(`VF_INTERFACE_NAME_MISMATCH`) rather than failing. Registering a name that collides with an
already-registered profile (including a built-in one) overwrites it for the rest of the process,
with its own `UserWarning` (`VF_INTERFACE_PROFILE_OVERWRITTEN`).

Omitting `definition` is unchanged from before: `name` must then refer to an
already-registered (built-in) profile. See `veriflow/interfaces/semicolab/` for the on-disk
shape of a built-in profile (`interface.v` + optional `tb_template.v` + optional `meta.yaml`).

### `execution` (optional)

```yaml
execution:
  connectivity_backend: icarus
  simulation_backend: icarus
  synthesis_backend: yosys
```

Selects which backend runs each stage. Omitting the section, `execution: null`, or omitting any
individual key uses the defaults from `default_execution_profile()`:

| Key | Default | Currently registered names |
|---|---|---|
| `connectivity_backend` | `icarus` | `icarus` |
| `simulation_backend` | `icarus` | `icarus` |
| `synthesis_backend` | `yosys` | `yosys` |

Backend names must already be registered in `veriflow.core.backends.registry`; an unknown name
fails with `VF_BACKEND_*_UNKNOWN`. This section introduces no new backends — today the only valid
values are the defaults, and the section exists so future backends can be selected without a
schema change.

### `pipeline` (optional)

```yaml
pipeline:
  stages:
    - type: connectivity
    - type: simulation
      backend: icarus     # optional per-stage override; omit to use `execution`'s default
    - type: synthesis
      backend: yosys
```

Selects exactly which stages run, and in what order. Omitting the section (or `pipeline: null`)
keeps the current default: connectivity (if `interface` is configured) → simulation (if
`tb_sources` is non-empty) → synthesis, unconditionally — i.e. **omitting `pipeline` changes
nothing** for existing configs.

| Stage type | Requires | Runs when listed |
|---|---|---|
| `connectivity` | `interface` section configured | Verifies `top_module` against the interface profile's port contract |
| `simulation` | `design.tb_sources` non-empty | Compiles + runs the testbench, captures `waves.vcd` |
| `synthesis` | — | Always runnable; the only stage with no precondition |

Rules:

- A stage type **not listed** in `pipeline.stages` never runs at all — it shows up as `SKIPPED` in
  the output and in `results.json`, exactly as if you had omitted `interface`/`tb_sources` (or
  passed the matching `--skip-*` flag in Database Mode).
- An unrecognized `type` value fails fast with `VF_PIPELINE_STAGE_UNKNOWN`.
- `backend:` is optional per stage; omitting it uses the `execution` section's default for that
  stage type (or the registry default if `execution` is also omitted).
- Extra keys on a stage entry (for fields not implemented yet, e.g. a future `timeout:`) are
  ignored silently rather than rejected, so configs stay forward-compatible.
- Connectivity/simulation still require their underlying precondition (`interface`/`tb_sources`)
  even when explicitly listed — listing `connectivity` with no `interface` section configured
  simply means that stage is skipped, same as leaving it out of `pipeline` entirely.

Common examples:

```yaml
# Connectivity + synthesis only, no simulation
pipeline:
  stages:
    - type: connectivity
    - type: synthesis

# Synthesis-only smoke check
pipeline:
  stages:
    - type: synthesis
```

### `technology` (optional)

```yaml
technology:
  name: generic
```

Names the technology target for the run. Omitting the section, `technology: null`, or
`name: null` means `generic`.

Registered names (see `veriflow.models.technology_profile`): `generic`, `sky130`, `gf180`,
`ihp130` — each loaded from its own `veriflow/technologies/<name>.yaml` file. An unknown name
fails with `VF_TECHNOLOGY_UNKNOWN`.

Each `technology.yaml` has:

| Field | Description |
|---|---|
| `name` | Required. Must match the filename's technology (used as the registry key). |
| `description` | Free text, informational only. |
| `synthesis_backend` | Informational today; synthesis always uses `yosys` regardless of this value. |
| `liberty` | Path to a `.lib` file, or `null`. When set, `abc -liberty <path>` is appended to the yosys script right after `synth`, performing real cell-library technology mapping. |
| `synth_extra` | List of extra yosys script lines, appended after the `liberty` line (before `check`/`stat`) — e.g. `["-flatten"]`. |

None of the four built-in technologies vendor a real `liberty` file yet (`sky130`/`gf180`/`ihp130`
all ship `liberty: null` in the repo) — `liberty` is resolved automatically once the technology's
PDK is installed with `veriflow pdk install <name>` (see `docs/INSTALL.md`'s "PDK Installation"
section and `veriflow.models.pdk_manager`); until then, synthesis falls back to the generic
script and prints a `VF_TECHNOLOGY_PDK_NOT_INSTALLED` warning (included in `results.json`'s
`warnings` field) rather than failing.

#### `technology.definition` — external technology profiles

```yaml
technology:
  name: mi_proceso
  definition: ./technologies/mi_proceso.yaml
```

The only other supported key besides `name` is `definition`; anything else is rejected with
`VF_TECHNOLOGY_CONFIG_INVALID`. `definition` points at a `technology.yaml`-shaped file (same
schema as the built-ins) that doesn't have to live under `veriflow/technologies/` — the path is
resolved relative to the directory containing `veriflow.yaml`. VeriFlow registers the profile
from that file before the synthesis stage runs. A relative `liberty:` path **inside** that file
is resolved relative to `veriflow.yaml`'s directory too (not the definition file's own directory,
and not the process's current working directory).

The registered profile's name is the `name:` field **inside the definition file**, not the
`name:` in the `technology` section — if they differ, VeriFlow uses the definition file's name
and emits a `UserWarning` (`VF_TECHNOLOGY_NAME_MISMATCH`) rather than failing, mirroring
`interface.definition`'s `VF_INTERFACE_NAME_MISMATCH` behavior. Registering a name that collides
with an already-registered technology (including a built-in one) overwrites it for the rest of
the process.

Omitting `definition` is unchanged from before: `name` must then refer to an already-registered
(built-in) technology.

### `simulation` (optional, required with `tb_sources`)

```yaml
simulation:
  tb_top: tb
```

| Key | Description |
|---|---|
| `tb_top` | Module name of the testbench top. Required (non-empty) whenever `design.tb_sources` is non-empty. |

Testbenches are **self-contained** in both modes: the files in `tb_sources` must form a complete,
compilable testbench (including the DUT instantiation). VeriFlow compiles RTL and TB files
together and selects the testbench top explicitly — there is no DUT injection or marker protocol.

### `output` (optional)

```yaml
output:
  runs_dir: runs
```

| Key | Default | Description |
|---|---|---|
| `runs_dir` | `runs` | Directory (relative to the config file) where run outputs are written. |

Each run is written to `<runs_dir>/run-NNN/` (zero-padded, auto-incremented: `run-001`,
`run-002`, …). Stage logs and artifacts land under `out/` inside the run directory, e.g.
`out/connectivity/logs/`, `out/sim/logs/`, `out/sim/waves/waves.vcd`, `out/synth/logs/`.

---

## Validation errors

The parser fails fast with stable `VeriFlowError` codes, including:

| Code | Cause |
|---|---|
| `VF_PROJECT_CONFIG_NOT_FOUND` | config file does not exist at the given path |
| `VF_PROJECT_CONFIG_YAML_ERROR` | config file exists but contains invalid YAML (parse error) |
| `VF_DESIGN_TOP_REQUIRED` | `design.top_module` missing or empty |
| `VF_DESIGN_RTL_REQUIRED` | `design.rtl_sources` missing or empty |
| `VF_INTERFACE_CONFIG_INVALID` | malformed `interface` section / unsupported keys |
| `VF_INTERFACE_NAME_REQUIRED` | `interface` section present without a usable `name` |
| `VF_INTERFACE_UNKNOWN` | `interface.name` not in the registry |
| `VF_EXECUTION_CONFIG_INVALID` | malformed `execution` section / unsupported keys |
| `VF_BACKEND_CONNECTIVITY_UNKNOWN` / `VF_BACKEND_SIMULATION_UNKNOWN` / `VF_BACKEND_SYNTHESIS_UNKNOWN` | backend name not in the registry |
| `VF_PIPELINE_CONFIG_INVALID` | `pipeline` section is not a mapping with a `stages` key |
| `VF_PIPELINE_STAGE_UNKNOWN` | a `pipeline.stages[].type` value isn't `connectivity`/`simulation`/`synthesis` |
| `VF_TECHNOLOGY_CONFIG_INVALID` | malformed `technology` section / unsupported keys |
| `VF_TECHNOLOGY_UNKNOWN` | `technology.name` not in the registry |
| `VF_SIM_TB_TOP_REQUIRED` | `tb_sources` given without `simulation.tb_top` |

Note: top-level `interface_name` is not supported — use the `interface` section.

---

## `project import`

Promotes a verified Project Mode run into a Database Mode database as a new tile:

```bash
veriflow project import --db ./database [--config veriflow.yaml] [--run run-NNN]
```

| Flag | Required | Description |
|---|---|---|
| `--db PATH` | yes | Path to the destination VeriFlow database directory. |
| `--config PATH` | no | Path to the Project Mode config to import from. Default: `veriflow.yaml`. |
| `--run run-NNN` | no | Specific run to import. Default: the highest-numbered run under `runs_dir` whose `results.json` reports `"status": "PASS"`. |

### What it validates before importing

1. A run to import can be identified: either `--run` names one that exists and has a
   `results.json`, or (if `--run` is omitted) at least one run under `runs_dir` has
   `"status": "PASS"`.
2. The chosen run's `status` in `results.json` is `"PASS"` — a `FAIL` run is never importable,
   whether picked automatically or named explicitly via `--run`.
3. The destination database is structurally valid (same check `db run` uses —
   `project_config.yaml`, `tile_index.csv`, `records.csv`, `tiles/` must all exist).
4. The imported run's `interface_name` (from its `results.json`) matches the database's
   `project_config.yaml` `interface_name` — importing a run built against a different
   interface than the database's own would silently corrupt tile consistency, so this is
   rejected rather than allowed through.

### What it copies into the new tile

- Creates a new tile via the same `create-tile` path Database Mode uses, keyed off the
  imported run's `top_module`.
- Copies every path in `results.json`'s `rtl_sources` into `config/tile_NNNN/src/rtl/`.
- If `tb_sources` is non-empty, removes the auto-generated `tb_tile.v` placeholder and copies
  the imported testbench files into `config/tile_NNNN/src/tb/` instead (the imported
  testbench is self-contained, so the scaffold placeholder would otherwise collide on the
  `tb` module name).
- Prefills `tile_config.yaml`'s `tile_name` (from the project directory name) and
  `tb_top_module` (from the project's `simulation.tb_top`, if set).
- Copies `results.json` itself to `config/tile_NNNN/imported_run.json` — a traceability
  snapshot of the exact run that was imported (`rtl_hash`, `timestamp`, per-stage statuses).

Nothing under `runs_dir` in the Project Mode project is modified or deleted by the import —
it only reads from it.

### Error codes

| Code | Cause |
|---|---|
| `VF_IMPORT_NO_PASSING_RUN` | `--run` omitted and no run under `runs_dir` has `status: "PASS"` |
| `VF_IMPORT_RUN_NOT_FOUND` | `--run` given but that run (or its `results.json`) doesn't exist |
| `VF_IMPORT_RUN_NOT_PASSING` | `--run` given but that run's `status` isn't `"PASS"` |
| `VF_IMPORT_INTERFACE_MISMATCH` | the run's `interface_name` differs from the database's `project_config.yaml` `interface_name` |
