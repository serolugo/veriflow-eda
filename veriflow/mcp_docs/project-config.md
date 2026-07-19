# VeriFlow — Project Mode Configuration (`veriflow.yaml`)

Project Mode runs a verification flow against a local project directory described by a single
`veriflow.yaml` file. It does not require a database — Database Mode (`veriflow db ...`) uses a
separate database workflow and `project_config.yaml`, which is **not** the file documented here.

This document is the reference for the `veriflow.yaml` schema, intended for users writing configs
by hand and for frontends (such as TileWizard) that generate them. Parsing is implemented in
`veriflow/workflows/project_config.py` (`ProjectWorkflowConfig`).

---

## Quick start

Generate a commented scaffold, then edit it to match your project:

```bash
# Generate veriflow.yaml with guided comments
veriflow project init

# Open veriflow.yaml and fill in at minimum:
#   design.top_module: "your_module_name"
#   design.rtl_sources:
#     - path/to/your_module.v

# Then run the pipeline
veriflow project run
```

`project init` writes a `veriflow.yaml` in the current directory (use `--config <path>` to
choose a different location, `--force` to overwrite an existing file).

### `VERIFLOW_CONFIG` — default config path

Every Project Mode command that takes `--config` (`run`, `set`, `generate-readme`, `import`,
`apply-spec` — **not** `init`, which is scaffolding a new file rather than reading one) resolves
its default in this priority order:

1. An explicit `--config PATH` on the command line always wins.
2. Otherwise, the `VERIFLOW_CONFIG` environment variable, if set.
3. Otherwise, the literal `veriflow.yaml`.

This is useful when working with a config file that isn't named `veriflow.yaml` (e.g. a
shuttle-provided config committed under a different name) without having to pass `--config` on
every invocation:

```bash
export VERIFLOW_CONFIG=shuttle_a.yaml
veriflow project run          # reads shuttle_a.yaml
veriflow project set interface semicolab   # edits shuttle_a.yaml
veriflow project run --config other.yaml   # explicit --config still overrides the env var
```

The generated file contains every section as a comment so you can uncomment and fill in only
what you need. Only `design.top_module` and `design.rtl_sources` are required before
`veriflow project run` will accept the config.

Once the file is filled in, run the pipeline:

```bash
# Run with an explicit config path
veriflow project run --config veriflow.yaml

# Or rely on the default (veriflow.yaml in the current directory)
veriflow project run
```

The pipeline executes connectivity check (only if an `interface` is configured), simulation
(only if `tb_sources` are provided), then synthesis. Exit code is `0` when the overall status
is `PASS`, non-zero otherwise.

---

## Canonical example

```yaml
design:
  top_module: shift_mux
  rtl_sources:
    - rtl/shift_mux.v
  tb_sources:
    - tb/tb_shift_mux.v

interface:
  name: semicolab

execution:
  connectivity_backend: icarus
  simulation_backend: icarus
  synthesis_backend: yosys

technology:
  name: generic

simulation:
  tb_top: tb

output:
  runs_dir: runs
```

Only `design` is required. Every other section may be omitted (or set to `null`) to get the
default behavior described below.

---

## Sections

### `design` (required)

| Key | Required | Description |
|---|---|---|
| `top_module` | yes | Name of the RTL top module. |
| `rtl_sources` | yes (non-empty) | List of RTL source files. |
| `tb_sources` | no | List of testbench source files. Only needed if you want simulation. |

All source paths are resolved **relative to the directory containing the config file**, not the
current working directory. Absolute paths also work but make the project non-portable.

If `tb_sources` is omitted or empty, the simulation stage is not run; connectivity (if configured)
and synthesis still run.

### `interface` (optional)

```yaml
interface:
  name: semicolab
```

Selects a registered interface profile and enables the connectivity check stage, which verifies
that `top_module` exposes the profile's port contract.

- Omitting the section, `interface: null`, or `name: null` means a **generic project**: no
  interface contract, no connectivity check.
- `name: semicolab` enables the built-in Semicolab interface profile (the nine-port structural
  contract required by the Semicolab harness).
- Available interface names are discoverable programmatically through the registry APIs in
  `veriflow.models.interface_profile` (`list_interface_profile_names()`,
  `list_interface_profiles()`, `has_interface_profile()`).
