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


# ── SynthesisStage: automatic PDK liberty resolution (veriflow pdk) ───────────

def test_synthesis_stage_resolves_installed_pdk_liberty(tmp_path):
    """When the technology's PDK is installed on disk, SynthesisStage fills in
    `liberty` automatically -- no `technology.yaml` edit required."""
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

    fake_liberty = tmp_path / "sky130.lib"
    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=fake_liberty):
        result = stage.run(StageInput(design=design, context=ctx))

    called_technology = mock_backend.run_synthesis.call_args.kwargs["technology"]
    assert called_technology.liberty == str(fake_liberty)
    assert result.warnings is None


def test_synthesis_stage_warns_when_pdk_not_installed(tmp_path):
    """Missing PDK is a warning, not an abort -- synthesis still runs with
    generic (non-technology-mapped) script."""
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

    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=None):
        result = stage.run(StageInput(design=design, context=ctx))

    called_technology = mock_backend.run_synthesis.call_args.kwargs["technology"]
    assert called_technology.liberty is None
    assert result.status == "PASS"  # synthesis still ran, generic mapping
    assert result.warnings is not None
    assert any("VF_TECHNOLOGY_PDK_NOT_INSTALLED" in w for w in result.warnings)
    assert any("sky130" in w for w in result.warnings)


def test_synthesis_stage_generic_technology_never_looks_up_pdk(tmp_path):
    """`generic` has no installable PDK -- get_liberty_path must not even be called."""
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext

    mock_backend = MagicMock()
    mock_backend.run_synthesis.return_value = ("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    profile = ExecutionProfile()  # default technology_name == "generic"
    stage = SynthesisStage(profile=profile, backend=mock_backend)

    design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
    ctx = ExecutionContext(run_dir=tmp_path)

    with patch("veriflow.core.stages.synthesis.get_liberty_path") as mock_get_liberty:
        result = stage.run(StageInput(design=design, context=ctx))

    mock_get_liberty.assert_not_called()
    assert result.warnings is None


def test_synthesis_stage_does_not_override_explicit_liberty(tmp_path):
    """A technology with `liberty` already set (e.g. via technology.definition)
    is left untouched -- no PDK lookup needed or performed."""
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext
    from veriflow.models.technology_profile import register_technology_profile

    register_technology_profile(TechnologyProfile(name="preconfigured", liberty="/already/set.lib"))
    try:
        mock_backend = MagicMock()
        mock_backend.run_synthesis.return_value = ("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
        profile = ExecutionProfile(technology_name="preconfigured")
        stage = SynthesisStage(profile=profile, backend=mock_backend)

        design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
        ctx = ExecutionContext(run_dir=tmp_path)

        with patch("veriflow.core.stages.synthesis.get_liberty_path") as mock_get_liberty:
            result = stage.run(StageInput(design=design, context=ctx))

        mock_get_liberty.assert_not_called()
        called_technology = mock_backend.run_synthesis.call_args.kwargs["technology"]
        assert called_technology.liberty == "/already/set.lib"
        assert result.warnings is None
    finally:
        from veriflow.models.technology_profile import _REGISTRY
        _REGISTRY.pop("preconfigured", None)


# ── StageResult.technology / technology_version (traceability snapshot) ──────

def test_synthesis_stage_reports_technology_and_version_when_pdk_installed(tmp_path):
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

    fake_liberty = tmp_path / "sky130.lib"
    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=fake_liberty), \
         patch("veriflow.core.stages.synthesis.get_installed_pdk_version", return_value="0fe599b2afb6708d281543108caf8310912f54af"):
        result = stage.run(StageInput(design=design, context=ctx))

    assert result.technology == "sky130"
    assert result.technology_version == "0fe599b2afb6708d281543108caf8310912f54af"


def test_synthesis_stage_omits_technology_fields_when_pdk_not_installed(tmp_path):
    """PDK missing -- falls back to generic synthesis -- no technology/
    technology_version in the traceability snapshot, since none was
    actually applied."""
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

    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=None):
        result = stage.run(StageInput(design=design, context=ctx))

    assert result.technology is None
    assert result.technology_version is None


def test_synthesis_stage_omits_technology_fields_for_generic(tmp_path):
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext

    mock_backend = MagicMock()
    mock_backend.run_synthesis.return_value = ("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    profile = ExecutionProfile()  # generic
    stage = SynthesisStage(profile=profile, backend=mock_backend)

    design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
    ctx = ExecutionContext(run_dir=tmp_path)

    result = stage.run(StageInput(design=design, context=ctx))
    assert result.technology is None
    assert result.technology_version is None


def test_synthesis_stage_reports_technology_with_no_version_when_unresolvable(tmp_path):
    """liberty resolved (PDK-mapped synthesis genuinely happened), but the
    installed version can't be determined -- "technology" is still
    meaningful even if "technology_version" isn't."""
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

    fake_liberty = tmp_path / "sky130.lib"
    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=fake_liberty), \
         patch("veriflow.core.stages.synthesis.get_installed_pdk_version", return_value=None):
        result = stage.run(StageInput(design=design, context=ctx))

    assert result.technology == "sky130"
    assert result.technology_version is None


