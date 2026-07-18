"""Regression tests for `veriflow project apply-spec` / `api.apply_spec()`
(2026-07-18): applying a shuttle_spec.yaml's interface/technology/pipeline
fields onto a project's veriflow.yaml, reusing the same comment-preserving
YAML editor as `veriflow project set` (not a separate/duplicated code path).
"""

from __future__ import annotations

import warnings

import pytest
import yaml

from veriflow.api import apply_spec
from veriflow.core import VeriFlowError
from veriflow.core.project_config_template import render_project_config_yaml


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_config(tmp_path) -> "Path":
    config_path = tmp_path / "veriflow.yaml"
    config_path.write_text(render_project_config_yaml(), encoding="utf-8")
    return config_path


def _write_spec(tmp_path, text: str) -> "Path":
    spec_path = tmp_path / "shuttle_spec.yaml"
    spec_path.write_text(text, encoding="utf-8")
    return spec_path


# ── 1. Plain interface/technology/pipeline ────────────────────────────────────


def test_apply_spec_interface_technology_pipeline(tmp_path):
    config_path = _make_config(tmp_path)
    spec_path = _write_spec(
        tmp_path,
        "interface: semicolab\ntechnology: sky130\npipeline:\n  stages:\n"
        "    - type: connectivity\n    - type: synthesis\n",
    )

    applied = apply_spec(spec_path, config_path)

    assert applied == {
        "interface": "semicolab",
        "technology": "sky130",
        "pipeline": ["connectivity", "synthesis"],
    }
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"] == {"name": "semicolab"}
    assert data["technology"] == {"name": "sky130"}
    assert data["pipeline"]["stages"] == [{"type": "connectivity"}, {"type": "synthesis"}]


def test_apply_spec_partial_fields_only_applies_whats_present(tmp_path):
    config_path = _make_config(tmp_path)
    spec_path = _write_spec(tmp_path, "interface: semicolab\n")

    applied = apply_spec(spec_path, config_path)

    assert applied == {"interface": "semicolab"}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"] == {"name": "semicolab"}
    assert "technology" not in data or data["technology"] is None


def test_apply_spec_interface_null_clears_interface(tmp_path):
    config_path = _make_config(tmp_path)
    spec_path = _write_spec(tmp_path, "interface: null\n")

    applied = apply_spec(spec_path, config_path)

    assert applied == {"interface": None}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data.get("interface") is None


# ── 2. *_definition combos (custom, not-yet-registered names) ────────────────


def test_apply_spec_interface_definition_writes_name_and_definition(tmp_path):
    config_path = _make_config(tmp_path)
    (tmp_path / "custom_if.v").write_text(
        "module custom_if(input clk); endmodule\n", encoding="utf-8"
    )
    spec_path = _write_spec(
        tmp_path,
        "interface: custom_if\ninterface_definition: ./custom_if.v\n",
    )

    applied = apply_spec(spec_path, config_path)

    assert applied["interface"] == "custom_if"
    assert applied["interface_definition"] == "./custom_if.v"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"] == {"name": "custom_if", "definition": "./custom_if.v"}

    # Round-trips through the real config loader too (validated at load time,
    # not at apply-time -- this is what apply_spec's bypass of
    # project_set_config's validated "interface" key relies on). Needs a
    # real top_module/rtl_sources filled in first -- the scaffold's own
    # blank design section is unrelated to apply_spec and would fail to
    # load regardless of the interface section.
    text = config_path.read_text(encoding="utf-8")
    text = text.replace('top_module: ""', 'top_module: "top"')
    text = text.replace("rtl_sources: []", 'rtl_sources: ["top.v"]')
    config_path.write_text(text, encoding="utf-8")

    from veriflow.workflows.project_config import ProjectWorkflowConfig
    cfg = ProjectWorkflowConfig.from_file(config_path, validate_rtl_sources=False)
    assert cfg.interface is not None
    assert cfg.interface.name == "custom_if"


