"""
VeriFlow V1 — Integration tests.
Uses tempfile.mkdtemp() for isolated environments. Cleans up after each test.
"""

import shutil
import tempfile
from datetime import date
from pathlib import Path

from veriflow.framework.design import Design
from veriflow.framework.stage_input import StageInput

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_design(top_module: str = "my_tile") -> Design:
    return Design(top_module=top_module, rtl_sources=[Path("/nonexistent/my_tile.v")])


def _make_design_with_tb(top_module: str = "my_tile") -> Design:
    return Design(
        top_module=top_module,
        rtl_sources=[Path("/nonexistent/my_tile.v")],
        tb_sources=[Path("/nonexistent/tb_tile.v")],
    )


def _make_stage_input(ctx, design: Design | None = None) -> StageInput:
    return StageInput(design=design or _make_design(), context=ctx)


def _make_db(tmp: Path) -> Path:
    """Initialize a fresh database inside tmp."""
    db = tmp / "database"
    from veriflow.commands.init_db import cmd_init
    cmd_init(db)
    return db


def _make_tile(db: Path, top_module: str = "my_tile") -> None:
    """Create a tile with a known top_module (required for Semicolab mode)."""
    from veriflow.commands.create_tile import cmd_create_tile
    cmd_create_tile(db, top_module=top_module)


def _fill_project_config(db: Path, id_prefix: str = "TST-01") -> None:
    import yaml
    cfg = {
        "id_prefix": id_prefix,
        "project_name": "Test Project",
        "repo": "https://github.com/test/test",
        "description": "Test project for VeriFlow unit tests.\n",
        "interface_name": "semicolab",
    }
    (db / "project_config.yaml").write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def _add_rtl(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
    """Write a minimal valid RTL file for the given tile."""
    rtl_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    rtl = rtl_dir / f"{module_name}.v"
    rtl.write_text(f"""`timescale 1ns/1ps
module {module_name} #(
    parameter REG_WIDTH = 32,
    parameter CSR_IN_WIDTH = 16,
    parameter CSR_OUT_WIDTH = 16
)(
    input  wire clk,
    input  wire arst_n,
    input  wire [CSR_IN_WIDTH-1:0]  csr_in,
    input  wire [REG_WIDTH-1:0]     data_reg_a,
    input  wire [REG_WIDTH-1:0]     data_reg_b,
    output wire [REG_WIDTH-1:0]     data_reg_c,
    output wire [CSR_OUT_WIDTH-1:0] csr_out,
    output wire                     csr_in_re,
    output wire                     csr_out_we
);
    assign data_reg_c = data_reg_a + data_reg_b;
    assign csr_out    = csr_in;
    assign csr_in_re  = 1'b0;
    assign csr_out_we = 1'b0;
endmodule
""", encoding="utf-8")


def _fill_tile_config(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
    import yaml
    cfg_path = db / "config" / f"tile_{tile_number_str}" / "tile_config.yaml"
    cfg = {
        "tile_name": "Test Tile",
        "tile_author": "Tester",
        "top_module": module_name,
        "description": "A test tile.",
        "ports": "Standard ports.",
        "usage_guide": "Just run it.",
        "tb_description": "Basic TB.",
    }
    cfg_path.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def _fill_run_config(db: Path, tile_number_str: str) -> None:
    """Merge run fields into tile_config.yaml (now a single file)."""
    import yaml
    cfg_path = db / "config" / f"tile_{tile_number_str}" / "tile_config.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    raw.update({
        "run_author": "Tester",
        "objective": "Test run",
        "tags": "test",
        "main_change": "Initial.",
        "notes": "No notes.",
    })
    cfg_path.write_text(yaml.dump(raw, default_flow_style=False), encoding="utf-8")


# ── test functions ────────────────────────────────────────────────────────────

def test_tile_id_generation():
    from veriflow.core.tile_id import generate_tile_id
    tid = generate_tile_id("MST130-01", 1, 1, 1, today=date(2026, 3, 15))
    assert tid == "MST130-01-26031500010101", f"Got: {tid}"


def test_tile_id_parsing():
    from veriflow.core.tile_id import parse_tile_id
    p = parse_tile_id("MST130-01-26031500010101")
    assert p["id_prefix"] == "MST130-01"
    assert p["tile_number"] == 1
    assert p["id_version"] == 1
    assert p["id_revision"] == 1
    assert p["yymmdd"] == "260315"


def test_run_id_first():
    from veriflow.core.run_id import get_next_run_id
    tmp = Path(tempfile.mkdtemp())
    try:
        runs_dir = tmp / "runs"
        runs_dir.mkdir()
        rid = get_next_run_id(runs_dir)
        assert rid == "run-001", f"Got: {rid}"
    finally:
        shutil.rmtree(tmp)


def test_run_id_increment():
    from veriflow.core.run_id import get_next_run_id
    tmp = Path(tempfile.mkdtemp())
    try:
        runs_dir = tmp / "runs"
        runs_dir.mkdir()
        (runs_dir / "run-001").mkdir()
        (runs_dir / "run-002").mkdir()
        rid = get_next_run_id(runs_dir)
        assert rid == "run-003", f"Got: {rid}"
    finally:
        shutil.rmtree(tmp)


def test_init_creates_structure():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "db"
        from veriflow.commands.init_db import cmd_init
        cmd_init(db)
        assert (db / "project_config.yaml").exists()
        assert (db / "tile_index.csv").exists()
        assert (db / "records.csv").exists()
        assert (db / "tiles").is_dir()
        assert (db / "config").is_dir()
        assert (db / "tiles" / ".gitkeep").exists()
    finally:
        shutil.rmtree(tmp)


def test_init_force():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "db"
        from veriflow.commands.init_db import cmd_init
        cmd_init(db)
        cmd_init(db, force=True)  # should not raise
        assert (db / "project_config.yaml").exists()
    finally:
        shutil.rmtree(tmp)


def test_init_no_force_raises():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "db"
        from veriflow.commands.init_db import cmd_init
        from veriflow.core import VeriFlowError
        cmd_init(db)
        raised = False
        try:
            cmd_init(db, force=False)
        except VeriFlowError:
            raised = True
        assert raised, "Expected VeriFlowError when database exists without --force"
    finally:
        shutil.rmtree(tmp)


def test_create_tile_structure():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)

        # Check config dir
        cfg_dir = db / "config" / "tile_0001"
        assert cfg_dir.exists()
        assert (cfg_dir / "tile_config.yaml").exists()
        assert (cfg_dir / "src" / "rtl").is_dir()
        assert (cfg_dir / "src" / "tb").is_dir()

        # Check tile_index row
        from veriflow.core.csv_store import read_tile_index
        rows = read_tile_index(db / "tile_index.csv")
        assert len(rows) == 1
        assert rows[0]["tile_number"] == "0001"
        assert rows[0]["version"] == "01"
        assert rows[0]["revision"] == "01"
    finally:
        shutil.rmtree(tmp)


def test_create_tile_tiles_dir():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        from veriflow.core.csv_store import read_tile_index
        rows = read_tile_index(db / "tile_index.csv")
        tile_id = rows[0]["tile_id"]
        tile_dir = db / "tiles" / tile_id
        assert tile_dir.is_dir()
        assert (tile_dir / "README.md").exists()
        assert (tile_dir / "works" / "rtl").is_dir()
        assert (tile_dir / "works" / "tb").is_dir()
        assert (tile_dir / "runs").is_dir()
    finally:
        shutil.rmtree(tmp)


def test_csv_empty_file_rule():
    """Empty CSV gets header written before first append."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)

        tile_index = db / "tile_index.csv"
        content = tile_index.read_text(encoding="utf-8")
        assert "tile_number" in content
        assert "tile_id" in content
    finally:
        shutil.rmtree(tmp)


def test_csv_header_validation():
    from veriflow.core import VeriFlowError
    from veriflow.core.csv_store import read_tile_index
    tmp = Path(tempfile.mkdtemp())
    try:
        bad_csv = tmp / "tile_index.csv"
        bad_csv.write_text("wrong,header,here\n1,X,Y\n", encoding="utf-8")
        raised = False
        try:
            read_tile_index(bad_csv)
        except VeriFlowError:
            raised = True
        assert raised, "Expected VeriFlowError for bad CSV header"
    finally:
        shutil.rmtree(tmp)


def test_flat_copy_basic():
    from veriflow.core.copier import copy_flat
    tmp = Path(tempfile.mkdtemp())
    try:
        src = tmp / "src"
        src.mkdir()
        (src / "a.v").write_text("module a; endmodule", encoding="utf-8")
        (src / "b.v").write_text("module b; endmodule", encoding="utf-8")
        dst = tmp / "dst"
        copied = copy_flat(src, dst)
        assert len(copied) == 2
        assert (dst / "a.v").exists()
        assert (dst / "b.v").exists()
    finally:
        shutil.rmtree(tmp)


def test_flat_copy_collision():
    from veriflow.core.copier import copy_flat
    tmp = Path(tempfile.mkdtemp())
    try:
        src1 = tmp / "src1"
        src1.mkdir()
        (src1 / "tile.v").write_text("module a; endmodule", encoding="utf-8")

        dst = tmp / "dst"
        copy_flat(src1, dst)

        # Second copy of same name should get _1 suffix
        src2 = tmp / "src2"
        src2.mkdir()
        (src2 / "tile.v").write_text("module b; endmodule", encoding="utf-8")
        copy_flat(src2, dst)

        assert (dst / "tile.v").exists()
        assert (dst / "tile_1.v").exists()
    finally:
        shutil.rmtree(tmp)


def test_bump_version():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        from veriflow.core.csv_store import get_tile_row
        row_before = get_tile_row(db / "tile_index.csv", "0001")
        old_id = row_before["tile_id"]

        from veriflow.commands.bump_version import cmd_bump_version
        cmd_bump_version(db, "0001")

        row_after = get_tile_row(db / "tile_index.csv", "0001")
        new_id = row_after["tile_id"]
        assert new_id != old_id
        assert row_after["version"] == "02"
        assert row_after["revision"] == "01"  # revision unchanged

        # Old dir preserved, new dir created
        assert (db / "tiles" / old_id).exists()
        assert (db / "tiles" / new_id).exists()
        # New dir has clean runs/
        assert (db / "tiles" / new_id / "runs").exists()
        assert not any((db / "tiles" / new_id / "runs").glob("run-*"))
    finally:
        shutil.rmtree(tmp)


def test_bump_revision():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        from veriflow.core.csv_store import get_tile_row
        row_before = get_tile_row(db / "tile_index.csv", "0001")
        old_id = row_before["tile_id"]

        from veriflow.commands.bump_revision import cmd_bump_revision
        cmd_bump_revision(db, "0001")

        row_after = get_tile_row(db / "tile_index.csv", "0001")
        new_id = row_after["tile_id"]
        assert new_id != old_id
        assert row_after["revision"] == "02"
        assert row_after["version"] == "01"   # version reset to 01

        # Old dir preserved, new dir created
        assert (db / "tiles" / old_id).exists()
        assert (db / "tiles" / new_id).exists()
        # New dir has clean runs/
        assert (db / "tiles" / new_id / "runs").exists()
        assert not any((db / "tiles" / new_id / "runs").glob("run-*"))
    finally:
        shutil.rmtree(tmp)


def test_validation_missing_project_config():
    from veriflow.core import VeriFlowError
    from veriflow.core.validator import validate_database
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "db"
        db.mkdir()
        raised = False
        try:
            validate_database(db)
        except VeriFlowError:
            raised = True
        assert raised
    finally:
        shutil.rmtree(tmp)


def test_validation_empty_id_prefix():
    from veriflow.core import VeriFlowError
    from veriflow.core.validator import validate_project_config
    from veriflow.models.project_config import ProjectConfig
    raised = False
    try:
        validate_project_config(ProjectConfig(id_prefix="", project_name="X", repo="", description=""))
    except VeriFlowError:
        raised = True
    assert raised


def test_validation_missing_top_module():
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        # tile_config has empty top_module
        from veriflow.core.validator import validate_run_inputs
        from veriflow.models.tile_config import TileConfig
        tc = TileConfig.from_dict({})  # top_module = ""
        raised = False
        try:
            validate_run_inputs(db, "0001", tc)
        except VeriFlowError:
            raised = True
        assert raised
    finally:
        shutil.rmtree(tmp)


def test_run_creates_structure():
    """
    Test that cmd_run creates the run directory structure and generates docs.
    Skips actual tool execution (--skip-check, --skip-sim, --skip-synth).
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")

        from veriflow.commands.run import cmd_run
        cmd_run(
            db=db,
            tile_number="0001",
            skip_check=True,
            skip_sim=True,
            skip_synth=True,
        )

        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        tile_id = row["tile_id"]
        tile_dir = db / "tiles" / tile_id
        run_dir = tile_dir / "runs" / "run-001"

        assert run_dir.exists(), f"run-001 not found at {run_dir}"
        assert (run_dir / "manifest.yaml").exists()
        assert (run_dir / "notes.md").exists()
        assert (run_dir / "summary.md").exists()
        assert (tile_dir / "README.md").exists()

        # CSV record appended
        import csv
        rows = list(csv.DictReader((db / "records.csv").read_text(encoding="utf-8").splitlines()))
        assert len(rows) == 1
        assert rows[0]["Tile_ID"] == tile_id
        assert rows[0]["Run_ID"] == "run-001"
    finally:
        shutil.rmtree(tmp)


def test_run_copies_rtl():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")

        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)

        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        run_dir = db / "tiles" / row["tile_id"] / "runs" / "run-001"
        assert (run_dir / "src" / "rtl" / "my_tile.v").exists()
    finally:
        shutil.rmtree(tmp)


def test_run_multiple_runs():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")

        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)

        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        tile_dir = db / "tiles" / row["tile_id"]
        assert (tile_dir / "runs" / "run-001").exists()
        assert (tile_dir / "runs" / "run-002").exists()
    finally:
        shutil.rmtree(tmp)


def test_manifest_custom_serializer():
    """Manifest should contain blank lines between sections."""
    from veriflow.generators.manifest import _render_manifest
    data = {
        "tile_id": "TST-01-26031500010101",
        "run_id": "run-001",
        "date": "2026-03-15",
        "author": "Tester",
        "objective": "Test",
        "status": "PASS",
        "tile": {"tile_name": "T", "top_module": "m", "version": "01", "revision": "01"},
        "tools": {"simulator": "iverilog", "simulator_version": "12.0", "synthesizer": "yosys", "synthesizer_version": ""},
        "run": {"sim_time": "", "seed": ""},
        "sources": {"rtl": ["tiles/x/runs/run-001/src/rtl/m.v"], "tb": []},
        "artifacts": {"connectivity_log": [], "sim_log": [], "synth_log": [], "wave": []},
        "results": {"connectivity": "PASS", "simulation": "SKIPPED", "synthesis": "PASS", "cells": "5", "warnings": "0", "errors": "0"},
    }
    rendered = _render_manifest(data)
    # Must have blank lines between sections
    assert "\n\n" in rendered
    # Must not use yaml.dump formatting
    assert "tile_id:" in rendered
    assert "results:" in rendered


def test_semicolab_true_creates_tb_tile_v():
    """semicolab: true should create tb_tile.v (self-contained, no tb_tasks.v)"""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        tb_dir = db / "config" / "tile_0001" / "src" / "tb"
        assert (tb_dir / "tb_tile.v").exists(), "tb_tile.v not found"
        assert not (tb_dir / "tb_tasks.v").exists(), "tb_tasks.v must not exist in new scaffold"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_false_creates_empty_tb():
    """interface_name: null should copy empty tb_tile.v, no tb_tasks.v"""
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": None}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        _make_tile(db)
        tb_dir = db / "config" / "tile_0001" / "src" / "tb"
        assert (tb_dir / "tb_tile.v").exists(), "tb_tile.v not found"
        assert not (tb_dir / "tb_tasks.v").exists(), "tb_tasks.v should not exist in universal mode"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_column_in_tile_index():
    """tile_index.csv should have semicolab column"""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        assert "semicolab" in row, "semicolab column missing from tile_index"
        assert row["semicolab"] == "true"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_column_in_records():
    """records.csv should have Semicolab column after a run"""
    import csv
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        rows = list(csv.DictReader((db / "records.csv").read_text(encoding="utf-8").splitlines()))
        assert len(rows) == 1
        assert "Semicolab" in rows[0], "Semicolab column missing from records"
        assert rows[0]["Semicolab"] == "true"
    finally:
        shutil.rmtree(tmp)


