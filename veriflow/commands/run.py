from datetime import date
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.ui.output import (
    console,
    print_run_header,
    print_section,
    print_status,
    print_fail_detail,
    print_done,
)
from veriflow.core.copier import copy_flat
from veriflow.core.csv_store import append_record, get_tile_row
from veriflow.core.run_id import get_next_run_id
from veriflow.core.sim_runner import launch_waves, run_connectivity_check, run_simulation
from veriflow.core.synth_runner import run_synthesis
from veriflow.core.validator import (
    detect_iverilog_version,
    validate_database,
    validate_run_inputs,
    validate_tools,
)
from veriflow.generators.manifest import generate_manifest
from veriflow.generators.notes import generate_notes
from veriflow.generators.readme import generate_readme
from veriflow.generators.summary import generate_summary
from veriflow.models.tile_config import TileConfig


def _tool_dir() -> Path:
    """Return the veriflow/template/ directory."""
    return Path(__file__).parent.parent / "template"


def _gitkeep(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / ".gitkeep").touch()


def cmd_run(
    db: Path,
    tile_number: str,
    skip_check: bool = False,
    skip_sim: bool = False,
    skip_synth: bool = False,
    only_check: bool = False,
    only_sim: bool = False,
    only_synth: bool = False,
    waves: bool = False,
) -> None:
    """Run the full verification pipeline for a tile."""

    # Resolve skip flags from --only-* flags
    if only_check:
        skip_sim = True
        skip_synth = True
    elif only_sim:
        skip_check = True
        skip_synth = True
    elif only_synth:
        skip_check = True
        skip_sim = True

    # ── 1. Validate database and tools
    validate_database(db)

    # Only validate external tools when at least one tool stage will actually run
    any_tool_stage = not (skip_check and skip_sim and skip_synth)
    if any_tool_stage:
        validate_tools()

    tile_number_str = f"{int(tile_number):04d}"

    # ── 2. Read configs
    config_tile_dir = db / "config" / f"tile_{tile_number_str}"
    if not config_tile_dir.exists():
        raise VeriFlowError(f"Config directory not found: {config_tile_dir}")

    tile_cfg_path = config_tile_dir / "tile_config.yaml"
    if not tile_cfg_path.exists():
        raise VeriFlowError(f"tile_config.yaml not found: {tile_cfg_path}")

    tile_config = TileConfig.from_dict(yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8")) or {})
    run_config = tile_config  # run fields are now merged into tile_config

    # Read project config for semicolab flag
    from veriflow.models.project_config import ProjectConfig
    project_cfg_path = db / "project_config.yaml"
    project_config = ProjectConfig.from_dict(yaml.safe_load(project_cfg_path.read_text(encoding="utf-8")) or {})
    semicolab = project_config.semicolab

    # In non-semicolab mode, skip connectivity check automatically
    if not semicolab and not only_check:
        skip_check = True

    validate_run_inputs(db, tile_number_str, tile_config)

    # ── 3. Look up tile_id and sync tile_name/tile_author from tile_config
    tile_index_path = db / "tile_index.csv"
    tile_row = get_tile_row(tile_index_path, tile_number_str)
    tile_id = tile_row["tile_id"]
    id_version = tile_row["version"]
    id_revision = tile_row["revision"]

    # Keep tile_index in sync with tile_config
    if tile_config.tile_name or tile_config.tile_author:
        from veriflow.core.csv_store import update_tile_index
        updated_row = dict(tile_row)
        updated_row["tile_name"] = tile_config.tile_name
        updated_row["tile_author"] = tile_config.tile_author
        update_tile_index(tile_index_path, tile_number_str, updated_row)

    tile_dir = db / "tiles" / tile_id
    runs_dir = tile_dir / "runs"

    # ── 4. Determine next run ID
    run_id = get_next_run_id(runs_dir)
    today_str = date.today().isoformat()

    print_run_header(db, tile_id, run_id)

    # ── 5. Create run folder structure
    run_dir = runs_dir / run_id
    for sub in (
        "src/rtl", "src/tb",
        "out/connectivity/logs",
        "out/sim/logs", "out/sim/waves",
        "out/synth/logs", "out/synth/reports",
    ):
        _gitkeep(run_dir / sub)
    console.print(f"  [secondary]  ✓ Run directory created[/secondary]")

    # ── 6. Copy RTL sources to run/src/rtl/
    src_rtl = config_tile_dir / "src" / "rtl"
    dst_rtl = run_dir / "src" / "rtl"
    rtl_files = copy_flat(src_rtl, dst_rtl)
    console.print(f"  [secondary]  ✓ {len(rtl_files)} RTL file(s) copied[/secondary]")

    # ── 7. Copy TB sources (if present)
    src_tb = config_tile_dir / "src" / "tb"
    dst_tb = run_dir / "src" / "tb"
    tb_files: list[Path] = []
    has_tb = src_tb.exists() and any(src_tb.glob("*.v"))
    if has_tb:
        tb_files = copy_flat(src_tb, dst_tb)
        console.print(f"  [secondary]  ✓ {len(tb_files)} TB file(s) copied[/secondary]")
    else:
        console.print(f"  [warn]⚠[/warn]  [secondary]No TB files found — simulation will be skipped[/secondary]")
        skip_sim = True

    # ── Template files
    # In semicolab mode, tb_base.v and tb_tasks.v live in src/tb/
    # In universal mode, tb_tile.v is compiled directly — no injection needed
    if semicolab:
        tb_base_path = run_dir / "src" / "tb" / "tb_tile.v"
        tb_tasks_path = run_dir / "src" / "tb" / "tb_tasks.v"
        if not tb_base_path.exists():
            raise VeriFlowError(f"tb_tile.v not found in src/tb/: {tb_base_path}")
        if not tb_tasks_path.exists():
            raise VeriFlowError(f"tb_tasks.v not found in src/tb/: {tb_tasks_path}")
    else:
        tb_base_path = None
        tb_tasks_path = None

    # ── Detect tool version
    iverilog_version = detect_iverilog_version()

    # ── Result accumulators
    conn_result = "SKIPPED"
    sim_result = "SKIPPED"
    synth_result = "SKIPPED"
    sim_parsed: dict = {"sim_time": "", "seed": ""}
    synth_parsed: dict = {"cells": "", "warnings": "0", "errors": "0", "has_latches": False}

    conn_log_path = run_dir / "out" / "connectivity" / "logs" / "connectivity.log"
    sim_log_path = run_dir / "out" / "sim" / "logs" / "sim.log"
    wave_path = run_dir / "out" / "sim" / "waves" / "waves.vcd"
    synth_log_path = run_dir / "out" / "synth" / "logs" / "synth.log"

    # ── 8. Connectivity check
    if not skip_check:
        print_section("Connectivity")
        print_status("Connectivity check", "RUN")
        conn_result = run_connectivity_check(
            rtl_files=rtl_files,
            tb_base_path=tb_base_path,
            tb_tasks_path=tb_tasks_path,
            top_module=tile_config.top_module,
            log_path=conn_log_path,
        )
        print_status("Connectivity check", conn_result)
        if conn_result == "FAIL":
            print_fail_detail("Check failed — pipeline stopped", conn_log_path)
            _finalize_run(
                db=db, run_dir=run_dir, tile_dir=tile_dir,
                tile_id=tile_id, run_id=run_id, today_str=today_str,
                tile_config=tile_config, run_config=run_config,
                id_version=id_version, id_revision=id_revision,
                rtl_files=rtl_files, tb_files=tb_files,
                conn_result=conn_result, sim_result=sim_result, synth_result=synth_result,
                sim_parsed=sim_parsed, synth_parsed=synth_parsed,
                iverilog_version=iverilog_version,
                conn_log_path=conn_log_path, sim_log_path=sim_log_path,
                synth_log_path=synth_log_path, wave_path=wave_path,
                tile_index_path=db / "tile_index.csv",
                semicolab=semicolab,
            )
            return

    # ── 9. Simulation
    if not skip_sim and has_tb:
        print_section("Simulation")
        print_status("Simulation", "RUN")
        sim_result, sim_parsed = run_simulation(
            rtl_files=rtl_files,
            tb_files=tb_files,
            tb_base_path=tb_base_path,        # None in universal mode
            tb_tasks_path=tb_tasks_path,      # None in universal mode
            top_module=tile_config.top_module,
            sim_log_path=sim_log_path,
            wave_path=wave_path,
            semicolab=semicolab,
        )
        print_status("Simulation", sim_result)

    # ── 10. Synthesis
    if not skip_synth:
        print_section("Synthesis")
        print_status("Synthesis", "RUN")
        synth_result, synth_parsed = run_synthesis(
            rtl_files=rtl_files,
            top_module=tile_config.top_module,
            synth_log_path=synth_log_path,
        )
        print_status("Synthesis", synth_result)

    # ── 11–17. Finalize
    _finalize_run(
        db=db, run_dir=run_dir, tile_dir=tile_dir,
        tile_id=tile_id, run_id=run_id, today_str=today_str,
        tile_config=tile_config, run_config=run_config,
        id_version=id_version, id_revision=id_revision,
        rtl_files=rtl_files, tb_files=tb_files,
        conn_result=conn_result, sim_result=sim_result, synth_result=synth_result,
        semicolab=semicolab,
        sim_parsed=sim_parsed, synth_parsed=synth_parsed,
        iverilog_version=iverilog_version,
        conn_log_path=conn_log_path, sim_log_path=sim_log_path,
        synth_log_path=synth_log_path, wave_path=wave_path,
        tile_index_path=db / "tile_index.csv",
    )

    # ── 18. Launch Surfer if requested
    if waves and wave_path.exists():
        
        launch_waves(wave_path)


def _derive_status(
    conn: str, sim: str, synth: str,
    skip_check: bool = False, skip_sim: bool = False, skip_synth: bool = False,
) -> str:
    if conn == "FAIL":
        return "FAIL"
    stages_skipped = any(s == "SKIPPED" for s in [conn, sim, synth])
    if stages_skipped:
        return "PARTIAL"
    if conn == "PASS" and sim in ("COMPLETED", "SKIPPED") and synth in ("PASS", "SKIPPED"):
        return "PASS"
    return "FAIL"


def _rel(db: Path, path: Path) -> str:
    """Return path relative to db/tiles/ as posix string."""
    tiles_dir = db / "tiles"
    try:
        return "tiles/" + path.relative_to(tiles_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _finalize_run(
    db: Path,
    run_dir: Path,
    tile_dir: Path,
    tile_id: str,
    run_id: str,
    today_str: str,
    tile_config: TileConfig,
    run_config: TileConfig,
    id_version: str,
    id_revision: str,
    rtl_files: list[Path],
    tb_files: list[Path],
    conn_result: str,
    sim_result: str,
    synth_result: str,
    sim_parsed: dict,
    synth_parsed: dict,
    iverilog_version: str,
    conn_log_path: Path,
    sim_log_path: Path,
    synth_log_path: Path,
    wave_path: Path,
    tile_index_path: Path,
    semicolab: bool = True,
) -> None:
    """Generate all documentation, update CSV, print summary."""

    tiles_dir = db / "tiles"

    def rel(p: Path) -> str:
        try:
            return "tiles/" + p.relative_to(tiles_dir).as_posix()
        except ValueError:
            return p.as_posix()

    status = _derive_status(conn_result, sim_result, synth_result)

    # Build artifact lists (only if file exists)
    conn_logs = [rel(conn_log_path)] if conn_log_path.exists() else []
    sim_logs = [rel(sim_log_path)] if sim_log_path.exists() else []
    synth_logs = [rel(synth_log_path)] if synth_log_path.exists() else []
    wave_files = [rel(wave_path)] if wave_path.exists() else []

    # ── 11. Generate manifest.yaml
    manifest_data = {
        "tile_id": tile_id,
        "run_id": run_id,
        "date": today_str,
        "author": run_config.run_author,
        "objective": run_config.objective,
        "status": status,
        "tile": {
            "tile_name": tile_config.tile_name,
            "top_module": tile_config.top_module,
            "version": id_version,
            "revision": id_revision,
        },
        "tools": {
            "simulator": "iverilog",
            "simulator_version": iverilog_version,
            "synthesizer": "yosys",
            "synthesizer_version": "",
        },
        "run": {
            "sim_time": sim_parsed.get("sim_time", ""),
            "seed": sim_parsed.get("seed", ""),
        },
        "sources": {
            "rtl": [rel(f) for f in rtl_files],
            "tb": [rel(f) for f in tb_files],
        },
        "artifacts": {
            "connectivity_log": conn_logs,
            "sim_log": sim_logs,
            "synth_log": synth_logs,
            "wave": wave_files,
        },
        "results": {
            "connectivity": conn_result,
            "simulation": sim_result,
            "synthesis": synth_result,
            "cells": synth_parsed.get("cells", ""),
            "warnings": synth_parsed.get("warnings", ""),
            "errors": synth_parsed.get("errors", ""),
        },
    }
    from veriflow.generators.manifest import generate_manifest
    generate_manifest(manifest_data, run_dir / "manifest.yaml")
    

    # ── 12. Generate notes.md
    from veriflow.generators.notes import generate_notes
    generate_notes(tile_id, tile_config, run_config, run_dir / "notes.md")
    

    # ── 13. Regenerate README.md
    from veriflow.generators.readme import generate_readme
    generate_readme(tile_id, tile_config, tile_dir / "README.md")
    

    # ── 14. Update works/
    works_rtl = tile_dir / "works" / "rtl"
    works_tb = tile_dir / "works" / "tb"
    for f in works_rtl.glob("*.v"):
        f.unlink()
    for f in works_tb.glob("*.v"):
        f.unlink()
    copy_flat(run_dir / "src" / "rtl", works_rtl)
    if (run_dir / "src" / "tb").exists():
        copy_flat(run_dir / "src" / "tb", works_tb)
    

    # ── 15. Append row to records.csv
    run_path_rel = rel(run_dir)
    from veriflow.core.csv_store import append_record
    append_record(db / "records.csv", {
        "Tile_ID": tile_id,
        "Run_ID": run_id,
        "Date": today_str,
        "Author": run_config.run_author,
        "Objective": run_config.objective,
        "Status": status,
        "Version": id_version,
        "Revision": id_revision,
        "Connectivity": conn_result,
        "Simulation": sim_result,
        "Synthesis": synth_result,
        "Tool_Version": iverilog_version,
        "Main_Change": run_config.main_change,
        "Run_Path": run_path_rel,
        "Tags": run_config.tags,
        "Semicolab": "true" if semicolab else "false",
    })
    

    # ── 16. Generate and save summary.md
    from veriflow.generators.summary import generate_summary
    summary_text = generate_summary(
        tile_id=tile_id,
        tile_name=tile_config.tile_name,
        run_id=run_id,
        date=today_str,
        connectivity=conn_result,
        simulation=sim_result,
        synthesis=synth_result,
        cells=synth_parsed.get("cells", ""),
        warnings=synth_parsed.get("warnings", "0"),
        errors=synth_parsed.get("errors", "0"),
        sim_time=sim_parsed.get("sim_time", ""),
        precheck_status=conn_result,
        output_path=run_dir / "summary.md",
    )
    

    # ── 17. Print summary to console
    print_section("Results")
    print_status("Connectivity",  conn_result)
    print_status("Simulation",    sim_result)
    cells_detail = str(synth_parsed.get("cells", "")) if synth_parsed.get("cells") else ""
    print_status("Synthesis",     synth_result, cells_detail)

    print_done(f"Run complete  ·  [id]{tile_id}[/id]  ·  [id]{run_id}[/id]  ·  status: {status}")
