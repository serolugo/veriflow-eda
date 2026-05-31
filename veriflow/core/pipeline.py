from __future__ import annotations

from veriflow.models.stage_context import StageContext
from veriflow.models.stage_result import StageResult


class PipelineStage:
    name: str

    def run(self, ctx: StageContext) -> StageResult:
        raise NotImplementedError


class PipelineRunner:
    def __init__(self, stages: list[PipelineStage]) -> None:
        self.stages = stages

    def run(self, ctx: StageContext) -> dict[str, StageResult]:
        results: dict[str, StageResult] = {}
        for stage in self.stages:
            results[stage.name] = stage.run(ctx)
        return results