# ── VeriFlowError structured metadata ────────────────────────────────────────

def test_veriflow_error_str():
    from veriflow.core import VeriFlowError
    assert str(VeriFlowError("x")) == "x"


def test_veriflow_error_default_code():
    from veriflow.core import VeriFlowError
    assert VeriFlowError("x").to_dict()["code"] == "VF_ERROR"


def test_veriflow_error_custom_code():
    from veriflow.core import VeriFlowError
    assert VeriFlowError("x", code="VF_TEST").to_dict()["code"] == "VF_TEST"


def test_veriflow_error_to_dict_shape():
    from veriflow.core import VeriFlowError
    d = VeriFlowError("msg", code="VF_TOOL_NOT_FOUND", details={"tool": "iverilog"}).to_dict()
    assert d == {
        "code": "VF_TOOL_NOT_FOUND",
        "message": "msg",
        "details": {"tool": "iverilog"},
        "exit_code": 1,
    }


def test_veriflow_error_exit_code_default():
    from veriflow.core import VeriFlowError
    assert VeriFlowError("x").exit_code == 1


def test_veriflow_error_details_none_by_default():
    from veriflow.core import VeriFlowError
    assert VeriFlowError("x").details is None


def test_veriflow_error_db_missing_code():
    from veriflow.core import VeriFlowError
    from veriflow.core.validator import validate_database
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "empty_db"
        db.mkdir()
        try:
            validate_database(db)
        except VeriFlowError as e:
            assert e.code == "VF_DB_MISSING_REQUIRED_PATH"
            assert "path" in (e.details or {})
    finally:
        shutil.rmtree(tmp)


def test_veriflow_error_tool_not_found_code():
    import shutil as real_shutil
    from veriflow.core import VeriFlowError
    from veriflow.core.validator import validate_tools
    old_which = real_shutil.which
    try:
        real_shutil.which = lambda _: None
        try:
            validate_tools()
        except VeriFlowError as e:
            assert e.code == "VF_TOOL_NOT_FOUND"
            assert "tool" in (e.details or {})
    finally:
        real_shutil.which = old_which


def test_veriflow_error_rtl_missing_code():
    from veriflow.core import VeriFlowError
    from veriflow.core.validator import validate_run_inputs
    from veriflow.models.tile_config import TileConfig
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        tc = TileConfig.from_dict({"top_module": "my_tile"})
        try:
            validate_run_inputs(db, "0001", tc)
        except VeriFlowError as e:
            assert e.code == "VF_INPUT_RTL_MISSING"
    finally:
        shutil.rmtree(tmp)


def test_veriflow_error_top_module_missing_code():
    from veriflow.core import VeriFlowError
    from veriflow.core.validator import validate_run_inputs
    from veriflow.models.tile_config import TileConfig
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        tc = TileConfig.from_dict({})  # top_module = ""
        try:
            validate_run_inputs(db, "0001", tc)
        except VeriFlowError as e:
            assert e.code == "VF_INPUT_TOP_MODULE_MISSING"
    finally:
        shutil.rmtree(tmp)


def test_veriflow_error_top_module_file_missing_code():
    from veriflow.core import VeriFlowError
    from veriflow.core.validator import validate_run_inputs
    from veriflow.models.tile_config import TileConfig
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        tc = TileConfig.from_dict({"top_module": "nonexistent_module"})
        try:
            validate_run_inputs(db, "0001", tc)
        except VeriFlowError as e:
            assert e.code == "VF_INPUT_TOP_MODULE_FILE_MISSING"
            assert (e.details or {}).get("top_module") == "nonexistent_module"
    finally:
        shutil.rmtree(tmp)


# ── --json CLI smoke tests ────────────────────────────────────────────────────

def test_cli_normal_no_json_flag():
    """Normal mode (no --json) succeeds; return code is 0."""
    import shutil, tempfile
    from veriflow.cli import main
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        rc = main(["--db", str(db), "run", "--tile", "0001",
                   "--skip-check", "--skip-sim", "--skip-synth"])
        assert rc == 0
    finally:
        shutil.rmtree(tmp)


def test_cli_json_run_success():
    """--json mode emits valid JSON with status=SUCCESS and run_result."""
    import io, json, contextlib, shutil, tempfile
    from veriflow.cli import main
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--json", "--db", str(db), "run", "--tile", "0001",
                       "--skip-check", "--skip-sim", "--skip-synth"])

        assert rc == 0
        data = json.loads(buf.getvalue())
        assert data["status"] == "SUCCESS"
        assert data["command"] == "run"
        assert "run_result" in data
        assert data["run_result"]["schema_version"] == "1.1"
        assert "stages" in data["run_result"]
    finally:
        shutil.rmtree(tmp)


def test_cli_json_veriflow_error():
    """VeriFlowError in --json mode emits structured JSON error, not a traceback."""
    import io, json, contextlib, shutil, tempfile
    from veriflow.cli import main
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "empty_db"
        db.mkdir()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--json", "--db", str(db), "run", "--tile", "0001"])
        assert rc != 0
        data = json.loads(buf.getvalue())
        assert data["status"] == "ERROR"
        assert data["error"]["code"].startswith("VF_")
        assert "message" in data["error"]
    finally:
        shutil.rmtree(tmp)


def test_cli_json_unhandled_exception():
    """Unhandled exceptions in --json mode emit VF_UNHANDLED_EXCEPTION JSON."""
    import io, json, contextlib, shutil, tempfile
    from unittest.mock import patch
    from veriflow.cli import main
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "db"
        db.mkdir()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with patch("veriflow.commands.init_db.cmd_init",
                       side_effect=RuntimeError("synthetic failure")):
                rc = main(["--json", "--db", str(db), "init"])
        assert rc == 1
        data = json.loads(buf.getvalue())
        assert data["status"] == "ERROR"
        assert data["error"]["code"] == "VF_UNHANDLED_EXCEPTION"
        assert "synthetic failure" in data["error"]["message"]
    finally:
        shutil.rmtree(tmp)


# ── RunContext unit tests ─────────────────────────────────────────────────────

def test_run_context_property_paths():
    from veriflow.models.run_context import RunContext
    db = Path("/fake/db")
    tile_dir = db / "tiles" / "TST-01-260101000101"
    run_dir = tile_dir / "runs" / "run-001"
    ctx = RunContext(
        db_path=db,
        tile_id="TST-01-260101000101",
        run_id="run-001",
        tile_dir=tile_dir,
        run_dir=run_dir,
        semicolab=True,
        skip_connectivity=False,
        skip_sim=False,
        skip_synth=False,
    )
    assert ctx.src_dir == run_dir / "src"
    assert ctx.out_dir == run_dir / "out"
    assert ctx.sim_dir == run_dir / "out" / "sim"
    assert ctx.synth_dir == run_dir / "out" / "synth"
    assert ctx.impl_dir == run_dir / "out" / "connectivity"
    assert ctx.manifest_path == run_dir / "manifest.yaml"
    assert ctx.summary_path == run_dir / "summary.md"
    assert ctx.notes_path == run_dir / "notes.md"
    assert ctx.results_path == run_dir / "results.json"


def test_run_context_uses_pathlib():
    from veriflow.models.run_context import RunContext
    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    ctx = RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        semicolab=False, skip_connectivity=True,
        skip_sim=True, skip_synth=True,
    )
    for prop in (ctx.src_dir, ctx.out_dir, ctx.sim_dir, ctx.synth_dir,
                 ctx.impl_dir, ctx.manifest_path, ctx.summary_path,
                 ctx.notes_path, ctx.results_path):
        assert isinstance(prop, Path), f"Expected Path, got {type(prop)}"


def test_run_context_no_file_creation():
    import tempfile, shutil
    from veriflow.models.run_context import RunContext
    tmp = Path(tempfile.mkdtemp())
    try:
        run_dir = tmp / "tiles" / "X" / "runs" / "run-001"
        ctx = RunContext(
            db_path=tmp, tile_id="X", run_id="run-001",
            tile_dir=tmp / "tiles" / "X",
            run_dir=run_dir,
            semicolab=True, skip_connectivity=False,
            skip_sim=False, skip_synth=False,
        )
        _ = ctx.src_dir
        _ = ctx.manifest_path
        _ = ctx.results_path
        assert not run_dir.exists(), "RunContext must not create directories on access"
    finally:
        shutil.rmtree(tmp)


# ── StageResult unit tests ────────────────────────────────────────────────────

def test_stage_result_minimal_to_dict():
    from veriflow.models.stage_result import StageResult
    sr = StageResult(name="connectivity", status="PASS", tool="iverilog")
    d = sr.to_dict()
    assert d["tool"] == "iverilog"
    assert d["status"] == "PASS"
    assert "logs" not in d
    assert "artifacts" not in d
    assert "metrics" not in d
    assert "error" not in d


def test_stage_result_with_logs_artifacts_metrics():
    from veriflow.models.stage_result import StageResult
    sr = StageResult(
        name="synthesis",
        status="PASS",
        tool="yosys",
        log_paths=["tiles/x/runs/run-001/out/synth/logs/synth.log"],
        artifacts={"report": ["tiles/x/runs/run-001/out/synth/reports/report.txt"]},
        metrics={"cells": "42", "warnings": "0", "errors": "0", "has_latches": False},
    )
    d = sr.to_dict()
    assert d["tool"] == "yosys"
    assert d["status"] == "PASS"
    assert d["logs"] == ["tiles/x/runs/run-001/out/synth/logs/synth.log"]
    assert d["artifacts"] == {"report": ["tiles/x/runs/run-001/out/synth/reports/report.txt"]}
    assert d["metrics"]["cells"] == "42"
    assert d["metrics"]["has_latches"] is False
    assert "error" not in d


def test_stage_result_no_filesystem_access():
    from veriflow.models.stage_result import StageResult
    sr = StageResult(name="simulation", status="SKIPPED")
    d = sr.to_dict()
    assert d["status"] == "SKIPPED"
    assert "tool" not in d
    assert "logs" not in d


def test_stage_result_skipped_omits_empty_fields():
    from veriflow.models.stage_result import StageResult
    sr = StageResult(name="synthesis", status="SKIPPED", tool="yosys", log_paths=[])
    d = sr.to_dict()
    assert "logs" not in d, "Empty log_paths should be omitted"
    assert "artifacts" not in d
    assert "metrics" not in d


def test_stage_result_error_field_included():
    from veriflow.models.stage_result import StageResult
    err = {"code": "VF_ERROR", "message": "tool crashed"}
    sr = StageResult(name="sim", status="FAIL", error=err)
    d = sr.to_dict()
    assert d["error"] == err


# ── api.run_tile tests ────────────────────────────────────────────────────────

def test_api_run_tile_returns_dict():
    """api.run_tile exists and returns a dict for a smoke run (all stages skipped)."""
    import shutil, tempfile
    from veriflow import api
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        result = api.run_tile(
            db, "0001",
            skip_connectivity=True, skip_sim=True, skip_synth=True,
        )
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result["schema_version"] == "1.1"
        assert "stages" in result
    finally:
        shutil.rmtree(tmp)


def test_api_run_tile_propagates_veriflow_error():
    """api.run_tile propagates VeriFlowError from cmd_run."""
    import shutil, tempfile
    from veriflow import api
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "empty_db"
        db.mkdir()
        raised = False
        try:
            api.run_tile(db, "0001", skip_connectivity=True, skip_sim=True, skip_synth=True)
        except VeriFlowError:
            raised = True
        assert raised, "Expected VeriFlowError to propagate from api.run_tile"
    finally:
        shutil.rmtree(tmp)


def test_api_run_tile_rejects_waves_non_interactive():
    """api.run_tile raises VF_NON_INTERACTIVE_VIEWER_DISABLED when waves=True and non_interactive=True."""
    from veriflow import api
    from veriflow.core import VeriFlowError
    raised = False
    try:
        api.run_tile("./fake", "0001", waves=True, non_interactive=True)
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_NON_INTERACTIVE_VIEWER_DISABLED"
        assert e.exit_code == 2
    assert raised, "Expected VF_NON_INTERACTIVE_VIEWER_DISABLED"


# ── registry ──────────────────────────────────────────────────────────────────

def test_cli_non_interactive_no_command():
    """--non-interactive without a subcommand returns VF_NON_INTERACTIVE_REQUIRES_COMMAND (rc=2)."""
    import io, contextlib
    from veriflow.cli import main
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = main(["--non-interactive"])
    assert rc == 2
    assert "--non-interactive requires" in buf.getvalue()


def test_cli_non_interactive_no_command_json():
    """--non-interactive + --json without a subcommand emits a structured JSON error."""
    import io, json, contextlib
    from veriflow.cli import main
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["--non-interactive", "--json"])
    assert rc == 2
    data = json.loads(buf.getvalue())
    assert data["status"] == "ERROR"
    assert data["error"]["code"] == "VF_NON_INTERACTIVE_REQUIRES_COMMAND"
    assert "--non-interactive requires" in data["error"]["message"]


def test_cli_non_interactive_run_succeeds():
    """--non-interactive run without --waves completes normally."""
    import shutil, tempfile
    from veriflow.cli import main
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        rc = main([
            "--db", str(db), "--non-interactive",
            "run", "--tile", "0001",
            "--skip-check", "--skip-sim", "--skip-synth",
        ])
        assert rc == 0
    finally:
        shutil.rmtree(tmp)


def test_cli_non_interactive_waves_command_rejected():
    """waves subcommand + --non-interactive is rejected with VF_NON_INTERACTIVE_VIEWER_DISABLED."""
    import io, contextlib, shutil, tempfile
    from veriflow.cli import main
    tmp = Path(tempfile.mkdtemp())
    try:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = main(["--db", str(tmp), "--non-interactive", "waves", "--tile", "0001"])
        assert rc == 2
        assert "Waveform viewer" in buf.getvalue()
    finally:
        shutil.rmtree(tmp)


def test_cli_non_interactive_run_waves_rejected():
    """run --waves + --non-interactive is rejected with VF_NON_INTERACTIVE_VIEWER_DISABLED."""
    import io, contextlib, shutil, tempfile
    from veriflow.cli import main
    tmp = Path(tempfile.mkdtemp())
    try:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = main(["--db", str(tmp), "--non-interactive", "run", "--tile", "0001", "--waves"])
        assert rc == 2
        assert "Waveform viewer" in buf.getvalue()
    finally:
        shutil.rmtree(tmp)


def test_launch_waves_docker_uses_surfer_wasm():
    """Docker mode should delegate to Surfer WASM."""
    import os
    from veriflow.core import sim_runner

    old_env = os.environ.get("SEMICOLAB_DOCKER")
    old_open_surfer = sim_runner.open_surfer
    calls = []

    try:
        os.environ["SEMICOLAB_DOCKER"] = "1"
        sim_runner.open_surfer = lambda wave_path: calls.append(wave_path)
        wave_path = Path("waves.vcd")
        sim_runner.launch_waves(wave_path)
        assert calls == [wave_path]
    finally:
        if old_env is None:
            os.environ.pop("SEMICOLAB_DOCKER", None)
        else:
            os.environ["SEMICOLAB_DOCKER"] = old_env
        sim_runner.open_surfer = old_open_surfer


