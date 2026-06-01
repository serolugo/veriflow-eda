from __future__ import annotations

from pathlib import Path

import pytest

from veriflow.core import VeriFlowError
from veriflow.framework import (
    Design,
    Flow,
    RunRequest,
    RunResult,
    Stage,
    StageInput,
    StageRegistry,
)
from veriflow.models.run_context import RunContext
from veriflow.models.stage_context import ExecutionContext, StageContext
from veriflow.models.stage_result import StageResult


# ── Stub stages ──────────────────────────────────────────────────────────────

class PassStage:
    name = "pass_stage"

    def run(self, input: StageInput) -> StageResult:
        return StageResult(name=self.name, status="PASS")


class FailStage:
    name = "fail_stage"

    def run(self, input: StageInput) -> StageResult:
        return StageResult(name=self.name, status="FAIL")


class RecordingStage:
    """Records the StageInput it was called with."""
    name = "recording_stage"

    def __init__(self) -> None:
        self.received_input: StageInput | None = None

    def run(self, input: StageInput) -> StageResult:
        self.received_input = input
        return StageResult(name=self.name, status="PASS")


class NamedRecordingStage:
    """Configurable-name recording stage for multi-stage tests."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.received_input: StageInput | None = None

    def run(self, input: StageInput) -> StageResult:
        self.received_input = input
        return StageResult(name=self.name, status="PASS")


class PassStage2:
    name = "pass_stage_2"

    def run(self, input: StageInput) -> StageResult:
        return StageResult(name=self.name, status="PASS")


class SkippedStage:
    name = "skipped_stage"

    def run(self, input: StageInput) -> StageResult:
        return StageResult(name=self.name, status="SKIPPED")


class LogRelStage:
    """Returns a log path computed via context.log_rel() for path-relativity checks."""
    name = "log_rel_stage"

    def run(self, input: StageInput) -> StageResult:
        log_path = input.context.synth_dir / "logs" / "synth.log"
        return StageResult(
            name=self.name,
            status="PASS",
            log_paths=[input.context.log_rel(log_path)],
        )


class MutatingStage:
    """Mutates the prior_results dict it receives to probe isolation."""
    name = "mutating_stage"

    def run(self, input: StageInput) -> StageResult:
        input.prior_results["injected"] = StageResult(name="injected", status="PASS")
        return StageResult(name=self.name, status="PASS")


# ── Fixture: reset StageRegistry between tests ───────────────────────────────

@pytest.fixture(autouse=True)
def clear_registry():
    StageRegistry.clear()
    yield
    StageRegistry.clear()


# ── Helper ────────────────────────────────────────────────────────────────────

def _design() -> Design:
    return Design(top_module="top", rtl_sources=[Path("/nonexistent/top.v")])


# ── 0. Design ─────────────────────────────────────────────────────────────────

def test_design_constructs_with_path_inputs():
    d = Design(top_module="top", rtl_sources=[Path("/nonexistent/top.v")])
    assert d.top_module == "top"
    assert d.rtl_sources == [Path("/nonexistent/top.v")]


def test_design_normalizes_str_to_path():
    d = Design(top_module="top", rtl_sources=["/nonexistent/top.v"])  # type: ignore[list-item]
    assert isinstance(d.rtl_sources[0], Path)


def test_design_normalizes_str_tb_sources():
    d = Design(
        top_module="top",
        rtl_sources=[Path("/nonexistent/top.v")],
        tb_sources=["/nonexistent/tb.v"],  # type: ignore[list-item]
    )
    assert isinstance(d.tb_sources[0], Path)


def test_design_allows_empty_tb_sources():
    d = Design(top_module="top", rtl_sources=[Path("/nonexistent/top.v")])
    assert d.tb_sources == []


def test_design_rejects_empty_top_module():
    with pytest.raises(VeriFlowError) as exc_info:
        Design(top_module="", rtl_sources=[Path("/nonexistent/top.v")])
    assert exc_info.value.code == "VF_DESIGN_TOP_REQUIRED"


def test_design_rejects_whitespace_top_module():
    with pytest.raises(VeriFlowError) as exc_info:
        Design(top_module="   ", rtl_sources=[Path("/nonexistent/top.v")])
    assert exc_info.value.code == "VF_DESIGN_TOP_REQUIRED"


def test_design_rejects_empty_rtl_sources():
    with pytest.raises(VeriFlowError) as exc_info:
        Design(top_module="top", rtl_sources=[])
    assert exc_info.value.code == "VF_DESIGN_RTL_REQUIRED"


def test_design_does_not_require_files_to_exist():
    d = Design(top_module="top", rtl_sources=[Path("/definitely/does/not/exist.v")])
    assert d.rtl_sources[0] == Path("/definitely/does/not/exist.v")


def test_design_exported_from_framework():
    from veriflow.framework import Design as FrameworkDesign
    assert FrameworkDesign is Design


def test_design_has_no_tb_base_path():
    assert not hasattr(_design(), "tb_base_path")


def test_design_has_no_tb_tasks_path():
    assert not hasattr(_design(), "tb_tasks_path")


# ── 1. StageInput ─────────────────────────────────────────────────────────────

def test_stage_input_stores_design_context_prior_results(tmp_path):
    design = _design()
    ctx = ExecutionContext(run_dir=tmp_path)
    prior = {"a": StageResult(name="a", status="PASS")}
    si = StageInput(design=design, context=ctx, prior_results=prior)
    assert si.design is design
    assert si.context is ctx
    assert si.prior_results == prior


def test_stage_input_default_prior_results_is_empty(tmp_path):
    si = StageInput(design=_design(), context=ExecutionContext(run_dir=tmp_path))
    assert si.prior_results == {}


# ── 2. Stage (Protocol) ───────────────────────────────────────────────────────

def test_stage_is_not_pipeline_stage():
    from veriflow.core.pipeline import PipelineStage
    assert Stage is not PipelineStage


# ── 3. StageRegistry ─────────────────────────────────────────────────────────

def test_stage_registry_register_and_get():
    StageRegistry.register("pass_stage", PassStage)
    assert StageRegistry.get("pass_stage") is PassStage


def test_stage_registry_duplicate_raises():
    StageRegistry.register("pass_stage", PassStage)
    with pytest.raises(VeriFlowError) as exc_info:
        StageRegistry.register("pass_stage", PassStage)
    assert exc_info.value.code == "VF_STAGE_DUPLICATE"


def test_stage_registry_unknown_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        StageRegistry.get("nonexistent")
    assert exc_info.value.code == "VF_STAGE_UNKNOWN"


# ── 4. RunRequest ─────────────────────────────────────────────────────────────

def test_run_request_defaults():
    req = RunRequest(work_dir=Path("/tmp/work"))
    assert req.semicolab is False
    assert req.skip_connectivity is False
    assert req.skip_sim is False
    assert req.skip_synth is False


def test_run_request_normalizes_work_dir():
    req = RunRequest(work_dir="/tmp/work")  # type: ignore[arg-type]
    assert isinstance(req.work_dir, Path)
    assert req.work_dir == Path("/tmp/work")


def test_run_request_has_no_top_module():
    req = RunRequest(work_dir=Path("/tmp/work"))
    assert not hasattr(req, "top_module")


# ── 5. RunResult ──────────────────────────────────────────────────────────────

def test_run_result_to_dict():
    sr = StageResult(name="connectivity", status="PASS", tool="iverilog")
    rr = RunResult(status="PASS", stages={"connectivity": sr})
    d = rr.to_dict()
    assert d["status"] == "PASS"
    assert "connectivity" in d["stages"]
    assert d["stages"]["connectivity"]["status"] == "PASS"
    assert d["stages"]["connectivity"]["tool"] == "iverilog"


def test_run_result_from_stages_pass():
    stages = {
        "a": StageResult(name="a", status="PASS"),
        "b": StageResult(name="b", status="SKIPPED"),
    }
    rr = RunResult.from_stages(stages)
    assert rr.status == "PASS"


def test_run_result_from_stages_fail():
    stages = {
        "a": StageResult(name="a", status="PASS"),
        "b": StageResult(name="b", status="FAIL"),
    }
    rr = RunResult.from_stages(stages)
    assert rr.status == "FAIL"


def test_run_result_from_stages_completed_counts_as_pass():
    stages = {"sim": StageResult(name="sim", status="COMPLETED")}
    rr = RunResult.from_stages(stages)
    assert rr.status == "PASS"


# ── 6. Flow ───────────────────────────────────────────────────────────────────

def test_flow_executes_stages_using_stage_input(tmp_path):
    recorder = RecordingStage()
    Flow([recorder]).run(_design(), RunRequest(work_dir=tmp_path))
    assert recorder.received_input is not None
    assert isinstance(recorder.received_input, StageInput)


def test_flow_passes_same_design_to_each_stage(tmp_path):
    design = _design()
    first = NamedRecordingStage("first")
    second = NamedRecordingStage("second")
    Flow([first, second]).run(design, RunRequest(work_dir=tmp_path))
    assert first.received_input.design is design
    assert second.received_input.design is design


def test_flow_passes_execution_context_through_stage_input(tmp_path):
    recorder = RecordingStage()
    Flow([recorder]).run(_design(), RunRequest(work_dir=tmp_path))
    assert isinstance(recorder.received_input.context, ExecutionContext)


def test_flow_second_stage_receives_first_result_in_prior_results(tmp_path):
    first = NamedRecordingStage("first")
    second = NamedRecordingStage("second")
    Flow([first, second]).run(_design(), RunRequest(work_dir=tmp_path))
    assert "first" in second.received_input.prior_results
    assert second.received_input.prior_results["first"].status == "PASS"


def test_flow_first_stage_has_empty_prior_results(tmp_path):
    first = NamedRecordingStage("first")
    Flow([first]).run(_design(), RunRequest(work_dir=tmp_path))
    assert first.received_input.prior_results == {}


def test_flow_prior_results_isolation(tmp_path):
    mutator = MutatingStage()
    recorder = RecordingStage()
    Flow([mutator, recorder]).run(_design(), RunRequest(work_dir=tmp_path))
    assert "injected" not in recorder.received_input.prior_results
    assert "mutating_stage" in recorder.received_input.prior_results


def test_flow_runs_stub_stages(tmp_path):
    flow = Flow([PassStage(), PassStage2()])
    result = flow.run(_design(), RunRequest(work_dir=tmp_path))
    assert isinstance(result, RunResult)
    assert result.status == "PASS"
    assert len(result.stages) == 2
    assert "pass_stage" in result.stages
    assert "pass_stage_2" in result.stages


def test_flow_early_exit_on_fail(tmp_path):
    never_called = RecordingStage()
    flow = Flow([FailStage(), never_called])
    result = flow.run(_design(), RunRequest(work_dir=tmp_path))
    assert result.status == "FAIL"
    assert "fail_stage" in result.stages
    assert "recording_stage" not in result.stages
    assert never_called.received_input is None


def test_flow_propagates_skip_flags(tmp_path):
    recorder = RecordingStage()
    flow = Flow([recorder])
    req = RunRequest(
        work_dir=tmp_path,
        skip_connectivity=True,
        skip_sim=True,
        semicolab=True,
    )
    flow.run(_design(), req)
    ctx = recorder.received_input.context
    assert ctx.skip_connectivity is True
    assert ctx.skip_sim is True
    assert ctx.semicolab is True
    assert ctx.skip_synth is False


def test_flow_work_dir_paths(tmp_path):
    recorder = RecordingStage()
    Flow([recorder]).run(_design(), RunRequest(work_dir=tmp_path))
    ctx = recorder.received_input.context
    assert isinstance(ctx, ExecutionContext)
    assert ctx.run_dir == tmp_path
    assert ctx.sim_dir == tmp_path / "out" / "sim"
    assert ctx.synth_dir == tmp_path / "out" / "synth"
    assert ctx.impl_dir == tmp_path / "out" / "connectivity"


def test_flow_empty_stages(tmp_path):
    result = Flow([]).run(_design(), RunRequest(work_dir=tmp_path))
    assert result.status == "PASS"
    assert result.stages == {}


def test_flow_skipped_stage_does_not_fail(tmp_path):
    result = Flow([SkippedStage()]).run(_design(), RunRequest(work_dir=tmp_path))
    assert result.status == "PASS"


def test_flow_rejects_duplicate_stage_names():
    with pytest.raises(VeriFlowError) as exc_info:
        Flow([PassStage(), PassStage()])
    assert exc_info.value.code == "VF_FLOW_DUPLICATE_STAGE"


def test_flow_duplicate_error_includes_stage_name():
    with pytest.raises(VeriFlowError) as exc_info:
        Flow([PassStage(), PassStage()])
    assert "pass_stage" in str(exc_info.value)


def test_flow_distinct_stage_names_allowed():
    flow = Flow([PassStage(), PassStage2()])
    assert len(flow.stages) == 2


def test_flow_context_has_no_database_identity(tmp_path):
    recorder = RecordingStage()
    Flow([recorder]).run(_design(), RunRequest(work_dir=tmp_path))
    ctx = recorder.received_input.context
    assert not hasattr(ctx, "tile_id")
    assert not hasattr(ctx, "run_id")
    assert not hasattr(ctx, "tile_dir")
    assert not hasattr(ctx, "db_path")


def test_flow_artifact_paths_are_run_relative(tmp_path):
    result = Flow([LogRelStage()]).run(_design(), RunRequest(work_dir=tmp_path))
    log_path = result.stages["log_rel_stage"].log_paths[0]
    assert log_path == "out/synth/logs/synth.log"


# ── 7. ExecutionContext ───────────────────────────────────────────────────────

def test_execution_context_constructs_with_path(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path)
    assert ctx.run_dir == tmp_path


def test_execution_context_normalizes_str_run_dir(tmp_path):
    ctx = ExecutionContext(run_dir=str(tmp_path))  # type: ignore[arg-type]
    assert isinstance(ctx.run_dir, Path)
    assert ctx.run_dir == tmp_path


def test_execution_context_derives_out_dir(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path)
    assert ctx.out_dir == tmp_path / "out"


def test_execution_context_derives_impl_dir(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path)
    assert ctx.impl_dir == tmp_path / "out" / "connectivity"


def test_execution_context_derives_sim_dir(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path)
    assert ctx.sim_dir == tmp_path / "out" / "sim"


def test_execution_context_derives_synth_dir(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path)
    assert ctx.synth_dir == tmp_path / "out" / "synth"


def test_execution_context_log_rel_inside_run_dir(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path)
    inside = tmp_path / "out" / "synth" / "logs" / "synth.log"
    assert ctx.log_rel(inside) == "out/synth/logs/synth.log"


def test_execution_context_log_rel_outside_run_dir(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path / "subdir")
    outside = tmp_path / "other" / "file.log"
    assert ctx.log_rel(outside) == outside.as_posix()


def test_execution_context_defaults(tmp_path):
    ctx = ExecutionContext(run_dir=tmp_path)
    assert ctx.semicolab is False
    assert ctx.skip_connectivity is False
    assert ctx.skip_sim is False
    assert ctx.skip_synth is False


# ── 8. RunContext database compatibility ──────────────────────────────────────

def test_run_context_satisfies_stage_context_attributes(tmp_path):
    ctx = RunContext(
        tile_id="T", run_id="run-001",
        tile_dir=tmp_path,
        run_dir=tmp_path / "runs" / "run-001",
        semicolab=False,
        skip_connectivity=False,
        skip_sim=False,
        skip_synth=False,
    )
    assert hasattr(ctx, "run_dir")
    assert hasattr(ctx, "semicolab")
    assert hasattr(ctx, "skip_connectivity")
    assert hasattr(ctx, "skip_sim")
    assert hasattr(ctx, "skip_synth")
    assert hasattr(ctx, "out_dir")
    assert hasattr(ctx, "impl_dir")
    assert hasattr(ctx, "sim_dir")
    assert hasattr(ctx, "synth_dir")
    assert callable(ctx.log_rel)


def test_run_context_log_rel_without_db_path(tmp_path):
    ctx = RunContext(
        tile_id="X", run_id="run-001",
        tile_dir=tmp_path,
        run_dir=tmp_path / "runs" / "run-001",
        semicolab=False,
        skip_connectivity=False,
        skip_sim=False,
        skip_synth=False,
    )
    p = tmp_path / "some" / "path.log"
    assert ctx.log_rel(p) == p.as_posix()


def test_run_context_log_rel_with_db_path(tmp_path):
    db = tmp_path / "db"
    tile_dir = db / "tiles" / "T"
    run_dir = tile_dir / "runs" / "run-001"
    ctx = RunContext(
        tile_id="T", run_id="run-001",
        tile_dir=tile_dir,
        run_dir=run_dir,
        semicolab=False,
        skip_connectivity=False,
        skip_sim=False,
        skip_synth=False,
        db_path=db,
    )
    inside = db / "tiles" / "T" / "runs" / "run-001" / "out" / "synth" / "logs" / "synth.log"
    assert ctx.log_rel(inside) == "tiles/T/runs/run-001/out/synth/logs/synth.log"
    outside = tmp_path / "elsewhere" / "file.log"
    assert ctx.log_rel(outside) == outside.as_posix()


# ── 9. Public exports ─────────────────────────────────────────────────────────

def test_public_exports_include_flow_and_stage_input():
    import veriflow.framework as fw
    assert hasattr(fw, "Flow")
    assert hasattr(fw, "StageInput")


def test_public_exports_do_not_include_legacy_stage_adapter():
    import veriflow.framework as fw
    assert not hasattr(fw, "LegacyStageAdapter")


# ── 10. Flow with migrated built-in stages ───────────────────────────────────

def test_flow_runs_synthesis_stage_natively(tmp_path):
    from unittest.mock import MagicMock
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.core.backends.base import SynthesisBackend

    mock_backend = MagicMock(spec=SynthesisBackend)
    mock_backend.run_synthesis.return_value = (
        "PASS",
        {"cells": "7", "warnings": "0", "errors": "0", "has_latches": False},
    )
    stage = SynthesisStage(backend=mock_backend)
    design = Design(top_module="top", rtl_sources=[Path("/nonexistent/top.v")])

    result = Flow([stage]).run(design, RunRequest(work_dir=tmp_path, skip_synth=False))
    assert result.status == "PASS"
    assert "synthesis" in result.stages
    assert result.stages["synthesis"].status == "PASS"
    mock_backend.run_synthesis.assert_called_once()


def test_flow_runs_connectivity_stage_natively(tmp_path):
    from unittest.mock import MagicMock
    from veriflow.core.stages.connectivity import ConnectivityStage
    from veriflow.core.backends.base import ConnectivityBackend
    from veriflow.models.interface_profile import semicolab_interface_profile

    mock_backend = MagicMock(spec=ConnectivityBackend)
    mock_backend.run_connectivity.return_value = "PASS"
    profile = semicolab_interface_profile()
    stage = ConnectivityStage(interface_profile=profile, backend=mock_backend)
    design = Design(top_module="top", rtl_sources=[Path("/nonexistent/top.v")])

    result = Flow([stage]).run(
        design,
        RunRequest(work_dir=tmp_path, skip_connectivity=False, semicolab=True),
    )
    assert result.status == "PASS"
    mock_backend.run_connectivity.assert_called_once()
    call_kwargs = mock_backend.run_connectivity.call_args
    assert call_kwargs.kwargs["top_module"] == "top"
    assert call_kwargs.kwargs["interface_profile"] is profile


def test_flow_runs_simulation_stage_natively(tmp_path):
    from unittest.mock import MagicMock
    from veriflow.core.stages.simulation import SimulationStage
    from veriflow.core.backends.base import SimulationBackend

    mock_backend = MagicMock(spec=SimulationBackend)
    mock_backend.run_simulation.return_value = ("COMPLETED", {"sim_time": "5ns", "seed": "1"})
    stage = SimulationStage(tb_base_path=None, tb_tasks_path=None, backend=mock_backend)
    design = Design(
        top_module="top",
        rtl_sources=[Path("/nonexistent/top.v")],
        tb_sources=[Path("/nonexistent/tb.v")],
    )

    result = Flow([stage]).run(design, RunRequest(work_dir=tmp_path, skip_sim=False))
    assert result.status == "PASS"
    mock_backend.run_simulation.assert_called_once()


def test_flow_built_in_stages_receive_design_from_flow(tmp_path):
    """Built-in stages read RTL/top from StageInput.design, not their constructor."""
    from unittest.mock import MagicMock
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.core.backends.base import SynthesisBackend

    mock_backend = MagicMock(spec=SynthesisBackend)
    mock_backend.run_synthesis.return_value = (
        "PASS",
        {"cells": "2", "warnings": "0", "errors": "0", "has_latches": False},
    )
    # Constructor has no rtl_files or top_module
    stage = SynthesisStage(backend=mock_backend)

    rtl = Path("/nonexistent/specific.v")
    design = Design(top_module="specific_top", rtl_sources=[rtl])

    Flow([stage]).run(design, RunRequest(work_dir=tmp_path, skip_synth=False))

    call_kwargs = mock_backend.run_synthesis.call_args
    assert call_kwargs.kwargs["rtl_files"] == [rtl]
    assert call_kwargs.kwargs["top_module"] == "specific_top"
