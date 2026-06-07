"""
Tests for DatabaseWorkflow and cmd_run() delegation.

Uses tempfile.mkdtemp() for isolation.  Tool stages are mocked via
unittest.mock.patch so tests pass without iverilog/yosys installed.
"""

import csv
import io
import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import yaml

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_db(tmp: Path) -> Path:
    db = tmp / "database"
    from veriflow.commands.init_db import cmd_init
    cmd_init(db)
    return db


def _make_tile(db: Path, top_module: str = "my_tile") -> None:
    from veriflow.commands.create_tile import cmd_create_tile
    cmd_create_tile(db, top_module=top_module)


def _fill_project_config(db: Path, interface_name: str | None = "semicolab") -> None:
    cfg = {
        "id_prefix": "TST-01",
        "project_name": "Test Project",
        "repo": "https://github.com/test/test",
        "description": "Test project.",
        "interface_name": interface_name,
    }
    (db / "project_config.yaml").write_text(
        yaml.dump(cfg, default_flow_style=False), encoding="utf-8"
    )


def _add_rtl(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
    rtl_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / f"{module_name}.v").write_text(
        f"`timescale 1ns/1ps\n"
        f"module {module_name} #(\n"
        f"    parameter REG_WIDTH = 32,\n"
        f"    parameter CSR_IN_WIDTH = 16,\n"
        f"    parameter CSR_OUT_WIDTH = 16\n"
        f")(\n"
        f"    input  wire clk,\n"
        f"    input  wire arst_n,\n"
        f"    input  wire [CSR_IN_WIDTH-1:0]  csr_in,\n"
        f"    input  wire [REG_WIDTH-1:0]     data_reg_a,\n"
        f"    input  wire [REG_WIDTH-1:0]     data_reg_b,\n"
        f"    output wire [REG_WIDTH-1:0]     data_reg_c,\n"
        f"    output wire [CSR_OUT_WIDTH-1:0] csr_out,\n"
        f"    output wire                     csr_in_re,\n"
        f"    output wire                     csr_out_we\n"
        f");\n"
        f"    assign data_reg_c = data_reg_a + data_reg_b;\n"
        f"    assign csr_out    = csr_in;\n"
        f"    assign csr_in_re  = 1'b0;\n"
        f"    assign csr_out_we = 1'b0;\n"
        f"endmodule\n",
        encoding="utf-8",
    )


def _add_tb(db: Path, tile_number_str: str, tb_name: str = "tb") -> None:
    tb_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "tb"
    tb_dir.mkdir(parents=True, exist_ok=True)
    (tb_dir / f"{tb_name}.v").write_text(
        f"`timescale 1ns/1ps\nmodule {tb_name};\n  initial begin\n    $finish;\n  end\nendmodule\n",
        encoding="utf-8",
    )


def _fill_tile_config(
    db: Path, tile_number_str: str, module_name: str = "my_tile"
) -> None:
    cfg_path = db / "config" / f"tile_{tile_number_str}" / "tile_config.yaml"
    cfg = {
        "tile_name": "Test Tile",
        "tile_author": "Tester",
        "top_module": module_name,
        "description": "A test tile.",
        "ports": "Standard ports.",
        "usage_guide": "Just run it.",
        "tb_description": "Basic TB.",
        "run_author": "Tester",
        "objective": "Test run",
        "tags": "test",
        "main_change": "Initial.",
        "notes": "No notes.",
    }
    cfg_path.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def _setup_db(
    tmp: Path,
    interface_name: str | None = "semicolab",
    with_tb: bool = False,
) -> Path:
    """Create a ready-to-run database with one tile (0001)."""
    db = _make_db(tmp)
    _fill_project_config(db, interface_name=interface_name)
    _make_tile(db)
    _add_rtl(db, "0001", "my_tile")
    _fill_tile_config(db, "0001", "my_tile")
    if with_tb:
        _add_tb(db, "0001", "tb")
    return db


