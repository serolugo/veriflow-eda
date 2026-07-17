"""
veriflow.api — Internal Python integration surface for VeriFlow.

Use this module to call VeriFlow from another Python process, TUI, CI
script, or agent without depending on cli.py internals or subprocess.

    from veriflow.api import run_tile
    result = run_tile("./database", "0001", skip_sim=True, skip_synth=True)

Covers both operating modes (Database Mode: run_tile/db_list_tiles/
db_list_runs/db_get_run/project_import/db_set/db_tile_set; Project Mode:
project_run/get_project_run_result/project_set) plus read-only registry
lookups an agent needs to choose valid config values before writing a
project config (list_interface_profiles/list_technology_profiles/list_pdks).

VeriFlowError is re-raised directly; callers should import it from
veriflow.core if they need to catch it. Business-logic outcomes (a run that
completed but did not pass verification) are always returned as data with
status "FAIL"/"PARTIAL" -- never raised. Only configuration/environment
problems (bad path, malformed YAML, missing tool, unregistered name) raise
VeriFlowError.
"""

from __future__ import annotations

from pathlib import Path

from veriflow.core import VeriFlowError


def _normalize_path(db_path: str | Path) -> Path:
    return Path(db_path)


def _validate_tile_number(tile: str | int) -> str:
    """Validate *tile* is convertible to an integer tile number and return
    it as a string, unpadded (downstream code zero-pads as needed).

    Raises VeriFlowError(VF_TILE_NUMBER_INVALID) for non-numeric input --
    the same code raised by `db bump-version`/`db bump-revision`/`db waves`
    for a non-numeric --tile (see commands/bump_version.py).
    """
    try:
        return str(int(tile))
    except (TypeError, ValueError) as exc:
        raise VeriFlowError(
            f"Tile number must be numeric: {tile!r}",
            code="VF_TILE_NUMBER_INVALID",
            details={"tile": tile},
        ) from exc


def run_tile(
    db_path: str | Path,
    tile: str,
    *,
    skip_connectivity: bool = False,
    skip_sim: bool = False,
    skip_synth: bool = False,
    only_connectivity: bool = False,
    only_sim: bool = False,
    only_synth: bool = False,
    waves: bool = False,
    non_interactive: bool = False,
) -> dict:
    """Run Database Mode's verification pipeline for *tile* and return the
    run_result dict.

    Delegates to cmd_run(); does not duplicate logic. Status "FAIL"/
    "PARTIAL" means the tile did not fully pass verification -- it is
    returned as data, not raised. VeriFlowError propagates to the caller
    unchanged for configuration/environment problems (missing database,
    missing tile, missing tool, etc.).

    Parameters
    ----------
    db_path : str | Path
        Path to the VeriFlow database directory.
    tile : str
        Tile number, e.g. "0001" or "1" -- must be convertible to an
        integer. Raises VeriFlowError(VF_TILE_NUMBER_INVALID) otherwise.
    skip_connectivity, skip_sim, skip_synth : bool
        Skip individual stages.
    only_connectivity, only_sim, only_synth : bool
        Run a single stage; remaining stages are skipped.
    waves : bool
        Launch waveform viewer after simulation. **Not suitable for agent
        use** -- opens a subprocess (Surfer) or browser window as a side
        effect, which has no meaning in an automated context. Always False
        when non_interactive=True (silently overridden, not raised --
        unlike the CLI's `db run --waves --non-interactive`, which raises
        VF_NON_INTERACTIVE_VIEWER_DISABLED for a human who typed
        conflicting flags on purpose).
    non_interactive : bool
        When True, forces waves=False rather than raising -- automated
        callers should not need to reason about this interaction.
    """
    tile_number = _validate_tile_number(tile)
    if non_interactive:
        waves = False

    from veriflow.commands.run import cmd_run

    return cmd_run(
        db=_normalize_path(db_path),
        tile_number=tile_number,
        skip_check=skip_connectivity,
        skip_sim=skip_sim,
        skip_synth=skip_synth,
        only_check=only_connectivity,
        only_sim=only_sim,
        only_synth=only_synth,
        waves=waves,
    )


