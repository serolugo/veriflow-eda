from pathlib import Path

from veriflow.core.sim_runner import launch_waves
from veriflow.ui.output import (
    print_done,
    print_fail_detail,
    print_run_header,
    print_section,
    print_status,
    print_warn,
)
from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow


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
) -> dict:
    """Run the full verification pipeline for a tile.

    Delegates execution to DatabaseWorkflow and handles terminal
    presentation and wave launching.
    """
    options = DatabaseRunOptions(
        skip_connectivity=skip_check,
        skip_sim=skip_sim,
        skip_synth=skip_synth,
        only_connectivity=only_check,
        only_sim=only_sim,
        only_synth=only_synth,
    )

    execution = DatabaseWorkflow(db).run_tile(tile_number, options)

    # ── Presentation ──────────────────────────────────────────────────────────
    data = execution.data
    conn_result = data["stages"]["connectivity"]["status"]
    sim_result = data["stages"]["simulation"]["status"]
    synth_result = data["stages"]["synthesis"]["status"]
    synth_metrics = data["stages"]["synthesis"].get("metrics") or {}

    print_run_header(db, execution.tile_id, execution.run_id)

    for warning in data.get("warnings") or []:
        print_warn(warning)

    if conn_result == "FAIL":
        conn_log_path = execution.run_dir / "out" / "connectivity" / "logs" / "connectivity.log"
        print_fail_detail("Check failed — pipeline stopped", conn_log_path)

    print_section("Results")
    print_status("Connectivity", conn_result)
    print_status("Simulation", sim_result)
    cells_detail = str(synth_metrics.get("cells", "")) if synth_metrics.get("cells") else ""
    print_status("Synthesis", synth_result, cells_detail)
    print_done(
        f"Run complete  ·  [id]{execution.tile_id}[/id]"
        f"  ·  [id]{execution.run_id}[/id]"
        f"  ·  status: {data['status']}"
    )

    # ── Wave launching ────────────────────────────────────────────────────────
    wave_path = execution.run_dir / "out" / "sim" / "waves" / "waves.vcd"
    if waves and wave_path.exists():
        launch_waves(wave_path)

    return execution.to_dict()
