# Command Reference

All VeriFlow commands follow the pattern `veriflow [global flags] <namespace> <subcommand> [flags]`.

The eight top-level namespaces are listed below. For flag-level detail, follow the link in each
row to the page where that command is fully documented.

---

## `project` — Project Mode

Full documentation: [User Guide → Project Mode](../PROJECT_CONFIG.md)

| Subcommand | Description |
|---|---|
| `project run` | Run the verification pipeline (connectivity, simulation, synthesis) for a project described by `veriflow.yaml` |
| `project init` | Generate a commented `veriflow.yaml` scaffold |
| `project import` | Import a verified Project Mode run into a Database Mode database as a new tile |
| `project set` | Modify a single field in `veriflow.yaml` (comments/formatting preserved) — interface, technology, pipeline, `stage-backend`, `technology-strict`, and more |
| `project generate-readme` | Render a submission `README.md` from the latest passing run |
| `project apply-spec` | Apply a `shuttle_spec.yaml`'s fields onto `veriflow.yaml` |

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
| `db set` | Modify a database-wide field in `project_config.yaml` (comments/formatting preserved) |
| `db import-repo` | Clone a git repo, run its `project run` as a precheck, and import the result as a new tile |
| `db tile set` | Modify a field in one tile's `tile_config.yaml` (comments/formatting preserved) |

---

## `doctor` — Tool & PDK Availability Check

Full documentation: [User Guide → Doctor](../user-guide/doctor.md)

| Command | Description |
|---|---|
| `doctor` | Check EDA tool availability (connectivity/simulation/synthesis backends) and PDK install status for every registered technology |

`doctor` has no subcommands. Run it as `veriflow doctor` or `veriflow doctor --json`.

---

## `interface` — Cached URL-Sourced Interface Definitions

Full documentation: [User Guide → Interface Profiles](../user-guide/interface.md)

| Subcommand | Description |
|---|---|
| `interface update` | Re-download a URL-sourced interface definition, overwriting the cache |
| `interface list-cached` | List all cached URL-sourced interface definitions (profile name, source URL, download date) |

These manage the permanent local cache used when `interface.definition`/`interface_definition` is
an `http(s)://` URL rather than a local `.v` file — see the linked guide for the full mechanism.

---

## `pdk` — PDK Management

Full documentation: [User Guide → PDK Management](../user-guide/pdk.md)

| Subcommand | Description |
|---|---|
| `pdk list` | List all technologies and their PDK install status |
| `pdk install` | Install a technology's PDK (`sky130`, `gf180` via volare; `ihp130` via git) |
| `pdk update` | Update an installed PDK to the latest (or a specific pinned) version |
| `pdk status` | Show detailed PDK install status, including resolved liberty paths |
| `pdk path` | Print an installed PDK's root directory path (plain output, for scripting) |
| `pdk versions` | List remote versions available for a PDK |
| `pdk remove` | Remove an installed PDK (`--dry-run` to preview without deleting) |

---

## `wrap` — Interface Wrapper Generator

Full documentation: [User Guide → Wrap](../user-guide/wrap.md)

| Subcommand | Description |
|---|---|
| `wrap init` | Read RTL source files and scaffold a `wrapper_config.yaml` with the port mapping |
| `wrap generate` | Read a completed `wrapper_config.yaml`, validate it, and generate the wrapper Verilog |
| `wrap wizard` | Interactive session that runs init and generate in one guided flow |

---

## `context` — LLM Context Without MCP

Full documentation: [Agents & Automation → MCP Server](../MCP_SERVER.md#not-using-mcp-veriflow-context)

| Command | Description |
|---|---|
| `context` | Print a consolidated, plain-text summary of VeriFlow (commands, config schemas, `results.json` shape, an end-to-end example) for pasting into a chat/agent that doesn't have MCP set up |

`context` has no subcommands. Run it as `veriflow context`, typically redirected to a file:
`veriflow context > context.txt`.

---

## `mcp` — Model Context Protocol Server

Full documentation: [Agents & Automation → MCP Server](../MCP_SERVER.md)

| Subcommand | Description |
|---|---|
| `mcp serve` | Start the MCP server over stdio (blocking) — launched automatically by an MCP client, not run by hand |
| `mcp install` | Register VeriFlow's MCP server with a client (`--client claude-code` or `--client claude-desktop`) |
