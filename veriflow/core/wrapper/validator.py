"""
validator.py — WrapperConfig mapping validator.

Operates on wrapper_config.yaml BEFORE generating anything.
Returns a WrapValidationResult with errors (VF_WRAP_E*) and info (VF_WRAP_I*)
messages. status == "FAIL" iff errors is non-empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from veriflow.models.interface_profile import InterfaceProfile
from veriflow.models.wrapper_config import WrapperConfig


_MAP_TO_RE = re.compile(r"^(\w+)(?:\[(\d+)(?::(\d+))?\])?$")


def _bits_to_ranges(used: set[int], width: int) -> list[tuple[int, int]]:
    """Return contiguous (hi, lo) ranges of bits in [0, width) NOT in *used*."""
    missing = sorted(set(range(width)) - used)
    if not missing:
        return []
    ranges: list[tuple[int, int]] = []
    lo = hi = missing[0]
    for b in missing[1:]:
        if b == hi + 1:
            hi = b
        else:
            ranges.append((hi, lo))
            lo = hi = b
    ranges.append((hi, lo))
    return ranges


@dataclass
class WrapValidationResult:
    status: Literal["PASS", "FAIL"]
    errors: list[dict] = field(default_factory=list)
    info: list[dict] = field(default_factory=list)
    mapped: list[dict] = field(default_factory=list)
    unmapped_ip_ports: list[str] = field(default_factory=list)
    unmapped_interface_ports: list[dict] = field(default_factory=list)


def validate_mapping(
    config: WrapperConfig,
    interface_profile: InterfaceProfile,
    ip_ports: list[tuple[str, str, Optional[int]]],
) -> WrapValidationResult:
    """Validate config.ports against *interface_profile* and *ip_ports*.

    ip_ports: list of (name, direction, width) as returned by
    port_parser.extract_ports. width is None when unresolvable (parametrized).
    """
    errors: list[dict] = []
    info: list[dict] = []
    mapped: list[dict] = []

    iface_port_map = {p.name: p for p in interface_profile.ports}
    ip_port_map: dict[str, tuple[str, Optional[int]]] = {
        name: (direction, width) for name, direction, width in ip_ports
    }

    # Emit inout info for ALL inout ports upfront
    for name, direction, _w in ip_ports:
        if direction == "inout":
            info.append({
                "code": "VF_WRAP_I_IP_PORT_INOUT_UNSUPPORTED",
                "severity": "info",
                "message": (
                    f"IP port {name!r} is inout; treated as output for connection purposes."
                ),
            })

    # Track used bits per interface port
    used_bits: dict[str, set[int]] = {p.name: set() for p in interface_profile.ports}
    mapped_ip_ports: set[str] = set()

    for ip_port, map_to in config.ports.items():
        m = _MAP_TO_RE.match(str(map_to).strip())
        if not m:
            errors.append({
                "code": "VF_WRAP_E_MAPPING_SYNTAX",
                "severity": "error",
                "message": (
                    f"Invalid mapping syntax {map_to!r} for ip_port {ip_port!r}. "
                    f"Expected: <port> or <port>[hi:lo] or <port>[bit]."
                ),
            })
            continue

        iface_name = m.group(1)
        bit_hi = int(m.group(2)) if m.group(2) is not None else None
        bit_lo = int(m.group(3)) if m.group(3) is not None else (bit_hi if bit_hi is not None else None)

        if ip_port not in ip_port_map:
            errors.append({
                "code": "VF_WRAP_E_IP_PORT_UNKNOWN",
                "severity": "error",
                "message": f"IP port {ip_port!r} not found in RTL.",
            })
            continue

        if iface_name not in iface_port_map:
            errors.append({
                "code": "VF_WRAP_E_INTERFACE_PORT_UNKNOWN",
                "severity": "error",
                "message": (
                    f"Interface port {iface_name!r} not found in profile "
                    f"{interface_profile.name!r}."
                ),
            })
            continue

        iface_port = iface_port_map[iface_name]

        if bit_hi is None:
            eff_hi, eff_lo = iface_port.width - 1, 0
        else:
            eff_hi, eff_lo = bit_hi, bit_lo  # type: ignore[assignment]

        if eff_hi >= iface_port.width or eff_lo < 0 or eff_hi < eff_lo:
            errors.append({
                "code": "VF_WRAP_E_SLICE_OUT_OF_RANGE",
                "severity": "error",
                "message": (
                    f"Slice [{eff_hi}:{eff_lo}] out of range for interface port "
                    f"{iface_name!r} (width={iface_port.width})."
                ),
            })
            continue

        bits_to_assign = set(range(eff_lo, eff_hi + 1))
        conflict = bits_to_assign & used_bits[iface_name]
        if conflict:
            errors.append({
                "code": "VF_WRAP_E_BIT_CONFLICT",
                "severity": "error",
                "message": (
                    f"Bits {sorted(conflict)} of interface port {iface_name!r} "
                    f"already mapped (conflict at ip_port {ip_port!r})."
                ),
            })
            continue

        used_bits[iface_name] |= bits_to_assign

        # Width mismatch check — informative only, never blocks generation
        _ip_direction, ip_width = ip_port_map[ip_port]
        if ip_width is not None:
            slice_width = eff_hi - eff_lo + 1
            if slice_width != ip_width:
                info.append({
                    "code": "VF_WRAP_I_IP_WIDTH_MISMATCH",
                    "severity": "info",
                    "message": (
                        f"IP port {ip_port!r} has width {ip_width} but maps to "
                        f"{iface_name!r}[{eff_hi}:{eff_lo}] (width {slice_width}); "
                        f"connectivity check will surface elaboration width errors."
                    ),
                })

        mapped_ip_ports.add(ip_port)
        mapped.append({
            "ip_port": ip_port,
            "interface_port": iface_name,
            "hi": bit_hi,
            "lo": bit_lo,
        })

    # Unmapped interface ports
    unmapped_interface_ports: list[dict] = []
    for iface_port in interface_profile.ports:
        for hi, lo in _bits_to_ranges(used_bits[iface_port.name], iface_port.width):
            unmapped_interface_ports.append({
                "port": iface_port.name,
                "direction": iface_port.direction,
                "hi": hi,
                "lo": lo,
            })
            if iface_port.direction == "output":
                info.append({
                    "code": "VF_WRAP_I_INTERFACE_OUTPUT_UNMAPPED",
                    "severity": "info",
                    "message": (
                        f"Interface output {iface_port.name!r}[{hi}:{lo}] is unmapped; "
                        f"will be assigned to 0."
                    ),
                })
            else:
                info.append({
                    "code": "VF_WRAP_I_INTERFACE_INPUT_UNUSED",
                    "severity": "info",
                    "message": (
                        f"Interface input {iface_port.name!r}[{hi}:{lo}] is not consumed "
                        f"by any IP port."
                    ),
                })

    # Unmapped IP ports
    unmapped_ip_ports: list[str] = []
    for name, direction, _w in ip_ports:
        if name not in mapped_ip_ports:
            unmapped_ip_ports.append(name)
            if direction == "input":
                info.append({
                    "code": "VF_WRAP_I_IP_INPUT_UNMAPPED",
                    "severity": "info",
                    "message": f"IP input {name!r} is unmapped; will be tied to 1'b0.",
                })
            else:
                info.append({
                    "code": "VF_WRAP_I_IP_OUTPUT_UNMAPPED",
                    "severity": "info",
                    "message": f"IP output {name!r} is unmapped; will be left unconnected.",
                })

    return WrapValidationResult(
        status="FAIL" if errors else "PASS",
        errors=errors,
        info=info,
        mapped=mapped,
        unmapped_ip_ports=unmapped_ip_ports,
        unmapped_interface_ports=unmapped_interface_ports,
    )
