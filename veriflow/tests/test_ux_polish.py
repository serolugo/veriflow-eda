"""Regression tests for the Database Mode UX polish pass (2026-07-12):

  1. show-run accepts a bare run number ("8") in addition to "run-008".
  2. The simulation stage displays "PASS" instead of "COMPLETED".
  3. [ERROR] messages render in pastel red via Rich.
  4. bump-version / bump-revision use the shared Rich console, not print().
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── 1. show-run: bare run number normalization ────────────────────────────────


def test_normalize_run_id_bare_number():
    from veriflow.workflows.database import _normalize_run_id
    assert _normalize_run_id("8") == "run-008"
    assert _normalize_run_id("1") == "run-001"
    assert _normalize_run_id("123") == "run-123"


def test_normalize_run_id_already_formatted_passthrough():
    from veriflow.workflows.database import _normalize_run_id
    assert _normalize_run_id("run-008") == "run-008"


def test_normalize_run_id_non_numeric_passthrough():
    from veriflow.workflows.database import _normalize_run_id
    assert _normalize_run_id("bogus") == "bogus"


def test_load_run_result_bare_number_matches_formatted_run_id(tmp_path):
    """--run 8 and --run run-008 must resolve to the identical run."""
    from veriflow.workflows.database import DatabaseWorkflow

    run_dir = tmp_path / "tiles" / "tile_0001" / "runs" / "run-008"
    run_dir.mkdir(parents=True)
    (run_dir / "results.json").write_text(
        json.dumps({
            "tile_id": "tile_0001",
            "run_id": "run-008",
            "status": "PASS",
            "interface_name": None,
            "stages": {},
            "sources": {},
            "artifacts": {},
        }),
        encoding="utf-8",
    )

    wf = DatabaseWorkflow(tmp_path)
    by_number = wf.load_run_result(tile_id="tile_0001", run_id="8")
    by_full = wf.load_run_result(tile_id="tile_0001", run_id="run-008")

    assert by_number.run_id == by_full.run_id == "run-008"
    assert by_number.run_dir == by_full.run_dir == run_dir


def test_cli_show_run_bare_number_forwarded_and_normalized(tmp_path):
    """End-to-end: `db show-run --run 8` must not raise and must resolve run-008."""
    from veriflow.cli import main

    run_dir = tmp_path / "tiles" / "tile_0001" / "runs" / "run-008"
    run_dir.mkdir(parents=True)
    (run_dir / "results.json").write_text(
        json.dumps({
            "tile_id": "tile_0001",
            "run_id": "run-008",
            "status": "PASS",
            "interface_name": None,
            "stages": {},
            "sources": {},
            "artifacts": {},
        }),
        encoding="utf-8",
    )
    # tile_index.csv so --tile 1 resolves to tile_0001
    tile_index = tmp_path / "tile_index.csv"
    tile_index.write_text(
        "tile_number,tile_id,tile_name,tile_author,version,revision,interface_name\n"
        "0001,tile_0001,,,,,\n",
        encoding="utf-8",
    )

    rc = main(["db", "show-run", "--db", str(tmp_path), "--tile", "1", "--run", "8"])
    assert rc == 0


# ── 2. simulation stage label: COMPLETED -> PASS ──────────────────────────────


def test_status_markup_completed_displays_as_pass():
    from veriflow.commands.db_read import _status_markup
    assert _status_markup("COMPLETED") == "[pass]PASS[/pass]"


def test_show_run_output_shows_pass_not_completed_for_simulation(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_show_run
    from veriflow.workflows.database import DatabaseRunResult
    from veriflow.models.stage_result import StageResult

    result = DatabaseRunResult(
        tile_id="tile_0001",
        run_id="run-001",
        run_dir=Path("/fake/run"),
        status="PASS",
        interface_name="semicolab",
        stages={
            "connectivity": StageResult(name="connectivity", status="PASS"),
            "simulation": StageResult(name="simulation", status="COMPLETED"),
            "synthesis": StageResult(name="synthesis", status="PASS"),
        },
        sources={},
        artifacts={},
        data={},
    )
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.load_run_result.return_value = result
        mock_cls.return_value = mock_wf
        cmd_db_show_run(tmp_path, run_id="run-001", tile="0001")

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "COMPLETED" not in combined
    assert "PASS" in combined


# ── 3. [ERROR] pastel-red coloring ────────────────────────────────────────────


def test_print_cli_error_contains_error_prefix(capsys):
    from veriflow.ui.output import print_cli_error
    print_cli_error("boom")
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "boom" in captured.err


def test_error_console_style_is_pastel_red():
    from veriflow.ui.output import error_console
    from veriflow.ui.theme import RED

    style = error_console.get_style("error")
    triplet = style.color.get_truecolor()
    r, g, b = int(RED[1:3], 16), int(RED[3:5], 16), int(RED[5:7], 16)
    assert (triplet.red, triplet.green, triplet.blue) == (r, g, b)


def test_error_markup_renders_ansi_pastel_red_when_terminal_forced():
    """Confirms Rich actually processes the [error] markup into ANSI color
    codes carrying the pastel-red RGB triplet (not just that the tag exists)."""
    import io
    from rich.console import Console
    from veriflow.ui.theme import VERIFLOW_THEME, RED

    buf = io.StringIO()
    console = Console(theme=VERIFLOW_THEME, file=buf, force_terminal=True, color_system="truecolor")
    console.print("[error]\\[ERROR][/error] boom")
    output = buf.getvalue()

    r, g, b = int(RED[1:3], 16), int(RED[3:5], 16), int(RED[5:7], 16)
    assert "\x1b[" in output
    assert f"{r};{g};{b}" in output
    assert "[ERROR] boom" in _strip_ansi(output)


def _strip_ansi(text: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cli_veriflow_error_prints_error_prefix_via_capsys(tmp_path, capsys):
    """End-to-end: a real VeriFlowError from a db command still produces the
    "[ERROR] ..." line through the new Rich-based printer."""
    from veriflow.cli import main
    rc = main(["db", "run", "--db", str(tmp_path), "--tile", "0001"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "Traceback" not in captured.err


# ── 4. bump-version / bump-revision use Rich, not plain print() ──────────────


def _make_db_with_tile(tmp_path: Path) -> Path:
    from veriflow.commands.init_db import cmd_init
    from veriflow.commands.create_tile import cmd_create_tile
    db = tmp_path / "database"
    cmd_init(db)
    (db / "project_config.yaml").write_text(
        'id_prefix: "TST-01"\nproject_name: "Test"\nrepo: ""\ninterface_name: null\ndescription: |\n\n',
        encoding="utf-8",
    )
    cmd_create_tile(db, top_module="my_tile")
    return db


def test_bump_version_output_uses_step_prefix_and_success_message(tmp_path, capsys):
    from veriflow.commands.bump_version import cmd_bump_version
    db = _make_db_with_tile(tmp_path)
    cmd_bump_version(db, "0001")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[bump-version]" in combined
    assert "Version bumped successfully." in combined


def test_bump_revision_output_uses_step_prefix_and_success_message(tmp_path, capsys):
    from veriflow.commands.bump_revision import cmd_bump_revision
    db = _make_db_with_tile(tmp_path)
    cmd_bump_revision(db, "0001")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[bump-revision]" in combined
    assert "Revision bumped successfully." in combined
