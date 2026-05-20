# VeriFlow V1 — User Manual

## 1. Introduction

VeriFlow V1 is an RTL verification framework designed for the multi-project ASIC chip design flow. It automates three verification stages — connectivity check, simulation, and synthesis — and generates structured documentation for every run.

**Internal components:**
- **VeriTile** — verification engine (iverilog + Yosys)
- **AutoDoc** — documentation engine (YAML, CSV, Markdown)
- **VeriFlow** — CLI orchestrator

---

## 2. Requirements

- Python 3.10 or higher
- PyYAML: `pip install pyyaml`
- Rich: `pip install rich`
- [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases) with `iverilog`, `vvp`, and `yosys` in PATH
- Optional: `pyfiglet` and `terminaltexteffects` for the animated SEMICOLAB banner
- Optional: `surfer` or `gtkwave` in PATH for waveform viewing

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

Expected result: `26 passed, 0 failed`.

---

## 4. Project Initialization

### 4.1 Create the database

```bash
veriflow --db ./database init
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
veriflow --db ./database init --force
```

### 4.2 Configure the project

Edit `database/project_config.yaml`:

```yaml
id_prefix: "MST130-01"       # prefix for Tile IDs
project_name: "My Chip"
repo: "https://github.com/user/repo"
description: |
  Chip project description.
```

The `id_prefix` field is required — tiles cannot be created without it.

---

## 5. Tile Management

### 5.1 Create a tile

```bash
veriflow --db ./database create-tile
```

Automatically generates:
- `database/config/tile_0001/tile_config.yaml` — tile + run configuration (single file)
- `database/config/tile_0001/src/rtl/` — folder for RTL
- `database/config/tile_0001/src/tb/tb_tile.v` — test template
- `database/tiles/<tile_id>/` — artifacts directory

### 5.2 Configure the tile

**`tile_config.yaml`** — contains both tile info (fill once) and run info (update before each run):
```yaml
tile_name: "Adder Tile"
tile_author: "Sebastian"
top_module: "adder_tile"    # exact name of the RTL module
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

    // USER LOGIC STARTS HERE //
    assign data_reg_c = data_reg_a + data_reg_b;
    assign csr_out    = 16'b0;
    assign csr_in_re  = 1'b0;
    assign csr_out_we = 1'b0;
    // USER LOGIC ENDS HERE //

endmodule
```

> All tiles must implement exactly the 9 ports defined by the VeriFlow port convention.

### 5.4 Write the testbench

**SemiCoLab mode (`semicolab: true`)**

`tb_tile.v` is created with the full testbench wrapper already in place. Write your stimuli between the markers — do not modify the rest of the file:

```verilog
    // USER TEST STARTS HERE //
    write_data_reg_a(32'd10);
    write_data_reg_b(32'd20);
    @(posedge clk);
    $display("result = %0d", data_reg_c);  // expected: 30
    // USER TEST ENDS HERE //
```

VeriFlow reads `tb_tile.v`, extracts the code between the markers, and injects it at runtime along with the DUT instantiation. The module wrapper, signals, clock, reset and tasks are all handled automatically.

> If `tb_tile.v` is not present in `src/tb/`, simulation is automatically skipped.

**Universal mode (`semicolab: false`)**

Write a complete testbench. Top module must be named `tb`. VeriFlow injects `$dumpfile`/`$dumpvars` automatically if not present:

```verilog
`timescale 1ns / 1ps
module tb;
    reg clk;
    reg rst_n;
    wire [7:0] result;

    my_module DUT (.clk(clk), .rst_n(rst_n), .result(result));

    always #5 clk = ~clk;

    initial begin
        clk = 0; rst_n = 0;
        #20 rst_n = 1;
        #100;
        $display("result = %0d", result);
        $finish;
    end
endmodule
```

**Available tasks:**

| Task | Usage |
|---|---|
| `write_data_reg_a(data)` | Applies value to data_reg_a on the next posedge |
| `write_data_reg_b(data)` | Applies value to data_reg_b on the next posedge |
| `write_csr_in(data)` | Applies value to csr_in |
| `reset_csr_in` | Clears bits [15:12] of csr_in |
| `read_csr_out(data)` | Captures csr_out into a variable |

**Directly accessible signals:**
`clk`, `arst_n`, `csr_in`, `data_reg_a`, `data_reg_b`, `data_reg_c`, `csr_out`, `csr_in_re`, `csr_out_we`

> The testbench automatically includes 2 reset cycles at the start before calling your code.

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
veriflow --db ./database run --tile 0001
```

