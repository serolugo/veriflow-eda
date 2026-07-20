# VeriFlow — Architecture Reference

This document merges what used to be two separate, ~90%-overlapping
internal references (`ARCHITECTURE.md` and `DESIGN.md`) into one. Both
covered the same modules from slightly different angles and had drifted
out of sync with each other and with the actual codebase (see
dev-docs/DOCS_AUDIT_FINAL.md) — keeping one document current is more
sustainable than keeping two near-duplicates in sync by hand.
`docs/DESIGN.md` now redirects here.

---

## Overview: Full execution flow

```
veriflow (no args)
    └── cli.py main() → parser.print_help()

veriflow project <run|init|import|set|generate-readme|apply-spec> [flags]
    └── cli.py main()
            └── commands/run_project.py, project_init.py, import_project.py,
                set_config.py, generate_readme.py (commands/), apply_spec.py
                    └── workflows/project.py (ProjectWorkflow) for `run`
                            ├── workflows/project_config.py  (veriflow.yaml parsing)
                            ├── framework/                   (Design, Flow, RunRequest, status)
                            └── core/stages/ + core/backends/
                    └── api.py for `import`/`generate-readme`/`apply-spec` (see below)

veriflow db <command> --db ./database [flags]
    └── cli.py main()
            └── argparse dispatch
                    ├── db init                → commands/init_db.py
                    ├── db create-tile         → commands/create_tile.py
                    ├── db run                 → commands/run.py
                    │       └── workflows/database.py (DatabaseWorkflow)
                    │               ├── core/validator.py    (validate DB + tools + inputs)
                    │               ├── core/copier.py       (copy RTL/TB to run/src/)
                    │               ├── core/pipeline_builder.py (build stages, per-stage backend)
                    │               ├── core/stages/         (connectivity, simulation, synthesis)
                    │               ├── generators/          (manifest, results.json, notes, summary, README)
                    │               └── core/csv_store.py    (append records.csv row)
                    ├── db waves               → commands/waves.py
                    │       └── core/sim_runner.py   (open_surfer / launch_waves)
                    ├── db bump-version        → commands/bump_version.py
                    ├── db bump-revision       → commands/bump_revision.py
                    ├── db list-tiles/list-runs/show-run → commands/db_read.py
                    ├── db set / db tile set   → commands/set_config.py
                    └── db import-repo         → api.py (import_repo, clones + prechecks + imports)

veriflow doctor [--json]
    └── core/validator.py + models/pdk_manager.py (EDA tool + PDK availability)

veriflow interface <update|list-cached>
    └── models/interface_profile.py (URL-sourced definition cache)

veriflow pdk <list|install|update|status|path|versions|remove>
    └── models/pdk_manager.py (volare-backed sky130/gf180, git-cloned ihp130)

veriflow wrap <init|generate|wizard>
    └── commands/wrap_init.py, wrap_generate.py, wrap_wizard.py
            └── workflows/wrap.py (WrapWorkflow) + core/wrapper/

veriflow context
    └── llms_txt.py (generate_llms_txt) — plain-text LLM context, dynamically
        derived from cli.py's own argparse tree

veriflow mcp <serve|install>
    └── mcp_server.py (FastMCP, stdio transport) / commands/mcp.py (client registration)
```

Errors propagate as `VeriFlowError` (defined in `core/__init__.py`) and are caught at the CLI entry point with the error's exit code.

---

## Module reference

### `cli.py` — Entry point and routing

Parses arguments with `argparse` and dispatches to command handlers. Eight top-level namespaces: `project`, `db` (all subcommands take `--db PATH`), `doctor`, `interface`, `pdk`, `wrap`, `context`, `mcp` — confirmed by walking the real parser tree (`build_parser()`), not hand-counted. Two additional behaviors:

- **No arguments** → `parser.print_help()` (exit 0)
- **`--json` / `--non-interactive`** → global flags placed before the subcommand

All imports of command modules are deferred (inside the `if` branches) to avoid loading unused code on every invocation.

---

### `workflows/database.py` — DatabaseWorkflow

