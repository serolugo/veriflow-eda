"""
veriflow.mcp_server — MCP (Model Context Protocol) server for VeriFlow.

Exposes veriflow.api's functions as MCP tools (thin wrappers, see below) and
VeriFlow's user docs as MCP resources, so an agent (Claude Code, Claude
Desktop, or any other MCP client) can drive VeriFlow directly instead of
shelling out to the CLI and parsing text output.

Run with `veriflow mcp serve` (see commands/mcp.py) -- not meant to be
invoked directly; the MCP client (not a human) launches this process over
stdio and speaks JSON-RPC to it.

Error contract for every tool: veriflow.api re-raises VeriFlowError
directly for configuration/environment problems, and returns FAIL/PARTIAL
as ordinary data for verification outcomes (see veriflow.api's own module
docstring). Every tool here catches VeriFlowError and converts it to a
structured dict instead of letting it become an uncaught exception --
an agent should never see a Python traceback, and status="FAIL" is data
to reason about, never an error to catch. A tool that returns list[dict]
on success returns a single-item list `[{"status": "ERROR", "error": {...}}]`
on error instead of a bare dict, so its declared output schema (an array)
still validates -- check `result[0]["status"] == "ERROR"` rather than
assuming every item is a real record.
"""

from __future__ import annotations

from pathlib import Path

from veriflow.core import VeriFlowError

try:
    from fastmcp import FastMCP

    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False


class _StubMCP:
    """Stand-in for a real FastMCP instance when the `fastmcp` package
    isn't installed (it's an optional dependency -- setup.py's `mcp`
    extra). Every `@mcp.tool`/`@mcp.resource` decorator below still needs
    somewhere to attach to at import time so the module itself stays
    importable -- e.g. so `veriflow doctor`/other non-MCP commands keep
    working in a `pip install veriflow-eda` (no extras) environment, and so
    test collection doesn't fail before test files get a chance to skip.
    Both decorators are pure no-ops here: they register nothing and return
    the wrapped function/resource unchanged, same as `@mcp.tool`'s own
    "registers as a side effect, returns the function unchanged" contract
    (see this module's own docstring) -- so every tool function below
    remains a plain, directly callable Python function either way. Actually
    *serving* the tools over MCP (`main()`) is a separate, later failure
    point -- see its own FASTMCP_AVAILABLE check -- since that's the only
    place a stubbed-out registration would actually matter."""

    def tool(self, fn=None, **kwargs):
        if fn is not None:
            return fn

        def decorator(f):
            return f

        return decorator

    def resource(self, *args, **kwargs):
        def decorator(f):
            return f

        return decorator


mcp = FastMCP(name="VeriFlow") if FASTMCP_AVAILABLE else _StubMCP()


def _error(exc: VeriFlowError) -> dict:
    return {"status": "ERROR", "error": exc.to_dict()}


def _error_list(exc: VeriFlowError) -> list[dict]:
    return [_error(exc)]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
