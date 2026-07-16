from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from veriflow.models.technology_profile import TechnologyProfile


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

    @abc.abstractmethod
    def check_availability(self) -> list[dict]:
        """Returns one dict per required tool.

        Each dict: {"tool": str, "available": bool, "version": str|None,
                    "path": str|None, "error": str|None}
        """


class SimulationBackend(abc.ABC):
    """Abstract backend for HDL simulation."""

    @abc.abstractmethod
    def run_simulation(
        self,
        rtl_files: list[Path],
        tb_files: list[Path],
        tb_top: str,
        sim_log_path: Path,
        wave_path: Path,
    ) -> tuple[str, dict]:
        """Returns ('COMPLETED'|'FAILED', parsed_dict)."""

    @abc.abstractmethod
    def check_availability(self) -> list[dict]:
        """Returns one dict per required tool.

        Each dict: {"tool": str, "available": bool, "version": str|None,
                    "path": str|None, "error": str|None}
        """


class SynthesisBackend(abc.ABC):
    """Abstract backend for RTL synthesis."""

    @abc.abstractmethod
    def run_synthesis(
        self,
        rtl_files: list[Path],
        top_module: str,
        synth_log_path: Path,
        technology: "TechnologyProfile | None" = None,
    ) -> tuple[str, dict]:
        """Returns ('PASS'|'FAIL', parsed_dict)."""

    @abc.abstractmethod
    def check_availability(self) -> list[dict]:
        """Returns one dict per required tool.

        Each dict: {"tool": str, "available": bool, "version": str|None,
                    "path": str|None, "error": str|None}
        """
