# VeriFlow V1 — User Manual

## 1. Introduction

VeriFlow V1 is an RTL verification framework designed for the multi-project ASIC chip design flow. It automates three verification stages — interface/connectivity check, simulation, and synthesis — and generates structured documentation for every run.

VeriFlow has two operating modes:

- **Database Mode** (`veriflow db ...`) — a tile database with indexed run history and generated documentation. This manual focuses on Database Mode.
- **Project Mode** (`veriflow project run`) — verifies a local project directory described by a single `veriflow.yaml` file. See [PROJECT_CONFIG.md](PROJECT_CONFIG.md).

**Internal components:**
- **VeriTile** — verification engine (iverilog + Yosys)
- **AutoDoc** — documentation engine (YAML, CSV, Markdown)
- **VeriFlow** — CLI orchestrator

---

## 2. Requirements

- Python 3.10 or higher
- PyYAML: `pip install pyyaml`
- Rich: `pip install rich`
- `iverilog`, `vvp`, and `yosys` in PATH — the [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases) is one convenient distribution that provides all three
- Optional: `pyfiglet` and `terminaltexteffects` for the animated SEMICOLAB banner
- Optional: `surfer` in PATH for waveform viewing

### Verify installation
```bash
iverilog -V
yosys --version
```

---

## 3. Installation

Extract the zip into your project, then install:

```bash
pip install -e .
```

This registers the `veriflow` command globally. Verify everything works:
```bash
python -m veriflow.tests.runner
```

Expected result: `193 passed, 0 failed`.

---

## 4. Project Initialization

### 4.1 Create the database

```bash
veriflow db init --db ./database
```

This creates:
```
database/
├── project_config.yaml
├── tile_index.csv
├── records.csv
├── config/
└── tiles/
```

If the folder already exists, use `--force` to overwrite:
```bash
veriflow db init --db ./database --force
```

### 4.2 Configure the project

Edit `database/project_config.yaml`:

```yaml
id_prefix: "MST130-01"       # prefix for Tile IDs
project_name: "My Chip"
repo: "https://github.com/user/repo"
interface_name: "semicolab"  # or null for a generic project
description: |
  Chip project description.
```

The `id_prefix` field is required — tiles cannot be created without it.

`interface_name` selects the interface profile for the whole database and must be declared explicitly:

- `interface_name: "semicolab"` — tiles follow the Semicolab nine-port structural contract; the connectivity check verifies it on every run.
- `interface_name: null` — generic project: any RTL module, no interface contract, no connectivity check.

Semicolab is an interface profile (a named port contract), not a boolean mode. An unknown name fails with `VF_INTERFACE_UNKNOWN`.

---

## 5. Tile Management

### 5.1 Create a tile

```bash
veriflow db create-tile --db ./database --top-module adder_tile
```

`--top-module` is required for Semicolab projects: the name is written into `tile_config.yaml` and substituted into the generated testbench so both share the same DUT name. For generic projects it can be omitted.

Automatically generates:
- `database/config/tile_0001/tile_config.yaml` — tile + run configuration (single file)
- `database/config/tile_0001/src/rtl/` — folder for RTL
- `database/config/tile_0001/src/tb/tb_tile.v` — self-contained testbench scaffold
- `database/tiles/<tile_id>/` — artifacts directory

### 5.2 Configure the tile

**`tile_config.yaml`** — contains both tile info (fill once) and run info (update before each run):
```yaml
tile_name: "Adder Tile"
tile_author: "Sebastian"
top_module: "adder_tile"    # exact name of the RTL module
tb_top_module: "tb"         # testbench top module name (module declared in tb_tile.v)
description: |
  32-bit adder tile.
ports: |
  data_reg_a, data_reg_b: operands
  data_reg_c: result
usage_guide: |
  Connect operands, read result from data_reg_c.

run_author: "Sebastian"
objective: "Initial verification"
tags: "initial"
main_change: |
  Initial implementation.
notes: |
  No notes.
```

> The `top_module` field must match exactly the name of the `.v` file in `src/rtl/`.
> `tb_top_module` defaults to `tb` and must match the module declared in your testbench.

