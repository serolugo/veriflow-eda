"""Tests for the file-backed technology profile loader (2026-07-14 migration:
technology definitions moved from hardcoded Python dataclass literals to
`.yaml` files under `veriflow/technologies/`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from veriflow.core import VeriFlowError
from veriflow.models.technology_profile import (
    DEFAULT_TECHNOLOGY_NAME,
    TECHNOLOGIES_DIR,
    TechnologyProfile,
    _load_builtin_technologies,
    get_technology_profile,
    load_technology_profile_from_file,
)


# ── load_technology_profile_from_file ─────────────────────────────────────────

def test_load_valid_yaml_returns_correct_fields(tmp_path):
    yaml_path = tmp_path / "mytech.yaml"
    yaml_path.write_text(
        "name: mytech\n"
        "description: A test technology.\n"
        "synthesis_backend: yosys\n"
        "liberty: /path/to/cells.lib\n"
        "synth_extra:\n"
        "  - \"-flatten\"\n"
        "  - \"-noabc\"\n",
        encoding="utf-8",
    )
    profile = load_technology_profile_from_file(yaml_path)
    assert profile.name == "mytech"
    assert profile.description == "A test technology."
    assert profile.synthesis_backend == "yosys"
    assert profile.liberty == "/path/to/cells.lib"
    assert profile.synth_extra == ["-flatten", "-noabc"]


def test_load_yaml_with_only_name_uses_defaults(tmp_path):
    yaml_path = tmp_path / "minimal.yaml"
    yaml_path.write_text("name: minimal\n", encoding="utf-8")
    profile = load_technology_profile_from_file(yaml_path)
    assert profile.name == "minimal"
    assert profile.description == ""
    assert profile.synthesis_backend == "yosys"
    assert profile.liberty is None
    assert profile.synth_extra == []
    assert profile.default_version is None


def test_load_yaml_with_default_version(tmp_path):
    yaml_path = tmp_path / "pinned.yaml"
    yaml_path.write_text(
        "name: pinned\n"
        "install_method: volare\n"
        "volare_pdk: pinned_pdk\n"
        "default_version: \"0fe599b2afb6708d281543108caf8310912f54af\"\n",
        encoding="utf-8",
    )
    profile = load_technology_profile_from_file(yaml_path)
    assert profile.default_version == "0fe599b2afb6708d281543108caf8310912f54af"


def test_load_missing_file_raises_not_found(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(VeriFlowError) as exc_info:
        load_technology_profile_from_file(missing)
    assert exc_info.value.code == "VF_TECHNOLOGY_FILE_NOT_FOUND"


def test_load_yaml_missing_name_raises_invalid(tmp_path):
    yaml_path = tmp_path / "no_name.yaml"
    yaml_path.write_text("description: no name field here\n", encoding="utf-8")
    with pytest.raises(VeriFlowError) as exc_info:
        load_technology_profile_from_file(yaml_path)
    assert exc_info.value.code == "VF_TECHNOLOGY_FILE_INVALID"


def test_load_yaml_non_mapping_raises_invalid(tmp_path):
    yaml_path = tmp_path / "list.yaml"
    yaml_path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(VeriFlowError) as exc_info:
        load_technology_profile_from_file(yaml_path)
    assert exc_info.value.code == "VF_TECHNOLOGY_FILE_INVALID"


def test_load_yaml_synth_extra_not_a_list_raises_invalid(tmp_path):
    yaml_path = tmp_path / "bad_synth_extra.yaml"
    yaml_path.write_text("name: bad\nsynth_extra: \"-flatten\"\n", encoding="utf-8")
    with pytest.raises(VeriFlowError) as exc_info:
        load_technology_profile_from_file(yaml_path)
    assert exc_info.value.code == "VF_TECHNOLOGY_FILE_INVALID"


# ── _load_builtin_technologies / registry regression ─────────────────────────

def test_technologies_dir_exists():
    assert TECHNOLOGIES_DIR.is_dir()
    for name in ("generic", "sky130", "gf180", "ihp130"):
        assert (TECHNOLOGIES_DIR / f"{name}.yaml").exists()


def test_load_builtin_technologies_includes_all_four():
    registry = _load_builtin_technologies()
    assert set(registry) == {"generic", "sky130", "gf180", "ihp130"}
    assert all(isinstance(p, TechnologyProfile) for p in registry.values())


def test_get_technology_profile_supported_names():
    for name in ("generic", "sky130", "gf180", "ihp130"):
        p = get_technology_profile(name)
        assert p.name == name
        assert p.liberty is None  # none of the built-ins vendor a real PDK yet
        assert p.synth_extra == []


def test_get_technology_profile_unknown_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        get_technology_profile("notapdkname")
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


# ── DEFAULT_TECHNOLOGY_NAME ───────────────────────────────────────────────────

def test_default_technology_name_is_generic():
    assert DEFAULT_TECHNOLOGY_NAME == "generic"


def test_default_technology_name_importable_from_execution_profile():
    """§3.5 of AUDIT_HARDCODING.md: 'generic' was re-declared as a literal
    default in 3 places instead of importing DEFAULT_TECHNOLOGY_NAME. Confirm
    execution_profile.py's default now matches the exported constant."""
    from veriflow.models.execution_profile import ExecutionProfile
    assert ExecutionProfile().technology_name == DEFAULT_TECHNOLOGY_NAME


def test_default_technology_name_used_in_project_technology_config():
    from veriflow.workflows.project_config import ProjectTechnologyConfig
    assert ProjectTechnologyConfig().name == DEFAULT_TECHNOLOGY_NAME
