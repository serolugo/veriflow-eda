"""Tests for veriflow.mcp_server's behavior when the optional `fastmcp`
dependency (setup.py's `mcp` extra) is NOT installed.

Deliberately does *not* `pytest.importorskip("fastmcp")` -- unlike
test_mcp_server.py (which requires a real fastmcp to exercise the tools
end-to-end and skips entirely without one), this file's whole point is to
exercise the no-fastmcp fallback path itself, so it must run regardless of
whether fastmcp happens to be installed in the current environment. Absence
is simulated via `sys.modules["fastmcp"] = None` (the standard way to make
`import fastmcp` raise ImportError without needing an actually-uninstalled
package -- see https://docs.python.org/3/reference/import.html#the-module-cache)
combined with a forced re-import of veriflow.mcp_server, mirroring the real
CI environment where `pip install -e .[dev]` (no `mcp` extra) never
installs fastmcp at all.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from veriflow.core import VeriFlowError

_MODULE_NAME = "veriflow.mcp_server"


def _reload_mcp_server_without_fastmcp(monkeypatch):
    """Force a fresh import of veriflow.mcp_server with `import fastmcp`
    raising ImportError. Both patches are made via `monkeypatch`, so
    whatever was in `sys.modules` for "fastmcp" and "veriflow.mcp_server"
    before this test (a real, fastmcp-backed module, if fastmcp happens to
    be installed here) is transparently restored after -- later tests
    (e.g. test_mcp_server.py, if collected in the same session) never see
    the stubbed-out version.
    """
    monkeypatch.setitem(sys.modules, "fastmcp", None)
    monkeypatch.delitem(sys.modules, _MODULE_NAME, raising=False)
    return importlib.import_module(_MODULE_NAME)


def test_import_without_fastmcp_does_not_crash(monkeypatch):
    module = _reload_mcp_server_without_fastmcp(monkeypatch)
    assert module.FASTMCP_AVAILABLE is False


def test_mcp_stub_object_used_when_fastmcp_absent(monkeypatch):
    module = _reload_mcp_server_without_fastmcp(monkeypatch)
    assert isinstance(module.mcp, module._StubMCP)


def test_tool_functions_remain_plain_callables_without_fastmcp(monkeypatch):
    """@mcp.tool becomes a no-op decorator via _StubMCP -- every tool
    function defined in the module must still be directly callable, same
    contract as with real fastmcp (see test_mcp_server.py's own module
    docstring)."""
    module = _reload_mcp_server_without_fastmcp(monkeypatch)
    result = module.veriflow_doctor()
    assert result["status"] in ("OK", "FAIL")


def test_resource_functions_remain_plain_callables_without_fastmcp(monkeypatch):
    module = _reload_mcp_server_without_fastmcp(monkeypatch)
    content = module.doc_manual()
    assert isinstance(content, str)
    assert len(content) > 100


def test_main_without_fastmcp_raises_clear_runtime_error(monkeypatch):
    module = _reload_mcp_server_without_fastmcp(monkeypatch)
    with pytest.raises(VeriFlowError) as exc_info:
        module.main()
    assert exc_info.value.code == "VF_MCP_FASTMCP_NOT_INSTALLED"
    assert "pip install veriflow-eda[mcp]" in str(exc_info.value)


def test_cmd_mcp_serve_without_fastmcp_raises_clear_runtime_error(monkeypatch):
    """cmd_mcp_serve (veriflow/commands/mcp.py) imports veriflow.mcp_server
    lazily inside the function body -- confirms that deferred import picks
    up the same fastmcp-less module state and surfaces the same clear
    error, not a raw ImportError/traceback."""
    import argparse

    _reload_mcp_server_without_fastmcp(monkeypatch)
    from veriflow.commands.mcp import cmd_mcp_serve

    with pytest.raises(VeriFlowError) as exc_info:
        cmd_mcp_serve(argparse.Namespace())
    assert exc_info.value.code == "VF_MCP_FASTMCP_NOT_INSTALLED"


def test_cli_mcp_serve_without_fastmcp_reports_clean_cli_error(monkeypatch, capsys):
    """End-to-end through veriflow.cli.main -- a human (or CI) running
    `veriflow mcp serve` without the `mcp` extra installed sees a clean
    error message and non-zero exit code, never a Python traceback."""
    _reload_mcp_server_without_fastmcp(monkeypatch)
    from veriflow.cli import main

    rc = main(["mcp", "serve"])
    assert rc != 0
    # Rich wraps long lines to the console width, so assert against
    # whitespace-normalized text rather than a raw contiguous substring.
    err = " ".join(capsys.readouterr().err.split())
    assert "fastmcp" in err
    assert "pip install veriflow-eda[mcp]" in err
