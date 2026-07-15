"""Regression tests: veriflow/ui/output.py helpers must never emit a
character that raises UnicodeEncodeError when encoded as cp1252 -- the
failure mode Rich's legacy-console renderer hits on Windows terminals
that report a cp1252 codepage (see dev-docs/SMOKE_TEST_FINDINGS.md,
"[2026-07-14] Fix: box-drawing / arrow / checkmark Unicode in ui/output.py").
"""

from __future__ import annotations

from pathlib import Path

from veriflow.ui import output as ui_output


def _assert_cp1252_safe(capsys) -> None:
    captured = capsys.readouterr()
    # Raises UnicodeEncodeError if any character in the captured output
    # falls outside cp1252's range -- that's the assertion.
    captured.out.encode("cp1252")
    captured.err.encode("cp1252")


def test_print_section_is_cp1252_safe(capsys):
    ui_output.print_section("Stages")
    _assert_cp1252_safe(capsys)


def test_print_warn_is_cp1252_safe(capsys):
    ui_output.print_warn("something looks off")
    _assert_cp1252_safe(capsys)


def test_print_fail_detail_is_cp1252_safe(capsys):
    ui_output.print_fail_detail("compile error", Path("out/synth/logs/synth.log"))
    _assert_cp1252_safe(capsys)


def test_print_fail_detail_without_log_path_is_cp1252_safe(capsys):
    ui_output.print_fail_detail("compile error")
    _assert_cp1252_safe(capsys)


def test_print_wave_url_is_cp1252_safe(capsys):
    ui_output.print_wave_url("http://localhost:8080/waves")
    _assert_cp1252_safe(capsys)


def test_print_done_is_cp1252_safe(capsys):
    ui_output.print_done("Database initialized successfully.")
    _assert_cp1252_safe(capsys)


def test_print_status_is_cp1252_safe(capsys):
    ui_output.print_status("synthesis", "PASS", "yosys")
    _assert_cp1252_safe(capsys)


def test_print_run_header_is_cp1252_safe(capsys):
    ui_output.print_run_header(Path("./database"), "MST130-01", "run-001")
    _assert_cp1252_safe(capsys)


def test_print_step_is_cp1252_safe(capsys):
    ui_output.print_step("init", "Database initialized")
    _assert_cp1252_safe(capsys)


def test_print_title_is_cp1252_safe(capsys):
    ui_output.print_title("Tiles")
    _assert_cp1252_safe(capsys)


def test_print_file_tree_is_cp1252_safe(capsys, tmp_path):
    f = tmp_path / "manifest.yaml"
    f.write_text("x", encoding="utf-8")
    ui_output.print_file_tree([f], tmp_path)
    _assert_cp1252_safe(capsys)


def test_print_tiles_table_is_cp1252_safe(capsys):
    """Exercises _FRAMED_HEAD_BOX -- the box-drawing Box() definition
    that used unicode "──" edges before the fix."""
    ui_output.print_tiles_table([("1", "MST130-01", "adder", "RL", "v01 r01", "semicolab")])
    _assert_cp1252_safe(capsys)


def test_print_runs_table_is_cp1252_safe(capsys):
    """Also exercises _FRAMED_HEAD_BOX."""
    ui_output.print_runs_table([("run-001", "[pass]PASS[/pass]", "2026-07-14", "-")])
    _assert_cp1252_safe(capsys)


def test_print_cli_error_is_cp1252_safe(capsys):
    ui_output.print_cli_error("Tool not found in PATH: yosys")
    _assert_cp1252_safe(capsys)


def test_frame_head_box_string_is_cp1252_safe():
    str(ui_output._FRAMED_HEAD_BOX).encode("cp1252")
