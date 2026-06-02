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
    tb_top: str,
    top_module: str,
    profile: ExecutionProfile | None = None,
    interface_profile: object | None = None,
) -> PipelineRunner:
    """Construct the fixed default pipeline: connectivity → simulation → synthesis.

    interface_profile is forwarded to ConnectivityStage.  tb_top selects the
    testbench top module for SimulationStage and is required to be non-empty.
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
                tb_top=tb_top,
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
