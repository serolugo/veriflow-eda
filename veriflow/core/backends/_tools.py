from __future__ import annotations

import shutil
import subprocess


def _check_tool(tool: str, version_flag: str = "-V") -> dict:
    """Check a single EDA tool: find in PATH, run version_flag, return status dict."""
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
            [tool, version_flag],
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