@contextmanager
def _patch_tools(
    conn_status: str = "PASS",
    sim_return: tuple = ("COMPLETED", {}),
    synth_return: tuple = ("PASS", {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False}),
):
    """Patch external tool validators and all three backends."""
    with (
        patch("veriflow.workflows.database.validate_tools"),
        patch("veriflow.workflows.database.detect_iverilog_version", return_value="12.0"),
        patch(
            "veriflow.core.backends.icarus.IcarusConnectivityBackend.run_connectivity",
            return_value=conn_status,
        ),
        patch(
            "veriflow.core.backends.icarus.IcarusSimulationBackend.run_simulation",
            return_value=sim_return,
        ) as mock_sim,
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=synth_return,
        ) as mock_synth,
    ):
        yield mock_sim, mock_synth


# ── DatabaseRunOptions ────────────────────────────────────────────────────────


def test_options_defaults():
    from veriflow.workflows.database import DatabaseRunOptions
    opts = DatabaseRunOptions()
    assert opts.skip_connectivity is False
    assert opts.skip_sim is False
    assert opts.skip_synth is False
    assert opts.only_connectivity is False
    assert opts.only_sim is False
    assert opts.only_synth is False


def test_options_explicit():
    from veriflow.workflows.database import DatabaseRunOptions
    opts = DatabaseRunOptions(skip_connectivity=True, only_synth=True)
    assert opts.skip_connectivity is True
    assert opts.only_synth is True


# ── DatabaseRunResult ─────────────────────────────────────────────────────────


def test_run_result_to_dict_returns_data():
    from veriflow.workflows.database import DatabaseRunResult
    payload = {"schema_version": "1.1", "status": "PARTIAL"}
    result = DatabaseRunResult(
        tile_id="X",
        run_id="run-001",
        run_dir=Path("/tmp/r"),
        status="PARTIAL",
        semicolab=False,
        stages={},
        sources={"rtl": [], "tb": []},
        artifacts={},
        data=payload,
    )
    assert result.to_dict() is payload


# ── DatabaseWorkflow.run_tile — structural ────────────────────────────────────


def test_returns_database_run_result():
    from veriflow.workflows.database import DatabaseRunResult, DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert isinstance(result, DatabaseRunResult)
    finally:
        shutil.rmtree(tmp)


def test_returns_correct_tile_id_run_id():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    from veriflow.core.csv_store import get_tile_row
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        row = get_tile_row(db / "tile_index.csv", "0001")
        assert result.tile_id == row["tile_id"]
        assert result.run_id == "run-001"
    finally:
        shutil.rmtree(tmp)


def test_returns_correct_run_dir():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    from veriflow.core.csv_store import get_tile_row
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        row = get_tile_row(db / "tile_index.csv", "0001")
        expected = db / "tiles" / row["tile_id"] / "runs" / "run-001"
        assert result.run_dir == expected
    finally:
        shutil.rmtree(tmp)


def test_creates_run_directory_structure():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        run_dir = result.run_dir
        for sub in (
            "src/rtl",
            "src/tb",
            "out/connectivity/logs",
            "out/sim/logs",
            "out/sim/waves",
            "out/synth/logs",
            "out/synth/reports",
        ):
            assert (run_dir / sub).is_dir(), f"Missing: {sub}"
    finally:
        shutil.rmtree(tmp)


def test_copies_rtl_snapshot():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert (result.run_dir / "src" / "rtl" / "my_tile.v").exists()
    finally:
        shutil.rmtree(tmp)


def test_copies_tb_snapshot_when_present():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, with_tb=True)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert (result.run_dir / "src" / "tb" / "tb.v").exists()
    finally:
        shutil.rmtree(tmp)


def test_generates_manifest_yaml():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert (result.run_dir / "manifest.yaml").exists()
    finally:
        shutil.rmtree(tmp)


def test_generates_notes_md():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert (result.run_dir / "notes.md").exists()
    finally:
        shutil.rmtree(tmp)


def test_generates_summary_md():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert (result.run_dir / "summary.md").exists()
    finally:
        shutil.rmtree(tmp)


def test_generates_readme_md():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    from veriflow.core.csv_store import get_tile_row
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        row = get_tile_row(db / "tile_index.csv", "0001")
        readme = db / "tiles" / row["tile_id"] / "README.md"
        assert readme.exists()
    finally:
        shutil.rmtree(tmp)


def test_generates_results_json():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        results_path = result.run_dir / "results.json"
        assert results_path.exists()
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.1"
    finally:
        shutil.rmtree(tmp)


