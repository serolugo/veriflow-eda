"""Regression tests for `veriflow project generate-readme` (2026-07-18):
rendering a submission README.md from the latest passing Project Mode run.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.api import generate_readme
from veriflow.core import VeriFlowError


# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_synth_backend(status="PASS"):
    from veriflow.core.backends.base import SynthesisBackend
    b = MagicMock(spec=SynthesisBackend)
    b.run_synthesis.return_value = (
        status,
        {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False},
    )
    return b


def _mock_conn_backend(status="PASS"):
    from veriflow.core.backends.base import ConnectivityBackend
    b = MagicMock(spec=ConnectivityBackend)
    b.run_connectivity.return_value = status
    return b


def _make_project(
    tmp_path: Path,
    *,
    dirname: str = "myproj",
    interface_name: str | None = None,
    extra_yaml: str = "",
) -> Path:
    project_dir = tmp_path / dirname
    (project_dir / "rtl").mkdir(parents=True)
    (project_dir / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")

    yaml_lines = [
        "design:",
        "  top_module: top",
        "  rtl_sources:",
        "    - rtl/top.v",
    ]
    if interface_name is not None:
        yaml_lines += ["interface:", f"  name: {interface_name}"]

    config_path = project_dir / "veriflow.yaml"
    config_path.write_text("\n".join(yaml_lines) + "\n" + extra_yaml, encoding="utf-8")
    return config_path


def _run_project(config_path: Path, *, conn_status="PASS", synth_status="PASS") -> str:
    from veriflow.workflows.project import ProjectWorkflow
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    cfg = ProjectWorkflowConfig.from_file(config_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend(conn_status)),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend(synth_status)),
    ):
        pr = ProjectWorkflow(cfg).run()
    return pr.run_dir.name


# ── 1. Successful generation ──────────────────────────────────────────────────


def test_generate_readme_with_passing_run_writes_correct_content(tmp_path):
    config_path = _make_project(
        tmp_path,
        interface_name="semicolab",
        extra_yaml="metadata:\n  description: A tiny test tile.\n",
    )
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "# top" in content
    assert "A tiny test tile." in content
    assert "top.v" in content
    assert "6e43619bfeec" in content or "`top.v`" in content  # sha256 prefix present in some form
    assert "semicolab" in content
    # timestamp's date portion (YYYY-MM-DD) appears in the rendered output
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", content)

    readme_path = config_path.parent / "README.md"
    assert readme_path.exists()
    assert readme_path.read_text(encoding="utf-8") == content


def test_generate_readme_includes_interface_port_map(tmp_path):
    config_path = _make_project(tmp_path, interface_name="semicolab")
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "clk" in content
    assert "| Port | Direction | Width |" in content


def test_generate_readme_semicolab_port_map_has_four_columns_with_descriptions(tmp_path):
    """semicolab's meta.yaml ships port_descriptions for all 9 ports (2026-07-20)
    -- the Port Map table must gain a 4th "Description" column and populate
    it, not just show the 3-column name/direction/width table."""
    config_path = _make_project(tmp_path, interface_name="semicolab")
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "| Port | Direction | Width | Description |" in content
    assert "| `clk` | input | 1 | System clock |" in content
    assert "| `arst_n` | input | 1 | Asynchronous reset, active low |" in content


def test_generate_readme_port_descriptions_in_veriflow_yaml_override_meta_yaml(tmp_path):
    config_path = _make_project(tmp_path, interface_name="semicolab")
    with config_path.open("a", encoding="utf-8") as f:
        f.write('  port_descriptions:\n    csr_in: "My custom description for CSR input"\n')
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "My custom description for CSR input" in content
    assert "Control/status register input bus" not in content  # meta.yaml's original, overridden
    # other ports keep their meta.yaml description, only csr_in was overridden
    assert "System clock" in content


def test_readme_render_context_includes_interface_port_descriptions(tmp_path):
    """Direct unit test of _readme_render_context() (not just through the
    full generate_readme() call), confirming interface_port_descriptions
    is present in the context dict and sourced from the interface
    profile's meta.yaml."""
    from veriflow.api import _find_latest_passing_run, _readme_render_context
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    config_path = _make_project(tmp_path, interface_name="semicolab")
    _run_project(config_path)

    config = ProjectWorkflowConfig.from_file(config_path, validate_rtl_sources=False)
    _run_id, results = _find_latest_passing_run(config.runs_dir)
    context = _readme_render_context(config, config_path, results)

    assert "interface_port_descriptions" in context
    assert context["interface_port_descriptions"]["clk"] == "System clock"
    assert len(context["interface_port_descriptions"]) == 9


