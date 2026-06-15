# VeriFlow

VeriFlow is a lightweight RTL verification and documentation framework for multi-project ASIC
chip design. It automates three verification stages — interface/connectivity checking, simulation,
and synthesis — using open-source EDA tools (Icarus Verilog and Yosys), and generates structured
run records for every execution.

No license server, no proprietary tools, no cloud account required. Install the EDA tools,
run `pip install veriflow`, and the `veriflow` command is available in the terminal.

---

## Two operating modes

| Mode | Entry point | Configuration | Use case |
|---|---|---|---|
| **Database Mode** | `veriflow db ...` | `project_config.yaml` + per-tile `tile_config.yaml` | Tile database with indexed run history, version tracking, and generated documentation |
| **Project Mode** | `veriflow project run` | Single `veriflow.yaml` | Verify a local RTL project directory; no database needed |

Both modes run the same three-stage verification pipeline in order:

1. **Connectivity check** — verifies that the RTL module exposes the declared port contract
   (only when an interface profile is configured; generic projects skip this stage).
2. **Simulation** — compiles RTL and self-contained testbench together, runs with `vvp`,
   captures VCD waveforms.
3. **Synthesis** — validates RTL with Yosys, reports cell count, detects inferred latches.

---

## Interface profiles

VeriFlow uses **interface profiles** to define named port contracts. The built-in profile is
`semicolab` (nine-port structural contract for the Semicolab harness). Projects with no
interface configured skip the connectivity check entirely — the profile selection is explicit,
not a global mode.

The `veriflow wrap` namespace generates interface-adapting wrappers: given generic RTL and a
target interface profile, it produces a Verilog wrapper and verifies it with the connectivity
check.

---

## Where to go next

| Section | What you will find |
|---|---|
| [Installation](INSTALL.md) | Install Icarus Verilog and Yosys on Linux, macOS, or Windows |
| [Database Mode](MANUAL.md) | Step-by-step walkthrough of the full Database Mode workflow |
| [Project Mode](PROJECT_CONFIG.md) | `veriflow.yaml` schema and Project Mode reference |
| [Wrap](user-guide/wrap.md) | Generate interface-adapting wrappers with `veriflow wrap` |
| [Doctor](user-guide/doctor.md) | Check EDA tool availability with `veriflow doctor` |
| [Quick Reference](QUICKREF.md) | Command cheat sheet for daily use |
| [All Commands](reference/commands.md) | Master table of all namespaces and subcommands |
| [Architecture](ARCHITECTURE.md) | Internal module reference for contributors |
| [TileBench](TILEBENCH.md) | Optional Docker companion environment |
| [Changelog](CHANGELOG.md) | Release history and what changed |
