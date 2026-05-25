# VeriFlow V1 — System Specification

## 1. Overview

VeriFlow V1 is a lightweight RTL verification framework for multi-project ASIC chip design. It automates the connectivity check, simulation, and synthesis flow for individual hardware tiles, and generates structured documentation for every run.

The system is composed of three internal components orchestrated through a single CLI:

- **VeriTile** — RTL verification engine (connectivity check, simulation, synthesis)
- **AutoDoc** — documentation engine (run records, structured files, CSV indexes)
- **VeriFlow** — CLI orchestrator that coordinates both

---

## 2. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| External dependencies | PyYAML |
| Persistence | CSV + YAML (no database) |
| Simulator | Icarus Verilog (`iverilog`, `vvp`) |
| Synthesizer | Yosys |
| Waveform viewer | Surfer |
| Distribution | OSS CAD Suite |
| Compatibility | Windows, Linux, macOS |
| CI/CD | GitHub Actions compatible |

---

## 3. Project Structure

```
veriflow/
├── cli.py                   # CLI entry point
├── commands/                # Per-command implementation
│   ├── init_db.py
│   ├── create_tile.py
│   ├── run.py
│   ├── waves.py
│   ├── bump_version.py
│   └── bump_revision.py
├── core/                    # Reusable core logic
│   ├── __init__.py          # VeriFlowError
│   ├── tile_id.py
│   ├── run_id.py
│   ├── csv_store.py
│   ├── copier.py
│   ├── sim_runner.py
│   ├── synth_runner.py
│   ├── log_parser.py
│   └── validator.py
├── generators/              # Documentation file generators
│   ├── readme.py
│   ├── notes.py
│   ├── manifest.py
│   ├── summary.py
│   └── results.py           # results.json writer
├── models/                  # Configuration dataclasses
│   ├── project_config.py
│   └── tile_config.py         # merged tile + run fields
├── template/                # Base Verilog files (owned by VeriFlow)
│   ├── ip_tile.v
│   ├── tb_base.v
│   └── tb_tasks.v
├── ui/                      # Terminal UI and styled output
│   ├── banner.py            # SEMICOLAB banner (pyfiglet + TerminalTextEffects)
│   ├── output.py            # Styled output helpers (Rich)
│   ├── theme.py             # Central color palette and Rich theme
│   ├── themes.py            # 16 Textual-compatible color palettes
│   └── tui.py               # Redirect stub to tilebench TUI
└── tests/
    ├── runner.py
    └── test_veriflow.py
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
│           └── tb/           # User test code
└── tiles/
    └── <tile_id>/            # Generated artifacts per tile
        ├── README.md
        ├── works/            # Latest verified sources
│       ├── rtl/
│       └── tb/
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
veriflow [--json] [--non-interactive] --db <path> <command> [options]

# Also available as:
python veriflow/cli.py --db <path> <command> [options]
```

### Global flags

| Flag | Description |
|---|---|
| `--json` | Suppress Rich output; emit single JSON object to stdout |
| `--non-interactive` | Disable TUI and waveform viewer; safe for CI/agent use |

### Subcommands

| Command | Description |
|---|---|
| `init [--force]` | Initialize the database |
| `create-tile` | Create a new tile |
| `run --tile XXXX [flags]` | Execute the verification pipeline |
| `waves --tile XXXX [--run run-NNN]` | Open waveform viewer (Surfer) |
| `bump-version --tile XXXX` | Increment tile version |
| `bump-revision --tile XXXX` | Increment tile revision |

### `run` command flags

| Flag | Description |
|---|---|
| `--skip-check` | Skip connectivity check |
| `--skip-sim` | Skip simulation |
| `--skip-synth` | Skip synthesis |
| `--only-check` | Run connectivity check only |
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
description: |
semicolab: true   # false → Universal mode (skip connectivity check)
```

### `tile_config.yaml`
Contains both tile information (permanent) and run information (updated each run):
```yaml
tile_name: ""
tile_author: ""
top_module: ""        # must match the RTL module name exactly
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

---

## 9. CSV Files

### `tile_index.csv`
```
tile_number, tile_id, tile_name, tile_author, version, revision
```
- One row per tile
- Updated on every bump
- Source of truth for resolving tile_number → current tile_id

### `records.csv`
```
Tile_ID, Run_ID, Date, Author, Objective, Status,
Version, Revision, Connectivity, Simulation, Synthesis,
Tool_Version, Main_Change, Run_Path, Tags, Semicolab
```
- One row appended per run
- `Run_Path` relative to `tiles/`
- `Semicolab` is `"true"` or `"false"` (reflects the mode at the time of the run)
- Queryable by an LLM for historical analysis

---

## 10. Verification Pipeline

```
[Connectivity Check] → FAIL → document and stop
        ↓ PASS
[Simulation]         → FAILED → document, continue
        ↓
[Synthesis]          → FAIL → document, complete run
        ↓
[Documentation]      → manifest, notes, summary, README, records
```

### Status derivation

| Condition | Status |
|---|---|
| Connectivity FAIL | FAIL |
| Any stage SKIPPED | PARTIAL |
| All PASS / COMPLETED | PASS |

---

## 11. Testbench Architecture

### Semicolab mode
`tb_tile.v` (copied to `src/tb/` on `create-tile`) is both the testbench wrapper and the user test file. VeriFlow:

1. Reads `tb_tile.v` from `src/tb/` in the run snapshot
2. Replaces `/* MODULE_INSTANTIATION */` with the auto-generated DUT instantiation
3. Extracts code between `// USER TEST STARTS HERE //` and `// USER TEST ENDS HERE //` from the same file
4. Replaces `/* USER_TEST */` with the extracted code
5. Writes the result to a temporary file, compiles, then deletes it

The user only edits the section between the markers. The rest of `tb_tile.v` is managed by VeriFlow and should not be modified.

If `tb_tile.v` is not present in `src/tb/`, simulation is skipped automatically. The connectivity check still runs using `tb_base.v` from the tool `template/` directory.

### Universal mode
1. Reads `tb_tile.v` from `src/tb/`
2. If `$dumpfile` is not present, injects it automatically after the module declaration
3. Writes to a temporary file and compiles
4. The user is responsible for the full testbench content
5. Top module must be named `tb`

---

## 12. Validation Rules

### Hard errors (stop execution)
- `project_config.yaml` not found
- `tile_index.csv` or `records.csv` not found
- `tiles/` not found
- `tile_config.yaml` not found
- `src/rtl/` empty or no `.v` files
- `tb_tile.v` not found in `src/tb/` when simulation will run (semicolab mode)
- `id_prefix` empty in `project_config.yaml`
- `top_module` empty in `tile_config.yaml`
- No `.v` file whose stem matches `top_module`
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
| `notes.md` | Run notes |
| `summary.md` | Tabular results summary |
| `README.md` | Tile documentation (regenerated on every run) |

---

## 14. Tests

Standalone suite at `tests/runner.py`. Does not require pytest.

```bash
python -m veriflow.tests.runner
```

26 integration tests covering:
- Tile ID generation and parsing
- Run ID generation
- init, create-tile, run, bump-version, bump-revision commands
- CSV validation (header, empty file)
- Flat copy with collision resolution
- Validation errors
- Manifest serialization
