"""Project Mode workflow configuration.

The optional ``interface`` section selects a registered interface profile:

    interface:
      name: semicolab

Omitting the section (or ``interface: null`` / ``name: null``) means a
generic project with no interface/connectivity check. Built-in interface
names are discoverable through the registry APIs in
``veriflow.models.interface_profile``. Custom YAML-defined interface
definitions are future work.

The optional ``execution`` and ``technology`` sections select execution
backends and the technology target:

    execution:
      connectivity_backend: icarus
      simulation_backend: icarus
      synthesis_backend: yosys

    technology:
      name: generic

Both sections are optional. Omitting a section (or setting it to ``null``)
uses the current defaults shown above. Backend names must already be
registered in ``veriflow.core.backends.registry`` and technology names in
``veriflow.models.technology_profile`` — no new backends are introduced
here, and custom backend plugins are future work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.core.backends.registry import (
    get_connectivity_backend,
    get_simulation_backend,
    get_synthesis_backend,
)
from veriflow.models.execution_profile import default_execution_profile
from veriflow.models.interface_profile import get_interface_profile
from veriflow.models.technology_profile import get_technology_profile

_EXECUTION_DEFAULTS = default_execution_profile()


@dataclass(frozen=True)
class ProjectInterfaceConfig:
    """Interface selection for Project Mode.

    ``name`` refers to a profile registered in
    ``veriflow.models.interface_profile``.
    """

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise VeriFlowError(
                "interface.name must be a non-empty string",
                code="VF_INTERFACE_NAME_REQUIRED",
            )


def _parse_interface_section(data: dict) -> ProjectInterfaceConfig | None:
    if "interface_name" in data:
        raise VeriFlowError(
            "Top-level 'interface_name' is not supported in Project Mode configuration.\n"
            "  Use the interface section instead:\n"
            "    interface:\n"
            "      name: semicolab",
            code="VF_INTERFACE_CONFIG_INVALID",
        )

    section = data.get("interface")
    if section is None:
        # omitted or `interface: null` — generic project, no interface check
        return None

    if not isinstance(section, dict):
        raise VeriFlowError(
            "interface section must be a mapping with a 'name' key, e.g.:\n"
            "    interface:\n"
            "      name: semicolab",
            code="VF_INTERFACE_CONFIG_INVALID",
            details={"interface": section},
        )

    unknown_keys = sorted(set(section) - {"name"})
    if unknown_keys:
        raise VeriFlowError(
            f"Unsupported keys in interface section: {', '.join(unknown_keys)}.\n"
            "  Only 'name' is supported; custom interface definitions are not yet supported.",
            code="VF_INTERFACE_CONFIG_INVALID",
            details={"unknown_keys": unknown_keys},
        )

    if "name" not in section:
        raise VeriFlowError(
            "interface section requires a 'name', e.g.:\n"
            "    interface:\n"
            "      name: semicolab",
            code="VF_INTERFACE_NAME_REQUIRED",
        )

    raw_name = section["name"]
    if raw_name is None:
        # explicit `name: null` — generic project, no interface check
        return None
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise VeriFlowError(
            "interface.name must be a non-empty string or null",
            code="VF_INTERFACE_NAME_REQUIRED",
            details={"name": raw_name},
        )

    name = raw_name.strip()
    # Raises VF_INTERFACE_UNKNOWN for names not in the registry
    get_interface_profile(name)
    return ProjectInterfaceConfig(name=name)


@dataclass(frozen=True)
class ProjectExecutionConfig:
    """Execution backend selection for Project Mode.

    Backend names refer to entries in ``veriflow.core.backends.registry``.
    """

    connectivity_backend: str = _EXECUTION_DEFAULTS.connectivity_backend
    simulation_backend: str = _EXECUTION_DEFAULTS.simulation_backend
    synthesis_backend: str = _EXECUTION_DEFAULTS.synthesis_backend

    def __post_init__(self) -> None:
        for key in ("connectivity_backend", "simulation_backend", "synthesis_backend"):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise VeriFlowError(
                    f"execution.{key} must be a non-empty string",
                    code="VF_EXECUTION_CONFIG_INVALID",
                    details={key: value},
                )


@dataclass(frozen=True)
class ProjectTechnologyConfig:
    """Technology target selection for Project Mode.

    ``name`` refers to a profile registered in
    ``veriflow.models.technology_profile``.
    """

    name: str = "generic"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise VeriFlowError(
                "technology.name must be a non-empty string",
                code="VF_TECHNOLOGY_CONFIG_INVALID",
                details={"name": self.name},
            )


_EXECUTION_KEYS = frozenset({
    "connectivity_backend",
    "simulation_backend",
    "synthesis_backend",
})

_BACKEND_VALIDATORS = {
    "connectivity_backend": get_connectivity_backend,
    "simulation_backend": get_simulation_backend,
    "synthesis_backend": get_synthesis_backend,
}


def _parse_execution_section(data: dict) -> ProjectExecutionConfig:
    section = data.get("execution")
    if section is None:
        # omitted or `execution: null` — current default backends
        return ProjectExecutionConfig()

    if not isinstance(section, dict):
        raise VeriFlowError(
            "execution section must be a mapping, e.g.:\n"
            "    execution:\n"
            "      connectivity_backend: icarus\n"
            "      simulation_backend: icarus\n"
            "      synthesis_backend: yosys",
            code="VF_EXECUTION_CONFIG_INVALID",
            details={"execution": section},
        )

    unknown_keys = sorted(set(section) - _EXECUTION_KEYS)
    if unknown_keys:
        raise VeriFlowError(
            f"Unsupported keys in execution section: {', '.join(unknown_keys)}.\n"
            f"  Supported keys: {', '.join(sorted(_EXECUTION_KEYS))}.",
            code="VF_EXECUTION_CONFIG_INVALID",
            details={"unknown_keys": unknown_keys},
        )

    defaults = ProjectExecutionConfig()
    values: dict[str, str] = {}
    for key, validate in _BACKEND_VALIDATORS.items():
        raw = section.get(key)
        if raw is None:
            # key omitted or `<key>: null` — current default backend
            values[key] = getattr(defaults, key)
            continue
        if not isinstance(raw, str) or not raw.strip():
            raise VeriFlowError(
                f"execution.{key} must be a non-empty string or null",
                code="VF_EXECUTION_CONFIG_INVALID",
                details={key: raw},
            )
        name = raw.strip()
        # Raises VF_BACKEND_*_UNKNOWN for names not in the registry
        validate(name)
        values[key] = name

    return ProjectExecutionConfig(**values)


def _parse_technology_section(data: dict) -> ProjectTechnologyConfig:
    section = data.get("technology")
    if section is None:
        # omitted or `technology: null` — generic technology target
        return ProjectTechnologyConfig()

    if not isinstance(section, dict):
        raise VeriFlowError(
            "technology section must be a mapping with a 'name' key, e.g.:\n"
            "    technology:\n"
            "      name: generic",
            code="VF_TECHNOLOGY_CONFIG_INVALID",
            details={"technology": section},
        )

    unknown_keys = sorted(set(section) - {"name"})
    if unknown_keys:
        raise VeriFlowError(
            f"Unsupported keys in technology section: {', '.join(unknown_keys)}.\n"
            "  Only 'name' is supported.",
            code="VF_TECHNOLOGY_CONFIG_INVALID",
            details={"unknown_keys": unknown_keys},
        )

    raw_name = section.get("name")
    if raw_name is None:
        # empty section or `name: null` — generic technology target
        return ProjectTechnologyConfig()
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise VeriFlowError(
            "technology.name must be a non-empty string or null",
            code="VF_TECHNOLOGY_CONFIG_INVALID",
            details={"name": raw_name},
        )

    name = raw_name.strip()
    # Raises VF_TECHNOLOGY_UNKNOWN for names not in the registry
    get_technology_profile(name)
    return ProjectTechnologyConfig(name=name)


@dataclass
class ProjectWorkflowConfig:
    top_module: str
    rtl_sources: list[Path]
    tb_sources: list[Path]
    tb_top: str | None
    runs_dir: Path
    interface: ProjectInterfaceConfig | None = None
    execution: ProjectExecutionConfig = field(default_factory=ProjectExecutionConfig)
    technology: ProjectTechnologyConfig = field(default_factory=ProjectTechnologyConfig)
    root: Path = field(default_factory=lambda: Path("."))

    @classmethod
    def from_dict(
        cls,
        data: dict,
        *,
        root: Path,
    ) -> "ProjectWorkflowConfig":
        design = data.get("design") or {}

        top_module = (design.get("top_module") or "").strip()
        if not top_module:
            raise VeriFlowError(
                "design.top_module is required and must not be empty",
                code="VF_DESIGN_TOP_REQUIRED",
            )

        raw_rtl = design.get("rtl_sources") or []
        if not raw_rtl:
            raise VeriFlowError(
                "design.rtl_sources must not be empty",
                code="VF_DESIGN_RTL_REQUIRED",
            )
        rtl_sources = [root / p for p in raw_rtl]

        raw_tb = design.get("tb_sources") or []
        tb_sources = [root / p for p in raw_tb]

        interface = _parse_interface_section(data)
        execution = _parse_execution_section(data)
        technology = _parse_technology_section(data)

        # simulation section
        sim_section = data.get("simulation")
        tb_top: str | None = None
        if isinstance(sim_section, dict):
            raw_tb_top = sim_section.get("tb_top")
            if raw_tb_top is not None:
                tb_top = str(raw_tb_top).strip() or None

        if tb_sources and not tb_top:
            raise VeriFlowError(
                "simulation.tb_top is required and must not be empty when tb_sources is non-empty",
                code="VF_SIM_TB_TOP_REQUIRED",
            )

        # output section
        output_section = data.get("output")
        runs_dir_val = None
        if isinstance(output_section, dict):
            runs_dir_val = output_section.get("runs_dir")

        runs_dir = root / (runs_dir_val if runs_dir_val else "runs")

        return cls(
            top_module=top_module,
            rtl_sources=rtl_sources,
            tb_sources=tb_sources,
            tb_top=tb_top,
            interface=interface,
            execution=execution,
            technology=technology,
            runs_dir=runs_dir,
            root=Path(root),
        )

    @classmethod
    def from_file(
        cls,
        path: Path | str,
    ) -> "ProjectWorkflowConfig":
        given = Path(path)
        path = given.resolve()
        if not path.exists():
            raise VeriFlowError(
                f"Project config not found: {path}",
                code="VF_PROJECT_CONFIG_NOT_FOUND",
                details={"path": str(path), "path_given": str(given)},
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise VeriFlowError(
                f"YAML parse error in {path}:\n  {exc}",
                code="VF_PROJECT_CONFIG_YAML_ERROR",
                details={"path": str(path)},
            ) from exc
        if raw is None:
            raw = {}
        return cls.from_dict(raw, root=path.parent)
