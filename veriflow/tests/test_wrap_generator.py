"""Tests for veriflow.core.wrapper.generator and port_parser.extract_ports."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from veriflow.core.wrapper.generator import generate_wrapper
from veriflow.core.wrapper.port_parser import extract_ports, _parse_width
from veriflow.core.wrapper.validator import validate_mapping
from veriflow.models.interface_profile import get_interface_profile
from veriflow.models.wrapper_config import WrapperConfig

SEMICOLAB = get_interface_profile("semicolab")

# Minimal RTL fixture — 4 ports of varying widths
_DUT_V = """\
module my_dut (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire [15:0] data_i,
    output wire  [7:0] result_o
);
endmodule
"""

# (name, direction, width) tuples matching _DUT_V
_DUT_PORTS = [
    ("clk_i",    "input",  1),
    ("rst_ni",   "input",  1),
    ("data_i",   "input",  16),
    ("result_o", "output", 8),
]

_PORTS = {
    "clk_i":    "clk",
    "rst_ni":   "arst_n",
    "data_i":   "csr_in[15:0]",
    "result_o": "csr_out[7:0]",
}


def _make_config(ports: dict | None = None) -> WrapperConfig:
    return WrapperConfig.from_dict({
        "interface_name": "semicolab",
        "metadata": {"name": "my_dut"},
        "design": {"top_module": "my_dut", "rtl_sources": ["my_dut.v"]},
        "ports": ports if ports is not None else _PORTS,
    })


def _gen(ports: dict | None = None) -> str:
    cfg = _make_config(ports)
    result = validate_mapping(cfg, SEMICOLAB, _DUT_PORTS)
    assert result.status == "PASS", f"Validation failed: {result.errors}"
    return generate_wrapper(cfg, SEMICOLAB, result, _DUT_PORTS)


# ── port_parser.extract_ports width extraction ────────────────────────────────

def test_extract_ports_scalar_width_is_1():
    ports = extract_ports(_DUT_V, "my_dut")
    clk = next(p for p in ports if p[0] == "clk_i")
    assert clk[2] == 1


def test_extract_ports_numeric_bus_width():
    ports = extract_ports(_DUT_V, "my_dut")
    data = next(p for p in ports if p[0] == "data_i")
    assert data[2] == 16


def test_extract_ports_output_bus_width():
    ports = extract_ports(_DUT_V, "my_dut")
    out = next(p for p in ports if p[0] == "result_o")
    assert out[2] == 8


def test_extract_ports_parametrized_width_is_none():
    src = """\