def veriflow_doctor() -> dict:
    """Check which EDA tools (iverilog, yosys, xsim, etc.) and PDKs are
    installed and available on this machine.

    Use this first if unsure whether VeriFlow can run verification here --
    every other tool that runs a pipeline stage (veriflow_project_run,
    veriflow_run_tile) depends on the backends this reports on. Returns a
    report with a "connectivity"/"simulation"/"synthesis" backend
    breakdown and a "technologies" (PDK) breakdown; overall "status" is
    "OK" only if every category has at least one fully-available backend.
    A missing PDK does not make status "FAIL" -- synthesis falls back to
    generic (non-technology-mapped) mapping when a PDK isn't installed.
    """
    import argparse

    from veriflow.commands.doctor import cmd_doctor

    try:
        _exit_code, report = cmd_doctor(argparse.Namespace())
        return report
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_project_run(config_path: str) -> dict:
    """Run Project Mode's verification pipeline end-to-end for a single
    RTL project and return the resulting results.json as a dict.

    Use this for "I have a .v file and a veriflow.yaml, verify it" --
    no database or tiles required. status "FAIL" in the returned dict
    means the RTL did NOT pass verification -- this is a valid, expected
    result to report back, not an error. Only a malformed veriflow.yaml,
    missing RTL sources, or an unregistered interface/technology name
    produces the ERROR envelope described in this module's docstring.

    Parameters
    ----------
    config_path : str
        Path to the Project Mode veriflow.yaml.
    """
    from veriflow.api import project_run

    try:
        return project_run(config_path)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_run_tile(db_path: str, tile: str) -> dict:
    """Run Database Mode's verification pipeline for one tile and return
    the run_result dict (same shape as veriflow_db_get_run's result).

    status "FAIL"/"PARTIAL" means the tile did not fully pass verification
    -- report it as the real outcome, don't treat it as a tool failure.
    Always runs non-interactively (never opens a waveform viewer, which
    would have no meaning for an agent) regardless of any local CLI
    default.

    Parameters
    ----------
    db_path : str
        Path to the VeriFlow database directory.
    tile : str
        Tile number, e.g. "0001" or "1".
    """
    from veriflow.api import run_tile

    try:
        return run_tile(db_path, tile, non_interactive=True)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_wrap_init(
    interface_name: str,
    rtl_file: str,
    wrapper_name: str | None = None,
) -> dict:
    """Scaffold a wrapper_config.yaml (as a dict, not written to disk) for
    wrapping a single RTL file against a registered interface profile.

    Auto-detects the RTL file's top module (it must declare exactly one
    `module`), extracts its ports, and returns a dict matching the
    wrapper_config.yaml schema plus a "detected_ports" list describing
    what was found in the RTL -- use veriflow_list_interface_profiles
    first if unsure which interface_name values are valid. This tool does
    NOT write any file; pair it with veriflow_wrap_generate (which reads
    a wrapper_config.yaml from disk) if a saved config is also needed.

    Parameters
    ----------
    interface_name : str
        A registered interface profile name (see veriflow_list_interface_profiles).
    rtl_file : str
        Path to the RTL file to scaffold a wrapper for.
    wrapper_name : str | None
        Wrapper module name. Defaults to "<top_module>_wrapper".
    """
    from veriflow.api import wrap_init

    try:
        return wrap_init(interface_name, rtl_file, wrapper_name=wrapper_name)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_wrap_generate(config_path: str) -> dict:
    """Generate a wrapper Verilog module from a wrapper_config.yaml
    (typically produced by veriflow_wrap_init and saved to disk first).

    Returns the full output dict (schema_version, status, ports, ...).
    A validation FAIL (e.g. a port declared in the config that isn't on
    the interface) is returned as data with status="FAIL", not raised.

    Parameters
    ----------
    config_path : str
        Path to wrapper_config.yaml.
    """
    from veriflow.api import wrap_generate

    try:
        return wrap_generate(config_path)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_project_import(config_path: str, db_path: str, force: bool = False) -> dict:
    """Import a verified Project Mode run (the latest one with status PASS)
    into a Database Mode database as a new tile.

    Copies the run's RTL/testbench sources into the new tile and records
    the source run for traceability. Use veriflow_project_run first to
    make sure there is a passing run to import.

    Parameters
    ----------
    config_path : str
        Path to the Project Mode veriflow.yaml whose latest passing run
        should be imported.
    db_path : str
        Path to the destination VeriFlow database directory.
    force : bool
        Allow importing a project with no interface configured into a
        database that requires one (downgrades the block to a warning in
        the returned dict's "warnings" list). Not recommended -- the
        resulting tile's first db run will likely fail its connectivity
        check.
    """
    from veriflow.api import project_import

    try:
        return project_import(config_path, db_path, force=force)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_import_repo(repo_url: str, db_path: str, branch: str = "main", force: bool = False) -> dict:
    """Clone a git repo, run its own project verification as a real
    precheck, and import the result into a database as a new tile.

    For importing directly from a contributor's repo URL rather than a
    local checkout that's already been cloned and verified. The clone is
    always removed afterward, whether the import succeeds or fails. Only
    a repo whose own veriflow.yaml passes verification is imported --
    this IS the precheck, not a dry run.

    Parameters
    ----------
    repo_url : str
        Anything `git clone` accepts (https URL, ssh URL, or local path).
    db_path : str
        Path to the destination VeriFlow database directory.
    branch : str
        Branch to clone (default "main").
    force : bool
        Re-import repo_url+branch even if already imported into this
        database (creates a new, separate tile), and downgrade a
        generic-into-interface-requiring-database mismatch to a warning.
        Never lets a failing precheck through regardless of this flag.
    """
    from veriflow.api import import_repo

    try:
        return import_repo(repo_url, db_path, branch=branch, force=force)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_apply_spec(spec_path: str, config_path: str | None = None) -> dict:
    """Apply a shuttle_spec.yaml's interface/technology/pipeline fields
    onto a project's veriflow.yaml, the same way `veriflow project set`
    would apply each field individually (comments/formatting preserved).

    Use this when a shuttle organizer has published a shuttle_spec.yaml
    contract that a project must configure itself against, instead of
    manually calling veriflow_project's set operations field by field.

    Parameters
    ----------
    spec_path : str
        Path to shuttle_spec.yaml.
    config_path : str | None
        Path to the destination veriflow.yaml. Defaults to the
        VERIFLOW_CONFIG environment variable, else "veriflow.yaml".

    Returns a dict of the fields actually applied.
    """
    from veriflow.api import apply_spec

    try:
        return apply_spec(spec_path, config_path)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_generate_readme(config_path: str) -> dict:
    """Render a submission README.md for the current project from its
    latest passing run, and write it to disk.

    Unlike veriflow.api's generate_readme() (which returns a bare string),
    this tool wraps the rendered content in a dict: {"status": "SUCCESS",
    "content": <rendered markdown>, "out_path": <where it was written>}.
    Fails with the ERROR envelope if no run under the project's runs_dir
    has status PASS yet -- run veriflow_project_run until one does.

    Parameters
    ----------
    config_path : str
        Path to the Project Mode veriflow.yaml.
    """
    from veriflow.api import generate_readme

    try:
        content = generate_readme(config_path)
    except VeriFlowError as exc:
        return _error(exc)

    out_path = Path(config_path).resolve().parent / "README.md"
    return {"status": "SUCCESS", "content": content, "out_path": str(out_path)}


