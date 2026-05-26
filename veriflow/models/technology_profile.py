from __future__ import annotations

from dataclasses import dataclass

from veriflow.core import VeriFlowError


@dataclass
class TechnologyProfile:
    name: str = "generic"
    pdk: str | None = None
    cell_library: str | None = None
    liberty: str | None = None
    constraints: str | None = None
    notes: str | None = None


def default_technology_profile() -> TechnologyProfile:
    return TechnologyProfile()


_REGISTRY: dict[str, TechnologyProfile] = {
    "generic": TechnologyProfile(
        name="generic",
        notes="Baseline technology target with no PDK constraints.",
    ),
    "sky130": TechnologyProfile(
        name="sky130",
        pdk="sky130",
        cell_library="sky130_fd_sc_hd",
        notes="SkyWater 130nm PDK — placeholder for future synthesis target configuration.",
    ),
    "gf180": TechnologyProfile(
        name="gf180",
        pdk="gf180mcu",
        cell_library="gf180mcu_fd_sc_mcu7t5v0",
        notes="GlobalFoundries 180nm MCU PDK — placeholder for future synthesis target configuration.",
    ),
    "ihp130": TechnologyProfile(
        name="ihp130",
        pdk="ihp-sg13g2",
        cell_library="sg13g2_stdcell",
        notes="IHP 130nm SG13G2 PDK — placeholder for future synthesis target configuration.",
    ),
}


def get_technology_profile(name: str) -> TechnologyProfile:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise VeriFlowError(
            f"Unknown technology profile: {name!r}",
            code="VF_TECHNOLOGY_UNKNOWN",
            details={"name": name, "supported": list(_REGISTRY)},
        )
