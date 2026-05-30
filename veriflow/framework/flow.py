from __future__ import annotations

from veriflow.framework.request import RunRequest
from veriflow.framework.result import RunResult
from veriflow.framework.stage import Stage
from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult


class FlowDefinition:
    def __init__(self, stages: list[Stage]) -> None:
        self.stages = stages

    def run(self, request: RunRequest) -> RunResult:
        ctx = RunContext(
            db_path=request.work_dir,
            tile_id="framework-run",
            run_id="run-001",
            tile_dir=request.work_dir,
            run_dir=request.work_dir,
            tile_config_path=request.work_dir / "tile_config.yaml",
            project_config_path=request.work_dir / "project_config.yaml",
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
