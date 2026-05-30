from __future__ import annotations

from pathlib import Path

from veriflow.core.backends.base import ConnectivityBackend
from veriflow.core.backends.icarus import IcarusConnectivityBackend
from veriflow.core.pipeline import PipelineStage
from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
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
        profile: ExecutionProfile | None = None,
        backend: ConnectivityBackend | None = None,
    ) -> None:
        self.rtl_files = rtl_files
        self.tb_base_path = tb_base_path
        self.tb_tasks_path = tb_tasks_path
        self.top_module = top_module
        self._profile = profile or default_execution_profile()
        self._backend = backend or IcarusConnectivityBackend()

    def run(self, ctx: RunContext) -> StageResult:
        tool = self._profile.connectivity_tool
        if ctx.skip_connectivity:
            return StageResult(name=self.name, status="SKIPPED", tool=tool)

        conn_log_path = ctx.impl_dir / "logs" / "connectivity.log"
        status = self._backend.run_connectivity(
            rtl_files=self.rtl_files,
            tb_base_path=self.tb_base_path,
            tb_tasks_path=self.tb_tasks_path,
            top_module=self.top_module,
            log_path=conn_log_path,
        )

        log_rel = ctx.log_rel(conn_log_path)

        return StageResult(
            name=self.name,
            status=status,
            tool=tool,
            log_paths=[log_rel] if conn_log_path.exists() else None,
        )
