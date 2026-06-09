"""Project Mode workflow configuration.

The optional ``interface`` section selects a registered interface profile:

    interface:
      name: semicolab

Omitting the section (or ``interface: null`` / ``name: null``) means a
generic project with no interface/connectivity check. Built-in interface
names are discoverable through the registry APIs in
``veriflow.models.interface_profile``. Custom YAML-defined interface
definitions are future work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.models.interface_profile import get_interface_profile


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


@dataclass
class ProjectWorkflowConfig:
    top_module: str
    rtl_sources: list[Path]
    tb_sources: list[Path]
    tb_top: str | None
    runs_dir: Path
    interface: ProjectInterfaceConfig | None = None

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
            runs_dir=runs_dir,
        )

    @classmethod
    def from_file(
        cls,
        path: Path | str,
    ) -> "ProjectWorkflowConfig":
        path = Path(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            raw = {}
        return cls.from_dict(raw, root=path.parent)
