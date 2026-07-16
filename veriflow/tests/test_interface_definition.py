"""Tests for external interface definitions (2026-07-14 migration, Step 4):

- Project Mode: `interface.definition:` in `veriflow.yaml`
- Database Mode: `interface_definition:` in `project_config.yaml`

Both resolve the given path relative to the config's own directory, register
the profile from the `.v` file, and use the parsed module name (warning if it
differs from the `name:`/`interface_name:` given alongside it).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from veriflow.core import VeriFlowError
from veriflow.models.interface_profile import _PROFILE_FACTORIES
from veriflow.models.project_config import ProjectConfig
from veriflow.workflows.project_config import ProjectWorkflowConfig


@pytest.fixture(autouse=True)
def _cleanup_registered_profiles():
    """Every test in this file may register a profile via `definition:` --
    remove whatever name(s) got added so other test files aren't affected."""
    before = set(_PROFILE_FACTORIES)
    yield
    for name in set(_PROFILE_FACTORIES) - before:
        del _PROFILE_FACTORIES[name]


def _write_tinytapeout_stub(path: Path) -> None:
    path.write_text(
        "module tinytapeout (\n"
        "    input  wire       clk,\n"
        "    input  wire       rst_n,\n"
        "    input  wire [7:0] ui_in,\n"
        "    output wire [7:0] uo_out\n"
        ");\n"
        "endmodule\n",
        encoding="utf-8",
    )


# ── Project Mode: interface.definition: in veriflow.yaml ─────────────────────

def test_project_mode_interface_definition_registers_and_resolves(tmp_path):
    _write_tinytapeout_stub(tmp_path / "tinytapeout_if.v")
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "interface": {"name": "tinytapeout", "definition": "./tinytapeout_if.v"},
        },
        root=tmp_path,
    )
    assert cfg.interface is not None
    assert cfg.interface.name == "tinytapeout"

    from veriflow.models.interface_profile import get_interface_profile
    profile = get_interface_profile("tinytapeout")
    assert {p.name for p in profile.ports} == {"clk", "rst_n", "ui_in", "uo_out"}


def test_project_mode_interface_definition_resolves_relative_to_config_dir(tmp_path):
    subdir = tmp_path / "interfaces"
    subdir.mkdir()
    _write_tinytapeout_stub(subdir / "tinytapeout_if.v")
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "interface": {"name": "tinytapeout", "definition": "./interfaces/tinytapeout_if.v"},
        },
        root=tmp_path,
    )
    assert cfg.interface.name == "tinytapeout"


def test_project_mode_interface_definition_name_mismatch_warns_and_uses_module_name(tmp_path):
    _write_tinytapeout_stub(tmp_path / "tinytapeout_if.v")
    with pytest.warns(UserWarning, match="VF_INTERFACE_NAME_MISMATCH"):
        cfg = ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": {"name": "wrong_name", "definition": "./tinytapeout_if.v"},
            },
            root=tmp_path,
        )
    assert cfg.interface.name == "tinytapeout"


def test_project_mode_no_definition_behaves_as_before(tmp_path):
    """interface.definition absent -- existing name-only behavior unchanged."""
    cfg = ProjectWorkflowConfig.from_dict(
        {
            "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
            "interface": {"name": "semicolab"},
        },
        root=tmp_path,
    )
    assert cfg.interface.name == "semicolab"


def test_project_mode_unknown_definition_keys_still_rejected(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]},
                "interface": {"name": "semicolab", "bogus_key": "x"},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_INTERFACE_CONFIG_INVALID"


# ── Database Mode: interface_definition: in project_config.yaml ─────────────

def _base_project_config_dict(**overrides) -> dict:
    data = {
        "id_prefix": "TST-01",
        "project_name": "Test Project",
        "repo": "https://github.com/test/test",
        "description": "Test project.",
        "interface_name": "tinytapeout",
    }
    data.update(overrides)
    return data


def test_database_mode_interface_definition_registers_and_resolves(tmp_path):
    _write_tinytapeout_stub(tmp_path / "tinytapeout_if.v")
    data = _base_project_config_dict(interface_definition="./tinytapeout_if.v")
    config = ProjectConfig.from_dict(data, root=tmp_path)
    assert config.interface_name == "tinytapeout"


def test_database_mode_interface_definition_name_mismatch_warns(tmp_path):
    _write_tinytapeout_stub(tmp_path / "tinytapeout_if.v")
    data = _base_project_config_dict(
        interface_name="wrong_name",
        interface_definition="./tinytapeout_if.v",
    )
    with pytest.warns(UserWarning, match="VF_INTERFACE_NAME_MISMATCH"):
        config = ProjectConfig.from_dict(data, root=tmp_path)
    assert config.interface_name == "tinytapeout"


def test_database_mode_no_definition_behaves_as_before(tmp_path):
    data = _base_project_config_dict(interface_name="semicolab")
    config = ProjectConfig.from_dict(data, root=tmp_path)
    assert config.interface_name == "semicolab"


def test_database_mode_interface_definition_without_root_raises():
    data = _base_project_config_dict(interface_definition="./tinytapeout_if.v")
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectConfig.from_dict(data)  # no root= given -- can't resolve the relative path
    assert exc_info.value.code == "VF_PROJECT_INTERFACE_CONFIG_INVALID"
