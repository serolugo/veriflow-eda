from __future__ import annotations

from veriflow.core import VeriFlowError
from veriflow.core.backends.base import ConnectivityBackend
from veriflow.core.backends.icarus import IcarusConnectivityBackend
from veriflow.core.pipeline import PipelineStage
from veriflow.framework.stage_input import StageInput
from veriflow.models.execution_profile import ExecutionProfile, default_execution_profile
from veriflow.models.stage_result import StageResult


class InterfaceStage(PipelineStage):
    name = "connectivity"

    def __init__(
        self,
        interface_profile: object | None,
        profile: ExecutionProfile | None = None,
        backend: ConnectivityBackend | None = None,
    ) -> None:
        self.interface_profile = interface_profile
        self._profile = profile or default_execution_profile()
        self._backend = backend or IcarusConnectivityBackend()

    def run(self, input: StageInput) -> StageResult:
        design = input.design
        ctx = input.context
        tool = self._profile.connectivity_tool
        if ctx.skip_connectivity:
            return StageResult(name=self.name, status="SKIPPED", tool=tool)

        if self.interface_profile is None:
            raise VeriFlowError(
                "Connectivity/interface validation requires an InterfaceProfile",
                code="VF_INTERFACE_PROFILE_REQUIRED",
            )

        conn_log_path = ctx.impl_dir / "logs" / "connectivity.log"
        conn_log_path.parent.mkdir(parents=True, exist_ok=True)
        status = self._backend.run_connectivity(
            rtl_files=design.rtl_sources,
            interface_profile=self.interface_profile,
            top_module=design.top_module,
            log_path=conn_log_path,
        )

        log_rel = ctx.log_rel(conn_log_path)

        return StageResult(
            name=self.name,
            status=status,
            tool=tool,
            log_paths=[log_rel] if conn_log_path.exists() else None,
        )
