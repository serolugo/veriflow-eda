from __future__ import annotations

from pathlib import Path

from veriflow.core.pipeline import PipelineStage
from veriflow.core.synth_runner import run_synthesis
from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult


class SynthesisStage(PipelineStage):
    name = "synthesis"

    def __init__(self, rtl_files: list[Path], top_module: str) -> None:
        self.rtl_files = rtl_files
        self.top_module = top_module

    def run(self, ctx: RunContext) -> StageResult:
        if ctx.skip_synth:
            return StageResult(name=self.name, status="SKIPPED", tool="yosys")

        synth_log_path = ctx.synth_dir / "logs" / "synth.log"
        status, parsed = run_synthesis(
            rtl_files=self.rtl_files,
            top_module=self.top_module,
            synth_log_path=synth_log_path,
        )

        tiles_dir = ctx.db_path / "tiles"
        try:
            log_rel = "tiles/" + synth_log_path.relative_to(tiles_dir).as_posix()
        except ValueError:
            log_rel = synth_log_path.as_posix()

        metrics = {
            "cells": parsed.get("cells", ""),
            "warnings": parsed.get("warnings", "0"),
            "errors": parsed.get("errors", "0"),
            "has_latches": parsed.get("has_latches", False),
        }

        return StageResult(
            name=self.name,
            status=status,
            tool="yosys",
            log_paths=[log_rel] if synth_log_path.exists() else None,
            metrics=metrics,
        )
