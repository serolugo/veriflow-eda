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
    assert "FileNotFoundError" not in output
