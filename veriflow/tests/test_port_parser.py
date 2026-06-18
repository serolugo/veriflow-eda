"""Regression tests for veriflow.core.wrapper.port_parser.

Covers edge cases that are NOT exercised by test_wrap_generator.py:
  - Column-aligned declarations with multiple spaces between tokens
  - No space between bus expression and port name  ([7:0]count)
  - signed / unsigned type qualifiers
  - wire signed combined qualifier
  - Parametric bus expressions (width -> None)
"""

from __future__ import annotations

import pytest

from veriflow.core.wrapper.port_parser import extract_ports, _parse_width


# ── _parse_width unit tests ────────────────────────────────────────────────────

def test_parse_width_none_for_scalar():
    assert _parse_width(None) == 1


def test_parse_width_simple_bus():
    assert _parse_width("[7:0]") == 8


def test_parse_width_asymmetric_bus():
    assert _parse_width("[15:0]") == 16


def test_parse_width_reversed_bus():
    assert _parse_width("[0:7]") == 8


def test_parse_width_parametric_returns_none():
    assert _parse_width("[W-1:0]") is None


def test_parse_width_internal_spaces():
    assert _parse_width("[ 7 : 0 ]") == 8


# ── counter8_top.v: exact regression fixtures ─────────────────────────────────

# Exact minimal snippet used for the original bug reproduction (step-1 snippet).
# DO NOT expand this fixture — the bug was count=None specifically in this
# 5-port, column-aligned, header-only form.
_COUNTER8_V = """\
module counter8_top (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    output wire [7:0] count,
    output wire       wrapped
);
endmodule
"""

# Same module with full implementation body — verifies the header regex
# correctly stops at the first ); even when the body contains instantiations
# with their own parentheses and bus expressions.
_COUNTER8_FULL_V = """\
module counter8_top (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    output wire [7:0] count,
    output wire       wrapped
);

    reg [7:0] count_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count_reg <= 8'd0;
        else if (enable)
            count_reg <= count_reg + 1'b1;
    end

    assign count = count_reg;

    edge_detector u_wrap_detect (
        .clk         (clk),
        .rst_n       (rst_n),
        .sig_in      (count_reg[7]),
        .rising_edge (wrapped)
    );

endmodule
"""

_COUNTER8_EXPECTED = [
    ("clk",     "input",  1),
    ("rst_n",   "input",  1),
    ("enable",  "input",  1),
    ("count",   "output", 8),
    ("wrapped", "output", 1),
]


# Tests on the exact minimal reproduction snippet (step-1 form)
def test_counter8_all_ports_detected():
    ports = extract_ports(_COUNTER8_V, "counter8_top")
    assert ports == _COUNTER8_EXPECTED


def test_counter8_count_width_is_8():
    """Regression: count must not be reported as width=None (aka '?')."""
    ports = extract_ports(_COUNTER8_V, "counter8_top")
    count = next(p for p in ports if p[0] == "count")
    assert count[2] == 8, f"count width should be 8, got {count[2]!r}"


def test_counter8_port_count():
    ports = extract_ports(_COUNTER8_V, "counter8_top")
    assert len(ports) == 5


# Tests on the full-body form — ensures body content doesn't pollute header parse
def test_counter8_full_body_all_ports_detected():
    ports = extract_ports(_COUNTER8_FULL_V, "counter8_top")
    assert ports == _COUNTER8_EXPECTED


def test_counter8_full_body_count_width_is_8():
    """Regression (full body): header regex must stop at first ); and not bleed into body."""
    ports = extract_ports(_COUNTER8_FULL_V, "counter8_top")
    count = next(p for p in ports if p[0] == "count")
    assert count[2] == 8, f"count width should be 8, got {count[2]!r}"


# ── Edge cases: spacing robustness ────────────────────────────────────────────

_NO_SPACE_AFTER_BUS_V = """\
module no_space (
    output wire [7:0]count,
    input  wire [3:0]data
);
endmodule
"""


def test_no_space_between_bus_and_port_name():
    """[7:0]count with zero spaces must still be detected."""
    ports = extract_ports(_NO_SPACE_AFTER_BUS_V, "no_space")
    names = [p[0] for p in ports]
    assert "count" in names
    assert "data" in names


def test_no_space_bus_width_correct():
    ports = extract_ports(_NO_SPACE_AFTER_BUS_V, "no_space")
    count = next(p for p in ports if p[0] == "count")
    assert count[2] == 8
    data = next(p for p in ports if p[0] == "data")
    assert data[2] == 4


# ── Edge cases: signed / unsigned type qualifier ───────────────────────────────

_SIGNED_V = """\
module signed_dut (
    output signed       [7:0] val_s,
    output wire signed  [7:0] val_ws,
    output unsigned     [3:0] val_u,
    input  wire               clk
);
endmodule
"""


def test_signed_qualifier_detected():
    ports = extract_ports(_SIGNED_V, "signed_dut")
    names = [p[0] for p in ports]
    assert "val_s" in names
    assert "val_ws" in names
    assert "val_u" in names
    assert "clk" in names


def test_signed_qualifier_width_correct():
    ports = extract_ports(_SIGNED_V, "signed_dut")
    val_s = next(p for p in ports if p[0] == "val_s")
    assert val_s[2] == 8
    val_ws = next(p for p in ports if p[0] == "val_ws")
    assert val_ws[2] == 8
    val_u = next(p for p in ports if p[0] == "val_u")
    assert val_u[2] == 4


# ── Edge cases: parametric bus ────────────────────────────────────────────────

_PARAMETRIC_V = """\
module param_dut #(parameter W = 8) (
    input  wire [W-1:0] data_i,
    output wire [W-1:0] data_o
);
endmodule
"""


def test_parametric_bus_width_is_none():
    ports = extract_ports(_PARAMETRIC_V, "param_dut")
    data_i = next(p for p in ports if p[0] == "data_i")
    assert data_i[2] is None
    data_o = next(p for p in ports if p[0] == "data_o")
    assert data_o[2] is None