def test_refreshes_works_rtl():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    from veriflow.core.csv_store import get_tile_row
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        DatabaseWorkflow(db).run_tile("0001", opts)
        row = get_tile_row(db / "tile_index.csv", "0001")
        works_rtl = db / "tiles" / row["tile_id"] / "works" / "rtl"
        assert any(works_rtl.glob("*.v"))
    finally:
        shutil.rmtree(tmp)


def test_appends_records_csv():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        DatabaseWorkflow(db).run_tile("0001", opts)
        rows = list(
            csv.DictReader(
                (db / "records.csv").read_text(encoding="utf-8").splitlines()
            )
        )
        assert len(rows) == 1
        assert rows[0]["Run_ID"] == "run-001"
    finally:
        shutil.rmtree(tmp)


# ── Status derivation ─────────────────────────────────────────────────────────


def test_all_skipped_returns_partial():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert result.status == "PARTIAL"
        assert result.data["status"] == "PARTIAL"
    finally:
        shutil.rmtree(tmp)


def test_all_pass_returns_pass():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, with_tb=True)
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(
            conn_status="PASS",
            sim_return=("COMPLETED", {"sim_time": "10ns", "seed": "0"}),
            synth_return=("PASS", {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False}),
        ):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert result.status == "PASS"
        assert result.data["status"] == "PASS"
    finally:
        shutil.rmtree(tmp)


def test_only_check_skips_sim_and_synth():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions(only_connectivity=True)
        with _patch_tools(conn_status="PASS") as (mock_sim, mock_synth):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        mock_sim.assert_not_called()
        mock_synth.assert_not_called()
        assert result.data["stages"]["simulation"]["status"] == "SKIPPED"
        assert result.data["stages"]["synthesis"]["status"] == "SKIPPED"
    finally:
        shutil.rmtree(tmp)


# ── Connectivity FAIL early exit ──────────────────────────────────────────────


def test_connectivity_fail_returns_fail():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name="semicolab")
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(conn_status="FAIL") as (mock_sim, mock_synth):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert result.status == "FAIL"
        assert result.data["status"] == "FAIL"
    finally:
        shutil.rmtree(tmp)


def test_connectivity_fail_does_not_run_simulation():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name="semicolab", with_tb=True)
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(conn_status="FAIL") as (mock_sim, mock_synth):
            DatabaseWorkflow(db).run_tile("0001", opts)
        mock_sim.assert_not_called()
    finally:
        shutil.rmtree(tmp)


def test_connectivity_fail_does_not_run_synthesis():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name="semicolab")
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(conn_status="FAIL") as (mock_sim, mock_synth):
            DatabaseWorkflow(db).run_tile("0001", opts)
        mock_synth.assert_not_called()
    finally:
        shutil.rmtree(tmp)


def test_connectivity_fail_stages_marked_skipped():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name="semicolab")
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(conn_status="FAIL"):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert result.data["stages"]["connectivity"]["status"] == "FAIL"
        assert result.data["stages"]["simulation"]["status"] == "SKIPPED"
        assert result.data["stages"]["synthesis"]["status"] == "SKIPPED"
    finally:
        shutil.rmtree(tmp)


def test_connectivity_fail_still_generates_artifacts():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name="semicolab")
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(conn_status="FAIL"):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert (result.run_dir / "manifest.yaml").exists()
        assert (result.run_dir / "results.json").exists()
        assert (result.run_dir / "summary.md").exists()
    finally:
        shutil.rmtree(tmp)


# ── Simulation FAIL still executes synthesis ──────────────────────────────────


def test_sim_fail_does_not_stop_synthesis():
    tmp = Path(tempfile.mkdtemp())
    try:
        # null interface so connectivity is auto-skipped; sim can fail freely
        db = _setup_db(tmp, interface_name=None, with_tb=True)
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(
            conn_status="PASS",
            sim_return=("FAIL", {}),
            synth_return=("PASS", {"cells": "3", "warnings": "0", "errors": "0", "has_latches": False}),
        ) as (mock_sim, mock_synth):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        mock_synth.assert_called_once()
        assert result.data["stages"]["simulation"]["status"] == "FAIL"
        assert result.data["stages"]["synthesis"]["status"] == "PASS"
    finally:
        shutil.rmtree(tmp)


