from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core import VeriFlowError
from veriflow.framework import RunRequest, RunResult
from veriflow.workflows import (
    ProjectExecutionConfig,
    ProjectInterfaceConfig,
    ProjectRunResult,
    ProjectTechnologyConfig,
    ProjectWorkflow,
    ProjectWorkflowConfig,
    build_project_flow,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "workflow.yaml"
    p.write_text(dedent(content), encoding="utf-8")
    return p


def _touch(root: Path, rel_path: str) -> Path:
    """Create an empty file at root/rel_path (parents included). Needed
    since ProjectWorkflowConfig.from_file() validates that every
    rtl_sources entry is a real file (VF_DESIGN_RTL_SOURCE_NOT_FILE)."""
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    return p


def _rtl_only_config(root: Path) -> ProjectWorkflowConfig:
    return ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "shift_mux",
                "rtl_sources": ["rtl/shift_mux.v"],
            },
        },
        root=root,
    )


def _mock_synth_backend():
    from veriflow.core.backends.base import SynthesisBackend
    b = MagicMock(spec=SynthesisBackend)
    b.run_synthesis.return_value = (
        "PASS",
        {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False},
    )
    return b


def _mock_conn_backend():
    from veriflow.core.backends.base import ConnectivityBackend
    b = MagicMock(spec=ConnectivityBackend)
    b.run_connectivity.return_value = "PASS"
    return b


def _mock_sim_backend():
    from veriflow.core.backends.base import SimulationBackend
    b = MagicMock(spec=SimulationBackend)
    b.run_simulation.return_value = ("COMPLETED", {})
    return b


# ── A. ProjectWorkflowConfig parsing ─────────────────────────────────────────

def test_config_minimal_rtl_only_parses(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    assert cfg.top_module == "shift_mux"
    assert cfg.rtl_sources == [tmp_path / "rtl" / "shift_mux.v"]
    assert cfg.tb_sources == []
    assert cfg.tb_top is None
    assert cfg.interface is None


def test_config_rtl_paths_resolved_relative_to_root(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v", "rtl/sub.v"],
            },
        },
        root=tmp_path,
    )
    assert cfg.rtl_sources == [
        tmp_path / "rtl" / "top.v",
        tmp_path / "rtl" / "sub.v",
    ]


def test_config_readme_template_omitted_resolves_to_none(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {"design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]}},
        root=tmp_path,
    )
    assert cfg.readme_template is None


def test_config_readme_template_null_resolves_to_none(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "readme_template": None,
        },
        root=tmp_path,
    )
    assert cfg.readme_template is None


def test_config_readme_template_resolved_relative_to_root(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "readme_template": "templates/custom_readme.j2",
        },
        root=tmp_path,
    )
    assert cfg.readme_template == (tmp_path / "templates" / "custom_readme.j2").resolve()


def test_config_readme_template_empty_string_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "readme_template": "   ",
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_README_TEMPLATE_INVALID"


def test_config_tb_paths_resolved_relative_to_root(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "simulation": {"tb_top": "tb"},
        },
        root=tmp_path,
    )
    assert cfg.tb_sources == [tmp_path / "tb" / "tb_top.v"]