- An unknown name fails with `VF_INTERFACE_UNKNOWN`. The only other supported key is
  `definition` (below); anything else is rejected with `VF_INTERFACE_CONFIG_INVALID`.

#### `interface.definition` — external interface profiles

```yaml
interface:
  name: tinytapeout
  definition: ./interfaces/tinytapeout_if.v
```

`definition` points at a Verilog stub (a `module <name> (...); endmodule` port-list
declaration, no body needed) that doesn't have to be one of VeriFlow's built-ins. The path is
resolved relative to the directory containing `veriflow.yaml`. VeriFlow registers the profile
from that file (ports parsed the same way `wrap init` auto-detects RTL ports) before the
connectivity stage runs.

The registered profile's name is the **module name parsed from the file**, not `name:` above —
if they differ, VeriFlow uses the parsed module name and emits a `UserWarning`
(`VF_INTERFACE_NAME_MISMATCH`) rather than failing. Registering a name that collides with an
already-registered profile (including a built-in one) overwrites it for the rest of the process,
with its own `UserWarning` (`VF_INTERFACE_PROFILE_OVERWRITTEN`).

Omitting `definition` is unchanged from before: `name` must then refer to an
already-registered (built-in) profile. See `veriflow/interfaces/semicolab/` for the on-disk
shape of a built-in profile (`interface.v` + optional `tb_template.v` + optional `meta.yaml`).

#### `interface.definition` from a URL

```yaml
interface:
  name: tinytapeout
  definition: https://raw.githubusercontent.com/example/repo/main/tinytapeout_if.v
```

`definition` also accepts an `http://`/`https://` URL, resolved through a **permanent local
cache** — same "fetch once, use from disk forever, update explicitly" philosophy as
`veriflow pdk install` (see `docs/INSTALL.md`). The first time a given URL is used, VeriFlow
downloads it to `~/.veriflow/interfaces/cache/<sha256(url)>/interface.v` (plus a
`source_url.txt` recording where it came from) and parses it exactly like a local file from
then on. Every later resolution of that same URL — in this project or any other — is a pure
cache read: **no network access at all**, even across separate `veriflow project run`
invocations. Nothing re-fetches it automatically, ever.

```bash
veriflow interface update <name>     # force re-download, overwrite the cache
veriflow interface list-cached       # show every cached URL, its profile name, and download date
```

`veriflow interface update <name>` looks up *name* (the profile name — the module name parsed
from the file, not the URL itself) against the cache, re-downloads its source URL, and
overwrites the cached copy. It only works for profiles that actually came from a URL — a
built-in profile or a local-file `definition:` has nothing to re-fetch and raises
`VF_INTERFACE_UPDATE_NOT_FOUND`.

Any URL scheme other than `http`/`https` (`file://`, `ftp://`, etc.) is rejected outright with
`VF_INTERFACE_URL_SCHEME_NOT_ALLOWED` — a definition string with no scheme prefix at all (a
plain local path) is unaffected and resolves exactly as described above.

**Security note:** VeriFlow does not validate the content of externally-fetched interface
definitions beyond parsing them as Verilog module declarations — only use URLs you trust. A
malicious or compromised URL could serve a `.v` file with a port list crafted to pass
connectivity checks it shouldn't, but VeriFlow itself only ever reads the file as a Verilog
text stub (no code execution, no other side effects) — the practical risk is a false-positive
connectivity PASS, not arbitrary code execution.

Database Mode's `project_config.yaml` supports the exact same URL resolution for its
`interface_definition:` field (the flat, non-nested equivalent of `interface.definition:` —
see `shuttle_spec.yaml` below) — same permanent cache, same `veriflow interface update`.

##### Error codes

| Code | Cause |
|---|---|
| `VF_INTERFACE_URL_SCHEME_NOT_ALLOWED` | `definition` has a scheme other than `http`/`https` |
| `VF_INTERFACE_URL_FETCH_FAILED` | network/HTTP error fetching a not-yet-cached URL (DNS failure, timeout, 404, etc.) |
| `VF_INTERFACE_UPDATE_NOT_FOUND` | `veriflow interface update <name>` — *name* has no cached URL-based definition |

### `execution` (optional)

```yaml
execution:
  connectivity_backend: icarus
  simulation_backend: icarus
  synthesis_backend: yosys
```

