"""Tests for external technology definitions
(`technology.definition:` in veriflow.yaml / `technology_definition:` in
project_config.yaml), mirroring interface.definition's mechanism -- see
`veriflow.models.technology_profile.load_and_register_technology_profile_from_file`.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from veriflow.core import VeriFlowError
from veriflow.models.project_config import ProjectConfig
from veriflow.models.technology_profile import (
    get_technology_profile,
    load_and_register_technology_profile_from_file,
)
from veriflow.workflows.project_config import ProjectWorkflowConfig


def _write_technology_yaml(path: Path, *, name: str, liberty: str | None = None, extra: str = "") -> Path:
    content = f"name: {name}\ndescription: custom technology\n"
    if liberty is not None:
        content += f"liberty: {liberty}\n"
    content += extra
    path.write_text(content, encoding="utf-8")
    return path


# ── technology_profile.load_and_register_technology_profile_from_file ────────

def test_load_and_register_absolute_liberty_unchanged(tmp_path):
    absolute_liberty = str(tmp_path / "cells.lib")
    tech_path = _write_technology_yaml(tmp_path / "custom.yaml", name="custom_abs", liberty=absolute_liberty)
    profile = load_and_register_technology_profile_from_file(tech_path, liberty_root=tmp_path / "unrelated")
    assert profile.name == "custom_abs"
    assert profile.liberty == absolute_liberty
    assert get_technology_profile("custom_abs") is profile


def test_load_and_register_relative_liberty_resolved_against_liberty_root(tmp_path):
    config_dir = tmp_path / "project"
    config_dir.mkdir()
    tech_dir = config_dir / "technologies"
    tech_dir.mkdir()
    tech_path = _write_technology_yaml(tech_dir / "custom.yaml", name="custom_rel", liberty="./cells/mycell.lib")
    profile = load_and_register_technology_profile_from_file(tech_path, liberty_root=config_dir)
    assert profile.liberty == str((config_dir / "cells" / "mycell.lib").resolve())


def test_load_and_register_without_liberty_root_leaves_relative_liberty_untouched(tmp_path):
    tech_path = _write_technology_yaml(tmp_path / "custom.yaml", name="custom_norroot", liberty="./cells/mycell.lib")
    profile = load_and_register_technology_profile_from_file(tech_path)
    assert profile.liberty == "./cells/mycell.lib"


def test_load_and_register_overwrites_existing_registration(tmp_path):
    from veriflow.models.technology_profile import TechnologyProfile, register_technology_profile

    original_generic = get_technology_profile("generic")
    tech_path = _write_technology_yaml(tmp_path / "generic2.yaml", name="generic", liberty=None)
    try:
        profile = load_and_register_technology_profile_from_file(tech_path)
        assert get_technology_profile("generic") is profile
        assert profile.description == "custom technology"
    finally:
        # restore -- avoid polluting the module-level registry for later tests
        register_technology_profile(original_generic)


# ── Project Mode: technology.definition ───────────────────────────────────────

def test_project_mode_technology_definition_registers_and_resolves(tmp_path):
    tech_dir = tmp_path / "technologies"
    tech_dir.mkdir()
    tech_path = _write_technology_yaml(tech_dir / "mi_proceso.yaml", name="mi_proceso", liberty="./cells/mi_proceso.lib")

    (tmp_path / "top.v").write_text("", encoding="utf-8")
    veriflow_yaml = tmp_path / "veriflow.yaml"
    veriflow_yaml.write_text(dedent("""\
        design:
          top_module: top
          rtl_sources:
            - top.v
        technology:
          name: mi_proceso
          definition: ./technologies/mi_proceso.yaml
        """), encoding="utf-8")

    cfg = ProjectWorkflowConfig.from_file(veriflow_yaml)
    assert cfg.technology.name == "mi_proceso"

    profile = get_technology_profile("mi_proceso")
    assert profile.liberty == str((tmp_path / "cells" / "mi_proceso.lib").resolve())


def test_project_mode_technology_definition_name_mismatch_warns_and_uses_file_name(tmp_path):
    tech_dir = tmp_path / "technologies"
    tech_dir.mkdir()
    _write_technology_yaml(tech_dir / "actual.yaml", name="actual_name")

    with pytest.warns(UserWarning, match="VF_TECHNOLOGY_NAME_MISMATCH"):
        cfg = ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["top.v"]},
                "technology": {"name": "declared_name", "definition": "./technologies/actual.yaml"},
            },
            root=tmp_path,
        )
    assert cfg.technology.name == "actual_name"


def test_project_mode_technology_definition_unsupported_key_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["top.v"]},
                "technology": {"name": "x", "pdk": "sky130"},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_TECHNOLOGY_CONFIG_INVALID"


def test_project_mode_technology_definition_empty_path_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(
            {
                "design": {"top_module": "top", "rtl_sources": ["top.v"]},
                "technology": {"definition": "   "},
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_TECHNOLOGY_CONFIG_INVALID"


# ── Database Mode: technology_definition ──────────────────────────────────────

def test_database_mode_technology_definition_registers_and_resolves(tmp_path):
    tech_dir = tmp_path / "technologies"
    tech_dir.mkdir()
    _write_technology_yaml(tech_dir / "mi_proceso.yaml", name="mi_proceso_db", liberty="./cells/mi_proceso.lib")

    cfg = ProjectConfig.from_dict(
        {
            "interface_name": None,
            "technology": {"name": "mi_proceso_db"},
            "technology_definition": "./technologies/mi_proceso.yaml",
        },
        root=tmp_path,
    )
    assert cfg.technology_name == "mi_proceso_db"
    profile = get_technology_profile("mi_proceso_db")
    assert profile.liberty == str((tmp_path / "cells" / "mi_proceso.lib").resolve())


def test_database_mode_technology_definition_requires_root():
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectConfig.from_dict(
            {
                "interface_name": None,
                "technology_definition": "./technologies/mi_proceso.yaml",
            },
        )
    assert exc_info.value.code == "VF_PROJECT_TECHNOLOGY_CONFIG_INVALID"


def test_database_mode_technology_definition_empty_string_fails(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectConfig.from_dict(
            {
                "interface_name": None,
                "technology_definition": "   ",
            },
            root=tmp_path,
        )
    assert exc_info.value.code == "VF_PROJECT_TECHNOLOGY_CONFIG_INVALID"


def test_database_mode_technology_definition_name_mismatch_warns(tmp_path):
    tech_dir = tmp_path / "technologies"
    tech_dir.mkdir()
    _write_technology_yaml(tech_dir / "actual2.yaml", name="actual_name_db")

    with pytest.warns(UserWarning, match="VF_TECHNOLOGY_NAME_MISMATCH"):
        cfg = ProjectConfig.from_dict(
            {
                "interface_name": None,
                "technology": {"name": "declared_name_db"},
                "technology_definition": "./technologies/actual2.yaml",
            },
            root=tmp_path,
        )
    assert cfg.technology_name == "actual_name_db"


# ── Database Mode: technology.require_pdk ─────────────────────────────────────


def test_database_mode_require_pdk_true_parses():
    cfg = ProjectConfig.from_dict(
        {"interface_name": None, "technology": {"name": "sky130", "require_pdk": True}},
    )
    assert cfg.require_pdk is True
    assert cfg.technology_name == "sky130"


def test_database_mode_require_pdk_defaults_to_false():
    cfg = ProjectConfig.from_dict({"interface_name": None, "technology": {"name": "sky130"}})
    assert cfg.require_pdk is False


def test_database_mode_require_pdk_defaults_false_with_no_technology_section():
    cfg = ProjectConfig.from_dict({"interface_name": None})
    assert cfg.require_pdk is False


def test_database_mode_require_pdk_non_bool_fails():
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectConfig.from_dict(
            {"interface_name": None, "technology": {"name": "sky130", "require_pdk": "true"}},
        )
    assert exc_info.value.code == "VF_PROJECT_TECHNOLOGY_CONFIG_INVALID"
