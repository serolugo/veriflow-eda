from __future__ import annotations

from dataclasses import dataclass

from veriflow.models.technology_profile import DEFAULT_TECHNOLOGY_NAME


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
    # Technology target name — resolved via get_technology_profile()
    technology_name: str = DEFAULT_TECHNOLOGY_NAME
    # If True, SynthesisStage fails explicitly (VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED)
    # when technology_name's PDK isn't installed, instead of warning + falling
    # back to generic synthesis (the default).
    require_pdk: bool = False


def default_execution_profile() -> ExecutionProfile:
    return ExecutionProfile()