Selects which backend runs each stage. Omitting the section, `execution: null`, or omitting any
individual key uses the defaults from `default_execution_profile()`:

| Key | Default | Currently registered names |
|---|---|---|
| `connectivity_backend` | `icarus` | `icarus` |
| `simulation_backend` | `icarus` | `icarus`, `xsim` |
| `synthesis_backend` | `yosys` | `yosys` |

Backend names must already be registered in `veriflow.core.backends.registry`; an unknown name
fails with `VF_BACKEND_*_UNKNOWN`.

`xsim` runs simulation through Vivado's `xvlog`/`xelab`/`xsim` CLI tools instead of Icarus
Verilog — **requires Vivado installed** and on `PATH` (`veriflow doctor` reports `[FAIL]` for
all three sub-tools otherwise, same as any other missing-tool backend). Selected the same way
as any other backend:

```yaml
execution:
  simulation_backend: xsim
```

See `docs/CUSTOM_BACKENDS.md` for the full backend contract — how to add support for another
commercial simulator (Xcelium, VCS, Questa, ...) without touching VeriFlow's core, using `xsim`
itself as the worked example.

#### ⚠️ `execution:` is Project Mode syntax only — Database Mode selects backends per-stage

**This `execution:` section only exists in Project Mode's `veriflow.yaml`.** Database Mode's
`project_config.yaml` and `tile_config.yaml` have **no `execution:` section at all** — writing
one there is silently ignored (as of the fix below, it now produces a warning instead — see
"Unrecognized top-level keys" further down). Database Mode selects a backend **per pipeline
stage**, via `pipeline.stages[].backend:` (documented in the next section):

```yaml
# project_config.yaml or tile_config.yaml (Database Mode) — correct way to select xsim:
pipeline:
  stages:
    - type: connectivity
      backend: icarus
    - type: simulation
      backend: xsim
    - type: synthesis
      backend: yosys
```

```yaml
# This does NOT work in Database Mode -- Project Mode syntax, wrong file:
execution:
  simulation_backend: xsim
```

This distinction matters in practice: a real bug was traced to exactly this mistake — a
database's `project_config.yaml` had `execution: {simulation_backend: xsim}`, which was silently
dropped, so every run used the default `icarus` backend instead of the intended `xsim`, with no
error or warning at all (confirmed live: `results.json` recorded `"tool": "iverilog/vvp"`, and
the simulation log's `$finish called at ... (1ps)` format is icarus/vvp's, never Vivado's). See
`dev-docs/UNKNOWN_CONFIG_KEYS_FIX.md` for the full investigation.

### `pipeline` (optional)

```yaml
pipeline:
  stages:
    - type: connectivity
    - type: simulation
      backend: icarus     # optional per-stage override; omit to use `execution`'s default
    - type: synthesis
      backend: yosys
```

Selects exactly which stages run, and in what order. Omitting the section (or `pipeline: null`)
keeps the current default: connectivity (if `interface` is configured) → simulation (if
`tb_sources` is non-empty) → synthesis, unconditionally — i.e. **omitting `pipeline` changes
nothing** for existing configs.

| Stage type | Requires | Runs when listed |
|---|---|---|
| `connectivity` | `interface` section configured | Verifies `top_module` against the interface profile's port contract |
| `simulation` | `design.tb_sources` non-empty | Compiles + runs the testbench, captures `waves.vcd` |
| `synthesis` | — | Always runnable; the only stage with no precondition |

Rules:

- A stage type **not listed** in `pipeline.stages` never runs at all — it shows up as `SKIPPED` in
  the output and in `results.json`, exactly as if you had omitted `interface`/`tb_sources` (or
  passed the matching `--skip-*` flag in Database Mode).
- An unrecognized `type` value fails fast with `VF_PIPELINE_STAGE_UNKNOWN`.
- `backend:` is optional per stage. **Project Mode** (`veriflow.yaml`): omitting it uses the
  `execution` section's default for that stage type, or the registry default if `execution` is
  also omitted. **Database Mode** (`project_config.yaml`/`tile_config.yaml`): there is no
  `execution:` section at all — omitting `backend:` here always uses the registry default
  directly. This is the *only* place Database Mode selects a non-default backend (e.g. `xsim`
  instead of `icarus`) — see the `execution:` warning above.
- Extra keys on a stage entry (for fields not implemented yet, e.g. a future `timeout:`) are
  ignored silently rather than rejected, so configs stay forward-compatible.
- Connectivity/simulation still require their underlying precondition (`interface`/`tb_sources`)
  even when explicitly listed — listing `connectivity` with no `interface` section configured
  simply means that stage is skipped, same as leaving it out of `pipeline` entirely.

#### Overriding one stage's backend without hand-editing YAML

`veriflow project set stage-backend <type>:<backend>` (and the equivalent `db set` / `db tile
set`) updates only the named stage's `backend:` field, leaving every other stage untouched — no
need to reconstruct the whole `pipeline.stages` list by hand:

```bash
veriflow project set stage-backend simulation:xsim
```

The stage type must already be part of the current pipeline (add it first via the `pipeline` key
if it's `SKIPPED` today — `VF_STAGE_NOT_IN_PIPELINE` otherwise), and the backend name must be
registered for that stage's category (`VF_SET_STAGE_BACKEND_UNKNOWN` lists the valid options
otherwise).

#### Unrecognized top-level keys (Database Mode)

`project_config.yaml` and `tile_config.yaml` (Database Mode) both warn — rather than silently
ignoring — any top-level key that isn't part of their recognized schema. This is deliberately a
warning, not an error, for forward-compatibility with fields not implemented yet: parsing
continues normally, and the warning is added to the run's `config_warnings` (surfaced in
`results.json`'s `"warnings"` array and printed via the same clean CLI output as any other
config warning — never a raw Python `UserWarning`).

