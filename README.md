# VeriFlow

<p align="center">
  <a href="LICENCE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python"></a>
  <a href="http://iverilog.icarus.com/"><img src="https://img.shields.io/badge/icarus%20verilog-required-purple" alt="Icarus Verilog"></a>
  <a href="https://yosyshq.net/yosys/"><img src="https://img.shields.io/badge/yosys-required-orange" alt="Yosys"></a>
</p>

Lightweight RTL verification and documentation framework for multi-project ASIC chip design. Automates interface/connectivity checking, simulation, and synthesis using open-source tooling, and generates structured run records per execution.

---

## Features

- **Two operating modes** — Project Mode (`veriflow project run`, single `veriflow.yaml` config) and Database Mode (`veriflow db ...`, tile database with full run history)
- **Interface profiles** — optional structural port-contract checking; the built-in `semicolab` profile verifies the nine-port Semicolab convention. Projects with no interface configured skip the connectivity check.
- **Simulation** — compiles RTL and self-contained user testbenches together and captures VCD waveforms
- **Synthesis** — validates RTL with Yosys, reports cell count, detects inferred latches
- **Auto-documentation** — generates `manifest.yaml`, `results.json`, `summary.md`, `notes.md`, and `README.md` per run (Database Mode)
- **Run history** — full CSV records per tile and per run
- **Version tracking** — `bump-version` and `bump-revision` with preserved history

---

## Requirements

