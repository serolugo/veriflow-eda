"""Tests for veriflow.core.wrapper.validator."""

from __future__ import annotations

import pytest

from veriflow.core.wrapper.validator import WrapValidationResult, validate_mapping
from veriflow.models.interface_profile import get_interface_profile
from veriflow.models.wrapper_config import WrapperConfig

SEMICOLAB = get_interface_profile("semicolab")

# 4-port DUT fixture — (name, direction, width)
_DUT_PORTS = [
    ("clk_i",    "input",  1),    # scalar
    ("rst_ni",   "input",  1),    # scalar
    ("data_i",   "input",  16),   # 16-bit
    ("result_o", "output", 8),    # 8-bit
]

# Full valid mapping: all DUT ports mapped, no width mismatches
_VALID_PORTS = {
    "clk_i":    "clk",           # 1-bit → clk (1-bit)
    "rst_ni":   "arst_n",        # 1-bit → arst_n (1-bit)
    "data_i":   "csr_in[15:0]",  # 16-bit → csr_in[15:0] (16-bit)
    "result_o": "csr_out[7:0]",  # 8-bit → csr_out[7:0] (8-bit)
}


def _make_config(ports: dict | None = None) -> WrapperConfig:
    return WrapperConfig.from_dict({
        "interface_name": "semicolab",
        "metadata": {"name": "my_dut"},
        "design": {"top_module": "my_dut", "rtl_sources": ["my_dut.v"]},
        "ports": ports if ports is not None else _VALID_PORTS,
    })


# ── Valid / PASS cases ────────────────────────────────────────────────────────

def test_valid_mapping_passes():
    result = validate_mapping(_make_config(), SEMICOLAB, _DUT_PORTS)
    assert result.status == "PASS"
    assert result.errors == []
    assert len(result.mapped) == 4


def test_valid_mapping_mapped_entries():
    result = validate_mapping(_make_config(), SEMICOLAB, _DUT_PORTS)
    names = {m["ip_port"] for m in result.mapped}
    assert names == {"clk_i", "rst_ni", "data_i", "result_o"}


def test_full_port_mapping_stores_none_slice():
    # clk_i → clk (full, no explicit slice)
    result = validate_mapping(_make_config(), SEMICOLAB, _DUT_PORTS)
    clk_entry = next(m for m in result.mapped if m["ip_port"] == "clk_i")
    assert clk_entry["hi"] is None
    assert clk_entry["lo"] is None


def test_explicit_slice_mapping_stores_hi_lo():
    result = validate_mapping(_make_config(), SEMICOLAB, _DUT_PORTS)
    csr_entry = next(m for m in result.mapped if m["ip_port"] == "data_i")
    assert csr_entry["hi"] == 15
    assert csr_entry["lo"] == 0


def test_valid_mapping_no_width_mismatch_info():
    # _VALID_PORTS maps all ports with matching widths — no VF_WRAP_I_IP_WIDTH_MISMATCH
    result = validate_mapping(_make_config(), SEMICOLAB, _DUT_PORTS)
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_WIDTH_MISMATCH" not in codes


# ── Partial mapping — info messages ──────────────────────────────────────────

def test_partial_mapping_is_pass():
    result = validate_mapping(_make_config({"clk_i": "clk"}), SEMICOLAB, _DUT_PORTS)
    assert result.status == "PASS"


def test_partial_mapping_unmapped_ip_input_info():
    result = validate_mapping(_make_config({"clk_i": "clk"}), SEMICOLAB, _DUT_PORTS)
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_INPUT_UNMAPPED" in codes   # rst_ni, data_i


def test_partial_mapping_unmapped_ip_output_info():
    result = validate_mapping(_make_config({"clk_i": "clk"}), SEMICOLAB, _DUT_PORTS)
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_OUTPUT_UNMAPPED" in codes  # result_o


def test_partial_mapping_unused_interface_input_info():
    result = validate_mapping(_make_config({"clk_i": "clk"}), SEMICOLAB, _DUT_PORTS)
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_INTERFACE_INPUT_UNUSED" in codes


