from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from veriflow.core import VeriFlowError


@dataclass
class Design:
    top_module: str
    rtl_sources: list[Path]
    tb_sources: list[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.top_module or not self.top_module.strip():
            raise VeriFlowError(
                "top_module must not be empty",
                code="VF_DESIGN_TOP_REQUIRED",
            )
        if not self.rtl_sources:
            raise VeriFlowError(
                "rtl_sources must not be empty",
                code="VF_DESIGN_RTL_REQUIRED",
            )
        self.rtl_sources = [Path(p) for p in self.rtl_sources]
        self.tb_sources = [Path(p) for p in self.tb_sources]


__all__ = ["Design"]