def test_apply_spec_interface_definition_without_explicit_name(tmp_path):
    """interface_definition alone (no `interface:` key) still writes a
    `definition:` child -- `name` is left for config-load time to resolve
    from the parsed module name."""
    config_path = _make_config(tmp_path)
    (tmp_path / "custom_if.v").write_text(
        "module custom_if(input clk); endmodule\n", encoding="utf-8"
    )
    spec_path = _write_spec(tmp_path, "interface_definition: ./custom_if.v\n")

    applied = apply_spec(spec_path, config_path)

    assert "interface" not in applied
    assert applied["interface_definition"] == "./custom_if.v"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"] == {"definition": "./custom_if.v"}


def test_apply_spec_technology_definition_writes_name_and_definition(tmp_path):
    config_path = _make_config(tmp_path)
    (tmp_path / "custom_tech.yaml").write_text(
        "name: custom_tech\ndescription: custom\n", encoding="utf-8"
    )
    spec_path = _write_spec(
        tmp_path,
        "technology: custom_tech\ntechnology_definition: ./custom_tech.yaml\n",
    )

    applied = apply_spec(spec_path, config_path)

    assert applied["technology"] == "custom_tech"
    assert applied["technology_definition"] == "./custom_tech.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["technology"] == {"name": "custom_tech", "definition": "./custom_tech.yaml"}


# ── 3. shuttle_name: informative only, never applied ──────────────────────────


def test_apply_spec_shuttle_name_warns_and_is_not_applied(tmp_path):
    config_path = _make_config(tmp_path)
    spec_path = _write_spec(tmp_path, 'shuttle_name: "MPW-42"\ninterface: semicolab\n')

    with pytest.warns(UserWarning, match="VF_SHUTTLE_NAME_NOT_APPLIED"):
        applied = apply_spec(spec_path, config_path)

    assert "shuttle_name" not in applied
    assert applied == {"interface": "semicolab"}


# ── 4. Error paths ─────────────────────────────────────────────────────────────


def test_apply_spec_missing_spec_file_raises(tmp_path):
    config_path = _make_config(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        apply_spec(tmp_path / "does_not_exist.yaml", config_path)
    assert exc_info.value.code == "VF_SHUTTLE_SPEC_NOT_FOUND"


def test_apply_spec_invalid_yaml_raises(tmp_path):
    config_path = _make_config(tmp_path)
    spec_path = tmp_path / "shuttle_spec.yaml"
    spec_path.write_text("interface: [unterminated\n", encoding="utf-8")

    with pytest.raises(VeriFlowError) as exc_info:
        apply_spec(spec_path, config_path)
    assert exc_info.value.code == "VF_SHUTTLE_SPEC_YAML_ERROR"


def test_apply_spec_invalid_technology_name_raises_same_error_as_project_set(tmp_path):
    """No definition supplied and the name isn't a registered profile --
    apply_spec must go through the same validated path as `project set
    technology`, not silently accept anything (proves reuse, not
    duplication, of set_config's validation)."""
    config_path = _make_config(tmp_path)
    spec_path = _write_spec(tmp_path, "technology: totally_bogus_tech_name\n")

    with pytest.raises(VeriFlowError) as exc_info:
        apply_spec(spec_path, config_path)
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


# ── 5. config_path=None uses the same VERIFLOW_CONFIG resolution as the CLI ──


def test_apply_spec_default_config_path_respects_env_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    custom_config = tmp_path / "shuttle_a.yaml"
    custom_config.write_text(render_project_config_yaml(), encoding="utf-8")
    monkeypatch.setenv("VERIFLOW_CONFIG", "shuttle_a.yaml")

    spec_path = _write_spec(tmp_path, "interface: semicolab\n")
    applied = apply_spec(spec_path, config_path=None)

    assert applied == {"interface": "semicolab"}
    data = yaml.safe_load(custom_config.read_text(encoding="utf-8"))
    assert data["interface"] == {"name": "semicolab"}


def test_apply_spec_default_config_path_falls_back_to_veriflow_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VERIFLOW_CONFIG", raising=False)
    default_config = tmp_path / "veriflow.yaml"
    default_config.write_text(render_project_config_yaml(), encoding="utf-8")

    spec_path = _write_spec(tmp_path, "interface: semicolab\n")
    applied = apply_spec(spec_path, config_path=None)

    assert applied == {"interface": "semicolab"}
