"""Regression tests for the Rich polish pass (2026-07-13):

  1. commands/init_db.py migrated print() -> print_step/print_done.
  2. commands/create_tile.py migrated print() -> print_step/print_done/print_warn.
  3. commands/doctor.py's [OK]/[FAIL] markers now use Rich color markup.
  4. list-tiles renders as a Rich Table (framed box; top rule matches header rule width).
  5. list-runs renders as a Rich Table (same), status colored.
  6. commands/run.py's live simulation status displays "PASS", not "COMPLETED".
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from veriflow.core import VeriFlowError


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_db(tmp: Path) -> Path:
    db = tmp / "database"
    from veriflow.commands.init_db import cmd_init
    cmd_init(db)
    return db


def _fill_project_config(db: Path, id_prefix: str = "TST-01") -> None:
    cfg = {
        "id_prefix": id_prefix,
        "project_name": "Test Project",
        "repo": "",
        "description": "Test project.",
        "interface_name": None,
    }
    (db / "project_config.yaml").write_text(
        yaml.dump(cfg, default_flow_style=False), encoding="utf-8"
    )


def _render_with_color(markup: str) -> str:
    """Render a markup string through a fresh forced-terminal Console using
    the real VERIFLOW_THEME, returning the raw (ANSI-laden) output."""
    from rich.console import Console
    from veriflow.ui.theme import VERIFLOW_THEME

    buf = io.StringIO()
    console = Console(theme=VERIFLOW_THEME, file=buf, force_terminal=True, color_system="truecolor")
    console.print(markup)
    return buf.getvalue()


def _rgb(hex_color: str) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"{r};{g};{b}"


# ── 1. init_db.py uses Rich ───────────────────────────────────────────────────


def test_init_db_output_uses_step_prefix_and_success_message(tmp_path, capsys):
    from veriflow.commands.init_db import cmd_init
    db = tmp_path / "database"
    cmd_init(db)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[init]" in combined
    assert "Database initialized successfully." in combined
    # Rich may word-wrap the long temp path across lines; compare with
    # newlines stripped out so wrapping doesn't break the substring check.
    assert str(db.resolve()) in combined.replace("\n", "")


def test_init_db_has_no_bare_print_calls():
    import inspect
    from veriflow.commands import init_db
    source = inspect.getsource(init_db.cmd_init)
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("print("), f"bare print() left in cmd_init: {stripped!r}"


# ── 2. create_tile.py uses Rich ────────────────────────────────────────────────


def test_create_tile_output_uses_step_prefix_and_success_message(tmp_path, capsys):
    from veriflow.commands.create_tile import cmd_create_tile
    db = _make_db(tmp_path)
    _fill_project_config(db)
    cmd_create_tile(db, top_module="my_tile")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[create-tile]" in combined
    assert "Tile created successfully." in combined


def test_create_tile_has_no_bare_print_calls():
    import inspect
    from veriflow.commands import create_tile
    source = inspect.getsource(create_tile.cmd_create_tile)
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("print("), f"bare print() left in cmd_create_tile: {stripped!r}"


def test_create_tile_short_hash_warning_still_uses_print_warn(tmp_path, capsys):
    """Regression guard: the {short_hash} warning must survive the Rich migration."""
    from veriflow.commands.create_tile import cmd_create_tile
    db = _make_db(tmp_path)
    _fill_project_config(db)
    (db / "project_config.yaml").write_text(
        (db / "project_config.yaml").read_text(encoding="utf-8")
        + '\nid_format: "{prefix}-{tile_number}-{short_hash}"\n',
        encoding="utf-8",
    )
    cmd_create_tile(db)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "VF_ID_PLACEHOLDER_UNAVAILABLE" in combined
    assert "000000" in combined


# ── 3. doctor.py uses Rich color markup ───────────────────────────────────────


def _ok_backend_cls(tool_name: str = "fake"):
    class _Backend:
        def check_availability(self):
            return [{"tool": tool_name, "available": True,
                     "version": "v1.0", "path": f"/bin/{tool_name}", "error": None}]
    return _Backend


def _fail_backend_cls(tool_name: str = "fake"):
    class _Backend:
        def check_availability(self):
            return [{"tool": tool_name, "available": False,
                     "version": None, "path": None,
                     "error": f"{tool_name!r} not found in PATH"}]
    return _Backend


def test_doctor_ok_marker_renders_pastel_green_when_terminal_forced():
    from veriflow.ui.theme import GREEN
    rendered = _render_with_color("[pass]\\[OK][/pass]  ")
    assert "\x1b[" in rendered
    assert _rgb(GREEN) in rendered
    assert "[OK]" in _strip_ansi(rendered)


def test_doctor_fail_marker_renders_pastel_red_when_terminal_forced():
    from veriflow.ui.theme import RED
    rendered = _render_with_color("[fail]\\[FAIL][/fail]")
    assert "\x1b[" in rendered
    assert _rgb(RED) in rendered
    assert "[FAIL]" in _strip_ansi(rendered)


def _strip_ansi(text: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_doctor_no_bare_print_calls():
    import inspect
    from veriflow.commands import doctor
    source = inspect.getsource(doctor._print_report)
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("print("), f"bare print() left in _print_report: {stripped!r}"


def test_doctor_text_still_shows_ok_and_categories(capsys):
    from veriflow.cli import main
    with patch("veriflow.commands.doctor._CONNECTIVITY", {"fake": _ok_backend_cls()}), \
         patch("veriflow.commands.doctor._SIMULATION",   {"fake": _ok_backend_cls()}), \
         patch("veriflow.commands.doctor._SYNTHESIS",    {"fake": _ok_backend_cls()}):
        main(["doctor"])
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "[CONNECTIVITY]" in out


# ── 4. list-tiles renders as a Rich Table ─────────────────────────────────────


def _make_tile_info(**overrides):
    from veriflow.workflows.database import DatabaseTileInfo
    base = dict(
        tile_number="0001", tile_id="tile_0001", tile_name="my_tile",
        tile_author="Roman", version="1", revision="0", interface_name="semicolab",
    )
    base.update(overrides)
    return DatabaseTileInfo(**base)


def test_list_tiles_uses_rich_table_with_headers(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_list_tiles
    tile = _make_tile_info()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_tiles.return_value = [tile]
        mock_cls.return_value = mock_wf
        cmd_db_list_tiles(tmp_path)
    out = capsys.readouterr().out
    for header in ("#", "Tile ID", "Name", "Author", "Ver", "Interface"):
        assert header in out
    assert "0001" in out
    assert "tile_0001" in out
    assert "my_tile" in out
    assert "Roman" in out
    assert "semicolab" in out


def _lines_via_swapped_console(render_fn) -> list[str]:
    """Call render_fn() with veriflow.ui.output.console swapped for a fresh,
    fixed-width, non-tty Console, returning the captured output split into
    lines. Used to measure exact rendered rule widths."""
    import io
    from rich.console import Console
    from veriflow.ui import output as ui_output
    from veriflow.ui.theme import VERIFLOW_THEME

    buf = io.StringIO()
    original = ui_output.console
    ui_output.console = Console(theme=VERIFLOW_THEME, file=buf, force_terminal=False, width=80)
    try:
        render_fn()
    finally:
        ui_output.console = original
    return buf.getvalue().split("\n")


def test_print_tiles_table_top_rule_matches_header_rule_width():
    """Regression guard for the top-rule/header-rule width mismatch bug:
    both horizontal rules must be produced by the same Table (same width)."""
    from veriflow.ui import output as ui_output

    lines = _lines_via_swapped_console(
        lambda: ui_output.print_tiles_table(
            [("0001", "TST-26071300010101", "n", "a", "v1 r1", "iface")]
        )
    )
    rule_lines = [l for l in lines if l and set(l) <= {" ", "-"} and "-" in l]
    assert len(rule_lines) >= 2, f"expected at least 2 rule lines, got: {lines!r}"
    assert len(rule_lines[0]) == len(rule_lines[1])


# ── 5. list-runs renders as a Rich Table, status colored ──────────────────────


def _make_run_info(**overrides):
    from veriflow.workflows.database import DatabaseRunInfo
    base = dict(
        tile_id="tile_0001", run_id="run-001", run_dir=Path("/fake/run"),
        status="PASS", date="2026-07-13", objective="test",
    )
    base.update(overrides)
    return DatabaseRunInfo(**base)


def test_list_runs_uses_rich_table_with_headers(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_list_runs
    run = _make_run_info()
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_runs.return_value = [run]
        mock_cls.return_value = mock_wf
        cmd_db_list_runs(tmp_path, tile="0001")
    out = capsys.readouterr().out
    for header in ("Run", "Status", "Date", "Wave"):
        assert header in out
    assert "run-001" in out
    assert "PASS" in out
    assert "2026-07-13" in out


def test_list_runs_fail_status_present(tmp_path, capsys):
    from veriflow.commands.db_read import cmd_db_list_runs
    run = _make_run_info(status="FAIL")
    with patch("veriflow.commands.db_read.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.list_runs.return_value = [run]
        mock_cls.return_value = mock_wf
        cmd_db_list_runs(tmp_path, tile="0001")
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_print_runs_table_top_rule_matches_header_rule_width():
    """Regression guard for the top-rule/header-rule width mismatch bug."""
    from veriflow.ui import output as ui_output

    lines = _lines_via_swapped_console(
        lambda: ui_output.print_runs_table(
            [("run-001", "[pass]PASS[/pass]", "2026-07-13", "[secondary]no[/secondary]")]
        )
    )
    rule_lines = [l for l in lines if l and set(l) <= {" ", "-"} and "-" in l]
    assert len(rule_lines) >= 2, f"expected at least 2 rule lines, got: {lines!r}"
    assert len(rule_lines[0]) == len(rule_lines[1])


def test_status_markup_color_mapping_still_correct():
    """Guards the color contract list-runs relies on: green PASS, red FAIL, grey SKIPPED."""
    from veriflow.commands.db_read import _status_markup
    assert _status_markup("PASS") == "[pass]PASS[/pass]"
    assert _status_markup("FAIL") == "[fail]FAIL[/fail]"
    assert _status_markup("SKIPPED") == "[secondary]SKIPPED[/secondary]"


# ── 6. run.py: live simulation status shows PASS, not COMPLETED ──────────────


def test_run_py_source_normalizes_completed_to_pass():
    import inspect
    from veriflow.commands import run as run_module
    source = inspect.getsource(run_module.cmd_run)
    assert '"PASS" if sim_result == "COMPLETED"' in source


def test_cmd_run_live_output_shows_pass_not_completed(tmp_path, capsys):
    from veriflow.commands.run import cmd_run

    execution = MagicMock()
    execution.data = {
        "status": "PASS",
        "warnings": [],
        "stages": {
            "connectivity": {"status": "PASS"},
            "simulation": {"status": "COMPLETED"},
            "synthesis": {"status": "PASS", "metrics": {"cells": "10"}},
        },
    }
    execution.tile_id = "tile_0001"
    execution.run_id = "run-001"
    execution.run_dir = tmp_path
    execution.to_dict.return_value = execution.data

    with patch("veriflow.commands.run.DatabaseWorkflow") as mock_cls:
        mock_wf = MagicMock()
        mock_wf.run_tile.return_value = execution
        mock_cls.return_value = mock_wf
        cmd_run(tmp_path, "0001")

    out = capsys.readouterr().out
    assert "COMPLETED" not in out
    assert "PASS" in out
