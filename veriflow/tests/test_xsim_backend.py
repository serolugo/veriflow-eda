"""Tests for XsimSimulationBackend.run_simulation() (core/backends/xsim.py).

Same subprocess-mocking pattern as icarus's own sim_runner tests
(test_veriflow.py's "Simulation runner tests" section) -- no real Vivado
install required; `subprocess.run` is patched at the module level so
`shutil.which`/PATH state on this machine is irrelevant.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core.backends.xsim import XsimSimulationBackend


def _make_files(tmp_path: Path) -> tuple[Path, Path]:
    rtl = tmp_path / "top.v"
    tb = tmp_path / "tb_top.v"
    rtl.write_text("module top; endmodule\n", encoding="utf-8")
    tb.write_text("module tb; endmodule\n", encoding="utf-8")
    return rtl, tb


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _run(backend, rtl, tb, tmp_path, tb_top="tb"):
    return backend.run_simulation(
        rtl_files=[rtl],
        tb_files=[tb],
        tb_top=tb_top,
        sim_log_path=tmp_path / "results" / "sim.log",
        wave_path=tmp_path / "results" / "waves" / "waves.vcd",
    )


# ── 3-step ordering and arguments ─────────────────────────────────────────────


def test_three_steps_invoked_in_order_with_correct_arguments(tmp_path):
    rtl, tb = _make_files(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _proc(0)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, _ = _run(backend, rtl, tb, tmp_path)

    assert status == "COMPLETED"
    assert len(calls) == 3
    xvlog_cmd, xelab_cmd, xsim_cmd = calls

    assert xvlog_cmd[0] == "xvlog"
    assert rtl.as_posix() in xvlog_cmd
    assert tb.as_posix() in xvlog_cmd

    assert xelab_cmd[0] == "xelab"
    assert "tb" in xelab_cmd
    assert "-s" in xelab_cmd
    snapshot_name = xelab_cmd[xelab_cmd.index("-s") + 1]

    assert xsim_cmd[0] == "xsim"
    assert xsim_cmd[1] == snapshot_name  # xsim must load exactly what xelab produced
    assert "--runall" in xsim_cmd
    assert "--log" in xsim_cmd


def test_all_three_steps_run_in_the_same_temp_cwd(tmp_path):
    """xelab's elaborated snapshot is only resolvable from the cwd it was
    created in -- all three steps must share one cwd (and it must not be
    the project directory)."""
    rtl, tb = _make_files(tmp_path)
    cwds: list[str] = []

    def fake_run(cmd, **kwargs):
        cwds.append(kwargs.get("cwd"))
        return _proc(0)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        _run(backend, rtl, tb, tmp_path)

    assert len(set(cwds)) == 1
    assert cwds[0] is not None
    assert Path(cwds[0]) != tmp_path


# ── Windows .bat resolution (2026-07-19 real-machine bug) ────────────────────


def test_run_simulation_uses_resolved_bat_path_on_windows(tmp_path):
    """Reproduces the real Windows bug end-to-end at the run_simulation
    level (not just check_availability): shutil.which resolving each
    tool to a "<tool>.BAT" launcher must be what's actually invoked, not
    the bare name (which fails with FileNotFoundError under
    CreateProcess/shell=False)."""
    rtl, tb = _make_files(tmp_path)
    calls: list[list[str]] = []

    def which_side(tool):
        return rf"C:\Xilinx\Vivado\2024.1\bin\{tool}.BAT"

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _proc(0)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.shutil.which", side_effect=which_side), \
         patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, _ = _run(backend, rtl, tb, tmp_path)

    assert status == "COMPLETED"
    assert len(calls) == 3
    xvlog_cmd, xelab_cmd, xsim_cmd = calls
    assert xvlog_cmd[0] == r"C:\Xilinx\Vivado\2024.1\bin\xvlog.BAT"
    assert xelab_cmd[0] == r"C:\Xilinx\Vivado\2024.1\bin\xelab.BAT"
    assert xsim_cmd[0] == r"C:\Xilinx\Vivado\2024.1\bin\xsim.BAT"
    invoked = {c[0] for c in calls}
    assert "xvlog" not in invoked
    assert "xelab" not in invoked
    assert "xsim" not in invoked


def test_run_simulation_unix_path_unaffected(tmp_path):
    """On Linux/macOS, shutil.which's result is already the correct
    absolute path -- used directly, same as before this fix, no
    functional difference from passing the bare name."""
    rtl, tb = _make_files(tmp_path)
    calls: list[list[str]] = []

    def which_side(tool):
        return f"/usr/local/bin/{tool}"

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _proc(0)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.shutil.which", side_effect=which_side), \
         patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, _ = _run(backend, rtl, tb, tmp_path)

    assert status == "COMPLETED"
    assert calls[0][0] == "/usr/local/bin/xvlog"
    assert calls[1][0] == "/usr/local/bin/xelab"
    assert calls[2][0] == "/usr/local/bin/xsim"


def test_run_simulation_falls_back_to_bare_name_when_tool_not_found(tmp_path):
    """shutil.which returning None (tool genuinely not installed) falls
    back to the bare name -- unchanged from before this fix; missing-tool
    detection happens upstream via check_availability()/validate_tools()."""
    rtl, tb = _make_files(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _proc(0)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.shutil.which", return_value=None), \
         patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        _run(backend, rtl, tb, tmp_path)

    assert calls[0][0] == "xvlog"


# ── Failure short-circuiting ───────────────────────────────────────────────────


def test_xvlog_failure_returns_failed_and_never_calls_xelab_or_xsim(tmp_path):
    rtl, tb = _make_files(tmp_path)
    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "xvlog":
            return _proc(1, stderr="xvlog: syntax error near 'endmodule'")
        raise AssertionError(f"{cmd[0]} must not be invoked after xvlog fails")

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, parsed = _run(backend, rtl, tb, tmp_path)

    assert status == "FAILED"
    assert calls == ["xvlog"]
    assert parsed == {"sim_time": "", "seed": ""}
    log_text = (tmp_path / "results" / "sim.log").read_text(encoding="utf-8")
    assert "xvlog" in log_text
    assert "syntax error" in log_text
    assert "xelab" not in log_text  # step never ran, no section for it


def test_xelab_failure_returns_failed_and_never_calls_xsim(tmp_path):
    rtl, tb = _make_files(tmp_path)
    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "xvlog":
            return _proc(0)
        if cmd[0] == "xelab":
            return _proc(1, stderr="xelab: unresolved module 'tb'")
        raise AssertionError("xsim must not be invoked after xelab fails")

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, parsed = _run(backend, rtl, tb, tmp_path)

    assert status == "FAILED"
    assert calls == ["xvlog", "xelab"]
    log_text = (tmp_path / "results" / "sim.log").read_text(encoding="utf-8")
    assert "xvlog" in log_text
    assert "unresolved module" in log_text


# ── Successful run ────────────────────────────────────────────────────────────


def test_xsim_success_returns_completed_and_parses_log(tmp_path):
    rtl, tb = _make_files(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[0] == "xsim":
            log_path = Path(cmd[cmd.index("--log") + 1])
            log_path.write_text("$finish called at 335000 (1ps)\n", encoding="utf-8")
        return _proc(0)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, parsed = _run(backend, rtl, tb, tmp_path)

    assert status == "COMPLETED"
    assert parsed["sim_time"] == "335 ns"
    log_text = (tmp_path / "results" / "sim.log").read_text(encoding="utf-8")
    assert "xvlog" in log_text
    assert "xelab" in log_text
    assert "xsim" in log_text


def test_xsim_nonzero_exit_returns_failed(tmp_path):
    rtl, tb = _make_files(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[0] == "xsim":
            return _proc(1, stderr="xsim: runtime error")
        return _proc(0)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, _ = _run(backend, rtl, tb, tmp_path)

    assert status == "FAILED"


def test_xsim_zero_exit_but_fatal_error_in_log_still_fails(tmp_path):
    """A second, independent PASS/FAIL signal: xsim returning exit code 0
    doesn't automatically mean COMPLETED if the transcript itself reports
    a fatal error."""
    rtl, tb = _make_files(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[0] == "xsim":
            log_path = Path(cmd[cmd.index("--log") + 1])
            log_path.write_text("ERROR: [Simulator 43-3999] Fatal error in testbench\n", encoding="utf-8")
        return _proc(0)  # exit code 0 despite the fatal error in the transcript

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        status, _ = _run(backend, rtl, tb, tmp_path)

    assert status == "FAILED"


# ── Waveform copy-back ────────────────────────────────────────────────────────


def test_vcd_dumped_by_testbench_is_copied_to_wave_path(tmp_path):
    """The TB's own `$dumpfile("waves.vcd")` call dumps into xsim's actual
    cwd (the temp work dir) -- must be copied to the real wave_path
    afterward, same end result as icarus's cwd-relocation trick."""
    rtl, tb = _make_files(tmp_path)
    captured_cwd: list[str] = []

    def fake_run(cmd, **kwargs):
        cwd = kwargs.get("cwd")
        captured_cwd.append(cwd)
        if cmd[0] == "xsim":
            (Path(cwd) / "waves.vcd").write_text("$dumpvars\n", encoding="utf-8")
        return _proc(0)

    backend = XsimSimulationBackend()
    wave_path = tmp_path / "results" / "waves" / "waves.vcd"
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        backend.run_simulation(
            rtl_files=[rtl], tb_files=[tb], tb_top="tb",
            sim_log_path=tmp_path / "results" / "sim.log", wave_path=wave_path,
        )

    assert wave_path.is_file()
    assert wave_path.read_text(encoding="utf-8") == "$dumpvars\n"


