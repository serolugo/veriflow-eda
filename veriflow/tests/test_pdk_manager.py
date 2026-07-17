"""Tests for veriflow.models.pdk_manager -- PDK directory resolution under
VERIFLOW_PDK_ROOT (~/.veriflow/pdks/), consumed by `veriflow pdk` (CLI),
`veriflow doctor`'s [TECHNOLOGIES] section, and SynthesisStage's automatic
liberty resolution.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core import VeriFlowError
from veriflow.models import pdk_manager
from veriflow.models.technology_profile import TechnologyProfile


def _patch_pdk_root(tmp_path: Path):
    return patch.object(pdk_manager, "VERIFLOW_PDK_ROOT", tmp_path)


# ── get_pdk_path ────────────────────────────────────────────────────────────

def test_get_pdk_path_returns_none_when_missing(tmp_path):
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_pdk_path("sky130") is None


def test_get_pdk_path_returns_path_when_present(tmp_path):
    (tmp_path / "sky130").mkdir()
    with _patch_pdk_root(tmp_path):
        result = pdk_manager.get_pdk_path("sky130")
    assert result == tmp_path / "sky130"


def test_get_pdk_path_ignores_a_file_with_the_same_name(tmp_path):
    (tmp_path / "sky130").write_text("not a directory", encoding="utf-8")
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_pdk_path("sky130") is None


# ── get_liberty_path ─────────────────────────────────────────────────────────

def _fake_technology(**overrides) -> TechnologyProfile:
    base = dict(
        name="sky130",
        pdk_subdir="sky130A",
        liberty_glob="libs.ref/sky130_fd_sc_hd/lib/*.lib",
    )
    base.update(overrides)
    return TechnologyProfile(**base)


def test_get_liberty_path_none_when_pdk_not_installed(tmp_path):
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=_fake_technology()):
        assert pdk_manager.get_liberty_path("sky130") is None


def test_get_liberty_path_none_when_no_liberty_glob(tmp_path):
    (tmp_path / "sky130").mkdir()
    technology = _fake_technology(liberty_glob=None)
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=technology):
        assert pdk_manager.get_liberty_path("sky130") is None


def test_get_liberty_path_none_when_glob_matches_nothing(tmp_path):
    (tmp_path / "sky130" / "sky130A").mkdir(parents=True)
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=_fake_technology()):
        assert pdk_manager.get_liberty_path("sky130") is None


def test_get_liberty_path_returns_matching_file(tmp_path):
    lib_dir = tmp_path / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    lib_file = lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib"
    lib_file.write_text("", encoding="utf-8")
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=_fake_technology()):
        result = pdk_manager.get_liberty_path("sky130")
    assert result == lib_file


def test_get_liberty_path_without_pdk_subdir_searches_pdk_root_directly(tmp_path):
    lib_dir = tmp_path / "ihp130" / "libs.ref" / "sg13g2_stdcell" / "lib"
    lib_dir.mkdir(parents=True)
    lib_file = lib_dir / "sg13g2_stdcell_typ_1p20V_25C.lib"
    lib_file.write_text("", encoding="utf-8")
    technology = _fake_technology(
        name="ihp130", pdk_subdir=None, liberty_glob="libs.ref/sg13g2_stdcell/lib/*.lib"
    )
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.get_technology_profile", return_value=technology):
        result = pdk_manager.get_liberty_path("ihp130")
    assert result == lib_file


def test_get_liberty_path_unknown_technology_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        pdk_manager.get_liberty_path("notapdkname")
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_get_liberty_path_generic_has_no_glob(tmp_path):
    """generic.yaml has no liberty_glob -- always None regardless of what's on disk."""
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_liberty_path("generic") is None


# ── build_volare_enable_command ───────────────────────────────────────────────

