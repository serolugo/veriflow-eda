from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core import VeriFlowError
from veriflow.framework import RunRequest, RunResult
from veriflow.workflows import (
    ProjectInterfaceConfig,
    ProjectRunResult,
    ProjectWorkflow,
    ProjectWorkflowConfig,
    build_project_flow,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "workflow.yaml"
    p.write_text(dedent(content), encoding="utf-8")
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

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
    ):
        wf = ProjectWorkflow(cfg)
        pr = wf.run()

    assert pr.run_dir == tmp_path / "runs" / "run-001"
    assert pr.run_dir.is_dir()


def test_workflow_second_automatic_run_creates_run_002(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
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

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
    ):
        wf = ProjectWorkflow(cfg)
        pr = wf.run()

    assert pr.run_dir == runs_dir / "run-002"


def test_workflow_explicit_request_work_dir_respected(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    explicit_dir = tmp_path / "my_run"

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
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

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
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
    pr = wf.run(request=req)

    # All stages skipped — synthesis result should be SKIPPED
    assert pr.result.stages["synthesis"].status == "SKIPPED"


def test_workflow_run_returns_project_run_result(tmp_path):
    cfg = _rtl_only_config(tmp_path)

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
    ):
        wf = ProjectWorkflow(cfg)
        pr = wf.run()

    assert isinstance(pr, ProjectRunResult)
    assert isinstance(pr.result, RunResult)


def test_workflow_result_contains_underlying_run_result(tmp_path):
    cfg = _rtl_only_config(tmp_path)

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
    ):
        pr = ProjectWorkflow(cfg).run()

    assert pr.result.status == "PASS"
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
        patch(
            "veriflow.core.stages.connectivity.IcarusConnectivityBackend",
            return_value=_mock_conn_backend(),
        ),
        patch(
            "veriflow.core.stages.simulation.IcarusSimulationBackend",
            return_value=_mock_sim_backend(),
        ),
        patch(
            "veriflow.core.stages.synthesis.YosysSynthesisBackend",
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
        patch(
            "veriflow.core.stages.connectivity.IcarusConnectivityBackend",
            return_value=_mock_conn_backend(),
        ),
        patch(
            "veriflow.core.stages.simulation.IcarusSimulationBackend",
            return_value=_mock_sim_backend(),
        ),
        patch(
            "veriflow.core.stages.synthesis.YosysSynthesisBackend",
            return_value=_mock_synth_backend(),
        ),
    ):
        pr = ProjectWorkflow(cfg).run()

    assert set(pr.result.stages.keys()) == {"connectivity", "simulation", "synthesis"}


def test_workflow_rtl_only_result_stage_keys(tmp_path):
    cfg = _rtl_only_config(tmp_path)

    with patch(
        "veriflow.core.stages.synthesis.YosysSynthesisBackend",
        return_value=_mock_synth_backend(),
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
        patch(
            "veriflow.core.stages.synthesis.YosysSynthesisBackend",
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


# ── D. Public API surface ─────────────────────────────────────────────────────

def test_public_exports_from_workflows():
    import veriflow.workflows as wf
    assert hasattr(wf, "ProjectWorkflowConfig")
    assert hasattr(wf, "ProjectInterfaceConfig")
    assert hasattr(wf, "ProjectWorkflow")
    assert hasattr(wf, "ProjectRunResult")
    assert hasattr(wf, "build_project_flow")


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
