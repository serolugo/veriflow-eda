from __future__ import annotations

from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult


class PipelineStage:
    name: str

    def run(self, ctx: RunContext) -> StageResult:
        raise NotImplementedError