def test_build_volare_enable_command_with_default_version(tmp_path):
    technology = _fake_technology(
        name="sky130",
        volare_pdk="sky130",
        default_version="0fe599b2afb6708d281543108caf8310912f54af",
    )
    pdk_dir = tmp_path / "sky130"
    cmd = pdk_manager.build_volare_enable_command(technology, pdk_dir)
    assert cmd == [
        "volare", "enable", "--pdk", "sky130",
        "0fe599b2afb6708d281543108caf8310912f54af",
        "--pdk-root", str(pdk_dir),
    ]


def test_build_volare_enable_command_without_default_version_unchanged(tmp_path):
    """No default_version -- same shape as before this field existed."""
    technology = _fake_technology(name="sky130", volare_pdk="sky130", default_version=None)
    pdk_dir = tmp_path / "sky130"
    cmd = pdk_manager.build_volare_enable_command(technology, pdk_dir)
    assert cmd == ["volare", "enable", "--pdk", "sky130", "--pdk-root", str(pdk_dir)]


def test_build_volare_enable_command_version_is_positional_before_pdk_root(tmp_path):
    technology = _fake_technology(name="gf180", volare_pdk="gf180mcu", default_version="abc123")
    pdk_dir = tmp_path / "gf180"
    cmd = pdk_manager.build_volare_enable_command(technology, pdk_dir)
    assert cmd.index("abc123") < cmd.index("--pdk-root")
    assert cmd[cmd.index("--pdk") + 2] == "abc123"  # right after --pdk <volare_pdk>


def test_builtin_sky130_and_gf180_have_default_version():
    from veriflow.models.technology_profile import get_technology_profile
    for name in ("sky130", "gf180"):
        technology = get_technology_profile(name)
        assert technology.default_version == "0fe599b2afb6708d281543108caf8310912f54af"


def test_builtin_ihp130_and_generic_have_no_default_version():
    from veriflow.models.technology_profile import get_technology_profile
    for name in ("ihp130", "generic"):
        technology = get_technology_profile(name)
        assert technology.default_version is None


# ── _create_pdk_link ─────────────────────────────────────────────────────────
#
# volare creates pdk_root/<pdk_subdir> as a symlink into
# pdk_root/versions/<version>/<pdk_subdir>. On Windows, creating a symlink
# requires SeCreateSymbolicLinkPrivilege or Developer Mode -- without it,
# Path.symlink_to() raises OSError, and _create_pdk_link falls back to a
# junction point (`mklink /J`), which works on NTFS without admin rights.

