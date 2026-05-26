from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionProfile:
    name: str = "default"
    connectivity_tool: str = "iverilog"
    simulation_tool: str = "iverilog/vvp"
    synthesis_tool: str = "yosys"
    doc_profile: str = "default"
    # Internal backend IDs — not user-configurable yet
    connectivity_backend: str = "icarus"
    simulation_backend: str = "icarus"
    synthesis_backend: str = "yosys"
    # Technology target name — resolved via get_technology_profile(); not wired into synthesis yet
    technology_name: str = "generic"


def default_execution_profile() -> ExecutionProfile:
    return ExecutionProfile()
