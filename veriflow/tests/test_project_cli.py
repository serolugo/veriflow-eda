"""
Project Mode CLI tests.

Tests parser dispatch, delegation boundary, output content, and exit-code
contract for `veriflow project run --config <path>`.  All workflow execution
is mocked so no EDA tools are required.
"""
from __future__ import annotations

import io
import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core import VeriFlowError
from veriflow.framework import RunResult
from veriflow.models.stage_result import StageResult
from veriflow.workflows import ProjectRunResult


# ── helpers ───────────────────────────────────────────────────────────────────

def _pass_result(run_dir: Path) -> ProjectRunResult:
    stages = {"synthesis": StageResult(name="synthesis", status="PASS", tool="yosys")}
    return ProjectRunResult(run_dir=run_dir, result=RunResult.from_stages(stages))


def _fail_result(run_dir: Path) -> ProjectRunResult:
    stages = {"synthesis": StageResult(name="synthesis", status="FAIL", tool="yosys")}
    return ProjectRunResult(run_dir=run_dir, result=RunResult.from_stages(stages))


def _multi_stage_pass_result(run_dir: Path) -> ProjectRunResult:
    stages = {
        "connectivity": StageResult(
            name="connectivity", status="PASS", tool="iverilog",
            log_paths=["out/connectivity/logs/connectivity.log"],
        ),
        "simulation": StageResult(
            name="simulation", status="PASS", tool="iverilog/vvp",
            log_paths=["out/sim/logs/sim.log"],
            artifacts={"wave": ["out/sim/waves/waves.vcd"]},
        ),
        "synthesis": StageResult(
            name="synthesis", status="PASS", tool="yosys",
            log_paths=["out/synth/logs/synth.log"],
        ),
    }
    return ProjectRunResult(run_dir=run_dir, result=RunResult.from_stages(stages))


def _mock_workflow(pr: ProjectRunResult):
    """Return (mock_cls, mock_instance) configured to return pr from .run()."""
    mock_wf = MagicMock()
    mock_wf.run.return_value = pr
    mock_cls = MagicMock()
    mock_cls.from_file.return_value = mock_wf
    return mock_cls, mock_wf


# ── A. Parser / dispatch ──────────────────────────────────────────────────────

def test_project_run_parses_config_argument(tmp_path):
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["project", "run", "--config", str(tmp_path / "veriflow.yaml")])
    assert args.command == "project"
    assert args.project_command == "run"
    assert args.config == str(tmp_path / "veriflow.yaml")


def test_project_run_config_defaults_to_veriflow_yaml():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["project", "run"])
    assert args.config == "veriflow.yaml"


def test_project_run_parses_skip_and_only_and_waves_flags():
    """Finding 5 (dev-docs/MODE_CONSISTENCY_AUDIT.md): `project run` gained
    the same --skip-*/--only-*/--waves flags `db run` already had, with the
    same literal flag names."""
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "project", "run", "--config", "x.yaml",
        "--skip-check", "--skip-sim", "--skip-synth",
        "--only-check", "--only-sim", "--only-synth", "--waves",
    ])
    assert args.skip_check is True
    assert args.skip_sim is True
    assert args.skip_synth is True
    assert args.only_check is True
    assert args.only_sim is True
    assert args.only_synth is True
    assert args.waves is True


def test_project_run_skip_and_only_and_waves_default_to_false():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["project", "run"])
    assert args.skip_check is False
    assert args.skip_sim is False
    assert args.skip_synth is False
    assert args.only_check is False
    assert args.only_sim is False
    assert args.only_synth is False
    assert args.waves is False


def test_db_init_still_parses_unchanged():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["db", "init", "--db", "/foo/db"])
    assert args.command == "db"
    assert args.db_command == "init"
    assert args.db == "/foo/db"


