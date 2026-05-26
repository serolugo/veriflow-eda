from __future__ import annotations

from veriflow.core import VeriFlowError
from veriflow.core.backends.base import ConnectivityBackend, SimulationBackend, SynthesisBackend
from veriflow.core.backends.icarus import IcarusConnectivityBackend, IcarusSimulationBackend
from veriflow.core.backends.yosys import YosysSynthesisBackend

_CONNECTIVITY: dict[str, type[ConnectivityBackend]] = {
    "icarus": IcarusConnectivityBackend,
}

_SIMULATION: dict[str, type[SimulationBackend]] = {
    "icarus": IcarusSimulationBackend,
}

_SYNTHESIS: dict[str, type[SynthesisBackend]] = {
    "yosys": YosysSynthesisBackend,
}


def get_connectivity_backend(name: str) -> ConnectivityBackend:
    cls = _CONNECTIVITY.get(name)
    if cls is None:
        raise VeriFlowError(
            f"Unknown connectivity backend: {name!r}",
            code="VF_BACKEND_CONNECTIVITY_UNKNOWN",
        )
    return cls()


def get_simulation_backend(name: str) -> SimulationBackend:
    cls = _SIMULATION.get(name)
    if cls is None:
        raise VeriFlowError(
            f"Unknown simulation backend: {name!r}",
            code="VF_BACKEND_SIMULATION_UNKNOWN",
        )
    return cls()


def get_synthesis_backend(name: str) -> SynthesisBackend:
    cls = _SYNTHESIS.get(name)
    if cls is None:
        raise VeriFlowError(
            f"Unknown synthesis backend: {name!r}",
            code="VF_BACKEND_SYNTHESIS_UNKNOWN",
        )
    return cls()