`project_config.yaml`'s recognized top-level keys: `id_prefix`, `project_name`, `repo`,
`description`, `interface_name`, `interface_definition`, `id_format`, `shuttle_name`,
`technology`, `technology_definition`, `pipeline`.

`tile_config.yaml`'s recognized top-level keys: `tile_name`, `tile_author`, `top_module`,
`tb_top_module`, `description`, `ports`, `usage_guide`, `tb_description`, `run_author`,
`objective`, `tags`, `main_change`, `notes`, `pipeline`, `technology`.

An unrecognized `execution:` key specifically gets a targeted message pointing at
`pipeline.stages[].backend` (the real fix for that exact mistake); any other unrecognized key
gets a generic "ignored, see this doc" message.

Common examples:

```yaml
# Connectivity + synthesis only, no simulation
pipeline:
  stages:
    - type: connectivity
    - type: synthesis

# Synthesis-only smoke check
pipeline:
  stages:
    - type: synthesis
```

### `technology` (optional)

```yaml
technology:
  name: generic
```

Names the technology target for the run. Omitting the section, `technology: null`, or
`name: null` means `generic`.

Registered names (see `veriflow.models.technology_profile`): `generic`, `sky130`, `gf180`,
`ihp130` — each loaded from its own `veriflow/technologies/<name>.yaml` file. An unknown name
fails with `VF_TECHNOLOGY_UNKNOWN`.

Each `technology.yaml` has:

| Field | Description |
|---|---|
| `name` | Required. Must match the filename's technology (used as the registry key). |
| `description` | Free text, informational only. |
| `synthesis_backend` | Informational today; synthesis always uses `yosys` regardless of this value. |
| `liberty` | Path to a `.lib` file, or `null`. When set, `abc -liberty <path>` is appended to the yosys script right after `synth`, performing real cell-library technology mapping. |
| `synth_extra` | List of extra yosys script lines, appended after the `liberty` line (before `check`/`stat`) — e.g. `["-flatten"]`. |

None of the four built-in technologies vendor a real `liberty` file yet (`sky130`/`gf180`/`ihp130`
all ship `liberty: null` in the repo) — `liberty` is resolved automatically once the technology's
PDK is installed with `veriflow pdk install <name>` (see `docs/INSTALL.md`'s "PDK Installation"
section and `veriflow.models.pdk_manager`); until then, synthesis falls back to the generic
script and prints a `VF_TECHNOLOGY_PDK_NOT_INSTALLED` warning (included in `results.json`'s
`warnings` field) rather than failing.

#### `technology.require_pdk` — fail instead of falling back to generic synthesis

```yaml
technology:
  name: sky130
  require_pdk: true
```

