"""
VeriFlow V1 — Integration tests.
Uses tempfile.mkdtemp() for isolated environments. Cleans up after each test.
"""

import shutil
import tempfile
from datetime import date
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db(tmp: Path) -> Path:
    """Initialize a fresh database inside tmp."""
    db = tmp / "database"
    from veriflow.commands.init_db import cmd_init
    cmd_init(db)
    return db


def _fill_project_config(db: Path, id_prefix: str = "TST-01") -> None:
    import yaml
    cfg = {
        "id_prefix": id_prefix,
        "project_name": "Test Project",
        "repo": "https://github.com/test/test",
        "description": "Test project for VeriFlow unit tests.\n",
    }
    (db / "project_config.yaml").write_text(
        "\n".join(f"{k}: {v!r}" if isinstance(v, str) and "\n" not in v
                  else (f"{k}: |\n  {v.strip()}" if "\n" in v else f"{k}: {v!r}")
                  for k, v in cfg.items()),
        encoding="utf-8",
    )
    # Use simple yaml.dump instead
    import yaml
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)

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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)

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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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


def test_semicolab_true_creates_tb_files():
    """semicolab: true should copy tb_tile.v and tb_tasks.v to src/tb/"""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        _fill_project_config(db, id_prefix="TST-01")
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
        tb_dir = db / "config" / "tile_0001" / "src" / "tb"
        assert (tb_dir / "tb_tile.v").exists(), "tb_tile.v not found"
        assert (tb_dir / "tb_tasks.v").exists(), "tb_tasks.v not found"
    finally:
        shutil.rmtree(tmp)


def test_semicolab_false_creates_empty_tb():
    """semicolab: false should only copy empty tb_tile.v, no tb_tasks.v"""
    import yaml
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _make_db(tmp)
        cfg = {"id_prefix": "TST-01", "project_name": "Test", "repo": "", "description": "", "semicolab": False}
        (db / "project_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        tile_config_path=db / "config" / "tile_0001" / "tile_config.yaml",
        project_config_path=db / "project_config.yaml",
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
        tile_config_path=db / "cfg.yaml",
        project_config_path=db / "proj.yaml",
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
            tile_config_path=tmp / "config" / "tile_config.yaml",
            project_config_path=tmp / "project_config.yaml",
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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


# ── ConnectivityStage unit tests ─────────────────────────────────────────────

def _make_ctx_conn(skip_connectivity: bool = True) -> "RunContext":
    from veriflow.models.run_context import RunContext
    db = Path("/fake/db")
    tile_dir = db / "tiles" / "X"
    run_dir = tile_dir / "runs" / "run-001"
    return RunContext(
        db_path=db, tile_id="X", run_id="run-001",
        tile_dir=tile_dir, run_dir=run_dir,
        tile_config_path=db / "cfg.yaml",
        project_config_path=db / "proj.yaml",
        semicolab=True, skip_connectivity=skip_connectivity,
        skip_sim=True, skip_synth=True,
    )


def test_connectivity_stage_is_pipeline_stage():
    from veriflow.core.pipeline import PipelineStage
    from veriflow.core.stages.connectivity import ConnectivityStage
    assert issubclass(ConnectivityStage, PipelineStage)
    assert ConnectivityStage.name == "connectivity"


def test_connectivity_stage_skipped_returns_stage_result():
    from veriflow.core.stages.connectivity import ConnectivityStage
    from veriflow.models.stage_result import StageResult
    result = ConnectivityStage(
        rtl_files=[], tb_base_path=None, tb_tasks_path=None, top_module="my_tile",
    ).run(_make_ctx_conn(skip_connectivity=True))
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
        _add_rtl(db, "0001", "my_tile")
        _fill_tile_config(db, "0001", "my_tile")
        _fill_run_config(db, "0001")

        from veriflow.commands.run import cmd_run
        with patch("veriflow.core.stages.connectivity.run_connectivity_check", return_value="FAIL"):
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
        tile_config_path=db / "cfg.yaml",
        project_config_path=db / "proj.yaml",
        semicolab=False, skip_connectivity=True,
        skip_sim=True, skip_synth=skip_synth,
    )