def test_launch_waves_local_uses_surfer_native():
    """Local mode should launch native Surfer when it is available."""
    import os
    import platform as real_platform
    import shutil as real_shutil
    from veriflow.core import sim_runner

    old_env = os.environ.get("SEMICOLAB_DOCKER")
    old_system = real_platform.system
    old_which = real_shutil.which
    old_popen = sim_runner.subprocess.Popen
    calls = []

    def fake_popen(cmd, **kwargs):
        calls.append((cmd, kwargs))

    try:
        os.environ.pop("SEMICOLAB_DOCKER", None)
        real_platform.system = lambda: "Linux"
        real_shutil.which = lambda tool: "C:/tools/surfer.exe" if tool == "surfer" else None
        sim_runner.subprocess.Popen = fake_popen

        wave_path = Path("waves.vcd")
        sim_runner.launch_waves(wave_path)

        assert calls, "Expected Surfer process launch"
        assert calls[0][0] == ["C:/tools/surfer.exe", str(wave_path)]
    finally:
        if old_env is None:
            os.environ.pop("SEMICOLAB_DOCKER", None)
        else:
            os.environ["SEMICOLAB_DOCKER"] = old_env
        real_platform.system = old_system
        real_shutil.which = old_which
        sim_runner.subprocess.Popen = old_popen


def test_launch_waves_local_without_surfer_prints_hint():
    """Local mode should require Surfer instead of using a legacy fallback."""
    import os
    import io
    import contextlib
    import shutil as real_shutil
    from veriflow.core import sim_runner

    old_env = os.environ.get("SEMICOLAB_DOCKER")
    old_which = real_shutil.which

    try:
        os.environ.pop("SEMICOLAB_DOCKER", None)
        real_shutil.which = lambda tool: None

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sim_runner.launch_waves(Path("waves.vcd"))

        output = buf.getvalue()
        assert "Surfer not found in PATH" in output
        assert ("GTK" + "Wave") not in output
        assert ("gtk" + "wave") not in output
    finally:
        if old_env is None:
            os.environ.pop("SEMICOLAB_DOCKER", None)
        else:
            os.environ["SEMICOLAB_DOCKER"] = old_env
        real_shutil.which = old_which


# ── InterfaceStage unit tests ─────────────────────────────────────────────

def _make_ctx_conn(skip_connectivity: bool = True) -> "RunContext":
    from veriflow.models.run_context import RunContext
    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    return RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        semicolab=True, skip_connectivity=skip_connectivity,
        skip_sim=True, skip_synth=True,
    )


def test_connectivity_stage_is_pipeline_stage():
    from veriflow.core.pipeline import PipelineStage
    from veriflow.core.stages.connectivity import InterfaceStage
    assert issubclass(InterfaceStage, PipelineStage)
    assert InterfaceStage.name == "connectivity"


def test_connectivity_stage_skipped_returns_stage_result():
    from veriflow.core.stages.connectivity import InterfaceStage
    from veriflow.models.stage_result import StageResult
    ctx = _make_ctx_conn(skip_connectivity=True)
    result = InterfaceStage(
        interface_profile=None,
    ).run(_make_stage_input(ctx))
    assert isinstance(result, StageResult)
    assert result.status == "SKIPPED"
    assert result.name == "connectivity"
    assert result.tool == "iverilog"
    assert result.metrics is None


def test_connectivity_fail_still_finalizes_run():
    """Connectivity FAIL stops further stages but still writes results.json."""
    import json
    from unittest.mock import patch
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)  # semicolab=True by default
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")

        from veriflow.commands.run import cmd_run
        with patch("veriflow.core.backends.icarus.run_connectivity_check", return_value="FAIL"):
            result = cmd_run(
                db=db, tile_number="0001",
                skip_check=False, skip_sim=True, skip_synth=True,
            )

        assert result["schema_version"] == "1.1"
        assert result["stages"]["connectivity"]["status"] == "FAIL"

        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        results_path = (
            db / "tiles" / row["tile_id"] / "runs" / "run-001" / "results.json"
        )
        assert results_path.exists(), "results.json must exist even after connectivity FAIL"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.1"
        assert data["stages"]["connectivity"]["status"] == "FAIL"
    finally:
        shutil.rmtree(tmp)


# ── PipelineStage / SynthesisStage unit tests ────────────────────────────────

def _make_ctx(skip_synth: bool = True) -> "RunContext":
    from veriflow.models.run_context import RunContext
    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    return RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        semicolab=False, skip_connectivity=True,
        skip_sim=True, skip_synth=skip_synth,
    )


def test_pipeline_stage_not_implemented():
    from veriflow.core.pipeline import PipelineStage
    raised = False
    try:
        PipelineStage().run(_make_stage_input(_make_ctx()))
    except NotImplementedError:
        raised = True
    assert raised, "PipelineStage.run() must raise NotImplementedError"


def test_synthesis_stage_is_pipeline_stage():
    from veriflow.core.pipeline import PipelineStage
    from veriflow.core.stages.synthesis import SynthesisStage
    assert issubclass(SynthesisStage, PipelineStage)
    assert SynthesisStage.name == "synthesis"


def test_synthesis_stage_skipped_returns_stage_result():
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.models.stage_result import StageResult
    ctx = _make_ctx(skip_synth=True)
    result = SynthesisStage().run(_make_stage_input(ctx))
    assert isinstance(result, StageResult)
    assert result.status == "SKIPPED"
    assert result.name == "synthesis"
    assert result.tool == "yosys"
    assert result.metrics is None


# ── PipelineBuilder unit tests ────────────────────────────────────────────────

def test_build_default_pipeline_returns_runner():
    from veriflow.core.pipeline import PipelineRunner
    from veriflow.core.pipeline_builder import build_default_pipeline
    runner = build_default_pipeline(
        rtl_files=[Path("/nonexistent/my_tile.v")],
        tb_files=[],
        tb_top="tb",
        top_module="my_tile",
    )
    assert isinstance(runner, PipelineRunner)


def test_build_default_pipeline_stage_order():
    from veriflow.core.pipeline_builder import build_default_pipeline
    runner = build_default_pipeline(
        rtl_files=[Path("/nonexistent/my_tile.v")],
        tb_files=[],
        tb_top="tb",
        top_module="my_tile",
    )
    assert [s.name for s in runner.stages] == ["connectivity", "simulation", "synthesis"]


# ── PipelineRunner unit tests ─────────────────────────────────────────────────

def test_pipeline_runner_executes_in_order():
    from veriflow.core.pipeline import PipelineRunner, PipelineStage
    from veriflow.models.stage_result import StageResult

    call_order: list[str] = []

    class StageA(PipelineStage):
        name = "stage_a"
        def run(self, input):
            call_order.append("a")
            return StageResult(name=self.name, status="PASS")

    class StageB(PipelineStage):
        name = "stage_b"
        def run(self, input):
            call_order.append("b")
            return StageResult(name=self.name, status="PASS")

    PipelineRunner([StageA(), StageB()], design=_make_design()).run(_make_ctx())
    assert call_order == ["a", "b"]


def test_pipeline_runner_returns_stage_result_by_name():
    from veriflow.core.pipeline import PipelineRunner, PipelineStage
    from veriflow.models.stage_result import StageResult

    class StageA(PipelineStage):
        name = "stage_a"
        def run(self, input):
            return StageResult(name=self.name, status="PASS")

    class StageB(PipelineStage):
        name = "stage_b"
        def run(self, input):
            return StageResult(name=self.name, status="SKIPPED")

    results = PipelineRunner([StageA(), StageB()], design=_make_design()).run(_make_ctx())
    assert set(results.keys()) == {"stage_a", "stage_b"}
    assert results["stage_a"].status == "PASS"
    assert results["stage_b"].status == "SKIPPED"
    assert isinstance(results["stage_a"], StageResult)


def test_pipeline_runner_propagates_veriflow_error():
    from veriflow.core import VeriFlowError
    from veriflow.core.pipeline import PipelineRunner, PipelineStage

    class FailStage(PipelineStage):
        name = "fail_stage"
        def run(self, input):
            raise VeriFlowError("stage failed", code="VF_TEST_FAIL")

    raised = False
    try:
        PipelineRunner([FailStage()], design=_make_design()).run(_make_ctx())
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_TEST_FAIL"
    assert raised, "PipelineRunner must propagate VeriFlowError"


# ── SimulationStage unit tests ────────────────────────────────────────────────

def _make_ctx_sim(skip_sim: bool = True) -> "RunContext":
    from veriflow.models.run_context import RunContext
    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    return RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        semicolab=False, skip_connectivity=True,
        skip_sim=skip_sim, skip_synth=True,
    )


def test_simulation_stage_is_pipeline_stage():
    from veriflow.core.pipeline import PipelineStage
    from veriflow.core.stages.simulation import SimulationStage
    assert issubclass(SimulationStage, PipelineStage)
    assert SimulationStage.name == "simulation"


def test_simulation_stage_skipped_returns_stage_result():
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.models.stage_result import StageResult
    ctx = _make_ctx_sim(skip_sim=True)
    result = SimulationStage(tb_top="tb").run(_make_stage_input(ctx, design=_make_design_with_tb()))
    assert isinstance(result, StageResult)
    assert result.status == "SKIPPED"
    assert result.name == "simulation"
    assert result.tool == "iverilog/vvp"
    assert result.metrics is None


def test_simulation_stage_skipped_no_tb():
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.models.stage_result import StageResult
    ctx = _make_ctx_sim(skip_sim=False)
    result = SimulationStage(tb_top="tb").run(_make_stage_input(ctx, design=_make_design()))
    assert isinstance(result, StageResult)
    assert result.status == "SKIPPED"
    assert result.name == "simulation"
    assert result.metrics is None


def test_results_json_schema_version():
    """results.json schema_version must remain 1.1 and stages structure unchanged."""
    import json
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        result = cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        assert result["schema_version"] == "1.1"
        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        results_path = db / "tiles" / row["tile_id"] / "runs" / "run-001" / "results.json"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.1"
        assert "stages" in data
        assert "simulation" in data["stages"]
        assert "synthesis" in data["stages"]
        assert "connectivity" in data["stages"]
    finally:
        shutil.rmtree(tmp)


# ── ExecutionProfile unit tests ──────────────────────────────────────────────

def test_default_execution_profile_values():
    from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
    p = default_execution_profile()
    assert isinstance(p, ExecutionProfile)
    assert p.name == "default"
    assert p.connectivity_tool == "iverilog"
    assert p.simulation_tool == "iverilog/vvp"
    assert p.synthesis_tool == "yosys"
    assert p.doc_profile == "default"


def test_execution_profile_is_dataclass():
    import dataclasses
    from veriflow.models.execution_profile import ExecutionProfile
    assert dataclasses.is_dataclass(ExecutionProfile)


def test_build_default_pipeline_accepts_profile():
    from veriflow.core.pipeline import PipelineRunner
    from veriflow.core.pipeline_builder import build_default_pipeline
    from veriflow.models.execution_profile import default_execution_profile
    runner = build_default_pipeline(
        rtl_files=[Path("/nonexistent/my_tile.v")],
        tb_files=[],
        tb_top="tb",
        top_module="my_tile",
        profile=default_execution_profile(),
    )
    assert isinstance(runner, PipelineRunner)


def test_build_default_pipeline_uses_profile_tool_labels():
    """Stage tool labels in StageResult reflect the profile's tool strings."""
    from veriflow.core.pipeline_builder import build_default_pipeline
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.run_context import RunContext

    profile = ExecutionProfile(
        connectivity_tool="iverilog",
        simulation_tool="iverilog/vvp",
        synthesis_tool="yosys",
    )
    runner = build_default_pipeline(
        rtl_files=[Path("/nonexistent/my_tile.v")], tb_files=[],
        tb_top="tb", top_module="my_tile", profile=profile,
    )

    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    ctx = RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        semicolab=False, skip_connectivity=True,
        skip_sim=True, skip_synth=True,
    )
    results = runner.run(ctx)
    assert results["connectivity"].tool == "iverilog"
    assert results["simulation"].tool == "iverilog/vvp"
    assert results["synthesis"].tool == "yosys"


def test_results_json_tool_strings_unchanged():
    """results.json tool strings remain identical after ExecutionProfile introduction."""
    import json
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        results_path = db / "tiles" / row["tile_id"] / "runs" / "run-001" / "results.json"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert data["stages"]["connectivity"]["tool"] == "iverilog"
        assert data["stages"]["simulation"]["tool"] == "iverilog/vvp"
        assert data["stages"]["synthesis"]["tool"] == "yosys"
    finally:
        shutil.rmtree(tmp)


def test_backend_base_classes_exist():
    import abc
    from veriflow.core.backends.base import ConnectivityBackend, SimulationBackend, SynthesisBackend
    assert issubclass(ConnectivityBackend, abc.ABC)
    assert issubclass(SimulationBackend, abc.ABC)
    assert issubclass(SynthesisBackend, abc.ABC)


def test_icarus_connectivity_backend_exists():
    from veriflow.core.backends.icarus import IcarusConnectivityBackend
    from veriflow.core.backends.base import ConnectivityBackend
    backend = IcarusConnectivityBackend()
    assert isinstance(backend, ConnectivityBackend)


def test_icarus_simulation_backend_exists():
    from veriflow.core.backends.icarus import IcarusSimulationBackend
    from veriflow.core.backends.base import SimulationBackend
    backend = IcarusSimulationBackend()
    assert isinstance(backend, SimulationBackend)


def test_yosys_synthesis_backend_exists():
    from veriflow.core.backends.yosys import YosysSynthesisBackend
    from veriflow.core.backends.base import SynthesisBackend
    backend = YosysSynthesisBackend()
    assert isinstance(backend, SynthesisBackend)


def test_backends_package_exports():
    from veriflow.core import backends
    assert hasattr(backends, "ConnectivityBackend")
    assert hasattr(backends, "SimulationBackend")
    assert hasattr(backends, "SynthesisBackend")
    assert hasattr(backends, "IcarusConnectivityBackend")
    assert hasattr(backends, "IcarusSimulationBackend")
    assert hasattr(backends, "YosysSynthesisBackend")


def test_icarus_connectivity_backend_delegates_to_runner():
    from unittest.mock import patch
    from veriflow.core.backends.icarus import IcarusConnectivityBackend
    from veriflow.models.interface_profile import semicolab_interface_profile
    backend = IcarusConnectivityBackend()
    profile = semicolab_interface_profile()
    with patch("veriflow.core.backends.icarus.run_connectivity_check", return_value="PASS") as mock_fn:
        result = backend.run_connectivity(
            rtl_files=[Path("a.v")],
            interface_profile=profile,
            top_module="top",
            log_path=Path("conn.log"),
        )
    assert result == "PASS"
    mock_fn.assert_called_once()


def test_icarus_simulation_backend_delegates_to_runner():
    from unittest.mock import patch
    from veriflow.core.backends.icarus import IcarusSimulationBackend
    backend = IcarusSimulationBackend()
    with patch(
        "veriflow.core.backends.icarus.run_simulation",
        return_value=("COMPLETED", {"sim_time": "10ns", "seed": "42"}),
    ) as mock_fn:
        status, parsed = backend.run_simulation(
            rtl_files=[Path("a.v")],
            tb_files=[Path("tb.v")],
            tb_top="tb",
            sim_log_path=Path("sim.log"),
            wave_path=Path("waves.vcd"),
        )
    assert status == "COMPLETED"
    assert parsed["sim_time"] == "10ns"
    mock_fn.assert_called_once()


def test_yosys_synthesis_backend_delegates_to_runner():
    from unittest.mock import patch
    from veriflow.core.backends.yosys import YosysSynthesisBackend
    backend = YosysSynthesisBackend()
    with patch(
        "veriflow.core.backends.yosys.run_synthesis",
        return_value=("PASS", {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False}),
    ) as mock_fn:
        status, parsed = backend.run_synthesis(
            rtl_files=[Path("a.v")],
            top_module="top",
            synth_log_path=Path("synth.log"),
        )
    assert status == "PASS"
    assert parsed["cells"] == "5"
    mock_fn.assert_called_once()


