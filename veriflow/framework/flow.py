from __future__ import annotations

from veriflow.core import VeriFlowError
from veriflow.framework.request import RunRequest
from veriflow.framework.result import RunResult
from veriflow.framework.stage import Stage
from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult


class FlowDefinition:
    def __init__(self, stages: list[Stage]) -> None:
        seen: set[str] = set()
        for stage in stages:
            if stage.name in seen:
                raise VeriFlowError(
                    f"Duplicate stage name '{stage.name}' in FlowDefinition",
                    code="VF_FLOW_DUPLICATE_STAGE",
                )
            seen.add(stage.name)
        self.stages = stages

    def run(self, request: RunRequest) -> RunResult:
        ctx = RunContext(
            tile_id="framework-run",
            run_id="run-001",
            tile_dir=request.work_dir,
            run_dir=request.work_dir,
            semicolab=request.semicolab,
            skip_connectivity=request.skip_connectivity,
            skip_sim=request.skip_sim,
            skip_synth=request.skip_synth,
        )

        collected: dict[str, StageResult] = {}
        for stage in self.stages:
            result = stage.run(ctx)
            collected[stage.name] = result
            if result.status == "FAIL":
                break

        return RunResult.from_stages(collected)


__all__ = ["FlowDefinition"]