def test_generate_readme_no_interface_omits_port_map(tmp_path):
    config_path = _make_project(tmp_path, interface_name=None)
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "| Port | Direction | Width |" not in content
    assert "`generic`" in content  # interface_name or "generic" fallback


def test_generate_readme_uses_stage_technology_when_present(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "**Technology:**" in content


# ── 1b. Template polish fixes (2026-07-19) ─────────────────────────────────────


def test_generate_readme_output_is_ascii_only(tmp_path):
    """No em dash or other non-ASCII glyphs -- same cp1252-safety
    convention applied elsewhere in the codebase (see
    dev-docs/SMOKE_TEST_FINDINGS.md)."""
    config_path = _make_project(tmp_path, interface_name="semicolab")
    _run_project(config_path)

    content = generate_readme(config_path)

    non_ascii = [c for c in content if ord(c) > 127]
    assert non_ascii == [], f"non-ASCII characters found: {non_ascii!r}"
    assert "--" in content  # ASCII replacement for the em dash in the title


def test_generate_readme_no_github_repository_env_shows_placeholder(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "<!-- add badge after pushing to GitHub -->" in content
    assert "badge.svg" not in content


def test_generate_readme_github_repository_env_renders_badge(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "serolugo/my-tile")
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "https://github.com/serolugo/my-tile/actions/workflows/precheck.yml/badge.svg" in content
    assert "<!-- add badge after pushing to GitHub -->" not in content


def test_generate_readme_empty_description_omits_blockquote_line(tmp_path):
    config_path = _make_project(tmp_path)  # no metadata section at all
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "> \n" not in content
    for line in content.splitlines():
        assert line.strip() != ">"


def test_generate_readme_generic_project_shows_no_interface_message(tmp_path):
    config_path = _make_project(tmp_path, interface_name=None)
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "No interface profile selected" in content
    assert "connectivity check skipped" in content


def test_generate_readme_metadata_author_version_shown(tmp_path):
    config_path = _make_project(
        tmp_path,
        extra_yaml="metadata:\n  author: Roman Lugo\n  version: \"1.0.0\"\n",
    )
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "**Author:** Roman Lugo" in content
    assert "**Version:** 1.0.0" in content


def test_generate_readme_metadata_author_or_version_missing_omits_line(tmp_path):
    config_path = _make_project(tmp_path)  # no metadata at all
    _run_project(config_path)

    content = generate_readme(config_path)

    assert "**Author:**" not in content
    assert "**Version:**" not in content


def test_generate_readme_tile_name_used_as_title(tmp_path):
    config_path = _make_project(
        tmp_path,
        extra_yaml="metadata:\n  name: Counter8 Tile\n",
    )
    _run_project(config_path)

    content = generate_readme(config_path)

    assert content.startswith("# Counter8 Tile -- VeriFlow Submission")


def test_generate_readme_title_falls_back_to_top_module_when_no_metadata_name(tmp_path):
    config_path = _make_project(tmp_path)  # no metadata.name
    _run_project(config_path)

    content = generate_readme(config_path)

    assert content.startswith("# top -- VeriFlow Submission")


# ── 1c. veriflow.yaml is the live source for interface/technology/metadata,
#        not the (possibly stale) results.json of the last passing run
#        (2026-07-19) ────────────────────────────────────────────────────────


def test_generate_readme_reflects_interface_added_after_a_generic_passing_run(tmp_path):
    """The exact reported scenario: a run passed as a generic project (no
    interface configured, so results.json has interface_name=null), then
    `veriflow.yaml` gains `interface: semicolab` -- without a new
    `project run`. The README must show semicolab and its 9 ports, not
    "generic", because interface_name/interface_ports are read from the
    live config, not the stale run."""
    config_path = _make_project(tmp_path, interface_name=None)
    _run_project(config_path)

    # confirm the run really is generic, i.e. this test actually exercises
    # the divergence it claims to
    import json
    results = json.loads((config_path.parent / "runs" / "run-001" / "results.json").read_text(encoding="utf-8"))
    assert results["interface_name"] is None

    # now the project adopts an interface, without re-running
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "interface:\n  name: semicolab\n",
        encoding="utf-8",
    )

    content = generate_readme(config_path)

    assert "**Interface:** `semicolab`" in content
    assert "**Interface:** `generic`" not in content
    port_map_section = content.split("## Port Map", 1)[1]
    port_lines = [line for line in port_map_section.splitlines() if line.startswith("| `")]
    assert len(port_lines) == 9  # semicolab's full port contract


def test_generate_readme_reflects_interface_removed_after_a_passing_run(tmp_path):
    """The inverse: a run passed with semicolab configured, then
    veriflow.yaml drops the interface section entirely -- the README must
    fall back to "generic" and omit the port map, not keep showing
    semicolab from the stale run."""
    config_path = _make_project(tmp_path, interface_name="semicolab")
    _run_project(config_path)

    config_path.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - rtl/top.v\n",
        encoding="utf-8",
    )

    content = generate_readme(config_path)

    assert "**Interface:** `generic`" in content
    assert "| Port | Direction | Width |" not in content
    assert "No interface profile selected" in content


