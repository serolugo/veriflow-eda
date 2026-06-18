"""Tests for render_project_config_yaml() and cmd_init_project.

veriflow project init now generates a scaffold with no arguments.
api.project_init() has been removed; these tests cover the scaffold
output, the --force guard, and the contract that the raw scaffold is
not runnable until the user fills in design.top_module / rtl_sources.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from veriflow.core import VeriFlowError
from veriflow.core.project_config_template import render_project_config_yaml


# ── render_project_config_yaml() ─────────────────────────────────────────────

def test_render_returns_string():
    assert isinstance(render_project_config_yaml(), str)


def test_render_non_empty():
    assert len(render_project_config_yaml()) > 0


def test_render_has_comment_header():
    result = render_project_config_yaml()
    assert result.startswith("#")
    assert "VeriFlow" in result


def test_render_references_docs():
    assert "PROJECT_CONFIG.md" in render_project_config_yaml()


def test_render_has_design_section():
    assert "design:" in render_project_config_yaml()


def test_render_has_top_module_key():
    assert "top_module:" in render_project_config_yaml()


def test_render_has_rtl_sources_key():
    assert "rtl_sources:" in render_project_config_yaml()


def test_render_parseable_yaml():
    doc = yaml.safe_load(render_project_config_yaml())
    assert isinstance(doc, dict)


def test_render_design_top_module_is_empty_string():
    doc = yaml.safe_load(render_project_config_yaml())
    assert doc["design"]["top_module"] == ""


def test_render_design_rtl_sources_is_empty_list():
    doc = yaml.safe_load(render_project_config_yaml())
    assert doc["design"]["rtl_sources"] == []


def test_render_no_interface_in_parsed_yaml():
    doc = yaml.safe_load(render_project_config_yaml())
    assert "interface" not in (doc or {})


def test_render_no_simulation_in_parsed_yaml():
    doc = yaml.safe_load(render_project_config_yaml())
    assert "simulation" not in (doc or {})


def test_render_no_execution_in_parsed_yaml():
    doc = yaml.safe_load(render_project_config_yaml())
    assert "execution" not in (doc or {})


def test_render_no_technology_in_parsed_yaml():
    doc = yaml.safe_load(render_project_config_yaml())
    assert "technology" not in (doc or {})


def test_render_no_output_in_parsed_yaml():
    doc = yaml.safe_load(render_project_config_yaml())
    assert "output" not in (doc or {})


def test_render_optional_sections_appear_as_comments():
    result = render_project_config_yaml()
    assert "# interface:" in result
    assert "# execution:" in result
    assert "# simulation:" in result


def test_render_scaffold_is_pure_ascii():
    """Scaffold must encode as ASCII so it never mojibakes on Windows (cp1252)."""
    result = render_project_config_yaml()
    result.encode("ascii")


def test_render_scaffold_not_valid_for_project_run():
    """Raw scaffold fails validation — user must fill in top_module and rtl_sources."""
    from veriflow.workflows.project_config import ProjectWorkflowConfig
    doc = yaml.safe_load(render_project_config_yaml())
    with pytest.raises(VeriFlowError) as exc_info:
        ProjectWorkflowConfig.from_dict(doc, root=Path("."))
    assert exc_info.value.code in ("VF_DESIGN_TOP_REQUIRED", "VF_DESIGN_RTL_REQUIRED")


# ── cmd_init_project ─────────────────────────────────────────────────────────

def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {
        "config": "veriflow.yaml",
        "force": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_cli_init_writes_file(tmp_path):
    from veriflow.commands.init_project import cmd_init_project
    out = tmp_path / "veriflow.yaml"
    rc = cmd_init_project(_make_args(config=str(out)))
    assert rc == 0
    assert out.exists()


def test_cli_init_file_contains_scaffold_comments(tmp_path):
    from veriflow.commands.init_project import cmd_init_project
    out = tmp_path / "veriflow.yaml"
    cmd_init_project(_make_args(config=str(out)))
    content = out.read_text(encoding="utf-8")
    assert "VeriFlow" in content
    assert "top_module" in content
    assert "rtl_sources" in content


def test_cli_init_file_is_parseable_yaml(tmp_path):
    from veriflow.commands.init_project import cmd_init_project
    out = tmp_path / "veriflow.yaml"
    cmd_init_project(_make_args(config=str(out)))
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "design" in doc


def test_cli_init_config_exists_raises(tmp_path):
    from veriflow.commands.init_project import cmd_init_project
    out = tmp_path / "veriflow.yaml"
    out.write_text("existing", encoding="utf-8")
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_init_project(_make_args(config=str(out)))
    assert exc_info.value.code == "VF_PROJECT_CONFIG_EXISTS"


def test_cli_init_config_exists_not_overwritten_without_force(tmp_path):
    from veriflow.commands.init_project import cmd_init_project
    out = tmp_path / "veriflow.yaml"
    out.write_text("existing", encoding="utf-8")
    try:
        cmd_init_project(_make_args(config=str(out)))
    except VeriFlowError:
        pass
    assert out.read_text(encoding="utf-8") == "existing"


def test_cli_init_force_overwrites(tmp_path):
    from veriflow.commands.init_project import cmd_init_project
    out = tmp_path / "veriflow.yaml"
    out.write_text("old content", encoding="utf-8")
    rc = cmd_init_project(_make_args(config=str(out), force=True))
    assert rc == 0
    content = out.read_text(encoding="utf-8")
    assert "old content" not in content
    assert "design:" in content


# ── CLI dispatch ──────────────────────────────────────────────────────────────

def test_cli_dispatch_project_init(tmp_path):
    from veriflow.cli import main
    out = tmp_path / "veriflow.yaml"
    rc = main(["project", "init", "--config", str(out)])
    assert rc == 0
    assert out.exists()


def test_cli_dispatch_project_init_parser_args():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["project", "init"])
    assert args.project_command == "init"
    assert args.config == "veriflow.yaml"
    assert args.force is False


def test_cli_dispatch_project_init_no_flags_accepted():
    """Confirm that --top/--tb/--interface are no longer accepted."""
    from veriflow.cli import build_parser
    import pytest
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["project", "init", "--top", "mymod", "a.v"])


def test_cli_dispatch_project_init_force_flag(tmp_path):
    from veriflow.cli import main
    out = tmp_path / "veriflow.yaml"
    out.write_text("old", encoding="utf-8")
    rc = main(["project", "init", "--force", "--config", str(out)])
    assert rc == 0
    assert "design:" in out.read_text(encoding="utf-8")