@mcp.tool
def veriflow_list_interface_profiles() -> list[dict]:
    """List every registered interface profile with its full port
    contract (name, direction, width per port).

    Call this before writing an `interface_name`/`interface.name` value
    into a project config, to see valid names and their required ports
    instead of guessing and hitting VF_INTERFACE_UNKNOWN.
    """
    from veriflow.api import list_interface_profiles

    try:
        return list_interface_profiles()
    except VeriFlowError as exc:
        return _error_list(exc)


@mcp.tool
def veriflow_list_technology_profiles() -> list[dict]:
    """List every registered technology (synthesis target) with its
    synthesis backend and current PDK/liberty install status.

    Call this before writing a `technology`/`technology.name` value into
    a project config, to see valid names instead of guessing and hitting
    VF_TECHNOLOGY_UNKNOWN.
    """
    from veriflow.api import list_technology_profiles

    try:
        return list_technology_profiles()
    except VeriFlowError as exc:
        return _error_list(exc)


@mcp.tool
def veriflow_list_pdks() -> list[dict]:
    """List installation status ("installed" | "not_installed") for every
    registered technology's PDK, with an install_hint command for any
    that are missing.

    Narrower than veriflow_doctor (PDKs only, no EDA tool checks) -- use
    this when only PDK availability matters, e.g. before recommending a
    `veriflow pdk install <name>` step.
    """
    from veriflow.api import list_pdks

    try:
        return list_pdks()
    except VeriFlowError as exc:
        return _error_list(exc)


@mcp.tool
def veriflow_db_list_tiles(db_path: str) -> list[dict]:
    """List all tiles registered in a Database Mode database (tile
    number, id, name, author, version, revision, interface).

    Read-only. Returns an empty list if the database has no tiles yet.

    Parameters
    ----------
    db_path : str
        Path to the VeriFlow database directory.
    """
    from veriflow.api import db_list_tiles

    try:
        return db_list_tiles(db_path)
    except VeriFlowError as exc:
        return _error_list(exc)


@mcp.tool
def veriflow_db_list_runs(db_path: str, tile: str) -> list[dict]:
    """List all runs for one tile, in ascending run-number order
    (run_id, status, date, has_waves).

    Read-only -- does not re-execute anything. Use this to see run
    history before calling veriflow_db_get_run for one run's full detail.

    Parameters
    ----------
    db_path : str
        Path to the VeriFlow database directory.
    tile : str
        Tile number, e.g. "0001" or "1".
    """
    from veriflow.api import db_list_runs

    try:
        return db_list_runs(db_path, tile)
    except VeriFlowError as exc:
        return _error_list(exc)


