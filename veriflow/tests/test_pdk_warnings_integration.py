"""End-to-end checks that a missing PDK's VF_TECHNOLOGY_PDK_NOT_INSTALLED
warning (raised inside SynthesisStage, see test_synthesis_technology.py for
unit coverage) actually reaches Database Mode's run_result["warnings"] and
Project Mode's results.json "warnings" field -- not just the StageResult it
originates from.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from veriflow.tests.test_database_workflow import _patch_tools, _setup_db


def _set_technology(db: Path, name: str) -> None:
    cfg_path = db / "project_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg["technology"] = {"name": name}
    cfg_path.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


# ── Database Mode ─────────────────────────────────────────────────────────────

def test_database_run_surfaces_pdk_not_installed_warning(tmp_path):
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        _set_technology(db, "sky130")
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
        with _patch_tools(), patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        warnings = result.data.get("warnings") or []
        assert any("VF_TECHNOLOGY_PDK_NOT_INSTALLED" in w for w in warnings)
        # missing PDK does not fail the run -- synthesis still completes
        assert result.data["stages"]["synthesis"]["status"] == "PASS"
    finally:
        shutil.rmtree(tmp)


def test_database_run_generic_technology_has_no_pdk_warning(tmp_path):
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)  # technology defaults to "generic"
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
        with _patch_tools(), patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        warnings = result.data.get("warnings") or []
        assert not any("VF_TECHNOLOGY_PDK_NOT_INSTALLED" in w for w in warnings)
    finally:
        shutil.rmtree(tmp)


# ── Project Mode ──────────────────────────────────────────────────────────────

def test_project_run_surfaces_pdk_not_installed_warning(tmp_path):
    from veriflow.workflows import ProjectWorkflow

    (tmp_path / "top.v").write_text(
        "module top(input a, output b);\nassign b = a;\nendmodule\n", encoding="utf-8"
    )
    (tmp_path / "veriflow.yaml").write_text(
        "design:\n"
        "  top_module: top\n"
        "  rtl_sources:\n"
        "    - top.v\n"
        "technology:\n"
        "  name: sky130\n",
        encoding="utf-8",
    )

    with patch(
        "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
        return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
    ), patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path / "pdks"):
        pr = ProjectWorkflow.from_file(tmp_path / "veriflow.yaml").run()

    import json
    data = json.loads((pr.run_dir / "results.json").read_text(encoding="utf-8"))
    assert any("VF_TECHNOLOGY_PDK_NOT_INSTALLED" in w for w in data["warnings"])
    assert data["stages"]["synthesis"]["status"] == "PASS"