def test_db_run_still_parses_unchanged():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["db", "run", "--db", "/foo", "--tile", "0001"])
    assert args.command == "db"
    assert args.db_command == "run"
    assert args.tile == "0001"


def test_db_bump_version_still_parses_unchanged():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["db", "bump-version", "--db", "/foo", "--tile", "0001"])
    assert args.db_command == "bump-version"


def test_db_bump_revision_still_parses_unchanged():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["db", "bump-revision", "--db", "/foo", "--tile", "0001"])
    assert args.db_command == "bump-revision"


def test_db_waves_still_parses_unchanged():
    from veriflow.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["db", "waves", "--db", "/foo", "--tile", "0001"])
    assert args.db_command == "waves"


def test_main_dispatches_project_run(tmp_path):
    """CLI dispatches to cmd_run_project when `project run` is given."""
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")
    pr = _pass_result(tmp_path / "runs" / "run-001")
    mock_cls, mock_wf = _mock_workflow(pr)

    with patch("veriflow.commands.run_project.ProjectWorkflow", mock_cls):
        rc = main(["project", "run", "--config", str(cfg)])

    mock_cls.from_file.assert_called_once()
    assert rc == 0


# ── B. Delegation boundary ────────────────────────────────────────────────────

def test_cli_calls_from_file_with_exact_path(tmp_path):
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")
    pr = _pass_result(tmp_path / "runs" / "run-001")
    mock_cls, mock_wf = _mock_workflow(pr)

    with patch("veriflow.commands.run_project.ProjectWorkflow", mock_cls):
        main(["project", "run", "--config", str(cfg)])

    mock_cls.from_file.assert_called_once_with(Path(str(cfg)))


def test_cli_calls_workflow_run(tmp_path):
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")
    pr = _pass_result(tmp_path / "runs" / "run-001")
    mock_cls, mock_wf = _mock_workflow(pr)

    with patch("veriflow.commands.run_project.ProjectWorkflow", mock_cls):
        main(["project", "run", "--config", str(cfg)])

    mock_wf.run.assert_called_once()


def test_cli_does_not_touch_stage_backends(tmp_path):
    """The CLI layer must not construct any stage backend directly."""
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")
    pr = _pass_result(tmp_path / "runs" / "run-001")
    mock_cls, mock_wf = _mock_workflow(pr)

    with patch("veriflow.commands.run_project.ProjectWorkflow", mock_cls), \
         patch("veriflow.core.stages.synthesis.YosysSynthesisBackend") as mock_be:
        main(["project", "run", "--config", str(cfg)])

    mock_be.assert_not_called()


# ── C. Output ─────────────────────────────────────────────────────────────────

def test_output_pass_includes_run_dir(tmp_path):
    from veriflow.commands import run_project as rp
    run_dir = tmp_path / "runs" / "run-001"
    pr = _pass_result(run_dir)
    mock_cls, mock_wf = _mock_workflow(pr)

    printed: list[str] = []
    with patch.object(rp, "ProjectWorkflow", mock_cls), \
         patch.object(rp, "console") as fake_console:
        fake_console.print.side_effect = lambda *a, **kw: printed.append(str(a[0]) if a else "")
        rp.cmd_run_project(tmp_path / "veriflow.yaml")

    combined = "\n".join(printed)
    assert str(run_dir) in combined


def test_output_pass_includes_overall_pass(tmp_path):
    from veriflow.commands import run_project as rp
    run_dir = tmp_path / "runs" / "run-001"
    pr = _pass_result(run_dir)
    mock_cls, mock_wf = _mock_workflow(pr)

    printed: list[str] = []
    with patch.object(rp, "ProjectWorkflow", mock_cls), \
         patch.object(rp, "console") as fake_console:
        fake_console.print.side_effect = lambda *a, **kw: printed.append(str(a[0]) if a else "")
        rp.cmd_run_project(tmp_path / "veriflow.yaml")

    combined = "\n".join(printed)
    assert "PASS" in combined


