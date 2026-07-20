# VeriFlow

VeriFlow is an RTL verification and documentation framework for multi-project ASIC chip design.
It automates three verification stages — interface/connectivity checking, simulation, and
synthesis — using open-source EDA tools (Icarus Verilog and Yosys, with Vivado's `xsim` supported
as a configurable alternative), maps designs onto real PDKs (`sky130`, `gf180`, `ihp130`) with no
manual `PDK_ROOT` setup, and generates structured run records for every execution.

No license server, no proprietary tools, no cloud account required. Install the EDA tools,
run `pip install veriflow-eda`, and the `veriflow` command is available in the terminal.

Beyond the core pipeline, VeriFlow also handles the parts of a multi-project shuttle workflow that
usually stay manual: importing a contributor's own repo straight into a shared tile database
(`db import-repo`), generating a submission `README.md` from a passing run, and exposing itself as
an [MCP server](MCP_SERVER.md) so an AI assistant can run verification, read results, and edit
config files as real tool calls instead of shelling out and parsing text.

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

## Interface profiles and technologies

VeriFlow uses **interface profiles** to define named port contracts. The built-in profile is
`semicolab` (nine-port structural contract for the Semicolab harness), but a project can also
point at its own profile — a local `.v` stub or an `http(s)://` URL, cached permanently after the
first fetch. Projects with no interface configured skip the connectivity check entirely — the
profile selection is explicit, not a global mode.

The same pattern applies to synthesis targets: built-in technologies (`sky130`, `gf180`, `ihp130`,
`generic`) or an external `technology.yaml`, each with its own PDK managed by `veriflow pdk`.

The `veriflow wrap` namespace generates interface-adapting wrappers: given generic RTL and a
target interface profile, it produces a Verilog wrapper and verifies it with the connectivity
check.

---

## Where to go next

| Section | What you will find |
|---|---|
| [Installation](INSTALL.md) | Install Icarus Verilog and Yosys (and optionally `xsim`/PDKs) on Linux, macOS, or Windows |
| [Project Mode](PROJECT_CONFIG.md) | `veriflow.yaml` schema and Project Mode reference |
| [Database Mode](MANUAL.md) | Step-by-step walkthrough of the full Database Mode workflow |
| [Wrap](user-guide/wrap.md) | Generate interface-adapting wrappers with `veriflow wrap` |
| [Doctor](user-guide/doctor.md) | Check EDA tool and PDK availability with `veriflow doctor` |
| [PDK Management](user-guide/pdk.md) | Install/update/inspect `sky130`/`gf180`/`ihp130` |
| [Interface Profiles](user-guide/interface.md) | Local and URL-sourced port contracts |
| [MCP Server](MCP_SERVER.md) | Let an AI assistant call VeriFlow directly, or paste `veriflow context` into any chat |
| [Custom Backends](CUSTOM_BACKENDS.md) | Configure `xsim`/Vivado per stage, or wire up your own backend |
| [Quick Reference](QUICKREF.md) | Command cheat sheet for daily use |
| [All Commands](reference/commands.md) | Master table of all eight namespaces and their subcommands |
| [System Specification](SPECS.md) | Formal schema and error-code reference |
| [Architecture](ARCHITECTURE.md) | Internal module reference for contributors |
| [Changelog](CHANGELOG.md) | Release history and what changed |