def test_sim_fail_result_not_pass():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name=None, with_tb=True)
        from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
        opts = DatabaseRunOptions()
        with _patch_tools(
            conn_status="PASS",
            sim_return=("FAIL", {}),
            synth_return=("PASS", {"cells": "3", "warnings": "0", "errors": "0", "has_latches": False}),
        ):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        # Connectivity is SKIPPED (null interface) → PARTIAL rather than FAIL
        assert result.status in ("FAIL", "PARTIAL")
        assert result.status != "PASS"
    finally:
        shutil.rmtree(tmp)


# ── Semicolab boolean ─────────────────────────────────────────────────────────


def test_semicolab_true_when_interface_name_semicolab():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name="semicolab")
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert result.semicolab is True
        assert result.data["semicolab"] is True
    finally:
        shutil.rmtree(tmp)


def test_semicolab_false_when_interface_name_null():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name=None)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert result.semicolab is False
        assert result.data["semicolab"] is False
    finally:
        shutil.rmtree(tmp)


def test_semicolab_reflected_in_records_csv():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name="semicolab")
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        DatabaseWorkflow(db).run_tile("0001", opts)
        rows = list(
            csv.DictReader(
                (db / "records.csv").read_text(encoding="utf-8").splitlines()
            )
        )
        assert rows[0]["Semicolab"] == "true"
    finally:
        shutil.rmtree(tmp)


# ── Null interface skips connectivity automatically ───────────────────────────


def test_null_interface_skips_connectivity():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name=None)
        opts = DatabaseRunOptions(skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        assert result.data["stages"]["connectivity"]["status"] == "SKIPPED"
    finally:
        shutil.rmtree(tmp)


# ── only_connectivity with no profile raises VF_INTERFACE_CHECK_NO_PROFILE ───


def test_only_connectivity_no_profile_raises():
    from veriflow.core import VeriFlowError
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp, interface_name=None)
        opts = DatabaseRunOptions(only_connectivity=True)
        raised = False
        try:
            DatabaseWorkflow(db).run_tile("0001", opts)
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_INTERFACE_CHECK_NO_PROFILE"
        assert raised
    finally:
        shutil.rmtree(tmp)


# ── results.json schema ───────────────────────────────────────────────────────


def test_results_json_schema_version_1_1():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        data = json.loads((result.run_dir / "results.json").read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.1"
    finally:
        shutil.rmtree(tmp)


def test_results_json_has_required_keys():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        data = json.loads((result.run_dir / "results.json").read_text(encoding="utf-8"))
        for key in ("schema_version", "tile_id", "run_id", "date", "status",
                    "semicolab", "stages", "sources", "artifacts", "error"):
            assert key in data, f"Missing key: {key}"
    finally:
        shutil.rmtree(tmp)


def test_results_json_stage_keys():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        data = json.loads((result.run_dir / "results.json").read_text(encoding="utf-8"))
        assert set(data["stages"].keys()) == {"connectivity", "simulation", "synthesis"}
    finally:
        shutil.rmtree(tmp)


def test_to_dict_matches_results_json():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        result = DatabaseWorkflow(db).run_tile("0001", opts)
        file_data = json.loads((result.run_dir / "results.json").read_text(encoding="utf-8"))
        assert result.to_dict() == file_data
    finally:
        shutil.rmtree(tmp)


# ── No waveform viewer launched ───────────────────────────────────────────────


def test_workflow_does_not_launch_waves():
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)
        with patch("veriflow.core.sim_runner.launch_waves") as mock_launch:
            DatabaseWorkflow(db).run_tile("0001", opts)
        mock_launch.assert_not_called()
    finally:
        shutil.rmtree(tmp)


# ── No CLI output from workflow ───────────────────────────────────────────────


