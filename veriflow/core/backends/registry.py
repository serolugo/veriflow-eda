from __future__ import annotations

from veriflow.core import VeriFlowError
from veriflow.core.backends.base import ConnectivityBackend, SimulationBackend, SynthesisBackend
from veriflow.core.backends.icarus import IcarusConnectivityBackend, IcarusSimulationBackend
from veriflow.core.backends.xsim import XsimSimulationBackend
from veriflow.core.backends.yosys import YosysSynthesisBackend

_CONNECTIVITY: dict[str, type[ConnectivityBackend]] = {
    "icarus": IcarusConnectivityBackend,
}

_SIMULATION: dict[str, type[SimulationBackend]] = {
    "icarus": IcarusSimulationBackend,
    "xsim": XsimSimulationBackend,
}

_SYNTHESIS: dict[str, type[SynthesisBackend]] = {
    "yosys": YosysSynthesisBackend,
}

# Backend ID -> human-readable EDA tool name, for display in results.json /
# manifest.yaml. A backend ID with no entry here falls back to itself, so a
# future backend that forgets to register a display name still shows
# *something* meaningful instead of raising.
_CONNECTIVITY_TOOL_NAMES: dict[str, str] = {"icarus": "iverilog"}
_SIMULATION_TOOL_NAMES: dict[str, str] = {"icarus": "iverilog/vvp", "xsim": "xvlog/xelab/xsim"}
_SYNTHESIS_TOOL_NAMES: dict[str, str] = {"yosys": "yosys"}


def get_connectivity_tool_name(backend_id: str) -> str:
    """Return the display name of the EDA tool behind *backend_id* (e.g.
    "icarus" -> "iverilog"), for results.json/manifest.yaml -- NOT the
    backend ID itself, which is an internal registry key."""
    return _CONNECTIVITY_TOOL_NAMES.get(backend_id, backend_id)


def get_simulation_tool_name(backend_id: str) -> str:
    return _SIMULATION_TOOL_NAMES.get(backend_id, backend_id)


def get_synthesis_tool_name(backend_id: str) -> str:
    return _SYNTHESIS_TOOL_NAMES.get(backend_id, backend_id)


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