def test_config_missing_top_module_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {"design": {"rtl_sources": ["rtl/top.v"]}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_DESIGN_TOP_REQUIRED"


def test_config_empty_top_module_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {"design": {"top_module": "   ", "rtl_sources": ["rtl/top.v"]}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_DESIGN_TOP_REQUIRED"


def test_config_missing_rtl_sources_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {"design": {"top_module": "top"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_DESIGN_RTL_REQUIRED"


def test_config_empty_rtl_sources_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {"design": {"top_module": "top", "rtl_sources": []}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_DESIGN_RTL_REQUIRED"


def test_config_tb_sources_without_tb_top_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {
                    "top_module": "top",
                    "rtl_sources": ["rtl/top.v"],
                    "tb_sources": ["tb/tb.v"],
                },
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_SIM_TB_TOP_REQUIRED"


def test_config_whitespace_tb_top_with_tb_sources_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {
                    "top_module": "top",
                    "rtl_sources": ["rtl/top.v"],
                    "tb_sources": ["tb/tb.v"],
                },
                "simulation": {"tb_top": "   "},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_SIM_TB_TOP_REQUIRED"


def test_config_interface_omitted_resolves_to_none(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    assert cfg.interface is None


def test_config_interface_null_section_resolves_to_none(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "interface": None,
        },
        root=tmp_path,
    )
    assert cfg.interface is None


def test_config_interface_name_null_resolves_to_none(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "interface": {"name": None},
        },
        root=tmp_path,
    )
    assert cfg.interface is None


def test_config_interface_name_semicolab_resolves(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "interface": {"name": "semicolab"},
        },
        root=tmp_path,
    )
    assert cfg.interface == ProjectInterfaceConfig(name="semicolab")
    assert cfg.interface.name == "semicolab"


def test_config_unknown_interface_name_raises(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": {"name": "nonexistent_iface"},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_UNKNOWN"


def test_config_interface_missing_name_key_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": {},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_NAME_REQUIRED"


def test_config_interface_empty_name_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": {"name": "   "},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_NAME_REQUIRED"


def test_config_interface_non_string_name_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": {"name": 123},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_NAME_REQUIRED"


def test_config_interface_non_mapping_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": "semicolab",
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_CONFIG_INVALID"


def test_config_interface_unknown_keys_fail(tmp_path):
    """Custom interface definitions are future work — extra keys are rejected."""
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": {"name": "semicolab", "ports": []},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_CONFIG_INVALID"


def test_config_legacy_flat_interface_name_rejected(tmp_path):
    """Top-level interface_name was never documented for Project Mode and is rejected."""
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface_name": "semicolab",
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_CONFIG_INVALID"


def test_config_both_flat_and_section_interface_rejected(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface_name": "semicolab",
                "interface": {"name": "semicolab"},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_CONFIG_INVALID"


def test_config_from_file_interface_section_parses(tmp_path):
    _touch(tmp_path, "rtl/shift_mux.v")
    p = _write_yaml(
        tmp_path,
        """\
        design:
          top_module: shift_mux
          rtl_sources:
            - rtl/shift_mux.v

        interface:
          name: semicolab
        """,
    )
    cfg = ProjectWorkflowConfig.from_file(p)
    assert cfg.interface == ProjectInterfaceConfig(name="semicolab")


def test_config_from_file_interface_null_parses_to_none(tmp_path):
    _touch(tmp_path, "rtl/shift_mux.v")
    p = _write_yaml(
        tmp_path,
        """\
        design:
          top_module: shift_mux
          rtl_sources:
            - rtl/shift_mux.v

        interface: null
        """,
    )
    cfg = ProjectWorkflowConfig.from_file(p)
    assert cfg.interface is None


def test_config_runs_dir_defaults_to_root_runs(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    assert cfg.runs_dir == tmp_path / "runs"


def test_config_runs_dir_configured_resolves_relative_to_root(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "output": {"runs_dir": "build/runs"},
        },
        root=tmp_path,
    )
    assert cfg.runs_dir == tmp_path / "build" / "runs"


def test_config_from_file_parses_yaml(tmp_path):
    p = _write_yaml(
        tmp_path,
        """\
        design:
          top_module: shift_mux
          rtl_sources:
            - rtl/shift_mux.v

        interface:
          name: semicolab

        simulation:
          tb_top: tb

        output:
          runs_dir: runs
        """,
    )
    # Add a tb source so tb_top is required
    _touch(tmp_path, "rtl/shift_mux.v")
    p2 = tmp_path / "workflow2.yaml"
    p2.write_text(
        dedent("""\
        design:
          top_module: shift_mux
          rtl_sources:
            - rtl/shift_mux.v
        output:
          runs_dir: runs
        """),
        encoding="utf-8",
    )
    cfg = ProjectWorkflowConfig.from_file(p2)
    assert cfg.top_module == "shift_mux"
    assert cfg.rtl_sources == [tmp_path / "rtl" / "shift_mux.v"]
    assert cfg.runs_dir == tmp_path / "runs"


# ── B. build_project_flow behavior ───────────────────────────────────────────

def test_flow_rtl_only_contains_only_synthesis(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    design, flow = build_project_flow(cfg)
    names = [s.name for s in flow.stages]
    assert names == ["synthesis"]


def test_flow_no_interface_stage_when_no_interface(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    _, flow = build_project_flow(cfg)
    assert not any(s.name == "connectivity" for s in flow.stages)


def test_flow_no_simulation_stage_when_no_tb_sources(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    _, flow = build_project_flow(cfg)
    assert not any(s.name == "simulation" for s in flow.stages)


def test_flow_semicolab_interface_includes_interface_stage_before_synthesis(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "interface": {"name": "semicolab"},
        },
        root=tmp_path,
    )
    _, flow = build_project_flow(cfg)
    names = [s.name for s in flow.stages]
    assert names == ["connectivity", "synthesis"]
    assert names.index("connectivity") < names.index("synthesis")


def test_flow_tb_config_includes_simulation_stage_before_synthesis(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "simulation": {"tb_top": "tb"},
        },
        root=tmp_path,
    )
    _, flow = build_project_flow(cfg)
    names = [s.name for s in flow.stages]
    assert names == ["simulation", "synthesis"]
    assert names.index("simulation") < names.index("synthesis")


def test_flow_full_config_stage_order(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "interface": {"name": "semicolab"},
            "simulation": {"tb_top": "tb"},
        },
        root=tmp_path,
    )
    _, flow = build_project_flow(cfg)
    names = [s.name for s in flow.stages]
    assert names == ["connectivity", "simulation", "synthesis"]


def test_flow_design_has_correct_top_module(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    design, _ = build_project_flow(cfg)
    assert design.top_module == "shift_mux"


def test_flow_design_has_correct_rtl_sources(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    design, _ = build_project_flow(cfg)
    assert design.rtl_sources == [tmp_path / "rtl" / "shift_mux.v"]


# ── C. ProjectWorkflow execution behavior ────────────────────────────────────

def test_workflow_from_file_loads_yaml(tmp_path):
    _touch(tmp_path, "rtl/my_top.v")
    p = _write_yaml(
        tmp_path,
        """\
        design:
          top_module: my_top
          rtl_sources:
            - rtl/my_top.v
        """,
    )
    wf = ProjectWorkflow.from_file(p)
    assert wf.config.top_module == "my_top"


def test_workflow_first_automatic_run_creates_run_001(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        wf = ProjectWorkflow(cfg)
        pr = wf.run()

    assert pr.run_dir == tmp_path / "runs" / "run-001"
    assert pr.run_dir.is_dir()


def test_workflow_second_automatic_run_creates_run_002(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        wf = ProjectWorkflow(cfg)
        wf.run()
        pr2 = wf.run()

    assert pr2.run_dir == tmp_path / "runs" / "run-002"
    assert pr2.run_dir.is_dir()


def test_workflow_non_run_nnn_dirs_ignored_during_allocation(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "backup").mkdir()
    (runs_dir / "run-old").mkdir()
    (runs_dir / "run-001").mkdir()
    cfg.runs_dir = runs_dir

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        wf = ProjectWorkflow(cfg)
        pr = wf.run()

    assert pr.run_dir == runs_dir / "run-002"


def test_workflow_explicit_request_work_dir_respected(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    explicit_dir = tmp_path / "my_run"

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        wf = ProjectWorkflow(cfg)
        req = RunRequest(work_dir=explicit_dir)
        pr = wf.run(request=req)

    assert pr.run_dir == explicit_dir
    assert explicit_dir.is_dir()


def test_workflow_explicit_request_not_numbered_under_runs_dir(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"
    explicit_dir = tmp_path / "custom_output"

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        wf = ProjectWorkflow(cfg)
        pr = wf.run(request=RunRequest(work_dir=explicit_dir))

    assert not (tmp_path / "runs").exists()
    assert pr.run_dir == explicit_dir


def test_workflow_skip_flags_preserved_in_explicit_request(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    run_dir = tmp_path / "run-001"

    wf = ProjectWorkflow(cfg)
    req = RunRequest(
        work_dir=run_dir,
        skip_connectivity=True,
        skip_sim=True,
        skip_synth=True,
    )
    with patch("veriflow.workflows.project.validate_tools"):
        pr = wf.run(request=req)

    # All stages skipped — synthesis result should be SKIPPED
    assert pr.result.stages["synthesis"].status == "SKIPPED"


def test_needed_tools_no_request_defaults_to_pipeline_only(tmp_path):
    from veriflow.workflows.project import _needed_tools

    cfg = _rtl_only_config(tmp_path)
    need_iverilog, need_yosys = _needed_tools(cfg)
    assert need_yosys is True


def test_needed_tools_skip_synth_request_does_not_need_yosys(tmp_path):
    """RunRequest.skip_synth=True must drop the yosys requirement even
    though synthesis is present in the pipeline -- same behavior as
    Database Mode's run_tile, which factors skip_* into its tool check."""
    from veriflow.workflows.project import _needed_tools

    cfg = _rtl_only_config(tmp_path)
    req = RunRequest(work_dir=tmp_path, skip_synth=True)
    need_iverilog, need_yosys = _needed_tools(cfg, req)
    assert need_yosys is False


def test_needed_tools_skip_check_request_does_not_need_iverilog_for_connectivity(tmp_path):
    """RunRequest.skip_connectivity=True must not require iverilog for
    connectivity checking (iverilog may still be needed for simulation,
    handled separately)."""
    from veriflow.workflows.project import _needed_tools

    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "shift_mux", "rtl_sources": ["rtl/shift_mux.v"]},
            "interface": {"name": "semicolab"},
        },
        root=tmp_path,
    )
    req = RunRequest(work_dir=tmp_path, skip_connectivity=True, skip_sim=True)
    need_iverilog, need_yosys = _needed_tools(cfg, req)
    assert need_iverilog is False


def test_needed_tools_all_skip_flags_need_no_tools(tmp_path):
    from veriflow.workflows.project import _needed_tools

    cfg = _rtl_only_config(tmp_path)
    req = RunRequest(work_dir=tmp_path, skip_connectivity=True, skip_sim=True, skip_synth=True)
    need_iverilog, need_yosys = _needed_tools(cfg, req)
    assert need_iverilog is False
    assert need_yosys is False


def test_workflow_skip_synth_request_calls_validate_tools_without_yosys(tmp_path):
    """End-to-end: ProjectWorkflow.run() with a connectivity-enabled config
    and RunRequest(skip_synth=True) must ask validate_tools for iverilog
    (connectivity still runs) but NOT yosys, even though synthesis is in
    the pipeline."""
    from veriflow.workflows.project import ProjectWorkflow

    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "shift_mux", "rtl_sources": ["rtl/shift_mux.v"]},
            "interface": {"name": "semicolab"},
        },
        root=tmp_path,
    )
    req = RunRequest(work_dir=tmp_path / "run-001", skip_synth=True)

    mock_backend = MagicMock()
    mock_backend.run_connectivity.return_value = "PASS"

    with (
        patch("veriflow.workflows.project.validate_tools") as mock_validate,
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=mock_backend),
    ):
        ProjectWorkflow(cfg).run(request=req)

    mock_validate.assert_called_once_with(need_iverilog=True, need_yosys=False)


def test_workflow_run_returns_project_run_result(tmp_path):
    cfg = _rtl_only_config(tmp_path)

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        wf = ProjectWorkflow(cfg)
        pr = wf.run()

    assert isinstance(pr, ProjectRunResult)
    assert isinstance(pr.result, RunResult)


def test_workflow_result_contains_underlying_run_result(tmp_path):
    """cfg is a synthesis-only generic project (no interface:, no
    tb_sources) -- connectivity/simulation never ran, so the overall
    status is "PARTIAL", not "PASS" (dev-docs/TRACEABILITY_AUDIT.md,
    Finding #4/#4b: "PASS" is reserved for a run where every configured
    stage type actually ran and passed)."""
    cfg = _rtl_only_config(tmp_path)

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        pr = ProjectWorkflow(cfg).run()

    assert pr.result.status == "PARTIAL"
    assert "synthesis" in pr.result.stages


def test_workflow_full_flow_from_empty_run_dir_succeeds(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "interface": {"name": "semicolab"},
            "simulation": {"tb_top": "tb"},
        },
        root=tmp_path,
    )
    cfg.runs_dir = tmp_path / "runs"

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_connectivity_backend",
            return_value=_mock_conn_backend(),
        ),
        patch(
            "veriflow.workflows.project.get_simulation_backend",
            return_value=_mock_sim_backend(),
        ),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        wf = ProjectWorkflow(cfg)
        run_dir = cfg.runs_dir / "run-001"
        # Verify the run directory doesn't exist yet — not pre-created by workflow
        assert not run_dir.exists()
        pr = wf.run()

    assert pr.result.status == "PASS"
    # run-001 created by the workflow
    assert pr.run_dir == run_dir
    assert run_dir.is_dir()
    # Stage artifact dirs created by stages, not pre-created by ProjectWorkflow
    assert (run_dir / "out" / "connectivity" / "logs").is_dir()
    assert (run_dir / "out" / "sim" / "logs").is_dir()
    assert (run_dir / "out" / "sim" / "waves").is_dir()
    assert (run_dir / "out" / "synth" / "logs").is_dir()


def test_workflow_full_config_result_stage_keys(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "interface": {"name": "semicolab"},
            "simulation": {"tb_top": "tb"},
        },
        root=tmp_path,
    )
    cfg.runs_dir = tmp_path / "runs"

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_connectivity_backend",
            return_value=_mock_conn_backend(),
        ),
        patch(
            "veriflow.workflows.project.get_simulation_backend",
            return_value=_mock_sim_backend(),
        ),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        pr = ProjectWorkflow(cfg).run()

    assert set(pr.result.stages.keys()) == {"connectivity", "simulation", "synthesis"}


def test_workflow_rtl_only_result_stage_keys(tmp_path):
    cfg = _rtl_only_config(tmp_path)

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
    ):
        pr = ProjectWorkflow(cfg).run()

    assert set(pr.result.stages.keys()) == {"synthesis"}


