"""Tests for veriflow.commands.wrap_wizard (cmd_wrap_wizard)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest
import yaml

import veriflow.api as _vf_api


# ── Fixtures ──────────────────────────────────────────────────────────────────

_DUT_V = """\
module my_dut (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire [15:0] data_i,
    output wire  [7:0] result_o
);
endmodule
"""

_DEFS_V = "`define DATA_WIDTH 16\n"


@pytest.fixture
def dut_dir(tmp_path: Path) -> Path:
    """Temp dir with defs.v (no module) and my_dut.v (has module)."""
    (tmp_path / "defs.v").write_text(_DEFS_V, encoding="utf-8")
    (tmp_path / "my_dut.v").write_text(_DUT_V, encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake_pass_result() -> dict:
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "command": "wrap generate",
        "interface_name": "semicolab",
        "wrapper": {"name": "my_dut_wrapper", "top_module": "my_dut", "file": "my_dut_wrapper.v"},
        "rtl_sources": ["rtl/my_dut.v"],
        "ports": {"mapped": [], "unmapped_ip_ports": [], "unmapped_interface_ports": []},
        "messages": [],
        "validation": {"status": "PASS"},
        "connectivity_check": {"status": "PASS", "log": "logs/connectivity.log"},
    }


@pytest.fixture
def fake_fail_result() -> dict:
    return {
        "schema_version": "1.0",
        "status": "FAIL",
        "command": "wrap generate",
        "interface_name": "semicolab",
        "wrapper": {"name": "my_dut_wrapper", "top_module": "my_dut", "file": None},
        "rtl_sources": ["my_dut.v"],
        "ports": {"mapped": [], "unmapped_ip_ports": [], "unmapped_interface_ports": []},
        "messages": [
            {"code": "VF_WRAP_E_MAPPING_SYNTAX", "severity": "error", "message": "bad mapping"}
        ],
        "validation": {"status": "FAIL"},
        "connectivity_check": None,
    }


def _make_args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(force=kwargs.get("force", False))


def _responses_iter(responses: list[str]) -> Iterator[str]:
    """Iterator that raises a clear error if the wizard asks for more input than expected."""
    yield from responses
    while True:
        raise AssertionError(
            f"Wizard asked for more input than expected "
            f"({len(responses)} responses were supplied)"
        )


def _run_wizard(responses: list[str], args=None) -> int:
    from veriflow.commands.wrap_wizard import cmd_wrap_wizard
    return cmd_wrap_wizard(args or _make_args())


# ── iverilog guard ────────────────────────────────────────────────────────────

def _iverilog_functional() -> bool:
    try:
        r = subprocess.run(
            ["iverilog", "-o", "/dev/null", "-"],
            input=b"module _probe; endmodule\n",
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


_IVERILOG_OK = _iverilog_functional()


# ── full flow (mocked generate) ───────────────────────────────────────────────

def test_wizard_full_flow_returns_0(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1",                           # interface: semicolab
        "my_dut",                      # top module
        str(dut_dir / "my_dut.v"),     # rtl source
        "",                            # end rtl sources
        "",                            # clk_i: unmapped
        "",                            # rst_ni: unmapped
        "",                            # data_i: unmapped
        "",                            # result_o: unmapped
        "",                            # metadata name (default)
        "",                            # author
        "",                            # description
        "",                            # version
        "",                            # wrapper_name (default)
        str(config_path),              # config file
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args())
    assert rc == 0


def test_wizard_full_flow_writes_yaml(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",               # 4 unmapped ports
        "", "", "", "",               # metadata defaults
        "",                           # wrapper_name default
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    assert config_path.exists()


def test_wizard_full_flow_yaml_interface_name(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert doc["interface_name"] == "semicolab"


def test_wizard_full_flow_yaml_top_module(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert doc["design"]["top_module"] == "my_dut"


def test_wizard_full_flow_yaml_port_keys(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert set(doc["ports"].keys()) == {"clk_i", "rst_ni", "data_i", "result_o"}


def test_wizard_full_flow_yaml_unmapped_ports_are_none(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert all(v is None for v in doc["ports"].values())


def test_wizard_full_flow_with_mappings(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """Mapped ports appear as filled values in the generated YAML."""
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "clk",           # clk_i → clk
        "arst_n",        # rst_ni → arst_n
        "csr_in[15:0]",  # data_i → csr_in[15:0]
        "csr_out[7:0]",  # result_o → csr_out[7:0]
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args())
    assert rc == 0
    doc = yaml.safe_load(config_path.read_text())
    assert doc["ports"]["clk_i"] == "clk"
    assert doc["ports"]["rst_ni"] == "arst_n"
    assert doc["ports"]["data_i"] == "csr_in[15:0]"
    assert doc["ports"]["result_o"] == "csr_out[7:0]"


def test_wizard_metadata_name_default(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """Empty metadata name defaults to top_module."""
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "",                     # name → default "my_dut"
        "Roman",                # author
        "", "2.0.0", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert doc["metadata"]["name"] == "my_dut"
    assert doc["metadata"]["author"] == "Roman"
    assert doc["metadata"]["version"] == "2.0.0"


def test_wizard_wrapper_name_custom(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "",
        "custom_wrap",           # wrapper_name
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert doc["wrapper_name"] == "custom_wrap"


def test_wizard_calls_wrap_generate(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """Wizard calls api.wrap_generate with the written config path."""
    config_path = tmp_path / "wrapper_config.yaml"
    called_with: list[str] = []

    def fake_generate(path, *a, **kw):
        called_with.append(str(path))
        return fake_pass_result

    monkeypatch.setattr(_vf_api, "wrap_generate", fake_generate)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    assert len(called_with) == 1
    assert called_with[0] == str(config_path)


# ── generate returns FAIL → wizard returns 1 ─────────────────────────────────

def test_wizard_returns_1_on_generate_fail(dut_dir, tmp_path, monkeypatch, fake_fail_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_fail_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args())
    assert rc == 1


# ── mapping syntax error → retry that port ───────────────────────────────────

def test_wizard_mapping_syntax_error_retries_port(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """Bad mapping syntax for one port causes only that port to be re-asked."""
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "bad!!",         # clk_i: syntax error → retry
        "clk",           # clk_i: retry OK
        "", "", "",      # rst_ni, data_i, result_o: unmapped
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args())
    assert rc == 0


def test_wizard_syntax_error_port_gets_corrected_value(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "bad!!",         # clk_i: syntax error
        "clk",           # clk_i: corrected
        "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert doc["ports"]["clk_i"] == "clk"


def test_wizard_unknown_port_error_retries(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """Mapping to a non-existent interface port triggers retry."""
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "nonexistent_port",   # clk_i: unknown interface port → retry
        "clk",                # clk_i: corrected
        "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args())
    assert rc == 0


# ── RTL not found → retry rtl_sources ────────────────────────────────────────

def test_wizard_rtl_not_found_retries_sources(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """First rtl_sources attempt fails; wizard asks again without changing top_module."""
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "defs.v"),      # first attempt: defs.v (no module)
        "",                            # end first rtl list
        str(dut_dir / "my_dut.v"),    # second attempt: my_dut.v (has module)
        "",                            # end second rtl list
        "", "", "", "",                # port mappings
        "", "", "", "", "",            # metadata + wrapper_name
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args())
    assert rc == 0


def test_wizard_rtl_retry_yaml_has_correct_sources(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """After RTL retry, the YAML contains the correct rtl_sources."""
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    dut_path = str(dut_dir / "my_dut.v")
    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "defs.v"), "",   # first attempt: fails
        dut_path, "",                  # second attempt: succeeds
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert dut_path in doc["design"]["rtl_sources"]


# ── config file exists ────────────────────────────────────────────────────────

def test_wizard_config_exists_loops_to_new_path(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """When config file exists and --force not set, wizard loops to ask again."""
    existing = tmp_path / "existing.yaml"
    new_path = tmp_path / "new.yaml"
    existing.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(existing),   # first choice: exists without --force → loop
        str(new_path),   # second choice: OK
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args(force=False))
    assert rc == 0
    assert new_path.exists()
    assert existing.read_text() == "occupied"  # untouched


def test_wizard_force_overwrites_existing_config(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """With --force, wizard overwrites an existing config file without looping."""
    config_path = tmp_path / "wrapper_config.yaml"
    config_path.write_text("old content", encoding="utf-8")
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "", "", "", "",
        "", "", "", "", "",
        str(config_path),    # exists, but --force → no loop
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args(force=True))
    assert rc == 0
    content = config_path.read_text()
    assert "old content" not in content
    assert "interface_name" in content


# ── render_wrapper_config_yaml: filled ports (N14) ────────────────────────────

def test_wizard_filled_ports_in_yaml(dut_dir, tmp_path, monkeypatch, fake_pass_result):
    """Ports mapped in the wizard appear as values in the YAML (not null)."""
    config_path = tmp_path / "wrapper_config.yaml"
    monkeypatch.setattr(_vf_api, "wrap_generate", lambda *a, **kw: fake_pass_result)

    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "clk",           # clk_i
        "arst_n",        # rst_ni
        "",              # data_i: unmapped
        "",              # result_o: unmapped
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    _run_wizard([], _make_args())
    doc = yaml.safe_load(config_path.read_text())
    assert doc["ports"]["clk_i"] == "clk"
    assert doc["ports"]["rst_ni"] == "arst_n"
    assert doc["ports"]["data_i"] is None    # unmapped → null
    assert doc["ports"]["result_o"] is None  # unmapped → null


# ── render_wrapper_config_yaml extension (N14) — unit tests ──────────────────

def test_render_filled_ports_appear_as_values(dut_dir):
    """render_wrapper_config_yaml writes non-None port values into YAML."""
    from veriflow.api import wrap_init
    from veriflow.core.wrapper.config_template import render_wrapper_config_yaml
    from veriflow.models.interface_profile import get_interface_profile

    config = wrap_init("semicolab", "my_dut", [str(dut_dir / "my_dut.v")])
    ip_ports = config.pop("_ip_ports")
    config["ports"]["clk_i"] = "clk"
    config["ports"]["data_i"] = "csr_in[15:0]"

    iface = get_interface_profile("semicolab")
    src = render_wrapper_config_yaml(config, iface, ip_ports)
    doc = yaml.safe_load(src)

    assert doc["ports"]["clk_i"] == "clk"
    assert doc["ports"]["data_i"] == "csr_in[15:0]"
    assert doc["ports"]["rst_ni"] is None     # still unfilled
    assert doc["ports"]["result_o"] is None   # still unfilled


def test_render_all_filled_ports_parseable(dut_dir):
    """YAML with all ports filled is valid and round-trips to WrapperConfig."""
    from veriflow.api import wrap_init
    from veriflow.core.wrapper.config_template import render_wrapper_config_yaml
    from veriflow.models.interface_profile import get_interface_profile
    from veriflow.models.wrapper_config import WrapperConfig

    config = wrap_init("semicolab", "my_dut", [str(dut_dir / "my_dut.v")])
    ip_ports = config.pop("_ip_ports")
    config["ports"] = {
        "clk_i":    "clk",
        "rst_ni":   "arst_n",
        "data_i":   "csr_in[15:0]",
        "result_o": "csr_out[7:0]",
    }

    iface = get_interface_profile("semicolab")
    src = render_wrapper_config_yaml(config, iface, ip_ports)
    doc = yaml.safe_load(src)

    cfg = WrapperConfig.from_dict(doc)
    assert cfg.ports["clk_i"] == "clk"
    assert cfg.ports["data_i"] == "csr_in[15:0]"


# ── iverilog integration test (P5 guard) ─────────────────────────────────────

@pytest.mark.skipif(not _IVERILOG_OK, reason="iverilog not functional")
def test_wizard_full_flow_real_generate(dut_dir, tmp_path, monkeypatch):
    """Full wizard flow with real WrapWorkflow (no mocked generate)."""
    config_path = tmp_path / "wrapper_config.yaml"
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Use valid mappings so the wrapper is well-formed for the connectivity check
    responses = _responses_iter([
        "1", "my_dut",
        str(dut_dir / "my_dut.v"), "",
        "clk",           # clk_i
        "arst_n",        # rst_ni
        "csr_in[15:0]",  # data_i
        "csr_out[7:0]",  # result_o
        "", "", "", "", "",
        str(config_path),
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

    rc = _run_wizard([], _make_args())
    assert rc == 0
    assert config_path.exists()
