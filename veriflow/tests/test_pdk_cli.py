"""Tests for `veriflow pdk` (commands/pdk.py + cli.py dispatch).

`VERIFLOW_PDK_ROOT` is imported by name into both `commands.pdk` (used
directly for `pdk install`/`pdk update`) and referenced internally by
`models.pdk_manager`'s own functions (`get_pdk_path`/`get_liberty_path`) --
patching one does not patch the other, so `_patch_pdk_root` below patches
both consistently.
"""

from __future__ import annotations

import argparse
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


def test_pdk_list_marks_generic_ok_no_pdk_required(tmp_path):
    """Checked via the returned dict, not the printed table -- the extra
    Version column narrows other columns enough that Rich wraps "no PDK
    required" across two table cell lines on a standard-width console."""
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "generic")
    assert row["status"] == "OK"
    assert row["note"] == "no PDK required"


def test_pdk_list_marks_uninstalled_pdk_not_installed(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "sky130")
    assert row["status"] == "NOT INSTALLED"
    assert row["action"] == "pdk install sky130"


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


# ── pdk list: "Action" column (install vs. update hint per status) ────────────

def test_pdk_list_action_shows_install_for_not_installed(tmp_path):
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "sky130")
    assert row["status"] == "NOT INSTALLED"
    assert row["action"] == "pdk install sky130"


def test_pdk_list_action_shows_install_for_installed_no_liberty(tmp_path):
    (tmp_path / "sky130").mkdir()
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "sky130")
    assert row["status"] == "INSTALLED, NO LIBERTY"
    assert row["action"] == "pdk install sky130"


def test_pdk_list_action_shows_update_for_ok(tmp_path):
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib").write_text("", encoding="utf-8")
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "sky130")
    assert row["status"] == "OK"
    assert row["action"] == "pdk update sky130"


def test_pdk_list_action_none_for_generic_no_pdk_required(tmp_path):
    """generic has no installable PDK at all -- no install/update action
    makes sense, unlike a genuinely-installed [OK] PDK."""
    with patched_pdk_root(tmp_path):
        rc, result = _run_pdk_list()
    assert rc == 0
    row = next(r for r in result["pdks"] if r["name"] == "generic")
    assert row["action"] is None


def test_pdk_list_table_header_is_action_not_install_hint(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        rc, _ = _run_pdk_list()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Action" in out
    assert "Install hint" not in out


# ── pdk list: home directory abbreviated with ~ ────────────────────────────────

def test_abbreviate_home_replaces_home_prefix():
    from veriflow.commands.pdk import _abbreviate_home
    full = str(Path.home() / ".veriflow" / "pdks" / "sky130" / "sky130A" / "lib.lib")
    result = _abbreviate_home(full)
    assert result.startswith("~")
    assert str(Path.home()) not in result


def test_abbreviate_home_exact_home_dir_becomes_tilde():
    from veriflow.commands.pdk import _abbreviate_home
    assert _abbreviate_home(str(Path.home())) == "~"


def test_abbreviate_home_leaves_unrelated_path_unchanged():
    from veriflow.commands.pdk import _abbreviate_home
    unrelated = str(Path("some") / "other" / "path" / "file.lib")
    assert _abbreviate_home(unrelated) == unrelated


def test_pdk_list_table_shows_tilde_for_home_rooted_liberty_path(tmp_path, capsys):
    """Integration check that _print_table actually applies the ~
    abbreviation -- the returned dict itself keeps the full path (see
    test_pdk_list_marks_installed_pdk_with_liberty_ok), only the rendered
    table is abbreviated."""
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib").write_text("", encoding="utf-8")
    with patched_pdk_root(tmp_path), patch("veriflow.commands.pdk.Path.home", return_value=tmp_path):
        rc, _ = _run_pdk_list()
    out = capsys.readouterr().out
    assert rc == 0
    assert "~" in out


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
    """A complete install (liberty resolves) is reported as already
    installed and no subprocess is run."""
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib").write_text("", encoding="utf-8")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk.subprocess.run") as mock_run:
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already installed" in out
    mock_run.assert_not_called()


def test_pdk_install_incomplete_installation_reinstalls(tmp_path, capsys):
    """A directory that exists but has no resolvable liberty file
    ([INSTALLED, NO LIBERTY]) is not "already installed" -- it's reinstalled."""
    (tmp_path / "sky130").mkdir()  # dir exists, no liberty file inside
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already installed" not in out
    assert "Incomplete installation detected, reinstalling sky130" in out
    mock_run.assert_called_once()


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
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert args[0] == "volare"
    assert args[1] == "enable"
    assert "--pdk" in args and "sky130" in args
    assert "--pdk-root" in args
    assert str(tmp_path / "sky130") in args


def test_pdk_install_passes_default_version_positionally(tmp_path):
    """sky130.yaml/gf180.yaml pin a default_version -- it must be passed as
    a positional arg right after `--pdk <volare_pdk>`."""
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    version = "0fe599b2afb6708d281543108caf8310912f54af"
    assert version in args
    assert args[args.index("--pdk") + 2] == version
    assert args.index(version) < args.index("--pdk-root")


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


def test_pdk_install_returncode_0_with_stderr_is_success_not_error(tmp_path, capsys):
    """Windows: volare emits a PermissionError from its own temp-file
    cleanup on stderr even when the install succeeded (returncode 0) --
    must not be treated as a failure."""
    fake_result = MagicMock(
        returncode=0, stdout="",
        stderr="PermissionError: [WinError 5] Access is denied: 'C:\\\\temp\\\\volare_tmp'",
    )
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "installed" in out


def test_pdk_install_returncode_0_with_stderr_shown_as_warning_not_error(tmp_path, capsys):
    fake_result = MagicMock(returncode=0, stdout="", stderr="some noisy cleanup warning")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Error" not in out
    assert "some noisy cleanup warning" in out


