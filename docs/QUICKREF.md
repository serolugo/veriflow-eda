# VeriFlow V1 — Quick Reference

## Activate environment (Windows)
```bat
C:\Users\<user>\oss-cad-suite\environment.bat
cd C:\path\to\your\project
```

---

## Commands

```bash
# Interactive TUI (no arguments)
veriflow

# Project Mode — run a project described by veriflow.yaml
veriflow project run
veriflow project run --config veriflow.yaml

# Initialize database
veriflow db init --db ./database
veriflow db init --db ./database --force

# Create tile (--top-module required for Semicolab projects)
veriflow db create-tile --db ./database --top-module my_module

# Full run
veriflow db run --db ./database --tile 0001

# Run with options
veriflow db run --db ./database --tile 0001 --waves
veriflow db run --db ./database --tile 0001 --skip-synth
veriflow db run --db ./database --tile 0001 --only-check
veriflow db run --db ./database --tile 0001 --skip-sim

# Open waveforms
veriflow db waves --db ./database --tile 0001
veriflow db waves --db ./database --tile 0001 --run run-003

# Bump version / revision
veriflow db bump-version --db ./database --tile 0001
veriflow db bump-revision --db ./database --tile 0001

# Read-only queries
veriflow db list-tiles --db ./database
veriflow db list-runs  --db ./database --tile 0001
veriflow db show-run   --db ./database --tile 0001 --run run-001

# Run tests
python -m veriflow.tests.runner
```

---

## Automation / CI

```bash
# Recommended automation command (JSON output, no interactive UI)
veriflow --json --non-interactive db run --db ./database --tile 0001

# JSON output only (Rich output suppressed; stdout = JSON)
veriflow --json db run --db ./database --tile 0001

# Non-interactive only (Rich output shown; no TUI or waveform viewer)
veriflow --non-interactive db run --db ./database --tile 0001
```

`--json` and `--non-interactive` are global flags — place them before the subcommand.

Exit code is `0` on success, non-zero on any error.

Every `db run` always writes `tiles/<tile_id>/runs/run-NNN/results.json` regardless of flags.

---

## Interface profiles

Set via `interface_name` in `database/project_config.yaml`. Applies to the entire database.

| Value | Description |
|---|---|
| `interface_name: "semicolab"` | Semicolab interface profile — nine-port contract, connectivity check enabled |
| `interface_name: null` | Generic project — any RTL module, no connectivity check |

Project Mode uses an `interface:` section in `veriflow.yaml` instead (`name: semicolab`, or omit the section for a generic project).

---

## Waveform viewer priority

1. Docker (`VERIFLOW_DOCKER`; `SEMICOLAB_DOCKER` deprecated) → Surfer WASM at `http://localhost:7681`
2. `surfer` in PATH → Surfer native

---

## Workflow (Database Mode)

```
db init → fill project_config.yaml (set id_prefix and interface_name)
        → db create-tile (--top-module for Semicolab)
        → fill tile_config.yaml
        → add RTL to src/rtl/<top_module>.v
        → edit the self-contained testbench in src/tb/tb_tile.v
        → update run info in tile_config.yaml
        → db run --tile XXXX --waves
```

---

## Files to edit per tile

```
database/config/tile_0001/
├── tile_config.yaml        ← tile info + run info (single file)
└── src/
    ├── rtl/<top_module>.v  ← user RTL
    └── tb/
        └── tb_tile.v       ← self-contained testbench (whole file is yours)
```

> If no `.v` file is present in `src/tb/`, simulation is automatically skipped.

---

## Testbenches (self-contained)

Testbenches are complete Verilog modules: you (or the generated scaffold) instantiate the DUT, and VeriFlow compiles RTL + TB files together. The testbench top module is selected by `tb_top_module` in `tile_config.yaml` (default `tb`); Project Mode uses `simulation.tb_top`.

**Semicolab scaffold** — `db create-tile` generates `tb_tile.v` with signals, clock/reset, DUT instantiation, `$dumpfile`/`$dumpvars`, and helper tasks already in place. Add stimulus in the marked block; the whole file is editable:

```verilog
    // ── USER STIMULUS BEGIN ──
    write_data_reg_a(32'd1);
    write_data_reg_b(32'd1);
    @(posedge clk);
    $display("result = %0d", data_reg_c);
    // ── USER STIMULUS END ──
```

**Generic scaffold** — minimal skeleton; declare signals and instantiate your DUT yourself:

```verilog
`timescale 1ns / 1ps
module tb;
  // your signals, DUT instantiation and test here
  initial begin
    $dumpfile("waves.vcd");
    $dumpvars(0, tb);
  end
  initial begin
    $finish;
  end
endmodule
```

> Include `$dumpfile` / `$dumpvars` yourself if you want waveforms.

---

## Tasks in the Semicolab scaffold

| Task | Description |
|---|---|
| `write_data_reg_a(data)` | Write to data_reg_a |
| `write_data_reg_b(data)` | Write to data_reg_b |
| `write_csr_in(data)` | Write to csr_in |
| `reset_csr_in` | Clear bits [15:12] of csr_in |
| `read_csr_out(data)` | Read csr_out into variable |

Defined inside the generated `tb_tile.v` — part of your testbench, editable.

**Semicolab interface signals:** `clk`, `arst_n`, `csr_in`, `data_reg_a`, `data_reg_b`, `data_reg_c`, `csr_out`, `csr_in_re`, `csr_out_we`

---

## Run status

| Status | Condition |
|---|---|
| `PASS` | All executed stages passed |
| `PARTIAL` | At least one stage was SKIPPED |
| `FAIL` | Connectivity FAIL, Simulation FAILED, or Synthesis FAIL |

---

## Tile ID format

```
MST130-01-26032500010102
│         │      │  │  └─ revision (02)
│         │      │  └──── version (01)
│         │      └─────── tile number (0001)
│         └────────────── date YYMMDD (260325)
└──────────────────────── id_prefix
```

---

## Version hierarchy

- `bump-version` → version +1, revision unchanged *(designer iteration)*
- `bump-revision` → revision +1, version reset to 01 *(advisor authorization)*
- Both preserve the previous directory and create a new clean one