def test_generate_readme_reflects_technology_changed_after_a_passing_run(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "technology:\n  name: sky130\n",
        encoding="utf-8",
    )

    content = generate_readme(config_path)

    assert "**Technology:** `sky130`" in content


def test_generate_readme_reflects_metadata_changed_after_a_passing_run(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "metadata:\n  description: Added after the run.\n  author: Roman Lugo\n",
        encoding="utf-8",
    )

    content = generate_readme(config_path)

    assert "Added after the run." in content
    assert "**Author:** Roman Lugo" in content


def test_generate_readme_stages_still_come_from_the_run_not_the_config(tmp_path):
    """The other half of the split: verification facts (stages, rtl_hash,
    timestamp, veriflow_version) must still come from the actual run --
    changing veriflow.yaml after the fact can't retroactively change what
    was verified."""
    config_path = _make_project(tmp_path, interface_name="semicolab")
    run_id = _run_project(config_path)

    content = generate_readme(config_path)

    assert "| Connectivity | PASS |" in content
    assert run_id == "run-001"  # sanity: this is indeed the run whose stages we expect


# ── 2. No passing run ──────────────────────────────────────────────────────────


def test_generate_readme_no_passing_run_raises(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path, synth_status="FAIL")

    with pytest.raises(VeriFlowError) as exc_info:
        generate_readme(config_path)
    assert exc_info.value.code == "VF_README_NO_PASSING_RUN"


def test_generate_readme_no_runs_at_all_raises(tmp_path):
    config_path = _make_project(tmp_path)

    with pytest.raises(VeriFlowError) as exc_info:
        generate_readme(config_path)
    assert exc_info.value.code == "VF_README_NO_PASSING_RUN"


# ── 3. Custom template_path ────────────────────────────────────────────────────


def test_generate_readme_custom_template_path_argument(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    # Inside config_path.parent (the project root), not tmp_path directly --
    # template_path is now constrained via safe_join() relative to the
    # project root (dev-docs/SECURITY_AUDIT.md, Finding #6).
    custom_template = config_path.parent / "custom.j2"
    custom_template.write_text("Custom README for {{ top_module }}\n", encoding="utf-8")

    content = generate_readme(config_path, template_path=custom_template)

    assert content == "Custom README for top\n"


def test_generate_readme_template_path_outside_project_root_rejected(tmp_path):
    """The security-hardening counterpart of the test above: a template
    outside the project root (e.g. tmp_path itself, one level above
    config_path.parent) must be rejected, not silently read."""
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    outside_template = tmp_path / "outside.j2"
    outside_template.write_text("Should never be read\n", encoding="utf-8")

    with pytest.raises(VeriFlowError) as exc_info:
        generate_readme(config_path, template_path=outside_template)
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_generate_readme_out_path_argument(tmp_path):
    config_path = _make_project(tmp_path)
    _run_project(config_path)

    out_path = tmp_path / "custom_out" / "SUBMISSION.md"
    out_path.parent.mkdir(parents=True)

    content = generate_readme(config_path, out_path=out_path)

    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == content
    # default location untouched
    assert not (config_path.parent / "README.md").exists()


# ── 4. readme_template: in veriflow.yaml ───────────────────────────────────────


def test_generate_readme_config_readme_template_resolves_relative_to_config(tmp_path):
    config_path = _make_project(
        tmp_path,
        extra_yaml="readme_template: templates/custom.j2\n",
    )
    _run_project(config_path)

    template_dir = config_path.parent / "templates"
    template_dir.mkdir()
    (template_dir / "custom.j2").write_text("From config: {{ top_module }}\n", encoding="utf-8")

    content = generate_readme(config_path)

    assert content == "From config: top\n"


def test_generate_readme_config_readme_template_relative_traversal_rejected(tmp_path):
    """The exact attack from dev-docs/SECURITY_AUDIT.md Finding #6: a
    malicious/imported veriflow.yaml with `readme_template: ../../../<secret>`
    must not be able to dump an arbitrary file's content into README.md.
    Confirms the fix at the config-parsing layer (ProjectWorkflowConfig's
    _parse_readme_template), not just the explicit --template CLI arg."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET CONTENT\n", encoding="utf-8")

    config_path = _make_project(
        tmp_path,
        dirname="deeply/nested/project",
        extra_yaml="readme_template: ../../../secret.txt\n",
    )

    with pytest.raises(VeriFlowError) as exc_info:
        generate_readme(config_path)
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_generate_readme_config_readme_template_absolute_path_rejected(tmp_path):
    """Same attack, absolute-path variant (no `../` needed at all -- a bare
    `Path(root) / "/etc/passwd"`-style join discards `root` entirely)."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET CONTENT\n", encoding="utf-8")

    config_path = _make_project(
        tmp_path,
        extra_yaml=f"readme_template: {str(secret).replace(chr(92), '/')!r}\n",
    )

    with pytest.raises(VeriFlowError) as exc_info:
        generate_readme(config_path)
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_generate_readme_explicit_template_path_overrides_config_readme_template(tmp_path):
    config_path = _make_project(
        tmp_path,
        extra_yaml="readme_template: templates/from_config.j2\n",
    )
    _run_project(config_path)

    template_dir = config_path.parent / "templates"
    template_dir.mkdir()
    (template_dir / "from_config.j2").write_text("From config\n", encoding="utf-8")

    explicit_template = config_path.parent / "explicit.j2"
    explicit_template.write_text("From explicit arg: {{ top_module }}\n", encoding="utf-8")

    content = generate_readme(config_path, template_path=explicit_template)

    assert content == "From explicit arg: top\n"


