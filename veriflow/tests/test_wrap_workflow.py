"""Tests for veriflow.workflows.wrap.WrapWorkflow."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from veriflow.core import VeriFlowError
from veriflow.core.backends.base import ConnectivityBackend
from veriflow.workflows.wrap import WrapWorkflow, _serialize_bits, _serialize_slice

# ── Fixtures ──────────────────────────────────────────────────────────────────

# Minimal 4-port DUT matching the semicolab test mapping
_DUT_V = """\
module my_dut (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire [15:0] data_i,
    output wire  [7:0] result_o
);
endmodule
"""

# Valid port mapping — all ports with matching widths
_VALID_PORTS = {
    "clk_i":    "clk",
    "rst_ni":   "arst_n",
    "data_i":   "csr_in[15:0]",
    "result_o": "csr_out[7:0]",
}


class _FakeBackend(ConnectivityBackend):
    """Stub connectivity backend for unit tests."""

    def __init__(self, status: str = "PASS") -> None:
        self._status = status

    def run_connectivity(self, rtl_files, interface_profile, top_module, log_path):
        log_path.write_text(f"fake connectivity: {self._status}", encoding="utf-8")
        return self._status

    def check_availability(self) -> list[dict]:
        return []


def _write_config(
    directory: Path,
    *,
    ports: dict | None = None,
    top_module: str = "my_dut",
    rtl_sources: list[str] | None = None,
    wrapper_name: str | None = None,
) -> Path:
    if rtl_sources is None:
        # default: defs.v first (no module), then my_dut.v (has module) → tests P3 search
        rtl_sources = ["defs.v", "my_dut.v"]
    if ports is None:
        ports = _VALID_PORTS
    cfg: dict = {
        "interface_name": "semicolab",
        "metadata": {"name": top_module},
        "design": {
            "top_module": top_module,
            "rtl_sources": rtl_sources,
        },
        "ports": dict(ports),
    }
    if wrapper_name is not None:
        cfg["wrapper_name"] = wrapper_name
    config_path = directory / "wrapper_config.yaml"
    config_path.write_text(yaml.dump(cfg), encoding="utf-8")
    return config_path


@pytest.fixture
def dut_dir(tmp_path: Path) -> Path:
    """Temp directory with defs.v (no module) and my_dut.v (has module)."""
    # defs.v: a valid Verilog file that does NOT contain module my_dut
    (tmp_path / "defs.v").write_text("`define DATA_WIDTH 16\n", encoding="utf-8")
    (tmp_path / "my_dut.v").write_text(_DUT_V, encoding="utf-8")
    return tmp_path


# ── Serialization helpers ─────────────────────────────────────────────────────

def test_serialize_slice_full_port():
    assert _serialize_slice(None, None) is None


def test_serialize_slice_single_bit():
    assert _serialize_slice(3, 3) == "3"


def test_serialize_slice_range():
    assert _serialize_slice(15, 0) == "15:0"
    assert _serialize_slice(7, 4) == "7:4"


def test_serialize_bits_range():
    assert _serialize_bits(31, 0) == "31:0"
    assert _serialize_bits(0, 0) == "0:0"


# ── PASS path (fake backend) ──────────────────────────────────────────────────

def test_generate_pass_returns_dict(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert isinstance(result, dict)


def test_generate_pass_status(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert result["status"] == "PASS"


def test_generate_pass_schema_keys(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    for key in ("schema_version", "status", "command", "interface_name",
                "wrapper", "rtl_sources", "ports", "messages",
                "validation", "connectivity_check"):
        assert key in result, f"missing key: {key}"


def test_generate_pass_wrapper_file_created(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert (out_dir / "rtl" / "my_dut_wrapper.v").exists()


def test_generate_pass_rtl_copied(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert (out_dir / "rtl" / "defs.v").exists()
    assert (out_dir / "rtl" / "my_dut.v").exists()


def test_generate_pass_log_written(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert (out_dir / "logs" / "connectivity.log").exists()


def test_generate_pass_json_written(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert (out_dir / "my_dut_wrapper.json").exists()


def test_generate_pass_json_parseable(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    doc = json.loads((out_dir / "my_dut_wrapper.json").read_text(encoding="utf-8"))
    assert doc["status"] == "PASS"


def test_generate_pass_command_field(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert result["command"] == "wrap generate"


def test_generate_pass_interface_name(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert result["interface_name"] == "semicolab"


def test_generate_pass_wrapper_fields(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    w = result["wrapper"]
    assert w["name"] == "my_dut_wrapper"
    assert w["top_module"] == "my_dut"
    assert w["file"] == "rtl/my_dut_wrapper.v"


def test_generate_pass_rtl_sources_relative(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert result["rtl_sources"] == ["rtl/defs.v", "rtl/my_dut.v"]


def test_generate_pass_validation_status(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert result["validation"]["status"] == "PASS"


def test_generate_pass_connectivity_check_fields(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    cc = result["connectivity_check"]
    assert cc is not None
    assert cc["status"] == "PASS"
    assert cc["log"] == "logs/connectivity.log"


# ── P4 — slice/bits serialization ────────────────────────────────────────────

def test_p4_full_port_slice_is_null(dut_dir, tmp_path):
    # clk_i → clk is a full-port mapping → slice must be null (None)
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    clk_entry = next(m for m in result["ports"]["mapped"] if m["ip_port"] == "clk_i")
    assert clk_entry["slice"] is None


def test_p4_explicit_slice_serialized(dut_dir, tmp_path):
    # data_i → csr_in[15:0] → slice must be "15:0"
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    data_entry = next(m for m in result["ports"]["mapped"] if m["ip_port"] == "data_i")
    assert data_entry["slice"] == "15:0"


def test_p4_unmapped_iface_ports_have_bits(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    for u in result["ports"]["unmapped_interface_ports"]:
        assert "bits" in u
        assert ":" in u["bits"]  # always "hi:lo" format


def test_p4_mapped_entries_no_hi_lo(dut_dir, tmp_path):
    # The JSON output must not expose internal hi/lo keys
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    for m in result["ports"]["mapped"]:
        assert "hi" not in m
        assert "lo" not in m


# ── P3 — multi-file RTL search ────────────────────────────────────────────────

def test_p3_module_found_in_second_file(dut_dir, tmp_path):
    # defs.v is listed first and does NOT contain module my_dut;
    # my_dut.v is listed second and DOES — workflow should still find it.
    config_path = _write_config(dut_dir, rtl_sources=["defs.v", "my_dut.v"])
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert result["status"] == "PASS"


def test_p3_module_found_in_first_file(dut_dir, tmp_path):
    # When listed first, my_dut.v is found immediately.
    config_path = _write_config(dut_dir, rtl_sources=["my_dut.v", "defs.v"])
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert result["status"] == "PASS"


# ── Validation FAIL path ──────────────────────────────────────────────────────

def test_validation_fail_no_wrapper_v(dut_dir, tmp_path):
    # Bit conflict → validation FAIL → wrapper.v must NOT be written
    conflict_ports = {
        "clk_i":  "csr_in[7:0]",
        "rst_ni": "csr_in[7:0]",   # same bits → conflict
    }
    config_path = _write_config(dut_dir, ports=conflict_ports)
    out_dir = tmp_path / "out"
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert result["status"] == "FAIL"
    assert not (out_dir / "rtl" / "my_dut_wrapper.v").exists()


def test_validation_fail_json_written(dut_dir, tmp_path):
    conflict_ports = {"clk_i": "csr_in[7:0]", "rst_ni": "csr_in[7:0]"}
    config_path = _write_config(dut_dir, ports=conflict_ports)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert (out_dir / "my_dut_wrapper.json").exists()


def test_validation_fail_json_status(dut_dir, tmp_path):
    conflict_ports = {"clk_i": "csr_in[7:0]", "rst_ni": "csr_in[7:0]"}
    config_path = _write_config(dut_dir, ports=conflict_ports)
    out_dir = tmp_path / "out"
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert result["validation"]["status"] == "FAIL"
    assert result["connectivity_check"] is None


def test_validation_fail_no_rtl_copied(dut_dir, tmp_path):
    conflict_ports = {"clk_i": "csr_in[7:0]", "rst_ni": "csr_in[7:0]"}
    config_path = _write_config(dut_dir, ports=conflict_ports)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert not (out_dir / "rtl").exists()


def test_validation_fail_messages_contain_errors(dut_dir, tmp_path):
    conflict_ports = {"clk_i": "csr_in[7:0]", "rst_ni": "csr_in[7:0]"}
    config_path = _write_config(dut_dir, ports=conflict_ports)
    result = WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    codes = {m["code"] for m in result["messages"]}
    assert "VF_WRAP_E_BIT_CONFLICT" in codes


# ── Connectivity FAIL path ────────────────────────────────────────────────────

def test_connectivity_fail_status(dut_dir, tmp_path):
    # Backend returns FAIL → root status must be FAIL, wrapper.v still written
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    result = WrapWorkflow(_FakeBackend("FAIL")).generate(config_path, out_dir)
    assert result["status"] == "FAIL"
    assert result["connectivity_check"]["status"] == "FAIL"


def test_connectivity_fail_wrapper_v_written(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("FAIL")).generate(config_path, out_dir)
    assert (out_dir / "rtl" / "my_dut_wrapper.v").exists()


def test_connectivity_fail_rtl_copied(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    out_dir = tmp_path / "out"
    WrapWorkflow(_FakeBackend("FAIL")).generate(config_path, out_dir)
    assert (out_dir / "rtl" / "my_dut.v").exists()


def test_connectivity_fail_validation_still_pass(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    result = WrapWorkflow(_FakeBackend("FAIL")).generate(config_path, tmp_path / "out")
    assert result["validation"]["status"] == "PASS"


# ── VF_WRAP_E_TOP_MODULE_NOT_FOUND ───────────────────────────────────────────

def test_top_module_not_found_raises(dut_dir, tmp_path):
    config_path = _write_config(dut_dir, top_module="ghost_module")
    with pytest.raises(VeriFlowError) as exc_info:
        WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert exc_info.value.code == "VF_WRAP_E_TOP_MODULE_NOT_FOUND"


def test_top_module_not_found_details(dut_dir, tmp_path):
    config_path = _write_config(dut_dir, top_module="ghost_module")
    with pytest.raises(VeriFlowError) as exc_info:
        WrapWorkflow(_FakeBackend("PASS")).generate(config_path, tmp_path / "out")
    assert exc_info.value.details is not None
    assert "ghost_module" in str(exc_info.value.details)


def test_top_module_not_found_no_output(dut_dir, tmp_path):
    config_path = _write_config(dut_dir, top_module="ghost_module")
    out_dir = tmp_path / "out"
    with pytest.raises(VeriFlowError):
        WrapWorkflow(_FakeBackend("PASS")).generate(config_path, out_dir)
    assert not (out_dir / "ghost_module_wrapper.json").exists()


# ── out_dir defaults ──────────────────────────────────────────────────────────

def test_out_dir_defaults_to_out_subdir(dut_dir):
    config_path = _write_config(dut_dir)
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path)  # no out_dir
    # All output must go into wrap_out/ — nothing loose in the config directory
    assert (dut_dir / "wrap_out" / "my_dut_wrapper.json").exists()
    assert not (dut_dir / "my_dut_wrapper.json").exists()


def test_out_dir_default_wrapper_v_in_rtl_subdir(dut_dir):
    config_path = _write_config(dut_dir)
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path)
    assert (dut_dir / "wrap_out" / "rtl" / "my_dut_wrapper.v").exists()
    assert not (dut_dir / "wrap_out" / "my_dut_wrapper.v").exists()
    assert not (dut_dir / "my_dut_wrapper.v").exists()


def test_out_dir_default_rtl_in_out_subdir(dut_dir):
    config_path = _write_config(dut_dir)
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path)
    assert (dut_dir / "wrap_out" / "rtl" / "my_dut.v").exists()


def test_out_dir_default_log_in_out_subdir(dut_dir):
    config_path = _write_config(dut_dir)
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path)
    assert (dut_dir / "wrap_out" / "logs" / "connectivity.log").exists()


def test_out_dir_explicit_arg_overrides_default(dut_dir, tmp_path):
    config_path = _write_config(dut_dir)
    custom_out = tmp_path / "custom_out"
    WrapWorkflow(_FakeBackend("PASS")).generate(config_path, custom_out)
    assert (custom_out / "my_dut_wrapper.json").exists()
    assert not (dut_dir / "wrap_out").exists()


# ── iverilog smoke test ───────────────────────────────────────────────────────

def _iverilog_functional() -> bool:
    if shutil.which("iverilog") is None:
        return False
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "t.v"
        o = Path(td) / "t.vvp"
        f.write_text("module m; endmodule", encoding="utf-8")
        r = subprocess.run(["iverilog", "-o", o.as_posix(), f.as_posix()], capture_output=True)
        return r.returncode == 0


_IVERILOG_OK = _iverilog_functional()


@pytest.mark.skipif(not _IVERILOG_OK, reason="iverilog not functional in this environment")
def test_generate_real_connectivity_pass(dut_dir, tmp_path):
    """Full integration test: real iverilog connectivity check must pass."""
    config_path = _write_config(dut_dir, rtl_sources=["my_dut.v"])
    out_dir = tmp_path / "out"
    result = WrapWorkflow().generate(config_path, out_dir)
    assert result["status"] == "PASS"
    assert result["connectivity_check"]["status"] == "PASS"


@pytest.mark.skipif(not _IVERILOG_OK, reason="iverilog not functional in this environment")
def test_generate_real_connectivity_log_written(dut_dir, tmp_path):
    config_path = _write_config(dut_dir, rtl_sources=["my_dut.v"])
    out_dir = tmp_path / "out"
    WrapWorkflow().generate(config_path, out_dir)
    assert (out_dir / "logs" / "connectivity.log").exists()
