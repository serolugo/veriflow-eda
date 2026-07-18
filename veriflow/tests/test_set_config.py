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
    # comment lines belonging to *other* sections are still present verbatim --
    # only the "# interface:" / "#   name: ..." placeholder itself is
    # uncommented in place (see test_project_set_interface_uncomments_existing_
    # commented_section_in_place below), not appended as a second copy.
    for line in original.splitlines():
        if line.strip().startswith("#") and "interface" not in line and "name:" not in line:
            assert line in updated
    assert updated.count("interface:") == 1


def test_project_set_interface_uncomments_existing_commented_section_in_place(tmp_path):
    """The scaffold ships `interface:` commented out (`# interface:\\n#   name:
    ""`). Setting it must uncomment and update that existing placeholder in
    place, not append a second, active `interface:` section at the end of
    the file."""
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    original = config_path.read_text(encoding="utf-8")
    assert "# interface:" in original  # sanity: scaffold ships it commented out

    project_set_config(config_path, "interface", "semicolab")

    updated = config_path.read_text(encoding="utf-8")
    assert "# interface:" not in updated
    # uncommented in place -- not appended as a new section at the end
    lines = updated.splitlines()
    interface_idx = next(i for i, l in enumerate(lines) if l == "interface:")
    assert interface_idx < len(lines) - 5
    data = yaml.safe_load(updated)
    assert data["interface"] == {"name": "semicolab"}


def test_project_set_does_not_duplicate_section_when_active_copy_exists_elsewhere(tmp_path):
    """Regression: a yaml with an *active* `interface:` section (e.g.
    appended below the scaffold's still-present `# interface:` commented
    placeholder, as any file written before the 2026-07-18
    uncomment-in-place fix would look) must update that one active
    section in place -- not uncomment the stale placeholder into a
    *second*, duplicate `interface:` section."""
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    original = config_path.read_text(encoding="utf-8")
    assert "# interface:" in original  # sanity: scaffold's placeholder is still there

    # Simulate an active section coexisting with the untouched commented
    # placeholder (append it directly, bypassing set_yaml_key entirely).
    with config_path.open("a", encoding="utf-8") as f:
        f.write("\ninterface:\n  name: semicolab\n")

    project_set_config(config_path, "interface", "null")

    updated = config_path.read_text(encoding="utf-8")
    active_lines = [line for line in updated.splitlines() if line.startswith("interface:")]
    assert len(active_lines) == 1, f"expected exactly one active 'interface:' line, got: {active_lines!r}"
    assert active_lines == ["interface: null"]
    data = yaml.safe_load(updated)
    assert data["interface"] is None


def test_db_set_does_not_duplicate_nested_section_when_active_copy_exists_elsewhere(tmp_path):
    """Same regression as above, for a nested key (`technology.name`) and
    a different command (`db set`)."""
    from veriflow.commands.set_config import db_set_config

    db = _init_db(tmp_path)
    config_path = db / "project_config.yaml"
    original = config_path.read_text(encoding="utf-8")
    assert "# technology:" in original  # sanity: scaffold's placeholder is still there

    with config_path.open("a", encoding="utf-8") as f:
        f.write("\ntechnology:\n  name: sky130\n")

    db_set_config(db, "technology", "gf180")

    updated = config_path.read_text(encoding="utf-8")
    active_lines = [line for line in updated.splitlines() if line == "technology:"]
    assert len(active_lines) == 1, f"expected exactly one active 'technology:' line, got: {active_lines!r}"
    data = yaml.safe_load(updated)
    assert data["technology"] == {"name": "gf180"}


def test_project_set_interface_null_clears_it(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "interface", "semicolab")
    project_set_config(config_path, "interface", "null")

    updated = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(updated)
    assert data["interface"] is None
    # written as the explicit `null` literal, not a value-less key
    assert "interface: null" in updated


