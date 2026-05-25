from __future__ import annotations

from pathlib import Path

from veriflow.core.pipeline import PipelineStage
from veriflow.core.sim_runner import run_connectivity_check
from veriflow.models.run_context import RunContext
from veriflow.models.stage_result import StageResult


class ConnectivityStage(PipelineStage):
    name = "connectivity"

    def __init__(
        self,
        rtl_files: list[Path],
        tb_base_path: Path | None,
        tb_tasks_path: Path | None,
        top_module: str,
    ) -> None:
        self.rtl_files = rtl_files
        self.tb_base_path = tb_base_path
        self.tb_tasks_path = tb_tasks_path
        self.top_module = top_module

    def run(self, ctx: RunContext) -> StageResult:
        if ctx.skip_connectivity:
            return StageResult(name=self.name, status="SKIPPED", tool="iverilog")

        conn_log_path = ctx.impl_dir / "logs" / "connectivity.log"
        status = run_connectivity_check(
            rtl_files=self.rtl_files,
            tb_base_path=self.tb_base_path,
            tb_tasks_path=self.tb_tasks_path,
            top_module=self.top_module,
            log_path=conn_log_path,
        )

        tiles_dir = ctx.db_path / "tiles"
        try:
            log_rel = "tiles/" + conn_log_path.relative_to(tiles_dir).as_posix()
        except ValueError:
            log_rel = conn_log_path.as_posix()

        return StageResult(
            name=self.name,
            status=status,
            tool="iverilog",
            log_paths=[log_rel] if conn_log_path.exists() else None,
        )
