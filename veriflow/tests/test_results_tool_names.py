"""Regression tests for Step 6 of the 2026-07-14 interfaces/technologies
migration: Database Mode's results.json / manifest.yaml must report tool
names read from the actual resolved backend, not hardcoded literal strings
(dev-docs/INTERFACES_TECH_AUDIT.md, finding #3: "iverilog"/"yosys" were
independently hardcoded in workflows/database.py and generators/manifest.py).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml


def _make_db(tmp: Path) -> Path:
    db = tmp / "database"
    from veriflow.commands.init_db import cmd_init
    cmd_init(db)
    return db


def _make_tile(db: Path, top_module: str = "my_tile") -> None:
    from veriflow.commands.create_tile import cmd_create_tile
    cmd_create_tile(db, top_module=top_module)


def _fill_project_config(db: Path) -> None:
    cfg = {
        "id_prefix": "TST-01",
        "project_name": "Test Project",
        "repo": "https://github.com/test/test",
        "description": "Test project.",
        "interface_name": None,
    }
    (db / "project_config.yaml").write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def _add_rtl(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
    rtl_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / f"{module_name}.v").write_text(
        f"module {module_name} (input wire clk);\nendmodule\n", encoding="utf-8"
    )


def _fill_tile_config(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
    cfg_path = db / "config" / f"tile_{tile_number_str}" / "tile_config.yaml"
    cfg = {
        "tile_name": "Test Tile",
        "tile_author": "Tester",
        "top_module": module_name,
        "description": "A test tile.",
        "ports": "Standard ports.",
        "usage_guide": "Just run it.",
        "tb_description": "Basic TB.",
        "run_author": "Tester",
        "objective": "Test run",
        "tags": "test",
        "main_change": "Initial.",
        "notes": "No notes.",
    }
    cfg_path.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def _setup_synth_only_db(tmp: Path) -> Path:
    db = _make_db(tmp)
    _fill_project_config(db)
    _make_tile(db)
    _add_rtl(db, "0001", "my_tile")
    _fill_tile_config(db, "0001", "my_tile")
    return db


def _run_synth_only(db: Path):
    from veriflow.workflows.database import DatabaseRunOptions, DatabaseWorkflow

    opts = DatabaseRunOptions(skip_connectivity=True, skip_sim=True)
    with (
        patch("veriflow.workflows.database.validate_tools"),
        patch("veriflow.workflows.database.detect_iverilog_version", return_value="12.0"),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("PASS", {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False}),
        ),
    ):
        return DatabaseWorkflow(db).run_tile("0001", opts)


def test_results_json_synthesis_tool_name_reflects_registry_not_a_literal():
    """Patch get_synthesis_tool_name itself to return a sentinel; the
    sentinel must appear in the actual results.json -- proving the value is
    read dynamically, since a hardcoded literal could never become it."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_synth_only_db(tmp)
        with patch("veriflow.workflows.database.get_synthesis_tool_name", return_value="SENTINEL_TOOL_NAME"):
            result = _run_synth_only(db)
        assert result.data["stages"]["synthesis"]["tool"] == "SENTINEL_TOOL_NAME"

        results_path = db / "tiles" / result.tile_id / "runs" / result.run_id / "results.json"
        on_disk = json.loads(results_path.read_text(encoding="utf-8"))
        assert on_disk["stages"]["synthesis"]["tool"] == "SENTINEL_TOOL_NAME"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_manifest_yaml_synthesizer_reflects_registry_not_a_literal():
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_synth_only_db(tmp)
        with patch("veriflow.workflows.database.get_synthesis_tool_name", return_value="SENTINEL_TOOL_NAME"):
            result = _run_synth_only(db)

        manifest_path = db / "tiles" / result.tile_id / "runs" / result.run_id / "manifest.yaml"
        manifest_text = manifest_path.read_text(encoding="utf-8")
        assert "SENTINEL_TOOL_NAME" in manifest_text
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_results_json_default_tool_names_match_current_backends():
    """With no patch on the tool-name registry, defaults stay exactly what
    they were before the migration -- 0 behavior change for today's only
    registered backends (icarus/yosys)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db = _setup_synth_only_db(tmp)
        result = _run_synth_only(db)
        assert result.data["stages"]["synthesis"]["tool"] == "yosys"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_get_tool_name_functions_fall_back_to_backend_id_for_unmapped():
    """A backend ID not in the display-name table falls back to itself
    instead of raising -- forward-compatible with a future backend that
    hasn't registered a display name yet."""
    from veriflow.core.backends.registry import (
        get_connectivity_tool_name,
        get_simulation_tool_name,
        get_synthesis_tool_name,
    )
    assert get_connectivity_tool_name("some_future_backend") == "some_future_backend"
    assert get_simulation_tool_name("some_future_backend") == "some_future_backend"
    assert get_synthesis_tool_name("some_future_backend") == "some_future_backend"


def test_get_tool_name_functions_known_mappings():
    from veriflow.core.backends.registry import (
        get_connectivity_tool_name,
        get_simulation_tool_name,
        get_synthesis_tool_name,
    )
    assert get_connectivity_tool_name("icarus") == "iverilog"
    assert get_simulation_tool_name("icarus") == "iverilog/vvp"
    assert get_synthesis_tool_name("yosys") == "yosys"
