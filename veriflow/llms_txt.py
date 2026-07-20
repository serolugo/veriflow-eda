"""
veriflow.llms_txt — Consolidated plain-text context for pasting into any
chat/agent that doesn't have MCP set up (`veriflow context`, see
commands/context.py).

The command-namespace listing and the `set` commands' available keys are
walked directly from cli.py's own argparse parser (`_command_reference()`/
`_set_command_keys()` below) rather than duplicated by hand, so they can't
drift out of sync with the real CLI as commands are added/renamed. The
config schemas, results.json shape, and end-to-end example are condensed,
hand-maintained summaries of docs/PROJECT_CONFIG.md and docs/MANUAL.md --
keep them in sync with those files when either changes materially.
"""

from __future__ import annotations

import argparse


def _direct_subcommands(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    """[(name, help)] for *parser*'s direct subcommands, declaration order.

    Reads argparse's own internal bookkeeping (`_subparsers`/
    `_choices_actions`) -- there's no public API for "what subcommands does
    this parser have, with their help text", short of re-parsing --help
    output. Used only to generate documentation text, never to affect
    parsing behavior, so the fragility is an acceptable trade for staying
    in sync with the real CLI automatically.
    """
    if parser._subparsers is None:
        return []
    for action in parser._subparsers._group_actions:
        if isinstance(action, argparse._SubParsersAction):
            return [(pa.dest, pa.help or "") for pa in action._choices_actions]
    return []


def _subparser_for(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser | None:
    if parser._subparsers is None:
        return None
    for action in parser._subparsers._group_actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices.get(name)
    return None


def _command_reference_section() -> str:
    from veriflow.cli import build_parser

    root = build_parser()
    lines = ["## Command reference", ""]
    for name, help_text in _direct_subcommands(root):
        namespace_parser = _subparser_for(root, name)
        children = _direct_subcommands(namespace_parser) if namespace_parser else []
        if not children:
            lines.append(f"- `veriflow {name}` -- {help_text}")
            continue
        lines.append(f"- `veriflow {name}` -- {help_text}")
        for child_name, child_help in children:
            # "db tile" has its own nested "set" subcommand.
            grandchild_parser = _subparser_for(namespace_parser, child_name)
            grandchildren = _direct_subcommands(grandchild_parser) if grandchild_parser else []
            if grandchildren:
                lines.append(f"  - `veriflow {name} {child_name}` -- {child_help}")
                for gc_name, gc_help in grandchildren:
                    lines.append(f"    - `veriflow {name} {child_name} {gc_name}` -- {gc_help}")
            else:
                lines.append(f"  - `veriflow {name} {child_name}` -- {child_help}")
    return "\n".join(lines)


def _set_command_keys() -> str:
    """Extract the "key" argument's help text (a pipe-separated list of
    valid keys) for the three `set` commands directly from the parser,
    rather than hand-copying it -- see this module's docstring."""
    from veriflow.cli import build_parser

    root = build_parser()
    project = _subparser_for(root, "project")
    db = _subparser_for(root, "db")
    db_tile = _subparser_for(db, "tile") if db else None

    entries = [
        ("veriflow project set <key> <value>", _subparser_for(project, "set") if project else None),
        ("veriflow db set --db <path> <key> <value>", _subparser_for(db, "set") if db else None),
        ("veriflow db tile set --db <path> --tile <n> <key> <value>", _subparser_for(db_tile, "set") if db_tile else None),
    ]

    lines = ["## `set` commands", ""]
    for label, subparser in entries:
        if subparser is None:
            continue
        key_help = ""
        for action in subparser._actions:
            if action.dest == "key":
                key_help = action.help or ""
        lines.append(f"- `{label}`")
        lines.append(f"  Available keys: {key_help}")
    return "\n".join(lines)


_HEADER = """\
# VeriFlow -- LLM context

VeriFlow is a Pre-Silicon Multiproject ASIC Validation Framework: it runs
connectivity checks, simulation, and synthesis against RTL, either as a
single standalone project (Project Mode) or as many tiles tracked in a
shared database for a multi-project shuttle (Database Mode).

Two operating modes, two config files:
- Project Mode: one `veriflow.yaml` describing a single RTL project.
  Commands: `veriflow project ...`.
- Database Mode: a database directory with `project_config.yaml`
  (database-wide defaults) and one `tile_config.yaml` per tile (per-tile
  overrides). Commands: `veriflow db ...`.

Every run (either mode) writes a `results.json` with `status`: `PASS`
(every configured stage actually ran and passed), `PARTIAL` (every stage
that ran passed, but at least one configured stage type didn't run at
all -- e.g. a generic project with no interface/testbench, or an
explicit `--skip-*` flag), or `FAIL` (something that ran did not pass).
A `FAIL`/`PARTIAL` result is normal, valid data describing a
verification outcome, not an error condition.

If you have MCP tools available (prefixed `veriflow_*`, e.g.
`veriflow_project_run`, `veriflow_db_set`), prefer those over shelling
out to the CLI commands below -- they're the same operations as real,
typed tool calls with structured results instead of text to parse. This
context exists for the case where no MCP tools are available. See
docs/MCP_SERVER.md for the full tool list and setup.
"""

_CONFIG_SCHEMA = """\
## `veriflow.yaml` (Project Mode) -- main fields

```yaml
design:                       # required
  top_module: my_module        # required
  rtl_sources: [rtl/my_module.v]  # required, non-empty
  tb_sources: [tb/tb_my_module.v] # optional -- omit to skip simulation

interface:                    # optional -- omit for a generic project
  name: semicolab               # registered profile, or your own via `definition:`
  definition: ./interfaces/custom_if.v   # optional: local path or http(s) URL

execution:                    # optional -- Project Mode only, see below
  connectivity_backend: icarus
  simulation_backend: icarus    # or "xsim" (requires Vivado)
  synthesis_backend: yosys

technology:                   # optional -- default "generic"
  name: sky130                  # generic | sky130 | gf180 | ihp130 | custom
  require_pdk: false             # true: hard-fail instead of falling back to generic synthesis
  definition: ./technologies/custom.yaml  # optional, external technology.yaml

pipeline:                     # optional -- which stages run, in order
  stages:
    - type: connectivity
    - type: simulation
      backend: icarus            # optional per-stage override
    - type: synthesis

simulation:
  tb_top: tb                    # required whenever tb_sources is non-empty

output:
  runs_dir: runs                 # default "runs"
```

Only `design` is required; every other section may be omitted for its
documented default. Full reference: docs/PROJECT_CONFIG.md.

## `project_config.yaml` (Database Mode, database-wide) -- main fields

```yaml
id_prefix: "MST130-01"        # required -- prefix for generated tile IDs
project_name: "My Chip"
repo: "https://github.com/user/repo"
description: |
  Chip project description.
interface_name: "semicolab"    # or null for a generic database
interface_definition: ./interfaces/custom_if.v   # optional
id_format: "{prefix}-{date}{tile_number}{version}{revision}"  # optional, default shown
shuttle_name: ""                # optional, informative only
technology:
  name: sky130
  require_pdk: false
technology_definition: ./technologies/custom.yaml   # optional
pipeline:                       # optional, database-wide default stage list
  stages:
    - type: connectivity
    - type: simulation
    - type: synthesis
```

NOTE: `execution:` is Project Mode-only syntax -- it does NOT exist in
Database Mode. To pick a non-default backend (e.g. xsim) in Database
Mode, set it per-stage: `pipeline.stages[].backend: xsim`. An unrecognized
top-level key here produces a warning (not silently ignored), surfaced in
`results.json`'s `"warnings"` array.

## `tile_config.yaml` (Database Mode, per-tile) -- main fields

```yaml
tile_name: "Adder Tile"
tile_author: "Jane Doe"
top_module: "adder_tile"        # must match the .v filename in src/rtl/
tb_top_module: "tb"              # module declared in the testbench, default "tb"
description: |
  32-bit adder tile.
ports: |
  data_reg_a, data_reg_b: operands
usage_guide: |
  Connect operands, read result from data_reg_c.
run_author: "Jane Doe"
objective: "Initial verification"
tags: "initial"
main_change: |
  Initial implementation.
notes: |
  No notes.
pipeline:                       # optional -- completely overrides project_config.yaml's pipeline
  stages:
    - type: connectivity
    - type: synthesis
technology:
  require_pdk: true              # only require_pdk can be overridden here, not name
```

Full reference: docs/MANUAL.md sections 4 and 5.
"""

_RESULTS_JSON_SCHEMA = """\
## `results.json` schema

### Database Mode (`schema_version "1.2"`)

Written to `tiles/<tile_id>/runs/run-NNN/results.json` after every `db run`.

| Field | Description |
|---|---|
| `schema_version` | `"1.2"` |
| `tile_id` | Full tile identifier |
| `run_id` | `run-NNN` |
| `date` | ISO 8601 date |
| `status` | `PASS` \\| `PARTIAL` \\| `FAIL` |
| `interface_name` | Interface profile name, or `null` |
| `stages` | Per-stage results: `connectivity`, `simulation`, `synthesis` -- each has `tool`, `status`, `logs`; `synthesis` additionally has `technology`/`technology_version` when PDK-mapped |
| `sources` | Relative paths to RTL/TB files used |
| `artifacts` | Relative paths to all generated output files |
| `error` | `null` on success, else an error object |

### Project Mode (`schema_version "1.0"`)

Written to `<runs_dir>/run-NNN/results.json` after every `project run`.

| Field | Description |
|---|---|
| `schema_version` | `"1.0"` |
| `status` | `PASS` \\| `PARTIAL` \\| `FAIL` |
| `command` | Always `"project run"` |
| `run_dir` | Path to this run directory |
| `interface_name` | Interface profile name, or `null` |
| `top_module` | RTL top module name |
| `rtl_sources` / `tb_sources` | Relative paths used |
| `technology` | Technology target name |
| `stages` | Per-stage results; a stage type never configured (or explicitly `--skip-*`'d) reports `"status": "SKIPPED"`; one that never got a turn because an earlier stage FAILed reports `"NOT_RUN"` |
| `rtl_hash` | `{filename: sha256}` snapshot taken at the start of the run, before any stage executes |
| `veriflow_version` | VeriFlow version that produced this run |
| `timestamp` | ISO 8601 UTC timestamp |

Full field-by-field reference with examples: docs/MANUAL.md sections 13.4 and 14.4.
"""

_CUSTOM_INTERFACE = """\
## Defining a custom interface profile

Write a Verilog stub with just the port list -- no body needed:

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

Reference it from `veriflow.yaml`:

```yaml
interface:
  name: tinytapeout
  definition: ./interfaces/tinytapeout_if.v   # relative to veriflow.yaml; local path or http(s) URL
```

Or, in Database Mode's `project_config.yaml`:

```yaml
interface_name: tinytapeout
interface_definition: ./interfaces/tinytapeout_if.v
```

The registered profile's name is the module name parsed from the file
(not `name:`) -- VeriFlow warns (doesn't fail) if they differ. `veriflow
project run` / `veriflow db run` registers the profile and runs the
connectivity check against it automatically.
"""

_CUSTOM_TECHNOLOGY = """\
## Defining a custom technology

Write a `technology.yaml`-shaped file:

```yaml
# technologies/my_process.yaml
name: my_process             # must match how you reference it below
description: "Example custom PDK target"
synthesis_backend: yosys     # informational; synthesis always uses yosys today
liberty: ./libs/my_process_tt.lib   # path to a .lib file, or null
synth_extra: []              # optional extra yosys script lines
```

Reference it from `veriflow.yaml` (or `project_config.yaml`'s `technology:` section):

```yaml
technology:
  name: my_process
  definition: ./technologies/my_process.yaml   # relative to veriflow.yaml
  require_pdk: true            # optional: hard-fail instead of falling back to generic synthesis
```

The registered profile's name is the `name:` field inside the definition
file (not the `name:` in the `technology:` section) -- VeriFlow warns
(doesn't fail) if they differ.
"""

_EXAMPLE = """\
## End-to-end example

```bash
# 1. Scaffold a new Project Mode config
veriflow project init
# edit veriflow.yaml: set design.top_module and design.rtl_sources

# 2. Configure it without hand-editing YAML (comments/formatting preserved)
veriflow project set interface semicolab
veriflow project set technology sky130

# 3. Run verification
veriflow project run
# -> runs/run-001/results.json, status: PASS, PARTIAL, or FAIL

# 4. Promote a passing run into a shared database as a new tile
veriflow db init --db ./database
veriflow db set --db ./database interface semicolab
veriflow project import --db ./database
# -> creates database/tiles/<tile_id>/ with the imported RTL + verification record

# From then on, re-run and inspect that tile directly:
veriflow db run --db ./database --tile 0001
veriflow db list-runs --db ./database --tile 0001
veriflow db show-run --db ./database --tile 0001 --run run-001
```
"""


def generate_llms_txt() -> str:
    """Build the full consolidated context text (see this module's docstring)."""
    sections = [
        _HEADER,
        _command_reference_section(),
        _CONFIG_SCHEMA,
        _RESULTS_JSON_SCHEMA,
        _CUSTOM_INTERFACE,
        _CUSTOM_TECHNOLOGY,
        _set_command_keys(),
        _EXAMPLE,
    ]
    return "\n\n".join(section.rstrip("\n") for section in sections) + "\n"
