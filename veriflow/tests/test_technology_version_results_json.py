"""End-to-end checks that a PDK-mapped synthesis run's resolved technology
version reaches the synthesis stage entry of both results.json schemas --
Database Mode (schema_version "1.2") and Project Mode (schema_version
"1.0") -- and is absent for generic (non-PDK-mapped) synthesis. Unit
coverage for the underlying StageResult fields lives in
test_synthesis_technology.py; this file only checks the field survives the
trip through _finalize_run (Database Mode) / _stage_entry (Project Mode).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from veriflow.models.pdk_manager import _create_pdk_link
from veriflow.tests.test_database_workflow import _patch_tools, _setup_db

_SKY130_VERSION = "0fe599b2afb6708d281543108caf8310912f54af"


def _install_fake_sky130(pdk_root: Path) -> None:
    """Set up a minimal but real sky130 install under *pdk_root* -- real
    enough that both get_liberty_path and get_installed_pdk_version resolve
    against it (liberty file present, and the pdk_subdir link/junction
    actually points at the versioned extraction directory)."""
    lib_dir = pdk_root / "sky130" / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    src = pdk_root / "sky130" / "volare" / "sky130" / "versions" / _SKY130_VERSION / "sky130A"
    src.mkdir(parents=True)
    (src / "libs.ref" / "sky130_fd_sc_hd" / "lib").mkdir(parents=True)
    (src / "libs.ref" / "sky130_fd_sc_hd" / "lib" / "sky130_fd_sc_hd__tt_025C_1v80.lib").write_text(
        "", encoding="utf-8"
    )
    link = pdk_root / "sky130" / "sky130A"
    _create_pdk_link(src, link)
    assert lib_dir.exists()  # sanity: the link actually resolves libs.ref through it


def _set_technology(db: Path, name: str) -> None:
    cfg_path = db / "project_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg["technology"] = {"name": name}
    cfg_path.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


# ── Database Mode ─────────────────────────────────────────────────────────────

def test_database_run_includes_technology_version_when_pdk_installed(tmp_path):
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    _install_fake_sky130(tmp_path)
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        _set_technology(db, "sky130")
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
        with _patch_tools(), patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        synth = result.data["stages"]["synthesis"]
        assert synth["technology"] == "sky130"
        assert synth["technology_version"] == _SKY130_VERSION
    finally:
        shutil.rmtree(tmp)


def test_database_run_omits_technology_version_for_generic(tmp_path):
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)  # technology defaults to "generic"
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
        with _patch_tools(), patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
            result = DatabaseWorkflow(db).run_tile("0001", opts)
        synth = result.data["stages"]["synthesis"]
        assert "technology" not in synth
        assert "technology_version" not in synth
    finally:
        shutil.rmtree(tmp)


def test_database_run_omits_technology_version_when_pdk_not_installed(tmp_path):
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_db(tmp)
        _set_technology(db, "sky130")
        opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
        with _patch_tools(), patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path):
            result = DatabaseWorkflow(db).run_tile("0001", opts)  # sky130 not installed under tmp_path
        synth = result.data["stages"]["synthesis"]
        assert "technology" not in synth
        assert "technology_version" not in synth
    finally:
        shutil.rmtree(tmp)


# ── Project Mode ──────────────────────────────────────────────────────────────

def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "top.v").write_text(
        "module top(input a, output b);\nassign b = a;\nendmodule\n", encoding="utf-8"
    )
    config_path = tmp_path / "veriflow.yaml"
    config_path.write_text(
        "design:\n"
        "  top_module: top\n"
        "  rtl_sources:\n"
        "    - top.v\n"
        "technology:\n"
        "  name: sky130\n",
        encoding="utf-8",
    )
    return config_path


def test_project_run_includes_technology_version_when_pdk_installed(tmp_path):
    from veriflow.workflows import ProjectWorkflow

    pdk_root = tmp_path / "pdks"
    _install_fake_sky130(pdk_root)
    config_path = _make_project(tmp_path)

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
        ),
        patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", pdk_root),
    ):
        pr = ProjectWorkflow.from_file(config_path).run()

    data = json.loads((pr.run_dir / "results.json").read_text(encoding="utf-8"))
    synth = data["stages"]["synthesis"]
    assert synth["technology"] == "sky130"
    assert synth["technology_version"] == _SKY130_VERSION


def test_project_run_omits_technology_version_when_pdk_not_installed(tmp_path):
    from veriflow.workflows import ProjectWorkflow

    config_path = _make_project(tmp_path)

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
        ),
        patch("veriflow.models.pdk_manager.VERIFLOW_PDK_ROOT", tmp_path / "pdks"),
    ):
        pr = ProjectWorkflow.from_file(config_path).run()

    data = json.loads((pr.run_dir / "results.json").read_text(encoding="utf-8"))
    synth = data["stages"]["synthesis"]
    assert "technology" not in synth
    assert "technology_version" not in synth


def test_project_run_omits_technology_version_for_generic(tmp_path):
    from veriflow.workflows import ProjectWorkflow

    (tmp_path / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    config_path = tmp_path / "veriflow.yaml"
    config_path.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - top.v\n",
        encoding="utf-8",
    )

    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
        ),
    ):
        pr = ProjectWorkflow.from_file(config_path).run()

    data = json.loads((pr.run_dir / "results.json").read_text(encoding="utf-8"))
    synth = data["stages"]["synthesis"]
    assert "technology" not in synth
    assert "technology_version" not in synth