def test_connectivity_stage_uses_backend():
    from unittest.mock import MagicMock
    from veriflow.core.stages.connectivity import InterfaceStage
    from veriflow.core.backends.base import ConnectivityBackend
    from veriflow.models.interface_profile import semicolab_interface_profile

    mock_backend = MagicMock(spec=ConnectivityBackend)
    mock_backend.run_connectivity.return_value = "PASS"

    stage = InterfaceStage(
        interface_profile=semicolab_interface_profile(),
        backend=mock_backend,
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_connectivity = False
        ctx.impl_dir = tmp / "impl"
        ctx.db_path = tmp / "db"
        result = stage.run(_make_stage_input(ctx))
        mock_backend.run_connectivity.assert_called_once()
        assert result.status == "PASS"
    finally:
        shutil.rmtree(tmp)


def test_simulation_stage_uses_backend():
    from unittest.mock import MagicMock
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SimulationBackend

    mock_backend = MagicMock(spec=SimulationBackend)
    mock_backend.run_simulation.return_value = ("COMPLETED", {"sim_time": "10ns", "seed": "42"})

    stage = SimulationStage(tb_top="tb", backend=mock_backend)

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_sim = False
        ctx.sim_dir = tmp / "sim"
        ctx.db_path = tmp / "db"
        result = stage.run(_make_stage_input(ctx, design=_make_design_with_tb()))
        mock_backend.run_simulation.assert_called_once()
        assert result.status == "COMPLETED"
    finally:
        shutil.rmtree(tmp)


def test_synthesis_stage_uses_backend():
    from unittest.mock import MagicMock
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.core.backends.base import SynthesisBackend

    mock_backend = MagicMock(spec=SynthesisBackend)
    mock_backend.run_synthesis.return_value = (
        "PASS",
        {"cells": "3", "warnings": "0", "errors": "0", "has_latches": False},
    )

    stage = SynthesisStage(backend=mock_backend)

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_synth = False
        ctx.synth_dir = tmp / "synth"
        ctx.db_path = tmp / "db"
        result = stage.run(_make_stage_input(ctx))
        mock_backend.run_synthesis.assert_called_once()
        assert result.status == "PASS"
    finally:
        shutil.rmtree(tmp)


# ── Backend registry tests ────────────────────────────────────────────────────

def test_registry_connectivity_icarus_returns_correct_class():
    from veriflow.core.backends.registry import get_connectivity_backend
    from veriflow.core.backends.icarus import IcarusConnectivityBackend
    backend = get_connectivity_backend("icarus")
    assert isinstance(backend, IcarusConnectivityBackend)


def test_registry_simulation_icarus_returns_correct_class():
    from veriflow.core.backends.registry import get_simulation_backend
    from veriflow.core.backends.icarus import IcarusSimulationBackend
    backend = get_simulation_backend("icarus")
    assert isinstance(backend, IcarusSimulationBackend)


def test_registry_synthesis_yosys_returns_correct_class():
    from veriflow.core.backends.registry import get_synthesis_backend
    from veriflow.core.backends.yosys import YosysSynthesisBackend
    backend = get_synthesis_backend("yosys")
    assert isinstance(backend, YosysSynthesisBackend)


def test_registry_connectivity_unknown_raises():
    from veriflow.core.backends.registry import get_connectivity_backend
    from veriflow.core import VeriFlowError
    try:
        get_connectivity_backend("unknown_backend")
        assert False, "Expected VeriFlowError"
    except VeriFlowError as e:
        assert e.code == "VF_BACKEND_CONNECTIVITY_UNKNOWN"


def test_registry_simulation_unknown_raises():
    from veriflow.core.backends.registry import get_simulation_backend
    from veriflow.core import VeriFlowError
    try:
        get_simulation_backend("unknown_backend")
        assert False, "Expected VeriFlowError"
    except VeriFlowError as e:
        assert e.code == "VF_BACKEND_SIMULATION_UNKNOWN"


def test_registry_synthesis_unknown_raises():
    from veriflow.core.backends.registry import get_synthesis_backend
    from veriflow.core import VeriFlowError
    try:
        get_synthesis_backend("unknown_backend")
        assert False, "Expected VeriFlowError"
    except VeriFlowError as e:
        assert e.code == "VF_BACKEND_SYNTHESIS_UNKNOWN"


def test_execution_profile_has_backend_ids():
    from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
    p = default_execution_profile()
    assert p.connectivity_backend == "icarus"
    assert p.simulation_backend == "icarus"
    assert p.synthesis_backend == "yosys"


def test_build_default_pipeline_uses_registry_backends():
    """build_default_pipeline routes through registry; tool labels are unchanged."""
    from veriflow.core.pipeline_builder import build_default_pipeline
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.run_context import RunContext

    profile = ExecutionProfile(
        connectivity_tool="iverilog",
        simulation_tool="iverilog/vvp",
        synthesis_tool="yosys",
        connectivity_backend="icarus",
        simulation_backend="icarus",
        synthesis_backend="yosys",
    )
    runner = build_default_pipeline(
        rtl_files=[Path("/nonexistent/my_tile.v")], tb_files=[],
        tb_top="tb", top_module="my_tile", profile=profile,
    )

    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    ctx = RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        semicolab=False, skip_connectivity=True,
        skip_sim=True, skip_synth=True,
    )
    results = runner.run(ctx)
    assert results["connectivity"].tool == "iverilog"
    assert results["simulation"].tool == "iverilog/vvp"
    assert results["synthesis"].tool == "yosys"


# ── technology profile foundation ────────────────────────────────────────────

def test_technology_profile_default_values():
    from veriflow.models.technology_profile import TechnologyProfile, default_technology_profile
    p = default_technology_profile()
    assert isinstance(p, TechnologyProfile)
    assert p.name == "generic"
    assert p.pdk is None
    assert p.cell_library is None
    assert p.liberty is None
    assert p.constraints is None
    assert p.notes is None


def test_technology_profile_registry_supported_names():
    from veriflow.models.technology_profile import get_technology_profile
    for name in ("generic", "sky130", "gf180", "ihp130"):
        p = get_technology_profile(name)
        assert p.name == name


def test_technology_profile_unknown_raises():
    from veriflow.models.technology_profile import get_technology_profile
    from veriflow.core import VeriFlowError
    try:
        get_technology_profile("notapdkname")
        assert False, "Expected VeriFlowError"
    except VeriFlowError as e:
        assert e.code == "VF_TECHNOLOGY_UNKNOWN"


def test_execution_profile_technology_name_default():
    from veriflow.models.execution_profile import default_execution_profile
    p = default_execution_profile()
    assert p.technology_name == "generic"


def test_execution_profile_backward_compatible_with_technology():
    from veriflow.models.execution_profile import ExecutionProfile
    p = ExecutionProfile()
    assert p.name == "default"
    assert p.connectivity_backend == "icarus"
    assert p.simulation_backend == "icarus"
    assert p.synthesis_backend == "yosys"
    assert p.technology_name == "generic"


# ── profile_loader tests ──────────────────────────────────────────────────────

def test_load_profile_minimal():
    """A YAML with only 'name' loads and all other fields take defaults."""
    import tempfile, shutil, yaml
    from veriflow.models.profile_loader import load_execution_profile
    from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
    tmp = Path(tempfile.mkdtemp())
    try:
        p_file = tmp / "profile.yaml"
        p_file.write_text(yaml.dump({"name": "ci"}), encoding="utf-8")
        profile = load_execution_profile(p_file)
        assert isinstance(profile, ExecutionProfile)
        assert profile.name == "ci"
        defaults = default_execution_profile()
        assert profile.connectivity_backend == defaults.connectivity_backend
        assert profile.simulation_backend == defaults.simulation_backend
        assert profile.synthesis_backend == defaults.synthesis_backend
        assert profile.connectivity_tool == defaults.connectivity_tool
        assert profile.simulation_tool == defaults.simulation_tool
        assert profile.synthesis_tool == defaults.synthesis_tool
        assert profile.technology_name == defaults.technology_name
        assert profile.doc_profile == defaults.doc_profile
    finally:
        shutil.rmtree(tmp)


def test_load_profile_full():
    """A YAML with all supported keys loads correctly."""
    import tempfile, shutil, yaml
    from veriflow.models.profile_loader import load_execution_profile
    from veriflow.models.execution_profile import ExecutionProfile
    tmp = Path(tempfile.mkdtemp())
    try:
        data = {
            "name": "full",
            "connectivity_backend": "icarus",
            "simulation_backend": "icarus",
            "synthesis_backend": "yosys",
            "connectivity_tool": "iverilog",
            "simulation_tool": "iverilog/vvp",
            "synthesis_tool": "yosys",
            "technology_name": "sky130",
            "doc_profile": "custom",
        }
        p_file = tmp / "profile.yaml"
        p_file.write_text(yaml.dump(data), encoding="utf-8")
        profile = load_execution_profile(p_file)
        assert isinstance(profile, ExecutionProfile)
        assert profile.name == "full"
        assert profile.connectivity_backend == "icarus"
        assert profile.simulation_backend == "icarus"
        assert profile.synthesis_backend == "yosys"
        assert profile.connectivity_tool == "iverilog"
        assert profile.simulation_tool == "iverilog/vvp"
        assert profile.synthesis_tool == "yosys"
        assert profile.technology_name == "sky130"
        assert profile.doc_profile == "custom"
    finally:
        shutil.rmtree(tmp)


def test_load_profile_unknown_key_raises():
    """An unknown key in the YAML raises VF_PROFILE_UNKNOWN_KEY."""
    import tempfile, shutil, yaml
    from veriflow.models.profile_loader import load_execution_profile
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        p_file = tmp / "profile.yaml"
        p_file.write_text(yaml.dump({"name": "x", "bad_key": "value"}), encoding="utf-8")
        raised = False
        try:
            load_execution_profile(p_file)
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_PROFILE_UNKNOWN_KEY"
            assert "bad_key" in str(e)
        assert raised, "Expected VF_PROFILE_UNKNOWN_KEY"
    finally:
        shutil.rmtree(tmp)


def test_load_profile_invalid_backend_raises():
    """An unrecognised connectivity_backend propagates the registry VeriFlowError."""
    import tempfile, shutil, yaml
    from veriflow.models.profile_loader import load_execution_profile
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        p_file = tmp / "profile.yaml"
        p_file.write_text(yaml.dump({"connectivity_backend": "notabackend"}), encoding="utf-8")
        raised = False
        try:
            load_execution_profile(p_file)
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_BACKEND_CONNECTIVITY_UNKNOWN"
        assert raised, "Expected VF_BACKEND_CONNECTIVITY_UNKNOWN"
    finally:
        shutil.rmtree(tmp)


def test_load_profile_invalid_technology_raises():
    """An unrecognised technology_name propagates VF_TECHNOLOGY_UNKNOWN."""
    import tempfile, shutil, yaml
    from veriflow.models.profile_loader import load_execution_profile
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        p_file = tmp / "profile.yaml"
        p_file.write_text(yaml.dump({"technology_name": "notapdk"}), encoding="utf-8")
        raised = False
        try:
            load_execution_profile(p_file)
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_TECHNOLOGY_UNKNOWN"
        assert raised, "Expected VF_TECHNOLOGY_UNKNOWN"
    finally:
        shutil.rmtree(tmp)


# ── A. Stage migration tests ──────────────────────────────────────────────────

def test_synthesis_stage_reads_design_rtl_and_top_module():
    from unittest.mock import MagicMock
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.core.backends.base import SynthesisBackend

    mock_backend = MagicMock(spec=SynthesisBackend)
    mock_backend.run_synthesis.return_value = (
        "PASS",
        {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False},
    )
    stage = SynthesisStage(backend=mock_backend)

    rtl = Path("/nonexistent/top.v")
    design = Design(top_module="my_top", rtl_sources=[rtl])

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_synth = False
        ctx.synth_dir = tmp / "synth"
        stage.run(StageInput(design=design, context=ctx))
        call_kwargs = mock_backend.run_synthesis.call_args
        assert call_kwargs.kwargs["rtl_files"] == [rtl]
        assert call_kwargs.kwargs["top_module"] == "my_top"
    finally:
        shutil.rmtree(tmp)


def test_simulation_stage_reads_rtl_and_tb_sources_from_design():
    from unittest.mock import MagicMock
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SimulationBackend

    mock_backend = MagicMock(spec=SimulationBackend)
    mock_backend.run_simulation.return_value = ("COMPLETED", {})

    stage = SimulationStage(tb_top="tb", backend=mock_backend)

    rtl = Path("/nonexistent/top.v")
    tb = Path("/nonexistent/tb.v")
    design = Design(top_module="my_top", rtl_sources=[rtl], tb_sources=[tb])

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_sim = False
        ctx.sim_dir = tmp / "sim"
        stage.run(StageInput(design=design, context=ctx))
        call_kwargs = mock_backend.run_simulation.call_args
        assert call_kwargs.kwargs["rtl_files"] == [rtl]
        assert call_kwargs.kwargs["tb_files"] == [tb]
        assert call_kwargs.kwargs["tb_top"] == "tb"
    finally:
        shutil.rmtree(tmp)


def test_simulation_stage_no_tb_skips_from_empty_tb_sources():
    from unittest.mock import MagicMock
    from veriflow.core.stages.simulation import SimulationStage

    stage = SimulationStage(tb_top="tb")
    design = Design(top_module="my_top", rtl_sources=[Path("/nonexistent/top.v")])

    ctx = MagicMock()
    ctx.skip_sim = False
    result = stage.run(StageInput(design=design, context=ctx))
    assert result.status == "SKIPPED"


def test_connectivity_stage_reads_design_rtl_and_top_module():
    from unittest.mock import MagicMock
    from veriflow.core.stages.connectivity import InterfaceStage
    from veriflow.core.backends.base import ConnectivityBackend
    from veriflow.models.interface_profile import semicolab_interface_profile

    mock_backend = MagicMock(spec=ConnectivityBackend)
    mock_backend.run_connectivity.return_value = "PASS"

    stage = InterfaceStage(interface_profile=semicolab_interface_profile(), backend=mock_backend)

    rtl = Path("/nonexistent/top.v")
    design = Design(top_module="my_top", rtl_sources=[rtl])

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_connectivity = False
        ctx.impl_dir = tmp / "impl"
        stage.run(StageInput(design=design, context=ctx))
        call_kwargs = mock_backend.run_connectivity.call_args
        assert call_kwargs.kwargs["rtl_files"] == [rtl]
        assert call_kwargs.kwargs["top_module"] == "my_top"
    finally:
        shutil.rmtree(tmp)


def test_connectivity_stage_passes_interface_profile_to_backend():
    from unittest.mock import MagicMock
    from veriflow.core.stages.connectivity import InterfaceStage
    from veriflow.core.backends.base import ConnectivityBackend
    from veriflow.models.interface_profile import semicolab_interface_profile

    mock_backend = MagicMock(spec=ConnectivityBackend)
    mock_backend.run_connectivity.return_value = "PASS"

    profile = semicolab_interface_profile()
    stage = InterfaceStage(
        interface_profile=profile,
        backend=mock_backend,
    )

    design = Design(top_module="top", rtl_sources=[Path("/nonexistent/top.v")])

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_connectivity = False
        ctx.impl_dir = tmp / "impl"
        stage.run(StageInput(design=design, context=ctx))
        call_kwargs = mock_backend.run_connectivity.call_args
        assert call_kwargs.kwargs["interface_profile"] is profile
    finally:
        shutil.rmtree(tmp)


