"""Interface profile models and registry.

Interface profiles are registered here and can be discovered through the
registry APIs (``list_interface_profiles``, ``has_interface_profile``, …) so
frontends such as TileWizard and TileBench can enumerate them. The initial
built-in profile is "semicolab". Custom YAML-defined interfaces are future
work. InterfaceStage still writes historical "connectivity" artifacts for
compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

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
    description: str = ""

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
        description="Nine-port structural contract required by the Semicolab harness.",
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


# Built-in interface profile registry. Each entry maps a stable interface
# name to a factory returning a fresh (frozen) InterfaceProfile, so callers
# can never mutate registry state through a returned profile. Insertion
# order defines the deterministic ordering of the list functions.
_PROFILE_FACTORIES: dict[str, Callable[[], InterfaceProfile]] = {
    "semicolab": semicolab_interface_profile,
}


def list_interface_profile_names() -> list[str]:
    """Return the registered interface names in stable registration order."""
    return list(_PROFILE_FACTORIES)


def list_interface_profiles() -> list[InterfaceProfile]:
    """Return all registered InterfaceProfiles in stable registration order.

    A new list of freshly built profiles is returned on every call.
    """
    return [factory() for factory in _PROFILE_FACTORIES.values()]


def has_interface_profile(name: str) -> bool:
    """Return True if *name* is a registered interface profile."""
    return name in _PROFILE_FACTORIES


def default_interface_profile() -> InterfaceProfile | None:
    """Return the default InterfaceProfile, or None.

    VeriFlow has no default interface: projects must opt in explicitly via
    interface_name / interface.name, and an omitted or null value means a
    generic project with no interface checking.
    """
    return None


def get_interface_profile(name: str | None) -> InterfaceProfile | None:
    """Return the InterfaceProfile for *name*, or None for a generic project.

    Raises VF_INTERFACE_UNKNOWN for any non-empty name that is not registered.
    """
    if name is None:
        return None
    factory = _PROFILE_FACTORIES.get(name)
    if factory is not None:
        return factory()
    registered = ", ".join(_PROFILE_FACTORIES)
    raise VeriFlowError(
        f"Unknown interface name {name!r}. Registered interfaces: {registered}\n"
        "  Set interface_name to a registered value in project_config.yaml.",
        code="VF_INTERFACE_UNKNOWN",
        details={"interface_name": name},
    )
