from __future__ import annotations

from pathlib import Path

from veriflow.core.pipeline import PipelineRunner
from veriflow.core.stages.connectivity import ConnectivityStage
from veriflow.core.stages.simulation import SimulationStage
from veriflow.core.stages.synthesis import SynthesisStage


def build_default_pipeline(
    *,
    rtl_files: list[Path],
    tb_files: list[Path],
    tb_base_path: Path | None,
    tb_tasks_path: Path | None,
    top_module: str,
    has_tb: bool,
) -> PipelineRunner:
    """Construct the fixed default pipeline: connectivity → simulation → synthesis."""
    return PipelineRunner([
        ConnectivityStage(
            rtl_files=rtl_files,
            tb_base_path=tb_base_path,
            tb_tasks_path=tb_tasks_path,
            top_module=top_module,
        ),
        SimulationStage(
            rtl_files=rtl_files,
            tb_files=tb_files,
            tb_base_path=tb_base_path,
            tb_tasks_path=tb_tasks_path,
            top_module=top_module,
            has_tb=has_tb,
        ),
        SynthesisStage(
            rtl_files=rtl_files,
            top_module=top_module,
        ),
    ])