def test_workflow_project_does_not_pre_create_stage_artifact_dirs(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    runs_dir = tmp_path / "runs"
    cfg.runs_dir = runs_dir

    created_before_flow: list[Path] = []

    original_flow_run = __import__(
        "veriflow.framework.flow", fromlist=["Flow"]
    ).Flow.run

    def capturing_flow_run(self, design, request):
        # Capture what exists in run_dir before stages run
        run_dir = request.work_dir
        if run_dir.exists():
            created_before_flow.extend(list(run_dir.rglob("*")))
        return original_flow_run(self, design, request)

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ),
        patch(
            "veriflow.framework.flow.Flow.run",
            capturing_flow_run,
        ),
    ):
        ProjectWorkflow(cfg).run()

    # The run directory itself is the only thing created before stages run
    assert created_before_flow == []


# ── E. Execution / technology config parsing ─────────────────────────────────

def _base_design() -> dict:
    return {"design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]}}


def test_config_execution_omitted_uses_defaults(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    assert cfg.execution == ProjectExecutionConfig()
    assert cfg.execution.connectivity_backend == "icarus"
    assert cfg.execution.simulation_backend == "icarus"
    assert cfg.execution.synthesis_backend == "yosys"


def test_config_technology_omitted_defaults_to_generic(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    assert cfg.technology == ProjectTechnologyConfig(name="generic")


def test_config_execution_null_uses_defaults(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "execution": None},
        root=tmp_path,
    )
    assert cfg.execution == ProjectExecutionConfig()


def test_config_technology_null_defaults_to_generic(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "technology": None},
        root=tmp_path,
    )
    assert cfg.technology == ProjectTechnologyConfig(name="generic")


def test_config_execution_explicit_backends_load(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            **_base_design(),
            "execution": {
                "connectivity_backend": "icarus",
                "simulation_backend": "icarus",
                "synthesis_backend": "yosys",
            },
        },
        root=tmp_path,
    )
    assert cfg.execution == ProjectExecutionConfig(
        connectivity_backend="icarus",
        simulation_backend="icarus",
        synthesis_backend="yosys",
    )


