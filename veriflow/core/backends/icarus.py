from __future__ import annotations

from pathlib import Path

from veriflow.core.backends._tools import _check_tool
from veriflow.core.backends.base import ConnectivityBackend, SimulationBackend
from veriflow.core.sim_runner import run_connectivity_check, run_simulation


class IcarusConnectivityBackend(ConnectivityBackend):

    def run_connectivity(
        self,
        rtl_files: list[Path],
        interface_profile: object,
        top_module: str,
        log_path: Path,
    ) -> str:
        return run_connectivity_check(
            rtl_files=rtl_files,
            interface_profile=interface_profile,
            top_module=top_module,
            log_path=log_path,
        )

    def check_availability(self) -> list[dict]:
        return [_check_tool("iverilog")]


class IcarusSimulationBackend(SimulationBackend):

    def run_simulation(
        self,
        rtl_files: list[Path],
        tb_files: list[Path],
        tb_top: str,
        sim_log_path: Path,
        wave_path: Path,
    ) -> tuple[str, dict]:
        return run_simulation(
            rtl_files=rtl_files,
            tb_files=tb_files,
            tb_top=tb_top,
            sim_log_path=sim_log_path,
            wave_path=wave_path,
        )

    def check_availability(self) -> list[dict]:
        return [_check_tool("iverilog"), _check_tool("vvp")]
