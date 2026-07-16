"""Tests for the file-backed interface profile loader (2026-07-14 migration:
interface port contracts moved from hardcoded Python dataclass literals to
`.v` stub files under `veriflow/interfaces/<name>/`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from veriflow.core import VeriFlowError
from veriflow.models.interface_profile import (
    INTERFACES_DIR,
    InterfaceProfile,
    _load_builtin_interfaces,
    get_interface_profile,
    load_interface_profile_from_file,
    register_interface_profile_from_file,
)


# ── load_interface_profile_from_file ──────────────────────────────────────────

def test_load_valid_stub_returns_correct_ports(tmp_path):
    stub = tmp_path / "my_if.v"
    stub.write_text(
        "module my_if (\n"
        "    input  wire        clk,\n"
        "    input  wire [7:0]  data_in,\n"
        "    output wire        valid\n"
        ");\n"
        "endmodule\n",
        encoding="utf-8",
    )
    profile = load_interface_profile_from_file(stub)
    assert profile.name == "my_if"
    ports_by_name = {p.name: p for p in profile.ports}
    assert ports_by_name["clk"].direction == "input"
    assert ports_by_name["clk"].width == 1
    assert ports_by_name["data_in"].direction == "input"
    assert ports_by_name["data_in"].width == 8
    assert ports_by_name["valid"].direction == "output"
    assert ports_by_name["valid"].width == 1


def test_load_detects_colocated_tb_template(tmp_path):
    stub = tmp_path / "interface.v"
    stub.write_text("module foo (input wire clk);\nendmodule\n", encoding="utf-8")
    (tmp_path / "tb_template.v").write_text("module tb;\nendmodule\n", encoding="utf-8")

    profile = load_interface_profile_from_file(stub)
    assert profile.tb_template == str(tmp_path / "tb_template.v")


def test_load_without_colocated_tb_template_is_none(tmp_path):
    stub = tmp_path / "interface.v"
    stub.write_text("module foo (input wire clk);\nendmodule\n", encoding="utf-8")

    profile = load_interface_profile_from_file(stub)
    assert profile.tb_template is None


def test_load_reads_meta_yaml_when_present(tmp_path):
    stub = tmp_path / "interface.v"
    stub.write_text("module foo (input wire clk);\nendmodule\n", encoding="utf-8")
    (tmp_path / "meta.yaml").write_text(
        "description: A test interface.\nrequires_top_module: true\n",
        encoding="utf-8",
    )

    profile = load_interface_profile_from_file(stub)
    assert profile.description == "A test interface."
    assert profile.requires_top_module is True


def test_load_without_meta_yaml_uses_defaults(tmp_path):
    stub = tmp_path / "interface.v"
    stub.write_text("module foo (input wire clk);\nendmodule\n", encoding="utf-8")

    profile = load_interface_profile_from_file(stub)
    assert profile.description == ""
    assert profile.requires_top_module is False


def test_load_missing_file_raises_not_found(tmp_path):
    missing = tmp_path / "does_not_exist.v"
    with pytest.raises(VeriFlowError) as exc_info:
        load_interface_profile_from_file(missing)
    assert exc_info.value.code == "VF_INTERFACE_FILE_NOT_FOUND"


def test_load_no_module_declaration_raises_no_ports(tmp_path):
    stub = tmp_path / "empty.v"
    stub.write_text("// just a comment, nothing else in this file\n", encoding="utf-8")
    with pytest.raises(VeriFlowError) as exc_info:
        load_interface_profile_from_file(stub)
    assert exc_info.value.code == "VF_INTERFACE_FILE_NO_PORTS"


def test_load_module_with_zero_ports_raises_no_ports(tmp_path):
    stub = tmp_path / "empty_ports.v"
    stub.write_text("module foo ();\nendmodule\n", encoding="utf-8")
    with pytest.raises(VeriFlowError) as exc_info:
        load_interface_profile_from_file(stub)
    assert exc_info.value.code == "VF_INTERFACE_FILE_NO_PORTS"


def test_load_multiple_modules_warns_and_uses_first(tmp_path):
    stub = tmp_path / "multi.v"
    stub.write_text(
        "module first (input wire clk);\nendmodule\n"
        "module second (input wire rst);\nendmodule\n",
        encoding="utf-8",
    )
    with pytest.warns(UserWarning, match="VF_INTERFACE_FILE_MULTIPLE_MODULES"):
        profile = load_interface_profile_from_file(stub)
    assert profile.name == "first"
    assert [p.name for p in profile.ports] == ["clk"]


# ── _load_builtin_interfaces / semicolab regression ──────────────────────────

def test_builtin_interfaces_dir_exists():
    assert INTERFACES_DIR.is_dir()
    assert (INTERFACES_DIR / "semicolab" / "interface.v").exists()


def test_load_builtin_interfaces_includes_semicolab():
    factories = _load_builtin_interfaces()
    assert "semicolab" in factories
    profile = factories["semicolab"]()
    assert isinstance(profile, InterfaceProfile)


def test_builtin_semicolab_has_same_nine_ports_as_before_migration():
    """Regression: the port contract loaded from interface.v must be
    byte-for-byte identical (name, direction, width) to the pre-migration
    hardcoded semicolab_interface_profile()."""
    profile = get_interface_profile("semicolab")
    expected = [
        ("clk", "input", 1),
        ("arst_n", "input", 1),
        ("csr_in", "input", 16),
        ("data_reg_a", "input", 32),
        ("data_reg_b", "input", 32),
        ("data_reg_c", "output", 32),
        ("csr_out", "output", 16),
        ("csr_in_re", "output", 1),
        ("csr_out_we", "output", 1),
    ]
    actual = [(p.name, p.direction, p.width) for p in profile.ports]
    assert actual == expected


def test_builtin_semicolab_requires_top_module_and_has_description():
    profile = get_interface_profile("semicolab")
    assert profile.requires_top_module is True
    assert profile.description


# ── register_interface_profile_from_file ─────────────────────────────────────

@pytest.fixture()
def _cleanup_registered_profiles():
    """Registering an external profile mutates the shared, module-level
    _PROFILE_FACTORIES dict -- remove whatever name(s) the test added so
    other tests in the same session don't see leftover test profiles."""
    from veriflow.models.interface_profile import _PROFILE_FACTORIES
    before = set(_PROFILE_FACTORIES)
    yield
    for name in set(_PROFILE_FACTORIES) - before:
        del _PROFILE_FACTORIES[name]


