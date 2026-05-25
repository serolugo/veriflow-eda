from __future__ import annotations

from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult


class PipelineStage:
    name: str

    def run(self, ctx: RunContext) -> StageResult:
        raise NotImplementedError


class PipelineRunner:
    def __init__(self, stages: list[PipelineStage]) -> None:
        self.stages = stages

    def run(self, ctx: RunContext) -> dict[str, StageResult]:
        results: dict[str, StageResult] = {}
        for stage in self.stages:
            results[stage.name] = stage.run(ctx)
        return results