def test_config_execution_partial_keys_use_defaults(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "execution": {"synthesis_backend": "yosys"}},
        root=tmp_path,
    )
    assert cfg.execution == ProjectExecutionConfig()


def test_config_execution_key_null_uses_default(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "execution": {"simulation_backend": None}},
        root=tmp_path,
    )
    assert cfg.execution.simulation_backend == "icarus"


def test_config_technology_generic_loads(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "technology": {"name": "generic"}},
        root=tmp_path,
    )
    assert cfg.technology == ProjectTechnologyConfig(name="generic")


def test_config_technology_empty_section_defaults_to_generic(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "technology": {}},
        root=tmp_path,
    )
    assert cfg.technology == ProjectTechnologyConfig(name="generic")


def test_config_technology_name_null_defaults_to_generic(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "technology": {"name": None}},
        root=tmp_path,
    )
    assert cfg.technology == ProjectTechnologyConfig(name="generic")


def test_config_execution_non_mapping_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "execution": "icarus"},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_EXECUTION_CONFIG_INVALID"


def test_config_technology_non_mapping_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "technology": "generic"},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_TECHNOLOGY_CONFIG_INVALID"


def test_config_execution_unknown_keys_fail(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "execution": {"simulation_tool": "vvp"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_EXECUTION_CONFIG_INVALID"


def test_config_technology_unknown_keys_fail(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "technology": {"name": "generic", "pdk": "sky130"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_TECHNOLOGY_CONFIG_INVALID"


def test_config_execution_non_string_backend_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "execution": {"synthesis_backend": 123}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_EXECUTION_CONFIG_INVALID"


def test_config_technology_non_string_name_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "technology": {"name": 130}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_TECHNOLOGY_CONFIG_INVALID"


# ── technology.require_pdk ────────────────────────────────────────────────────


def test_config_technology_require_pdk_true_parses(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "technology": {"name": "sky130", "require_pdk": True}},
        root=tmp_path,
    )
    assert cfg.technology.require_pdk is True
    assert cfg.technology.name == "sky130"


def test_config_technology_require_pdk_defaults_to_false(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "technology": {"name": "sky130"}},
        root=tmp_path,
    )
    assert cfg.technology.require_pdk is False


def test_config_technology_require_pdk_defaults_false_with_no_section(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(_base_design(), root=tmp_path)
    assert cfg.technology.require_pdk is False


def test_config_technology_require_pdk_non_bool_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "technology": {"name": "sky130", "require_pdk": "true"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_TECHNOLOGY_CONFIG_INVALID"


def test_config_unknown_connectivity_backend_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "execution": {"connectivity_backend": "verilator"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_BACKEND_CONNECTIVITY_UNKNOWN"


def test_config_unknown_simulation_backend_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "execution": {"simulation_backend": "verilator"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_BACKEND_SIMULATION_UNKNOWN"


def test_config_unknown_synthesis_backend_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "execution": {"synthesis_backend": "librelane"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_BACKEND_SYNTHESIS_UNKNOWN"


def test_config_unknown_technology_name_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {**_base_design(), "technology": {"name": "tsmc7"}},
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_config_from_file_execution_and_technology_parse(tmp_path):
    _touch(tmp_path, "rtl/shift_mux.v")
    p = _write_yaml(
        tmp_path,
        """\
        design:
          top_module: shift_mux
          rtl_sources:
            - rtl/shift_mux.v

        execution:
          connectivity_backend: icarus
          simulation_backend: icarus
          synthesis_backend: yosys

        technology:
          name: generic
        """,
    )
    cfg = ProjectWorkflowConfig.from_file(p)
    assert cfg.execution == ProjectExecutionConfig()
    assert cfg.technology == ProjectTechnologyConfig(name="generic")


def test_config_from_file_execution_null_parses_to_defaults(tmp_path):
    _touch(tmp_path, "rtl/shift_mux.v")
    p = _write_yaml(
        tmp_path,
        """\
        design:
          top_module: shift_mux
          rtl_sources:
            - rtl/shift_mux.v

        execution: null
        technology: null
        """,
    )
    cfg = ProjectWorkflowConfig.from_file(p)
    assert cfg.execution == ProjectExecutionConfig()
    assert cfg.technology == ProjectTechnologyConfig(name="generic")


# ── F. Execution / technology flow wiring ────────────────────────────────────

def test_flow_passes_configured_connectivity_backend_to_interface_stage(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            **_base_design(),
            "interface": {"name": "semicolab"},
            "execution": {"connectivity_backend": "icarus"},
        },
        root=tmp_path,
    )
    mock_be = _mock_conn_backend()
    with patch(
        "veriflow.workflows.project.get_connectivity_backend",
        return_value=mock_be,
    ) as getter:
        _, flow = build_project_flow(cfg)

    getter.assert_called_once_with("icarus")
    stage = next(s for s in flow.stages if s.name == "connectivity")
    assert stage._backend is mock_be


def test_flow_passes_configured_simulation_backend_to_simulation_stage(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "simulation": {"tb_top": "tb"},
            "execution": {"simulation_backend": "icarus"},
        },
        root=tmp_path,
    )
    mock_be = _mock_sim_backend()
    with patch(
        "veriflow.workflows.project.get_simulation_backend",
        return_value=mock_be,
    ) as getter:
        _, flow = build_project_flow(cfg)

    getter.assert_called_once_with("icarus")
    stage = next(s for s in flow.stages if s.name == "simulation")
    assert stage._backend is mock_be


def test_flow_passes_configured_synthesis_backend_and_technology(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {
            **_base_design(),
            "execution": {"synthesis_backend": "yosys"},
            "technology": {"name": "sky130"},
        },
        root=tmp_path,
    )
    mock_be = _mock_synth_backend()
    with patch(
        "veriflow.workflows.project.get_synthesis_backend",
        return_value=mock_be,
    ) as getter:
        _, flow = build_project_flow(cfg)

    getter.assert_called_once_with("yosys")
    stage = next(s for s in flow.stages if s.name == "synthesis")
    assert stage._backend is mock_be
    assert stage._profile.technology_name == "sky130"


def test_flow_default_config_uses_default_backends_and_profile(tmp_path):
    """With execution/technology omitted, the flow matches the current defaults."""
    from veriflow.core.backends.icarus import (
        IcarusConnectivityBackend,
        IcarusSimulationBackend,
    )
    from veriflow.core.backends.yosys import YosysSynthesisBackend
    from veriflow.models.execution_profile import default_execution_profile

    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "interface": {"name": "semicolab"},
            "simulation": {"tb_top": "tb"},
        },
        root=tmp_path,
    )
    _, flow = build_project_flow(cfg)
    by_name = {s.name: s for s in flow.stages}

    assert isinstance(by_name["connectivity"]._backend, IcarusConnectivityBackend)
    assert isinstance(by_name["simulation"]._backend, IcarusSimulationBackend)
    assert isinstance(by_name["synthesis"]._backend, YosysSynthesisBackend)
    for stage in flow.stages:
        assert stage._profile == default_execution_profile()


def test_flow_connectivity_backend_config_allowed_without_interface(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "execution": {"connectivity_backend": "icarus"}},
        root=tmp_path,
    )
    _, flow = build_project_flow(cfg)
    assert [s.name for s in flow.stages] == ["synthesis"]


def test_flow_simulation_backend_config_allowed_without_simulation(tmp_path):
    cfg = ProjectWorkflowConfig.from_dict(
        {**_base_design(), "execution": {"simulation_backend": "icarus"}},
        root=tmp_path,
    )
    _, flow = build_project_flow(cfg)
    assert [s.name for s in flow.stages] == ["synthesis"]


# ── D. Public API surface ─────────────────────────────────────────────────────

def test_public_exports_from_workflows():
    import veriflow.workflows as wf
    assert hasattr(wf, "ProjectWorkflowConfig")
    assert hasattr(wf, "ProjectInterfaceConfig")
    assert hasattr(wf, "ProjectExecutionConfig")
    assert hasattr(wf, "ProjectTechnologyConfig")
    assert hasattr(wf, "ProjectWorkflow")
    assert hasattr(wf, "ProjectRunResult")
    assert hasattr(wf, "build_project_flow")


def test_project_execution_config_is_frozen_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(ProjectExecutionConfig)
    cfg = ProjectExecutionConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.synthesis_backend = "other"


def test_project_technology_config_is_frozen_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(ProjectTechnologyConfig)
    cfg = ProjectTechnologyConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.name = "other"


def test_project_execution_config_empty_backend_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectExecutionConfig(simulation_backend="   ")
    assert exc_info.value.code == "VF_EXECUTION_CONFIG_INVALID"


def test_project_technology_config_empty_name_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectTechnologyConfig(name="   ")
    assert exc_info.value.code == "VF_TECHNOLOGY_CONFIG_INVALID"


def test_project_interface_config_is_frozen_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(ProjectInterfaceConfig)
    iface = ProjectInterfaceConfig(name="semicolab")
    with pytest.raises(dataclasses.FrozenInstanceError):
        iface.name = "other"


def test_project_interface_config_empty_name_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectInterfaceConfig(name="   ")
    assert exc_info.value.code == "VF_INTERFACE_NAME_REQUIRED"


def test_project_run_result_has_run_dir_and_result(tmp_path):
    from veriflow.framework import RunResult
    from veriflow.models.stage_result import StageResult
    rr = RunResult.from_stages({"s": StageResult(name="s", status="PASS")})
    pr = ProjectRunResult(run_dir=tmp_path, result=rr)
    assert pr.run_dir == tmp_path
    assert pr.result is rr


def test_project_workflow_config_is_dataclass(tmp_path):
    import dataclasses
    assert dataclasses.is_dataclass(ProjectWorkflowConfig)


def test_project_run_result_is_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(ProjectRunResult)


# ── G. Regression: rtl_sources resolved to absolute regardless of cwd ─────────

def test_from_file_rtl_sources_are_absolute_when_cwd_differs(tmp_path, monkeypatch):
    """from_file must produce absolute rtl_sources even when cwd != config dir.

    Regression for the smoke-test bug where yosys received a relative path
    and failed with "File 'counter8.v' not found" when the tool was invoked
    from a directory other than the one containing veriflow.yaml.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _touch(project_dir, "counter8.v")
    config = project_dir / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: counter8\n  rtl_sources:\n    - counter8.v\n",
        encoding="utf-8",
    )

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    cfg = ProjectWorkflowConfig.from_file(config)

    assert all(p.is_absolute() for p in cfg.rtl_sources), (
        "rtl_sources must be absolute regardless of the calling process's cwd"
    )
    assert cfg.rtl_sources == [project_dir / "counter8.v"]


def test_from_file_relative_config_path_rtl_sources_are_absolute(tmp_path, monkeypatch):
    """from_file resolves a relative config path before deriving rtl_sources.

    Covers the default CLI invocation: `veriflow project run` (no --config)
    resolves to 'veriflow.yaml' relative to cwd.  rtl_sources must still
    be absolute so backends never receive a bare filename like 'counter8.v'.
    """
    _touch(tmp_path, "counter8.v")
    config = tmp_path / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: counter8\n  rtl_sources:\n    - counter8.v\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    cfg = ProjectWorkflowConfig.from_file(Path("veriflow.yaml"))

    assert all(p.is_absolute() for p in cfg.rtl_sources)
    assert cfg.rtl_sources == [tmp_path / "counter8.v"]


def test_from_file_runs_dir_is_absolute_when_cwd_differs(tmp_path, monkeypatch):
    """runs_dir derived from config must also be absolute after the fix."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _touch(project_dir, "top.v")
    config = project_dir / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - top.v\n",
        encoding="utf-8",
    )

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    cfg = ProjectWorkflowConfig.from_file(config)

    assert cfg.runs_dir.is_absolute()
    assert cfg.runs_dir == project_dir / "runs"


def test_workflow_synth_backend_receives_absolute_rtl_paths(tmp_path, monkeypatch):
    """SynthesisStage must pass absolute paths to the backend, not bare filenames.

    This is the direct regression test: the backend's run_synthesis call must
    receive absolute Path objects so that yosys (or any other backend) can find
    the files without depending on the process's cwd at execution time.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _touch(project_dir, "counter8.v")
    config = project_dir / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: counter8\n  rtl_sources:\n    - counter8.v\n",
        encoding="utf-8",
    )

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    from unittest.mock import MagicMock
    from veriflow.core.backends.base import SynthesisBackend

    mock_be = MagicMock(spec=SynthesisBackend)
    mock_be.run_synthesis.return_value = (
        "PASS",
        {"cells": "3", "warnings": "0", "errors": "0", "has_latches": False},
    )

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=mock_be,
        ),
    ):
        wf = ProjectWorkflow.from_file(config)
        wf.run()

    call_kwargs = mock_be.run_synthesis.call_args
    rtl_files_received = call_kwargs.kwargs.get("rtl_files") or call_kwargs.args[0]
    assert all(p.is_absolute() for p in rtl_files_received), (
        "Backend received relative paths; yosys would fail with 'file not found' "
        "when cwd does not match the config directory"
    )


# ── H. from_file() validates rtl_sources entries are real files (2026-07-20) ──


def test_from_file_rtl_sources_directory_raises(tmp_path):
    """The exact reported scaffold bug: rtl_sources pointing at a directory
    (not a file) must raise a clean VeriFlowError, not silently proceed
    into a raw iverilog/yosys 'is a directory' crash deep in the pipeline."""
    (tmp_path / "src").mkdir()
    config = tmp_path / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - src\n",
        encoding="utf-8",
    )

    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_file(config)
    assert exc_info.value.code == "VF_DESIGN_RTL_SOURCE_NOT_FILE"
    assert "src" in str(exc_info.value)


def test_from_file_rtl_sources_missing_file_raises(tmp_path):
    config = tmp_path / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - rtl/does_not_exist.v\n",
        encoding="utf-8",
    )

    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_file(config)
    assert exc_info.value.code == "VF_DESIGN_RTL_SOURCE_NOT_FILE"


def test_from_file_rtl_sources_real_file_passes(tmp_path):
    _touch(tmp_path, "rtl/top.v")
    config = tmp_path / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - rtl/top.v\n",
        encoding="utf-8",
    )

    cfg = ProjectWorkflowConfig.from_file(config)
    assert cfg.rtl_sources == [tmp_path / "rtl" / "top.v"]


def test_from_dict_does_not_validate_rtl_sources(tmp_path):
    """from_dict() is exercised directly by many other tests with synthetic
    (never-written) rtl_sources paths -- it must not validate file
    existence; only from_file() does."""
    cfg = ProjectWorkflowConfig.from_dict(
        {"design": {"top_module": "top", "rtl_sources": ["rtl/does_not_exist.v"]}},
        root=tmp_path,
    )
    assert cfg.rtl_sources == [tmp_path / "rtl" / "does_not_exist.v"]


def test_from_file_validate_rtl_sources_false_skips_check(tmp_path):
    """Opt-out used internally by project_import()/generate_readme(),
    neither of which reads rtl_sources -- confirms the flag actually works
    end to end through from_file(), not just from_dict()."""
    config = tmp_path / "veriflow.yaml"
    config.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - rtl/does_not_exist.v\n",
        encoding="utf-8",
    )

    cfg = ProjectWorkflowConfig.from_file(config, validate_rtl_sources=False)
    assert cfg.rtl_sources == [tmp_path / "rtl" / "does_not_exist.v"]


# ── H. Regression: missing config file raises VeriFlowError, not FileNotFoundError

def test_from_file_missing_config_raises_veriflow_error(tmp_path):
    """from_file must raise VeriFlowError, not a raw FileNotFoundError."""
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_file(missing)
    assert exc_info.value.code == "VF_PROJECT_CONFIG_NOT_FOUND"


def test_from_file_missing_config_error_message_includes_path(tmp_path):
    """The error message must name the resolved path so the user knows what was searched."""
    missing = tmp_path / "no_config.yaml"
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_file(missing)
    assert str(missing.resolve()) in str(exc_info.value)


def test_from_file_missing_config_details_include_both_paths(tmp_path, monkeypatch):
    """details dict must carry both the resolved path and the original given path."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_file(Path("veriflow.yaml"))

    details = exc_info.value.details or {}
    assert "path" in details
    assert "path_given" in details
    assert details["path_given"] == "veriflow.yaml"


def test_workflow_from_file_missing_config_raises_veriflow_error(tmp_path):
    """ProjectWorkflow.from_file propagates VeriFlowError for a missing config."""
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflow.from_file(tmp_path / "missing.yaml")
    assert exc_info.value.code == "VF_PROJECT_CONFIG_NOT_FOUND"


# ── I. Regression: missing EDA tools raise VF_TOOL_NOT_FOUND, not FileNotFoundError

def test_workflow_run_missing_iverilog_raises_vf_tool_not_found(tmp_path):
    """A full-config project (interface + tb_sources) needs iverilog; a missing
    binary must surface as a clean VeriFlowError, not a raw subprocess crash."""
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "interface": {"name": "semicolab"},
            "simulation": {"tb_top": "tb"},
        },
        root=tmp_path,
    )
    cfg.runs_dir = tmp_path / "runs"

    with patch(
        "veriflow.core.validator.shutil.which",
        side_effect=lambda tool: None if tool == "iverilog" else "/usr/bin/yosys",
    ):
        with pytest.raises(VeriFlowError) as exc_info:
            ProjectWorkflow(cfg).run()

    assert exc_info.value.code == "VF_TOOL_NOT_FOUND"
    assert exc_info.value.details["tool"] == "iverilog"