def test_partial_mapping_unmapped_interface_output_info():
    result = validate_mapping(_make_config({"clk_i": "clk"}), SEMICOLAB, _DUT_PORTS)
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_INTERFACE_OUTPUT_UNMAPPED" in codes


def test_partial_mapping_unmapped_ip_ports_list():
    result = validate_mapping(_make_config({"clk_i": "clk"}), SEMICOLAB, _DUT_PORTS)
    assert set(result.unmapped_ip_ports) == {"rst_ni", "data_i", "result_o"}


def test_partial_mapping_unmapped_interface_ports_list():
    # With full mapping, only bits 8-15 of csr_out are unmapped
    result = validate_mapping(_make_config(), SEMICOLAB, _DUT_PORTS)
    unmapped_names = {u["port"] for u in result.unmapped_interface_ports}
    assert "data_reg_c" in unmapped_names
    assert "csr_out" in unmapped_names


# ── Structural errors (VF_WRAP_E*) ───────────────────────────────────────────

def test_E_MAPPING_SYNTAX():
    result = validate_mapping(_make_config({"clk_i": "!!invalid!!"}), SEMICOLAB, _DUT_PORTS)
    assert result.status == "FAIL"
    assert any(e["code"] == "VF_WRAP_E_MAPPING_SYNTAX" for e in result.errors)


def test_E_INTERFACE_PORT_UNKNOWN():
    result = validate_mapping(_make_config({"clk_i": "nonexistent_port"}), SEMICOLAB, _DUT_PORTS)
    assert result.status == "FAIL"
    assert any(e["code"] == "VF_WRAP_E_INTERFACE_PORT_UNKNOWN" for e in result.errors)


def test_E_IP_PORT_UNKNOWN():
    result = validate_mapping(_make_config({"ghost_port": "clk"}), SEMICOLAB, _DUT_PORTS)
    assert result.status == "FAIL"
    assert any(e["code"] == "VF_WRAP_E_IP_PORT_UNKNOWN" for e in result.errors)


def test_E_SLICE_OUT_OF_RANGE():
    # csr_in is 16 bits [15:0]; bit 16 is out of range
    result = validate_mapping(_make_config({"data_i": "csr_in[16:0]"}), SEMICOLAB, _DUT_PORTS)
    assert result.status == "FAIL"
    assert any(e["code"] == "VF_WRAP_E_SLICE_OUT_OF_RANGE" for e in result.errors)


def test_E_SLICE_OUT_OF_RANGE_single_bit():
    # csr_in[16] — single bit out of range
    result = validate_mapping(_make_config({"data_i": "csr_in[16]"}), SEMICOLAB, _DUT_PORTS)
    assert result.status == "FAIL"
    assert any(e["code"] == "VF_WRAP_E_SLICE_OUT_OF_RANGE" for e in result.errors)


def test_E_BIT_CONFLICT():
    result = validate_mapping(
        _make_config({
            "clk_i":  "clk",
            "data_i": "csr_in[7:0]",
            "rst_ni": "csr_in[7:0]",  # same bits → conflict
        }),
        SEMICOLAB,
        _DUT_PORTS,
    )
    assert result.status == "FAIL"
    assert any(e["code"] == "VF_WRAP_E_BIT_CONFLICT" for e in result.errors)


def test_E_BIT_CONFLICT_partial_overlap():
    result = validate_mapping(
        _make_config({
            "clk_i":    "clk",
            "data_i":   "csr_in[7:0]",
            "rst_ni":   "csr_in[4:0]",  # overlaps bits 4-0 with data_i
        }),
        SEMICOLAB,
        _DUT_PORTS,
    )
    assert result.status == "FAIL"
    assert any(e["code"] == "VF_WRAP_E_BIT_CONFLICT" for e in result.errors)


# ── VF_WRAP_I_IP_WIDTH_MISMATCH ──────────────────────────────────────────────

def test_width_mismatch_emits_info():
    # data_i is 16-bit, csr_in[7:0] is 8-bit → mismatch
    result = validate_mapping(
        _make_config({"data_i": "csr_in[7:0]"}),
        SEMICOLAB,
        _DUT_PORTS,
    )
    assert result.status == "PASS"
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_WIDTH_MISMATCH" in codes


