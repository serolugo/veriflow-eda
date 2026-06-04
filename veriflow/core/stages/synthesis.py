from __future__ import annotations

from veriflow.core.backends.base import SynthesisBackend
from veriflow.core.backends.yosys import YosysSynthesisBackend
from veriflow.core.pipeline import PipelineStage
from veriflow.framework.stage_input import StageInput
from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
from veriflow.models.stage_result import StageResult


class SynthesisStage(PipelineStage):
    name = "synthesis"

    def __init__(
        self,
        profile: ExecutionProfile | None = None,
        backend: SynthesisBackend | None = None,
    ) -> None:
        self._profile = profile or default_execution_profile()
        self._backend = backend or YosysSynthesisBackend()

    def run(self, input: StageInput) -> StageResult:
        design = input.design
        ctx = input.context
        tool = self._profile.synthesis_tool
        if ctx.skip_synth:
            return StageResult(name=self.name, status="SKIPPED", tool=tool)

        synth_log_path = ctx.synth_dir / "logs" / "synth.log"
        synth_log_path.parent.mkdir(parents=True, exist_ok=True)
        status, parsed = self._backend.run_synthesis(
            rtl_files=design.rtl_sources,
            top_module=design.top_module,
            synth_log_path=synth_log_path,
        )

        log_rel = ctx.log_rel(synth_log_path)

        metrics = {
            "cells": parsed.get("cells", ""),
            "warnings": parsed.get("warnings", "0"),
            "errors": parsed.get("errors", "0"),
            "has_latches": parsed.get("has_latches", False),
        }

        return StageResult(
            name=self.name,
            status=status,
            tool=tool,
            log_paths=[log_rel] if synth_log_path.exists() else None,
            metrics=metrics,
        )