- Python 3.10+
- `iverilog`, `vvp` (Icarus Verilog), and `yosys` in PATH — the [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases) is one convenient distribution that bundles all of them
- [Surfer](https://surfer-project.org/) — optional waveform viewer
- PyYAML: `pip install pyyaml`

---

## Installation

```bash
pip install -e .
```

After installation, the `veriflow` command is available directly in the terminal.

---

## Operating modes

| Mode | Entry point | Configuration | Use case |
|---|---|---|---|
| **Project Mode** | `veriflow project run [--config veriflow.yaml]` | One `veriflow.yaml` per project | Verify a local RTL project directory; no database needed |
| **Database Mode** | `veriflow db <command> --db <path>` | `project_config.yaml` + per-tile `tile_config.yaml` | Tile database with indexed run history and generated documentation |

In both modes, the **connectivity check is controlled by interface profile selection**, not by a boolean flag:

- Database Mode: `interface_name: "semicolab"` (or `interface_name: null` for a generic project) in `project_config.yaml`
- Project Mode: an `interface:` section with `name: semicolab`, or omit the section entirely for a generic project

Semicolab is an *interface profile* — a named structural port contract — not a separate mode. A generic project (no interface) runs no connectivity check.

---

## Quick start (Database Mode)

```bash
# 1 — Initialize a new database
veriflow db init --db ./my_db

# 2 — Edit project_config.yaml: set id_prefix and interface_name
$EDITOR my_db/project_config.yaml

# 3 — Create a tile entry (--top-module is required for Semicolab projects)
veriflow db create-tile --db ./my_db --top-module my_module

# 4 — Add your RTL and testbench
cp my_module.v my_db/config/tile_0001/src/rtl/
# Edit my_db/config/tile_0001/tile_config.yaml (set description, run fields, etc.)
# Edit my_db/config/tile_0001/src/tb/tb_tile.v (self-contained testbench scaffold)

# 5 — Run the full verification pipeline
veriflow db run --db ./my_db --tile 0001
```

## Quick start (Project Mode)

```bash
# veriflow.yaml in the current directory
veriflow project run

# or with an explicit config path
veriflow project run --config veriflow.yaml
```

See [docs/PROJECT_CONFIG.md](docs/PROJECT_CONFIG.md) for the full `veriflow.yaml` schema.

---

## Database structure

```
my_db/
├── project_config.yaml       ← project-level settings (id_prefix, interface_name, …)
├── tile_index.csv            ← registry of all tiles
├── records.csv               ← full run history
├── config/
│   └── tile_0001/
│       ├── tile_config.yaml  ← tile metadata + run fields
│       └── src/
│           ├── rtl/          ← your RTL sources (.v)
│           └── tb/           ← testbench files (self-contained, e.g. tb_tile.v)
└── tiles/
    └── <tile_id>/
        ├── README.md         ← auto-generated tile docs
        ├── works/            ← latest source snapshot
        │   ├── rtl/
        │   └── tb/
        └── runs/
            └── run-001/      ← full per-run artifacts
```

---

## Configuration

### `project_config.yaml` (Database Mode)

```yaml
id_prefix: "MST130-01"        # Required — prefix embedded in every tile_id
project_name: ""
repo: ""
interface_name: "semicolab"   # "semicolab" = Semicolab port-contract checking
                              # null        = generic project, no connectivity check
description: |
```

`interface_name` must be declared explicitly. An unknown name fails with `VF_INTERFACE_UNKNOWN`.

### `tile_config.yaml`

```yaml
# ── Tile information (permanent) ──
tile_name: ""
tile_author: ""
top_module: ""            # Must match the RTL filename exactly (e.g. my_adder → my_adder.v)
tb_top_module: "tb"       # Testbench top module name (module declared in tb_tile.v)

description: |
ports: |
usage_guide: |
tb_description: |

# ── Run fields (fill before each run) ──
run_author: ""
objective: ""
tags: ""                  # Comma-separated (e.g. initial, fix, refactor)
main_change: |
notes: |
```

---

## Commands (Database Mode)

All Database Mode commands live under the `veriflow db` namespace and take `--db <path>`.

### `db init`

Initialize a new database directory.

```bash
veriflow db init --db ./my_db [--force]
```

| Flag | Description |
|------|-------------|
| `--force` | Overwrite an existing database |

Creates `project_config.yaml`, empty `tile_index.csv` and `records.csv` files, and the `config/` and `tiles/` directories. CSV headers are written automatically when the first tile or run record is appended.

---

### `db create-tile`

Register a new tile and scaffold its directories.

```bash
veriflow db create-tile --db ./my_db --top-module my_module
```

| Flag | Description |
|------|-------------|
| `--top-module NAME` | RTL top module name. Required for Semicolab projects — it is written into `tile_config.yaml` and substituted into the generated testbench |

Auto-assigns the next tile number, generates a unique `tile_id`, creates `config/tile_XXXX/` with a `tile_config.yaml` template, scaffolds `src/rtl/` and `src/tb/`, and appends a row to `tile_index.csv`. Semicolab projects get a generated `tb_tile.v` with the DUT already instantiated and helper tasks included; generic projects get a minimal starter `tb_tile.v`.

---

### `db run`

Run the full verification pipeline for a tile.

```bash
veriflow db run --db ./my_db --tile <number> [options]
```

| Flag | Description |
|------|-------------|
| `--tile XXXX` | Tile number to run (required) |
| `--skip-check` | Skip connectivity check |
| `--skip-sim` | Skip simulation |
| `--skip-synth` | Skip synthesis |
| `--only-check` | Run connectivity check only (errors if no interface profile is configured) |
| `--only-sim` | Run simulation only |
| `--only-synth` | Run synthesis only |
| `--waves` | Open Surfer after simulation completes |

**Pipeline order:** connectivity check → simulation → synthesis → documentation → CSV update

The connectivity check runs only when an interface profile is configured; generic projects skip it automatically. If no testbench sources are present in `src/tb/`, simulation is skipped automatically.

Each run creates `tiles/<tile_id>/runs/run-NNN/` containing:

```
run-NNN/
├── manifest.yaml           ← structured run metadata
├── results.json            ← machine-readable run result
├── summary.md              ← result table
├── notes.md                ← run notes
├── src/rtl/                ← RTL snapshot
├── src/tb/                 ← testbench snapshot
└── out/
    ├── connectivity/logs/
    ├── sim/logs/ and sim/waves/waves.vcd
    └── synth/logs/ and synth/reports/
```

**Example run summary:**

```
Tile ID: MST130-01-26032500010101
Tile:    My Adder
Run:     run-001
Date:    2026-03-25

| Stage        | Result    | Details  |
|--------------|-----------|----------|
| Connectivity | PASS      |          |
| Simulation   | COMPLETED | 115 ns   |
| Synthesis    | PASS      | 3 cells  |
```

---

### `db waves`

Open Surfer for a tile's waveform output.

```bash
veriflow db waves --db ./my_db --tile <number> [--run run-NNN]
```

| Flag | Description |
|------|-------------|
| `--tile XXXX` | Tile number (required) |
| `--run run-NNN` | Specific run to open (default: latest) |

---

### `db bump-version`

Increment the tile version (major redesign). Preserves the old tile directory and creates a new one carrying over the `works/` snapshot.

```bash
veriflow db bump-version --db ./my_db --tile <number>
```

---

### `db bump-revision`

Increment the tile revision (minor update) and reset the version counter. Same preservation behavior as `bump-version`.

```bash
veriflow db bump-revision --db ./my_db --tile <number>
```

---

### `db list-tiles` / `db list-runs` / `db show-run`

Read-only inspection commands.

```bash
veriflow db list-tiles --db ./my_db
veriflow db list-runs  --db ./my_db --tile 0001
veriflow db show-run   --db ./my_db --tile 0001 --run run-001
```

---

## Machine-readable and automation-friendly execution

By default, VeriFlow runs interactively with Rich-formatted terminal output — nothing changes if neither flag below is passed. Two global flags activate scripted and CI use:

| Mode | Flags | Human output | stdout |
|---|---|---|---|
| Human (default) | *(none)* | Rich color output | run summary |
| JSON only | `--json` | Suppressed | JSON object |
| Non-interactive | `--non-interactive` | Rich color output | run summary |
| JSON + non-interactive | `--json --non-interactive` | Suppressed | JSON object |

### Recommended automation command

```bash
veriflow --json --non-interactive db run --db <db> --tile <tile>
```

### `results.json`

Every `db run` command writes `results.json` into the run directory alongside `manifest.yaml`. It is always written — even without `--json` — and captures the complete machine-readable outcome of that run.

**Location:** `tiles/<tile_id>/runs/run-NNN/results.json`

```json
{
  "schema_version": "1.2",
  "tile_id": "MST130-01-26032500010101",
  "run_id": "run-001",
  "date": "2026-03-25",
  "status": "PASS",
  "interface_name": "semicolab",
  "stages": {
    "connectivity": {
      "tool": "iverilog", "status": "PASS",
      "logs": ["tiles/MST130-01-26032500010101/runs/run-001/out/connectivity/logs/connectivity.log"]
    },
    "simulation": {
      "tool": "iverilog/vvp", "status": "COMPLETED",
      "logs": ["tiles/MST130-01-26032500010101/runs/run-001/out/sim/logs/sim.log"],
      "artifacts": { "wave": ["tiles/MST130-01-26032500010101/runs/run-001/out/sim/waves/waves.vcd"] },
      "metrics": { "sim_time": "115 ns" }
    },
    "synthesis": {
      "tool": "yosys", "status": "PASS",
      "logs": ["tiles/MST130-01-26032500010101/runs/run-001/out/synth/logs/synth.log"],
      "metrics": { "cells": "3", "warnings": "0", "errors": "0", "has_latches": false }
    }
  },
  "sources": {
    "rtl": ["tiles/MST130-01-26032500010101/runs/run-001/src/rtl/adder_tile.v"],
    "tb":  ["tiles/MST130-01-26032500010101/runs/run-001/src/tb/tb_tile.v"]
  },
  "artifacts": {
    "manifest":         ["tiles/MST130-01-26032500010101/runs/run-001/manifest.yaml"],
    "summary":          ["tiles/MST130-01-26032500010101/runs/run-001/summary.md"],
    "notes":            ["tiles/MST130-01-26032500010101/runs/run-001/notes.md"],
    "readme":           ["tiles/MST130-01-26032500010101/README.md"],
    "records":          ["records.csv"],
    "connectivity_log": ["tiles/MST130-01-26032500010101/runs/run-001/out/connectivity/logs/connectivity.log"],
    "sim_log":          ["tiles/MST130-01-26032500010101/runs/run-001/out/sim/logs/sim.log"],
    "synth_log":        ["tiles/MST130-01-26032500010101/runs/run-001/out/synth/logs/synth.log"],
    "wave":             ["tiles/MST130-01-26032500010101/runs/run-001/out/sim/waves/waves.vcd"]
  },
  "error": null
}
```

`interface_name` is the selected interface profile name, or `null` when the project has no interface configured (in that case the connectivity stage reports `SKIPPED`).

All paths in `results.json` are relative to the database root — no absolute OS-specific paths are stored. The file is identical in content on Windows and Linux.

`schema_version` is incremented when the structure of `results.json` changes (current: `"1.2"`, which replaced the legacy `semicolab` boolean with `interface_name`). Consumers parsing this file programmatically should read `schema_version` first and handle unknown versions gracefully.

### `--json` mode

Suppresses Rich output and emits a single JSON object to stdout on completion. The process exit code is non-zero on any error.

```bash
veriflow --json db run --db ./my_db --tile 0001
```

**Success:** `{ "status": "SUCCESS", "command": "db run", "run_result": { ... } }`

**Error:** `{ "status": "ERROR", "error": { "code": "VF_TILE_CONFIG_MISSING", "message": "...", "details": {...}, "exit_code": 1 } }`

Error `code` values are stable strings (e.g. `VF_TILE_CONFIG_MISSING`, `VF_INTERFACE_UNKNOWN`, `VF_INTERRUPTED`).

### `--non-interactive` mode

Disables the TUI and waveform viewer. Combining `--non-interactive` with `--waves` or the `waves` command is an error.

```bash
veriflow --non-interactive db run --db ./my_db --tile 0001
```

---

## Testbenches

Testbenches are **self-contained Verilog modules**: the files in `src/tb/` must form a complete, compilable testbench, including the DUT instantiation. VeriFlow compiles your RTL and testbench files together and selects the testbench top module explicitly — there is no marker extraction or runtime code injection.

- **Database Mode:** the testbench top module name comes from `tb_top_module` in `tile_config.yaml` (default `tb`).
- **Project Mode:** the testbench top comes from `simulation.tb_top` in `veriflow.yaml`.

`db create-tile` generates a starting scaffold in `src/tb/tb_tile.v`:

- For **Semicolab** projects, the scaffold already contains the nine-port signal declarations, clock/reset, the DUT instantiation (from `--top-module`), waveform dump, and helper tasks (`write_data_reg_a`, `write_data_reg_b`, `write_csr_in`, `reset_csr_in`, `read_csr_out`). Add your stimulus in the marked stimulus block — the whole file is yours to edit.
- For **generic** projects, the scaffold is a minimal empty `module tb` skeleton; declare signals and instantiate your DUT yourself.

If no `.v` testbench sources are present, simulation is skipped automatically.

---

## Companion environments

See [docs/TILEBENCH.md](docs/TILEBENCH.md) for the optional TileBench Docker environment
(VeriFlow pre-installed, browser-based waveform viewer, no local EDA tools required).

---

## Documentation

| Document | Description |
|---|---|
| [SPECS.md](docs/SPECS.md) | Full system specification |
| [PROJECT_CONFIG.md](docs/PROJECT_CONFIG.md) | Project Mode `veriflow.yaml` configuration reference |
| [DESIGN.md](docs/DESIGN.md) | Detailed technical design |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture reference |
| [MANUAL.md](docs/MANUAL.md) | Complete user manual |
| [QUICKREF.md](docs/QUICKREF.md) | Quick reference card |

---

## Tests

```bash
python -m veriflow.tests.runner
# Expected current result: 720 passed, 0 failed

# Or with pytest (collects the full suite):
python -m pytest veriflow/tests -q
```

---

## Built with

- [Icarus Verilog](http://iverilog.icarus.com/)
- [Yosys](https://yosyshq.net/yosys/)
- [Surfer](https://surfer-project.org/)

---

## License

MIT License — Copyright (c) 2026 Roman Lugo

See [`LICENCE`](LICENCE) for the full license text.