def test_pdk_install_returncode_0_with_empty_stderr_prints_no_warning(tmp_path, capsys):
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"), \
         patch("veriflow.commands.pdk.print_warn") as mock_warn:
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    mock_warn.assert_not_called()


def test_pdk_install_returncode_nonzero_with_stderr_still_raises(tmp_path):
    """returncode is the sole success/failure signal -- non-empty stderr on
    a failing run is still a failure, not "success with a warning"."""
    fake_result = MagicMock(returncode=1, stdout="", stderr="fatal: real failure")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_install
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="sky130"))
    assert exc_info.value.code == "VF_PDK_INSTALL_FAILED"


# ── Windows symlink/junction fallback (_ensure_pdk_subdir_link) ──────────────
#
# Real-world trigger: volare enable exits 0, but on a Windows box without
# Developer Mode / SeCreateSymbolicLinkPrivilege, the pdk_root/<pdk_subdir>
# symlink volare tries to create into pdk_root/versions/<version>/ never
# appears. VeriFlow must notice this and fall back to a junction point
# rather than reporting a broken [INSTALLED, NO LIBERTY] install as success.

_SKY130_VERSION = "0fe599b2afb6708d281543108caf8310912f54af"


def test_pdk_install_creates_junction_fallback_when_symlink_missing(tmp_path):
    """expected_link (pdk_root/sky130A) never appeared, but volare did
    extract the files under pdk_root/versions/<version>/sky130A --
    _create_pdk_link is called to bridge the gap."""
    src_dir = tmp_path / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src_dir.mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    mock_link.assert_called_once_with(src_dir, tmp_path / "sky130" / "sky130A")


def test_pdk_install_junction_fallback_prints_windows_fallback_message(tmp_path, capsys):
    src_dir = tmp_path / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src_dir.mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link"):
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Creating directory link sky130A (Windows fallback)" in out


def test_pdk_install_no_fallback_needed_when_symlink_present(tmp_path):
    """The normal case (symlink worked, or a prior fixup already ran) --
    _create_pdk_link must not be called."""
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    mock_link.assert_not_called()


def test_pdk_install_incomplete_extraction_raises_when_src_also_missing(tmp_path):
    """Neither pdk_root/sky130A nor pdk_root/versions/<version>/sky130A
    exist -- volare didn't extract anything usable; a clear error, not a
    silently "successful" broken install."""
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_install
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="sky130"))
    assert exc_info.value.code == "VF_PDK_INSTALL_INCOMPLETE"
    assert "sky130" in str(exc_info.value)


def test_pdk_update_creates_junction_fallback_when_symlink_missing(tmp_path):
    (tmp_path / "sky130").mkdir()  # get_pdk_path must resolve for update to proceed
    src_dir = tmp_path / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src_dir.mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        rc = main(["pdk", "update", "sky130"])
    assert rc == 0
    mock_link.assert_called_once_with(src_dir, tmp_path / "sky130" / "sky130A")


# ── _ensure_pdk_subdir_link (unit) ────────────────────────────────────────────

def _fake_sky130_technology(**overrides):
    from veriflow.models.technology_profile import TechnologyProfile
    base = dict(
        name="sky130",
        install_method="volare",
        volare_pdk="sky130",
        pdk_subdir="sky130A",
        default_version=_SKY130_VERSION,
    )
    base.update(overrides)
    return TechnologyProfile(**base)


def test_ensure_pdk_subdir_link_noop_when_no_pdk_subdir(tmp_path):
    from veriflow.commands.pdk import _ensure_pdk_subdir_link
    technology = _fake_sky130_technology(pdk_subdir=None)
    with patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        _ensure_pdk_subdir_link(technology, tmp_path)
    mock_link.assert_not_called()


def test_ensure_pdk_subdir_link_noop_when_link_already_exists(tmp_path):
    from veriflow.commands.pdk import _ensure_pdk_subdir_link
    (tmp_path / "sky130A").mkdir()
    technology = _fake_sky130_technology()
    with patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        _ensure_pdk_subdir_link(technology, tmp_path)
    mock_link.assert_not_called()


def test_ensure_pdk_subdir_link_discovers_version_dir_when_unpinned(tmp_path):
    """No default_version -- falls back to discovering the single extracted
    <pdk_subdir> under pdk_root/versions/*/."""
    from veriflow.commands.pdk import _ensure_pdk_subdir_link
    src_dir = tmp_path / "volare" / "sky130" / "versions" / "some-other-hash" / "sky130A"
    src_dir.mkdir(parents=True)
    technology = _fake_sky130_technology(default_version=None)
    with patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        _ensure_pdk_subdir_link(technology, tmp_path)
    mock_link.assert_called_once_with(src_dir, tmp_path / "sky130A")


# ── volare symlink-privilege failure recovery (_recover_from_volare_symlink_failure) ──
#
# Discovered by actually running `veriflow pdk install sky130` on a real
# Windows machine without Developer Mode: volare's CLI wrapper
# (`volare.__main__.enable_cmd`) catches the symlink OSError and calls
# `exit(-1)` -- so the failure is a hard non-zero returncode, NOT a silent
# "exits 0, directory missing" case. It also prints via a plain
# `rich.console.Console()`, which writes to *stdout* by default, not
# stderr. Both details matter for correctly recognizing and recovering
# from this specific failure.

def test_recover_from_volare_symlink_failure_ignores_unrelated_failure(tmp_path):
    from veriflow.commands.pdk import _recover_from_volare_symlink_failure
    technology = _fake_sky130_technology()
    fake_result = MagicMock(returncode=1, stdout="", stderr="fatal: network error")
    with patch("veriflow.commands.pdk._ensure_pdk_subdir_link") as mock_ensure:
        recovered = _recover_from_volare_symlink_failure(technology, tmp_path, fake_result, step_label="pdk install")
    assert recovered is False
    mock_ensure.assert_not_called()


