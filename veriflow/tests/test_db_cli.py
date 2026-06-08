"""
Database Mode `veriflow db ...` namespace CLI tests.

Covers:
  A. Parser / argument parsing for each db subcommand
  B. Dispatch — each subcommand calls the correct handler with correct args
  C. Legacy compatibility — flat legacy commands and `project run` unaffected
  D. Error behavior — missing required args fail clearly
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core import VeriFlowError


# ── A. Parser / argument parsing ──────────────────────────────────────────────

def test_db_init_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["db", "init", "--db", str(tmp_path)])
    assert args.command == "db"
    assert args.db_command == "init"
    assert args.db == str(tmp_path)
    assert args.force is False


def test_db_init_parses_force(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["db", "init", "--db", str(tmp_path), "--force"])
    assert args.force is True


def test_db_create_tile_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(
        ["db", "create-tile", "--db", str(tmp_path), "--top-module", "my_tile"]
    )
    assert args.command == "db"
    assert args.db_command == "create-tile"
    assert args.db == str(tmp_path)
    assert args.top_module == "my_tile"


def test_db_create_tile_top_module_defaults_to_empty(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["db", "create-tile", "--db", str(tmp_path)])
    assert args.top_module == ""


def test_db_run_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["db", "run", "--db", str(tmp_path), "--tile", "0001"])
    assert args.command == "db"
    assert args.db_command == "run"
    assert args.db == str(tmp_path)
    assert args.tile == "0001"
    assert args.skip_check is False
    assert args.skip_sim is False
    assert args.skip_synth is False
    assert args.only_check is False
    assert args.only_sim is False
    assert args.only_synth is False
    assert args.waves is False


def test_db_run_parses_skip_flags(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args([
        "db", "run", "--db", str(tmp_path), "--tile", "0001",
        "--skip-check", "--skip-sim", "--only-synth",
    ])
    assert args.skip_check is True
    assert args.skip_sim is True
    assert args.only_synth is True


def test_db_waves_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(
        ["db", "waves", "--db", str(tmp_path), "--tile", "0001", "--run", "run-002"]
    )
    assert args.command == "db"
    assert args.db_command == "waves"
    assert args.db == str(tmp_path)
    assert args.tile == "0001"
    assert args.run == "run-002"


def test_db_waves_run_defaults_to_none(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["db", "waves", "--db", str(tmp_path), "--tile", "0001"])
    assert args.run is None


def test_db_bump_version_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(
        ["db", "bump-version", "--db", str(tmp_path), "--tile", "0001"]
    )
    assert args.command == "db"
    assert args.db_command == "bump-version"
    assert args.db == str(tmp_path)
    assert args.tile == "0001"


def test_db_bump_revision_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(
        ["db", "bump-revision", "--db", str(tmp_path), "--tile", "0001"]
    )
    assert args.command == "db"
    assert args.db_command == "bump-revision"
    assert args.db == str(tmp_path)
    assert args.tile == "0001"


# ── B. Dispatch ───────────────────────────────────────────────────────────────

def test_db_namespace_init_dispatches_to_cmd_init(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.init_db.cmd_init") as mock_fn:
        rc = main(["db", "init", "--db", str(tmp_path)])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), force=False)
    assert rc == 0


def test_db_namespace_init_force_flag_forwarded(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.init_db.cmd_init") as mock_fn:
        rc = main(["db", "init", "--db", str(tmp_path), "--force"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), force=True)
    assert rc == 0


def test_db_namespace_create_tile_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.create_tile.cmd_create_tile") as mock_fn:
        rc = main(["db", "create-tile", "--db", str(tmp_path), "--top-module", "my_tile"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), top_module="my_tile")
    assert rc == 0


def test_db_namespace_run_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.run.cmd_run") as mock_fn:
        mock_fn.return_value = {"status": "PASS"}
        rc = main(["db", "run", "--db", str(tmp_path), "--tile", "0001"])
    mock_fn.assert_called_once_with(
        db=Path(str(tmp_path)),
        tile_number="0001",
        skip_check=False,
        skip_sim=False,
        skip_synth=False,
        only_check=False,
        only_sim=False,
        only_synth=False,
        waves=False,
    )
    assert rc == 0


def test_db_namespace_run_forwards_skip_flags(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.run.cmd_run") as mock_fn:
        mock_fn.return_value = {}
        main(["db", "run", "--db", str(tmp_path), "--tile", "0001", "--skip-check", "--only-synth"])
    _, kwargs = mock_fn.call_args
    assert kwargs["skip_check"] is True
    assert kwargs["only_synth"] is True


def test_db_namespace_waves_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.waves.cmd_waves") as mock_fn:
        rc = main(["db", "waves", "--db", str(tmp_path), "--tile", "0001"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), tile_number="0001", run_id=None)
    assert rc == 0


def test_db_namespace_waves_run_id_forwarded(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.waves.cmd_waves") as mock_fn:
        main(["db", "waves", "--db", str(tmp_path), "--tile", "0001", "--run", "run-003"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), tile_number="0001", run_id="run-003")


def test_db_namespace_bump_version_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.bump_version.cmd_bump_version") as mock_fn:
        rc = main(["db", "bump-version", "--db", str(tmp_path), "--tile", "0001"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), tile_number="0001")
    assert rc == 0


def test_db_namespace_bump_revision_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.bump_revision.cmd_bump_revision") as mock_fn:
        rc = main(["db", "bump-revision", "--db", str(tmp_path), "--tile", "0001"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), tile_number="0001")
    assert rc == 0


def test_db_namespace_veriflow_error_exits_nonzero(tmp_path):
    from veriflow.cli import main
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with patch("veriflow.commands.init_db.cmd_init") as mock_fn:
            mock_fn.side_effect = VeriFlowError("boom", code="VF_TEST", exit_code=1)
            rc = main(["db", "init", "--db", str(tmp_path)])
    assert rc != 0
    assert "boom" in buf.getvalue()


def test_db_namespace_run_non_interactive_waves_raises(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.run.cmd_run"):
        rc = main([
            "--non-interactive",
            "db", "run", "--db", str(tmp_path), "--tile", "0001", "--waves",
        ])
    assert rc != 0


def test_db_namespace_waves_non_interactive_raises(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.waves.cmd_waves"):
        rc = main(["--non-interactive", "db", "waves", "--db", str(tmp_path), "--tile", "0001"])
    assert rc != 0


# ── C. Legacy compatibility ───────────────────────────────────────────────────

def test_legacy_init_still_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["--db", "/foo/db", "init"])
    assert args.command == "init"
    assert args.db == "/foo/db"


def test_legacy_create_tile_still_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["--db", "/foo", "create-tile", "--top-module", "m"])
    assert args.command == "create-tile"
    assert args.top_module == "m"


def test_legacy_run_still_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["--db", "/foo", "run", "--tile", "0001"])
    assert args.command == "run"
    assert args.tile == "0001"


def test_legacy_waves_still_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["--db", "/foo", "waves", "--tile", "0001"])
    assert args.command == "waves"


def test_legacy_bump_version_still_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["--db", "/foo", "bump-version", "--tile", "0001"])
    assert args.command == "bump-version"


def test_legacy_bump_revision_still_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["--db", "/foo", "bump-revision", "--tile", "0001"])
    assert args.command == "bump-revision"


def test_legacy_init_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.init_db.cmd_init") as mock_fn:
        rc = main(["--db", str(tmp_path), "init"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), force=False)
    assert rc == 0


def test_legacy_run_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.run.cmd_run") as mock_fn:
        mock_fn.return_value = {}
        rc = main(["--db", str(tmp_path), "run", "--tile", "0002"])
    mock_fn.assert_called_once_with(
        db=Path(str(tmp_path)),
        tile_number="0002",
        skip_check=False,
        skip_sim=False,
        skip_synth=False,
        only_check=False,
        only_sim=False,
        only_synth=False,
        waves=False,
    )
    assert rc == 0


def test_project_run_still_works(tmp_path):
    from veriflow.cli import main
    from veriflow.framework import RunResult
    from veriflow.models.stage_result import StageResult
    from veriflow.workflows import ProjectRunResult

    cfg = tmp_path / "veriflow.yaml"
    cfg.write_text("")
    stages = {"synthesis": StageResult(name="synthesis", status="PASS", tool="yosys")}
    pr = ProjectRunResult(
        run_dir=tmp_path / "runs" / "run-001",
        result=RunResult.from_stages(stages),
    )
    mock_wf = MagicMock()
    mock_wf.run.return_value = pr
    mock_cls = MagicMock()
    mock_cls.from_file.return_value = mock_wf

    with patch("veriflow.commands.run_project.ProjectWorkflow", mock_cls):
        rc = main(["project", "run", "--config", str(cfg)])

    assert rc == 0
    mock_cls.from_file.assert_called_once_with(Path(str(cfg)))


# ── D. Error behavior ─────────────────────────────────────────────────────────

def test_db_run_missing_db_exits_with_error(tmp_path):
    """argparse exits 2 when required --db is absent."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "run", "--tile", "0001"])
    assert exc_info.value.code != 0


def test_db_run_missing_tile_exits_with_error(tmp_path):
    """argparse exits 2 when required --tile is absent."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "run", "--db", str(tmp_path)])
    assert exc_info.value.code != 0


def test_db_init_missing_db_exits_with_error():
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "init"])
    assert exc_info.value.code != 0


def test_db_bump_version_missing_tile_exits_with_error(tmp_path):
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "bump-version", "--db", str(tmp_path)])
    assert exc_info.value.code != 0


def test_legacy_db_commands_require_db_unchanged():
    """Existing flat commands still return non-zero when --db is omitted."""
    from veriflow.cli import main
    rc = main(["init"])
    assert rc != 0