def test_simulation_stage_passes_tb_top_to_backend():
    from unittest.mock import MagicMock
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SimulationBackend

    mock_backend = MagicMock(spec=SimulationBackend)
    mock_backend.run_simulation.return_value = ("COMPLETED", {})

    stage = SimulationStage(tb_top="my_testbench", backend=mock_backend)

    design = Design(
        top_module="top",
        rtl_sources=[Path("/nonexistent/top.v")],
        tb_sources=[Path("/nonexistent/tb.v")],
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_sim = False
        ctx.sim_dir = tmp / "sim"
        stage.run(StageInput(design=design, context=ctx))
        call_kwargs = mock_backend.run_simulation.call_args
        assert call_kwargs.kwargs["tb_top"] == "my_testbench"
        assert "tb_base_path" not in call_kwargs.kwargs
        assert "tb_tasks_path" not in call_kwargs.kwargs
        assert "semicolab" not in call_kwargs.kwargs
    finally:
        shutil.rmtree(tmp)


def test_stage_context_paths_unchanged_after_migration():
    """log_rel and output dirs are unaffected by the migration."""
    from veriflow.models.run_context import RunContext
    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    ctx = RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        semicolab=False, skip_connectivity=True,
        skip_sim=True, skip_synth=True,
    )
    log_file = run_dir / "out" / "synth" / "logs" / "synth.log"
    assert ctx.log_rel(log_file) == "tiles/X/runs/run-001/out/synth/logs/synth.log"
    assert ctx.synth_dir == run_dir / "out" / "synth"
    assert ctx.impl_dir == run_dir / "out" / "connectivity"


# ── B. PipelineRunner compatibility tests ────────────────────────────────────

def test_pipeline_runner_injects_design_into_stage_input():
    from veriflow.core.pipeline import PipelineRunner, PipelineStage
    from veriflow.models.stage_result import StageResult

    received: list[StageInput] = []

    class RecStage(PipelineStage):
        name = "rec"
        def run(self, input):
            received.append(input)
            return StageResult(name=self.name, status="PASS")

    design = _make_design()
    PipelineRunner([RecStage()], design=design).run(_make_ctx())
    assert len(received) == 1
    assert received[0].design is design


def test_pipeline_runner_passes_prior_results_to_subsequent_stages():
    from veriflow.core.pipeline import PipelineRunner, PipelineStage
    from veriflow.models.stage_result import StageResult

    received_prior: list[dict] = []

    class StageA(PipelineStage):
        name = "a"
        def run(self, input):
            return StageResult(name=self.name, status="PASS")

    class StageB(PipelineStage):
        name = "b"
        def run(self, input):
            received_prior.append(dict(input.prior_results))
            return StageResult(name=self.name, status="PASS")

    PipelineRunner([StageA(), StageB()], design=_make_design()).run(_make_ctx())
    assert "a" in received_prior[0]
    assert received_prior[0]["a"].status == "PASS"


def test_pipeline_runner_runs_all_stages_including_after_fail():
    """PipelineRunner has no early-exit semantics — all stages always execute."""
    from veriflow.core.pipeline import PipelineRunner, PipelineStage
    from veriflow.models.stage_result import StageResult

    executed: list[str] = []

    class FailStage(PipelineStage):
        name = "fail"
        def run(self, input):
            executed.append("fail")
            return StageResult(name=self.name, status="FAIL")

    class AfterFailStage(PipelineStage):
        name = "after"
        def run(self, input):
            executed.append("after")
            return StageResult(name=self.name, status="PASS")

    PipelineRunner([FailStage(), AfterFailStage()], design=_make_design()).run(_make_ctx())
    assert executed == ["fail", "after"]


# ── C. Flow real-stage compatibility tests ────────────────────────────────────

