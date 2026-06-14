"""
port_parser.py — Verilog port extraction using regex.

Handles ANSI-style module declarations (the most common in modern Verilog):
    input  wire [N:0] port_name,
    output reg        port_name,
    input             port_name

Returns (name, direction, width) tuples:
  - direction is lowercase "input"/"output"/"inout".
  - width is an int when the bus expression is purely numeric ([hi:lo] with
    integer hi/lo); 1 for scalar ports (no bus expression); None when the
    expression contains parameters or other non-numeric tokens (e.g. [W-1:0]).
"""

import re
from typing import List, Optional, Tuple


_PORT_RE = re.compile(
    r"\b(input|output|inout)\b"
    r"(?:\s+(?:wire|reg|logic))?"
    r"(?:\s*(\[[\w\s:+-]+\]))?"   # group 2: optional bus expression
    r"\s+([\w]+)"                  # group 3: port name
    r"\s*[,;)\n]",
    re.IGNORECASE,
)

_BUS_RE = re.compile(r"^\[\s*(\d+)\s*:\s*(\d+)\s*\]$")


def _parse_width(bus_expr: Optional[str]) -> Optional[int]:
    """Return port width from a bus expression string, or None if unresolvable.

    Returns 1 for scalar ports (bus_expr is None).
    Returns hi - lo + 1 (absolute) when bus_expr is a purely numeric [hi:lo].
    Returns None when bus_expr contains parameters or other non-integer tokens.
    """
    if bus_expr is None:
        return 1
    m = _BUS_RE.match(bus_expr.strip())
    if m:
        return abs(int(m.group(1)) - int(m.group(2))) + 1
    return None


def extract_ports(verilog_source: str, top_module: str) -> List[Tuple[str, str, Optional[int]]]:
    """Return a list of (name, direction, width) tuples from *top_module*.

    direction is one of "input", "output", "inout" (lowercase).
    width follows the rules in _parse_width above.
    Raises ValueError if the module declaration is not found.
    """
    pattern = re.compile(
        r"\bmodule\s+" + re.escape(top_module) + r"\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(verilog_source)
    if not m:
        raise ValueError(f"Module '{top_module}' not found in source.")

    header_body = m.group(1)

    ports: List[Tuple[str, str, Optional[int]]] = []
    seen: set = set()
    for pm in _PORT_RE.finditer(header_body):
        direction = pm.group(1).lower()
        bus_expr = pm.group(2)
        name = pm.group(3)
        if name not in seen:
            seen.add(name)
            ports.append((name, direction, _parse_width(bus_expr)))

    if not ports:
        module_body_pat = re.compile(
            r"\bmodule\s+" + re.escape(top_module) + r"\b.*?endmodule",
            re.DOTALL | re.IGNORECASE,
        )
        bm = module_body_pat.search(verilog_source)
        if bm:
            for pm in _PORT_RE.finditer(bm.group(0)):
                direction = pm.group(1).lower()
                bus_expr = pm.group(2)
                name = pm.group(3)
                if name not in seen:
                    seen.add(name)
                    ports.append((name, direction, _parse_width(bus_expr)))

    return ports
