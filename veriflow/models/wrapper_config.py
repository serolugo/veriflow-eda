from __future__ import annotations

from dataclasses import dataclass

from veriflow.core import VeriFlowError
from veriflow.models.interface_profile import has_interface_profile, list_interface_profile_names


@dataclass
class WrapperDesign:
    top_module: str
    rtl_sources: list[str]


@dataclass
class WrapperConfig:
    interface_name: str
    metadata: dict
    design: WrapperDesign
    ports: dict[str, str]
    wrapper_name: str

    @classmethod
    def from_dict(cls, data: dict) -> "WrapperConfig":
        interface_name = data.get("interface_name")
        if not interface_name or not str(interface_name).strip():
            raise VeriFlowError(
                "wrapper_config.yaml must declare 'interface_name'.",
                code="VF_WRAP_INTERFACE_REQUIRED",
            )
        interface_name = str(interface_name).strip()
        if not has_interface_profile(interface_name):
            registered = ", ".join(list_interface_profile_names())
            raise VeriFlowError(
                f"Unknown interface name {interface_name!r}. Registered interfaces: {registered}",
                code="VF_WRAP_INTERFACE_UNKNOWN",
                details={"interface_name": interface_name},
            )

        design_data = data.get("design") or {}
        top_module = (design_data.get("top_module") or "").strip()
        if not top_module:
            raise VeriFlowError(
                "wrapper_config.yaml must declare 'design.top_module'.",
                code="VF_WRAP_TOP_MODULE_REQUIRED",
            )

        rtl_sources = design_data.get("rtl_sources") or []
        if not rtl_sources:
            raise VeriFlowError(
                "wrapper_config.yaml must declare at least one file in 'design.rtl_sources'.",
                code="VF_WRAP_RTL_SOURCES_EMPTY",
            )

        raw_wrapper_name = (data.get("wrapper_name") or "").strip()
        wrapper_name = raw_wrapper_name if raw_wrapper_name else f"{top_module}_wrapper"

        return cls(
            interface_name=interface_name,
            metadata=dict(data.get("metadata") or {}),
            design=WrapperDesign(
                top_module=top_module,
                rtl_sources=list(rtl_sources),
            ),
            ports=dict(data.get("ports") or {}),
            wrapper_name=wrapper_name,
        )
