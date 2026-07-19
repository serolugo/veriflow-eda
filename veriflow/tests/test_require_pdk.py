"""Regression tests for the `technology.require_pdk` flag (2026-07-18):
forces synthesis to fail explicitly (VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED)
when the named technology's PDK isn't installed, instead of silently
degrading to generic synthesis with a warning.

SynthesisStage's own behavior (raise vs. warn+fallback) is covered in
test_synthesis_technology.py. This file covers:
  A. TileConfig.from_dict's tile-level `technology: {require_pdk: ...}` section
  B. DatabaseWorkflow.run_tile -- tile > project > default require_pdk inheritance
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from veriflow.core import VeriFlowError


# ── A. TileConfig.from_dict: technology.require_pdk ───────────────────────────


def test_tile_config_require_pdk_true_parses():
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({"technology": {"require_pdk": True}})
    assert cfg.require_pdk is True


def test_tile_config_require_pdk_false_parses():
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({"technology": {"require_pdk": False}})
    assert cfg.require_pdk is False


def test_tile_config_require_pdk_absent_is_none_inherit():
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({})
    assert cfg.require_pdk is None


def test_tile_config_technology_section_without_require_pdk_is_none():
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({"technology": {}})
    assert cfg.require_pdk is None


def test_tile_config_require_pdk_non_bool_fails():
    from veriflow.models.tile_config import TileConfig
    with pytest.raises(VeriFlowError) as exc_info:
        TileConfig.from_dict({"technology": {"require_pdk": "true"}})
    assert exc_info.value.code == "VF_TILE_TECHNOLOGY_CONFIG_INVALID"


def test_tile_config_technology_unknown_key_fails():
    """A tile can't override technology *name* -- that's database-wide,
    set only in project_config.yaml."""
    from veriflow.models.tile_config import TileConfig
    with pytest.raises(VeriFlowError) as exc_info:
        TileConfig.from_dict({"technology": {"name": "sky130"}})
    assert exc_info.value.code == "VF_TILE_TECHNOLOGY_CONFIG_INVALID"


def test_tile_config_technology_non_mapping_fails():
    from veriflow.models.tile_config import TileConfig
    with pytest.raises(VeriFlowError) as exc_info:
        TileConfig.from_dict({"technology": "sky130"})
    assert exc_info.value.code == "VF_TILE_TECHNOLOGY_CONFIG_INVALID"


# ── B. DatabaseWorkflow.run_tile: tile > project > default inheritance ───────


def _make_db(tmp: Path) -> Path:
    from veriflow.commands.init_db import cmd_init
    db = tmp / "database"
    cmd_init(db)
    return db


def _fill_project_config(db: Path, *, technology_yaml: str = "") -> None:
    text = (
        'id_prefix: "TST-01"\nproject_name: "Test"\nrepo: ""\n'
        'interface_name: null\ndescription: |\n\n' + technology_yaml
    )
    (db / "project_config.yaml").write_text(text, encoding="utf-8")


def _add_rtl(db: Path, tile_number_str: str, module_name: str = "top") -> None:
    rtl_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / f"{module_name}.v").write_text(f"module {module_name}; endmodule\n", encoding="utf-8")


def _fill_tile_config(db: Path, tile_number_str: str, *, module_name="top", technology_yaml: str = "") -> None:
    cfg_path = db / "config" / f"tile_{tile_number_str}" / "tile_config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    text = text.replace('top_module: ""', f'top_module: "{module_name}"')
    text += "\n" + technology_yaml
    cfg_path.write_text(text, encoding="utf-8")


def _setup_db(tmp: Path, *, project_technology_yaml="", tile_technology_yaml="") -> Path:
    from veriflow.commands.create_tile import cmd_create_tile
    db = _make_db(tmp)
    _fill_project_config(db, technology_yaml=project_technology_yaml)
    cmd_create_tile(db, top_module="top")
    _add_rtl(db, "0001")
    _fill_tile_config(db, "0001", technology_yaml=tile_technology_yaml)
    return db


@patch("veriflow.workflows.database.validate_tools")
@patch("veriflow.workflows.database.detect_iverilog_version", return_value="12.0")
@patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=None)  # PDK never installed
@patch("veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
       return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}))
@patch("veriflow.core.backends.icarus.IcarusSimulationBackend.run_simulation", return_value=("COMPLETED", {}))
@patch("veriflow.core.backends.icarus.IcarusConnectivityBackend.run_connectivity", return_value="PASS")
class TestDatabaseRequirePdkInheritance:
    def test_neither_set_defaults_to_false_warns_not_raises(self, conn_mock, sim_mock, synth_mock, *_):
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(
                tmp,
                project_technology_yaml='technology:\n  name: "sky130"\n',
            )
            result = DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert result.data["stages"]["synthesis"]["status"] == "PASS"
            assert synth_mock.called
        finally:
            import shutil
            shutil.rmtree(tmp)

    def test_project_require_pdk_true_raises_when_tile_unset(self, conn_mock, sim_mock, synth_mock, *_):
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(
                tmp,
                project_technology_yaml='technology:\n  name: "sky130"\n  require_pdk: true\n',
            )
            with pytest.raises(VeriFlowError) as exc_info:
                DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert exc_info.value.code == "VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED"
            assert not synth_mock.called
        finally:
            import shutil
            shutil.rmtree(tmp)

    def test_tile_require_pdk_false_overrides_project_true(self, conn_mock, sim_mock, synth_mock, *_):
        """Tile explicitly opts out of the database's require_pdk -- proceeds
        with the usual warn+generic-fallback instead of failing."""
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(
                tmp,
                project_technology_yaml='technology:\n  name: "sky130"\n  require_pdk: true\n',
                tile_technology_yaml='technology:\n  require_pdk: false\n',
            )
            result = DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert result.data["stages"]["synthesis"]["status"] == "PASS"
            assert synth_mock.called
        finally:
            import shutil
            shutil.rmtree(tmp)

    def test_tile_require_pdk_true_overrides_project_false(self, conn_mock, sim_mock, synth_mock, *_):
        """Tile opts INTO require_pdk even though the database default is
        False -- raises, same as if the database itself required it."""
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(
                tmp,
                project_technology_yaml='technology:\n  name: "sky130"\n  require_pdk: false\n',
                tile_technology_yaml='technology:\n  require_pdk: true\n',
            )
            with pytest.raises(VeriFlowError) as exc_info:
                DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert exc_info.value.code == "VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED"
            assert not synth_mock.called
        finally:
            import shutil
            shutil.rmtree(tmp)
