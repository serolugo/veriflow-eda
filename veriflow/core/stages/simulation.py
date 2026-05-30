from __future__ import annotations

from pathlib import Path

from veriflow.core.backends.base import SimulationBackend
from veriflow.core.backends.icarus import IcarusSimulationBackend
from veriflow.core.pipeline import PipelineStage
from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult


class SimulationStage(PipelineStage):
    name = "simulation"

    def __init__(
        self,
        rtl_files: list[Path],
        tb_files: list[Path],
        tb_base_path: Path | None,
        tb_tasks_path: Path | None,
        top_module: str,
        has_tb: bool,
        profile: ExecutionProfile | None = None,
        backend: SimulationBackend | None = None,
    ) -> None:
        self.rtl_files = rtl_files
        self.tb_files = tb_files
        self.tb_base_path = tb_base_path
        self.tb_tasks_path = tb_tasks_path
        self.top_module = top_module
        self.has_tb = has_tb
        self._profile = profile or default_execution_profile()
        self._backend = backend or IcarusSimulationBackend()

    def run(self, ctx: RunContext) -> StageResult:
        tool = self._profile.simulation_tool
        if ctx.skip_sim or not self.has_tb:
            return StageResult(name=self.name, status="SKIPPED", tool=tool)

        sim_log_path = ctx.sim_dir / "logs" / "sim.log"
        wave_path = ctx.sim_dir / "waves" / "waves.vcd"

        status, parsed = self._backend.run_simulation(
            rtl_files=self.rtl_files,
            tb_files=self.tb_files,
            tb_base_path=self.tb_base_path,
            tb_tasks_path=self.tb_tasks_path,
            top_module=self.top_module,
            sim_log_path=sim_log_path,
            wave_path=wave_path,
            semicolab=ctx.semicolab,
        )

        log_paths = [ctx.log_rel(sim_log_path)] if sim_log_path.exists() else None
        wave_files = [ctx.log_rel(wave_path)] if wave_path.exists() else None

        metrics: dict = {}
        if parsed.get("sim_time"):
            metrics["sim_time"] = parsed["sim_time"]
        if parsed.get("seed"):
            metrics["seed"] = parsed["seed"]

        return StageResult(
            name=self.name,
            status=status,
            tool=tool,
            log_paths=log_paths,
            artifacts={"wave": wave_files} if wave_files else None,
            metrics=metrics or None,
        )
