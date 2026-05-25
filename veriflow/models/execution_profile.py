from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionProfile:
    name: str = "default"
    connectivity_tool: str = "iverilog"
    simulation_tool: str = "iverilog/vvp"
    synthesis_tool: str = "yosys"
    doc_profile: str = "default"


def default_execution_profile() -> ExecutionProfile:
    return ExecutionProfile()