def test_register_external_profile_becomes_available(tmp_path, _cleanup_registered_profiles):
    stub = tmp_path / "tinytapeout_if.v"
    stub.write_text(
        "module tinytapeout (\n"
        "    input  wire       clk,\n"
        "    input  wire       rst_n,\n"
        "    input  wire [7:0] ui_in,\n"
        "    output wire [7:0] uo_out\n"
        ");\n"
        "endmodule\n",
        encoding="utf-8",
    )
    name = register_interface_profile_from_file(stub)
    assert name == "tinytapeout"

    profile = get_interface_profile("tinytapeout")
    assert profile is not None
    assert {p.name for p in profile.ports} == {"clk", "rst_n", "ui_in", "uo_out"}


def test_register_external_profile_name_comes_from_module_not_filename(tmp_path, _cleanup_registered_profiles):
    stub = tmp_path / "some_arbitrary_filename.v"
    stub.write_text("module actual_module_name (input wire clk);\nendmodule\n", encoding="utf-8")
    name = register_interface_profile_from_file(stub)
    assert name == "actual_module_name"


def test_register_overwriting_existing_profile_warns(tmp_path):
    from veriflow.models.interface_profile import _PROFILE_FACTORIES

    original_factory = _PROFILE_FACTORIES["semicolab"]
    stub = tmp_path / "semicolab.v"
    stub.write_text("module semicolab (input wire clk);\nendmodule\n", encoding="utf-8")
    try:
        with pytest.warns(UserWarning, match="VF_INTERFACE_PROFILE_OVERWRITTEN"):
            register_interface_profile_from_file(stub)
    finally:
        # Restore the real built-in definition regardless of outcome, so
        # later tests in the same process aren't affected by this overwrite.
        _PROFILE_FACTORIES["semicolab"] = original_factory
