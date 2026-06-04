from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from veriflow.core import VeriFlowError


@dataclass(frozen=True)
class InterfacePort:
    name: str
    direction: Literal["input", "output", "inout"]
    width: int = 1

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise VeriFlowError(
                "InterfacePort name must not be empty or whitespace",
                code="VF_INTERFACE_PORT_NAME_REQUIRED",
            )
        if self.width <= 0:
            raise VeriFlowError(
                f"InterfacePort width must be greater than zero, got {self.width!r}",
                code="VF_INTERFACE_PORT_WIDTH_INVALID",
                details={"name": self.name, "width": self.width},
            )


@dataclass(frozen=True)
class InterfaceProfile:
    name: str
    ports: tuple[InterfacePort, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise VeriFlowError(
                "InterfaceProfile name must not be empty or whitespace",
                code="VF_INTERFACE_NAME_REQUIRED",
            )
        if not self.ports:
            raise VeriFlowError(
                "InterfaceProfile must define at least one port",
                code="VF_INTERFACE_PORT_REQUIRED",
            )
        seen: set[str] = set()
        for port in self.ports:
            if port.name in seen:
                raise VeriFlowError(
                    f"Duplicate port name {port.name!r} in InterfaceProfile {self.name!r}",
                    code="VF_INTERFACE_PORT_DUPLICATE",
                    details={"port": port.name, "profile": self.name},
                )
            seen.add(port.name)


def semicolab_interface_profile() -> InterfaceProfile:
    """Return the nine-port structural contract required by the Semicolab harness."""
    return InterfaceProfile(
        name="semicolab",
        ports=(
            InterfacePort("clk",        "input",  1),
            InterfacePort("arst_n",     "input",  1),
            InterfacePort("csr_in",     "input",  16),
            InterfacePort("data_reg_a", "input",  32),
            InterfacePort("data_reg_b", "input",  32),
            InterfacePort("data_reg_c", "output", 32),
            InterfacePort("csr_out",    "output", 16),
            InterfacePort("csr_in_re",  "output", 1),
            InterfacePort("csr_out_we", "output", 1),
        ),
    )


def get_interface_profile(name: str | None) -> InterfaceProfile | None:
    """Return the InterfaceProfile for *name*, or None for a generic project.

    Raises VF_INTERFACE_UNKNOWN for any non-empty name that is not registered.
    """
    if name is None:
        return None
    if name == "semicolab":
        return semicolab_interface_profile()
    raise VeriFlowError(
        f"Unknown interface name {name!r}. Registered interfaces: semicolab\n"
        "  Set interface_name to a registered value in project_config.yaml.",
        code="VF_INTERFACE_UNKNOWN",
        details={"interface_name": name},
    )