@mcp.tool
def veriflow_db_get_run(db_path: str, tile: str, run: str) -> dict:
    """Read one tile run's persisted result (results.json) without
    re-executing anything.

    Same dict shape veriflow_run_tile returns. Use this to inspect a past
    run instead of re-running verification.

    Parameters
    ----------
    db_path : str
        Path to the VeriFlow database directory.
    tile : str
        Tile number, e.g. "0001" or "1".
    run : str
        Run id, either bare ("3") or formatted ("run-003").
    """
    from veriflow.api import db_get_run

    try:
        return db_get_run(db_path, tile, run)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_get_project_run_result(run_dir: str) -> dict:
    """Read a Project Mode run's results.json from a specific run
    directory without re-executing anything.

    Use this to inspect a past `veriflow_project_run` result again (e.g.
    a run from an earlier session) instead of re-running verification.

    Parameters
    ----------
    run_dir : str
        Path to the run directory (e.g. "runs/run-001").
    """
    from veriflow.api import get_project_run_result

    try:
        return get_project_run_result(run_dir)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_project_init(top_module: str | None = None) -> dict:
    """Create a new, empty veriflow.yaml scaffold in the current directory
    (or specified path), optionally setting design.top_module in the same
    call. Use this when starting a brand-new project before any other
    veriflow_project_* tool can be used.

    Fails with the ERROR envelope (VF_PROJECT_CONFIG_EXISTS) if
    veriflow.yaml already exists there.

    Parameters
    ----------
    top_module : str | None
        RTL top module name to write into design.top_module. If omitted,
        the scaffold ships with top_module commented out for the user/agent
        to fill in later (e.g. via veriflow_project_set).
    """
    from veriflow.api import project_init

    try:
        return project_init(top_module=top_module)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_project_set(config_path: str, key: str, value: str) -> dict:
    """Modify a single field in a Project Mode veriflow.yaml without
    disturbing comments or other fields. Common keys: 'interface',
    'technology', 'technology-strict' (technology + require_pdk=true in one
    call), 'pipeline' (comma-separated stage types), 'stage-backend'
    (format 'stage:backend', e.g. 'simulation:xsim'), 'top-module',
    'rtl-sources' (comma-separated), 'require-pdk' ('true'/'false'), and
    metadata fields (name, author, description, version).

    Use this BEFORE veriflow_project_run when the user wants to change
    configuration and then verify. Fails with the ERROR envelope
    (VF_SET_KEY_UNKNOWN, VF_SET_INTERFACE_INVALID, VF_TECHNOLOGY_UNKNOWN,
    VF_PIPELINE_STAGE_UNKNOWN, VF_SET_STAGE_BACKEND_UNKNOWN,
    VF_STAGE_NOT_IN_PIPELINE, ...) for an unsupported key or invalid value.

    Parameters
    ----------
    config_path : str
        Path to the Project Mode veriflow.yaml.
    key : str
        Field to modify.
    value : str
        New value for the field.
    """
    from veriflow.api import project_set

    try:
        return project_set(config_path, key, value)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_db_set(db_path: str, key: str, value: str) -> dict:
    """Modify a field in a Database Mode project_config.yaml
    (database-wide settings: interface, technology, technology-strict,
    id-format, prefix, shuttle, pipeline, stage-backend).

    Parameters
    ----------
    db_path : str
        Path to the VeriFlow database directory.
    key : str
        Field to modify.
    value : str
        New value for the field.
    """
    from veriflow.api import db_set

    try:
        return db_set(db_path, key, value)
    except VeriFlowError as exc:
        return _error(exc)


@mcp.tool
def veriflow_db_tile_set(db_path: str, tile: str, key: str, value: str) -> dict:
    """Modify a field in a specific tile's tile_config.yaml (top-module,
    tb-top, name, author, description, tags, objective, pipeline override,
    stage-backend override, require-pdk). A tile cannot override its
    technology *name* -- that's database-wide, use veriflow_db_set instead.

    Parameters
    ----------
    db_path : str
        Path to the VeriFlow database directory.
    tile : str
        Tile number, e.g. "0001" or "1".
    key : str
        Field to modify.
    value : str
        New value for the field.
    """
    from veriflow.api import db_tile_set

    try:
        return db_tile_set(db_path, tile, key, value)
    except VeriFlowError as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Resources -- VeriFlow's user docs, readable by the agent on demand instead