def test_recover_from_volare_symlink_failure_detects_error_in_stderr(tmp_path):
    from veriflow.commands.pdk import _recover_from_volare_symlink_failure
    technology = _fake_sky130_technology()
    fake_result = MagicMock(
        returncode=1, stdout="",
        stderr="[WinError 1314] A required privilege is not held by the client",
    )
    with patch("veriflow.commands.pdk._ensure_pdk_subdir_link") as mock_ensure:
        recovered = _recover_from_volare_symlink_failure(technology, tmp_path, fake_result, step_label="pdk install")
    assert recovered is True
    mock_ensure.assert_called_once_with(technology, tmp_path, step_label="pdk install")


def test_recover_from_volare_symlink_failure_detects_error_in_stdout(tmp_path):
    """The real-world case: volare's Console() defaults to stdout, so the
    error text lands there, not in stderr."""
    from veriflow.commands.pdk import _recover_from_volare_symlink_failure
    technology = _fake_sky130_technology()
    fake_result = MagicMock(
        returncode=1,
        stdout="[WinError 1314] El cliente no dispone de un privilegio requerido: "
               "'volare\\\\sky130\\\\versions\\\\hash\\\\sky130A' -> 'C:\\\\...\\\\sky130A'",
        stderr="",
    )
    with patch("veriflow.commands.pdk._ensure_pdk_subdir_link") as mock_ensure:
        recovered = _recover_from_volare_symlink_failure(technology, tmp_path, fake_result, step_label="pdk install")
    assert recovered is True
    mock_ensure.assert_called_once()


def test_pdk_install_recovers_from_symlink_failure_when_files_extracted(tmp_path, capsys):
    """End-to-end: volare exits non-zero with the WinError 1314 signature,
    but the files it already fetched are on disk -- install must still
    succeed (rc == 0), not report VF_PDK_INSTALL_FAILED."""
    src_dir = tmp_path / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src_dir.mkdir(parents=True)
    fake_result = MagicMock(
        returncode=4294967295, stderr="",
        stdout="[WinError 1314] El cliente no dispone de un privilegio requerido: "
               "'volare\\\\sky130\\\\versions\\\\...\\\\sky130A' -> '...\\\\sky130A'",
    )
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "installed" in out
    mock_link.assert_called_once_with(src_dir, tmp_path / "sky130" / "sky130A")


def test_pdk_install_symlink_failure_recovery_still_fails_when_files_missing(tmp_path):
    """Same WinError signature, but this time the files genuinely aren't on
    disk either -- must still raise (VF_PDK_INSTALL_INCOMPLETE, from the
    fallback's own check), not silently report success."""
    fake_result = MagicMock(
        returncode=4294967295, stderr="",
        stdout="[WinError 1314] A required privilege is not held by the client",
    )
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_install
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="sky130"))
    assert exc_info.value.code == "VF_PDK_INSTALL_INCOMPLETE"


def test_pdk_install_unrelated_failure_still_raises_install_failed(tmp_path):
    """Confirms the recovery path is scoped to the specific WinError 1314
    signature -- any other non-zero returncode is still a hard failure."""
    fake_result = MagicMock(returncode=1, stdout="", stderr="network unreachable")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_install
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="sky130"))
    assert exc_info.value.code == "VF_PDK_INSTALL_FAILED"


def test_pdk_update_recovers_from_symlink_failure_when_files_extracted(tmp_path):
    (tmp_path / "sky130").mkdir()
    src_dir = tmp_path / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src_dir.mkdir(parents=True)
    fake_result = MagicMock(
        returncode=4294967295, stderr="",
        stdout="[WinError 1314] A required privilege is not held by the client",
    )
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        rc = main(["pdk", "update", "sky130"])
    assert rc == 0
    mock_link.assert_called_once_with(src_dir, tmp_path / "sky130" / "sky130A")


# ── volare tarball-cleanup failure recovery (_recover_from_volare_tarball_cleanup_failure) ──
#
# Discovered by reproducing a genuine, locked-file PermissionError with a
# real tempfile.TemporaryDirectory on this Windows machine, then reading
# the installed `volare` package's source (`manage.py`): `fetch()`
# downloads every requested library sequentially, then deletes each
# downloaded `*.tar.zst` in a `finally:` block via a bare
# `os.unlink(path)` that only catches FileNotFoundError -- not
# PermissionError. sky130 downloads several large libraries (~3 GB total)
# vs. gf180's few/smaller ones, making a still-locked archive (e.g. still
# being scanned by antivirus) far more likely for sky130 specifically.
# This is a genuine in-band exception -- not the `weakref.finalize`
# GC-cleanup traceback `_is_volare_cleanup_noise` already handles -- so it
# has no "Exception ignored in:" header, aborts `enable()` with a
# non-zero returncode, and previously leaked straight through the raw,
# unfiltered `raise VeriFlowError(...:\n{result.stderr or result.stdout}")`
# on that failure branch.

_TARBALL_CLEANUP_MESSAGE = (
    "[red][WinError 32] El proceso no tiene acceso al archivo porque "
    "est� siendo utilizado por otro proceso: "
    "'C:\\\\Users\\\\Roman\\\\AppData\\\\Local\\\\Temp\\\\tmp4u6on054.volare\\\\sky130_fd_sc_hd.tar.zst'"
)


def test_is_volare_tarball_cleanup_failure_true_for_realistic_message():
    from veriflow.commands.pdk import _is_volare_tarball_cleanup_failure
    assert _is_volare_tarball_cleanup_failure(_TARBALL_CLEANUP_MESSAGE) is True


def test_is_volare_tarball_cleanup_failure_false_for_unrelated_permission_error():
    from veriflow.commands.pdk import _is_volare_tarball_cleanup_failure
    unrelated = "[red][WinError 32] The process cannot access the file: 'C:\\\\some\\\\other\\\\file.txt'"
    assert _is_volare_tarball_cleanup_failure(unrelated) is False


