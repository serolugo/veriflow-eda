# VeriFlow

<p align="center">
  <a href="LICENCE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python"></a>
  <a href="http://iverilog.icarus.com/"><img src="https://img.shields.io/badge/icarus%20verilog-required-purple" alt="Icarus Verilog"></a>
  <a href="https://yosyshq.net/yosys/"><img src="https://img.shields.io/badge/yosys-required-orange" alt="Yosys"></a>
</p>

Lightweight RTL verification and documentation framework for multi-project ASIC chip design. Automates connectivity check, simulation, and synthesis for individual hardware tiles using open-source tooling, and generates structured run records per execution.

---

## Features

- **Two operating modes** — SemiCoLab mode (fixed port convention) and Universal mode (any RTL module)
- **Connectivity check** — verifies port wiring via Icarus Verilog compilation *(SemiCoLab mode only)*
- **Simulation** — runs user testbenches and captures VCD waveforms
- **Synthesis** — validates RTL with Yosys, reports cell count, detects inferred latches
- **Auto-documentation** — generates `manifest.yaml`, `summary.md`, `notes.md`, and `README.md` per run
- **Run history** — full CSV records per tile and per run
- **Version tracking** — `bump-version` and `bump-revision` with preserved history

---

## Requirements

- Python 3.10+
- [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases) — provides `iverilog`, `vvp`, and `yosys`
- [Surfer](https://surfer-project.org/) — waveform viewer
- PyYAML: `pip install pyyaml`

---

## Installation

```bash
pip install -e .
```

After installation, the `veriflow` command is available directly in the terminal.

---

## Quick start

```bash
# 1 — Initialize a new database
veriflow --db ./my_db init

# 2 — Edit project_config.yaml: set id_prefix and semicolab mode
$EDITOR my_db/project_config.yaml

# 3 — Create a tile entry
veriflow --db ./my_db create-tile

# 4 — Add your RTL and testbench
cp my_module.v my_db/config/tile_0001/src/rtl/
# Edit my_db/config/tile_0001/tile_config.yaml (set top_module, description, etc.)
# Edit my_db/config/tile_0001/src/tb/tb_tile.v (add your stimuli)

# 5 — Run the full verification pipeline
veriflow --db ./my_db run --tile 0001
```

---

## Operating modes

Set via `semicolab` in `project_config.yaml`. Applies to the entire database.

<table style="width:100%; table-layout:fixed;">
  <colgroup>
    <col style="width:18%">
    <col style="width:15%">
    <col style="width:22%">
    <col style="width:45%">
  </colgroup>
  <thead>
    <tr><th>Mode</th><th><code>semicolab</code></th><th>Connectivity check</th><th>Testbench</th></tr>
  </thead>
  <tbody>
    <tr><td>SemiCoLab</td><td><code>true</code></td><td>Enabled</td><td>Write stimuli between markers in <code>tb_tile.v</code></td></tr>
    <tr><td>Universal</td><td><code>false</code></td><td>Skipped</td><td>Write a complete <code>module tb</code> in <code>tb_tile.v</code></td></tr>
  </tbody>
</table>

---

## Database structure

```
my_db/
├── project_config.yaml       ← project-level settings
├── tile_index.csv            ← registry of all tiles
├── records.csv               ← full run history
├── config/
│   └── tile_0001/
│       ├── tile_config.yaml  ← tile metadata + run fields
│       └── src/
│           ├── rtl/          ← your RTL sources (.v)
│           └── tb/           ← testbench files (tb_tile.v, plus tb_tasks.v in SemiCoLab mode)
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

### `project_config.yaml`

```yaml
id_prefix: "MST130-01"   # Required — prefix embedded in every tile_id
project_name: ""
repo: ""
semicolab: true           # true = SemiCoLab mode, false = Universal mode
description: |
```

### `tile_config.yaml`

```yaml
# ── Tile information (permanent) ──
tile_name: ""
tile_author: ""
top_module: ""            # Must match the RTL filename exactly (e.g. my_adder → my_adder.v)

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

## Commands

All commands require `--db <path>` pointing to an initialized database.

### `init`

Initialize a new database directory.

```bash
veriflow --db ./my_db init [--force]
```

| Flag | Description |
|------|-------------|
| `--force` | Overwrite an existing database |

Creates `project_config.yaml`, empty `tile_index.csv` and `records.csv` files, and the `config/` and `tiles/` directories. CSV headers are written automatically when the first tile or run record is appended.

---

### `create-tile`

Register a new tile and scaffold its directories.

```bash
veriflow --db ./my_db create-tile
```

Auto-assigns the next tile number, generates a unique `tile_id`, creates `config/tile_XXXX/` with a `tile_config.yaml` template, scaffolds `src/rtl/` and `src/tb/`, and appends a row to `tile_index.csv`. SemiCoLab mode copies `tb_tile.v` and `tb_tasks.v`; Universal mode copies a starter `tb_tile.v`.

---

### `run`

Run the full verification pipeline for a tile.

```bash
veriflow --db ./my_db run --tile <number> [options]
```

| Flag | Description |
|------|-------------|
| `--tile XXXX` | Tile number to run (required) |
| `--skip-check` | Skip connectivity check |
| `--skip-sim` | Skip simulation |
| `--skip-synth` | Skip synthesis |
| `--only-check` | Run connectivity check only |
| `--only-sim` | Run simulation only |
| `--only-synth` | Run synthesis only |
| `--waves` | Open Surfer after simulation completes |

**Pipeline order:** connectivity check → simulation → synthesis → documentation → CSV update

Each run creates `tiles/<tile_id>/runs/run-NNN/` containing:

```
run-NNN/
├── manifest.yaml           ← structured run metadata
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

### `waves`

Open Surfer for a tile's waveform output.

```bash
veriflow --db ./my_db waves --tile <number> [--run run-NNN]
```

| Flag | Description |
|------|-------------|
| `--tile XXXX` | Tile number (required) |
| `--run run-NNN` | Specific run to open (default: latest) |

---

### `bump-version`

Increment the tile version (major redesign). Preserves the old tile directory and creates a new one carrying over the `works/` snapshot.

```bash
veriflow --db ./my_db bump-version --tile <number>
```

---

### `bump-revision`

Increment the tile revision (minor update) and reset the version counter. Same preservation behavior as `bump-version`.

```bash
veriflow --db ./my_db bump-revision --tile <number>
```

---

## SemiCoLab testbench

In SemiCoLab mode, `tb_tile.v` is created with a full testbench wrapper. Write your stimuli only between the markers — do not modify anything outside them:

```verilog
    // USER TEST STARTS HERE //
    write_data_reg_a(32'd42);
    write_data_reg_b(32'd1);
    @(posedge clk);
    $display("result = %0d", data_reg_c);
    // USER TEST ENDS HERE //
```

VeriFlow extracts the code between the markers, injects the DUT instantiation, and compiles the final testbench at run time. If no `.v` testbench files are present, simulation is automatically skipped. In SemiCoLab mode, `tb_tile.v` and `tb_tasks.v` are required when testbench files are present.

---

## Run with TileBench (recommended)

[**SemiCoLab TileBench**](https://github.com/serolugo/semicolab-tilebench) is a Docker environment with VeriFlow pre-installed alongside TileWizard and a browser-based waveform viewer — no local tool installation required beyond Docker.

```bash
# Pull and launch
docker pull serolugo/tilebench:latest
.\tilebench.bat my_workspace   # Windows
./tilebench.sh  my_workspace   # Linux / macOS

# Then use VeriFlow normally inside the container
veriflow --db ./veriflow/my_db init
veriflow --db ./veriflow/my_db create-tile
veriflow --db ./veriflow/my_db run --tile 0001
```

TileBench mounts your workspace folder into the container — your files always stay on your machine.

---

## Documentation

| Document | Description |
|---|---|
| [SPECS.md](docs/SPECS.md) | Full system specification |
| [DESIGN.md](docs/DESIGN.md) | Detailed technical design |
| [MANUAL.md](docs/MANUAL.md) | Complete user manual |
| [QUICKREF.md](docs/QUICKREF.md) | Quick reference card |

---

## Tests

```bash
python -m veriflow.tests.runner
# Expected current result: 26 passed, 0 failed
```

---

## Built with

- [Icarus Verilog](http://iverilog.icarus.com/)
- [Yosys](https://yosyshq.net/yosys/)
- [Surfer](https://surfer-project.org/)
- [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)

---

## License

MIT License — Copyright (c) 2026 Roman Lugo

See [`LICENCE`](LICENCE) for the full license text.
