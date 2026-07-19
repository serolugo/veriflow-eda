from __future__ import annotations

import shutil
import subprocess


def _check_tool(tool: str, version_flag: str = "-V") -> dict:
    """Check a single EDA tool: find in PATH, run version_flag, return status dict.

    Invokes *path* (shutil.which's own resolved result), not the bare
    *tool* name -- on Windows, some EDA suites (Vivado's xvlog/xelab/xsim
    among them) install a same-named extensionless file alongside a
    "<tool>.bat" launcher; shutil.which already does the PATHEXT-aware
    search needed to find the right one (returning ".../xvlog.BAT"), but
    subprocess.run(["xvlog", ...]) with shell=False re-resolves the bare
    name itself via CreateProcess, which does NOT apply PATHEXT the way
    shutil.which/cmd.exe do -- it can launch a bare-named ".exe" directly
    (a Windows loader special case) but not a ".bat"/".cmd", so passing
    the bare name fails with FileNotFoundError ([WinError 2]) even though
    the tool is genuinely installed and shutil.which just found it.
    Confirmed against a real Vivado 2024.1 install. Using shutil.which's
    own resolved path sidesteps the whole issue on every platform (a
    no-op on Linux/macOS, where there's no extension ambiguity to begin
    with)."""
    path = shutil.which(tool)
    if path is None:
        return {
            "tool": tool,
            "available": False,
            "version": None,
            "path": None,
            "error": f"{tool!r} not found in PATH",
        }
    try:
        proc = subprocess.run(
            [path, version_flag],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # iverilog writes to stderr; yosys writes to stdout — try stdout first
        output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        version = output.splitlines()[0] if output else None
        return {
            "tool": tool,
            "available": True,
            "version": version,
            "path": path,
            "error": None,
        }
    except Exception as exc:
        return {
            "tool": tool,
            "available": False,
            "version": None,
            "path": path,
            "error": str(exc),
        }
