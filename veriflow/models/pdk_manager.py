"""PDK directory management for `veriflow pdk` (zero-configuration PDK
installs -- no manual PDK_ROOT / liberty path environment variables).

VeriFlow keeps installed PDKs under `~/.veriflow/pdks/<technology_name>/`,
one subdirectory per technology (matching the `name:` field in
`veriflow/technologies/<name>.yaml`, not necessarily the PDK's own name).
`get_liberty_path` resolves the actual `.lib` file inside that directory
using the technology profile's `pdk_subdir`/`liberty_glob` fields.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from veriflow.models.technology_profile import TechnologyProfile, get_technology_profile

VERIFLOW_PDK_ROOT = Path.home() / ".veriflow" / "pdks"


def get_pdk_path(pdk_name: str) -> Path | None:
    """Return VERIFLOW_PDK_ROOT/<pdk_name> if it exists, else None."""
    path = VERIFLOW_PDK_ROOT / pdk_name
    return path if path.is_dir() else None


def get_liberty_path(pdk_name: str) -> Path | None:
    """Resolve the installed liberty (.lib) file for *pdk_name*, or None.

    Returns None when the PDK directory doesn't exist, the technology
    profile declares no `liberty_glob`, or the glob matches nothing. Raises
    VF_TECHNOLOGY_UNKNOWN (via get_technology_profile) if *pdk_name* isn't a
    registered technology.
    """
    technology = get_technology_profile(pdk_name)
    if not technology.liberty_glob:
        return None
    pdk_path = get_pdk_path(pdk_name)
    if pdk_path is None:
        return None
    search_root = (pdk_path / technology.pdk_subdir) if technology.pdk_subdir else pdk_path
    if not search_root.is_dir():
        return None
    matches = sorted(search_root.glob(technology.liberty_glob))
    return matches[0] if matches else None


def get_installed_pdk_version(pdk_name: str) -> str | None:
    """Return the currently-active installed version/commit hash for
    *pdk_name*, or None if it can't be determined (not installed, unknown
    technology, tool unavailable, etc.).

    volare-installed technologies (sky130/gf180): resolves
    `pdk_root/<pdk_subdir>` (a symlink, or -- on Windows without Developer
    Mode -- a junction point created by `_create_pdk_link`'s fallback) to
    its real target under `pdk_root/volare/<volare_pdk>/versions/<hash>/`
    and extracts `<hash>`. Deliberately does NOT read volare's own
    `<volare_dir>/current` bookkeeping file: `volare.manage.enable()` only
    writes that file *after* the symlink-creation step succeeds, so on a
    machine where that step failed and VeriFlow's junction-point fallback
    had to run, `current` is never written at all -- confirmed empirically
    on a real Windows install fixed by that exact fallback. Resolving the
    directory link itself works regardless of which mechanism created it.

    git-installed technologies (ihp130): `git -C <pdk_path> rev-parse
    --short HEAD`.

    Returns the full resolved value (a full 40-char hash for volare;
    git's own short hash, already short, for git) -- callers that need a
    shorter display string (e.g. `pdk list`'s table) truncate it
    themselves.
    """
    technology = get_technology_profile(pdk_name)  # raises VF_TECHNOLOGY_UNKNOWN
    pdk_path = get_pdk_path(pdk_name)
    if pdk_path is None:
        return None

    if technology.install_method == "volare":
        if not technology.pdk_subdir or not technology.volare_pdk:
            return None
        link = pdk_path / technology.pdk_subdir
        if not link.exists():
            return None
        versions_dir = pdk_path / "volare" / technology.volare_pdk / "versions"
        try:
            relative = link.resolve().relative_to(versions_dir.resolve())
        except (OSError, ValueError):
            return None
        return relative.parts[0] if relative.parts else None

    if technology.install_method == "git":
        try:
            result = subprocess.run(
                ["git", "-C", str(pdk_path), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        version = (result.stdout or "").strip()
        return version or None

    return None


def build_volare_enable_command(technology: TechnologyProfile, pdk_dir: Path) -> list[str]:
    """Build the `volare enable` argv for installing/updating *technology*
    into *pdk_dir*.

    When `technology.default_version` is set (a pinned commit hash from
    `technologies/<name>.yaml`), it's passed as a positional argument right
    after `--pdk <volare_pdk>`:

        volare enable --pdk <volare_pdk> <default_version> --pdk-root <pdk_dir>

    When absent, the command is unchanged from before this field existed --
    volare resolves whatever it considers "latest" on its own:

        volare enable --pdk <volare_pdk> --pdk-root <pdk_dir>
    """
    cmd = ["volare", "enable", "--pdk", technology.volare_pdk]
    if technology.default_version:
        cmd.append(technology.default_version)
    cmd += ["--pdk-root", str(pdk_dir)]
    return cmd


def _create_pdk_link(src: Path, dst: Path) -> None:
    """Create a symlink from dst -> src.

    On Windows, falls back to a junction point if symlink creation fails
    (requires SeCreateSymbolicLinkPrivilege or Developer Mode). Junction
    points work without admin rights on NTFS volumes.

    Raises OSError if both attempts fail.
    """
    try:
        dst.symlink_to(src)
    except OSError:
        if sys.platform == "win32":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise OSError(
                    f"Failed to create junction point {dst} -> {src}: "
                    f"{result.stderr}"
                )
        else:
            raise  # Linux/macOS: symlink should always work
