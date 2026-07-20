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
    source_repo: str | None = None,
    source_branch: str | None = None,
    force: bool = False,
) -> dict:
    """Import a verified Project Mode run into a Database Mode database as a
    new tile.

    Copies the RTL (and, if present, testbench) sources recorded in the
    chosen run's results.json into the new tile's src/rtl and src/tb, and
    copies results.json itself to config/tile_NNNN/imported_run.json for
    traceability (rtl_hash, timestamp, exact stage statuses of the run that
    was imported).

    source_repo/source_branch are recorded onto imported_run.json (in
    addition to copying results.json) only when the caller is `import_repo()`
    -- direct Project Mode imports (`veriflow project import`) have no repo
    URL and leave them out entirely, so `imported_run.json` for those is a
    byte-for-byte copy of results.json as before. This is how `import_repo()`
    later detects "this repo+branch was already imported" (VF_IMPORT_REPO_ALREADY_IMPORTED).

    A technology mismatch between the source project and the destination
    database does not block the import (unlike an interface mismatch, which
    changes the port list and would silently break simulation): the returned
    dict's "warnings" list gets an entry instead, since the tile can simply
    be re-synthesized against the destination's technology on the next `db
    run`.

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

    force, when True, downgrades VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE
    (below) from an error to a warning appended to the returned dict's
    "warnings" list, letting the import proceed anyway. It does not affect
    VF_IMPORT_INTERFACE_MISMATCH -- two *declared but different* interfaces
    is never something force can paper over.

    Raises:
        VeriFlowError(VF_IMPORT_NO_PASSING_RUN)      -- run_id is None and no run has status PASS
        VeriFlowError(VF_IMPORT_RUN_NOT_FOUND)        -- run_id given but missing / no results.json
        VeriFlowError(VF_IMPORT_RUN_NOT_PASSING)      -- run_id given but its status != PASS
        VeriFlowError(VF_IMPORT_INTERFACE_MISMATCH)   -- project's interface_name != database's (both declared)
        VeriFlowError(VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE) -- project has no interface, database requires one, force=False
        VeriFlowError(VF_DATABASE_CONFIG_YAML_ERROR)  -- destination project_config.yaml is malformed
        VeriFlowError(VF_IMPORT_RTL_SOURCE_MISSING)   -- a recorded RTL/TB source no longer exists on disk
        VeriFlowError(VF_IMPORT_TOP_MODULE_NOT_IN_SOURCES) -- no recorded RTL source declares `module <top_module>`
    """
    import json
    import re
    import shutil

    import yaml

    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.validator import validate_database
    from veriflow.models.project_config import ProjectConfig
    from veriflow.models.tile_config import DEFAULT_TB_TOP_MODULE
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    config_path = Path(config_path).resolve()
    db_path = Path(db_path).resolve()

    # a. Load the Project Mode config -- only runs_dir/tb_top are used below,
    # not rtl_sources (the run's own recorded sources are what matter, and
    # a missing one is reported as VF_IMPORT_RTL_SOURCE_MISSING further
    # down, not a live-config check here).
    project_config = ProjectWorkflowConfig.from_file(config_path, validate_rtl_sources=False)
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

    warnings_list: list[str] = []

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

    # d.1b Generic project imported into an interface-requiring database --
    # symmetric to the mismatch check above: "no interface declared" is
    # itself incompatible when the destination requires one specific
    # interface, since the RTL was never verified against that port
    # contract. Unlike a technology mismatch (below), this isn't recoverable
    # by just re-running something -- the tile's first `db run` connectivity
    # check will simply fail against a contract the RTL was never checked
    # against. Blocks by default; force=True downgrades to a warning.
    if project_interface_name is None and db_project_config.interface_name is not None:
        if not force:
            raise VeriFlowError(
                "Source project has no interface configured (generic), but "
                "destination database requires interface "
                f"{db_project_config.interface_name!r}. The imported tile "
                "would fail its first db run. Configure the source project "
                "with 'veriflow project set interface "
                f"{db_project_config.interface_name}' (and ensure it passes "
                "project run) before importing, or use --force to import "
                "anyway (not recommended).",
                code="VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE",
                details={"db_interface_name": db_project_config.interface_name},
            )
        warnings_list.append(
            "WARNING: tile imported as generic but database requires "
            f"'{db_project_config.interface_name}' -- db run will likely "
            "fail until the RTL is verified against this interface."
        )

    # d.2 Technology comparison (Gotcha B) -- warn, don't block. Unlike
    # interface (which changes the port list and would silently break
    # simulation if mismatched), technology only selects the synthesis
    # backend/liberty file, so a mismatch is recoverable: the tile just gets
    # re-synthesized against the destination's technology on the next `db
    # run`. Prefer the actual technology the synthesis stage ran against
    # (results["stages"]["synthesis"]["technology"], only present if that
    # stage ran and reported one); fall back to the source veriflow.yaml's
    # configured technology (results["technology"], always present) when it
    # didn't. Only compared when the destination database actually declares
    # a technology -- a database with no `technology:` section in
    # project_config.yaml imposes no constraint at all.
    project_technology_name = (
        results.get("stages", {}).get("synthesis", {}).get("technology")
        or results.get("technology")
    )
    if (
        db_project_config.technology_name is not None
        and project_technology_name is not None
        and project_technology_name != db_project_config.technology_name
    ):
        warnings_list.append(
            f"Source project was verified against technology "
            f"'{project_technology_name}' but destination database uses "
            f"'{db_project_config.technology_name}' — tile will be "
            f"re-synthesized against '{db_project_config.technology_name}' "
            "on next db run."
        )

    # e. Create the tile and copy sources into it
    top_module = results["top_module"]
    tile_info = cmd_create_tile(db_path, top_module=top_module, silent=True)
    tile_number_str = tile_info["tile_number"]
    tile_id = tile_info["tile_id"]

    config_tile_dir = db_path / "config" / f"tile_{tile_number_str}"
    rtl_dir = config_tile_dir / "src" / "rtl"
    tb_dir = config_tile_dir / "src" / "tb"
    project_root = config_path.parent

    # e.2 RTL filename vs top_module (Gotcha A): Database Mode's sim/synth
    # runners locate the top-level file by filename convention
    # (<top_module>.v), while Project Mode only cares about the `module
    # <top_module>` declaration inside the file's text -- a project whose
    # top-level file isn't literally named `<top_module>.v` passes `project
    # run` fine but would silently break once imported. Rename the file that
    # actually declares the module on copy rather than requiring the source
    # project to be renamed.
    rtl_sources = results.get("rtl_sources") or []
    expected_rtl_filename = f"{top_module}.v"
    rename_source_rel = None
    if not any(Path(rel).name == expected_rtl_filename for rel in rtl_sources):
        module_re = re.compile(r"\bmodule\s+" + re.escape(top_module) + r"\b")
        for rel in rtl_sources:
            src = (project_root / rel).resolve()
            if src.exists() and module_re.search(src.read_text(encoding="utf-8", errors="ignore")):
                rename_source_rel = rel
                break
        if rename_source_rel is None:
            raise VeriFlowError(
                f"None of the recorded RTL sources declare `module {top_module}`. "
                f"Expected a file named {expected_rtl_filename!r}, or one "
                f"containing `module {top_module}`.",
                code="VF_IMPORT_TOP_MODULE_NOT_IN_SOURCES",
                details={"top_module": top_module, "rtl_sources": rtl_sources},
            )
        warnings_list.append(
            f"Renamed '{Path(rename_source_rel).name}' to "
            f"'{expected_rtl_filename}' for Database Mode compatibility."
        )

    for rel in rtl_sources:
        src = (project_root / rel).resolve()
        dest_name = expected_rtl_filename if rel == rename_source_rel else Path(rel).name
        try:
            shutil.copy2(src, rtl_dir / dest_name)
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

    # Prefill tile_config.yaml: tile_name (metadata.name if the source
    # project set one, else the project directory name as before),
    # tile_author/description from metadata.author/metadata.description if
    # set, top_module (already set by cmd_create_tile), and tb_top_module if
    # the project declares one. results.json's schema has no simulation.tb_top
    # field, so that one comes from the just-loaded ProjectWorkflowConfig
    # instead -- metadata isn't modeled by ProjectWorkflowConfig at all (same
    # as _readme_render_context()), so it's read directly from the source
    # veriflow.yaml here, same raw-YAML-read pattern.
    source_raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    source_metadata = source_raw.get("metadata") or {}
    metadata_name = (source_metadata.get("name") or "").strip()
    metadata_author = (source_metadata.get("author") or "").strip()
    metadata_description = (source_metadata.get("description") or "").strip()

    tile_cfg_path = config_tile_dir / "tile_config.yaml"
    tile_cfg_text = tile_cfg_path.read_text(encoding="utf-8")
    tile_cfg_text = tile_cfg_text.replace(
        'tile_name: ""', f'tile_name: "{metadata_name or project_root.name}"'
    )
    if metadata_author:
        tile_cfg_text = tile_cfg_text.replace('tile_author: ""', f'tile_author: "{metadata_author}"')
    if metadata_description:
        description_lines = "\n".join(f"  {ln}" for ln in metadata_description.splitlines())
        tile_cfg_text = tile_cfg_text.replace(
            "description: |\n  # What does this tile do?",
            f"description: |\n{description_lines}",
        )
    if project_config.tb_top:
        tile_cfg_text = tile_cfg_text.replace(
            f'tb_top_module: "{DEFAULT_TB_TOP_MODULE}"',
            f'tb_top_module: "{project_config.tb_top}"',
        )
    tile_cfg_path.write_text(tile_cfg_text, encoding="utf-8")

    # f. Copy results.json -> imported_run.json for traceability (plus
    # source_repo/source_branch when imported via `db import-repo`)
    imported_run_path = config_tile_dir / "imported_run.json"
    if source_repo is not None:
        run_data = json.loads((runs_dir / run_id / "results.json").read_text(encoding="utf-8"))
        run_data["source_repo"] = source_repo
        run_data["source_branch"] = source_branch
        imported_run_path.write_text(
            json.dumps(run_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    else:
        shutil.copy2(runs_dir / run_id / "results.json", imported_run_path)

    # g. Summary
    return {
        "tile_id": tile_id,
        "tile_number": tile_number_str,
        "db_path": str(db_path),
        "config_path": str(config_path),
        "run_id": run_id,
        "rtl_hash": results.get("rtl_hash", {}),
        "warnings": warnings_list,
    }


def _find_prior_import(db_path: Path, repo_url: str, branch: str) -> str | None:
    """Return the tile_id of an existing tile whose imported_run.json
    records the same source_repo+source_branch, or None.

    Only tiles created by `import_repo()` have these fields at all (a plain
    `veriflow project import` or a manually created tile's imported_run.json
    has neither) -- those are simply never a match.
    """
    import json

    from veriflow.core.csv_store import get_tile_row

    config_dir = db_path / "config"
    if not config_dir.is_dir():
        return None

    tile_index_path = db_path / "tile_index.csv"

    for tile_dir in sorted(config_dir.glob("tile_*")):
        imported_run_path = tile_dir / "imported_run.json"
        if not imported_run_path.is_file():
            continue
        try:
            data = json.loads(imported_run_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("source_repo") == repo_url and data.get("source_branch") == branch:
            tile_number = tile_dir.name.removeprefix("tile_")
            try:
                row = get_tile_row(tile_index_path, tile_number)
            except VeriFlowError:
                row = None
            return (row or {}).get("tile_id") or tile_number

    return None


def import_repo(
    repo_url: str,
    db_path: str | Path,
    *,
    branch: str = "main",
    config_path: str = "veriflow.yaml",
    force: bool = False,
) -> dict:
    """Clone a git repo, run its own `project run` as a real precheck, and
    import the result into a Database Mode database as a new tile -- for
    shuttle organizers importing directly from a contributor's repo rather
    than a local checkout they already cloned themselves.

    Flow: clone repo_url (given branch, --depth 1) into a fresh temp dir ->
    look for config_path at the clone's root -> run it for real (this IS the
    precheck, not a dry run) -> on status PASS, `project_import()` the
    result -> always remove the temp dir, success or failure.

    Duplicate-import guard: before doing any of that, checks whether
    repo_url+branch was already imported into this database (by scanning
    existing tiles' imported_run.json for a matching source_repo/
    source_branch, written by a prior `import_repo()` call -- see
    `project_import()`'s source_repo parameter). Checked first, before
    cloning, so a rejected duplicate doesn't pay for a clone+run it can't
    use. If found and force=False, raises VF_IMPORT_REPO_ALREADY_IMPORTED
    naming the existing tile. If found and force=True, proceeds normally --
    a new tile is created (the existing one is left untouched, never
    overwritten). This check is independent of the precheck below: force
    never lets a failing `project run` through -- that gate is
    `project_import()`'s own PASS-only requirement, unchanged.

    Parameters
    ----------
    repo_url : str
        Anything `git clone` accepts (https URL, ssh URL, or a local path).
    db_path : str | Path
        Path to the destination VeriFlow database directory.
    branch : str
        Branch to clone (default "main").
    config_path : str
        Path to the Project Mode veriflow.yaml, relative to the repo's root
        (default "veriflow.yaml").
    force : bool
        Passed straight through to `project_import()` in addition to its
        own two uses here:
        - Re-import repo_url+branch even if already imported into this
          database (creates another, separate tile).
        - Downgrade VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE (a generic repo
          cloned into an interface-requiring database) to a warning instead
          of blocking the import.
        Does not affect the precheck -- a failing `project run` is always
        rejected regardless, and never affects VF_IMPORT_INTERFACE_MISMATCH
        (two declared-but-different interfaces is never forceable).

    Raises:
        VeriFlowError(VF_IMPORT_REPO_ALREADY_IMPORTED)  -- repo_url+branch already imported, force=False
        VeriFlowError(VF_IMPORT_REPO_CLONE_FAILED)      -- git clone failed (bad URL/branch/network)
        VeriFlowError(VF_IMPORT_REPO_NO_CONFIG)         -- config_path missing at the repo's root
        VeriFlowError(VF_IMPORT_REPO_PRECHECK_FAILED)   -- project run status != PASS
        ... plus anything project_import() itself can raise (VF_IMPORT_INTERFACE_MISMATCH,
        VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE, etc.)
    """
    import shutil
    import subprocess
    import tempfile

    from veriflow.commands.pdk import _force_remove_readonly
    from veriflow.core.validator import validate_database

    db_path = Path(db_path).resolve()
    validate_database(db_path)

    prior_tile_id = _find_prior_import(db_path, repo_url, branch)
    if prior_tile_id is not None and not force:
        raise VeriFlowError(
            f"{repo_url!r} (branch {branch!r}) was already imported as tile "
            f"{prior_tile_id!r}. Use force=True (--force) to import it again "
            "as a new, separate tile.",
            code="VF_IMPORT_REPO_ALREADY_IMPORTED",
            details={"repo_url": repo_url, "branch": branch, "tile_id": prior_tile_id},
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="veriflow_import_"))
    try:
        clone_result = subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(tmp_dir)],
            capture_output=True,
            text=True,
        )
        if clone_result.returncode != 0:
            raise VeriFlowError(
                f"Failed to clone {repo_url!r} (branch {branch!r}):\n"
                f"  {clone_result.stderr.strip()}",
                code="VF_IMPORT_REPO_CLONE_FAILED",
                details={"repo_url": repo_url, "branch": branch, "stderr": clone_result.stderr},
            )

        cloned_config_path = tmp_dir / config_path
        if not cloned_config_path.is_file():
            raise VeriFlowError(
                f"{config_path!r} not found at the root of {repo_url!r} (branch {branch!r}).",
                code="VF_IMPORT_REPO_NO_CONFIG",
                details={"repo_url": repo_url, "branch": branch, "config_path": config_path},
            )

        run_result = project_run(cloned_config_path)
        if run_result.get("status") != "PASS":
            raise VeriFlowError(
                f"Precheck failed for {repo_url!r} (branch {branch!r}): "
                f"status={run_result.get('status')!r}. Only a passing "
                "'project run' can be imported.",
                code="VF_IMPORT_REPO_PRECHECK_FAILED",
                details={"repo_url": repo_url, "branch": branch, "run_result": run_result},
            )

        result = project_import(
            cloned_config_path, db_path,
            source_repo=repo_url, source_branch=branch, force=force,
        )
        result["source_repo"] = repo_url
        result["source_branch"] = branch
        return result
    finally:
        # plain ignore_errors=True silently leaves .git/objects behind --
        # git marks those files read-only on Windows, which raises
        # PermissionError inside rmtree; _force_remove_readonly clears the
        # attribute and retries instead of giving up (confirmed via a real
        # git clone left in %TEMP% until this fix was added).
        shutil.rmtree(tmp_dir, onerror=_force_remove_readonly)