def test_flow_executes_synthesis_stage_over_design():
    from unittest.mock import MagicMock
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.core.backends.base import SynthesisBackend
    from veriflow.framework.flow import Flow
    from veriflow.framework.request import RunRequest

    mock_backend = MagicMock(spec=SynthesisBackend)
    mock_backend.run_synthesis.return_value = (
        "PASS",
        {"cells": "3", "warnings": "0", "errors": "0", "has_latches": False},
    )
    stage = SynthesisStage(backend=mock_backend)

    design = Design(
        top_module="my_top",
        rtl_sources=[Path("/nonexistent/top.v")],
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        result = Flow([stage]).run(design, RunRequest(work_dir=tmp, skip_synth=False))
        assert result.status == "PASS"
        mock_backend.run_synthesis.assert_called_once()
        call_kwargs = mock_backend.run_synthesis.call_args
        assert call_kwargs.kwargs["top_module"] == "my_top"
    finally:
        shutil.rmtree(tmp)


def test_flow_executes_stages_without_constructor_rtl():
    """Migrated stages accept no Design-owned data in their constructor."""
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.stages.connectivity import InterfaceStage
    # These constructors must work without rtl_files / top_module / tb_files
    _ = InterfaceStage(interface_profile=None)
    _ = SimulationStage(tb_top="tb")
    _ = SynthesisStage()


def test_flow_stops_on_fail_with_real_stage():
    from unittest.mock import MagicMock
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SynthesisBackend, SimulationBackend
    from veriflow.framework.flow import Flow
    from veriflow.framework.request import RunRequest

    mock_synth = MagicMock(spec=SynthesisBackend)
    mock_synth.run_synthesis.return_value = (
        "FAIL",
        {"cells": "", "warnings": "1", "errors": "1", "has_latches": False},
    )
    mock_sim = MagicMock(spec=SimulationBackend)

    design = Design(
        top_module="my_top",
        rtl_sources=[Path("/nonexistent/top.v")],
        tb_sources=[Path("/nonexistent/tb.v")],
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        flow = Flow([
            SynthesisStage(backend=mock_synth),
            SimulationStage(tb_top="tb", backend=mock_sim),
        ])
        result = flow.run(design, RunRequest(work_dir=tmp, skip_synth=False, skip_sim=False))
        assert result.status == "FAIL"
        assert "synthesis" in result.stages
        assert "simulation" not in result.stages
        mock_sim.run_simulation.assert_not_called()
    finally:
        shutil.rmtree(tmp)


# ── D. Database/CLI compatibility: artifact paths ────────────────────────────

def test_cmd_run_artifact_paths_are_tiles_relative():
    """RunContext.log_rel() yields tiles/... paths; results.json reflects that."""
    import json
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        tile_id = row["tile_id"]
        results_path = db / "tiles" / tile_id / "runs" / "run-001" / "results.json"
        assert results_path.exists()
        data = json.loads(results_path.read_text(encoding="utf-8"))
        # Manifest artifact path must be tiles-relative
        manifest_paths = data["artifacts"]["manifest"]
        assert len(manifest_paths) == 1
        assert manifest_paths[0].startswith("tiles/")
    finally:
        shutil.rmtree(tmp)


def test_pipeline_runner_design_is_accessible():
    """PipelineRunner exposes .design so cmd_run can pass it to single-stage wrappers."""
    from veriflow.core.pipeline import PipelineRunner
    design = _make_design()
    runner = PipelineRunner(stages=[], design=design)
    assert runner.design is design


# ── InterfaceProfile model tests ─────────────────────────────────────────────

def test_semicolab_interface_profile_has_nine_ports():
    from veriflow.models.interface_profile import semicolab_interface_profile
    p = semicolab_interface_profile()
    assert p.name == "semicolab"
    assert len(p.ports) == 9
    port_map = {port.name: port for port in p.ports}
    assert port_map["clk"].direction == "input"    and port_map["clk"].width == 1
    assert port_map["arst_n"].direction == "input" and port_map["arst_n"].width == 1
    assert port_map["csr_in"].direction == "input" and port_map["csr_in"].width == 16
    assert port_map["data_reg_a"].direction == "input"  and port_map["data_reg_a"].width == 32
    assert port_map["data_reg_b"].direction == "input"  and port_map["data_reg_b"].width == 32
    assert port_map["data_reg_c"].direction == "output" and port_map["data_reg_c"].width == 32
    assert port_map["csr_out"].direction == "output"    and port_map["csr_out"].width == 16
    assert port_map["csr_in_re"].direction == "output"  and port_map["csr_in_re"].width == 1
    assert port_map["csr_out_we"].direction == "output" and port_map["csr_out_we"].width == 1


def test_interface_profile_rejects_empty_name():
    from veriflow.core import VeriFlowError
    from veriflow.models.interface_profile import InterfacePort, InterfaceProfile
    port = InterfacePort("clk", "input", 1)
    raised = False
    try:
        InterfaceProfile(name="", ports=(port,))
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_INTERFACE_NAME_REQUIRED"
    assert raised


def test_interface_profile_rejects_empty_ports():
    from veriflow.core import VeriFlowError
    from veriflow.models.interface_profile import InterfaceProfile
    raised = False
    try:
        InterfaceProfile(name="test", ports=())
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_INTERFACE_PORT_REQUIRED"
    assert raised


def test_interface_port_rejects_width_zero():
    from veriflow.core import VeriFlowError
    from veriflow.models.interface_profile import InterfacePort
    raised = False
    try:
        InterfacePort("clk", "input", 0)
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_INTERFACE_PORT_WIDTH_INVALID"
    assert raised


def test_interface_port_rejects_empty_name():
    from veriflow.core import VeriFlowError
    from veriflow.models.interface_profile import InterfacePort
    raised = False
    try:
        InterfacePort("", "input", 1)
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_INTERFACE_PORT_NAME_REQUIRED"
    assert raised


def test_interface_profile_rejects_duplicate_port_names():
    from veriflow.core import VeriFlowError
    from veriflow.models.interface_profile import InterfacePort, InterfaceProfile
    raised = False
    try:
        InterfaceProfile(
            name="dup",
            ports=(
                InterfacePort("clk", "input", 1),
                InterfacePort("clk", "input", 1),
            ),
        )
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_INTERFACE_PORT_DUPLICATE"
        assert "clk" in str(e)
    assert raised


# ── Generated wrapper tests ────────────────────────────────────────────────────

def test_build_interface_check_wrapper_semicolab_ports():
    from veriflow.core.sim_runner import _build_interface_check_wrapper
    from veriflow.models.interface_profile import semicolab_interface_profile
    wrapper = _build_interface_check_wrapper("my_tile", semicolab_interface_profile())
    for name in ("clk", "arst_n", "csr_in", "data_reg_a", "data_reg_b",
                 "data_reg_c", "csr_out", "csr_in_re", "csr_out_we"):
        assert name in wrapper, f"Port {name!r} missing from wrapper"
        assert f".{name}({name})" in wrapper, f"Named connection for {name!r} missing"
    assert "my_tile DUT" in wrapper


def test_build_interface_check_wrapper_custom_profile():
    from veriflow.core.sim_runner import _build_interface_check_wrapper
    from veriflow.models.interface_profile import InterfacePort, InterfaceProfile
    profile = InterfaceProfile(
        name="custom",
        ports=(
            InterfacePort("a_in", "input", 8),
            InterfacePort("b_out", "output", 4),
        ),
    )
    wrapper = _build_interface_check_wrapper("custom_dut", profile)
    # Named connections present
    assert ".a_in(a_in)" in wrapper
    assert ".b_out(b_out)" in wrapper
    assert "custom_dut DUT" in wrapper
    # Widths derived from profile, not hardcoded
    assert "[7:0]" in wrapper, "8-bit port must declare [7:0]"
    assert "[3:0]" in wrapper, "4-bit port must declare [3:0]"
    # No Semicolab-specific ports appear
    for semicolab_port in ("csr_in", "csr_out", "arst_n", "data_reg_a",
                           "data_reg_b", "data_reg_c", "csr_in_re", "csr_out_we"):
        assert semicolab_port not in wrapper, \
            f"Semicolab port {semicolab_port!r} must not appear in a custom-profile wrapper"


def test_build_interface_check_wrapper_no_stimulus_content():
    from veriflow.core.sim_runner import _build_interface_check_wrapper
    from veriflow.models.interface_profile import semicolab_interface_profile
    wrapper = _build_interface_check_wrapper("my_tile", semicolab_interface_profile())
    for forbidden in ("USER TEST", "$display", "$finish", "initial begin",
                      "`include", "tb_tasks", "tb_tile"):
        assert forbidden not in wrapper, f"Stimulus/harness content {forbidden!r} must not appear"
    # No filesystem path separators — wrapper must contain no file paths at all
    assert "/" not in wrapper and "\\" not in wrapper, \
        "Wrapper must not contain any filesystem path"


def test_build_interface_check_wrapper_width_signals():
    from veriflow.core.sim_runner import _build_interface_check_wrapper
    from veriflow.models.interface_profile import semicolab_interface_profile
    wrapper = _build_interface_check_wrapper("my_tile", semicolab_interface_profile())
    assert "[15:0]" in wrapper   # csr_in / csr_out width
    assert "[31:0]" in wrapper   # data_reg_a/b/c width


def test_run_connectivity_check_compiles_wrapper_not_tb_files():
    """run_connectivity_check passes RTL + generated wrapper to iverilog; no -I, no TB paths."""
    from unittest.mock import patch, MagicMock
    from veriflow.core.sim_runner import run_connectivity_check
    from veriflow.models.interface_profile import semicolab_interface_profile

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    tmp = Path(tempfile.mkdtemp())
    try:
        rtl = tmp / "my_tile.v"
        rtl.write_text("module my_tile; endmodule\n", encoding="utf-8")

        with patch("veriflow.core.sim_runner.subprocess.run", side_effect=fake_run):
            run_connectivity_check(
                rtl_files=[rtl],
                interface_profile=semicolab_interface_profile(),
                top_module="my_tile",
                log_path=tmp / "conn.log",
            )

        assert len(captured_cmds) == 1, "iverilog must be invoked exactly once"
        cmd = captured_cmds[0]

        # RTL source is in the command
        assert rtl.as_posix() in cmd, "RTL file must be compiled"

        # No TB include directory passed — tb_tasks.v is not needed
        assert "-I" not in cmd, "No -I flag expected: TB include dir must not be present"

        # No TB file paths in any argument
        cmd_str = " ".join(cmd)
        assert "tb_tile" not in cmd_str, "tb_tile.v path must not appear in iverilog command"
        assert "tb_tasks" not in cmd_str, "tb_tasks.v path must not appear in iverilog command"

        # Exactly RTL + one generated wrapper: two .v sources total
        v_sources = [a for a in cmd if a.endswith(".v")]
        assert len(v_sources) == 2, f"Expected rtl + wrapper (.v), got: {v_sources}"
        assert rtl.as_posix() in v_sources, "RTL must be one of the two .v sources"
    finally:
        shutil.rmtree(tmp)


# ── Connectivity isolation tests ───────────────────────────────────────────────

def test_connectivity_stage_never_opens_tb_sources():
    """Connectivity must not reference Design.tb_sources — uses InterfaceProfile only."""
    from unittest.mock import MagicMock
    from veriflow.core.stages.connectivity import InterfaceStage
    from veriflow.models.interface_profile import semicolab_interface_profile

    tb_never_opened = Path("/should/never/be/opened/tb_tile.v")
    design_with_tb = Design(
        top_module="top",
        rtl_sources=[Path("/nonexistent/top.v")],
        tb_sources=[tb_never_opened],
    )
    mock_backend = MagicMock()
    mock_backend.run_connectivity.return_value = "PASS"
    stage = InterfaceStage(interface_profile=semicolab_interface_profile(), backend=mock_backend)

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_connectivity = False
        ctx.impl_dir = tmp / "impl"
        stage.run(StageInput(design=design_with_tb, context=ctx))
        call_kwargs = mock_backend.run_connectivity.call_args
        assert "tb_base_path" not in call_kwargs.kwargs
        assert "tb_tasks_path" not in call_kwargs.kwargs
        assert str(tb_never_opened) not in str(call_kwargs)
    finally:
        shutil.rmtree(tmp)


def test_connectivity_stage_missing_profile_raises():
    """Missing InterfaceProfile while connectivity executes raises VF_INTERFACE_PROFILE_REQUIRED."""
    from unittest.mock import MagicMock
    from veriflow.core import VeriFlowError
    from veriflow.core.stages.connectivity import InterfaceStage

    stage = InterfaceStage(interface_profile=None)
    ctx = MagicMock()
    ctx.skip_connectivity = False
    raised = False
    try:
        stage.run(_make_stage_input(ctx))
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_INTERFACE_PROFILE_REQUIRED"
    assert raised, "Expected VF_INTERFACE_PROFILE_REQUIRED"


# ── A. SimulationStage: generic self-contained simulation tests ───────────────

def test_simulation_stage_rejects_empty_tb_top():
    from veriflow.core import VeriFlowError
    from veriflow.core.stages.simulation import SimulationStage
    raised = False
    try:
        SimulationStage(tb_top="")
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_SIM_TB_TOP_REQUIRED"
    assert raised, "Expected VF_SIM_TB_TOP_REQUIRED for empty tb_top"


def test_simulation_stage_rejects_whitespace_only_tb_top():
    from veriflow.core import VeriFlowError
    from veriflow.core.stages.simulation import SimulationStage
    raised = False
    try:
        SimulationStage(tb_top="   ")
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_SIM_TB_TOP_REQUIRED"
    assert raised, "Expected VF_SIM_TB_TOP_REQUIRED for whitespace tb_top"


def test_simulation_stage_passes_explicit_tb_top_to_backend():
    from unittest.mock import MagicMock
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SimulationBackend

    mock_backend = MagicMock(spec=SimulationBackend)
    mock_backend.run_simulation.return_value = ("COMPLETED", {})

    stage = SimulationStage(tb_top="explicit_top", backend=mock_backend)
    design = Design(
        top_module="dut",
        rtl_sources=[Path("/nonexistent/dut.v")],
        tb_sources=[Path("/nonexistent/tb.v")],
    )
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_sim = False
        ctx.sim_dir = tmp / "sim"
        stage.run(StageInput(design=design, context=ctx))
        call_kwargs = mock_backend.run_simulation.call_args
        assert call_kwargs.kwargs["tb_top"] == "explicit_top"
    finally:
        shutil.rmtree(tmp)


def test_simulation_stage_passes_all_rtl_and_tb_sources():
    from unittest.mock import MagicMock
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SimulationBackend

    mock_backend = MagicMock(spec=SimulationBackend)
    mock_backend.run_simulation.return_value = ("COMPLETED", {})

    rtl1 = Path("/nonexistent/rtl1.v")
    rtl2 = Path("/nonexistent/rtl2.v")
    tb1 = Path("/nonexistent/tb1.v")
    tb2 = Path("/nonexistent/tb2.v")

    stage = SimulationStage(tb_top="tb", backend=mock_backend)
    design = Design(top_module="dut", rtl_sources=[rtl1, rtl2], tb_sources=[tb1, tb2])

    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_sim = False
        ctx.sim_dir = tmp / "sim"
        stage.run(StageInput(design=design, context=ctx))
        call_kwargs = mock_backend.run_simulation.call_args
        assert call_kwargs.kwargs["rtl_files"] == [rtl1, rtl2]
        assert call_kwargs.kwargs["tb_files"] == [tb1, tb2]
    finally:
        shutil.rmtree(tmp)


def test_simulation_stage_does_not_consult_ctx_semicolab():
    """SimulationStage must not read ctx.semicolab; it is platform-neutral."""
    from unittest.mock import MagicMock, PropertyMock
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SimulationBackend

    mock_backend = MagicMock(spec=SimulationBackend)
    mock_backend.run_simulation.return_value = ("COMPLETED", {})

    stage = SimulationStage(tb_top="tb", backend=mock_backend)
    design = Design(
        top_module="dut",
        rtl_sources=[Path("/nonexistent/dut.v")],
        tb_sources=[Path("/nonexistent/tb.v")],
    )
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = MagicMock()
        ctx.skip_sim = False
        ctx.sim_dir = tmp / "sim"
        # Remove semicolab attribute to verify stage doesn't access it
        del ctx.semicolab
        stage.run(StageInput(design=design, context=ctx))
        # If we got here without AttributeError, semicolab was not accessed
        call_kwargs = mock_backend.run_simulation.call_args
        assert "semicolab" not in call_kwargs.kwargs
    finally:
        shutil.rmtree(tmp)


# ── B. Simulation runner tests ────────────────────────────────────────────────

def test_run_simulation_command_contains_all_rtl_and_tb_files():
    from unittest.mock import patch, MagicMock
    from veriflow.core.sim_runner import run_simulation

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    tmp = Path(tempfile.mkdtemp())
    try:
        rtl = tmp / "my_tile.v"
        tb = tmp / "tb_tile.v"
        rtl.write_text("module my_tile; endmodule\n", encoding="utf-8")
        tb.write_text("module tb; endmodule\n", encoding="utf-8")

        with patch("veriflow.core.sim_runner.subprocess.run", side_effect=fake_run):
            run_simulation(
                rtl_files=[rtl],
                tb_files=[tb],
                tb_top="tb",
                sim_log_path=tmp / "sim.log",
                wave_path=tmp / "waves" / "waves.vcd",
            )

        assert len(captured) >= 1
        compile_cmd = captured[0]
        assert rtl.as_posix() in compile_cmd, "RTL file must be in compile command"
        assert tb.as_posix() in compile_cmd, "TB file must be in compile command"
    finally:
        shutil.rmtree(tmp)


def test_run_simulation_command_contains_minus_s_tb_top():
    from unittest.mock import patch, MagicMock
    from veriflow.core.sim_runner import run_simulation

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    tmp = Path(tempfile.mkdtemp())
    try:
        rtl = tmp / "my_tile.v"
        tb = tmp / "tb_tile.v"
        rtl.write_text("module my_tile; endmodule\n", encoding="utf-8")
        tb.write_text("module tb; endmodule\n", encoding="utf-8")

        with patch("veriflow.core.sim_runner.subprocess.run", side_effect=fake_run):
            run_simulation(
                rtl_files=[rtl],
                tb_files=[tb],
                tb_top="tb",
                sim_log_path=tmp / "sim.log",
                wave_path=tmp / "waves" / "waves.vcd",
            )

        compile_cmd = captured[0]
        assert "-s" in compile_cmd, "-s flag must be in compile command"
        s_idx = compile_cmd.index("-s")
        assert compile_cmd[s_idx + 1] == "tb", "-s must be followed by tb_top name"
    finally:
        shutil.rmtree(tmp)


def test_run_simulation_command_no_include_flag():
    from unittest.mock import patch, MagicMock
    from veriflow.core.sim_runner import run_simulation

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    tmp = Path(tempfile.mkdtemp())
    try:
        rtl = tmp / "my_tile.v"
        tb = tmp / "tb_tile.v"
        rtl.write_text("module my_tile; endmodule\n", encoding="utf-8")
        tb.write_text("module tb; endmodule\n", encoding="utf-8")

        with patch("veriflow.core.sim_runner.subprocess.run", side_effect=fake_run):
            run_simulation(
                rtl_files=[rtl],
                tb_files=[tb],
                tb_top="tb",
                sim_log_path=tmp / "sim.log",
                wave_path=tmp / "waves" / "waves.vcd",
            )

        compile_cmd = captured[0]
        assert "-I" not in compile_cmd, "No -I flag: no hidden include dirs allowed"
    finally:
        shutil.rmtree(tmp)


def test_run_simulation_command_no_injected_temp_tb():
    """Compile command .v files must be exactly the provided rtl + tb files."""
    from unittest.mock import patch, MagicMock
    from veriflow.core.sim_runner import run_simulation

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    tmp = Path(tempfile.mkdtemp())
    try:
        rtl = tmp / "my_tile.v"
        tb = tmp / "tb_tile.v"
        rtl.write_text("module my_tile; endmodule\n", encoding="utf-8")
        tb.write_text("module tb; endmodule\n", encoding="utf-8")

        with patch("veriflow.core.sim_runner.subprocess.run", side_effect=fake_run):
            run_simulation(
                rtl_files=[rtl],
                tb_files=[tb],
                tb_top="tb",
                sim_log_path=tmp / "sim.log",
                wave_path=tmp / "waves" / "waves.vcd",
            )

        compile_cmd = captured[0]
        v_sources = [a for a in compile_cmd if a.endswith(".v")]
        expected = {rtl.as_posix(), tb.as_posix()}
        assert set(v_sources) == expected, (
            f"Compile .v args must be exactly rtl+tb files. Got extra: {set(v_sources) - expected}"
        )
    finally:
        shutil.rmtree(tmp)


# ── C. Semicolab scaffold tests ───────────────────────────────────────────────

def test_semicolab_scaffold_creates_tb_tile_v():
    """Semicolab create_tile produces src/tb/tb_tile.v."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        assert (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").exists()
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_tb_contains_module_tb():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "module tb" in content, "Generated TB must declare 'module tb'"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_tb_contains_dut_top_module():
    """Creating a Semicolab tile with a known top_module produces TB that names it."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db, top_module="my_adder_tile")
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "my_adder_tile" in content, "Configured DUT top module name must appear in TB"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_tb_contains_semicolab_ports():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        for port in ("clk", "arst_n", "csr_in", "data_reg_a", "data_reg_b",
                     "data_reg_c", "csr_out", "csr_in_re", "csr_out_we"):
            assert port in content, f"Semicolab port {port!r} missing from generated TB"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_tb_contains_dumpfile():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert '$dumpfile("waves.vcd")' in content
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_tb_contains_dumpvars():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "$dumpvars" in content
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_tb_contains_stimulus_section():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "USER STIMULUS" in content, "Generated TB must have a user stimulus section"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_tb_no_unresolved_dut_placeholder():
    """Generated TB must not contain the raw template marker /* DUT_MODULE */."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "/* DUT_MODULE */" not in content, "Raw DUT_MODULE placeholder must not remain"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_scaffold_no_tb_tasks_v():
    """New Semicolab scaffold must not produce tb_tasks.v."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        assert not (db / "config" / "tile_0001" / "src" / "tb" / "tb_tasks.v").exists()
    finally:
        shutil.rmtree(tmp)


# ── D. Generic scaffold tests ─────────────────────────────────────────────────

def test_generic_scaffold_no_semicolab_wiring():
    """Generic project (interface_name: null) must not inject Semicolab ports or helpers."""
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": None}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        _make_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        for semicolab_port in ("csr_in", "csr_out", "data_reg_a", "data_reg_b", "data_reg_c",
                               "csr_in_re", "csr_out_we"):
            assert semicolab_port not in content, (
                f"Semicolab port {semicolab_port!r} must not appear in universal scaffold"
            )
        assert "DUT_MODULE" not in content, "DUT_MODULE placeholder must not appear in universal scaffold"
    finally:
        shutil.rmtree(tmp)


# ── E. Database/flow wiring tests ─────────────────────────────────────────────

def test_tile_config_contains_tb_top_module():
    """Generated tile_config.yaml must contain tb_top_module: 'tb'."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        _make_tile(db)
        import yaml
        cfg = yaml.safe_load((db / "config" / "tile_0001" / "tile_config.yaml").read_text(encoding="utf-8"))
        assert "tb_top_module" in cfg, "tile_config.yaml must contain tb_top_module"
        assert cfg["tb_top_module"] == "tb"
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_forwards_tb_top_module():
    """cmd_run must pass tile_config.tb_top_module into the pipeline as tb_top."""
    from unittest.mock import patch
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")

        # Set tb_top_module to a custom value
        cfg_path = db / "config" / "tile_0001" / "tile_config.yaml"
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        raw.update({
            "top_module": "my_tile",
            "tb_top_module": "my_custom_tb",
            "run_author": "Tester",
            "objective": "Test",
        })
        cfg_path.write_text(yaml.dump(raw), encoding="utf-8")

        captured_tb_top: list[str] = []

        original_build = __import__(
            "veriflow.core.pipeline_builder", fromlist=["build_default_pipeline"]
        ).build_default_pipeline

        def capturing_build(**kwargs):
            captured_tb_top.append(kwargs.get("tb_top", ""))
            return original_build(**kwargs)

        from veriflow.commands.run import cmd_run
        with patch("veriflow.workflows.database.build_default_pipeline", side_effect=capturing_build):
            cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)

        assert len(captured_tb_top) == 1
        assert captured_tb_top[0] == "my_custom_tb", (
            f"Expected tb_top='my_custom_tb', got {captured_tb_top[0]!r}"
        )
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_connectivity_still_uses_semicolab_interface_profile():
    """Connectivity stage still uses semicolab_interface_profile() for Semicolab projects."""
    from unittest.mock import patch
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)  # semicolab=True
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")

        from veriflow.commands.run import cmd_run
        with patch("veriflow.core.backends.icarus.run_connectivity_check", return_value="PASS"):
            result = cmd_run(
                db=db, tile_number="0001",
                skip_check=False, skip_sim=True, skip_synth=True,
            )
        assert result["stages"]["connectivity"]["status"] == "PASS"
    finally:
        shutil.rmtree(tmp)


def test_tile_config_backward_compat_missing_tb_top_module():
    """Old tile_config.yaml without tb_top_module key is still parseable.

    tb_top_module defaults to 'tb' so old config files can be loaded without error.
    This is PARSING compatibility only — old Semicolab workspaces using the former
    injected/mixed testbench layout still require manual testbench migration before
    functional simulation will succeed.
    """
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({"top_module": "my_tile"})
    assert cfg.tb_top_module == "tb"


def test_tile_config_explicit_empty_tb_top_module_passes_through():
    """Explicit empty tb_top_module in config passes through as empty string."""
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({"top_module": "my_tile", "tb_top_module": ""})
    assert cfg.tb_top_module == ""


def test_create_tile_semicolab_requires_top_module():
    """Creating a Semicolab tile without top_module must raise VF_TILE_TOP_MODULE_REQUIRED."""
    from veriflow.core import VeriFlowError
    from veriflow.commands.create_tile import cmd_create_tile
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)  # semicolab=True by default
        raised = False
        try:
            cmd_create_tile(db)  # no top_module → must fail for Semicolab
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_TILE_TOP_MODULE_REQUIRED"
        assert raised, "Expected VF_TILE_TOP_MODULE_REQUIRED when creating Semicolab tile without top_module"
    finally:
        shutil.rmtree(tmp)


def test_create_tile_semicolab_whitespace_top_module_rejected():
    """Whitespace-only top_module must be rejected for Semicolab tiles."""
    from veriflow.core import VeriFlowError
    from veriflow.commands.create_tile import cmd_create_tile
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)  # semicolab=True
        raised = False
        try:
            cmd_create_tile(db, top_module="   ")
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_TILE_TOP_MODULE_REQUIRED"
        assert raised
    finally:
        shutil.rmtree(tmp)


def test_create_tile_non_semicolab_no_top_module_required():
    """Generic project (interface_name: null) does not require top_module."""
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": None}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)  # no top_module — OK for generic project
        assert (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").exists()
    finally:
        shutil.rmtree(tmp)


def test_create_tile_single_source_of_truth():
    """--top-module NAME must propagate to BOTH tile_config.yaml AND tb_tile.v.

    The DUT top module name is the single source of truth:
    tile_config.top_module drives Design.top_module (→ synthesis, connectivity),
    while tb_tile.v must instantiate the same module.
    """
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db, top_module="shift_mux")

        cfg_path = db / "config" / "tile_0001" / "tile_config.yaml"
        tb_path  = db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v"

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        assert raw.get("top_module") == "shift_mux", (
            f"tile_config.yaml must record top_module='shift_mux', got {raw.get('top_module')!r}"
        )
        assert raw.get("tb_top_module") == "tb", (
            f"tile_config.yaml must have tb_top_module='tb', got {raw.get('tb_top_module')!r}"
        )

        tb_content = tb_path.read_text(encoding="utf-8")
        assert "shift_mux DUT (" in tb_content, (
            "tb_tile.v must instantiate shift_mux DUT — same name as tile_config.top_module"
        )
        assert "/* DUT_MODULE */" not in tb_content, (
            "Raw DUT_MODULE placeholder must not remain in the generated TB"
        )
    finally:
        shutil.rmtree(tmp)


def test_generic_scaffold_tb_contains_waveform_dump():
    """Generic scaffold (interface_name: null) must include $dumpfile/$dumpvars for waveform generation."""
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": None}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
        content = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "$dumpfile" in content, "Generic scaffold must include $dumpfile"
        assert "$dumpvars" in content, "Generic scaffold must include $dumpvars"
    finally:
        shutil.rmtree(tmp)


# ── top_module identifier validation ─────────────────────────────────────────

def _make_semicolab_db(tmp: Path) -> Path:
    """Initialize a Semicolab database (interface_name: 'semicolab') inside tmp."""
    db = _make_db(tmp)
    _fill_project_config(db)  # interface_name: "semicolab"
    return db


def test_create_tile_rejects_hyphen_in_top_module():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.core import VeriFlowError
        from veriflow.commands.create_tile import cmd_create_tile
        raised = False
        try:
            cmd_create_tile(db, top_module="shift-mux")
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_TILE_TOP_MODULE_INVALID", f"Expected VF_TILE_TOP_MODULE_INVALID, got {e.code}"
        assert raised, "Expected VF_TILE_TOP_MODULE_INVALID for 'shift-mux'"
    finally:
        shutil.rmtree(tmp)


def test_create_tile_rejects_leading_digit_in_top_module():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.core import VeriFlowError
        from veriflow.commands.create_tile import cmd_create_tile
        raised = False
        try:
            cmd_create_tile(db, top_module="123tile")
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_TILE_TOP_MODULE_INVALID"
        assert raised, "Expected VF_TILE_TOP_MODULE_INVALID for '123tile'"
    finally:
        shutil.rmtree(tmp)


def test_create_tile_rejects_space_in_top_module():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.core import VeriFlowError
        from veriflow.commands.create_tile import cmd_create_tile
        raised = False
        try:
            cmd_create_tile(db, top_module="bad name")
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_TILE_TOP_MODULE_INVALID"
        assert raised, "Expected VF_TILE_TOP_MODULE_INVALID for 'bad name'"
    finally:
        shutil.rmtree(tmp)


def test_create_tile_rejects_injection_attempt_in_top_module():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.core import VeriFlowError
        from veriflow.commands.create_tile import cmd_create_tile
        raised = False
        try:
            cmd_create_tile(db, top_module='shift_mux"; invalid')
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_TILE_TOP_MODULE_INVALID"
        assert raised, "Expected VF_TILE_TOP_MODULE_INVALID for injection attempt"
    finally:
        shutil.rmtree(tmp)


def test_create_tile_invalid_top_module_does_not_generate_files():
    """Validation must fire before any file is written."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.core import VeriFlowError
        from veriflow.commands.create_tile import cmd_create_tile
        try:
            cmd_create_tile(db, top_module="shift-mux")
        except VeriFlowError:
            pass
        assert not (db / "config" / "tile_0001").exists(), (
            "Config directory must not be created when top_module is invalid"
        )
    finally:
        shutil.rmtree(tmp)


def test_create_tile_accepts_shift_mux():
    """shift_mux is a valid Verilog identifier and must succeed."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db, top_module="shift_mux")
        import yaml
        raw = yaml.safe_load(
            (db / "config" / "tile_0001" / "tile_config.yaml").read_text(encoding="utf-8")
        )
        assert raw.get("top_module") == "shift_mux"
        tb = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "shift_mux DUT (" in tb
    finally:
        shutil.rmtree(tmp)


def test_create_tile_accepts_leading_underscore():
    """_internal_tile is a valid Verilog identifier (starts with underscore)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db, top_module="_internal_tile")
        tb = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "_internal_tile DUT (" in tb
    finally:
        shutil.rmtree(tmp)


