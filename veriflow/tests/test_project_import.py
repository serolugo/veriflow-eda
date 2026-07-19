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


def _make_db(
    tmp_path: Path,
    *,
    interface_name: str | None = "semicolab",
    dirname: str = "mydb",
    technology_name: str | None = None,
) -> Path:
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
    if technology_name is not None:
        cfg["technology"] = {"name": technology_name}
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


def test_import_carries_metadata_name_author_description_to_tile_config(tmp_path):
    """veriflow.yaml's metadata.name/author/description are carried into
    the new tile's tile_config.yaml (tile_name/tile_author/description),
    instead of requiring the user to retype what they already wrote once."""
    config_path = _make_project(tmp_path, dirname="counter8_project")
    with config_path.open("a", encoding="utf-8") as f:
        f.write(
            "metadata:\n"
            "  name: Counter8 Tile\n"
            "  author: Roman Lugo\n"
            "  description: An 8-bit counter with async reset.\n"
        )
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_cfg_path = db_path / "config" / f"tile_{result['tile_number']}" / "tile_config.yaml"
    tile_cfg_text = tile_cfg_path.read_text(encoding="utf-8")
    assert 'tile_name: "Counter8 Tile"' in tile_cfg_text
    assert 'tile_author: "Roman Lugo"' in tile_cfg_text

    tile_cfg = yaml.safe_load(tile_cfg_text)
    assert tile_cfg["description"].strip() == "An 8-bit counter with async reset."


def test_import_metadata_name_preferred_over_directory_name(tmp_path):
    config_path = _make_project(tmp_path, dirname="counter8_project")
    with config_path.open("a", encoding="utf-8") as f:
        f.write("metadata:\n  name: A Nicer Display Name\n")
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_cfg = (db_path / "config" / f"tile_{result['tile_number']}" / "tile_config.yaml").read_text(encoding="utf-8")
    assert 'tile_name: "A Nicer Display Name"' in tile_cfg
    assert "counter8_project" not in tile_cfg


def test_import_without_metadata_falls_back_to_directory_name(tmp_path):
    """Unchanged pre-existing behavior when the source project has no
    metadata section at all."""
    config_path = _make_project(tmp_path, dirname="counter8_project")
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    result = project_import(config_path, db_path)

    tile_cfg_path = db_path / "config" / f"tile_{result['tile_number']}" / "tile_config.yaml"
    tile_cfg_text = tile_cfg_path.read_text(encoding="utf-8")
    assert 'tile_name: "counter8_project"' in tile_cfg_text
    assert 'tile_author: ""' in tile_cfg_text


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


def test_import_generic_project_into_interface_database_blocked_by_default(tmp_path):
    """A generic (no-interface) project imported into a database that
    *requires* one interface is blocked by default (VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE),
    not silently allowed through -- confirmed live: the tile got created,
    was labeled with the database's interface (interface is database-wide,
    not per-tile), and its first `db run` failed connectivity immediately
    because the RTL was never verified against that contract. This is
    symmetric to VF_IMPORT_INTERFACE_MISMATCH (declared-but-different is an
    error) -- "undeclared" against a database that requires one is now also
    an error, not a free pass."""
    config_path = _make_project(tmp_path, interface_name=None, with_tb=False)
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name="semicolab")

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path)
    assert exc_info.value.code == "VF_IMPORT_GENERIC_TO_INTERFACE_DATABASE"
    assert "semicolab" in str(exc_info.value)

    # No tile should have been created
    assert not (db_path / "config" / "tile_0001").exists()


def test_import_generic_project_into_interface_database_with_force(tmp_path):
    config_path = _make_project(tmp_path, interface_name=None, with_tb=False)
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name="semicolab")

    result = project_import(config_path, db_path, force=True)

    assert result["tile_number"] == "0001"
    assert len(result["warnings"]) == 1
    warning = result["warnings"][0]
    assert "generic" in warning
    assert "semicolab" in warning


def test_import_generic_project_into_generic_database_still_works(tmp_path):
    """Both sides generic (no interface declared anywhere) is the
    legitimate case -- must keep working with no error or warning."""
    config_path = _make_project(tmp_path, interface_name=None, with_tb=False)
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name=None)

    result = project_import(config_path, db_path)
    assert result["tile_number"] == "0001"
    assert result["warnings"] == []


# ── 2b. Technology comparison (Gotcha B: warn, don't block) ──────────────────


def test_import_technology_mismatch_warns_not_raises(tmp_path):
    """Source project defaults to technology 'generic' (no `technology:`
    section in veriflow.yaml); destination database declares 'sky130'.
    This must not block the import -- only a warning message, since the
    tile can just be re-synthesized against 'sky130' on the next db run."""
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path, technology_name="sky130")

    result = project_import(config_path, db_path)

    assert result["tile_number"] == "0001"
    assert len(result["warnings"]) == 1
    warning = result["warnings"][0]
    assert "generic" in warning
    assert "sky130" in warning
    assert "re-synthesized" in warning


def test_import_technology_match_no_warning(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path, technology_name="generic")

    result = project_import(config_path, db_path)
    assert result["warnings"] == []


