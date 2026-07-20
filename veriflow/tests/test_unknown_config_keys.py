"""Regression tests for unknown-top-level-key detection in
veriflow.yaml / project_config.yaml / tile_config.yaml (2026-07-19,
extended 2026-07-19).

Root cause this guards against: Database Mode's `ProjectConfig`/
`TileConfig` never rejected unrecognized top-level keys, so a config
written with Project Mode's `execution:` syntax (veriflow.yaml's
connectivity_backend/simulation_backend/synthesis_backend section --
Database Mode has no such section; backend selection there is per-stage
via `pipeline.stages[].backend`) was silently dropped with zero
indication why `execution.simulation_backend: xsim` had no effect at
all -- confirmed live: a real `db run` used `IcarusSimulationBackend`
despite `xsim` being configured.

Warnings are collected into `config_warnings` (same mechanism as
interface_definition's name-mismatch/profile-overwrite warnings, see
test_interface_config_warnings.py) -- never `warnings.warn()`.

Extended (dev-docs/MODE_CONSISTENCY_AUDIT.md, Finding 1): Project Mode's
`ProjectWorkflowConfig` had no equivalent check at all -- a typo'd
top-level key in `veriflow.yaml` (`desing:`, `tecnhology:`, ...) was
silently ignored with no warning, unlike either of Database Mode's two
schemas. `TestProjectWorkflowConfig*` below mirrors the same test shape
used for `ProjectConfig`/`TileConfig` above.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.models.project_config import ProjectConfig
from veriflow.models.tile_config import TileConfig


# ── ProjectConfig.from_dict: unit-level ───────────────────────────────────────


def _base_project_dict(**overrides) -> dict:
    data = {
        "id_prefix": "TST",
        "project_name": "smoke_test",
        "repo": "",
        "interface_name": None,
        "description": "",
    }
    data.update(overrides)
    return data


def test_project_config_known_keys_only_no_warnings():
    cfg = ProjectConfig.from_dict(_base_project_dict())
    assert cfg.config_warnings == []


def test_project_config_unknown_execution_key_warns_not_raises(recwarn):
    data = _base_project_dict(execution={"simulation_backend": "xsim"})
    cfg = ProjectConfig.from_dict(data)

    assert len(recwarn) == 0
    assert len(cfg.config_warnings) == 1
    warning = cfg.config_warnings[0]
    assert "execution" in warning
    assert "pipeline.stages[].backend" in warning
    assert "docs/PROJECT_CONFIG.md" in warning


def test_project_config_unknown_execution_key_rest_of_parse_continues_normally():
    """The unknown key doesn't block or corrupt parsing of everything else
    in the same document."""
    data = _base_project_dict(
        execution={"simulation_backend": "xsim"},
        id_prefix="TST-01",
        pipeline={"stages": [{"type": "connectivity"}, {"type": "simulation"}, {"type": "synthesis"}]},
    )
    cfg = ProjectConfig.from_dict(data)

    assert cfg.id_prefix == "TST-01"
    assert [s.type for s in cfg.pipeline.stages] == ["connectivity", "simulation", "synthesis"]
    assert len(cfg.config_warnings) == 1


def test_project_config_unrelated_unknown_key_generic_warning():
    data = _base_project_dict(some_typo_field=123)
    cfg = ProjectConfig.from_dict(data)

    assert len(cfg.config_warnings) == 1
    assert "some_typo_field" in cfg.config_warnings[0]
    assert "execution" not in cfg.config_warnings[0]


def test_project_config_multiple_unknown_keys_each_get_own_warning():
    data = _base_project_dict(execution={}, another_typo=True)
    cfg = ProjectConfig.from_dict(data)

    assert len(cfg.config_warnings) == 2
    joined = " ".join(cfg.config_warnings)
    assert "execution" in joined
    assert "another_typo" in joined


@pytest.mark.parametrize("key", [
    "id_prefix", "project_name", "repo", "description", "interface_name",
    "interface_definition", "id_format", "shuttle_name", "technology",
    "technology_definition", "pipeline",
])
def test_project_config_every_recognized_key_produces_no_warning(key, tmp_path):
    """Sanity sweep: none of the fields the parser actually reads should
    ever be mistaken for an unknown key."""
    data = _base_project_dict()
    if key == "interface_definition":
        pytest.skip("requires interface_name to also be set to a non-None value + a real .v file; covered elsewhere")
    if key == "technology_definition":
        pytest.skip("requires a real technology definition file on disk; covered elsewhere")
    if key == "technology":
        data["technology"] = {"name": "generic"}
    elif key == "pipeline":
        data["pipeline"] = {"stages": [{"type": "synthesis"}]}
    else:
        data[key] = data.get(key) or "x"
    cfg = ProjectConfig.from_dict(data, root=tmp_path)
    assert cfg.config_warnings == []


# ── TileConfig.from_dict: unit-level ──────────────────────────────────────────


def test_tile_config_known_keys_only_no_warnings():
    cfg = TileConfig.from_dict({"tile_name": "x", "top_module": "top"})
    assert cfg.config_warnings == []


def test_tile_config_unknown_execution_key_warns_not_raises(recwarn):
    cfg = TileConfig.from_dict({
        "tile_name": "x", "top_module": "top",
        "execution": {"simulation_backend": "xsim"},
    })

    assert len(recwarn) == 0
    assert len(cfg.config_warnings) == 1
    warning = cfg.config_warnings[0]
    assert "execution" in warning
    assert "pipeline.stages[].backend" in warning
    assert "docs/PROJECT_CONFIG.md" in warning


def test_tile_config_unrelated_unknown_key_generic_warning():
    cfg = TileConfig.from_dict({"tile_name": "x", "top_module": "top", "typo_field": 1})
    assert len(cfg.config_warnings) == 1
    assert "typo_field" in cfg.config_warnings[0]


# ── Database Mode end-to-end: CLI print_warn + results.json ──────────────────


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


def _mock_synth_backend(status="PASS"):
    from veriflow.core.backends.base import SynthesisBackend
    b = MagicMock(spec=SynthesisBackend)
    b.run_synthesis.return_value = (status, {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})
    return b


def _make_db_with_unknown_execution_key(tmp_path: Path) -> Path:
    from veriflow.commands.init_db import cmd_init
    from veriflow.commands.create_tile import cmd_create_tile

    db = tmp_path / "db"
    cmd_init(db)
    (db / "project_config.yaml").write_text(
        'id_prefix: "TST-01"\nproject_name: "Test"\nrepo: ""\n'
        'interface_name: null\ndescription: |\n\n'
        'pipeline:\n  stages:\n    - type: simulation\n    - type: synthesis\n'
        'execution:\n  simulation_backend: xsim\n',
        encoding="utf-8",
    )
    cmd_create_tile(db, top_module="top")
    rtl_dir = db / "config" / "tile_0001" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    tb_dir = db / "config" / "tile_0001" / "src" / "tb"
    tb_dir.mkdir(parents=True, exist_ok=True)
    (tb_dir / "tb_tile.v").write_text("module tb; endmodule\n", encoding="utf-8")
    return db


def _patched_db_backends():
    return (
        patch("veriflow.workflows.database.validate_tools"),
        patch("veriflow.workflows.database.detect_iverilog_version", return_value="12.0"),
        patch("veriflow.core.backends.icarus.IcarusConnectivityBackend.run_connectivity", return_value="PASS"),
        patch("veriflow.core.backends.icarus.IcarusSimulationBackend.run_simulation", return_value=("COMPLETED", {})),
        patch("veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
              return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False})),
    )


def test_db_run_results_data_includes_unknown_execution_key_warning(tmp_path, capsys):
    from veriflow.cli import main

    db = _make_db_with_unknown_execution_key(tmp_path)
    capsys.readouterr()  # discard cmd_init/cmd_create_tile's own Rich output
    backends = _patched_db_backends()
    with backends[0], backends[1], backends[2], backends[3], backends[4]:
        main(["--json", "db", "run", "--db", str(db), "--tile", "0001"])

    payload = json.loads(capsys.readouterr().out)
    warnings_list = payload["run_result"]["warnings"]
    assert any("execution" in w and "pipeline.stages[].backend" in w for w in warnings_list)


def test_db_run_cli_output_shows_warning_via_print_warn(tmp_path, capsys):
    from veriflow.cli import main

    db = _make_db_with_unknown_execution_key(tmp_path)
    backends = _patched_db_backends()
    with backends[0], backends[1], backends[2], backends[3], backends[4]:
        main(["db", "run", "--db", str(db), "--tile", "0001"])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "execution" in combined
    assert "pipeline.stages[].backend" in combined
    assert "!" in captured.out  # print_warn()'s marker
    assert "UserWarning" not in combined


# ── ProjectWorkflowConfig.from_dict: unit-level (Finding 1) ───────────────────


def _base_project_workflow_dict(**overrides) -> dict:
    data = {"design": {"top_module": "top", "rtl_sources": ["top.v"]}}
    data.update(overrides)
    return data


def test_project_workflow_config_known_keys_only_no_warnings(tmp_path):
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    cfg = ProjectWorkflowConfig.from_dict(_base_project_workflow_dict(), root=tmp_path)
    assert cfg.config_warnings == []


def test_project_workflow_config_unrelated_unknown_key_generic_warning(tmp_path):
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    data = _base_project_workflow_dict(desing={"oops": True})
    cfg = ProjectWorkflowConfig.from_dict(data, root=tmp_path)

    assert len(cfg.config_warnings) == 1
    assert "desing" in cfg.config_warnings[0]


def test_project_workflow_config_multiple_unknown_keys_each_get_own_warning(tmp_path):
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    data = _base_project_workflow_dict(tecnhology={"name": "generic"}, another_typo=True)
    cfg = ProjectWorkflowConfig.from_dict(data, root=tmp_path)

    assert len(cfg.config_warnings) == 2
    joined = " ".join(cfg.config_warnings)
    assert "tecnhology" in joined
    assert "another_typo" in joined


def test_project_workflow_config_unknown_key_does_not_block_parsing(tmp_path):
    """The unknown key doesn't block or corrupt parsing of everything else
    in the same document."""
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    data = _base_project_workflow_dict(
        bogus_key=1, design={"top_module": "top2", "rtl_sources": ["a.v", "b.v"]}
    )
    cfg = ProjectWorkflowConfig.from_dict(data, root=tmp_path)

    assert cfg.top_module == "top2"
    assert len(cfg.rtl_sources) == 2
    assert len(cfg.config_warnings) == 1


def test_project_workflow_config_unknown_key_warning_combines_with_interface_warnings(tmp_path):
    """config_warnings must include BOTH the unknown-top-level-key warning
    and interface.definition's own name-mismatch warning -- one doesn't
    overwrite the other."""
    from veriflow.models.interface_profile import _PROFILE_FACTORIES
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    before = set(_PROFILE_FACTORIES)
    try:
        (tmp_path / "custom_if.v").write_text(
            "module wrong_name(input wire clk); endmodule\n", encoding="utf-8"
        )
        data = _base_project_workflow_dict(
            interface={"name": "custom_if", "definition": "./custom_if.v"},
            bogus_key=1,
        )
        cfg = ProjectWorkflowConfig.from_dict(data, root=tmp_path)

        joined = " ".join(cfg.config_warnings)
        assert "bogus_key" in joined
        assert "VF_INTERFACE_NAME_MISMATCH" in joined
    finally:
        for name in set(_PROFILE_FACTORIES) - before:
            del _PROFILE_FACTORIES[name]


@pytest.mark.parametrize("key", [
    "design", "interface", "execution", "technology", "simulation",
    "output", "pipeline", "metadata", "readme_template",
])
def test_project_workflow_config_every_recognized_key_produces_no_warning(key, tmp_path):
    """Sanity sweep: none of veriflow.yaml's real top-level sections should
    ever be mistaken for an unknown key."""
    from veriflow.workflows.project_config import ProjectWorkflowConfig

    data = _base_project_workflow_dict()
    if key != "design":
        data[key] = None
    cfg = ProjectWorkflowConfig.from_dict(data, root=tmp_path)
    assert cfg.config_warnings == []


# ── Project Mode end-to-end: CLI print_warn + --json results.json ────────────


def _make_project_with_unknown_top_level_key(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    cfg_path = project_dir / "veriflow.yaml"
    cfg_path.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - top.v\n"
        "desing:\n  oops: true\n",
        encoding="utf-8",
    )
    return cfg_path


def _patched_project_synth_pass():
    return patch(
        "veriflow.core.backends.yosys.YosysSynthesisBackend.run_synthesis",
        return_value=("PASS", {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}),
    )


def test_project_run_results_data_includes_unknown_top_level_key_warning(tmp_path, capsys):
    """Also exercises Finding 3's fix (--json project run returns the full
    results.json) -- payload["run_result"] wouldn't exist at all otherwise."""
    from veriflow.cli import main

    cfg_path = _make_project_with_unknown_top_level_key(tmp_path)
    with patch("veriflow.workflows.project.validate_tools"), _patched_project_synth_pass():
        main(["--json", "project", "run", "--config", str(cfg_path)])

    payload = json.loads(capsys.readouterr().out)
    warnings_list = payload["run_result"]["warnings"]
    assert any("desing" in w for w in warnings_list)


def test_project_run_cli_output_shows_warning_via_print_warn(tmp_path, capsys):
    from veriflow.cli import main

    cfg_path = _make_project_with_unknown_top_level_key(tmp_path)
    with patch("veriflow.workflows.project.validate_tools"), _patched_project_synth_pass():
        main(["project", "run", "--config", str(cfg_path)])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "desing" in combined
    assert "!" in captured.out  # print_warn()'s marker
    assert "UserWarning" not in combined