def test_is_volare_tarball_cleanup_failure_false_for_unrelated_failure():
    from veriflow.commands.pdk import _is_volare_tarball_cleanup_failure
    assert _is_volare_tarball_cleanup_failure("fatal: network error") is False


def test_recover_from_volare_tarball_cleanup_failure_ignores_unrelated_failure(tmp_path):
    from veriflow.commands.pdk import _recover_from_volare_tarball_cleanup_failure
    technology = _fake_sky130_technology()
    fake_result = MagicMock(returncode=1, stdout="", stderr="fatal: network error")
    with patch("veriflow.commands.pdk._ensure_pdk_subdir_link") as mock_ensure:
        recovered = _recover_from_volare_tarball_cleanup_failure(
            technology, tmp_path, fake_result, step_label="pdk install"
        )
    assert recovered is False
    mock_ensure.assert_not_called()


def test_recover_from_volare_tarball_cleanup_failure_detects_error_in_stdout(tmp_path):
    """The real-world case: volare's Console() defaults to stdout, so the
    error text lands there, not in stderr (same as the symlink-privilege
    failure's presentation)."""
    from veriflow.commands.pdk import _recover_from_volare_tarball_cleanup_failure
    technology = _fake_sky130_technology()
    fake_result = MagicMock(returncode=1, stdout=_TARBALL_CLEANUP_MESSAGE, stderr="")
    with patch("veriflow.commands.pdk._ensure_pdk_subdir_link") as mock_ensure:
        recovered = _recover_from_volare_tarball_cleanup_failure(
            technology, tmp_path, fake_result, step_label="pdk install"
        )
    assert recovered is True
    mock_ensure.assert_called_once_with(technology, tmp_path, step_label="pdk install")


def test_pdk_install_recovers_from_tarball_cleanup_failure_when_files_extracted(tmp_path, capsys):
    """End-to-end: volare exits non-zero because it couldn't delete a
    locked temp tarball, but the library files it already extracted are on
    disk -- install must still succeed (rc == 0), not report
    VF_PDK_INSTALL_FAILED, and the raw PermissionError text must not reach
    the user unfiltered."""
    src_dir = tmp_path / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src_dir.mkdir(parents=True)
    fake_result = MagicMock(returncode=1, stderr="", stdout=_TARBALL_CLEANUP_MESSAGE)
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        rc = main(["--non-interactive", "pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "installed" in out
    assert "WinError 32" not in out
    mock_link.assert_called_once_with(src_dir, tmp_path / "sky130" / "sky130A")


def test_pdk_install_tarball_cleanup_recovery_still_fails_when_files_missing(tmp_path):
    """Same failure signature, but the files genuinely aren't on disk
    either -- must still raise (VF_PDK_INSTALL_INCOMPLETE), not silently
    report success."""
    fake_result = MagicMock(returncode=1, stderr="", stdout=_TARBALL_CLEANUP_MESSAGE)
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_install
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="sky130", non_interactive=True))
    assert exc_info.value.code == "VF_PDK_INSTALL_INCOMPLETE"


def test_pdk_update_recovers_from_tarball_cleanup_failure_when_files_extracted(tmp_path):
    (tmp_path / "sky130").mkdir()
    src_dir = tmp_path / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src_dir.mkdir(parents=True)
    fake_result = MagicMock(returncode=1, stderr="", stdout=_TARBALL_CLEANUP_MESSAGE)
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._create_pdk_link") as mock_link:
        rc = main(["--non-interactive", "pdk", "update", "sky130"])
    assert rc == 0
    mock_link.assert_called_once_with(src_dir, tmp_path / "sky130" / "sky130A")


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
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "update", "sky130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert args[0] == "volare"
    assert args[1] == "enable"


def test_pdk_update_passes_default_version_positionally(tmp_path):
    (tmp_path / "sky130").mkdir()
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "update", "sky130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    version = "0fe599b2afb6708d281543108caf8310912f54af"
    assert version in args
    assert args[args.index("--pdk") + 2] == version


def test_pdk_update_returncode_0_with_stderr_is_success_not_error(tmp_path, capsys):
    (tmp_path / "sky130").mkdir()
    fake_result = MagicMock(returncode=0, stdout="", stderr="some noisy cleanup message")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "update", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Error" not in out
    assert "some noisy cleanup message" in out


def test_pdk_update_returncode_nonzero_still_raises(tmp_path):
    (tmp_path / "sky130").mkdir()
    fake_result = MagicMock(returncode=1, stdout="", stderr="fatal: real failure")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_update
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_update(argparse.Namespace(pdk_name="sky130"))
    assert exc_info.value.code == "VF_PDK_UPDATE_FAILED"


# ── _warn_on_stderr helper ─────────────────────────────────────────────────────

def test_warn_on_stderr_prints_when_stderr_present():
    from veriflow.commands.pdk import _warn_on_stderr
    fake_result = MagicMock(returncode=0, stderr="  something happened  ")
    with patch("veriflow.commands.pdk.print_warn") as mock_warn:
        _warn_on_stderr(fake_result)
    mock_warn.assert_called_once_with("something happened")


def test_warn_on_stderr_silent_when_stderr_empty():
    from veriflow.commands.pdk import _warn_on_stderr
    fake_result = MagicMock(returncode=0, stderr="")
    with patch("veriflow.commands.pdk.print_warn") as mock_warn:
        _warn_on_stderr(fake_result)
    mock_warn.assert_not_called()


def test_warn_on_stderr_silent_when_stderr_none():
    from veriflow.commands.pdk import _warn_on_stderr
    fake_result = MagicMock(returncode=0, stderr=None)
    with patch("veriflow.commands.pdk.print_warn") as mock_warn:
        _warn_on_stderr(fake_result)
    mock_warn.assert_not_called()


def test_warn_on_stderr_whitespace_only_is_silent():
    from veriflow.commands.pdk import _warn_on_stderr
    fake_result = MagicMock(returncode=0, stderr="   \n  ")
    with patch("veriflow.commands.pdk.print_warn") as mock_warn:
        _warn_on_stderr(fake_result)
    mock_warn.assert_not_called()


