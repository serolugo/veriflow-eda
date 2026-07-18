"""Regression tests for the VERIFLOW_CONFIG environment variable
(2026-07-18): every Project Mode `--config` argument's default should be,
in priority order: an explicit `--config` on the command line, then the
`VERIFLOW_CONFIG` env var, then the literal "veriflow.yaml".
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.cli import build_parser, main


PROJECT_SUBCOMMANDS_WITH_CONFIG = [
    ["project", "run"],
    ["project", "set", "interface", "semicolab"],
    ["project", "generate-readme"],
    ["project", "import", "--db", "somedb"],
    ["project", "apply-spec", "spec.yaml"],
]


@pytest.mark.parametrize("argv", PROJECT_SUBCOMMANDS_WITH_CONFIG, ids=lambda a: a[1])
def test_default_config_is_veriflow_yaml_without_env_var(argv, monkeypatch):
    monkeypatch.delenv("VERIFLOW_CONFIG", raising=False)
    parser = build_parser()
    args = parser.parse_args(argv)
    assert args.config == "veriflow.yaml"


@pytest.mark.parametrize("argv", PROJECT_SUBCOMMANDS_WITH_CONFIG, ids=lambda a: a[1])
def test_env_var_overrides_default_when_config_omitted(argv, monkeypatch):
    monkeypatch.setenv("VERIFLOW_CONFIG", "custom/shuttle.yaml")
    parser = build_parser()
    args = parser.parse_args(argv)
    assert args.config == "custom/shuttle.yaml"


@pytest.mark.parametrize("argv", PROJECT_SUBCOMMANDS_WITH_CONFIG, ids=lambda a: a[1])
def test_explicit_config_flag_wins_over_env_var(argv, monkeypatch):
    monkeypatch.setenv("VERIFLOW_CONFIG", "custom/shuttle.yaml")
    parser = build_parser()
    args = parser.parse_args([*argv, "--config", "explicit.yaml"])
    assert args.config == "explicit.yaml"


def test_project_init_config_default_unaffected_by_env_var(monkeypatch):
    """`project init` was explicitly excluded from this change -- its
    --config default stays the literal "veriflow.yaml" regardless of
    VERIFLOW_CONFIG (it's the file *being created*, not read)."""
    monkeypatch.setenv("VERIFLOW_CONFIG", "custom/shuttle.yaml")
    parser = build_parser()
    args = parser.parse_args(["project", "init"])
    assert args.config == "veriflow.yaml"


def test_project_run_actually_reads_the_env_var_resolved_path(tmp_path, monkeypatch):
    """End-to-end: `veriflow project run` (no --config) actually loads the
    file named by VERIFLOW_CONFIG, not the hardcoded "veriflow.yaml"."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")

    custom_config = tmp_path / "shuttle_a.yaml"
    custom_config.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - rtl/top.v\n",
        encoding="utf-8",
    )
    # A decoy "veriflow.yaml" that must NOT be the one picked up
    (tmp_path / "veriflow.yaml").write_text(
        "design:\n  top_module: decoy\n  rtl_sources:\n    - rtl/top.v\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("VERIFLOW_CONFIG", "shuttle_a.yaml")

    from veriflow.workflows.project_config import ProjectWorkflowConfig

    with patch("veriflow.commands.run_project.cmd_run_project") as mock_cmd:
        mock_cmd.return_value = 0
        main(["project", "run"])
        called_config_path = mock_cmd.call_args[0][0]

    assert Path(called_config_path).name == "shuttle_a.yaml"

    # Sanity: the resolved path really does point at the non-decoy config
    cfg = ProjectWorkflowConfig.from_file(called_config_path, validate_rtl_sources=False)
    assert cfg.top_module == "top"
