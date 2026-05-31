from __future__ import annotations

from veriflow.core import VeriFlowError
from veriflow.framework.design import Design
from veriflow.framework.request import RunRequest
from veriflow.framework.result import RunResult
from veriflow.framework.stage import Stage
from veriflow.framework.stage_input import StageInput
from veriflow.models.stage_context import ExecutionContext
from veriflow.models.stage_result import StageResult


class Flow:
    def __init__(self, stages: list[Stage]) -> None:
        seen: set[str] = set()
        for stage in stages:
            if stage.name in seen:
                raise VeriFlowError(
                    f"Duplicate stage name '{stage.name}' in Flow",
                    code="VF_FLOW_DUPLICATE_STAGE",
                )
            seen.add(stage.name)
        self.stages = stages

    def run(self, design: Design, request: RunRequest) -> RunResult:
        context = ExecutionContext(
            run_dir=request.work_dir,
            semicolab=request.semicolab,
            skip_connectivity=request.skip_connectivity,
            skip_sim=request.skip_sim,
            skip_synth=request.skip_synth,
        )

        stage_results: dict[str, StageResult] = {}
        for stage in self.stages:
            stage_input = StageInput(
                design=design,
                context=context,
                prior_results=dict(stage_results),
            )
            result = stage.run(stage_input)
            stage_results[stage.name] = result
            if result.status == "FAIL":
                break

        return RunResult.from_stages(stage_results)


__all__ = ["Flow"]