# ── volare temp-file cleanup noise filtering ──────────────────────────────────
#
# On Windows, a `tempfile.py` finalizer can fail with PermissionError
# [WinError 32] trying to delete a `*.tar.zst` under a `*.volare` temp dir
# because the OS hasn't released the file handle yet by the time garbage
# collection runs the finalizer -- the install has already succeeded by
# then. CPython prints this as an "Exception ignored in: <finalize
# object ...>" traceback on stderr; it's pure noise, not an install error.

_CLEANUP_TRACEBACK = (
    "Exception ignored in: <finalize object at 0x0000020F12345678; dead>\n"
    "Traceback (most recent call last):\n"
    '  File "C:\\Python313\\Lib\\tempfile.py", line 900, in _cleanup\n'
    "    cls._rmtree(name, ignore_errors=ignore_errors)\n"
    '  File "C:\\Python313\\Lib\\tempfile.py", line 880, in _rmtree\n'
    "    _shutil.rmtree(name, onexc=onexc)\n"
    "PermissionError: [WinError 32] The process cannot access the file "
    "because it is being used by another process: "
    "'C:\\\\Users\\\\Roman\\\\AppData\\\\Local\\\\Temp\\\\tmp1a2b3c4d.volare\\\\sky130.tar.zst'\n"
)

_REAL_ERROR_LINE = "Error: could not resolve PDK version 'bogus-hash' for sky130\n"


def test_is_volare_cleanup_noise_true_for_pure_traceback():
    from veriflow.commands.pdk import _is_volare_cleanup_noise
    assert _is_volare_cleanup_noise(_CLEANUP_TRACEBACK) is True


def test_is_volare_cleanup_noise_true_for_empty_or_whitespace():
    from veriflow.commands.pdk import _is_volare_cleanup_noise
    assert _is_volare_cleanup_noise("") is True
    assert _is_volare_cleanup_noise("   \n  ") is True


def test_is_volare_cleanup_noise_false_for_real_error():
    from veriflow.commands.pdk import _is_volare_cleanup_noise
    assert _is_volare_cleanup_noise(_REAL_ERROR_LINE) is False


def test_is_volare_cleanup_noise_false_when_mixed_with_real_error():
    """Not PURELY the cleanup traceback -- must not be classified as noise,
    so mixed content is never silently swallowed whole."""
    from veriflow.commands.pdk import _is_volare_cleanup_noise
    assert _is_volare_cleanup_noise(_CLEANUP_TRACEBACK + _REAL_ERROR_LINE) is False


def test_is_volare_cleanup_noise_false_for_unrelated_permission_error():
    """Same WinError 32 code, but not a volare temp .tar.zst -- must not be
    misclassified as the known-harmless case."""
    from veriflow.commands.pdk import _is_volare_cleanup_noise
    unrelated = (
        "Exception ignored in: <finalize object at 0x1; dead>\n"
        "Traceback (most recent call last):\n"
        '  File "tempfile.py", line 1, in _cleanup\n'
        "PermissionError: [WinError 32] The process cannot access the file "
        "because it is being used by another process: 'C:\\\\some\\\\other\\\\file.txt'\n"
    )
    assert _is_volare_cleanup_noise(unrelated) is False


def test_filter_volare_cleanup_noise_removes_pure_traceback():
    from veriflow.commands.pdk import _filter_volare_cleanup_noise
    assert _filter_volare_cleanup_noise(_CLEANUP_TRACEBACK) == ""


def test_filter_volare_cleanup_noise_empty_stays_empty():
    from veriflow.commands.pdk import _filter_volare_cleanup_noise
    assert _filter_volare_cleanup_noise("") == ""
    assert _filter_volare_cleanup_noise("   \n  ") == ""


def test_filter_volare_cleanup_noise_keeps_real_error_unchanged():
    from veriflow.commands.pdk import _filter_volare_cleanup_noise
    assert _filter_volare_cleanup_noise(_REAL_ERROR_LINE) == _REAL_ERROR_LINE.strip()


def test_filter_volare_cleanup_noise_strips_traceback_keeps_real_error():
    """Mixed stderr: cleanup traceback + a real error -- only the real
    error should survive filtering."""
    from veriflow.commands.pdk import _filter_volare_cleanup_noise
    mixed = _CLEANUP_TRACEBACK + _REAL_ERROR_LINE
    result = _filter_volare_cleanup_noise(mixed)
    assert result == _REAL_ERROR_LINE.strip()
    assert "Exception ignored in" not in result
    assert "tempfile.py" not in result


def test_filter_volare_cleanup_noise_real_error_before_traceback():
    """Order shouldn't matter -- real error first, cleanup traceback after."""
    from veriflow.commands.pdk import _filter_volare_cleanup_noise
    mixed = _REAL_ERROR_LINE + _CLEANUP_TRACEBACK
    result = _filter_volare_cleanup_noise(mixed)
    assert result == _REAL_ERROR_LINE.strip()


def test_warn_on_stderr_pure_cleanup_noise_is_suppressed():
    from veriflow.commands.pdk import _warn_on_stderr
    fake_result = MagicMock(returncode=0, stderr=_CLEANUP_TRACEBACK)
    with patch("veriflow.commands.pdk.print_warn") as mock_warn:
        _warn_on_stderr(fake_result)
    mock_warn.assert_not_called()


def test_warn_on_stderr_mixed_shows_only_real_error():
    from veriflow.commands.pdk import _warn_on_stderr
    fake_result = MagicMock(returncode=0, stderr=_CLEANUP_TRACEBACK + _REAL_ERROR_LINE)
    with patch("veriflow.commands.pdk.print_warn") as mock_warn:
        _warn_on_stderr(fake_result)
    mock_warn.assert_called_once_with(_REAL_ERROR_LINE.strip())


