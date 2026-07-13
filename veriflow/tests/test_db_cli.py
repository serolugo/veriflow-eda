"""
Database Mode `veriflow db ...` namespace CLI tests.

Covers:
  A. Parser / argument parsing for each db subcommand
  B. Dispatch — each subcommand calls the correct handler with correct args
  C. Flat legacy forms removed — `veriflow --db ... <cmd>` is rejected; `project run` unaffected
  D. Error behavior — missing required args fail clearly
  E. Read-only read commands (list-tiles, list-runs, show-run)
"""
from __future__ import annotations

import json
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


def test_db_namespace_run_resolves_relative_dot_db_path(tmp_path, monkeypatch):
    """--db . must resolve to an absolute path, not be passed through as '.'."""
    from veriflow.cli import main
    monkeypatch.chdir(tmp_path)
    with patch("veriflow.commands.init_db.cmd_init") as mock_fn:
        rc = main(["db", "init", "--db", "."])
    assert rc == 0
    called_path = mock_fn.call_args.args[0]
    assert called_path.is_absolute()
    assert called_path == tmp_path.resolve()
    assert str(called_path) != "."


def test_db_namespace_create_tile_dispatches(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.create_tile.cmd_create_tile") as mock_fn:
        rc = main(["db", "create-tile", "--db", str(tmp_path), "--top-module", "my_tile"])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), top_module="my_tile", tile_author="")
    assert rc == 0