Default `false` (the behavior described above: missing PDK is a warning, synthesis still runs
generically). Set `require_pdk: true` to make a missing PDK a hard failure instead —
`VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED`, raised by the synthesis stage *before* invoking
yosys at all. This stops the run entirely (no `results.json` is written for that attempt) rather
than returning a `FAIL` result — the same category as other configuration-level errors
(`VF_TECHNOLOGY_UNKNOWN`, `VF_INTERFACE_UNKNOWN`), not "the RTL failed verification." Useful when
a PASS is expected to mean "actually verified against the target PDK" (e.g. a shuttle's
`db import-repo` precheck), where a silent generic-synthesis fallback would be misleading.

Database Mode's `project_config.yaml` supports the same `technology.require_pdk` (as the
database-wide default for every tile); a tile's own `tile_config.yaml` may override it with:

```yaml
technology:
  require_pdk: false   # or true — only require_pdk can be set here, not name (database-wide)
```

Precedence: a tile's own `require_pdk` (if set) wins; otherwise the database's
`project_config.yaml` value; otherwise `false`. Set either with `veriflow project set
require-pdk true` / `veriflow db set require-pdk true` / `veriflow db tile set require-pdk true`.

Setting a real technology *and* requiring its PDK together is common enough to have a one-call
shortcut: `veriflow project set technology-strict sky130` (or the equivalent `db set`) is the
same as `set technology sky130` followed by `set require-pdk true`. Only available at the project
and database levels — a tile has no `technology.name` of its own to set (see above).

#### `technology.definition` — external technology profiles

```yaml
technology:
  name: mi_proceso
  definition: ./technologies/mi_proceso.yaml
```

The only other supported key besides `name` is `definition`; anything else is rejected with
`VF_TECHNOLOGY_CONFIG_INVALID`. `definition` points at a `technology.yaml`-shaped file (same
schema as the built-ins) that doesn't have to live under `veriflow/technologies/` — the path is
resolved relative to the directory containing `veriflow.yaml`. VeriFlow registers the profile
from that file before the synthesis stage runs. A relative `liberty:` path **inside** that file
is resolved relative to `veriflow.yaml`'s directory too (not the definition file's own directory,
and not the process's current working directory).

The registered profile's name is the `name:` field **inside the definition file**, not the
`name:` in the `technology` section — if they differ, VeriFlow uses the definition file's name
and emits a `UserWarning` (`VF_TECHNOLOGY_NAME_MISMATCH`) rather than failing, mirroring
`interface.definition`'s `VF_INTERFACE_NAME_MISMATCH` behavior. Registering a name that collides
with an already-registered technology (including a built-in one) overwrites it for the rest of
the process.

Omitting `definition` is unchanged from before: `name` must then refer to an already-registered
(built-in) technology.

### `simulation` (optional, required with `tb_sources`)

```yaml
simulation:
  tb_top: tb
```

| Key | Description |
|---|---|
| `tb_top` | Module name of the testbench top. Required (non-empty) whenever `design.tb_sources` is non-empty. |

Testbenches are **self-contained** in both modes: the files in `tb_sources` must form a complete,
compilable testbench (including the DUT instantiation). VeriFlow compiles RTL and TB files
together and selects the testbench top explicitly — there is no DUT injection or marker protocol.

### `output` (optional)

```yaml
output:
  runs_dir: runs
```

| Key | Default | Description |
|---|---|---|
| `runs_dir` | `runs` | Directory (relative to the config file) where run outputs are written. |

Each run is written to `<runs_dir>/run-NNN/` (zero-padded, auto-incremented: `run-001`,
`run-002`, …). Stage logs and artifacts land under `out/` inside the run directory, e.g.
`out/connectivity/logs/`, `out/sim/logs/`, `out/sim/waves/waves.vcd`, `out/synth/logs/`.

---

## Validation errors

The parser fails fast with stable `VeriFlowError` codes, including:

