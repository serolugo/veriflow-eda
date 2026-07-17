"""`veriflow pdk` -- zero-configuration PDK management.

VeriFlow installs and tracks PDKs under `~/.veriflow/pdks/<technology>/`
(see `veriflow.models.pdk_manager`) so users never set PDK_ROOT / liberty
path environment variables by hand: `veriflow pdk install <name>` fetches
the PDK, and synthesis picks up the resulting liberty file automatically
(see `core.stages.synthesis.SynthesisStage`).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from rich import box
from rich.table import Table

from veriflow.core import VeriFlowError
from veriflow.models.pdk_manager import (
    VERIFLOW_PDK_ROOT,
    _create_pdk_link,
    build_volare_enable_command,
    get_liberty_path,
    get_pdk_path,
)
from veriflow.models.technology_profile import (
    TechnologyProfile,
    get_technology_profile,
    list_technology_profile_names,
)
from veriflow.ui.output import console, print_done, print_error, print_step, print_warn
from veriflow.ui.theme import BLUE, GREY, WHITE

_STATUS_STYLE = {
    "OK": "pass",
    "NOT INSTALLED": "fail",
    "INSTALLED, NO LIBERTY": "warn",
}


def _pdk_row(name: str) -> dict:
    technology = get_technology_profile(name)
    if technology.install_method is None:
        return {
            "name": name,
            "status": "OK",
            "liberty": None,
            "note": "no PDK required",
            "install_hint": None,
        }

    pdk_path = get_pdk_path(name)
    if pdk_path is None:
        return {
            "name": name,
            "status": "NOT INSTALLED",
            "liberty": None,
            "note": None,
            "install_hint": technology.install_hint or f"veriflow pdk install {name}",
        }

    liberty_path = get_liberty_path(name)
    if liberty_path is None:
        return {
            "name": name,
            "status": "INSTALLED, NO LIBERTY",
            "liberty": None,
            "note": None,
            "install_hint": technology.install_hint or f"veriflow pdk install {name}",
        }

    return {
        "name": name,
        "status": "OK",
        "liberty": str(liberty_path),
        "note": None,
        "install_hint": None,
    }


def _collect_rows() -> list[dict]:
    return [_pdk_row(name) for name in list_technology_profile_names()]


def _print_table(rows: list[dict], *, title: str) -> None:
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style=f"bold {BLUE}",
        border_style=GREY,
        padding=(0, 2),
    )
    table.add_column("PDK", style=WHITE)
    table.add_column("Status")
    table.add_column("Liberty", style=GREY)
    table.add_column("Install hint", style=GREY)

    for row in rows:
        style = _STATUS_STYLE.get(row["status"], "secondary")
        status_text = f"[{style}]\\[{row['status']}][/{style}]"
        liberty_col = row["liberty"] or row["note"] or ""
        table.add_row(row["name"], status_text, liberty_col, row["install_hint"] or "")

    console.print(f"\n  [label]{title}[/label]")
    console.print(table)
    console.print()


# ── pdk list / pdk status ──────────────────────────────────────────────────

def cmd_pdk_list(args: argparse.Namespace) -> tuple[int, dict]:
    rows = _collect_rows()
    _print_table(rows, title="PDKs")
    return 0, {"status": "SUCCESS", "command": "pdk list", "pdks": rows}


def cmd_pdk_status(args: argparse.Namespace) -> tuple[int, dict]:
    rows = _collect_rows()
    _print_table(rows, title="PDK status")
    console.print(f"  [secondary]PDK root:[/secondary] {VERIFLOW_PDK_ROOT}")
    for row in rows:
        if row["liberty"]:
            console.print(f"  [secondary]{row['name']}:[/secondary] {row['liberty']}")
    console.print()
    return 0, {
        "status": "SUCCESS",
        "command": "pdk status",
        "pdks": rows,
        "pdk_root": str(VERIFLOW_PDK_ROOT),
    }


# ── pdk install / pdk update ───────────────────────────────────────────────

def _volare_available() -> bool:
    return shutil.which("volare") is not None


def _git_available() -> bool:
    return shutil.which("git") is not None


def _warn_on_stderr(result: subprocess.CompletedProcess) -> None:
    """Surface stderr from a *successful* (returncode 0) subprocess call as
    a warning instead of silently discarding it.

    Success/failure is judged solely by returncode -- e.g. on Windows,
    volare emits a PermissionError from its own temp-file cleanup on
    stderr even when the install itself completed fine (returncode 0);
    treating any stderr output as an error would misreport that as a
    failure. Non-empty stderr on an otherwise-successful run is still
    useful information, so it's shown, just not as an error.
    """
    if result.stderr and result.stderr.strip():
        print_warn(result.stderr.strip())


def _ensure_pdk_subdir_link(technology: TechnologyProfile, pdk_root: Path, *, step_label: str = "pdk install") -> None:
    """After a successful `volare enable`, make sure pdk_root/<pdk_subdir>
    actually exists.

    volare's real on-disk layout (see `volare.common.get_volare_dir`/
    `get_versions_dir` and `volare.manage.enable` in the installed
    `volare` package) extracts each version under
    `pdk_root/volare/<volare_pdk>/versions/<version>/<variant>/` and then
    symlinks `pdk_root/<variant>` -> that directory for the "current"
    version. `pdk_subdir` (e.g. "sky130A") is one such variant. On Windows,
    creating that top-level symlink silently fails without
    SeCreateSymbolicLinkPrivilege or Developer Mode enabled -- `volare
    enable` still exits 0, but `pdk_root/<pdk_subdir>` never appears. When
    that happens, fall back to a junction point (works without admin rights
    on NTFS) pointing at the same already-extracted files.

    A no-op when `pdk_subdir` isn't set, or when the expected path already
    exists (the normal case everywhere except affected Windows setups, and
    also true on a re-run against an already-fixed-up install).
    """
    if not technology.pdk_subdir:
        return

    expected_link = pdk_root / technology.pdk_subdir
    if expected_link.exists():
        return  # volare created it fine, or a previous install already fixed it up

    versions_dir = pdk_root / "volare" / technology.volare_pdk / "versions"
    if technology.default_version:
        src = versions_dir / technology.default_version / technology.pdk_subdir
    else:
        # No pinned version -- volare resolved "latest" on its own, so the
        # exact version directory it extracted into isn't known upfront.
        # Discover it: there should be exactly one <pdk_subdir> under
        # pdk_root/volare/<volare_pdk>/versions/*/ right after a fresh install.
        candidates = sorted(versions_dir.glob(f"*/{technology.pdk_subdir}")) if versions_dir.is_dir() else []
        src = candidates[-1] if candidates else versions_dir / "unknown" / technology.pdk_subdir

    if not src.exists():
        raise VeriFlowError(
            f"volare did not extract PDK files for {technology.name!r} -- "
            f"expected directory not found: {src}\n"
            "  This usually means the PDK version wasn't fully downloaded/extracted. "
            f"Try 'veriflow pdk install {technology.name}' again.",
            code="VF_PDK_INSTALL_INCOMPLETE",
            details={"name": technology.name, "expected_src": str(src)},
        )

    print_step(step_label, f"Creating directory link {technology.pdk_subdir} (Windows fallback)...")
    _create_pdk_link(src, expected_link)


# WinError 1314 == ERROR_PRIVILEGE_NOT_HELD -- os.symlink()'s failure mode on
# Windows without SeCreateSymbolicLinkPrivilege/Developer Mode. The numeric
# code is stable across Windows locales; the accompanying message text is
# not (confirmed empirically: "[WinError 1314] El cliente no dispone de un
# privilegio requerido" on a Spanish-locale install), so this is the only
# reliable substring to match on.
_WINDOWS_SYMLINK_PRIVILEGE_ERROR = "WinError 1314"


def _recover_from_volare_symlink_failure(
    technology: TechnologyProfile, pdk_dir: Path, result: subprocess.CompletedProcess, *, step_label: str
) -> bool:
    """volare's CLI wrapper (`volare.__main__.enable_cmd`) catches *any*
    exception from `enable()` -- including the symlink OSError -- and exits
    non-zero. That means a Windows symlink-privilege failure surfaces as a
    hard `returncode != 0`, not the silent "exits 0, directory just missing"
    case `_ensure_pdk_subdir_link` otherwise handles. But volare's `enable()`
    runs `fetch()` (the actual download/extraction) *before* attempting the
    top-level symlink -- so the PDK files are already correctly on disk even
    when this exact failure happens.

    Note: volare prints this error via a plain `rich.console.Console()`,
    which defaults to *stdout*, not stderr (confirmed empirically) -- so
    both streams are checked here, not just stderr.

    Returns True if this was that specific failure and the junction-point
    fallback recovered it (caller should treat the install as successful,
    with a warning); False if this doesn't look like that failure at all
    (caller should raise the original error).
    """
    combined_output = (result.stderr or "") + (result.stdout or "")
    if _WINDOWS_SYMLINK_PRIVILEGE_ERROR not in combined_output:
        return False
    print_warn(
        f"volare could not create the {technology.pdk_subdir!r} symlink "
        "(Windows requires Developer Mode or admin rights for symlinks) "
        "-- falling back to a junction point instead."
    )
    _ensure_pdk_subdir_link(technology, pdk_dir, step_label=step_label)
    return True


def cmd_pdk_install(args: argparse.Namespace) -> int:
    name = args.pdk_name
    technology = get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN
    if technology.install_method is None:
        raise VeriFlowError(
            f"Technology {name!r} has no installable PDK.",
            code="VF_PDK_NOT_INSTALLABLE",
            details={"name": name},
        )

    if get_pdk_path(name) is not None:
        if get_liberty_path(name) is not None:
            console.print(
                f"\n  [secondary]{name} is already installed -- use[/secondary] "
                f"veriflow pdk update {name} [secondary]to update[/secondary]\n"
            )
            return 0
        # Directory exists but no liberty resolves ([INSTALLED, NO LIBERTY])
        # -- a prior install was interrupted or never finished. Don't treat
        # this as "already installed"; fall through and reinstall.
        print_step("pdk install", f"Incomplete installation detected, reinstalling {name}...")

    pdk_dir = VERIFLOW_PDK_ROOT / name

    if technology.install_method == "volare":
        if not _volare_available():
            print_error("volare required -- run: pip install veriflow-eda\\[pdks]")
            return 1
        cmd = build_volare_enable_command(technology, pdk_dir)
        print_step("pdk install", f"Installing {name} ({' '.join(cmd)}) ...")
        pdk_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if not _recover_from_volare_symlink_failure(technology, pdk_dir, result, step_label="pdk install"):
                raise VeriFlowError(
                    f"volare enable failed for {name}:\n{result.stderr or result.stdout}",
                    code="VF_PDK_INSTALL_FAILED",
                    details={"name": name, "stderr": result.stderr},
                )
        else:
            _warn_on_stderr(result)
            _ensure_pdk_subdir_link(technology, pdk_dir, step_label="pdk install")

    elif technology.install_method == "git":
        if not _git_available():
            print_error("git required -- install git and ensure it is in PATH")
            return 1
        print_step("pdk install", f"Cloning {technology.git_url} ...")
        result = subprocess.run(
            ["git", "clone", technology.git_url, str(pdk_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise VeriFlowError(
                f"git clone failed for {name}:\n{result.stderr or result.stdout}",
                code="VF_PDK_INSTALL_FAILED",
                details={"name": name, "stderr": result.stderr},
            )
        _warn_on_stderr(result)

    print_done(f"{name} installed  ·  [id]{pdk_dir}[/id]")
    return 0


def cmd_pdk_update(args: argparse.Namespace) -> int:
    name = args.pdk_name
    technology = get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN
    if technology.install_method is None:
        raise VeriFlowError(
            f"Technology {name!r} has no installable PDK.",
            code="VF_PDK_NOT_INSTALLABLE",
            details={"name": name},
        )

    pdk_dir = get_pdk_path(name)
    if pdk_dir is None:
        print_error(f"{name} is not installed -- run: veriflow pdk install {name}")
        return 1

    if technology.install_method == "volare":
        if not _volare_available():
            print_error("volare required -- run: pip install veriflow-eda\\[pdks]")
            return 1
        cmd = build_volare_enable_command(technology, pdk_dir)
        print_step("pdk update", f"Updating {name} ({' '.join(cmd)}) ...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if not _recover_from_volare_symlink_failure(technology, pdk_dir, result, step_label="pdk update"):
                raise VeriFlowError(
                    f"volare enable failed for {name}:\n{result.stderr or result.stdout}",
                    code="VF_PDK_UPDATE_FAILED",
                    details={"name": name, "stderr": result.stderr},
                )
        else:
            _warn_on_stderr(result)
            _ensure_pdk_subdir_link(technology, pdk_dir, step_label="pdk update")

    elif technology.install_method == "git":
        if not _git_available():
            print_error("git required -- install git and ensure it is in PATH")
            return 1
        print_step("pdk update", f"Pulling latest changes for {name} ...")
        result = subprocess.run(
            ["git", "-C", str(pdk_dir), "pull"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise VeriFlowError(
                f"git pull failed for {name}:\n{result.stderr or result.stdout}",
                code="VF_PDK_UPDATE_FAILED",
                details={"name": name, "stderr": result.stderr},
            )
        _warn_on_stderr(result)

    print_done(f"{name} updated  ·  [id]{pdk_dir}[/id]")
    return 0


# ── pdk versions ────────────────────────────────────────────────────────────

def cmd_pdk_versions(args: argparse.Namespace) -> tuple[int, dict]:
    """List remote versions available for a volare-installed PDK.

    Runs `volare ls-remote --pdk <volare_pdk>` under the hood, presented as
    plain "available versions" output -- the user never needs to know
    volare exists to read or act on it.
    """
    name = args.pdk_name
    technology = get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN
    if technology.install_method != "volare":
        raise VeriFlowError(
            f"{name!r} has no listable remote versions "
            f"(install_method={technology.install_method!r}; "
            "version listing is only available for volare-installed PDKs).",
            code="VF_PDK_VERSIONS_UNSUPPORTED",
            details={"name": name, "install_method": technology.install_method},
        )
    if not _volare_available():
        print_error("volare required -- run: pip install veriflow-eda\\[pdks]")
        return 1, {"status": "ERROR", "command": "pdk versions", "pdk": name, "versions": []}

    result = subprocess.run(
        ["volare", "ls-remote", "--pdk", technology.volare_pdk],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise VeriFlowError(
            f"Listing versions failed for {name}:\n{result.stderr or result.stdout}",
            code="VF_PDK_VERSIONS_FAILED",
            details={"name": name, "stderr": result.stderr},
        )

    versions = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

    console.print(f"\n  [label]Available versions -- {name}[/label]\n")
    if versions:
        for version in versions:
            console.print(f"  {version}")
    else:
        console.print("  [secondary](no versions returned)[/secondary]")
    console.print()

    return 0, {"status": "SUCCESS", "command": "pdk versions", "pdk": name, "versions": versions}
