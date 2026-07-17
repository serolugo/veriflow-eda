from __future__ import annotations

from dataclasses import replace

from veriflow.core.backends.base import SynthesisBackend
from veriflow.core.backends.yosys import YosysSynthesisBackend
from veriflow.core.pipeline import PipelineStage
from veriflow.framework.stage_input import StageInput
from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
from veriflow.models.pdk_manager import get_installed_pdk_version, get_liberty_path
from veriflow.models.stage_result import StageResult
from veriflow.models.technology_profile import DEFAULT_TECHNOLOGY_NAME, get_technology_profile


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
        technology = get_technology_profile(self._profile.technology_name)

        stage_warnings: list[str] = []
        if technology.name != DEFAULT_TECHNOLOGY_NAME and not technology.liberty:
            # A named technology with no liberty already set (the common case --
            # none of the built-in technology.yaml files vendor one) falls back
            # to whatever `veriflow pdk install` has put on disk. Missing PDK is
            # a warning, not an error: synthesis still runs with generic mapping.
            liberty_path = get_liberty_path(technology.name)
            if liberty_path is not None:
                technology = replace(technology, liberty=str(liberty_path))
            else:
                stage_warnings.append(
                    f"PDK for {technology.name!r} not found -- run: veriflow pdk install {technology.name} "
                    "[VF_TECHNOLOGY_PDK_NOT_INSTALLED]"
                )

        # Traceability snapshot: only meaningful once synthesis is actually
        # PDK-mapped (liberty resolved above, either from an installed PDK
        # or an explicit technology.definition) -- "generic" and
        # missing-PDK-fallback runs report neither field, since there's no
        # specific PDK build to attribute the run to.
        technology_field: str | None = None
        technology_version_field: str | None = None
        if technology.name != DEFAULT_TECHNOLOGY_NAME and technology.liberty:
            technology_field = technology.name
            technology_version_field = get_installed_pdk_version(technology.name)

        status, parsed = self._backend.run_synthesis(
            rtl_files=design.rtl_sources,
            top_module=design.top_module,
            synth_log_path=synth_log_path,
            technology=technology,
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
            warnings=stage_warnings or None,
            technology=technology_field,
            technology_version=technology_version_field,
        )
