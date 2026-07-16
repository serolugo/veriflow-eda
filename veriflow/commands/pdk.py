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

from rich import box
from rich.table import Table

from veriflow.core import VeriFlowError
from veriflow.models.pdk_manager import VERIFLOW_PDK_ROOT, get_liberty_path, get_pdk_path
from veriflow.models.technology_profile import get_technology_profile, list_technology_profile_names
from veriflow.ui.output import console, print_done, print_error, print_step
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
        console.print(
            f"\n  [secondary]{name} is already installed -- use[/secondary] "
            f"veriflow pdk update {name} [secondary]to update[/secondary]\n"
        )
        return 0

    pdk_dir = VERIFLOW_PDK_ROOT / name

    if technology.install_method == "volare":
        if not _volare_available():
            print_error("volare required -- run: pip install veriflow-eda\\[pdks]")
            return 1
        print_step("pdk install", f"Installing {name} (volare enable --pdk {technology.volare_pdk}) ...")
        pdk_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["volare", "enable", "--pdk", technology.volare_pdk, "--pdk-root", str(pdk_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise VeriFlowError(
                f"volare enable failed for {name}:\n{result.stderr or result.stdout}",
                code="VF_PDK_INSTALL_FAILED",
                details={"name": name, "stderr": result.stderr},
            )

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
        print_step("pdk update", f"Updating {name} (volare enable --pdk {technology.volare_pdk}) ...")
        result = subprocess.run(
            ["volare", "enable", "--pdk", technology.volare_pdk, "--pdk-root", str(pdk_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise VeriFlowError(
                f"volare enable failed for {name}:\n{result.stderr or result.stdout}",
                code="VF_PDK_UPDATE_FAILED",
                details={"name": name, "stderr": result.stderr},
            )

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

    print_done(f"{name} updated  ·  [id]{pdk_dir}[/id]")
    return 0