def test_project_set_interface_null_writes_explicit_null_literal_when_never_active(tmp_path):
    """Same clear-to-null case, but on a fresh scaffold where `interface:`
    was never set active first -- exercises the uncomment-in-place path
    (the scaffold's `# interface:` placeholder is commented; it gets
    uncommented directly to `interface: null`) rather than the
    update-an-already-active-key path covered above."""
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "interface", "null")

    updated = config_path.read_text(encoding="utf-8")
    assert "interface: null" in updated
    data = yaml.safe_load(updated)
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


def test_project_set_rtl_sources_updates_yaml_as_list(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    (config_path.parent / "src").mkdir()
    (config_path.parent / "src" / "counter8.v").write_text("", encoding="utf-8")
    (config_path.parent / "src" / "edge_detector.v").write_text("", encoding="utf-8")

    project_set_config(config_path, "rtl-sources", "src/counter8.v,src/edge_detector.v")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["design"]["rtl_sources"] == ["src/counter8.v", "src/edge_detector.v"]


def test_project_set_rtl_sources_missing_file_warns_not_raises(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)

    with pytest.warns(UserWarning, match="VF_SET_SOURCE_NOT_FOUND"):
        result = project_set_config(config_path, "rtl-sources", "src/does_not_exist.v")

    assert result["value"] == "src/does_not_exist.v"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["design"]["rtl_sources"] == ["src/does_not_exist.v"]


def test_project_set_rtl_sources_empty_value_raises(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with pytest.raises(VeriFlowError) as exc_info:
        project_set_config(config_path, "rtl-sources", "  ,  ")
    assert exc_info.value.code == "VF_SET_SOURCE_LIST_EMPTY"


def test_project_set_tb_sources_updates_yaml_as_list(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    (config_path.parent / "tb").mkdir()
    (config_path.parent / "tb" / "tb_top.v").write_text("", encoding="utf-8")

    project_set_config(config_path, "tb-sources", "tb/tb_top.v")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["design"]["tb_sources"] == ["tb/tb_top.v"]


def test_project_set_tb_top_updates_yaml(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "tb-top", "tb_counter8")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["simulation"]["tb_top"] == "tb_counter8"


def test_project_set_name_updates_metadata(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "name", "Counter8 Tile")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["metadata"]["name"] == "Counter8 Tile"


def test_project_set_author_updates_metadata(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "author", "Roman Lugo")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["metadata"]["author"] == "Roman Lugo"


def test_project_set_version_updates_metadata(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "version", "2.0.0")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["metadata"]["version"] == "2.0.0"


def test_project_set_description_updates_metadata_as_block_scalar(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    project_set_config(config_path, "description", "An 8-bit counter with async reset.")

    text = config_path.read_text(encoding="utf-8")
    assert "description: |" in text
    data = yaml.safe_load(text)
    assert data["metadata"]["description"].strip() == "An 8-bit counter with async reset."


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


@pytest.mark.skipif(not _HAS_RUAMEL, reason="ruamel.yaml not installed in this environment")
def test_yaml_editor_ruamel_none_value_writes_explicit_null_literal(tmp_path):
    """ruamel's default null representer writes a value-less `key:` (empty
    after the colon) for a None value, not the `null` literal -- both
    parse back identically, but the task spec wants the literal written to
    disk. Covers the raw append path (no scaffold comment involved) and
    the update-an-existing-active-key path, both of which route through
    `_set_yaml_key_ruamel`'s direct ruamel dump (unlike the
    uncomment-in-place path, which has its own renderer and was already
    correct -- see test_project_set_interface_null_writes_explicit_null_
    literal_when_never_active)."""
    from veriflow.core.yaml_config_editor import set_yaml_key

    # brand new key, nothing to update or uncomment -- pure append path
    append_path = tmp_path / "append.yaml"
    append_path.write_text("a: 1\n", encoding="utf-8")
    set_yaml_key(append_path, ("b",), None)
    assert "b: null" in append_path.read_text(encoding="utf-8")

    # already-active key -- update-in-place path
    update_path = tmp_path / "update.yaml"
    update_path.write_text("a: 1\n", encoding="utf-8")
    set_yaml_key(update_path, ("a",), None)
    assert "a: null" in update_path.read_text(encoding="utf-8")


def test_yaml_editor_uncomments_existing_commented_key_in_place(tmp_path):
    """A key that exists only as a commented-out placeholder (e.g.
    `# c: 3`) is uncommented and updated in place -- not left as-is with a
    second, active copy appended at the end."""
    from veriflow.core.yaml_config_editor import set_yaml_key

    path = tmp_path / "config.yaml"
    path.write_text("# a commented example\n# c: 3\na: 1\n", encoding="utf-8")
    set_yaml_key(path, ("c",), 5)
    text = path.read_text(encoding="utf-8")
    assert "# a commented example" in text  # unrelated comment untouched
    assert "# c:" not in text
    assert text.count("c:") == 1
    data = yaml.safe_load(text)
    assert data["c"] == 5
    assert data["a"] == 1


def test_yaml_editor_prefers_active_key_over_stale_commented_placeholder(tmp_path):
    """Regression for the duplicate-section bug: when a key is *both*
    commented out (a leftover/stale placeholder) AND already active
    elsewhere in the file, the active one must be updated in place --
    uncommenting the stale placeholder too would create a second, active
    copy of the same top-level key."""
    from veriflow.core.yaml_config_editor import set_yaml_key

    path = tmp_path / "config.yaml"
    path.write_text(
        "# c: 3\n"
        "a: 1\n"
        "c:\n"
        "  child: value\n",
        encoding="utf-8",
    )
    set_yaml_key(path, ("c", "child"), "updated")
    text = path.read_text(encoding="utf-8")
    active_lines = [line for line in text.splitlines() if line == "c:"]
    assert len(active_lines) == 1, f"expected exactly one active 'c:' line, got: {active_lines!r}"
    assert "# c: 3" in text  # stale commented placeholder left untouched, not a bug per se
    data = yaml.safe_load(text)
    assert data["c"] == {"child": "updated"}
    assert data["a"] == 1


def test_yaml_editor_prefers_active_flat_key_over_stale_commented_placeholder(tmp_path):
    """Same regression as above, for a flat (1-element) key_path."""
    from veriflow.core.yaml_config_editor import set_yaml_key

    path = tmp_path / "config.yaml"
    path.write_text("# c: 3\na: 1\nc: old\n", encoding="utf-8")
    set_yaml_key(path, ("c",), "new")
    text = path.read_text(encoding="utf-8")
    active_lines = [line for line in text.splitlines() if line.startswith("c:")]
    assert len(active_lines) == 1, f"expected exactly one active 'c:' line, got: {active_lines!r}"
    data = yaml.safe_load(text)
    assert data["c"] == "new"


@pytest.mark.skipif(not _HAS_RUAMEL, reason="ruamel.yaml not installed in this environment")
def test_yaml_editor_ruamel_appends_new_key(tmp_path):
    """A key absent from the file entirely -- not even as a commented
    placeholder -- is still appended at the end (unchanged behavior)."""
    from veriflow.core.yaml_config_editor import set_yaml_key

    path = tmp_path / "config.yaml"
    path.write_text("# a commented example\na: 1\n", encoding="utf-8")
    set_yaml_key(path, ("c",), 3)
    text = path.read_text(encoding="utf-8")
    assert "# a commented example" in text
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


# ── yaml_config_editor: CI regression (2026-07-21) -- fallback bugs that only
#    manifest without ruamel.yaml installed, as in the actual CI environment
#    (ruamel is an optional extra, `setup.py`'s `yaml-edit`, never installed
#    by default). Each test below explicitly forces the fallback path via
#    HAS_RUAMEL=False, so these run deterministically in both environments
#    instead of silently only exercising ruamel whenever it happens to be
#    installed locally -- which is exactly how these 3 bugs shipped unnoticed
#    in the first place. ──────────────────────────────────────────────────────


def test_yaml_editor_fallback_clearing_active_nested_section_to_scalar_stays_valid_yaml(tmp_path):
    """Bug 1: clearing an already-active nested section (`interface:\\n
    name: semicolab`) to a plain scalar (`interface: null`) used to leave
    the old child line (`  name: semicolab`) behind, still indented under
    what is now a scalar value -- invalid YAML
    (yaml.scanner.ScannerError: "mapping values are not allowed here")."""
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text("design:\n  top_module: top\ninterface:\n  name: semicolab\n", encoding="utf-8")
    _set_yaml_key_fallback(path, ("interface",), None, block_scalar=False)
    text = path.read_text(encoding="utf-8")

    data = yaml.safe_load(text)  # must not raise ScannerError
    assert data["interface"] is None
    assert data["design"]["top_module"] == "top"
    assert "name: semicolab" not in text


def test_yaml_editor_fallback_uncomment_then_clear_matches_ci_repro(tmp_path):
    """The exact reported CI repro end to end: uncomment interface (from
    the scaffold's commented placeholder) then immediately clear it to
    null, both under the fallback -- must produce valid, reloadable YAML."""
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with patch("veriflow.core.yaml_config_editor.HAS_RUAMEL", False):
        project_set_config(config_path, "interface", "semicolab")
        project_set_config(config_path, "interface", "null")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # must not raise
    assert data["interface"] is None


def test_yaml_editor_fallback_nested_key_list_value_renders_as_yaml_list(tmp_path):
    """Bug 2: a list value for a nested key used to be rendered via
    _render_scalar(), which has no list handling and falls through to
    str(value) -- writing the literal Python repr string
    "['a.v', 'b.v']" as a quoted YAML scalar instead of a real list."""
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text("design:\n  top_module: top\n  rtl_sources: []\n", encoding="utf-8")
    _set_yaml_key_fallback(path, ("design", "rtl_sources"), ["src/counter8.v", "src/edge_detector.v"], block_scalar=False)
    text = path.read_text(encoding="utf-8")

    assert "['src/counter8.v', 'src/edge_detector.v']" not in text
    data = yaml.safe_load(text)
    assert data["design"]["rtl_sources"] == ["src/counter8.v", "src/edge_detector.v"]


def test_yaml_editor_fallback_replacing_existing_list_value_drops_old_items(tmp_path):
    """A second list-value write must replace the old `- item` lines, not
    just the key line, leaving stale entries behind."""
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - old_a.v\n    - old_b.v\nsimulation:\n  tb_top: tb\n",
        encoding="utf-8",
    )
    _set_yaml_key_fallback(path, ("design", "rtl_sources"), ["new.v"], block_scalar=False)
    text = path.read_text(encoding="utf-8")

    data = yaml.safe_load(text)
    assert data["design"]["rtl_sources"] == ["new.v"]
    assert data["simulation"]["tb_top"] == "tb"  # sibling untouched
    assert "old_a.v" not in text
    assert "old_b.v" not in text


def test_yaml_editor_fallback_rtl_sources_via_project_set_matches_ci_repro(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with patch("veriflow.core.yaml_config_editor.HAS_RUAMEL", False):
        project_set_config(config_path, "rtl-sources", "src/counter8.v,src/edge_detector.v")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["design"]["rtl_sources"] == ["src/counter8.v", "src/edge_detector.v"]


def test_yaml_editor_fallback_nested_block_scalar_writes_under_parent(tmp_path):
    """Bug 3: a nested block scalar (e.g. metadata.description) used to
    ignore the parent entirely, searching for `child_key` as a *top-level*
    key -- since no such top-level key exists, it got appended as a stray
    unrelated top-level section instead of nested under its real parent,
    so `data["metadata"]["description"]` raised KeyError('metadata')."""
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text("design:\n  top_module: top\n", encoding="utf-8")
    _set_yaml_key_fallback(
        path, ("metadata", "description"), "An 8-bit counter with async reset.", block_scalar=True
    )
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    assert "metadata" in data  # must not raise KeyError
    assert data["metadata"]["description"].strip() == "An 8-bit counter with async reset."


def test_yaml_editor_fallback_nested_block_scalar_updates_existing_in_place(tmp_path):
    from veriflow.core.yaml_config_editor import _set_yaml_key_fallback

    path = tmp_path / "config.yaml"
    path.write_text(
        "design:\n  top_module: top\nmetadata:\n  author: \"Roman Lugo\"\n  description: |\n    old text\n  version: \"1.0.0\"\n",
        encoding="utf-8",
    )
    _set_yaml_key_fallback(path, ("metadata", "description"), "new text", block_scalar=True)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    assert data["metadata"]["description"].strip() == "new text"
    assert data["metadata"]["author"] == "Roman Lugo"  # sibling before, untouched
    assert data["metadata"]["version"] == "1.0.0"  # sibling after, untouched
    assert "old text" not in text


def test_yaml_editor_fallback_metadata_description_via_project_set_matches_ci_repro(tmp_path):
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with patch("veriflow.core.yaml_config_editor.HAS_RUAMEL", False):
        project_set_config(config_path, "description", "An 8-bit counter with async reset.")

    text = config_path.read_text(encoding="utf-8")
    assert "description: |" in text
    data = yaml.safe_load(text)
    assert data["metadata"]["description"].strip() == "An 8-bit counter with async reset."


def test_yaml_editor_fallback_full_suite_matches_ci(tmp_path):
    """Broader smoke test: the same sequence of operations exercised across
    this whole file, all under the fallback -- confirms nothing regresses
    when every one of these bugs' fixes interact with each other."""
    from veriflow.commands.set_config import project_set_config

    config_path = _write_project_yaml(tmp_path)
    with patch("veriflow.core.yaml_config_editor.HAS_RUAMEL", False):
        project_set_config(config_path, "interface", "semicolab")
        project_set_config(config_path, "technology", "sky130")
        project_set_config(config_path, "rtl-sources", "src/counter8.v,src/edge_detector.v")
        project_set_config(config_path, "tb-sources", "tb/tb_top.v")
        project_set_config(config_path, "name", "Counter8 Tile")
        project_set_config(config_path, "author", "Roman Lugo")
        project_set_config(config_path, "description", "An 8-bit counter with async reset.")
        project_set_config(config_path, "version", "2.0.0")
        project_set_config(config_path, "interface", "null")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["interface"] is None
    assert data["technology"] == {"name": "sky130"}
    assert data["design"]["rtl_sources"] == ["src/counter8.v", "src/edge_detector.v"]
    assert data["design"]["tb_sources"] == ["tb/tb_top.v"]
    assert data["metadata"] == {
        "name": "Counter8 Tile",
        "author": "Roman Lugo",
        "description": "An 8-bit counter with async reset.\n",
        "version": "2.0.0",
    }


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
    project_set_config still produces valid, comment-preserving output.

    Uses "top-module" (design.top_module), an *already-active* key in the
    scaffold, rather than "interface" -- the commented-placeholder
    uncomment step runs regardless of HAS_RUAMEL and would otherwise
    short-circuit before this test ever reaches the fallback branch it's
    meant to exercise.
    """
    config_path = _write_project_yaml(tmp_path)
    original = config_path.read_text(encoding="utf-8")

    with patch("veriflow.core.yaml_config_editor.HAS_RUAMEL", False):
        from veriflow.commands.set_config import project_set_config

        project_set_config(config_path, "top-module", "counter8")

    updated = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(updated)
    assert data["design"]["top_module"] == "counter8"
    for line in original.splitlines():
        if line.strip().startswith("#"):
            assert line in updated
