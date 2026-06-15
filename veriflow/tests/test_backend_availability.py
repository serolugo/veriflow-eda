"""Tests for check_availability() on all backends."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from veriflow.core.backends.icarus import IcarusConnectivityBackend, IcarusSimulationBackend
from veriflow.core.backends.yosys import YosysSynthesisBackend

# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_proc(version_line: str) -> MagicMock:
    proc = MagicMock()
    proc.stdout = version_line + "\n"
    proc.stderr = ""
    return proc


# ── IcarusConnectivityBackend ─────────────────────────────────────────────────

class TestIcarusConnectivityAvailability:
    def test_not_in_path(self):
        backend = IcarusConnectivityBackend()
        with patch("veriflow.core.backends._tools.shutil.which", return_value=None):
            result = backend.check_availability()
        assert len(result) == 1
        entry = result[0]
        assert entry["tool"] == "iverilog"
        assert entry["available"] is False
        assert entry["version"] is None
        assert entry["path"] is None
        assert entry["error"] is not None

    def test_available_with_version(self):
        backend = IcarusConnectivityBackend()
        with patch("veriflow.core.backends._tools.shutil.which", return_value="/usr/bin/iverilog"), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   return_value=_fake_proc("Icarus Verilog version 11.0")):
            result = backend.check_availability()
        assert len(result) == 1
        entry = result[0]
        assert entry["tool"] == "iverilog"
        assert entry["available"] is True
        assert entry["version"] == "Icarus Verilog version 11.0"
        assert entry["path"] == "/usr/bin/iverilog"
        assert entry["error"] is None

    def test_subprocess_exception_returns_unavailable(self):
        backend = IcarusConnectivityBackend()
        with patch("veriflow.core.backends._tools.shutil.which", return_value="/usr/bin/iverilog"), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   side_effect=FileNotFoundError("boom")):
            result = backend.check_availability()
        entry = result[0]
        assert entry["available"] is False
        assert "boom" in entry["error"]


# ── IcarusSimulationBackend ───────────────────────────────────────────────────

class TestIcarusSimulationAvailability:
    def test_both_not_in_path(self):
        backend = IcarusSimulationBackend()
        with patch("veriflow.core.backends._tools.shutil.which", return_value=None):
            result = backend.check_availability()
        assert len(result) == 2
        tools = {r["tool"] for r in result}
        assert tools == {"iverilog", "vvp"}
        for entry in result:
            assert entry["available"] is False
            assert entry["error"] is not None

    def test_both_available(self):
        backend = IcarusSimulationBackend()
        with patch("veriflow.core.backends._tools.shutil.which",
                   side_effect=lambda t: f"/usr/bin/{t}"), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   return_value=_fake_proc("Icarus Verilog version 11.0")):
            result = backend.check_availability()
        assert len(result) == 2
        by_tool = {r["tool"]: r for r in result}
        assert by_tool["iverilog"]["available"] is True
        assert by_tool["iverilog"]["path"] == "/usr/bin/iverilog"
        assert by_tool["vvp"]["available"] is True
        assert by_tool["vvp"]["path"] == "/usr/bin/vvp"

    def test_iverilog_available_vvp_missing(self):
        backend = IcarusSimulationBackend()

        def which_side(tool: str):
            return "/usr/bin/iverilog" if tool == "iverilog" else None

        with patch("veriflow.core.backends._tools.shutil.which", side_effect=which_side), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   return_value=_fake_proc("Icarus Verilog version 11.0")):
            result = backend.check_availability()

        by_tool = {r["tool"]: r for r in result}
        assert by_tool["iverilog"]["available"] is True
        assert by_tool["vvp"]["available"] is False


# ── YosysSynthesisBackend ─────────────────────────────────────────────────────

class TestYosysAvailability:
    def test_not_in_path(self):
        backend = YosysSynthesisBackend()
        with patch("veriflow.core.backends._tools.shutil.which", return_value=None):
            result = backend.check_availability()
        assert len(result) == 1
        entry = result[0]
        assert entry["tool"] == "yosys"
        assert entry["available"] is False
        assert entry["error"] is not None

    def test_available_with_version(self):
        backend = YosysSynthesisBackend()
        with patch("veriflow.core.backends._tools.shutil.which", return_value="/usr/bin/yosys"), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   return_value=_fake_proc("Yosys 0.38 (git sha1 abc1234)")):
            result = backend.check_availability()
        assert len(result) == 1
        entry = result[0]
        assert entry["tool"] == "yosys"
        assert entry["available"] is True
        assert entry["version"] == "Yosys 0.38 (git sha1 abc1234)"
        assert entry["path"] == "/usr/bin/yosys"

    def test_version_from_stderr_fallback(self):
        """iverilog-style: version on stderr, empty stdout."""
        backend = YosysSynthesisBackend()
        proc = MagicMock()
        proc.stdout = ""
        proc.stderr = "Yosys 0.38 (via stderr)\n"
        with patch("veriflow.core.backends._tools.shutil.which", return_value="/usr/bin/yosys"), \
             patch("veriflow.core.backends._tools.subprocess.run", return_value=proc):
            result = backend.check_availability()
        assert result[0]["version"] == "Yosys 0.38 (via stderr)"
