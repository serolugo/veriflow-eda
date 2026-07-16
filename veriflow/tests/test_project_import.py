"""Regression tests for `veriflow project import` (2026-07-14): importing a
verified Project Mode run into a Database Mode database as a new tile.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from veriflow.api import project_import
from veriflow.core import VeriFlowError


# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_conn_backend(status="PASS"):
    from veriflow.core.backends.base import ConnectivityBackend
    b = MagicMock(spec=ConnectivityBackend)
    b.run_connectivity.return_value = status
    return b


def _mock_sim_backend(status="COMPLETED"):
    from veriflow.core.backends.base import SimulationBackend
    b = MagicMock(spec=SimulationBackend)
    b.run_simulation.return_value = (status, {})
    return b


def _mock_synth_backend(status="PASS"):
    from veriflow.core.backends.base import SynthesisBackend
    b = MagicMock(spec=SynthesisBackend)
    b.run_synthesis.return_value = (
        status,
        {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False},
    )
    return b


def _make_project(
    tmp_path: Path,
    *,
    dirname: str = "myproj",
    interface_name: str | None = "semicolab",
    with_tb: bool = True,
) -> Path:
    """Create a project directory with RTL (+ optional TB) and veriflow.yaml.
    Does not run it -- call _run_project() separately."""
    project_dir = tmp_path / dirname
    (project_dir / "rtl").mkdir(parents=True)
    (project_dir / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")

    yaml_lines = [
        "design:",
        "  top_module: top",
        "  rtl_sources:",
        "    - rtl/top.v",
    ]
    if with_tb:
        (project_dir / "tb").mkdir(parents=True)
        (project_dir / "tb" / "tb_top.v").write_text("module tb; endmodule\n", encoding="utf-8")
        yaml_lines += ["  tb_sources:", "    - tb/tb_top.v"]
    if interface_name is not None:
        yaml_lines += ["interface:", f"  name: {interface_name}"]
    if with_tb:
        yaml_lines += ["simulation:", "  tb_top: tb"]

    config_path = project_dir / "veriflow.yaml"
    config_path.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    return config_path


def _run_project(
    config_path: Path,
    *,
    conn_status="PASS",
    sim_status="COMPLETED",
    synth_status="PASS",
) -> str:
    """Run the project (mocked backends) and return the run_id created."""
    from veriflow.workflows.project import ProjectWorkflow
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    cfg = ProjectWorkflowConfig.from_file(config_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend(conn_status)),
        patch("veriflow.workflows.project.get_simulation_backend", return_value=_mock_sim_backend(sim_status)),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend(synth_status)),
    ):
        pr = ProjectWorkflow(cfg).run()
    return pr.run_dir.name


def _make_db(tmp_path: Path, *, interface_name: str | None = "semicolab", dirname: str = "mydb") -> Path:
    from veriflow.commands.init_db import cmd_init

    db_path = tmp_path / dirname
    cmd_init(db_path)
    cfg = {
        "id_prefix": "TST",
        "project_name": "Test DB",
        "repo": "",
        "description": "Test project.",
        "interface_name": interface_name,
    }
    (db_path / "project_config.yaml").write_text(
        yaml.dump(cfg, default_flow_style=False), encoding="utf-8"
    )
    return db_path


# ── 1. Successful import (latest passing run) ────────────────────────────────


def test_import_latest_passing_run_creates_tile(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    assert result["tile_number"] == "0001"
    assert result["run_id"] == "run-001"
    assert result["db_path"] == str(db_path.resolve())
    assert result["config_path"] == str(config_path.resolve())
    assert "top.v" in result["rtl_hash"]


def test_import_copies_rtl_sources(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_dir = db_path / "config" / f"tile_{result['tile_number']}"
    rtl_file = tile_dir / "src" / "rtl" / "top.v"
    assert rtl_file.exists()
    assert rtl_file.read_text(encoding="utf-8") == "module top; endmodule\n"


def test_import_copies_tb_sources_and_removes_placeholder(tmp_path):
    config_path = _make_project(tmp_path, with_tb=True)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_dir = db_path / "config" / f"tile_{result['tile_number']}"
    tb_dir = tile_dir / "src" / "tb"
    assert (tb_dir / "tb_top.v").exists()
    # The auto-generated scaffold must be gone -- two `module tb;` files
    # would collide at simulation time.
    assert not (tb_dir / "tb_tile.v").exists()


def test_import_without_tb_sources_leaves_placeholder_untouched(tmp_path):
    """rtl-only project: nothing to copy into src/tb/, so create_tile's own
    scaffold (if any) is left alone."""
    config_path = _make_project(tmp_path, interface_name=None, with_tb=False)
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name=None)

    result = project_import(config_path, db_path)

    tile_dir = db_path / "config" / f"tile_{result['tile_number']}"
    assert list((tile_dir / "src" / "rtl").glob("*.v")) != []
    # universal template scaffold still present, untouched
    assert (tile_dir / "src" / "tb" / "tb_tile.v").exists()


def test_import_writes_imported_run_json_matching_results(tmp_path):
    config_path = _make_project(tmp_path)
    run_id = _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_dir = db_path / "config" / f"tile_{result['tile_number']}"
    imported = json.loads((tile_dir / "imported_run.json").read_text(encoding="utf-8"))
    original = json.loads(
        (config_path.parent / "runs" / run_id / "results.json").read_text(encoding="utf-8")
    )
    assert imported == original
    assert imported["rtl_hash"] == result["rtl_hash"]


def test_import_prefills_tile_name_from_project_directory(tmp_path):
    config_path = _make_project(tmp_path, dirname="counter8_project")
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_cfg = (db_path / "config" / f"tile_{result['tile_number']}" / "tile_config.yaml").read_text(encoding="utf-8")
    assert 'tile_name: "counter8_project"' in tile_cfg


def test_import_prefills_top_module_and_tb_top_module(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_cfg = (db_path / "config" / f"tile_{result['tile_number']}" / "tile_config.yaml").read_text(encoding="utf-8")
    assert 'top_module: "top"' in tile_cfg
    assert 'tb_top_module: "tb"' in tile_cfg


def test_import_registers_tile_in_tile_index(tmp_path):
    from veriflow.core.csv_store import get_tile_row

    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    row = get_tile_row(db_path / "tile_index.csv", "0001")
    assert row["tile_id"] == result["tile_id"]


# ── 2. Error cases ─────────────────────────────────────────────────────────────


def test_import_no_passing_run_raises(tmp_path):
    """A run exists but FAILed -- no run_id given, no PASS run to pick."""
    config_path = _make_project(tmp_path)
    _run_project(config_path, synth_status="FAIL")
    db_path = _make_db(tmp_path)

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path)
    assert exc_info.value.code == "VF_IMPORT_NO_PASSING_RUN"


def test_import_no_runs_at_all_raises_no_passing_run(tmp_path):
    config_path = _make_project(tmp_path)
    db_path = _make_db(tmp_path)

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path)
    assert exc_info.value.code == "VF_IMPORT_NO_PASSING_RUN"


def test_import_specific_run_not_found_raises(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path, run_id="run-999")
    assert exc_info.value.code == "VF_IMPORT_RUN_NOT_FOUND"


def test_import_specific_run_not_passing_raises(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path, synth_status="FAIL")
    db_path = _make_db(tmp_path)

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path, run_id="run-001")
    assert exc_info.value.code == "VF_IMPORT_RUN_NOT_PASSING"
    assert "run-001" in str(exc_info.value)


def test_import_interface_mismatch_raises(tmp_path):
    config_path = _make_project(tmp_path, interface_name="semicolab")
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name=None)

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path)
    assert exc_info.value.code == "VF_IMPORT_INTERFACE_MISMATCH"
    assert "semicolab" in str(exc_info.value)


def test_import_invalid_db_yaml_raises(tmp_path):
    """A malformed project_config.yaml in the destination database raises a
    VeriFlowError (VF_DATABASE_CONFIG_YAML_ERROR), not a bare
    yaml.YAMLError (dev-docs/MCP_API_AUDIT.md)."""
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)
    # Corrupt the destination db's project_config.yaml with invalid YAML
    (db_path / "project_config.yaml").write_text(
        "id_prefix: [unterminated\n", encoding="utf-8"
    )

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path)
    assert exc_info.value.code == "VF_DATABASE_CONFIG_YAML_ERROR"


def test_import_missing_rtl_source_raises(tmp_path):
    """An RTL source recorded in results.json but deleted from disk after
    the run raises VF_IMPORT_RTL_SOURCE_MISSING, not a bare
    FileNotFoundError (dev-docs/MCP_API_AUDIT.md)."""
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    # Delete the RTL source recorded in the run's results.json
    (config_path.parent / "rtl" / "top.v").unlink()

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path)
    assert exc_info.value.code == "VF_IMPORT_RTL_SOURCE_MISSING"
    assert "top.v" in str(exc_info.value)


def test_import_interface_none_in_project_never_mismatches(tmp_path):
    """A generic (no-interface) project can be imported into any database,
    including one that declares an interface -- only a *declared* mismatch
    (project sets X, db sets Y != X) should fail, per VF_IMPORT_INTERFACE_MISMATCH."""
    config_path = _make_project(tmp_path, interface_name=None, with_tb=False)
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name="semicolab")

    result = project_import(config_path, db_path)
    assert result["tile_number"] == "0001"


# ── 3. Explicit --run selection ────────────────────────────────────────────────


def test_import_explicit_run_id_picks_that_run_not_latest(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)  # run-001, PASS
    _run_project(config_path, synth_status="FAIL")  # run-002, FAIL
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path, run_id="run-001")
    assert result["run_id"] == "run-001"


def test_import_latest_passing_skips_a_later_failing_run(tmp_path):
    """run-002 fails after run-001 passes -- auto-select must still find run-001."""
    config_path = _make_project(tmp_path)
    _run_project(config_path)  # run-001, PASS
    _run_project(config_path, synth_status="FAIL")  # run-002, FAIL
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)
    assert result["run_id"] == "run-001"


def test_import_picks_highest_numbered_passing_run(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)  # run-001, PASS
    _run_project(config_path)  # run-002, PASS
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)
    assert result["run_id"] == "run-002"


# ── 4. CLI dispatch ────────────────────────────────────────────────────────────


def test_cli_project_import_dispatches(tmp_path):
    from veriflow.cli import main

    fake_result = {
        "tile_id": "TST-1",
        "tile_number": "0001",
        "db_path": str(tmp_path / "db"),
        "config_path": str(tmp_path / "veriflow.yaml"),
        "run_id": "run-001",
        "rtl_hash": {"top.v": "abc123"},
    }
    with patch("veriflow.api.project_import", return_value=fake_result) as mock_fn:
        rc = main(["project", "import", "--db", str(tmp_path / "db"), "--config", str(tmp_path / "veriflow.yaml")])

    mock_fn.assert_called_once_with(
        Path(str(tmp_path / "veriflow.yaml")), Path(str(tmp_path / "db")), run_id=None
    )
    assert rc == 0


def test_cli_project_import_forwards_run_id(tmp_path):
    from veriflow.cli import main

    fake_result = {
        "tile_id": "TST-1", "tile_number": "0001",
        "db_path": str(tmp_path / "db"), "config_path": str(tmp_path / "veriflow.yaml"),
        "run_id": "run-003", "rtl_hash": {},
    }
    with patch("veriflow.api.project_import", return_value=fake_result) as mock_fn:
        main(["project", "import", "--db", str(tmp_path / "db"), "--run", "run-003"])

    mock_fn.assert_called_once_with(Path("veriflow.yaml"), Path(str(tmp_path / "db")), run_id="run-003")


def test_cli_project_import_output_includes_tile_id(tmp_path, capsys):
    from veriflow.cli import main

    fake_result = {
        "tile_id": "TST-42", "tile_number": "0001",
        "db_path": str(tmp_path / "db"), "config_path": str(tmp_path / "veriflow.yaml"),
        "run_id": "run-001", "rtl_hash": {},
    }
    with patch("veriflow.api.project_import", return_value=fake_result):
        main(["project", "import", "--db", str(tmp_path / "db")])
    out = capsys.readouterr().out
    assert "TST-42" in out


def test_cli_project_import_veriflow_error_propagates_nonzero(tmp_path):
    from veriflow.cli import main

    with patch(
        "veriflow.api.project_import",
        side_effect=VeriFlowError("no run", code="VF_IMPORT_NO_PASSING_RUN"),
    ):
        rc = main(["project", "import", "--db", str(tmp_path / "db")])
    assert rc != 0


def test_project_import_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["project", "import", "--db", "mydb"])
    assert args.command == "project"
    assert args.project_command == "import"
    assert args.db == "mydb"
    assert args.config == "veriflow.yaml"
    assert args.run_id is None
