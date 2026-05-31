from __future__ import annotations

from veriflow.framework.design import Design
from veriflow.framework.stage_input import StageInput
from veriflow.models.stage_context import StageContext
from veriflow.models.stage_result import StageResult


class PipelineStage:
    name: str

    def run(self, input: StageInput) -> StageResult:
        raise NotImplementedError


class PipelineRunner:
    def __init__(self, stages: list[PipelineStage], design: Design) -> None:
        self.stages = stages
        self.design = design

    def run(self, ctx: StageContext) -> dict[str, StageResult]:
        results: dict[str, StageResult] = {}
        for stage in self.stages:
            stage_input = StageInput(
                design=self.design,
                context=ctx,
                prior_results=dict(results),
            )
            results[stage.name] = stage.run(stage_input)
        return results