_DEFAULT_README_TEMPLATE_PATH = Path(__file__).parent / "templates" / "submission_readme_template.j2"


def _readme_render_context(config, config_path: Path, results: dict) -> dict:
    """Build the Jinja2 render context for `generate_readme()`.

    Two distinct data sources, deliberately kept separate:

    - The *current* `veriflow.yaml` (via *config*, an already-loaded
      `ProjectWorkflowConfig`, plus a raw re-read for the `metadata:`
      section it doesn't model): `interface_name`, `interface_ports`,
      `interface_port_descriptions`, `technology`, and
      `description`/`author`/`version`/`tile_name`. These describe the
      project *as configured right now* -- e.g. after `veriflow project
      set interface semicolab`, the README reflects `semicolab`
      immediately, even if the last passing run predates that change and
      never actually verified it. `interface_port_descriptions` merges the
      interface profile's own `meta.yaml` port_descriptions (shared by
      every project using that interface) with veriflow.yaml's
      `interface.port_descriptions` (a per-project override/addition,
      taking precedence per port).
    - *results* (that run's results.json): everything else, spread in via
      `**results` -- `stages` (pass/fail per stage), `rtl_hash`,
      `timestamp`, `veriflow_version`. These describe what a specific run
      actually verified and can't be back-filled from the live config.

    repo_owner/repo_name are None (not a hardcoded "owner"/"repo" fallback)
    when GITHUB_REPOSITORY isn't set, so the default template can tell
    "running locally" apart from "actually in owner/repo" and skip
    rendering a badge that would 404."""
    import os
    import yaml

    from veriflow.models.interface_profile import get_interface_profile

    repo_owner, _, repo_name = os.environ.get("GITHUB_REPOSITORY", "").partition("/")
    if not repo_owner or not repo_name:
        repo_owner, repo_name = None, None

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    metadata = raw.get("metadata") or {}
    description = (metadata.get("description") or "").strip()
    author = (metadata.get("author") or "").strip()
    raw_version = metadata.get("version")
    version = str(raw_version).strip() if raw_version is not None else ""
    tile_name = (metadata.get("name") or "").strip() or results.get("top_module")

    interface_name = config.interface.name if config.interface else None
    interface_ports = []
    interface_port_descriptions: dict[str, str] = {}
    if interface_name:
        # config.interface.name is only ever set to a name that already
        # resolved successfully at config-load time (or raised
        # VF_INTERFACE_UNKNOWN there), so this can't raise here.
        profile = get_interface_profile(interface_name)
        interface_ports = [
            {"name": p.name, "direction": p.direction, "width": p.width}
            for p in profile.ports
        ]
        # port_descriptions: profile's own meta.yaml first (shared across
        # every project using this interface), then veriflow.yaml's
        # interface.port_descriptions overrides/adds on top, per port --
        # a project-specific note takes precedence over the generic one.
        if profile.port_descriptions:
            interface_port_descriptions.update(profile.port_descriptions)
        raw_interface_section = raw.get("interface")
        if isinstance(raw_interface_section, dict):
            raw_overrides = raw_interface_section.get("port_descriptions")
            if isinstance(raw_overrides, dict):
                interface_port_descriptions.update(
                    {str(k): str(v) for k, v in raw_overrides.items()}
                )

    technology = config.technology.name

    return {
        **results,
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "description": description,
        "author": author,
        "version": version,
        "tile_name": tile_name,
        "interface_name": interface_name,
        "interface_ports": interface_ports,
        "interface_port_descriptions": interface_port_descriptions,
        "technology": technology,
    }


