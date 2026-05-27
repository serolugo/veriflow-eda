from __future__ import annotations

from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.backends.registry import (
    get_connectivity_backend,
    get_simulation_backend,
    get_synthesis_backend,
)
from veriflow.models.execution_profile import ExecutionProfile
from veriflow.models.technology_profile import get_technology_profile

_KNOWN_KEYS = frozenset({
    "name",
    "connectivity_backend",
    "simulation_backend",
    "synthesis_backend",
    "connectivity_tool",
    "simulation_tool",
    "synthesis_tool",
    "technology_name",
    "doc_profile",
})


def load_execution_profile(path: str | Path) -> ExecutionProfile:
    """Load an ExecutionProfile from a YAML file.

    Raises VeriFlowError for unknown keys, unrecognised backend names, or
    unknown technology_name.  File-not-found is also surfaced as VeriFlowError
    (VF_PROFILE_NOT_FOUND) so callers never have to catch OSError.
    """
    path = Path(path)
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise VeriFlowError(
            f"Profile file not found: {path}",
            code="VF_PROFILE_NOT_FOUND",
            details={"path": str(path)},
        )

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        raise VeriFlowError(
            f"Profile file must contain a YAML mapping, got {type(raw).__name__!r}: {path}",
            code="VF_PROFILE_INVALID",
            details={"path": str(path)},
        )

    unknown = sorted(set(raw) - _KNOWN_KEYS)
    if unknown:
        raise VeriFlowError(
            f"Unknown key(s) in profile {path.name!r}: {', '.join(unknown)}",
            code="VF_PROFILE_UNKNOWN_KEY",
            details={"unknown_keys": unknown, "path": str(path)},
        )

    defaults = ExecutionProfile()

    connectivity_backend = raw.get("connectivity_backend", defaults.connectivity_backend)
    simulation_backend = raw.get("simulation_backend", defaults.simulation_backend)
    synthesis_backend = raw.get("synthesis_backend", defaults.synthesis_backend)
    technology_name = raw.get("technology_name", defaults.technology_name)

    # Validate backend names — registry raises VeriFlowError with its own code on failure
    get_connectivity_backend(connectivity_backend)
    get_simulation_backend(simulation_backend)
    get_synthesis_backend(synthesis_backend)
    # Validate technology name — raises VF_TECHNOLOGY_UNKNOWN on failure
    get_technology_profile(technology_name)

    return ExecutionProfile(
        name=raw.get("name", defaults.name),
        connectivity_backend=connectivity_backend,
        simulation_backend=simulation_backend,
        synthesis_backend=synthesis_backend,
        connectivity_tool=raw.get("connectivity_tool", defaults.connectivity_tool),
        simulation_tool=raw.get("simulation_tool", defaults.simulation_tool),
        synthesis_tool=raw.get("synthesis_tool", defaults.synthesis_tool),
        technology_name=technology_name,
        doc_profile=raw.get("doc_profile", defaults.doc_profile),
    )