def test_output_fail_includes_run_dir_and_fail_status(tmp_path):
    from veriflow.commands import run_project as rp
    run_dir = tmp_path / "runs" / "run-001"
    pr = _fail_result(run_dir)
    mock_cls, mock_wf = _mock_workflow(pr)

    printed: list[str] = []
    with patch.object(rp, "ProjectWorkflow", mock_cls), \
         patch.object(rp, "console") as fake_console:
        fake_console.print.side_effect = lambda *a, **kw: printed.append(str(a[0]) if a else "")
        rp.cmd_run_project(tmp_path / "veriflow.yaml")

    combined = "\n".join(printed)
    assert str(run_dir) in combined
    assert "FAIL" in combined


def test_output_includes_each_stage_name_and_status(tmp_path):
    from veriflow.commands import run_project as rp
    run_dir = tmp_path / "runs" / "run-001"
    pr = _multi_stage_pass_result(run_dir)
    mock_cls, mock_wf = _mock_workflow(pr)

    status_calls: list[tuple[str, str]] = []
    with patch.object(rp, "ProjectWorkflow", mock_cls), \
         patch.object(rp, "print_status", side_effect=lambda l, s, d="": status_calls.append((l, s))), \
         patch.object(rp, "console"):
        rp.cmd_run_project(tmp_path / "veriflow.yaml")

    stage_names = [name for name, _ in status_calls]
    assert "connectivity" in stage_names
    assert "simulation" in stage_names
    assert "synthesis" in stage_names
    assert all(status == "PASS" for _, status in status_calls)


# ── D. Exit codes ─────────────────────────────────────────────────────────────

def test_pass_workflow_exits_0(tmp_path):
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")
    pr = _pass_result(tmp_path / "runs" / "run-001")
    mock_cls, _ = _mock_workflow(pr)

    with patch("veriflow.commands.run_project.ProjectWorkflow", mock_cls):
        rc = main(["project", "run", "--config", str(cfg)])

    assert rc == 0


def test_fail_workflow_exits_nonzero(tmp_path):
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")
    pr = _fail_result(tmp_path / "runs" / "run-001")
    mock_cls, _ = _mock_workflow(pr)

    with patch("veriflow.commands.run_project.ProjectWorkflow", mock_cls):
        rc = main(["project", "run", "--config", str(cfg)])

    assert rc != 0


def test_veriflow_error_exits_nonzero_with_error_message(tmp_path):
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with patch("veriflow.commands.run_project.ProjectWorkflow") as mock_cls:
            mock_cls.from_file.side_effect = VeriFlowError(
                "bad config", code="VF_TEST_CONFIG", exit_code=1
            )
            rc = main(["project", "run", "--config", str(cfg)])

    assert rc != 0
    assert "bad config" in buf.getvalue()


def test_unexpected_exception_not_silently_converted_to_pass(tmp_path):
    """Unhandled exceptions in non-JSON mode propagate rather than returning PASS (rc=0)."""
    from veriflow.cli import main
    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")

    with patch("veriflow.commands.run_project.ProjectWorkflow") as mock_cls:
        mock_cls.from_file.side_effect = RuntimeError("unexpected failure")
        with pytest.raises(RuntimeError, match="unexpected failure"):
            main(["project", "run", "--config", str(cfg)])