def test_no_vcd_produced_is_not_an_error(tmp_path):
    """A testbench with no $dumpfile call simply produces no waveform --
    must not raise or fail the run."""
    rtl, tb = _make_files(tmp_path)

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", return_value=_proc(0)):
        status, _ = _run(backend, rtl, tb, tmp_path)

    assert status == "COMPLETED"
    assert not (tmp_path / "results" / "waves" / "waves.vcd").exists()


# ── Temp directory cleanup ─────────────────────────────────────────────────────


def test_temp_dir_cleaned_up_on_success(tmp_path):
    seen_tmp_dir: list[Path] = []

    def fake_run(cmd, **kwargs):
        seen_tmp_dir.append(Path(kwargs["cwd"]))
        return _proc(0)

    rtl, tb = _make_files(tmp_path)
    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        _run(backend, rtl, tb, tmp_path)

    assert seen_tmp_dir
    assert not seen_tmp_dir[0].exists()


def test_temp_dir_cleaned_up_on_xvlog_failure(tmp_path):
    seen_tmp_dir: list[Path] = []

    def fake_run(cmd, **kwargs):
        seen_tmp_dir.append(Path(kwargs["cwd"]))
        return _proc(1, stderr="fail")

    rtl, tb = _make_files(tmp_path)
    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        _run(backend, rtl, tb, tmp_path)

    assert not seen_tmp_dir[0].exists()


def test_temp_dir_cleaned_up_on_unexpected_exception(tmp_path):
    """Even a genuine crash mid-flow (not just a tool reporting FAIL) must
    not leak the temp work directory."""
    rtl, tb = _make_files(tmp_path)
    seen_tmp_dir: list[Path] = []

    def fake_run(cmd, **kwargs):
        seen_tmp_dir.append(Path(kwargs["cwd"]))
        raise RuntimeError("simulated crash")

    backend = XsimSimulationBackend()
    with patch("veriflow.core.backends.xsim.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError):
            _run(backend, rtl, tb, tmp_path)

    assert not seen_tmp_dir[0].exists()
