# Command Reference

All VeriFlow commands follow the pattern `veriflow [global flags] <namespace> <subcommand> [flags]`.

The four top-level namespaces are listed below. For flag-level detail, follow the link in each
row to the page where that command is fully documented.

---

## `db` — Database Mode

Full documentation: [User Guide → Database Mode](../MANUAL.md)

| Subcommand | Description |
|---|---|
| `db init` | Create a new tile database directory with a `project_config.yaml` scaffold |
| `db create-tile` | Add a new tile to the database and scaffold its source files |
| `db run` | Run the verification pipeline (connectivity, simulation, synthesis) for a tile |
| `db waves` | Open the waveform file from a completed run |
| `db bump-version` | Increment the version field of a tile ID |
| `db bump-revision` | Increment the revision field of a tile ID (resets version to 01) |
| `db list-tiles` | List all tiles in the database |
| `db list-runs` | List all runs for a specific tile |
| `db show-run` | Show the details of a specific run |

---

## `project` — Project Mode

Full documentation: [User Guide → Project Mode](../PROJECT_CONFIG.md)

| Subcommand | Description |
|---|---|
| `project run` | Run the verification pipeline for a project described by `veriflow.yaml` |

---

## `wrap` — Interface Wrapper Generator

Full documentation: [User Guide → Wrap](../user-guide/wrap.md)

| Subcommand | Description |
|---|---|
| `wrap init` | Read RTL source files and scaffold a `wrapper_config.yaml` with the port mapping |
| `wrap generate` | Read a completed `wrapper_config.yaml`, validate it, and generate the wrapper Verilog |
| `wrap wizard` | Interactive session that runs init and generate in one guided flow |

---

## `doctor` — Tool Availability Check

Full documentation: [User Guide → Doctor](../user-guide/doctor.md)

| Command | Description |
|---|---|
| `doctor` | Check that all required EDA tools (iverilog, vvp, yosys) are installed and in PATH |

`doctor` has no subcommands. Run it as `veriflow doctor` or `veriflow doctor --json`.