def test_workflow_does_not_call_ui_output():
    """DatabaseWorkflow must not call any veriflow.ui.output functions."""
    import veriflow.ui.output as ui_mod

    # Patch every callable that prints to the terminal
    targets = [n for n in dir(ui_mod) if not n.startswith("_")]
    patches = [patch.object(ui_mod, name, MagicMock()) for name in targets
               if callable(getattr(ui_mod, name))]

    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True, skip_synth=True)

        for p in patches:
            p.start()
        try:
            DatabaseWorkflow(db).run_tile("0001", opts)
        finally:
            for p in patches:
                p.stop()

        for p in patches:
            p.new.assert_not_called()
    finally:
        shutil.rmtree(tmp)


# ── cmd_run() delegation ──────────────────────────────────────────────────────


def _make_mock_run_result(run_dir: Path, status: str = "PARTIAL") -> "DatabaseRunResult":
    from veriflow.workflows.database import DatabaseRunResult
    data = {
        "schema_version": "1.1",
        "tile_id": "TST-01-26060700010101",
        "run_id": "run-001",
        "date": "2026-06-07",
        "status": status,
        "semicolab": False,
        "stages": {
            "connectivity": {"status": "SKIPPED"},
            "simulation": {"status": "SKIPPED"},
            "synthesis": {"tool": "yosys", "status": "SKIPPED",
                          "metrics": {"cells": "", "warnings": "0",
                                      "errors": "0", "has_latches": False}},
        },
        "sources": {"rtl": [], "tb": []},
        "artifacts": {
            "manifest": [], "summary": [], "notes": [],
            "readme": [], "records": [],
            "connectivity_log": [], "sim_log": [], "synth_log": [], "wave": [],
        },
        "error": None,
    }
    return DatabaseRunResult(
        tile_id="TST-01-26060700010101",
        run_id="run-001",
        run_dir=run_dir,
        status=status,
        semicolab=False,
        stages={},
        sources={"rtl": [], "tb": []},
        artifacts={},
        data=data,
    )


