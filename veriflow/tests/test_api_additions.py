"""Tests for the new veriflow.api functions added in the 2026-07-15 MCP API
cleanup (dev-docs/MCP_API_AUDIT.md, Parte 2): project_run,
list_interface_profiles, list_technology_profiles, list_pdks,
db_list_tiles, db_list_runs, db_get_run.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from veriflow.core import VeriFlowError


# ── shared helpers ────────────────────────────────────────────────────────────

def _make_project(tmp_path: Path, *, dirname: str = "myproj") -> Path:
    """A minimal generic (no interface, no tb) Project Mode project -- only
    the synthesis stage runs, so a single mocked yosys backend is enough."""
    project_dir = tmp_path / dirname
    (project_dir / "rtl").mkdir(parents=True)
    (project_dir / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    config_path = project_dir / "veriflow.yaml"
    config_path.write_text(
        "design:\n"
        "  top_module: top\n"
        "  rtl_sources:\n"
        "    - rtl/top.v\n",
        encoding="utf-8",
    )
    return config_path


def _make_db(tmp_path: Path) -> Path:
    from veriflow.commands.init_db import cmd_init
    db = tmp_path / "database"
    cmd_init(db)
    return db


def _fill_project_config(db: Path, interface_name: str | None = "semicolab") -> None:
    cfg = {
        "id_prefix": "TST-01",
        "project_name": "Test Project",
        "repo": "",
        "description": "Test project.",
        "interface_name": interface_name,
    }
    (db / "project_config.yaml").write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def _make_tile(db: Path, top_module: str = "my_tile") -> None:
    from veriflow.commands.create_tile import cmd_create_tile
    cmd_create_tile(db, top_module=top_module)


def _add_rtl(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
    rtl_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / f"{module_name}.v").write_text(f"module {module_name}; endmodule\n", encoding="utf-8")


def _fill_tile_config(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
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


def _setup_db_with_tile(tmp_path: Path) -> Path:
    db = _make_db(tmp_path)
    _fill_project_config(db)
    _make_tile(db)
    _add_rtl(db, "0001")
    _fill_tile_config(db, "0001")
    return db


@contextmanager
def _patch_db_tools(
    conn_status: str = "PASS",
    sim_return: tuple = ("COMPLETED", {}),
    synth_return: tuple = ("PASS", {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False}),
):
    with (
        patch("veriflow.workflows.database.validate_tools"),
        patch("veriflow.workflows.database.detect_iverilog_version", return_value="12.0"),
        patch("veriflow.core.backends.icarus.IcarusConnectivityBackend.run_connectivity", return_value=conn_status),
        patch("veriflow.core.backends.icarus.IcarusSimulationBackend.run_simulation", return_value=sim_return),
        patch("veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis", return_value=synth_return),
    ):
        yield


# ── project_run ────────────────────────────────────────────────────────────────

def test_project_run_returns_results_json_dict(tmp_path):
    from veriflow.api import project_run

    config_path = _make_project(tmp_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
        ),
    ):
        data = project_run(config_path)

    assert data["schema_version"] == "1.0"
    assert data["status"] == "PASS"
    assert data["stages"]["synthesis"]["status"] == "PASS"


def test_project_run_fail_is_returned_not_raised(tmp_path):
    """Status FAIL means the RTL did not pass verification -- data, not an
    exception (same pattern as run_tile)."""
    from veriflow.api import project_run

    config_path = _make_project(tmp_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("FAIL", {"cells": "0", "warnings": "0", "errors": "1", "has_latches": False}),
        ),
    ):
        data = project_run(config_path)

    assert data["status"] == "FAIL"


def test_project_run_accepts_str_path(tmp_path):
    from veriflow.api import project_run

    config_path = _make_project(tmp_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
        ),
    ):
        data = project_run(str(config_path))
    assert data["command"] == "project run"


def test_project_run_propagates_veriflow_error_for_bad_config(tmp_path):
    from veriflow.api import project_run

    with pytest.raises(VeriFlowError):
        project_run(tmp_path / "nonexistent" / "veriflow.yaml")


# ── list_interface_profiles ────────────────────────────────────────────────────

def test_list_interface_profiles_includes_semicolab():
    from veriflow.api import list_interface_profiles

    profiles = list_interface_profiles()
    names = {p["name"] for p in profiles}
    assert "semicolab" in names


def test_list_interface_profiles_shape():
    from veriflow.api import list_interface_profiles

    profiles = list_interface_profiles()
    semicolab = next(p for p in profiles if p["name"] == "semicolab")
    assert set(semicolab.keys()) == {"name", "description", "requires_top_module", "ports"}
    assert isinstance(semicolab["ports"], list)
    assert len(semicolab["ports"]) == 9  # semicolab's 9-port contract
    for port in semicolab["ports"]:
        assert set(port.keys()) == {"name", "direction", "width"}
        assert isinstance(port["width"], int)


# ── list_technology_profiles ───────────────────────────────────────────────────

def test_list_technology_profiles_includes_all_builtins():
    from veriflow.api import list_technology_profiles

    technologies = list_technology_profiles()
    names = {t["name"] for t in technologies}
    assert names == {"generic", "sky130", "gf180", "ihp130"}


def test_list_technology_profiles_generic_has_no_pdk_required():
    from veriflow.api import list_technology_profiles

    technologies = list_technology_profiles()
    generic = next(t for t in technologies if t["name"] == "generic")
    assert generic["pdk_installed"] is True
    assert generic["liberty_path"] is None
    assert set(generic.keys()) == {"name", "description", "synthesis_backend", "pdk_installed", "liberty_path"}


def test_list_technology_profiles_uninstalled_pdk_reports_false(tmp_path):
    from veriflow.api import list_technology_profiles

    with patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        technologies = list_technology_profiles()
    sky130 = next(t for t in technologies if t["name"] == "sky130")
    assert sky130["pdk_installed"] is False
    assert sky130["liberty_path"] is None


def test_list_technology_profiles_installed_pdk_reports_liberty_path(tmp_path):
    from veriflow.api import list_technology_profiles

    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    lib_file = lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib"
    lib_file.write_text("", encoding="utf-8")

    with patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        technologies = list_technology_profiles()
    sky130 = next(t for t in technologies if t["name"] == "sky130")
    assert sky130["pdk_installed"] is True
    assert sky130["liberty_path"] == str(lib_file)


# ── list_pdks ────────────────────────────────────────────────────────────────

def test_list_pdks_status(tmp_path):
    from veriflow.api import list_pdks

    (tmp_path / "sky130").mkdir()  # directory exists but no liberty resolves
    lib_dir = tmp_path / "gf180" / "gf180mcuD" / "libs.ref" / "gf180mcu_fd_sc_mcu7t5v0" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib").write_text("", encoding="utf-8")

    with patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        pdks = list_pdks()

    by_name = {p["name"]: p for p in pdks}
    assert by_name["generic"]["status"] == "installed"
    assert by_name["generic"]["install_hint"] is None
    assert by_name["sky130"]["status"] == "not_installed"
    assert by_name["sky130"]["install_hint"] == "veriflow pdk install sky130"
    assert by_name["gf180"]["status"] == "installed"
    assert by_name["gf180"]["liberty_path"] is not None
    assert by_name["ihp130"]["status"] == "not_installed"


def test_list_pdks_shape():
    from veriflow.api import list_pdks

    pdks = list_pdks()
    assert {p["name"] for p in pdks} == {"generic", "sky130", "gf180", "ihp130"}
    for p in pdks:
        assert set(p.keys()) == {"name", "status", "liberty_path", "install_hint"}
        assert p["status"] in ("installed", "not_installed")


# ── db_list_tiles ────────────────────────────────────────────────────────────

def test_db_list_tiles_returns_registered_tile(tmp_path):
    from veriflow.api import db_list_tiles

    db = _setup_db_with_tile(tmp_path)
    tiles = db_list_tiles(db)

    assert len(tiles) == 1
    t = tiles[0]
    assert t["tile_number"] == "0001"
    assert t["interface"] == "semicolab"
    assert set(t.keys()) == {
        "tile_number", "tile_id", "tile_name", "tile_author", "version", "revision", "interface",
    }


def test_db_list_tiles_empty_database_returns_empty_list(tmp_path):
    from veriflow.api import db_list_tiles

    db = _make_db(tmp_path)
    _fill_project_config(db)
    assert db_list_tiles(db) == []


# ── db_list_runs / db_get_run ──────────────────────────────────────────────────

def test_db_list_runs_and_db_get_run(tmp_path):
    from veriflow.api import db_get_run, db_list_runs
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    db = _setup_db_with_tile(tmp_path)
    opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
    with _patch_db_tools():
        DatabaseWorkflow(db).run_tile("0001", opts)

    runs = db_list_runs(db, "0001")
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-001"
    assert set(runs[0].keys()) == {"run_id", "status", "date", "has_waves"}

    run = db_get_run(db, "0001", "run-001")
    assert run["schema_version"] == "1.2"
    assert run["run_id"] == "run-001"
    assert run["stages"]["synthesis"]["status"] == "PASS"


def test_db_list_runs_and_get_run_accept_bare_int_forms(tmp_path):
    """tile/run accept int or unpadded str, not just zero-padded strings."""
    from veriflow.api import db_get_run, db_list_runs
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    db = _setup_db_with_tile(tmp_path)
    opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
    with _patch_db_tools():
        DatabaseWorkflow(db).run_tile("0001", opts)

    runs = db_list_runs(db, 1)
    assert runs[0]["run_id"] == "run-001"

    run = db_get_run(db, 1, 1)
    assert run["run_id"] == "run-001"


def test_db_list_runs_empty_for_tile_with_no_runs(tmp_path):
    from veriflow.api import db_list_runs

    db = _setup_db_with_tile(tmp_path)
    assert db_list_runs(db, "0001") == []


def test_db_list_runs_invalid_tile_number_raises(tmp_path):
    from veriflow.api import db_list_runs

    db = _setup_db_with_tile(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        db_list_runs(db, "abc")
    assert exc_info.value.code == "VF_TILE_NUMBER_INVALID"


def test_db_get_run_invalid_tile_number_raises(tmp_path):
    from veriflow.api import db_get_run

    db = _setup_db_with_tile(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        db_get_run(db, "abc", "run-001")
    assert exc_info.value.code == "VF_TILE_NUMBER_INVALID"


def test_db_get_run_missing_run_raises(tmp_path):
    from veriflow.api import db_get_run

    db = _setup_db_with_tile(tmp_path)
    with pytest.raises(VeriFlowError):
        db_get_run(db, "0001", "run-999")
