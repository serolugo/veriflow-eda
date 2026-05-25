from __future__ import annotations

from pathlib import Path

from veriflow.core.pipeline import PipelineRunner
from veriflow.core.stages.connectivity import ConnectivityStage
from veriflow.core.stages.simulation import SimulationStage
from veriflow.core.stages.synthesis import SynthesisStage
from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile


def build_default_pipeline(
    *,
    rtl_files: list[Path],
    tb_files: list[Path],
    tb_base_path: Path | None,
    tb_tasks_path: Path | None,
    top_module: str,
    has_tb: bool,
    profile: ExecutionProfile | None = None,
) -> PipelineRunner:
    """Construct the fixed default pipeline: connectivity → simulation → synthesis."""
    p = profile or default_execution_profile()
    return PipelineRunner([
        ConnectivityStage(
            rtl_files=rtl_files,
            tb_base_path=tb_base_path,
            tb_tasks_path=tb_tasks_path,
            top_module=top_module,
            profile=p,
        ),
        SimulationStage(
            rtl_files=rtl_files,
            tb_files=tb_files,
            tb_base_path=tb_base_path,
            tb_tasks_path=tb_tasks_path,
            top_module=top_module,
            has_tb=has_tb,
            profile=p,
        ),
        SynthesisStage(
            rtl_files=rtl_files,
            top_module=top_module,
            profile=p,
        ),
    ])
