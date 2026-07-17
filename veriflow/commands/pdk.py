"""`veriflow pdk` -- zero-configuration PDK management.

VeriFlow installs and tracks PDKs under `~/.veriflow/pdks/<technology>/`
(see `veriflow.models.pdk_manager`) so users never set PDK_ROOT / liberty
path environment variables by hand: `veriflow pdk install <name>` fetches
the PDK, and synthesis picks up the resulting liberty file automatically
(see `core.stages.synthesis.SynthesisStage`).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from veriflow.core import VeriFlowError
from veriflow.models.pdk_manager import (
    VERIFLOW_PDK_ROOT,
    _create_pdk_link,
    build_volare_enable_command,
    get_installed_pdk_version,
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


def _short_version(version: str | None) -> str | None:
    """Truncate a resolved version/commit hash to 8 chars for table display
    (results.json / API callers use the untruncated `get_installed_pdk_version`
    return value directly -- this is display-only)."""
    if not version:
        return None
    return version[:8]


def _pdk_row(name: str) -> dict:
    technology = get_technology_profile(name)
    if technology.install_method is None:
        return {
            "name": name,
            "status": "OK",
            "liberty": None,
            "version": None,
            "note": "no PDK required",
            "action": None,
        }

    pdk_path = get_pdk_path(name)
    if pdk_path is None:
        return {
            "name": name,
            "status": "NOT INSTALLED",
            "liberty": None,
            "version": None,
            "note": None,
            # Short form (no "veriflow " prefix) to avoid wrapping the
            # Action column on narrow terminals -- unlike the API's
            # install_hint field (see api.py), the table is always shown
            # under a "veriflow pdk list" header, so the program name is
            # already implied by context.
            "action": f"pdk install {name}",
        }

    liberty_path = get_liberty_path(name)
    if liberty_path is None:
        return {
            "name": name,
            "status": "INSTALLED, NO LIBERTY",
            "liberty": None,
            "version": None,
            "note": None,
            "action": f"pdk install {name}",  # short form -- see note above
        }

    return {
        "name": name,
        "status": "OK",
        "liberty": str(liberty_path),
        "version": _short_version(get_installed_pdk_version(name)),
        "note": None,
        "action": f"pdk update {name}",
    }


def _collect_rows() -> list[dict]:
    return [_pdk_row(name) for name in list_technology_profile_names()]


def _abbreviate_home(path_str: str) -> str:
    """Replace a leading `Path.home()` prefix with `~`, display-only (the
    row dict itself keeps the full path -- e.g. for `--json` consumers and
    `pdk path`'s scripting use case, where a literal `~` is meaningless
    without shell expansion)."""
    home = str(Path.home())
    if path_str == home:
        return "~"
    if path_str.startswith(home + os.sep):
        return "~" + path_str[len(home):]
    return path_str


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
    table.add_column("Version", style=GREY)
    table.add_column("Liberty", style=GREY)
    table.add_column("Action", style=GREY)

    for row in rows:
        style = _STATUS_STYLE.get(row["status"], "secondary")
        status_text = f"[{style}]\\[{row['status']}][/{style}]"
        liberty_col = _abbreviate_home(row["liberty"]) if row["liberty"] else (row["note"] or "")
        table.add_row(row["name"], status_text, row["version"] or "", liberty_col, row["action"] or "")

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


def cmd_pdk_path(args: argparse.Namespace) -> int:
    """Print an installed PDK's root directory path to stdout, plain --
    no Rich styling, no surrounding text -- so it composes directly in
    shell scripts (`cd $(veriflow pdk path sky130)`), the same convention
    as `which`/`git --exec-path`. Errors go to stderr with exit 1, also
    plain, for the same reason.

    Prints the directory even when [INSTALLED, NO LIBERTY] (no liberty
    glob match) -- get_pdk_path only checks the directory exists, not
    that a liberty file resolves inside it -- useful for diagnosing an
    incomplete install.
    """
    name = args.pdk_name
    get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN

    pdk_path = get_pdk_path(name)
    if pdk_path is None:
        print(f"{name} is not installed -- run: veriflow pdk install {name}", file=sys.stderr)
        return 1

    print(pdk_path)
    return 0


# ── pdk install / pdk update ───────────────────────────────────────────────

def _volare_available() -> bool:
    return shutil.which("volare") is not None


def _git_available() -> bool:
    return shutil.which("git") is not None


def _run_subprocess_with_spinner(
    cmd: list[str], message: str, *, non_interactive: bool
) -> subprocess.CompletedProcess:
    """Run *cmd* to completion, showing an animated spinner with *message*
    while it's in flight.

    volare/git operations for large PDKs (sky130 in particular: several GB,
    multiple minutes) otherwise print nothing between the initial
    `print_step` line and the final result -- indistinguishable from a
    hang. The subprocess runs on a worker thread so this thread is free to
    stay inside Rich's `Progress` context (which owns the spinner's own
    redraw loop) until the worker finishes; joining with a short timeout in
    a loop -- rather than a single blocking `thread.join()` -- keeps this
    responsive to Ctrl+C.

    Suppressed entirely under `--non-interactive` (plain `subprocess.run`,
    no spinner) so CI log parsing never has to deal with Rich's
    cursor-control escape sequences.
    """
    if non_interactive:
        return subprocess.run(cmd, capture_output=True, text=True)

    outcome: dict[str, object] = {}

    def _target() -> None:
        try:
            outcome["result"] = subprocess.run(cmd, capture_output=True, text=True)
        except BaseException as exc:  # re-raised on the main thread below
            outcome["error"] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(message, total=None)
        while worker.is_alive():
            worker.join(timeout=0.1)

    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome["result"]  # type: ignore[return-value]


def _checkout_git_version(name: str, pdk_dir: Path, version: str, *, step_label: str, error_code: str) -> None:
    """Check out a specific commit/ref in a git-installed PDK (ihp130)."""
    print_step(step_label, f"Checking out {version} for {name} ...")
    result = subprocess.run(
        ["git", "-C", str(pdk_dir), "checkout", version],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise VeriFlowError(
            f"git checkout {version} failed for {name}:\n{result.stderr or result.stdout}",
            code=error_code,
            details={"name": name, "version": version, "stderr": result.stderr},
        )


# Anchored end-to-end: the block must run from "Exception ignored in:
# <finalize object" all the way to the PermissionError line with nothing
# else trailing. Non-greedy .*? plus \Z (absolute end of string) means a
# real error appended *after* the traceback breaks the match entirely --
# `_is_volare_cleanup_noise` isn't fooled by trailing content the way a
# plain substring-containment check would be.
_CLEANUP_BLOCK_FULL_RE = re.compile(
    r"\AException ignored in: <finalize object.*?"
    r"PermissionError: \[WinError 32\][^\n]*\Z",
    re.DOTALL,
)

# Same shape, but *not* anchored to the whole string -- used to locate each
# candidate block's span anywhere within a larger, possibly-mixed stderr
# capture (non-greedy, so it stops at the nearest PermissionError line
# rather than swallowing everything up to the last one).
_CLEANUP_BLOCK_SPAN_RE = re.compile(
    r"Exception ignored in: <finalize object.*?"
    r"PermissionError: \[WinError 32\][^\n]*\n?",
    re.DOTALL,
)


def _is_volare_cleanup_noise(text: str) -> bool:
    """True if *text* is entirely volare's known Windows temp-file cleanup
    noise, or just whitespace.

    On Windows, a `tempfile.py` finalizer sometimes fails to delete a
    `*.tar.zst` archive under a `*.volare` temp directory because the
    process handle hasn't released the file yet -- CPython prints this as
    an "Exception ignored in: <finalize object ...>" traceback during
    garbage collection. The install has already completed successfully by
    the time this fires; it's harmless noise, not an install error.

    Requires the *entire* (stripped) text to be exactly one such block --
    trailing content after the traceback (a real error appended after it)
    fails the match -- plus the `.volare`/`.tar.zst` markers, so an
    unrelated PermissionError (same WinError code, different file) is
    never misclassified as this specific, known-harmless case.
    """
    stripped = text.strip()
    if not stripped:
        return True
    if not _CLEANUP_BLOCK_FULL_RE.match(stripped):
        return False
    return ".volare" in stripped and ".tar.zst" in stripped and "tempfile.py" in stripped


def _filter_volare_cleanup_noise(stderr: str) -> str:
    """Strip volare's temp-file cleanup tracebacks out of *stderr*, leaving
    any real error content untouched -- even when the two are mixed in the
    same capture, in either order (each "Exception ignored in: <finalize
    object ...>" ... PermissionError span is located independently and
    only removed if `_is_volare_cleanup_noise` confirms that exact span is
    the known-harmless case; everything else -- including an unrelated
    finalizer exception -- is left in place).
    """
    if not stderr:
        return ""

    def _strip_if_noise(match: re.Match) -> str:
        return "" if _is_volare_cleanup_noise(match.group(0)) else match.group(0)

    filtered = _CLEANUP_BLOCK_SPAN_RE.sub(_strip_if_noise, stderr)
    return filtered.strip()


def _warn_on_stderr(result: subprocess.CompletedProcess) -> None:
    """Surface stderr from a *successful* (returncode 0) subprocess call as
    a warning instead of silently discarding it.

    Success/failure is judged solely by returncode -- e.g. on Windows,
    volare emits a PermissionError from its own temp-file cleanup on
    stderr even when the install itself completed fine (returncode 0);
    treating any stderr output as an error would misreport that as a
    failure. That specific cleanup traceback is filtered out entirely
    (see `_filter_volare_cleanup_noise`) since it's pure noise; any other
    non-empty stderr on an otherwise-successful run is still shown, just
    not as an error.
    """
    filtered = _filter_volare_cleanup_noise(result.stderr or "")
    if filtered:
        print_warn(filtered)


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


def _is_volare_tarball_cleanup_failure(combined_output: str) -> bool:
    """True if *combined_output* looks like `volare.manage.fetch()` failing
    to delete a downloaded tarball from its temp directory.

    Read from the installed `volare` package's source (`manage.py`):
    `fetch()` downloads and extracts every requested library sequentially
    inside a `try:` block, then deletes each downloaded `*.tar.zst` in a
    `finally:` block via a bare `os.unlink(path)` that only catches
    `FileNotFoundError` -- *not* `PermissionError`. On Windows, a
    just-downloaded multi-hundred-MB archive can still be locked (e.g. by
    antivirus scanning it) when that unlink runs -- far more likely for a
    PDK with many large libraries (sky130's several `.tar.zst` downloads,
    ~3 GB total) than one with few/small ones (gf180). This is a genuine,
    in-band `PermissionError` (not a `weakref.finalize` GC-cleanup
    traceback -- contrast `_is_volare_cleanup_noise`), so it has no
    "Exception ignored in: <finalize object" header at all; it's just
    `str(exc)` printed as `[red]{e}` by `enable_cmd`'s `except Exception`
    handler, via the same plain stdout-defaulting `Console()` documented in
    `_recover_from_volare_symlink_failure`. Note `str(exc)` does *not*
    include the "PermissionError" class-name prefix (that only appears in
    a formatted traceback) -- just "[WinError 32] <OS message>" -- so, like
    `_WINDOWS_SYMLINK_PRIVILEGE_ERROR`, the WinError code is the only
    reliable, locale-independent substring to match on.
    """
    return (
        "WinError 32" in combined_output
        and ".volare" in combined_output
        and ".tar.zst" in combined_output
    )


def _recover_from_volare_tarball_cleanup_failure(
    technology: TechnologyProfile, pdk_dir: Path, result: subprocess.CompletedProcess, *, step_label: str
) -> bool:
    """Recover from the tarball-cleanup `PermissionError` `_is_volare_tarball_cleanup_failure`
    detects. `fetch()` extracts PDK files in its `try:` block and only
    fails during the *cleanup* of the downloaded archive afterwards, so by
    the time this failure happens the PDK library files are already fully
    extracted on disk -- only volare's own temp-file housekeeping failed.
    Since the exception aborts `enable()` before it reaches its
    symlink-creation step (same as the WinError-1314 case
    `_recover_from_volare_symlink_failure` handles), `pdk_root/<pdk_subdir>`
    still needs to be created here.

    Returns True if this was that specific failure and recovery succeeded
    (caller should treat the install as successful, with a warning); False
    otherwise (caller should raise the original error).
    """
    combined_output = (result.stderr or "") + (result.stdout or "")
    if not _is_volare_tarball_cleanup_failure(combined_output):
        return False
    print_warn(
        f"volare could not delete a temporary download archive for {technology.name} "
        "(still locked, e.g. by antivirus scanning it) -- the PDK files were "
        "already extracted successfully; continuing."
    )
    _ensure_pdk_subdir_link(technology, pdk_dir, step_label=step_label)
    return True


def cmd_pdk_install(args: argparse.Namespace) -> int:
    name = args.pdk_name
    requested_version: str | None = getattr(args, "version", None)
    technology = get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN
    if technology.install_method is None:
        raise VeriFlowError(
            f"Technology {name!r} has no installable PDK.",
            code="VF_PDK_NOT_INSTALLABLE",
            details={"name": name},
        )
    if requested_version:
        # Overrides technologies/<name>.yaml's pinned default_version for
        # this run only -- build_volare_enable_command and
        # _ensure_pdk_subdir_link both key off technology.default_version,
        # so this one substitution makes --version flow through unchanged.
        technology = replace(technology, default_version=requested_version)

    if get_pdk_path(name) is not None:
        if get_liberty_path(name) is not None:
            current_version = get_installed_pdk_version(name)
            if requested_version and current_version and requested_version != current_version:
                console.print(
                    f"\n  [secondary]{name} is installed at version[/secondary] "
                    f"[id]{current_version}[/id]\n"
                    f"  [secondary]Use[/secondary] --version {requested_version} "
                    "[secondary]to install a different version "
                    "(will replace current installation).[/secondary]\n"
                )
                # falls through -- proceeds to (re)install requested_version
            else:
                already_msg = f"{name} is already installed"
                if current_version:
                    already_msg += f" at version {current_version}"
                console.print(
                    f"\n  [secondary]{already_msg} -- use[/secondary] "
                    f"veriflow pdk update {name} [secondary]to update[/secondary]\n"
                )
                return 0
        else:
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
        non_interactive = getattr(args, "non_interactive", False)
        result = _run_subprocess_with_spinner(
            cmd,
            f"Installing {name} via volare... (this may take several minutes)",
            non_interactive=non_interactive,
        )
        if result.returncode != 0:
            recovered = _recover_from_volare_symlink_failure(
                technology, pdk_dir, result, step_label="pdk install"
            ) or _recover_from_volare_tarball_cleanup_failure(technology, pdk_dir, result, step_label="pdk install")
            if not recovered:
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
        non_interactive = getattr(args, "non_interactive", False)
        result = _run_subprocess_with_spinner(
            ["git", "clone", technology.git_url, str(pdk_dir)],
            f"Cloning {name} via git... (this may take a few minutes)",
            non_interactive=non_interactive,
        )
        if result.returncode != 0:
            raise VeriFlowError(
                f"git clone failed for {name}:\n{result.stderr or result.stdout}",
                code="VF_PDK_INSTALL_FAILED",
                details={"name": name, "stderr": result.stderr},
            )
        _warn_on_stderr(result)
        if requested_version:
            _checkout_git_version(
                name, pdk_dir, requested_version, step_label="pdk install", error_code="VF_PDK_INSTALL_FAILED"
            )

    print_done(f"{name} installed  ·  [id]{pdk_dir}[/id]")
    return 0


def cmd_pdk_update(args: argparse.Namespace) -> int:
    name = args.pdk_name
    requested_version: str | None = getattr(args, "version", None)
    technology = get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN
    if technology.install_method is None:
        raise VeriFlowError(
            f"Technology {name!r} has no installable PDK.",
            code="VF_PDK_NOT_INSTALLABLE",
            details={"name": name},
        )
    if requested_version:
        technology = replace(technology, default_version=requested_version)

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
        non_interactive = getattr(args, "non_interactive", False)
        result = _run_subprocess_with_spinner(
            cmd,
            f"Updating {name} via volare... (this may take several minutes)",
            non_interactive=non_interactive,
        )
        if result.returncode != 0:
            recovered = _recover_from_volare_symlink_failure(
                technology, pdk_dir, result, step_label="pdk update"
            ) or _recover_from_volare_tarball_cleanup_failure(technology, pdk_dir, result, step_label="pdk update")
            if not recovered:
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
        non_interactive = getattr(args, "non_interactive", False)
        if requested_version:
            print_step("pdk update", f"Fetching latest refs for {name} ...")
            fetch_result = _run_subprocess_with_spinner(
                ["git", "-C", str(pdk_dir), "fetch"],
                f"Fetching latest refs for {name} via git...",
                non_interactive=non_interactive,
            )
            if fetch_result.returncode != 0:
                raise VeriFlowError(
                    f"git fetch failed for {name}:\n{fetch_result.stderr or fetch_result.stdout}",
                    code="VF_PDK_UPDATE_FAILED",
                    details={"name": name, "stderr": fetch_result.stderr},
                )
            _warn_on_stderr(fetch_result)
            _checkout_git_version(
                name, pdk_dir, requested_version, step_label="pdk update", error_code="VF_PDK_UPDATE_FAILED"
            )
        else:
            print_step("pdk update", f"Pulling latest changes for {name} ...")
            result = _run_subprocess_with_spinner(
                ["git", "-C", str(pdk_dir), "pull"],
                f"Pulling latest changes for {name} via git... (this may take a few minutes)",
                non_interactive=non_interactive,
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


# ── pdk remove ────────────────────────────────────────────────────────────────

def _dir_size_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _format_size(num_bytes: int) -> str:
    size_mb = num_bytes / (1024 * 1024)
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB"
    return f"{size_mb:.1f} MB"


def cmd_pdk_remove(args: argparse.Namespace) -> int:
    """Remove an installed PDK's directory entirely.

    No interactive confirmation prompt -- consistent with the rest of
    `veriflow pdk` (install/update also proceed unprompted) and
    `--non-interactive`-friendly. Use --dry-run first to see what would be
    removed and how much space it would free without touching anything.
    """
    name = args.pdk_name
    dry_run: bool = getattr(args, "dry_run", False)
    get_technology_profile(name)  # raises VF_TECHNOLOGY_UNKNOWN

    pdk_path = get_pdk_path(name)
    if pdk_path is None:
        print_error(f"{name} is not installed -- nothing to remove")
        return 1

    size_str = _format_size(_dir_size_bytes(pdk_path))

    if dry_run:
        console.print(
            f"\n  [secondary]Would remove[/secondary]  [id]{pdk_path}[/id]"
            f"  [secondary]({size_str})[/secondary]\n"
        )
        return 0

    print_step("pdk remove", f"Removing {name} ({size_str}) at {pdk_path} ...")
    shutil.rmtree(pdk_path, onerror=_force_remove_readonly)
    print_done(f"{name} removed  ·  [id]{pdk_path}[/id]")
    return 0


def _force_remove_readonly(func, path, _exc_info) -> None:
    """`shutil.rmtree` onerror handler: clear the read-only attribute and
    retry the failed operation.

    git marks files under `.git/objects/pack/` (and sometimes others)
    read-only on Windows -- plain `shutil.rmtree` cannot delete them and
    raises `PermissionError: [WinError 5] Access is denied`. Confirmed by
    actually running `pdk remove` against a real git-installed PDK
    (ihp130) on this machine before this handler was added.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


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
