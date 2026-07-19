from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from veriflow.core import VeriFlowError

_SUPPORTED_CLIENTS = ("claude-code", "claude-desktop")


def cmd_mcp_serve(args: argparse.Namespace) -> int:
    """Implement `veriflow mcp serve`: start the MCP server over stdio.

    Blocking -- meant to be launched by an MCP client (Claude Code, Claude
    Desktop), not run directly by a human in a terminal."""
    from veriflow.mcp_server import main as serve

    serve()
    return 0


def _claude_desktop_config_path() -> Path:
    """Per-OS location of Claude Desktop's config file.

    Windows: %APPDATA%\\Claude\\claude_desktop_config.json
    macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json

    Raises VeriFlowError(VF_MCP_UNSUPPORTED_PLATFORM) on any other platform
    (e.g. Linux) -- Claude Desktop has no documented config location there
    as of this writing.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise VeriFlowError(
                "%APPDATA% is not set -- cannot locate Claude Desktop's config directory.",
                code="VF_MCP_APPDATA_NOT_SET",
            )
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    raise VeriFlowError(
        f"Unsupported platform for --client claude-desktop: {sys.platform!r}. "
        "Claude Desktop's config file location is only known for Windows and macOS.",
        code="VF_MCP_UNSUPPORTED_PLATFORM",
        details={"platform": sys.platform},
    )


def _install_claude_desktop(config_path: Path | None = None) -> dict:
    """Add/update VeriFlow's entry in Claude Desktop's mcpServers config,
    preserving every other entry already there. Creates the file (and its
    parent directory) with the minimal structure if it doesn't exist yet.

    *config_path* is exposed as a parameter purely so tests can point this
    at a temp file instead of the real per-OS location -- cmd_mcp_install
    never passes it explicitly.
    """
    resolved = config_path if config_path is not None else _claude_desktop_config_path()

    if resolved.exists():
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise VeriFlowError(
                f"{resolved} exists but is not valid JSON:\n  {exc}",
                code="VF_MCP_CONFIG_YAML_ERROR",
                details={"path": str(resolved)},
            ) from exc
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers["veriflow"] = {"command": "veriflow", "args": ["mcp", "serve"]}
    data["mcpServers"] = servers

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {"status": "SUCCESS", "client": "claude-desktop", "config_path": str(resolved)}


def _install_claude_code() -> dict:
    """Register veriflow with the `claude` CLI's own MCP config
    (`claude mcp add <name> -- <command> [args...]`, the real flag shape --
    not `--command`, which claude mcp add does not accept). Runs it via
    subprocess if `claude` is on PATH; otherwise prints the exact command
    for the user to run themselves."""
    claude_bin = shutil.which("claude")
    command_parts = ["claude", "mcp", "add", "veriflow", "--", "veriflow", "mcp", "serve"]

    if claude_bin is None:
        print("The 'claude' CLI was not found in PATH. Run this command yourself:")
        print("  " + " ".join(command_parts))
        return {"status": "MANUAL", "client": "claude-code", "command": command_parts}

    result = subprocess.run(command_parts, capture_output=True, text=True)
    if result.returncode != 0:
        raise VeriFlowError(
            f"'claude mcp add' failed:\n  {result.stderr.strip()}",
            code="VF_MCP_CLAUDE_CODE_ADD_FAILED",
            details={"stderr": result.stderr, "returncode": result.returncode},
        )
    return {"status": "SUCCESS", "client": "claude-code", "stdout": result.stdout.strip()}


def cmd_mcp_install(args: argparse.Namespace) -> tuple[int, dict]:
    """Implement `veriflow mcp install --client <claude-code|claude-desktop>`."""
    client = args.client
    if client not in _SUPPORTED_CLIENTS:
        raise VeriFlowError(
            f"Unknown --client {client!r}. Supported clients: {', '.join(_SUPPORTED_CLIENTS)}.",
            code="VF_MCP_UNKNOWN_CLIENT",
            details={"client": client, "supported": list(_SUPPORTED_CLIENTS)},
        )
    if client == "claude-code":
        result = _install_claude_code()
    else:
        result = _install_claude_desktop()
    return 0, result
