"""Regression tests for Project Mode's results.json (2026-07-14 design change):
ProjectWorkflow.run() now persists a structured, portable JSON summary,
mirroring Database Mode's results.json/manifest.yaml behavior.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.core import VeriFlowError
from veriflow.workflows.project import ProjectWorkflow
from veriflow.workflows.project_config import ProjectWorkflowConfig


# ── helpers ───────────────────────────────────────────────────────────────────


def _mock_synth_backend(status="PASS"):
    from veriflow.core.backends.base import SynthesisBackend
    b = MagicMock(spec=SynthesisBackend)
    b.run_synthesis.return_value = (
        status,
        {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False},
    )
    return b


def _mock_conn_backend(status="PASS"):
    from veriflow.core.backends.base import ConnectivityBackend
    b = MagicMock(spec=ConnectivityBackend)
    b.run_connectivity.return_value = status
    return b


def _mock_sim_backend(status="COMPLETED"):
    from veriflow.core.backends.base import SimulationBackend
    b = MagicMock(spec=SimulationBackend)
    b.run_simulation.return_value = (status, {})
    return b


def _rtl_only_config(root: Path, rtl_content: str = "module shift_mux; endmodule\n") -> ProjectWorkflowConfig:
    rtl_dir = root / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / "shift_mux.v").write_text(rtl_content, encoding="utf-8")
    return ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "shift_mux",
                "rtl_sources": ["rtl/shift_mux.v"],
            },
        },
        root=root,
    )


def _full_config(root: Path) -> ProjectWorkflowConfig:
    (root / "rtl").mkdir(parents=True, exist_ok=True)
    (root / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    (root / "tb").mkdir(parents=True, exist_ok=True)
    (root / "tb" / "tb_top.v").write_text("module tb; endmodule\n", encoding="utf-8")
    return ProjectWorkflowConfig.from_dict(
        {
            "design": {
                "top_module": "top",
                "rtl_sources": ["rtl/top.v"],
                "tb_sources": ["tb/tb_top.v"],
            },
            "interface": {"name": "semicolab"},
            "simulation": {"tb_top": "tb"},
        },
        root=root,
    )


def _run_full(cfg, *, conn_status="PASS", sim_status="COMPLETED", synth_status="PASS"):
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend(conn_status)),
        patch("veriflow.workflows.project.get_simulation_backend", return_value=_mock_sim_backend(sim_status)),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend(synth_status)),
    ):
        return ProjectWorkflow(cfg).run()


def _load_results(pr) -> dict:
    return json.loads((pr.run_dir / "results.json").read_text(encoding="utf-8"))


# ── 1. Basic schema ────────────────────────────────────────────────────────────


def test_run_writes_results_json(tmp_path):
    cfg = _full_config(tmp_path)
    pr = _run_full(cfg)
    assert (pr.run_dir / "results.json").exists()


def test_results_json_top_level_schema_fields(tmp_path):
    cfg = _full_config(tmp_path)
    pr = _run_full(cfg)
    data = _load_results(pr)

    assert data["schema_version"] == "1.0"
    assert data["command"] == "project run"
    assert data["status"] in ("PASS", "FAIL")
    assert data["top_module"] == "top"
    assert data["interface_name"] == "semicolab"
    assert data["technology"] == "generic"
    assert set(data["stages"].keys()) == {"connectivity", "simulation", "synthesis"}


def test_results_json_status_pass_when_all_stages_pass(tmp_path):
    cfg = _full_config(tmp_path)
    pr = _run_full(cfg, conn_status="PASS", sim_status="COMPLETED", synth_status="PASS")
    data = _load_results(pr)
    assert data["status"] == "PASS"


def test_results_json_status_fail_when_a_stage_fails(tmp_path):
    cfg = _full_config(tmp_path)
    pr = _run_full(cfg, synth_status="FAIL")
    data = _load_results(pr)
    assert data["status"] == "FAIL"
    assert data["stages"]["synthesis"]["status"] == "FAIL"


# ── 2. Paths are relative to the config root, not absolute ───────────────────


def test_results_json_run_dir_is_relative(tmp_path):
    cfg = _full_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"
    pr = _run_full(cfg)
    data = _load_results(pr)
    assert data["run_dir"] == "runs/run-001"
    assert not Path(data["run_dir"]).is_absolute()


def test_results_json_rtl_and_tb_sources_are_relative(tmp_path):
    cfg = _full_config(tmp_path)
    pr = _run_full(cfg)
    data = _load_results(pr)
    assert data["rtl_sources"] == ["rtl/top.v"]
    assert data["tb_sources"] == ["tb/tb_top.v"]
    for p in data["rtl_sources"] + data["tb_sources"]:
        assert not Path(p).is_absolute()


def test_results_json_is_portable_regardless_of_run_dir_depth(tmp_path):
    """Even with a custom nested output.runs_dir, paths stay root-relative."""
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    cfg = ProjectWorkflowConfig.from_dict(
        {"design": {"top_module": "top", "rtl_sources": ["rtl/top.v"]}},
        root=tmp_path,
    )
    cfg.runs_dir = tmp_path / "build" / "output" / "runs"
    pr = _run_full(cfg)
    data = _load_results(pr)
    assert data["run_dir"] == "build/output/runs/run-001"


# ── 3. Stages not configured show up as SKIPPED, not omitted ─────────────────


def test_results_json_unconfigured_stages_marked_skipped(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    pr = _run_full(cfg)
    data = _load_results(pr)
    assert data["stages"]["connectivity"] == {"status": "SKIPPED", "log": None}
    assert data["stages"]["simulation"] == {"status": "SKIPPED", "log": None, "waves": None}
    assert data["interface_name"] is None


# ── 4. COMPLETED -> PASS normalization for simulation ─────────────────────────


def test_results_json_simulation_completed_normalized_to_pass(tmp_path):
    cfg = _full_config(tmp_path)
    pr = _run_full(cfg, sim_status="COMPLETED")
    data = _load_results(pr)
    assert data["stages"]["simulation"]["status"] == "PASS"


# ── 5. rtl_hash ────────────────────────────────────────────────────────────────


def test_results_json_rtl_hash_matches_sha256_of_file_content(tmp_path):
    content = "module shift_mux; /* distinctive content */ endmodule\n"
    cfg = _rtl_only_config(tmp_path, rtl_content=content)
    pr = _run_full(cfg)
    data = _load_results(pr)

    # Hash the actual on-disk bytes (not the original str) -- write_text()
    # may translate newlines depending on platform, so this is the only
    # comparison immune to that.
    expected = hashlib.sha256((tmp_path / "rtl" / "shift_mux.v").read_bytes()).hexdigest()
    assert data["rtl_hash"] == {"shift_mux.v": expected}


def test_results_json_rtl_hash_changes_if_file_edited_between_runs(tmp_path):
    cfg = _rtl_only_config(tmp_path, rtl_content="module shift_mux; endmodule\n")
    pr1 = _run_full(cfg)
    hash1 = _load_results(pr1)["rtl_hash"]["shift_mux.v"]

    (tmp_path / "rtl" / "shift_mux.v").write_text(
        "module shift_mux; /* edited */ endmodule\n", encoding="utf-8"
    )
    pr2 = _run_full(cfg)
    hash2 = _load_results(pr2)["rtl_hash"]["shift_mux.v"]

    assert hash1 != hash2


def test_results_json_rtl_hash_skips_missing_files(tmp_path):
    """rtl_sources pointing at a nonexistent file must not crash results.json
    generation -- the entry is just omitted from rtl_hash."""
    cfg = ProjectWorkflowConfig.from_dict(
        {"design": {"top_module": "top", "rtl_sources": ["rtl/does_not_exist.v"]}},
        root=tmp_path,
    )
    pr = _run_full(cfg)
    data = _load_results(pr)
    assert data["rtl_hash"] == {}


# ── 6. veriflow_version / timestamp ───────────────────────────────────────────


def test_results_json_veriflow_version_matches_package(tmp_path):
    from veriflow import __version__
    cfg = _rtl_only_config(tmp_path)
    pr = _run_full(cfg)
    data = _load_results(pr)
    assert data["veriflow_version"] == __version__


def test_results_json_timestamp_is_parseable_iso8601_utc(tmp_path):
    cfg = _rtl_only_config(tmp_path)
    pr = _run_full(cfg)
    data = _load_results(pr)
    parsed = datetime.fromisoformat(data["timestamp"])
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0


# ── 7. Real (non-mocked-filesystem) log/wave paths ────────────────────────────


def test_results_json_log_paths_populated_when_stage_writes_a_log(tmp_path):
    """Use a fake backend that actually writes to the log path (unlike the
    pure MagicMock backends above, whose logs never land on disk), to verify
    the "log" field is populated and root-relative once the file exists."""
    from veriflow.core.backends.base import SynthesisBackend

    class _RealFileSynthBackend(SynthesisBackend):
        def run_synthesis(self, *, rtl_files, top_module, synth_log_path, technology=None):
            synth_log_path.write_text("yosys ran ok\n", encoding="utf-8")
            return "PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}

        def check_availability(self):
            return [{"tool": "yosys", "available": True, "version": "0.0", "path": "/bin/yosys", "error": None}]

    cfg = _rtl_only_config(tmp_path)
    cfg.runs_dir = tmp_path / "runs"
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_RealFileSynthBackend()),
    ):
        pr = ProjectWorkflow(cfg).run()
    data = _load_results(pr)

    log = data["stages"]["synthesis"]["log"]
    assert log == "runs/run-001/out/synth/logs/synth.log"
    assert (tmp_path / log).read_text(encoding="utf-8") == "yosys ran ok\n"


# ── 8. get_project_run_result (api.py) ────────────────────────────────────────


def test_get_project_run_result_reads_generated_file(tmp_path):
    from veriflow.api import get_project_run_result

    cfg = _full_config(tmp_path)
    pr = _run_full(cfg)

    data = get_project_run_result(pr.run_dir)
    assert data == _load_results(pr)


def test_get_project_run_result_accepts_str_path(tmp_path):
    from veriflow.api import get_project_run_result

    cfg = _full_config(tmp_path)
    pr = _run_full(cfg)

    data = get_project_run_result(str(pr.run_dir))
    assert data["command"] == "project run"


def test_get_project_run_result_raises_not_found(tmp_path):
    from veriflow.api import get_project_run_result

    missing = tmp_path / "runs" / "run-999"
    with pytest.raises(VeriFlowError) as exc_info:
        get_project_run_result(missing)
    assert exc_info.value.code == "VF_PROJECT_RUN_RESULT_NOT_FOUND"


def test_get_project_run_result_raises_corrupt_on_bad_json(tmp_path):
    """A results.json that exists but isn't valid JSON (e.g. a run
    interrupted mid-write) raises VF_PROJECT_RUN_RESULT_CORRUPT rather than
    a bare json.JSONDecodeError (dev-docs/MCP_API_AUDIT.md)."""
    from veriflow.api import get_project_run_result

    run_dir = tmp_path / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "results.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(VeriFlowError) as exc_info:
        get_project_run_result(run_dir)
    assert exc_info.value.code == "VF_PROJECT_RUN_RESULT_CORRUPT"
