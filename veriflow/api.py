"""
veriflow.api — Internal Python integration surface for VeriFlow.

Use this module to call VeriFlow from another Python process, TUI, CI
script, or agent without depending on cli.py internals or subprocess.

    from veriflow.api import run_tile
    result = run_tile("./database", "0001", skip_sim=True, skip_synth=True)

VeriFlowError is re-raised directly; callers should import it from
veriflow.core if they need to catch it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from veriflow.core import VeriFlowError


def normalize_path(db_path: str | Path) -> Path:
    return Path(db_path)


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
    """Run the verification pipeline for *tile* and return the run_result dict.

    Delegates to cmd_run(); does not duplicate logic.
    VeriFlowError propagates to the caller unchanged.

    Parameters
    ----------
    db_path : str | Path
        Path to the VeriFlow database directory.
    tile : str
        Four-digit tile number as a string (e.g. "0001").
    skip_connectivity, skip_sim, skip_synth : bool
        Skip individual stages.
    only_connectivity, only_sim, only_synth : bool
        Run a single stage; remaining stages are skipped.
    waves : bool
        Launch waveform viewer after simulation.
    non_interactive : bool
        When True, disables the waveform viewer (raises VeriFlowError if
        waves=True is also requested).
    """
    if non_interactive and waves:
        raise VeriFlowError(
            "Waveform viewer cannot be launched in non-interactive mode",
            code="VF_NON_INTERACTIVE_VIEWER_DISABLED",
            exit_code=2,
        )

    from veriflow.commands.run import cmd_run

    return cmd_run(
        db=normalize_path(db_path),
        tile_number=tile,
        skip_check=skip_connectivity,
        skip_sim=skip_sim,
        skip_synth=skip_synth,
        only_check=only_connectivity,
        only_sim=only_sim,
        only_synth=only_synth,
        waves=waves,
    )


def wrap_init(
    interface_name: str,
    rtl_file: "str | Path",
    *,
    wrapper_name: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Scaffold a wrapper config dict from a single RTL file.

    Reads *rtl_file* and auto-detects the top module name (requires exactly
    one module declaration in the file). Extracts IP ports (3-tuples
    name/direction/width, N10), and returns a dict matching the
    wrapper_config.yaml schema.
    Does NOT write any files.

    The returned dict also contains a private ``"_ip_ports"`` key (list of
    3-tuples) that cmd_wrap_init uses to render the commented YAML scaffold.
    Callers that only need the config dict can ignore it.

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
        "_ip_ports": ip_ports,  # private -- for cmd_wrap_init; not a YAML schema key
    }



def wrap_generate(
    config_path: str | Path,
    out_dir: Optional[str | Path] = None,
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
    """
    import json

    run_dir = Path(run_dir)
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise VeriFlowError(
            f"results.json not found for run: {run_dir}",
            code="VF_PROJECT_RUN_RESULT_NOT_FOUND",
            details={"run_dir": str(run_dir), "path": str(results_path)},
        )
    return json.loads(results_path.read_text(encoding="utf-8"))


def _find_latest_passing_run(runs_dir: Path) -> tuple[Optional[str], Optional[dict]]:
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
    run_id: Optional[str] = None,
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
    db_raw = yaml.safe_load(db_project_cfg_path.read_text(encoding="utf-8")) or {}
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
        shutil.copy2(src, rtl_dir / Path(rel).name)

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
            shutil.copy2(src, tb_dir / Path(rel).name)

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