def test_stage_result_to_dict_includes_technology_fields_when_set():
    from veriflow.models.stage_result import StageResult
    sr = StageResult(name="synthesis", status="PASS", technology="sky130", technology_version="abc123")
    d = sr.to_dict()
    assert d["technology"] == "sky130"
    assert d["technology_version"] == "abc123"


def test_stage_result_to_dict_omits_technology_fields_when_none():
    from veriflow.models.stage_result import StageResult
    sr = StageResult(name="synthesis", status="PASS")
    d = sr.to_dict()
    assert "technology" not in d
    assert "technology_version" not in d


# ── require_pdk: fail (not warn) when the PDK isn't installed ────────────────


def test_synthesis_stage_require_pdk_raises_when_not_installed(tmp_path):
    from veriflow.core import VeriFlowError
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext

    mock_backend = MagicMock()
    profile = ExecutionProfile(technology_name="sky130", require_pdk=True)
    stage = SynthesisStage(profile=profile, backend=mock_backend)

    design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
    ctx = ExecutionContext(run_dir=tmp_path)

    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=None):
        with pytest.raises(VeriFlowError) as exc_info:
            stage.run(StageInput(design=design, context=ctx))

    assert exc_info.value.code == "VF_TECHNOLOGY_PDK_REQUIRED_NOT_INSTALLED"
    assert "sky130" in str(exc_info.value)
    # Stopped before ever invoking the backend (before running yosys)
    mock_backend.run_synthesis.assert_not_called()


def test_synthesis_stage_require_pdk_passes_when_installed(tmp_path):
    """require_pdk=True with the PDK actually installed: normal synthesis,
    real liberty applied, no error at all."""
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext

    mock_backend = MagicMock()
    mock_backend.run_synthesis.return_value = ("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    profile = ExecutionProfile(technology_name="sky130", require_pdk=True)
    stage = SynthesisStage(profile=profile, backend=mock_backend)

    design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
    ctx = ExecutionContext(run_dir=tmp_path)

    fake_liberty = tmp_path / "sky130.lib"
    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=fake_liberty):
        result = stage.run(StageInput(design=design, context=ctx))

    called_technology = mock_backend.run_synthesis.call_args.kwargs["technology"]
    assert called_technology.liberty == str(fake_liberty)
    assert result.status == "PASS"
    assert result.warnings is None


def test_synthesis_stage_require_pdk_false_default_unchanged(tmp_path):
    """require_pdk defaults to False -- current warn+generic-fallback
    behavior is completely unchanged."""
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext

    mock_backend = MagicMock()
    mock_backend.run_synthesis.return_value = ("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    profile = ExecutionProfile(technology_name="sky130")  # require_pdk defaults False
    assert profile.require_pdk is False
    stage = SynthesisStage(profile=profile, backend=mock_backend)

    design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
    ctx = ExecutionContext(run_dir=tmp_path)

    with patch("veriflow.core.stages.synthesis.get_liberty_path", return_value=None):
        result = stage.run(StageInput(design=design, context=ctx))

    assert result.status == "PASS"
    assert result.warnings is not None
    assert any("VF_TECHNOLOGY_PDK_NOT_INSTALLED" in w for w in result.warnings)


def test_synthesis_stage_require_pdk_irrelevant_for_generic_technology(tmp_path):
    """generic has no PDK to require -- require_pdk=True must not raise,
    since get_liberty_path is never even consulted for it."""
    from veriflow.core.stages.synthesis import SynthesisStage
    from veriflow.framework.design import Design
    from veriflow.framework.stage_input import StageInput
    from veriflow.models.execution_profile import ExecutionProfile
    from veriflow.models.stage_context import ExecutionContext

    mock_backend = MagicMock()
    mock_backend.run_synthesis.return_value = ("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    profile = ExecutionProfile(require_pdk=True)  # technology_name defaults to "generic"
    stage = SynthesisStage(profile=profile, backend=mock_backend)

    design = Design(top_module="top", rtl_sources=[tmp_path / "top.v"])
    ctx = ExecutionContext(run_dir=tmp_path)

    with patch("veriflow.core.stages.synthesis.get_liberty_path") as mock_get_liberty:
        result = stage.run(StageInput(design=design, context=ctx))

    mock_get_liberty.assert_not_called()
    assert result.status == "PASS"
    assert result.warnings is None