def test_cmd_run_delegates_to_workflow():
    """cmd_run must construct DatabaseRunOptions and call DatabaseWorkflow.run_tile."""
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        run_dir = tmp / "run"
        run_dir.mkdir()
        mock_result = _make_mock_run_result(run_dir)

        with patch("veriflow.commands.run.DatabaseWorkflow") as MockWorkflow:
            mock_instance = MagicMock()
            MockWorkflow.return_value = mock_instance
            mock_instance.run_tile.return_value = mock_result

            cmd_run(
                db=Path("/fake/db"),
                tile_number="0001",
                skip_check=True,
                skip_sim=True,
                skip_synth=True,
            )

        MockWorkflow.assert_called_once_with(Path("/fake/db"))
        mock_instance.run_tile.assert_called_once()
        call_args = mock_instance.run_tile.call_args
        assert call_args[0][0] == "0001"
        opts = call_args[0][1]
        assert opts.skip_connectivity is True
        assert opts.skip_sim is True
        assert opts.skip_synth is True
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_passes_only_flags():
    """--only-* flags must be forwarded as only_* on DatabaseRunOptions."""
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        run_dir = tmp / "run"
        run_dir.mkdir()
        mock_result = _make_mock_run_result(run_dir)

        with patch("veriflow.commands.run.DatabaseWorkflow") as MockWorkflow:
            mock_instance = MagicMock()
            MockWorkflow.return_value = mock_instance
            mock_instance.run_tile.return_value = mock_result

            cmd_run(db=Path("/fake/db"), tile_number="0001", only_synth=True)

        opts = mock_instance.run_tile.call_args[0][1]
        assert opts.only_synth is True
        assert opts.only_connectivity is False
        assert opts.only_sim is False
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_returns_to_dict_unchanged():
    """cmd_run must return DatabaseRunResult.to_dict() verbatim."""
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        run_dir = tmp / "run"
        run_dir.mkdir()
        mock_result = _make_mock_run_result(run_dir)

        with patch("veriflow.commands.run.DatabaseWorkflow") as MockWorkflow:
            mock_instance = MagicMock()
            MockWorkflow.return_value = mock_instance
            mock_instance.run_tile.return_value = mock_result

            returned = cmd_run(
                db=Path("/fake/db"),
                tile_number="0001",
                skip_check=True,
                skip_sim=True,
                skip_synth=True,
            )

        assert returned is mock_result.data
        assert returned["schema_version"] == "1.1"
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_waves_launches_from_execution_run_dir():
    """waves=True must launch from run_dir path, not re-run business logic."""
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        run_dir = tmp / "run"
        wave_path = run_dir / "out" / "sim" / "waves" / "waves.vcd"
        wave_path.parent.mkdir(parents=True, exist_ok=True)
        wave_path.write_text("$dumpvars;", encoding="utf-8")

        mock_result = _make_mock_run_result(run_dir)

        with (
            patch("veriflow.commands.run.DatabaseWorkflow") as MockWorkflow,
            patch("veriflow.commands.run.launch_waves") as mock_launch,
        ):
            mock_instance = MagicMock()
            MockWorkflow.return_value = mock_instance
            mock_instance.run_tile.return_value = mock_result

            cmd_run(
                db=Path("/fake/db"),
                tile_number="0001",
                skip_check=True,
                skip_sim=True,
                skip_synth=True,
                waves=True,
            )

        mock_launch.assert_called_once_with(wave_path)
        # Verify run_tile called only once (no second execution for wave path)
        mock_instance.run_tile.assert_called_once()
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_waves_no_file_does_not_launch():
    """waves=True with no wave file must not launch the viewer."""
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        run_dir = tmp / "run"
        run_dir.mkdir()
        mock_result = _make_mock_run_result(run_dir)
        # wave file does NOT exist at run_dir / "out/sim/waves/waves.vcd"

        with (
            patch("veriflow.commands.run.DatabaseWorkflow") as MockWorkflow,
            patch("veriflow.commands.run.launch_waves") as mock_launch,
        ):
            mock_instance = MagicMock()
            MockWorkflow.return_value = mock_instance
            mock_instance.run_tile.return_value = mock_result

            cmd_run(
                db=Path("/fake/db"),
                tile_number="0001",
                skip_check=True,
                skip_sim=True,
                skip_synth=True,
                waves=True,
            )

        mock_launch.assert_not_called()
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_waves_false_does_not_launch():
    """waves=False must never launch the viewer."""
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        run_dir = tmp / "run"
        wave_path = run_dir / "out" / "sim" / "waves" / "waves.vcd"
        wave_path.parent.mkdir(parents=True, exist_ok=True)
        wave_path.write_text("$dumpvars;", encoding="utf-8")

        mock_result = _make_mock_run_result(run_dir)

        with (
            patch("veriflow.commands.run.DatabaseWorkflow") as MockWorkflow,
            patch("veriflow.commands.run.launch_waves") as mock_launch,
        ):
            mock_instance = MagicMock()
            MockWorkflow.return_value = mock_instance
            mock_instance.run_tile.return_value = mock_result

            cmd_run(
                db=Path("/fake/db"),
                tile_number="0001",
                skip_check=True,
                skip_sim=True,
                skip_synth=True,
                waves=False,
            )

        mock_launch.assert_not_called()
    finally:
        shutil.rmtree(tmp)


# ── Parity: existing cmd_run behavior unchanged ───────────────────────────────


def test_cmd_run_still_returns_schema_version_1_1():
    """End-to-end: cmd_run returns dict with schema_version 1.1."""
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        result = cmd_run(
            db=db,
            tile_number="0001",
            skip_check=True,
            skip_sim=True,
            skip_synth=True,
        )
        assert isinstance(result, dict)
        assert result["schema_version"] == "1.1"
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_still_creates_run_directory():
    """End-to-end: cmd_run creates run-001 under tile runs/."""
    from veriflow.commands.run import cmd_run
    from veriflow.core.csv_store import get_tile_row
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        cmd_run(
            db=db,
            tile_number="0001",
            skip_check=True,
            skip_sim=True,
            skip_synth=True,
        )
        row = get_tile_row(db / "tile_index.csv", "0001")
        run_dir = db / "tiles" / row["tile_id"] / "runs" / "run-001"
        assert run_dir.exists()
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_result_has_stages():
    from veriflow.commands.run import cmd_run
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        result = cmd_run(
            db=db,
            tile_number="0001",
            skip_check=True,
            skip_sim=True,
            skip_synth=True,
        )
        assert "stages" in result
        assert "connectivity" in result["stages"]
        assert "simulation" in result["stages"]
        assert "synthesis" in result["stages"]
    finally:
        shutil.rmtree(tmp)
