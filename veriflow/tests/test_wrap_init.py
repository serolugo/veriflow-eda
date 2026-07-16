"""Tests for veriflow.api.wrap_init and veriflow.core.wrapper.config_template."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from veriflow.api import wrap_init
from veriflow.core import VeriFlowError
from veriflow.core.wrapper.config_template import render_wrapper_config_yaml
from veriflow.models.interface_profile import get_interface_profile
from veriflow.models.wrapper_config import WrapperConfig

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

_TWO_MODS_V = """\
module mod_a (
    input wire clk
);
endmodule
module mod_b (
    input wire data
);
endmodule
"""

_VALID_PORTS = {
    "clk_i":    "clk",
    "rst_ni":   "arst_n",
    "data_i":   "csr_in[15:0]",
    "result_o": "csr_out[7:0]",
}


@pytest.fixture
def dut_dir(tmp_path: Path) -> Path:
    """Temp dir with defs.v (no module) and my_dut.v (single module)."""
    (tmp_path / "defs.v").write_text("`define DATA_WIDTH 16\n", encoding="utf-8")
    (tmp_path / "my_dut.v").write_text(_DUT_V, encoding="utf-8")
    return tmp_path


@pytest.fixture
def two_mods_file(tmp_path: Path) -> Path:
    """Temp file with two module declarations."""
    p = tmp_path / "two_mods.v"
    p.write_text(_TWO_MODS_V, encoding="utf-8")
    return p


# ── wrap_init -- dict structure ───────────────────────────────────────────────

def _call_init(dut_dir: Path, **kwargs) -> dict:
    defaults = {
        "interface_name": "semicolab",
        "rtl_file": str(dut_dir / "my_dut.v"),
    }
    defaults.update(kwargs)
    return wrap_init(**defaults)


def test_wrap_init_returns_dict(dut_dir):
    result = _call_init(dut_dir)
    assert isinstance(result, dict)


def test_wrap_init_interface_name(dut_dir):
    result = _call_init(dut_dir)
    assert result["interface_name"] == "semicolab"


def test_wrap_init_design_top_module(dut_dir):
    result = _call_init(dut_dir)
    assert result["design"]["top_module"] == "my_dut"


def test_wrap_init_detects_module_name(dut_dir):
    """Auto-detected module name matches the only module in the file."""
    result = _call_init(dut_dir)
    assert result["design"]["top_module"] == "my_dut"


def test_wrap_init_design_rtl_sources(dut_dir):
    src = str(dut_dir / "my_dut.v")
    result = wrap_init("semicolab", src)
    assert result["design"]["rtl_sources"] == [src]


def test_wrap_init_ports_keys_match_dut(dut_dir):
    result = _call_init(dut_dir)
    assert set(result["ports"].keys()) == {"clk_i", "rst_ni", "data_i", "result_o"}


def test_wrap_init_ports_values_are_none(dut_dir):
    result = _call_init(dut_dir)
    assert all(v is None for v in result["ports"].values())


def test_wrap_init_wrapper_name_default(dut_dir):
    result = _call_init(dut_dir)
    assert result["wrapper_name"] == "my_dut_wrapper"


def test_wrap_init_wrapper_name_custom(dut_dir):
    result = _call_init(dut_dir, wrapper_name="my_custom_wrapper")
    assert result["wrapper_name"] == "my_custom_wrapper"


def test_wrap_init_metadata_defaults(dut_dir):
    result = _call_init(dut_dir)
    meta = result["metadata"]
    assert meta["name"] == "my_dut"
    assert meta["author"] == ""
    assert meta["description"] == ""
    assert meta["version"] == "1.0.0"


def test_wrap_init_metadata_custom(dut_dir):
    result = _call_init(
        dut_dir,
        metadata={"name": "My IP", "author": "Roman", "version": "2.0.0"},
    )
    meta = result["metadata"]
    assert meta["name"] == "My IP"
    assert meta["author"] == "Roman"
    assert meta["version"] == "2.0.0"
    assert meta["description"] == ""


def test_wrap_init_no_private_ip_ports_key(dut_dir):
    """_ip_ports was a private leak of implementation detail into the public
    dict -- replaced by the public "detected_ports" key (2026-07-15 MCP API
    cleanup, dev-docs/MCP_API_AUDIT.md)."""
    result = _call_init(dut_dir)
    assert "_ip_ports" not in result


def test_wrap_init_detected_ports_present(dut_dir):
    result = _call_init(dut_dir)
    assert "detected_ports" in result
    assert len(result["detected_ports"]) == 4
    names = [p["name"] for p in result["detected_ports"]]
    assert "clk_i" in names
    assert "result_o" in names


def test_wrap_init_detected_ports_are_clean_dicts(dut_dir):
    result = _call_init(dut_dir)
    for entry in result["detected_ports"]:
        assert set(entry.keys()) == {"name", "direction", "width"}


def test_wrap_init_detected_ports_widths(dut_dir):
    result = _call_init(dut_dir)
    by_name = {p["name"]: p["width"] for p in result["detected_ports"]}
    assert by_name["clk_i"] == 1
    assert by_name["data_i"] == 16
    assert by_name["result_o"] == 8


# ── wrap_init -- error cases ──────────────────────────────────────────────────

def test_wrap_init_no_module_found(dut_dir):
    """File with no module declaration raises VF_WRAP_E_NO_MODULE_FOUND."""
    with pytest.raises(VeriFlowError) as exc_info:
        wrap_init("semicolab", str(dut_dir / "defs.v"))
    assert exc_info.value.code == "VF_WRAP_E_NO_MODULE_FOUND"


def test_wrap_init_no_module_found_details(dut_dir):
    """details['rtl_file'] contains the path of the offending file."""
    defs_path = str(dut_dir / "defs.v")
    with pytest.raises(VeriFlowError) as exc_info:
        wrap_init("semicolab", defs_path)
    assert exc_info.value.details["rtl_file"] == defs_path


def test_wrap_init_multiple_modules_found(two_mods_file):
    """File with two module declarations raises VF_WRAP_E_MULTIPLE_MODULES_FOUND."""
    with pytest.raises(VeriFlowError) as exc_info:
        wrap_init("semicolab", str(two_mods_file))
    assert exc_info.value.code == "VF_WRAP_E_MULTIPLE_MODULES_FOUND"


def test_wrap_init_multiple_modules_names_in_message(two_mods_file):
    """Error message lists both detected module names."""
    with pytest.raises(VeriFlowError) as exc_info:
        wrap_init("semicolab", str(two_mods_file))
    msg = str(exc_info.value)
    assert "mod_a" in msg
    assert "mod_b" in msg


def test_wrap_init_multiple_modules_details(two_mods_file):
    """details['modules'] contains both module names."""
    with pytest.raises(VeriFlowError) as exc_info:
        wrap_init("semicolab", str(two_mods_file))
    assert "mod_a" in exc_info.value.details["modules"]
    assert "mod_b" in exc_info.value.details["modules"]


def test_wrap_init_unknown_interface(dut_dir):
    with pytest.raises(VeriFlowError) as exc_info:
        wrap_init("nonexistent_interface", str(dut_dir / "my_dut.v"))
    assert exc_info.value.code == "VF_INTERFACE_UNKNOWN"


# ── render_wrapper_config_yaml ────────────────────────────────────────────────

def _to_tuples(detected_ports: list[dict]) -> list[tuple[str, str, int | None]]:
    return [(p["name"], p["direction"], p["width"]) for p in detected_ports]


def _render(dut_dir: Path) -> str:
    config = _call_init(dut_dir)
    ip_ports = _to_tuples(config.pop("detected_ports"))
    iface = get_interface_profile("semicolab")
    return render_wrapper_config_yaml(config, iface, ip_ports)


def test_render_returns_string(dut_dir):
    assert isinstance(_render(dut_dir), str)


def test_render_non_empty(dut_dir):
    assert len(_render(dut_dir)) > 0


def test_render_has_interface_comment(dut_dir):
    src = _render(dut_dir)
    assert "semicolab" in src
    assert src.startswith("#")


def test_render_has_iface_port_comments(dut_dir):
    src = _render(dut_dir)
    assert "# Interface ports" in src
    # All semicolab ports should appear in comments
    for port_name in ("clk", "arst_n", "csr_in", "data_reg_a", "csr_out"):
        assert port_name in src


def test_render_parseable_yaml(dut_dir):
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    assert isinstance(doc, dict)


def test_render_interface_name_field(dut_dir):
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    assert doc["interface_name"] == "semicolab"


def test_render_design_top_module(dut_dir):
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    assert doc["design"]["top_module"] == "my_dut"


def test_render_wrapper_name_field(dut_dir):
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    assert doc["wrapper_name"] == "my_dut_wrapper"


def test_render_ports_keys_present(dut_dir):
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    assert set(doc["ports"].keys()) == {"clk_i", "rst_ni", "data_i", "result_o"}


def test_render_ports_values_none(dut_dir):
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    assert all(v is None for v in doc["ports"].values())


def test_render_ip_port_comments_include_direction_width(dut_dir):
    src = _render(dut_dir)
    # Each port should have a comment with direction and width
    assert "# input, 1" in src    # clk_i or rst_ni
    assert "# input, 16" in src   # data_i
    assert "# output, 8" in src   # result_o


def test_render_yaml_roundtrip_valid_after_filling_ports(dut_dir):
    """Rendered YAML becomes a valid WrapperConfig after ports are filled in."""
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    # Fill in the ports manually (as a user would)
    doc["ports"] = dict(_VALID_PORTS)
    # from_dict must succeed without raising
    cfg = WrapperConfig.from_dict(doc)
    assert cfg.interface_name == "semicolab"
    assert cfg.design.top_module == "my_dut"
    assert cfg.ports == _VALID_PORTS


def test_render_metadata_author_empty_quoted(dut_dir):
    """Empty metadata fields must not produce 'null' -- they must be empty strings."""
    src = _render(dut_dir)
    doc = yaml.safe_load(src)
    assert doc["metadata"]["author"] == ""
    assert doc["metadata"]["description"] == ""


def test_render_version_preserved(dut_dir):
    config = _call_init(dut_dir, metadata={"version": "2.3.1"})
    ip_ports = _to_tuples(config.pop("detected_ports"))
    iface = get_interface_profile("semicolab")
    src = render_wrapper_config_yaml(config, iface, ip_ports)
    doc = yaml.safe_load(src)
    assert doc["metadata"]["version"] == "2.3.1"


def test_render_rtl_sources_preserved(dut_dir):
    src_path = str(dut_dir / "my_dut.v")
    config = wrap_init("semicolab", src_path)
    ip_ports = _to_tuples(config.pop("detected_ports"))
    iface = get_interface_profile("semicolab")
    src = render_wrapper_config_yaml(config, iface, ip_ports)
    doc = yaml.safe_load(src)
    assert src_path in doc["design"]["rtl_sources"]


def test_render_no_ip_ports_section(dut_dir):
    """When ip_ports is empty, the ports section has a comment placeholder."""
    config = _call_init(dut_dir)
    config.pop("detected_ports")
    iface = get_interface_profile("semicolab")
    src = render_wrapper_config_yaml(config, iface, [])
    assert "# (no ports detected" in src


# ── cmd_wrap_init CLI command ─────────────────────────────────────────────────

def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {
        "interface": "semicolab",
        "rtl_file": "",
        "config": "wrapper_config.yaml",
        "wrapper_name": None,
        "author": None,
        "description": None,
        "version": None,
        "force": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_cli_init_writes_config(dut_dir, tmp_path):
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    args = _make_args(
        rtl_file=str(dut_dir / "my_dut.v"),
        config=str(out),
    )
    rc = cmd_wrap_init(args)
    assert rc == 0
    assert out.exists()


def test_cli_init_config_parseable(dut_dir, tmp_path):
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    args = _make_args(rtl_file=str(dut_dir / "my_dut.v"), config=str(out))
    cmd_wrap_init(args)
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["interface_name"] == "semicolab"
    assert set(doc["ports"].keys()) == {"clk_i", "rst_ni", "data_i", "result_o"}


def test_cli_init_config_exists_raises(dut_dir, tmp_path):
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    out.write_text("existing", encoding="utf-8")
    args = _make_args(rtl_file=str(dut_dir / "my_dut.v"), config=str(out))
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_wrap_init(args)
    assert exc_info.value.code == "VF_WRAP_E_CONFIG_EXISTS"


def test_cli_init_force_overwrites(dut_dir, tmp_path):
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    out.write_text("old content", encoding="utf-8")
    args = _make_args(
        rtl_file=str(dut_dir / "my_dut.v"),
        config=str(out),
        force=True,
    )
    rc = cmd_wrap_init(args)
    assert rc == 0
    content = out.read_text(encoding="utf-8")
    assert "old content" not in content
    assert "interface_name" in content


def test_cli_init_custom_wrapper_name(dut_dir, tmp_path):
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    args = _make_args(
        rtl_file=str(dut_dir / "my_dut.v"),
        config=str(out),
        wrapper_name="custom_wrap",
    )
    cmd_wrap_init(args)
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["wrapper_name"] == "custom_wrap"


def test_cli_init_metadata_author(dut_dir, tmp_path):
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    args = _make_args(
        rtl_file=str(dut_dir / "my_dut.v"),
        config=str(out),
        author="Roman",
    )
    cmd_wrap_init(args)
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["metadata"]["author"] == "Roman"


def test_cli_init_no_module_found_propagates(dut_dir, tmp_path):
    """File with no module declaration raises VF_WRAP_E_NO_MODULE_FOUND via CLI."""
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    args = _make_args(
        rtl_file=str(dut_dir / "defs.v"),
        config=str(out),
    )
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_wrap_init(args)
    assert exc_info.value.code == "VF_WRAP_E_NO_MODULE_FOUND"
    assert not out.exists()


def test_cli_init_multiple_modules_found_propagates(two_mods_file, tmp_path):
    """File with multiple modules raises VF_WRAP_E_MULTIPLE_MODULES_FOUND via CLI."""
    from veriflow.commands.wrap_init import cmd_wrap_init
    out = tmp_path / "wrapper_config.yaml"
    args = _make_args(
        rtl_file=str(two_mods_file),
        config=str(out),
    )
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_wrap_init(args)
    assert exc_info.value.code == "VF_WRAP_E_MULTIPLE_MODULES_FOUND"
    assert not out.exists()


# ── render_wrapper_config_yaml: filled ports (N14) ───────────────────────────

def test_render_filled_ports_appear_as_values(dut_dir):
    """When config['ports'][name] is non-None, the value appears in the YAML output."""
    config = _call_init(dut_dir)
    ip_ports = _to_tuples(config.pop("detected_ports"))
    config["ports"]["clk_i"] = "clk"
    config["ports"]["data_i"] = "csr_in[15:0]"
    iface = get_interface_profile("semicolab")
    src = render_wrapper_config_yaml(config, iface, ip_ports)
    doc = yaml.safe_load(src)
    assert doc["ports"]["clk_i"] == "clk"
    assert doc["ports"]["data_i"] == "csr_in[15:0]"
    assert doc["ports"]["rst_ni"] is None   # still unfilled
    assert doc["ports"]["result_o"] is None  # still unfilled


def test_render_all_filled_ports_parseable(dut_dir):
    """YAML with all ports filled is parseable and WrapperConfig.from_dict succeeds."""
    config = _call_init(dut_dir)
    ip_ports = _to_tuples(config.pop("detected_ports"))
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