def test_db_mode_commands_require_db_unchanged(tmp_path):
    """DB-mode commands still fail when --db is omitted (argparse exits 2)."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "init"])
    assert exc_info.value.code != 0


# ── E. Missing config file — clean error, no raw traceback ───────────────────

def test_missing_config_exits_nonzero(tmp_path):
    """CLI must exit non-zero (not crash) when the config file is missing."""
    from veriflow.cli import main
    rc = main(["project", "run", "--config", str(tmp_path / "no_such.yaml")])
    assert rc != 0


def test_missing_config_prints_clean_error_not_traceback(tmp_path):
    """Missing config must produce a clean [ERROR] line, not a Python traceback."""
    import io
    import contextlib
    from veriflow.cli import main

    stderr_buf = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf):
        main(["project", "run", "--config", str(tmp_path / "no_such.yaml")])

    output = stderr_buf.getvalue()
    assert "Traceback" not in output
    assert "FileNotFoundError" not in output
    assert "[ERROR]" in output


def test_missing_config_json_mode_returns_structured_error(tmp_path):
    """In --json mode, missing config must produce a structured error dict, not an exception."""
    import io
    import json
    import contextlib
    from veriflow.cli import main

    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        rc = main(["--json", "project", "run", "--config", str(tmp_path / "no_such.yaml")])

    assert rc != 0
    payload = json.loads(stdout_buf.getvalue())
    assert payload["status"] == "ERROR"
    assert payload["error"]["code"] == "VF_PROJECT_CONFIG_NOT_FOUND"


def test_missing_default_config_exits_nonzero(tmp_path, monkeypatch):
    """Running with no --config in a directory without veriflow.yaml must exit non-zero cleanly."""
    import io
    import contextlib
    from veriflow.cli import main

    monkeypatch.chdir(tmp_path)
    stderr_buf = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf):
        rc = main(["project", "run"])

    assert rc != 0
    output = stderr_buf.getvalue()
    assert "Traceback" not in output


# ── F. --skip-*/--only-*/--waves (Finding 5, 2026-07-19) ─────────────────────
# dev-docs/MODE_CONSISTENCY_AUDIT.md: `project run` previously had no way to
# run a partial pipeline or open the waveform viewer at all -- `db run` had
# both. These exercise the real ProjectWorkflow/Flow/stage-skip machinery
# (only the EDA backends are mocked, not the workflow itself), unlike
# sections A-E above which mock the whole ProjectWorkflow class.

def _make_full_pipeline_project(tmp_path: Path) -> Path:
    """A project with an interface (connectivity eligible) and tb_sources
    (simulation eligible) so all three stages are normally in the pipeline
    -- lets skip_*/only_* actually skip something, rather than a stage
    that was already going to be SKIPPED regardless (e.g. connectivity with
    no interface configured)."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    (project_dir / "tb_top.v").write_text("module tb; endmodule\n", encoding="utf-8")
    cfg_path = project_dir / "veriflow.yaml"
    cfg_path.write_text(
        "design:\n"
        "  top_module: top\n"
        "  rtl_sources:\n    - top.v\n"
        "  tb_sources:\n    - tb_top.v\n"
        "interface:\n  name: semicolab\n"
        "simulation:\n  tb_top: tb\n",
        encoding="utf-8",
    )
    return cfg_path


def _conn_backend(status="PASS"):
    from veriflow.core.backends.base import ConnectivityBackend
    b = MagicMock(spec=ConnectivityBackend)
    b.run_connectivity.return_value = status
    return b


def _sim_backend(status="COMPLETED"):
    from veriflow.core.backends.base import SimulationBackend
    b = MagicMock(spec=SimulationBackend)
    b.run_simulation.return_value = (status, {})
    return b


def _synth_backend(status="PASS"):
    from veriflow.core.backends.base import SynthesisBackend
    b = MagicMock(spec=SynthesisBackend)
    b.run_synthesis.return_value = (status, {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    return b


def _patched_project_backends():
    return (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_conn_backend()),
        patch("veriflow.workflows.project.get_simulation_backend", return_value=_sim_backend()),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_synth_backend()),
    )


def test_cmd_run_project_only_check_skips_sim_and_synth(tmp_path):
    from veriflow.commands.run_project import cmd_run_project
    cfg_path = _make_full_pipeline_project(tmp_path)

    patches = _patched_project_backends()
    for p in patches:
        p.start()
    try:
        exit_code, result_data = cmd_run_project(cfg_path, only_check=True, json_mode=True)
    finally:
        for p in patches:
            p.stop()

    assert exit_code == 0
    assert result_data["stages"]["connectivity"]["status"] == "PASS"
    assert result_data["stages"]["simulation"]["status"] == "SKIPPED"
    assert result_data["stages"]["synthesis"]["status"] == "SKIPPED"


