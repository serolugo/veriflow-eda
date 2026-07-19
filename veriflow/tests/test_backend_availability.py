"""Tests for check_availability() on all backends."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from veriflow.core.backends.icarus import IcarusConnectivityBackend, IcarusSimulationBackend
from veriflow.core.backends.xsim import XsimSimulationBackend
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


# ── XsimSimulationBackend ─────────────────────────────────────────────────────

class TestXsimSimulationAvailability:
    def test_all_three_not_in_path(self):
        backend = XsimSimulationBackend()
        with patch("veriflow.core.backends._tools.shutil.which", return_value=None):
            result = backend.check_availability()
        assert len(result) == 3
        tools = {r["tool"] for r in result}
        assert tools == {"xvlog", "xelab", "xsim"}
        for entry in result:
            assert entry["available"] is False
            assert entry["version"] is None
            assert entry["path"] is None
            assert entry["error"] is not None

    def test_all_three_available(self):
        backend = XsimSimulationBackend()
        with patch("veriflow.core.backends._tools.shutil.which",
                   side_effect=lambda t: f"/opt/Vivado/bin/{t}"), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   return_value=_fake_proc("Vivado Simulator 2024.1")):
            result = backend.check_availability()
        assert len(result) == 3
        by_tool = {r["tool"]: r for r in result}
        for tool in ("xvlog", "xelab", "xsim"):
            assert by_tool[tool]["available"] is True
            assert by_tool[tool]["path"] == f"/opt/Vivado/bin/{tool}"
            assert by_tool[tool]["version"] == "Vivado Simulator 2024.1"

    def test_partial_availability_xvlog_only(self):
        """Only xvlog present -- xelab/xsim missing (e.g. a partial/broken
        Vivado install) each report their own independent status."""
        backend = XsimSimulationBackend()

        def which_side(tool: str):
            return "/opt/Vivado/bin/xvlog" if tool == "xvlog" else None

        with patch("veriflow.core.backends._tools.shutil.which", side_effect=which_side), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   return_value=_fake_proc("Vivado Simulator 2024.1")):
            result = backend.check_availability()

        by_tool = {r["tool"]: r for r in result}
        assert by_tool["xvlog"]["available"] is True
        assert by_tool["xelab"]["available"] is False
        assert by_tool["xsim"]["available"] is False

    def test_partial_availability_xsim_missing_only(self):
        backend = XsimSimulationBackend()

        def which_side(tool: str):
            return None if tool == "xsim" else f"/opt/Vivado/bin/{tool}"

        with patch("veriflow.core.backends._tools.shutil.which", side_effect=which_side), \
             patch("veriflow.core.backends._tools.subprocess.run",
                   return_value=_fake_proc("Vivado Simulator 2024.1")):
            result = backend.check_availability()

        by_tool = {r["tool"]: r for r in result}
        assert by_tool["xvlog"]["available"] is True
        assert by_tool["xelab"]["available"] is True
        assert by_tool["xsim"]["available"] is False

    def test_all_three_available_via_windows_bat_resolution(self):
        """End-to-end reproduction of the real Windows bug: shutil.which
        resolves each tool to its "<tool>.BAT" launcher (not a bare-name
        executable) -- check_availability() must still report all three
        as available, using the resolved .BAT path for the actual
        subprocess call rather than the bare name that would fail under
        CreateProcess/shell=False."""
        backend = XsimSimulationBackend()
        captured_cmds: list[list[str]] = []

        def which_side(tool: str):
            return rf"C:\Xilinx\Vivado\2024.1\bin\{tool}.BAT"

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return _fake_proc("Vivado Simulator v2024.1")

        with patch("veriflow.core.backends._tools.shutil.which", side_effect=which_side), \
             patch("veriflow.core.backends._tools.subprocess.run", side_effect=fake_run):
            result = backend.check_availability()

        by_tool = {r["tool"]: r for r in result}
        for tool in ("xvlog", "xelab", "xsim"):
            assert by_tool[tool]["available"] is True
            assert by_tool[tool]["path"] == rf"C:\Xilinx\Vivado\2024.1\bin\{tool}.BAT"
            assert by_tool[tool]["version"] == "Vivado Simulator v2024.1"

        # Every actual subprocess invocation used the resolved .BAT path,
        # never the bare tool name
        invoked_argv0 = {cmd[0] for cmd in captured_cmds}
        assert invoked_argv0 == {
            r"C:\Xilinx\Vivado\2024.1\bin\xvlog.BAT",
            r"C:\Xilinx\Vivado\2024.1\bin\xelab.BAT",
            r"C:\Xilinx\Vivado\2024.1\bin\xsim.BAT",
        }
        assert "xvlog" not in invoked_argv0
        assert "xelab" not in invoked_argv0
        assert "xsim" not in invoked_argv0

    def test_uses_version_flag(self):
        """check_availability must probe with `-version` (Vivado CLI
        convention), not iverilog/yosys's `-V`."""
        backend = XsimSimulationBackend()
        captured_flags = []

        def fake_run(cmd, **kwargs):
            captured_flags.append(cmd[1])
            return _fake_proc("Vivado Simulator 2024.1")

        with patch("veriflow.core.backends._tools.shutil.which", return_value="/opt/Vivado/bin/xvlog"), \
             patch("veriflow.core.backends._tools.subprocess.run", side_effect=fake_run):
            backend.check_availability()

        assert captured_flags == ["-version", "-version", "-version"]


