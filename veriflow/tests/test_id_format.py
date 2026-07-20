"""Regression tests for the configurable tile_id format design change
(2026-07-12): project_config.yaml's optional `id_format` field replaces the
previously-hardcoded tile_id layout.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from veriflow.core import VeriFlowError


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_db(tmp: Path) -> Path:
    db = tmp / "database"
    from veriflow.commands.init_db import cmd_init
    cmd_init(db)
    return db


def _write_project_config(
    db: Path,
    *,
    id_prefix: str = "TST-01",
    interface_name: str | None = None,
    id_format: str | None = None,
    shuttle_name: str | None = None,
    technology_name: str | None = None,
) -> None:
    cfg: dict = {
        "id_prefix": id_prefix,
        "project_name": "Test Project",
        "repo": "",
        "description": "Test project.",
        "interface_name": interface_name,
    }
    if id_format is not None:
        cfg["id_format"] = id_format
    if shuttle_name is not None:
        cfg["shuttle_name"] = shuttle_name
    if technology_name is not None:
        cfg["technology"] = {"name": technology_name}
    (db / "project_config.yaml").write_text(
        yaml.dump(cfg, default_flow_style=False), encoding="utf-8"
    )


# ── 1. ProjectConfig parsing ──────────────────────────────────────────────────


def test_project_config_default_id_format():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
    })
    assert cfg.id_format == "{prefix}-{date}{tile_number}{version}{revision}"
    assert cfg.shuttle_name == ""
    assert cfg.technology_name is None


def test_project_config_custom_id_format_parsed():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
        "id_format": "{prefix}-{tile_number}",
    })
    assert cfg.id_format == "{prefix}-{tile_number}"


def test_project_config_blank_id_format_falls_back_to_default():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
        "id_format": "   ",
    })
    assert cfg.id_format == "{prefix}-{date}{tile_number}{version}{revision}"


def test_project_config_shuttle_name_parsed():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
        "shuttle_name": "shuttle42",
    })
    assert cfg.shuttle_name == "shuttle42"


def test_project_config_technology_name_parsed():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
        "technology": {"name": "sky130"},
    })
    assert cfg.technology_name == "sky130"


def test_project_config_technology_absent_is_none():
    from veriflow.models.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict({
        "id_prefix": "X", "project_name": "P", "repo": "", "description": "",
        "interface_name": None,
    })
    assert cfg.technology_name is None


# ── 2. core.tile_id: compute_initials / format_tile_id ───────────────────────


def test_compute_initials_two_words():
    from veriflow.core.tile_id import compute_initials
    assert compute_initials("Roman Lugo") == "RL"


def test_compute_initials_single_word():
    from veriflow.core.tile_id import compute_initials
    assert compute_initials("Cher") == "C"


def test_compute_initials_empty_string():
    from veriflow.core.tile_id import compute_initials
    assert compute_initials("") == ""
    assert compute_initials("   ") == ""


def _all_placeholders(**overrides) -> dict:
    base = {
        "prefix": "TST-01",
        "date": "260712",
        "tile_number": "0002",
        "version": "01",
        "revision": "01",
        "shuttle_name": "",
        "interface": "semicolab",
        "technology": "generic",
        "author_initials": "",
        "short_hash": "000000",
    }
    base.update(overrides)
    return base


def test_format_tile_id_default_format():
    from veriflow.core.tile_id import format_tile_id
    result = format_tile_id(
        "{prefix}-{date}{tile_number}{version}{revision}", _all_placeholders()
    )
    assert result == "TST-01-26071200020101"


def test_format_tile_id_minimal_format():
    from veriflow.core.tile_id import format_tile_id
    result = format_tile_id("{prefix}-{tile_number}", _all_placeholders())
    assert result == "TST-01-0002"


def test_format_tile_id_shuttle_format():
    from veriflow.core.tile_id import format_tile_id
    result = format_tile_id(
        "{prefix}-{shuttle_name}-{tile_number}",
        _all_placeholders(shuttle_name="shuttle42"),
    )
    assert result == "TST-01-shuttle42-0002"


def test_format_tile_id_interface_and_dotted_version():
    from veriflow.core.tile_id import format_tile_id
    result = format_tile_id(
        "{prefix}-{interface}-{tile_number}-{version}.{revision}",
        _all_placeholders(),
    )
    assert result == "TST-01-semicolab-0002-01.01"


def test_format_tile_id_technology_and_author_initials():
    from veriflow.core.tile_id import format_tile_id
    result = format_tile_id(
        "{prefix}-{technology}-{author_initials}-{tile_number}",
        _all_placeholders(technology="sky130", author_initials="RL"),
    )
    assert result == "TST-01-sky130-RL-0002"


def test_format_tile_id_unknown_placeholder_raises_veriflow_error():
    from veriflow.core.tile_id import format_tile_id
    with pytest.raises(VeriFlowError) as exc_info:
        format_tile_id("{prefix}-{typo}", _all_placeholders())
    assert exc_info.value.code == "VF_ID_FORMAT_INVALID"
    assert "typo" in str(exc_info.value)


def test_format_tile_id_malformed_format_raises_veriflow_error():
    from veriflow.core.tile_id import format_tile_id
    with pytest.raises(VeriFlowError) as exc_info:
        format_tile_id("{prefix}-{unclosed", _all_placeholders())
    assert exc_info.value.code == "VF_ID_FORMAT_INVALID"


# ── 3. cmd_create_tile end-to-end with custom id_format ──────────────────────


def test_create_tile_default_id_format_unchanged(tmp_path):
    """Databases that don't set id_format keep generating the legacy layout."""
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01")
    cmd_create_tile(db)

    row = get_tile_row(db / "tile_index.csv", "0001")
    tile_id = row["tile_id"]
    today_str = date.today().strftime("%y%m%d")
    assert tile_id == f"TST-01-{today_str}00010101"