def project_run(config_path: str | Path) -> dict:
    """Run Project Mode's verification pipeline end-to-end and return the
    resulting results.json as a dict.

    Equivalent to `ProjectWorkflow.from_file(config_path).run()` followed by
    `get_project_run_result(run_dir)`, in one call. This is the simplest
    entry point for "I have a `.v` file and a `veriflow.yaml`, verify it" --
    no database, no tiles, nothing to create beforehand.

    Status "FAIL" means the RTL did not pass verification -- it is returned
    as data, not raised (same pattern as run_tile). VeriFlowError propagates
    unchanged for configuration-level errors (malformed veriflow.yaml,
    missing RTL sources, unregistered interface/technology names, etc.).
    """
    from veriflow.workflows.project import ProjectWorkflow

    pr = ProjectWorkflow.from_file(_normalize_path(config_path)).run()
    return get_project_run_result(pr.run_dir)


def wrap_init(
    interface_name: str,
    rtl_file: str | Path,
    *,
    wrapper_name: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Scaffold a wrapper config dict from a single RTL file.

    Reads *rtl_file* and auto-detects the top module name (requires exactly
    one module declaration in the file). Extracts IP ports and returns a
    dict matching the wrapper_config.yaml schema, plus a "detected_ports"
    key: [{"name": str, "direction": str, "width": int | null}] (width is
    null when it depends on an unresolved parameter, e.g. `[W-1:0]`).
    Does NOT write any files.

    Raises:
        VeriFlowError(VF_INTERFACE_UNKNOWN)              -- interface not registered
        VeriFlowError(VF_WRAP_E_NO_MODULE_FOUND)         -- file has no module declaration
        VeriFlowError(VF_WRAP_E_MULTIPLE_MODULES_FOUND)  -- file has 2+ module declarations
    """
    import re
    from veriflow.core.wrapper.port_parser import extract_ports
    from veriflow.models.interface_profile import get_interface_profile

    # Validate interface_name early -- raises VF_INTERFACE_UNKNOWN if not registered
    get_interface_profile(interface_name)

    rtl_path = Path(rtl_file)
    if not rtl_path.exists():
        raise VeriFlowError(
            f"RTL file not found: {rtl_path}",
            code="VF_WRAP_RTL_FILE_NOT_FOUND",
            details={"path": str(rtl_path)},
        )
    text = rtl_path.read_text(encoding="utf-8")

    # Auto-detect module name from the file
    module_re = re.compile(r"\bmodule\s+(\w+)", re.IGNORECASE)
    found = module_re.findall(text)
    seen: set = set()
    modules: list = []
    for name in found:
        if name not in seen:
            seen.add(name)
            modules.append(name)

    if len(modules) == 0:
        raise VeriFlowError(
            f"No module declaration found in {rtl_path}.",
            code="VF_WRAP_E_NO_MODULE_FOUND",
            details={"rtl_file": str(rtl_path)},
        )
    if len(modules) > 1:
        raise VeriFlowError(
            f"Multiple module declarations found in {rtl_path}: "
            f"{', '.join(modules)}. "
            "Auto-detection requires exactly one module per file. "
            "Move the top module to its own file before running wrap init.",
            code="VF_WRAP_E_MULTIPLE_MODULES_FOUND",
            details={"rtl_file": str(rtl_path), "modules": modules},
        )

    top_module = modules[0]
    ip_ports = extract_ports(text, top_module)
    meta = dict(metadata) if metadata else {}

    return {
        "interface_name": interface_name,
        "metadata": {
            "name": meta.get("name", top_module),
            "author": meta.get("author", ""),
            "description": meta.get("description", ""),
            "version": meta.get("version", "1.0.0"),
        },
        "design": {
            "top_module": top_module,
            "rtl_sources": [str(rtl_path)],
        },
        "wrapper_name": wrapper_name or f"{top_module}_wrapper",
        "ports": {name: None for name, _, _ in ip_ports},
        "detected_ports": [
            {"name": name, "direction": direction, "width": width}
            for name, direction, width in ip_ports
        ],
    }


def wrap_generate(
    config_path: str | Path,
    out_dir: str | Path | None = None,
) -> dict:
    """Run veriflow wrap generate for *config_path*.

    Returns the full output dict (schema_version, status, ports, …).
    VeriFlowError propagates unchanged for config-level errors (missing
    interface_name, top_module not found in RTL, etc.).
    Validation FAIL is returned as a dict with status="FAIL" — not raised.
    """
    from veriflow.workflows.wrap import WrapWorkflow

    return WrapWorkflow().generate(
        config_path=Path(config_path),
        out_dir=Path(out_dir) if out_dir is not None else None,
    )


def get_project_run_result(run_dir: str | Path) -> dict:
    """Read and return the results.json for a Project Mode run.

    Parameters
    ----------
    run_dir : str | Path
        Path to the run directory (e.g. "runs/run-001"), as produced by
        `veriflow project run` / `ProjectWorkflow.run()`.

    Raises:
        VeriFlowError(VF_PROJECT_RUN_RESULT_NOT_FOUND) -- results.json missing
        VeriFlowError(VF_PROJECT_RUN_RESULT_CORRUPT)    -- results.json exists
            but is not valid JSON (e.g. a run interrupted mid-write)
    """
    import json

    run_dir = _normalize_path(run_dir)
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise VeriFlowError(
            f"results.json not found for run: {run_dir}",
            code="VF_PROJECT_RUN_RESULT_NOT_FOUND",
            details={"run_dir": str(run_dir), "path": str(results_path)},
        )
    try:
        return json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VeriFlowError(
            f"results.json is not valid JSON for run: {run_dir}\n  {exc}",
            code="VF_PROJECT_RUN_RESULT_CORRUPT",
            details={"run_dir": str(run_dir), "path": str(results_path)},
        ) from exc


def _find_latest_passing_run(runs_dir: Path) -> tuple[str | None, dict | None]:
    """Return (run_id, results_dict) for the highest-numbered run-NNN under
    runs_dir whose results.json has status == "PASS", or (None, None)."""
    import json
    import re

    if not runs_dir.exists():
        return None, None

    pattern = re.compile(r"^run-(\d{3})$")
    numbered = []
    for entry in runs_dir.iterdir():
        if entry.is_dir():
            m = pattern.match(entry.name)
            if m:
                numbered.append((int(m.group(1)), entry.name))
    numbered.sort(reverse=True)

    for _, run_name in numbered:
        results_path = runs_dir / run_name / "results.json"
        if not results_path.exists():
            continue
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") == "PASS":
            return run_name, data

    return None, None


def project_import(
    config_path: str | Path,
    db_path: str | Path,
    *,
    run_id: str | None = None,
) -> dict:
    """Import a verified Project Mode run into a Database Mode database as a
    new tile.

    Copies the RTL (and, if present, testbench) sources recorded in the
    chosen run's results.json into the new tile's src/rtl and src/tb, and
    copies results.json itself to config/tile_NNNN/imported_run.json for
    traceability (rtl_hash, timestamp, exact stage statuses of the run that
    was imported).

    Parameters
    ----------
    config_path : str | Path
        Path to the Project Mode veriflow.yaml.
    db_path : str | Path
        Path to the destination VeriFlow database directory.
    run_id : str | None
        Specific run to import (e.g. "run-003"). If None, imports the
        highest-numbered run under runs_dir whose results.json reports
        status "PASS".

    Raises:
        VeriFlowError(VF_IMPORT_NO_PASSING_RUN)      -- run_id is None and no run has status PASS
        VeriFlowError(VF_IMPORT_RUN_NOT_FOUND)        -- run_id given but missing / no results.json
        VeriFlowError(VF_IMPORT_RUN_NOT_PASSING)      -- run_id given but its status != PASS
        VeriFlowError(VF_IMPORT_INTERFACE_MISMATCH)   -- project's interface_name != database's
        VeriFlowError(VF_DATABASE_CONFIG_YAML_ERROR)  -- destination project_config.yaml is malformed
        VeriFlowError(VF_IMPORT_RTL_SOURCE_MISSING)   -- a recorded RTL/TB source no longer exists on disk
    """
    import shutil

    import yaml

    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.validator import validate_database
    from veriflow.models.project_config import ProjectConfig
    from veriflow.models.tile_config import DEFAULT_TB_TOP_MODULE
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    config_path = Path(config_path).resolve()
    db_path = Path(db_path).resolve()

    # a. Load the Project Mode config
    project_config = ProjectWorkflowConfig.from_file(config_path)
    runs_dir = project_config.runs_dir

    # b. Determine which run to import
    if run_id is None:
        found_run_id, results = _find_latest_passing_run(runs_dir)
        if found_run_id is None:
            raise VeriFlowError(
                f"No passing run found under {runs_dir}. "
                "Run 'veriflow project run' until a run reports status PASS "
                "before importing.",
                code="VF_IMPORT_NO_PASSING_RUN",
                details={"runs_dir": str(runs_dir)},
            )
        run_id = found_run_id
    else:
        results_path = runs_dir / run_id / "results.json"
        if not results_path.exists():
            raise VeriFlowError(
                f"Run {run_id!r} not found (or has no results.json) under {runs_dir}",
                code="VF_IMPORT_RUN_NOT_FOUND",
                details={"run_id": run_id, "runs_dir": str(runs_dir)},
            )
        results = get_project_run_result(runs_dir / run_id)
        if results.get("status") != "PASS":
            raise VeriFlowError(
                f"Run {run_id!r} has status {results.get('status')!r}, not PASS. "
                "Only a passing run can be imported.",
                code="VF_IMPORT_RUN_NOT_PASSING",
                details={"run_id": run_id, "status": results.get("status")},
            )

    # d. Interface compatibility check
    validate_database(db_path)
    db_project_cfg_path = db_path / "project_config.yaml"
    try:
        db_raw = yaml.safe_load(db_project_cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise VeriFlowError(
            f"YAML parse error in {db_project_cfg_path}:\n  {exc}",
            code="VF_DATABASE_CONFIG_YAML_ERROR",
            details={"path": str(db_project_cfg_path)},
        ) from exc
    db_project_config = ProjectConfig.from_dict(db_raw, root=db_path)

    project_interface_name = results.get("interface_name")
    if project_interface_name is not None and project_interface_name != db_project_config.interface_name:
        raise VeriFlowError(
            f"Interface mismatch: the imported run uses interface_name="
            f"{project_interface_name!r}, but the database's project_config.yaml "
            f"declares interface_name={db_project_config.interface_name!r}.",
            code="VF_IMPORT_INTERFACE_MISMATCH",
            details={
                "project_interface_name": project_interface_name,
                "db_interface_name": db_project_config.interface_name,
            },
        )

    # e. Create the tile and copy sources into it
    top_module = results["top_module"]
    tile_info = cmd_create_tile(db_path, top_module=top_module)
    tile_number_str = tile_info["tile_number"]
    tile_id = tile_info["tile_id"]

    config_tile_dir = db_path / "config" / f"tile_{tile_number_str}"
    rtl_dir = config_tile_dir / "src" / "rtl"
    tb_dir = config_tile_dir / "src" / "tb"
    project_root = config_path.parent

    for rel in results.get("rtl_sources") or []:
        src = (project_root / rel).resolve()
        try:
            shutil.copy2(src, rtl_dir / Path(rel).name)
        except FileNotFoundError as exc:
            raise VeriFlowError(
                f"RTL source file no longer exists: {src}\n"
                f"  Recorded in {run_id!r}'s results.json but missing on disk -- "
                "was it moved or deleted after the run completed?",
                code="VF_IMPORT_RTL_SOURCE_MISSING",
                details={"path": str(src), "run_id": run_id},
            ) from exc

    tb_sources = results.get("tb_sources") or []
    if tb_sources:
        # Importing a project's own already-complete, verified testbench --
        # remove the auto-generated tb_tile.v placeholder scaffold first so
        # the copied-in files are the sole (and only) testbench, avoiding a
        # `module tb;` name collision between the two during simulation.
        placeholder = tb_dir / "tb_tile.v"
        if placeholder.exists():
            placeholder.unlink()
        for rel in tb_sources:
            src = (project_root / rel).resolve()
            try:
                shutil.copy2(src, tb_dir / Path(rel).name)
            except FileNotFoundError as exc:
                raise VeriFlowError(
                    f"Testbench source file no longer exists: {src}\n"
                    f"  Recorded in {run_id!r}'s results.json but missing on disk -- "
                    "was it moved or deleted after the run completed?",
                    code="VF_IMPORT_RTL_SOURCE_MISSING",
                    details={"path": str(src), "run_id": run_id},
                ) from exc

    # Prefill tile_config.yaml: tile_name (project directory name), top_module
    # (already set by cmd_create_tile), and tb_top_module if the project
    # declares one. results.json's schema has no simulation.tb_top field, so
    # this comes from the just-loaded ProjectWorkflowConfig instead.
    tile_cfg_path = config_tile_dir / "tile_config.yaml"
    tile_cfg_text = tile_cfg_path.read_text(encoding="utf-8")
    tile_cfg_text = tile_cfg_text.replace('tile_name: ""', f'tile_name: "{project_root.name}"')
    if project_config.tb_top:
        tile_cfg_text = tile_cfg_text.replace(
            f'tb_top_module: "{DEFAULT_TB_TOP_MODULE}"',
            f'tb_top_module: "{project_config.tb_top}"',
        )
    tile_cfg_path.write_text(tile_cfg_text, encoding="utf-8")

    # f. Copy results.json -> imported_run.json for traceability
    shutil.copy2(runs_dir / run_id / "results.json", config_tile_dir / "imported_run.json")

    # g. Summary
    return {
        "tile_id": tile_id,
        "tile_number": tile_number_str,
        "db_path": str(db_path),
        "config_path": str(config_path),
        "run_id": run_id,
        "rtl_hash": results.get("rtl_hash", {}),
    }


def list_interface_profiles() -> list[dict]:
    """List every registered interface profile with its port contract.

    Lets an agent pick a valid `interface_name` for a project config
    without guessing or triggering VF_INTERFACE_UNKNOWN. Includes both
    built-in profiles (currently just "semicolab") and any registered at
    runtime via interface.definition/interface_definition earlier in the
    same process.
    """
    from veriflow.models.interface_profile import list_interface_profiles as _list_interface_profiles

    return [
        {
            "name": profile.name,
            "description": profile.description,
            "requires_top_module": profile.requires_top_module,
            "ports": [
                {"name": port.name, "direction": port.direction, "width": port.width}
                for port in profile.ports
            ],
        }
        for profile in _list_interface_profiles()
    ]


def list_technology_profiles() -> list[dict]:
    """List every registered technology with its synthesis backend and
    current PDK/liberty resolution status.

    Lets an agent pick a valid `technology.name` for a project config
    without guessing or triggering VF_TECHNOLOGY_UNKNOWN. A technology with
    no installable PDK (e.g. "generic") always reports pdk_installed=True
    ("no PDK required") -- same convention as `veriflow doctor`'s
    [TECHNOLOGIES] section.
    """
    from veriflow.models.pdk_manager import get_liberty_path
    from veriflow.models.technology_profile import get_technology_profile, list_technology_profile_names

    technologies: list[dict] = []
    for name in list_technology_profile_names():
        technology = get_technology_profile(name)
        if technology.liberty:
            liberty_path = technology.liberty
        elif technology.install_method is not None:
            resolved = get_liberty_path(name)
            liberty_path = str(resolved) if resolved else None
        else:
            liberty_path = None
        technologies.append({
            "name": technology.name,
            "description": technology.description,
            "synthesis_backend": technology.synthesis_backend,
            "pdk_installed": technology.install_method is None or liberty_path is not None,
            "liberty_path": liberty_path,
        })
    return technologies


def list_pdks() -> list[dict]:
    """List installation status for every registered technology's PDK.

    Wraps the same resolution logic as `veriflow pdk list`
    (commands/pdk.py) and `veriflow doctor`'s [TECHNOLOGIES] section, but
    with a flat two-value status ("installed" | "not_installed") instead of
    the CLI's three-value tier -- from an agent's perspective, a PDK
    directory that exists but has no resolvable liberty file is not usable
    for synthesis mapping either way.
    """
    from veriflow.models.pdk_manager import get_liberty_path
    from veriflow.models.technology_profile import get_technology_profile, list_technology_profile_names

    pdks: list[dict] = []
    for name in list_technology_profile_names():
        technology = get_technology_profile(name)
        if technology.install_method is None:
            pdks.append({"name": name, "status": "installed", "liberty_path": None, "install_hint": None})
            continue
        liberty_path = get_liberty_path(name)
        if liberty_path is not None:
            pdks.append({
                "name": name,
                "status": "installed",
                "liberty_path": str(liberty_path),
                "install_hint": None,
            })
        else:
            pdks.append({
                "name": name,
                "status": "not_installed",
                "liberty_path": None,
                "install_hint": technology.install_hint or f"veriflow pdk install {name}",
            })
    return pdks


def db_list_tiles(db_path: str | Path) -> list[dict]:
    """List all tiles registered in a Database Mode database.

    Read-only -- never writes files, never re-runs anything. Returns an
    empty list if the database has no tiles yet (or tile_index.csv is
    missing, same as the underlying DatabaseWorkflow.list_tiles()).
    """
    from veriflow.workflows.database import DatabaseWorkflow

    tiles = DatabaseWorkflow(_normalize_path(db_path)).list_tiles()
    return [
        {
            "tile_number": t.tile_number,
            "tile_id": t.tile_id,
            "tile_name": t.tile_name,
            "tile_author": t.tile_author,
            "version": t.version,
            "revision": t.revision,
            "interface": t.interface_name,
        }
        for t in tiles
    ]


def db_list_runs(db_path: str | Path, tile: str | int) -> list[dict]:
    """List all runs for one tile, in ascending run-number order.

    Read-only. Raises VeriFlowError(VF_TILE_NUMBER_INVALID) if *tile* is
    not convertible to an integer, VeriFlowError(VF_DATABASE_TILE_NOT_FOUND)
    if the tile doesn't exist.
    """
    from veriflow.workflows.database import DatabaseWorkflow

    tile_number = _validate_tile_number(tile)
    runs = DatabaseWorkflow(_normalize_path(db_path)).list_runs(tile_number=tile_number)
    return [
        {
            "run_id": r.run_id,
            "status": r.status,
            "date": r.date,
            "has_waves": r.wave_path is not None,
        }
        for r in runs
    ]


def db_get_run(db_path: str | Path, tile: str | int, run: str | int) -> dict:
    """Read a specific run's persisted result without re-executing anything.

    Same dict shape as `run_tile()`'s return value (results.json,
    schema_version "1.2"). *run* accepts a bare number ("3" / 3, normalized
    to "run-003") or an already-formatted run id ("run-003").

    Raises VeriFlowError(VF_TILE_NUMBER_INVALID) if *tile* is not
    convertible to an integer, VeriFlowError(VF_DATABASE_RUN_RESULT_MISSING)
    if the run has no results.json yet.
    """
    from veriflow.workflows.database import DatabaseWorkflow

    tile_number = _validate_tile_number(tile)
    result = DatabaseWorkflow(_normalize_path(db_path)).load_run_result(
        tile_number=tile_number, run_id=str(run)
    )
    return result.to_dict()


def project_set(config_path: str | Path, key: str, value: str) -> dict:
    """Modify a field in veriflow.yaml (Project Mode) without hand-editing
    YAML -- comments and formatting elsewhere in the file are preserved.

    Returns {"key": key, "value": value, "config": str(config_path)}.

    Supported keys: interface, technology, top-module, pipeline, runs-dir.
    Raises VeriFlowError(VF_SET_KEY_UNKNOWN) for an unsupported key,
    VeriFlowError(VF_SET_INTERFACE_INVALID) / VF_TECHNOLOGY_UNKNOWN /
    VF_PIPELINE_STAGE_UNKNOWN for an invalid value, or
    VeriFlowError(VF_PROJECT_CONFIG_NOT_FOUND) if config_path doesn't exist.
    """
    from veriflow.commands.set_config import project_set_config

    return project_set_config(_normalize_path(config_path), key, value)


def db_set(db_path: str | Path, key: str, value: str) -> dict:
    """Modify a field in db_path/project_config.yaml (Database Mode)
    without hand-editing YAML -- comments and formatting are preserved.

    Returns {"key": key, "value": value, "config": str(config_path)}.

    Supported keys: interface, technology, id-format, prefix, shuttle,
    pipeline. Raises VeriFlowError(VF_SET_KEY_UNKNOWN) for an unsupported
    key, or a value-specific code (VF_SET_INTERFACE_INVALID,
    VF_TECHNOLOGY_UNKNOWN, VF_ID_FORMAT_INVALID, VF_PIPELINE_STAGE_UNKNOWN)
    for an invalid value.
    """
    from veriflow.commands.set_config import db_set_config

    return db_set_config(_normalize_path(db_path), key, value)


def db_tile_set(db_path: str | Path, tile: str | int, key: str, value: str) -> dict:
    """Modify a field in a tile's tile_config.yaml (Database Mode) without
    hand-editing YAML -- comments and formatting are preserved.

    Returns {"key": key, "value": value, "tile": tile_number_str, "config": ...}.

    Supported keys: top-module, tb-top, name, author, description, tags,
    objective, pipeline. Raises VeriFlowError(VF_TILE_NUMBER_INVALID) if
    *tile* isn't numeric, VeriFlowError(VF_TILE_CONFIG_NOT_FOUND) if the
    tile doesn't exist, VeriFlowError(VF_SET_KEY_UNKNOWN) for an
    unsupported key.
    """
    from veriflow.commands.set_config import db_tile_set_config

    return db_tile_set_config(_normalize_path(db_path), tile, key, value)
