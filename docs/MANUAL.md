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

To use a profile that isn't one of VeriFlow's built-ins, add `interface_definition:`
pointing at a Verilog port-contract stub (relative to the database directory):

```yaml
interface_name: tinytapeout
interface_definition: ./interfaces/tinytapeout_if.v
```

See [14.6](#146-custom-interface-profiles-interfacedefinition) for the full
explanation (written from Project Mode's `veriflow.yaml`, but the mechanism —
and the `.v` stub format — is identical for both modes).

### 4.3 Customize the tile ID format (`id_format`)

By default, `create-tile` generates tile IDs in the fixed layout used since the project's
earliest versions: `<prefix>-<YYMMDD><tile_number><version><revision>` (e.g.
`MST130-01-26032500010101`). This is controlled by the optional `id_format` field in
`project_config.yaml`:

```yaml
id_format: "{prefix}-{date}{tile_number}{version}{revision}"  # default
```

`id_format` is a Python format string evaluated against the placeholders below at
`create-tile` time. Omitting `id_format` entirely keeps the default layout, so existing
databases are unaffected.

| Placeholder | Resolves to |
|---|---|
| `{prefix}` | `id_prefix` |
| `{date}` | `create-tile` date, `YYMMDD` |
| `{tile_number}` | tile number, zero-padded to 4 digits |
| `{version}` | `id_version`, zero-padded to 2 digits |
| `{revision}` | `id_revision`, zero-padded to 2 digits |
| `{shuttle_name}` | `shuttle_name` (optional field, default `""`) |
| `{interface}` | `interface_name` |
| `{technology}` | `technology.name`, or `"generic"` if the `technology:` section is omitted |
| `{author_initials}` | initials of the tile author (from `--tile-author`, computed at `create-tile` time — e.g. "Roman Lugo" → `"RL"`) |
| `{short_hash}` | **not yet implemented** (requires a content snapshot) — resolves to `"000000"` and prints a `VF_ID_PLACEHOLDER_UNAVAILABLE` warning if used |

An unknown placeholder (a typo) fails fast with `VF_ID_FORMAT_INVALID`, naming the bad
placeholder and listing the valid ones.

Common formats:

```yaml
# Default -- current fixed-width layout
id_format: "{prefix}-{date}{tile_number}{version}{revision}"

# Minimal
id_format: "{prefix}-{tile_number}"

# With shuttle name
id_format: "{prefix}-{shuttle_name}-{tile_number}"

# With interface, dotted version.revision
id_format: "{prefix}-{interface}-{tile_number}-{version}.{revision}"
```

> **`bump-version` / `bump-revision` and custom `id_format`.** These commands parse the
> *existing* tile_id's fixed-width numeric suffix to derive the next version/revision, then
> generate the new ID with the legacy hardcoded layout — they do not yet re-run `id_format`.
> For databases still using the default `id_format`, this is transparent. If you set a custom
> `id_format` that doesn't produce the legacy `<prefix>-YYMMDDNNNNVVRR` shape, `bump-version`/
> `bump-revision` fail cleanly with `VF_TILE_ID_BUMP_UNSUPPORTED_FORMAT` rather than crash —
> bumping under a custom `id_format` is not supported yet.

### 4.4 Configure the pipeline (`pipeline`)

By default `db run` executes connectivity (if `interface_name` is also set), simulation (if
the tile has testbench sources), then synthesis — the same behavior as always. The optional
`pipeline` section in `project_config.yaml` sets a **database-wide default** stage list/order
for all tiles; an individual tile's `tile_config.yaml` may override it completely (see
[5.2](#52-configure-the-tile)).

```yaml
pipeline:
  stages:
    - type: connectivity
    - type: simulation
      backend: icarus     # optional per-stage override
    - type: synthesis
      backend: yosys
```

| Stage type | Runs when listed |
|---|---|
| `connectivity` | Only if `interface_name` is also set — same precondition as today |
| `simulation` | Only if the tile has testbench sources — same precondition as today |
| `synthesis` | No precondition |

A stage type left out of `pipeline.stages` behaves exactly like passing the matching
`--skip-check`/`--skip-sim`/`--skip-synth` flag to `db run` — it shows up as `SKIPPED` in
the results, not omitted. An unrecognized `type` fails with `VF_PIPELINE_STAGE_UNKNOWN`.
Omitting `pipeline` entirely (the common case) keeps the current default — existing
databases are unaffected.

> **Stage order in Database Mode is not reorderable.** Unlike Project Mode's `veriflow.yaml`,
> `db run`'s connectivity → simulation → synthesis execution order is fixed regardless of the
> order stages are listed in `pipeline.stages` — the section only controls **which** stages
> run and their `backend:`, not the sequence. This is a scope limitation, not a bug: `db run`'s
> early-stop-on-connectivity-FAIL logic assumes connectivity always runs first.

---

## 5. Tile Management

### 5.1 Create a tile

```bash
veriflow db create-tile --db ./database --top-module adder_tile --tile-author "Roman Lugo"
```

`--top-module` is required for Semicolab projects: the name is written into `tile_config.yaml` and substituted into the generated testbench so both share the same DUT name. For generic projects it can be omitted.

`--tile-author` is optional: when given, it's written into `tile_config.yaml`'s `tile_author` field and used to compute the `{author_initials}` `id_format` placeholder (see [4.3](#43-customize-the-tile-id-format-id_format)).

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

`tile_config.yaml` also accepts an optional `pipeline` section (see
[4.4](#44-configure-the-pipeline-pipeline)) that **completely overrides** `project_config.yaml`'s
`pipeline` for this tile only:

```yaml
pipeline:
  stages:
    - type: connectivity
    - type: synthesis   # no simulation for this tile
```

Omit it to inherit the database's `pipeline` (or the current default if the database doesn't
set one either).

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

> **Keeping `tb_tile.v` in sync with `top_module`.** `create-tile` instantiates the DUT in
> `tb_tile.v` using whatever `top_module` you passed at creation time (or leaves it blank for
> generic projects). If you later change `top_module` in `tile_config.yaml` — for example when
> switching from direct RTL to a wrapper module — `tb_tile.v` is **not** updated automatically;
> it is a hand-edited file and VeriFlow does not rewrite it after generation. `db run` checks for
> this and prints a `VF_SIM_TB_MODULE_MISMATCH` warning (not an error, since a mismatch can be
> intentional) when the instantiated module name no longer matches `top_module`. Update the DUT
> instantiation in `tb_tile.v` to clear the warning.

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

1. **Docker** (`VERIFLOW_DOCKER` env var; `SEMICOLAB_DOCKER` is a deprecated alias) — opens Surfer WASM at `http://localhost:7681` with the VCD preloaded via `?load_url=`. A direct URL is printed to the terminal if `webbrowser.open` cannot open it on the host.
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

---

## 14. Project Mode

Everything above this section describes **Database Mode** (`veriflow db ...`). This section
covers **Project Mode** (`veriflow project ...`), the other operating mode introduced in
section 1.

### 14.1 When to use Project Mode vs Database Mode

Use **Project Mode** when you want to verify a single RTL module against a single
`veriflow.yaml` file, with no database, no tile numbering, and no multi-project run history —
for example, checking a standalone IP block, iterating quickly during development, or running
in CI on a repository that isn't a VeriFlow database. There is nothing to initialize beyond the
config file itself.

Use **Database Mode** when you're tracking many tiles across a shuttle/project, need version
and revision history (`bump-version`/`bump-revision`), auto-generated per-tile documentation
(`manifest.yaml`, `notes.md`, `summary.md`, `README.md`), and CSV indexes (`tile_index.csv`,
`records.csv`).

The two modes are not mutually exclusive: `veriflow project import` (14.3) takes a verified
Project Mode run and promotes it into a database as a new tile, so a common flow is
"prototype in Project Mode, then import into Database Mode once it's ready to track long-term."

### 14.2 Full flow

```bash
# 1. Scaffold a commented veriflow.yaml in the current directory
veriflow project init

# 2. Edit veriflow.yaml -- at minimum set design.top_module and design.rtl_sources
#    (see PROJECT_CONFIG.md for the complete schema: interface, execution,
#    pipeline, technology, simulation, output sections)

# 3. Run the pipeline
veriflow project run

# 4. Inspect the result
cat runs/run-001/results.json
```

`project run` executes connectivity (only if `interface` is configured), simulation (only if
`tb_sources` are non-empty), then synthesis — or whatever subset the optional `pipeline:`
section selects (14.5). Each run is written to `runs/run-NNN/` (auto-incremented), and
`results.json` is always written there, unconditionally — it does not require `--json`
(same convention as Database Mode's `results.json`, 13.4).

For the full `veriflow.yaml` schema, validation error codes, and `pipeline:` reference, see
[PROJECT_CONFIG.md](PROJECT_CONFIG.md).

### 14.3 `project import` — promote a run into a database

```bash
veriflow project import --db ./database [--config veriflow.yaml] [--run run-NNN]
```

Imports a verified Project Mode run into a Database Mode database as a new tile: creates the
tile, copies the run's RTL (and testbench, if present) sources into the tile's `src/rtl`/`src/tb`,
and copies `results.json` to `config/tile_NNNN/imported_run.json` for traceability. See
[PROJECT_CONFIG.md](PROJECT_CONFIG.md#project-import) for the full syntax, validation rules,
and error codes.

### 14.4 `results.json` — Project Mode schema

Every `project run` writes `results.json` to the run directory. Unlike Database Mode's
`results.json` (13.4, `schema_version "1.2"`), Project Mode's has its own, simpler schema
(`schema_version "1.0"`) since there is no tile/version/revision concept in this mode.

**Location:** `<runs_dir>/run-NNN/results.json` (default `runs_dir`: `runs`)

| Field | Description |
|---|---|
| `schema_version` | Document schema version (`"1.0"`) |
| `status` | Overall status: `PASS` or `FAIL` |
| `command` | Always `"project run"` |
| `run_dir` | Path to this run directory, relative to the config file |
| `interface_name` | Selected interface profile name, or `null` for a generic project |
| `top_module` | RTL top module name |
| `rtl_sources` / `tb_sources` | Relative paths to the RTL/TB files used |
| `technology` | Technology target name (`"generic"` by default) |
| `stages` | Per-stage results (`connectivity`, `simulation`, `synthesis`); a stage absent from the pipeline reports `"status": "SKIPPED"` |
| `rtl_hash` | `{filename: sha256}` for each RTL source, snapshotted at run time |
| `veriflow_version` | VeriFlow version that produced this run |
| `timestamp` | ISO 8601 UTC timestamp |

**Example:**

```json
{
  "schema_version": "1.0",
  "status": "PASS",
  "command": "project run",
  "run_dir": "runs/run-002",
  "interface_name": null,
  "top_module": "counter8",
  "rtl_sources": ["counter8.v"],
  "tb_sources": [],
  "technology": "generic",
  "stages": {
    "connectivity": {"status": "SKIPPED", "log": null},
    "simulation": {"status": "SKIPPED", "log": null, "waves": null},
    "synthesis": {"status": "PASS", "log": "runs/run-002/out/synth/logs/synth.log"}
  },
  "rtl_hash": {"counter8.v": "b7d9fc0301211c1143be13ea41b2a1d9cc558b473387088cf234b2459c436935"},
  "veriflow_version": "1.0.0",
  "timestamp": "2026-07-14T04:16:19.283009+00:00"
}
```

`project import` (14.3) reads this file to decide which run is importable (`status: "PASS"`)
and which sources to copy.

### 14.5 Configurable pipeline (`pipeline`)

`veriflow.yaml` supports the same optional `pipeline:` section as `project_config.yaml`
(4.4) — a list of stage types (`connectivity`, `simulation`, `synthesis`), in order, each with
an optional per-stage `backend:` override. Omitting the section keeps the current default
(all three stages, connectivity/simulation still gated on `interface`/`tb_sources` being
configured). See [PROJECT_CONFIG.md](PROJECT_CONFIG.md#pipeline-optional) for the full schema,
examples, and validation error codes (`VF_PIPELINE_CONFIG_INVALID`, `VF_PIPELINE_STAGE_UNKNOWN`).

### 14.6 Custom interface profiles (`interface.definition`)

Built-in interface profiles (currently just `semicolab`) live under
`veriflow/interfaces/<name>/` inside the installed package — each is a folder with:

| File | Required | Contents |
|---|---|---|
| `interface.v` | yes | A Verilog module stub declaring only the port list (name, direction, width). No body needed — an empty `endmodule` is enough. |
| `tb_template.v` | no | A testbench scaffold copied into `src/tb/tb_tile.v` by `db create-tile` when this profile is selected. |
| `meta.yaml` | no | `description:` and `requires_top_module:` — the two profile attributes that can't be expressed in a `.v` file. Both default to empty/`false` when this file is absent. |

The port contract itself is parsed from `interface.v` with the same
regex-based extractor used for RTL auto-detection in `wrap init` — the
profile's name is the parsed **module name**, not the directory name.

To use a profile that isn't built in, add `definition:` alongside `name:` in
the `interface` section, pointing at your own `.v` stub (path relative to
`veriflow.yaml`):

```yaml
interface:
  name: tinytapeout
  definition: ./interfaces/tinytapeout_if.v
```

```verilog
// interfaces/tinytapeout_if.v
module tinytapeout (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out
);
endmodule
```

`project run` registers the profile from that file before the connectivity
stage runs, so `interface.name` becomes available immediately — no code
change, no restart. If `name:` doesn't match the module name actually
declared in the `.v` file, VeriFlow uses the module name and emits a
`UserWarning` (`VF_INTERFACE_NAME_MISMATCH`) rather than failing. Registering
a name that collides with an existing profile (including a built-in one)
overwrites it for the rest of the process, with its own warning
(`VF_INTERFACE_PROFILE_OVERWRITTEN`) — useful for locally testing a
different revision of a profile without renaming it.

Database Mode's `project_config.yaml` supports the identical mechanism under
a differently-named key (see 4.2): `interface_name:` + `interface_definition:`,
resolved relative to the database directory instead of `veriflow.yaml`.

Omitting `definition:` entirely is unchanged from before — `name:` must then
refer to an already-registered (built-in) profile, exactly as today.

### 14.7 Technology profiles (`technology.yaml`)

Built-in technology profiles (`generic`, `sky130`, `gf180`, `ihp130`) live as
individual `.yaml` files under `veriflow/technologies/` inside the installed
package — one file per technology, keyed by its own `name:` field (not the
filename). Schema:

```yaml
name: sky130                # required
description: "SkyWater 130nm PDK -- liberty not yet vendored"
synthesis_backend: yosys    # informational today; synthesis always uses yosys
liberty: null                # path to a .lib file, or null
synth_extra: []              # extra yosys script lines, appended after `synth`
```

`liberty` and `synth_extra` are the two fields that actually change synthesis
behavior, wired into `core/synth_runner.py`:

- When `liberty` is set, `abc -liberty <path>` is appended to the yosys
  script right after `synth`, performing real cell-library technology
  mapping.
- Every line in `synth_extra` is appended after that (and before
  `check`/`stat`) — e.g. `synth_extra: ["-flatten"]` for a flattened
  netlist, with no code change required.

None of the four built-in technologies vendor a real `liberty` file yet
(`sky130.yaml`/`gf180.yaml`/`ihp130.yaml` all ship `liberty: null` in the
repo), so in practice every built-in technology still produces the same
generic synthesis script until its PDK is installed with `veriflow pdk
install` (14.8) -- once installed, `liberty` is resolved automatically at
synthesis time, no config edit required. Set `technology.name` in
`veriflow.yaml` (or `project_config.yaml`'s `technology:` section — see the
`{technology}` placeholder in 4.3) to select one; an unregistered name fails
with `VF_TECHNOLOGY_UNKNOWN`.

### 14.8 PDK management (`veriflow pdk`)

VeriFlow installs and tracks PDKs itself under `~/.veriflow/pdks/<technology
name>/` -- no `PDK_ROOT` or liberty path environment variables to set by
hand. Four subcommands:

```bash
veriflow pdk list                 # table: PDK, Status, Liberty, Install hint
veriflow pdk install <name>       # e.g. sky130, gf180, ihp130
veriflow pdk update <name>        # re-fetch the latest version
veriflow pdk status               # like list, plus full resolved liberty paths
```

Status values in `pdk list`/`pdk status`:

| Status | Meaning |
|---|---|
| `OK` | PDK installed and its liberty file resolved (or the technology needs no PDK, e.g. `generic`) |
| `NOT INSTALLED` | `VERIFLOW_PDK_ROOT/<name>/` doesn't exist yet |
| `INSTALLED, NO LIBERTY` | The directory exists but `liberty_glob` matched nothing inside it |

Each built-in technology's `technologies/<name>.yaml` declares how it's
installed:

```yaml
install_method: volare       # "volare" | "git"
volare_pdk: sky130           # PDK name passed to `volare enable --pdk`
pdk_subdir: sky130A          # subdirectory of the PDK root holding the actual PDK tree
liberty_glob: "libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
install_hint: "veriflow pdk install sky130"
```

- `sky130` and `gf180` use `install_method: volare` and require the `pdks`
  extra (`pip install veriflow-eda[pdks]`); `pdk install`/`pdk update` fail
  with a clear message (exit code 1) if `volare` isn't importable/in PATH.
- `ihp130` uses `install_method: git` and only requires `git` in PATH
  (`git clone`/`git pull` under the hood).
- `generic` has no `install_method` -- it's always reported `OK`, "no PDK
  required".

`veriflow doctor`'s `[TECHNOLOGIES]` section shows the same OK/NOT INSTALLED
status for every registered technology, alongside the existing EDA tool
checks -- a missing PDK does **not** affect `doctor`'s exit code, since
synthesis still works (falling back to generic mapping) without one.

If a technology's PDK isn't installed when `project run`/`db run` reaches the
synthesis stage, the run still completes -- a `VF_TECHNOLOGY_PDK_NOT_INSTALLED`
warning is printed and included in `results.json`'s `warnings` field, but
synthesis proceeds without technology mapping rather than aborting.

### 14.9 External technology definitions (`technology.definition`)

Like `interface.definition` (14.6), a technology doesn't have to be one of
the four built-ins. Add `definition:` alongside `name:` in the `technology`
section, pointing at your own `.yaml` file (path relative to `veriflow.yaml`):

```yaml
technology:
  name: mi_proceso
  definition: ./technologies/mi_proceso.yaml
```

```yaml
# technologies/mi_proceso.yaml
name: mi_proceso
description: "Custom in-house technology"
synthesis_backend: yosys
liberty: ./cells/mi_proceso.lib   # relative to veriflow.yaml, not to this file
synth_extra: []
```

`project run` registers the profile from that file before the synthesis
stage runs. A relative `liberty:` path inside the definition file is resolved
against `veriflow.yaml`'s directory (not the process's current working
directory, and not the definition file's own directory). If `name:` in the
`technology` section doesn't match the `name:` declared inside the
definition file, VeriFlow uses the definition file's name and emits a
`VF_TECHNOLOGY_NAME_MISMATCH` warning, mirroring `interface.definition`'s
`VF_INTERFACE_NAME_MISMATCH` behavior.

Database Mode's `project_config.yaml` supports the identical mechanism under
a top-level `technology_definition:` key (paired with the existing
`technology: {name: ...}` section), resolved relative to the database
directory instead of `veriflow.yaml` -- the same naming convention as
`interface_name:` / `interface_definition:` (4.2).
