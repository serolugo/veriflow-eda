# VeriFlow

Lightweight RTL verification and documentation framework for multi-project ASIC chip design. Automates connectivity check, simulation, and synthesis for individual hardware tiles using open-source tooling, and generates structured run records per execution.

---

## Features

- **Two operating modes** — SemiCoLab mode (fixed port convention) and Universal mode (any RTL module)
- **Connectivity check** — verifies port wiring via Icarus Verilog compilation *(SemiCoLab mode)*
- **Simulation** — runs user testbenches and captures VCD waveforms
- **Synthesis** — validates RTL with Yosys, reports cell count, detects inferred latches
- **Auto-documentation** — generates `manifest.yaml`, `summary.md`, `notes.md`, and `README.md` per run
- **Run history** — full CSV records queryable per tile and per run
- **Version tracking** — `bump-version` and `bump-revision` with preserved history
- **Waveform viewer** — opens Surfer (native or WASM) or GTKWave directly from the CLI
- **Interactive TUI** — launch with no arguments to browse tiles and runs (requires TileBench)

---

## Requirements

- Python 3.10+
- [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases) (`iverilog`, `vvp`, `yosys`)
- PyYAML: `pip install pyyaml`
- Rich: `pip install rich` (styled console output)
- Optional: `pyfiglet`, `terminaltexteffects` (banner animation); `surfer` or `gtkwave` in PATH (waveforms)

## Installation

```bash
pip install -e .
```

After installation, the `veriflow` command is available directly in the terminal.

---

## Quick Start

```bash
# Launch the interactive TUI (no arguments)
veriflow

# Initialize the database
veriflow --db ./database init

# Set semicolab: true or false in database/project_config.yaml

# Create a tile
veriflow --db ./database create-tile

# Fill in config/tile_0001/ with your RTL and test, then run
veriflow --db ./database run --tile 0001 --waves
```

---

## Operating Modes

Configured via `semicolab` in `project_config.yaml`. Applies to the entire database.

| Mode | `semicolab` | Connectivity Check | Testbench |
|---|---|---|---|
| SemiCoLab | `true` | ✓ Enabled | Write stimuli in `tb_tile.v` between markers |
| Universal | `false` | ✗ Skipped | Write full `module tb` in `tb_tile.v` |

---

## SemiCoLab Testbench

`tb_tile.v` is created with the full testbench wrapper on `create-tile`. Write your stimuli between the markers — do not modify the rest:

```verilog
    // USER TEST STARTS HERE //
    write_data_reg_a(32'd1);
    write_data_reg_b(32'd1);
    @(posedge clk);
    $display("result = %0d", data_reg_c);
    // USER TEST ENDS HERE //
```

VeriFlow extracts the code between the markers and injects it at runtime along with the DUT instantiation.
If no `tb_tile.v` is present, simulation is automatically skipped.

---

## Commands

```bash
veriflow                                                    # interactive TUI
veriflow --db ./database init [--force]
veriflow --db ./database create-tile
veriflow --db ./database run --tile 0001 [--waves] [--skip-synth] [--skip-sim] [--skip-check] [--only-check] [--only-sim] [--only-synth]
veriflow --db ./database waves --tile 0001 [--run run-003]
veriflow --db ./database bump-version --tile 0001
veriflow --db ./database bump-revision --tile 0001
```

---

## Run Summary

```
Tile ID: MST130-01-26032500010101
Tile:    Adder Tile
Run:     run-001
Date:    2026-03-25

| Stage        | Result        | Details          |
|--------------|---------------|------------------|
| Connectivity | PASS          |                  |
| Simulation   | COMPLETED     | 115 ns           |
| Synthesis    | PASS          | 3 cells          |
```

---

## Documentation

| Document | Description |
|---|---|
| [SPECS.md](docs/SPECS.md) | Full system specification |
| [DESIGN.md](docs/DESIGN.md) | Detailed technical design |
| [MANUAL.md](docs/MANUAL.md) | Complete user manual |
| [QUICKREF.md](docs/QUICKREF.md) | Quick reference card |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module-by-module technical reference |
| [CHANGELOG.md](docs/CHANGELOG.md) | Version history |

---

## Tests

```bash
python -m veriflow.tests.runner
# Results: 26 passed, 0 failed
```

---

## Built With

- [Icarus Verilog](http://iverilog.icarus.com/)
- [Yosys](https://yosyshq.net/yosys/)
- [Surfer](https://surfer-project.org/) (primary waveform viewer)
- [GTKWave](http://gtkwave.sourceforge.net/) (fallback waveform viewer)
- [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)
- [Rich](https://github.com/Textualize/rich)
