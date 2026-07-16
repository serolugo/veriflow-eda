"""Tests for TechnologyProfile wiring into synthesis (2026-07-14 migration,
Step 5): `technology.liberty` and `technology.synth_extra` reach the actual
yosys script, and `SynthesisStage` resolves the technology profile from
`ExecutionProfile.technology_name` before calling the backend.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from veriflow.core.backends.yosys import YosysSynthesisBackend
from veriflow.core.synth_runner import run_synthesis
from veriflow.models.technology_profile import TechnologyProfile


def _fake_completed_process():
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "yosys ok\n"
    proc.stderr = ""
    return proc


# ── core/synth_runner.run_synthesis ───────────────────────────────────────────

def test_run_synthesis_no_technology_script_unchanged(tmp_path):
    with patch("veriflow.core.synth_runner.subprocess.run", return_value=_fake_completed_process()) as mock_run:
        run_synthesis(
            rtl_files=[tmp_path / "top.v"],
            top_module="top",
            synth_log_path=tmp_path / "synth.log",
        )
    script = mock_run.call_args.args[0][2]
    assert "abc -liberty" not in script
    assert script == "\nread_verilog " + (tmp_path / "top.v").as_posix() + "\nhierarchy -check -top top\nsynth\ncheck\nstat\n"


def test_run_synthesis_with_liberty_adds_abc_liberty_line(tmp_path):
    technology = TechnologyProfile(name="sky130", liberty="/pdk/sky130.lib")
    with patch("veriflow.core.synth_runner.subprocess.run", return_value=_fake_completed_process()) as mock_run:
        run_synthesis(
            rtl_files=[tmp_path / "top.v"],
            top_module="top",
            synth_log_path=tmp_path / "synth.log",
            technology=technology,
        )
    script = mock_run.call_args.args[0][2]
    lines = script.strip().splitlines()
    assert "abc -liberty /pdk/sky130.lib" in lines
    # Must come after `synth`, before `check`/`stat`
    assert lines.index("synth") < lines.index("abc -liberty /pdk/sky130.lib") < lines.index("check")


def test_run_synthesis_with_synth_extra_adds_lines(tmp_path):
    technology = TechnologyProfile(name="fast_check", synth_extra=["-flatten", "-noabc"])
    with patch("veriflow.core.synth_runner.subprocess.run", return_value=_fake_completed_process()) as mock_run:
        run_synthesis(
            rtl_files=[tmp_path / "top.v"],
            top_module="top",
            synth_log_path=tmp_path / "synth.log",
            technology=technology,
        )
    script = mock_run.call_args.args[0][2]
    lines = script.strip().splitlines()
    assert "-flatten" in lines
    assert "-noabc" in lines
    assert lines.index("synth") < lines.index("-flatten") < lines.index("check")


def test_run_synthesis_with_liberty_and_synth_extra_both_applied(tmp_path):
    technology = TechnologyProfile(name="sky130", liberty="/pdk/sky130.lib", synth_extra=["-flatten"])
    with patch("veriflow.core.synth_runner.subprocess.run", return_value=_fake_completed_process()) as mock_run:
        run_synthesis(
            rtl_files=[tmp_path / "top.v"],
            top_module="top",
            synth_log_path=tmp_path / "synth.log",
            technology=technology,
        )
    script = mock_run.call_args.args[0][2]
    lines = script.strip().splitlines()
    assert lines.index("synth") < lines.index("abc -liberty /pdk/sky130.lib") < lines.index("-flatten") < lines.index("check")


def test_run_synthesis_technology_with_liberty_none_is_noop(tmp_path):
    technology = TechnologyProfile(name="generic")  # liberty=None, synth_extra=[] (defaults)
    with patch("veriflow.core.synth_runner.subprocess.run", return_value=_fake_completed_process()) as mock_run:
        run_synthesis(
            rtl_files=[tmp_path / "top.v"],
            top_module="top",
            synth_log_path=tmp_path / "synth.log",
            technology=technology,
        )
    script = mock_run.call_args.args[0][2]
    assert "abc -liberty" not in script


# ── YosysSynthesisBackend passes technology through ───────────────────────────

def test_yosys_backend_forwards_technology_to_run_synthesis(tmp_path):
    technology = TechnologyProfile(name="sky130", liberty="/pdk/sky130.lib")
    backend = YosysSynthesisBackend()
    with patch("veriflow.core.backends.yosys.run_synthesis", return_value=("PASS", {})) as mock_run_synthesis:
        backend.run_synthesis(
            rtl_files=[tmp_path / "top.v"],
            top_module="top",
            synth_log_path=tmp_path / "synth.log",
            technology=technology,
        )
    assert mock_run_synthesis.call_args.kwargs["technology"] is technology


def test_yosys_backend_technology_defaults_to_none(tmp_path):
    backend = YosysSynthesisBackend()
    with patch("veriflow.core.backends.yosys.run_synthesis", return_value=("PASS", {})) as mock_run_synthesis:
        backend.run_synthesis(
            rtl_files=[tmp_path / "top.v"],
            top_module="top",
            synth_log_path=tmp_path / "synth.log",
        )
    assert mock_run_synthesis.call_args.kwargs["technology"] is None


# ── SynthesisStage resolves technology from ExecutionProfile.technology_name ──

def test_synthesis_stage_resolves_and_forwards_technology(tmp_path):
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext

    mock_backend = MagicMock()
    mock_backend.run_synthesis.return_value = ("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    profile = ExecutionProfile(technology_name="sky130")
    stage = SynthesisStage(profile=profile, backend=mock_backend)

    design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
    ctx = ExecutionContext(run_dir=tmp_path)
    stage.run(StageInput(design=design, context=ctx))

    called_technology = mock_backend.run_synthesis.call_args.kwargs["technology"]
    assert called_technology is not None
    assert called_technology.name == "sky130"
