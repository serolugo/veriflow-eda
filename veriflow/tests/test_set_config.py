"""Tests for `veriflow project set` / `veriflow db set` / `veriflow db tile
set` (veriflow/commands/set_config.py, veriflow/core/yaml_config_editor.py)
and their veriflow.api counterparts (project_set/db_set/db_tile_set).

Fixtures use the real scaffold generators (render_project_config_yaml(),
init_db.cmd_init, create_tile.cmd_create_tile) rather than hand-typed YAML,
so "comments are preserved" is checked against the actual shipped scaffold
text, not an approximation of it.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from veriflow.core import VeriFlowError
from veriflow.core.project_config_template import render_project_config_yaml


def _write_project_yaml(tmp_path: Path) -> Path:
    config_path = tmp_path / "veriflow.yaml"
    config_path.write_text(render_project_config_yaml(), encoding="utf-8")
    return config_path


def _init_db(tmp_path: Path) -> Path:
    from veriflow.commands.init_db import cmd_init
    from veriflow.commands.set_config import db_set_config

    db = tmp_path / "db"
    cmd_init(db, force=False)
    db_set_config(db, "prefix", "TT")  # create-tile requires id_prefix to be set
    return db


def _create_tile(db: Path, **kwargs) -> str:
    from veriflow.commands.create_tile import cmd_create_tile

    result = cmd_create_tile(db, **kwargs)
    return result["tile_number"]


# ── project set: core logic (project_set_config) ────────────────────────────

def test_project_set_interface_updates_yaml_and_preserves_comments(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    original = config_path.read_text(encoding="utf-8")

    result = project_set_config(config_path, "interface", "semicolab")

    assert result == {"key": "interface", "value": "semicolab", "config": str(config_path)}
    updated = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(updated)
    assert data["interface"] == {"name": "semicolab"}
    # every comment line from the original scaffold is still present verbatim
    for line in original.splitlines():
        if line.strip().startswith("#"):
            assert line in updated


def test_project_set_interface_null_clears_it(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "interface", "semicolab")
    project_set_config(config_path, "interface", "null")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"] is None


def test_project_set_interface_unknown_raises(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        project_set_config(config_path, "interface", "not_a_real_profile")
    assert exc_info.value.code == "VF_SET_INTERFACE_INVALID"


def test_project_set_interface_accepts_existing_v_file_path(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    custom = tmp_path / "custom_if.v"
    custom.write_text("module custom_if(); endmodule\n", encoding="utf-8")

    result = project_set_config(config_path, "interface", str(custom))
    assert result["value"] == str(custom)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"]["name"] == str(custom)


def test_project_set_technology_updates_yaml(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "technology", "sky130")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["technology"] == {"name": "sky130"}


def test_project_set_technology_unknown_raises(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        project_set_config(config_path, "technology", "not_a_real_tech")
    assert exc_info.value.code == "VF_TECHNOLOGY_UNKNOWN"


def test_project_set_top_module_updates_yaml(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "top-module", "counter8")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["design"]["top_module"] == "counter8"
    # rtl_sources (a sibling key already in the same section) survives untouched
    assert data["design"]["rtl_sources"] == []


def test_project_set_pipeline_writes_correct_section(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "pipeline", "connectivity,synthesis")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["pipeline"] == {"stages": [{"type": "connectivity"}, {"type": "synthesis"}]}


def test_project_set_pipeline_invalid_stage_raises(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        project_set_config(config_path, "pipeline", "connectivity,bogus")
    assert exc_info.value.code == "VF_PIPELINE_STAGE_UNKNOWN"


def test_project_set_runs_dir_updates_yaml(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "runs-dir", "my_runs")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["output"]["runs_dir"] == "my_runs"


def test_project_set_unknown_key_raises_with_valid_keys_listed(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        project_set_config(config_path, "unknown_key", "value")
    assert exc_info.value.code == "VF_SET_KEY_UNKNOWN"
    msg = str(exc_info.value)
    for key in ("interface", "technology", "top-module", "pipeline", "runs-dir"):
        assert key in msg


def test_project_set_missing_config_raises(tmp_path):
    from veriflow.commands.set_config import project_set_config

    with pytest.raises(VeriFlowError) as exc_info:
        project_set_config(tmp_path / "does_not_exist.yaml", "technology", "sky130")
    assert exc_info.value.code == "VF_PROJECT_CONFIG_NOT_FOUND"


def test_project_set_result_loads_via_real_config_parser(tmp_path):
    """End-to-end: the file produced by project_set_config is valid enough
    for ProjectWorkflowConfig.from_dict to parse the fields we touched."""
    from veriflow.commands.set_config import project_set_config
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "interface", "semicolab")
    project_set_config(config_path, "technology", "sky130")
    project_set_config(config_path, "pipeline", "connectivity,synthesis")
    project_set_config(config_path, "top-module", "counter8")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw["design"]["rtl_sources"] = ["counter8.v"]
    cfg = ProjectWorkflowConfig.from_dict(raw, root=tmp_path)
    assert cfg.top_module == "counter8"
    assert cfg.interface.name == "semicolab"
    assert cfg.technology.name == "sky130"
    assert [s.type for s in cfg.pipeline.stages] == ["connectivity", "synthesis"]


# ── project set: CLI ─────────────────────────────────────────────────────────

def test_project_set_cli_parses():
    from veriflow.cli import build_parser

    args = build_parser().parse_args(["project", "set", "interface", "semicolab", "--config", "foo.yaml"])
    assert args.command == "project"
    assert args.project_command == "set"
    assert args.key == "interface"
    assert args.value == "semicolab"
    assert args.config == "foo.yaml"


def test_project_set_cli_config_defaults_to_veriflow_yaml():
    from veriflow.cli import build_parser

    args = build_parser().parse_args(["project", "set", "technology", "sky130"])
    assert args.config == "veriflow.yaml"


def test_project_set_cli_dispatches_and_writes_file(tmp_path):
    from veriflow.cli import main

    config_path = _write_project_yaml(tmp_path)
    rc = main(["project", "set", "technology", "sky130", "--config", str(config_path)])
    assert rc == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["technology"] == {"name": "sky130"}


def test_project_set_cli_invalid_value_exits_nonzero(tmp_path, capsys):
    from veriflow.cli import main

    config_path = _write_project_yaml(tmp_path)
    rc = main(["project", "set", "technology", "not_a_real_tech", "--config", str(config_path)])
    assert rc != 0


# ── db set: core logic (db_set_config) ───────────────────────────────────────

def test_db_set_prefix_updates_project_config(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    original = (db / "project_config.yaml").read_text(encoding="utf-8")

    result = db_set_config(db, "prefix", "TT")

    assert result["key"] == "prefix"
    assert result["value"] == "TT"
    updated = (db / "project_config.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(updated)
    assert data["id_prefix"] == "TT"
    for line in original.splitlines():
        if line.strip().startswith("#"):
            assert line in updated


def test_db_set_interface_updates_flat_key(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    db_set_config(db, "interface", "semicolab")
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["interface_name"] == "semicolab"


def test_db_set_interface_unknown_raises(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        db_set_config(db, "interface", "not_a_real_profile")
    assert exc_info.value.code == "VF_SET_INTERFACE_INVALID"


def test_db_set_technology_updates_nested_key(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    db_set_config(db, "technology", "sky130")
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["technology"] == {"name": "sky130"}


def test_db_set_id_format_valid_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    db_set_config(db, "id-format", "{prefix}-{date}{tile_number}")
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["id_format"] == "{prefix}-{date}{tile_number}"


def test_db_set_id_format_unknown_placeholder_raises(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        db_set_config(db, "id-format", "{prefix}-{bogus_placeholder}")
    assert exc_info.value.code == "VF_ID_FORMAT_INVALID"


def test_db_set_shuttle_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    db_set_config(db, "shuttle", "myshuttle")
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["shuttle_name"] == "myshuttle"


def test_db_set_pipeline_writes_correct_section(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    db_set_config(db, "pipeline", "connectivity,synthesis")
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["pipeline"] == {"stages": [{"type": "connectivity"}, {"type": "synthesis"}]}


def test_db_set_unknown_key_raises_with_valid_keys_listed(tmp_path):
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        db_set_config(db, "unknown_key", "value")
    assert exc_info.value.code == "VF_SET_KEY_UNKNOWN"
    msg = str(exc_info.value)
    for key in ("interface", "technology", "id-format", "prefix", "shuttle", "pipeline"):
        assert key in msg


def test_db_set_missing_database_raises(tmp_path):
    from veriflow.commands.set_config import db_set_config

    with pytest.raises(VeriFlowError) as exc_info:
        db_set_config(tmp_path / "no_such_db", "prefix", "TT")
    assert exc_info.value.code == "VF_DB_MISSING_REQUIRED_PATH"


def test_db_set_result_loads_via_real_config_parser(tmp_path):
    from veriflow.commands.set_config import db_set_config
    from veriflow.models.project_config import ProjectConfig

    db = _init_db(tmp_path)
    db_set_config(db, "prefix", "TT")
    db_set_config(db, "interface", "semicolab")
    db_set_config(db, "technology", "sky130")

    raw = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    cfg = ProjectConfig.from_dict(raw, root=db)
    assert cfg.id_prefix == "TT"
    assert cfg.interface_name == "semicolab"
    assert cfg.technology_name == "sky130"


# ── db set: CLI ───────────────────────────────────────────────────────────────

def test_db_set_cli_parses(tmp_path):
    from veriflow.cli import build_parser

    args = build_parser().parse_args(["db", "set", "prefix", "TT", "--db", str(tmp_path)])
    assert args.command == "db"
    assert args.db_command == "set"
    assert args.key == "prefix"
    assert args.value == "TT"
    assert args.db == str(tmp_path)


def test_db_set_cli_dispatches_and_writes_file(tmp_path):
    from veriflow.cli import main

    db = _init_db(tmp_path)
    rc = main(["db", "set", "prefix", "TT", "--db", str(db)])
    assert rc == 0
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["id_prefix"] == "TT"


# ── db tile set: core logic (db_tile_set_config) ─────────────────────────────

def test_db_tile_set_top_module_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db, top_module="counter8_wrapper")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    original = tile_cfg_path.read_text(encoding="utf-8")

    result = db_tile_set_config(db, int(tile_number), "top-module", "counter8_wrapper_v2")

    assert result == {
        "key": "top-module",
        "value": "counter8_wrapper_v2",
        "tile": tile_number,
        "config": str(tile_cfg_path),
    }
    updated = tile_cfg_path.read_text(encoding="utf-8")
    data = yaml.safe_load(updated)
    assert data["top_module"] == "counter8_wrapper_v2"
    for line in original.splitlines():
        if line.strip().startswith("#"):
            assert line in updated


def test_db_tile_set_accepts_string_and_int_tile_number(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    for tile_arg in (tile_number, int(tile_number), "1"):
        result = db_tile_set_config(db, tile_arg, "name", "Counter8")
        assert result["tile"] == tile_number


def test_db_tile_set_name_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    db_tile_set_config(db, tile_number, "name", "Counter8 Wrapper")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["tile_name"] == "Counter8 Wrapper"


def test_db_tile_set_author_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    db_tile_set_config(db, tile_number, "author", "Roman Lugo")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["tile_author"] == "Roman Lugo"


def test_db_tile_set_tb_top_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    db_tile_set_config(db, tile_number, "tb-top", "tb_counter8")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["tb_top_module"] == "tb_counter8"


def test_db_tile_set_tags_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    db_tile_set_config(db, tile_number, "tags", "initial,fix")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["tags"] == "initial,fix"


def test_db_tile_set_objective_updates_yaml(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    db_tile_set_config(db, tile_number, "objective", "verify reset behavior")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["objective"] == "verify reset behavior"


def test_db_tile_set_description_writes_block_scalar(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    db_tile_set_config(db, tile_number, "description", "An 8-bit counter with async reset.")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    text = tile_cfg_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["description"].strip() == "An 8-bit counter with async reset."
    assert "description: |" in text


def test_db_tile_set_pipeline_writes_correct_section(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    db_tile_set_config(db, tile_number, "pipeline", "connectivity,synthesis")
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["pipeline"] == {"stages": [{"type": "connectivity"}, {"type": "synthesis"}]}


def test_db_tile_set_unknown_key_raises(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    with pytest.raises(VeriFlowError) as exc_info:
        db_tile_set_config(db, tile_number, "unknown_key", "value")
    assert exc_info.value.code == "VF_SET_KEY_UNKNOWN"


def test_db_tile_set_nonexistent_tile_raises(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        db_tile_set_config(db, 9999, "name", "value")
    assert exc_info.value.code == "VF_TILE_CONFIG_NOT_FOUND"


def test_db_tile_set_invalid_tile_number_raises(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config

    db = _init_db(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        db_tile_set_config(db, "not_a_number", "name", "value")
    assert exc_info.value.code == "VF_TILE_NUMBER_INVALID"


def test_db_tile_set_result_loads_via_real_config_parser(tmp_path):
    from veriflow.commands.set_config import db_tile_set_config
    from veriflow.models.tile_config import TileConfig

    db = _init_db(tmp_path)
    tile_number = _create_tile(db, top_module="counter8_wrapper")
    db_tile_set_config(db, tile_number, "top-module", "counter8_wrapper")
    db_tile_set_config(db, tile_number, "name", "Counter8 Wrapper")
    db_tile_set_config(db, tile_number, "pipeline", "connectivity,synthesis")

    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    raw = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    cfg = TileConfig.from_dict(raw)
    assert cfg.top_module == "counter8_wrapper"
    assert cfg.tile_name == "Counter8 Wrapper"
    assert [s.type for s in cfg.pipeline.stages] == ["connectivity", "synthesis"]


# ── db tile set: CLI ──────────────────────────────────────────────────────────

def test_db_tile_set_cli_parses(tmp_path):
    from veriflow.cli import build_parser

    args = build_parser().parse_args(
        ["db", "tile", "set", "top-module", "counter8", "--db", str(tmp_path), "--tile", "0001"]
    )
    assert args.command == "db"
    assert args.db_command == "tile"
    assert args.db_tile_command == "set"
    assert args.key == "top-module"
    assert args.value == "counter8"
    assert args.tile == "0001"


def test_db_tile_set_cli_dispatches_and_writes_file(tmp_path):
    from veriflow.cli import main

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    rc = main(["db", "tile", "set", "name", "Counter8", "--db", str(db), "--tile", tile_number])
    assert rc == 0
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["tile_name"] == "Counter8"


def test_db_tile_no_subcommand_returns_error():
    from veriflow.cli import main

    rc = main(["db", "tile"])
    assert rc == 1


def test_db_tile_set_cli_json_mode_reports_nested_command(tmp_path):
    from veriflow.cli import main

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    rc = main(["--json", "db", "tile", "set", "name", "Counter8", "--db", str(db), "--tile", tile_number])
    assert rc == 0


# ── veriflow.api: project_set / db_set / db_tile_set ─────────────────────────

def test_api_project_set_writes_file(tmp_path):
    from veriflow.api import project_set

    config_path = _write_project_yaml(tmp_path)
    result = project_set(config_path, "interface", "semicolab")
    assert result["key"] == "interface"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"]["name"] == "semicolab"


def test_api_project_set_invalid_raises(tmp_path):
    from veriflow.api import project_set

    config_path = _write_project_yaml(tmp_path)
    with pytest.raises(VeriFlowError):
        project_set(config_path, "interface", "not_a_real_profile")


def test_api_db_set_writes_file(tmp_path):
    from veriflow.api import db_set

    db = _init_db(tmp_path)
    result = db_set(db, "prefix", "TT")
    assert result["key"] == "prefix"
    data = yaml.safe_load((db / "project_config.yaml").read_text(encoding="utf-8"))
    assert data["id_prefix"] == "TT"


def test_api_db_tile_set_writes_file(tmp_path):
    from veriflow.api import db_tile_set

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    result = db_tile_set(db, int(tile_number), "top-module", "counter8_wrapper")
    assert result["tile"] == tile_number
    tile_cfg_path = db / "config" / f"tile_{tile_number}" / "tile_config.yaml"
    data = yaml.safe_load(tile_cfg_path.read_text(encoding="utf-8"))
    assert data["top_module"] == "counter8_wrapper"


def test_api_db_tile_set_accepts_string_paths(tmp_path):
    from veriflow.api import db_tile_set

    db = _init_db(tmp_path)
    tile_number = _create_tile(db)
    result = db_tile_set(str(db), tile_number, "name", "Counter8")
    assert result["tile"] == tile_number


# ── yaml_config_editor: ruamel path (active when ruamel.yaml is installed) ──

_HAS_RUAMEL = __import__("veriflow.core.yaml_config_editor", fromlist=["HAS_RUAMEL"]).HAS_RUAMEL


@pytest.mark.skipif(not _HAS_RUAMEL, reason="ruamel.yaml not installed in this environment")
def test_yaml_editor_ruamel_updates_existing_key_in_place(tmp_path):
    from veriflow.core.yaml_config_editor import set_yaml_key

    path = tmp_path / "config.yaml"
    path.write_text("a: 1  # keep me\nb: 2\n", encoding="utf-8")
    set_yaml_key(path, ("a",), 99)
    text = path.read_text(encoding="utf-8")
    assert "a: 99" in text
    assert "# keep me" in text
    assert "b: 2" in text


@pytest.mark.skipif(not _HAS_RUAMEL, reason="ruamel.yaml not installed in this environment")
def test_yaml_editor_ruamel_appends_new_key(tmp_path):
    from veriflow.core.yaml_config_editor import set_yaml_key

    path = tmp_path / "config.yaml"
    path.write_text("# a commented example\n# c: 3\na: 1\n", encoding="utf-8")
    set_yaml_key(path, ("c",), 3)
    text = path.read_text(encoding="utf-8")
    assert "# a commented example" in text
    assert "# c: 3" in text  # original commented example untouched
    assert "a: 1" in text
    data = yaml.safe_load(text)
    assert data["c"] == 3


@pytest.mark.skipif(not _HAS_RUAMEL, reason="ruamel.yaml not installed in this environment")
def test_yaml_editor_ruamel_null_value(tmp_path):
    from veriflow.core.yaml_config_editor import set_yaml_key

    path = tmp_path / "config.yaml"
    path.write_text("a: foo\n", encoding="utf-8")
    set_yaml_key(path, ("a",), None)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["a"] is None


# ── yaml_config_editor: text-patch fallback (no ruamel.yaml) ─────────────────

def test_yaml_editor_fallback_updates_existing_top_level_key(tmp_path):
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text('id_prefix: ""\nother: 1\n', encoding="utf-8")
    _set_yaml_key_fallback(path, ("id_prefix",), "TT", block_scalar=False)
    text = path.read_text(encoding="utf-8")
    assert 'id_prefix: "TT"' in text
    assert "other: 1" in text


def test_yaml_editor_fallback_inserts_new_nested_key(tmp_path):
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text("design:\n  top_module: \"\"\n\n# interface:\n#   name: \"\"\n", encoding="utf-8")
    _set_yaml_key_fallback(path, ("interface", "name"), "semicolab", block_scalar=False)
    text = path.read_text(encoding="utf-8")
    assert "# interface:" in text  # original commented example untouched
    assert "interface:\n  name: \"semicolab\"" in text
    data = yaml.safe_load(text)
    assert data["interface"]["name"] == "semicolab"
    assert data["design"]["top_module"] == ""


def test_yaml_editor_fallback_updates_existing_nested_key(tmp_path):
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text("design:\n  top_module: \"old\"\n  rtl_sources: []\n", encoding="utf-8")
    _set_yaml_key_fallback(path, ("design", "top_module"), "new", block_scalar=False)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["design"]["top_module"] == "new"
    assert data["design"]["rtl_sources"] == []


def test_yaml_editor_fallback_block_scalar(tmp_path):
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text("description: |\n  # placeholder\n\nother: 1\n", encoding="utf-8")
    _set_yaml_key_fallback(path, ("description",), "Multi\nline\ntext", block_scalar=True)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["description"].strip() == "Multi\nline\ntext"
    assert data["other"] == 1


def test_yaml_editor_fallback_pipeline_appends_new_section(tmp_path):
    from veriflow.core.yaml_config_editor import _set_yaml_pipeline_fallback

    path = tmp_path / "config.yaml"
    path.write_text("# pipeline:\n#   stages:\n#     - type: connectivity\nid_prefix: \"\"\n", encoding="utf-8")
    _set_yaml_pipeline_fallback(path, [{"type": "connectivity"}, {"type": "synthesis"}])
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["pipeline"]["stages"] == [{"type": "connectivity"}, {"type": "synthesis"}]
    assert "# pipeline:" in text


def test_yaml_editor_fallback_pipeline_replaces_existing_section(tmp_path):
    from veriflow.core.yaml_config_editor import _set_yaml_pipeline_fallback

    path = tmp_path / "config.yaml"
    path.write_text(
        "id_prefix: \"\"\npipeline:\n  stages:\n    - type: connectivity\n    - type: simulation\nshuttle_name: \"x\"\n",
        encoding="utf-8",
    )
    _set_yaml_pipeline_fallback(path, [{"type": "synthesis"}])
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["pipeline"]["stages"] == [{"type": "synthesis"}]
    assert data["id_prefix"] == ""
    assert data["shuttle_name"] == "x"


def test_project_set_uses_fallback_when_ruamel_unavailable(tmp_path):
    """Force the no-ruamel code path (monkeypatching HAS_RUAMEL) and confirm
    project_set_config still produces valid, comment-preserving output."""
    config_path = _write_project_yaml(tmp_path)
    original = config_path.read_text(encoding="utf-8")

    with patch("veriflow.core.yaml_config_editor.HAS_RUAMEL", False):
        from veriflow.commands.set_config import project_set_config

        project_set_config(config_path, "interface", "semicolab")

    updated = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(updated)
    assert data["interface"]["name"] == "semicolab"
    for line in original.splitlines():
        if line.strip().startswith("#"):
            assert line in updated