def test_pipeline_stage_not_implemented():
    from veriflow.core.pipeline import PipelineStage
    raised = False
    try:
        PipelineStage().run(_make_ctx())
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
    result = SynthesisStage(rtl_files=[], top_module="my_tile").run(_make_ctx(skip_synth=True))
    assert isinstance(result, StageResult)
    assert result.status == "SKIPPED"
    assert result.name == "synthesis"
    assert result.tool == "yosys"
    assert result.metrics is None


# ── PipelineRunner unit tests ─────────────────────────────────────────────────

def test_pipeline_runner_executes_in_order():
    from veriflow.core.pipeline import PipelineRunner, PipelineStage
    from veriflow.models.stage_result import StageResult

    call_order: list[str] = []

    class StageA(PipelineStage):
        name = "stage_a"
        def run(self, ctx):
            call_order.append("a")
            return StageResult(name=self.name, status="PASS")

    class StageB(PipelineStage):
        name = "stage_b"
        def run(self, ctx):
            call_order.append("b")
            return StageResult(name=self.name, status="PASS")

    PipelineRunner([StageA(), StageB()]).run(_make_ctx())
    assert call_order == ["a", "b"]


def test_pipeline_runner_returns_stage_result_by_name():
    from veriflow.core.pipeline import PipelineRunner, PipelineStage
    from veriflow.models.stage_result import StageResult

    class StageA(PipelineStage):
        name = "stage_a"
        def run(self, ctx):
            return StageResult(name=self.name, status="PASS")

    class StageB(PipelineStage):
        name = "stage_b"
        def run(self, ctx):
            return StageResult(name=self.name, status="SKIPPED")

    results = PipelineRunner([StageA(), StageB()]).run(_make_ctx())
    assert set(results.keys()) == {"stage_a", "stage_b"}
    assert results["stage_a"].status == "PASS"
    assert results["stage_b"].status == "SKIPPED"
    assert isinstance(results["stage_a"], StageResult)


def test_pipeline_runner_propagates_veriflow_error():
    from veriflow.core import VeriFlowError
    from veriflow.core.pipeline import PipelineRunner, PipelineStage

    class FailStage(PipelineStage):
        name = "fail_stage"
        def run(self, ctx):
            raise VeriFlowError("stage failed", code="VF_TEST_FAIL")

    raised = False
    try:
        PipelineRunner([FailStage()]).run(_make_ctx())
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
        tile_config_path=db / "cfg.yaml",
        project_config_path=db / "proj.yaml",
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
    result = SimulationStage(
        rtl_files=[], tb_files=[], tb_base_path=None, tb_tasks_path=None,
        top_module="my_tile", has_tb=True,
    ).run(_make_ctx_sim(skip_sim=True))
    assert isinstance(result, StageResult)
    assert result.status == "SKIPPED"
    assert result.name == "simulation"
    assert result.tool == "iverilog/vvp"
    assert result.metrics is None


def test_simulation_stage_skipped_no_tb():
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.models.stage_result import StageResult
    result = SimulationStage(
        rtl_files=[], tb_files=[], tb_base_path=None, tb_tasks_path=None,
        top_module="my_tile", has_tb=False,
    ).run(_make_ctx_sim(skip_sim=False))
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
        from veriflow.commands.create_tile import cmd_create_tile
        cmd_create_tile(db)
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
    ("semicolab_true_creates_tb_files",  test_semicolab_true_creates_tb_files),
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
    ("connectivity_stage_is_pipeline_stage",              test_connectivity_stage_is_pipeline_stage),
    ("connectivity_stage_skipped_returns_stage_result",   test_connectivity_stage_skipped_returns_stage_result),
    ("connectivity_fail_still_finalizes_run",             test_connectivity_fail_still_finalizes_run),
    ("api_run_tile_returns_dict",                         test_api_run_tile_returns_dict),
    ("api_run_tile_propagates_veriflow_error",            test_api_run_tile_propagates_veriflow_error),
    ("api_run_tile_rejects_waves_non_interactive",        test_api_run_tile_rejects_waves_non_interactive),
]