def test_db_namespace_create_tile_tile_author_forwarded(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.create_tile.cmd_create_tile") as mock_fn:
        rc = main([
            "db", "create-tile", "--db", str(tmp_path),
            "--top-module", "my_tile", "--tile-author", "Roman Lugo",
        ])
    mock_fn.assert_called_once_with(Path(str(tmp_path)), top_module="my_tile", tile_author="Roman Lugo")
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


# ── C. Flat legacy forms removed ──────────────────────────────────────────────

def test_flat_init_rejected():
    """`veriflow --db PATH init` no longer parses; argparse exits 2."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "/foo/db", "init"])
    assert exc_info.value.code == 2


def test_flat_create_tile_rejected():
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "/foo", "create-tile", "--top-module", "m"])
    assert exc_info.value.code == 2


def test_flat_run_rejected():
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "/foo", "run", "--tile", "0001"])
    assert exc_info.value.code == 2


def test_flat_waves_rejected():
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "/foo", "waves", "--tile", "0001"])
    assert exc_info.value.code == 2


def test_flat_bump_version_rejected():
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "/foo", "bump-version", "--tile", "0001"])
    assert exc_info.value.code == 2


def test_flat_bump_revision_rejected():
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "/foo", "bump-revision", "--tile", "0001"])
    assert exc_info.value.code == 2


def test_flat_command_without_db_rejected():
    """`veriflow init` (flat command, no --db) is no longer a known command."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["init"])
    assert exc_info.value.code == 2


def test_root_db_flag_rejected_for_db_namespace():
    """--db is a subcommand argument, not a global flag."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--db", "/foo", "db", "run", "--tile", "0001"])
    assert exc_info.value.code == 2


def test_flat_dispatch_does_not_reach_handlers(tmp_path):
    """Rejected flat forms must exit before any command handler is invoked."""
    from veriflow.cli import main
    with patch("veriflow.commands.run.cmd_run") as mock_fn:
        with pytest.raises(SystemExit):
            main(["--db", str(tmp_path), "run", "--tile", "0002"])
    mock_fn.assert_not_called()


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


def test_db_create_tile_missing_db_exits_with_error():
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "create-tile"])
    assert exc_info.value.code != 0


# ── E. Read-only commands: helpers ────────────────────────────────────────────

def _make_tile_info(
    number: str = "0001",
    tile_id: str = "tile_0001",
    name: str = "my_tile",
    author: str = "author",
) -> "DatabaseTileInfo":
    from veriflow.workflows.database import DatabaseTileInfo
    return DatabaseTileInfo(
        tile_number=number,
        tile_id=tile_id,
        tile_name=name,
        tile_author=author,
        version="1",
        revision="0",
        interface_name="semicolab",
    )


def _make_run_info(
    tile_id: str = "tile_0001",
    run_id: str = "run-001",
    status: str = "PASS",
    run_dir: Path | None = None,
) -> "DatabaseRunInfo":
    from veriflow.workflows.database import DatabaseRunInfo
    return DatabaseRunInfo(
        tile_id=tile_id,
        run_id=run_id,
        run_dir=run_dir or Path("/fake/run"),
        status=status,
        date="2026-01-01",
        objective="test objective",
    )


def _make_run_result(
    tile_id: str = "tile_0001",
    run_id: str = "run-001",
    status: str = "PASS",
) -> "DatabaseRunResult":
    from veriflow.workflows.database import DatabaseRunResult
    from veriflow.models.stage_result import StageResult
    return DatabaseRunResult(
        tile_id=tile_id,
        run_id=run_id,
        run_dir=Path("/fake/run"),
        status=status,
        interface_name="semicolab",
        stages={
            "connectivity": StageResult(name="connectivity", status="PASS"),
            "simulation": StageResult(name="simulation", status="COMPLETED"),
            "synthesis": StageResult(name="synthesis", status="PASS"),
        },
        sources={},
        artifacts={},
        data={
            "tile_id": tile_id,
            "run_id": run_id,
            "status": status,
            "interface_name": "semicolab",
            "stages": {
                "connectivity": {"status": "PASS"},
                "simulation": {"status": "COMPLETED"},
                "synthesis": {"status": "PASS"},
            },
        },
    )


# ── E1. Parser ────────────────────────────────────────────────────────────────

def test_db_list_tiles_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["db", "list-tiles", "--db", str(tmp_path)])
    assert args.command == "db"
    assert args.db_command == "list-tiles"
    assert args.db == str(tmp_path)


def test_db_list_runs_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(
        ["db", "list-runs", "--db", str(tmp_path), "--tile", "0001"]
    )
    assert args.command == "db"
    assert args.db_command == "list-runs"
    assert args.db == str(tmp_path)
    assert args.tile == "0001"


def test_db_show_run_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(
        ["db", "show-run", "--db", str(tmp_path), "--tile", "0001", "--run", "run-001"]
    )
    assert args.command == "db"
    assert args.db_command == "show-run"
    assert args.db == str(tmp_path)
    assert args.tile == "0001"
    assert args.run == "run-001"


# ── E2. Dispatch ──────────────────────────────────────────────────────────────

def test_db_list_tiles_dispatches(tmp_path):
    from veriflow.cli import main
    tile = _make_tile_info()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_tiles.return_value = [tile]
        mock_cls.return_value = mock_wf
        rc = main(["db", "list-tiles", "--db", str(tmp_path)])
    mock_cls.assert_called_once_with(Path(str(tmp_path)))
    mock_wf.list_tiles.assert_called_once()
    assert rc == 0


def test_db_list_runs_dispatches(tmp_path):
    from veriflow.cli import main
    run = _make_run_info()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_runs.return_value = [run]
        mock_cls.return_value = mock_wf
        rc = main(["db", "list-runs", "--db", str(tmp_path), "--tile", "0001"])
    mock_wf.list_runs.assert_called_once_with(tile_id=None, tile_number="0001")
    assert rc == 0


def test_db_show_run_dispatches(tmp_path):
    from veriflow.cli import main
    result = _make_run_result()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.load_run_result.return_value = result
        mock_cls.return_value = mock_wf
        rc = main(["db", "show-run", "--db", str(tmp_path), "--tile", "0001", "--run", "run-001"])
    mock_wf.load_run_result.assert_called_once_with(tile_id=None, tile_number="0001", run_id="run-001")
    assert rc == 0


# ── E3. Human output ──────────────────────────────────────────────────────────

def test_db_list_tiles_output_includes_tile_info(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_list_tiles
    tile = _make_tile_info(number="0001", tile_id="tile_0001")
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_tiles.return_value = [tile]
        mock_cls.return_value = mock_wf
        cmd_db_list_tiles(tmp_path)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "0001" in combined
    assert "tile_0001" in combined


def test_db_list_runs_output_includes_run_id_and_status(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_list_runs
    run = _make_run_info(run_id="run-001", status="PASS")
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_runs.return_value = [run]
        mock_cls.return_value = mock_wf
        cmd_db_list_runs(tmp_path, tile="0001")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "run-001" in combined
    assert "PASS" in combined


def test_db_show_run_output_includes_run_id_status_and_stages(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_show_run
    result = _make_run_result(run_id="run-001", status="PASS")
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.load_run_result.return_value = result
        mock_cls.return_value = mock_wf
        cmd_db_show_run(tmp_path, run_id="run-001", tile="0001")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "run-001" in combined
    assert "PASS" in combined
    assert "connectivity" in combined
    assert "synthesis" in combined


def test_db_list_tiles_empty_prints_message(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_list_tiles
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_tiles.return_value = []
        mock_cls.return_value = mock_wf
        result = cmd_db_list_tiles(tmp_path)
    assert result == []
    combined = capsys.readouterr().out + capsys.readouterr().err
    # no crash; zero tiles is not an error


def test_db_list_runs_empty_prints_message(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_list_runs
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_runs.return_value = []
        mock_cls.return_value = mock_wf
        result = cmd_db_list_runs(tmp_path, tile="0001")
    assert result == []


# ── E4. JSON output ───────────────────────────────────────────────────────────

def test_db_list_tiles_json_has_tiles_key(tmp_path, capsys):
    from veriflow.cli import main
    tile = _make_tile_info()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_tiles.return_value = [tile]
        mock_cls.return_value = mock_wf
        rc = main(["--json", "db", "list-tiles", "--db", str(tmp_path)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "tiles" in data
    assert isinstance(data["tiles"], list)
    assert data["tiles"][0]["tile_number"] == "0001"
    assert data["tiles"][0]["tile_id"] == "tile_0001"
    assert rc == 0


def test_db_list_runs_json_has_runs_key(tmp_path, capsys):
    from veriflow.cli import main
    run = _make_run_info()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_runs.return_value = [run]
        mock_cls.return_value = mock_wf
        rc = main(["--json", "db", "list-runs", "--db", str(tmp_path), "--tile", "0001"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "runs" in data
    assert isinstance(data["runs"], list)
    assert data["runs"][0]["run_id"] == "run-001"
    assert data["runs"][0]["status"] == "PASS"
    assert rc == 0


def test_db_show_run_json_has_run_key(tmp_path, capsys):
    from veriflow.cli import main
    result = _make_run_result()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.load_run_result.return_value = result
        mock_cls.return_value = mock_wf
        rc = main(["--json", "db", "show-run", "--db", str(tmp_path), "--tile", "0001", "--run", "run-001"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "run" in data
    assert data["run"]["tile_id"] == "tile_0001"
    assert data["run"]["run_id"] == "run-001"
    assert rc == 0


def test_db_list_tiles_json_empty_returns_empty_list(tmp_path, capsys):
    from veriflow.cli import main
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_tiles.return_value = []
        mock_cls.return_value = mock_wf
        rc = main(["--json", "db", "list-tiles", "--db", str(tmp_path)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["tiles"] == []
    assert rc == 0


# ── E5. Error behavior ────────────────────────────────────────────────────────

def test_db_list_runs_missing_tile_exits_via_argparse(tmp_path):
    """argparse exits 2 when required --tile is absent for list-runs."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "list-runs", "--db", str(tmp_path)])
    assert exc_info.value.code != 0


def test_db_show_run_missing_run_exits_via_argparse(tmp_path):
    """argparse exits 2 when required --run is absent for show-run."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "show-run", "--db", str(tmp_path), "--tile", "0001"])
    assert exc_info.value.code != 0


def test_db_show_run_missing_tile_exits_via_argparse(tmp_path):
    """argparse exits 2 when required --tile is absent for show-run."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "show-run", "--db", str(tmp_path), "--run", "run-001"])
    assert exc_info.value.code != 0


def test_db_list_tiles_missing_db_exits_via_argparse():
    """argparse exits when required --db is absent for list-tiles."""
    from veriflow.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["db", "list-tiles"])
    assert exc_info.value.code != 0