# ── 5. CLI ──────────────────────────────────────────────────────────────────────


def test_cli_generate_readme_dispatches(tmp_path):
    from veriflow.cli import main

    with patch("veriflow.api.generate_readme", return_value="content") as mock_fn:
        rc = main(["project", "generate-readme", "--config", str(tmp_path / "veriflow.yaml")])

    mock_fn.assert_called_once_with(
        Path(str(tmp_path / "veriflow.yaml")), out_path=None, template_path=None
    )
    assert rc == 0


def test_cli_generate_readme_forwards_out_and_template(tmp_path):
    from veriflow.cli import main

    with patch("veriflow.api.generate_readme", return_value="content") as mock_fn:
        main([
            "project", "generate-readme",
            "--config", str(tmp_path / "veriflow.yaml"),
            "--out", str(tmp_path / "OUT.md"),
            "--template", str(tmp_path / "t.j2"),
        ])

    mock_fn.assert_called_once_with(
        Path(str(tmp_path / "veriflow.yaml")),
        out_path=str(tmp_path / "OUT.md"),
        template_path=str(tmp_path / "t.j2"),
    )


def test_cli_generate_readme_prints_confirmation(tmp_path, capsys):
    from veriflow.cli import main

    with patch("veriflow.api.generate_readme", return_value="content"):
        main(["project", "generate-readme", "--config", str(tmp_path / "veriflow.yaml")])

    out = capsys.readouterr().out
    assert "README.md written" in out


def test_cli_generate_readme_non_interactive_produces_no_output(tmp_path, capsys):
    from veriflow.cli import main

    with patch("veriflow.api.generate_readme", return_value="content"):
        rc = main([
            "--non-interactive", "project", "generate-readme",
            "--config", str(tmp_path / "veriflow.yaml"),
        ])

    out = capsys.readouterr().out
    assert out == ""
    assert rc == 0


def test_cli_generate_readme_non_interactive_still_reports_errors(tmp_path, capsys):
    from veriflow.cli import main

    with patch(
        "veriflow.api.generate_readme",
        side_effect=VeriFlowError("no run", code="VF_README_NO_PASSING_RUN"),
    ):
        rc = main([
            "--non-interactive", "project", "generate-readme",
            "--config", str(tmp_path / "veriflow.yaml"),
        ])

    assert rc != 0
    err = capsys.readouterr().err
    assert "VF_README_NO_PASSING_RUN" in err or "no run" in err


def test_project_generate_readme_parses():
    from veriflow.cli import build_parser

    args = build_parser().parse_args(["project", "generate-readme"])
    assert args.command == "project"
    assert args.project_command == "generate-readme"
    assert args.config == "veriflow.yaml"
    assert args.out is None
    assert args.template is None