### 5.3 Add the RTL

Create `database/config/tile_0001/src/rtl/adder_tile.v`:

```verilog
`timescale 1ns / 1ps

module adder_tile #(
    parameter REG_WIDTH     = 32,
    parameter CSR_IN_WIDTH  = 16,
    parameter CSR_OUT_WIDTH = 16
)(
    input  wire                      clk,
    input  wire                      arst_n,
    input  wire [CSR_IN_WIDTH-1:0]   csr_in,
    input  wire [REG_WIDTH-1:0]      data_reg_a,
    input  wire [REG_WIDTH-1:0]      data_reg_b,
    output wire [REG_WIDTH-1:0]      data_reg_c,
    output wire [CSR_OUT_WIDTH-1:0]  csr_out,
    output wire                      csr_in_re,
    output wire                      csr_out_we
);

    assign data_reg_c = data_reg_a + data_reg_b;
    assign csr_out    = 16'b0;
    assign csr_in_re  = 1'b0;
    assign csr_out_we = 1'b0;

endmodule
```

> Semicolab tiles must expose the 9 ports defined by the Semicolab interface profile. Generic tiles may use any port list.

### 5.4 Write the testbench

Testbenches are **self-contained Verilog modules**: the files in `src/tb/` must form a complete, compilable testbench, including the DUT instantiation. VeriFlow compiles your RTL and testbench files together and selects the testbench top module explicitly (`tb_top_module` in `tile_config.yaml`). There is no marker extraction and no runtime code injection — the whole testbench file is yours to edit.

**Semicolab projects**

`create-tile` generates `tb_tile.v` from a scaffold template with everything already in place: signal declarations for the nine-port contract, clock generation, reset sequence, waveform dump (`$dumpfile`/`$dumpvars`), the DUT instantiation (using the `--top-module` name), and helper tasks. Add your stimulus in the marked stimulus block:

```verilog
    // ── USER STIMULUS BEGIN ──
    write_data_reg_a(32'd10);
    write_data_reg_b(32'd20);
    @(posedge clk);
    $display("result = %0d", data_reg_c);  // expected: 30
    // ── USER STIMULUS END ──
```

The scaffold is a starting point, not a managed file — you may restructure it freely as long as it remains a complete testbench whose top module matches `tb_top_module`.

**Generic projects**

`create-tile` generates a minimal `tb_tile.v` skeleton. Declare your signals, instantiate your DUT, and write your test:

```verilog
`timescale 1ns / 1ps
module tb;
    reg clk;
    reg rst_n;
    wire [7:0] result;

    my_module DUT (.clk(clk), .rst_n(rst_n), .result(result));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, tb);
    end

    initial begin
        clk = 0; rst_n = 0;
        #20 rst_n = 1;
        #100;
        $display("result = %0d", result);
        $finish;
    end
endmodule
```

> Include `$dumpfile("waves.vcd")` / `$dumpvars` in your testbench if you want waveforms — VeriFlow does not insert them for you.
> If no `.v` files are present in `src/tb/`, simulation is automatically skipped.

**Tasks provided by the Semicolab scaffold:**

| Task | Usage |
|---|---|
| `write_data_reg_a(data)` | Applies value to data_reg_a on the next posedge |
| `write_data_reg_b(data)` | Applies value to data_reg_b on the next posedge |
| `write_csr_in(data)` | Applies value to csr_in |
| `reset_csr_in` | Clears bits [15:12] of csr_in |
| `read_csr_out(data)` | Captures csr_out into a variable |

These tasks are defined inside the generated `tb_tile.v` itself — they are part of your testbench, not a hidden library.

### 5.5 Update run information

Before each run, update the run section at the bottom of `tile_config.yaml`:

```yaml
run_author: "Sebastian"
objective: "Initial verification of the adder"
tags: "initial, adder"

main_change: |
  What changed since the last run.

notes: |
  Any additional notes.
```

---

## 6. Running the Pipeline

### 6.1 Full run

```bash
veriflow db run --db ./database --tile 0001
```

The pipeline executes in order:

1. **Connectivity check** — compiles the RTL together with a generated elaboration wrapper derived from the interface profile, verifying that `top_module` exposes the profile's port contract. Runs only when an interface profile is configured; generic projects skip it automatically. If it fails, the pipeline stops.
2. **Simulation** — compiles RTL + testbench files together with iverilog (`-s <tb_top_module>`), runs with `vvp`, captures `waves.vcd`.
3. **Synthesis** — runs Yosys with hierarchy check, synth, check, and stat.
4. **Documentation** — generates manifest, results.json, notes, summary, README, updates records.csv.

### 6.2 Run options

```bash
# Show waveforms automatically when done
veriflow db run --db ./database --tile 0001 --waves

# Connectivity check only (errors if no interface profile is configured)
veriflow db run --db ./database --tile 0001 --only-check

# Simulation only
veriflow db run --db ./database --tile 0001 --only-sim

# Synthesis only
veriflow db run --db ./database --tile 0001 --only-synth

# Skip synthesis
veriflow db run --db ./database --tile 0001 --skip-synth

# Skip simulation
veriflow db run --db ./database --tile 0001 --skip-sim
```

### 6.3 Interpreting the result

```
| Stage        | Result        | Details          |
|--------------|---------------|------------------|
| Connectivity | PASS          |                  |
| Simulation   | COMPLETED     | 135 ns           |
| Synthesis    | PASS          | 253 cells        |
```

| Result | Meaning |
|---|---|
| `PASS` | Stage successful |
| `COMPLETED` | Simulation finished without errors |
| `FAIL` | Stage failed |
| `FAILED` | Simulation finished with errors |
| `SKIPPED` | Stage was not executed |

**Global status:**
- `PASS` — every executed stage passed
- `PARTIAL` — at least one stage was skipped
- `FAIL` — connectivity, simulation, or synthesis failed

---

## 7. Waveforms

### View waveforms of the latest run

```bash
veriflow db waves --db ./database --tile 0001
```

### View waveforms of a specific run

```bash
veriflow db waves --db ./database --tile 0001 --run run-003
```

VeriFlow opens waveforms using the following priority:

1. **Docker** (`SEMICOLAB_DOCKER` env var) — opens Surfer WASM at `http://localhost:7681` with the VCD preloaded via `?load_url=`. A direct URL is printed to the terminal if `webbrowser.open` cannot open it on the host.
2. **Surfer native** — if `surfer` is found in PATH, launches it with the VCD path.
3. If Surfer is not found, a hint with the Surfer install URL is printed.

### In Surfer

1. Open the loaded VCD
2. Select the signals you want to see (`clk`, `arst_n`, `data_reg_a`, etc.)
3. Add them to the waveform view
4. Zoom to the full simulation range

---

## 8. Version Management

### Bump version (internal change)

When you make a significant RTL change and want to mark a new development iteration:

```bash
veriflow db bump-version --db ./database --tile 0001
```

- Version: `01` → `02`
- Revision: unchanged
- Previous directory: preserved as history
- New directory: `works/` copied, clean `runs/`

### Bump revision (advisor authorization)

When the advisor approves the design:

```bash
veriflow db bump-revision --db ./database --tile 0001
```

- Revision: `01` → `02`
- Version: **reset to `01`**
- Previous directory: preserved as history
- New directory: `works/` copied, clean `runs/`

### Traceability

Each tile ID in `tiles/` represents an independent instance with its own run history:

```
tiles/
├── MST130-01-26032500010101/   ← initial version
│   └── runs/run-001/ ... run-005/
├── MST130-01-26032500010201/   ← bump-version
│   └── runs/run-001/ ... run-003/
└── MST130-01-26032500010102/   ← bump-revision (version reset)
    └── runs/run-001/
```

---

## 9. Generated Files

Each run generates in `tiles/<tile_id>/runs/run-NNN/`:

### `manifest.yaml`
Full run metadata: tile ID, run ID, date, author, objective, status, tools, sources, artifacts, and per-stage results.

### `results.json`
Machine-readable run result (see section 13.4).

### `notes.md`
Designer notes for the run, taken from the `notes` field in `tile_config.yaml`.

### `summary.md`
Tabular results summary. Also printed to the console when the run completes.

### `README.md`
Tile documentation updated with data from `tile_config.yaml`. Regenerated on every run.

---

## 10. CSV Records

### `tile_index.csv`
Index of all tiles. Always reflects the most recent tile ID for each tile number. Columns: `tile_number`, `tile_id`, `tile_name`, `tile_author`, `version`, `revision`, `interface_name`. The `interface_name` column records the interface profile the tile was created under (empty for generic projects).

### `records.csv`
Complete history of all runs across all tiles. Each run appends a row with: Tile_ID, Run_ID, date, author, objective, status, stage results, tool version, run path, tags, and `Interface` — the interface profile name active for the run (empty for generic projects).

---

## 11. Tests

```bash
python -m veriflow.tests.runner
```

Tests use `tempfile.mkdtemp()` for isolated environments and clean up after themselves. The standalone runner needs no pytest or external tools (run tests execute without iverilog/yosys). The suite can also be collected with pytest: `python -m pytest veriflow/tests -q`.

---

## 12. Common Troubleshooting

### `ModuleNotFoundError: No module named 'veriflow'`
`cli.py` includes an automatic path fix. If it persists, use:
```bash
python -m veriflow.cli db <command> --db ./database  # or: veriflow db <command> --db ./database
```

### `Tool not found in PATH: iverilog`
Activate OSS CAD Suite (or otherwise put iverilog/yosys in PATH):
```bat
C:\Users\<user>\oss-cad-suite\environment.bat
```

### No waveform viewer opens
Install Surfer from [surfer-project.org](https://surfer-project.org) and ensure `surfer` is in PATH.

### Connectivity FAIL
Check the log:
```bash
type database\tiles\<tile_id>\runs\<run-NNN>\out\connectivity\logs\connectivity.log
```

### Simulation FAILED
Check the log:
```bash
type database\tiles\<tile_id>\runs\<run-NNN>\out\sim\logs\sim.log
```

### Waveform shows `xxxxxxxx`
Uninitialized signals display as `x`. Make sure `arst_n` is active at the start and the DUT initializes its outputs in the reset block.

---

## 13. Automation and machine-readable output

VeriFlow's default behavior — Rich terminal output, interactive TUI, waveform viewer — is unchanged when no extra flags are passed.

### 13.1 CLI flags

| Flag | Effect |
|---|---|
| `--json` | Suppresses Rich output; emits a single JSON object to stdout on completion |
| `--non-interactive` | Disables TUI and waveform viewer; safe for CI, scripts, and agents |

Both flags are global and can be combined.

### 13.2 Execution modes

| Mode | Flags | Human output | stdout |
|---|---|---|---|
| Human (default) | *(none)* | Rich color output | run summary |
| JSON only | `--json` | Suppressed | JSON object |
| Non-interactive | `--non-interactive` | Rich color output | run summary |
| JSON + non-interactive | `--json --non-interactive` | Suppressed | JSON object |

### 13.3 Recommended automation command

```bash
veriflow --json --non-interactive db run --db <db> --tile <tile>
```

Exit code is `0` on success, non-zero on any error.

### 13.4 `results.json` artifact

Every `db run` command writes `results.json` to the run directory alongside `manifest.yaml`. This file is always written — it does not require `--json`.

**Location:** `tiles/<tile_id>/runs/run-NNN/results.json`

| Field | Description |
|---|---|
| `schema_version` | Document schema version (`"1.2"`) |
| `tile_id` | Full tile identifier |
| `run_id` | Run identifier (`run-NNN`) |
| `date` | ISO 8601 date |
| `status` | Overall status: `PASS`, `PARTIAL`, or `FAIL` |
| `interface_name` | Selected interface profile name (e.g. `"semicolab"`), or `null` when no interface is configured |
| `stages` | Per-stage results (connectivity, simulation, synthesis) |
| `sources` | Relative paths to RTL and TB files used |
| `artifacts` | Relative paths to all generated output files |
| `error` | `null` on success; error object if the run was aborted |

**Example:**

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

For a generic project (`interface_name: null`), the file contains `"interface_name": null` and the connectivity stage reports `"status": "SKIPPED"`.

> **`schema_version` and forward compatibility:** `schema_version` will be incremented when the structure of `results.json` changes. Version `"1.2"` replaced the legacy `semicolab` boolean field with `interface_name`. Consumers that parse this file programmatically should read `schema_version` first and handle unknown versions gracefully rather than assuming a fixed shape.

### 13.5 Python API (`veriflow.api`)

For integrations that run inside the same Python process — TUI wrappers, CI harnesses, agents — `veriflow.api.run_tile` is the stable internal entry point. It delegates directly to `cmd_run()` without going through argparse or subprocess.

```python
from veriflow.api import run_tile
from veriflow.core import VeriFlowError

try:
    result = run_tile(
        "./database",
        "0001",
        skip_connectivity=True,   # same flags as the CLI
        skip_sim=False,
        skip_synth=False,
        non_interactive=True,     # suppress waveform viewer
    )
    print(result["status"])       # "PASS" | "PARTIAL" | "FAIL"
    print(result["schema_version"])  # "1.2"
except VeriFlowError as e:
    print(e.code, e.message)
```

**Function signature:**

```python
run_tile(
    db_path: str | Path,
    tile: str,
    *,
    skip_connectivity: bool = False,
    skip_sim: bool = False,
    skip_synth: bool = False,
    only_connectivity: bool = False,
    only_sim: bool = False,
    only_synth: bool = False,
    waves: bool = False,
    non_interactive: bool = False,
) -> dict
```

- Returns the same `run_result` dict that `cmd_run()` returns (same shape as `results.json`).
- `VeriFlowError` propagates to the caller unchanged.
- Raises `VF_NON_INTERACTIVE_VIEWER_DISABLED` if `waves=True` and `non_interactive=True`.
- This is an **internal** surface — it is not a REST or RPC API.

### 13.6 `--json` CLI output

When `--json` is active the CLI emits one JSON object to stdout after the command completes. All Rich output goes to stderr or is suppressed.

**Success (`db run`):**
```json
{
  "status": "SUCCESS",
  "command": "db run",
  "run_result": { "schema_version": "1.2", "tile_id": "...", ... }
}
```

`run_result` mirrors the contents of `results.json`. For other subcommands it is omitted (`db list-tiles`, `db list-runs`, and `db show-run` include their read results instead).

**Error:**
```json
{
  "status": "ERROR",
  "error": {
    "code": "VF_TILE_CONFIG_MISSING",
    "message": "tile_config.yaml not found: database/config/tile_0001/tile_config.yaml",
    "details": { "path": "database/config/tile_0001/tile_config.yaml" },
    "exit_code": 1
  }
}
```

**Known error codes:**

| Code | Condition |
|---|---|
| `VF_TILE_CONFIG_MISSING` | `tile_config.yaml` not found |
| `VF_INTERFACE_UNKNOWN` | `interface_name` not a registered interface profile |
| `VF_PROJECT_INTERFACE_REQUIRED` | `interface_name` missing from `project_config.yaml` |
| `VF_INTERFACE_CHECK_NO_PROFILE` | `--only-check` used with no interface profile configured |
| `VF_NON_INTERACTIVE_REQUIRES_COMMAND` | `--non-interactive` used without a subcommand |
| `VF_NON_INTERACTIVE_VIEWER_DISABLED` | `--waves` or `waves` used with `--non-interactive` |
| `VF_INTERRUPTED` | Process interrupted (Ctrl+C) |
| `VF_UNHANDLED_EXCEPTION` | Unexpected internal error |
| `VF_ERROR` | Generic fallback |

### 13.7 `--non-interactive` constraints

- Disables the TUI (no-argument launch becomes an error).
- Disables the waveform viewer (`--waves` and `waves` subcommand are blocked).
- All other commands work normally.

### 13.8 Portability

All paths written to `results.json` and `manifest.yaml` are relative to the database root. No OS-specific absolute paths appear in any persistent artifact. A `results.json` produced on Windows is readable without modification on Linux and vice versa.