def test_warn_on_stderr_real_error_without_cleanup_shown_normally():
    from veriflow.commands.pdk import _warn_on_stderr
    fake_result = MagicMock(returncode=0, stderr=_REAL_ERROR_LINE)
    with patch("veriflow.commands.pdk.print_warn") as mock_warn:
        _warn_on_stderr(fake_result)
    mock_warn.assert_called_once_with(_REAL_ERROR_LINE.strip())


def test_pdk_install_suppresses_cleanup_noise_end_to_end(tmp_path, capsys):
    """End-to-end: volare exits 0 with only cleanup-traceback stderr --
    install reports success with no warning noise shown to the user."""
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr=_CLEANUP_TRACEBACK)
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        rc = main(["pdk", "install", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Exception ignored in" not in out
    assert "tempfile.py" not in out


# ── pdk versions ──────────────────────────────────────────────────────────────

def test_pdk_versions_success_calls_ls_remote_and_parses_lines(tmp_path):
    fake_result = MagicMock(returncode=0, stdout="abc123\ndef456\n\n", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run:
        from veriflow.commands.pdk import cmd_pdk_versions
        import argparse
        rc, result = cmd_pdk_versions(argparse.Namespace(pdk_name="sky130"))
    assert rc == 0
    assert result["pdk"] == "sky130"
    assert result["versions"] == ["abc123", "def456"]
    called_args = mock_run.call_args.args[0]
    assert called_args == ["volare", "ls-remote", "--pdk", "sky130"]


def test_pdk_versions_output_hides_volare_mention_on_success(tmp_path, capsys):
    """Per spec: the user shouldn't need to know volare exists."""
    fake_result = MagicMock(returncode=0, stdout="abc123\n", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        main(["pdk", "versions", "sky130"])
    out = capsys.readouterr().out
    assert "volare" not in out.lower()
    assert "abc123" in out
    assert "Available versions" in out


def test_pdk_versions_volare_missing_prints_clear_message_and_exits_1(tmp_path, capsys):
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=False):
        rc = main(["pdk", "versions", "sky130"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "volare" in out
    assert "pdks" in out


def test_pdk_versions_unsupported_for_git_backed_technology(tmp_path):
    from veriflow.commands.pdk import cmd_pdk_versions
    import argparse
    with patched_pdk_root(tmp_path):
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_versions(argparse.Namespace(pdk_name="ihp130"))
    assert exc_info.value.code == "VF_PDK_VERSIONS_UNSUPPORTED"


def test_pdk_versions_unsupported_for_generic(tmp_path):
    from veriflow.commands.pdk import cmd_pdk_versions
    import argparse
    with patched_pdk_root(tmp_path):
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_versions(argparse.Namespace(pdk_name="generic"))
    assert exc_info.value.code == "VF_PDK_VERSIONS_UNSUPPORTED"


def test_pdk_versions_unknown_technology_raises(tmp_path):
    from veriflow.commands.pdk import cmd_pdk_versions
    import argparse
    with patched_pdk_root(tmp_path):
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_versions(argparse.Namespace(pdk_name="notapdkname"))
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_pdk_versions_subprocess_failure_raises(tmp_path):
    fake_result = MagicMock(returncode=1, stdout="", stderr="network error")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        from veriflow.commands.pdk import cmd_pdk_versions
        import argparse
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_versions(argparse.Namespace(pdk_name="sky130"))
    assert exc_info.value.code == "VF_PDK_VERSIONS_FAILED"


def test_pdk_versions_json_mode(tmp_path, capsys):
    fake_result = MagicMock(returncode=0, stdout="abc123\n", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result):
        rc = main(["--json", "pdk", "versions", "sky130"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["command"] == "pdk versions"
    assert data["versions"] == ["abc123"]


def test_pdk_versions_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["pdk", "versions", "sky130"])
    assert args.command == "pdk"
    assert args.pdk_command == "versions"
    assert args.pdk_name == "sky130"


# ── pdk remove ────────────────────────────────────────────────────────────────

def test_pdk_remove_not_installed_prints_error_and_exits_1(tmp_path):
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "remove", "sky130"])
    assert rc == 1


def test_pdk_remove_unknown_technology_raises(tmp_path):
    from veriflow.commands.pdk import cmd_pdk_remove
    with patched_pdk_root(tmp_path):
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_remove(argparse.Namespace(pdk_name="notapdkname", dry_run=False))
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_pdk_remove_deletes_installed_pdk(tmp_path, capsys):
    pdk_dir = tmp_path / "sky130"
    (pdk_dir / "sky130A" / "libs.ref").mkdir(parents=True)
    (pdk_dir / "sky130A" / "libs.ref" / "cells.lib").write_text("x" * 1000, encoding="utf-8")
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "remove", "sky130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert not pdk_dir.exists()
    assert "removed" in out


def test_pdk_remove_deletes_readonly_files(tmp_path, capsys):
    """Regression test for a real bug found via manual verification: git
    marks files under .git/objects/pack/ read-only on Windows, and plain
    shutil.rmtree raises PermissionError: [WinError 5] Access is denied on
    them. Reproduced for real against an actual git-installed PDK (ihp130)
    on this machine; cmd_pdk_remove must clear the read-only bit and retry."""
    import os
    import stat

    pdk_dir = tmp_path / "ihp130"
    pack_dir = pdk_dir / ".git" / "objects" / "pack"
    pack_dir.mkdir(parents=True)
    readonly_file = pack_dir / "pack-abc123.idx"
    readonly_file.write_bytes(b"fake pack data")
    os.chmod(readonly_file, stat.S_IREAD)

    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "remove", "ihp130"])
    out = capsys.readouterr().out
    assert rc == 0
    assert not pdk_dir.exists()
    assert "removed" in out


def test_pdk_remove_dry_run_does_not_delete(tmp_path, capsys):
    pdk_dir = tmp_path / "sky130"
    (pdk_dir / "sky130A" / "libs.ref").mkdir(parents=True)
    (pdk_dir / "sky130A" / "libs.ref" / "cells.lib").write_text("x" * (2 * 1024 * 1024), encoding="utf-8")
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "remove", "sky130", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert pdk_dir.exists()  # nothing deleted
    assert "Would remove" in out
    assert "MB" in out or "GB" in out
    assert "sky130" in out


def test_pdk_remove_dry_run_shows_correct_size(tmp_path):
    from veriflow.commands.pdk import cmd_pdk_remove
    pdk_dir = tmp_path / "sky130"
    (pdk_dir / "sky130A").mkdir(parents=True)
    (pdk_dir / "sky130A" / "a.lib").write_bytes(b"x" * 500_000)
    (pdk_dir / "sky130A" / "b.lib").write_bytes(b"x" * 500_000)
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk.shutil.rmtree") as mock_rmtree:
        rc = cmd_pdk_remove(argparse.Namespace(pdk_name="sky130", dry_run=True))
    assert rc == 0
    mock_rmtree.assert_not_called()


def test_format_size_mb_and_gb():
    from veriflow.commands.pdk import _format_size
    assert _format_size(500 * 1024 * 1024) == "500.0 MB"
    assert _format_size(int(2.5 * 1024 * 1024 * 1024)) == "2.50 GB"


def test_dir_size_bytes_sums_files_recursively(tmp_path):
    from veriflow.commands.pdk import _dir_size_bytes
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_bytes(b"1" * 100)
    (tmp_path / "sub" / "b.txt").write_bytes(b"2" * 200)
    assert _dir_size_bytes(tmp_path) == 300


# ── pdk install/update --version ───────────────────────────────────────────────

def test_pdk_install_version_passed_positionally_to_volare(tmp_path):
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130", "--version", "deadbeef00"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert "deadbeef00" in args
    assert args[args.index("--pdk") + 2] == "deadbeef00"
    # overrides the yaml-pinned default_version, not appended alongside it
    assert "0fe599b2afb6708d281543108caf8310912f54af" not in args


def test_pdk_install_no_version_flag_uses_pinned_default(tmp_path):
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert "0fe599b2afb6708d281543108caf8310912f54af" in args


def test_pdk_install_same_version_reports_already_installed(tmp_path, capsys):
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib").write_text("", encoding="utf-8")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk.get_installed_pdk_version", return_value="abc123"), \
         patch("veriflow.commands.pdk.subprocess.run") as mock_run:
        rc = main(["pdk", "install", "sky130", "--version", "abc123"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already installed" in out
    assert "abc123" in out
    mock_run.assert_not_called()


def test_pdk_install_different_version_shows_message_and_proceeds(tmp_path, capsys):
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib").write_text("", encoding="utf-8")
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk.get_installed_pdk_version", return_value="old_hash"), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "install", "sky130", "--version", "new_hash"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "old_hash" in out
    assert "--version new_hash" in out
    assert "replace" in out
    assert "installation" in out
    # proceeded with the (re)install rather than stopping
    mock_run.assert_called_once()
    args = mock_run.call_args.args[0]
    assert "new_hash" in args


def test_pdk_update_version_flag_fetches_and_checks_out_volare(tmp_path):
    """volare technologies route --version through build_volare_enable_command
    (same as install) -- no separate fetch/checkout needed for volare."""
    (tmp_path / "sky130").mkdir()
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk._ensure_pdk_subdir_link"):
        rc = main(["pdk", "update", "sky130", "--version", "cafef00d"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert "cafef00d" in args


def test_pdk_install_git_version_checks_out_after_clone(tmp_path):
    fake_clone = MagicMock(returncode=0, stdout="", stderr="")
    fake_checkout = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._git_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", side_effect=[fake_clone, fake_checkout]) as mock_run:
        rc = main(["pdk", "install", "ihp130", "--version", "22f2a25f"])
    assert rc == 0
    assert mock_run.call_count == 2
    clone_args = mock_run.call_args_list[0].args[0]
    checkout_args = mock_run.call_args_list[1].args[0]
    assert clone_args[:2] == ["git", "clone"]
    assert checkout_args == ["git", "-C", str(tmp_path / "ihp130"), "checkout", "22f2a25f"]


def test_pdk_install_git_no_version_skips_checkout(tmp_path):
    fake_clone = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._git_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_clone) as mock_run:
        rc = main(["pdk", "install", "ihp130"])
    assert rc == 0
    mock_run.assert_called_once()  # clone only, no checkout


def test_pdk_install_git_checkout_failure_raises(tmp_path):
    fake_clone = MagicMock(returncode=0, stdout="", stderr="")
    fake_checkout = MagicMock(returncode=1, stdout="", stderr="error: pathspec did not match")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._git_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", side_effect=[fake_clone, fake_checkout]):
        from veriflow.commands.pdk import cmd_pdk_install
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_pdk_install(argparse.Namespace(pdk_name="ihp130", version="bogus"))
    assert exc_info.value.code == "VF_PDK_INSTALL_FAILED"


def test_pdk_update_git_version_fetches_and_checks_out(tmp_path):
    (tmp_path / "ihp130").mkdir()
    fake_fetch = MagicMock(returncode=0, stdout="", stderr="")
    fake_checkout = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._git_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", side_effect=[fake_fetch, fake_checkout]) as mock_run:
        rc = main(["pdk", "update", "ihp130", "--version", "22f2a25f"])
    assert rc == 0
    fetch_args = mock_run.call_args_list[0].args[0]
    checkout_args = mock_run.call_args_list[1].args[0]
    assert fetch_args == ["git", "-C", str(tmp_path / "ihp130"), "fetch"]
    assert checkout_args == ["git", "-C", str(tmp_path / "ihp130"), "checkout", "22f2a25f"]


def test_pdk_update_git_no_version_pulls_as_before(tmp_path):
    (tmp_path / "ihp130").mkdir()
    fake_pull = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._git_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_pull) as mock_run:
        rc = main(["pdk", "update", "ihp130"])
    assert rc == 0
    args = mock_run.call_args.args[0]
    assert args == ["git", "-C", str(tmp_path / "ihp130"), "pull"]


# ── Parser ────────────────────────────────────────────────────────────────────

def test_pdk_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["pdk", "install", "sky130"])
    assert args.command == "pdk"
    assert args.pdk_command == "install"
    assert args.pdk_name == "sky130"


def test_pdk_remove_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["pdk", "remove", "sky130", "--dry-run"])
    assert args.command == "pdk"
    assert args.pdk_command == "remove"
    assert args.pdk_name == "sky130"
    assert args.dry_run is True


def test_pdk_install_version_flag_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["pdk", "install", "sky130", "--version", "abc123"])
    assert args.version == "abc123"


