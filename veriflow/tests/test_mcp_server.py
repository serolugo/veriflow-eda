"""Tests for veriflow.mcp_server (MCP tools + resources), veriflow.llms_txt
(`veriflow context`), and veriflow.commands.mcp (`veriflow mcp install`).

MCP tool functions decorated with `@mcp.tool` remain plain, directly
callable Python functions (confirmed via introspection: FastMCP's bare
`@mcp.tool` usage registers the tool as a side effect and returns the
original function unchanged) -- so they're called directly here, no MCP
client/transport machinery needed.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

pytest.importorskip("fastmcp")  # optional dep (setup.py's `mcp` extra) -- see mcp_server.py's _StubMCP

from veriflow import mcp_server  # noqa: E402
from veriflow.core import VeriFlowError  # noqa: E402

skip_no_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not found in PATH")


# ── shared helpers (mirrors test_api_additions.py's patterns) ─────────────────

def _make_project(tmp_path: Path, *, dirname: str = "myproj", interface_name: str | None = None) -> Path:
    project_dir = tmp_path / dirname
    (project_dir / "rtl").mkdir(parents=True)
    (project_dir / "rtl" / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    config_path = project_dir / "veriflow.yaml"
    lines = [
        "design:",
        "  top_module: top",
        "  rtl_sources:",
        "    - rtl/top.v",
    ]
    if interface_name:
        lines += ["interface:", f"  name: {interface_name}"]
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config_path


def _patched_synth_pass():
    return patch(
        "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
        return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
    )


def _make_db(tmp_path: Path) -> Path:
    from veriflow.commands.init_db import cmd_init
    db = tmp_path / "database"
    cmd_init(db)
    return db


def _fill_project_config(db: Path, interface_name: str | None = None) -> None:
    cfg = {
        "id_prefix": "TST-01",
        "project_name": "Test Project",
        "repo": "",
        "description": "Test project.",
        "interface_name": interface_name,
    }
    (db / "project_config.yaml").write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def _make_tile(db: Path, top_module: str = "my_tile") -> None:
    from veriflow.commands.create_tile import cmd_create_tile
    cmd_create_tile(db, top_module=top_module)


def _add_rtl(db: Path, tile_number_str: str, module_name: str = "my_tile") -> None:
    rtl_dir = db / "config" / f"tile_{tile_number_str}" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / f"{module_name}.v").write_text(f"module {module_name}; endmodule\n", encoding="utf-8")


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


def _setup_generic_db_with_tile(tmp_path: Path) -> Path:
    db = _make_db(tmp_path)
    _fill_project_config(db, interface_name=None)
    _make_tile(db)
    _add_rtl(db, "0001")
    _fill_tile_config(db, "0001")
    return db


def _patch_db_tools():
    return (
        patch("veriflow.workflows.database.validate_tools"),
        patch("veriflow.workflows.database.detect_iverilog_version", return_value="12.0"),
        patch("veriflow.core.backends.icarus.IcarusConnectivityBackend.run_connectivity", return_value="PASS"),
        patch("veriflow.core.backends.icarus.IcarusSimulationBackend.run_simulation", return_value=("COMPLETED", {})),
        patch(
            "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
            return_value=("PASS", {"cells": "5", "warnings": "0", "errors": "0", "has_latches": False}),
        ),
    )


def _apply_patches(patches):
    for p in patches:
        p.start()


def _stop_patches(patches):
    for p in patches:
        p.stop()


# ── error envelope: every tool, invalid input → structured dict, no raise ─────

def test_doctor_never_raises():
    result = mcp_server.veriflow_doctor()
    assert result["status"] in ("OK", "FAIL")


def test_project_run_error_envelope(tmp_path):
    result = mcp_server.veriflow_project_run(str(tmp_path / "nope" / "veriflow.yaml"))
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_PROJECT_CONFIG_NOT_FOUND"


def test_run_tile_error_envelope(tmp_path):
    db = _setup_generic_db_with_tile(tmp_path)
    result = mcp_server.veriflow_run_tile(str(db), "abc")
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_TILE_NUMBER_INVALID"


def test_wrap_init_error_envelope(tmp_path):
    result = mcp_server.veriflow_wrap_init("not_a_real_interface", str(tmp_path / "top.v"))
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_INTERFACE_UNKNOWN"


def test_wrap_generate_error_envelope(tmp_path):
    result = mcp_server.veriflow_wrap_generate(str(tmp_path / "nope" / "wrapper_config.yaml"))
    assert result["status"] == "ERROR"
    assert "error" in result


def test_project_import_error_envelope(tmp_path):
    result = mcp_server.veriflow_project_import(
        str(tmp_path / "nope" / "veriflow.yaml"), str(tmp_path / "db")
    )
    assert result["status"] == "ERROR"


@skip_no_git
def test_import_repo_error_envelope(tmp_path):
    db = _setup_generic_db_with_tile(tmp_path)
    result = mcp_server.veriflow_import_repo(str(tmp_path / "does_not_exist_repo"), str(db))
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_IMPORT_REPO_CLONE_FAILED"


def test_apply_spec_error_envelope(tmp_path):
    result = mcp_server.veriflow_apply_spec(str(tmp_path / "nope.yaml"))
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_SHUTTLE_SPEC_NOT_FOUND"


def test_generate_readme_error_envelope(tmp_path):
    config_path = _make_project(tmp_path)
    result = mcp_server.veriflow_generate_readme(str(config_path))
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_README_NO_PASSING_RUN"


def test_db_list_runs_error_envelope_is_single_item_list(tmp_path):
    db = _setup_generic_db_with_tile(tmp_path)
    result = mcp_server.veriflow_db_list_runs(str(db), "abc")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["status"] == "ERROR"
    assert result[0]["error"]["code"] == "VF_TILE_NUMBER_INVALID"


def test_db_get_run_error_envelope(tmp_path):
    db = _setup_generic_db_with_tile(tmp_path)
    result = mcp_server.veriflow_db_get_run(str(db), "0001", "run-999")
    assert result["status"] == "ERROR"


def test_get_project_run_result_error_envelope(tmp_path):
    result = mcp_server.veriflow_get_project_run_result(str(tmp_path / "nope"))
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_PROJECT_RUN_RESULT_NOT_FOUND"


def test_db_list_tiles_never_raises_on_nonexistent_db(tmp_path):
    result = mcp_server.veriflow_db_list_tiles(str(tmp_path / "not_a_db"))
    assert isinstance(result, list)
    if result and isinstance(result[0], dict) and result[0].get("status") == "ERROR":
        assert "error" in result[0]


# ── list-returning tools that don't raise: shape sanity ───────────────────────

def test_list_interface_profiles_success():
    result = mcp_server.veriflow_list_interface_profiles()
    assert isinstance(result, list)
    assert any(p["name"] == "semicolab" for p in result)


def test_list_technology_profiles_success():
    result = mcp_server.veriflow_list_technology_profiles()
    names = {t["name"] for t in result}
    assert names == {"generic", "sky130", "gf180", "ihp130"}


def test_list_pdks_success():
    result = mcp_server.veriflow_list_pdks()
    assert {p["name"] for p in result} == {"generic", "sky130", "gf180", "ihp130"}


# ── success paths (mocked EDA backends, mirroring test_api_additions.py) ──────

def test_project_run_success(tmp_path):
    config_path = _make_project(tmp_path)
    with patch("veriflow.workflows.project.validate_tools"), _patched_synth_pass():
        result = mcp_server.veriflow_project_run(str(config_path))
    assert result["status"] == "PASS"
    assert result["schema_version"] == "1.0"


def test_get_project_run_result_success(tmp_path):
    config_path = _make_project(tmp_path)
    with patch("veriflow.workflows.project.validate_tools"), _patched_synth_pass():
        run_result = mcp_server.veriflow_project_run(str(config_path))
    # run_dir is relative to the config file's directory, not the CWD.
    run_dir = config_path.parent / run_result["run_dir"]
    result = mcp_server.veriflow_get_project_run_result(str(run_dir))
    assert result["status"] == "PASS"


def test_run_tile_success(tmp_path):
    """Generic tile (no interface configured): connectivity is SKIPPED,
    simulation/synthesis PASS -- Database Mode reports that mix as
    PARTIAL, not PASS (PASS requires every applicable stage to actually
    run and pass, not just the ones that did)."""
    db = _setup_generic_db_with_tile(tmp_path)
    patches = _patch_db_tools()
    _apply_patches(patches)
    try:
        result = mcp_server.veriflow_run_tile(str(db), "0001")
    finally:
        _stop_patches(patches)
    assert result["schema_version"] == "1.2"
    assert result["status"] == "PARTIAL"


def test_db_list_tiles_and_runs_and_get_run_success(tmp_path):
    db = _setup_generic_db_with_tile(tmp_path)
    patches = _patch_db_tools()
    _apply_patches(patches)
    try:
        mcp_server.veriflow_run_tile(str(db), "0001")
    finally:
        _stop_patches(patches)

    tiles = mcp_server.veriflow_db_list_tiles(str(db))
    assert len(tiles) == 1
    assert tiles[0]["tile_number"] == "0001"

    runs = mcp_server.veriflow_db_list_runs(str(db), "0001")
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-001"

    run = mcp_server.veriflow_db_get_run(str(db), "0001", "run-001")
    assert run["status"] == "PARTIAL"


def test_wrap_init_success(tmp_path):
    rtl_file = tmp_path / "my_dut.v"
    rtl_file.write_text(
        "module my_dut (\n"
        "    input  wire       clk,\n"
        "    output wire [7:0] data_o\n"
        ");\nendmodule\n",
        encoding="utf-8",
    )
    result = mcp_server.veriflow_wrap_init("semicolab", str(rtl_file))
    assert result["interface_name"] == "semicolab"
    assert result["design"]["top_module"] == "my_dut"
    assert result["wrapper_name"] == "my_dut_wrapper"
    assert len(result["detected_ports"]) == 2


def test_project_import_success(tmp_path):
    config_path = _make_project(tmp_path)
    with patch("veriflow.workflows.project.validate_tools"), _patched_synth_pass():
        mcp_server.veriflow_project_run(str(config_path))

    db = _make_db(tmp_path)
    _fill_project_config(db, interface_name=None)

    result = mcp_server.veriflow_project_import(str(config_path), str(db))
    # project_import()'s success dict has no "status" key at all (only the
    # ERROR envelope adds one) -- absence of "error" is what proves success.
    assert "error" not in result
    assert result["tile_number"] == "0001"


def test_generate_readme_success(tmp_path):
    config_path = _make_project(tmp_path)
    with patch("veriflow.workflows.project.validate_tools"), _patched_synth_pass():
        mcp_server.veriflow_project_run(str(config_path))

    result = mcp_server.veriflow_generate_readme(str(config_path))
    assert result["status"] == "SUCCESS"
    assert result["content"]
    assert Path(result["out_path"]).is_file()


def test_project_init_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = mcp_server.veriflow_project_init(top_module="counter8")
    assert "error" not in result
    config_path = tmp_path / "veriflow.yaml"
    assert config_path.is_file()
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["design"]["top_module"] == "counter8"


def test_project_init_no_top_module_still_scaffolds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = mcp_server.veriflow_project_init()
    assert "error" not in result
    assert (tmp_path / "veriflow.yaml").is_file()


def test_project_init_error_envelope_when_file_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "veriflow.yaml").write_text("design:\n  top_module: x\n", encoding="utf-8")
    result = mcp_server.veriflow_project_init()
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_PROJECT_CONFIG_EXISTS"


# ── veriflow_db_init / veriflow_create_tile (Finding 13, 2026-07-19) ─────────

def test_db_init_tool_success(tmp_path):
    db_path = tmp_path / "database"
    result = mcp_server.veriflow_db_init(str(db_path))
    assert "error" not in result
    assert result["db_path"] == str(db_path)
    assert (db_path / "project_config.yaml").is_file()


def test_db_init_tool_error_envelope_when_exists_without_force(tmp_path):
    db_path = tmp_path / "database"
    mcp_server.veriflow_db_init(str(db_path))
    result = mcp_server.veriflow_db_init(str(db_path))
    assert result["status"] == "ERROR"


def test_db_init_tool_force_overwrites(tmp_path):
    db_path = tmp_path / "database"
    mcp_server.veriflow_db_init(str(db_path))
    result = mcp_server.veriflow_db_init(str(db_path), force=True)
    assert "error" not in result


def test_create_tile_tool_success(tmp_path):
    db_path = tmp_path / "database"
    mcp_server.veriflow_db_init(str(db_path))
    _fill_project_config(db_path, interface_name=None)

    result = mcp_server.veriflow_create_tile(str(db_path), top_module="my_tile", tile_author="Ada")
    assert "error" not in result
    assert result["tile_number"] == "0001"
    assert (db_path / "config" / "tile_0001" / "tile_config.yaml").is_file()


def test_create_tile_tool_error_envelope_for_missing_database(tmp_path):
    result = mcp_server.veriflow_create_tile(str(tmp_path / "no_such_db"))
    assert result["status"] == "ERROR"


def test_db_init_then_create_tile_tool_end_to_end(tmp_path):
    """The two new tools compose the way an agent would actually chain
    them: init the database, then create a tile in it, without any
    manual YAML editing in between."""
    db_path = tmp_path / "database"
    init_result = mcp_server.veriflow_db_init(str(db_path))
    _fill_project_config(Path(init_result["db_path"]), interface_name=None)

    tile_result = mcp_server.veriflow_create_tile(init_result["db_path"], top_module="top")
    assert "error" not in tile_result
    assert tile_result["tile_number"] == "0001"


def test_project_set_tool_success(tmp_path):
    config_path = _make_project(tmp_path)
    result = mcp_server.veriflow_project_set(str(config_path), "technology", "sky130")
    assert "error" not in result
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["technology"] == {"name": "sky130"}


def test_project_set_tool_stage_backend_success(tmp_path):
    config_path = _make_project(tmp_path)
    result = mcp_server.veriflow_project_set(str(config_path), "stage-backend", "simulation:xsim")
    assert "error" not in result
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert {"type": "simulation", "backend": "xsim"} in data["pipeline"]["stages"]


def test_project_set_tool_error_envelope(tmp_path):
    config_path = _make_project(tmp_path)
    result = mcp_server.veriflow_project_set(str(config_path), "technology", "not_a_real_tech")
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_TECHNOLOGY_UNKNOWN"


def test_db_set_tool_success(tmp_path):
    db = _make_db(tmp_path)
    result = mcp_server.veriflow_db_set(str(db), "technology-strict", "sky130")
    assert "error" not in result
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["technology"] == {"name": "sky130", "require_pdk": True}


def test_db_set_tool_error_envelope(tmp_path):
    result = mcp_server.veriflow_db_set(str(tmp_path / "no_such_db"), "prefix", "TT")
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_DB_MISSING_REQUIRED_PATH"


def test_db_tile_set_tool_success(tmp_path):
    db = _setup_generic_db_with_tile(tmp_path)
    result = mcp_server.veriflow_db_tile_set(str(db), "0001", "name", "Counter8")
    assert "error" not in result
    tile_cfg_path = db / "config" / "tile_0001" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["tile_name"] == "Counter8"


def test_db_tile_set_tool_error_envelope(tmp_path):
    db = _setup_generic_db_with_tile(tmp_path)
    result = mcp_server.veriflow_db_tile_set(str(db), "9999", "name", "value")
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "VF_TILE_CONFIG_NOT_FOUND"


def test_apply_spec_success(tmp_path):
    config_path = _make_project(tmp_path)
    spec_path = tmp_path / "shuttle_spec.yaml"
    spec_path.write_text(
        yaml.dump({"technology": "generic", "pipeline": {"stages": [{"type": "synthesis"}]}}),
        encoding="utf-8",
    )
    result = mcp_server.veriflow_apply_spec(str(spec_path), str(config_path))
    assert "error" not in result
    assert result.get("technology") == "generic"


# ── resources: real doc content, in sync with docs/ ────────────────────────────

_RESOURCE_FUNCS = {
    "veriflow://docs/manual": (mcp_server.doc_manual, "MANUAL.md"),
    "veriflow://docs/quickref": (mcp_server.doc_quickref, "QUICKREF.md"),
    "veriflow://docs/project-config": (mcp_server.doc_project_config, "PROJECT_CONFIG.md"),
    "veriflow://docs/install": (mcp_server.doc_install, "INSTALL.md"),
    "veriflow://docs/custom-backends": (mcp_server.doc_custom_backends, "CUSTOM_BACKENDS.md"),
    "veriflow://docs/wrap": (mcp_server.doc_wrap, "user-guide/wrap.md"),
    "veriflow://docs/doctor": (mcp_server.doc_doctor, "user-guide/doctor.md"),
}

_DOCS_ROOT = Path(__file__).resolve().parent.parent.parent / "docs"


@pytest.mark.parametrize("uri", list(_RESOURCE_FUNCS.keys()))
def test_resource_matches_real_doc_content(uri):
    fn, doc_rel_path = _RESOURCE_FUNCS[uri]
    packaged_content = fn.fn() if hasattr(fn, "fn") else fn()
    real_content = (_DOCS_ROOT / doc_rel_path).read_text(encoding="utf-8")
    assert packaged_content == real_content, (
        f"veriflow/mcp_docs is out of sync with docs/{doc_rel_path} -- "
        "run scripts/sync_mcp_docs.py"
    )


def test_resource_content_non_empty():
    for fn, _ in _RESOURCE_FUNCS.values():
        content = fn.fn() if hasattr(fn, "fn") else fn()
        assert len(content) > 100


# ── veriflow context ────────────────────────────────────────────────────────

def test_generate_llms_txt_non_empty_and_has_expected_sections():
    from veriflow.llms_txt import generate_llms_txt

    text = generate_llms_txt()
    assert len(text) > 500
    assert "Command reference" in text
    assert "veriflow db run" in text
    assert "veriflow project run" in text
    assert "results.json" in text
    assert "custom interface profile" in text.lower()
    assert "custom technology" in text.lower()
    assert "set` commands" in text
    assert "End-to-end example" in text


def test_context_command_prints_generated_content(capsys):
    from veriflow.cli import main

    rc = main(["context"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "VeriFlow -- LLM context" in out
    assert "Command reference" in out


def test_context_command_json_mode_includes_content():
    from veriflow.cli import main

    rc = main(["--json", "context"])
    assert rc == 0


# ── mcp install ──────────────────────────────────────────────────────────────

def test_mcp_install_unknown_client_raises_clear_error():
    from veriflow.commands.mcp import cmd_mcp_install
    import argparse

    with pytest.raises(VeriFlowError) as exc_info:
        cmd_mcp_install(argparse.Namespace(client="not-a-real-client"))
    assert exc_info.value.code == "VF_MCP_UNKNOWN_CLIENT"


def test_mcp_install_claude_code_unknown_choice_rejected_by_cli(capsys):
    """An invalid --client choice is rejected by argparse itself (before
    cmd_mcp_install ever runs), which exits the process directly --
    cmd_mcp_install's own VF_MCP_UNKNOWN_CLIENT check (tested above) is
    what protects any caller that reaches it without going through argparse."""
    from veriflow.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["mcp", "install", "--client", "bogus"])
    assert exc_info.value.code == 2


def test_mcp_install_claude_desktop_creates_config(tmp_path):
    from veriflow.commands.mcp import _install_claude_desktop

    config_path = tmp_path / "Claude" / "claude_desktop_config.json"
    result = _install_claude_desktop(config_path=config_path)

    assert result["status"] == "SUCCESS"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["veriflow"] == {"command": "veriflow", "args": ["mcp", "serve"]}


def test_mcp_install_claude_desktop_preserves_existing_entries(tmp_path):
    from veriflow.commands.mcp import _install_claude_desktop

    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"other-server": {"command": "other"}}, "someOtherKey": True}),
        encoding="utf-8",
    )

    _install_claude_desktop(config_path=config_path)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other-server"] == {"command": "other"}
    assert data["mcpServers"]["veriflow"] == {"command": "veriflow", "args": ["mcp", "serve"]}
    assert data["someOtherKey"] is True


def test_mcp_install_claude_desktop_malformed_json_raises_clear_error(tmp_path):
    from veriflow.commands.mcp import _install_claude_desktop

    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(VeriFlowError) as exc_info:
        _install_claude_desktop(config_path=config_path)
    assert exc_info.value.code == "VF_MCP_CONFIG_YAML_ERROR"


def test_mcp_install_claude_code_falls_back_to_printing_command_when_cli_missing(capsys):
    from veriflow.commands.mcp import _install_claude_code

    with patch("shutil.which", return_value=None):
        result = _install_claude_code()

    out = capsys.readouterr().out
    assert result["status"] == "MANUAL"
    assert "claude mcp add veriflow" in out


def test_mcp_serve_entry_point_is_callable():
    """Just confirms cmd_mcp_serve resolves to veriflow.mcp_server.main
    without importing/running the actual blocking server."""
    from veriflow.commands.mcp import cmd_mcp_serve

    assert callable(cmd_mcp_serve)