| Code | Cause |
|---|---|
| `VF_PROJECT_CONFIG_NOT_FOUND` | config file does not exist at the given path |
| `VF_PROJECT_CONFIG_YAML_ERROR` | config file exists but contains invalid YAML (parse error) |
| `VF_DESIGN_TOP_REQUIRED` | `design.top_module` missing or empty |
| `VF_DESIGN_RTL_REQUIRED` | `design.rtl_sources` missing or empty |
| `VF_INTERFACE_CONFIG_INVALID` | malformed `interface` section / unsupported keys |
| `VF_INTERFACE_NAME_REQUIRED` | `interface` section present without a usable `name` |
| `VF_INTERFACE_UNKNOWN` | `interface.name` not in the registry |
| `VF_EXECUTION_CONFIG_INVALID` | malformed `execution` section / unsupported keys |
| `VF_BACKEND_CONNECTIVITY_UNKNOWN` / `VF_BACKEND_SIMULATION_UNKNOWN` / `VF_BACKEND_SYNTHESIS_UNKNOWN` | backend name not in the registry |
| `VF_PIPELINE_CONFIG_INVALID` | `pipeline` section is not a mapping with a `stages` key |
| `VF_PIPELINE_STAGE_UNKNOWN` | a `pipeline.stages[].type` value isn't `connectivity`/`simulation`/`synthesis` |
| `VF_TECHNOLOGY_CONFIG_INVALID` | malformed `technology` section / unsupported keys |
| `VF_TECHNOLOGY_UNKNOWN` | `technology.name` not in the registry |
| `VF_SIM_TB_TOP_REQUIRED` | `tb_sources` given without `simulation.tb_top` |

Note: top-level `interface_name` is not supported — use the `interface` section.

---

## `project import`

Promotes a verified Project Mode run into a Database Mode database as a new tile:

```bash
veriflow project import --db ./database [--config veriflow.yaml] [--run run-NNN] [--force]
```

| Flag | Required | Description |
|---|---|---|
| `--db PATH` | yes | Path to the destination VeriFlow database directory. |
| `--config PATH` | no | Path to the Project Mode config to import from. Default: `veriflow.yaml`. |
| `--run run-NNN` | no | Specific run to import. Default: the highest-numbered run under `runs_dir` whose `results.json` reports `"status": "PASS"`. |
| `--force` | no | Import a generic (no-interface) project into an interface-requiring database anyway (see `VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE` below). Does **not** bypass an interface *mismatch* (`VF_IMPORT_INTERFACE_MISMATCH`), which is always rejected. |

### What it validates before importing

1. A run to import can be identified: either `--run` names one that exists and has a
   `results.json`, or (if `--run` is omitted) at least one run under `runs_dir` has
   `"status": "PASS"`.
2. The chosen run's `status` in `results.json` is `"PASS"` — a `FAIL` run is never importable,
   whether picked automatically or named explicitly via `--run`.
3. The destination database is structurally valid (same check `db run` uses —
   `project_config.yaml`, `tile_index.csv`, `records.csv`, `tiles/` must all exist).
4. **Interface compatibility**, in two parts:
   - *Mismatch*: the imported run's `interface_name` is set and differs from the database's
     `interface_name` — e.g. project declares `semicolab`, database declares (or requires) a
     different one. Always rejected (`VF_IMPORT_INTERFACE_MISMATCH`); `--force` does not
     override this.
   - *Generic into an interface-requiring database*: the imported run has **no** interface
     configured at all, but the destination database **does** require one. Rejected by default
     (`VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE`) — since interface is database-wide, not
     per-tile, the tile would otherwise get created and labeled with the database's interface
     without the RTL ever having been verified against that port contract, and its first
     `db run` would fail connectivity immediately. `--force` downgrades this to a warning and
     lets the import proceed anyway (not recommended — see below).

### What it only warns about (doesn't block the import)

- **Technology mismatch**: if the run's technology (from the synthesis stage, falling back to
  the project's configured `technology`) differs from the destination database's
  `project_config.yaml` technology, the import still proceeds — a message is added to the
  returned result's `"warnings"` list (and printed after the import completes) rather than
  raising, since the tile can simply be re-synthesized against the destination's technology on
  the next `db run`. Unlike interface, a technology mismatch doesn't silently break simulation.
- **RTL filename vs. `top_module`**: Database Mode requires a file literally named
  `<top_module>.v` under `src/rtl/`. If none of the recorded RTL sources is named that way,
  `project_import` looks for whichever file's text declares `module <top_module>` and renames
  it to `<top_module>.v` on copy, adding a warning. If no recorded source declares the module at
  all — which shouldn't happen if `project run` already passed — it raises
  `VF_IMPORT_TOP_MODULE_NOT_IN_SOURCES` instead of producing a tile `db run` can never pass.
