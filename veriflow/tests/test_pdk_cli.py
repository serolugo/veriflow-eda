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