# ── _check_tool: uses shutil.which's resolved path, not the bare name ────────
# (2026-07-19: real Windows bug -- Vivado installs xvlog/xelab/xsim as a
# same-named extensionless file alongside a "<tool>.bat" launcher.
# shutil.which correctly finds ".../xvlog.BAT" (PATHEXT-aware search),
# but subprocess.run(["xvlog", ...]) with the bare name fails with
# FileNotFoundError ([WinError 2]) under CreateProcess/shell=False, which
# doesn't apply PATHEXT the way shutil.which/cmd.exe do. Confirmed against
# a real Vivado 2024.1 install on this machine before applying the fix.)

class TestCheckToolUsesResolvedPath:
    def test_windows_bat_resolution_is_passed_to_subprocess(self):
        """shutil.which resolving to a same-named-plus-.bat path must be
        what actually gets invoked, not the bare tool name."""
        from veriflow.core.backends._tools import _check_tool

        resolved = r"C:\Xilinx\Vivado\2024.1\bin\xvlog.BAT"
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return _fake_proc("Vivado Simulator v2024.1")

        with patch("veriflow.core.backends._tools.shutil.which", return_value=resolved), \
             patch("veriflow.core.backends._tools.subprocess.run", side_effect=fake_run):
            result = _check_tool("xvlog", version_flag="-version")

        assert captured_cmd[0] == resolved
        assert captured_cmd[0] != "xvlog"
        assert result["available"] is True
        assert result["path"] == resolved

    def test_unix_style_path_unaffected(self):
        """On Linux/macOS, shutil.which's result is already the correct
        absolute path with no extension ambiguity -- behavior is
        unchanged (same path used, no bare-name fallback ever needed)."""
        from veriflow.core.backends._tools import _check_tool

        resolved = "/usr/local/bin/xvlog"
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return _fake_proc("Vivado Simulator v2024.1")

        with patch("veriflow.core.backends._tools.shutil.which", return_value=resolved), \
             patch("veriflow.core.backends._tools.subprocess.run", side_effect=fake_run):
            result = _check_tool("xvlog", version_flag="-version")

        assert captured_cmd[0] == resolved
        assert result["available"] is True

    def test_tool_genuinely_missing_still_reports_unavailable(self):
        """shutil.which returning None is unaffected by this fix -- still
        reported unavailable, no subprocess call attempted at all."""
        from veriflow.core.backends._tools import _check_tool

        with patch("veriflow.core.backends._tools.shutil.which", return_value=None), \
             patch("veriflow.core.backends._tools.subprocess.run") as mock_run:
            result = _check_tool("xvlog", version_flag="-version")

        mock_run.assert_not_called()
        assert result["available"] is False
        assert result["path"] is None


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
