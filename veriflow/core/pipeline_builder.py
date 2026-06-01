from __future__ import annotations

from pathlib import Path

from veriflow.core.backends.registry import (
    get_connectivity_backend,
    get_simulation_backend,
    get_synthesis_backend,
)
from veriflow.core.pipeline import PipelineRunner
from veriflow.core.stages.connectivity import ConnectivityStage
from veriflow.core.stages.simulation import SimulationStage
from veriflow.core.stages.synthesis import SynthesisStage
from veriflow.framework.design import Design
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
    interface_profile: object | None = None,
) -> PipelineRunner:
    """Construct the fixed default pipeline: connectivity → simulation → synthesis.

    interface_profile is forwarded to ConnectivityStage.  tb_base_path and
    tb_tasks_path are forwarded to SimulationStage only (remaining simulation
    debt: Semicolab simulation still reads the mixed harness file).
    """
    p = profile or default_execution_profile()
    design = Design(
        top_module=top_module,
        rtl_sources=rtl_files,
        tb_sources=tb_files,
    )
    return PipelineRunner(
        stages=[
            ConnectivityStage(
                interface_profile=interface_profile,
                profile=p,
                backend=get_connectivity_backend(p.connectivity_backend),
            ),
            SimulationStage(
                tb_base_path=tb_base_path,
                tb_tasks_path=tb_tasks_path,
                profile=p,
                backend=get_simulation_backend(p.simulation_backend),
            ),
            SynthesisStage(
                profile=p,
                backend=get_synthesis_backend(p.synthesis_backend),
            ),
        ],
        design=design,
    )