def test_create_tile_accepts_trailing_digit():
    """tile2 is a valid Verilog identifier (digit after initial letter)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_semicolab_db(tmp)
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db, top_module="tile2")
        tb = (db / "config" / "tile_0001" / "src" / "tb" / "tb_tile.v").read_text(encoding="utf-8")
        assert "tile2 DUT (" in tb
    finally:
        shutil.rmtree(tmp)


# ── Interface name selection tests ───────────────────────────────────────────

# B. ProjectConfig parsing

def test_project_config_parses_interface_name_semicolab():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({"id_prefix": "X", "project_name": "P", "repo": "", "description": "", "interface_name": "semicolab"})
    assert cfg.interface_name == "semicolab"


def test_project_config_parses_interface_name_null():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({"id_prefix": "X", "project_name": "P", "repo": "", "description": "", "interface_name": None})
    assert cfg.interface_name is None


def test_project_config_missing_interface_name_raises():
    from veriflow.core import VeriFlowError
    from veriflow.models.project_config import ProjectConfig
    raised = False
    try:
        ProjectConfig.from_dict({"id_prefix": "X", "project_name": "P", "repo": "", "description": ""})
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_PROJECT_INTERFACE_REQUIRED"
        assert "interface_name" in str(e)
    assert raised, "Absent interface_name must raise VF_PROJECT_INTERFACE_REQUIRED"


def test_project_config_interface_name_whitespace_becomes_none():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({"id_prefix": "X", "project_name": "P", "repo": "", "description": "", "interface_name": "   "})
    assert cfg.interface_name is None


def test_project_config_legacy_semicolab_true_raises():
    from veriflow.core import VeriFlowError
    from veriflow.models.project_config import ProjectConfig
    raised = False
    try:
        ProjectConfig.from_dict({"id_prefix": "X", "project_name": "P", "repo": "", "description": "", "semicolab": True})
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_PROJECT_INTERFACE_CONFIG_LEGACY"
        assert "interface_name" in str(e)
    assert raised, "Legacy semicolab: true must raise VF_PROJECT_INTERFACE_CONFIG_LEGACY"


def test_project_config_legacy_semicolab_false_raises():
    from veriflow.core import VeriFlowError
    from veriflow.models.project_config import ProjectConfig
    raised = False
    try:
        ProjectConfig.from_dict({"id_prefix": "X", "project_name": "P", "repo": "", "description": "", "semicolab": False})
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_PROJECT_INTERFACE_CONFIG_LEGACY"
    assert raised, "Legacy semicolab: false must raise VF_PROJECT_INTERFACE_CONFIG_LEGACY"


def test_project_config_legacy_error_includes_migration_guidance():
    from veriflow.core import VeriFlowError
    from veriflow.models.project_config import ProjectConfig
    try:
        ProjectConfig.from_dict({"semicolab": True})
    except VeriFlowError as e:
        assert "semicolab: true" in str(e)
        assert "semicolab: false" in str(e)
        return
    assert False, "Expected VeriFlowError"


def test_project_config_both_keys_rejected():
    """Having both semicolab and interface_name present is rejected."""
    from veriflow.core import VeriFlowError
    from veriflow.models.project_config import ProjectConfig
    raised = False
    try:
        ProjectConfig.from_dict({
            "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
            "semicolab": True, "interface_name": "semicolab",
        })
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_PROJECT_INTERFACE_CONFIG_LEGACY"
    assert raised, "Both semicolab and interface_name must be rejected"


def test_project_config_missing_interface_raises_required_not_legacy():
    """Empty config (no semicolab, no interface_name) raises VF_PROJECT_INTERFACE_REQUIRED."""
    from veriflow.core import VeriFlowError
    from veriflow.models.project_config import ProjectConfig
    raised = False
    try:
        ProjectConfig.from_dict({})
    except VeriFlowError as e:
        raised = True
        assert e.code == "VF_PROJECT_INTERFACE_REQUIRED", f"Expected VF_PROJECT_INTERFACE_REQUIRED, got {e.code!r}"
    assert raised, "Empty config must raise VF_PROJECT_INTERFACE_REQUIRED, not VF_PROJECT_INTERFACE_CONFIG_LEGACY"


# D. Database execution

def test_cmd_run_generic_project_skips_connectivity():
    """interface_name: null automatically skips connectivity in normal runs."""
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": None}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        result = cmd_run(db=db, tile_number="0001", skip_sim=True, skip_synth=True)
        assert result["stages"]["connectivity"]["status"] == "SKIPPED"
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_only_check_no_interface_raises():
    """only_check=True with no interface profile raises VF_INTERFACE_CHECK_NO_PROFILE."""
    import yaml
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": None}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        raised = False
        try:
            cmd_run(db=db, tile_number="0001", only_check=True)
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_INTERFACE_CHECK_NO_PROFILE"
        assert raised, "Expected VF_INTERFACE_CHECK_NO_PROFILE"
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_unknown_interface_raises_before_stages():
    """Unknown interface_name raises VF_INTERFACE_UNKNOWN before any stage executes."""
    import yaml
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        # Set up a valid semicolab config and create the tile
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        # Overwrite project_config with an unknown interface before running
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": "future_interface"}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        from veriflow.commands.run import cmd_run
        raised = False
        try:
            cmd_run(db=db, tile_number="0001", skip_sim=True, skip_synth=True)
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_INTERFACE_UNKNOWN"
        assert raised, "Expected VF_INTERFACE_UNKNOWN for unknown interface_name"
    finally:
        shutil.rmtree(tmp)


def test_cmd_create_tile_unknown_interface_raises_before_files():
    """Unknown interface_name in create_tile raises VF_INTERFACE_UNKNOWN before writing files."""
    import yaml
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": "future_interface"}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        from veriflow.commands.create_tile import cmd_create_tile
        raised = False
        try:
            cmd_create_tile(db, top_module="my_tile")
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_INTERFACE_UNKNOWN"
        assert raised, "Expected VF_INTERFACE_UNKNOWN"
        assert not (db / "config" / "tile_0001").exists(), "No files must be written before validation"
    finally:
        shutil.rmtree(tmp)


# F. Artifact compatibility

def test_results_json_semicolab_field_is_boolean():
    """results.json['semicolab'] must remain a boolean (not a string or missing)."""
    import json
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        result = cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        assert isinstance(result["semicolab"], bool), "semicolab in return dict must be bool"
        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        results_path = db / "tiles" / row["tile_id"] / "runs" / "run-001" / "results.json"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert isinstance(data["semicolab"], bool), "results.json semicolab must be bool"
        assert data["semicolab"] is True
    finally:
        shutil.rmtree(tmp)


def test_results_json_schema_version_unchanged_after_refactor():
    """results.json schema_version must remain '1.1' after the interface_name refactor."""
    import json
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        from veriflow.core.csv_store import get_tile_row
        row = get_tile_row(db / "tile_index.csv", "0001")
        results_path = db / "tiles" / row["tile_id"] / "runs" / "run-001" / "results.json"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.1"
    finally:
        shutil.rmtree(tmp)


def test_records_csv_semicolab_field_is_true_false_string():
    """CSV Semicolab field must be the string 'true' or 'false', not a boolean."""
    import csv, yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        rows = list(csv.DictReader((db / "records.csv").read_text(encoding="utf-8").splitlines()))
        assert len(rows) == 1
        assert rows[0]["Semicolab"] in ("true", "false"), "Semicolab CSV field must be 'true' or 'false'"
        assert rows[0]["Semicolab"] == "true"
    finally:
        shutil.rmtree(tmp)


def test_records_csv_generic_project_semicolab_is_false_string():
    """Generic project (interface_name: null) writes Semicolab='false' to CSV."""
    import csv, yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "interface_name": None}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        from veriflow.commands.run import cmd_run
        cmd_run(db=db, tile_number="0001", skip_check=True, skip_sim=True, skip_synth=True)
        rows = list(csv.DictReader((db / "records.csv").read_text(encoding="utf-8").splitlines()))
        assert rows[0]["Semicolab"] == "false"
    finally:
        shutil.rmtree(tmp)


def test_cmd_run_missing_interface_raises_required():
    """cmd_run must raise VF_PROJECT_INTERFACE_REQUIRED when interface_name is absent."""
    import yaml
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db)
        _make_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")
        # Write a config with no interface_name key at all
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": ""}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        from veriflow.commands.run import cmd_run
        raised = False
        try:
            cmd_run(db=db, tile_number="0001", skip_sim=True, skip_synth=True)
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_PROJECT_INTERFACE_REQUIRED"
        assert raised, "Missing interface_name must raise VF_PROJECT_INTERFACE_REQUIRED in cmd_run"
    finally:
        shutil.rmtree(tmp)


def test_cmd_create_tile_missing_interface_raises_required():
    """cmd_create_tile must raise VF_PROJECT_INTERFACE_REQUIRED when interface_name is absent."""
    import yaml
    from veriflow.core import VeriFlowError
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": ""}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        from veriflow.commands.create_tile import cmd_create_tile
        raised = False
        try:
            cmd_create_tile(db, top_module="my_tile")
        except VeriFlowError as e:
            raised = True
            assert e.code == "VF_PROJECT_INTERFACE_REQUIRED"
        assert raised, "Missing interface_name must raise VF_PROJECT_INTERFACE_REQUIRED in cmd_create_tile"
        assert not (db / "config" / "tile_0001").exists(), "No files must be written before the error"
    finally:
        shutil.rmtree(tmp)


ALL_TESTS = [
    ("tile_id_generation",              test_tile_id_generation),
    ("tile_id_parsing",                 test_tile_id_parsing),
    ("run_id_first",                    test_run_id_first),
    ("run_id_increment",                test_run_id_increment),
    ("init_creates_structure",          test_init_creates_structure),
    ("init_force",                      test_init_force),
    ("init_no_force_raises",            test_init_no_force_raises),
    ("create_tile_structure",           test_create_tile_structure),
    ("create_tile_tiles_dir",           test_create_tile_tiles_dir),
    ("csv_empty_file_rule",             test_csv_empty_file_rule),
    ("csv_header_validation",           test_csv_header_validation),
    ("flat_copy_basic",                 test_flat_copy_basic),
    ("flat_copy_collision",             test_flat_copy_collision),
    ("bump_version",                    test_bump_version),
    ("bump_revision",                   test_bump_revision),
    ("validation_missing_project_config", test_validation_missing_project_config),
    ("validation_empty_id_prefix",      test_validation_empty_id_prefix),
    ("validation_missing_top_module",   test_validation_missing_top_module),
    ("run_creates_structure",           test_run_creates_structure),
    ("run_copies_rtl",                  test_run_copies_rtl),
    ("run_multiple_runs",               test_run_multiple_runs),
    ("manifest_custom_serializer",      test_manifest_custom_serializer),
    ("semicolab_true_creates_tb_tile_v",  test_semicolab_true_creates_tb_tile_v),
    ("semicolab_false_creates_empty_tb", test_semicolab_false_creates_empty_tb),
    ("semicolab_column_in_tile_index",   test_semicolab_column_in_tile_index),
    ("semicolab_column_in_records",      test_semicolab_column_in_records),
    ("launch_waves_docker_uses_surfer_wasm", test_launch_waves_docker_uses_surfer_wasm),
    ("launch_waves_local_uses_surfer_native", test_launch_waves_local_uses_surfer_native),
    ("launch_waves_local_without_surfer_prints_hint", test_launch_waves_local_without_surfer_prints_hint),
    ("veriflow_error_str",                    test_veriflow_error_str),
    ("veriflow_error_default_code",           test_veriflow_error_default_code),
    ("veriflow_error_custom_code",            test_veriflow_error_custom_code),
    ("veriflow_error_to_dict_shape",          test_veriflow_error_to_dict_shape),
    ("veriflow_error_exit_code_default",      test_veriflow_error_exit_code_default),
    ("veriflow_error_details_none_by_default",test_veriflow_error_details_none_by_default),
    ("veriflow_error_db_missing_code",        test_veriflow_error_db_missing_code),
    ("veriflow_error_tool_not_found_code",    test_veriflow_error_tool_not_found_code),
    ("veriflow_error_rtl_missing_code",       test_veriflow_error_rtl_missing_code),
    ("veriflow_error_top_module_missing_code",      test_veriflow_error_top_module_missing_code),
    ("veriflow_error_top_module_file_missing_code", test_veriflow_error_top_module_file_missing_code),
    ("cli_normal_no_json_flag",          test_cli_normal_no_json_flag),
    ("cli_json_run_success",             test_cli_json_run_success),
    ("cli_json_veriflow_error",          test_cli_json_veriflow_error),
    ("cli_json_unhandled_exception",     test_cli_json_unhandled_exception),
    ("cli_non_interactive_no_command",              test_cli_non_interactive_no_command),
    ("cli_non_interactive_no_command_json",         test_cli_non_interactive_no_command_json),
    ("cli_non_interactive_run_succeeds",            test_cli_non_interactive_run_succeeds),
    ("cli_non_interactive_waves_command_rejected",  test_cli_non_interactive_waves_command_rejected),
    ("cli_non_interactive_run_waves_rejected",      test_cli_non_interactive_run_waves_rejected),
    ("run_context_property_paths",                  test_run_context_property_paths),
    ("run_context_uses_pathlib",                    test_run_context_uses_pathlib),
    ("run_context_no_file_creation",                test_run_context_no_file_creation),
    ("stage_result_minimal_to_dict",                test_stage_result_minimal_to_dict),
    ("stage_result_with_logs_artifacts_metrics",    test_stage_result_with_logs_artifacts_metrics),
    ("stage_result_no_filesystem_access",           test_stage_result_no_filesystem_access),
    ("stage_result_skipped_omits_empty_fields",     test_stage_result_skipped_omits_empty_fields),
    ("stage_result_error_field_included",           test_stage_result_error_field_included),
    ("build_default_pipeline_returns_runner",        test_build_default_pipeline_returns_runner),
    ("build_default_pipeline_stage_order",          test_build_default_pipeline_stage_order),
    ("pipeline_stage_not_implemented",              test_pipeline_stage_not_implemented),
    ("synthesis_stage_is_pipeline_stage",           test_synthesis_stage_is_pipeline_stage),
    ("synthesis_stage_skipped_returns_stage_result",test_synthesis_stage_skipped_returns_stage_result),
    ("pipeline_runner_executes_in_order",           test_pipeline_runner_executes_in_order),
    ("pipeline_runner_returns_stage_result_by_name",test_pipeline_runner_returns_stage_result_by_name),
    ("pipeline_runner_propagates_veriflow_error",   test_pipeline_runner_propagates_veriflow_error),
    ("simulation_stage_is_pipeline_stage",          test_simulation_stage_is_pipeline_stage),
    ("simulation_stage_skipped_returns_stage_result", test_simulation_stage_skipped_returns_stage_result),
    ("simulation_stage_skipped_no_tb",              test_simulation_stage_skipped_no_tb),
    ("results_json_schema_version",                 test_results_json_schema_version),
    ("connectivity_stage_is_pipeline_stage",                   test_connectivity_stage_is_pipeline_stage),
    ("connectivity_stage_skipped_returns_stage_result",        test_connectivity_stage_skipped_returns_stage_result),
    ("connectivity_fail_still_finalizes_run",                  test_connectivity_fail_still_finalizes_run),
    ("api_run_tile_returns_dict",                         test_api_run_tile_returns_dict),
    ("api_run_tile_propagates_veriflow_error",            test_api_run_tile_propagates_veriflow_error),
    ("api_run_tile_rejects_waves_non_interactive",        test_api_run_tile_rejects_waves_non_interactive),
    ("default_execution_profile_values",                  test_default_execution_profile_values),
    ("execution_profile_is_dataclass",                    test_execution_profile_is_dataclass),
    ("build_default_pipeline_accepts_profile",            test_build_default_pipeline_accepts_profile),
    ("build_default_pipeline_uses_profile_tool_labels",   test_build_default_pipeline_uses_profile_tool_labels),
    ("results_json_tool_strings_unchanged",               test_results_json_tool_strings_unchanged),
    # backend interface foundation
    ("backend_base_classes_exist",                        test_backend_base_classes_exist),
    ("icarus_connectivity_backend_exists",                test_icarus_connectivity_backend_exists),
    ("icarus_simulation_backend_exists",                  test_icarus_simulation_backend_exists),
    ("yosys_synthesis_backend_exists",                    test_yosys_synthesis_backend_exists),
    ("backends_package_exports",                          test_backends_package_exports),
    ("icarus_connectivity_backend_delegates_to_runner",        test_icarus_connectivity_backend_delegates_to_runner),
    ("icarus_simulation_backend_delegates_to_runner",     test_icarus_simulation_backend_delegates_to_runner),
    ("yosys_synthesis_backend_delegates_to_runner",       test_yosys_synthesis_backend_delegates_to_runner),
    ("connectivity_stage_uses_backend",                        test_connectivity_stage_uses_backend),
    ("simulation_stage_uses_backend",                     test_simulation_stage_uses_backend),
    ("synthesis_stage_uses_backend",                      test_synthesis_stage_uses_backend),
    # backend registry
    ("registry_connectivity_icarus_returns_correct_class", test_registry_connectivity_icarus_returns_correct_class),
    ("registry_simulation_icarus_returns_correct_class",   test_registry_simulation_icarus_returns_correct_class),
    ("registry_synthesis_yosys_returns_correct_class",     test_registry_synthesis_yosys_returns_correct_class),
    ("registry_connectivity_unknown_raises",               test_registry_connectivity_unknown_raises),
    ("registry_simulation_unknown_raises",                 test_registry_simulation_unknown_raises),
    ("registry_synthesis_unknown_raises",                  test_registry_synthesis_unknown_raises),
    ("execution_profile_has_backend_ids",                  test_execution_profile_has_backend_ids),
    ("build_default_pipeline_uses_registry_backends",      test_build_default_pipeline_uses_registry_backends),
    # technology profile foundation
    ("technology_profile_default_values",                  test_technology_profile_default_values),
    ("technology_profile_registry_supported_names",        test_technology_profile_registry_supported_names),
    ("technology_profile_unknown_raises",                  test_technology_profile_unknown_raises),
    ("execution_profile_technology_name_default",          test_execution_profile_technology_name_default),
    ("execution_profile_backward_compatible_with_technology", test_execution_profile_backward_compatible_with_technology),
    # profile loader foundation
    ("load_profile_minimal",                                test_load_profile_minimal),
    ("load_profile_full",                                   test_load_profile_full),
    ("load_profile_unknown_key_raises",                     test_load_profile_unknown_key_raises),
    ("load_profile_invalid_backend_raises",                 test_load_profile_invalid_backend_raises),
    ("load_profile_invalid_technology_raises",              test_load_profile_invalid_technology_raises),
    # stage migration
    ("synthesis_stage_reads_design_rtl_and_top_module",     test_synthesis_stage_reads_design_rtl_and_top_module),
    ("simulation_stage_reads_rtl_and_tb_sources_from_design", test_simulation_stage_reads_rtl_and_tb_sources_from_design),
    ("simulation_stage_no_tb_skips_from_empty_tb_sources",  test_simulation_stage_no_tb_skips_from_empty_tb_sources),
    ("connectivity_stage_reads_design_rtl_and_top_module",  test_connectivity_stage_reads_design_rtl_and_top_module),
    ("connectivity_stage_passes_interface_profile_to_backend", test_connectivity_stage_passes_interface_profile_to_backend),
    ("simulation_stage_passes_tb_top_to_backend",            test_simulation_stage_passes_tb_top_to_backend),
    ("stage_context_paths_unchanged_after_migration",       test_stage_context_paths_unchanged_after_migration),
    # PipelineRunner compatibility
    ("pipeline_runner_injects_design_into_stage_input",     test_pipeline_runner_injects_design_into_stage_input),
    ("pipeline_runner_passes_prior_results_to_subsequent_stages", test_pipeline_runner_passes_prior_results_to_subsequent_stages),
    ("pipeline_runner_runs_all_stages_including_after_fail",test_pipeline_runner_runs_all_stages_including_after_fail),
    # Flow real-stage compatibility
    ("flow_executes_synthesis_stage_over_design",           test_flow_executes_synthesis_stage_over_design),
    ("flow_executes_stages_without_constructor_rtl",        test_flow_executes_stages_without_constructor_rtl),
    ("flow_stops_on_fail_with_real_stage",                  test_flow_stops_on_fail_with_real_stage),
    # Database/CLI compatibility
    ("cmd_run_artifact_paths_are_tiles_relative",           test_cmd_run_artifact_paths_are_tiles_relative),
    ("pipeline_runner_design_is_accessible",                test_pipeline_runner_design_is_accessible),
    # InterfaceProfile model
    ("semicolab_interface_profile_has_nine_ports",          test_semicolab_interface_profile_has_nine_ports),
    ("interface_profile_rejects_empty_name",                test_interface_profile_rejects_empty_name),
    ("interface_profile_rejects_empty_ports",               test_interface_profile_rejects_empty_ports),
    ("interface_port_rejects_width_zero",                   test_interface_port_rejects_width_zero),
    ("interface_port_rejects_empty_name",                   test_interface_port_rejects_empty_name),
    ("interface_profile_rejects_duplicate_port_names",      test_interface_profile_rejects_duplicate_port_names),
    # Generated interface wrapper
    ("build_interface_check_wrapper_semicolab_ports",       test_build_interface_check_wrapper_semicolab_ports),
    ("build_interface_check_wrapper_custom_profile",        test_build_interface_check_wrapper_custom_profile),
    ("build_interface_check_wrapper_no_stimulus_content",   test_build_interface_check_wrapper_no_stimulus_content),
    ("build_interface_check_wrapper_width_signals",         test_build_interface_check_wrapper_width_signals),
    ("run_connectivity_check_compiles_wrapper_not_tb_files",test_run_connectivity_check_compiles_wrapper_not_tb_files),
    # Connectivity isolation
    ("connectivity_stage_never_opens_tb_sources",           test_connectivity_stage_never_opens_tb_sources),
    ("connectivity_stage_missing_profile_raises",           test_connectivity_stage_missing_profile_raises),
    # A. SimulationStage: generic self-contained simulation
    ("simulation_stage_rejects_empty_tb_top",               test_simulation_stage_rejects_empty_tb_top),
    ("simulation_stage_rejects_whitespace_only_tb_top",     test_simulation_stage_rejects_whitespace_only_tb_top),
    ("simulation_stage_passes_explicit_tb_top_to_backend",  test_simulation_stage_passes_explicit_tb_top_to_backend),
    ("simulation_stage_passes_all_rtl_and_tb_sources",      test_simulation_stage_passes_all_rtl_and_tb_sources),
    ("simulation_stage_does_not_consult_ctx_semicolab",     test_simulation_stage_does_not_consult_ctx_semicolab),
    # B. Simulation runner
    ("run_simulation_command_contains_all_rtl_and_tb_files",test_run_simulation_command_contains_all_rtl_and_tb_files),
    ("run_simulation_command_contains_minus_s_tb_top",      test_run_simulation_command_contains_minus_s_tb_top),
    ("run_simulation_command_no_include_flag",               test_run_simulation_command_no_include_flag),
    ("run_simulation_command_no_injected_temp_tb",           test_run_simulation_command_no_injected_temp_tb),
    # C. Semicolab scaffold
    ("semicolab_scaffold_creates_tb_tile_v",                 test_semicolab_scaffold_creates_tb_tile_v),
    ("semicolab_scaffold_tb_contains_module_tb",             test_semicolab_scaffold_tb_contains_module_tb),
    ("semicolab_scaffold_tb_contains_dut_top_module",        test_semicolab_scaffold_tb_contains_dut_top_module),
    ("semicolab_scaffold_tb_contains_semicolab_ports",       test_semicolab_scaffold_tb_contains_semicolab_ports),
    ("semicolab_scaffold_tb_contains_dumpfile",              test_semicolab_scaffold_tb_contains_dumpfile),
    ("semicolab_scaffold_tb_contains_dumpvars",              test_semicolab_scaffold_tb_contains_dumpvars),
    ("semicolab_scaffold_tb_contains_stimulus_section",      test_semicolab_scaffold_tb_contains_stimulus_section),
    ("semicolab_scaffold_tb_no_unresolved_dut_placeholder",  test_semicolab_scaffold_tb_no_unresolved_dut_placeholder),
    ("semicolab_scaffold_no_tb_tasks_v",                     test_semicolab_scaffold_no_tb_tasks_v),
    # D. Generic scaffold
    ("generic_scaffold_no_semicolab_wiring",                 test_generic_scaffold_no_semicolab_wiring),
    # E. Database/flow wiring
    ("tile_config_contains_tb_top_module",                   test_tile_config_contains_tb_top_module),
    ("cmd_run_forwards_tb_top_module",                       test_cmd_run_forwards_tb_top_module),
    ("cmd_run_connectivity_still_uses_semicolab_interface_profile", test_cmd_run_connectivity_still_uses_semicolab_interface_profile),
    ("tile_config_backward_compat_missing_tb_top_module",    test_tile_config_backward_compat_missing_tb_top_module),
    ("tile_config_explicit_empty_tb_top_module_passes_through", test_tile_config_explicit_empty_tb_top_module_passes_through),
    # create_tile validation
    ("create_tile_semicolab_requires_top_module",            test_create_tile_semicolab_requires_top_module),
    ("create_tile_semicolab_whitespace_top_module_rejected", test_create_tile_semicolab_whitespace_top_module_rejected),
    ("create_tile_non_semicolab_no_top_module_required",     test_create_tile_non_semicolab_no_top_module_required),
    # generic scaffold waveform
    ("generic_scaffold_tb_contains_waveform_dump",           test_generic_scaffold_tb_contains_waveform_dump),
    # single source of truth
    ("create_tile_single_source_of_truth",                   test_create_tile_single_source_of_truth),
    # top_module identifier validation
    ("create_tile_rejects_hyphen_in_top_module",             test_create_tile_rejects_hyphen_in_top_module),
    ("create_tile_rejects_leading_digit_in_top_module",      test_create_tile_rejects_leading_digit_in_top_module),
    ("create_tile_rejects_space_in_top_module",              test_create_tile_rejects_space_in_top_module),
    ("create_tile_rejects_injection_attempt_in_top_module",  test_create_tile_rejects_injection_attempt_in_top_module),
    ("create_tile_invalid_top_module_does_not_generate_files", test_create_tile_invalid_top_module_does_not_generate_files),
    ("create_tile_accepts_shift_mux",                        test_create_tile_accepts_shift_mux),
    ("create_tile_accepts_leading_underscore",               test_create_tile_accepts_leading_underscore),
    ("create_tile_accepts_trailing_digit",                   test_create_tile_accepts_trailing_digit),
    # interface_name selection (this PR)
    ("project_config_parses_interface_name_semicolab",       test_project_config_parses_interface_name_semicolab),
    ("project_config_parses_interface_name_null",            test_project_config_parses_interface_name_null),
    ("project_config_missing_interface_name_raises",         test_project_config_missing_interface_name_raises),
    ("project_config_interface_name_whitespace_becomes_none",test_project_config_interface_name_whitespace_becomes_none),
    ("project_config_legacy_semicolab_true_raises",          test_project_config_legacy_semicolab_true_raises),
    ("project_config_legacy_semicolab_false_raises",         test_project_config_legacy_semicolab_false_raises),
    ("project_config_legacy_error_includes_migration_guidance", test_project_config_legacy_error_includes_migration_guidance),
    ("project_config_both_keys_rejected",                    test_project_config_both_keys_rejected),
    ("project_config_missing_interface_raises_required_not_legacy", test_project_config_missing_interface_raises_required_not_legacy),
    ("cmd_run_generic_project_skips_connectivity",           test_cmd_run_generic_project_skips_connectivity),
    ("cmd_run_only_check_no_interface_raises",               test_cmd_run_only_check_no_interface_raises),
    ("cmd_run_unknown_interface_raises_before_stages",       test_cmd_run_unknown_interface_raises_before_stages),
    ("cmd_create_tile_unknown_interface_raises_before_files",test_cmd_create_tile_unknown_interface_raises_before_files),
    ("cmd_run_missing_interface_raises_required",            test_cmd_run_missing_interface_raises_required),
    ("cmd_create_tile_missing_interface_raises_required",    test_cmd_create_tile_missing_interface_raises_required),
    ("results_json_semicolab_field_is_boolean",              test_results_json_semicolab_field_is_boolean),
    ("results_json_schema_version_unchanged_after_refactor", test_results_json_schema_version_unchanged_after_refactor),
    ("records_csv_semicolab_field_is_true_false_string",     test_records_csv_semicolab_field_is_true_false_string),
    ("records_csv_generic_project_semicolab_is_false_string",test_records_csv_generic_project_semicolab_is_false_string),
]
