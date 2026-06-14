"""
generator.py — Verilog wrapper generation.

Only call generate_wrapper() when WrapValidationResult.status == "PASS".
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from veriflow.models.interface_profile import InterfaceProfile
from veriflow.models.wrapper_config import WrapperConfig
from .validator import WrapValidationResult

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_wrapper(
    config: WrapperConfig,
    interface_profile: InterfaceProfile,
    result: WrapValidationResult,
    ip_ports: list[tuple[str, str, Optional[int]]],
) -> str:
    """Render and return the wrapper Verilog source as a string."""
    ip_dir = {name: direction for name, direction, _w in ip_ports}
    iface_widths = {p.name: p.width for p in interface_profile.ports}

    # Port declaration lines (comma-joined by template)
    port_decls = []
    for p in interface_profile.ports:
        bus = f"[{p.width - 1}:0] " if p.width > 1 else ""
        port_decls.append(f"    {p.direction} wire {bus}{p.name}")

    # Instantiation connection lines
    conn_lines = []
    for m in result.mapped:
        hi, lo = m["hi"], m["lo"]
        iface_name = m["interface_port"]
        if hi is None:
            signal = iface_name
        elif hi == lo:
            signal = f"{iface_name}[{hi}]"
        else:
            signal = f"{iface_name}[{hi}:{lo}]"
        conn_lines.append(f"        .{m['ip_port']}({signal})")

    for port_name in result.unmapped_ip_ports:
        direction = ip_dir.get(port_name, "output")
        signal = "1'b0" if direction == "input" else ""
        conn_lines.append(f"        .{port_name}({signal})")

    # Assign statements for unmapped interface outputs
    assign_lines = []
    for ump in result.unmapped_interface_ports:
        if ump["direction"] != "output":
            continue
        hi, lo = ump["hi"], ump["lo"]
        port_name = ump["port"]
        width = iface_widths[port_name]
        if width == 1 and hi == 0 and lo == 0:
            assign_lines.append(f"assign {port_name} = 1'b0;")
        else:
            bits = hi - lo + 1
            assign_lines.append(f"assign {port_name}[{hi}:{lo}] = {bits}'b0;")

    assign_block = (
        "\n".join(f"    {s}" for s in assign_lines) + "\n"
        if assign_lines
        else ""
    )

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.get_template("wrapper_template.j2")

    return template.render(
        wrapper_name=config.wrapper_name,
        top_module=config.design.top_module,
        metadata_name=config.metadata.get("name", config.design.top_module),
        interface_name=interface_profile.name,
        date=datetime.date.today().isoformat(),
        port_decls_joined=",\n".join(port_decls),
        connections_joined=",\n".join(conn_lines),
        assign_block=assign_block,
    )
