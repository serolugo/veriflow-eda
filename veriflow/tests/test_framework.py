from __future__ import annotations

from pathlib import Path

import pytest

from veriflow.core import VeriFlowError
from veriflow.core.pipeline import PipelineStage
from veriflow.framework import (
    FlowDefinition,
    RunRequest,
    RunResult,
    Stage,
    StageRegistry,
)
from veriflow.models.run_context import RunContext
from veriflow.models.stage_context import ExecutionContext, StageContext
from veriflow.models.stage_result import StageResult


# ── Stub stages ──────────────────────────────────────────────────────────────

class PassStage(Stage):
    name = "pass_stage"

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(name=self.name, status="PASS")


class FailStage(Stage):
    name = "fail_stage"

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(name=self.name, status="FAIL")


class RecordingStage(Stage):
    """Records the context it was called with."""
    name = "recording_stage"

    def __init__(self) -> None:
        self.received_ctx: StageContext | None = None

    def run(self, ctx: StageContext) -> StageResult:
        self.received_ctx = ctx
        return StageResult(name=self.name, status="PASS")


class PassStage2(Stage):
    name = "pass_stage_2"

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(name=self.name, status="PASS")


class SkippedStage(Stage):
    name = "skipped_stage"

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(name=self.name, status="SKIPPED")


class LogRelStage(Stage):
    """Returns a log path computed via ctx.log_rel() for path-relativity checks."""
    name = "log_rel_stage"

    def run(self, ctx: StageContext) -> StageResult:
        log_path = ctx.synth_dir / "logs" / "synth.log"
        return StageResult(
            name=self.name,
            status="PASS",
            log_paths=[ctx.log_rel(log_path)],
        )


# ── Fixture: reset StageRegistry between tests ───────────────────────────────

@pytest.fixture(autouse=True)
def clear_registry():
    StageRegistry.clear()
    yield
    StageRegistry.clear()


# ── 1. Stage alias ────────────────────────────────────────────────────────────

def test_stage_is_pipeline_stage():
    assert Stage is PipelineStage


# ── 2. StageRegistry ─────────────────────────────────────────────────────────

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


# ── 3. RunRequest ─────────────────────────────────────────────────────────────

def test_run_request_defaults():
    req = RunRequest(top_module="my_mod", work_dir=Path("/tmp/work"))
    assert req.semicolab is False
    assert req.skip_connectivity is False
    assert req.skip_sim is False
    assert req.skip_synth is False


def test_run_request_normalizes_work_dir():
    req = RunRequest(top_module="my_mod", work_dir="/tmp/work")  # type: ignore[arg-type]
    assert isinstance(req.work_dir, Path)
    assert req.work_dir == Path("/tmp/work")


# ── 4. RunResult ──────────────────────────────────────────────────────────────

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


# ── 5. FlowDefinition ─────────────────────────────────────────────────────────

def test_flow_definition_runs_stub_stages(tmp_path):
    flow = FlowDefinition([PassStage(), PassStage2()])
    req = RunRequest(top_module="top", work_dir=tmp_path)
    result = flow.run(req)
    assert isinstance(result, RunResult)
    assert result.status == "PASS"
    assert len(result.stages) == 2
    assert "pass_stage" in result.stages
    assert "pass_stage_2" in result.stages


def test_flow_definition_early_exit_on_fail(tmp_path):
    never_called = RecordingStage()
    flow = FlowDefinition([FailStage(), never_called])
    req = RunRequest(top_module="top", work_dir=tmp_path)
    result = flow.run(req)
    assert result.status == "FAIL"
    assert "fail_stage" in result.stages
    # Stage after the FAIL must not have been reached
    assert "recording_stage" not in result.stages
    assert never_called.received_ctx is None


def test_flow_definition_propagates_skip_flags(tmp_path):
    recorder = RecordingStage()
    flow = FlowDefinition([recorder])
    req = RunRequest(
        top_module="top",
        work_dir=tmp_path,
        skip_connectivity=True,
        skip_sim=True,
        semicolab=True,
    )
    flow.run(req)
    ctx = recorder.received_ctx
    assert ctx is not None
    assert ctx.skip_connectivity is True
    assert ctx.skip_sim is True
    assert ctx.semicolab is True
    assert ctx.skip_synth is False


def test_flow_definition_work_dir_paths(tmp_path):
    recorder = RecordingStage()
    flow = FlowDefinition([recorder])
    req = RunRequest(top_module="top", work_dir=tmp_path)
    flow.run(req)
    ctx = recorder.received_ctx
    assert isinstance(ctx, ExecutionContext)
    assert ctx.run_dir == tmp_path
    # Derived paths should be inside work_dir
    assert ctx.sim_dir == tmp_path / "out" / "sim"
    assert ctx.synth_dir == tmp_path / "out" / "synth"
    assert ctx.impl_dir == tmp_path / "out" / "connectivity"


def test_flow_definition_empty_stages(tmp_path):
    flow = FlowDefinition([])
    result = flow.run(RunRequest(top_module="top", work_dir=tmp_path))
    assert result.status == "PASS"
    assert result.stages == {}


def test_flow_definition_skipped_stage_does_not_fail(tmp_path):
    flow = FlowDefinition([SkippedStage()])
    result = flow.run(RunRequest(top_module="top", work_dir=tmp_path))
    assert result.status == "PASS"


# ── 6. FlowDefinition duplicate stage guard ───────────────────────────────────

def test_flow_definition_rejects_duplicate_stage_names():
    with pytest.raises(VeriFlowError) as exc_info:
        FlowDefinition([PassStage(), PassStage()])
    assert exc_info.value.code == "VF_FLOW_DUPLICATE_STAGE"


def test_flow_definition_duplicate_error_includes_stage_name():
    with pytest.raises(VeriFlowError) as exc_info:
        FlowDefinition([PassStage(), PassStage()])
    assert "pass_stage" in str(exc_info.value)


def test_flow_definition_distinct_stage_names_allowed():
    flow = FlowDefinition([PassStage(), PassStage2()])
    assert len(flow.stages) == 2


# ── 7. FlowDefinition uses ExecutionContext ───────────────────────────────────

def test_flow_receives_execution_context(tmp_path):
    recorder = RecordingStage()
    FlowDefinition([recorder]).run(RunRequest(top_module="top", work_dir=tmp_path))
    assert isinstance(recorder.received_ctx, ExecutionContext)


def test_flow_context_has_no_database_identity(tmp_path):
    recorder = RecordingStage()
    FlowDefinition([recorder]).run(RunRequest(top_module="top", work_dir=tmp_path))
    ctx = recorder.received_ctx
    assert not hasattr(ctx, "tile_id")
    assert not hasattr(ctx, "run_id")
    assert not hasattr(ctx, "tile_dir")
    assert not hasattr(ctx, "db_path")


def test_flow_artifact_paths_are_run_relative(tmp_path):
    result = FlowDefinition([LogRelStage()]).run(
        RunRequest(top_module="top", work_dir=tmp_path)
    )
    log_path = result.stages["log_rel_stage"].log_paths[0]
    assert log_path == "out/synth/logs/synth.log"


def test_flow_definition_no_db_path(tmp_path):
    recorder = RecordingStage()
    FlowDefinition([recorder]).run(RunRequest(top_module="top", work_dir=tmp_path))
    assert isinstance(recorder.received_ctx, ExecutionContext)
    assert not hasattr(recorder.received_ctx, "db_path")


# ── 8. ExecutionContext ───────────────────────────────────────────────────────

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


# ── 9. RunContext database compatibility ──────────────────────────────────────

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