def test_create_tile_minimal_id_format(tmp_path):
    """--top-level scenario from the task: id_format '{prefix}-{tile_number}'."""
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01", id_format="{prefix}-{tile_number}")
    cmd_create_tile(db)

    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01-0001"

    # a second tile increments tile_number, not any date/version noise
    cmd_create_tile(db)
    row2 = get_tile_row(db / "tile_index.csv", "0002")
    assert row2["tile_id"] == "TST-01-0002"


def test_create_tile_shuttle_name_id_format(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01",
        id_format="{prefix}-{shuttle_name}-{tile_number}",
        shuttle_name="shuttle42",
    )
    cmd_create_tile(db)
    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01-shuttle42-0001"


# ── tile_id path safety (2026-07-19, dev-docs/SECURITY_AUDIT.md #2) ──────────
# format_tile_id() is a raw str.format() with no output sanitization -- the
# resulting tile_id is used directly as tiles/<tile_id>/'s directory name
# (commands/create_tile.py). shuttle_name/id_prefix are both plain
# user-controlled strings (`db set shuttle`/`db set prefix`), so a value
# containing "../" reaching tile_id via a placeholder is the attack surface,
# not a hypothetical -- this is the same shuttle_name value and id_format
# shape as test_create_tile_shuttle_name_id_format above, just with a
# malicious shuttle_name instead of a normal one.

def test_create_tile_shuttle_name_traversal_rejected(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core import VeriFlowError

    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01",
        id_format="{prefix}-{shuttle_name}-{tile_number}",
        shuttle_name="../../../ESCAPED",
    )
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_create_tile(db)
    assert exc_info.value.code == "VF_UNSAFE_PATH"
    assert not (tmp_path / "ESCAPED").exists()
    # no tile directory left behind under the database either (tiles/
    # itself always has a scaffold .gitkeep from db init -- only real tile
    # subdirectories matter here)
    assert [p for p in (db / "tiles").iterdir() if p.is_dir()] == []


def test_create_tile_prefix_traversal_rejected(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core import VeriFlowError

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="../../../ESCAPED")
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_create_tile(db)
    assert exc_info.value.code == "VF_UNSAFE_PATH"
    assert not (tmp_path / "ESCAPED").exists()


def test_create_tile_shuttle_name_absolute_path_traversal_rejected(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core import VeriFlowError

    escape_target = tmp_path / "ESCAPED"
    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01",
        id_format="{shuttle_name}",
        shuttle_name=str(escape_target).replace("\\", "/"),
    )
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_create_tile(db)
    assert exc_info.value.code == "VF_UNSAFE_PATH"
    assert not escape_target.exists()


def test_create_tile_interface_id_format(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01", interface_name="semicolab",
        id_format="{prefix}-{interface}-{tile_number}-{version}.{revision}",
    )
    cmd_create_tile(db, top_module="my_tile")
    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01-semicolab-0001-01.01"


