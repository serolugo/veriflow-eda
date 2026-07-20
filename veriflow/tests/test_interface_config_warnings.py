"""Regression tests for interface config-parse-time warnings
(VF_INTERFACE_NAME_MISMATCH / VF_INTERFACE_PROFILE_OVERWRITTEN) being
surfaced as structured data -- results.json's "warnings" array, printed
via `print_warn()`'s clean CLI output -- instead of a raw Python
`warnings.warn()` UserWarning (2026-07-19 fix, following up on the
interface-URL feature's manual verification, which showed a raw
"UserWarning: ..." traceback in the terminal).

Covers both Project Mode (`veriflow project run`) and Database Mode
(`veriflow db run`).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veriflow.models.interface_profile import _PROFILE_FACTORIES


@pytest.fixture(autouse=True)
def _cleanup_registered_profiles():
    before = set(_PROFILE_FACTORIES)
    yield
    for name in set(_PROFILE_FACTORIES) - before:
        del _PROFILE_FACTORIES[name]


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
    b.run_synthesis.return_value = (
        status, {"cells": "1", "warnings": "0", "errors": "0", "has_latches": False}
    )
    return b


# ── Project Mode: no Python warning, results.json, CLI print_warn ────────────


def _make_project(tmp_path: Path, *, name: str = "wrong_name") -> Path:
    (tmp_path / "warntest_uniq_if.v").write_text(
        "module warntest_uniq_if(input clk); endmodule\n", encoding="utf-8"
    )
    (tmp_path / "top.v").write_text("module top(input clk); endmodule\n", encoding="utf-8")
    config_path = tmp_path / "veriflow.yaml"
    config_path.write_text(
        "design:\n  top_module: top\n  rtl_sources:\n    - top.v\n"
        f"interface:\n  name: {name}\n  definition: ./warntest_uniq_if.v\n",
        encoding="utf-8",
    )
    return config_path


def test_project_run_no_python_warning_emitted(tmp_path, recwarn):
    """The whole `project run` path, not just config parsing -- confirms
    no Python UserWarning escapes anywhere between config load and the
    finished run."""
    from veriflow.cli import main

    config_path = _make_project(tmp_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend()),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend()),
    ):
        rc = main(["project", "run", "--config", str(config_path)])
    # _make_project has no tb_sources -- simulation never ran, so the
    # overall status is PARTIAL (non-zero exit), not PASS (dev-docs/
    # TRACEABILITY_AUDIT.md Finding #4/#4b). Irrelevant to what this test
    # actually checks (no stray Python UserWarning), which is unaffected.
    assert rc == 1
    assert len(recwarn) == 0


def test_project_run_results_json_includes_interface_warning(tmp_path):
    from veriflow.cli import main

    config_path = _make_project(tmp_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend()),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend()),
    ):
        main(["project", "run", "--config", str(config_path)])

    results = json.loads((tmp_path / "runs" / "run-001" / "results.json").read_text(encoding="utf-8"))
    assert len(results["warnings"]) == 1
    assert "VF_INTERFACE_NAME_MISMATCH" in results["warnings"][0]


def test_project_run_cli_output_uses_print_warn_not_raw_userwarning(tmp_path, capsys):
    """The CLI's own output -- not just the underlying warning list --
    must show print_warn()'s clean `!` marker and never the words
    "UserWarning" or a Python source file path."""
    from veriflow.cli import main

    config_path = _make_project(tmp_path)
    with (
        patch("veriflow.workflows.project.validate_tools"),
        patch("veriflow.workflows.project.get_connectivity_backend", return_value=_mock_conn_backend()),
        patch("veriflow.workflows.project.get_synthesis_backend", return_value=_mock_synth_backend()),
    ):
        main(["project", "run", "--config", str(config_path)])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "VF_INTERFACE_NAME_MISMATCH" in combined
    assert "!" in captured.out  # print_warn()'s marker
    assert "UserWarning" not in combined
    assert ".py:" not in combined  # no "file.py:NNN: UserWarning: ..." traceback line


# ── Database Mode: no Python warning, results data, CLI print_warn ───────────


def _make_db_project(tmp_path: Path) -> Path:
    from veriflow.commands.init_db import cmd_init
    from veriflow.commands.create_tile import cmd_create_tile

    (tmp_path / "warntest_uniq_if.v").write_text(
        "module warntest_uniq_if(input clk); endmodule\n", encoding="utf-8"
    )
    db = tmp_path / "db"
    cmd_init(db)
    text = (
        'id_prefix: "TST-01"\nproject_name: "Test"\nrepo: ""\n'
        'interface_name: "wrong_name"\n'
        f'interface_definition: "{(tmp_path / "warntest_uniq_if.v").as_posix()}"\n'
        "description: |\n\n"
    )
    (db / "project_config.yaml").write_text(text, encoding="utf-8")

    cmd_create_tile(db, top_module="top")
    rtl_dir = db / "config" / "tile_0001" / "src" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
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


def test_db_run_no_python_warning_emitted(tmp_path, recwarn):
    from veriflow.cli import main

    db = _make_db_project(tmp_path)
    backends = _patched_db_backends()
    with backends[0], backends[1], backends[2], backends[3], backends[4]:
        rc = main(["db", "run", "--db", str(db), "--tile", "0001"])
    assert rc == 0
    assert len(recwarn) == 0


def test_db_run_results_data_includes_interface_warnings(tmp_path, capsys):
    from veriflow.cli import main

    db = _make_db_project(tmp_path)
    capsys.readouterr()  # discard cmd_init/cmd_create_tile's own Rich output
    backends = _patched_db_backends()
    with backends[0], backends[1], backends[2], backends[3], backends[4]:
        main(["--json", "db", "run", "--db", str(db), "--tile", "0001"])

    payload = json.loads(capsys.readouterr().out)
    warnings_list = payload["run_result"]["warnings"]
    assert any("VF_INTERFACE_NAME_MISMATCH" in w for w in warnings_list)
    assert any("VF_INTERFACE_PROFILE_OVERWRITTEN" in w for w in warnings_list)


def test_db_run_cli_output_uses_print_warn_not_raw_userwarning(tmp_path, capsys):
    from veriflow.cli import main

    db = _make_db_project(tmp_path)
    backends = _patched_db_backends()
    with backends[0], backends[1], backends[2], backends[3], backends[4]:
        main(["db", "run", "--db", str(db), "--tile", "0001"])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "VF_INTERFACE_NAME_MISMATCH" in combined or "VF_INTERFACE_PROFILE_OVERWRITTEN" in combined
    assert "!" in captured.out
    assert "UserWarning" not in combined
    assert ".py:" not in combined
