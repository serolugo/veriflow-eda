from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from veriflow.core.backends.registry import (
    get_connectivity_backend,
    get_simulation_backend,
    get_synthesis_backend,
)
from veriflow.core.run_id import get_next_run_id
from veriflow.core.stages.connectivity import InterfaceStage
from veriflow.core.stages.simulation import SimulationStage
from veriflow.core.stages.synthesis import SynthesisStage
from veriflow.framework import Design, Flow, RunRequest, RunResult
from veriflow.models.execution_profile import ExecutionProfile
from veriflow.models.interface_profile import get_interface_profile
from veriflow.workflows.project_config import ProjectWorkflowConfig


@dataclass
class ProjectRunResult:
    run_dir: Path
    result: RunResult


def build_project_flow(
    config: ProjectWorkflowConfig,
) -> tuple[Design, Flow]:
    design = Design(
        top_module=config.top_module,
        rtl_sources=config.rtl_sources,
        tb_sources=config.tb_sources,
    )

    profile = ExecutionProfile(
        connectivity_backend=config.execution.connectivity_backend,
        simulation_backend=config.execution.simulation_backend,
        synthesis_backend=config.execution.synthesis_backend,
        technology_name=config.technology.name,
    )

    stages = []

    if config.interface is not None:
        stages.append(
            InterfaceStage(
                interface_profile=get_interface_profile(config.interface.name),
                profile=profile,
                backend=get_connectivity_backend(profile.connectivity_backend),
            )
        )

    if config.tb_sources:
        stages.append(
            SimulationStage(
                tb_top=config.tb_top,
                profile=profile,
                backend=get_simulation_backend(profile.simulation_backend),
            )
        )

    stages.append(
        SynthesisStage(
            profile=profile,
            backend=get_synthesis_backend(profile.synthesis_backend),
        )
    )

    return design, Flow(stages)


class ProjectWorkflow:
    def __init__(
        self,
        config: ProjectWorkflowConfig,
    ) -> None:
        self.config = config

    @classmethod
    def from_file(
        cls,
        path: Path | str,
    ) -> "ProjectWorkflow":
        return cls(ProjectWorkflowConfig.from_file(path))

    def run(
        self,
        request: RunRequest | None = None,
    ) -> ProjectRunResult:
        design, flow = build_project_flow(self.config)

        if request is None:
            run_dir = self.config.runs_dir / get_next_run_id(self.config.runs_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
            request = RunRequest(work_dir=run_dir)
        else:
            run_dir = request.work_dir
            run_dir.mkdir(parents=True, exist_ok=True)

        result = flow.run(design, request)

        return ProjectRunResult(run_dir=run_dir, result=result)
