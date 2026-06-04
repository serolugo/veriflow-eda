from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from veriflow.core import VeriFlowError
from veriflow.models.interface_profile import get_interface_profile


@dataclass
class ProjectWorkflowConfig:
    top_module: str
    rtl_sources: list[Path]
    tb_sources: list[Path]
    tb_top: str | None
    interface_name: str | None
    runs_dir: Path

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

        # interface section — omitted or name: null both resolve to None
        interface_section = data.get("interface")
        interface_name: str | None = None
        if isinstance(interface_section, dict):
            raw_name = interface_section.get("name")
            if isinstance(raw_name, str):
                raw_name = raw_name.strip() or None
            interface_name = raw_name

        # Validate interface_name — raises VF_INTERFACE_UNKNOWN for unknown names
        get_interface_profile(interface_name)

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
            interface_name=interface_name,
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
