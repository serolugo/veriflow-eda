import re


def parse_sim_log(log_text: str) -> dict:
    """
    Parse iverilog/vvp simulation log.
    Returns dict with sim_time and seed.
    """
    sim_time = ""
    seed = ""

    # iverilog: "$finish called at 335000 (1ps)"
    m = re.search(r"\$finish called at (\d+)\s*\((\w+)\)", log_text)
    if m:
        raw_time = int(m.group(1))
        unit = m.group(2)
        # Convert to ns
        unit_to_ns = {"1ps": 0.001, "ps": 0.001, "ns": 1, "us": 1000, "ms": 1000000}
        factor = unit_to_ns.get(unit, 1)
        val = raw_time * factor
        sim_time = f"{val:.3f}".rstrip("0").rstrip(".") + " ns"

    # seed pattern
    m = re.search(r"seed[^\d]*(\d+)", log_text, re.IGNORECASE)
    if m:
        seed = m.group(1).strip()

    return {"sim_time": sim_time, "seed": seed}


def parse_synth_log(log_text: str) -> dict:
    """
    Parse Yosys synthesis log.
    Returns dict with cells, warnings, errors, has_latches.

    Yosys stat output format:
       253 cells
    """
    cells = ""
    warnings = 0
    errors = 0
    has_latches = False

    # Yosys: "      253 cells"  (indented number followed by "cells")
    # Take the LAST occurrence (final stat block)
    matches = re.findall(r"^\s+(\d+) cells\s*$", log_text, re.MULTILINE)
    if matches:
        cells = matches[-1]

    # Warnings
    warnings = len(re.findall(r"^\s*Warning:", log_text, re.MULTILINE | re.IGNORECASE))

    # Errors
    errors = len(re.findall(r"^\s*Error:", log_text, re.MULTILINE | re.IGNORECASE))

    # Inferred latches. Anchored to line start (past optional whitespace) so
    # this doesn't false-positive on Yosys's normal, non-buggy
    # "No latch inferred for signal ..." message (an unanchored substring
    # search matches "latch inferred" inside "No latch inferred" too).
    if re.search(r"^\s*Latch inferred", log_text, re.IGNORECASE | re.MULTILINE):
        has_latches = True

    return {
        "cells": cells,
        "warnings": str(warnings),
        "errors": str(errors),
        "has_latches": has_latches,
    }


def parse_iverilog_version(version_output: str) -> str:
    """Parse the version string from `iverilog -V` output."""
    m = re.search(r"Icarus Verilog version\s+([\d.]+)", version_output, re.IGNORECASE)
    if m:
        return m.group(1)
    first_line = version_output.strip().splitlines()[0] if version_output.strip() else ""
    return first_line
