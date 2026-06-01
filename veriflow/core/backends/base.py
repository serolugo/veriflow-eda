from __future__ import annotations

import abc
from pathlib import Path


class ConnectivityBackend(abc.ABC):
    """Abstract backend for RTL interface/connectivity checking."""

    @abc.abstractmethod
    def run_connectivity(
        self,
        rtl_files: list[Path],
        interface_profile: object,
        top_module: str,
        log_path: Path,
    ) -> str:
        """Returns 'PASS' or 'FAIL'."""


class SimulationBackend(abc.ABC):
    """Abstract backend for HDL simulation."""

    @abc.abstractmethod
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
        """Returns ('COMPLETED'|'FAILED', parsed_dict)."""


class SynthesisBackend(abc.ABC):
    """Abstract backend for RTL synthesis."""

    @abc.abstractmethod
    def run_synthesis(
        self,
        rtl_files: list[Path],
        top_module: str,
        synth_log_path: Path,
    ) -> tuple[str, dict]:
        """Returns ('PASS'|'FAIL', parsed_dict)."""