def test_create_pdk_link_posix_calls_symlink_only(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    with patch("veriflow.models.pdk_manager.sys.platform", "linux"), \
         patch.object(Path, "symlink_to") as mock_symlink, \
         patch("veriflow.models.pdk_manager.subprocess.run") as mock_run:
        pdk_manager._create_pdk_link(src, dst)
    mock_symlink.assert_called_once_with(src)
    mock_run.assert_not_called()


def test_create_pdk_link_windows_symlink_succeeds_no_mklink(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    with patch("veriflow.models.pdk_manager.sys.platform", "win32"), \
         patch.object(Path, "symlink_to") as mock_symlink, \
         patch("veriflow.models.pdk_manager.subprocess.run") as mock_run:
        pdk_manager._create_pdk_link(src, dst)
    mock_symlink.assert_called_once_with(src)
    mock_run.assert_not_called()


def test_create_pdk_link_windows_symlink_fails_falls_back_to_mklink_junction(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    fake_result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("veriflow.models.pdk_manager.sys.platform", "win32"), \
         patch.object(Path, "symlink_to", side_effect=OSError("privilege not held")), \
         patch("veriflow.models.pdk_manager.subprocess.run", return_value=fake_result) as mock_run:
        pdk_manager._create_pdk_link(src, dst)  # must not raise
    mock_run.assert_called_once_with(
        ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
        capture_output=True,
        text=True,
    )


def test_create_pdk_link_windows_junction_also_fails_raises_oserror(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    fake_result = MagicMock(returncode=1, stdout="", stderr="Access is denied.")
    with patch("veriflow.models.pdk_manager.sys.platform", "win32"), \
         patch.object(Path, "symlink_to", side_effect=OSError("privilege not held")), \
         patch("veriflow.models.pdk_manager.subprocess.run", return_value=fake_result):
        with pytest.raises(OSError) as exc_info:
            pdk_manager._create_pdk_link(src, dst)
    message = str(exc_info.value)
    assert str(src) in message
    assert str(dst) in message
    assert "Access is denied." in message


def test_create_pdk_link_posix_symlink_failure_reraises_without_mklink(tmp_path):
    """Junction points are an NTFS/Windows concept -- on Linux/macOS a
    symlink failure propagates unchanged, no fallback attempted."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    with patch("veriflow.models.pdk_manager.sys.platform", "linux"), \
         patch.object(Path, "symlink_to", side_effect=OSError("permission denied")), \
         patch("veriflow.models.pdk_manager.subprocess.run") as mock_run:
        with pytest.raises(OSError, match="permission denied"):
            pdk_manager._create_pdk_link(src, dst)
    mock_run.assert_not_called()


# ── get_installed_pdk_version ─────────────────────────────────────────────────

def test_get_installed_pdk_version_none_when_not_installed(tmp_path):
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_installed_pdk_version("sky130") is None


def test_get_installed_pdk_version_unknown_technology_raises():
    with pytest.raises(VeriFlowError) as exc_info:
        pdk_manager.get_installed_pdk_version("notapdkname")
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_get_installed_pdk_version_generic_returns_none(tmp_path):
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_installed_pdk_version("generic") is None


def test_get_installed_pdk_version_volare_resolves_hash_from_link_target(tmp_path):
    """Uses the real _create_pdk_link mechanism to set up the link (real
    symlink on POSIX, junction-point fallback on Windows without Developer
    Mode) -- exercises the same resolution path production code relies on,
    not a mocked stand-in for it."""
    pdk_dir = tmp_path / "sky130"
    version_hash = "0fe599b2afb6708d281543108caf8310912f54af"
    src = pdk_dir / "volare" / "sky130" / "versions" / version_hash / "sky130A"
    src.mkdir(parents=True)
    link = pdk_dir / "sky130A"
    pdk_manager._create_pdk_link(src, link)

    with _patch_pdk_root(tmp_path):
        version = pdk_manager.get_installed_pdk_version("sky130")
    assert version == version_hash


def test_get_installed_pdk_version_volare_none_when_link_missing(tmp_path):
    """PDK directory exists but the top-level pdk_subdir link was never
    created (or the fallback hasn't run yet) -- can't determine a version."""
    (tmp_path / "sky130").mkdir()
    with _patch_pdk_root(tmp_path):
        assert pdk_manager.get_installed_pdk_version("sky130") is None


def test_get_installed_pdk_version_git_returns_short_hash(tmp_path):
    pdk_dir = tmp_path / "ihp130"
    pdk_dir.mkdir()
    fake_result = MagicMock(returncode=0, stdout="a3f1c2d4\n", stderr="")
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.subprocess.run", return_value=fake_result) as mock_run:
        version = pdk_manager.get_installed_pdk_version("ihp130")
    assert version == "a3f1c2d4"
    args = mock_run.call_args.args[0]
    assert args[:3] == ["git", "-C", str(pdk_dir)]
    assert "rev-parse" in args
    assert "--short" in args
    assert "HEAD" in args


def test_get_installed_pdk_version_git_none_when_command_fails(tmp_path):
    pdk_dir = tmp_path / "ihp130"
    pdk_dir.mkdir()
    fake_result = MagicMock(returncode=128, stdout="", stderr="fatal: not a git repository")
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.subprocess.run", return_value=fake_result):
        assert pdk_manager.get_installed_pdk_version("ihp130") is None


def test_get_installed_pdk_version_git_none_when_git_missing(tmp_path):
    pdk_dir = tmp_path / "ihp130"
    pdk_dir.mkdir()
    with _patch_pdk_root(tmp_path), \
         patch("veriflow.models.pdk_manager.subprocess.run", side_effect=OSError("git not found")):
        assert pdk_manager.get_installed_pdk_version("ihp130") is None