def test_db_list_tiles_veriflow_error_propagates_nonzero(tmp_path):
    from veriflow.cli import main
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
            mock_wf = MagicMock()
            mock_wf.list_tiles.side_effect = VeriFlowError("not found", code="VF_TEST", exit_code=1)
            mock_cls.return_value = mock_wf
            rc = main(["db", "list-tiles", "--db", str(tmp_path)])
    assert rc != 0
    assert "not found" in buf.getvalue()


def test_db_list_runs_veriflow_error_propagates_nonzero(tmp_path):
    from veriflow.cli import main
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
            mock_wf = MagicMock()
            mock_wf.list_runs.side_effect = VeriFlowError(
                "tile not found", code="VF_DATABASE_TILE_NOT_FOUND", exit_code=1
            )
            mock_cls.return_value = mock_wf
            rc = main(["db", "list-runs", "--db", str(tmp_path), "--tile", "9999"])
    assert rc != 0


def test_db_show_run_veriflow_error_propagates_nonzero(tmp_path):
    from veriflow.cli import main
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
            mock_wf = MagicMock()
            mock_wf.load_run_result.side_effect = VeriFlowError(
                "run not found", code="VF_DATABASE_RUN_NOT_FOUND", exit_code=1
            )
            mock_cls.return_value = mock_wf
            rc = main(["db", "show-run", "--db", str(tmp_path), "--tile", "0001", "--run", "run-999"])
    assert rc != 0


# ── E6. Read-only guarantee ───────────────────────────────────────────────────

def test_db_list_tiles_does_not_call_run_tile(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_tiles.return_value = []
        mock_wf.run_tile.side_effect = AssertionError("run_tile must not be called by list-tiles")
        mock_cls.return_value = mock_wf
        rc = main(["db", "list-tiles", "--db", str(tmp_path)])
    mock_wf.run_tile.assert_not_called()
    assert rc == 0


def test_db_list_runs_does_not_call_run_tile(tmp_path):
    from veriflow.cli import main
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_runs.return_value = []
        mock_wf.run_tile.side_effect = AssertionError("run_tile must not be called by list-runs")
        mock_cls.return_value = mock_wf
        rc = main(["db", "list-runs", "--db", str(tmp_path), "--tile", "0001"])
    mock_wf.run_tile.assert_not_called()
    assert rc == 0


def test_db_show_run_does_not_call_run_tile(tmp_path):
    from veriflow.cli import main
    result = _make_run_result()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.load_run_result.return_value = result
        mock_wf.run_tile.side_effect = AssertionError("run_tile must not be called by show-run")
        mock_cls.return_value = mock_wf
        rc = main(["db", "show-run", "--db", str(tmp_path), "--tile", "0001", "--run", "run-001"])
    mock_wf.run_tile.assert_not_called()
    assert rc == 0
