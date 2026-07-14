"""Regression tests for the configurable pipeline: which stages run, in
what order, and on what backend (2026-07-14 design change).

Covers:
  A. models/pipeline_config.py -- PipelineConfig.from_dict, DEFAULT_PIPELINE
  B. ProjectWorkflowConfig (veriflow.yaml) parsing + build_project_flow
  C. ProjectConfig/TileConfig (Database Mode) parsing
  D. DatabaseWorkflow.run_tile -- tile > project > default inheritance
  E. Backward compatibility: no pipeline section anywhere -> unchanged behavior
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from veriflow.core import VeriFlowError


# ── A. PipelineConfig / DEFAULT_PIPELINE ──────────────────────────────────────


def test_pipeline_config_from_dict_full_list():
    from veriflow.models.pipeline_config import PipelineConfig
    cfg = PipelineConfig.from_dict({
        "stages": [
            {"type": "connectivity"},
            {"type": "simulation"},
            {"type": "synthesis"},
        ]
    })
    assert [s.type for s in cfg.stages] == ["connectivity", "simulation", "synthesis"]


def test_pipeline_config_from_dict_partial_list():
    from veriflow.models.pipeline_config import PipelineConfig
    cfg = PipelineConfig.from_dict({"stages": [{"type": "connectivity"}, {"type": "synthesis"}]})
    assert [s.type for s in cfg.stages] == ["connectivity", "synthesis"]
    assert not cfg.has_stage("simulation")


def test_pipeline_config_from_dict_backend_override():
    from veriflow.models.pipeline_config import PipelineConfig
    cfg = PipelineConfig.from_dict({"stages": [{"type": "synthesis", "backend": "yosys"}]})
    assert cfg.backend_for("synthesis") == "yosys"


def test_pipeline_config_from_dict_no_backend_is_none():
    from veriflow.models.pipeline_config import PipelineConfig
    cfg = PipelineConfig.from_dict({"stages": [{"type": "synthesis"}]})
    assert cfg.backend_for("synthesis") is None
    assert cfg.backend_for("connectivity") is None  # not even in the pipeline


def test_pipeline_config_unknown_stage_type_raises():
    from veriflow.models.pipeline_config import PipelineConfig
    with pytest.raises(VeriFlowError) as exc_info:
        PipelineConfig.from_dict({"stages": [{"type": "bogus"}]})
    assert exc_info.value.code == "VF_PIPELINE_STAGE_UNKNOWN"
    assert "bogus" in str(exc_info.value)


def test_pipeline_config_missing_type_key_raises():
    from veriflow.models.pipeline_config import PipelineConfig
    with pytest.raises(VeriFlowError) as exc_info:
        PipelineConfig.from_dict({"stages": [{"backend": "icarus"}]})
    assert exc_info.value.code == "VF_PIPELINE_STAGE_UNKNOWN"


def test_pipeline_config_extra_keys_ignored_silently():
    from veriflow.models.pipeline_config import PipelineConfig
    cfg = PipelineConfig.from_dict({"stages": [{"type": "connectivity", "timeout": 30, "flag": True}]})
    assert [s.type for s in cfg.stages] == ["connectivity"]


def test_pipeline_config_absent_stages_key_is_empty():
    from veriflow.models.pipeline_config import PipelineConfig
    cfg = PipelineConfig.from_dict({})
    assert cfg.stages == ()


def test_default_pipeline_has_three_stages_in_order():
    from veriflow.models.pipeline_config import DEFAULT_PIPELINE
    assert [s.type for s in DEFAULT_PIPELINE.stages] == ["connectivity", "simulation", "synthesis"]
    assert all(s.backend is None for s in DEFAULT_PIPELINE.stages)


def test_parse_optional_pipeline_section_absent_returns_none():
    from veriflow.models.pipeline_config import parse_optional_pipeline_section
    assert parse_optional_pipeline_section({}) is None
    assert parse_optional_pipeline_section({"pipeline": None}) is None


def test_parse_optional_pipeline_section_malformed_raises():
    from veriflow.models.pipeline_config import parse_optional_pipeline_section
    with pytest.raises(VeriFlowError) as exc_info:
        parse_optional_pipeline_section({"pipeline": "not-a-mapping"})
    assert exc_info.value.code == "VF_PIPELINE_CONFIG_INVALID"


def test_parse_optional_pipeline_section_valid():
    from veriflow.models.pipeline_config import parse_optional_pipeline_section
    cfg = parse_optional_pipeline_section({"pipeline": {"stages": [{"type": "synthesis"}]}})
    assert cfg is not None
    assert [s.type for s in cfg.stages] == ["synthesis"]


# ── B. ProjectWorkflowConfig + build_project_flow ─────────────────────────────


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
    b.run_synthesis.return_value = (status, {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    return b


def _full_project_config(tmp_path: Path, pipeline_yaml: str = "") -> "object":
    from veriflow.workflows.project_config import ProjectWorkflowConfig
    (tmp_path / "rtl").mkdir(exist_ok=True)
    (tmp_path / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    (tmp_path / "tb").mkdir(exist_ok=True)
    (tmp_path / "tb" / "tb_top.v").write_text("module tb; endmodule\n", encoding="utf-8")
    text = (
        "design:\n"
        "  top_module: top\n"
        "  rtl_sources:\n"
        "    - rtl/top.v\n"
        "  tb_sources:\n"
        "    - tb/tb_top.v\n"
        "interface:\n"
        "  name: semicolab\n"
        "simulation:\n"
        "  tb_top: tb\n"
        + pipeline_yaml
    )
    return ProjectWorkflowConfig.from_dict(yaml.safe_load(text), root=tmp_path)


def test_project_workflow_config_default_pipeline_when_absent(tmp_path):
    cfg = _full_project_config(tmp_path)
    from veriflow.models.pipeline_config import DEFAULT_PIPELINE
    assert cfg.pipeline == DEFAULT_PIPELINE


def test_project_workflow_config_custom_pipeline_parsed(tmp_path):
    cfg = _full_project_config(
        tmp_path,
        "pipeline:\n  stages:\n    - type: connectivity\n    - type: synthesis\n",
    )
    assert [s.type for s in cfg.pipeline.stages] == ["connectivity", "synthesis"]


def test_project_workflow_config_unknown_stage_type_propagates(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        _full_project_config(tmp_path, "pipeline:\n  stages:\n    - type: bogus\n")
    assert exc_info.value.code == "VF_PIPELINE_STAGE_UNKNOWN"


def test_build_project_flow_excludes_simulation_when_not_in_pipeline(tmp_path):
    from veriflow.workflows.project import build_project_flow
    cfg = _full_project_config(
        tmp_path,
        "pipeline:\n  stages:\n    - type: connectivity\n    - type: synthesis\n",
    )
    design, flow = build_project_flow(cfg)
    assert [s.name for s in flow.stages] == ["connectivity", "synthesis"]


def test_build_project_flow_default_pipeline_includes_all_three(tmp_path):
    from veriflow.workflows.project import build_project_flow
    cfg = _full_project_config(tmp_path)
    design, flow = build_project_flow(cfg)
    assert [s.name for s in flow.stages] == ["connectivity", "simulation", "synthesis"]


def test_build_project_flow_synthesis_only_pipeline(tmp_path):
    from veriflow.workflows.project import build_project_flow
    cfg = _full_project_config(tmp_path, "pipeline:\n  stages:\n    - type: synthesis\n")
    design, flow = build_project_flow(cfg)
    assert [s.name for s in flow.stages] == ["synthesis"]


def test_run_with_custom_pipeline_skips_simulation_stage_result(tmp_path):
    from veriflow.workflows.project import ProjectWorkflow
    cfg = _full_project_config(
        tmp_path,
        "pipeline:\n  stages:\n    - type: connectivity\n    - type: synthesis\n",
    )
    with (
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend()),
        patch("veriflow.workflows.project.get_simulation_backend", return_value=_mock_sim_backend()) as sim_getter,
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend()),
    ):
        pr = ProjectWorkflow(cfg).run()

    assert "simulation" not in pr.result.stages
    assert not sim_getter.called
    assert pr.result.status == "PASS"


def test_results_json_shows_simulation_skipped_when_excluded_from_pipeline(tmp_path):
    import json
    from veriflow.workflows.project import ProjectWorkflow
    cfg = _full_project_config(
        tmp_path,
        "pipeline:\n  stages:\n    - type: connectivity\n    - type: synthesis\n",
    )
    with (
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend()),
        patch("veriflow.workflows.project.get_simulation_backend", return_value=_mock_sim_backend()),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend()),
    ):
        pr = ProjectWorkflow(cfg).run()

    data = json.loads((pr.run_dir / "results.json").read_text(encoding="utf-8"))
    assert data["stages"]["simulation"] == {"status": "SKIPPED", "log": None, "waves": None}
    assert data["stages"]["connectivity"]["status"] == "PASS"
    assert data["stages"]["synthesis"]["status"] == "PASS"


def test_build_project_flow_per_stage_backend_override(tmp_path):
    from veriflow.workflows.project import build_project_flow
    cfg = _full_project_config(
        tmp_path,
        "pipeline:\n  stages:\n    - type: synthesis\n      backend: yosys\n",
    )
    with patch("veriflow.workflows.project.get_synthesis_backend") as getter:
        build_project_flow(cfg)
    getter.assert_called_once_with("yosys")


# ── C. Database Mode config models ────────────────────────────────────────────


def test_database_project_config_pipeline_absent_is_none():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
    })
    assert cfg.pipeline is None


def test_database_project_config_pipeline_parsed():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
        "pipeline": {"stages": [{"type": "synthesis"}]},
    })
    assert [s.type for s in cfg.pipeline.stages] == ["synthesis"]


def test_database_tile_config_pipeline_absent_is_none():
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({})
    assert cfg.pipeline is None


def test_database_tile_config_pipeline_parsed():
    from veriflow.models.tile_config import TileConfig
    cfg = TileConfig.from_dict({"pipeline": {"stages": [{"type": "connectivity"}, {"type": "synthesis"}]}})
    assert [s.type for s in cfg.pipeline.stages] == ["connectivity", "synthesis"]


def test_database_project_config_unknown_stage_type_propagates():
    from veriflow.models.project_config import ProjectConfig
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectConfig.from_dict({
            "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
            "interface_name": None,
            "pipeline": {"stages": [{"type": "bogus"}]},
        })
    assert exc_info.value.code == "VF_PIPELINE_STAGE_UNKNOWN"


# ── D. DatabaseWorkflow.run_tile: tile > project > default inheritance ───────


def _make_db(tmp: Path) -> Path:
    db = tmp / "database"
    from veriflow.commands.init_db import cmd_init
    cmd_init(db)
    return db


def _fill_project_config(db: Path, *, interface_name="semicolab", pipeline_yaml: str = "") -> None:
    text = (
        f'id_prefix: "TST-01"\nproject_name: "Test"\nrepo: ""\n'
        f'interface_name: {interface_name!r}\ndescription: |\n\n' + pipeline_yaml
    )
    (db / "project_config.yaml").write_text(text, encoding="utf-8")


def _add_rtl(db: Path, tile_number_str: str, module_name: str = "top") -> None:
    rtl_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / f"{module_name}.v").write_text(f"module {module_name}; endmodule\n", encoding="utf-8")


def _fill_tile_config(db: Path, tile_number_str: str, *, module_name="top", pipeline_yaml: str = "") -> None:
    cfg_path = db / "config" / f"tile_{tile_number_str}" / "tile_config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    text = text.replace('top_module: ""', f'top_module: "{module_name}"')
    text += "\n" + pipeline_yaml
    cfg_path.write_text(text, encoding="utf-8")


def _setup_db(tmp: Path, *, project_pipeline_yaml="", tile_pipeline_yaml="") -> Path:
    from veriflow.commands.create_tile import cmd_create_tile
    db = _make_db(tmp)
    _fill_project_config(db, pipeline_yaml=project_pipeline_yaml)
    cmd_create_tile(db, top_module="top")
    _add_rtl(db, "0001")
    _fill_tile_config(db, "0001", pipeline_yaml=tile_pipeline_yaml)
    return db


@patch("veriflow.workflows.database.validate_tools")
@patch("veriflow.workflows.database.detect_iverilog_version", return_value="12.0")
@patch("veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
       return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}))
@patch("veriflow.core.backends.icarus.IcarusSimulationBackend.run_simulation", return_value=("COMPLETED", {}))
@patch("veriflow.core.backends.icarus.IcarusConnectivityBackend.run_connectivity", return_value="PASS")
class TestDatabasePipelineInheritance:
    def test_neither_set_runs_all_three(self, conn_mock, sim_mock, synth_mock, *_):
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(tmp)
            result = DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert result.data["stages"]["connectivity"]["status"] == "PASS"
            # Database Mode's raw results.json stores the simulation backend's
            # own status vocabulary ("COMPLETED"); PASS/FAIL normalization is a
            # display-layer concern (show-run/list-runs/db run), not applied
            # to the stored data -- see db_read.py's _status_markup.
            assert result.data["stages"]["simulation"]["status"] == "COMPLETED"
            assert result.data["stages"]["synthesis"]["status"] == "PASS"
            assert conn_mock.called and sim_mock.called and synth_mock.called
        finally:
            import shutil
            shutil.rmtree(tmp)

    def test_project_pipeline_used_when_tile_has_none(self, conn_mock, sim_mock, synth_mock, *_):
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(
                tmp,
                project_pipeline_yaml="pipeline:\n  stages:\n    - type: connectivity\n    - type: synthesis\n",
            )
            result = DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert result.data["stages"]["connectivity"]["status"] == "PASS"
            assert result.data["stages"]["simulation"]["status"] == "SKIPPED"
            assert result.data["stages"]["synthesis"]["status"] == "PASS"
            assert not sim_mock.called
        finally:
            import shutil
            shutil.rmtree(tmp)

    def test_tile_pipeline_overrides_project_pipeline(self, conn_mock, sim_mock, synth_mock, *_):
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(
                tmp,
                project_pipeline_yaml="pipeline:\n  stages:\n    - type: connectivity\n    - type: simulation\n    - type: synthesis\n",
                tile_pipeline_yaml="pipeline:\n  stages:\n    - type: synthesis\n",
            )
            result = DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert result.data["stages"]["connectivity"]["status"] == "SKIPPED"
            assert result.data["stages"]["simulation"]["status"] == "SKIPPED"
            assert result.data["stages"]["synthesis"]["status"] == "PASS"
            assert not conn_mock.called
            assert not sim_mock.called
            assert synth_mock.called
        finally:
            import shutil
            shutil.rmtree(tmp)

    def test_neither_set_matches_default_pipeline_behavior(self, conn_mock, sim_mock, synth_mock, *_):
        """Backward compatibility: no pipeline section anywhere -> identical
        to DEFAULT_PIPELINE (all three stages)."""
        from veriflow.workflows.database import DatabaseWorkflow, DatabaseRunOptions
        tmp = Path(tempfile.mkdtemp())
        try:
            db = _setup_db(tmp)
            result = DatabaseWorkflow(db).run_tile("0001", DatabaseRunOptions())
            assert result.data["status"] == "PASS"
            assert set(result.data["stages"].keys()) == {"connectivity", "simulation", "synthesis"}
        finally:
            import shutil
            shutil.rmtree(tmp)