def test_create_tile_technology_id_format_defaults_to_generic(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01", id_format="{prefix}-{technology}-{tile_number}")
    cmd_create_tile(db)
    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01-generic-0001"


def test_create_tile_technology_id_format_configured(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01",
        id_format="{prefix}-{technology}-{tile_number}",
        technology_name="sky130",
    )
    cmd_create_tile(db)
    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01-sky130-0001"


def test_create_tile_author_initials_id_format(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01", id_format="{prefix}-{author_initials}-{tile_number}",
    )
    cmd_create_tile(db, tile_author="Roman Lugo")
    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01-RL-0001"


def test_create_tile_author_initials_blank_when_no_tile_author(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01", id_format="{prefix}-{author_initials}-{tile_number}",
    )
    cmd_create_tile(db)
    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01--0001"


def test_create_tile_tile_author_written_into_tile_config(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01")
    cmd_create_tile(db, tile_author="Roman Lugo")

    tile_cfg_text = (db / "config" / "tile_0001" / "tile_config.yaml").read_text(encoding="utf-8")
    assert 'tile_author: "Roman Lugo"' in tile_cfg_text


def test_create_tile_unknown_placeholder_raises_id_format_invalid(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01", id_format="{prefix}-{bogus}")
    with pytest.raises(VeriFlowError) as exc_info:
        cmd_create_tile(db)
    assert exc_info.value.code == "VF_ID_FORMAT_INVALID"


def test_create_tile_short_hash_warns_and_substitutes_000000(tmp_path, capsys):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(
        db, id_prefix="TST-01", id_format="{prefix}-{tile_number}-{short_hash}",
    )
    cmd_create_tile(db)

    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["tile_id"] == "TST-01-0001-000000"

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "VF_ID_PLACEHOLDER_UNAVAILABLE" in combined
    assert "short_hash" in combined


def test_create_tile_no_short_hash_warning_when_not_used(tmp_path, capsys):
    from veriflow.commands.create_tile import cmd_create_tile

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01", id_format="{prefix}-{tile_number}")
    cmd_create_tile(db)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "VF_ID_PLACEHOLDER_UNAVAILABLE" not in combined


# ── 4. bump-version / bump-revision guard for incompatible custom id_format ──


def test_bump_version_fails_cleanly_on_custom_incompatible_id_format(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.commands.bump_version import cmd_bump_version

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01", id_format="{prefix}-{tile_number}")
    cmd_create_tile(db)

    with pytest.raises(VeriFlowError) as exc_info:
        cmd_bump_version(db, "0001")
    assert exc_info.value.code == "VF_TILE_ID_BUMP_UNSUPPORTED_FORMAT"


def test_bump_revision_fails_cleanly_on_custom_incompatible_id_format(tmp_path):
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.commands.bump_revision import cmd_bump_revision

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01", id_format="{prefix}-{tile_number}")
    cmd_create_tile(db)

    with pytest.raises(VeriFlowError) as exc_info:
        cmd_bump_revision(db, "0001")
    assert exc_info.value.code == "VF_TILE_ID_BUMP_UNSUPPORTED_FORMAT"


def test_bump_version_still_works_with_default_id_format(tmp_path):
    """Regression guard: default id_format must remain fully compatible with
    bump-version's legacy parse_tile_id/generate_tile_id path."""
    from veriflow.commands.create_tile import cmd_create_tile
    from veriflow.commands.bump_version import cmd_bump_version
    from veriflow.core.csv_store import get_tile_row

    db = _make_db(tmp_path)
    _write_project_config(db, id_prefix="TST-01")
    cmd_create_tile(db)

    cmd_bump_version(db, "0001")
    row = get_tile_row(db / "tile_index.csv", "0001")
    assert row["version"] == "02"
    assert row["revision"] == "01"


# ── 5. CLI plumbing: --tile-author ────────────────────────────────────────────


def test_cli_create_tile_tile_author_flag_parses(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args([
        "db", "create-tile", "--db", str(tmp_path), "--tile-author", "Roman Lugo",
    ])
    assert args.tile_author == "Roman Lugo"


def test_cli_create_tile_tile_author_defaults_to_empty(tmp_path):
    from veriflow.cli import build_parser
    args = build_parser().parse_args(["db", "create-tile", "--db", str(tmp_path)])
    assert args.tile_author == ""
