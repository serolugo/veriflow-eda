"""Interface profile models and registry.

Built-in interface profiles are loaded from ``veriflow/interfaces/<name>/`` at
first use — each subdirectory holds an ``interface.v`` port-contract stub
(parsed with the same regex-based extractor used for RTL auto-detection in
``wrap init``), an optional co-located ``tb_template.v``, and an optional
``meta.yaml`` for the two fields a `.v` file can't express
(``description``, ``requires_top_module``). Projects can also register their
own interface profile at runtime from an arbitrary `.v` file via
``register_interface_profile_from_file`` (see ``workflows/project_config.py``'s
``interface.definition`` field). Discoverable through the registry APIs
(``list_interface_profiles``, ``has_interface_profile``, …) so any frontend or
tool can enumerate them. InterfaceStage still writes historical "connectivity"
artifacts for compatibility.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.wrapper.port_parser import extract_ports

INTERFACES_DIR = Path(__file__).parent.parent / "interfaces"

_MODULE_RE = re.compile(r"\bmodule\s+(\w+)", re.IGNORECASE)


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
    requires_top_module: bool = False
    tb_template: str | None = None  # path to a co-located tb_template.v; None → tb_universal_template.v
    port_descriptions: dict[str, str] | None = None  # {port_name: description}, from meta.yaml

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


def _find_module_names(text: str) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for name in _MODULE_RE.findall(text):
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def load_interface_profile_from_file(path: Path) -> InterfaceProfile:
    """Load an InterfaceProfile from a Verilog port-contract stub file.

    The file needs only a `module <name> (...);` port-list declaration (an
    `endmodule` with no body is enough -- see e.g.
    `veriflow/interfaces/semicolab/interface.v`). Ports are extracted with
    `core.wrapper.port_parser.extract_ports`, the same regex-based parser
    used for RTL auto-detection in `wrap init`.

    The profile's name is the parsed module name (not the file/directory
    name). An optional `tb_template.v` in the same directory becomes
    `tb_template`; an optional `meta.yaml` in the same directory supplies
    `description`/`requires_top_module`/`port_descriptions` (description and
    requires_top_module default to `""`/`False`, port_descriptions to None,
    when absent -- a bare `.v` file with no sidecar is a complete, valid
    profile).

    Raises:
        VeriFlowError(VF_INTERFACE_FILE_NOT_FOUND) -- path does not exist
        VeriFlowError(VF_INTERFACE_FILE_NO_PORTS)   -- no module declaration,
            or the (first) module declaration has zero ports
    Warns (UserWarning, not raised):
        file has 2+ module declarations -- the first (in file order) is used
        [VF_INTERFACE_FILE_MULTIPLE_MODULES]
    """
    path = Path(path)
    if not path.exists():
        raise VeriFlowError(
            f"Interface definition file not found: {path}",
            code="VF_INTERFACE_FILE_NOT_FOUND",
            details={"path": str(path)},
        )
    text = path.read_text(encoding="utf-8")

    modules = _find_module_names(text)
    if not modules:
        raise VeriFlowError(
            f"No module declaration found in {path}.",
            code="VF_INTERFACE_FILE_NO_PORTS",
            details={"path": str(path)},
        )
    if len(modules) > 1:
        warnings.warn(
            f"Multiple module declarations found in {path}: {', '.join(modules)}. "
            f"Using {modules[0]!r}. [VF_INTERFACE_FILE_MULTIPLE_MODULES]",
            stacklevel=2,
        )
    module_name = modules[0]

    raw_ports = extract_ports(text, module_name)
    if not raw_ports:
        raise VeriFlowError(
            f"Module {module_name!r} in {path} has no ports.",
            code="VF_INTERFACE_FILE_NO_PORTS",
            details={"path": str(path), "module": module_name},
        )
    ports = tuple(
        InterfacePort(
            name=name,
            direction=direction,
            width=width if width is not None else 1,
        )
        for name, direction, width in raw_ports
    )

    description = ""
    requires_top_module = False
    port_descriptions: dict[str, str] | None = None
    meta_path = path.parent / "meta.yaml"
    if meta_path.exists():
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        description = meta.get("description") or ""
        requires_top_module = bool(meta.get("requires_top_module", False))
        raw_port_descriptions = meta.get("port_descriptions")
        if isinstance(raw_port_descriptions, dict) and raw_port_descriptions:
            port_descriptions = {
                str(k): str(v) for k, v in raw_port_descriptions.items()
            }

    tb_template_path = path.parent / "tb_template.v"
    tb_template = str(tb_template_path) if tb_template_path.exists() else None

    return InterfaceProfile(
        name=module_name,
        ports=ports,
        description=description,
        requires_top_module=requires_top_module,
        tb_template=tb_template,
        port_descriptions=port_descriptions,
    )


def _load_builtin_interfaces() -> dict[str, Callable[[], InterfaceProfile]]:
    """Scan INTERFACES_DIR for `<name>/interface.v` subdirectories and build
    one lazy factory per built-in interface, keyed by directory name.

    Returns an empty dict if INTERFACES_DIR doesn't exist (defensive -- e.g.
    a stripped-down install missing the data directory shouldn't crash at
    import time, just register zero built-in interfaces).
    """
    factories: dict[str, Callable[[], InterfaceProfile]] = {}
    if not INTERFACES_DIR.is_dir():
        return factories
    for subdir in sorted(p for p in INTERFACES_DIR.iterdir() if p.is_dir()):
        interface_file = subdir / "interface.v"
        if interface_file.exists():
            factories[subdir.name] = (lambda p=interface_file: load_interface_profile_from_file(p))
    return factories


# Built-in interface profile registry. Each entry maps a stable interface
# name to a factory returning a fresh (frozen) InterfaceProfile, so callers
# can never mutate registry state through a returned profile. Insertion
# order defines the deterministic ordering of the list functions.
_PROFILE_FACTORIES: dict[str, Callable[[], InterfaceProfile]] = _load_builtin_interfaces()


def semicolab_interface_profile() -> InterfaceProfile:
    """Backward-compatible accessor for the built-in "semicolab" profile.

    The 9-port contract itself now lives in
    `veriflow/interfaces/semicolab/interface.v` (loaded through the registry,
    same as any other interface) -- this wrapper exists only so existing call
    sites that import this function by name keep working unchanged.
    """
    return get_interface_profile("semicolab")


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


def register_interface_profile_from_file(path: Path) -> str:
    """Load an InterfaceProfile from an external `.v` file and register it.

    Used for project-supplied interfaces (`interface.definition:` in
    `veriflow.yaml` / `interface_definition:` in `project_config.yaml`) --
    unlike the built-in scan, the registered name comes from the parsed
    module name, not from any directory/file naming convention.

    Overwrites any existing profile registered under the same name --
    including a built-in one, so a project can locally redefine e.g.
    "semicolab" if it needs to -- emitting a UserWarning when it does.

    Returns the registered profile's name (the parsed module name).
    """
    profile = load_interface_profile_from_file(Path(path))
    if profile.name in _PROFILE_FACTORIES:
        warnings.warn(
            f"Overwriting existing interface profile {profile.name!r} with "
            f"external definition from {path}. [VF_INTERFACE_PROFILE_OVERWRITTEN]",
            stacklevel=2,
        )
    _PROFILE_FACTORIES[profile.name] = (lambda p=Path(path): load_interface_profile_from_file(p))
    return profile.name
