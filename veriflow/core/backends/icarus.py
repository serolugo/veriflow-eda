from __future__ import annotations

from pathlib import Path

from veriflow.core.backends.base import ConnectivityBackend, SimulationBackend
from veriflow.core.sim_runner import run_connectivity_check, run_simulation


class IcarusConnectivityBackend(ConnectivityBackend):

    def run_connectivity(
        self,
        rtl_files: list[Path],
        tb_base_path: Path,
        tb_tasks_path: Path,
        top_module: str,
        log_path: Path,
    ) -> str:
        return run_connectivity_check(
            rtl_files=rtl_files,
            tb_base_path=tb_base_path,
            tb_tasks_path=tb_tasks_path,
            top_module=top_module,
            log_path=log_path,
        )


class IcarusSimulationBackend(SimulationBackend):

    def run_simulation(
        self,
        rtl_files: list[Path],
        tb_files: list[Path],
        tb_base_path,
        tb_tasks_path,
        top_module: str,
        sim_log_path: Path,
        wave_path: Path,
        semicolab: bool = True,
    ) -> tuple[str, dict]:
        return run_simulation(
            rtl_files=rtl_files,
            tb_files=tb_files,
            tb_base_path=tb_base_path,
            tb_tasks_path=tb_tasks_path,
            top_module=top_module,
            sim_log_path=sim_log_path,
            wave_path=wave_path,
            semicolab=semicolab,
        )