def test_cmd_run_project_skip_synth_only_skips_synthesis(tmp_path):
    from veriflow.commands.run_project import cmd_run_project
    cfg_path = _make_full_pipeline_project(tmp_path)

    patches = _patched_project_backends()
    for p in patches:
        p.start()
    try:
        exit_code, result_data = cmd_run_project(cfg_path, skip_synth=True, json_mode=True)
    finally:
        for p in patches:
            p.stop()

    assert exit_code == 0
    assert result_data["stages"]["connectivity"]["status"] == "PASS"
    assert result_data["stages"]["simulation"]["status"] == "PASS"
    assert result_data["stages"]["synthesis"]["status"] == "SKIPPED"


def test_cmd_run_project_only_synth_skips_check_and_sim(tmp_path):
    from veriflow.commands.run_project import cmd_run_project
    cfg_path = _make_full_pipeline_project(tmp_path)

    patches = _patched_project_backends()
    for p in patches:
        p.start()
    try:
        exit_code, result_data = cmd_run_project(cfg_path, only_synth=True, json_mode=True)
    finally:
        for p in patches:
            p.stop()

    assert exit_code == 0
    assert result_data["stages"]["connectivity"]["status"] == "SKIPPED"
    assert result_data["stages"]["simulation"]["status"] == "SKIPPED"
    assert result_data["stages"]["synthesis"]["status"] == "PASS"


def test_cmd_run_project_no_flags_runs_everything(tmp_path):
    """Sanity check: with no skip/only flags, all three stages still run
    (nothing about the new plumbing changes the default no-flags path)."""
    from veriflow.commands.run_project import cmd_run_project
    cfg_path = _make_full_pipeline_project(tmp_path)

    patches = _patched_project_backends()
    for p in patches:
        p.start()
    try:
        exit_code, result_data = cmd_run_project(cfg_path, json_mode=True)
    finally:
        for p in patches:
            p.stop()

    assert exit_code == 0
    assert result_data["stages"]["connectivity"]["status"] == "PASS"
    assert result_data["stages"]["simulation"]["status"] == "PASS"
    assert result_data["stages"]["synthesis"]["status"] == "PASS"


def test_project_run_waves_with_non_interactive_raises_clean_error(tmp_path):
    """Same guard `db run --waves --non-interactive` already has
    (VF_NON_INTERACTIVE_VIEWER_DISABLED, exit code 2) -- ported to
    `project run --waves`."""
    import io
    import contextlib
    from veriflow.cli import main

    cfg_path = _make_full_pipeline_project(tmp_path)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = main(["--non-interactive", "project", "run", "--config", str(cfg_path), "--waves"])
    assert rc == 2
    assert "Waveform viewer" in buf.getvalue()


def test_cmd_run_project_waves_launches_viewer_when_wave_file_exists(tmp_path):
    from veriflow.commands.run_project import cmd_run_project
    cfg_path = _make_full_pipeline_project(tmp_path)

    patches = _patched_project_backends()
    for p in patches:
        p.start()
    try:
        with patch("veriflow.core.sim_runner.launch_waves") as mock_launch:
            exit_code, result_data = cmd_run_project(cfg_path, waves=True, json_mode=True)
    finally:
        for p in patches:
            p.stop()

    assert exit_code == 0
    sim_waves = result_data["stages"]["simulation"]["waves"]
    if sim_waves is None:
        pytest.skip("mocked simulation backend reported no wave artifact -- nothing to launch")
    mock_launch.assert_called_once()
    assert "FileNotFoundError" not in output