# of being pasted wholesale into every conversation. Read from
# veriflow/mcp_docs/ (packaged data, see setup.py's package_data and
# scripts/sync_mcp_docs.py) via importlib.resources, so this works the same
# whether VeriFlow is a `pip install` or an editable repo checkout -- never
# assumes the current working directory is the repo root.
# ---------------------------------------------------------------------------


def _read_mcp_doc(filename: str) -> str:
    from importlib import resources

    return resources.files("veriflow.mcp_docs").joinpath(filename).read_text(encoding="utf-8")


@mcp.resource("veriflow://docs/manual", name="VeriFlow Manual", mime_type="text/markdown")
def doc_manual() -> str:
    """Full VeriFlow user manual: both operating modes, config schemas,
    every CLI command, results.json structure, and more."""
    return _read_mcp_doc("manual.md")


@mcp.resource("veriflow://docs/quickref", name="VeriFlow Quick Reference", mime_type="text/markdown")
def doc_quickref() -> str:
    """Condensed command/config cheat sheet -- faster to scan than the
    full manual when just a reminder of syntax is needed."""
    return _read_mcp_doc("quickref.md")


@mcp.resource("veriflow://docs/project-config", name="VeriFlow Project Config Reference", mime_type="text/markdown")
def doc_project_config() -> str:
    """Full field-by-field reference for veriflow.yaml (Project Mode) and
    project_config.yaml/tile_config.yaml (Database Mode)."""
    return _read_mcp_doc("project-config.md")


@mcp.resource("veriflow://docs/install", name="VeriFlow Installation Guide", mime_type="text/markdown")
def doc_install() -> str:
    """How to install the EDA tools (iverilog, yosys, optional xsim) and
    PDKs VeriFlow depends on, per platform."""
    return _read_mcp_doc("install.md")


@mcp.resource("veriflow://docs/custom-backends", name="VeriFlow Custom Backends Guide", mime_type="text/markdown")
def doc_custom_backends() -> str:
    """How to add or configure custom simulation/synthesis backends
    beyond VeriFlow's built-in ones."""
    return _read_mcp_doc("custom-backends.md")


@mcp.resource("veriflow://docs/wrap", name="VeriFlow Wrap Guide", mime_type="text/markdown")
def doc_wrap() -> str:
    """How wrapper generation works: scaffolding a wrapper_config.yaml
    from RTL and an interface profile, then generating the wrapper."""
    return _read_mcp_doc("wrap.md")


@mcp.resource("veriflow://docs/doctor", name="VeriFlow Doctor Guide", mime_type="text/markdown")
def doc_doctor() -> str:
    """What `veriflow doctor` checks and how to read its output."""
    return _read_mcp_doc("doctor.md")


def main() -> None:
    """Entry point for `veriflow mcp serve` -- blocking, stdio transport.

    Tools below call into CLI command functions (cmd_doctor, cmd_run,
    cmd_create_tile, ...) that print human-readable progress via the
    shared Rich console as a side effect. Over stdio, stdout carries the
    JSON-RPC protocol itself -- any stray console output there would
    corrupt it, so it's silenced for the lifetime of the server, the same
    way cli.py's own --json mode silences it (console.quiet is a real
    Rich Console attribute, not project-specific).

    Raises VeriFlowError(VF_MCP_FASTMCP_NOT_INSTALLED) if the optional
    `fastmcp` dependency isn't installed -- the module itself still
    imports fine without it (see `_StubMCP` above), so this is the actual
    point of failure, at run time rather than at import time."""
    if not FASTMCP_AVAILABLE:
        raise VeriFlowError(
            "fastmcp is required for the MCP server -- install with: "
            "pip install veriflow-eda[mcp]",
            code="VF_MCP_FASTMCP_NOT_INSTALLED",
        )

    from veriflow.ui.output import console

    console.quiet = True
    try:
        mcp.run(transport="stdio")
    finally:
        console.quiet = False


if __name__ == "__main__":
    main()
