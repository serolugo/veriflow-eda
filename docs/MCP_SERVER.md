# VeriFlow + MCP (Model Context Protocol)

This page is for anyone who hasn't used MCP before. If you just want the
one-line setup, jump to [Quick setup](#quick-setup).

## What is MCP, and why would I want this?

MCP is a small protocol that lets an AI assistant (Claude Code, Claude
Desktop, and others) call real tools on your machine instead of only
reading and writing text. Without it, if you ask an assistant to "check
whether tile 0003 passes verification," it has to shell out to
`veriflow db show-run` and parse the text output itself, hoping it gets
the flags right.

With VeriFlow's MCP server running, the assistant instead has direct,
structured access to VeriFlow: it can run a verification pipeline, list
tiles, read a project's config schema, or scaffold a wrapper — as a
proper function call with a typed result, not a guess at a shell
command. It's the difference between describing your kitchen to someone
over the phone and letting them actually open the fridge.

You still stay in control: the assistant only has access to the specific
tools listed below (running verification, reading results, listing
profiles, etc.) — nothing beyond what VeriFlow itself already exposes.

## Quick setup

```bash
pip install veriflow-eda[mcp]
veriflow mcp install --client claude-code
```

That's it — restart Claude Code (or start a new session) and it will have
VeriFlow's tools available automatically.

Using Claude Desktop instead of Claude Code?

```bash
veriflow mcp install --client claude-desktop
```

This edits Claude Desktop's config file directly (creating it if it
doesn't exist yet), adding a `veriflow` entry to `mcpServers` without
touching anything else already configured there. Restart Claude Desktop
afterward.

Don't have the `claude` CLI installed, or want to see exactly what
`--client claude-code` does before running it? It prints the equivalent
command instead of failing silently:

```bash
claude mcp add veriflow -- veriflow mcp serve
```

## What `veriflow mcp serve` actually is

`veriflow mcp install` doesn't start a server itself — it registers
`veriflow mcp serve` as the command your MCP client should launch
whenever it needs VeriFlow. You never run `veriflow mcp serve` by hand;
the client (Claude Code/Desktop) starts and stops it automatically, once
per session, and talks to it over stdio.

## Available tools

| Tool | What it does |
|---|---|
| `veriflow_doctor` | Check which EDA tools/PDKs are installed and available |
| `veriflow_project_run` | Run Project Mode verification end-to-end for a `veriflow.yaml` |
| `veriflow_run_tile` | Run Database Mode verification for one tile |
| `veriflow_wrap_init` | Scaffold a wrapper config from an RTL file + interface profile |
| `veriflow_wrap_generate` | Generate a wrapper module from a wrapper config |
| `veriflow_project_import` | Import a passing Project Mode run into a database as a new tile |
| `veriflow_import_repo` | Clone a repo, precheck it, and import it as a new tile |
| `veriflow_apply_spec` | Apply a `shuttle_spec.yaml` onto a project's `veriflow.yaml` |
| `veriflow_generate_readme` | Render a submission README.md from the latest passing run |
| `veriflow_list_interface_profiles` | List registered interface profiles and their ports |
| `veriflow_list_technology_profiles` | List registered technologies and their PDK status |
| `veriflow_list_pdks` | List PDK install status with install hints |
| `veriflow_db_init` | Initialize a new VeriFlow database |
| `veriflow_create_tile` | Create a new tile entry in a database |
| `veriflow_db_list_tiles` | List all tiles in a database |
| `veriflow_db_list_runs` | List all runs for one tile |
| `veriflow_db_get_run` | Read one tile run's persisted result |
| `veriflow_get_project_run_result` | Read one Project Mode run's persisted result |
| `veriflow_project_init` | Scaffold a new veriflow.yaml, optionally setting `top_module` |
| `veriflow_project_set` | Modify a single field in veriflow.yaml (interface, technology, pipeline, stage-backend, ...) |
| `veriflow_db_set` | Modify a database-wide field in `project_config.yaml` |
| `veriflow_db_tile_set` | Modify a field in one tile's `tile_config.yaml` |

Every tool returns a plain, structured result — a `"status": "FAIL"`
result from `veriflow_run_tile` means the tile genuinely didn't pass
verification (real data to report back), not that something went wrong
with the tool call itself. A configuration problem (bad path, unknown
profile name, etc.) comes back as `{"status": "ERROR", "error": {...}}`
instead of a raw crash.

### Example: configure, then verify

The `veriflow_*_set` tools mean an agent doesn't need the user to hand-edit
YAML before it can act. If the user says "change the interface to
semicolab and verify", the agent can do both steps itself:

```
veriflow_project_set(config_path, "interface", "semicolab")
veriflow_project_run(config_path)
```

Or, to point one specific stage at a non-default backend without touching
the rest of the pipeline (e.g. "run simulation on xsim"):

```
veriflow_project_set(config_path, "stage-backend", "simulation:xsim")
veriflow_project_run(config_path)
```

Alongside the tools, the server also exposes VeriFlow's own docs
(manual, quick reference, config schema, install guide, custom backends,
wrap guide, doctor guide) as MCP resources, so the assistant can read
the actual documentation on demand instead of guessing.

## Not using MCP? `veriflow context`

If you'd rather not set up MCP at all — e.g. you're pasting into a web
chat that doesn't support it — `veriflow context` prints a consolidated,
plain-text summary of VeriFlow (commands, config schemas, `results.json`
shape, how to define a custom interface/technology, an end-to-end
example) that you can paste directly into any conversation:

```bash
veriflow context > contexto.txt
```

This gives the assistant useful background even without any tool access
— it just won't be able to actually run anything for you.