The pipeline executes in order:

1. **Connectivity check** — compiles RTL + TB with iverilog to verify ports connect correctly. If it fails, the pipeline stops.
2. **Simulation** — compiles and injects the user test, runs with `vvp`, generates `waves.vcd`.
3. **Synthesis** — runs Yosys with hierarchy check, synth, check, and stat.
4. **Documentation** — generates manifest, notes, summary, README, updates records.csv.

### 6.2 Run options

```bash
# Show waveforms automatically when done
veriflow --db ./database run --tile 0001 --waves

# Connectivity check only
veriflow --db ./database run --tile 0001 --only-check

# Simulation only
veriflow --db ./database run --tile 0001 --only-sim

# Synthesis only
veriflow --db ./database run --tile 0001 --only-synth

# Skip synthesis
veriflow --db ./database run --tile 0001 --skip-synth

# Skip simulation
veriflow --db ./database run --tile 0001 --skip-sim
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
- `PASS` — everything passed
- `PARTIAL` — at least one stage was skipped
- `FAIL` — connectivity or synthesis failed

---

## 7. Waveforms

### View waveforms of the latest run

```bash
veriflow --db ./database waves --tile 0001
```

### View waveforms of a specific run

```bash
veriflow --db ./database waves --tile 0001 --run run-003
```

VeriFlow opens waveforms using the following priority:

1. **Docker** (`SEMICOLAB_DOCKER` env var) — opens Surfer WASM at `http://localhost:7681` with the VCD preloaded via `?load_url=`. A direct URL is printed to the terminal if `webbrowser.open` cannot open it on the host.
2. **Surfer native** — if `surfer` is found in PATH, launches it with the VCD path.
3. **GTKWave fallback** — if `gtkwave` is found in PATH (and Surfer is not).
4. If neither is found, a hint with the Surfer install URL is printed.

### In GTKWave (fallback)

1. In the SST panel on the left, expand `tb` → `DUT`
2. Select the signals you want to see (`clk`, `arst_n`, `data_reg_a`, etc.)
3. Click **Append** or **Insert** to add them to the viewer
4. Press **Ctrl+Shift+F** to zoom to the full simulation range

---

## 8. Version Management

### Bump version (internal change)

When you make a significant RTL change and want to mark a new development iteration:

```bash
veriflow --db ./database bump-version --tile 0001
```

- Version: `01` → `02`
- Revision: unchanged
- Previous directory: preserved as history
- New directory: `works/` copied, clean `runs/`

### Bump revision (advisor authorization)

When the advisor approves the design:

```bash
veriflow --db ./database bump-revision --tile 0001
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

### `notes.md`
Designer notes for the run, taken from `run_config.yaml`.

### `summary.md`
Tabular results summary. Also printed to the console when the run completes.

### `README.md`
Tile documentation updated with data from `tile_config.yaml`. Regenerated on every run.

---

## 10. CSV Records

### `tile_index.csv`
Index of all tiles. Always reflects the most recent tile ID for each tile number.

### `records.csv`
Complete history of all runs across all tiles. Each run appends a row with: Tile_ID, Run_ID, date, author, objective, status, stage results, tool version, run path, and tags.

---

## 11. Tests

```bash
python -m veriflow.tests.runner
```

Tests use `tempfile.mkdtemp()` for isolated environments and clean up after themselves. No pytest or external tools required (run tests execute without iverilog/yosys).

---

## 12. Common Troubleshooting

### `ModuleNotFoundError: No module named 'veriflow'`
`cli.py` includes an automatic path fix. If it persists, use:
```bash
python -m veriflow.cli --db ./database <command>  # or: veriflow --db ./database <command>
```

### `Tool not found in PATH: iverilog`
Activate OSS CAD Suite:
```bat
C:\Users\<user>\oss-cad-suite\environment.bat
```

### No waveform viewer opens
VeriFlow tries Surfer first, then GTKWave. Install Surfer from [surfer-project.org](https://surfer-project.org) or ensure GTKWave is in PATH via OSS CAD Suite.

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

### GTKWave shows `xxxxxxxx`
Uninitialized signals display as `x`. Make sure `arst_n` is active at the start and the DUT initializes its outputs in the reset block.