- **Generic project into an interface-requiring database, with `--force`**: see item 4 above —
  normally a hard error, `--force` downgrades it to a `"WARNING: tile imported as generic but
  database requires '<interface>' — db run will likely fail until the RTL is verified against
  this interface."` entry in `"warnings"` instead of blocking the import.

### What it copies into the new tile

- Creates a new tile via the same `create-tile` path Database Mode uses, keyed off the
  imported run's `top_module`.
- Copies every path in `results.json`'s `rtl_sources` into `config/tile_NNNN/src/rtl/`.
- If `tb_sources` is non-empty, removes the auto-generated `tb_tile.v` placeholder and copies
  the imported testbench files into `config/tile_NNNN/src/tb/` instead (the imported
  testbench is self-contained, so the scaffold placeholder would otherwise collide on the
  `tb` module name).
- Prefills `tile_config.yaml`'s `tile_name` (from the project directory name) and
  `tb_top_module` (from the project's `simulation.tb_top`, if set).
- Copies `results.json` itself to `config/tile_NNNN/imported_run.json` — a traceability
  snapshot of the exact run that was imported (`rtl_hash`, `timestamp`, per-stage statuses).

Nothing under `runs_dir` in the Project Mode project is modified or deleted by the import —
it only reads from it.

### Error codes

| Code | Cause |
|---|---|
| `VF_IMPORT_NO_PASSING_RUN` | `--run` omitted and no run under `runs_dir` has `status: "PASS"` |
| `VF_IMPORT_RUN_NOT_FOUND` | `--run` given but that run (or its `results.json`) doesn't exist |
| `VF_IMPORT_RUN_NOT_PASSING` | `--run` given but that run's `status` isn't `"PASS"` |
| `VF_IMPORT_INTERFACE_MISMATCH` | both sides declare an interface, but they **differ** (e.g. project `semicolab`, database `other_if`) — always rejected, `--force` has no effect |
| `VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE` | the project declares **no** interface at all, but the destination database requires one — rejected unless `--force` (downgrades to a warning) |
| `VF_IMPORT_TOP_MODULE_NOT_IN_SOURCES` | no recorded RTL source declares `module <top_module>` (rename couldn't be resolved) |
| `VF_IMPORT_RTL_SOURCE_MISSING` | a recorded RTL/TB source file no longer exists on disk |
| `VF_DATABASE_CONFIG_YAML_ERROR` | the destination database's `project_config.yaml` is malformed |

---

## `shuttle_spec.yaml` / `project apply-spec`

A shuttle organizer's own config (interface/technology/pipeline requirements) is a separate
concern from a contributor's `veriflow.yaml` — it shouldn't require hand-editing every field by
name. `shuttle_spec.yaml` is a small, flat schema for exactly that; `project apply-spec` applies
its fields onto an existing `veriflow.yaml` using the same comment-preserving editor as
`project set` (not a separate/duplicated implementation).

```yaml
shuttle_name: ""          # optional, informative only -- see below
interface: null           # interface profile name, or null
interface_definition: null # optional, path to an external .v interface definition
technology: generic       # technology name
technology_definition: null # optional, path to an external technology.yaml
pipeline:
  stages:
    - type: connectivity
    - type: simulation
    - type: synthesis
```

```bash
veriflow project apply-spec shuttle_spec.yaml [--config veriflow.yaml]
```

| Field | Applied as | Notes |
|---|---|---|
| `shuttle_name` | *(not applied)* | Project Mode has no shuttle concept — `veriflow.yaml` has no field for it. Emits a `UserWarning` (`VF_SHUTTLE_NAME_NOT_APPLIED`) rather than silently dropping it. |
| `interface` | `interface.name` (via `project set interface`) | `null` clears the section, same as `project set interface null`. |
| `interface_definition` | `interface.definition` (+ `interface.name` if also given) | Written directly (bypassing `project set`'s validated `interface` key, which requires an already-registered name) — validated later at config-load time, same as hand-authoring `interface: {name: ..., definition: ...}`. |
| `technology` | `technology.name` (via `project set technology`) | Same validation as `project set technology` — an unregistered name with no `technology_definition` raises `VF_TECHNOLOGY_UNKNOWN`. |
| `technology_definition` | `technology.definition` (+ `technology.name` if also given) | Same bypass rationale as `interface_definition`. |
| `pipeline.stages` | `pipeline.stages` (via `project set pipeline`) | Comma-joined stage type list. |

Only fields present in the spec file are applied — a partial spec (e.g. just `interface:`) leaves
every other section of `veriflow.yaml` untouched. `--config` follows the same resolution as every
other Project Mode command (`--config` > `VERIFLOW_CONFIG` > `veriflow.yaml`).

### Error codes

| Code | Cause |
|---|---|
| `VF_SHUTTLE_SPEC_NOT_FOUND` | the spec file path doesn't exist |
| `VF_SHUTTLE_SPEC_YAML_ERROR` | the spec file exists but contains invalid YAML |
| `VF_TECHNOLOGY_UNKNOWN` / `VF_INTERFACE_UNKNOWN` | a plain (no `*_definition`) name isn't registered |

---

## `db import-repo`

Clones a git repository, runs its own `veriflow.yaml` through a real `project run` as a live
precheck, and — only on a passing precheck — imports it into a Database Mode database as a new
tile (`project_import`, inheriting all of its checks/warnings above).

```bash
veriflow db import-repo --db ./database --repo <url-or-local-path> \
    [--branch main] [--config veriflow.yaml] [--force]
```

| Flag | Required | Description |
|---|---|---|
| `--db PATH` | yes | Path to the destination VeriFlow database directory. |
| `--repo URL` | yes | Anything `git clone` accepts — an https/ssh URL, or a local path. |
| `--branch NAME` | no | Branch to clone. Default: `main`. |
| `--config PATH` | no | Path to `veriflow.yaml` **relative to the cloned repo's root**. Default: `veriflow.yaml`. Unrelated to the `VERIFLOW_CONFIG` env var, which is about the *local* project you're currently in, not the repo being cloned. |
| `--force` | no | Two effects, both propagated straight through to `project_import`: (1) re-import this exact repo+branch even if it was already imported into this database (creates a new, separate tile; the existing one is left untouched); (2) import a generic (no-interface) repo into an interface-requiring database anyway (`VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE` below). Neither use bypasses the precheck or an interface *mismatch* — those are always enforced regardless of `--force`. |

### Flow

1. Clone `--repo` (`--branch`, `--depth 1`) into a fresh temporary directory.
2. Look for `--config` at the clone's root — missing is `VF_IMPORT_REPO_NO_CONFIG`.
3. Run `project run` for real (this **is** the precheck, not a dry run/simulation of one).
4. If the run's status isn't `PASS`, raise `VF_IMPORT_REPO_PRECHECK_FAILED` (the full run result
   is attached to the error's details, so you can see exactly what failed).
5. On `PASS`, call `project_import` — creating the tile, applying the technology-warning and
   RTL-rename fixes described above.
6. Always remove the temporary clone directory afterward, success or failure.

### Duplicate-import guard

Before cloning anything, checks whether `--repo` + `--branch` was already imported into this
database (`imported_run.json` on every existing tile records `source_repo`/`source_branch` when
imported this way). If a match is found and `--force` isn't given, the import is rejected
(`VF_IMPORT_REPO_ALREADY_IMPORTED`) naming the existing tile. With `--force`, the import proceeds
and creates a brand-new tile — the previous one is never overwritten. This guard is independent
of the precheck: `--force` never lets a failing `project run` through; that gate
(`VF_IMPORT_REPO_PRECHECK_FAILED`) always applies regardless.

### Error codes

| Code | Cause |
|---|---|
| `VF_IMPORT_REPO_ALREADY_IMPORTED` | this exact repo+branch was already imported and `--force` wasn't given |
| `VF_IMPORT_REPO_CLONE_FAILED` | `git clone` failed (bad URL/branch, network error, etc.) |
| `VF_IMPORT_REPO_NO_CONFIG` | `--config` not found at the cloned repo's root |
| `VF_IMPORT_REPO_PRECHECK_FAILED` | `project run`'s status wasn't `PASS` |

Plus anything `project_import` itself can raise (`VF_IMPORT_INTERFACE_MISMATCH`,
`VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE`, `VF_IMPORT_TOP_MODULE_NOT_IN_SOURCES`,
`VF_IMPORT_RTL_SOURCE_MISSING`, etc.).
