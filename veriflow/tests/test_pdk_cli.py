"""Tests for `veriflow pdk` (commands/pdk.py + cli.py dispatch).

`VERIFLOW_PDK_ROOT` is imported by name into both `commands.pdk` (used
directly for `pdk install`/`pdk update`) and referenced internally by
`models.pdk_manager`'s own functions (`get_pdk_path`/`get_liberty_path`) --
patching one does not patch the other, so `_patch_pdk_root` below patches
both consistently.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.cli import main
from veriflow.core import VeriFlowError


@contextlib.contextmanager
def patched_pdk_root(tmp_path: Path):
    with patch("veriflow.commands.pdk.VERIFLOW_PDK_ROOT", tmp_path), \
         patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
        yield


# ── pdk list ──────────────────────────────────────────────────────────────────

def test_pdk_list_shows_all_registered_technologies(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    for name in ("generic", "sky130", "gf180", "ihp130"):
        assert name in out


def test_pdk_list_marks_generic_ok_no_pdk_required(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        main(["pdk", "list"])
    out = capsys.readouterr().out
    assert "no PDK required" in out


def test_pdk_list_marks_uninstalled_pdk_not_installed(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "sky130")
    assert row["status"] == "NOT INSTALLED"
    assert row["install_hint"] == "veriflow pdk install sky130"


def test_pdk_list_marks_installed_pdk_with_liberty_ok(tmp_path):
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    lib_file = lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib"
    lib_file.write_text("", encoding="utf-8")
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "sky130")
    assert row["status"] == "OK"
    assert row["liberty"] == str(lib_file)


def test_pdk_list_marks_installed_without_liberty(tmp_path):
    (tmp_path / "sky130").mkdir()
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "sky130")
    assert row["status"] == "INSTALLED, NO LIBERTY"


def _run_pdk_list():
    from veriflow.commands.pdk import cmd_pdk_list
    import argparse
    return cmd_pdk_list(argparse.Namespace())


def test_pdk_list_json_mode(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        rc = main(["--json", "pdk", "list"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["command"] == "pdk list"
    assert {row["name"] for row in data["pdks"]} == {"generic", "sky130", "gf180", "ihp130"}


# ── pdk status ────────────────────────────────────────────────────────────────

def test_pdk_status_reports_pdk_root(tmp_path):
    with patched_pdk_root(tmp_path):
        from veriflow.commands.pdk import cmd_pdk_status
        import argparse
        rc, result = cmd_pdk_status(argparse.Namespace())
    assert rc == 0
    assert result["pdk_root"] == str(tmp_path)


# ── pdk install ───────────────────────────────────────────────────────────────

def test_pdk_install_unknown_technology_fails(tmp_path):
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "install", "notapdkname"])
    assert rc == 1


def test_pdk_install_generic_has_no_installable_pdk(tmp_path):
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "install", "generic"])
    assert rc == 1


def test_pdk_install_unknown_technology_raises_with_correct_code(tmp_path):
    with patched_pdk_root(tmp_path):
        from veriflow.commands.pdk import cmd_pdk_install
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="notapdkname"))
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_pdk_install_generic_raises_with_correct_code(tmp_path):
    with patched_pdk_root(tmp_path):
        from veriflow.commands.pdk import cmd_pdk_install
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="generic"))
    assert exc_info.value.code == "VF_PDK_NOT_INSTALLABLE"


def test_pdk_install_already_installed_is_a_noop(tmp_path, capsys):
    (tmp_path / "sky130").mkdir()
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already installed" in out


def test_pdk_install_volare_missing_prints_clear_message_and_exits_1(tmp_path, capsys):
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=False):
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "volare" in out
    assert "pdks" in out


def test_pdk_install_volare_available_calls_expected_subprocess(tmp_path):
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run:
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert args[0] == "volare"
    assert args[1] == "enable"
    assert "--pdk" in args and "sky130" in args
    assert "--pdk-root" in args
    assert str(tmp_path / "sky130") in args


def test_pdk_install_git_missing_prints_clear_message_and_exits_1(tmp_path, capsys):
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._git_available", return_value=False):
        rc = main(["pdk", "install", "ihp130"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "git" in out


def test_pdk_install_git_available_calls_expected_subprocess(tmp_path):
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._git_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run:
        rc = main(["pdk", "install", "ihp130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert args[0] == "git"
    assert args[1] == "clone"
    assert str(tmp_path / "ihp130") in args


def test_pdk_install_subprocess_failure_raises(tmp_path):
    fake_result = MagicMock(returncode=1, stdout="", stderr="boom")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_install
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="sky130"))
    assert exc_info.value.code == "VF_PDK_INSTALL_FAILED"


# ── pdk update ────────────────────────────────────────────────────────────────

def test_pdk_update_not_installed_prints_message_and_exits_1(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "update", "sky130"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not installed" in out
    assert "sky130" in out


def test_pdk_update_installed_calls_expected_subprocess(tmp_path):
    (tmp_path / "sky130").mkdir()
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run:
        rc = main(["pdk", "update", "sky130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert args[0] == "volare"
    assert args[1] == "enable"


# ── Parser ────────────────────────────────────────────────────────────────────

def test_pdk_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["pdk", "install", "sky130"])
    assert args.command == "pdk"
    assert args.pdk_command == "install"
    assert args.pdk_name == "sky130"


def test_pdk_no_subcommand_returns_1():
    rc = main(["pdk"])
    assert rc == 1