def test_workflow_run_missing_yosys_raises_vf_tool_not_found(tmp_path):
    """Synthesis is unconditionally in the default pipeline; a missing yosys
    binary must surface as a clean VeriFlowError, not a raw subprocess crash."""
    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"

    with patch("veriflow.core.validator.shutil.which", return_value=None):
        with pytest.raises(VeriFlowError) as exc_info:
            ProjectWorkflow(cfg).run()

    assert exc_info.value.code == "VF_TOOL_NOT_FOUND"
    assert exc_info.value.details["tool"] == "yosys"


def test_workflow_run_synthesis_only_pipeline_does_not_check_iverilog(tmp_path):
    """A pipeline listing only 'synthesis' must validate yosys but never ask
    for iverilog, even though it's still installed/available on this machine."""
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "pipeline": {"stages": [{"type": "synthesis"}]},
        },
        root=tmp_path,
    )
    cfg.runs_dir = tmp_path / "runs"

    with patch("veriflow.workflows.project.validate_tools") as mock_validate:
        with patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ):
            ProjectWorkflow(cfg).run()

    mock_validate.assert_called_once_with(need_iverilog=False, need_yosys=True)


def test_workflow_run_default_pipeline_rtl_only_does_not_require_iverilog(tmp_path):
    """DEFAULT_PIPELINE lists connectivity+simulation+synthesis, but a bare
    rtl-only config (no interface, no tb_sources) never actually runs
    connectivity/simulation -- iverilog must not be required in that case."""
    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"

    with patch("veriflow.workflows.project.validate_tools") as mock_validate:
        with patch(
            "veriflow.workflows.project.get_synthesis_backend",
            return_value=_mock_synth_backend(),
        ):
            ProjectWorkflow(cfg).run()

    mock_validate.assert_called_once_with(need_iverilog=False, need_yosys=True)


def test_workflow_run_validates_tools_before_building_flow(tmp_path):
    """validate_tools must run before any backend/stage is touched -- patch
    get_synthesis_backend to blow up if called, and confirm the VeriFlowError
    from validate_tools is what actually propagates."""
    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"

    with (
        patch("veriflow.workflows.project.validate_tools", side_effect=VeriFlowError(
            "Tool not found in PATH: yosys", code="VF_TOOL_NOT_FOUND", details={"tool": "yosys"},
        )),
        patch("veriflow.workflows.project.get_synthesis_backend") as mock_get_backend,
    ):
        with pytest.raises(VeriFlowError) as exc_info:
            ProjectWorkflow(cfg).run()

    assert exc_info.value.code == "VF_TOOL_NOT_FOUND"
    mock_get_backend.assert_not_called()