def test_pdk_update_version_flag_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["pdk", "update", "sky130", "--version", "abc123"])
    assert args.version == "abc123"


def test_pdk_no_subcommand_returns_1():
    rc = main(["pdk"])
    assert rc == 1


# ── install/update progress spinner (_run_subprocess_with_spinner) ────────────
#
# sky130 installs can take several minutes and ~3 GB -- with nothing printed
# between the initial "Installing sky130 ..." step line and the final
# result, it's indistinguishable from a hang. A Rich Progress spinner runs
# while the volare/git subprocess executes on a worker thread, and is
# suppressed entirely under --non-interactive so it never pollutes CI logs.

def test_run_subprocess_with_spinner_non_interactive_skips_spinner():
    from veriflow.commands.pdk import _run_subprocess_with_spinner
    fake_result = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result) as mock_run, \
         patch("veriflow.commands.pdk.Progress") as mock_progress_cls:
        result = _run_subprocess_with_spinner(["echo", "hi"], "Installing...", non_interactive=True)
    assert result is fake_result
    mock_run.assert_called_once_with(["echo", "hi"], capture_output=True, text=True)
    mock_progress_cls.assert_not_called()


def test_run_subprocess_with_spinner_interactive_shows_spinner():
    """A mocked subprocess that takes a moment -- the spinner (Progress)
    must be constructed and given a task carrying the install message while
    the subprocess (running on a worker thread) is still in flight."""
    import time

    from veriflow.commands.pdk import _run_subprocess_with_spinner

    fake_result = MagicMock(returncode=0, stdout="ok", stderr="")

    def _slow_run(*_args, **_kwargs):
        time.sleep(0.2)
        return fake_result

    mock_progress_instance = MagicMock()
    mock_progress_instance.__enter__.return_value = mock_progress_instance

    with patch("veriflow.commands.pdk.subprocess.run", side_effect=_slow_run), \
         patch("veriflow.commands.pdk.Progress", return_value=mock_progress_instance) as mock_progress_cls:
        result = _run_subprocess_with_spinner(
            ["volare", "enable"],
            "Installing sky130 via volare... (this may take several minutes)",
            non_interactive=False,
        )

    assert result is fake_result
    mock_progress_cls.assert_called_once()
    mock_progress_instance.add_task.assert_called_once_with(
        "Installing sky130 via volare... (this may take several minutes)", total=None
    )
    mock_progress_instance.__exit__.assert_called_once()