def generate_readme(
    config_path: str | Path,
    out_path: str | Path | None = None,
    template_path: str | Path | None = None,
) -> str:
    """Render a submission README.md for the current project.

    interface_name/technology/metadata always reflect *config_path* (the
    current veriflow.yaml) as of this call, not whatever a past run saw --
    only run-verification facts (per-stage status, rtl_hash, timestamp,
    veriflow_version) come from the latest passing run's results.json. See
    `_readme_render_context()` for the full split.

    Parameters
    ----------
    config_path : str | Path
        Path to the Project Mode veriflow.yaml.
    out_path : str | Path | None
        Where to write the rendered README. Defaults to `README.md` in the
        same directory as *config_path*.
    template_path : str | Path | None
        Jinja2 template to render with. If None, uses `readme_template:`
        from *config_path* if set, else VeriFlow's built-in default
        (`veriflow/templates/submission_readme_template.j2`).

    Raises:
        VeriFlowError(VF_README_NO_PASSING_RUN) -- no run under runs_dir
            has status PASS.

    Returns the rendered README content as a string.
    """
    from jinja2 import Template

    from veriflow.workflows.project_config import ProjectWorkflowConfig

    config_path = Path(config_path).resolve()
    # rtl_sources is never read by this function -- it describes a past
    # run's verification facts plus the *current* interface/technology/
    # metadata, so a not-yet-created RTL file shouldn't block regenerating
    # the README.
    config = ProjectWorkflowConfig.from_file(config_path, validate_rtl_sources=False)

    run_id, results = _find_latest_passing_run(config.runs_dir)
    if run_id is None:
        raise VeriFlowError(
            f"No passing run found under {config.runs_dir}. "
            "Run 'veriflow project run' until a run reports status PASS "
            "before generating a README.",
            code="VF_README_NO_PASSING_RUN",
            details={"runs_dir": str(config.runs_dir)},
        )

    if template_path is not None:
        resolved_template = Path(template_path)
    elif config.readme_template is not None:
        resolved_template = config.readme_template
    else:
        resolved_template = _DEFAULT_README_TEMPLATE_PATH

    template = Template(
        resolved_template.read_text(encoding="utf-8"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    context = _readme_render_context(config, config_path, results)
    content = template.render(**context)

    resolved_out = Path(out_path).resolve() if out_path is not None else config.root / "README.md"
    resolved_out.write_text(content, encoding="utf-8")

    return content


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


def db_init(db_path: str | Path, *, force: bool = False) -> dict:
    """Initialize a new VeriFlow database (Database Mode) at *db_path*.

    Scaffolds `tiles/`, `config/`, `project_config.yaml`, `tile_index.csv`,
    and `records.csv`. Counterpart to `project_init()` -- Database Mode had
    no equivalent entry in `veriflow.api` before this (only
    `veriflow.commands.init_db.cmd_init`, outside the public API surface an
    agent/caller would normally look in -- dev-docs/MODE_CONSISTENCY_AUDIT.md,
    Finding 13).

    Returns {"db_path", "project_config", "tile_index", "records"} (all
    absolute paths, as strings). Raises VeriFlowError (no explicit code --
    same as the underlying `cmd_init`) if db_path already exists and force
    is False.
    """
    from veriflow.commands.init_db import cmd_init

    db = _normalize_path(db_path)
    cmd_init(db, force=force)

    return {
        "db_path": str(db),
        "project_config": str(db / "project_config.yaml"),
        "tile_index": str(db / "tile_index.csv"),
        "records": str(db / "records.csv"),
    }


def create_tile(
    db_path: str | Path, top_module: str | None = None, tile_author: str | None = None
) -> dict:
    """Create a new tile entry in a Database Mode database at *db_path*.

    Thin wrapper around `commands.create_tile.cmd_create_tile` (already a
    plain Python function, not a `cmd_*(args: argparse.Namespace)` --
    reused directly, not reimplemented). Counterpart to `project_init()` --
    Database Mode had no `veriflow.api` entry for tile creation before this
    (dev-docs/MODE_CONSISTENCY_AUDIT.md, Finding 13).

    top_module: RTL top module name. Required when the database's
    configured interface profile needs testbench scaffolding (raises
    VeriFlowError(VF_TILE_TOP_MODULE_REQUIRED) when missing).

    Returns {"tile_id", "tile_number", "path"} (`path`: the new tile's
    directory under `tiles/`, as a string).
    """
    from veriflow.commands.create_tile import cmd_create_tile

    db = _normalize_path(db_path)
    result = cmd_create_tile(db, top_module=top_module or "", tile_author=tile_author or "")

    return {
        "tile_id": result["tile_id"],
        "tile_number": result["tile_number"],
        "path": str(db / "tiles" / result["tile_id"]),
    }


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


def project_init(
    config_path: str | Path = "veriflow.yaml", *, top_module: str | None = None, force: bool = False
) -> dict:
    """Scaffold a new, commented veriflow.yaml (Project Mode) at
    *config_path*, optionally setting `design.top_module` in the same call.

    Returns {"config": str(config_path)} (plus "top_module" if it was set).
    Raises VeriFlowError(VF_PROJECT_CONFIG_EXISTS) if config_path already
    exists and force is False.
    """
    import argparse

    from veriflow.commands.init_project import cmd_init_project

    config_path = _normalize_path(config_path)
    cmd_init_project(argparse.Namespace(config=str(config_path), force=force))

    result: dict = {"config": str(config_path)}
    if top_module:
        from veriflow.commands.set_config import project_set_config

        project_set_config(config_path, "top-module", top_module)
        result["top_module"] = top_module
    return result


def project_set(config_path: str | Path, key: str, value: str) -> dict:
    """Modify a field in veriflow.yaml (Project Mode) without hand-editing
    YAML -- comments and formatting elsewhere in the file are preserved.

    Returns {"key": key, "value": value, "config": str(config_path)}.

    Supported keys: interface, technology, technology-strict (technology +
    require_pdk=true in one call), require-pdk, top-module, pipeline,
    stage-backend (override one stage's backend, e.g.
    "simulation:xsim", without touching the rest of the pipeline),
    runs-dir. Raises VeriFlowError(VF_SET_KEY_UNKNOWN) for an unsupported
    key, VeriFlowError(VF_SET_INTERFACE_INVALID) / VF_TECHNOLOGY_UNKNOWN /
    VF_PIPELINE_STAGE_UNKNOWN / VF_SET_STAGE_BACKEND_FORMAT_INVALID /
    VF_SET_STAGE_BACKEND_UNKNOWN / VF_STAGE_NOT_IN_PIPELINE for an invalid
    value, or VeriFlowError(VF_PROJECT_CONFIG_NOT_FOUND) if config_path
    doesn't exist.
    """
    from veriflow.commands.set_config import project_set_config

    return project_set_config(_normalize_path(config_path), key, value)


def db_set(db_path: str | Path, key: str, value: str) -> dict:
    """Modify a field in db_path/project_config.yaml (Database Mode)
    without hand-editing YAML -- comments and formatting are preserved.

    Returns {"key": key, "value": value, "config": str(config_path)}.

    Supported keys: interface, technology, technology-strict, require-pdk,
    id-format, prefix, shuttle, pipeline, stage-backend, project-name, repo,
    description. Raises
    VeriFlowError(VF_SET_KEY_UNKNOWN) for an unsupported key, or a
    value-specific code (VF_SET_INTERFACE_INVALID, VF_TECHNOLOGY_UNKNOWN,
    VF_ID_FORMAT_INVALID, VF_PIPELINE_STAGE_UNKNOWN,
    VF_SET_STAGE_BACKEND_FORMAT_INVALID, VF_SET_STAGE_BACKEND_UNKNOWN,
    VF_STAGE_NOT_IN_PIPELINE) for an invalid value.
    """
    from veriflow.commands.set_config import db_set_config

    return db_set_config(_normalize_path(db_path), key, value)


def db_tile_set(db_path: str | Path, tile: str | int, key: str, value: str) -> dict:
    """Modify a field in a tile's tile_config.yaml (Database Mode) without
    hand-editing YAML -- comments and formatting are preserved.

    Returns {"key": key, "value": value, "tile": tile_number_str, "config": ...}.

    Supported keys: top-module, tb-top, name, author, description, tags,
    objective, pipeline, stage-backend, require-pdk. No key sets a tile's
    technology *name* -- that's database-wide (see `db_set`); a tile can
    only override `require_pdk`. Raises VeriFlowError(VF_TILE_NUMBER_INVALID)
    if *tile* isn't numeric, VeriFlowError(VF_TILE_CONFIG_NOT_FOUND) if the
    tile doesn't exist, VeriFlowError(VF_SET_KEY_UNKNOWN) for an
    unsupported key.
    """
    from veriflow.commands.set_config import db_tile_set_config

    return db_tile_set_config(_normalize_path(db_path), tile, key, value)


def _default_veriflow_config_path() -> Path:
    """Same `--config` resolution rule as the CLI (`cli.py::_default_config_path`,
    duplicated here as a one-line default lookup, not the YAML-editing logic
    itself -- explicit --config/config_path always wins over this, this is
    only what's used when the caller passes config_path=None."""
    import os

    return Path(os.environ.get("VERIFLOW_CONFIG", "veriflow.yaml"))


def apply_spec(spec_path: str | Path, config_path: str | Path | None = None) -> dict:
    """Apply a `shuttle_spec.yaml` (a shuttle organizer's technology/
    interface/pipeline contract, see docs/PROJECT_CONFIG.md) onto a
    project's `veriflow.yaml`.

    Every field present in the spec is applied via the *same*
    `project_set_config()` (or, for the two fields it has no key for,
    `set_yaml_key()` directly) that `veriflow project set` itself uses --
    no separate YAML-writing logic, so behavior (comment preservation,
    validation, uncomment-in-place, etc.) is identical to setting each
    field by hand one at a time.

    Fields recognized in the spec:
      - `interface` (str | null): normally applied via
        `project_set_config(..., "interface", ...)` -- `null` clears it,
        same as `project set interface null`. **Except** when
        `interface_definition` is also set (below): a custom interface's
        name isn't registered yet, so it can't go through
        `project_set_config()`'s immediate registry validation -- both
        `interface.name` and `interface.definition` are then written
        directly via `set_yaml_key()`, mirroring hand-authoring
        `interface: {name: ..., definition: ...}` in veriflow.yaml
        (registration happens later, at config-load time).
      - `interface_definition` (str | null): only applied when non-null;
        see above for how it's written.
      - `technology` (str): applied via `project_set_config(...,
        "technology", ...)` -- unless `technology_definition` is also
        set, same reasoning and same direct-write treatment as
        `interface`/`interface_definition` above. `null`/absent is
        skipped either way -- Project Mode's technology has no "clear
        it" concept (it always defaults to "generic", never None), so
        there's nothing meaningful to apply.
      - `technology_definition` (str | null): only applied when non-null;
        see `technology` above.
      - `pipeline.stages` (list of `{"type": ...}` dicts): the stage
        types are joined into the same comma-separated string
        `project_set_config(..., "pipeline", ...)` already expects.
      - `shuttle_name` (str): informative only -- there is no field in
        `veriflow.yaml` for it (Project Mode has no shuttle concept;
        that's a Database Mode/`project_config.yaml` idea). Recorded in
        neither the file nor the returned dict, and surfaced as a
        `UserWarning` so it isn't silently dropped without a trace.

    Parameters
    ----------
    spec_path : str | Path
        Path to the `shuttle_spec.yaml` file to read.
    config_path : str | Path | None
        Path to the destination `veriflow.yaml`. If None, resolves via
        the `VERIFLOW_CONFIG` environment variable, else `"veriflow.yaml"`
        -- the same priority order as the CLI's `--config` default.

    Raises:
        VeriFlowError(VF_SHUTTLE_SPEC_NOT_FOUND)  -- spec_path doesn't exist
        VeriFlowError(VF_SHUTTLE_SPEC_YAML_ERROR) -- spec_path isn't valid YAML
        VeriFlowError(VF_PROJECT_CONFIG_NOT_FOUND) -- config_path doesn't exist
        (plus whatever project_set_config() itself raises for an invalid
        interface/technology/pipeline value)

    Returns a dict of the fields actually applied, e.g.
    `{"interface": "semicolab", "technology": "sky130",
    "pipeline": ["connectivity", "synthesis"]}` -- only the keys that were
    actually written, in the same shape as the spec's own values (not
    `project_set_config()`'s per-call `{"key", "value", "config"}` dicts).
    """
    import warnings

    import yaml

    from veriflow.commands.set_config import project_set_config
    from veriflow.core.yaml_config_editor import set_yaml_nested_keys

    spec_path = Path(spec_path).resolve()
    if not spec_path.is_file():
        raise VeriFlowError(
            f"Shuttle spec not found: {spec_path}",
            code="VF_SHUTTLE_SPEC_NOT_FOUND",
            details={"path": str(spec_path)},
        )
    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise VeriFlowError(
            f"YAML parse error in {spec_path}:\n  {exc}",
            code="VF_SHUTTLE_SPEC_YAML_ERROR",
            details={"path": str(spec_path)},
        ) from exc

    resolved_config = Path(config_path) if config_path is not None else _default_veriflow_config_path()

    applied: dict = {}

    if "shuttle_name" in spec and spec.get("shuttle_name"):
        warnings.warn(
            f"shuttle_spec.yaml's shuttle_name ({spec['shuttle_name']!r}) is "
            "informative only -- veriflow.yaml has no field for it (that's a "
            "Database Mode/project_config.yaml concept), so it was not applied "
            "anywhere. [VF_SHUTTLE_NAME_NOT_APPLIED]",
            stacklevel=2,
        )

    raw_interface = spec.get("interface")
    raw_interface_definition = spec.get("interface_definition")
    if raw_interface_definition:
        # A custom interface backed by an external .v file isn't
        # registered yet, so it can't go through project_set_config()'s
        # "interface" key -- that validates immediately against the
        # *current* registry (_validate_interface_value), which would
        # reject a not-yet-registered custom name. Writing name+definition
        # directly mirrors hand-authoring `interface: {name, definition}`
        # -- registration happens later, at config-load time
        # (ProjectWorkflowConfig._parse_interface_section), same as if the
        # user had typed this into veriflow.yaml themselves. Both children
        # are set in a single set_yaml_nested_keys() pass, not two
        # separate set_yaml_key() calls -- see that function's docstring
        # for the ruamel comment-bundling bug two sequential calls hit
        # here (discovered while implementing this).
        children = {"definition": str(raw_interface_definition)}
        if raw_interface:
            children = {"name": str(raw_interface), **children}
            applied["interface"] = raw_interface
        set_yaml_nested_keys(resolved_config, "interface", children)
        applied["interface_definition"] = raw_interface_definition
    elif "interface" in spec:
        value = "null" if raw_interface is None else str(raw_interface)
        project_set_config(resolved_config, "interface", value)
        applied["interface"] = raw_interface

    raw_technology = spec.get("technology")
    raw_technology_definition = spec.get("technology_definition")
    if raw_technology_definition:
        # Same reasoning and same-single-pass treatment as interface_definition above.
        children = {"definition": str(raw_technology_definition)}
        if raw_technology:
            children = {"name": str(raw_technology), **children}
            applied["technology"] = raw_technology
        set_yaml_nested_keys(resolved_config, "technology", children)
        applied["technology_definition"] = raw_technology_definition
    elif raw_technology:
        project_set_config(resolved_config, "technology", str(raw_technology))
        applied["technology"] = raw_technology

    pipeline_section = spec.get("pipeline")
    if isinstance(pipeline_section, dict) and pipeline_section.get("stages"):
        stage_types = [s["type"] for s in pipeline_section["stages"]]
        project_set_config(resolved_config, "pipeline", ",".join(stage_types))
        applied["pipeline"] = stage_types

    return applied
