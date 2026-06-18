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
- An unknown name fails with `VF_INTERFACE_UNKNOWN`. Keys other than `name` are rejected —
  custom YAML-defined interface definitions are future work.

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

### `technology` (optional)

```yaml
technology:
  name: generic
```

Names the technology target for the run. Omitting the section, `technology: null`, or
`name: null` means `generic`.

Registered names (see `veriflow.models.technology_profile`): `generic`, `sky130`, `gf180`,
`ihp130`. An unknown name fails with `VF_TECHNOLOGY_UNKNOWN`.

The technology name is currently carried as profile metadata only — the non-generic entries are
PDK/cell-library placeholders and are **not** wired into synthesis. Technology-aware synthesis
(PDK paths, liberty files, constraints) is future work.

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
| `VF_DESIGN_TOP_REQUIRED` | `design.top_module` missing or empty |
| `VF_DESIGN_RTL_REQUIRED` | `design.rtl_sources` missing or empty |
| `VF_INTERFACE_CONFIG_INVALID` | malformed `interface` section / unsupported keys |
| `VF_INTERFACE_NAME_REQUIRED` | `interface` section present without a usable `name` |
| `VF_INTERFACE_UNKNOWN` | `interface.name` not in the registry |
| `VF_EXECUTION_CONFIG_INVALID` | malformed `execution` section / unsupported keys |
| `VF_BACKEND_CONNECTIVITY_UNKNOWN` / `VF_BACKEND_SIMULATION_UNKNOWN` / `VF_BACKEND_SYNTHESIS_UNKNOWN` | backend name not in the registry |
| `VF_TECHNOLOGY_CONFIG_INVALID` | malformed `technology` section / unsupported keys |
| `VF_TECHNOLOGY_UNKNOWN` | `technology.name` not in the registry |
| `VF_SIM_TB_TOP_REQUIRED` | `tb_sources` given without `simulation.tb_top` |

Note: top-level `interface_name` is not supported — use the `interface` section.