The Database Mode execution engine. `commands/run.py` delegates here; the workflow performs no Rich output or wave launching (that is the caller's responsibility).

**`DatabaseWorkflow(database_path)`** main APIs:

| Method | Description |
|---|---|
| `run_tile(tile_number, options: DatabaseRunOptions) → DatabaseRunResult` | Execute the full pipeline for one tile |
| `list_tiles() → list[DatabaseTileInfo]` | One entry per registered tile (includes `interface_name`) |
| `list_runs(tile_id=…, tile_number=…) → list[DatabaseRunInfo]` | All runs for a tile, from persisted files |
| `load_run_result(tile_id=…, tile_number=…, run_id=…) → DatabaseRunResult` | Reload a persisted `results.json` without re-running tools |

`DatabaseRunOptions` carries `skip_connectivity`, `skip_sim`, `skip_synth`, `only_connectivity`, `only_sim`, `only_synth`.

`DatabaseRunResult` carries `tile_id`, `run_id`, `run_dir`, `status`, `interface_name`, `stages` (dict of `StageResult`), `sources`, `artifacts`, and `data` (the full `results.json` dict).

**`run_tile` flow:**
1. Resolves `--only-*` flags into `skip_*` combinations
2. Validates the database; validates tools only if at least one tool stage will run
3. Reads `tile_config.yaml` and `project_config.yaml`; resolves the interface profile from `interface_name`
4. No interface profile → `skip_check = True` automatically; `--only-check` with no profile → `VF_INTERFACE_CHECK_NO_PROFILE`
5. Validates run inputs; resolves `tile_id` from `tile_index.csv`; syncs `tile_name`/`tile_author` back to the index
6. Determines the next `run_id`; builds a `RunContext` (carries `interface_name` and the skip flags)
7. Creates the run directory tree and copies RTL/TB sources (no TB sources → `skip_sim = True`)
8. Builds the pipeline via `build_default_pipeline(...)` and runs the stages; connectivity FAIL stops the pipeline and finalizes immediately
9. `_finalize_run` generates `manifest.yaml`, `notes.md`, tile `README.md`, `summary.md`, and `results.json` (schema 1.2, includes `interface_name`), refreshes `works/`, and appends the `records.csv` row (includes the `Interface` column)

**Status derivation** — both `DatabaseWorkflow` and `ProjectWorkflow` now call the same
`veriflow.framework.status.derive_run_status()` (see dev-docs/TRACEABILITY_AUDIT.md Findings
#4/#4b: the two modes used to implement this independently and had silently diverged — Project
Mode's own copy treated an all-SKIPPED run as `PASS`, a vacuous pass since nothing that ran had
actually failed because nothing ran at all):

| Condition | Status |
|---|---|
| Any stage `FAIL` | `FAIL` |
| No `FAIL`, but any stage `SKIPPED`/`NOT_RUN` (or zero stages ran at all) | `PARTIAL` |
| No `FAIL`, nothing incomplete (every stage PASS/COMPLETED) | `PASS` |

Project Mode's `results.json` additionally distinguishes `SKIPPED` (never configured, or an
explicit `--skip-*` flag) from `NOT_RUN` (was configured, but `Flow.run()` broke out on an
earlier stage's `FAIL` before reaching it) — both count identically toward `PARTIAL` above; the
distinction is for a human/tool reading the file, not a third status tier. Database Mode's
early-return-on-connectivity-FAIL path reports `SKIPPED` for the stages it never reached, not
`NOT_RUN` — a difference in how each mode's `Flow.run()`-equivalent is structured, not a status
value either mode's `derive_run_status` call treats differently.

---

### `workflows/project.py` — ProjectWorkflow

Project Mode execution engine. `ProjectWorkflow.from_file(path)` loads a `ProjectWorkflowConfig` from `veriflow.yaml`; `run()` builds a `Design` + `Flow`, snapshots `rtl_hash` *before* running any stage (dev-docs/TRACEABILITY_AUDIT.md Finding #1 — the hash must reflect the RTL the run started with, not whatever it looked like once every stage had already finished), executes the flow into `<runs_dir>/run-NNN/`, then recomputes the overall status over the three canonical stage names (not just whichever ones `Flow` actually instantiated — see the status derivation note above) before writing `results.json`.

`build_project_flow(config)` assembles the stage list from `config.pipeline.stages` (see
`models/pipeline_config.py` below) rather than a fixed order — a stage type absent from
`pipeline.stages` is simply never instantiated. Each type still has its own precondition:
- `InterfaceStage` (`"connectivity"`) only if an `interface` section is configured
- `SimulationStage` only if `tb_sources` are present
- `SynthesisStage` has no precondition beyond being present in `pipeline.stages`

Each stage in `pipeline.stages` may carry its own `backend:` override, resolved through the same
backend registry as Database Mode (see below) — this is what `stage-backend`/`pipeline.stages[].backend:`
(e.g. `simulation: xsim`) ultimately drives.

See [PROJECT_CONFIG.md](PROJECT_CONFIG.md) for the `veriflow.yaml` schema and validation error codes.

---

### `commands/init_db.py` — Database initialization

Creates the canonical database layout under `<db>/`:
```
project_config.yaml    (template — id_prefix, project_name, repo, interface_name, description)
tile_index.csv         (empty — header written on first tile)
records.csv            (empty — header written on first run)
config/                (empty)
tiles/                 (.gitkeep)
```

With `--force`: overwrites an existing database entirely.

---

### `commands/create_tile.py` — Tile scaffolding

`cmd_create_tile(db, *, top_module="")`:

1. Reads and validates `project_config.yaml`; resolves the interface profile from `interface_name`
2. For Semicolab projects, `--top-module` is required and must be a valid Verilog identifier (`VF_TILE_TOP_MODULE_REQUIRED` / `VF_TILE_TOP_MODULE_INVALID`)
3. Calls `csv_store.get_next_tile_number()`; generates `tile_id` via `tile_id.generate_tile_id()` with version=01, revision=01, date=today
4. Creates `config/tile_XXXX/tile_config.yaml` (merged template with inline comments; `top_module` substituted when provided)
5. Creates `config/tile_XXXX/src/rtl/` and `src/tb/`; generates the self-contained testbench scaffold `src/tb/tb_tile.v` (Semicolab: from `template/tb_semicolab_template.v` with the DUT instantiation filled in; generic: from `template/tb_universal_template.v`)
6. Creates `tiles/<tile_id>/` with `README.md`, `works/rtl/`, `works/tb/`, `runs/`
7. Appends to `tile_index.csv` (row includes the `interface_name` column)

---

### `api.py` — Internal Python integration surface

`run_tile(db_path, tile, *, skip_connectivity, skip_sim, skip_synth, only_connectivity, only_sim, only_synth, waves, non_interactive) → dict`

Thin wrapper over `cmd_run()` for callers that want a Python-callable entry point without going through the CLI or subprocess.  Accepts `str | Path` for `db_path`; normalises it via `normalize_path()`.  All flag names mirror the CLI flags.  `VeriFlowError` propagates unchanged.  Raises `VF_NON_INTERACTIVE_VIEWER_DISABLED` if `waves=True` and `non_interactive=True`.

This surface has grown well beyond `run_tile` since this document last described it — it is now
the single layer both `cli.py` (for several `project`/`db` subcommands) and `mcp_server.py` (every
MCP tool) call through, rather than duplicating logic per frontend:

| Function | Backs |
|---|---|
| `project_run` | `project run` |
| `project_import` | `project import` |
| `import_repo` | `db import-repo` — clone (with `core/git_safety.py` URL validation), run the clone's own `project run` as a real precheck, then `project_import()` the result |
| `generate_readme` | `project generate-readme` |
| `apply_spec` | `project apply-spec` |
| `get_project_run_result` | reading a persisted Project Mode `results.json` |
| `list_pdks` | `pdk list` / the `veriflow_list_pdks` MCP tool |

Intended consumers: the CLI itself, the MCP server, CI/CD scripts, other agent tooling.  This is an internal surface — it is not a REST or RPC API.

---

### `core/path_safety.py` / `core/git_safety.py` — Path and URL containment

Added in response to dev-docs/SECURITY_AUDIT.md. `safe_join(base_dir, name) -> Path` resolves
`name` relative to `base_dir` and raises `VeriFlowError(code="VF_UNSAFE_PATH")` unless the result
stays strictly inside `base_dir` once resolved — catches `../` traversal, absolute-path overrides
(POSIX *and* Windows drive-letter, detected even on a POSIX host — see the regex fallback in
`_is_absolute_override`), and symlinks that resolve outside. Used everywhere a user-controlled
string becomes part of a filesystem path before any write: `wrapper_name` (`workflows/wrap.py`),
`tile_id` (`commands/create_tile.py`), and `readme_template`/`--template`
(`api.py`/`workflows/project_config.py`).

`validate_git_clone_url(url)` (`core/git_safety.py`) enforces an explicit scheme allowlist
(`http://`/`https://`/a local path with no scheme) before any `git clone` — rejects git's own
`ext::`/`fd::` transport-helper syntax (arbitrary local command execution) and any other scheme
(`ssh://`, `git://`, `file://`, ...) outright. Applied in `api.py`'s `import_repo()` and
`commands/pdk.py`'s `ihp130` git-clone install path.

---

### `veriflow/framework/status.py` — Shared run-status aggregation

`derive_run_status(stage_statuses: Iterable[str]) -> str` — the single implementation both
`ProjectWorkflow` and `DatabaseWorkflow` now call to collapse per-stage statuses into one overall
run status (see the status-derivation note under `workflows/database.py` above). Previously each
mode had its own copy, and they had silently diverged.

---

### `mcp_server.py` — Model Context Protocol server

`veriflow mcp serve` starts this over stdio (launched automatically by an MCP client, never run by
hand); `veriflow mcp install --client <claude-code|claude-desktop>` (`commands/mcp.py`) registers
it with a client. Built on `fastmcp` (optional dependency — importing `mcp_server.py` without it
installed raises a clear, actionable `VeriFlowError` rather than an import-time crash; see
dev-docs/MCP_OPTIONAL_FASTMCP_FIX.md for why that guard exists).

Exposes 22 `@mcp.tool` functions — thin wrappers that call straight into `api.py`/`commands/`, one
per CLI command that makes sense as an isolated, stateless operation (`veriflow_project_run`,
`veriflow_db_set`, `veriflow_import_repo`, `veriflow_wrap_generate`, ... — full list and one-line
descriptions in [MCP_SERVER.md](MCP_SERVER.md), kept in sync 1:1 with `grep -c "@mcp.tool"
veriflow/mcp_server.py`). Every tool returns a plain, structured result (a genuine `"status":
"FAIL"` is real data, not a tool-call error; a configuration problem comes back as
`{"status": "ERROR", "error": {...}}`).

Also exposes 7 `@mcp.resource` endpoints (`veriflow://docs/manual`, `.../quickref`,
`.../project-config`, `.../install`, `.../custom-backends`, `.../wrap`, `.../doctor`) serving the
matching file under `veriflow/mcp_docs/` — a packaged, flat-named copy of the `docs/` subset an
installed wheel needs (`docs/` itself lives outside the `veriflow/` package directory, so it isn't
included by `setup.py`'s `package_data`). `scripts/sync_mcp_docs.py` is the only thing that writes
to `veriflow/mcp_docs/`; a test fails if the two ever diverge, as a reminder to re-run it after
editing any of the mirrored source files.

`veriflow context` (`llms_txt.py`) is the non-MCP fallback: a plain-text dump covering the same
ground (commands, schemas, an end-to-end example) for pasting into a chat that has no tool access.
Its command-reference and `set`-command-keys sections are generated by walking `cli.py`'s real
`argparse` tree at call time, not hand-maintained — they can't silently drift out of sync with the
CLI the way prose descriptions can.

---

### `commands/run.py` — Run command presentation

Main entry: `cmd_run(db, tile_number, skip_*, only_*, waves)`.

Builds `DatabaseRunOptions`, calls `DatabaseWorkflow(db).run_tile(...)`, then handles presentation only: prints the run header, per-stage results, and completion line via `ui/output`, and launches the waveform viewer if `--waves` was passed and `waves.vcd` exists. Returns the `run_result` dict (same shape as `results.json`).

All pipeline logic lives in `DatabaseWorkflow` (see above).

---

### `commands/db_read.py` — Read-only database queries

| Function | Description |
|---|---|
| `cmd_db_list_tiles(db)` | Lists tiles from `tile_index.csv`; prints a Rich table; returns `list[DatabaseTileInfo]` |
| `cmd_db_list_runs(db, tile)` | Lists runs for a tile from persisted run directories |
| `cmd_db_show_run(db, run_id, tile)` | Loads one persisted `results.json` via `DatabaseWorkflow.load_run_result()` |

In `--json` mode the CLI serializes these results into the output payload.

---

### `core/pipeline_builder.py` — Default pipeline construction (Database Mode)

`build_default_pipeline(*, rtl_files, tb_files, tb_top, top_module, profile=None, interface_profile=None) → PipelineRunner`

Still, today, literally the fixed three-stage builder (connectivity → simulation → synthesis) this
document originally described — unlike Project Mode (below), Database Mode's pipeline
configurability was **not** implemented by changing what this function builds. All three stage
objects are always constructed; `pipeline.stages` (`project_config.yaml`/`tile_config.yaml`,
tile-level overrides database-level) is instead translated into the *existing* `skip_connectivity`/
`skip_sim`/`skip_synth` context flags before this runs (`DatabaseWorkflow.run_tile()`: "a stage type
absent from the effective pipeline behaves exactly like the matching `--skip-*` flag") — a stage
type not in `pipeline.stages` ends up reporting `SKIPPED` via the same code path as an explicit
`--skip-check`/`--skip-sim`/`--skip-synth`, not by never being instantiated. Per-stage
`backend:` overrides (`stage-backend`) *are* threaded through here, via `profile: ExecutionProfile`.

- `interface_profile` is forwarded to `InterfaceStage`; when the context's `skip_connectivity` is set the stage reports `SKIPPED`.
- `tb_top` selects the testbench top module for `SimulationStage` and must be non-empty (`VF_SIM_TB_TOP_REQUIRED`).
- `profile: ExecutionProfile` (defaults to `default_execution_profile()`) supplies tool labels and backend IDs; backend instances are obtained from the backend registry. Stage constructors still accept an explicit `backend` parameter, so tests can inject mocks directly.

`DatabaseWorkflow` calls this once after sources are copied, then runs each stage individually via single-stage `PipelineRunner` calls so that the connectivity-FAIL early-exit logic is preserved.

Contrast with Project Mode's `build_project_flow` (`workflows/project.py`, above), which reads
`config.pipeline.stages` directly and only instantiates the stage types actually listed — the two
modes reach "configurable pipeline" by genuinely different mechanisms, not a shared implementation.
`models/pipeline_config.py` defines the `PipelineConfig`/`PipelineStageConfig` dataclasses
(`stages: list[{type, backend}]`) both modes parse `pipeline:` into; `has_stage(name)` and
`backend_for(name)` are the two lookups each workflow calls against it.

---

### `core/stages/` — Pipeline stages

All stages implement `run(input: StageInput) → StageResult`, where `StageInput` carries the `Design` and the run context.

| Stage | Module | Behavior |
|---|---|---|
| `InterfaceStage` (name `"connectivity"`) | `stages/connectivity.py` | Skips if `ctx.skip_connectivity`; otherwise requires an `InterfaceProfile` and runs the backend's connectivity check against the RTL |
| `SimulationStage` | `stages/simulation.py` | Skips if `ctx.skip_sim` or no TB sources; otherwise compiles RTL+TB with the explicit `tb_top` and runs the simulation |
| `SynthesisStage` | `stages/synthesis.py` | Skips if `ctx.skip_synth`; otherwise runs Yosys synthesis |

`InterfaceStage` writes its artifacts under the historical `out/connectivity/` path.

---

### `core/backends/registry.py` — Backend registry

A static, read-only mapping from backend name strings to concrete backend classes.  Three lookup functions are exposed:

```python
get_connectivity_backend(name: str) -> ConnectivityBackend
get_simulation_backend(name: str)   -> SimulationBackend
get_synthesis_backend(name: str)    -> SynthesisBackend
```

Registered names today: `"icarus"` (connectivity, simulation), `"xsim"` (simulation only — Vivado's
`xvlog`/`xelab`/`xsim`, see `core/backends/xsim.py` and [CUSTOM_BACKENDS.md](CUSTOM_BACKENDS.md)),
`"yosys"` (synthesis).  An unrecognised name raises `VeriFlowError` with one of:

| Code | Trigger |
|---|---|
| `VF_BACKEND_CONNECTIVITY_UNKNOWN` | unknown connectivity backend name |
| `VF_BACKEND_SIMULATION_UNKNOWN`   | unknown simulation backend name |
| `VF_BACKEND_SYNTHESIS_UNKNOWN`    | unknown synthesis backend name |

The registry is still a plain Python dictionary with no dynamic imports/plugin discovery — adding
a backend means adding a class + a registry entry, not dropping a file into a plugin directory.
What *has* changed since this was last accurate: a backend is no longer selected once per process.
`pipeline.stages[].backend:` (Project Mode's `veriflow.yaml`, Database Mode's `project_config.yaml`/
`tile_config.yaml`) selects a backend **per stage**, resolved fresh from this same registry each
time `build_project_flow`/`build_default_pipeline` runs. `project set stage-backend <type>:<backend>`
(and the `db set`/`db tile set` equivalents, `commands/set_config.py`) write that field without
hand-editing YAML.

---

### `models/interface_profile.py` — Interface profiles

`InterfaceProfile` is a frozen dataclass (`name`, `description`, tuple of `InterfacePort(name, direction, width)`). The built-in `semicolab` profile defines the nine-port structural contract required by the Semicolab harness.

Registry APIs:

```python
get_interface_profile(name)          # None for name=None (generic project); VF_INTERFACE_UNKNOWN otherwise
list_interface_profile_names()
list_interface_profiles()
has_interface_profile(name)
default_interface_profile()          # always None — interfaces are opt-in
```

VeriFlow has no default interface: projects must opt in explicitly via `interface_name` (Database Mode) or `interface.name` (Project Mode). An omitted or null value means a generic project with no interface checking.

**Custom profiles are fully implemented** (not future work, see the old text this replaced):

- `load_interface_profile_from_file(path) -> InterfaceProfile` / `register_interface_profile_from_file(path)` — parse a `.v` port-list stub (regex-based, same extractor `wrap init` uses for RTL auto-detection) and register it under the module name found inside. Driven by `interface.definition:`/`interface_definition:` pointing at a local path.
- `resolve_interface_definition(definition, base_dir) -> Path` — the entry point that also accepts an `http(s)://` URL. URL definitions go through a **permanent local cache**: `_cache_dir_for_url(url)` hashes the URL (sha256) to a cache directory under `~/.veriflow/interfaces/cache/`; `_download_interface_url(url)` fetches it once (size-capped via `_reject_if_declared_too_large`/`_read_capped` — dev-docs/SECURITY_AUDIT.md — and scheme-restricted to `http`/`https` via `_url_scheme`), and every later resolution of that URL is a pure cache read, no network access. `find_cached_interface_by_name`/`update_cached_interface_url`/`list_cached_interface_urls` back the `veriflow interface list-cached`/`interface update` CLI commands.

---

### `models/technology_profile.py` — Technology / PDK targets

> **Backend vs technology profile distinction:**
> A *backend* is a tool that executes work (e.g. `yosys`, `iverilog`).
> A *technology profile* is a synthesis target / PDK context (e.g. `sky130`, `gf180`, `ihp130`).
> These are orthogonal: the same backend can synthesise for different technology targets, and the same target can in principle be served by different backends.

`TechnologyProfile` is a plain dataclass describing a named technology target — **now with real
PDK install metadata**, not just descriptive fields (the old version of this document described
`pdk`/`cell_library`/`liberty`/`constraints`/`notes` as "metadata placeholders only... not wired
into `YosysSynthesisBackend`" — that has since shipped in full, see `models/pdk_manager.py` below):

```python
@dataclass
class TechnologyProfile:
    name: str = "generic"
    liberty: str | None = None            # resolved absolute path once installed
    require_pdk: bool = False             # true: hard-fail synthesis instead of falling back to generic
    install_method: str | None = None     # "volare" | "git" | None (no installable PDK, e.g. "generic")
    volare_pdk: str | None = None         # PDK name passed to `volare enable --pdk`
    git_url: str | None = None            # repo URL for install_method == "git"
    default_version: str | None = None    # pinned commit hash; omit for volare's own "latest"
    pdk_subdir: str | None = None         # subdirectory of the PDK root holding the actual PDK tree
    liberty_glob: str | None = None       # glob (rooted at pdk_subdir) resolving to the liberty file
```

`get_technology_profile(name)` looks up a built-in (`"generic"`, `"sky130"`, `"gf180"`, `"ihp130"`)
from `technologies/<name>.yaml`; `VF_TECHNOLOGY_UNKNOWN` for anything else.
`load_and_register_technology_profile_from_file(path, liberty_root=...)` handles an external
`technology.definition:`/`technology_definition:` file, resolving a relative `liberty:` path
against the referencing config's directory. `liberty` is populated at resolution time by
`models/pdk_manager.py` (below), not stored as a static string in the YAML — a technology that
isn't installed yet simply has `liberty=None`. `core/stages/synthesis.py` then either falls back to
generic (non-technology-mapped) synthesis with a `VF_TECHNOLOGY_PDK_NOT_INSTALLED` warning, or, if
`require_pdk` is set, raises `VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED` instead.

---

### `models/pdk_manager.py` — PDK install/lookup

Backs the entire `veriflow pdk` namespace (`list`/`install`/`update`/`status`/`path`/`versions`/`remove`)
and `veriflow doctor`'s `[TECHNOLOGIES]` section. All PDKs live under
`~/.veriflow/pdks/<technology name>/` (`VERIFLOW_PDK_ROOT`, overridable) — no `PDK_ROOT` or liberty
path environment variables for the user to set by hand.

```python
get_pdk_path(pdk_name) -> Path | None            # ~/.veriflow/pdks/<name>/, if it exists
get_liberty_path(pdk_name) -> Path | None         # resolves technology.liberty_glob against the PDK dir
get_installed_pdk_version(pdk_name) -> str | None # currently-active version, if any
build_volare_enable_command(technology, pdk_dir) -> list[str]   # `volare enable --pdk <name> [<hash>] --pdk-root <path>`
```

Two install strategies, selected by `TechnologyProfile.install_method`:
- **`"volare"`** (`sky130`, `gf180`) — shells out to [volare](https://pypi.org/project/volare/)
  (requires the `pdks` extra, `pip install veriflow-eda[pdks]`); `default_version` pins a specific
  commit hash, omitted falls back to volare's own "latest" resolution.
- **`"git"`** (`ihp130`) — plain `git clone`/`git pull` of `TechnologyProfile.git_url`, no extra
  Python package beyond `git` in `PATH`.
- **`None`** (`generic`) — always reports `OK`, "no PDK required".

If a technology's PDK isn't installed when synthesis runs, the run still completes — falls back to
generic (non-technology-mapped) synthesis with a `VF_TECHNOLOGY_PDK_NOT_INSTALLED` warning in
`results.json`, unless `technology.require_pdk`/`technology-strict` is set, which hard-fails
instead. See [MANUAL.md §14.8](MANUAL.md#148-pdk-management-veriflow-pdk) for the full CLI
walkthrough and status-value table.

---

### `models/profile_loader.py` — Profile file loading (internal foundation, still unused)

`load_execution_profile(path: str | Path) → ExecutionProfile`

Reads a YAML file and returns a populated `ExecutionProfile`. Still, as of today, an **internal
foundation only** — no other production module imports `load_execution_profile`, it is not exposed
through the CLI, and default behavior (no profile file) is unchanged. This predates, and is
unrelated to, the `pipeline.stages[].backend:`/`stage-backend` mechanism that actually shipped
per-stage backend selection (see `core/backends/registry.py` above) — that mechanism reads
`pipeline.stages[]` directly off the parsed config, not through this loader. Whether
`profile_loader.py` still has a future (e.g. a `--profile` flag for implementation-stage profiles
like LibreLane/OpenLane) or should be removed as dead code is an open question, not resolved by
this pass.

---

### `models/execution_profile.py` — Toolchain description

`ExecutionProfile` is a plain dataclass that records which external tools, internal backend IDs, and technology target the current run uses:

```python
@dataclass
class ExecutionProfile:
    name: str = "default"
    connectivity_tool: str = "iverilog"
    simulation_tool: str = "iverilog/vvp"
    synthesis_tool: str = "yosys"
    doc_profile: str = "default"
    connectivity_backend: str = "icarus"
    simulation_backend: str = "icarus"
    synthesis_backend: str = "yosys"
    technology_name: str = "generic"    # resolved via get_technology_profile()
    require_pdk: bool = False           # hard-fail instead of falling back to generic synthesis
```

The `*_tool` fields determine the `StageResult.tool` label written to `results.json`.  The `*_backend` fields are IDs passed to the backend registry — per-stage now (`pipeline.stages[].backend:`/`stage-backend`), not one fixed value for the whole run; see `core/pipeline_builder.py` and `workflows/project.py` above for how each mode resolves a stage-specific `ExecutionProfile`.

`default_execution_profile() → ExecutionProfile` returns the canonical instance.

---

### `commands/waves.py` — Waveform viewer

`cmd_waves(db, tile_number, run_id)`:

1. Validates the database
2. Resolves `tile_id` from `tile_index.csv`
3. If `--run` is given: opens that specific run directory; raises `VeriFlowError` if not found
4. If `--run` is omitted: scans `runs/` for directories matching `run-NNN`, picks the highest
5. Verifies `out/sim/waves/waves.vcd` exists
6. Calls `launch_waves()`, which uses Surfer WASM in Docker and native Surfer locally

---

### `commands/bump_version.py` / `commands/bump_revision.py` — Version management

Both commands:
1. Resolve the current `tile_id` from `tile_index.csv`
2. Increment the appropriate counter (version +1; or revision +1 + version reset to 01)
3. Generate a new `tile_id` with today's date
4. Create the new `tiles/<new_tile_id>/` directory with `works/` copied from the previous one and a clean `runs/`
5. Update `tile_index.csv` to point to the new `tile_id`

The previous directory is preserved as read-only history.

---

### `core/sim_runner.py` — Connectivity check, simulation, wave viewer

Testbenches are self-contained — there is no injection, marker extraction, or temp TB rewriting.

**Connectivity / interface check:**

- `_build_interface_check_wrapper(top_module, interface_profile)` — generates a minimal Verilog elaboration wrapper from the profile: one signal per declared port plus a named-port DUT instantiation. No clock, reset, tasks, or stimulus.
- `run_connectivity_check(rtl_files, interface_profile, top_module, log_path)` — compiles the RTL sources plus the generated wrapper with `iverilog -o NUL//dev/null`; does not read user testbench files; returns `"PASS"` or `"FAIL"`

**Simulation:**

- `run_simulation(rtl_files, tb_files, tb_top, sim_log_path, wave_path)` — compiles all RTL and TB files together with `iverilog -s <tb_top>` into `tempfile.mkdtemp()` (avoids Windows path-with-spaces issues), runs `vvp` from `wave_path.parent` so `$dumpfile("waves.vcd")` lands in the correct directory; returns `("COMPLETED"|"FAILED", {sim_time, seed})`. `$dumpfile`/`$dumpvars` must be present in the testbench itself.

**Waveform viewer:**

- `open_surfer(wave_path)` — Docker mode only; constructs `http://localhost:7681/?load_url=<vcd>` URL and prints it; calls `webbrowser.open()` as best-effort
- `launch_waves(wave_path)` — priority: (1) `VERIFLOW_DOCKER` (or deprecated `SEMICOLAB_DOCKER`) → `open_surfer`; (2) `surfer` in PATH → native Surfer; (3) prints Surfer install hint

---

### `core/synth_runner.py` — Synthesis

`run_synthesis(rtl_files, top_module, synth_log_path)`:

Builds and runs an inline Yosys script:
```
read_verilog <files...>
hierarchy -check -top <top_module>
synth
check
stat
```

Returns `("PASS"|"FAIL", {cells, warnings, errors, has_latches})`.
FAIL if return code != 0 or `"Latch inferred"` detected in the log.

---

### `core/validator.py` — Pre-run validation

| Function | What it checks |
|---|---|
| `validate_database(db)` | `project_config.yaml`, `tile_index.csv`, `records.csv`, `tiles/` exist |
| `validate_tools()` | `iverilog` and `yosys` in PATH (`shutil.which`) |
| `validate_run_inputs(db, tile_number, tile_config)` | `config/tile_XXXX/` exists; `src/rtl/` has `.v` files; `top_module` set and has matching `.v` file |
| `validate_project_config(project_config)` | `id_prefix` is not empty |
| `detect_iverilog_version()` | Runs `iverilog -V`, parses with `log_parser.parse_iverilog_version` |

---

### `core/csv_store.py` — CSV persistence

Manages two CSV files:

**`tile_index.csv`** — one row per tile, current `tile_id` for each `tile_number`:
```
tile_number, tile_id, tile_name, tile_author, version, revision, interface_name
```

**`records.csv`** — one row appended per run:
```
Tile_ID, Run_ID, Date, Author, Objective, Status,
Version, Revision, Connectivity, Simulation, Synthesis,
Tool_Version, Main_Change, Run_Path, Tags, Interface
```

`interface_name` / `Interface` hold the interface profile name (e.g. `semicolab`), empty for generic projects.

Both files: if empty, the header is written before the first append. If non-empty, the header is validated before any read/write. `get_tile_row` raises `VeriFlowError` if the tile is not found.

---

### `core/copier.py` — Flat file copy

`copy_flat(src_dir, dst_dir, extension=".v") → list[Path]`

Copies all files matching `extension` from `src_dir` to `dst_dir` without preserving subdirectory structure. Name collisions are resolved by appending `_1`, `_2`, etc. Returns the list of destination paths.

---

### `core/log_parser.py` — Output parsing

| Function | Input | Output |
|---|---|---|
| `parse_sim_log(log_text)` | `vvp` stdout | `{sim_time: "335 ns", seed: ""}` — parses `$finish called at N (unit)`, converts to ns |
| `parse_synth_log(log_text)` | `yosys` stdout | `{cells: "253", warnings: "0", errors: "0", has_latches: False}` — takes last `stat` block |
| `parse_iverilog_version(version_output)` | `iverilog -V` stdout | `"Icarus Verilog 13.0"` |

---

### `core/run_id.py` — Run ID generation

`get_next_run_id(runs_dir) → str`

Scans `runs_dir` for directories matching `run-NNN`. Returns `"run-001"` if none exist, otherwise the next zero-padded 3-digit ID.

---

### `core/tile_id.py` — Tile ID generation and parsing

**Format:** `<id_prefix>-<YYMMDD><tile_number:04d><version:02d><revision:02d>`

Example: `MST130-01-26032500010102`

- `generate_tile_id(id_prefix, tile_number, id_version, id_revision, today)` — builds the ID
- `parse_tile_id(tile_id) → dict` — decomposes into `{id_prefix, yymmdd, tile_number, id_version, id_revision}`; assumes the numeric block after the last `-` is exactly 14 characters

---

### `generators/` — Per-run documentation

| Module | Function | Output |
|---|---|---|
| `manifest.py` | `generate_manifest(data, output_path)` | `manifest.yaml` — custom serializer with blank-line sections; no `yaml.dump` |
| `results.py` | `generate_results_json(data, output_path)` | `results.json` — machine-readable run result (schema 1.2) |
| `notes.py` | `generate_notes(tile_id, tile_config, output_path)` | `notes.md` — designer notes from `tile_config.notes` |
| `readme.py` | `generate_readme(tile_id, tile_config, output_path)` | `README.md` in `tiles/<tile_id>/` — regenerated on every run |
| `summary.py` | `generate_summary(...)` | `summary.md` — results table; also printed to console |

---

### `models/` — Configuration dataclasses

**`ProjectConfig`** (Database Mode `project_config.yaml`)
```python
@dataclass
class ProjectConfig:
    id_prefix: str
    project_name: str
    repo: str
    description: str
    interface_name: str | None = None   # None → generic project
```
`from_dict` requires the `interface_name` key (`VF_PROJECT_INTERFACE_REQUIRED` if missing) and rejects the deprecated `semicolab` key (`VF_PROJECT_INTERFACE_CONFIG_LEGACY`).

**`TileConfig`** — merged tile + run fields (single `tile_config.yaml`):
```python
@dataclass
class TileConfig:
    # Tile fields (fill once at create-tile time)
    tile_name: str
    tile_author: str
    top_module: str
    tb_top_module: str   # testbench top module, defaults to "tb"
    description: str
    ports: str
    usage_guide: str
    tb_description: str
    # Run fields (update before each run)
    run_author: str
    objective: str
    tags: str
    main_change: str
    notes: str
```

**`RunContext`** — per-run execution context handed to stages: `tile_id`, `run_id`, `tile_dir`, `run_dir`, `interface_name`, `skip_connectivity`, `skip_sim`, `skip_synth`, `db_path`; plus derived path properties and `log_rel()`.

**`StageResult`** — uniform per-stage result (`name`, `status`, `tool`, `log_paths`, `artifacts`, `metrics`, `error`); `to_dict()` produces the stage dictionaries persisted in `results.json`.

---

### `template/*.v` — Testbench scaffold templates

Used only at `create-tile` time to generate the initial `src/tb/tb_tile.v`. After scaffolding, the file belongs entirely to the user; nothing is injected at run time.

| File | Role |
|---|---|
| `tb_semicolab_template.v` | Self-contained Semicolab testbench scaffold: nine-port signals, clock/reset, `$dumpfile`/`$dumpvars`, helper tasks, `/* DUT_MODULE */` placeholder replaced with `--top-module`, marked user-stimulus block |
| `tb_universal_template.v` | Minimal generic scaffold: empty `module tb` with waveform dump; user declares signals and instantiates the DUT |

---

### `ui/` — Terminal UI and styled output

| Module | Role |
|---|---|
| `ui/theme.py` | Central Rich color palette and `VERIFLOW_THEME`; all UI modules import from here |
| `ui/output.py` | Styled output helpers used by all commands: `print_status`, `print_section`, `print_run_header`, `print_done`, `print_fail_detail`, `print_wave_url`, `print_ports_table` |
| `ui/themes.py` | 16 Textual-compatible color palettes; `Palette` dataclass with semantic keys (`bg`, `accent`, `green`, `red`, …); `~/.veriflow_theme` persists the selection (migrates from `~/.semicolab_theme`); provides `build_css()` and `palette_to_vars()` for Textual CSS injection |
