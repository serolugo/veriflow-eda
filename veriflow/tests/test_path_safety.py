"""Tests for veriflow.core.path_safety.safe_join() -- the shared
path-containment guard added for dev-docs/SECURITY_AUDIT.md's Findings
#1/#2/#6 (wrapper_name, tile_id, readme_template all interpolated a
user-controlled string into a path with no containment check).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from veriflow.core import VeriFlowError
from veriflow.core.path_safety import safe_join


def test_safe_join_plain_name_stays_inside(tmp_path):
    result = safe_join(tmp_path, "file.txt")
    assert result == (tmp_path / "file.txt").resolve()


def test_safe_join_nested_relative_name_stays_inside(tmp_path):
    result = safe_join(tmp_path, "sub/dir/file.txt")
    assert result == (tmp_path / "sub" / "dir" / "file.txt").resolve()


def test_safe_join_base_dir_need_not_exist_yet(tmp_path):
    """Callers validate a destination path before creating its parent
    directory (e.g. wrap.py validates before out_dir/rtl exists) --
    safe_join must not require base_dir to already be real on disk."""
    base = tmp_path / "not_created_yet"
    result = safe_join(base, "file.txt")
    assert result == (base / "file.txt").resolve()


def test_safe_join_dot_dot_traversal_rejected(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        safe_join(tmp_path, "../escaped.txt")
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_safe_join_deep_dot_dot_traversal_rejected(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        safe_join(tmp_path, "../../../../../../etc/passwd")
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_safe_join_absolute_path_override_rejected(tmp_path):
    """The pathlib gotcha this whole module exists to close: `Path("a") /
    "/etc/passwd"` discards "a" entirely on POSIX. safe_join must catch
    this via the containment check even though the raw `/` join itself
    doesn't error."""
    outside = tmp_path.parent / "OUTSIDE" / "pwned.txt"
    with pytest.raises(VeriFlowError) as exc_info:
        safe_join(tmp_path, str(outside))
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_safe_join_absolute_path_that_happens_to_be_inside_is_allowed(tmp_path):
    """An absolute path is not rejected just for being absolute -- only for
    resolving outside base_dir. A caller passing an already-absolute path
    that's legitimately inside base_dir (e.g. a CLI --template argument
    given as a full path) must still work."""
    inside = tmp_path / "legit.txt"
    result = safe_join(tmp_path, str(inside))
    assert result == inside.resolve()


def test_safe_join_windows_drive_absolute_override_rejected(tmp_path):
    """A Windows drive-letter absolute path (`C:/...`) is the platform's
    equivalent full override -- rejected the same way as a POSIX absolute
    path, not silently nested under base_dir.

    This must reject identically on every host OS, not just Windows: a
    malicious `wrapper_name`/`tile_id`/`readme_template` can encode this
    pattern regardless of which OS is actually running VeriFlow when it's
    processed (e.g. a shuttle organizer importing a contributor's repo on
    Linux CI). On POSIX, `PurePosixPath("C:/...").is_absolute()` is False
    (it doesn't start with "/"), so a naive `is_absolute()`-only check
    would silently nest this under base_dir instead of rejecting it --
    see the two tests below, which simulate that POSIX semantics directly
    on whatever host this suite happens to run on."""
    windows_style = "C:/definitely/not/inside/base_dir/pwned.txt"
    with pytest.raises(VeriFlowError) as exc_info:
        safe_join(tmp_path, windows_style)
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_windows_drive_pattern_detected_under_simulated_posix_is_absolute_semantics(monkeypatch):
    """Unit-level proof that _is_absolute_override() doesn't rely on the
    host OS's own PurePath.is_absolute() -- monkeypatch path_safety's
    PurePath reference to PurePosixPath (instantiable on any host, unlike
    concrete PosixPath) to reproduce exactly the semantics real Linux/
    macOS hosts have for this string, and confirm the regex fallback still
    flags it as an absolute-path override."""
    from pathlib import PurePosixPath

    from veriflow.core import path_safety

    monkeypatch.setattr(path_safety, "PurePath", PurePosixPath)

    windows_style = "C:/definitely/not/inside/base_dir/pwned.txt"
    assert PurePosixPath(windows_style).is_absolute() is False  # the CI-observed gap
    assert path_safety._is_absolute_override(windows_style) is True  # closed by the regex fallback


def test_safe_join_windows_drive_pattern_rejected_with_simulated_posix_is_absolute_semantics(
    tmp_path, monkeypatch
):
    """End-to-end version of the above: with PurePath forced to
    PurePosixPath (simulating the exact is_absolute() semantics a real
    Ubuntu/macOS CI runner has for a Windows-style drive-letter string),
    safe_join() must still reject the attack via the regex fallback --
    confirming the fix without needing to actually run on 3 different
    machines."""
    from pathlib import PurePosixPath

    from veriflow.core import path_safety

    monkeypatch.setattr(path_safety, "PurePath", PurePosixPath)

    windows_style = "C:/definitely/not/inside/base_dir/pwned.txt"
    with pytest.raises(VeriFlowError) as exc_info:
        safe_join(tmp_path, windows_style)
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_safe_join_symlink_escaping_base_dir_rejected(tmp_path):
    """A symlink created *inside* base_dir but pointing *outside* it must
    be caught too -- Path.resolve() follows symlinks by default, so the
    same containment check that catches ../ also catches this."""
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = base / "escape_link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment (e.g. Windows without Developer Mode)")

    with pytest.raises(VeriFlowError) as exc_info:
        safe_join(base, "escape_link/pwned.txt")
    assert exc_info.value.code == "VF_UNSAFE_PATH"


def test_safe_join_empty_name_resolves_to_base_dir_itself(tmp_path):
    result = safe_join(tmp_path, "")
    assert result == tmp_path.resolve()


def test_safe_join_error_details_include_name_and_base_dir(tmp_path):
    with pytest.raises(VeriFlowError) as exc_info:
        safe_join(tmp_path, "../escaped.txt")
    assert exc_info.value.details["name"] == "../escaped.txt"
    assert exc_info.value.details["base_dir"] == str(tmp_path.resolve())