def test_width_mismatch_full_port_different_width():
    # result_o is 8-bit mapped to data_reg_c (32-bit full port) → mismatch
    result = validate_mapping(
        _make_config({"result_o": "data_reg_c"}),
        SEMICOLAB,
        _DUT_PORTS,
    )
    assert result.status == "PASS"
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_WIDTH_MISMATCH" in codes


def test_no_width_mismatch_when_widths_match():
    # clk_i (1-bit) → clk (1-bit): no mismatch
    result = validate_mapping(
        _make_config({"clk_i": "clk"}),
        SEMICOLAB,
        _DUT_PORTS,
    )
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_WIDTH_MISMATCH" not in codes


def test_no_width_mismatch_when_ip_width_none():
    # Port with width=None (parametrized) → no message even if slice width differs
    dut_with_param = [("param_port", "input", None)] + list(_DUT_PORTS)
    result = validate_mapping(
        _make_config({"param_port": "csr_in[7:0]"}),
        SEMICOLAB,
        dut_with_param,
    )
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_WIDTH_MISMATCH" not in codes


def test_width_mismatch_does_not_block_generation():
    # Width mismatch is info-only — status must still be PASS
    result = validate_mapping(
        _make_config({"data_i": "csr_in[3:0]"}),  # 16-bit → 4-bit slice
        SEMICOLAB,
        _DUT_PORTS,
    )
    assert result.status == "PASS"
    assert len(result.errors) == 0


def test_width_mismatch_message_mentions_widths():
    result = validate_mapping(
        _make_config({"data_i": "csr_in[7:0]"}),
        SEMICOLAB,
        _DUT_PORTS,
    )
    msg = next(
        m["message"] for m in result.info
        if m["code"] == "VF_WRAP_I_IP_WIDTH_MISMATCH"
    )
    assert "16" in msg   # ip_width
    assert "8" in msg    # slice_width


# ── inout handling ────────────────────────────────────────────────────────────

def test_inout_port_always_emits_info():
    dut_with_inout = list(_DUT_PORTS) + [("bidir", "inout", 1)]
    result = validate_mapping(_make_config(), SEMICOLAB, dut_with_inout)
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_PORT_INOUT_UNSUPPORTED" in codes


def test_inout_port_mapped_still_emits_info():
    dut_with_inout = list(_DUT_PORTS) + [("bidir", "inout", 1)]
    ports = dict(_VALID_PORTS)
    ports["bidir"] = "data_reg_a[0]"
    result = validate_mapping(_make_config(ports), SEMICOLAB, dut_with_inout)
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_PORT_INOUT_UNSUPPORTED" in codes
    assert any(m["ip_port"] == "bidir" for m in result.mapped)


def test_unmapped_inout_treated_as_output():
    dut_with_inout = list(_DUT_PORTS) + [("bidir", "inout", 1)]
    result = validate_mapping(_make_config(), SEMICOLAB, dut_with_inout)
    assert "bidir" in result.unmapped_ip_ports
    codes = {m["code"] for m in result.info}
    assert "VF_WRAP_I_IP_OUTPUT_UNMAPPED" in codes


# ── Multiple errors in one pass ───────────────────────────────────────────────

def test_multiple_errors_all_reported():
    result = validate_mapping(
        _make_config({
            "ghost":   "clk",     # IP port unknown
            "clk_i":  "!!bad!!",  # syntax error
        }),
        SEMICOLAB,
        _DUT_PORTS,
    )
    assert result.status == "FAIL"
    codes = {e["code"] for e in result.errors}
    assert "VF_WRAP_E_IP_PORT_UNKNOWN" in codes
    assert "VF_WRAP_E_MAPPING_SYNTAX" in codes


# ── Empty config.ports ────────────────────────────────────────────────────────

def test_empty_ports_is_pass_with_info():
    result = validate_mapping(_make_config({}), SEMICOLAB, _DUT_PORTS)
    assert result.status == "PASS"
    assert result.mapped == []
    assert len(result.unmapped_ip_ports) == 4