module param_dut #(parameter W = 8) (
    input wire [W-1:0] data_in,
    output wire        valid_o
);
endmodule
"""
    ports = extract_ports(src, "param_dut")
    data = next(p for p in ports if p[0] == "data_in")
    assert data[2] is None


def test_extract_ports_returns_direction():
    ports = extract_ports(_DUT_V, "my_dut")
    by_name = {p[0]: p[1] for p in ports}
    assert by_name["clk_i"] == "input"
    assert by_name["rst_ni"] == "input"
    assert by_name["data_i"] == "input"
    assert by_name["result_o"] == "output"


def test_parse_width_scalar():
    assert _parse_width(None) == 1


def test_parse_width_numeric_bus():
    assert _parse_width("[15:0]") == 16
    assert _parse_width("[31:0]") == 32
    assert _parse_width("[0:0]") == 1
    assert _parse_width("[7:4]") == 4


def test_parse_width_reversed_range():
    # Verilog allows [0:N-1] but it's uncommon; abs() ensures correct count
    assert _parse_width("[0:7]") == 8


def test_parse_width_parametrized_returns_none():
    assert _parse_width("[W-1:0]") is None
    assert _parse_width("[WIDTH:0]") is None
    assert _parse_width("[N:0]") is None


# ── Basic structure ───────────────────────────────────────────────────────────

def test_generate_returns_non_empty_string():
    src = _gen()
    assert isinstance(src, str)
    assert len(src) > 0


def test_wrapper_module_declaration():
    src = _gen()
    assert "module my_dut_wrapper" in src


def test_endmodule_present():
    src = _gen()
    assert "endmodule" in src


def test_all_interface_ports_declared():
    src = _gen()
    for port in SEMICOLAB.ports:
        assert port.name in src


def test_bus_port_has_width_in_declaration():
    src = _gen()
    assert "[15:0] csr_in" in src
    assert "[31:0] data_reg_a" in src


def test_scalar_port_has_no_width_in_declaration():
    src = _gen()
    assert "input wire clk" in src
    assert "[0:0] clk" not in src


# ── Instantiation ─────────────────────────────────────────────────────────────

def test_top_module_instantiated():
    src = _gen()
    assert "my_dut u_my_dut" in src


def test_mapped_ports_connected():
    src = _gen()
    assert ".clk_i(clk)" in src
    assert ".rst_ni(arst_n)" in src
    assert ".data_i(csr_in[15:0])" in src
    assert ".result_o(csr_out[7:0])" in src


def test_unmapped_input_tied_to_zero():
    src = _gen(ports={})
    assert ".clk_i(1'b0)" in src
    assert ".rst_ni(1'b0)" in src
    assert ".data_i(1'b0)" in src


def test_unmapped_output_left_unconnected():
    src = _gen(ports={})
    assert ".result_o()" in src


# ── Assign statements ─────────────────────────────────────────────────────────

def test_unmapped_scalar_output_gets_assign():
    src = _gen()
    assert "assign csr_in_re = 1'b0;" in src
    assert "assign csr_out_we = 1'b0;" in src


def test_unmapped_bus_output_gets_assign():
    src = _gen()
    assert "assign data_reg_c[31:0] = 32'b0;" in src


def test_partial_unmapped_bus_output_assign():
    src = _gen()
    assert "assign csr_out[15:8] = 8'b0;" in src


def test_unmapped_input_no_assign():
    src = _gen()
    assert "assign data_reg_a" not in src
    assert "assign data_reg_b" not in src


# ── Header comment ────────────────────────────────────────────────────────────

def test_header_contains_wrapper_name():
    src = _gen()
    assert "my_dut_wrapper" in src.split("module")[0]


def test_header_contains_interface_name():
    src = _gen()
    assert "semicolab" in src.split("module")[0]


# ── iverilog smoke test ───────────────────────────────────────────────────────

def _iverilog_functional() -> bool:
    """Return True only if iverilog can actually compile (not just print -V)."""
    if shutil.which("iverilog") is None:
        return False
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "t.v"
        o = Path(td) / "t.vvp"
        f.write_text("module m; endmodule", encoding="utf-8")
        r = subprocess.run(
            ["iverilog", "-o", o.as_posix(), f.as_posix()],
            capture_output=True,
        )
        return r.returncode == 0


_IVERILOG_OK = _iverilog_functional()


def _iverilog_compile(src: str, extra_v: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        wrapper_path = Path(td) / "my_dut_wrapper.v"
        dut_path = Path(td) / "my_dut.v"
        out_path = Path(td) / "out.vvp"
        wrapper_path.write_text(src, encoding="utf-8")
        dut_path.write_text(extra_v, encoding="utf-8")
        return subprocess.run(
            [
                "iverilog",
                "-o", out_path.as_posix(),
                wrapper_path.as_posix(),
                dut_path.as_posix(),
            ],
            capture_output=True,
            text=True,
        )


@pytest.mark.skipif(not _IVERILOG_OK, reason="iverilog not functional in this environment")
def test_generated_wrapper_compiles():
    proc = _iverilog_compile(_gen(), _DUT_V)
    assert proc.returncode == 0, f"iverilog stderr:\n{proc.stderr}"


@pytest.mark.skipif(not _IVERILOG_OK, reason="iverilog not functional in this environment")
def test_partial_mapping_compiles():
    proc = _iverilog_compile(_gen(ports={"clk_i": "clk"}), _DUT_V)
    assert proc.returncode == 0, f"iverilog stderr:\n{proc.stderr}"