def test_pdk_install_non_interactive_suppresses_spinner(tmp_path):
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk.Progress") as mock_progress_cls:
        rc = main(["--non-interactive", "pdk", "install", "sky130"])
    assert rc == 0
    mock_progress_cls.assert_not_called()


def test_pdk_install_interactive_uses_spinner(tmp_path):
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    mock_progress_instance = MagicMock()
    mock_progress_instance.__enter__.return_value = mock_progress_instance
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk.Progress", return_value=mock_progress_instance) as mock_progress_cls:
        rc = main(["pdk", "install", "sky130"])
    assert rc == 0
    mock_progress_cls.assert_called_once()
    call_args = mock_progress_instance.add_task.call_args
    assert "sky130" in call_args.args[0]
    assert "volare" in call_args.args[0]


def test_pdk_update_non_interactive_suppresses_spinner(tmp_path):
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk.Progress") as mock_progress_cls:
        rc = main(["--non-interactive", "pdk", "update", "sky130"])
    assert rc == 0
    mock_progress_cls.assert_not_called()


def test_pdk_update_interactive_uses_spinner(tmp_path):
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    mock_progress_instance = MagicMock()
    mock_progress_instance.__enter__.return_value = mock_progress_instance
    with patched_pdk_root(tmp_path), \
         patch("veriflow.commands.pdk._volare_available", return_value=True), \
         patch("veriflow.commands.pdk.subprocess.run", return_value=fake_result), \
         patch("veriflow.commands.pdk.Progress", return_value=mock_progress_instance) as mock_progress_cls:
        rc = main(["pdk", "update", "sky130"])
    assert rc == 0
    mock_progress_cls.assert_called_once()


# ── pdk path ────────────────────────────────────────────────────────────────

def test_pdk_path_prints_plain_path_for_installed_pdk(tmp_path, capsys):
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "path", "sky130"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == str(tmp_path / "sky130")
    assert captured.err == ""


def test_pdk_path_not_installed_errors_to_stderr(tmp_path, capsys):
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "path", "sky130"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "not installed" in captured.err


def test_pdk_path_prints_root_even_without_liberty(tmp_path, capsys):
    """[INSTALLED, NO LIBERTY] -- get_pdk_path only checks the directory
    exists, so the root path is still printed (useful for diagnosing an
    incomplete install)."""
    (tmp_path / "sky130").mkdir()
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "path", "sky130"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == str(tmp_path / "sky130")


def test_pdk_path_unknown_technology_fails(tmp_path):
    with patched_pdk_root(tmp_path):
        rc = main(["pdk", "path", "notapdkname"])
    assert rc == 1


def test_pdk_path_flag_parses():
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["pdk", "path", "sky130"])
    assert args.pdk_command == "path"
    assert args.pdk_name == "sky130"