def test_import_technology_unset_in_db_no_warning(tmp_path):
    """Destination database with no `technology:` section at all imposes no
    constraint -- never warns, regardless of the source project's technology."""
    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path, technology_name=None)

    result = project_import(config_path, db_path)
    assert result["warnings"] == []


# ── 2c. RTL filename vs top_module (Gotcha A) ─────────────────────────────────


def _make_project_with_rtl_filename(
    tmp_path: Path,
    *,
    rtl_filename: str,
    top_module: str = "top",
    dirname: str = "myproj",
) -> Path:
    """Like `_make_project`, but the RTL file's name and the `module` name it
    declares can differ, to exercise the Gotcha A auto-rename/error path.
    No testbench (irrelevant to this check)."""
    project_dir = tmp_path / dirname
    (project_dir / "rtl").mkdir(parents=True)
    (project_dir / "rtl" / rtl_filename).write_text(
        f"module {top_module}; endmodule\n", encoding="utf-8"
    )

    config_path = project_dir / "veriflow.yaml"
    config_path.write_text(
        "\n".join([
            "design:",
            f"  top_module: {top_module}",
            "  rtl_sources:",
            f"    - rtl/{rtl_filename}",
        ]) + "\n",
        encoding="utf-8",
    )
    return config_path


def test_import_rtl_filename_mismatch_auto_renames_with_warning(tmp_path):
    """RTL source is named `core.v` but declares `module top` -- Database
    Mode locates the top-level file by filename convention, so it must be
    renamed to `top.v` on copy, with an informative warning."""
    config_path = _make_project_with_rtl_filename(
        tmp_path, rtl_filename="core.v", top_module="top"
    )
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name=None)

    result = project_import(config_path, db_path)

    tile_dir = db_path / "config" / f"tile_{result['tile_number']}"
    assert (tile_dir / "src" / "rtl" / "top.v").is_file()
    assert not (tile_dir / "src" / "rtl" / "core.v").exists()
    assert len(result["warnings"]) == 1
    assert "core.v" in result["warnings"][0]
    assert "top.v" in result["warnings"][0]


def test_import_rtl_filename_already_matches_no_rename(tmp_path):
    config_path = _make_project_with_rtl_filename(
        tmp_path, rtl_filename="top.v", top_module="top"
    )
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name=None)

    result = project_import(config_path, db_path)

    tile_dir = db_path / "config" / f"tile_{result['tile_number']}"
    assert (tile_dir / "src" / "rtl" / "top.v").is_file()
    assert result["warnings"] == []


def test_import_top_module_not_in_any_source_raises(tmp_path):
    """Safety net: if no recorded RTL source declares `module <top_module>`
    at all (shouldn't happen if `project run` already passed connectivity),
    raise VF_IMPORT_TOP_MODULE_NOT_IN_SOURCES rather than silently importing
    a tile that can never simulate/synthesize correctly."""
    config_path = _make_project_with_rtl_filename(
        tmp_path, rtl_filename="core.v", top_module="top"
    )
    _run_project(config_path)
    db_path = _make_db(tmp_path, interface_name=None)

    # Simulate the module having been renamed/removed after the run completed
    (config_path.parent / "rtl" / "core.v").write_text(
        "module something_else; endmodule\n", encoding="utf-8"
    )

    with pytest.raises(VeriFlowError) as exc_info:
        project_import(config_path, db_path)
    assert exc_info.value.code == "VF_IMPORT_TOP_MODULE_NOT_IN_SOURCES"
    assert "top" in str(exc_info.value)


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
        Path(str(tmp_path / "veriflow.yaml")), Path(str(tmp_path / "db")), run_id=None, force=False
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

    mock_fn.assert_called_once_with(
        Path("veriflow.yaml"), Path(str(tmp_path / "db")), run_id="run-003", force=False
    )


def test_cli_project_import_forwards_force_flag(tmp_path):
    from veriflow.cli import main

    fake_result = {
        "tile_id": "TST-1", "tile_number": "0001",
        "db_path": str(tmp_path / "db"), "config_path": str(tmp_path / "veriflow.yaml"),
        "run_id": "run-001", "rtl_hash": {}, "warnings": ["WARNING: tile imported as generic ..."],
    }
    with patch("veriflow.api.project_import", return_value=fake_result) as mock_fn:
        main(["project", "import", "--db", str(tmp_path / "db"), "--force"])

    mock_fn.assert_called_once_with(
        Path("veriflow.yaml"), Path(str(tmp_path / "db")), run_id=None, force=True
    )


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


def test_cli_project_import_output_excludes_create_tile_lines(tmp_path, capsys):
    """cmd_create_tile's own step-by-step progress output (tagged
    "[create-tile]") must not leak into `project import`'s summary -- it
    is invoked with silent=True and only the "[project-import]" lines
    plus the final summary should appear."""
    from veriflow.cli import main

    config_path = _make_project(tmp_path)
    _run_project(config_path)
    db_path = _make_db(tmp_path)

    rc = main(["project", "import", "--db", str(db_path), "--config", str(config_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "create-tile" not in out
    assert "project-import" in out


def test_project_import_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["project", "import", "--db", "mydb"])
    assert args.command == "project"
    assert args.project_command == "import"
    assert args.db == "mydb"
    assert args.config == "veriflow.yaml"
    assert args.run_id is None
